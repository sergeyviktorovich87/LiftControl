"""Full text stays on the authenticated server; FCM carries a short-lived capability."""
from django.core import signing
from django.shortcuts import get_object_or_404
from django.utils import timezone
from django.utils.crypto import constant_time_compare
from rest_framework.decorators import api_view, authentication_classes, permission_classes, throttle_classes
from rest_framework.exceptions import PermissionDenied
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .models import (MobileSession, Membership, TicketEvent, PersonalTaskEvent,
                     ChatMessage, CommissioningMessage, CommissioningProgress,
                     TicketComment)
from .ticket_delivery import DeliveryThrottle

SALT = 'liftcontrol.notification-content.v1'


def ticket_text(event):
    t = event.ticket
    return '\n'.join(filter(None, [t.location_address,
        t.location_label, t.title, t.description, event.reason]))


def task_text(event):
    t = event.task
    return '\n'.join(filter(None, [t.title, t.description, event.reason]))


def inbox_text(row):
    if row.body:
        return row.body
    company = row.organization_id
    if row.event_type == 'team_chat':
        obj = ChatMessage.objects.filter(pk=row.event_id, organization_id=company).first()
        return (obj.body or 'Вложения / карточка') if obj else ''
    if row.event_type == 'commissioning_team_chat':
        return CommissioningMessage.objects.filter(pk=row.event_id, organization_id=company).values_list('text', flat=True).first() or 'Фотографии'
    if row.event_type == 'commissioning_progress':
        return CommissioningProgress.objects.filter(pk=row.event_id, lift__project__organization_id=company).values_list('description', flat=True).first() or ''
    if row.event_type in ('ticket', 'ticket_delivery'):
        event = TicketEvent.objects.select_related('ticket__elevator__building').filter(pk=row.event_id, organization_id=company).first()
        return ticket_text(event) if event else ''
    if row.event_type == 'ticket_comment':
        return TicketComment.objects.filter(pk=row.event_id, organization_id=company).values_list('body', flat=True).first() or ''
    if row.event_type == 'task':
        event = PersonalTaskEvent.objects.select_related('task').filter(pk=row.event_id, task__organization_id=company).first()
        return task_text(event) if event else ''
    return row.body


def content_token(session, company, target, event):
    return signing.dumps([session.pk, company, target, event], salt=SALT)


@api_view(['POST'])
@authentication_classes([])
@permission_classes([AllowAny])
@throttle_classes([DeliveryThrottle])
def fetch_content(request):
    raw = request.data.get('token')
    if not isinstance(raw, str) or len(raw) > 500:
        raise PermissionDenied('Недействительное уведомление.')
    try:
        session_id, company, target, event_id = signing.loads(raw, salt=SALT, max_age=900)
    except (signing.BadSignature, ValueError, TypeError) as exc:
        raise PermissionDenied('Уведомление устарело.') from exc
    session = get_object_or_404(MobileSession.objects.select_related('user'), pk=session_id,
        revoked_at__isnull=True, expires_at__gt=timezone.now(), user__is_active=True)
    user = session.user
    if not constant_time_compare(session.password_stamp, user.get_session_auth_hash()) or not Membership.objects.filter(
            user=user, organization_id=company, active=True).exists():
        raise PermissionDenied('Доступ отозван.')
    user._organization_id = company
    from .access import membership
    if not membership(user):
        raise PermissionDenied('Доступ отозван.')
    if target == 'ticket':
        from .notification_preferences import ticket_recipients
        event = get_object_or_404(TicketEvent.objects.select_related('ticket__elevator__building'), pk=event_id, organization_id=company)
        if not ticket_recipients(event.ticket, event.action).filter(user=user).exists():
            raise PermissionDenied('Нет доступа.')
        body = ticket_text(event)
    elif target == 'task':
        from .access import role, technician_id
        event = get_object_or_404(PersonalTaskEvent.objects.select_related('task'), pk=event_id, task__organization_id=company)
        if role(user) not in ('ADMIN', 'DIRECTOR', 'DISPATCHER') and not (
                role(user) == 'MECHANIC' and event.task.assigned_to_id == technician_id(user)):
            raise PermissionDenied('Нет доступа.')
        body = task_text(event)
    else:
        from .notification_inbox import _visible_inbox
        from .models import Organization
        row = get_object_or_404(_visible_inbox(user, Organization.objects.get(pk=company)), pk=event_id)
        body = inbox_text(row)
        row.__class__.objects.filter(pk=row.pk, delivered_at__isnull=True).update(delivered_at=timezone.now())
    return Response({'body': body}, headers={'Cache-Control': 'private, no-store'})
