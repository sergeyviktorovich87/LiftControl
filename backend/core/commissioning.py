"""0.13 commissioning API.

Project writes recheck organization and the relevant assignment. Team chat
uses organization-level commissioning access. Audit/progress are append-only.
"""
import hashlib
import json
import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from uuid import UUID
from zoneinfo import ZoneInfo

from django.contrib.auth import get_user_model
from django.db import transaction, IntegrityError
from django.db.models import Exists, OuterRef, Q
from types import SimpleNamespace
from django.http import FileResponse
from django.shortcuts import get_object_or_404
from django.utils.http import content_disposition_header
from django.utils import timezone
from PIL import Image, UnidentifiedImageError
from rest_framework.decorators import api_view, permission_classes, throttle_classes
from rest_framework.exceptions import APIException, NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from rest_framework.serializers import IntegerField

from .access import MemberAccess, audit, org, role, commissioning_access
from .mobile_sync import SyncConflict
from .notification_inbox import enqueue_commissioning_action
from .models import (Membership, Organization, Elevator, CommissioningProject as Project,
    CommissioningLift as Lift, CommissioningAssignment as Assignment,
    CommissioningProgress as Progress, CommissioningExpense as Expense,
    CommissioningNeed as Need, CommissioningExtraWork as Extra,
    CommissioningMessage as Message, CommissioningLiftRequest as LiftRequest,
    CommissioningSyncReceipt, CommissioningPhoto, CommissioningNameplate)

from .media import serve
from .uploads import MAX_FILE_BYTES, MAX_FILE_MB, MAX_MULTIPART_FILES
from .media_vault import atomic_media, ingest
from .views import ChatThrottle

log = logging.getLogger(__name__)


def _photo_data(photo, project):
    url = f'/api/commissioning/{project.pk}/photos/{photo.pk}/'
    scope = f'?organization={project.organization_id}'
    return {'id': photo.pk, 'url': url + scope,
            'preview_url': url + 'preview/' + scope if photo.asset.preview else None}


def _photo_uploads(request):
    photos = request.FILES.getlist('photos')
    if set(request.FILES) - {'photos'}:
        raise ValidationError('Для фотографий используйте поле photos.')
    if len(photos) > MAX_MULTIPART_FILES or any(not 0 < f.size <= MAX_FILE_BYTES for f in photos):
        raise ValidationError(f'До 5 фотографий размером до {MAX_FILE_MB} МБ каждая.')
    return photos


def _save_photos(user, organization, uploads, **parent):
    for upload in uploads:
        asset = ingest(user, upload, organization=organization, video=False)
        CommissioningPhoto.objects.create(asset=asset, **parent)
    if uploads:
        log.info('commissioning_photos_saved organization=%s count=%s', organization.pk, len(uploads))


@api_view(['GET'])
@permission_classes([MemberAccess])
def photo(request, pk, photo_id, preview=False):
    project = _project(request, pk)
    row = get_object_or_404(
        CommissioningPhoto.objects.select_related('asset', 'progress').filter(
            progress__lift__project=project,
            asset__organization=project.organization, asset__state='READY',
        ), pk=photo_id,
    )
    if not _manager(request.user) and not Assignment.objects.filter(
        lift_id=row.progress.lift_id, user=request.user, active=True,
    ).exists():
        raise PermissionDenied('Фото доступно исполнителям этого лифта.')
    return _serve_photo(request, row.asset, preview)


def _nameplate_lift(request, project, lift_id):
    lift = _lift(project, lift_id)
    if not _manager(request.user) and not Assignment.objects.filter(lift=lift, user=request.user, active=True).exists():
        raise PermissionDenied('Шильдики доступны исполнителю этого лифта и руководителю.')
    return lift


