#!/usr/bin/env bash
# Entry point for future server updates. Uses the preserving-data installer.
set -Eeuo pipefail
release_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd "$release_dir"
sha256sum --check RELEASE.sha256
bash "$release_dir/setup-updates.sh"
exec bash "$release_dir/update-android.sh"
