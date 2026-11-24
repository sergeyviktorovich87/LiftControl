#!/usr/bin/env bash
# Update an installed 0.8+ using its existing verified dependencies. Never reset data.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash update-panel.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for file in Dockerfile PATCH.sha256 SOURCE_COMMIT.txt VERSION.txt payload/requirements.txt compose.updates.yaml compose.media.yaml compose.uploads.yaml compose.fcm-updates.yaml compose.inspections.yaml copy-media.py backup-media.py; do
  test -s "$file" || { echo "Отсутствует $file"; exit 1; }
done
sha256sum --check --strict PATCH.sha256
cd /opt/liftcontrol
exec 9>/opt/liftcontrol/.panel-update.lock
flock -n 9 || { echo 'Другое обновление уже выполняется.'; exit 1; }
base=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
test -s compose.v06.yaml || { echo 'Сначала нужна установленная версия 0.6.'; exit 1; }
for overlay in compose.v05.yaml compose.v06.yaml compose.push.yaml compose.public.yaml compose.updates.yaml compose.fcm.yaml compose.fcm-updates.yaml compose.media.yaml compose.uploads.yaml compose.inspections.yaml; do
  [[ ! -s "$overlay" ]] || base+=(-f "$overlay")
done
"${base[@]}" config -q
container=$("${base[@]}" ps -q api)
test -n "$container" || { echo 'Контейнер API не найден.'; exit 1; }
installed=$(curl --fail --silent --max-time 5 http://127.0.0.1:18080/api/health/ | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')
target=$(tr -d '\r\n' < "$release_dir/VERSION.txt")
[[ "$target" =~ ^[0-9]+\.[0-9]+\.[0-9]+$ ]] || { echo 'Некорректный файл VERSION.txt.'; exit 1; }
case "$installed" in
  0.8|0.9|0.10|0.11|0.11.1|0.12.0|0.13.0|0.13.1|0.13.2|0.13.3|0.13.4|0.13.5|0.13.6|0.13.7|0.13.8|0.13.9|0.13.10|0.13.11|0.13.12|0.13.13|0.13.14|0.13.15|0.13.16|"$target") ;;
  *) [[ "$installed" =~ ^0\.13\.[0-9]+$ && "$target" =~ ^0\.13\.[0-9]+$ ]] || { echo "Версия $installed не поддерживает переход на $target этим пакетом."; exit 1; } ;;
esac
# Prevent downgrades and check the auto-updater's preflight under the same lock.
python3 - "$installed" "$target" <<'PY'
import os,sys
def numeric(s): return tuple(map(int,s.split('.')))
assert numeric(sys.argv[1]) <= numeric(sys.argv[2]), 'DOWNGRADE_BLOCKED'
expected=os.getenv('LIFTCONTROL_AUTO_EXPECTED_VERSION')
assert not expected or expected==sys.argv[1], 'INSTALLED_VERSION_CHANGED'
PY
source_commit=$(tr -d '\r\n' < "$release_dir/SOURCE_COMMIT.txt")
[[ "$source_commit" =~ ^[a-f0-9]{40}$ ]] || { echo 'Некорректный номер исходной сборки.'; exit 1; }
stamp=$(date -u +%Y%m%d-%H%M%S)
backup="/opt/liftcontrol/backups/before-offline-$stamp"
mkdir -p "$backup"
previous_image=$(docker inspect "$container" --format '{{.Image}}')
previous_tag="liftcontrol-api:before-offline-$stamp"
docker tag "$previous_image" "$previous_tag"
printf 'services:\n  api:\n    image: %s\n' "$previous_tag" > "$backup/compose.rollback.yaml"
workers=()
for worker_name in push-worker native-push-worker inspection-reminder-worker; do
  worker=$("${base[@]}" ps -q "$worker_name" 2>/dev/null || true)
  if [[ -n "$worker" ]]; then
    workers+=("$worker_name")
    worker_image=$(docker inspect "$worker" --format '{{.Image}}')
    worker_tag="liftcontrol-api:$worker_name-before-update-$stamp"
    docker tag "$worker_image" "$worker_tag"
    printf '  %s:\n    image: %s\n' "$worker_name" "$worker_tag" >> "$backup/compose.rollback.yaml"
  fi
