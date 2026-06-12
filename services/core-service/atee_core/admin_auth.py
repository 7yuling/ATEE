import hashlib
import hmac
import secrets
import sqlite3
import time
from contextlib import closing
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PBKDF2_ITERATIONS = 200_000


class AdminAuthService:
    def __init__(self, sqlite_path: str | Path | None = None):
        self.path = Path(sqlite_path) if sqlite_path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            self._ensure_schema()

    def status(self) -> dict[str, Any]:
        return {
            "accounts_configured": self.admin_count() > 0,
            "admin_count": self.admin_count(),
            "captcha_login_enabled": self.path is not None,
            "bootstrap_allowed": self.admin_count() == 0,
        }

    def admin_count(self) -> int:
        if not self.path:
            return 0
        with closing(self._connect()) as conn:
            row = conn.execute("SELECT COUNT(*) FROM admin_accounts WHERE disabled_at IS NULL").fetchone()
        return int(row[0] if row else 0)

    def list_admins(self) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "admin_account_store_unavailable", "admins": []}
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            rows = conn.execute(
                """
                SELECT username, created_at, updated_at, last_login_at, disabled_at
                FROM admin_accounts
                ORDER BY username ASC
                """
            ).fetchall()
        return {
            "ok": True,
            "admins": [dict(row) for row in rows],
            "count": len(rows),
            "display": {"locale": "zh-CN", "message_zh": "管理员账号列表已返回。"},
        }

    def create_captcha(self) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "admin_account_store_unavailable"}
        self._cleanup_expired()
        left = secrets.randbelow(8) + 2
        right = secrets.randbelow(8) + 2
        answer = str(left + right)
        captcha_id = secrets.token_urlsafe(18)
        salt = secrets.token_hex(16)
        now = self._now_iso()
        expires_at = time.time() + 300
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO admin_captchas
                (captcha_id, answer_hash, salt, expires_at, attempts, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (captcha_id, self._hash_text(answer, salt), salt, expires_at, 0, now),
            )
            conn.commit()
        return {
            "ok": True,
            "captcha_id": captcha_id,
            "question": f"{left} + {right} = ?",
            "expires_in_seconds": 300,
            "display": {"locale": "zh-CN", "message_zh": "验证码已生成，5 分钟内有效。"},
        }

    def register(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.admin_count() > 0:
            return {"ok": False, "status": 403, "reason": "first_admin_already_exists"}
        captcha_error = self._verify_captcha_from_payload(payload)
        if captcha_error:
            return captcha_error
        return self._create_admin(payload, bootstrap=True)

    def create_admin(self, payload: dict[str, Any]) -> dict[str, Any]:
        return self._create_admin(payload, bootstrap=False)

    def change_password(self, payload: dict[str, Any], actor_username: str | None = None) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "admin_account_store_unavailable"}
        username = self._clean_username(payload.get("username") or actor_username or "")
        old_password = str(payload.get("old_password") or "")
        new_password = str(payload.get("new_password") or "")
        if not username:
            return {"ok": False, "status": 400, "reason": "username_required"}
        if len(new_password) < 8:
            return {"ok": False, "status": 400, "reason": "new_password_too_short"}
        if actor_username and actor_username == username and not self.verify_password(username, old_password):
            return {"ok": False, "status": 403, "reason": "old_password_invalid"}
        password_hash, salt = self._hash_password(new_password)
        now = self._now_iso()
        with closing(self._connect()) as conn:
            cursor = conn.execute(
                """
                UPDATE admin_accounts
                SET password_hash = ?, salt = ?, updated_at = ?
                WHERE username = ? AND disabled_at IS NULL
                """,
                (password_hash, salt, now, username),
            )
            conn.commit()
        if cursor.rowcount != 1:
            return {"ok": False, "status": 404, "reason": "admin_not_found"}
        return {
            "ok": True,
            "username": username,
            "display": {"locale": "zh-CN", "message_zh": "管理员密码已更新。"},
        }

    def login(self, payload: dict[str, Any], remote_addr: str = "") -> dict[str, Any]:
        captcha_error = self._verify_captcha_from_payload(payload)
        if captcha_error:
            return captcha_error
        username = self._clean_username(payload.get("username"))
        password = str(payload.get("password") or "")
        if not self.verify_password(username, password):
            return {"ok": False, "status": 401, "reason": "invalid_admin_credentials"}
        token = secrets.token_urlsafe(36)
        token_hash = self._hash_session_token(token)
        now = self._now_iso()
        expires_at = time.time() + 12 * 3600
        with closing(self._connect()) as conn:
            conn.execute(
                """
                INSERT INTO admin_sessions
                (token_hash, username, source_hash, expires_at, created_at)
                VALUES (?, ?, ?, ?, ?)
                """,
                (token_hash, username, self._hash_text(remote_addr or "unknown", "source")[:32], expires_at, now),
            )
            conn.execute("UPDATE admin_accounts SET last_login_at = ?, updated_at = ? WHERE username = ?", (now, now, username))
            conn.commit()
        return {
            "ok": True,
            "token": token,
            "username": username,
            "expires_in_seconds": 12 * 3600,
            "display": {"locale": "zh-CN", "message_zh": "管理员登录成功。"},
        }

    def validate_session(self, token: str) -> dict[str, Any] | None:
        if not self.path or not token:
            return None
        self._cleanup_expired()
        token_hash = self._hash_session_token(token)
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT s.username, s.expires_at
                FROM admin_sessions s
                JOIN admin_accounts a ON a.username = s.username
                WHERE s.token_hash = ? AND a.disabled_at IS NULL
                """,
                (token_hash,),
            ).fetchone()
        if not row or float(row["expires_at"]) < time.time():
            return None
        return {"username": row["username"]}

    def verify_password(self, username: str, password: str) -> bool:
        if not self.path or not username or not password:
            return False
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                """
                SELECT password_hash, salt
                FROM admin_accounts
                WHERE username = ? AND disabled_at IS NULL
                """,
                (self._clean_username(username),),
            ).fetchone()
        if not row:
            return False
        expected = str(row["password_hash"])
        password_hash = self._hash_password(password, salt=str(row["salt"]))[0]
        return hmac.compare_digest(password_hash, expected)

    def _create_admin(self, payload: dict[str, Any], bootstrap: bool) -> dict[str, Any]:
        if not self.path:
            return {"ok": False, "status": 503, "reason": "admin_account_store_unavailable"}
        username = self._clean_username(payload.get("username"))
        password = str(payload.get("password") or "")
        if not username:
            return {"ok": False, "status": 400, "reason": "username_required"}
        if len(password) < 8:
            return {"ok": False, "status": 400, "reason": "password_too_short"}
        password_hash, salt = self._hash_password(password)
        now = self._now_iso()
        try:
            with closing(self._connect()) as conn:
                conn.execute(
                    """
                    INSERT INTO admin_accounts
                    (username, password_hash, salt, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?)
                    """,
                    (username, password_hash, salt, now, now),
                )
                conn.commit()
        except sqlite3.IntegrityError:
            return {"ok": False, "status": 409, "reason": "admin_already_exists"}
        return {
            "ok": True,
            "username": username,
            "bootstrap": bootstrap,
            "display": {"locale": "zh-CN", "message_zh": "管理员账号已创建。"},
        }

    def _verify_captcha_from_payload(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        captcha_id = str(payload.get("captcha_id") or "").strip()
        answer = str(payload.get("captcha_answer") or "").strip()
        if not captcha_id or not answer:
            return {"ok": False, "status": 400, "reason": "captcha_required"}
        if not self._verify_captcha(captcha_id, answer):
            return {"ok": False, "status": 401, "reason": "captcha_invalid_or_expired"}
        return None

    def _verify_captcha(self, captcha_id: str, answer: str) -> bool:
        if not self.path:
            return False
        with closing(self._connect()) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT answer_hash, salt, expires_at, attempts FROM admin_captchas WHERE captcha_id = ?",
                (captcha_id,),
            ).fetchone()
            if not row:
                return False
            conn.execute("UPDATE admin_captchas SET attempts = attempts + 1 WHERE captcha_id = ?", (captcha_id,))
            if float(row["expires_at"]) < time.time() or int(row["attempts"] or 0) >= 5:
                conn.execute("DELETE FROM admin_captchas WHERE captcha_id = ?", (captcha_id,))
                conn.commit()
                return False
            ok = hmac.compare_digest(str(row["answer_hash"]), self._hash_text(answer, str(row["salt"])))
            if ok:
                conn.execute("DELETE FROM admin_captchas WHERE captcha_id = ?", (captcha_id,))
            conn.commit()
            return ok

    def _cleanup_expired(self) -> None:
        if not self.path:
            return
        now = time.time()
        with closing(self._connect()) as conn:
            conn.execute("DELETE FROM admin_captchas WHERE expires_at < ?", (now,))
            conn.execute("DELETE FROM admin_sessions WHERE expires_at < ?", (now,))
            conn.commit()

    def _hash_password(self, password: str, salt: str | None = None) -> tuple[str, str]:
        salt = salt or secrets.token_hex(16)
        digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt.encode("utf-8"), PBKDF2_ITERATIONS)
        return digest.hex(), salt

    def _hash_session_token(self, token: str) -> str:
        return hashlib.sha256(str(token).encode("utf-8")).hexdigest()

    def _hash_text(self, text: str, salt: str) -> str:
        return hashlib.sha256(f"{salt}:{text}".encode("utf-8")).hexdigest()

    def _clean_username(self, value: Any) -> str:
        cleaned = "".join(ch for ch in str(value or "").strip() if ch.isalnum() or ch in {"@", ".", "_", "-"})
        return cleaned[:80]

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _connect(self) -> sqlite3.Connection:
        if not self.path:
            raise RuntimeError("admin_account_store_unavailable")
        conn = sqlite3.connect(self.path, timeout=30)
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        return conn

    def _ensure_schema(self) -> None:
        with closing(self._connect()) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_accounts (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    last_login_at TEXT,
                    disabled_at TEXT
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_sessions (
                    token_hash TEXT PRIMARY KEY,
                    username TEXT NOT NULL,
                    source_hash TEXT,
                    expires_at REAL NOT NULL,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS admin_captchas (
                    captcha_id TEXT PRIMARY KEY,
                    answer_hash TEXT NOT NULL,
                    salt TEXT NOT NULL,
                    expires_at REAL NOT NULL,
                    attempts INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL
                )
                """
            )
            conn.execute("CREATE INDEX IF NOT EXISTS idx_admin_sessions_username ON admin_sessions(username)")
            conn.commit()
