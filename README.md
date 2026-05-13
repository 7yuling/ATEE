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

Then open:

```text
http://127.0.0.1:8787/
```

中文快速开始见 [docs/user-guide/zh-cn-quickstart.md](docs/user-guide/zh-cn-quickstart.md).

## Test

```powershell
cd C:\Users\Pro16\Documents\Codex\2026-05-12\skills\atee
python -m unittest discover -s tests
```

## Main API

- `POST /v1/check`
- `POST /v1/event`
- `POST /v1/appeal`
- `GET /v1/runtime/status`
- `GET /v1/admin/config`
- `POST /v1/admin/config`
- `POST /v1/admin/mode`
- `POST /v1/admin/pause-agent`
- `POST /v1/admin/break-glass/status`

## Local Config

When the Core Service starts through `run_server.py`, it creates and loads:

```text
config/config.json
```

Runtime mode, Agent pause state, trusted proxy CIDRs, timeout budgets, auto IP ban switch, and break-glass switch are persisted there. Secret bypass keys should live in a separate local file referenced by `bypass_key_file`; `bypass_key` itself is not returned by config APIs.

`config/config.example.json` contains the safe default configuration used for the stage-one package.