def _nameplate_data(row):
    scope = f'?organization={row.lift.project.organization_id}'
    url = f'/api/commissioning/{row.lift.project_id}/lifts/{row.lift_id}/nameplates/{row.pk}/photo/'
    return {'id': row.pk, 'description': row.description, 'created_at': row.created_at,
            'author': row.author.get_full_name() or row.author.username,
            'url': url + scope, 'preview_url': url + 'preview/' + scope if row.asset.preview else None,
            'content_type': row.asset.content_type}


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
@throttle_classes([ChatThrottle])
def nameplates(request, pk, lift_id):
    project = _project(request, pk)
    lift = _nameplate_lift(request, project, lift_id)
    if request.method == 'GET':
        rows = lift.nameplates.select_related('author', 'asset', 'lift__project')
        return Response([_nameplate_data(row) for row in rows], headers={'Cache-Control': 'private, no-store'})
    description = _string(request.data, 'description', 1000)
    photos = _photo_uploads(request)
    if not photos:
        raise ValidationError({'photos': 'Прикрепите фотографию шильдика.'})
    operation = request.data.get('operation_id')
    if operation is not None:
        try:
            operation = UUID(operation)
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({'operation_id': 'Некорректный идентификатор загрузки.'})
    hashes = []
    for upload in photos:
        hashes.append(hashlib.file_digest(upload, 'sha256').hexdigest())
        upload.seek(0)
    fingerprint = hashlib.sha256(json.dumps(['nameplate', pk, lift_id, description, hashes]).encode()).hexdigest()
    with atomic_media():
        get_user_model().objects.select_for_update(no_key=True).get(pk=request.user.pk)
        project = _write_project(request, pk)
        lift = _nameplate_lift(request, project, lift_id)
        _assigned(request, lift)
        if operation is not None:
            saved = CommissioningSyncReceipt.objects.filter(organization=project.organization, user=request.user, operation_id=operation).first()
            if saved:
                if saved.payload_hash != fingerprint:
                    raise SyncConflict()
                return Response(saved.result)
        created = []
        for upload in photos:
            asset = ingest(request.user, upload, organization=project.organization, video=False)
            row = CommissioningNameplate.objects.create(lift=lift, author=request.user, asset=asset, description=description)
            created.append(row.pk)
        result = {'ids': created}
        if operation is not None:
            CommissioningSyncReceipt.objects.create(organization=project.organization, user=request.user, operation_id=operation, payload_hash=fingerprint, result=result)
        audit(request.user, 'commissioning.nameplates.add', lift.pk)
    log.info('commissioning_nameplates_added lift=%s count=%s', lift.pk, len(created))
    return Response(result, status=201)


@api_view(['GET'])
@permission_classes([MemberAccess])
def nameplate_photo(request, pk, lift_id, nameplate_id, preview=False):
    project = _project(request, pk)
    lift = _nameplate_lift(request, project, lift_id)
    row = get_object_or_404(CommissioningNameplate.objects.select_related('asset'), pk=nameplate_id,
                           lift=lift, asset__organization=project.organization, asset__state='READY')
    return _serve_photo(request, row.asset, preview)


def _serve_photo(request, asset, preview):
    if preview:
        if not asset.preview:
            raise NotFound('Миниатюра недоступна.')
        asset = SimpleNamespace(file=asset.preview, size=asset.preview_size, content_type='image/webp')
    try:
        return serve(asset, request)
    except FileNotFoundError:
        raise NotFound('Фотография недоступна.')



def _manager(user):
    return role(user) in ('ADMIN', 'DIRECTOR')


def _require_manager(user):
    if not _manager(user):
        raise PermissionDenied('Управление объектами наладки доступно руководителю.')


def _project(request, pk):
    if not commissioning_access(request.user):
        raise PermissionDenied('Администратор не выдал доступ к пусконаладке.')
    p = get_object_or_404(Project, pk=pk, organization=org(request.user))
    if not _manager(request.user) and not Assignment.objects.filter(
        lift__project=p, user=request.user, active=True
    ).exists():
        raise PermissionDenied('Объект наладки не назначен вам.')
    return p


def _write_project(request, pk):
    if not commissioning_access(request.user):
        raise PermissionDenied('Администратор не выдал доступ к пусконаладке.')
    project = get_object_or_404(Project.objects.select_for_update(), pk=pk, organization=org(request.user))
    if not _manager(request.user) and not Assignment.objects.filter(
        lift__project=project, user=request.user, active=True,
    ).exists():
        raise PermissionDenied('Объект наладки не назначен вам.')
    _editable(project)
    return project


def _editable(project):
    if project.archived_at:
        raise ValidationError('Объект находится в архиве и доступен только для чтения.')


def _assigned(request, lift):
    if _manager(request.user) or not Assignment.objects.filter(
        lift=lift, user=request.user, active=True
    ).exists():
        raise PermissionDenied('Изменять прогресс может только назначенный наладчик.')


def _lift(project, pk):
    return get_object_or_404(Lift, pk=pk, project=project)


def _optional_lift(project, data):
    value = data.get('lift')
    return _lift(project, value) if value else None


def _string(data, key, limit, required=True):
    value = data.get(key, '')
    if not isinstance(value, str):
        raise ValidationError({key: 'Введите текст.'})
    value = value.strip()
    if len(value) > limit or (required and not value):
        raise ValidationError({key: f'Требуется текст до {limit} символов.'})
    return value


def _money(data, key):
    try:
        value = Decimal(str(data[key]))
    except (KeyError, TypeError, ValueError, InvalidOperation):
        raise ValidationError({key: 'Введите сумму.'})
    if not value.is_finite() or value < 0 or value >= Decimal('10000000000') or value.as_tuple().exponent < -2:
        raise ValidationError({key: 'Неверная сумма (не более двух знаков после запятой).'})
    return value


