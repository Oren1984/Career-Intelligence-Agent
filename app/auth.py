# app/auth.py
# Local single-owner authentication: bcrypt password hashes in config/users.yaml.

"""Local authentication for the single-owner application.

- Credentials live in a local YAML file (default ``config/users.yaml``,
  override with ``USERS_FILE``). It is git-ignored, excluded from the Docker
  build context and bind-mounted read-only into the container.
- Passwords are stored only as bcrypt hashes; plaintext is never written or
  logged. ``scripts/create_user.py`` manages the file.
- Each user maps to exactly one workspace (data boundary). There is no
  registration, role management or administrative account.
- Failed logins are throttled in process memory per username: after
  MAX_FAILURES failures within FAILURE_WINDOW the username is locked for
  LOCKOUT. This is basic protection for a local app (it resets on restart
  and is not shared between processes).
"""
from __future__ import annotations

import os
import re
import tempfile
import threading
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import bcrypt
import yaml

from app.workspace import REPO_ROOT, validate_workspace

USERNAME_RE = re.compile(r"^[a-z][a-z0-9_.-]{1,31}$")
MIN_PASSWORD_LENGTH = 8
MAX_PASSWORD_BYTES = 72          # bcrypt limit
DEFAULT_TIMEOUT_MINUTES = 60

MAX_FAILURES = 5
FAILURE_WINDOW = 15 * 60         # seconds
LOCKOUT = 5 * 60                 # seconds

# Used to spend comparable time on unknown usernames (no user-enumeration timing signal).
_DUMMY_HASH = bcrypt.hashpw(b"not-a-real-password", bcrypt.gensalt(rounds=12))


@dataclass(frozen=True)
class User:
    username: str
    workspace: str
    password_hash: str


class AuthError(ValueError):
    """Invalid username/password input for user management."""


def users_file() -> Path:
    return Path(os.environ.get("USERS_FILE", REPO_ROOT / "config" / "users.yaml"))


def _read(path: Path) -> dict:
    if not path.exists():
        return {}
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh) or {}


def load_users(path: Path | None = None) -> dict[str, User]:
    """Users from the credentials file; malformed entries are skipped."""
    data = _read(path or users_file())
    users: dict[str, User] = {}
    for name, entry in (data.get("users") or {}).items():
        try:
            if not USERNAME_RE.match(str(name)) or not isinstance(entry, dict):
                continue
            pw_hash = str(entry["password_hash"])
            if not pw_hash.startswith("$2"):
                continue
            users[name] = User(name, validate_workspace(entry["workspace"]), pw_hash)
        except Exception:
            continue
    return users


def session_timeout_minutes(path: Path | None = None) -> int:
    value = os.environ.get("SESSION_TIMEOUT_MINUTES") or _read(path or users_file()).get("session_timeout_minutes")
    try:
        minutes = int(value)
    except (TypeError, ValueError):
        return DEFAULT_TIMEOUT_MINUTES
    return max(1, minutes)


def validate_new_password(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AuthError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(password.encode("utf-8")) > MAX_PASSWORD_BYTES:
        raise AuthError(f"Password must be at most {MAX_PASSWORD_BYTES} bytes.")


def hash_password(password: str) -> str:
    validate_new_password(password)
    return bcrypt.hashpw(password.encode("utf-8"), bcrypt.gensalt(rounds=12)).decode("ascii")


def verify_password(password: str, password_hash: str) -> bool:
    try:
        return bcrypt.checkpw(password.encode("utf-8")[:MAX_PASSWORD_BYTES], password_hash.encode("ascii"))
    except Exception:
        return False


def upsert_user(username: str, workspace: str, password: str, path: Path | None = None) -> None:
    """Create or update a user (atomic write; other users and settings are preserved)."""
    if not USERNAME_RE.match(username):
        raise AuthError("Username must be 2–32 chars: lowercase letters, digits, '.', '_' or '-'.")
    validate_workspace(workspace)
    path = path or users_file()
    data = _read(path)
    data.setdefault("session_timeout_minutes", DEFAULT_TIMEOUT_MINUTES)
    users = data.get("users") or {}
    users[username] = {"workspace": workspace, "password_hash": hash_password(password)}
    data["users"] = users

    path.parent.mkdir(parents=True, exist_ok=True)
    header = "# Local credentials — managed by scripts/create_user.py. Never commit this file.\n"
    fd, tmp = tempfile.mkstemp(dir=path.parent, prefix=".users-", suffix=".yaml")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(header)
            yaml.safe_dump(data, fh, sort_keys=True, allow_unicode=True)
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


# ── Login throttling ─────────────────────────────────────────────────────────

class LoginThrottle:
    """In-memory failed-login tracking per username."""

    def __init__(self, max_failures: int = MAX_FAILURES, window: float = FAILURE_WINDOW,
                 lockout: float = LOCKOUT, clock=time.monotonic):
        self._max, self._window, self._lockout, self._clock = max_failures, window, lockout, clock
        self._failures: dict[str, list[float]] = {}
        self._locked_until: dict[str, float] = {}
        self._lock = threading.Lock()

    def locked_for(self, username: str) -> float:
        """Seconds remaining on a lockout (0 when not locked)."""
        with self._lock:
            return max(0.0, self._locked_until.get(username, 0.0) - self._clock())

    def record_failure(self, username: str) -> None:
        now = self._clock()
        with self._lock:
            recent = [t for t in self._failures.get(username, []) if now - t < self._window] + [now]
            if len(recent) >= self._max:
                self._locked_until[username] = now + self._lockout
                recent = []
            self._failures[username] = recent

    def record_success(self, username: str) -> None:
        with self._lock:
            self._failures.pop(username, None)
            self._locked_until.pop(username, None)


THROTTLE = LoginThrottle()


@dataclass(frozen=True)
class LoginResult:
    user: Optional[User]
    reason: str            # ok | invalid | locked | no_users
    retry_after: float = 0.0


def authenticate(username: str, password: str, users: dict[str, User] | None = None,
                 throttle: LoginThrottle = THROTTLE) -> LoginResult:
    """Check credentials with throttling. Error reasons never reveal whether a username exists."""
    username = (username or "").strip().lower()
    users = load_users() if users is None else users
    if not users:
        return LoginResult(None, "no_users")
    wait = throttle.locked_for(username)
    if wait > 0:
        return LoginResult(None, "locked", wait)
    user = users.get(username)
    ok = verify_password(password or "", user.password_hash if user else _DUMMY_HASH.decode("ascii"))
    if user is not None and ok:
        throttle.record_success(username)
        return LoginResult(user, "ok")
    throttle.record_failure(username)
    wait = throttle.locked_for(username)
    return LoginResult(None, "locked" if wait > 0 else "invalid", wait)
