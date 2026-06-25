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

## Validation

1. Register the site with `POST /v1/admin/sites`.
2. Visit `/proxy/sites/<site_id>/`.
3. Create a temporary site feature ban with `POST /v1/admin/site-feature-bans`.
4. Verify the matching control is disabled and the matching write returns
   `403` with `atee_blocked=true`.
