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

Appeal POST is limited to one submission per `punishment_id` and `banned_ip_hash` per hour. Rate-limited appeals return `429` and do not create a record.

## Runtime

- `GET /v1/runtime/status`
- `GET /v1/admin/config`
- `POST /v1/admin/config`
- `POST /v1/admin/mode` with `{"mode": "observe" | "auto" | "degraded" | "read_only"}`
- `POST /v1/admin/pause-agent` with `{"paused": true}`
- `POST /v1/admin/break-glass/status`

## GET /v1/admin/config

Returns the current non-secret configuration and the local config path.

## POST /v1/admin/config

Allowed fields:

```json
{
  "locale": "zh-CN",
  "trusted_proxy_cidrs": ["10.0.0.0/8"],
  "auto_ip_ban_enabled": false,
  "local_precheck_ms": 100,
  "remote_soft_timeout_ms": 3000,
  "remote_hard_timeout_ms": 5000,
  "ledger_max_bytes": 268435456,
  "bypass_enabled": false,
  "bypass_key_file": null
}
```

Updating `trusted_proxy_cidrs` immediately rebuilds the Trusted Real IP Resolver.

