"""Delivery confirmation for the mechanic's app, independent of work acceptance."""
from datetime import timedelta

from django.core import signing
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework import serializers
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle

from .access import MemberAccess, org, role
from .models import Membership, MobileSession, TicketDeliveryReceipt

DISPATCH = ('created', 'reassigned')
SALT = 'liftcontrol.ticket-delivery.v1'


def track_dispatch(event, recipients):
    if event.action not in DISPATCH:
        return
    ticket = event.ticket
    responsible = ticket.responsible_id
    members = recipients.filter(role='MECHANIC')
    if responsible:
        members = members.filter(technician_id=responsible)
    TicketDeliveryReceipt.objects.filter(ticket=ticket, warn_after__isnull=False).update(warn_after=None)
    responsible_users = set(members.values_list('user_id', flat=True))
    pending = responsible_users - {event.actor_id} if responsible_users else {None}
    TicketDeliveryReceipt.objects.bulk_create([
        TicketDeliveryReceipt(ticket=ticket, event=event, recipient_id=user_id,
                              warn_after=event.created_at + timedelta(minutes=5))
        for user_id in pending
    ])


def receipt_data(ticket, user):
    rows = getattr(ticket, 'recent_delivery', None)
    if rows is None:
        rows = list(ticket.delivery_receipts.select_related('event').order_by('-event_id', 'pk'))
    if not rows:
        return None
    event = rows[0].event
    latest = getattr(ticket, 'last_dispatch', None)
    if latest is None:
        latest = ticket.events.filter(action__in=DISPATCH).order_by('-pk').values_list('pk', flat=True).first()
    if latest != event.pk:
        return None
    current = [row for row in rows if row.event_id == event.pk]
    own = next((row for row in current if row.recipient_id == user.pk), None)
    can_view = user.pk in (ticket.created_by_id, event.actor_id) or role(user) in ('ADMIN', 'DIRECTOR', 'DISPATCHER')
    if not can_view and own is None:
        return None
    if not can_view:
        current = [own]
    read = [row.read_at for row in current if row.read_at]
    received = [row.received_at for row in current if row.received_at]
    if read:
        state = 'read'
    elif received:
        state = 'received'
    elif any(row.warned_at for row in current):
        state = 'unconfirmed'
    elif all(row.recipient_id is None for row in current):
        state = 'no_recipient'
    else:
        state = 'pending'
    return {
        'state': state,
        'read_at': min(read).isoformat() if read else None,
        'received_at': min(received).isoformat() if received else None,
        'ack_id': own.pk if own is not None and own.received_at is None else None,
    }


def _active_rows(organization_id, user_id):
    return TicketDeliveryReceipt.objects.filter(
        ticket__organization_id=organization_id, recipient_id=user_id, received_at__isnull=True,
        recipient__memberships__organization_id=organization_id,
        recipient__memberships__role='MECHANIC', recipient__memberships__active=True,
        recipient__memberships__technician__active=True,
    )


class Acknowledgments(serializers.Serializer):
    ids = serializers.ListField(child=serializers.IntegerField(min_value=1, max_value=2**63-1),
                                allow_empty=False, max_length=100)


@api_view(['POST'])
@permission_classes([MemberAccess])
def acknowledge(request):
    if not isinstance(request.auth, MobileSession) or role(request.user) != 'MECHANIC':
        raise PermissionDenied('Подтверждение доступно механику в Android.')
    data = Acknowledgments(data=request.data)
    data.is_valid(raise_exception=True)
    updated = _active_rows(org(request.user).pk, request.user.pk).filter(
        pk__in=data.validated_data['ids']).update(received_at=timezone.now(), warn_after=None)
    return Response({'updated': updated})


def push_token(event_id, session):
    receipt = TicketDeliveryReceipt.objects.filter(event_id=event_id, recipient_id=session.user_id,
                                                    received_at__isnull=True).first()
    if receipt:
        return signing.dumps([receipt.pk, receipt.ticket.organization_id, session.pk], salt=SALT)
    return None


class DeliveryThrottle(AnonRateThrottle):
    rate = '360/min'


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([DeliveryThrottle])
def acknowledge_push(request):
    token = request.data.get('receipt')
    if not isinstance(token, str) or len(token) > 300:
        raise serializers.ValidationError('Неверное подтверждение.')
    try:
        receipt, organization, session_id = signing.loads(token, salt=SALT, max_age=900)
    except signing.BadSignature as exc:
        raise PermissionDenied('Подтверждение недействительно.') from exc
    session = MobileSession.objects.select_related('user').filter(
        pk=session_id, revoked_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True).first()
    if not session or not constant_time_compare(session.password_stamp, session.user.get_session_auth_hash()):
        raise PermissionDenied('Сеанс устройства завершён.')
    _active_rows(organization, session.user_id).filter(pk=receipt).update(
        received_at=timezone.now(), warn_after=None)
    return Response(status=204)


@transaction.atomic
def enqueue_due_receipt_warnings(limit=100):
    from .notification_inbox import _enqueue
    now = timezone.now()
    due = list(TicketDeliveryReceipt.objects.select_for_update(skip_locked=True).filter(
        warn_after__lte=now, received_at__isnull=True,
    ).order_by('warn_after', 'pk')[:limit])
    for row in due:
        event, ticket = row.event, row.ticket
        row.warn_after = None
        sender = event.actor_id or ticket.created_by_id
        received = TicketDeliveryReceipt.objects.filter(event=event, received_at__isnull=False).exists()
        if sender and not received and ticket.status == 'NEW' and not ticket.events.filter(
                pk__gt=event.pk, action__in=DISPATCH).exists():
            _enqueue(ticket.organization, [sender], 'ticket_delivery', event.pk, 'unconfirmed',
                     f'Заявка №{ticket.pk}: нет подтверждения доставки за 5 минут', 'ticket_delivery', ticket.pk, push=True)
            row.warned_at = now
        row.save(update_fields=['warn_after', 'warned_at'])
    return len(due)
