# ATEE P0 Security Boundaries

ATEE P0 intentionally keeps the implementation narrow.

## Allowed Automatic Actions

- `allow`
- `challenge`
- `cooldown`
- `feature_ban`
- `account_ban_short`
- `ip_ban_short`
- `adjust_trust_score`
- `rule_hint`

## Forbidden Actions

- Permanent ban
- Delete user
- Delete content
- Modify business database
- Modify global policy or scoring rule
- Execute shell commands
- Ban all users
- Shut down the site

## Real IP

Forwarded IP headers are trusted only when `remote_addr` is inside `trusted_proxy_cidrs`.

When `trusted_proxy_cidrs` is not configured, automatic IP ban is disabled even if an IP appears in headers.

## Prompt Packet Privacy

ATEE deletes standard sensitive fields such as Cookie, Authorization, token, API key, and password fields. It hashes user ID, session ID, and IP. It does not store raw Prompt Packets or raw request bodies.

This does not guarantee that every privacy item embedded in arbitrary free text can be detected.

## Admin Rendering

Agent output, appeal reasons, reason codes, and user-provided text are `untrusted_text`. The included admin console renders them with `textContent` and sends a restrictive Content Security Policy.

