#!/usr/bin/env bash
# Explicit full installation: applies the backed-up 0.6 import, then enables public HTTPS.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash install-v06-with-https.sh 89.169.20.154'; exit 1; }
[[ $# -ge 1 ]] || { echo 'Укажите адрес: sudo bash install-v06-with-https.sh 89.169.20.154'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
[[ -s RELEASE.sha256 ]] || { echo 'Нужен полный архив LiftControl-v0.6-amd64.'; exit 1; }
sha256sum --check RELEASE.sha256
python3 - "$1" <<'PY'
import sys
from access import normalize_host
normalize_host(sys.argv[1])
PY
bash "$release_dir/update-v06.sh"
exec bash "$release_dir/setup-public.sh" "$@"