done
previous=("${base[@]}")
stopped=0
created_updates=0
created_media=0
created_uploads=0
updated_fcm=0
recover() {
  result=$?
  if [[ $result -ne 0 ]]; then
    docker tag "$previous_image" liftcontrol-api:0.6 || true
    if [[ $created_updates -eq 1 ]]; then rm -f /opt/liftcontrol/compose.updates.yaml; fi
    if [[ $created_media -eq 1 ]]; then rm -f /opt/liftcontrol/compose.media.yaml; fi
    if [[ $created_uploads -eq 1 ]]; then rm -f /opt/liftcontrol/compose.uploads.yaml; fi
    if [[ $updated_fcm -eq 1 ]]; then
      rm -f /opt/liftcontrol/compose.fcm-updates.yaml
    fi
  fi
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    "${previous[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate api || true
    for worker_name in "${workers[@]}"; do "${previous[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate "$worker_name" || true; done
    echo "Обновление не завершилось. Предыдущий образ возвращён; копия базы: $backup/database.dump"
  fi
}
trap recover EXIT
install -d -o root -g root -m 0755 /opt/liftcontrol/updates
upload_owner=${SUDO_USER:-root}
upload_group=$(id -gn "$upload_owner")
install -d -o "$upload_owner" -g "$upload_group" -m 0755 /opt/liftcontrol/updates/android
if [[ ! -s compose.updates.yaml ]]; then
  install -o root -g root -m 0644 "$release_dir/compose.updates.yaml" compose.updates.yaml
  created_updates=1
  base+=(-f compose.updates.yaml)
fi
if [[ -s compose.fcm.yaml && ! -s compose.fcm-updates.yaml ]]; then
  # Keep installed FCM credentials and custom settings. Extend only the worker's
  # updates mount and environment through a Compose overlay.
  install -m 0644 "$release_dir/compose.fcm-updates.yaml" compose.fcm-updates.yaml
  updated_fcm=1
  base+=(-f compose.fcm-updates.yaml)
fi
"${base[@]}" config --format json | python3 -c '
import json,sys
a=json.load(sys.stdin)["services"]["api"]
assert a.get("environment",{}).get("LIFTCONTROL_UPDATES_DIR")=="/updates", "Неверный каталог обновлений"
assert any(v.get("type")=="bind" and v.get("source")=="/opt/liftcontrol/updates" and v.get("target")=="/updates" and v.get("read_only") is True for v in a.get("volumes",[])), "Нужен каталог обновлений только для чтения"
'
docker build --pull=false --network none --build-arg "BASE_IMAGE=$previous_tag" --build-arg "BUILD_COMMIT=$source_commit" -t liftcontrol-api:0.6 "$release_dir"
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  -e DJANGO_DEBUG=True --entrypoint python liftcontrol-api:0.6 manage.py check
# A critical lift call must not be interrupted by an unattended restart.
# This check is immediately before stopping the API; it is not a guarantee
# against a new call arriving during the maintenance window.
if [[ -n "${LIFTCONTROL_AUTO_EXPECTED_VERSION:-}" ]]; then
  docker exec "$container" python manage.py shell -c "from core.models import Ticket; raise SystemExit(75 if Ticket.objects.filter(priority='ENTRAPMENT').exclude(status__in=['DONE','CANCELED']).exists() else 0)"
fi
stopped=1
"${base[@]}" stop api "${workers[@]}"
"${base[@]}" exec -T db pg_dump -U postgres -d liftcontrol -Fc > "$backup/database.dump"
test -s "$backup/database.dump"
"${base[@]}" exec -T db pg_restore --list < "$backup/database.dump" > "$backup/database.list"
# Keep the original volume intact. Copy before changing the API mount; an
# interrupted copy can be repeated and a conflicting destination stops migration.
install -d -o root -g root -m 0711 /srv/liftcontrol-data
install -d -o 10001 -g 10001 -m 0700 /srv/liftcontrol-data/media
old_media=$(docker inspect "$container" --format '{{range .Mounts}}{{if eq .Destination "/app/private_media"}}{{.Source}}{{end}}{{end}}')
test -n "$old_media" || { echo 'Исходное хранилище файлов не найдено.'; exit 1; }
python3 - "$old_media" "$backup/database.dump" <<'PY'
from pathlib import Path
import shutil,sys
source=Path(sys.argv[1])
size=sum(p.stat().st_size for p in source.rglob('*') if p.is_file())
destination=Path('/srv/liftcontrol-data/media')
copies=2 if source==destination else 5
required=size*copies+Path(sys.argv[2]).stat().st_size*3+1024**3
if shutil.disk_usage(destination).free<required:
    raise SystemExit('Недостаточно места для переноса и резервной копии. Нужно свободно примерно %.1f ГБ.' % (required/1024**3))
PY
if [[ "$old_media" != /srv/liftcontrol-data/media ]]; then
  docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges --user 10001:10001 \
    --volumes-from "$container":ro -v /srv/liftcontrol-data/media:/new-media \
    -v "$release_dir/copy-media.py":/run/copy-media.py:ro --entrypoint python "$previous_tag" /run/copy-media.py | tee "$backup/media-copy.log"
