"""Read-only, same-origin release catalogue. The web process cannot publish or execute releases."""
import json
import os
import re
from pathlib import Path
from django.http import FileResponse
from django.views.decorators.cache import never_cache
from rest_framework.decorators import api_view, permission_classes
from rest_framework.exceptions import NotFound, PermissionDenied, ValidationError
from rest_framework.response import Response
from .access import MemberAccess, role

VERSION = '0.7'


def release(kind):
    root = Path(os.getenv('LIFTCONTROL_UPDATES_DIR', '/updates')).resolve()
    try:
        manifest = json.loads((root / 'release.json').read_text())
        item = manifest.get(kind)
        if not isinstance(item, dict):
            return None
        filename = item.get('filename', '')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9._-]{0,150}', filename) or '..' in filename:
            raise ValueError()
        path = root / filename
        if path.is_symlink() or path.resolve().parent != root or not path.is_file():
            raise ValueError()
        size = path.stat().st_size
        maximum = 200 * 1024**2 if kind == 'android' else 600 * 1024**2
        if not 1 <= size <= maximum or size != item['size']:
            raise ValueError()
        if not re.fullmatch(r'[a-f0-9]{64}', item.get('sha256', '')):
            raise ValueError()
        version = item['version']
        if not isinstance(version, str) or len(version) > 40:
            raise ValueError()
        if kind == 'android' and (type(item.get('version_code')) is not int or not 0 < item['version_code'] <= 2100000000):
            raise ValueError()
        return {'filename': filename, 'version': version, 'size': size,
                'sha256': item['sha256'], 'notes': str(item.get('notes', ''))[:4000],
                **({'version_code': item['version_code']} if kind == 'android' else {})}
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError):
        raise ValidationError('Файл обновления на сервере не прошёл проверку. Обратитесь к администратору.')


@never_cache
@api_view(['GET'])
@permission_classes([MemberAccess])
def catalogue(request):
    result = {'installed': {'panel': VERSION, 'api': VERSION, 'commit': os.getenv('BUILD_COMMIT', '')[:40]},
              'android': release('android')}
    if role(request.user) in ('ADMIN', 'DIRECTOR'):
        result['panel'] = release('panel')
    return Response(result)


@never_cache
@api_view(['GET'])
@permission_classes([MemberAccess])
def download_release(request, kind):
    if kind not in ('android', 'panel'):
        raise NotFound()
    if kind == 'panel' and role(request.user) not in ('ADMIN', 'DIRECTOR'):
        raise PermissionDenied()
    item = release(kind)
    if not item:
        raise NotFound('Обновление ещё не опубликовано.')
    path = Path(os.getenv('LIFTCONTROL_UPDATES_DIR', '/updates')).resolve() / item['filename']
    response = FileResponse(path.open('rb'), as_attachment=True, filename=item['filename'],
        content_type='application/vnd.android.package-archive' if kind == 'android' else 'application/zip')
    response['X-Content-SHA256'] = item['sha256']
    response['Cache-Control'] = 'private, no-store'
    return response
