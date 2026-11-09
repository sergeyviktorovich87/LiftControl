#!/usr/bin/env bash
set -Eeuo pipefail
[[ $EUID -eq 0 ]] || { echo 'Запустите через sudo.'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
test -s /opt/liftcontrol/compose.yaml
install -d -o root -g root -m 0755 /opt/liftcontrol/updates
upload_owner=${SUDO_USER:-root}
install -d -o "$upload_owner" -g "$(id -gn "$upload_owner")" -m 0755 /opt/liftcontrol/updates/android
install -o root -g root -m 0644 "$release_dir/compose.updates.yaml" /opt/liftcontrol/compose.updates.yaml
echo 'Каталог обновлений подготовлен. Приложению разрешено только чтение.'