fi
if [[ ! -s compose.media.yaml ]]; then
  install -o root -g root -m 0644 "$release_dir/compose.media.yaml" compose.media.yaml
  created_media=1
  base+=(-f compose.media.yaml)
fi
install -d -o 10001 -g 10001 -m 0700 /srv/liftcontrol-data/upload-tmp
if [[ ! -s compose.uploads.yaml ]]; then
  install -o root -g root -m 0644 "$release_dir/compose.uploads.yaml" compose.uploads.yaml
  created_uploads=1
  base+=(-f compose.uploads.yaml)
fi
"${base[@]}" --profile maintenance config --format json | python3 -c '
import json,sys
services=json.load(sys.stdin)["services"]
for name in ("api","migrate"):
    assert any(v.get("type")=="bind" and v.get("source")=="/srv/liftcontrol-data/media" and v.get("target")=="/app/private_media" for v in services[name].get("volumes",[])), "Неверный каталог медиа"
'
"${base[@]}" --profile maintenance run --rm --no-deps -T migrate
"${base[@]}" exec -T db psql -U postgres -d liftcontrol -v ON_ERROR_STOP=1 <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO liftapp;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
SQL
"${base[@]}" run --rm --no-deps -T --entrypoint python api manage.py migrate_media_vault | tee "$backup/media-migration.log"
install -o root -g root -m 0700 "$release_dir/backup-media.py" /opt/liftcontrol/backup-media.py
install -d -o root -g root -m 0700 /srv/liftcontrol-data/backups
python3 /opt/liftcontrol/backup-media.py --after-update
"${base[@]}" up -d --no-build --no-deps --force-recreate api
healthy=0
for attempt in {1..30}; do
  if curl --fail --silent --max-time 4 http://127.0.0.1:18080/api/health/ > "$backup/health.json"; then
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1])).get("version") == sys.argv[2]' "$backup/health.json" "$target"; then healthy=1; break; fi
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { echo 'Не прошла проверка Android API.'; exit 1; }
# The new API is serving traffic. Later timer/program maintenance must not roll
# it back to a filesystem snapshot that no longer includes new uploads.
trap - EXIT
if [[ ! -s compose.inspections.yaml ]]; then
  install -o root -g root -m 0644 "$release_dir/compose.inspections.yaml" compose.inspections.yaml
  base+=(-f compose.inspections.yaml)
fi
for worker_name in push-worker native-push-worker inspection-reminder-worker; do
  if "${base[@]}" config --services | grep -qx "$worker_name"; then "${base[@]}" up -d --no-build --no-deps --force-recreate "$worker_name"; fi
done
# Keep the installed certificate renewal program compatible with the new API.
# Refresh the public access programs before applying the upload limit.
if [[ -s public/access.py ]]; then
  mkdir -p "$backup/public-programs"
  for program in access.py setup-public.sh renew-public.sh status-public.sh rollback-public.sh configure-push.sh compose.push.yaml; do
    [[ ! -f "public/$program" ]] || cp -p "public/$program" "$backup/public-programs/$program"
    mode=0700
    [[ "$program" != *.yaml ]] || mode=0600
    install -m "$mode" "$release_dir/$program" "public/.$program.next"
    mv -f "public/.$program.next" "public/$program"
  done
fi
if [[ -s compose.public.yaml && -s public/nginx/default.conf ]]; then
  python3 "$release_dir/access.py" upload-limit
fi
cp "$release_dir/SOURCE_COMMIT.txt" "$backup/installed-source.txt"
if command -v systemctl >/dev/null && [[ -d /run/systemd/system ]]; then
  cat > /etc/systemd/system/liftcontrol-media-backup.service <<'SERVICE'
[Unit]
Description=Verified LiftControl database and media backup
After=docker.service
Requires=docker.service
[Service]
Type=oneshot
UMask=0077
ExecStart=/usr/bin/python3 /opt/liftcontrol/backup-media.py
SERVICE
  cat > /etc/systemd/system/liftcontrol-media-backup.timer <<'TIMER'
[Unit]
Description=Daily LiftControl backup
[Timer]
OnCalendar=*-*-* 03:30:00 Asia/Chita
RandomizedDelaySec=15m
Persistent=true
[Install]
WantedBy=timers.target
TIMER
  systemctl daemon-reload
  systemctl enable --now liftcontrol-media-backup.timer
fi
echo "Панель и API $target установлены. Лифты, заявки, аккаунты и фото сохранены."
echo 'Файлы: /srv/liftcontrol-data/media; резервные копии: /srv/liftcontrol-data/backups'
echo 'PWA: обновление доступно при следующем открытии панели.'
echo 'Для автоматических обновлений: sudo bash install-auto-update.sh'
echo "Резервная копия: $backup"
