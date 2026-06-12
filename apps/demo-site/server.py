import errno
import json
import os
import sys
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit


ROOT = Path(__file__).resolve().parents[2]
ADAPTER_DIR = ROOT / "adapters" / "python-fastapi"
STATIC_DIR = Path(__file__).resolve().parent
if str(ADAPTER_DIR) not in sys.path:
    sys.path.insert(0, str(ADAPTER_DIR))

from atee_adapter import AteeThinAdapter, build_context  # noqa: E402


DINING_HALL_SOURCE = {
    "repo": "chicken-123-oss/dining-hall",
    "url": "https://github.com/chicken-123-oss/dining-hall",
}

SEED_TOPICS = [
    {
        "id": 1,
        "title": "今日食堂甜咸大战",
        "description": "豆腐脑、粽子、汤圆都可以吵，但先让 ATEE 看一眼风险。",
        "author_name": "canteen-admin",
        "author_id": 1,
        "created_at": 1718006400,
        "pinned": 1,
    },
    {
        "id": 2,
        "title": "午餐窗口排队反馈",
        "description": "收集排队、插队、恶意刷屏等社区治理场景。",
        "author_name": "floor-monitor",
        "author_id": 2,
        "created_at": 1718092800,
        "pinned": 0,
    },
    {
        "id": 3,
        "title": "上传菜单截图前先过安全闸",
        "description": "危险扩展名和脚本片段会被 Fast-Path 拦截。",
        "author_name": "kitchen-bot",
        "author_id": 3,
        "created_at": 1718179200,
        "pinned": 0,
    },
]

SEED_POSTS = {
    1: [
        {
            "id": 1,
            "topic_id": 1,
            "author_id": 2,
            "author_name": "noodle-fan",
            "content": "甜豆腐脑可以进甜品区，咸豆腐脑可以进主食区。",
            "created_at": 1718182800,
            "reply_to": None,
        },
        {
            "id": 2,
            "topic_id": 1,
            "author_id": 3,
            "author_name": "rice-fan",
            "content": "先别急着吵，带脚本的评论会被 ATEE 扣下。",
            "created_at": 1718186400,
            "reply_to": 1,
        },
    ],
    2: [
        {
            "id": 3,
            "topic_id": 2,
            "author_id": 4,
            "author_name": "queue-helper",
            "content": "建议把高峰期反馈统一放在这个话题里。",
            "created_at": 1718190000,
            "reply_to": None,
        }
    ],
    3: [],
}


