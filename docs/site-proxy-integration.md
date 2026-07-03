# ATEE Site Proxy Integration

ATEE can connect a site without modifying the target site's code by using the
standard site proxy:

```text
/proxy/sites/<site_id>/
```

The proxy loads the registered site's `base_url`, rewrites same-origin site
requests through ATEE, injects Page Guard into HTML pages, and performs a
server-side `/v1/feature-access` check before protected write actions reach the
target site.

## Register A Site

```json
{
  "name": "example-site",
  "base_url": "http://127.0.0.1:5001/",
  "environment": "staging",
  "allowed_domains": ["127.0.0.1"],
  "auth_mode": "none",
  "protected_features": ["login", "posts", "comments"],
  "page_guard_enabled": true
}
```

The returned site payload includes:

```json
{
  "site_proxy": {
    "standard": "atee_site_proxy_v1",
    "enabled": true,
    "proxy_path": "/proxy/sites/1/",
    "feature_access_path": "/proxy/sites/1/v1/feature-access"
  }
}
```

Users should browse through `proxy_path`; direct visits to the original
`base_url` do not receive ATEE runtime interception.

Registering a site only stores the target metadata and proxy rules inside
ATEE. It does not change public DNS, Nginx, Caddy, CDN, or the target site's
own routing. To send real browser traffic through ATEE, put Core Service behind
your public reverse proxy and expose the returned `proxy_path`.

## Public Traffic Through Nginx

Keep Core Service private, for example on `127.0.0.1:8787`, then let Nginx
forward the public ATEE domain to Core:

```nginx
server {
    listen 443 ssl http2;
    server_name atee.example.com;

    # TLS certificate configuration omitted.

    location / {
        proxy_pass http://127.0.0.1:8787;
        proxy_http_version 1.1;
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
    }
}
```

After registration, users and testers should open:

```text
https://atee.example.com/proxy/sites/<site_id>/
```

Target-site absolute paths such as `/api/me`, `/api/admin/status`, and
`/admin` are expected to stay under that prefix, for example:

```text
/proxy/sites/<site_id>/api/me
/proxy/sites/<site_id>/api/admin/status
/proxy/sites/<site_id>/admin
```

A direct request to `https://atee.example.com/api/me` is not a target-site
request and may return ATEE's `404 not_found`.

ATEE accounts and the target site's accounts are separate. ATEE admin login
only authorizes ATEE management APIs. Target-site login should still happen
through the proxied target page and should create target-site cookies scoped to
`/proxy/sites/<site_id>/`. The optional `site_proxy.admin_session_ref` is a
local session file used only by configured admin action templates; it is not a
password-sharing mechanism and should not make arbitrary target credentials log
in to ATEE.

## Default Protected Routes

The standard proxy includes reusable defaults:

```text
POST /api/login                  -> login
POST /api/register               -> register
POST /api/topics                 -> posts
POST /api/topics/<id>/posts      -> comments
DELETE /api/posts/<id>           -> delete_posts
DELETE /api/topics/<id>          -> delete_topics
POST/PUT/PATCH/DELETE /api/admin -> admin_actions
```

ATEE checks these routes on both sides:

- Browser side: injected runtime guard disables matching controls and intercepts
  `fetch()` writes.
- Server side: the proxy checks feature access before forwarding matching writes
  to the target site.

The checked Dining Hall demo profile, including its extra pin-topic and password
rules, is documented in [dining-hall-site-proxy.md](dining-hall-site-proxy.md).

## Custom Rules

Sites can add custom rules during registration or update:

```json
{
  "site_proxy": {
    "enabled": true,
    "feature_map": {
      "#publish": "publishing"
    },
    "path_rules": [
      {
        "methods": ["POST"],
        "path": "/api/publish",
        "feature_scope": "publishing"
      },
      {
        "methods": ["POST", "PUT"],
        "path_prefix": "/api/moderation/",
        "feature_scope": "moderation"
      },
      {
        "methods": ["DELETE"],
        "path_regex": "^/api/items/\\d+$",
        "feature_scope": "delete_items"
      }
    ]
  }
}
```

Rule matching supports exact `path`, `path_prefix`, and `path_regex`. Keep
feature names stable; actions and feature bans should use the same
`feature_scope` string.

## Admin Session Actions

For concept demos where ATEE is allowed to act as the connected site's external
admin brain, store the target site's admin session in a local session file and
reference it from `site_proxy`. Do not commit that file.

```json
{
  "site_proxy": {
    "admin_session_enabled": true,
    "admin_session_ref": "config/sessions/site-admin.json",
    "auto_apply_admin_actions": true,
    "admin_action_templates": {
      "comments": {
        "method": "POST",
        "path": "/admin/feature-ban",
        "body_template": {
          "user_hash": "{user_hash}",
          "feature": "{feature_scope}",
          "reason": "{reason}",
          "action_id": "{action_id}"
        },
        "success_status": [200, 201, 202, 204]
      }
    }
  }
}
```

When a feature ban is created for a mapped feature, ATEE first records its own
reversible action, then calls the target site's admin template with the stored
admin session. If that target call fails, the ATEE proxy-side feature ban stays
active and the result reports the target admin action as failed.

Proxy pages also report Page Guard action observations to
`/proxy/sites/<site_id>/v1/page-actions`, which reuses the normal site scan
inventory and auto-generates feature mappings where the control can be matched.

## Validation

1. Register the site with `POST /v1/admin/sites`.
2. Visit `/proxy/sites/<site_id>/`.
3. Create a temporary site feature ban with `POST /v1/admin/site-feature-bans`.
4. Verify the matching control is disabled and the matching write returns
   `403` with `atee_blocked=true`.
