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
from dataclasses import dataclass

from . import auth

OWNER_USERNAME_ENV = "SPENDIE_OWNER_USERNAME"
OWNER_HASH_ENV = "SPENDIE_OWNER_PASSWORD_HASH"
DEFAULT_OWNER = "mariapapas"

USERNAME = re.compile(r"^[a-z0-9._-]{3,32}$")
MIN_PASSWORD = 10

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
"""


@dataclass(frozen=True)
class User:
    id: int
    username: str
    password_hash: str
    owner: bool

    @property
    def fingerprint(self) -> str:
        """Ties a session to the password it was opened with, so changing the
        password signs every other session out."""
        return hashlib.sha256(b"spendie.session-pw.v1|"
                              + self.password_hash.encode()).hexdigest()[:24]

    def public(self) -> dict:
        return {"id": self.id, "username": self.username}


def _row(r) -> User:
    return User(int(r["id"]), r["username"], r["password_hash"], bool(r["owner"]))


def ensure_table(base) -> None:
    with base.conn() as c:
        c.executescript(_TABLE)


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
    """Create the first account from the environment, if there are none."""
    ensure_table(base)
    if count(base) > 0:
        return None
    stored = owner_hash_from_env()
    if not stored:
        return None
    name = normalise(os.environ.get(OWNER_USERNAME_ENV) or DEFAULT_OWNER)
    return create(base, name, stored, owner=True)


def ledger_location(base_path: str, user: User) -> tuple[str, str]:
    """(SQLite path, Postgres schema) for this account's ledger."""
    if user.owner:
        return base_path, "public"
    root, ext = os.path.splitext(base_path)
    return f"{root}-u{user.id}{ext or '.db'}", f"u_{user.id}"