class DemoBusinessApp:
    def __init__(self, adapter: Any):
        self.adapter = adapter
        self.source = dict(DINING_HALL_SOURCE)
        self.topics = [dict(topic) for topic in SEED_TOPICS]
        self.posts = {
            topic_id: [dict(post) for post in posts]
            for topic_id, posts in SEED_POSTS.items()
        }
        self._next_topic_id = max(topic["id"] for topic in self.topics) + 1
        self._next_post_id = max(
            [post["id"] for posts in self.posts.values() for post in posts] or [0]
        ) + 1

    def login(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/login",
            headers or {},
            {
                "username": str(body.get("username") or "")[:80],
                "password": str(body.get("password") or "")[:200],
            },
            remote_addr,
            "login",
        )
        security = self.adapter.check(context)
        return self._business_response("login", security, {"user": context["body"]["username"]})

    def comment(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/comment",
            headers or {},
            {"text": str(body.get("text") or "")[:2000]},
            remote_addr,
            "comment_create",
        )
        security = self.adapter.event(context)
        return self._business_response("comment", security, {"text": context["body"]["text"]})

    def stats(self) -> dict[str, Any]:
        return {
            "ok": True,
            "source": self.source,
            "users": 4,
            "topics": len(self.topics),
            "posts": sum(len(posts) for posts in self.posts.values()),
        }

    def list_topics(self) -> list[dict[str, Any]]:
        return [self._topic_payload(topic) for topic in self.topics]

    def list_posts(self, topic_id: int) -> list[dict[str, Any]]:
        return [dict(post) for post in self.posts.get(topic_id, [])]

    def create_topic(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        title = str(body.get("title") or "").strip()[:120]
        description = str(body.get("description") or "").strip()[:500]
        context = build_context(
            "POST",
            "/api/topics",
            headers or {},
            {"title": title, "description": description},
            remote_addr,
            "post_create",
        )
        security = self.adapter.event(context)
        response = self._business_response("topic", security, {"title": title, "description": description})
        if not response["ok"]:
            return response

        topic = {
            "id": self._next_topic_id,
            "title": title or "未命名食堂话题",
            "description": description,
            "author_id": 4,
            "author_name": "demo-user",
            "created_at": int(time.time()),
            "pinned": 0,
        }
        self._next_topic_id += 1
        self.topics.insert(0, topic)
        self.posts[topic["id"]] = []
        response["topic"] = self._topic_payload(topic)
        return response

    def create_post(self, topic_id: int, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        topic = self._find_topic(topic_id)
        if not topic:
            return {"ok": False, "error": "topic_not_found"}

        content = str(body.get("content") or body.get("text") or "").strip()[:2000]
        reply_to = body.get("reply_to")
        context = build_context(
            "POST",
            f"/api/topics/{topic_id}/posts",
            headers or {},
            {"content": content, "reply_to": reply_to},
            remote_addr,
            "post_create",
        )
        security = self.adapter.event(context)
        response = self._business_response("post", security, {"topic_id": topic_id, "content": content})
        if not response["ok"]:
            return response

        post = {
            "id": self._next_post_id,
            "topic_id": topic_id,
            "author_id": 4,
            "author_name": "demo-user",
            "content": content,
            "created_at": int(time.time()),
            "reply_to": reply_to if isinstance(reply_to, int) else None,
        }
        self._next_post_id += 1
        self.posts.setdefault(topic_id, []).append(post)
        response["post"] = dict(post)
        return response

    def upload(self, body: dict[str, Any], headers: dict[str, str] | None = None, remote_addr: str = "127.0.0.1") -> dict[str, Any]:
        context = build_context(
            "POST",
            "/upload",
            headers or {},
            {
                "filename": str(body.get("filename") or "demo.txt")[:160],
                "text": str(body.get("text") or "")[:2000],
            },
            remote_addr,
            "file_upload",
        )
        security = self.adapter.event(context)
        return self._business_response("upload", security, {"filename": context["body"]["filename"]})

    def appeal(self, body: dict[str, Any]) -> dict[str, Any]:
        payload = {
            "punishment_id": str(body.get("punishment_id") or "")[:160],
            "banned_ip_hash": str(body.get("banned_ip_hash") or "")[:160],
            "reason": str(body.get("reason") or "")[:2000],
        }
        result = self.adapter.appeal(payload)
        return {
            "ok": result.get("accepted", False),
            "demo_action": "appeal_submitted",
            "appeal": result,
        }

    def _business_response(self, action: str, security: dict[str, Any], data: dict[str, Any]) -> dict[str, Any]:
        action_result = security.get("action_result") or {}
        executed = bool(action_result.get("executed"))
        held = executed or (security.get("route") or {}).get("route") == "fast_path_block"
        return {
            "ok": not held,
            "demo_action": f"{action}_{'accepted' if not held else 'held'}",
            "data": data,
            "security": self._security_summary(security),
            "core_response": security,
        }

    def _find_topic(self, topic_id: int) -> dict[str, Any] | None:
        for topic in self.topics:
            if topic["id"] == topic_id:
                return topic
        return None

    def _topic_payload(self, topic: dict[str, Any]) -> dict[str, Any]:
        payload = dict(topic)
        payload["post_count"] = len(self.posts.get(topic["id"], []))
        return payload

    def _security_summary(self, security: dict[str, Any]) -> dict[str, Any]:
        gateway = security.get("tool_gateway") or {}
        action_result = security.get("action_result") or {}
        return {
            "route": (security.get("route") or {}).get("route"),
            "event_type": (security.get("route") or {}).get("event_type"),
            "selected_action": (security.get("decision") or {}).get("selected_action"),
            "effective_action": gateway.get("effective_action"),
            "executed": bool(action_result.get("executed")),
            "message_zh": (security.get("display") or {}).get("message_zh"),
        }


DEMO = DemoBusinessApp(AteeThinAdapter(os.environ.get("ATEE_CORE_URL", "http://127.0.0.1:8787")))


class DemoHandler(BaseHTTPRequestHandler):
    server_version = "ATEEDemo/0.1"

    def do_GET(self) -> None:
        path = urlsplit(self.path).path
        if path in {"/", "/demo"}:
            self._send_text((STATIC_DIR / "index.html").read_text(encoding="utf-8"), "text/html; charset=utf-8")
            return
        if path == "/demo/styles.css":
            self._send_text((STATIC_DIR / "styles.css").read_text(encoding="utf-8"), "text/css; charset=utf-8")
            return
        if path == "/demo/demo.js":
            self._send_text((STATIC_DIR / "demo.js").read_text(encoding="utf-8"), "application/javascript; charset=utf-8")
            return
        if path == "/assets/flow.svg":
            self._send_text((STATIC_DIR / "assets" / "flow.svg").read_text(encoding="utf-8"), "image/svg+xml; charset=utf-8")
            return
        if path == "/api/stats":
            self._send_json(DEMO.stats())
            return
        if path == "/api/topics":
            self._send_json(DEMO.list_topics())
            return
        topic_posts_id = self._topic_posts_id(path)
        if topic_posts_id is not None:
            self._send_json(DEMO.list_posts(topic_posts_id))
            return
        if path == "/health":
            self._send_json({"ok": True, "service": "atee-demo-site"})
            return
        self._send_json({"error": "not_found"}, status=404)

    def do_POST(self) -> None:
        path = urlsplit(self.path).path
        body = self._read_json()
        headers = dict(self.headers.items())
        remote_addr = self.client_address[0] if self.client_address else "127.0.0.1"
        try:
            if path == "/api/login":
                self._send_json(DEMO.login(body, headers, remote_addr))
                return
            if path == "/api/comment":
                self._send_json(DEMO.comment(body, headers, remote_addr))
                return
            if path == "/api/topics":
                self._send_json(DEMO.create_topic(body, headers, remote_addr))
                return
            topic_posts_id = self._topic_posts_id(path)
            if topic_posts_id is not None:
                result = DEMO.create_post(topic_posts_id, body, headers, remote_addr)
                self._send_json(result, status=404 if result.get("error") == "topic_not_found" else 200)
                return
            if path == "/api/upload":
                self._send_json(DEMO.upload(body, headers, remote_addr))
                return
            if path == "/api/appeal":
                result = DEMO.appeal(body)
                status = int((result.get("appeal") or {}).get("status", 200))
                self._send_json(result, status=status)
                return
        except Exception as exc:
            self._send_json(
                {
                    "ok": False,
                    "error": "core_request_failed",
                    "message_zh": "演示站无法连接 ATEE Core Service，请检查 Core 地址和端口。",
                    "detail": str(exc)[:200],
                },
                status=502,
            )
            return
        self._send_json({"error": "not_found"}, status=404)

    def log_message(self, format: str, *args: Any) -> None:
        return

    def _read_json(self) -> dict[str, Any]:
        length = int(self.headers.get("Content-Length", "0") or "0")
        if length <= 0:
            return {}
        try:
            data = json.loads(self.rfile.read(length).decode("utf-8"))
            return data if isinstance(data, dict) else {}
        except json.JSONDecodeError:
            return {}

    def _send_json(self, payload: dict[str, Any], status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _send_text(self, text: str, content_type: str, status: int = 200) -> None:
        body = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self'; object-src 'none'; base-uri 'self'")
        self.end_headers()
        self.wfile.write(body)

    def _topic_posts_id(self, path: str) -> int | None:
        parts = [part for part in path.split("/") if part]
        if len(parts) == 4 and parts[:2] == ["api", "topics"] and parts[3] == "posts":
            try:
                return int(parts[2])
            except ValueError:
                return None
        return None


def run(host: str = "127.0.0.1", port: int = 8790) -> None:
    server = ThreadingHTTPServer((host, port), DemoHandler)
    print(f"ATEE Demo Site running at http://{host}:{port}")
    server.serve_forever()


def bind_from_env() -> tuple[str, int]:
    host = os.environ.get("ATEE_DEMO_HOST", "127.0.0.1")
    try:
        port = int(os.environ.get("ATEE_DEMO_PORT", "8790"))
    except ValueError:
        port = 8790
    return host, port


if __name__ == "__main__":
    demo_host, demo_port = bind_from_env()
    try:
        run(demo_host, demo_port)
    except OSError as exc:
        if exc.errno == errno.EADDRINUSE:
            print(f"ATEE Demo Site could not bind {demo_host}:{demo_port}; the address is already in use.", file=sys.stderr)
            sys.exit(98)
        raise
