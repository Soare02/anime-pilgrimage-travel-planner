"""Administrator login and revocable, process-local cookie sessions.

No configured credentials means no access. Sessions intentionally disappear on
restart; deploy this local backend with one worker (or use a shared session store).
"""

import hashlib
import hmac
import os
import secrets
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field

load_dotenv(Path(__file__).with_name(".env"))

COOKIE_NAME = "pilgrimage_admin_session"
NO_STORE = {"Cache-Control": "no-store", "Pragma": "no-cache"}
SAFE_METHODS = {"GET", "HEAD", "OPTIONS"}


def auth_error(status: int, message: str, **headers: str) -> HTTPException:
    return HTTPException(status_code=status, detail=message, headers={**NO_STORE, **headers})


@dataclass(frozen=True)
class AdminSession:
    username: str
    csrf_token: str
    expires_at: int

    def public_data(self) -> dict:
        return {"username": self.username, "csrf_token": self.csrf_token, "expires_at": self.expires_at}


class AdminAuth:
    LOGIN_WINDOW = 300
    MAX_LOGIN_ATTEMPTS = 5
    MAX_SESSIONS = 128

    def __init__(self, username: str, password: str, *, ttl: int = 28800, secure: bool = False):
        self.username = username.strip()
        self.configured = 1 <= len(self.username) <= 128 and 12 <= len(password) <= 1024
        self.ttl = max(300, min(ttl, 86400))
        self.secure = secure
        self._salt = secrets.token_bytes(16)
        self._password_hash = self._hash_password(password) if self.configured else b""
        self._sessions: dict[str, AdminSession] = {}
        self._attempts: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _hash_password(self, password: str) -> bytes:
        return hashlib.scrypt(password.encode("utf-8"), salt=self._salt, n=16384, r=8, p=1)

    def require_configured(self) -> None:
        if not self.configured:
            raise auth_error(503, "管理功能未配置。请在后端设置 ADMIN_USERNAME 和至少 12 位的 ADMIN_PASSWORD 后重启。")

    def login(self, username: str, password: str, address: str) -> tuple[str, AdminSession]:
        self.require_configured()
        now = time.time()
        with self._lock:
            self._attempts = {key: [t for t in times if t > now - self.LOGIN_WINDOW]
                              for key, times in self._attempts.items() if times[-1] > now - self.LOGIN_WINDOW}
            attempts = self._attempts.get(address, [])
            if len(attempts) >= self.MAX_LOGIN_ATTEMPTS:
                retry = max(1, int(attempts[0] + self.LOGIN_WINDOW - now) + 1)
                raise auth_error(429, "登录尝试过于频繁，请稍后重试。", **{"Retry-After": str(retry)})
            # Limit memory even when the server receives many distinct client IPs.
            if address not in self._attempts and len(self._attempts) >= 1024:
                raise auth_error(429, "登录尝试过于频繁，请稍后重试。", **{"Retry-After": "300"})
            self._attempts[address] = [*attempts, now]

        password_matches = hmac.compare_digest(self._hash_password(password), self._password_hash)
        username_matches = hmac.compare_digest(username.encode("utf-8"), self.username.encode("utf-8"))
        if not (password_matches and username_matches):
            raise auth_error(401, "管理员账号或密码错误。")

        token = secrets.token_urlsafe(32)
        session = AdminSession(self.username, secrets.token_urlsafe(32), int(now) + self.ttl)
        with self._lock:
            self._attempts.pop(address, None)
            self._sessions = {key: value for key, value in self._sessions.items() if value.expires_at > now}
            if len(self._sessions) >= self.MAX_SESSIONS:
                self._sessions.pop(next(iter(self._sessions)))
            self._sessions[self._token_hash(token)] = session
        return token, session

    @staticmethod
    def _token_hash(token: str) -> str:
        return hashlib.sha256(token.encode("utf-8")).hexdigest()

    def authenticate(self, request: Request) -> AdminSession:
        self.require_configured()
        token = request.cookies.get(COOKIE_NAME, "")
        key = self._token_hash(token)
        with self._lock:
            session = self._sessions.get(key)
            if session and session.expires_at <= time.time():
                self._sessions.pop(key, None)
                session = None
        if not session:
            raise auth_error(401, "请先登录管理员账号。")
        if request.method not in SAFE_METHODS:
            csrf = request.headers.get("X-CSRF-Token", "")
            if not hmac.compare_digest(csrf.encode("utf-8"), session.csrf_token.encode("utf-8")):
                raise auth_error(403, "请求校验失败，请刷新管理页面后重试。")
        return session

    def revoke(self, token: str) -> None:
        with self._lock:
            self._sessions.pop(self._token_hash(token), None)


def _session_ttl() -> int:
    try:
        return int(os.getenv("ADMIN_SESSION_TTL_SECONDS", "28800"))
    except ValueError:
        return 28800


admin_auth = AdminAuth(
    os.getenv("ADMIN_USERNAME", ""), os.getenv("ADMIN_PASSWORD", ""),
    ttl=_session_ttl(), secure=os.getenv("ADMIN_COOKIE_SECURE", "0") == "1",
)


def require_admin(request: Request, response: Response) -> AdminSession:
    session = admin_auth.authenticate(request)
    response.headers.update(NO_STORE)
    return session


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=128)
    password: str = Field(min_length=1, max_length=1024, repr=False)


router = APIRouter(prefix="/api/admin", tags=["administration"])


@router.post("/login")
def login(req: LoginRequest, request: Request, response: Response):
    # A custom header prevents cross-origin HTML forms from logging a browser in.
    # Cross-origin JS cannot send it without an allowed CORS preflight.
    if request.headers.get("X-Admin-Request") != "1" or request.headers.get("Sec-Fetch-Site") == "cross-site":
        raise auth_error(403, "请从管理页面发起登录。")
    address = request.client.host if request.client else "unknown"
    token, session = admin_auth.login(req.username, req.password, address)
    admin_auth.revoke(request.cookies.get(COOKIE_NAME, ""))
    response.headers.update(NO_STORE)
    response.set_cookie(
        COOKIE_NAME, token, max_age=admin_auth.ttl, httponly=True,
        secure=admin_auth.secure, samesite="strict", path="/api",
    )
    return session.public_data()


@router.get("/session")
def get_session(session: AdminSession = Depends(require_admin)):
    return session.public_data()


@router.post("/logout")
def logout(request: Request, response: Response, session: AdminSession = Depends(require_admin)):
    admin_auth.revoke(request.cookies.get(COOKIE_NAME, ""))
    response.delete_cookie(COOKIE_NAME, path="/api", httponly=True, secure=admin_auth.secure, samesite="strict")
    return {"status": "success"}
