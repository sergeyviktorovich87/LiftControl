#!/usr/bin/env bash
# LiftControl base installer: clean Ubuntu 24.04 only. NOT an upgrade script.
set -Eeuo pipefail
umask 077
trap 'echo "INSTALL FAILED near line $LINENO. Inspect /var/log/liftcontrol-install.log" >&2' ERR

[[ $EUID -eq 0 ]] || { echo 'Run with sudo: sudo bash install.sh'; exit 2; }
[[ -f /etc/os-release ]] || { echo 'Ubuntu required'; exit 2; }
. /etc/os-release
[[ "$ID" == ubuntu && "$VERSION_ID" == 24.04 ]] || { echo 'Only Ubuntu 24.04 LTS is supported'; exit 2; }
[[ ! -e /opt/liftcontrol/compose.yaml ]] || { echo 'Existing installation detected; no changes made. Use audit.sh instead.'; exit 2; }
ADMIN_USER="${SUDO_USER:-}"
[[ -n "$ADMIN_USER" && "$ADMIN_USER" != root ]] || { echo 'Run as an existing sudo user, not root'; exit 2; }
ADMIN_HOME=$(getent passwd "$ADMIN_USER" | cut -d: -f6)
[[ -n "$ADMIN_HOME" && -s "$ADMIN_HOME/.ssh/authorized_keys" ]] || { echo 'Admin SSH authorized_keys required before hardening'; exit 2; }
if [[ ! -s "$ADMIN_HOME/.ssh/authorized_keys" ]] || ! id "$ADMIN_USER" >/dev/null; then exit 2; fi
MEM_KB=$(awk '/MemTotal/ {print $2}' /proc/meminfo)
(( MEM_KB >= 750000 )) || { echo 'At least 750 MB RAM required'; exit 2; }
DISK_KB=$(df -Pk / | awk 'NR==2 {print $4}')
(( DISK_KB >= 10000000 )) || { echo 'At least 10 GB free disk space required'; exit 2; }
ROOT_DIR=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
for f in backup-db.sh healthcheck.sh audit.sh; do [[ -s "$ROOT_DIR/$f" ]] || { echo "Missing companion file: $f"; exit 2; }; done

install -m 0600 /dev/null /var/log/liftcontrol-install.log
exec > >(tee -a /var/log/liftcontrol-install.log) 2>&1
printf '\n=== LiftControl fresh-server installer ===\n'
apt-get update
DEBIAN_FRONTEND=noninteractive apt-get install -y ca-certificates curl git gnupg openssl openssh-server ufw unattended-upgrades

# Docker CE from the vendor's signed apt repository. No curl|sh.
if ! docker compose version >/dev/null 2>&1; then
  install -m 0755 -d /etc/apt/keyrings
  curl --fail --silent --show-error --location https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
  chmod a+r /etc/apt/keyrings/docker.asc
  cat > /etc/apt/sources.list.d/docker.sources <<DOCKER_REPO
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Architectures: $(dpkg --print-architecture)
Signed-By: /etc/apt/keyrings/docker.asc
DOCKER_REPO
  apt-get update
  DEBIAN_FRONTEND=noninteractive apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
fi
systemctl enable --now docker
install -m 0755 -d /etc/docker
if [[ ! -e /etc/docker/daemon.json ]]; then
  cat > /etc/docker/daemon.json <<'DOCKER_LOGS'
{"log-driver":"json-file","log-opts":{"max-size":"10m","max-file":"3"}}
DOCKER_LOGS
  systemctl restart docker
else
  echo 'Existing Docker daemon.json preserved; review log rotation manually.'
fi

# Swap on small VPS. Never replace existing swap data.
if ! swapon --show=NAME | grep -qx /swapfile && [[ ! -f /swapfile ]]; then
  fallocate -l 2G /swapfile
  chmod 600 /swapfile
  mkswap /swapfile >/dev/null
  swapon /swapfile
  grep -qE '^/swapfile[[:space:]]' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
fi

