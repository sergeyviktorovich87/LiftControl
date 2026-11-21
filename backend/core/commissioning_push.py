"""Deliver already scoped commissioning inbox events to active Android devices."""
import logging
import os
from datetime import timedelta

import requests
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import constant_time_compare

from . import native_push
from .models import NativePushDevice, NotificationInbox
from .notification_inbox import _visible_inbox
from .notification_preferences import allows, personal_commissioning

logger = logging.getLogger('liftcontrol.push')


def _send(item):
    user = item.user
    user._organization_id = item.organization_id
    now = timezone.now()
    if (not user.is_active or item.created_at < now - timedelta(minutes=30)
            or not _visible_inbox(user, item.organization).filter(pk=item.pk, read_at__isnull=True).exists()
            or not allows(user.pk, item.organization_id, 'updates', now=now,
                          personal=lambda: personal_commissioning(item))):
        return True
    data = {
        'target': 'commissioning', 'organization_id': str(item.organization_id),
        'project_id': str(item.target_id), 'event_id': str(item.pk), 'kind': item.kind,
    }
    devices = NativePushDevice.objects.select_related('session').filter(
        active=True, session__user=user, session__revoked_at__isnull=True, session__expires_at__gt=now,
    )
    complete = True
    for device in devices:
        if not constant_time_compare(device.session.password_stamp, user.get_session_auth_hash()):
            continue
        result = requests.post(
            f"https://fcm.googleapis.com/v1/projects/{native_push.client_config()['projectId']}/messages:send",
            headers={'Authorization': 'Bearer ' + native_push.access_token()},
            json={'message': {'token': device.token, 'data': data,
                              'android': {'priority': 'HIGH', 'ttl': '300s'}}},
            timeout=8, allow_redirects=False,
        )
        if result.status_code == 404:
            NativePushDevice.objects.filter(pk=device.pk).update(active=False)
        elif result.status_code != 200:
            complete = False
    return complete


def process_commissioning_batch(limit=20):
    if not native_push.enabled() or not os.path.isfile(os.getenv('FCM_SERVICE_ACCOUNT_FILE', '')):
        return 0
    with transaction.atomic():
        now = timezone.now()
        rows = list(NotificationInbox.objects.select_for_update(skip_locked=True).filter(
            commissioning_push_after__lte=now,
        ).order_by('commissioning_push_after', 'pk')[:limit])
        for row in rows:
            row.commissioning_push_attempts += 1
            row.commissioning_push_after = now + timedelta(minutes=2)
        NotificationInbox.objects.bulk_update(rows, ['commissioning_push_attempts', 'commissioning_push_after'])
    for row in rows:
        try:
            complete = _send(row)
        except Exception as exc:
            logger.warning('commissioning_push_failed error=%s', type(exc).__name__)
            complete = False
        row.commissioning_push_after = (
            None if complete or row.commissioning_push_attempts >= 4 else
            timezone.now() + timedelta(seconds=20 * 2 ** row.commissioning_push_attempts)
        )
        row.save(update_fields=['commissioning_push_after'])
    return len(rows)
