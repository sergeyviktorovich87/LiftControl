"""Browser requests only; the host executes a fixed, verified release updater."""
import json
import os
import re
import stat
import time
from datetime import timedelta
from pathlib import Path

from django.contrib.auth import get_user_model
from django.db import transaction
from django.utils import timezone
from django.views.decorators.cache import never_cache
from rest_framework.authentication import SessionAuthentication
from rest_framework.decorators import api_view, authentication_classes, permission_classes
from rest_framework.exceptions import PermissionDenied, ValidationError, Throttled
from rest_framework.response import Response

from .access import MemberAccess, audit
from .models import AuditEvent
from .updates import VERSION

ACTION = 'system_update.request'
VERSION_RE = re.compile(r'(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})\.(?:0|[1-9][0-9]{0,5})')
STATES = frozenset(('idle','checking','available','current','installing','installed',
                    'deferred','migration_approval','blocked','failed','changed'))
ACTIVE = frozenset(('checking','installing'))


def read_status():
    path = Path(os.getenv('LIFTCONTROL_UPDATES_DIR', '/updates')) / 'host-update-status.json'
    try:
        with os.fdopen(os.open(path, os.O_RDONLY | os.O_NOFOLLOW | os.O_NONBLOCK), 'rb') as source:
            info = os.fstat(source.fileno())
            if not stat.S_ISREG(info.st_mode) or info.st_uid != 0 or info.st_mode & 0o022 or info.st_size > 4096:
                return None
            raw = json.loads(source.read(4097))
        if not isinstance(raw, dict) or raw.get('state') not in STATES:
            return None
        updated = raw.get('updated')
        if type(updated) is not int or updated > time.time()+60:
            return None
        target = raw.get('target', '')
        if not isinstance(target, str) or (target and not VERSION_RE.fullmatch(target)):
            return None
        request_id = raw.get('request_id', 0)
        if type(request_id) is not int or request_id < 0:
            return None
        return {'state':raw['state'], 'target':target, 'updated':updated,
                'request_id':request_id, 'auto_enabled':raw.get('auto_enabled') is True,
                'reachable':time.time()-updated < (3600 if raw['state'] in ACTIVE else 120)}
    except (OSError, ValueError, TypeError):
        return None


def recent_request(after=0):
    return AuditEvent.objects.filter(action=ACTION, pk__gt=after,
        created_at__gte=timezone.now()-timedelta(minutes=10),
        actor__is_active=True, actor__is_superuser=True).order_by('pk').first()


@never_cache
@api_view(['GET','POST'])
@authentication_classes([SessionAuthentication])
@permission_classes([MemberAccess])
def system_update(request):
    if not request.user.is_superuser:
        raise PermissionDenied('Только владелец сервера может управлять обновлением системы.')
    current = read_status()
    if request.method == 'GET':
        pending = recent_request(current['request_id'] if current else 0)
        return Response({'installed':VERSION, 'host':current,
                         'pending':pending.pk if pending else None})
    if not current or not current['reachable']:
        raise ValidationError('Служба обновления VPS недоступна.')
    if current['state'] in ACTIVE:
        raise ValidationError('Обновление уже выполняется.')
    if not isinstance(request.data, dict) or set(request.data)-{'action','target'}:
        raise ValidationError('Некорректный запрос.')
    action = request.data.get('action')
    target = request.data.get('target','')
    if action not in ('check','install') or not isinstance(target,str):
        raise ValidationError('Неизвестная операция.')
    if action == 'check' and target:
        raise ValidationError('Проверка не принимает номер версии.')
    if action == 'install' and (not VERSION_RE.fullmatch(target) or
            current['state'] != 'available' or target != current['target'] or
            tuple(map(int,target.split('.'))) <= tuple(map(int,VERSION.split('.')))):
        raise ValidationError('Сначала проверьте доступное обновление.')
    with transaction.atomic():
        # Serialize server-wide requests using the first existing superuser row.
        get_user_model().objects.select_for_update().filter(is_superuser=True).order_by('pk').first()
        if recent_request(current['request_id']):
            raise ValidationError('Запрос уже отправлен службе.')
        if AuditEvent.objects.filter(action=ACTION,created_at__gte=timezone.now()-timedelta(seconds=10)).exists():
            raise Throttled(wait=10)
        row = audit(request.user,ACTION,details={'action':action,'target':target})
    return Response({'request_id':row.pk},status=202)
