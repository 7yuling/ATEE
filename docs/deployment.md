# ATEE Deployment Notes

## Docker Quick Start

Build and run the Core Service:

```powershell
docker compose up --build
```

Open:

```text
http://127.0.0.1:8787/
```

The compose file uses named volumes:

- `atee-config` mounted at `/app/config`
- `atee-data` mounted at `/app/data`

On first start, ATEE creates `/app/config/config.json` with safe mock-model defaults. Runtime data is stored in `/app/data/atee_ledger.sqlite3`.

## Remote Provider Secrets

The image does not copy `config/config.json`, `config/secrets/`, local SQLite data, logs, reports, or `node_modules`.

For a real OpenAI-compatible provider in Docker, prefer an environment variable or a secret manager:

```powershell
$env:ATEE_LLM_API_KEY="..."
docker compose up --build
```

Then configure the running service through the admin config API or by mounting a production config volume that references `llm_api_key_env`.

Windows DPAPI `*.dpapi.json` files are bound to the Windows user that created them and are not portable into Linux containers. For Docker, use `llm_api_key_env` or a container secret mechanism instead.

To rehearse the Agent AI business path without calling the configured live provider:

```bash
python scripts/agent-ai-full-flow-smoke.py --report reports/agent-ai-full-flow-smoke.md
```

Use `--include-live --budget-cents 1` only when you intentionally want one live provider call through the full path. The script uses a temporary ledger and omits API keys, key file paths, proxy URLs, API base URLs, authorization headers, raw prompts, raw request bodies, and temporary ledger paths from output and reports.

Before packaging a local build, run the release gate:

```bash
python scripts/local-release-gate.py --report reports/local-release-gate.md
```

It runs configuration preflight, Python compile checks, unit tests, the default fake Agent AI full-flow smoke, and a workspace sensitive scan. The report omits raw command output and secret-bearing values.

## Bind Address

`services/core-service/run_server.py` reads:

- `ATEE_HOST`, default `127.0.0.1`
- `ATEE_PORT`, default `8787`

The Docker image sets `ATEE_HOST=0.0.0.0` so the service is reachable through the published port.

## Health Check

The Dockerfile health check calls:

```text
http://127.0.0.1:8787/health
```

The container command runs the configuration preflight before opening the service port:

```text
python services/core-service/check_config.py
```

If remote model config or secret loading is invalid, the service exits before binding the HTTP port.

## Ubuntu/Linux Systemd

Ubuntu and other Linux servers should not use Windows DPAPI `*.dpapi.json` secret files. Use `llm_api_key_env` with an environment variable, a systemd environment file with locked-down permissions, or your production secret manager.

For a current-user systemd service:

```bash
bash scripts/linux/install-atee-systemd.sh --user
systemctl --user status atee-core.service
```

If the server must keep the user service alive after logout, enable lingering outside this project:

```bash
loginctl enable-linger <linux-user>
```

For a system service, run as root and explicitly choose a non-root runtime user:

```bash
sudo bash scripts/linux/install-atee-systemd.sh --system --run-user atee
sudo systemctl status atee-core.service
```

The installer writes a unit file that runs:

```text
scripts/linux/start-atee-core.sh
```

That script sets `ATEE_HOST`, `ATEE_PORT`, `PYTHONUNBUFFERED`, runs `services/core-service/check_config.py`, and only then starts `services/core-service/run_server.py`.

Default Linux service files:

- User unit: `~/.config/systemd/user/atee-core.service`
- User env file: `~/.config/atee/atee-core.env`
- System unit: `/etc/systemd/system/atee-core.service`
- System env file: `/etc/atee/atee-core.env`

Copy the placeholder environment file when you need provider secrets:

```bash
cp scripts/linux/atee-core.env.example ~/.config/atee/atee-core.env
chmod 600 ~/.config/atee/atee-core.env
```

Do not put real API keys or admin tokens in the repository. For production, configure `config/config.json` to reference `llm_api_key_env` and `admin_token_env`, then inject `ATEE_LLM_API_KEY` and `ATEE_ADMIN_TOKEN` through the environment file or a secret manager. Bind to `127.0.0.1` behind Nginx/Caddy unless you have a trusted internal network and firewall policy.

