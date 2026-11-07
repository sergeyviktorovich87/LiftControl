#!/usr/bin/env bash
# Add native-device sessions to an installed 0.6 stack. Never import/reset work data.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash update-android.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for file in liftcontrol-api-v06-amd64.tar.gz RELEASE.sha256 SOURCE_COMMIT.txt; do
  test -s "$file" || { echo "Отсутствует $file"; exit 1; }
done
sha256sum --check RELEASE.sha256
cd /opt/liftcontrol
base=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
test -s compose.v06.yaml || { echo 'Сначала нужна установленная версия 0.6.'; exit 1; }
for overlay in compose.v05.yaml compose.v06.yaml compose.push.yaml compose.public.yaml; do
  [[ ! -s "$overlay" ]] || base+=(-f "$overlay")
done
"${base[@]}" config -q
container=$("${base[@]}" ps -q api)
test -n "$container" || { echo 'Контейнер API не найден.'; exit 1; }
stamp=$(date -u +%Y%m%d-%H%M%S)
backup="/opt/liftcontrol/backups/before-android-$stamp"
mkdir -p "$backup"
previous_image=$(docker inspect "$container" --format '{{.Image}}')
previous_tag="liftcontrol-api:before-android-$stamp"
docker tag "$previous_image" "$previous_tag"
printf 'services:\n  api:\n    image: %s\n' "$previous_tag" > "$backup/compose.rollback.yaml"
worker=$("${base[@]}" ps -q push-worker 2>/dev/null || true)
if [[ -n "$worker" ]]; then
  worker_image=$(docker inspect "$worker" --format '{{.Image}}')
  worker_tag="liftcontrol-api:worker-before-android-$stamp"
  docker tag "$worker_image" "$worker_tag"
  printf '  push-worker:\n    image: %s\n' "$worker_tag" >> "$backup/compose.rollback.yaml"
fi
docker load --input "$release_dir/liftcontrol-api-v06-amd64.tar.gz"
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  -e DJANGO_DEBUG=True --entrypoint python liftcontrol-api:0.6 manage.py check
stopped=0
recover() {
  result=$?
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    "${base[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate api || true
    [[ -z "$worker" ]] || "${base[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate push-worker || true
    echo "Обновление не завершилось. Предыдущий образ возвращён; копия базы: $backup/database.dump"
  fi
}
trap recover EXIT
"${base[@]}" stop api
stopped=1
[[ -z "$worker" ]] || "${base[@]}" stop push-worker
"${base[@]}" exec -T db pg_dump -U postgres -d liftcontrol -Fc > "$backup/database.dump"
test -s "$backup/database.dump"
"${base[@]}" exec -T db pg_restore --list < "$backup/database.dump" > "$backup/database.list"
"${base[@]}" --profile maintenance run --rm --no-deps -T migrate
"${base[@]}" exec -T db psql -U postgres -d liftcontrol -v ON_ERROR_STOP=1 <<'SQL'
GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA app TO liftapp;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE postgres IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
SQL
"${base[@]}" up -d --no-build --no-deps --force-recreate api
healthy=0
for attempt in {1..30}; do
  if curl --fail --silent http://127.0.0.1:18080/api/health/ > "$backup/health.json"; then
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1])).get("android_api") == 1' "$backup/health.json"; then healthy=1; break; fi
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { echo 'Не прошла проверка Android API.'; exit 1; }
[[ -z "$worker" ]] || "${base[@]}" up -d --no-build --no-deps --force-recreate push-worker
cp "$release_dir/SOURCE_COMMIT.txt" "$backup/installed-source.txt"
echo 'Android API установлен. Лифты, заявки, аккаунты, фото и настройки доступа сохранены.'
echo "Резервная копия: $backup"
