# AGENTS.md

This file applies to the whole ATEE repository unless a more specific
`AGENTS.md` is added in a subdirectory.

## Project Shape

ATEE is a Core Service centered security system for connected websites.
Keep the security logic in `services/core-service/atee_core`; adapters and
site-side scripts should stay thin.

Important areas:

- `services/core-service/atee_core`: Core APIs, action ledger, appeals,
  feature access, site inventory, decision and tool gateways.
- `apps/admin-console-src`: React + Ant Design admin console source.
- `apps/admin-console`: built admin console assets served by Core.
- `apps/page-guard`: embeddable Page Guard and shared action classifier.
- `adapters`: thin Python and Node adapter examples.
- `scripts`: smoke tests, drills, scanners, maintenance helpers.
- `tests`: Python `unittest` suite.
- `docs`: user, developer, deployment, and alignment docs.

## Architecture Rules

- Do not duplicate the security engine in adapters, browser scripts, or demo
  sites. They should call Core.
- Do not write to a connected site's business database from ATEE. ATEE records
  reversible action ledger entries and exposes checks.
- Keep `/v1/feature-access` read-only: it checks active feature locks and does
  not run fresh AI scoring.
- User appeals may auto-revoke only active, reversible, user-level
  `feature_ban` actions with `target_scope.type == "user_feature"`.
- Site-wide `site_feature` fuses are admin controlled and must not be lifted
  by ordinary user appeals.
- Page Guard and `scripts/page-action-scan.mjs` must share the classifier in
  `apps/page-guard/page-action-classifier.mjs`.
- Do not store raw Prompt Packets, raw request bodies, API keys, admin tokens,
  proxy URLs, or unredacted provider endpoints in reports or ledger data.

## Naming Rules

- JavaScript and frontend source filenames use kebab-case:
  `admin-site-management.jsx`, `page-action-classifier.mjs`.
- Python modules use snake_case:
  `site_inventory.py`, `async_review_worker.py`.
- Keep conventional root and platform filenames as-is:
  `README.md`, `Dockerfile`, `Caddyfile.example`, `package-lock.json`.
- Windows entry scripts use kebab-case where project-owned:
  `run-atee-windows.cmd`.

## Editing Guidance

- Prefer small, surgical changes that match nearby code style.
- Use existing helpers before adding new abstractions.
- Use structured parsers/APIs where practical instead of ad hoc text parsing.
- Avoid unrelated refactors, generated churn, and metadata-only changes.
- Treat user changes as intentional. Do not revert work you did not make.
- Use `apply_patch` for hand edits.

## Security And Secrets

- Never commit secrets from `config/secrets`, runtime SQLite data, local logs,
  provider keys, admin tokens, or proxy URLs.
- Do not echo user-provided keys in commits, docs, reports, or terminal
  summaries.
- Keep report output sanitized. Prefer booleans such as
  `api_key_configured=true` over values or file paths.
- `config/config.json`, `data/`, `runtime/`, `reports/`, `node_modules/`, and
  `__pycache__/` are runtime or generated areas; avoid adding new generated
  files from them unless the task explicitly asks for it.

## Verification Commands

Run the narrowest useful checks first, then broaden for cross-cutting changes.

Core and HTTP behavior:

```powershell
python -m unittest tests.test_core tests.test_http_e2e
```

Admin console source and build:

```powershell
python -m unittest tests.test_admin_console
npm.cmd run build:admin
```

Browser E2E:

```powershell
npm.cmd run e2e:browser
```

Full Python suite:

```powershell
python -m unittest discover -s tests
```

Page scan syntax:

```powershell
node --check scripts\page-action-scan.mjs
```

## Git Guidance

- Before staging, inspect `git status --short --branch`.
- Do not include unrelated untracked reports or local runtime files.
- If renaming files, update imports, tests, docs, and build output as needed.
- After staging, confirm `git diff --cached --stat` and
  `git diff --cached --name-status`.

## Current Acceptance Baseline

The current mainline expectation is:

- `python -m unittest discover -s tests` passes.
- `npm.cmd run build:admin` passes.
- `npm.cmd run e2e:browser` passes.
- Page Guard recognizes login, register, submit, search, save, delete, menu,
  pagination, dialog trigger, and upload controls without confusing
  `dropdown` menus for delete actions.