## Admin Token Rotation

Rotate the Admin Token in an environment file without printing the token to the terminal:

```bash
python scripts/rotate-admin-token.py --env-file ~/.config/atee/atee-core.env --json
```

Windows example:

```powershell
python scripts\rotate-admin-token.py --env-file .\runtime\atee-core.env --json
```

The script updates `ATEE_ADMIN_TOKEN`, preserves unrelated environment lines, and prints only a short SHA-256 fingerprint by default. Use `--show-token` only in a private terminal when an operator must copy the new token into the React console. Restart ATEE after rotating the server-side token.

## Reverse Proxy

ATEE should normally bind to `127.0.0.1` and sit behind a production reverse proxy. Example configs are provided at:

```text
deploy/reverse-proxy/nginx/atee.conf.example
deploy/reverse-proxy/caddy/Caddyfile.example
deploy/reverse-proxy/nginx/atee-sso.conf.example
deploy/reverse-proxy/caddy/Caddyfile.sso.example
```

Both examples proxy to `127.0.0.1:8787`, forward `X-Forwarded-*` and `X-Real-IP`, add basic security headers, and avoid wildcard CORS. If you trust the reverse proxy address, add its CIDR to `trusted_proxy_cidrs` so ATEE can use forwarded client IP metadata. Keep `admin_auth_enabled=true` for any shared or remotely reachable deployment.

For production operator attribution, have the reverse proxy or SSO layer set `X-ATEE-Admin-Id` after authentication, or ask operators to enter a stable id in the React console. ATEE records the sanitized id plus short id/source hashes in the audit ledger, but does not store Admin Tokens or raw client IPs in ledger summaries.

For SSO deployments, prefer the `*-sso.example` files. They model an auth_request-compatible gateway such as oauth2-proxy and make the proxy overwrite `X-ATEE-Admin-Id` from the authenticated identity. Do not forward a browser-supplied `X-ATEE-Admin-Id` unchanged in production; otherwise audit attribution can be spoofed even when Admin Token authentication is enabled.

## Production Smoke Check

After the reverse proxy, Admin Token, and optional SSO identity injection are configured, run the production smoke check from a trusted operator machine:

```bash
export ATEE_ADMIN_TOKEN="..."
python scripts/production-smoke-check.py \
  --base-url https://atee.example.com \
  --expect-admin-auth \
  --verify-audit-actor \
  --audit-actor-id browser-spoof-test \
  --expected-audit-actor operator@example.com \
  --report reports/production-smoke.md
```

The script checks `/health`, the admin console HTML, split JS/CSS assets, runtime status, Admin Token enforcement, and optional audit attribution. With `--verify-audit-actor`, it sends one safe admin audit probe through `/v1/admin/break-glass/status` and then checks `/v1/admin/ledger/recent` for the expected actor summary. The JSON output and Markdown report intentionally omit the full target URL, Admin Token, authorization headers, and actor identifiers.

Use `--allow-http` only for local rehearsal against `127.0.0.1`; production targets should stay on HTTPS and expose HSTS/security headers through the reverse proxy.

## Admin Token Rotation Smoke Check

After rotating the Admin Token, use the rotation smoke script to verify that the environment file changed, the service picked up the new token, the old token is rejected, and the normal production smoke checks still pass:

```bash
python scripts/admin-token-rotation-smoke.py \
  --env-file ~/.config/atee/atee-core.env \
  --base-url https://atee.example.com \
  --expect-admin-auth \
  --restart-command "systemctl --user restart atee-core.service" \
  --verify-audit-actor \
  --audit-actor-id browser-spoof-test \
  --expected-audit-actor operator@example.com \
  --report reports/admin-token-rotation-smoke.md
```

For Windows scheduled-task or service deployments, replace `--restart-command` with your vetted stop/start or service restart command. If the restart command is omitted, the script still rotates the environment file and runs the checks; a real service that reads tokens only at startup will usually fail the new-token smoke check until restarted.

The JSON output and Markdown report intentionally omit token values, authorization headers, the full target URL, and actor identifiers. They include only short token fingerprints and boolean check results so operators can keep the report without exposing the rotated secret.

Uninstall:

