#!/usr/bin/env bash
# Run once on the host from the verified release package.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
preserve=${1:-}
[[ -z "$preserve" || "$preserve" == '--preserve' ]] || exit 2
command -v systemctl >/dev/null
test -d /run/systemd/system
command -v gh >/dev/null || { echo 'Install current official GitHub CLI (gh) first'; exit 1; }
help=$(gh attestation verify --help)
for flag in --bundle --signer-workflow --source-ref --source-digest --deny-self-hosted-runners; do
  grep -q -- "$flag" <<< "$help" || { echo 'GitHub CLI is too old; update it'; exit 1; }
done
sha256sum --check --strict PATCH.sha256 >/dev/null
install -d -o root -g root -m 0755 /usr/local/lib/liftcontrol
install -d -o root -g root -m 0700 /var/lib/liftcontrol-updater
for program in github-updater.py github-update-bridge.py; do
  install -o root -g root -m 0755 "$program" "/usr/local/lib/liftcontrol/.$program.next"
  mv -f "/usr/local/lib/liftcontrol/.$program.next" "/usr/local/lib/liftcontrol/$program"
done
for unit in liftcontrol-github-bridge.service liftcontrol-github-bridge.timer; do
  install -o root -g root -m 0644 "$unit" "/etc/systemd/system/$unit"
done
install -o root -g root -m 0644 liftcontrol-github-update.service /etc/systemd/system/liftcontrol-github-update.service
install -o root -g root -m 0644 liftcontrol-github-update.timer /etc/systemd/system/liftcontrol-github-update.timer
systemctl daemon-reload
if [[ "$preserve" != '--preserve' ]] || systemctl is-enabled --quiet liftcontrol-github-update.timer; then
  systemctl enable --now liftcontrol-github-update.timer
fi
systemctl enable --now liftcontrol-github-bridge.timer
systemctl list-timers liftcontrol-github-update.timer --no-pager
echo 'Automatic update is enabled. Run systemctl start liftcontrol-github-update.service for an immediate check.'
