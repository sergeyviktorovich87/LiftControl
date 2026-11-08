#!/usr/bin/env bash
# Update an installed 0.8/0.9 using its existing verified dependencies. Never reset data.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash update-panel.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for file in Dockerfile PATCH.sha256 SOURCE_COMMIT.txt payload/requirements.txt; do
  test -s "$file" || { echo "Отсутствует $file"; exit 1; }
done
sha256sum --check --strict PATCH.sha256
cd /opt/liftcontrol
base=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
test -s compose.v06.yaml || { echo 'Сначала нужна установленная версия 0.6.'; exit 1; }
for overlay in compose.v05.yaml compose.v06.yaml compose.push.yaml compose.public.yaml compose.updates.yaml compose.fcm.yaml; do
  [[ ! -s "$overlay" ]] || base+=(-f "$overlay")
done
"${base[@]}" config -q
container=$("${base[@]}" ps -q api)
test -n "$container" || { echo 'Контейнер API не найден.'; exit 1; }
installed=$(curl --fail --silent http://127.0.0.1:18080/api/health/ | python3 -c 'import json,sys; print(json.load(sys.stdin).get("version",""))')
[[ "$installed" == 0.8 || "$installed" == 0.9 ]] || { echo 'Этот компактный пакет требует установленную 0.8 или 0.9.'; exit 1; }
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
for worker_name in push-worker native-push-worker; do
  worker=$("${base[@]}" ps -q "$worker_name" 2>/dev/null || true)
  if [[ -n "$worker" ]]; then
    workers+=("$worker_name")
    worker_image=$(docker inspect "$worker" --format '{{.Image}}')
    worker_tag="liftcontrol-api:$worker_name-before-update-$stamp"
    docker tag "$worker_image" "$worker_tag"
    printf '  %s:\n    image: %s\n' "$worker_name" "$worker_tag" >> "$backup/compose.rollback.yaml"
  fi
done
stopped=0
recover() {
  result=$?
  if [[ $result -ne 0 ]]; then
    docker tag "$previous_image" liftcontrol-api:0.6 || true
  fi
  if [[ $result -ne 0 && $stopped -eq 1 ]]; then
    "${base[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate api || true
    for worker_name in "${workers[@]}"; do "${base[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate "$worker_name" || true; done
    echo "Обновление не завершилось. Предыдущий образ возвращён; копия базы: $backup/database.dump"
  fi
}
trap recover EXIT
docker build --pull=false --network none --build-arg "BASE_IMAGE=$previous_tag" --build-arg "BUILD_COMMIT=$source_commit" -t liftcontrol-api:0.6 "$release_dir"
docker run --rm --read-only --network none --cap-drop ALL --security-opt no-new-privileges \
  -e DJANGO_DEBUG=True --entrypoint python liftcontrol-api:0.6 manage.py check
"${base[@]}" stop api
stopped=1
for worker_name in "${workers[@]}"; do "${base[@]}" stop "$worker_name"; done
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
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1])).get("version") == "0.9"' "$backup/health.json"; then healthy=1; break; fi
  fi
  sleep 2
done
[[ $healthy -eq 1 ]] || { echo 'Не прошла проверка Android API.'; exit 1; }
for worker_name in push-worker native-push-worker; do
  if "${base[@]}" config --services | grep -qx "$worker_name"; then "${base[@]}" up -d --no-build --no-deps --force-recreate "$worker_name"; fi
done
# Keep the installed certificate renewal program compatible with the new API.
# Only programs are updated; certificates, keys, NGINX and timer settings stay in place.
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
cp "$release_dir/SOURCE_COMMIT.txt" "$backup/installed-source.txt"
echo 'Панель и API 0.9 установлены. Лифты, заявки, аккаунты, фото и настройки доступа сохранены.'
echo "Резервная копия: $backup"
