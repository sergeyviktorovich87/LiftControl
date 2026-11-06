#!/usr/bin/env bash
set -Eeuo pipefail
COMPOSE=/opt/liftcontrol/compose.yaml
BACKUPS=/opt/liftcontrol/backups
BAD=0
ok() { echo "OK: $*"; }
warn() { echo "WARN: $*"; BAD=1; }

if systemctl is-active --quiet docker; then ok 'Docker active'; else warn 'Docker not active'; fi
if [[ -f "$COMPOSE" ]] && docker compose -f "$COMPOSE" ps -q db >/dev/null 2>&1; then
  cid=$(docker compose -f "$COMPOSE" ps -q db)
  if [[ -n "$cid" ]] && [[ "$(docker inspect -f '{{.State.Health.Status}}' "$cid" 2>/dev/null)" == healthy ]]; then
    ok 'PostgreSQL healthy'
  else
    warn 'PostgreSQL not healthy'
  fi
else
  warn 'Compose missing or inaccessible'
fi

disk=$(df -P / | awk 'NR==2 {gsub(/%/,"",$5);print $5}')
if (( disk < 85 )); then ok "Disk usage ${disk}%"; else warn "Disk usage ${disk}%"; fi

if find "$BACKUPS" -maxdepth 1 -name 'liftcontrol-*.dump' -mmin -1560 -print -quit 2>/dev/null | grep -q .; then
  ok 'Recent database backup'
else
  warn 'No recent database backup within 26h'
fi
if find "$BACKUPS" -maxdepth 1 -name 'postgres-globals-*.sql' -mmin -1560 -print -quit 2>/dev/null | grep -q .; then
  ok 'Recent PostgreSQL roles backup'
else
  warn 'No recent roles backup within 26h'
fi
if [[ $BAD == 0 ]]; then
  echo 'HEALTH OK'
else
  echo 'HEALTH FAILED; check journalctl -u liftcontrol-healthcheck.service'
  exit 1
fi
