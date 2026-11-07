#!/usr/bin/env bash
# Generate the secret on the server itself; never put it in chat or the repository.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите через sudo.'; exit 1; }
[[ $# -eq 1 && $1 == https://* && $1 != *$'\n'* ]] || { echo 'Укажите HTTPS-адрес системы: sudo bash configure-push.sh https://your-host'; exit 1; }
[[ $1 =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]] || { echo 'Нужен HTTPS-адрес без пароля, пути и параметров.'; exit 1; }
install_root=/opt/liftcontrol
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$install_root"
base=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
[[ ! -s compose.v05.yaml ]] || base+=(-f compose.v05.yaml)
base+=(-f compose.v06.yaml)
[[ ! -e secrets/webpush_private_key && ! -e push-public.env ]] || { echo 'Ключи уже есть. Повторная генерация запрещена: подписки телефонов должны сохраниться.'; exit 1; }
"${base[@]}" exec -T api python - "$1" > push-keys.tmp <<'PY'
import sys, json, base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization
key=ec.generate_private_key(ec.SECP256R1())
private=key.private_bytes(serialization.Encoding.PEM,serialization.PrivateFormat.PKCS8,serialization.NoEncryption()).decode()
public=base64.urlsafe_b64encode(key.public_key().public_bytes(serialization.Encoding.X962,serialization.PublicFormat.UncompressedPoint)).rstrip(b'=').decode()
print(json.dumps({'private':private,'public':public,'subject':sys.argv[1]}))
PY
python3 - <<'PY'
import json,os
from pathlib import Path
value=json.loads(Path('push-keys.tmp').read_text())
Path('secrets/webpush_private_key').write_text(value['private'])
os.chown('secrets/webpush_private_key',10001,10001)
os.chmod('secrets/webpush_private_key',0o400)
Path('push-public.env').write_text('WEBPUSH_VAPID_PUBLIC_KEY='+value['public']+'\nWEBPUSH_VAPID_SUBJECT='+value['subject']+'\n')
PY
rm -f push-keys.tmp
install -m 600 "$release_dir/compose.push.yaml" "$install_root/compose.push.yaml"
"${base[@]}" -f compose.push.yaml config -q
"${base[@]}" -f compose.push.yaml up -d --no-build --no-deps api push-worker
echo 'Отправитель push запущен. На каждом телефоне откройте Настройки → Включить push.'
echo 'Проверьте новую заявку при свернутом браузере. Звук определяется настройками Android.'
