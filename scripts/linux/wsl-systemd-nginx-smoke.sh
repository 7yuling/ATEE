#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR=$(CDPATH= cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
PROJECT_ROOT=$(CDPATH= cd -- "$SCRIPT_DIR/../.." && pwd)

SERVICE_NAME=${ATEE_WSL_SMOKE_SERVICE:-atee-core-wsltest}
CORE_PORT=${ATEE_WSL_SMOKE_CORE_PORT:-18887}
PROXY_PORT=${ATEE_WSL_SMOKE_PROXY_PORT:-18888}
PLACEHOLDER_LLM_KEY=${ATEE_WSL_SMOKE_LLM_KEY:-atee-wsl-placeholder-key}
NGINX_CONF=${ATEE_WSL_SMOKE_NGINX_CONF:-/etc/nginx/conf.d/atee-wsltest.conf}

cleanup() {
  systemctl --user stop "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
  systemctl --user disable "${SERVICE_NAME}.service" >/dev/null 2>&1 || true
  rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/systemd/user/${SERVICE_NAME}.service"
  rm -f "${XDG_CONFIG_HOME:-$HOME/.config}/atee/${SERVICE_NAME}.env"
  systemctl --user daemon-reload >/dev/null 2>&1 || true
  if [ -f "$NGINX_CONF" ]; then
    rm -f "$NGINX_CONF"
    nginx -t >/dev/null 2>&1 && systemctl restart nginx >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT

wait_for_http() {
  local url="$1"
  local attempt
  for attempt in $(seq 1 30); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      return 0
    fi
    sleep 1
  done
  curl -fsS "$url" >/dev/null
}

update_env_file() {
  local env_file="$1"
  if grep -q "^ATEE_LLM_API_KEY=" "$env_file"; then
    sed -i "s/^ATEE_LLM_API_KEY=.*/ATEE_LLM_API_KEY=${PLACEHOLDER_LLM_KEY}/" "$env_file"
  else
    printf "\nATEE_LLM_API_KEY=%s\n" "$PLACEHOLDER_LLM_KEY" >> "$env_file"
  fi
  chmod 600 "$env_file"
}

write_nginx_conf() {
  cat > "$NGINX_CONF" <<EOF
server {
    listen 127.0.0.1:${PROXY_PORT};
    server_name localhost;
    client_max_body_size 1m;
    large_client_header_buffers 4 16k;

    location / {
        proxy_pass http://127.0.0.1:${CORE_PORT};
        proxy_http_version 1.1;
        proxy_set_header Host \$host;
        proxy_set_header X-Real-IP \$remote_addr;
        proxy_set_header X-Forwarded-For \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Cookie "";
    }
}
EOF
}

cd "$PROJECT_ROOT"

bash scripts/linux/install-atee-systemd.sh \
  --user \
  --service-name "$SERVICE_NAME" \
  --port "$CORE_PORT" \
  --no-start

ENV_FILE="${XDG_CONFIG_HOME:-$HOME/.config}/atee/${SERVICE_NAME}.env"
update_env_file "$ENV_FILE"

systemctl --user daemon-reload
systemctl --user start "${SERVICE_NAME}.service"
wait_for_http "http://127.0.0.1:${CORE_PORT}/health"

python3 scripts/production-smoke-check.py \
  --base-url "http://127.0.0.1:${CORE_PORT}" \
  --allow-http \
  --report "reports/wsl-systemd-production-smoke.md"

write_nginx_conf
nginx -t
systemctl restart nginx
wait_for_http "http://127.0.0.1:${PROXY_PORT}/health"

python3 scripts/production-smoke-check.py \
  --base-url "http://127.0.0.1:${PROXY_PORT}" \
  --allow-http \
  --report "reports/wsl-nginx-production-smoke.md"

systemctl --user --no-pager --full status "${SERVICE_NAME}.service" | sed -n "1,18p"
printf "\nWSL systemd+nginx smoke passed: core_port=%s proxy_port=%s\n" "$CORE_PORT" "$PROXY_PORT"