def _project_info(p, user):
    managing = _manager(user)
    lifts = p.lifts.order_by('id')
    if managing:
        lifts = lifts.annotate(has_assignee=Exists(Assignment.objects.filter(lift_id=OuterRef('pk'), active=True)))
    lifts = list(lifts)
    result = {
        'id': p.pk, 'name': p.name, 'address': p.address,
        'archived': bool(p.archived_at),
        'lift_count': len(lifts),
        'progress': round(sum(l.progress for l in lifts) / len(lifts), 1) if lifts else 0,
    }
    if managing:
        result.update(
            contract_amount=str(p.contract_amount), adjuster_fee=str(p.adjuster_fee),
            unassigned_count=sum(not lift.has_assignee for lift in lifts),
        )
    return result


def _details(p, user):
    result = _project_info(p, user)
    managing = _manager(user)
    result['can_manage'] = managing
    result['lifts'] = [{
        'id': l.pk, 'label': l.label, 'factory_number': l.factory_number,
        'elevator': l.elevator_id, 'progress': l.progress, 'revision': l.revision,
        'entrance': l.elevator.entrance if l.elevator and l.elevator.organization_id == p.organization_id else '',
        'entrance_kind': l.elevator.entrance_kind if l.elevator and l.elevator.organization_id == p.organization_id else 'ENTRANCE',
        'can_view_nameplates': managing or any(a.active and a.user_id == user.pk for a in l.assignments.all()),
        'can_edit': not _manager(user) and any(a.active and a.user_id == user.pk for a in l.assignments.all()),
        'assignees': [{
            'user': a.user_id,
            'name': a.user.get_full_name() or a.user.username,
        } for a in l.assignments.all() if a.active],
        'history': [{
            'id': h.pk, 'before': h.before, 'after': h.after,
            'description': h.description, 'author': h.actor.get_full_name() or h.actor.username,
            'created_at': h.created_at,
            'photos': [_photo_data(photo, p) for photo in h.photos.all()]
                      if managing or any(a.active and a.user_id == user.pk for a in l.assignments.all()) else [],
        } for h in l.history.all()],
    } for l in p.lifts.select_related('elevator').prefetch_related('assignments__user', 'history__actor', 'history__photos__asset').order_by('id')]
    visible_expenses = p.expenses.all() if _manager(user) else p.expenses.filter(author=user)
    result['expenses'] = [{
        'id': e.pk, 'lift': e.lift_id, 'author': e.author.get_full_name() or e.author.username,
        'amount': str(e.amount), 'description': e.description, 'created_at': e.created_at,
        'spent_on': e.spent_on,
        'has_receipt': bool(e.receipt), 'reimbursed_at': e.reimbursed_at,
    } for e in visible_expenses.select_related('author').order_by('-id')]
    result['needs'] = [{
        'id': n.pk, 'lift': n.lift_id, 'category': n.category, 'description': n.description,
        'blocking': n.blocking, 'resolved': bool(n.resolved_at), 'created_at': n.created_at,
    } for n in p.needs.all().order_by('-id')]
    result['extras'] = [{
        'id': w.pk, 'lift': w.lift_id, 'description': w.description,
        'price': str(w.price), 'status': w.status, 'created_at': w.created_at,
    } for w in p.extras.all().order_by('-id')]
    # Older clients still expect this field. Archived chats are never exposed.
    result['messages'] = []
    result['lift_requests'] = [{
        'id': r.pk, 'label': r.label, 'factory_number': r.factory_number,
        'status': r.status,
    } for r in p.lift_requests.all().order_by('-id')]
    return result


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
def projects(request):
    if not commissioning_access(request.user):
        raise PermissionDenied('Администратор не выдал доступ к пусконаладке.')
    if request.method == 'GET':
        projects = Project.objects.filter(organization=org(request.user))
        if not _manager(request.user):
            projects = projects.filter(lifts__assignments__user=request.user,
                                       lifts__assignments__active=True).distinct()
        return Response([_project_info(p, request.user) for p in projects])
    _require_manager(request.user)
    name = _string(request.data, 'name', 200)
    address = _string(request.data, 'address', 300)
    with transaction.atomic():
        p = Project.objects.create(
            organization=org(request.user), name=name, address=address,
            contract_amount=_money(request.data, 'contract_amount') if 'contract_amount' in request.data else 0,
            adjuster_fee=_money(request.data, 'adjuster_fee') if 'adjuster_fee' in request.data else 0,
            created_by=request.user,
        )
        audit(request.user, 'commissioning.project_created', p.pk)
    log.info('commissioning_project_created project=%s', p.pk)
    return Response(_project_info(p, request.user), status=201)


