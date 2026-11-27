"""Web Push: strict endpoint allowlist, secret VAPID key, durable delivery outbox.

No HTTP request sends outbound push traffic. Background worker does so from an
isolated container with egress access. Do not log subscription endpoints or keys.
"""
import json
import logging
import os
import re
from datetime import timedelta
from urllib.parse import urlsplit
from .notification_content import ticket_text

from django.contrib.auth import get_user_model
from django.db import transaction
from django.db.models import Q,Case,When,Value,IntegerField
from django.utils import timezone
from rest_framework.exceptions import ValidationError, PermissionDenied
from .access import org, role, memberships
from .models import PushSubscription, PushDelivery

logger = logging.getLogger('liftcontrol.push')


def push_config():
    private_file = os.getenv('WEBPUSH_VAPID_PRIVATE_KEY_FILE', '')
    public_key = os.getenv('WEBPUSH_VAPID_PUBLIC_KEY', '')
    subject = os.getenv('WEBPUSH_VAPID_SUBJECT', '')
    return {'enabled': bool(public_key and subject and (os.getenv('WEBPUSH_ENABLED','').lower() == 'true' or private_file and os.path.isfile(private_file))),
            'private_file': private_file, 'public_key': public_key, 'subject': subject}


def valid_endpoint(endpoint):
    if not isinstance(endpoint, str) or len(endpoint) > 2048:
        return False
    try:
        url = urlsplit(endpoint)
        host = (url.hostname or '').lower()
        allowed = (
            host in ('fcm.googleapis.com', 'updates.push.services.mozilla.com', 'web.push.apple.com')
            or host.endswith('.push.apple.com')
            or host.endswith('.notify.windows.com')
        )
        return (url.scheme == 'https' and allowed and url.port in (None, 443)
                and bool(url.path and url.path != '/') and not url.username
                and not url.password and not url.fragment)
    except ValueError:
        return False


def _key(value):
    return (isinstance(value, str) and 12 <= len(value) <= 255
            and re.fullmatch(r'[A-Za-z0-9_-]+={0,2}', value) is not None)


@transaction.atomic
def register_subscription(user, data):
    if not user.is_superuser and not memberships(user).exists():
        raise PermissionDenied('Для push требуется действующее членство в организации.')
    if not push_config()['enabled']:
        raise ValidationError('Push пока не настроен администратором.')
    expected = data.get('expected_user')
    if expected is not None and str(expected) != str(user.pk):
        raise PermissionDenied('Учётная запись изменилась. Повторите подключение.')
    endpoint = data.get('endpoint', '')
    keys = data.get('keys', {})
    if not isinstance(keys, dict) or not valid_endpoint(endpoint) or not _key(keys.get('p256dh')) or not _key(keys.get('auth')):
        raise ValidationError('Неверные данные подписки браузера.')
    get_user_model().objects.select_for_update(no_key=True).get(pk=user.pk)
    existing = PushSubscription.objects.filter(endpoint=endpoint).first()
    if existing and existing.user_id != user.pk:
        raise PermissionDenied('Этот браузер уже привязан к другому пользователю. Отпишитесь и войдите заново.')
    if existing:
        existing.p256dh, existing.auth = keys['p256dh'], keys['auth']
        existing.save(update_fields=['p256dh', 'auth'])
        return existing
    if PushSubscription.objects.filter(user=user).count() >= 5:
        raise ValidationError('На пользователя допускается не более 5 устройств.')
    sub,_=PushSubscription.objects.get_or_create(endpoint=endpoint,defaults={'user':user,'organization':org(user),'p256dh':keys['p256dh'],'auth':keys['auth']})
    if sub.user_id!=user.pk:
        raise PermissionDenied('Этот браузер привязан к другой учётной записи.')
    return sub


def unregister_subscription(user, endpoint):
    return PushSubscription.objects.filter(user=user, endpoint=endpoint).delete()[0]


