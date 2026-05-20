#!/usr/bin/env sh
set -eu

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
PROJECT_ROOT=${ATEE_PROJECT_ROOT:-$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)}
PYTHON_BIN=${ATEE_PYTHON:-python3}
ATEE_HOST=${ATEE_HOST:-127.0.0.1}
ATEE_PORT=${ATEE_PORT:-8787}
ATEE_LOG_DIR=${ATEE_LOG_DIR:-"$PROJECT_ROOT/logs"}

mkdir -p "$ATEE_LOG_DIR"
cd "$PROJECT_ROOT"

export ATEE_HOST
export ATEE_PORT
export PYTHONUNBUFFERED=1

"$PYTHON_BIN" - "$ATEE_HOST" "$ATEE_PORT" > "$ATEE_LOG_DIR/atee-port-preflight.log" 2>&1 <<'PY'
import socket
import sys

host = sys.argv[1]
port = int(sys.argv[2])
try:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind((host, port))
except OSError as exc:
    print(f"ATEE port preflight failed: {host}:{port} is not available ({exc}).")
    sys.exit(1)
print(f"ATEE port preflight passed: {host}:{port}.")
PY

"$PYTHON_BIN" services/core-service/check_config.py > "$ATEE_LOG_DIR/atee-preflight.log" 2>&1
exec "$PYTHON_BIN" services/core-service/run_server.py >> "$ATEE_LOG_DIR/atee-server.out.log" 2>> "$ATEE_LOG_DIR/atee-server.err.log"
