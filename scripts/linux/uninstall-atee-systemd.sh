#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="atee-core"
MODE="user"
REMOVE_ENV=0

usage() {
  cat <<'USAGE'
Usage: uninstall-atee-systemd.sh [options]

Options:
  --user                 Remove current user's systemd service (default).
  --system               Remove system service. Requires root.
  --service-name NAME    systemd service name without .service.
  --remove-env           Also remove the service environment file.
  -h, --help             Show this help.
USAGE
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user) MODE="user" ;;
    --system) MODE="system" ;;
    --service-name) SERVICE_NAME="${2:?--service-name requires a value}"; shift ;;
    --remove-env) REMOVE_ENV=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

if [ "$MODE" = "system" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    echo "--system mode must be run as root." >&2
    exit 1
  fi
  UNIT_DIR="/etc/systemd/system"
  ENV_DIR="/etc/atee"
  SYSTEMCTL=(systemctl)
else
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  ENV_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/atee"
  SYSTEMCTL=(systemctl --user)
fi

UNIT_FILE="$UNIT_DIR/${SERVICE_NAME}.service"
ENV_FILE="$ENV_DIR/${SERVICE_NAME}.env"

"${SYSTEMCTL[@]}" disable --now "${SERVICE_NAME}.service" 2>/dev/null || true
rm -f "$UNIT_FILE"
if [ "$REMOVE_ENV" -eq 1 ]; then
  rm -f "$ENV_FILE"
fi
"${SYSTEMCTL[@]}" daemon-reload

echo "Uninstalled ${SERVICE_NAME}.service from $MODE mode."
