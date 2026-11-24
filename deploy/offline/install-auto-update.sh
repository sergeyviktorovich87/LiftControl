#!/usr/bin/env bash
# Run once on the host from the verified release package.
set -Eeuo pipefail
umask 077
[[ $EUID -eq 0 ]] || { echo 'Run with sudo'; exit 1; }
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
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
install -o root -g root -m 0755 github-updater.py /usr/local/lib/liftcontrol/github-updater.py
install -o root -g root -m 0644 liftcontrol-github-update.service /etc/systemd/system/liftcontrol-github-update.service
install -o root -g root -m 0644 liftcontrol-github-update.timer /etc/systemd/system/liftcontrol-github-update.timer
systemctl daemon-reload
systemctl enable --now liftcontrol-github-update.timer
systemctl list-timers liftcontrol-github-update.timer --no-pager
echo 'Automatic update is enabled. Run systemctl start liftcontrol-github-update.service for an immediate check.'
