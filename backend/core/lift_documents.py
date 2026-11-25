from zoneinfo import ZoneInfo

from django.db import transaction
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import serializers
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response

from .access import MemberAccess, admin_user, audit, org
from .models import Elevator, LiftDocument, LiftDocumentFolder, Organization
from .uploads import MAX_FILE_BYTES, MAX_FILE_MB

PRIVATE = {'Cache-Control': 'private, no-store'}


class DocumentFilter(serializers.Serializer):
    elevator = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    category = serializers.ChoiceField(choices=LiftDocument.Category.choices)


class DocumentUpload(DocumentFilter):
    elevator = serializers.IntegerField(min_value=1, max_value=2**63-1, required=False)
    category = serializers.ChoiceField(choices=LiftDocument.Category.choices, required=False)
    folder = serializers.IntegerField(min_value=1, max_value=2**63-1, required=False)
    title = serializers.CharField(max_length=200)
    file = serializers.FileField()

    def validate(self, data):
        if not data.get('folder') and ('elevator' not in data or 'category' not in data):
            raise ValidationError('Укажите папку либо лифт и тип документа.')
        return data

    def validate_file(self, upload):
        if not 5 <= upload.size <= MAX_FILE_BYTES or upload.read(5) != b'%PDF-':
            raise ValidationError(f'Выберите PDF до {MAX_FILE_MB} МБ.')
        upload.seek(0)
        return upload


class InspectionDate(serializers.Serializer):
    date = serializers.DateField(allow_null=True)


def _require_admin(user):
    if not admin_user(user):
        raise PermissionDenied('Раздел документов доступен администратору.')


def _active_documents(company):
    from django.db.models import Q
    from .lift_document_folders import catalog
    _, _, active = catalog(company)
    return LiftDocument.objects.filter(organization=company, deleted_at__isnull=True).filter(
        Q(folder__isnull=True) | Q(folder_id__in=active)).filter(
        Q(elevator__isnull=True) | Q(elevator__organization=company)).select_related('elevator__building')


def _for_lift(rows, company, elevator_id):
    from django.db.models import Q
    from .lift_document_folders import catalog
    _, effective, _ = catalog(company)
    return rows.filter(Q(folder_id__in=[fid for fid, ids in effective.items() if elevator_id in ids]) |
                       Q(folder__isnull=True, elevator_id=elevator_id))


def _item(doc):
    return {'id': doc.pk, 'title': doc.title, 'category': doc.category,
            'folder': doc.folder_id, 'elevator_id': doc.elevator_id,
            'address': doc.elevator.building.address if doc.elevator_id else '',
            'created_at': doc.created_at, 'updated_at': doc.updated_at,
            'url': f'/api/lift-documents/{doc.pk}/pdf/?organization={doc.organization_id}'}


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
def documents(request):
    _require_admin(request.user)
    company = org(request.user)
    if request.method == 'GET':
        fields = DocumentFilter(data=request.query_params)
        fields.is_valid(raise_exception=True)
        get_object_or_404(Elevator, pk=fields.validated_data['elevator'], organization=company)
        rows = _for_lift(_active_documents(company), company, fields.validated_data['elevator']).filter(category=fields.validated_data['category'])
        return Response([_item(doc) for doc in rows], headers=PRIVATE)

    fields = DocumentUpload(data=request.data)
    fields.is_valid(raise_exception=True)
    data = fields.validated_data
    doc = LiftDocument(organization=company, category=data.get('category', 'CONTRACT'), title=data['title'])
    try:
        with transaction.atomic():
            Organization.objects.select_for_update().get(pk=company.pk)
            if data.get('folder'):
                from .lift_document_folders import catalog
                _, _, active = catalog(company)
                doc.folder = get_object_or_404(LiftDocumentFolder, pk=data['folder'], organization=company, pk__in=active)
            else:
                doc.elevator = get_object_or_404(Elevator, pk=data['elevator'], organization=company)
            doc.file.save('document.pdf', data['file'], save=False)
            doc.save()
            audit(request.user, 'lift_document.upload', doc.pk,
                  {'elevator': doc.elevator_id, 'folder': doc.folder_id, 'category': doc.category})
    except Exception:
        if doc.file:
            doc.file.delete(save=False)
        raise
    return Response(_item(doc), status=201, headers=PRIVATE)