@api_view(['GET'])
@permission_classes([MemberAccess])
def project(request, pk):
    return Response(_details(_project(request, pk), request.user))


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def add_lift(request, pk):
    _require_manager(request.user)
    p = _project(request, pk)
    _editable(p)
    label = _string(request.data, 'label', 150)
    factory = _string(request.data, 'factory_number', 100, required=False)
    related = None
    if request.data.get('elevator'):
        related = get_object_or_404(Elevator, organization=p.organization, pk=request.data['elevator'])
    if Lift.objects.filter(project=p, label=label).exists() or (
        factory and Lift.objects.filter(project=p, factory_number=factory).exists()
    ):
        raise ValidationError('Лифт с таким номером уже существует на объекте.')
    lift = Lift.objects.create(project=p, label=label, factory_number=factory, elevator=related)
    audit(request.user, 'commissioning.lift_created', lift.pk, {'project': p.pk})
    return Response({'id': lift.pk}, status=201)


def _eligible_assignees(organization):
    return Membership.objects.filter(
        Q(role=Membership.Role.MECHANIC, technician__organization=organization, technician__active=True)
        | Q(role=Membership.Role.ADJUSTER, can_commissioning=True),
        organization=organization, active=True, user__is_active=True,
    )


@api_view(['GET'])
@permission_classes([MemberAccess])
def assignees(request):
    _require_manager(request.user)
    members = _eligible_assignees(org(request.user)).select_related('user', 'technician')
    rows = [{
        'user': member.user_id,
        'name': member.technician.full_name if member.technician_id else
                member.user.get_full_name() or member.user.username,
        'role': member.role,
        'can_commissioning': member.can_commissioning,
    } for member in members]
    return Response(sorted(rows, key=lambda row: (row['name'].casefold(), row['user'])))


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def assign(request, pk, lift_id):
    _require_manager(request.user)
    user_id = IntegerField(min_value=1, max_value=2**63 - 1).run_validation(request.data.get('user'))
    active = request.data.get('active', True)
    grant = request.data.get('grant_commissioning', False)
    if type(active) is not bool or type(grant) is not bool or (grant and not active):
        raise ValidationError('Проверьте параметры назначения.')

    # Use the same lock order as membership edits before granting a role.
    organization = org(request.user)
    Organization.objects.select_for_update(no_key=True).get(pk=organization.pk)
    _require_manager(request.user)
    p = _write_project(request, pk)
    lift = _lift(p, lift_id)
    members = (
        _eligible_assignees(organization) if active else
        Membership.objects.filter(organization=organization, active=True, user__is_active=True)
    )
    member = get_object_or_404(members, user_id=user_id)
    if active and not member.can_commissioning:
        if not grant:
            raise ValidationError('Подтвердите выдачу роли наладчика сотруднику.')
        member.can_commissioning = True
        member.save(update_fields=['can_commissioning'])
        audit(request.user, 'organization.member_changed', member.pk,
              {'before': {'can_commissioning': False}, 'after': {'can_commissioning': True}})
    was_active = Assignment.objects.filter(lift=lift, user_id=member.user_id, active=True).exists()
    assignment, _ = Assignment.objects.update_or_create(
        lift=lift, user_id=member.user_id, defaults={'active': active})
    event = audit(request.user, 'commissioning.assignment_changed', lift.pk,
                  {'user': member.user_id, 'active': active})
    if active and not was_active:
        enqueue_commissioning_action(p, event, 'lift_assigned', 'Назначен лифт на наладку', recipient=member.user_id)
    log.info('commissioning_assignment_changed project=%s lift=%s active=%s', p.pk, lift.pk, active)
    return Response({'id': assignment.pk, 'active': active})


@api_view(['POST'])
@permission_classes([MemberAccess])
def update_progress(request, pk, lift_id):
    photos = _photo_uploads(request)
    data = request.data
    if hasattr(data, 'getlist'):
        data = {
            'revision': IntegerField(min_value=0).run_validation(data.get('revision')),
            'progress': IntegerField(min_value=0, max_value=100).run_validation(data.get('progress')),
            'description': data.get('description'),
        }
    with atomic_media():
        p = _write_project(request, pk)
        lift = get_object_or_404(Lift.objects.select_for_update(), pk=lift_id, project=p)
        _assigned(request, lift)
        return Response(_save_progress(request, lift, data, photos))


