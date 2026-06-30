import json
import re
import urllib.error
import urllib.request
from http.cookies import SimpleCookie
from pathlib import Path
from typing import Any
from urllib.parse import unquote, urlsplit, urlunsplit


PROXY_PREFIX_RE = re.compile(r"^/proxy/sites/(\d+)(?:/(.*))?$")
HTML_URL_ATTR_RE = re.compile(
    r"(?P<before>\s(?:href|src|action|poster|data-src)=['\"])(?P<url>/[^'\"]*)(?P<after>['\"])",
    flags=re.IGNORECASE,
)
HOP_BY_HOP_HEADERS = {
    "connection",
    "keep-alive",
    "proxy-authenticate",
    "proxy-authorization",
    "te",
    "trailer",
    "transfer-encoding",
    "upgrade",
    "content-length",
    "content-encoding",
    "accept-encoding",
    "expect",
    "host",
    "authorization",
}
PROXY_MAX_BODY_BYTES = 10 * 1024 * 1024


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # type: ignore[override]
        return None


NO_REDIRECT_OPENER = urllib.request.build_opener(_NoRedirect)


def is_site_proxy_path(path: str) -> bool:
    return urlsplit(path).path.startswith("/proxy/sites/")


def handle_site_proxy_request(handler: Any, core: Any, page_guard_dir: Path) -> bool:
    parsed = urlsplit(handler.path)
    match = PROXY_PREFIX_RE.match(parsed.path)
    if not match:
        return False

    site_id = int(match.group(1))
    proxy_path = "/" + unquote(match.group(2) or "")
    prefix = f"/proxy/sites/{site_id}"
    site = core.site_inventory.get_site(site_id)
    if not site:
        _send_json(handler, {"ok": False, "status": 404, "reason": "site_not_found"}, status=404)
        return True
    if str(site.get("status") or "active").lower() != "active":
        _send_json(handler, {"ok": False, "status": 409, "reason": "site_not_active"}, status=409)
        return True
    if not _proxy_config(site, site_id).get("enabled", True):
        _send_json(handler, {"ok": False, "status": 409, "reason": "site_proxy_disabled"}, status=409)
        return True

    if handler.command == "GET" and proxy_path == "/atee-runtime-guard.js":
        _send_bytes(
            handler,
            runtime_guard_js(site, site_id, prefix).encode("utf-8"),
            "application/javascript; charset=utf-8",
        )
        return True
    if handler.command == "GET" and proxy_path in {"/page-guard/atee-page-guard.mjs", "/page-guard/page-action-classifier.mjs"}:
        asset = page_guard_dir / Path(proxy_path).name
        _send_bytes(handler, asset.read_bytes(), "application/javascript; charset=utf-8")
        return True
    if proxy_path == "/v1/page-actions":
        payload = _read_json_body(handler)
        if payload is None:
            return True
        actions = payload.get("actions") if isinstance(payload.get("actions"), list) else []
        result = core.create_site_scan(
            {
                "site_id": site_id,
                "start_url": payload.get("page_url") or site.get("base_url"),
                "actions": actions,
                "allow_high_risk_actions": False,
                "max_pages": 1,
                "max_actions": max(1, len(actions)),
                "timeout_ms": 1000,
                "execute_scan": False,
            }
        )
        _send_json(handler, result, status=int(result.get("status", 200)))
        return True
    if proxy_path == "/v1/feature-access":
        payload = _read_json_body(handler)
        if payload is None:
            return True
        payload["site_id"] = site_id
        payload.setdefault("user_id", _proxy_user_id(handler, site))
        result = core.feature_access(payload)
        _send_json(handler, result, status=int(result.get("status", 200)))
        return True

    body = _read_body(handler)
    if body is None:
        return True
    feature_scope = feature_scope_for_request(site, proxy_path, handler.command)
    if feature_scope:
        access = core.feature_access(
            {
                "site_id": site_id,
                "user_id": _proxy_user_id(handler, site),
                "feature_scope": feature_scope,
            }
        )
        if access.get("allowed") is False:
            _send_json(
                handler,
                {
                    "ok": False,
                    "status": 403,
                    "reason": access.get("reason") or "feature_access_blocked",
                    "atee_blocked": True,
                    "feature_scope": feature_scope,
                    "access": access,
                },
                status=403,
            )
            return True

    _proxy_upstream(handler, site, site_id, prefix, proxy_path, parsed.query, body)
    return True