install -m 0755 -d /etc/systemd/journald.conf.d /var/log/journal
cat > /etc/systemd/journald.conf.d/30-liftcontrol.conf <<'JOURNAL'
[Journal]
Storage=persistent
SystemMaxUse=200M
MaxRetentionSec=30day
JOURNAL
systemctl restart systemd-journald
cat > /etc/apt/apt.conf.d/51liftcontrol-upgrades <<'UPDATES'
APT::Periodic::Update-Package-Lists "1";
APT::Periodic::Unattended-Upgrade "1";
Unattended-Upgrade::Automatic-Reboot "false";
UPDATES
systemctl enable --now unattended-upgrades || true

# Verify key access before disabling password login.
[[ -s "$ADMIN_HOME/.ssh/authorized_keys" ]] || { echo 'Missing SSH keys; refusing to harden'; exit 2; }
install -m 0755 -d /etc/ssh/sshd_config.d
cat > /etc/ssh/sshd_config.d/10-liftcontrol.conf <<'SSH_CONFIG'
PermitRootLogin no
PasswordAuthentication no
KbdInteractiveAuthentication no
PubkeyAuthentication yes
SSH_CONFIG
install -m 0755 -d /run/sshd
sshd -t
if ! sshd -T | grep -qx 'passwordauthentication no' || ! sshd -T | grep -qx 'permitrootlogin no'; then
  echo 'SSH effective config does not match hardening requirements; aborting.'
  exit 2
fi
SSH_PORT=$(sshd -T | awk '$1=="port" {print $2; exit}')
[[ "$SSH_PORT" =~ ^[0-9]+$ ]] || { echo 'Could not detect SSH port safely'; exit 2; }
ufw allow "$SSH_PORT"/tcp
ufw default deny incoming
ufw default allow outgoing
ufw --force enable
if systemctl is-active --quiet ssh; then
  systemctl reload ssh
else
  systemctl enable --now ssh
fi

ROOT=/opt/liftcontrol
install -m 0700 -d "$ROOT/secrets" "$ROOT/backups" "$ROOT/scripts"
if [[ ! -s "$ROOT/secrets/postgres_admin_password" ]]; then openssl rand -hex 32 > "$ROOT/secrets/postgres_admin_password"; fi
if [[ ! -s "$ROOT/secrets/postgres_app_password" ]]; then openssl rand -hex 32 > "$ROOT/secrets/postgres_app_password"; fi
if [[ ! -s "$ROOT/secrets/postgres_migrator_password" ]]; then openssl rand -hex 32 > "$ROOT/secrets/postgres_migrator_password"; fi
chown 999:999 "$ROOT/secrets/postgres_admin_password"
chmod 0400 "$ROOT/secrets/postgres_admin_password"
chmod 0600 "$ROOT/secrets/postgres_app_password" "$ROOT/secrets/postgres_migrator_password"
cat > "$ROOT/compose.yaml" <<'COMPOSE'
services:
  db:
    image: postgres:18
    restart: unless-stopped
    environment:
      POSTGRES_DB: liftcontrol
      POSTGRES_USER: postgres
      POSTGRES_PASSWORD_FILE: /run/secrets/postgres_admin_password
    secrets: [postgres_admin_password]
    volumes: [pgdata:/var/lib/postgresql]
    networks: [backend]
    shm_size: 64mb
    command: [postgres, -c, max_connections=30, -c, shared_buffers=64MB]
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d liftcontrol"]
      interval: 30s
      timeout: 5s
      retries: 5
secrets:
  postgres_admin_password:
    file: ./secrets/postgres_admin_password
volumes:
  pgdata:
networks:
  backend:
    internal: true
COMPOSE
chmod 0600 "$ROOT/compose.yaml"
install -m 0700 "$ROOT_DIR/backup-db.sh" "$ROOT/scripts/backup-db.sh"
install -m 0700 "$ROOT_DIR/healthcheck.sh" "$ROOT/scripts/healthcheck.sh"
install -m 0700 "$ROOT_DIR/audit.sh" "$ROOT/scripts/audit.sh"
docker compose -f "$ROOT/compose.yaml" config -q
docker compose -f "$ROOT/compose.yaml" up -d db
for (( attempt=1; attempt<=80; attempt++ )); do
  if docker compose -f "$ROOT/compose.yaml" exec -T db pg_isready -U postgres -d liftcontrol >/dev/null 2>&1; then break; fi
  sleep 2
