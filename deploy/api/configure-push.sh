#!/usr/bin/env bash
# Public key may change its contact URL; an existing private key is never rotated here.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите через sudo.'; exit 1; }
[[ $# -eq 1 && $1 =~ ^https://[A-Za-z0-9.-]+(:[0-9]+)?/?$ ]] || { echo 'Укажите HTTPS-адрес без пароля и параметров: sudo bash configure-push.sh https://your-host'; exit 1; }
install_root=/opt/liftcontrol
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$install_root"
base=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
[[ ! -s compose.v05.yaml ]] || base+=(-f compose.v05.yaml)
base+=(-f compose.v06.yaml)
[[ ! -s compose.public.yaml ]] || base+=(-f compose.public.yaml)
for overlay in compose.updates.yaml compose.fcm.yaml; do
  [[ ! -s "$overlay" ]] || base+=(-f "$overlay")
done
if [[ -e secrets/webpush_private_key || -e push-public.env ]]; then
  [[ -s secrets/webpush_private_key && -s push-public.env ]] || { echo 'Сохранилась неполная настройка ключей. Сначала восстановите её из резервной копии; новый ключ не создан.'; exit 1; }
  # Verify the public value against the saved key, inside the existing image.
  actual_public=$(docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges:true \
    -v "$install_root/secrets/webpush_private_key:/run/private_key:ro" --entrypoint python liftcontrol-api:0.6 -c \
    'from pathlib import Path; import base64; from cryptography.hazmat.primitives import serialization as s; k=s.load_pem_private_key(Path("/run/private_key").read_bytes(),None); print(base64.urlsafe_b64encode(k.public_key().public_bytes(s.Encoding.X962,s.PublicFormat.UncompressedPoint)).rstrip(b"=").decode())')
  python3 - "$actual_public" "$1" <<'PY'
from pathlib import Path
import os,sys,tempfile
values=dict(line.split('=',1) for line in Path('push-public.env').read_text().splitlines() if '=' in line)
if values.get('WEBPUSH_VAPID_PUBLIC_KEY')!=sys.argv[1]:
    raise SystemExit('Сохранённые ключи не совпали. Подписки сохранены, настройка остановлена.')
fd,name=tempfile.mkstemp(prefix='.push-public-',dir='.')
with os.fdopen(fd,'w') as out:
    out.write('WEBPUSH_VAPID_PUBLIC_KEY='+sys.argv[1]+'\nWEBPUSH_VAPID_SUBJECT='+sys.argv[2]+'\n')
os.chmod(name,0o600);os.replace(name,'push-public.env')
PY
  echo 'Сохранённый ключ push проверен; подписки телефонов сохраняются.'
else
  trap 'rm -f push-keys.tmp' EXIT
  "${base[@]}" exec -T api python - "$1" > push-keys.tmp <<'PY'
import sys,json,base64
from cryptography.hazmat.primitives.asymmetric import ec
from cryptography.hazmat.primitives import serialization as s
key=ec.generate_private_key(ec.SECP256R1())
print(json.dumps({'private':key.private_bytes(s.Encoding.PEM,s.PrivateFormat.PKCS8,s.NoEncryption()).decode(),
 'public':base64.urlsafe_b64encode(key.public_key().public_bytes(s.Encoding.X962,s.PublicFormat.UncompressedPoint)).rstrip(b'=').decode(), 'subject':sys.argv[1]}))
PY
  python3 - <<'PY'
import json,os
from pathlib import Path
value=json.loads(Path('push-keys.tmp').read_text())
# Exclusive creation prevents overwriting a key on an accidental concurrent invocation.
fd=os.open('secrets/webpush_private_key',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o400)
with os.fdopen(fd,'w') as out:out.write(value['private'])
os.chown('secrets/webpush_private_key',10001,10001)
fd=os.open('push-public.env',os.O_WRONLY|os.O_CREAT|os.O_EXCL,0o600)
with os.fdopen(fd,'w') as out:out.write('WEBPUSH_VAPID_PUBLIC_KEY='+value['public']+'\nWEBPUSH_VAPID_SUBJECT='+value['subject']+'\n')
PY
  rm -f push-keys.tmp
  trap - EXIT
fi
if [[ ! -s "$install_root/compose.push.yaml" ]]; then
  install -m 600 "$release_dir/compose.push.yaml" "$install_root/compose.push.yaml"
fi
"${base[@]}" -f compose.push.yaml config -q
"${base[@]}" -f compose.push.yaml up -d --no-build --no-deps api push-worker
echo 'Отправитель push запущен. На каждом телефоне: Настройки → Включить push.'
echo 'Проверьте новую заявку при свёрнутом браузере. Звук определяется настройками Android.'
