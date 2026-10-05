"""Accounts: who can sign in, and which ledger is theirs.

Each account has its own ledger and sees nothing of anyone else's. Rather than
add an owner column to every table and every query, each ledger is a separate
namespace: a Postgres schema per account (`u_<id>`), or on SQLite a file per
account beside the original. The first account — the one that existed before
there were accounts — keeps the original namespace, so its data never moves.

The account list itself lives in that original database, in `app_users`.
Passwords are scrypt hashes (see `auth.hash_password`); nothing here ever holds
a password in the clear.

The first account is created from the environment the first time the app
starts with none: `SPENDIE_OWNER_USERNAME` (default "mariapapas") and
`SPENDIE_OWNER_PASSWORD_HASH`, or, failing that, the single shared password
the app used before (`SPENDIE_PASSWORD_HASH` / `SPENDIE_PASSWORD`). After that
the environment is not consulted; passwords change in the app.
"""

from __future__ import annotations

import hashlib
import os
import re
import secrets
import time
from dataclasses import dataclass

from . import auth

OWNER_USERNAME_ENV = "SPENDIE_OWNER_USERNAME"
OWNER_HASH_ENV = "SPENDIE_OWNER_PASSWORD_HASH"
OWNER_EMAIL_ENV = "SPENDIE_OWNER_EMAIL"
DEFAULT_OWNER = "mariapapas"

USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")
EMAIL = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")
MIN_PASSWORD = 10

# Emailed secrets. A sign-in code is short because it is typed; a reset link
# is long because it is clicked. Both are stored only as hashes.
CODE_TTL = 10 * 60
RESET_TTL = 30 * 60
MAX_ATTEMPTS = 5
RESEND_AFTER = 60
RESETS_PER_HOUR = 3

_TABLE = """
CREATE TABLE IF NOT EXISTS app_users (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    username      TEXT NOT NULL UNIQUE,
    password_hash TEXT NOT NULL,
    owner         INTEGER NOT NULL DEFAULT 0,
    created_at    TEXT DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS app_secrets (
    name  TEXT PRIMARY KEY,
    value TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS app_codes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    purpose     TEXT NOT NULL,
    secret_hash TEXT NOT NULL,
    payload     TEXT,
    expires_at  REAL NOT NULL,
    attempts    INTEGER NOT NULL DEFAULT 0,
    used        INTEGER NOT NULL DEFAULT 0,
    created_at  REAL NOT NULL
);
"""

# Added after accounts first shipped, so an existing table gains them.
_NEW_COLUMNS = (("email", "TEXT"), ("email_verified", "INTEGER NOT NULL DEFAULT 0"))


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    owner: bool
    email: str | None = None
    email_verified: bool = False

    @property
    def fingerprint(self) -> str:
        """Ties a session to the password it was opened with, so changing the
        password signs every other session out."""
        return hashlib.sha256(b"spendie.session-pw.v1|"
                              + self.password_hash.encode()).hexdigest()[:24]

    def public(self) -> dict:
        return {"id": self.id, "username": self.username,
                "email": self.email, "email_verified": self.email_verified}


def _row(r) -> User:
    return User(int(r["id"]), r["username"], r["password_hash"], bool(r["owner"]),
                r["email"] or None, bool(r["email_verified"]))


def ensure_table(base) -> None:
    with base.conn() as c:
        c.executescript(_TABLE)
    for name, kind in _NEW_COLUMNS:
        # One connection each: on Postgres a failed statement spoils the
        # transaction it is in, and "already exists" is the normal case.
        try:
            with base.conn() as c:
                c.execute(f"ALTER TABLE app_users ADD COLUMN {name} {kind}")
        except Exception:                              # noqa: BLE001
            pass
    with base.conn() as c:
        c.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_app_users_email "
                  "ON app_users (email)")


def count(base) -> int:
    with base.conn() as c:
        return int(c.execute("SELECT COUNT(*) AS n FROM app_users").fetchone()["n"])


def by_id(base, user_id) -> User | None:
    try:
        user_id = int(user_id)
    except (TypeError, ValueError):
        return None
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_users WHERE id = ?", (user_id,)).fetchone()
    return _row(r) if r else None


