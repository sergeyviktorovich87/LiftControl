#!/usr/bin/env bash
set -Eeuo pipefail
exec python3 /opt/liftcontrol/public/access.py status "$@"