done
docker compose -f "$ROOT/compose.yaml" exec -T db pg_isready -U postgres -d liftcontrol >/dev/null
# Wait for PostgreSQL Docker health status before running monitored checks.
for (( attempt=1; attempt<=75; attempt++ )); do
  db_cid=$(docker compose -f "$ROOT/compose.yaml" ps -q db)
  status=$(docker inspect -f "{{.State.Health.Status}}" "$db_cid")
  if [[ "$status" == healthy ]]; then break; fi
  sleep 2
done
[[ "$status" == healthy ]] || { echo "Database health check failed"; exit 1; }

# No passwords on argv, no secrets written to installer logs. Fresh database only.
APP_PASSWORD=$(cat "$ROOT/secrets/postgres_app_password")
MIGRATOR_PASSWORD=$(cat "$ROOT/secrets/postgres_migrator_password")
docker compose -f "$ROOT/compose.yaml" exec -T db psql -X -v ON_ERROR_STOP=1 -U postgres -d liftcontrol >/dev/null <<SQL
CREATE ROLE liftapp LOGIN PASSWORD '$APP_PASSWORD';
CREATE ROLE liftmigrator LOGIN PASSWORD '$MIGRATOR_PASSWORD';
REVOKE ALL ON DATABASE liftcontrol FROM PUBLIC;
GRANT CONNECT ON DATABASE liftcontrol TO liftapp, liftmigrator;
CREATE SCHEMA IF NOT EXISTS app AUTHORIZATION liftmigrator;
GRANT USAGE ON SCHEMA app TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE liftmigrator IN SCHEMA app GRANT SELECT, INSERT, UPDATE, DELETE ON TABLES TO liftapp;
ALTER DEFAULT PRIVILEGES FOR ROLE liftmigrator IN SCHEMA app GRANT USAGE, SELECT ON SEQUENCES TO liftapp;
ALTER ROLE liftapp IN DATABASE liftcontrol SET search_path TO app, public;
ALTER ROLE liftmigrator IN DATABASE liftcontrol SET search_path TO app, public;
SQL
unset APP_PASSWORD MIGRATOR_PASSWORD

cat > /etc/systemd/system/liftcontrol-backup.service <<'BACKUP_SERVICE'
[Unit]
Description=LiftControl PostgreSQL database and global roles backup
Requires=docker.service
After=docker.service
[Service]
Type=oneshot
User=root
UMask=0077
ExecStart=/opt/liftcontrol/scripts/backup-db.sh
TimeoutStartSec=15min
BACKUP_SERVICE
cat > /etc/systemd/system/liftcontrol-backup.timer <<'BACKUP_TIMER'
[Unit]
Description=Daily LiftControl backup
[Timer]
OnCalendar=*-*-* 03:00:00 Asia/Yakutsk
Persistent=true
AccuracySec=1min
Unit=liftcontrol-backup.service
[Install]
WantedBy=timers.target
BACKUP_TIMER
cat > /etc/systemd/system/liftcontrol-healthcheck.service <<'HEALTH_SERVICE'
[Unit]
Description=LiftControl local infrastructure healthcheck
Requires=docker.service
After=docker.service
[Service]
Type=oneshot
User=root
ExecStart=/opt/liftcontrol/scripts/healthcheck.sh
HEALTH_SERVICE
cat > /etc/systemd/system/liftcontrol-healthcheck.timer <<'HEALTH_TIMER'
[Unit]
Description=Hourly local LiftControl healthcheck
[Timer]
OnCalendar=hourly
Persistent=true
Unit=liftcontrol-healthcheck.service
[Install]
WantedBy=timers.target
HEALTH_TIMER
systemctl daemon-reload
systemctl start liftcontrol-backup.service
systemctl enable --now liftcontrol-backup.timer liftcontrol-healthcheck.timer
systemctl start liftcontrol-healthcheck.service

echo 'INSTALLATION COMPLETED. Review backup and health status, then TEST SSH key login in a separate session.'
"$ROOT/scripts/audit.sh"