def _save_progress(request, lift, data, photos=()):
    if type(data.get('revision')) is not int or data['revision'] != lift.revision:
        raise ValidationError({'revision': 'Прогресс уже изменён. Обновите данные перед сохранением.'})
    value = data.get('progress')
    if type(value) is not int or not 0 <= value <= 100:
        raise ValidationError({'progress': 'Процент должен быть от 0 до 100.'})
    description = _string(data, 'description', 4000)
    if value == lift.progress:
        raise ValidationError('Процент не изменился.')
    before = lift.progress
    lift.progress = value
    lift.revision += 1
    lift.save(update_fields=['progress', 'revision'])
    event = Progress.objects.create(lift=lift, actor=request.user,
                                    before=before, after=value, description=description)
    _save_photos(request.user, lift.project.organization, photos, progress=event)
    from .notification_inbox import enqueue_commissioning_progress
    enqueue_commissioning_progress(event)
    audit(request.user, 'commissioning.progress_changed', lift.pk,
          {'before': before, 'after': value, 'revision': lift.revision})
    log.info('commissioning_progress lift=%s revision=%s', lift.pk, lift.revision)
    return {'progress': value, 'revision': lift.revision, 'event': event.pk}


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def request_lift(request, pk):
    p = _project(request, pk)
    _editable(p)
    if _manager(request.user):
        raise ValidationError('Руководитель добавляет лифт напрямую.')
    label = _string(request.data, 'label', 150)
    factory = _string(request.data, 'factory_number', 100, required=False)
    item = LiftRequest.objects.create(project=p, requested_by=request.user,
                                      label=label, factory_number=factory)
    event = audit(request.user, 'commissioning.lift_requested', item.pk, {'project': p.pk})
    enqueue_commissioning_action(p, event, 'lift_requested', 'Запрошен лифт для наладки')
    return Response({'id': item.pk, 'status': item.status}, status=201)


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def decide_lift(request, pk, request_id):
    _require_manager(request.user)
    p = _project(request, pk)
    _editable(p)
    item = get_object_or_404(LiftRequest.objects.select_for_update(), pk=request_id, project=p)
    if item.status != 'PENDING':
        raise ValidationError('Заявка уже рассмотрена.')
    approve = request.data.get('approve')
    if not isinstance(approve, bool):
        raise ValidationError('Укажите approve: true или false.')
    if approve:
        if Lift.objects.filter(project=p, label=item.label).exists() or (
            item.factory_number and Lift.objects.filter(project=p, factory_number=item.factory_number).exists()
        ):
            raise ValidationError('Такой лифт уже есть.')
        lift = Lift.objects.create(project=p, label=item.label, factory_number=item.factory_number)
        # Approval does not grant edit rights to any other employee.
        if _eligible_assignees(p.organization).filter(user=item.requested_by, can_commissioning=True).exists():
            Assignment.objects.get_or_create(lift=lift, user=item.requested_by)
    item.status = 'APPROVED' if approve else 'REJECTED'
    item.reviewed_by = request.user
    item.save(update_fields=['status', 'reviewed_by'])
    event = audit(request.user, 'commissioning.lift_request_decided', item.pk, {'approved': approve})
    enqueue_commissioning_action(p, event, 'lift_decided', 'Лифт добавлен' if approve else 'Добавление лифта отклонено', recipient=item.requested_by_id)
    return Response({'id': item.pk, 'status': item.status})


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def add_expense(request, pk):
    p = _write_project(request, pk)
    lift = _expense_access(request, p, request.data)
    item = _save_expense(request, p, lift, request.data)
    return Response({'id': item.pk}, status=201)


def _expense_access(request, project, data):
    if _manager(request.user):
        raise PermissionDenied('Личный расход вносит только его автор-наладчик.')
    lift = _optional_lift(project, data)
    if lift is not None:
        _assigned(request, lift)
    return lift


def _save_expense(request, project, lift, data):
    amount = _money(data, 'amount')
    if amount <= 0:
        raise ValidationError('Сумма должна быть положительной.')
    spent_on = timezone.localdate(timezone=ZoneInfo(project.organization.timezone))
    if data.get('spent_on') not in (None, ''):
        try:
            spent_on = date.fromisoformat(data['spent_on'])
        except (TypeError, ValueError):
            raise ValidationError({'spent_on': 'Укажите дату ГГГГ-ММ-ДД.'})
    item = Expense.objects.create(
        organization=project.organization, project=project, lift=lift,
        author=request.user, amount=amount, spent_on=spent_on,
        description=_string(data, 'description', 1000),
    )
    event = audit(request.user, 'commissioning.expense_created', item.pk, {'project': project.pk})
    enqueue_commissioning_action(project, event, 'expense_created', 'Новый расход на наладку')
    return item


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def upload_receipt(request, pk, expense_id):
    p = _write_project(request, pk)
    uploaded = request.FILES.get('receipt')
    image_format = _receipt_format(uploaded)
    item = get_object_or_404(Expense.objects.select_for_update(),
                             pk=expense_id, project=p, author=request.user)
    if item.lift_id:
        _assigned(request, item.lift)
    if item.receipt:
        raise ValidationError('Чек уже прикреплён. Исходный файл не заменяется.')
    _save_receipt(request, item, uploaded, image_format)
    return Response({'ok': True}, status=201)


def _receipt_format(uploaded):
    if not uploaded or uploaded.size > MAX_FILE_BYTES:
        raise ValidationError(f'Требуется фото чека до {MAX_FILE_MB} МБ.')
    try:
        with Image.open(uploaded) as picture:
            if picture.width * picture.height > 30_000_000:
                raise ValidationError('Слишком высокое разрешение изображения чека.')
            image_format = picture.format
            picture.verify()
        uploaded.seek(0)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError):
        raise ValidationError('Файл не является безопасным изображением.')
    if image_format not in ('JPEG', 'PNG', 'WEBP'):
        raise ValidationError('Допустимы JPEG, PNG или WebP.')
    return image_format


