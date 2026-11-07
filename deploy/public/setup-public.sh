#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Запустите: sudo bash setup-public.sh 89.169.20.154'; exit 1; }
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
if [[ -f PUBLIC_RELEASE.sha256 ]]; then sha256sum --check PUBLIC_RELEASE.sha256; fi
exec python3 "$release_dir/access.py" setup "$@"
