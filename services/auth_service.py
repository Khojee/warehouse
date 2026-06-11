"""Stage 1 authentication for FlowCore.

Session-based auth on top of NiceGUI's per-browser user storage:
- bcrypt password hashing
- failed-attempt lockout (3 attempts -> 15 minute lock, stored in DB)
- 15 minute inactivity timeout
"""

from __future__ import annotations

import secrets
import time
from collections.abc import MutableMapping
from datetime import datetime, timedelta
from typing import Any

import bcrypt
from nicegui import app
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError

from database import DB_PATH, SessionLocal, engine
from models import Base, User


SESSION_KEY = "flowcore_auth"
SESSION_TIMEOUT_SECONDS = 15 * 60

LOCK_THRESHOLD = 3
LOCK_MINUTES = 15

INVALID_MESSAGE = "Invalid username or password."
LOCKED_MESSAGE = "Account temporarily locked. Try again later."

DEFAULT_ADMIN_USERNAME = "admin"
DEFAULT_ADMIN_PASSWORD = "admin123"
DEFAULT_ADMIN_FULL_NAME = "Admin"

# Used to equalize timing when the username does not exist.
_DUMMY_HASH = bcrypt.hashpw(b"flowcore-dummy-password", bcrypt.gensalt())


def hash_password(password: str) -> str:
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8"), password_hash.encode("utf-8"))
    except ValueError:
        return False


def get_storage_secret() -> str:
    """Stable per-installation secret for NiceGUI session storage."""
    path = DB_PATH.parent / ".storage_secret"
    if path.exists():
        secret = path.read_text(encoding="utf-8").strip()
        if secret:
            return secret
    path.parent.mkdir(parents=True, exist_ok=True)
    secret = secrets.token_hex(32)
    path.write_text(secret, encoding="utf-8")
    return secret


def ensure_users_table() -> None:
    """Create the users table if missing and seed the default admin account."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine, tables=[User.__table__])
    with SessionLocal.begin() as session:
        existing = session.scalar(select(User).limit(1))
        if existing is None:
            session.add(
                User(
                    username=DEFAULT_ADMIN_USERNAME,
                    password_hash=hash_password(DEFAULT_ADMIN_PASSWORD),
                    full_name=DEFAULT_ADMIN_FULL_NAME,
                    is_active=True,
                    failed_attempts=0,
                )
            )


# ------------------------------------------------------------------ sessions
# All helpers accept an optional storage mapping so they can also be used from
# background timers, where `app.storage.user` cannot resolve the request.

def _resolve_storage(storage: MutableMapping[str, Any] | None) -> MutableMapping[str, Any]:
    return app.storage.user if storage is None else storage


def login_session(user: User, storage: MutableMapping[str, Any] | None = None) -> None:
    _resolve_storage(storage)[SESSION_KEY] = {
        "user_id": user.id,
        "username": user.username,
        "full_name": user.full_name,
        "last_activity": time.time(),
    }


def logout_session(storage: MutableMapping[str, Any] | None = None) -> None:
    _resolve_storage(storage).pop(SESSION_KEY, None)


def current_user(storage: MutableMapping[str, Any] | None = None) -> dict[str, Any] | None:
    """Return the session data, expiring it after 15 minutes of inactivity."""
    storage = _resolve_storage(storage)
    data = storage.get(SESSION_KEY)
    if not isinstance(data, dict) or "user_id" not in data:
        return None
    try:
        last_activity = float(data.get("last_activity", 0))
    except (TypeError, ValueError):
        last_activity = 0.0
    if time.time() - last_activity > SESSION_TIMEOUT_SECONDS:
        logout_session(storage)
        return None
    return data


def touch_session(
    idle_seconds: float = 0.0,
    storage: MutableMapping[str, Any] | None = None,
) -> None:
    """Reset the inactivity timer (optionally back-dated by known idle time)."""
    storage = _resolve_storage(storage)
    data = storage.get(SESSION_KEY)
    if not isinstance(data, dict):
        return
    data = dict(data)
    data["last_activity"] = time.time() - max(idle_seconds, 0.0)
    storage[SESSION_KEY] = data


# -------------------------------------------------------------- authenticate

def authenticate(username: str, password: str) -> tuple[bool, str]:
    """Verify credentials, enforce lockout, and open a session on success.

    Returns (ok, message). Messages never reveal whether the username exists.
    """
    username = (username or "").strip()
    password = password or ""
    if not username or not password:
        return False, INVALID_MESSAGE

    try:
        with SessionLocal.begin() as session:
            user = session.scalar(select(User).where(User.username == username))
            now = datetime.utcnow()

            if user is None:
                bcrypt.checkpw(password.encode("utf-8"), _DUMMY_HASH)
                return False, INVALID_MESSAGE

            if user.locked_until is not None and user.locked_until > now:
                return False, LOCKED_MESSAGE

            password_ok = verify_password(password, user.password_hash)
            if not password_ok or not user.is_active:
                user.failed_attempts = (user.failed_attempts or 0) + 1
                if user.failed_attempts >= LOCK_THRESHOLD:
                    user.locked_until = now + timedelta(minutes=LOCK_MINUTES)
                    user.failed_attempts = 0
                    return False, LOCKED_MESSAGE
                return False, INVALID_MESSAGE

            user.failed_attempts = 0
            user.locked_until = None
            user.last_login = now
            login_session(user)
            return True, ""
    except SQLAlchemyError:
        return False, "Login failed. Please try again."
