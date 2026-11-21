#!/usr/bin/env bash
# Publish an already verified Android build; the API keeps read-only access.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash publish-android.sh'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
for item in publish-update.py compose.updates.yaml android-release.json; do
  test -s "$item" || { echo "В пакете отсутствует $item"; exit 1; }
done
[[ ! -f PACKAGE.sha256 ]] || sha256sum --check --strict PACKAGE.sha256
python3 "$release_dir/publish-update.py" --android-release "$release_dir" --check-android > /dev/null
cd /opt/liftcontrol
for item in compose.yaml compose.api.yaml compose.v04.yaml compose.v06.yaml; do
  test -s "$item" || { echo "Не найдена установленная панель: $item"; exit 1; }
done
command -v flock > /dev/null
exec 9>/opt/liftcontrol/.android-publication.lock
flock -n 9 || { echo 'Другая публикация уже выполняется.'; exit 1; }
previous=(docker compose -f compose.yaml -f compose.api.yaml -f compose.v04.yaml)
for overlay in compose.v05.yaml compose.v06.yaml compose.push.yaml compose.public.yaml compose.updates.yaml compose.fcm.yaml compose.fcm-updates.yaml compose.media.yaml; do
  [[ ! -s "$overlay" ]] || previous+=(-f "$overlay")
done
"${previous[@]}" config -q
container=$("${previous[@]}" ps -q api)
test -n "$container" || { echo 'Панель не запущена.'; exit 1; }
installed=$(curl --fail --silent --max-time 5 http://127.0.0.1:18080/api/health/ | python3 -c 'import json,sys; d=json.load(sys.stdin); assert "updates" in d.get("capabilities",[]), "На сервере ещё нет механизма обновлений APK"; print(d["version"])')
install -d -o root -g root -m 0755 /opt/liftcontrol/updates /opt/liftcontrol/backups
stamp=$(date -u +%Y%m%d-%H%M%S)
backup=$(mktemp -d "/opt/liftcontrol/backups/apk-publication-$stamp-XXXXXX")
[[ ! -f updates/release.json ]] || cp -p updates/release.json "$backup/release.json"
created_overlay=0
mount_changed=0
recover() {
  result=$?
  if [[ $result -ne 0 ]]; then
    if [[ $created_overlay -eq 1 ]]; then rm -f /opt/liftcontrol/compose.updates.yaml; fi
    if [[ $mount_changed -eq 1 ]]; then
      "${previous[@]}" -f "$backup/compose.rollback.yaml" up -d --no-build --no-deps --force-recreate api || true
    fi
    echo "Публикация не подтверждена. Диагностика и прежний каталог: $backup"
  fi
}
trap recover EXIT
if [[ ! -s compose.updates.yaml ]]; then
  install -o root -g root -m 0644 "$release_dir/compose.updates.yaml" compose.updates.yaml
  created_overlay=1
fi
current=("${previous[@]}")
[[ $created_overlay -eq 0 ]] || current+=(-f compose.updates.yaml)
"${current[@]}" config --format json | python3 -c '
import json,sys
a=json.load(sys.stdin)["services"]["api"]
assert a.get("environment",{}).get("LIFTCONTROL_UPDATES_DIR")=="/updates", "Неожиданная настройка каталога обновлений"
assert any(v.get("type")=="bind" and v.get("source")=="/opt/liftcontrol/updates" and v.get("target")=="/updates" and v.get("read_only") is True for v in a.get("volumes",[])), "Нужен каталог /updates только для чтения"
'
mounted=$(docker inspect "$container" --format '{{json .Mounts}}' | python3 -c 'import json,sys; print(int(any(m.get("Destination")=="/updates" and m.get("Source")=="/opt/liftcontrol/updates" and m.get("RW") is False for m in json.load(sys.stdin))))')
configured=$(docker inspect "$container" --format '{{json .Config.Env}}' | python3 -c 'import json,sys; print(int("LIFTCONTROL_UPDATES_DIR=/updates" in json.load(sys.stdin)))')
if [[ $mounted != 1 || $configured != 1 ]]; then
  previous_image=$(docker inspect "$container" --format '{{.Image}}')
  previous_tag="liftcontrol-api:before-apk-publication-$stamp"
  docker tag "$previous_image" "$previous_tag"
  printf 'services:\n  api:\n    image: %s\n' "$previous_tag" > "$backup/compose.rollback.yaml"
  mount_changed=1
  "${current[@]}" up -d --no-build --no-deps --force-recreate api
fi
healthy=0
for attempt in {1..20}; do
  if curl --fail --silent --max-time 2 http://127.0.0.1:18080/api/health/ > "$backup/health.json"; then
    if python3 -c 'import json,sys; assert json.load(open(sys.argv[1]))["version"]==sys.argv[2]' "$backup/health.json" "$installed"; then healthy=1; break; fi
  fi
  sleep 1
done
[[ $healthy -eq 1 ]] || { echo 'Панель не прошла проверку после подключения каталога.'; exit 1; }
python3 "$release_dir/publish-update.py" --android-release "$release_dir" --output /opt/liftcontrol/updates
container=$("${current[@]}" ps -q api)
docker exec "$container" python -c '
import hashlib,json,os,pathlib
root=pathlib.Path(os.environ.get("LIFTCONTROL_UPDATES_DIR","/updates"))
item=json.loads((root/"release.json").read_text())["android"]
apk=root/item["filename"]
assert apk.stat().st_size==item["size"] and hashlib.sha256(apk.read_bytes()).hexdigest()==item["sha256"]
print("Сервер видит Android "+item["version"]+" · сборка "+str(item["version_code"]))
'
echo 'Обновление опубликовано. Сотрудники увидят его при следующей проверке приложения.'
echo 'Для немедленной проверки: Профиль и настройки → Обновления → Проверить обновления.'
echo 'Публикация APK не устанавливает приложение на сервер и не меняет базу заявок.'