def _save_receipt(request, item, uploaded, image_format):
    item.receipt.save('receipt.' + image_format.lower(), uploaded, save=True)
    audit(request.user, 'commissioning.receipt_uploaded', item.pk)


@api_view(['GET'])
@permission_classes([MemberAccess])
def receipt(request, pk, expense_id):
    p = _project(request, pk)
    item = get_object_or_404(Expense, pk=expense_id, project=p)
    if not _manager(request.user) and item.author_id != request.user.id:
        raise PermissionDenied('Чужие чеки недоступны.')
    if not item.receipt:
        raise ValidationError('Фото чека отсутствует.')
    extension = item.receipt.name.rsplit('.', 1)[-1].lower()
    mime = {'jpeg': 'image/jpeg', 'jpg': 'image/jpeg', 'png': 'image/png', 'webp': 'image/webp'}
    try:
        if extension not in mime:
            # Existing FileField names were UUIDs without a suffix.
            with item.receipt.open('rb') as file:
                with Image.open(file) as image:
                    extension = image.format.lower()
        response = FileResponse(item.receipt.open('rb'), content_type=mime[extension])
    except (FileNotFoundError, UnidentifiedImageError, AttributeError, KeyError):
        raise NotFound('Фото чека недоступно.')
    response['Content-Disposition'] = content_disposition_header(True, f'receipt-{item.pk}.{extension}')
    response['Cache-Control'] = 'no-store, private'
    response['X-Content-Type-Options'] = 'nosniff'
    return response


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def reimburse(request, pk, expense_id):
    _require_manager(request.user)
    p = _project(request, pk)
    _editable(p)
    item = get_object_or_404(Expense.objects.select_for_update(), pk=expense_id, project=p)
    if item.reimbursed_at:
        raise ValidationError('Расход уже возмещён.')
    item.reimbursed_at = timezone.now()
    item.save(update_fields=['reimbursed_at'])
    event = audit(request.user, 'commissioning.expense_reimbursed', item.pk)
    enqueue_commissioning_action(p, event, 'expense_reimbursed', 'Расход на наладку возмещён', recipient=item.author_id)
    return Response({'id': item.pk, 'reimbursed_at': item.reimbursed_at})


@api_view(['POST'])
@permission_classes([MemberAccess])
def add_need(request, pk):
    p = _project(request, pk)
    _editable(p)
    lift = _optional_lift(p, request.data)
    if lift is not None and not _manager(request.user):
        _assigned(request, lift)
    category = _string(request.data, 'category', 30, required=False) or 'OTHER'
    if category not in ('MATERIAL', 'TOOL', 'POWER', 'WATER', 'ACCESS', 'DOCUMENT', 'INSTALLATION', 'OTHER'):
        raise ValidationError('Неизвестная категория потребности.')
    blocking = request.data.get('blocking', False)
    if not isinstance(blocking, bool):
        raise ValidationError('Неверный признак блокировки.')
    item = Need.objects.create(project=p, lift=lift, author=request.user,
                               category=category, blocking=blocking,
                               description=_string(request.data, 'description', 2000))
    event = audit(request.user, 'commissioning.need_created', item.pk, {'project': p.pk})
    enqueue_commissioning_action(p, event, 'need_created', 'Новая потребность по наладке')
    return Response({'id': item.pk}, status=201)


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def resolve_need(request, pk, need_id):
    _require_manager(request.user)
    p = _project(request, pk)
    _editable(p)
    item = get_object_or_404(Need.objects.select_for_update(), pk=need_id, project=p)
    if item.resolved_at:
        raise ValidationError('Потребность уже закрыта.')
    item.resolved_at = timezone.now()
    item.save(update_fields=['resolved_at'])
    event = audit(request.user, 'commissioning.need_resolved', item.pk)
    enqueue_commissioning_action(p, event, 'need_resolved', 'Потребность по наладке закрыта', recipient=item.author_id)
    return Response({'id': item.pk, 'resolved': True})


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def add_extra(request, pk):
    p = _project(request, pk)
    _editable(p)
    lift = _optional_lift(p, request.data)
    if lift is not None and not _manager(request.user):
        _assigned(request, lift)
    item = Extra.objects.create(project=p, lift=lift, author=request.user,
                                price=_money(request.data, 'price'),
                                description=_string(request.data, 'description', 2000),
                                status='APPROVED' if _manager(request.user) else 'PENDING',
                                reviewed_by=request.user if _manager(request.user) else None,
                                reviewed_at=timezone.now() if _manager(request.user) else None)
    event = audit(request.user, 'commissioning.extra_proposed', item.pk, {'project': p.pk})
    if item.status == "PENDING":
        enqueue_commissioning_action(p, event, 'extra_proposed', 'Предложены дополнительные работы')
    return Response({'id': item.pk, 'status': item.status}, status=201)


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def decide_extra(request, pk, extra_id):
    _require_manager(request.user)
    p = _project(request, pk)
    _editable(p)
    item = get_object_or_404(Extra.objects.select_for_update(), pk=extra_id, project=p)
    if item.status != 'PENDING':
        raise ValidationError('Решение уже принято.')
    approve = request.data.get('approve')
    if not isinstance(approve, bool):
        raise ValidationError('Укажите approve: true или false.')
    item.status = 'APPROVED' if approve else 'REJECTED'
    item.reviewed_by = request.user
    item.reviewed_at = timezone.now()
    item.save(update_fields=['status', 'reviewed_by', 'reviewed_at'])
    event = audit(request.user, 'commissioning.extra_decided', item.pk, {'approved': approve})
    enqueue_commissioning_action(p, event, 'extra_decided', 'Допработа согласована' if approve else 'Допработа отклонена', recipient=item.author_id)
    return Response({'id': item.pk, 'status': item.status})