def feature_scope_for_request(site: dict[str, Any], path: str, method: str) -> str:
    method = method.upper()
    if method not in {"POST", "PUT", "PATCH", "DELETE"}:
        return ""
    for rule in _proxy_config(site).get("path_rules") or []:
        if _rule_matches(rule, path, method):
            return str(rule.get("feature_scope") or "")
    return ""


def runtime_guard_js(site: dict[str, Any], site_id: int, prefix: str) -> str:
    proxy_config = _proxy_config(site, site_id)
    config = {
        "siteId": site_id,
        "prefix": prefix,
        "featureAccessUrl": f"{prefix}/v1/feature-access",
        "protectedFeatures": proxy_config.get("protected_features") or [],
        "protectedActionTypes": proxy_config.get("protected_action_types") or [],
        "featureMap": proxy_config.get("feature_map") or {},
        "pathRules": proxy_config.get("path_rules") or [],
        "actionReportUrl": f"{prefix}/v1/page-actions",
        "reportActions": bool(proxy_config.get("observe_actions", True)),
    }
    return f"""
const ATEE_PROXY_CONFIG = {json.dumps(config, ensure_ascii=False, sort_keys=True)};

(() => {{
  const config = ATEE_PROXY_CONFIG;
  const rawFetch = window.fetch.bind(window);

  window.ATEE_PAGE_GUARD_CONFIG = {{
    siteId: config.siteId,
    userId: proxyUserId(),
    featureAccessUrl: config.featureAccessUrl,
    protectedFeatures: config.protectedFeatures,
    protectedActionTypes: config.protectedActionTypes,
    featureMap: config.featureMap,
    actionReportUrl: config.actionReportUrl,
    reportActions: config.reportActions,
    autoStart: false
  }};

  const style = document.createElement("style");
  style.textContent = ".atee-page-guard-blocked{{opacity:.48!important;cursor:not-allowed!important;filter:grayscale(.35)!important;outline:2px solid rgba(233,69,96,.65)!important;outline-offset:2px!important}}";
  document.head.appendChild(style);

  function proxiedPath(path) {{
    if (!path || !path.startsWith("/") || path === config.prefix || path.startsWith(config.prefix + "/")) return path;
    return config.prefix + path;
  }}

  function proxiedUrl(rawUrl) {{
    const url = new URL(rawUrl, location.href);
    if (url.origin === location.origin) {{
      url.pathname = proxiedPath(url.pathname);
    }}
    return url.toString();
  }}

  function targetPath(url) {{
    if (!url.pathname.startsWith(config.prefix + "/")) return url.pathname;
    return url.pathname.slice(config.prefix.length) || "/";
  }}

  function mutationFeature(path, method) {{
    method = method.toUpperCase();
    if (!["POST", "PUT", "PATCH", "DELETE"].includes(method)) return "";
    for (const rule of config.pathRules || []) {{
      const methods = Array.isArray(rule.methods) ? rule.methods.map((item) => String(item).toUpperCase()) : [];
      if (!methods.includes(method)) continue;
      if (rule.path && path === rule.path) return rule.feature_scope || "";
      if (rule.path_prefix && path.startsWith(rule.path_prefix)) return rule.feature_scope || "";
      if (rule.path_regex) {{
        try {{
          if (new RegExp(rule.path_regex).test(path)) return rule.feature_scope || "";
        }} catch {{}}
      }}
    }}
    return "";
  }}

  async function featureAccess(featureScope) {{
    const response = await rawFetch(config.featureAccessUrl, {{
      method: "POST",
      headers: {{"Content-Type": "application/json"}},
      credentials: "include",
      body: JSON.stringify({{
        site_id: config.siteId,
        user_id: proxyUserId(),
        feature_scope: featureScope
      }})
    }});
    return response.json();
  }}

  window.fetch = async (input, init = {{}}) => {{
    const request = input instanceof Request ? input : null;
    const method = String(init.method || request?.method || "GET").toUpperCase();
    const rawUrl = typeof input === "string" ? input : request?.url || String(input);
    const nextUrl = proxiedUrl(rawUrl);
    const url = new URL(nextUrl, location.href);
    const featureScope = mutationFeature(targetPath(url), method);
    if (featureScope) {{
      const access = await featureAccess(featureScope).catch((error) => ({{allowed: true, reason: String(error)}}));
      if (access.allowed === false) {{
        window.dispatchEvent(new CustomEvent("atee:blocked", {{detail: {{featureScope, access, method, path: targetPath(url)}}}}));
        return new Response(JSON.stringify({{
          ok: false,
          msg: "Blocked by ATEE",
          reason: access.reason,
          atee_blocked: true,
          feature_scope: featureScope
        }}), {{
          status: 403,
          headers: {{"Content-Type": "application/json; charset=utf-8"}}
        }});
      }}
    }}
    if (request) {{
      return rawFetch(new Request(nextUrl, request), init);
    }}
    return rawFetch(nextUrl, init);
  }};

  const rawPushState = history.pushState.bind(history);
  const rawReplaceState = history.replaceState.bind(history);
  history.pushState = function (state, title, url) {{
    if (arguments.length < 3 || url == null) return rawPushState(state, title);
    return rawPushState(state, title, proxiedUrl(url));
  }};
  history.replaceState = function (state, title, url) {{
    if (arguments.length < 3 || url == null) return rawReplaceState(state, title);
    return rawReplaceState(state, title, proxiedUrl(url));
  }};

  document.addEventListener("click", (event) => {{
    const control = event.target?.closest?.("a[href], [onclick]");
    if (!control) return;
    const rawHref = control.getAttribute("href") || directLocationHref(control.getAttribute("onclick") || "");
    if (!rawHref || !rawHref.startsWith("/") || rawHref.startsWith(config.prefix + "/")) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    location.href = proxiedPath(rawHref);
  }}, true);

  document.addEventListener("submit", (event) => {{
    const form = event.target;
    if (!form?.getAttribute) return;
    const action = form.getAttribute("action");
    if (action && action.startsWith("/") && !action.startsWith(config.prefix + "/")) {{
      form.setAttribute("action", proxiedPath(action));
    }}
  }}, true);

  function directLocationHref(onclick) {{
    const match = onclick.match(/location\\.href\\s*=\\s*['"]([^'"]+)['"]/);
    return match ? match[1] : "";
  }}

  function proxyUserId() {{
    try {{
      const key = "atee_site_proxy_user_id";
      let value = localStorage.getItem(key);
      if (!value) {{
        value = "site-proxy-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
        localStorage.setItem(key, value);
      }}
      return value;
    }} catch {{
      return "site-proxy-user";
    }}
  }}

  async function startGuard() {{
    try {{
      const module = await import(config.prefix + "/page-guard/atee-page-guard.mjs");
      window.ATEE_PAGE_GUARD_CONFIG.userId = proxyUserId();
      window.ATEE_SITE_PROXY_GUARD_LAST = await module.startPageGuard(window.ATEE_PAGE_GUARD_CONFIG);
      window.ATEE_SITE_PROXY_GUARD_READY = true;
    }} catch (error) {{
      window.ATEE_SITE_PROXY_GUARD_READY = false;
      window.ATEE_SITE_PROXY_GUARD_ERROR = error?.message || String(error);
    }}
  }}

  const scheduleGuard = (() => {{
    let timer = 0;
    return () => {{
      clearTimeout(timer);
      timer = setTimeout(startGuard, 120);
    }};
  }})();

  if (document.readyState === "loading") {{
    document.addEventListener("DOMContentLoaded", scheduleGuard, {{once: true}});
  }} else {{
    scheduleGuard();
  }}
  new MutationObserver(scheduleGuard).observe(document.documentElement, {{
    childList: true,
    subtree: true,
    attributes: true,
    attributeFilter: ["class", "disabled", "style"]
  }});
}})();
""".strip()


