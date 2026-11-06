import csv
import io
import warnings
from datetime import datetime, timedelta, time
from zoneinfo import ZoneInfo
from django.contrib.auth import logout
from django.core.files.base import ContentFile
from django.db import transaction
from django.http import FileResponse, HttpResponse
from django.middleware.csrf import get_token
from django.utils import timezone
from django.views.decorators.cache import never_cache
from PIL import Image, ImageOps, UnidentifiedImageError
from rest_framework import mixins
from rest_framework.decorators import api_view, permission_classes, action
from rest_framework.exceptions import PermissionDenied, ValidationError
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.viewsets import ModelViewSet, GenericViewSet
from rest_framework.throttling import UserRateThrottle
from .models import Building, Elevator, Maintenance, Technician, Ticket, Organization, DutyShift, PartRequest, ChatMessage, Document, TicketPhoto, AuditEvent
from .serializers import BuildingSerializer, ElevatorSerializer, MaintenanceSerializer, TechnicianSerializer, TicketSerializer, DutySerializer, PartSerializer, ChatSerializer, DocumentSerializer
from .access import MemberAccess, ManagerWrite, org, role, manager, admin_user, technician_id, audit
from .scheduling import preview_plan, apply_plan


@api_view(['GET'])
@permission_classes([AllowAny])
def health(request):
    return Response({'status':'ok','service':'LiftControl API','version':'0.4'})


@never_cache
@api_view(['GET'])
@permission_classes([MemberAccess])
def me(request):
    organization = org(request.user)
    return Response({'id':request.user.id,'name':request.user.get_full_name() or request.user.username,'role':role(request.user),
        'organization':organization.name,'timezone':organization.timezone,'technician':technician_id(request.user),
        'can_manage':manager(request.user),'can_export_chat':admin_user(request.user),'is_superuser':request.user.is_superuser,
        'csrf':get_token(request)})


@api_view(['POST'])
@permission_classes([MemberAccess])
def sign_out(request):
    logout(request)
    return Response({'ok':True})


@api_view(['GET'])
@permission_classes([MemberAccess])
def dashboard(request):
    organization = org(request.user)
    today = timezone.localdate()
    return Response({'buildings':Building.objects.filter(organization=organization).count(),
        'elevators':Elevator.objects.filter(organization=organization,active=True).count(),
        'technicians':Technician.objects.filter(organization=organization,active=True).count(),
        'open_tickets':Ticket.objects.filter(organization=organization).exclude(status__in=['DONE','CANCELED']).count(),
        'maintenance_today':Maintenance.objects.filter(organization=organization,planned_date=today).count()})


class TenantViewSet(ModelViewSet):
    permission_classes = [ManagerWrite]
    http_method_names = ['get','post','patch','head','options']
    def get_queryset(self):
        return super().get_queryset().filter(organization=org(self.request.user))
    def perform_create(self,serializer):
        obj = serializer.save(organization=org(self.request.user))
        audit(self.request.user, self.basename+'.create', obj.pk)
    def perform_update(self,serializer):
        obj = serializer.save()
        audit(self.request.user, self.basename+'.update', obj.pk)


class BuildingViewSet(TenantViewSet):
    queryset = Building.objects.all()
    serializer_class = BuildingSerializer


class TechnicianViewSet(TenantViewSet):
    queryset = Technician.objects.all()
    serializer_class = TechnicianSerializer


class ElevatorViewSet(TenantViewSet):
    queryset = Elevator.objects.select_related('building','assigned_technician').all()
    serializer_class = ElevatorSerializer
    @action(detail=True,methods=['get'])
    def documents(self,request,pk=None):
        elevator = self.get_object()
        # No manual attachments to individual lifts; match the shared library.
        docs = Document.objects.filter(organization=org(request.user),manufacturer__iexact=elevator.manufacturer)
        docs = [d for d in docs if not d.model or d.model.casefold() == elevator.model.casefold()]
        return Response(DocumentSerializer(docs,many=True).data)


