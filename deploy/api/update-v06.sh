#!/usr/bin/env bash
# Authorized pilot-data replacement: accounts survive; pg_dump precedes all mutations.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash update-v06.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for file in liftcontrol-api-v06-amd64.tar.gz RELEASE.sha256 compose.v06.yaml SOURCE_COMMIT.txt; do
  test -s "$file" || { echo "Отсутствует $file"; exit 1; }
done
sha256sum --check RELEASE.sha256
install_root=/opt/liftcontrol
cd "$install_root"
for file in compose.yaml compose.api.yaml compose.v04.yaml; do
  test -s "$file" || { echo "Не найден $install_root/$file. Нужна установленная 0.4 или 0.5."; exit 1; }
done
base=(docker compose -f "$install_root/compose.yaml" -f "$install_root/compose.api.yaml" -f "$install_root/compose.v04.yaml")
[[ ! -s "$install_root/compose.v05.yaml" ]] || base+=(-f "$install_root/compose.v05.yaml")
[[ ! -s "$install_root/compose.v06.yaml" ]] || base+=(-f "$install_root/compose.v06.yaml")
[[ ! -s "$install_root/compose.push.yaml" ]] || base+=(-f "$install_root/compose.push.yaml")
[[ ! -s "$install_root/compose.public.yaml" ]] || base+=(-f "$install_root/compose.public.yaml")
next=("${base[@]}" -f "$release_dir/compose.v06.yaml")
"${next[@]}" config -q
old_container=$("${base[@]}" ps -q api)
test -n "$old_container" || { echo 'Контейнер API не найден. Остановлено без изменений.'; exit 1; }
old_image=$(docker inspect "$old_container" --format '{{.Image}}')
project=$(docker inspect "$old_container" --format '{{index .Config.Labels "com.docker.compose.project"}}')
worker_ids=$(docker ps -q --filter "label=com.docker.compose.project=$project" --filter 'label=com.docker.compose.service=push-worker')
stamp=$(date -u +%Y%m%d-%H%M%S)
backup_dir="$install_root/backups/before-v06-$stamp"
mkdir -p "$backup_dir"
[[ ! -e "$install_root/compose.v06.yaml" ]] || cp -a "$install_root/compose.v06.yaml" "$backup_dir/compose.previous-v06.yaml"
old_tag="liftcontrol-api:before-v06-$stamp"
docker tag "$old_image" "$old_tag"
printf 'services:\n  api:\n    image: %s\n' "$old_tag" > "$backup_dir/compose.rollback.yaml"
if [[ -n "$worker_ids" ]]; then
  old_worker=${worker_ids%%$'\n'*}
  worker_image=$(docker inspect "$old_worker" --format '{{.Image}}')
  docker tag "$worker_image" "liftcontrol-api:worker-before-v06-$stamp"
  printf '  push-worker:\n    image: liftcontrol-api:worker-before-v06-%s\n' "$stamp" >> "$backup_dir/compose.rollback.yaml"
