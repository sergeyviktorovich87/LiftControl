#!/usr/bin/env bash
# Install from a VERIFIED private GitHub Actions artifact. Does not open API/DB ports.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash update-v05.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for file in liftcontrol-api-v05-amd64.tar.gz liftcontrol-api-v05-amd64.tar.gz.sha256 compose.v05.yaml SOURCE_COMMIT.txt; do
  test -s "$file" || { echo "Отсутствует $file"; exit 1; }
done
sha256sum --check liftcontrol-api-v05-amd64.tar.gz.sha256
install_root=/opt/liftcontrol
cd "$install_root"
for file in compose.yaml compose.api.yaml compose.v04.yaml; do
  test -s "$file" || { echo "Не найден $install_root/$file. Сначала установите 0.4."; exit 1; }
done
base=(docker compose -f "$install_root/compose.yaml" -f "$install_root/compose.api.yaml" -f "$install_root/compose.v04.yaml")
next=("${base[@]}" -f "$release_dir/compose.v05.yaml")
"${next[@]}" config -q
old_container=$("${base[@]}" ps -q api)
test -n "$old_container" || { echo 'Контейнер API не найден. Остановлено без изменений.'; exit 1; }
old_image=$(docker inspect "$old_container" --format '{{.Image}}')
stamp=$(date -u +%Y%m%d-%H%M%S)
backup_dir="$install_root/backups/before-v05-$stamp"
mkdir -p "$backup_dir"
old_tag="liftcontrol-api:before-v05-$stamp"
docker tag "$old_image" "$old_tag"
printf 'services:\n  api:\n    image: %s\n' "$old_tag" > "$backup_dir/compose.rollback.yaml"
# Load and verify the image before touching the running application.
docker load --input "$release_dir/liftcontrol-api-v05-amd64.tar.gz"
docker image inspect liftcontrol-api:0.5 >/dev/null
stopped=0
recover() {
  result=$?
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    echo 'Установка не завершена. Возвращаем предыдущий образ API. Миграции базы НЕ откатываем.'
    "${base[@]}" -f "$backup_dir/compose.rollback.yaml" up -d --no-build --no-deps api || true
    echo "Резервная копия и файлы отката: $backup_dir"
  fi
}
trap recover EXIT
# One known writer (API) is stopped while snapshot and migrations run.
"${base[@]}" stop api
stopped=1
"${base[@]}" exec -T db pg_dump -U postgres -d liftcontrol -Fc > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump"
"${base[@]}" exec -T db pg_restore --list < "$backup_dir/database.dump" > "$backup_dir/database.list"
if docker volume inspect liftcontrol_private_media >/dev/null 2>&1; then
  docker run --rm --user 10001:10001 --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
    -v liftcontrol_private_media:/media:ro --entrypoint tar liftcontrol-api:0.5 -C /media -czf - . > "$backup_dir/media.tar.gz"
fi
"${next[@]}" --profile maintenance run --rm --no-deps -T migrate
"${base[@]}" exec -T db psql -U postgres -d liftcontrol -v ON_ERROR_STOP=1 <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO liftapp;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
SQL
"${next[@]}" up -d --no-build --no-deps api
healthy=0
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18080/api/health/ > "$backup_dir/health.json"; then
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["version"] == "0.5"' "$backup_dir/health.json"; then healthy=1; break; fi
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { echo 'Проверка версии 0.5 не пройдена.'; exit 1; }
"${next[@]}" exec -T api python -c 'from pathlib import Path; p=Path("/app/private_media/.write-check"); p.write_text("ok"); p.unlink(); print("PRIVATE MEDIA OK")'
install -m 600 "$release_dir/compose.v05.yaml" "$install_root/compose.v05.yaml"
stopped=0
trap - EXIT
printf 'LiftControl 0.5 установлен. Резервная копия: %s\n' "$backup_dir"
echo 'SSH-туннель и рабочий интерфейс: http://127.0.0.1:18080/'
echo 'Push-рассылку включаем отдельно после настройки HTTPS и ключей VAPID.'
