import hashlib
import hmac
import os
import secrets
import sqlite3
import threading
import time
from contextvars import ContextVar
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

ROOT = Path(__file__).resolve().parent.parent
CURRENT_USER = ContextVar("dataflow_current_user", default=None)
CURRENT_ROLE = ContextVar("dataflow_current_role", default=None)
CURRENT_SESSION = ContextVar("dataflow_current_session", default=None)
PASSWORD_ITERATIONS = 600_000
SESSION_HOURS = 12
MAX_LOGIN_ATTEMPTS = 8
LOGIN_WINDOW_SECONDS = 300
REQUEST_LIMIT = 180
REQUEST_WINDOW_SECONDS = 60
RATE_BUCKETS: dict[str, list[float]] = {}
RATE_LOCK = threading.Lock()


class ClosingConnection(sqlite3.Connection):
    def __exit__(self, exc_type, exc_value, traceback):
        try:
            return super().__exit__(exc_type, exc_value, traceback)
        finally:
            self.close()


def auth_enabled() -> bool:
    return os.getenv("DATAFLOW_AUTH_ENABLED", "true").strip().lower() not in ("0", "false", "no")


def database_path() -> Path:
    configured = os.getenv("DATAFLOW_AUTH_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    data_root = Path(os.getenv("DATAFLOW_DATA_DIR", str(ROOT / "workspace"))).expanduser()
    return data_root / "auth.sqlite3"


def _connect() -> sqlite3.Connection:
    path = database_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path, timeout=10, factory=ClosingConnection)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys=ON")
    connection.execute("PRAGMA busy_timeout=10000")
    return connection


