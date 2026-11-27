"""Bounded offline commands. Identity and permissions are always server-side."""
import base64
import hashlib
import json
import uuid
from datetime import timedelta

from django.core import signing
from django.core.files.uploadedfile import SimpleUploadedFile
from django.contrib.auth import get_user_model
from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.dateparse import parse_datetime
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError, APIException
from rest_framework.response import Response

from .access import MemberAccess, org, role, technician_id
from .models import DutyShift, MobileSyncReceipt, Ticket
from .serializers import TicketSerializer
from . import ticket_flow as flow
from .media_vault import atomic_media
from .uploads import MAX_FILE_BYTES

SALT = 'liftcontrol.offline-create.v1'


def offline_grant(user):
    if not flow.can_create_ticket(user):
        return None
    now = timezone.now()
    start, end = now, now + timedelta(hours=24)
    if role(user) == 'MECHANIC':
        shift = DutyShift.objects.filter(organization=org(user), technician_id=technician_id(user),
            start__lte=now, end__gt=now).first()
        if not shift:
            return None
        start, end = max(start, shift.start), shift.end
    return signing.dumps({'user': user.pk, 'organization': org(user).pk,
        'start': start.isoformat(), 'end': end.isoformat()}, salt=SALT)


def creation_time(user, operation, occurred):
    # A signed, time-bounded grant permits work recorded during an offline duty
    # to arrive after handover. Revoked memberships/sessions still fail first.
    if flow.can_create_ticket(user):
        return None
    try:
        grant = signing.loads(operation.get('grant', ''), salt=SALT, max_age=7*86400)
        valid = grant['user'] == user.pk and grant['organization'] == org(user).pk
        valid = valid and parse_datetime(grant['start']) <= occurred <= parse_datetime(grant['end'])
    except (signing.BadSignature, TypeError, ValueError, KeyError):
        valid = False
    if not valid or not flow.is_on_duty(user, occurred):
        raise PermissionDenied('Не подтверждено дежурство во время создания. Заявка сохранена на телефоне; передайте её диспетчеру.')
    return occurred


class SyncConflict(APIException):
    status_code = 409
    default_detail = 'Операция с таким номером уже была отправлена с другими данными.'


