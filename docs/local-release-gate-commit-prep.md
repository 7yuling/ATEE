# ATEE Local Release Gate Report

- Generated at UTC: 2026-06-05T15:15:43+00:00
- Overall OK: True
- Mode: quick

## Steps

- config_preflight: OK
- python_compile: OK
- unit_tests: OK tests=32
- agent_ai_full_flow_smoke: OK
- async_ai_review_worker_smoke: OK
- sensitive_scan: OK findings=0

## Security Notes

- Raw command output is intentionally omitted from this report.
- The sensitive scan skips local runtime config, config/secrets, node_modules, Git internals, and Python cache folders.
- API keys, provider hosts, proxy endpoints, authorization headers, raw prompts, and raw request bodies are not printed.
