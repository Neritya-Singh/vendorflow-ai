"""Server-side configuration. Secret VALUES never leave this process."""
from __future__ import annotations

import hashlib
import os
import secrets
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]


def _flag(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    offline_mode: bool
    offline_extractor: str  # "labels" (test double) or "gemini" (real client, for failure tests)
    admin_password: str
    session_key: bytes = field(repr=False)
    cookie_secure: bool = True
    session_hours: int = 8
    frontend_dist: Path = ROOT / "frontend" / "dist"

    @property
    def gemini_configured(self) -> bool:
        return bool(os.getenv("GEMINI_API_KEY", "").strip())

    @property
    def supabase_configured(self) -> bool:
        return bool(os.getenv("SUPABASE_URL", "").strip()
                    and (os.getenv("SUPABASE_SECRET_KEY") or os.getenv("SUPABASE_SERVICE_ROLE_KEY") or "").strip())


class ConfigurationError(RuntimeError):
    pass


def load_settings(*, env_file: bool = True) -> Settings:
    if env_file:
        load_dotenv(ROOT / ".env")
    offline = _flag("VENDORFLOW_OFFLINE_MODE")
    if offline and os.getenv("SUPABASE_URL", "").strip():
        # Never mix a simulated store with a configured real project by accident.
        raise ConfigurationError("VENDORFLOW_OFFLINE_MODE cannot be combined with SUPABASE_URL.")
    password = os.getenv("ADMIN_PASSWORD", "")
    # Sessions are HMAC-signed. Prefer an explicit SESSION_SECRET; otherwise derive
    # a key bound to the admin password (changing it revokes all sessions), mixed
    # with a per-process random value when neither is set.
    session_secret = os.getenv("SESSION_SECRET", "").strip()
    if session_secret:
        key = hashlib.sha256(("vf-session:" + session_secret + ":" + password).encode()).digest()
    else:
        key = hashlib.sha256(b"vf-session:" + secrets.token_bytes(32) + password.encode()).digest()
    return Settings(
        offline_mode=offline,
        offline_extractor=os.getenv("VENDORFLOW_OFFLINE_EXTRACTOR", "labels").strip().lower(),
        admin_password=password,
        session_key=key,
        cookie_secure=_flag("COOKIE_SECURE", True),
        session_hours=int(os.getenv("ADMIN_SESSION_HOURS", "8")),
    )
