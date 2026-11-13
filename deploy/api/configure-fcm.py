#!/usr/bin/env python3
"""Run on the VPS as root. Never accept or print credential values through the web panel."""
import argparse
import json
import os
import re
from pathlib import Path


def configure(client_path, account_path, base=Path('/opt/liftcontrol')):
    if os.geteuid() != 0:
        raise ValueError('Запустите через sudo.')
    public = json.loads(Path(client_path).read_text())
    account = json.loads(Path(account_path).read_text())
    project = public['project_info']
    client = next(c for c in public['client'] if c['client_info']['android_client_info']['package_name'] == 'ru.liftcontrol.app.beta')
    if (account.get('type') != 'service_account' or account.get('project_id') != project['project_id']
            or account.get('token_uri') != 'https://oauth2.googleapis.com/token'
            or not re.fullmatch(r'[a-z0-9][a-z0-9-]{3,62}', project['project_id'])
            or 'BEGIN PRIVATE KEY' not in account.get('private_key', '')):
        raise ValueError('Файлы должны принадлежать одному проекту Firebase и содержать ключ сервисного аккаунта.')
    if not (base / 'compose.yaml').is_file():
        raise ValueError('Установленный сервер не найден.')
    config = {'projectId': project['project_id'], 'messagingSenderId': project['project_number'],
              'appId': client['client_info']['mobilesdk_app_id'], 'apiKey': client['api_key'][0]['current_key']}
    (base / 'secrets').mkdir(mode=0o700, exist_ok=True)
    secret = base / 'secrets/fcm_service_account.json'
    descriptor = os.open(secret, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o600)
    with os.fdopen(descriptor, 'w') as file:
        json.dump(account, file); file.flush(); os.fsync(file.fileno())
    os.chown(secret, 10001, 10001); os.chmod(secret, 0o400)
    public_file = base / 'firebase-public.json'
    descriptor = os.open(public_file, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | os.O_NOFOLLOW, 0o644)
    with os.fdopen(descriptor, 'w') as file: json.dump(config, file)
    os.chmod(public_file, 0o644)
    (base / 'compose.fcm.yaml').write_bytes(Path(__file__).with_name('compose.fcm.yaml').read_bytes())


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('google_services_json'); parser.add_argument('service_account_json')
    args = parser.parse_args()
    try:
        configure(args.google_services_json, args.service_account_json)
        print('FCM настроен. Запустите update-panel.sh из этого пакета, регистрация телефонов выполняется автоматически после входа.')
    except (OSError, ValueError, KeyError, StopIteration):
        raise SystemExit('Не удалось настроить FCM. Проверьте файлы, пакет ru.liftcontrol.app.beta и права root. Секреты не выводятся.')