@api_view(['DELETE', 'PATCH'])
@permission_classes([MemberAccess])
@transaction.atomic
def remove(request, document_id):
    _require_admin(request.user)
    company = org(request.user)
    Organization.objects.select_for_update().get(pk=company.pk)
    doc = get_object_or_404(_active_documents(company).select_for_update(), pk=document_id)
    if request.method == 'PATCH':
        class Rename(serializers.Serializer):
            title = serializers.CharField(max_length=200)
            expected_updated_at = serializers.DateTimeField(required=True)
        fields = Rename(data=request.data)
        fields.is_valid(raise_exception=True)
        if fields.validated_data['expected_updated_at'] != doc.updated_at:
            raise ValidationError('Документ уже изменён. Обновите список.')
        doc.title, doc.updated_at = fields.validated_data['title'], timezone.now()
        doc.save(update_fields=['title', 'updated_at'])
        audit(request.user, 'lift_document.rename', doc.pk)
        return Response(_item(doc), headers=PRIVATE)
    doc.deleted_at = doc.updated_at = timezone.now()
    doc.save(update_fields=['deleted_at', 'updated_at'])
    audit(request.user, 'lift_document.delete', doc.pk,
          {'elevator': doc.elevator_id, 'category': doc.category})
    return Response(status=204, headers=PRIVATE)


@api_view(['GET'])
@permission_classes([MemberAccess])
def pdf(request, document_id):
    rows = _active_documents(org(request.user))
    doc = get_object_or_404(rows, pk=document_id)
    if not admin_user(request.user):
        if doc.folder_id:
            from .access import role
            from .lift_document_folders import catalog
            _, effective, _ = catalog(org(request.user))
            if role(request.user) == 'ADJUSTER' or not effective.get(doc.folder_id):
                raise NotFound()
        elif doc.category != LiftDocument.Category.INSPECTION or not doc.elevator_id:
            raise NotFound()
    try:
        file = doc.file.open('rb')
    except FileNotFoundError:
        raise NotFound('Файл документа отсутствует.')
    response = FileResponse(file, filename=f'lift-document-{doc.pk}.pdf', content_type='application/pdf')
    response['Cache-Control'] = PRIVATE['Cache-Control']
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['GET', 'PATCH'])
@permission_classes([MemberAccess])
def inspection(request, elevator_id):
    company = org(request.user)
    if request.method == 'PATCH':
        _require_admin(request.user)
        fields = InspectionDate(data=request.data)
        fields.is_valid(raise_exception=True)
        date = fields.validated_data['date']
        if date and date < timezone.localdate(timezone=ZoneInfo(company.timezone)):
            raise ValidationError({'date': 'Укажите сегодняшнюю или будущую дату.'})
        with transaction.atomic():
            elevator = get_object_or_404(Elevator.objects.select_for_update(), pk=elevator_id,
                                         organization=company, active=True)
            previous = elevator.next_inspection_on
            if previous != date:
                elevator.next_inspection_on = date
                elevator.save(update_fields=['next_inspection_on'])
                audit(request.user, 'lift_inspection.schedule', elevator.pk,
                      {'date': date.isoformat() if date else None})
    else:
        elevator = get_object_or_404(Elevator, pk=elevator_id, organization=company)
    acts = _for_lift(_active_documents(company), company, elevator.pk).filter(category=LiftDocument.Category.INSPECTION)
    return Response({'date': elevator.next_inspection_on, 'acts': [_item(doc) for doc in acts]}, headers=PRIVATE)
