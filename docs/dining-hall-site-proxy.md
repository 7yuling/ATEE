# Dining Hall Site Proxy Integration

This page captures the checked integration profile for
`chicken-123-oss/dining-hall`.

## Topology

- ATEE Core stays on `http://127.0.0.1:8787`.
- Dining Hall stays on `http://127.0.0.1:5001`.
- Users and testers open Dining Hall only through:

```text
http://127.0.0.1:8787/proxy/sites/<site_id>/
```

Do not mount Dining Hall at the same origin root as ATEE Core. Dining Hall owns
`/admin`; ATEE owns `/admin`, `/v1/*`, `/page-guard/*`, and `/proxy/sites/*`.
The proxy keeps the target admin page under `/proxy/sites/<site_id>/admin`.

## Register And Smoke Check

Start both services, then run:

```powershell
python scripts\dining-hall-integration-smoke.py `
  --core-url http://127.0.0.1:8787 `
  --site-url http://127.0.0.1:5001/
```

If ATEE admin auth is enabled, set `ATEE_ADMIN_TOKEN` in the shell first or pass
`--admin-token-env` with the environment variable name. The script does not echo
the token.

The script:

- registers or updates the managed site named `dining-hall-demo`;
- enables Site Proxy and Page Guard;
- keeps target admin auto-actions disabled;
- verifies runtime guard injection through the proxy;
- creates temporary site feature bans for protected writes;
- confirms protected writes return `403` with `atee_blocked=true`;
- revokes those temporary feature bans unless `--keep-feature-bans` is passed.

## Protected Routes

ATEE defaults already cover the main Dining Hall writes:

```text
POST   /api/login                  -> login
POST   /api/register               -> register
POST   /api/topics                 -> posts
POST   /api/topics/<id>/posts      -> comments
DELETE /api/posts/<id>             -> delete_posts
DELETE /api/topics/<id>            -> delete_topics
POST/PUT/PATCH/DELETE /api/admin/* -> admin_actions
```

Dining Hall also needs these custom rules:

```text
POST ^/api/topics/\d+/pin$ -> admin_actions
PUT  /api/me/password      -> account_settings
```

`/api/appeal` remains a Dining Hall route. Do not map it to ATEE `/v1/appeal`
for this first integration; ATEE appeals use `/v1/appeal` or ATEE-owned aliases
such as `/atee-appeal`, `/security/appeal`, and `/.well-known/atee-appeal`.

## Verification Notes

In browser testing, confirm Network requests stay under
`/proxy/sites/<site_id>/api/...`. Dining Hall has JavaScript assignments such as
`location.href = "/login"`; ATEE handles these with referer-based proxy context,
so login redirects, topic redirects, admin redirects, and appeal redirects should
be part of the smoke pass.

For blocking tests, feature-ban these scopes one at a time and verify the target
SQLite data is not changed by the blocked request:

```text
posts
comments
delete_topics
admin_actions
account_settings
```