```bash
bash scripts/linux/uninstall-atee-systemd.sh --user
sudo bash scripts/linux/uninstall-atee-systemd.sh --system
```

## Windows Scheduled Task

For a current-user background run without installing a scheduled task, start and stop ATEE with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start-atee-core-background.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\stop-atee-core-background.ps1
```

The background launcher runs the same configuration preflight, starts the service as the current Windows user, waits for `/health`, writes logs to `logs\`, and stores the process id in `logs\atee-server.pid`. It also normalizes duplicate `Path`/`PATH` environment entries before calling `Start-Process`, because Windows process creation treats environment names case-insensitively.

For a dependency-free Windows background entrypoint, install ATEE as a scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-task.ps1
```

The default trigger is `AtLogOn`, which runs under the current Windows user. This is the safest option when `llm_api_key_file` points to a Windows DPAPI CurrentUser file. To use an `AtStartup` trigger, run PowerShell as Administrator and make sure the configured service account can decrypt or provide the model key:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-task.ps1 -Trigger AtStartup
```

The task runs:

```text
scripts\windows\start-atee-core.ps1
```

That script sets `ATEE_HOST` and `ATEE_PORT`, runs `services\core-service\check_config.py`, and only starts `services\core-service\run_server.py` if the preflight passes.

Logs are written under:

```text
logs\atee-preflight.log
logs\atee-server.out.log
logs\atee-server.err.log
```

Uninstall the scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\uninstall-atee-task.ps1
```

This is not a native Windows Service Control Manager service. It is the no-extra-dependency P0 option. For production SCM integration, use a vetted wrapper such as WinSW or NSSM and keep the same `start-atee-core.ps1` preflight/logging script as the target command.

## Windows SCM Service With WinSW

For native Windows Service Control Manager integration, provide a vetted WinSW executable and let the installer generate the service wrapper files:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-winsw.ps1 -WinswExePath C:\Tools\WinSW-x64.exe
```

The script copies the provided WinSW binary to:

```text
runtime\winsw\ATEECore.exe
```

and writes:

```text
runtime\winsw\ATEECore.xml
```

The generated service still targets `scripts\windows\start-atee-core.ps1`, so the same configuration preflight and log paths are used before the Core Service opens its HTTP port.

Uninstall:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\uninstall-atee-winsw.ps1 -RemoveFiles
```

Operational notes:

- Run install/uninstall from an elevated PowerShell prompt.
- The WinSW binary is not included in this repository and is not downloaded by the script.
- Generated wrapper files live under `runtime\`, which is ignored by git.
- WinSW services normally run under the Windows service account configured in SCM. DPAPI CurrentUser secrets must be created under that same account, or replace DPAPI with `llm_api_key_env`/a secret manager.

## Backup, Restore, And Log Rotation

Create a local state backup:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\backup-atee-state.ps1
```

The backup archive is written under:

```text
backups\
```

It can include:

- `config/config.json`
- `data/atee_ledger.sqlite3`
- SQLite WAL/SHM sidecar files if present
- logs only when `-IncludeLogs` is passed

It intentionally excludes:

- `config/secrets/`
- `*.key`
- `*.secret`
- `node_modules/`
- `runtime/`

Restore a backup after stopping ATEE:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\restore-atee-state.ps1 -BackupPath backups\atee-state-YYYYMMDD-HHMMSS.zip -Force
```

The restore target must be an existing ATEE installation directory. The restore script refuses to run without `-Force` and refuses archives that contain `config/secrets`.

Rehearse backup and restore end to end in temporary source/target directories:

```powershell
python scripts\backup-restore-drill.py --report reports\backup-restore-drill.md
```

The drill generates mock runtime config, SQLite security summaries, a pending appeal, action records, and a log file, then calls the Windows backup and restore scripts. It verifies that config and SQLite state are restored, logs are archived, and `config/secrets` remains excluded. The generated report intentionally omits temp paths and sensitive values.

Rotate large logs manually:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\rotate-atee-logs.ps1 -MaxBytes 10485760 -KeepFiles 5
```

Generated backups are ignored by git through `backups/`. Backups may contain runtime configuration and security summaries, so treat them as operationally sensitive even though raw API keys and secret files are excluded.