class ProjectChatClosed(APIException):
    status_code = 410
    default_detail = 'Чат объекта закрыт. Отправьте сообщение в общий чат наладчиков.'
    default_code = 'project_chat_closed'


@api_view(['POST'])
@permission_classes([MemberAccess])
def send_message(request, pk):
    _project(request, pk)
    raise ProjectChatClosed()


def _team_messages(request):
    if not commissioning_access(request.user):
        raise PermissionDenied('Чат доступен сотрудникам с доступом к наладке.')
    return Message.objects.filter(organization=org(request.user))


def _team_message_data(message, receipts=None):
    def attachment(row):
        base = f'/api/commissioning/chat/{message.pk}/photos/{row.pk}/'
        scope = f'?organization={message.organization_id}'
        return {'id': row.pk, 'url': base + scope, 'content_type': row.asset.content_type,
                'preview_url': base + 'preview/' + scope if row.asset.preview else None}

    return {'id': message.pk, 'receipt': (receipts or {}).get(message.pk), 'body': message.text, 'author': message.author_id,
            'author_name': message.author.get_full_name() or message.author.username,
            'created_at': message.created_at,
            'attachments': [attachment(row) for row in message.photos.all()]}


@api_view(['GET', 'POST'])
@permission_classes([MemberAccess])
@throttle_classes([ChatThrottle])
def team_chat(request):
    rows = _team_messages(request)
    if request.method == 'GET':
        newest = list(rows.select_related('author').prefetch_related('photos__asset').order_by('-pk')[:200])
        from .message_receipts import summaries
        receipts = summaries(org(request.user).pk, 'commissioning_team_chat', [m.pk for m in newest if m.author_id == request.user.pk])
        return Response([_team_message_data(message, receipts) for message in reversed(newest)],
                        headers={'Cache-Control': 'private, no-store'})

    expected = request.data.get('expected_sender')
    if expected is not None and str(expected) != str(request.user.pk):
        raise PermissionDenied('Учётная запись изменилась. Войдите заново перед отправкой сообщения.')
    photos = _photo_uploads(request)
    company = org(request.user)
    body = _string(request.data, 'body', 4000, required=not photos)
    operation = request.data.get('operation_id')
    if operation is not None:
        try:
            operation = UUID(operation)
        except (AttributeError, TypeError, ValueError):
            raise ValidationError({'operation_id': 'Некорректный идентификатор сообщения.'})
        hashes = []
        for photo in photos:
            hashes.append(hashlib.file_digest(photo, 'sha256').hexdigest())
            photo.seek(0)
        fingerprint = hashlib.sha256(json.dumps(['team_chat', body, hashes]).encode()).hexdigest()
    with atomic_media():
        if operation is not None:
            # Use the same lock order as offline commissioning writes.
            get_user_model().objects.select_for_update(no_key=True).get(pk=request.user.pk)
            receipt = CommissioningSyncReceipt.objects.filter(
                organization=company, user=request.user, operation_id=operation,
            ).first()
            if receipt is not None:
                if receipt.payload_hash != fingerprint:
                    raise SyncConflict()
                return Response(receipt.result)
        message = rows.create(organization=company, author=request.user, text=body)
        _save_photos(request.user, company, photos, message=message)
        from .notification_inbox import enqueue_commissioning_chat
        enqueue_commissioning_chat(message)
        audit(request.user, 'commissioning.chat.send', message.pk)
        result = {'id': message.pk}
        if operation is not None:
            CommissioningSyncReceipt.objects.create(
                organization=company, user=request.user, operation_id=operation,
                payload_hash=fingerprint, result=result,
            )
    log.info('commissioning_chat_sent organization=%s id=%s', company.pk, message.pk)
    return Response(result, status=201)