class TicketViewSet(TenantViewSet):
    permission_classes = [MemberAccess]
    queryset = Ticket.objects.select_related('elevator__building','assigned_to').all()
    serializer_class = TicketSerializer
    def can_repair(self,ticket):
        if not manager(self.request.user) and ticket.assigned_to_id != technician_id(self.request.user):
            raise PermissionDenied('Фотографии изменяет исполнитель или руководитель.')
    @action(detail=True,methods=['post'])
    def photos(self,request,pk=None):
        ticket = self.get_object()
        self.can_repair(ticket)
        upload = request.FILES.get('file')
        if not upload or upload.size > 10*1024*1024:
            raise ValidationError('Выберите изображение до 10 МБ.')
        try:
            with warnings.catch_warnings():
                warnings.simplefilter('error',Image.DecompressionBombWarning)
                img = Image.open(upload)
                if img.format not in ('JPEG','PNG','WEBP') or img.width*img.height > 32000000:
                    raise ValueError()
                img.load()
                img = ImageOps.exif_transpose(img).convert('RGB')
                img.thumbnail((2560,2560))
                buf = io.BytesIO()
                img.save(buf,format='JPEG',quality=88)
        except (UnidentifiedImageError,OSError,ValueError,Image.DecompressionBombWarning,Image.DecompressionBombError):
            raise ValidationError('Не удалось прочитать JPEG, PNG или WebP до 32 Мп.')
        photo = None
        try:
            with transaction.atomic():
                Ticket.objects.select_for_update().get(pk=ticket.pk)
                if ticket.photos.filter(deleted_at__isnull=True).count() >= 8:
                    raise ValidationError('В заявке допускается до 8 фотографий.')
                photo = TicketPhoto(organization=org(request.user),ticket=ticket,uploaded_by=request.user)
                photo.file.save('repair.jpg',ContentFile(buf.getvalue()),save=False)
                photo.save()
                audit(request.user,'ticket.photo.add',ticket.pk)
        except Exception:
            if photo and photo.file.name:
                photo.file.delete(save=False)
            raise
        return Response({'id':photo.pk,'url':f'/api/tickets/{ticket.pk}/photos/{photo.pk}/'},status=201)
    @action(detail=True,methods=['get','delete'],url_path=r'photos/(?P<photo_id>\d+)')
    def photo(self,request,pk=None,photo_id=None):
        ticket = self.get_object()
        from django.shortcuts import get_object_or_404
        photo = get_object_or_404(ticket.photos,pk=photo_id,deleted_at__isnull=True)
        if request.method == 'DELETE':
            self.can_repair(ticket)
            photo.deleted_at = timezone.now()
            photo.save(update_fields=['deleted_at'])
            audit(request.user,'ticket.photo.remove',photo.pk)
            return Response(status=204)
        response = FileResponse(photo.file.open('rb'),content_type='image/jpeg')
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response
    # DELETE is available only on the photo action; never on ticket records.
    http_method_names = ['get','post','patch','delete','head','options']
    def destroy(self,request,*args,**kwargs):
        raise PermissionDenied('История заявок не удаляется. Используйте статус «Отменена».')


class MaintenanceViewSet(TenantViewSet):
    permission_classes = [MemberAccess]
    queryset = Maintenance.objects.select_related('elevator__building','technician').all()
    serializer_class = MaintenanceSerializer


class DutyViewSet(TenantViewSet):
    queryset = DutyShift.objects.select_related('technician').all()
    serializer_class = DutySerializer
    http_method_names = ['get','post','patch','delete','head','options']
    def get_queryset(self):
        q = super().get_queryset()
        start,end = self.request.query_params.get('from'),self.request.query_params.get('to')
        if start and end:
            try:
                tz = ZoneInfo(org(self.request.user).timezone)
                a = datetime.combine(datetime.strptime(start,'%Y-%m-%d').date(),time.min,tzinfo=tz)
                b = datetime.combine(datetime.strptime(end,'%Y-%m-%d').date()+timedelta(days=1),time.min,tzinfo=tz)
                if not 0 < (b-a).days <= 366:
                    raise ValueError()
                q = q.filter(start__lt=b,end__gt=a)
            except ValueError:
                raise ValidationError('Неверный период; максимум 366 дней.')
        return q
    @transaction.atomic
    def create(self,request,*args,**kwargs):
        Organization.objects.select_for_update().get(pk=org(request.user).pk)
        return super().create(request,*args,**kwargs)
    @transaction.atomic
    def update(self,request,*args,**kwargs):
        Organization.objects.select_for_update().get(pk=org(request.user).pk)
        return super().update(request,*args,**kwargs)
    @transaction.atomic
    def destroy(self,request,*args,**kwargs):
        Organization.objects.select_for_update().get(pk=org(request.user).pk)
        shift = self.get_object()
        audit(request.user,'duty.remove',shift.pk)
        shift.delete()
        return Response(status=204)
    @action(detail=False,methods=['post'])
    def preview(self,request):
        return Response(preview_plan(request.user,request.data))
    @action(detail=False,methods=['post'])
    def apply(self,request):
        return Response(apply_plan(request.user,request.data.get('token','')))


