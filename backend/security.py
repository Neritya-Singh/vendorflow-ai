"""Admin session cookies, CSRF and simple per-client throttling.

Demo-grade: one shared admin password, stateless HMAC-signed session cookie.
Not a production identity provider (no per-user accounts, MFA or revocation list).
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import threading
import time
from collections import OrderedDict

from fastapi import HTTPException, Request

from vendorflow.admin_login_guard import (
    clear_admin_login_failures, record_admin_login_failure, remaining_admin_lockout,
)

from .config import Settings

COOKIE_NAME = "vf_admin"
CSRF_HEADER = "x-csrf-token"


def _b64(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _unb64(text: str) -> bytes:
    return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4))


def issue_session(settings: Settings) -> tuple[str, str]:
    """Return (cookie value, csrf token). The CSRF token is bound inside the signed cookie."""
    csrf = secrets.token_urlsafe(24)
    payload = {"exp": int(time.time()) + settings.session_hours * 3600, "csrf": csrf,
               "sid": secrets.token_urlsafe(9)}
    body = _b64(json.dumps(payload, separators=(",", ":")).encode())
    sig = _b64(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    return f"{body}.{sig}", csrf


def read_session(settings: Settings, cookie: str | None) -> dict | None:
    if not cookie or "." not in cookie or not settings.admin_password:
        return None
    body, _, sig = cookie.partition(".")
    expected = _b64(hmac.new(settings.session_key, body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(expected, sig):
        return None
    try:
        payload = json.loads(_unb64(body))
    except (ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or int(payload.get("exp", 0)) < time.time():
        return None
    return payload


def client_key(request: Request) -> str:
    # Behind a single trusted proxy (Render/Fly/Cloud Run) the left-most
    # X-Forwarded-For is the client; only honour it when explicitly configured.
    forwarded = request.headers.get("x-forwarded-for", "")
    if forwarded and request.app.state.trust_proxy:
        return forwarded.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


class LoginThrottle:
    """Per-client wrapper around the v1.1 admin_login_guard (5 failures -> 15 min)."""

    def __init__(self, max_clients: int = 10_000):
        self._states: OrderedDict[str, dict] = OrderedDict()
        self._lock = threading.Lock()
        self._max = max_clients

    def _state(self, key: str) -> dict:
        state = self._states.setdefault(key, {})
        self._states.move_to_end(key)
        while len(self._states) > self._max:
            self._states.popitem(last=False)
        return state

    def locked_for(self, key: str) -> int:
        with self._lock:
            return remaining_admin_lockout(self._state(key))

    def failure(self, key: str) -> int:
        with self._lock:
            return record_admin_login_failure(self._state(key))

    def success(self, key: str) -> None:
        with self._lock:
            clear_admin_login_failures(self._state(key))


class SlidingWindowLimiter:
    """Coarse failure limiter for vendor credential lookups (anti-guessing)."""

    def __init__(self, limit: int, window_seconds: int):
        self.limit, self.window = limit, window_seconds
        self._hits: dict[str, list[float]] = {}
        self._lock = threading.Lock()

    def _recent(self, key: str, now: float) -> list[float]:
        hits = [t for t in self._hits.get(key, []) if now - t < self.window]
        if hits:
            self._hits[key] = hits
        else:
            self._hits.pop(key, None)
        return hits

    def blocked(self, key: str) -> bool:
        with self._lock:
            return len(self._recent(key, time.monotonic())) >= self.limit

    def hit(self, key: str) -> None:
        with self._lock:
            now = time.monotonic()
            self._hits[key] = [*self._recent(key, now), now]
            if len(self._hits) > 10_000:
                self._hits.pop(next(iter(self._hits)))


def require_admin(request: Request) -> dict:
    settings: Settings = request.app.state.settings
    session = read_session(settings, request.cookies.get(COOKIE_NAME))
    if session is None:
        raise HTTPException(status_code=401, detail="Sign in to the admin console to continue.")
    return session


def require_admin_csrf(request: Request) -> dict:
    session = require_admin(request)
    token = request.headers.get(CSRF_HEADER, "")
    if not token or not hmac.compare_digest(token, str(session.get("csrf", ""))):
        raise HTTPException(status_code=403, detail="Security token missing or expired. Refresh the page and retry.")
    return session