@api_view(['GET'])
@permission_classes([MemberAccess])
def team_message(request, message_id):
    message = get_object_or_404(
        _team_messages(request).select_related('author').prefetch_related('photos__asset'),
        pk=message_id,
    )
    from .message_receipts import summaries
    receipts = summaries(org(request.user).pk, 'commissioning_team_chat', [message.pk]) if message.author_id == request.user.pk else {}
    return Response(_team_message_data(message, receipts), headers={'Cache-Control': 'private, no-store'})


@api_view(['GET'])
@permission_classes([MemberAccess])
def team_photo(request, message_id, photo_id, preview=False):
    photo = get_object_or_404(
        CommissioningPhoto.objects.select_related('asset').filter(
            message__in=_team_messages(request), message_id=message_id,
            asset__organization=org(request.user), asset__state='READY',
        ), pk=photo_id,
    )
    return _serve_photo(request, photo.asset, preview)


@api_view(['POST'])
@permission_classes([MemberAccess])
def sync_record(request, pk):
    """Replay the existing writes, with a durable receipt and fresh access checks."""
    try:
        command = request.data if not request.FILES else json.loads(request.data['command'])
        if not isinstance(command, dict) or not isinstance(command.get('body'), dict):
            raise ValueError()
        operation_id = UUID(command['id'])
        kind, body = command['type'], command['body']
        if kind not in ('progress', 'expense', 'receipt', 'message'):
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise ValidationError('Некорректная запись наладки.')
    uploaded = request.FILES.get('receipt')
    if request.FILES and (not uploaded or kind not in ('expense', 'receipt')):
        raise ValidationError('Фото можно прикрепить только к личному расходу.')
    digest = ''
    image_format = None
    if uploaded:
        image_format = _receipt_format(uploaded)
        digest = hashlib.file_digest(uploaded, 'sha256').hexdigest()
        uploaded.seek(0)
    fingerprint = hashlib.sha256(json.dumps(
        [pk, kind, body, digest], sort_keys=True, ensure_ascii=False,
    ).encode()).hexdigest()
    item = None
    try:
        with transaction.atomic():
            project = _write_project(request, pk)
            lift = expense = None
            if kind == 'progress':
                if type(body.get('lift')) is not int:
                    raise ValidationError('Укажите лифт.')
                lift = _lift(project, body['lift'])
                _assigned(request, lift)
            elif kind == 'expense':
                lift = _expense_access(request, project, body)
            elif kind == 'receipt':
                if not uploaded or type(body.get('expense')) is not int:
                    raise ValidationError('Укажите личный расход и прикрепите фото.')
                expense = get_object_or_404(Expense.objects.select_for_update(),
                                            project=project, pk=body['expense'], author=request.user)
                if expense.lift_id:
                    _assigned(request, expense.lift)
            # Serialize operation IDs across projects for a single account.
            get_user_model().objects.select_for_update(no_key=True).get(pk=request.user.pk)
            saved = CommissioningSyncReceipt.objects.filter(
                organization=project.organization, user=request.user, operation_id=operation_id,
            ).first()
            if saved:
                if saved.payload_hash != fingerprint:
                    raise SyncConflict()
                return Response({'operation_id': str(operation_id), 'result': saved.result, 'replayed': True})
            if kind == 'progress':
                result = _save_progress(request, lift, body)
            elif kind == 'message':
                raise ProjectChatClosed()
            else:
                item = expense if expense is not None else _save_expense(request, project, lift, body)
                if uploaded:
                    if item.receipt:
                        item = None
                        raise ValidationError('Чек уже прикреплён.')
                    _save_receipt(request, item, uploaded, image_format)
                result = {'id': item.pk}
            CommissioningSyncReceipt.objects.create(
                organization=project.organization, user=request.user, operation_id=operation_id,
                payload_hash=fingerprint, result=result,
            )
    except Exception:
        if item and item.receipt:
            try:
                if not Expense.objects.filter(receipt=item.receipt.name).exists():
                    item.receipt.delete(save=False)
            except Exception:
                log.warning('commissioning_receipt_cleanup_failed')
        raise
    log.info('commissioning_sync_saved')
    return Response({'operation_id': str(operation_id), 'result': result, 'replayed': False}, status=201)


@api_view(['POST'])
@permission_classes([MemberAccess])
@transaction.atomic
def archive_project(request, pk):
    _require_manager(request.user)
    p = get_object_or_404(Project.objects.select_for_update(), pk=pk, organization=org(request.user))
    _editable(p)
    p.archive_reason = _string(request.data, 'reason', 1000)
    p.archived_at = timezone.now()
    p.save(update_fields=['archive_reason', 'archived_at'])
    audit(request.user, 'commissioning.project_archived', p.pk, {'reason': p.archive_reason})
    return Response({'id': p.pk, 'archived': True})
