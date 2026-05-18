#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)
SERVICE_NAME="atee-core"
MODE="user"
RUN_USER=""
PYTHON_BIN="${ATEE_PYTHON:-python3}"
BIND_HOST="${ATEE_HOST:-127.0.0.1}"
PORT="${ATEE_PORT:-8787}"
NO_START=0

usage() {
  cat <<'USAGE'
Usage: install-atee-systemd.sh [options]

Options:
  --user                 Install as current user's systemd service (default).
  --system               Install as system service. Requires root and --run-user.
  --run-user USER        Linux user for --system mode.
  --project-root PATH    ATEE project root. Defaults to this repository root.
  --service-name NAME    systemd service name without .service.
  --python PATH          Python executable. Defaults to python3 or ATEE_PYTHON.
  --host HOST            Bind host. Defaults to 127.0.0.1.
  --port PORT            Bind port. Defaults to 8787.
  --no-start             Install but do not enable/start immediately.
  -h, --help             Show this help.
USAGE
}

systemd_unit_value() {
  local value="$1"
  value=${value//%/%%}
  printf '%s' "$value"
}

while [ "$#" -gt 0 ]; do
  case "$1" in
    --user) MODE="user" ;;
    --system) MODE="system" ;;
    --run-user) RUN_USER="${2:?--run-user requires a value}"; shift ;;
    --project-root) PROJECT_ROOT="${2:?--project-root requires a value}"; shift ;;
    --service-name) SERVICE_NAME="${2:?--service-name requires a value}"; shift ;;
    --python) PYTHON_BIN="${2:?--python requires a value}"; shift ;;
    --host) BIND_HOST="${2:?--host requires a value}"; shift ;;
    --port) PORT="${2:?--port requires a value}"; shift ;;
    --no-start) NO_START=1 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "Unknown option: $1" >&2; usage; exit 2 ;;
  esac
  shift
done

PROJECT_ROOT=$(CDPATH= cd -- "$PROJECT_ROOT" && pwd)
START_SCRIPT="$PROJECT_ROOT/scripts/linux/start-atee-core.sh"
CONFIG_FILE="$PROJECT_ROOT/config/config.json"
CONFIG_EXAMPLE="$PROJECT_ROOT/config/config.example.json"
if [ ! -f "$START_SCRIPT" ]; then
  echo "start-atee-core.sh was not found under $PROJECT_ROOT" >&2
  exit 1
fi
if [ ! -f "$CONFIG_FILE" ]; then
  echo "config/config.json was not found under $PROJECT_ROOT." >&2
  echo "Initialize it before installing the systemd service:" >&2
  echo "  cd $PROJECT_ROOT" >&2
  echo "  cp config/config.example.json config/config.json" >&2
  echo "  # Optional: edit config/config.json for your environment." >&2
  if [ ! -f "$CONFIG_EXAMPLE" ]; then
    echo "config/config.example.json is also missing; check that the repository was copied completely." >&2
  fi
  exit 1
fi

if [ "$MODE" = "system" ]; then
  if [ "$(id -u)" -ne 0 ]; then
    echo "--system mode must be run as root." >&2
    exit 1
  fi
  if [ -z "$RUN_USER" ]; then
    echo "--system mode requires --run-user so the service does not run as root." >&2
    exit 1
  fi
  UNIT_DIR="/etc/systemd/system"
  ENV_DIR="/etc/atee"
  SYSTEMCTL=(systemctl)
  WANTED_BY="multi-user.target"
else
  UNIT_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user"
  ENV_DIR="${XDG_CONFIG_HOME:-$HOME/.config}/atee"
  SYSTEMCTL=(systemctl --user)
  WANTED_BY="default.target"
fi

mkdir -p "$UNIT_DIR" "$ENV_DIR" "$PROJECT_ROOT/logs"
ENV_FILE="$ENV_DIR/${SERVICE_NAME}.env"
UNIT_FILE="$UNIT_DIR/${SERVICE_NAME}.service"

if [ ! -f "$ENV_FILE" ]; then
  cat > "$ENV_FILE" <<EOF
# ATEE runtime environment. Keep real secrets out of git.
# For a real OpenAI-compatible provider, configure ATEE to use llm_api_key_env
# and set the secret here or inject it from your secret manager.
# ATEE_LLM_API_KEY=
# HTTPS_PROXY=http://proxy.example:8080
# HTTP_PROXY=http://proxy.example:8080
EOF
  chmod 600 "$ENV_FILE"
fi

{
  echo "[Unit]"
  echo "Description=ATEE Core Service"
  echo "After=network-online.target"
  echo "Wants=network-online.target"
  echo
  echo "[Service]"
  echo "Type=simple"
  if [ "$MODE" = "system" ]; then
    echo "User=$RUN_USER"
  fi
  echo "WorkingDirectory=$(systemd_unit_value "$PROJECT_ROOT")"
  echo "EnvironmentFile=-$(systemd_unit_value "$ENV_FILE")"
  echo "Environment=ATEE_PROJECT_ROOT=$(systemd_unit_value "$PROJECT_ROOT")"
  echo "Environment=ATEE_PYTHON=$(systemd_unit_value "$PYTHON_BIN")"
  echo "Environment=ATEE_HOST=$BIND_HOST"
  echo "Environment=ATEE_PORT=$PORT"
  echo "Environment=ATEE_LOG_DIR=$(systemd_unit_value "$PROJECT_ROOT/logs")"
  echo "ExecStart=$(systemd_unit_value "$START_SCRIPT")"
  echo "Restart=on-failure"
  echo "RestartSec=5"
  echo "NoNewPrivileges=true"
  echo "PrivateTmp=true"
  echo
  echo "[Install]"
  echo "WantedBy=$WANTED_BY"
} > "$UNIT_FILE"

"${SYSTEMCTL[@]}" daemon-reload
if [ "$NO_START" -eq 0 ]; then
  "${SYSTEMCTL[@]}" enable --now "${SERVICE_NAME}.service"
else
  "${SYSTEMCTL[@]}" enable "${SERVICE_NAME}.service"
fi

echo "Installed ${SERVICE_NAME}.service in $MODE mode."
echo "Unit: $UNIT_FILE"
echo "Environment file: $ENV_FILE"
