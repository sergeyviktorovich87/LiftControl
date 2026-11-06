#!/usr/bin/env bash
set -Eeuo pipefail
COMPOSE=/opt/liftcontrol/compose.yaml
BACKUPS=/opt/liftcontrol/backups
ok() { printf 'OK   %s\n' "$*"; }
warn() { printf 'WARN %s\n' "$*"; }

printf '\nLiftControl infrastructure audit (read-only)\n'
if [[ "$(id -u)" != 0 ]]; then echo 'Run: sudo bash audit.sh'; exit 2; fi
if command -v git >/dev/null; then ok "Git $(git --version)"; else warn 'Git absent'; fi
if systemctl is-active --quiet docker; then ok 'Docker service'; else warn 'Docker inactive'; fi
if command -v docker >/dev/null && docker compose version >/dev/null 2>&1; then ok 'Docker Compose'; else warn 'Docker Compose unavailable'; fi
if command -v ufw >/dev/null && ufw status | grep -q 'Status: active'; then ok 'UFW active'; else warn 'UFW not active'; fi
if systemctl is-active --quiet unattended-upgrades; then ok 'Unattended upgrades running'; else warn 'Unattended upgrades status requires inspection'; fi
if systemctl is-enabled --quiet liftcontrol-backup.timer; then ok 'Daily backup timer enabled'; else warn 'Daily backup timer not enabled'; fi
if [[ -f /opt/liftcontrol/scripts/backup-db.sh ]] && grep -q 'pg_dumpall' /opt/liftcontrol/scripts/backup-db.sh; then
  ok 'Backup script includes PostgreSQL globals'
else
  warn 'Backup script does not back up roles automatically'
fi
if [[ -f "$COMPOSE" ]]; then
  ok 'Compose configuration exists'
  if docker compose -f "$COMPOSE" config -q 2>/dev/null; then ok 'Compose syntax'; else warn 'Compose invalid'; fi
  if docker compose -f "$COMPOSE" ps --status running --services 2>/dev/null | grep -qx db; then ok 'DB container running'; else warn 'DB not running'; fi
  if docker compose -f "$COMPOSE" config 2>/dev/null | grep -Eq '(^|[[:space:]])published:'; then warn 'Compose publishes a TCP port: review exposure'; else ok 'No published Compose ports'; fi
else
  warn 'Compose configuration missing'
fi
if [[ -d "$BACKUPS" ]]; then
  db=$(find "$BACKUPS" -maxdepth 1 -name 'liftcontrol-*.dump' -type f | wc -l)
  roles=$(find "$BACKUPS" -maxdepth 1 -name 'postgres-globals-*.sql' -type f | wc -l)
  ok "Local backup files: database=$db roles=$roles"
  if find "$BACKUPS" -maxdepth 1 -name 'liftcontrol-*.dump' -mmin -1560 -print -quit | grep -q .; then ok 'Recent DB backup (26h)'; else warn 'DB backup stale'; fi
  if find "$BACKUPS" -maxdepth 1 -name 'postgres-globals-*.sql' -mmin -1560 -print -quit | grep -q .; then ok 'Recent roles backup (26h)'; else warn 'Roles backup stale'; fi
else
  warn 'Backups directory missing'
fi
if systemctl is-enabled --quiet liftcontrol-healthcheck.timer 2>/dev/null; then ok 'Local healthcheck timer'; else warn 'Local healthcheck timer not enabled'; fi
if command -v sshd >/dev/null; then
  sshcfg=$(sshd -T 2>/dev/null || true)
  if grep -qx 'passwordauthentication no' <<<"$sshcfg"; then ok 'SSH password auth disabled'; else warn 'SSH password authentication not confirmed'; fi
  if grep -qx 'permitrootlogin no' <<<"$sshcfg"; then ok 'SSH root login disabled'; else warn 'SSH root restriction not confirmed'; fi
fi
printf '\nThis audit does NOT prove an off-host backup or recovery drill.\n'