def deliver_one(item, config):
    from pywebpush import webpush, WebPushException
    from .models import PushSubscription
    sub = item.subscription
    # A former employee must not receive previously queued notifications.
    ticket = item.ticket
    from .notification_preferences import allows, category, personal_ticket, ticket_recipients
    if not ticket_recipients(ticket, item.kind).filter(user_id=sub.user_id).exists():
        return 'DISABLED'
    if not allows(sub.user_id, item.organization_id, category(ticket.priority, item.kind),
                  personal=lambda: personal_ticket(ticket, sub.user_id)):
        return 'DISABLED'
    expected = {'created':'NEW','escalated':'NEW','accepted':'IN_PROGRESS','completed':'DONE',
                'canceled':'CANCELED','stopped':'STOPPED','resumed':'IN_PROGRESS',
                'long_repair':'LONG_REPAIR'}
    # An offline/retrying worker must not announce a historical NEW state.
    if (item.kind == 'escalated' and ticket.priority != 'ENTRAPMENT'
            or expected.get(item.kind, ticket.status) != ticket.status
            or ticket.events.filter(created_at__gt=item.created_at,
                action__in=list(expected)+['reassigned']).exists()
            or item.created_at < timezone.now() - timedelta(minutes=30)):
        return 'SUPERSEDED'
    event = ticket.events.filter(action=item.kind, created_at__lte=item.created_at).order_by('-pk').first()
    if event is None:
        return 'SUPERSEDED'
    titles = {
        'created': 'Застревание: люди в кабине' if ticket.priority == 'ENTRAPMENT' else 'Новая заявка',
        'escalated': 'Застревание: люди в кабине',
        'accepted': 'Заявка принята',
        'completed': 'Заявка выполнена',
        'canceled': 'Заявка отменена',
        'reassigned': 'Изменён исполнитель',
        'stopped': 'Лифт остановлен',
        'resumed': 'Ремонт продолжен',
        'long_repair': 'Длительный ремонт',
    }
    payload = {
        'title': (titles.get(item.kind) or 'Изменения в заявке') + f' #{ticket.pk}',
        'body': ticket_text(event),
        'url': f'/?organization={item.organization_id}&ticket={ticket.pk}#tickets',
        'organization_id':item.organization_id, 'ticket_id':ticket.pk,
        'event_id': event.pk if event else item.pk, 'status': ticket.status,
        'kind': 'created' if item.kind == 'escalated' else item.kind, 'priority': ticket.priority,
        'tag': f'org-{item.organization_id}-ticket-{ticket.pk}',
    }
    from .webpush_health import receipt_token
    payload['receipt_token'] = receipt_token('ticket',item)
    from .webpush_transport import send
    return send(sub,payload,config,ttl=max(60,1800-(timezone.now()-item.created_at).total_seconds()),urgent=ticket.priority in ('ENTRAPMENT','EMERGENCY','HIGH'))


def process_batch(limit=20):
    config = push_config()
    if not config['enabled'] or not config['private_file'] or not os.path.isfile(config['private_file']):
        return 0
    now = timezone.now()
    with transaction.atomic():
        rows = list(PushDelivery.objects.select_for_update(skip_locked=True,of=('self',))
                    .filter(Q(state='PENDING') | Q(state='PROCESSING') | Q(state='SENT',attempts__lt=3), next_attempt_at__lte=now)
                    .annotate(urgency=Case(When(ticket__priority='ENTRAPMENT',then=Value(0)),When(ticket__priority__in=['EMERGENCY','HIGH'],then=Value(1)),default=Value(2),output_field=IntegerField())).order_by('urgency','pk')[:limit])
        for row in rows:
            row.state = 'PROCESSING'
            row.attempts += 1
            row.next_attempt_at = now + timedelta(minutes=4)
        PushDelivery.objects.bulk_update(rows, ['state', 'attempts', 'next_attempt_at'])
    for row in rows:
        try:
            result = deliver_one(row, config)
        except PushSubscription.DoesNotExist:
            result = 'EXPIRED'
        except Exception as exc:
            logger.warning('webpush_item_failed delivery=%s error=%s',row.pk,type(exc).__name__)
            result = 'RETRY'
        if result == 'EXPIRED':
            # The subscription (and its cascading deliveries) is already gone.
            continue
        if result == 'RETRY' and row.attempts < 8:
            row.state = 'PENDING'
            row.next_attempt_at = timezone.now() + timedelta(seconds=min(600,20 * 2 ** min(row.attempts,5)))
        else:
            row.state = result if result != 'RETRY' else 'FAILED'
            row.sent_at = timezone.now() if result == 'SENT' else None
            if result == 'SENT':row.next_attempt_at=timezone.now()+timedelta(minutes=3)
        PushDelivery.objects.filter(pk=row.pk,attempts=row.attempts,state='PROCESSING').update(state=row.state,sent_at=row.sent_at,next_attempt_at=row.next_attempt_at)
    return len(rows)