def initialize() -> None:
    with _connect() as connection:
        connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS users (
                id TEXT PRIMARY KEY,
                username TEXT NOT NULL UNIQUE COLLATE NOCASE,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL CHECK(role IN ('admin', 'analyst', 'viewer')),
                enabled INTEGER NOT NULL DEFAULT 1,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS sessions (
                token_hash TEXT PRIMARY KEY,
                user_id TEXT NOT NULL REFERENCES users(id) ON DELETE CASCADE,
                csrf_token TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT,
                username TEXT,
                role TEXT,
                action TEXT NOT NULL,
                resource TEXT NOT NULL,
                status_code INTEGER NOT NULL,
                client_ip TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_sessions_expiry ON sessions(expires_at);
            CREATE INDEX IF NOT EXISTS idx_audit_created ON audit_log(created_at DESC);
            """
        )


def has_users() -> bool:
    initialize()
    with _connect() as connection:
        return connection.execute("SELECT EXISTS(SELECT 1 FROM users)").fetchone()[0] == 1


def _hash_password(password: str, salt: bytes | None = None) -> str:
    salt = salt or secrets.token_bytes(16)
    derived = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), salt, PASSWORD_ITERATIONS)
    return f"pbkdf2_sha256${PASSWORD_ITERATIONS}${salt.hex()}${derived.hex()}"


def _verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, rounds, salt, expected = encoded.split("$", 3)
        if algorithm != "pbkdf2_sha256" or int(rounds) < 100_000:
            return False
        actual = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt), int(rounds))
        return hmac.compare_digest(actual.hex(), expected)
    except (ValueError, TypeError):
        return False


DUMMY_PASSWORD_HASH = _hash_password("DataFlow dummy login verifier")


def _validate_account(username: str, password: str) -> tuple[str, str]:
    name = username.strip()
    if len(name) < 3 or len(name) > 64 or not all(ch.isalnum() or ch in "._-@" for ch in name):
        raise HTTPException(400, "Login 3–64 belgi bo'lsin (harf, raqam, . _ - @)")
    if len(password) < 12 or len(password) > 256:
        raise HTTPException(400, "Parol 12–256 belgi bo'lishi kerak")
    return name, _hash_password(password)


def create_first_admin(username: str, password: str) -> dict:
    name, password_hash = _validate_account(username, password)
    initialize()
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        if connection.execute("SELECT EXISTS(SELECT 1 FROM users)").fetchone()[0]:
            raise HTTPException(409, "Birinchi administrator allaqachon yaratilgan")
        user_id = uuid4().hex
        created = datetime.now(timezone.utc).isoformat()
        connection.execute(
            "INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?, ?, ?, 'admin', ?)",
            (user_id, name, password_hash, created),
        )
    return {"id": user_id, "username": name, "role": "admin"}


def create_user(username: str, password: str, role: str) -> dict:
    if role not in ("admin", "analyst", "viewer"):
        raise HTTPException(400, "Rol admin, analyst yoki viewer bo'lishi kerak")
    name, password_hash = _validate_account(username, password)
    user_id = uuid4().hex
    try:
        with _connect() as connection:
            connection.execute(
                "INSERT INTO users (id, username, password_hash, role, created_at) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, password_hash, role, datetime.now(timezone.utc).isoformat()),
            )
    except sqlite3.IntegrityError as error:
        raise HTTPException(409, "Bu login band") from error
    return {"id": user_id, "username": name, "role": role}


def change_user(user_id: str, enabled: bool | None, role: str | None, password: str | None) -> dict:
    if role is not None and role not in ("admin", "analyst", "viewer"):
        raise HTTPException(400, "Rol admin, analyst yoki viewer bo'lishi kerak")
    password_hash = _hash_password(password) if password is not None else None
    if password is not None and (len(password) < 12 or len(password) > 256):
        raise HTTPException(400, "Parol 12–256 belgi bo'lishi kerak")
    with _connect() as connection:
        connection.execute("BEGIN IMMEDIATE")
        user = connection.execute("SELECT id, username, role, enabled FROM users WHERE id=?", (user_id,)).fetchone()
        if not user:
            raise HTTPException(404, "Foydalanuvchi topilmadi")
        if user["role"] == "admin" and user["enabled"] and (enabled is False or role not in (None, "admin")):
            admins = connection.execute(
                "SELECT COUNT(*) FROM users WHERE role='admin' AND enabled=1"
            ).fetchone()[0]
            if admins <= 1:
                raise HTTPException(400, "Tizimda kamida bitta faol administrator qolishi kerak")
        connection.execute(
            "UPDATE users SET enabled=COALESCE(?, enabled), role=COALESCE(?, role), "
            "password_hash=COALESCE(?, password_hash) WHERE id=?",
            (None if enabled is None else int(enabled), role, password_hash, user_id),
        )
        if enabled is False or password_hash:
            connection.execute("DELETE FROM sessions WHERE user_id=?", (user_id,))
        changed = connection.execute(
            "SELECT id, username, role, enabled FROM users WHERE id=?", (user_id,)
        ).fetchone()
    return dict(changed)


def list_users() -> list[dict]:
    with _connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id, username, role, enabled, created_at FROM users ORDER BY username"
            ).fetchall()
        ]


def create_session(username: str, password: str) -> tuple[dict, str, str]:
    initialize()
    with _connect() as connection:
        user = connection.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username=? COLLATE NOCASE AND enabled=1",
            (username.strip(),),
        ).fetchone()
    # Keep the password hash path indistinguishable for unknown account names.
    if user:
        valid = _verify_password(password, user["password_hash"])
    else:
        _verify_password(password, DUMMY_PASSWORD_HASH)
        valid = False
    if not valid:
        raise HTTPException(401, "Login yoki parol noto'g'ri")
    token = secrets.token_urlsafe(32)
    csrf_token = secrets.token_urlsafe(24)
    now = datetime.now(timezone.utc)
    with _connect() as connection:
        connection.execute("DELETE FROM sessions WHERE expires_at <= ?", (now.isoformat(),))
        connection.execute(
            "INSERT INTO sessions (token_hash, user_id, csrf_token, expires_at, created_at) VALUES (?, ?, ?, ?, ?)",
            (
                hashlib.sha256(token.encode()).hexdigest(),
                user["id"],
                csrf_token,
                (now + timedelta(hours=SESSION_HOURS)).isoformat(),
                now.isoformat(),
            ),
        )
    return (
        {"id": user["id"], "username": user["username"], "role": user["role"]},
        token,
        csrf_token,
    )


def session_for_token(token: str | None) -> dict | None:
    if not token:
        return None
    token_hash = hashlib.sha256(token.encode()).hexdigest()
    with _connect() as connection:
        row = connection.execute(
            "SELECT users.id, users.username, users.role, sessions.csrf_token, sessions.expires_at "
            "FROM sessions JOIN users ON users.id=sessions.user_id "
            "WHERE sessions.token_hash=? AND users.enabled=1",
            (token_hash,),
        ).fetchone()
    if not row:
        return None
    try:
        expiry = datetime.fromisoformat(row["expires_at"])
    except ValueError:
        return None
    if expiry <= datetime.now(timezone.utc):
        with _connect() as connection:
            connection.execute("DELETE FROM sessions WHERE token_hash=?", (token_hash,))
        return None
    return dict(row)


def revoke_session(token: str | None) -> None:
    if token:
        with _connect() as connection:
            connection.execute(
                "DELETE FROM sessions WHERE token_hash=?",
                (hashlib.sha256(token.encode()).hexdigest(),),
            )


def record_audit(
    user: dict | None, action: str, resource: str, status: int, client_ip: str
) -> None:
    with _connect() as connection:
        connection.execute(
            "INSERT INTO audit_log (user_id, username, role, action, resource, status_code, client_ip, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (
                user.get("id") if user else None,
                user.get("username") if user else None,
                user.get("role") if user else None,
                action[:12],
                resource[:240],
                status,
                client_ip[:64],
                datetime.now(timezone.utc).isoformat(),
            ),
        )


def audit_events(limit: int) -> list[dict]:
    with _connect() as connection:
        return [
            dict(row)
            for row in connection.execute(
                "SELECT id, username, role, action, resource, status_code, client_ip, created_at "
                "FROM audit_log ORDER BY id DESC LIMIT ?",
                (max(1, min(limit, 500)),),
            ).fetchall()
        ]


def _is_local(request: Request) -> bool:
    host = request.client.host if request.client else ""
    return host in ("127.0.0.1", "::1", "localhost", "testclient")


def _allow_rate(key: str, limit: int, window: int) -> bool:
    now = time.monotonic()
    with RATE_LOCK:
        if len(RATE_BUCKETS) > 10_000:
            for bucket, timestamps in list(RATE_BUCKETS.items()):
                if not timestamps or now - timestamps[-1] >= max(window, REQUEST_WINDOW_SECONDS):
                    RATE_BUCKETS.pop(bucket, None)
        events = [stamp for stamp in RATE_BUCKETS.get(key, []) if now - stamp < window]
        if len(events) >= limit:
            RATE_BUCKETS[key] = events
            return False
        events.append(now)
        RATE_BUCKETS[key] = events
        return True


def _set_context(user: dict | None, session: dict | None):
    user_token = CURRENT_USER.set(user["id"] if user else "local")
    role_token = CURRENT_ROLE.set(user["role"] if user else None)
    session_token = CURRENT_SESSION.set(session)
    return user_token, role_token, session_token


def reset_context(tokens) -> None:
    CURRENT_USER.reset(tokens[0])
    CURRENT_ROLE.reset(tokens[1])
    CURRENT_SESSION.reset(tokens[2])


def current_user_id() -> str:
    return CURRENT_USER.get() or "local"


def current_role() -> str | None:
    return CURRENT_ROLE.get()


def set_audit_resource(user: dict | None, path: str) -> str:
    return f"{user['id'] if user else 'local'}:{path}"


class LoginIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)


class SetupIn(LoginIn):
    setup_token: str = Field(default="", max_length=256)


class UserIn(BaseModel):
    username: str = Field(min_length=3, max_length=64)
    password: str = Field(min_length=1, max_length=256)
    role: str = "analyst"


class UserUpdateIn(BaseModel):
    enabled: bool | None = None
    role: str | None = None
    password: str | None = Field(default=None, min_length=12, max_length=256)


def make_router() -> APIRouter:
    router = APIRouter()

    @router.get("/auth/status")
    def status():
        return {"configured": has_users(), "auth_enabled": auth_enabled()}

    @router.post("/auth/setup")
    def setup(req: SetupIn, request: Request):
        if not auth_enabled() and not _is_local(request):
            raise HTTPException(503, "Masofaviy administrator sozlashi uchun autentifikatsiya yoqilishi kerak")
        initialize()
        if has_users():
            raise HTTPException(409, "Birinchi administrator allaqachon yaratilgan")
        expected = os.getenv("DATAFLOW_BOOTSTRAP_TOKEN", "")
        if expected:
            if not hmac.compare_digest(req.setup_token, expected):
                raise HTTPException(403, "Administrator yaratish kodi noto'g'ri")
        elif not _is_local(request):
            raise HTTPException(403, "Birinchi administratorni faqat localhost'dan yarating")
        user = create_first_admin(req.username, req.password)
        initialize_owner = getattr(request.app.state, "workspace_owner_initializer", None)
        if initialize_owner:
            initialize_owner(user["id"])
        record_audit(user, "setup", "/auth/setup", 201, request.client.host if request.client else "unknown")
        return {"user": user, "message": "Administrator yaratildi. Endi tizimga kiring."}

    @router.post("/auth/login")
    def login(req: LoginIn, request: Request):
        key = request.client.host if request.client else "unknown"
        if not _allow_rate(f"login:{key}", MAX_LOGIN_ATTEMPTS, LOGIN_WINDOW_SECONDS):
            raise HTTPException(429, "Kirish urinishlari limiti tugadi. Birozdan so'ng qayta urinib ko'ring.")
        try:
            user, token, csrf = create_session(req.username, req.password)
        except HTTPException as error:
            record_audit(
                {"id": None, "username": req.username, "role": None},
                "login_failed",
                "/auth/login",
                error.status_code,
                key,
            )
            raise
        record_audit(user, "login", "/auth/login", 200, key)
        response = JSONResponse({"user": user, "csrf_token": csrf, "expires_in": SESSION_HOURS * 3600})
        response.set_cookie(
            "dataflow_session",
            token,
            httponly=True,
            secure=os.getenv("DATAFLOW_SECURE_COOKIES", "false").lower() == "true",
            samesite="strict",
            max_age=SESSION_HOURS * 3600,
            path="/",
        )
        return response

    @router.post("/auth/logout")
    def logout(request: Request):
        session = CURRENT_SESSION.get()
        revoke_session(request.cookies.get("dataflow_session"))
        if session:
            record_audit(
                {"id": session["id"], "username": session["username"], "role": session["role"]},
                "logout",
                "/auth/logout",
                200,
                request.client.host if request.client else "unknown",
            )
        response = JSONResponse({"logged_out": True})
        response.delete_cookie("dataflow_session", path="/", httponly=True, samesite="strict")
        return response

    @router.get("/auth/me")
    def me(request: Request):
        session = session_for_token(request.cookies.get("dataflow_session"))
        if not session:
            raise HTTPException(401, "Tizimga kiring")
        return {
            "user": {
                "id": session["id"], "username": session["username"], "role": session["role"]
            },
            "csrf_token": session["csrf_token"],
        }

    @router.get("/auth/users")
    def users():
        if current_role() != "admin":
            raise HTTPException(403, "Foydalanuvchilarni faqat administrator boshqaradi")
        return list_users()

    @router.post("/auth/users")
    def add_user(req: UserIn):
        if current_role() != "admin":
            raise HTTPException(403, "Foydalanuvchi qo'shish uchun administrator huquqi kerak")
        return create_user(req.username, req.password, req.role)

    @router.patch("/auth/users/{user_id}")
    def update_user(user_id: str, req: UserUpdateIn):
        if current_role() != "admin":
            raise HTTPException(403, "Foydalanuvchini boshqarish uchun administrator huquqi kerak")
        current = CURRENT_SESSION.get()
        if current and current["id"] == user_id and req.enabled is False:
            raise HTTPException(400, "O'zingizning administrator hisobingizni o'chira olmaysiz")
        return change_user(user_id, req.enabled, req.role, req.password)

    @router.get("/auth/audit")
    def audit(limit: int = 100):
        if current_role() != "admin":
            raise HTTPException(403, "Audit jurnalini faqat administrator ko'ra oladi")
        return audit_events(limit)

    return router


def public_path(path: str) -> bool:
    return (
        path in (
            "/", "/health", "/charts.js", "/dashboard.js", "/pycells.js", "/extras.js",
            "/i18n.js", "/auth.js", "/favicon.ico", "/auth/status", "/auth/setup", "/auth/login",
        )
    )


def required_role(path: str, method: str) -> str:
    if path == "/auth/logout":
        return "viewer"
    if path == "/settings":
        return "analyst" if method in ("GET", "HEAD") else "admin"
    if path.startswith("/auth/users") or path.startswith("/auth/audit"):
        return "admin"
    if path in ("/settings", "/report-settings", "/reports/refresh", "/backup"):
        return "admin"
    if (
        path == "/sql"
        or path.startswith("/py/")
        or path.startswith("/templates/")
        or path.endswith("/ask")
        or path.endswith("/insights")
        or path.endswith("/clean/suggest")
    ):
        return "analyst"
    if method not in ("GET", "HEAD", "OPTIONS"):
        return "analyst"
    return "viewer"


ROLE_ORDER = {"viewer": 0, "analyst": 1, "admin": 2}


async def auth_middleware(request: Request, call_next):
    initialize()
    client_ip = request.client.host if request.client else "unknown"
    path = request.url.path
    if auth_enabled() and not _allow_rate(f"request:{client_ip}", REQUEST_LIMIT, REQUEST_WINDOW_SECONDS):
        return JSONResponse({"detail": "So'rovlar limiti tugadi. Birozdan so'ng qayta urinib ko'ring."}, 429)
    if not _is_local(request) and not auth_enabled() and not public_path(path):
        return JSONResponse({"detail": "Masofaviy foydalanish uchun autentifikatsiya majburiy."}, 503)
    if (
        not _is_local(request)
        and os.getenv("DATAFLOW_PYTHON_SANDBOX", "local").strip().lower() != "docker"
        and (
            path == "/sql"
            or path.startswith("/dashboard")
            or path.endswith("/ask")
            or path.startswith("/templates/") and path.endswith("/run")
        )
    ):
        return JSONResponse(
            {"detail": "Masofaviy SQL/Python bajarish uchun izolyatsiyalangan Docker sandbox majburiy."},
            503,
        )

    user = None
    session = None
    if auth_enabled() and not public_path(path):
        if not has_users():
            return JSONResponse(
                {"detail": "Avval /auth/setup orqali birinchi administratorni yarating.", "setup_required": True},
                503,
            )
        session = session_for_token(request.cookies.get("dataflow_session"))
        if not session:
            return JSONResponse({"detail": "Tizimga kiring.", "auth_required": True}, 401)
        user = {"id": session["id"], "username": session["username"], "role": session["role"]}
        required = required_role(path, request.method)
        if ROLE_ORDER.get(user["role"], -1) < ROLE_ORDER[required]:
            return JSONResponse({"detail": "Bu amal uchun huquq yetarli emas."}, 403)
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("origin")
            expected_origin = f"{request.url.scheme}://{request.headers.get('host', '')}"
            if origin and origin.rstrip("/") != expected_origin.rstrip("/"):
                return JSONResponse({"detail": "So'rov manbai ruxsat etilmagan."}, 403)
            if not hmac.compare_digest(request.headers.get("x-csrf-token", ""), session["csrf_token"]):
                return JSONResponse({"detail": "CSRF token noto'g'ri. Sahifani yangilang."}, 403)

    tokens = _set_context(user, session)
    try:
        if user and not public_path(path):
            initialize_workspace = getattr(request.app.state, "workspace_initializer", None)
            if initialize_workspace:
                initialize_workspace(user["id"])
        response = await call_next(request)
    except Exception:
        if auth_enabled() and not public_path(path):
            try:
                record_audit(user, request.method, path, 500, client_ip)
            except sqlite3.Error:
                pass
        raise
    finally:
        reset_context(tokens)
    if auth_enabled() and not public_path(path):
        try:
            record_audit(user, request.method, path, response.status_code, client_ip)
        except sqlite3.Error:
            # Database errors must not turn a successful request into a false success.
            response = JSONResponse({"detail": "Audit jurnalini yozib bo'lmadi."}, 500)
    return response