def by_username(base, username: str) -> User | None:
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_users WHERE username = ?",
                      (normalise(username),)).fetchone()
    return _row(r) if r else None


def normalise(username) -> str:
    return str(username or "").strip().lower()


def by_email(base, email: str) -> User | None:
    email = normalise(email)
    if not email:
        return None
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_users WHERE email = ?", (email,)).fetchone()
    return _row(r) if r else None


def by_identifier(base, identifier: str) -> User | None:
    """A username or an email, whichever was typed."""
    ident = normalise(identifier)
    return by_email(base, ident) if "@" in ident else by_username(base, ident)


def check_email(email: str) -> str | None:
    if not EMAIL.match(normalise(email)):
        return "That doesn't look like an email address."
    return None


def set_email(base, user_id: int, email: str | None, verified: bool = False) -> bool:
    """Set an account's email. False if another account already has it."""
    email = normalise(email) or None
    if email:
        other = by_email(base, email)
        if other is not None and other.id != int(user_id):
            return False
    with base.conn() as c:
        c.execute("UPDATE app_users SET email = ?, email_verified = ? WHERE id = ?",
                  (email, 1 if verified else 0, int(user_id)))
    return True


def mark_verified(base, user_id: int) -> None:
    with base.conn() as c:
        c.execute("UPDATE app_users SET email_verified = 1 WHERE id = ?", (int(user_id),))


# ── Emailed codes and links ──────────────────────────────────────────────────

def now() -> float:
    """The clock, kept in one place so tests can move it."""
    return time.time()


def _digest(secret: str) -> str:
    return hashlib.sha256(b"spendie.code.v1|" + secret.encode()).hexdigest()


def issue(base, user_id: int, purpose: str, payload: str | None = None) -> str | None:
    """Make a code (or a reset token) for this account and purpose.

    None when asked again too soon: one code a minute, three resets an hour.
    Issuing a new one retires any earlier one for the same purpose, so only
    the latest email works.
    """
    t = now()
    with base.conn() as c:
        rows = c.execute(
            "SELECT created_at FROM app_codes WHERE user_id = ? AND purpose = ? "
            "AND created_at > ? ORDER BY created_at DESC",
            (int(user_id), purpose, t - 3600)).fetchall()
        if purpose == "reset":
            if len(rows) >= RESETS_PER_HOUR:
                return None
        elif rows and t - float(rows[0]["created_at"]) < RESEND_AFTER:
            return None
        secret = (secrets.token_urlsafe(32) if purpose == "reset"
                  else f"{secrets.randbelow(10 ** 6):06d}")
        c.execute("UPDATE app_codes SET used = 1 WHERE user_id = ? AND purpose = ? "
                  "AND used = 0", (int(user_id), purpose))
        c.execute(
            "INSERT INTO app_codes (user_id, purpose, secret_hash, payload, "
            "expires_at, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (int(user_id), purpose, _digest(secret), payload,
             t + (RESET_TTL if purpose == "reset" else CODE_TTL), t))
    return secret


def redeem(base, user_id: int, purpose: str, code: str) -> tuple[bool, str | None]:
    """Check a typed code. (True, payload) once; every miss counts.

    Five misses retire the code, so guessing six digits is not a matter of
    patience.
    """
    code = "".join(ch for ch in str(code or "") if ch.isdigit())
    with base.conn() as c:
        r = c.execute(
            "SELECT * FROM app_codes WHERE user_id = ? AND purpose = ? AND used = 0 "
            "ORDER BY created_at DESC", (int(user_id), purpose)).fetchone()
        if r is None or float(r["expires_at"]) < now():
            return False, None
        if code and _digest(code) == r["secret_hash"]:
            c.execute("UPDATE app_codes SET used = 1 WHERE id = ?", (r["id"],))
            return True, r["payload"]
        attempts = int(r["attempts"]) + 1
        c.execute("UPDATE app_codes SET attempts = ?, used = ? WHERE id = ?",
                  (attempts, 1 if attempts >= MAX_ATTEMPTS else 0, r["id"]))
    return False, None


