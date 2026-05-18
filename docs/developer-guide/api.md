# ATEE P0 Developer API

## POST /v1/check

Request:

```json
{
  "method": "POST",
  "path": "/login",
  "headers": {},
  "query": {},
  "body": {},
  "remote_addr": "203.0.113.10",
  "user_id": "optional",
  "session_id": "optional",
  "event_type": "login"
}
```

Response includes:

- `real_ip`: trusted IP parsing result.
- `fast_path`: skip/block/pass/rate limit decision.
- `route`: skip, fast_path_block, sync_agent, or async_agent.
- `decision`: selected action and confidence scores.
- `tool_gateway`: execution boundary result.
- `ledger_record`: stored summary or aggregate.

## POST /v1/event

Same shape as `/v1/check`, defaulting to a write/event path.

## POST /v1/appeal

Request:

```json
{
  "punishment_id": "pun-123",
  "banned_ip_hash": "optional",
  "reason": "plain text"
}
```

Appeal POST is limited to one submission per `punishment_id` and `banned_ip_hash` per hour. Rate-limited appeals return `429` and do not create a record. Accepted pending appeals are persisted to SQLite and loaded again on Core Service restart.

## Runtime

- `GET /v1/runtime/status`
- `GET /v1/admin/config`
- `POST /v1/admin/config`
- `GET /v1/admin/llm/test`
- `POST /v1/admin/llm/test`
- `GET /v1/admin/ledger/recent?limit=10`
- `GET /v1/admin/appeals?status=pending`
- `POST /v1/admin/appeals/review`
- `GET /v1/admin/actions?status=active`
- `POST /v1/admin/actions/revoke`
- `POST /v1/admin/actions/cleanup-expired`
- `POST /v1/admin/mode` with `{"mode": "observe" | "auto" | "degraded" | "read_only"}`
- `POST /v1/admin/pause-agent` with `{"paused": true}`
- `POST /v1/admin/break-glass/status`

## Demo Site API

The optional demo site runs separately on `http://127.0.0.1:8790/` and uses the Python Thin Adapter to call Core Service:

- `POST /api/login` maps to Core `/v1/check` with `event_type=login`.
- `POST /api/comment` maps to Core `/v1/event` with `event_type=comment_create`.
- `POST /api/upload` maps to Core `/v1/event` with `event_type=file_upload`.
- `POST /api/appeal` maps to Core `/v1/appeal`.

The demo response includes a compact `security` summary plus the raw `core_response` for local verification.

## HTTP E2E And Load Smoke

`tests/test_http_e2e.py` starts a temporary Core Service on a random localhost port with the mock LLM gateway. It verifies:

- Admin console HTML and static JS are served over HTTP.
- `/v1/check`, `/v1/appeal`, admin appeal review, admin action list, and action revoke work together.
- A small parallel `/v1/check` load smoke completes without request failures.

The smoke tests do not use the local DeepSeek API key and do not require a fixed port.

## Mixed Load And Recovery Test

`tests/test_recovery_load.py` runs a longer in-process mixed workload against a temporary Core Service and SQLite database. It sends skip, async, sync, and Fast-Path requests, then verifies that ledger summaries, reviewed appeals, pending appeals, revoked actions, and expired actions are still visible after creating a fresh Core Service instance from the same config path.

This test is still intentionally bounded for local CI speed. It does not replace multi-hour production load testing or provider failure-injection drills.

## Provider Fault Injection

`tests/test_provider_faults.py` starts a local fake OpenAI-compatible provider and points Core Service at it. It verifies:

- Successful provider calls receive only redacted request summaries, not raw sensitive body values.
- HTTP 500 provider failures fall back to the local `rule_hint` path.
- After three consecutive provider failures, the gateway opens the circuit and stops sending additional provider requests during the cooldown.
- Public Core, status, and ledger responses do not expose the configured API key or raw sensitive body values.

The fake provider runs on localhost and does not use the real DeepSeek key.

## Docker Deployment

The repository includes `Dockerfile`, `.dockerignore`, and `docker-compose.yml` for a minimal Core Service deployment:

```powershell
docker compose up --build
```

The image sets `ATEE_HOST=0.0.0.0`, exposes port `8787`, runs `services/core-service/check_config.py` before opening the service port, and uses `/health` as the container health check. The compose file uses named volumes for `/app/config` and `/app/data` so generated config and SQLite state survive container restarts.

`.dockerignore` excludes local config, secret files, SQLite data, logs, reports, and `node_modules`. Use `llm_api_key_env` or a container secret manager for real provider keys; Windows DPAPI files are not portable into Linux containers.

See `docs/deployment.md` for the operational notes.

## Windows Scheduled Task

