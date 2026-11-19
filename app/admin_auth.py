"""Admin accounts, password hashing, server-side sessions, login throttling and audit log.

No external dependencies: passwords use scrypt from the standard library; sessions live in PostgreSQL.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import re
import secrets
import time
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models import AdminAudit, AdminSession, AdminUser

MAX_ADMINS = 4  # Martin, Presiyan, Росица, Миглена (meeting 18 Nov); raise deliberately, not by accident
MIN_PASSWORD_LENGTH = 12
LOGIN_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{2,63}$")
SESSION_IDLE = timedelta(hours=2)
SESSION_MAX = timedelta(hours=12)
COOKIE_NAME = "mik_admin"

_N, _R, _P = 2**17, 8, 1  # scrypt cost (128 MiB, OWASP-recommended minimum for scrypt; ~0.4 s on a small server)
_MAXMEM = 256 * 1024 * 1024


class AdminError(ValueError):
    """A problem the operator should read (bad login name, weak password, too many admins...)."""


def _now() -> datetime:
    return datetime.now(timezone.utc)


def aware(dt: datetime) -> datetime:
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)  # SQLite drops tzinfo


# ---- passwords ------------------------------------------------------------------------------------------------

def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=_N, r=_R, p=_P, maxmem=_MAXMEM)
    b = lambda x: base64.b64encode(x).decode("ascii")  # noqa: E731
    return f"scrypt${_N}${_R}${_P}${b(salt)}${b(digest)}"


def verify_password(password: str, stored: str) -> bool:
    try:
        scheme, n, r, p, salt, digest = stored.split("$")
        if scheme != "scrypt":
            return False
        expected = base64.b64decode(digest)
        got = hashlib.scrypt(
            password.encode("utf-8"), salt=base64.b64decode(salt), n=int(n), r=int(r), p=int(p),
            maxmem=_MAXMEM, dklen=len(expected),
        )
        return hmac.compare_digest(got, expected)
    except Exception:  # malformed hash must never raise into the request
        return False


def needs_rehash(stored: str) -> bool:
    """True when a stored hash uses weaker cost parameters than the current ones (re-hashed at next good login)."""
    try:
        _, n, r, p, *_ = stored.split("$")
        return (int(n), int(r), int(p)) != (_N, _R, _P) and int(n) * int(r) < _N * _R
    except Exception:
        return False


# verified against when the login name does not exist, so unknown and known logins take the same time
DUMMY_HASH = hash_password(secrets.token_urlsafe(16))


def check_password_strength(password: str) -> None:
    if len(password) < MIN_PASSWORD_LENGTH:
        raise AdminError(f"Password must be at least {MIN_PASSWORD_LENGTH} characters.")
    if len(set(password)) < 5:
        raise AdminError("Password is too repetitive.")


# ---- accounts -------------------------------------------------------------------------------------------------

def normalise_login(login: str) -> str:
    login = (login or "").strip().lower()
    if not LOGIN_RE.match(login):
        raise AdminError("Login must be 3-64 characters: lowercase letters, digits, '.', '_' or '-'.")
    return login


def create_admin(db: Session, login: str, display_name: str, password: str, *, max_admins: int = MAX_ADMINS) -> AdminUser:
    login = normalise_login(login)
    display_name = (display_name or "").strip()
    if not display_name or len(display_name) > 120:
        raise AdminError("Display name is required (max 120 characters).")
    check_password_strength(password)
    if db.scalar(select(AdminUser).where(AdminUser.login == login)):
        raise AdminError("This login already exists.")
    active = db.scalar(select(func.count()).select_from(AdminUser).where(AdminUser.is_active.is_(True)))
    if active >= max_admins:
        raise AdminError(f"There are already {active} active admins (limit {max_admins}). Deactivate one first.")
    user = AdminUser(login=login, display_name=display_name, password_hash=hash_password(password), is_active=True)
    db.add(user)
    db.add(AdminAudit(user_id=None, action="admin_created", detail=f"login={login}"))
    db.commit()
    return user


def get_by_login(db: Session, login: str) -> AdminUser | None:
    return db.scalar(select(AdminUser).where(AdminUser.login == (login or "").strip().lower()))


def audit(db: Session, action: str, user_id: int | None = None, detail: str = "") -> None:
    db.add(AdminAudit(user_id=user_id, action=action, detail=detail[:255]))
    db.commit()


AUDIT_NOISE = ("login_failed", "login_throttled")


def purge_old_audit(db: Session, days: int = 90) -> int:
    """Delete failed/throttled sign-in rows older than `days` (they are noise, and unbounded otherwise)."""
    from sqlalchemy import delete
    cutoff = _now() - timedelta(days=days)
    n = db.execute(delete(AdminAudit).where(AdminAudit.action.in_(AUDIT_NOISE), AdminAudit.at < cutoff)).rowcount
    db.commit()
    return n or 0


# ---- sessions -------------------------------------------------------------------------------------------------

def _sid(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def start_session(db: Session, user: AdminUser) -> tuple[str, AdminSession]:
    token = secrets.token_urlsafe(32)
    now = _now()
    sess = AdminSession(
        id=_sid(token), user_id=user.id, csrf_token=secrets.token_urlsafe(24),
        created_at=now, last_seen_at=now, expires_at=now + SESSION_MAX,
    )
    db.add(sess)
    user.last_login_at = now
    # opportunistic cleanup of expired sessions
    for old in db.scalars(select(AdminSession).where(AdminSession.expires_at < now)):
        db.delete(old)
    db.commit()
    return token, sess


def load_session(db: Session, token: str | None) -> tuple[AdminUser, AdminSession] | None:
    if not token or len(token) > 128:
        return None
    sess = db.get(AdminSession, _sid(token))
    if sess is None:
        return None
    now = _now()
    user = db.get(AdminUser, sess.user_id)
    if (aware(sess.expires_at) <= now or aware(sess.last_seen_at) + SESSION_IDLE <= now
            or user is None or not user.is_active):
        db.delete(sess)
        db.commit()
        return None
    sess.last_seen_at = now
    db.commit()
    return user, sess


def end_session(db: Session, token: str | None) -> None:
    if not token or len(token) > 128:
        return
    sess = db.get(AdminSession, _sid(token))
    if sess:
        db.delete(sess)
        db.commit()


def end_all_sessions(db: Session, user_id: int) -> None:
    for s in db.scalars(select(AdminSession).where(AdminSession.user_id == user_id)):
        db.delete(s)
    db.commit()


# ---- login throttling (in memory: resets on restart; one worker) ------------------------------------------------

class LoginThrottle:
    """Lock a key for `lock_seconds` after `limit` failures within `window` seconds.

    Memory is bounded: expired entries are pruned and at most `max_keys` keys are tracked, so an attacker sending
    endless distinct login names cannot grow it without limit.
    """

    def __init__(self, limit: int = 5, window: int = 900, lock_seconds: int = 900, clock=time.monotonic,
                 max_keys: int = 10_000):
        self.limit, self.window, self.lock_seconds, self.clock = limit, window, lock_seconds, clock
        self.max_keys = max_keys
        self._fails: dict[str, list[float]] = {}
        self._locked: dict[str, float] = {}

    def locked_for(self, key: str) -> int:
        until = self._locked.get(key, 0.0)
        left = until - self.clock()
        if left <= 0:
            self._locked.pop(key, None)
            return 0
        return int(left) + 1

    def _prune(self, now: float) -> None:
        self._locked = {k: t for k, t in self._locked.items() if t > now}
        self._fails = {k: v for k, v in self._fails.items() if v and now - v[-1] < self.window}
        while len(self._fails) + len(self._locked) > self.max_keys and self._fails:
            self._fails.pop(next(iter(self._fails)))  # oldest-inserted failure counter first; locks are kept

    def failure(self, key: str) -> bool:
        """Record a failure. Returns True when this failure started a lock."""
        now = self.clock()
        if len(self._fails) + len(self._locked) >= self.max_keys:
            self._prune(now)
        recent = [t for t in self._fails.get(key, []) if now - t < self.window] + [now]
        self._fails[key] = recent
        if len(recent) >= self.limit:
            self._locked[key] = now + self.lock_seconds
            self._fails.pop(key, None)
            return True
        return False

    def success(self, key: str) -> None:
        self._fails.pop(key, None)