def redeem_reset(base, token: str) -> User | None:
    """The account a reset link belongs to, using the link up. None if the
    link is unknown, used, or expired."""
    if not token:
        return None
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_codes WHERE purpose = 'reset' AND "
                      "secret_hash = ? AND used = 0", (_digest(str(token)),)).fetchone()
        if r is None or float(r["expires_at"]) < now():
            return None
        c.execute("UPDATE app_codes SET used = 1 WHERE id = ?", (r["id"],))
    return by_id(base, r["user_id"])


def check_new(username: str, password: str) -> str | None:
    """What is wrong with a proposed account, in words, or None."""
    if not USERNAME.match(username):
        return ("Usernames are 3 to 32 characters: letters, numbers, "
                "dots, dashes and underscores.")
    if len(password or "") < MIN_PASSWORD:
        return f"Passwords need at least {MIN_PASSWORD} characters."
    return None


def create(base, username: str, password_hash: str, owner: bool = False) -> User | None:
    """Add an account. None if the username is already taken."""
    username = normalise(username)
    with base.conn() as c:
        c.execute("INSERT OR IGNORE INTO app_users (username, password_hash, owner) "
                  "VALUES (?, ?, ?)", (username, password_hash, 1 if owner else 0))
        r = c.execute("SELECT * FROM app_users WHERE username = ?",
                      (username,)).fetchone()
    user = _row(r) if r else None
    if user is None or user.password_hash != password_hash:
        return None                      # someone already had that name
    return user


def set_password(base, user_id: int, password_hash: str) -> None:
    with base.conn() as c:
        c.execute("UPDATE app_users SET password_hash = ? WHERE id = ?",
                  (password_hash, int(user_id)))


def authenticate(base, username: str, password: str) -> User | None:
    user = by_username(base, username)
    if user is None:
        # Spend the same time as a real check, so a missing username can't be
        # told apart from a wrong password by how long the answer takes.
        auth.verify_password(password, _DUMMY)
        return None
    return user if auth.verify_password(password, user.password_hash) else None


_DUMMY = auth.hash_password("spendie-no-such-user", salt=b"\0" * 16)


def stored_secret(base, name: str) -> str:
    """A random secret kept in the database, the same for every instance.

    Used for the session key when the environment provides none: every
    serverless instance reads the same row, so a session signed by one is
    accepted by the next.
    """
    import secrets
    with base.conn() as c:
        c.execute("INSERT OR IGNORE INTO app_secrets (name, value) VALUES (?, ?)",
                  (name, secrets.token_hex(32)))
        return c.execute("SELECT value FROM app_secrets WHERE name = ?",
                         (name,)).fetchone()["value"]


def owner_hash_from_env() -> str | None:
    stored = os.environ.get(OWNER_HASH_ENV, "").strip()
    return stored or auth.configured_hash()


def bootstrap_owner(base) -> User | None:
    """Create the first account from the environment, if there are none.

    Also gives the owner the email in SPENDIE_OWNER_EMAIL while they have
    none, so codes have somewhere to go; the first code confirms it.
    """
    ensure_table(base)
    if count(base) > 0:
        _owner_email(base)
        return None
    stored = owner_hash_from_env()
    if not stored:
        return None
    name = normalise(os.environ.get(OWNER_USERNAME_ENV) or DEFAULT_OWNER)
    user = create(base, name, stored, owner=True)
    _owner_email(base)
    return by_id(base, user.id) if user else None


def _owner_email(base) -> None:
    email = normalise(os.environ.get(OWNER_EMAIL_ENV))
    if not email or check_email(email):
        return
    with base.conn() as c:
        r = c.execute("SELECT id, email FROM app_users WHERE owner = 1 "
                      "ORDER BY id").fetchone()
    if r is not None and not r["email"]:
        set_email(base, r["id"], email)


def ledger_location(base_path: str, user: User) -> tuple[str, str]:
    """(SQLite path, Postgres schema) for this account's ledger."""
    if user.owner:
        return base_path, "public"
    root, ext = os.path.splitext(base_path)
    return f"{root}-u{user.id}{ext or '.db'}", f"u_{user.id}"
