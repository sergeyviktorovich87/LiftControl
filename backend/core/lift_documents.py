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
from .models import Elevator, LiftDocument

PRIVATE = {'Cache-Control': 'private, no-store'}


class DocumentFilter(serializers.Serializer):
    elevator = serializers.IntegerField(min_value=1, max_value=2**63 - 1)
    category = serializers.ChoiceField(choices=LiftDocument.Category.choices)


class DocumentUpload(DocumentFilter):
    title = serializers.CharField(max_length=200)
    file = serializers.FileField()

    def validate_file(self, upload):
        if not 5 <= upload.size <= 20 * 1024**2 or upload.read(5) != b'%PDF-':
            raise ValidationError('Выберите PDF до 20 МБ.')
        upload.seek(0)
        return upload


class InspectionDate(serializers.Serializer):
    date = serializers.DateField(allow_null=True)


def _require_admin(user):
    if not admin_user(user):
        raise PermissionDenied('Раздел документов доступен администратору.')


def _active_documents(company):
    return LiftDocument.objects.filter(organization=company, elevator__organization=company,
                                       deleted_at__isnull=True)


def _item(doc):
    return {'id': doc.pk, 'title': doc.title, 'category': doc.category,
            'created_at': doc.created_at,
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
        rows = _active_documents(company).filter(elevator_id=fields.validated_data['elevator'],
                                                 category=fields.validated_data['category'])
        return Response([_item(doc) for doc in rows], headers=PRIVATE)

    fields = DocumentUpload(data=request.data)
    fields.is_valid(raise_exception=True)
    data = fields.validated_data
    elevator = get_object_or_404(Elevator, pk=data['elevator'], organization=company)
    doc = LiftDocument(organization=company, elevator=elevator,
                       category=data['category'], title=data['title'])
    try:
        with transaction.atomic():
            doc.file.save('document.pdf', data['file'], save=False)
            doc.save()
            audit(request.user, 'lift_document.upload', doc.pk,
                  {'elevator': elevator.pk, 'category': doc.category})
    except Exception:
        if doc.file:
            doc.file.delete(save=False)
        raise
    return Response(_item(doc), status=201, headers=PRIVATE)


@api_view(['DELETE'])
@permission_classes([MemberAccess])
@transaction.atomic
def remove(request, document_id):
    _require_admin(request.user)
    doc = get_object_or_404(_active_documents(org(request.user)).select_for_update(), pk=document_id)
    doc.deleted_at = timezone.now()
    doc.save(update_fields=['deleted_at'])
    audit(request.user, 'lift_document.delete', doc.pk,
          {'elevator': doc.elevator_id, 'category': doc.category})
    return Response(status=204, headers=PRIVATE)


@api_view(['GET'])
@permission_classes([MemberAccess])
def pdf(request, document_id):
    rows = _active_documents(org(request.user))
    if not admin_user(request.user):
        rows = rows.filter(category=LiftDocument.Category.INSPECTION)
    doc = get_object_or_404(rows, pk=document_id)
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
    acts = _active_documents(company).filter(elevator=elevator, category=LiftDocument.Category.INSPECTION)
    return Response({'date': elevator.next_inspection_on, 'acts': [_item(doc) for doc in acts]}, headers=PRIVATE)