@api_view(['POST'])
@permission_classes([MemberAccess])
@atomic_media()
def synchronize(request):
    operation = request.data
    uploaded = request.FILES.get('file')
    if request.FILES:
        try:
            operation = json.loads(request.data['command'])
        except (KeyError, ValueError, TypeError):
            raise ValidationError('Неподдерживаемый формат операции.')
        if uploaded is None or not 0 < uploaded.size <= MAX_FILE_BYTES:
            raise ValidationError('Выберите фотографию до 100 МБ.')
    if not isinstance(operation, dict) or set(operation) - {'id', 'type', 'ticket', 'body', 'occurred_at', 'grant'}:
        raise ValidationError('Неподдерживаемый формат операции.')
    try:
        op_id = uuid.UUID(str(operation['id']))
        occurred = parse_datetime(str(operation['occurred_at']))
        if occurred is None or timezone.is_naive(occurred):
            raise ValueError()
    except (ValueError, KeyError, TypeError):
        raise ValidationError('Некорректный номер или время операции.')
    body = operation.get('body', {})
    if not isinstance(body, dict):
        raise ValidationError('Некорректные данные операции.')
    payload = json.dumps(operation, sort_keys=True, separators=(',', ':'), ensure_ascii=False).encode()
    if uploaded is not None:
        if operation.get('type') != 'photo' or set(body) != {'name'} or not isinstance(body['name'], str):
            raise ValidationError('В этой операции нельзя прикрепить файл.')
        uploaded.name = body['name'][:180]
        payload += b'\0' + hashlib.file_digest(uploaded, 'sha256').digest()
        uploaded.seek(0)
    fingerprint = hashlib.sha256(payload).hexdigest()
    # Serialize same-account commands across API processes and lost-response retries.
    get_user_model().objects.select_for_update(no_key=True).get(pk=request.user.pk)
    receipt = MobileSyncReceipt.objects.filter(organization=org(request.user), user=request.user, operation_id=op_id).first()
    if receipt:
        if receipt.payload_hash != fingerprint:
            raise SyncConflict()
        return Response({'operation_id': str(op_id), 'ticket': TicketSerializer(receipt.ticket, context={'request':request}).data,
            'result': receipt.result, 'replayed': True})
    now = timezone.now()
    if not now - timedelta(days=7) <= occurred <= now + timedelta(minutes=5):
        raise ValidationError('Операция старше 7 дней или часы телефона неверны. Данные остаются на телефоне.')
    kind, result = operation.get('type'), {}
    if kind == 'create':
        allowed = {'building', 'elevator', 'title', 'description', 'priority', 'assigned_to', 'entrance_hint', 'floor_hint', 'contact_name', 'contact_phone'}
        if set(body) - allowed:
            raise ValidationError('Недопустимые поля новой заявки.')
        at = creation_time(request.user, operation, occurred)
        serializer = TicketSerializer(data=body, context={'request':request})
        serializer.is_valid(raise_exception=True)
        ticket = flow.create_ticket(request.user, serializer.validated_data, offline_at=at)
    else:
        try:
            ticket_id = int(operation['ticket'])
        except (ValueError, KeyError, TypeError, OverflowError):
            raise ValidationError('Укажите заявку.')
        get_object_or_404(Ticket, pk=ticket_id, organization=org(request.user))
        if kind == 'accept' and not body:
            ticket = flow.accept_ticket(request.user, ticket_id)
        elif kind == 'complete' and set(body) in ({'work_description'}, {'work_description', 'people_released'}):
            ticket = flow.complete_ticket(request.user, ticket_id, body['work_description'], body.get('people_released'))
        elif kind == 'stop' and set(body) == {'reason'}:
            ticket = flow.stop_ticket(request.user, ticket_id, body['reason'])
        elif kind == 'resume' and not body:
            ticket = flow.resume_ticket(request.user, ticket_id)
        elif kind == 'long-repair' and set(body) in ({'reason'}, {'reason', 'expected_date'}):
            ticket = flow.defer_repair(request.user, ticket_id, body['reason'], body.get('expected_date'))
        elif kind == 'cancel' and set(body) == {'reason'}:
            ticket = flow.cancel_ticket(request.user, ticket_id, body['reason'])
        elif kind == 'assign' and set(body) == {'assigned_to', 'reason'}:
            ticket = flow.reassign_ticket(request.user, ticket_id, body['assigned_to'], body['reason'])
        elif kind == 'comment' and set(body) == {'body'}:
            comment = flow.add_comment(request.user, ticket_id, body['body'])
            ticket = comment.ticket
            result = {'id':comment.pk, 'body':comment.body, 'created_at':comment.created_at.isoformat()}
        elif kind == 'photo' and (uploaded is not None or set(body) in ({'file'}, {'file', 'name'})):
            if uploaded is None:
                try:
                    encoded = body['file']
                    if not isinstance(encoded, str) or len(encoded) > 14*1024*1024:
                        raise ValueError()
                    image = base64.b64decode(encoded, validate=True)
                except (ValueError, TypeError):
                    raise ValidationError('Фотография повреждена или слишком большая.')
                uploaded = SimpleUploadedFile(str(body.get('name', 'repair.jpg'))[:180], image)
            from .ticket_photos import save_photo
            ticket = get_object_or_404(Ticket, pk=ticket_id, organization=org(request.user))
            photo = save_photo(request.user, ticket, uploaded)
            result = {'id':photo.pk}
        else:
            raise ValidationError('Неподдерживаемая операция или поля.')
    MobileSyncReceipt.objects.create(organization=org(request.user), user=request.user, operation_id=op_id,
        payload_hash=fingerprint, ticket=ticket, result=result, occurred_at=occurred)
    return Response({'operation_id':str(op_id), 'ticket':TicketSerializer(ticket, context={'request':request}).data,
        'result':result, 'replayed':False}, status=201)
