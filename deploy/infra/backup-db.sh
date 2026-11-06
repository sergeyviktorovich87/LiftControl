#!/usr/bin/env bash
set -Eeuo pipefail
umask 077
DIR=/opt/liftcontrol/backups
COMPOSE=/opt/liftcontrol/compose.yaml
STAMP=$(date -u +%Y%m%d-%H%M%S)
DB_TMP=$(mktemp "$DIR/liftcontrol-$STAMP-XXXXXX.partial")
ROLE_TMP=$(mktemp "$DIR/postgres-globals-$STAMP-XXXXXX.partial")
trap 'rm -f -- "$DB_TMP" "$ROLE_TMP"' EXIT

docker compose -f "$COMPOSE" exec -T db pg_dump -U postgres -d liftcontrol -Fc > "$DB_TMP"
docker compose -f "$COMPOSE" exec -T db pg_dumpall -U postgres --globals-only > "$ROLE_TMP"
test -s "$DB_TMP" && test -s "$ROLE_TMP"
docker compose -f "$COMPOSE" exec -T db pg_restore --list < "$DB_TMP" >/dev/null
grep -qE '^CREATE ROLE liftapp;' "$ROLE_TMP"

mv "$DB_TMP" "${DB_TMP%.partial}.dump"
mv "$ROLE_TMP" "${ROLE_TMP%.partial}.sql"
echo 'BACKUP OK: database and roles'