class PartViewSet(TenantViewSet):
    permission_classes = [MemberAccess]
    queryset = PartRequest.objects.select_related('elevator__building','requested_by').all()
    serializer_class = PartSerializer
    def perform_create(self,serializer):
        part = serializer.save(organization=org(self.request.user),requested_by=self.request.user)
        audit(self.request.user,'part.create',part.pk)


class ChatThrottle(UserRateThrottle):
    rate = '30/minute'


class ChatViewSet(mixins.ListModelMixin,mixins.CreateModelMixin,GenericViewSet):
    permission_classes = [MemberAccess]
    queryset = ChatMessage.objects.select_related('author').all()
    serializer_class = ChatSerializer
    throttle_classes = [ChatThrottle]
    def get_queryset(self):
        q = super().get_queryset().filter(organization=org(self.request.user))
        if self.action == 'export':
            start,end = self.request.query_params.get('from'),self.request.query_params.get('to')
            try:
                tz = ZoneInfo(org(self.request.user).timezone)
                a = datetime.combine(datetime.strptime(start,'%Y-%m-%d').date(),time.min,tzinfo=tz)
                b = datetime.combine(datetime.strptime(end,'%Y-%m-%d').date()+timedelta(days=1),time.min,tzinfo=tz)
                if not 0 < (b-a).days <= 366:
                    raise ValueError()
            except (ValueError,TypeError):
                raise ValidationError('Выберите период выгрузки до 366 дней.')
            return q.filter(created_at__gte=a,created_at__lt=b)
        # Newest 200 messages returned oldest-first; bounded UI without leaking other tenants.
        ids = q.order_by('-id').values_list('id',flat=True)[:200]
        return q.filter(id__in=ids).order_by('id')
    def perform_create(self,serializer):
        msg = serializer.save(organization=org(self.request.user),author=self.request.user)
        audit(self.request.user,'chat.send',msg.pk)
    @action(detail=False,methods=['get'])
    def export(self,request):
        if not admin_user(request.user):
            raise PermissionDenied('Выгрузка чата доступна только администратору.')
        output = io.StringIO()
        writer = csv.writer(output)
        writer.writerow(['Дата','Автор','Сообщение'])
        def safe(text):
            text = str(text)
            return "'"+text if text.lstrip().startswith(('=','+','-','@')) or text.startswith(('\t','\r','\n')) else text
        for msg in self.get_queryset().iterator():
            writer.writerow([timezone.localtime(msg.created_at).isoformat(),safe((msg.author.get_full_name() or msg.author.username) if msg.author else 'Удалённый пользователь'),safe(msg.body)])
        audit(request.user,'chat.export')
        response = HttpResponse('\ufeff'+output.getvalue(),content_type='text/csv; charset=utf-8')
        response['Content-Disposition']='attachment; filename="LiftControl-chat.csv"'
        response['Cache-Control']='private, no-store'
        return response


class DocumentViewSet(TenantViewSet):
    queryset = Document.objects.all()
    serializer_class = DocumentSerializer
    http_method_names = ['get','post','head','options']
    def perform_create(self,serializer):
        upload = self.request.FILES.get('file')
        if not upload or upload.size > 20*1024*1024 or upload.read(5) != b'%PDF-':
            raise ValidationError('Выберите PDF до 20 МБ.')
        upload.seek(0)
        document = serializer.save(organization=org(self.request.user),file=upload)
        audit(self.request.user,'document.create',document.pk)
    @action(detail=True,methods=['get'])
    def download(self,request,pk=None):
        doc = self.get_object()
        response = FileResponse(doc.file.open('rb'),as_attachment=True,filename=f'document-{doc.pk}.pdf',content_type='application/pdf')
        response['Cache-Control']='private, no-store'
        response['X-Content-Type-Options']='nosniff'
        return response


@api_view(['GET'])
@permission_classes([MemberAccess])
def audit_events(request):
    if not admin_user(request.user):
        raise PermissionDenied()
    return Response(list(AuditEvent.objects.filter(organization=org(request.user)).values('id','created_at','action','object_id','actor_id')[:200]))
