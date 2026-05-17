# ATEE P0

ATEE (Agent Trust Evaluation Engine) is a small, runnable P0 implementation based on the two v3.3 design documents in `C:\Users\Pro16\Downloads`.

中文适配已内置：管理台、运行状态展示、申诉提示、新手引导和 Prompt Packet 常见中文敏感字段脱敏均支持 `zh-CN`。

This version focuses on the production safety boundaries from the workflow:

- Core logic lives in `services/core-service`.
- Thin adapters only extract request context and call the Core Service.
- Every request goes through Trusted Real IP Resolver and Fast-Path Rule Gate.
- Async events still pass Fast-Path before review.
- Prompt packets are minimized and redacted; raw request bodies are not stored.
- Tool Gateway enforces action, confidence, runtime mode, and real IP constraints.
- Security Ledger Lite aggregates low-risk/high-frequency events.
- Appeal paths are whitelisted but rate-limited.
- Admin UI renders untrusted text with `textContent`.

## Run

```powershell
cd C:\Users\Pro16\Documents\Codex\2026-05-12\skills\atee
python services\core-service\run_server.py
```

On Windows, you can also double-click or run:

```powershell
.\run_atee_windows.cmd
```

The Windows launcher runs `services\core-service\check_config.py` before starting the service. It verifies remote model config and confirms encrypted key files are readable in the current Windows user context.

Then open:

```text
http://127.0.0.1:8787/
```

To keep the Core Service running in the current Windows user context:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\start-atee-core-background.ps1
```

Stop it with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\stop-atee-core-background.ps1
```

To run the local business demo site in a second terminal:

```powershell
python apps\demo-site\server.py
```

Then open:

```text
http://127.0.0.1:8790/
```

To run the Core Service with Docker:

```powershell
docker compose up --build
```

Docker deployment notes are in [docs/deployment.md](docs/deployment.md). The image excludes local config, secrets, SQLite data, logs, reports, and `node_modules`.

For Ubuntu/Linux systemd deployment:

```bash
bash scripts/linux/install-atee-systemd.sh --user
```

Linux provider secrets should use `llm_api_key_env` with an environment file or secret manager, not Windows DPAPI files.

To install the Core Service as a dependency-free Windows scheduled task:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-task.ps1
```

Uninstall it with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\uninstall-atee-task.ps1
```

For native Windows SCM integration with a vetted WinSW binary:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-winsw.ps1 -WinswExePath C:\Tools\WinSW-x64.exe
```

For local backup and log maintenance:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\backup-atee-state.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\rotate-atee-logs.ps1
```

To rehearse backup and restore end to end in temporary directories:

```powershell
python scripts\backup-restore-drill.py --report reports\backup-restore-drill.md
```

中文快速开始见 [docs/user-guide/zh-cn-quickstart.md](docs/user-guide/zh-cn-quickstart.md).

## Test

```powershell
cd C:\Users\Pro16\Documents\Codex\2026-05-12\skills\atee
python -m unittest discover -s tests
```

For the local release gate before packaging or handoff:

```powershell
python scripts\local-release-gate.py --report reports\local-release-gate.md
```

The gate runs configuration preflight, Python compile checks, unit tests, the default fake Agent AI full-flow smoke, and a workspace sensitive scan without printing raw command output.

HTTP E2E and basic load smoke coverage are included in `tests\test_http_e2e.py`; they start a temporary local Core Service on a random localhost port and do not use the real DeepSeek key.

Mixed load and restart recovery coverage is included in `tests\test_recovery_load.py`; it exercises skip, async, sync, and Fast-Path traffic, then verifies SQLite recovery for ledger records, appeal review state, revoked actions, and expired actions.

Provider fault injection coverage is included in `tests\test_provider_faults.py`; it runs a local fake OpenAI-compatible provider to verify success redaction, HTTP failure fallback, and circuit breaker behavior without using the real DeepSeek key.

For a larger local mixed-load check:

```powershell
python scripts\local-stress-check.py --requests 500 --workers 8
```

For a time-boxed local endurance rehearsal with a sanitized Markdown report:

```powershell
python scripts\local-stress-check.py --duration-seconds 3600 --target-rps 8 --workers 8 --report reports\local-stress.md
```

For a provider/proxy fault drill using the configured remote model settings without changing `config/config.json`:

```powershell
python scripts\provider-fault-drill.py
```

The default drill forces an in-memory bad proxy, verifies fallback and circuit opening, and skips live provider traffic. Add `--include-live` only when you intentionally want to call the configured provider once. Add `--report reports\provider-drill.md` to write a sanitized Markdown report.