The repository includes a dependency-free Windows scheduled task wrapper:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-task.ps1
```

The installed task runs `scripts\windows\start-atee-core.ps1`, which sets `ATEE_HOST`/`ATEE_PORT`, writes logs under `logs\`, runs `check_config.py`, and starts the Core Service only after preflight passes. Uninstall with:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\uninstall-atee-task.ps1
```

Use `-Trigger AtStartup` from an elevated PowerShell prompt for startup-triggered operation. This is the no-extra-dependency P0 path rather than a native Service Control Manager integration.

For native Windows SCM integration, provide a vetted WinSW executable:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\install-atee-winsw.ps1 -WinswExePath C:\Tools\WinSW-x64.exe
```

The script copies the provided wrapper into ignored `runtime\winsw\`, generates the WinSW XML, and points the service at `start-atee-core.ps1`. It does not download WinSW or include a third-party binary in the repository.

## Backup And Log Maintenance

Windows maintenance scripts:

```powershell
powershell -ExecutionPolicy Bypass -File scripts\windows\backup-atee-state.ps1
powershell -ExecutionPolicy Bypass -File scripts\windows\restore-atee-state.ps1 -BackupPath backups\atee-state-YYYYMMDD-HHMMSS.zip -Force
powershell -ExecutionPolicy Bypass -File scripts\windows\rotate-atee-logs.ps1
```

Backups include runtime config and SQLite state, optionally logs with `-IncludeLogs`, and intentionally exclude `config/secrets/`, key files, `node_modules/`, and generated service runtime files. Restore refuses to run without `-Force` and rejects archives that contain `config/secrets`.

To rehearse backup and restore end to end without touching the real project state:

```powershell
python scripts\backup-restore-drill.py --report reports\backup-restore-drill.md
```

The drill creates temporary source and target installation directories, generates mock SQLite security state, invokes the Windows backup and restore scripts, then verifies restored config, SQLite ledger state, pending appeals, actions, and secret exclusion. The report omits API keys, key file paths, proxy URLs, API base URLs, raw prompts, raw request bodies, and temp paths.

## Local Stress Check

For a larger manual mixed-load and restart-recovery check:

```powershell
python scripts\local-stress-check.py --requests 500 --workers 8
```

For a time-boxed endurance rehearsal:

```powershell
python scripts\local-stress-check.py --duration-seconds 3600 --target-rps 8 --workers 8 --report reports\local-stress.md
```

The script uses a temporary mock Core Service and SQLite database. It prints a JSON summary with route counts, elapsed time, target RPS, actual throughput, persisted ledger status, pending appeal recovery, revoked action recovery, and expired action recovery. `--report <path>` writes a sanitized Markdown report. Increase `--requests` for count-based runs, or use `--duration-seconds` for time-boxed local rehearsals; `--target-rps` keeps long runs from becoming uncontrolled CPU/SQLite burn-in tests, and `--max-requests` can cap duration-mode runs.

## Provider/Proxy Fault Drill

To exercise the configured remote provider settings without changing `config/config.json`:

```powershell
python scripts\provider-fault-drill.py
```

The default drill loads the configured provider, API base, key source, and proxy flags, then makes an in-memory copy with a bad localhost proxy. It expects three controlled provider failures followed by `llm_circuit_open` on the fourth request. The JSON output reports only booleans and health summaries, not the API key, key file path, proxy URL, or raw prompt.

To write a sanitized Markdown report:

```powershell
python scripts\provider-fault-drill.py --report reports\provider-drill.md
```

The report includes provider/model labels, configured/not-configured booleans, reason codes, and circuit status. It intentionally omits API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies.

Use `--include-live` only when you intentionally want to send one health-check request to the configured live provider after the bad-proxy drill.

## Provider Budget Drill

To verify that the gateway stops sending provider requests after the daily budget is exhausted:

```powershell
python scripts\provider-budget-drill.py --attempts 6 --budget-cents 2 --report reports\provider-budget-drill.md
```

The drill starts a temporary local fake provider, configures a small in-memory remote budget, and confirms that only the budgeted attempts reach the provider. Later attempts should return `llm_budget_exhausted` without opening the failure circuit. The JSON output and Markdown report omit API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies.

## Provider Live Batch Drill

To rehearse small-batch provider behavior without calling the configured live provider:

```powershell
python scripts\provider-live-batch-drill.py --attempts 4 --budget-cents 2 --report reports\provider-live-batch-drill.md
```

The default mode starts a temporary local fake provider. It records reason counts, latency summary, budget status, circuit status, and provider call counts. Add `--include-live` only for an intentional live provider rehearsal; live mode is capped at 3 attempts and still uses the in-memory budget guard. The JSON output and Markdown report omit API keys, key file paths, proxy URLs, API base URLs, raw prompts, and raw request bodies.

## Agent AI Full-Flow Smoke

To rehearse the Agent AI path without calling the configured live provider:

```powershell
python scripts\agent-ai-full-flow-smoke.py --report reports\agent-ai-full-flow-smoke.md
```

The default run starts a temporary local fake OpenAI-compatible provider and a temporary SQLite ledger. It verifies runtime status, low-risk skip, one sync Agent AI review, Fast-Path XSS block, appeal submit, admin review, and ledger audit.

Use `--include-live` only for an intentional one-call live full-flow rehearsal:

```powershell
python scripts\agent-ai-full-flow-smoke.py --include-live --budget-cents 1 --report reports\agent-ai-full-flow-smoke-live.md
```

Output and reports omit API keys, key file paths, proxy URLs, API base URLs, authorization headers, raw prompts, raw request bodies, and temporary ledger paths. If the Agent is paused or the runtime is in observe mode, the tool gateway may report `would_have_action`; that is expected and means no punishment was executed.

## Local Release Gate

Before packaging or handing a build to another environment, run the local release gate:

```powershell
python scripts\local-release-gate.py --report reports\local-release-gate.md
```

The gate runs configuration preflight, Python compile checks, unit tests, the default fake Agent AI full-flow smoke, and a workspace sensitive scan. It intentionally omits raw command output from JSON and Markdown reports. Use `--quick` for a fast local check that runs the same categories with a focused test subset.

## Browser E2E

The project includes a browser automation script backed by `playwright-core` and the system Chrome/Edge executable:

```powershell
npm install
npm run e2e:browser
```

The script starts a temporary mock Core Service on a random localhost port, opens the admin console in headless Chrome, verifies key UI text, submits and reviews a demo appeal, switches to auto mode, executes a Fast-Path action, lists the action, revokes it, checks browser console errors, and shuts down the temporary service. It does not use the real DeepSeek key.

## Admin API Authentication

By default, local development keeps admin authentication disabled. For production, set `admin_auth_enabled=true` and provide an Admin Token through `admin_token_env` or `admin_token_file`.

When enabled, all `/v1/admin/*` endpoints require one of these headers:

```text
Authorization: Bearer <admin-token>
X-ATEE-Admin-Token: <admin-token>
```

The token value is never returned by status, config, or error responses. Public runtime status reports only whether admin auth is enabled and whether a token is configured. The React console stores the entered Admin Token in browser `sessionStorage` and sends it only to `/v1/admin/*` requests.

Management clients may also send `X-ATEE-Admin-Id` on `/v1/admin/*` requests. ATEE sanitizes this optional operator id and stores it in admin audit ledger summaries together with short hashes for the operator id and source address. Admin Tokens, raw source addresses, secret file paths, and provider keys are not written to the audit summary.

## GET /v1/admin/config

Returns the current non-secret configuration and the local config path.

Relative file paths written through config resolve from the project root. This includes write-only fields such as `llm_api_key_file`, plus `bypass_key_file` and `ledger_sqlite_path`, so the service does not depend on the shell directory used to start it.

## POST /v1/admin/config

Allowed fields. Sensitive write-only fields such as `llm_api_base`, `llm_api_key_value`, `llm_api_key_file`, `llm_proxy_url`, and `admin_token_file` are accepted on update, then returned only as `*_configured` booleans. `llm_api_key_value` is copied into the service process environment variable named by `llm_api_key_env`; it is not persisted to `config.json`.

```json
{
  "locale": "zh-CN",
  "runtime_mode": "observe",
  "agent_paused": false,
  "trusted_proxy_cidrs": ["10.0.0.0/8"],
  "appeal_paths": ["/atee-appeal", "/security/appeal"],
  "auto_ip_ban_enabled": false,
  "local_precheck_ms": 100,
  "remote_soft_timeout_ms": 3000,
  "remote_hard_timeout_ms": 5000,
  "ledger_max_bytes": 268435456,
  "ledger_sqlite_path": "data/atee_ledger.sqlite3",
  "admin_auth_enabled": false,
  "admin_token_file": "config/secrets/admin-token.dpapi.json",
  "admin_token_env": "ATEE_ADMIN_TOKEN",
  "llm_mode": "mock",
  "llm_provider": "mock",
  "llm_model": "atee-local-mock-v1",
  "llm_api_base": "https://provider.example/v1",
  "llm_api_key_value": "write-only-runtime-secret",
  "llm_api_key_file": "config/secrets/provider.dpapi.json",
  "llm_api_key_env": "ATEE_LLM_API_KEY",
  "llm_proxy_url": "http://127.0.0.1:7890",
  "llm_daily_budget_cents": 0,
  "bypass_enabled": false,
  "bypass_key_file": null
}
```

Updating `trusted_proxy_cidrs` immediately rebuilds the Trusted Real IP Resolver. Updating `ledger_max_bytes` or `ledger_sqlite_path` rebuilds the local Ledger Lite handle.

## GET /v1/admin/ledger/recent

Returns recent persisted ledger summaries:

```json
{
  "ok": true,
  "records": [
    {
      "id": 1,
      "event_type": "agent_decision",
      "severity": "medium",
      "endpoint_type": "login",
      "action": "would_have_action",
      "summary": "..."
    }
  ],
  "status": {
    "sqlite_enabled": true,
    "sqlite_path": "data/atee_ledger.sqlite3",
    "persisted_records": 1,
    "raw_prompt_storage": false,
    "raw_request_body_storage": false
  }
}
```

`limit` is clamped to `1..100`. Low-risk skip aggregates are intentionally not written to SQLite for every request.

## SQLite Ledger Lite

Stage one persists medium/high-risk ledger summaries, accepted pending appeals, and actually executed action records to SQLite while keeping raw Prompt Packet text and raw request bodies out of storage. The default path is configured by `ledger_sqlite_path`; relative paths resolve from the project root when the service is started with `config/config.json`.

The same SQLite file currently contains:

- `ledger_records`: medium/high-risk security summaries.
- `appeals`: accepted pending appeals keyed by `punishment_id`.
- `action_records`: actions that passed Tool Gateway and were actually executed.

Appeal rate-limit hit windows remain in memory for stage one. Observe-mode `would_have_action` results are not action records because nothing was executed.

## Admin Appeal Review

List appeals:

```text
GET /v1/admin/appeals?status=pending
```

`status` can be `pending`, `approved`, `rejected`, or `all`.

Review an appeal:

```json
{
  "punishment_id": "pun-123",
  "resolution": "approved",
  "admin_note": "plain text note"
}
```

`resolution` must be `approved` or `rejected`. Admin notes and appeal reasons are stored and rendered as untrusted text.

## Admin Action Management

List action records:

```text
GET /v1/admin/actions?status=active
```

`status` can be `active`, `revoked`, `expired`, or `all`.

Revoke an active ATEE action record:

```json
{
  "action_id": 1,
  "reason": "plain text reason"
}
```

Cleanup expired actions:

```text
POST /v1/admin/actions/cleanup-expired
```

These endpoints update ATEE's own action ledger only. Stage one still does not modify the business database, delete content, or hide content.

## Remote LLM Gateway Mock

Stage one uses a local mock gateway by default:

```json
{
  "llm_mode": "mock",
  "llm_provider": "mock",
  "llm_model": "atee-local-mock-v1"
}
```

The mock does not need network access or an API key. It returns structured `agent_decision` JSON to exercise the same Core Service path that a real OpenAI-compatible gateway will use later. It does not store raw prompts.

Use `/v1/admin/llm/test` to verify the gateway is reachable.

## OpenAI-Compatible Gateway

Set `llm_mode` to `openai_compatible` to call a provider at `{llm_api_base}/chat/completions`. API keys can be provided by `llm_api_key_env`, one-time write-only `llm_api_key_value`, or `llm_api_key_file`; API Base, API key file paths, proxy URLs, and key values are never returned by config, status, or test APIs.

`llm_api_key_value` is for controlled console entry and connection testing. It sets only the current service process environment variable named by `llm_api_key_env`; production deployments should inject the key through systemd environment files or a secret manager before service start.

For strict secret transport, public `http://` API bases are rejected with `insecure_api_base_requires_https`. Localhost HTTP remains allowed for test doubles.

On Windows, `llm_api_key_file` can point to a DPAPI CurrentUser encrypted file created by:

```powershell
python services\core-service\encrypt_secret.py --input config\secrets\provider_api_key.txt --output config\secrets\provider_api_key.dpapi.json
```

DPAPI CurrentUser files are bound to the Windows user context that created them. For a production Windows service, create or migrate the encrypted file under the same service account that will run ATEE, or use `llm_api_key_env` with your secret manager.

Before starting on Windows, run:

```powershell
python services\core-service\check_config.py
```

The Windows launcher runs the same preflight automatically and exits before opening the service port if the remote model secret cannot be read.

Use `llm_proxy_url` for production proxy routing, for example `<proxy-url>`. Public config/status payloads return only `llm_api_key_file_configured` and `llm_proxy_configured`, not the secret path or proxy URL.

Set `llm_daily_budget_cents` to a positive value to cap remote model attempts for the current day. Stage one uses a conservative one-cent estimate per remote attempt; `0` means no budget cap. When the cap is reached, the gateway returns `llm_budget_exhausted` and falls back to the local `rule_hint` decision without calling the provider.

After three consecutive provider request failures or hard timeouts, the gateway opens a short circuit for 60 seconds. During that window it returns `llm_circuit_open` and skips provider calls. Runtime status exposes budget and circuit health, but never returns the API key, key file path, proxy URL, or raw prompt.