def _proxy_upstream(
    handler: Any,
    site: dict[str, Any],
    site_id: int,
    prefix: str,
    proxy_path: str,
    query: str,
    body: bytes,
) -> None:
    target_url = _target_url(site, proxy_path, query)
    if not _target_allowed(site, target_url):
        _send_json(handler, {"ok": False, "status": 403, "reason": "target_domain_not_allowed"}, status=403)
        return
    request = urllib.request.Request(
        target_url,
        data=body if body else None,
        headers=_upstream_headers(handler, target_url),
        method=handler.command,
    )
    try:
        response = NO_REDIRECT_OPENER.open(request, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    except urllib.error.URLError as error:
        _send_json(
            handler,
            {"ok": False, "status": 502, "reason": "target_unreachable", "detail": str(error.reason)},
            status=502,
        )
        return
    with response:
        payload = response.read()
        status = int(response.status)
        headers = _response_headers(response.headers, site, site_id, prefix)
        content_type = response.headers.get("Content-Type", "")
        if "text/html" in content_type.lower():
            text = payload.decode(_charset(content_type), errors="replace")
            payload = _prepare_html_response(text, prefix).encode("utf-8")
            headers = _set_response_header(headers, "Content-Type", "text/html; charset=utf-8")
        headers = _set_response_header(headers, "Content-Length", str(len(payload)))
        handler.send_response(status)
        for key, value in headers:
            handler.send_header(key, value)
        handler.end_headers()
        if handler.command != "HEAD":
            handler.wfile.write(payload)


def _target_url(site: dict[str, Any], proxy_path: str, query: str) -> str:
    base = urlsplit(site["base_url"])
    base_path = (base.path or "/").rstrip("/")
    target_path = "/" + proxy_path.lstrip("/")
    if base_path and base_path != "/":
        target_path = base_path + target_path
    return urlunsplit((base.scheme, base.netloc, target_path, query, ""))


def _target_allowed(site: dict[str, Any], target_url: str) -> bool:
    parsed = urlsplit(target_url)
    base = urlsplit(site["base_url"])
    if parsed.scheme not in {"http", "https"}:
        return False
    allowed = {str(item).lower() for item in site.get("allowed_domains") or []}
    if base.hostname:
        allowed.add(base.hostname.lower())
    return bool(parsed.hostname and parsed.hostname.lower() in allowed)


def _upstream_headers(handler: Any, target_url: str) -> dict[str, str]:
    headers: dict[str, str] = {}
    for key, value in handler.headers.items():
        if key.lower() not in HOP_BY_HOP_HEADERS:
            headers[key] = value
    target = urlsplit(target_url)
    headers["Host"] = target.netloc
    headers["X-Forwarded-Host"] = handler.headers.get("Host", "")
    headers["X-Forwarded-Proto"] = "http"
    return headers


def _response_headers(headers: Any, site: dict[str, Any], site_id: int, prefix: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    for key, value in headers.items():
        lower = key.lower()
        if lower in HOP_BY_HOP_HEADERS or lower in {"content-security-policy", "x-frame-options"}:
            continue
        if lower == "location":
            value = _rewrite_location(value, site, site_id, prefix)
        if lower == "set-cookie":
            value = _rewrite_set_cookie(value, site, prefix)
        result.append((key, value))
    result.append(("Cache-Control", "no-store"))
    return result


def _set_response_header(headers: list[tuple[str, str]], name: str, value: str) -> list[tuple[str, str]]:
    result: list[tuple[str, str]] = []
    replaced = False
    lower_name = name.lower()
    for key, current in headers:
        if key.lower() == lower_name:
            if not replaced:
                result.append((name, value))
                replaced = True
            continue
        result.append((key, current))
    if not replaced:
        result.append((name, value))
    return result


def _rewrite_location(value: str, site: dict[str, Any], site_id: int, prefix: str) -> str:
    if not value:
        return value
    parsed = urlsplit(value)
    if not parsed.netloc and value.startswith("/"):
        return prefix + value
    base = urlsplit(site["base_url"])
    if parsed.hostname and base.hostname and parsed.hostname.lower() == base.hostname.lower():
        path = parsed.path or "/"
        return urlunsplit(("", "", f"/proxy/sites/{site_id}{path}", parsed.query, parsed.fragment))
    return value


def _rewrite_set_cookie(value: str, site: dict[str, Any], prefix: str) -> str:
    cookie = SimpleCookie()
    try:
        cookie.load(value)
    except Exception:
        return _rewrite_set_cookie_text(value, site, prefix)
    if not cookie:
        return _rewrite_set_cookie_text(value, site, prefix)
    for morsel in cookie.values():
        morsel["domain"] = ""
        morsel["path"] = _proxy_cookie_path(site, prefix, morsel["path"] or "/")
    return cookie.output(header="").strip()


def _rewrite_set_cookie_text(value: str, site: dict[str, Any], prefix: str) -> str:
    parts = [part.strip() for part in str(value or "").split(";")]
    if not parts or not parts[0]:
        return value
    rewritten = [parts[0]]
    path_seen = False
    for part in parts[1:]:
        lower = part.lower()
        if lower.startswith("domain="):
            continue
        if lower.startswith("path="):
            _, _, raw_path = part.partition("=")
            rewritten.append(f"Path={_proxy_cookie_path(site, prefix, raw_path or '/')}")
            path_seen = True
            continue
        rewritten.append(part)
    if not path_seen:
        rewritten.append(f"Path={_proxy_cookie_path(site, prefix, '/')}")
    return "; ".join(rewritten)


def _proxy_cookie_path(site: dict[str, Any], prefix: str, cookie_path: str) -> str:
    base_path = (urlsplit(site.get("base_url", "")).path or "/").rstrip("/")
    raw_path = str(cookie_path or "/").strip() or "/"
    if not raw_path.startswith("/"):
        raw_path = "/"
    if base_path and base_path != "/" and raw_path.startswith(base_path):
        raw_path = raw_path.removeprefix(base_path) or "/"
    if raw_path == "/":
        return prefix.rstrip("/") + "/"
    return prefix.rstrip("/") + "/" + raw_path.lstrip("/")


def _proxy_config(site: dict[str, Any], site_id: int | None = None) -> dict[str, Any]:
    config = site.get("site_proxy") if isinstance(site.get("site_proxy"), dict) else {}
    if site_id and not config.get("proxy_path"):
        config = {**config, "proxy_path": f"/proxy/sites/{site_id}/"}
    return config


def _rule_matches(rule: dict[str, Any], path: str, method: str) -> bool:
    methods = [str(item).upper() for item in (rule.get("methods") or [])]
    if method.upper() not in methods:
        return False
    if rule.get("path") and path == str(rule["path"]):
        return True
    if rule.get("path_prefix") and path.startswith(str(rule["path_prefix"])):
        return True
    if rule.get("path_regex"):
        try:
            return bool(re.fullmatch(str(rule["path_regex"]), path) or re.match(str(rule["path_regex"]), path))
        except re.error:
            return False
    return False


def _prepare_html_response(text: str, prefix: str) -> str:
    return _inject_runtime_guard(_rewrite_html_url_attributes(text, prefix), prefix)


def _rewrite_html_url_attributes(text: str, prefix: str) -> str:
    def replace(match: re.Match[str]) -> str:
        url = match.group("url")
        if url.startswith("//") or url == prefix or url.startswith(prefix + "/"):
            return match.group(0)
        return f"{match.group('before')}{prefix}{url}{match.group('after')}"

    return HTML_URL_ATTR_RE.sub(replace, text)


def _inject_runtime_guard(text: str, prefix: str) -> str:
    snippet = f'\n<script src="{prefix}/atee-runtime-guard.js"></script>\n'
    head = re.search(r"<head\b[^>]*>", text, flags=re.IGNORECASE)
    if head:
        return text[: head.end()] + snippet + text[head.end() :]
    lower = text.lower()
    body = lower.find("<body")
    if body >= 0:
        body_end = lower.find(">", body)
        if body_end >= 0:
            return text[: body_end + 1] + snippet + text[body_end + 1 :]
    index = lower.rfind("</body>")
    if index >= 0:
        return text[:index] + snippet + text[index:]
    return text + snippet


def _read_body(handler: Any) -> bytes | None:
    try:
        length = int(handler.headers.get("Content-Length", "0") or "0")
    except ValueError:
        length = 0
    if length > PROXY_MAX_BODY_BYTES:
        _send_json(handler, {"ok": False, "status": 413, "reason": "request_body_too_large"}, status=413)
        return None
    return handler.rfile.read(length) if length > 0 else b""


def _read_json_body(handler: Any) -> dict[str, Any] | None:
    body = _read_body(handler)
    if body is None:
        return None
    if not body:
        return {}
    try:
        data = json.loads(body.decode("utf-8"))
    except json.JSONDecodeError:
        _send_json(handler, {"ok": False, "status": 400, "reason": "invalid_json"}, status=400)
        return None
    return data if isinstance(data, dict) else {}


def _proxy_user_id(handler: Any, site: dict[str, Any] | None = None) -> str:
    headers = []
    if site:
        headers.extend(_proxy_config(site).get("user_id_headers") or [])
    headers.extend(["X-ATEE-User-Id", "X-User-Id"])
    value = ""
    for header in headers:
        value = handler.headers.get(str(header)) or ""
        if value:
            break
    return str(value).strip() or "site-proxy-user"


def _send_json(handler: Any, payload: dict[str, Any], status: int = 200) -> None:
    body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    _send_bytes(handler, body, "application/json; charset=utf-8", status=status)


def _send_bytes(handler: Any, body: bytes, content_type: str, status: int = 200) -> None:
    handler.send_response(status)
    handler.send_header("Content-Type", content_type)
    handler.send_header("Content-Length", str(len(body)))
    handler.send_header("Cache-Control", "no-store")
    handler.end_headers()
    if handler.command != "HEAD":
        handler.wfile.write(body)


def _charset(content_type: str) -> str:
    match = re.search(r"charset=([^;]+)", content_type, flags=re.IGNORECASE)
    return match.group(1).strip() if match else "utf-8"


def _unique(items: list[str]) -> list[str]:
    result: list[str] = []
    for item in items:
        value = str(item).strip()
        if value and value not in result:
            result.append(value)
    return result