For a local provider budget drill that verifies budget exhaustion stops further provider calls:

```powershell
python scripts\provider-budget-drill.py --attempts 6 --budget-cents 2 --report reports\provider-budget-drill.md
```

For a small-batch provider rehearsal, defaulting to a local fake provider:

```powershell
python scripts\provider-live-batch-drill.py --attempts 4 --budget-cents 2 --report reports\provider-live-batch-drill.md
```

Add `--include-live` only when you intentionally want to call the configured live provider. Live mode is capped at 3 attempts.

Browser E2E uses local `playwright-core` with the system Chrome/Edge executable:

```powershell
npm install
npm run e2e:browser
```

The browser script starts a temporary mock Core Service on a random localhost port, clicks through the admin console, reviews an appeal, revokes an action, and then shuts everything down.

## Main API

- `POST /v1/check`
- `POST /v1/event`
- `POST /v1/appeal`
- `GET /v1/runtime/status`
- `GET /v1/admin/config`
- `POST /v1/admin/config`
- `GET /v1/admin/llm/test`
- `POST /v1/admin/llm/test`
- `GET /v1/admin/ledger/recent`
- `GET /v1/admin/appeals`
- `POST /v1/admin/appeals/review`
- `GET /v1/admin/actions`
- `POST /v1/admin/actions/revoke`
- `POST /v1/admin/actions/cleanup-expired`
- `POST /v1/admin/mode`
- `POST /v1/admin/pause-agent`
- `POST /v1/admin/break-glass/status`

## Demo Site

`apps/demo-site` is a minimal business site that uses the Python Thin Adapter against Core Service. It covers:

- Login: `POST /api/login` -> Core `/v1/check`
- Comment: `POST /api/comment` -> Core `/v1/event`
- Upload: `POST /api/upload` -> Core `/v1/event`
- Appeal: `POST /api/appeal` -> Core `/v1/appeal`

The demo UI uses external CSS/JS assets and renders returned text with `textContent`.

## Local Config

When the Core Service starts through `run_server.py`, it creates and loads:

```text
config/config.json
```

Runtime mode, Agent pause state, trusted proxy CIDRs, timeout budgets, auto IP ban switch, ledger SQLite path, and break-glass switch are persisted there. Secret bypass keys should live in a separate local file referenced by `bypass_key_file`; `bypass_key` itself is not returned by config APIs.

`config/config.example.json` contains the safe default configuration used for the stage-one package.

Relative paths in local config, such as `config/secrets/...` and `data/...`, resolve from the project root, not from the current shell directory.

## SQLite Ledger Lite

By default, medium/high-risk ledger summaries, pending appeals, and executed action records are stored in:

```text
data/atee_ledger.sqlite3
```

Low-risk skip events are aggregated in memory for the current minute and are not written to SQLite on every request. Accepted appeals and actually executed actions are loaded again when Core Service restarts. Admin APIs can review appeals, revoke ATEE action records, and mark expired actions. Recent persisted ledger summaries can be checked with `/v1/admin/ledger/recent?limit=10` or the admin console button.

## Model Gateway

The default model gateway is a local mock:

```text
llm_mode=mock
llm_provider=mock
llm_model=atee-local-mock-v1
```

It does not need an API key and does not store raw prompts. Use `/v1/admin/llm/test` or the admin console button to verify it.

For a real OpenAI-compatible provider, set:

```text
llm_mode=openai_compatible
llm_provider=<provider-name>
llm_api_base=https://...
llm_model=<model-name>
llm_api_key_file=config/secrets/<provider>_api_key.dpapi.json
llm_proxy_url=<proxy-url>
llm_daily_budget_cents=0
```

`config/secrets/` is ignored by git. On Windows, encrypt a key file with:

```powershell
python services\core-service\encrypt_secret.py --input config\secrets\provider_api_key.txt --output config\secrets\provider_api_key.dpapi.json
```

Public providers must use HTTPS; HTTP bases are rejected before the Authorization header is sent. Proxy configuration is stored as `llm_proxy_url`; public status only shows whether a proxy is configured.

DPAPI CurrentUser secrets must be created under the same Windows user context that runs ATEE. If you deploy as a Windows service account, migrate the encrypted key while logged in as that account or provide the key through `llm_api_key_env` from a secret manager.

`llm_daily_budget_cents=0` leaves remote calls uncapped. A positive value enables a simple daily budget guard that estimates one cent per remote attempt; when exhausted, the gateway returns `llm_budget_exhausted` and uses the local fallback decision. Three consecutive provider timeouts or request failures open a 60-second circuit breaker and return `llm_circuit_open` without calling the provider.