fi
docker load --input "$release_dir/liftcontrol-api-v06-amd64.tar.gz"
docker image inspect liftcontrol-api:0.6 >/dev/null
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  -e DJANGO_DEBUG=True --entrypoint python liftcontrol-api:0.6 manage.py check
stopped=0
snapshot=0
changed=0
recover() {
  result=$?
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    "${next[@]}" stop api >/dev/null 2>&1 || true
    if [[ -e "$backup_dir/compose.previous-v06.yaml" ]]; then
      cp -a "$backup_dir/compose.previous-v06.yaml" "$install_root/compose.v06.yaml"
    else
      rm -f "$install_root/compose.v06.yaml"
    fi
    if [[ $changed -eq 1 && $snapshot -eq 1 ]]; then
      echo 'Ошибка обновления: восстанавливаем базу из проверенной копии до запуска прежнего API.'
      if ! "${base[@]}" exec -T db dropdb --force --if-exists -U postgres liftcontrol \
        || ! "${base[@]}" exec -T db createdb -U postgres -T template0 liftcontrol \
        || ! "${base[@]}" exec -T db pg_restore --exit-on-error --clean --if-exists -U postgres -d liftcontrol < "$backup_dir/database.dump"; then
        echo "Автовосстановление не завершено. API оставлен остановленным. Копия: $backup_dir"
        return
      fi
    fi
    "${base[@]}" -f "$backup_dir/compose.rollback.yaml" up -d --no-build --no-deps api || true
    if [[ -n "$worker_ids" ]]; then
      # IDs are returned solely by docker's label filters for this project's worker.
      read -r -a previous_workers <<< "${worker_ids//$'\n'/ }"
      if [[ -s "$install_root/compose.push.yaml" ]]; then
        "${base[@]}" -f "$backup_dir/compose.rollback.yaml" up -d --no-build --no-deps push-worker || true
      else
        docker start "${previous_workers[@]}" >/dev/null || true
      fi
    fi
    echo "Предыдущий API восстановлен. Резервная копия: $backup_dir"
  fi
}
trap recover EXIT
"${base[@]}" stop api
stopped=1
if [[ -n "$worker_ids" ]]; then
  read -r -a previous_workers <<< "${worker_ids//$'\n'/ }"
  docker stop "${previous_workers[@]}" >/dev/null
fi
"${base[@]}" exec -T db pg_dump -U postgres -d liftcontrol -Fc > "$backup_dir/database.dump"
test -s "$backup_dir/database.dump"
"${base[@]}" exec -T db pg_restore --list < "$backup_dir/database.dump" > "$backup_dir/database.list"
snapshot=1
if docker volume inspect liftcontrol_private_media >/dev/null 2>&1; then
  docker run --rm --user 10001:10001 --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
    -v liftcontrol_private_media:/media:ro --entrypoint tar liftcontrol-api:0.6 -C /media -czf - . > "$backup_dir/media.tar.gz"
fi
changed=1
"${next[@]}" --profile maintenance run --rm --no-deps -T migrate
"${base[@]}" exec -T db psql -U postgres -d liftcontrol -v ON_ERROR_STOP=1 <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO liftapp;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
SQL
install -d -m 700 -o 999 -g 10001 "$backup_dir/import"
# Import has its own JSON snapshot and one-time marker; a repeated installer never clears new work.
"${next[@]}" --profile maintenance run --rm --no-deps -T \
  -v "$backup_dir/import:/backup" migrate python manage.py import_megapolis \
  --apply --replace-work-data --backup /backup/work-data.json
"${next[@]}" up -d --no-build --no-deps api
healthy=0
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18080/api/health/ > "$backup_dir/health.json"; then
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["version"] == "0.6"' "$backup_dir/health.json"; then healthy=1; break; fi
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { echo 'Проверка версии 0.6 не пройдена.'; exit 1; }
"${next[@]}" exec -T api python manage.py shell -c "from core.models import AuditEvent; assert AuditEvent.objects.filter(action='data.megapolis_imported_v1').exists(); print('MEGAPOLIS IMPORT VERIFIED')"
if [[ -s "$install_root/compose.push.yaml" ]]; then
  "${next[@]}" up -d --no-build --no-deps push-worker
fi
install -m 600 "$release_dir/compose.v06.yaml" "$install_root/compose.v06.yaml"
stopped=0
trap - EXIT
printf 'LiftControl 0.6 установлен. Резервная копия: %s\n' "$backup_dir"
echo 'Интерфейс: http://127.0.0.1:18080/ — выберите Мегаполис в настройках.'
echo 'Свяжите аккаунты механиков с карточками Мегаполиса через одноразовые приглашения.'
echo 'Серверные push включаются отдельно: см. UPDATE-v06.md. Проверка уведомлений телефона уже доступна.'
