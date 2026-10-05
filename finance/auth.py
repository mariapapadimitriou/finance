"""Password hashing, and the gate in front of the whole app.

The ledger was public by choice while it held nothing but transactions. A Plaid
access token is a different thing: it is a live credential to a bank account,
and an endpoint that uses it must not be something a stranger can reach. So
everything sits behind a sign-in — the UI, every API route, and in particular
the ones that link, sync or delete.

There are accounts now, each with a ledger of its own; see finance/users.py.
This module keeps the hashing and the single-password settings the first
account is created from.

Three decisions worth stating:

*Fail closed when hosted.* With no password configured, a deployment refuses
every request rather than serving an open app. Forgetting to set the variable
is the likely mistake, and it must not be the one that quietly leaves a bank
connection exposed. Running locally is unaffected: no password set means no
password asked for, because the alternative is a login prompt in front of a
SQLite file on your own laptop.

*The session key is derived, not configured.* A signed cookie needs a stable
secret, and a serverless instance that invented its own would log you out
whenever a different instance answered. Rather than ask for a second
environment variable that must never drift, it is derived from the password
hash — stable across instances, secret because the hash is, and it changes when
you change your password, which correctly signs every existing session out.

*Failure is slow by construction.* There is no attempt counter, because
counting in memory means counting per instance and forgetting on recycle.
Instead the hash is scrypt with a cost that takes real time per guess, which is
the same defence without the state.
"""

from __future__ import annotations

import hashlib
import hmac
import os
import secrets

# Tuned so one verification takes roughly a tenth of a second: slow enough that
# guessing at scale is hopeless, fast enough that logging in feels instant.
#
# maxmem is passed explicitly because OpenSSL defaults it to 32 MiB and these
# parameters need exactly 128 * N * r = 32 MiB — landing a hair over the limit
# and raising "memory limit exceeded" rather than hashing anything.
_N, _R, _P = 2 ** 15, 8, 1
_DKLEN = 32
_MAXMEM = 96 * 1024 * 1024

PASSWORD_ENV = "SPENDIE_PASSWORD"
HASH_ENV = "SPENDIE_PASSWORD_HASH"
COOKIE = "spendie_session"


def hash_password(password: str, salt: bytes | None = None) -> str:
    """Hash a password into the `scrypt$salt$key` form stored in the env."""
    salt = salt or secrets.token_bytes(16)
    key = hashlib.scrypt(password.encode(), salt=salt, n=_N, r=_R, p=_P,
                         dklen=_DKLEN, maxmem=_MAXMEM)
    return f"scrypt${salt.hex()}${key.hex()}"


def _env_salt(password: str) -> bytes:
    """A salt fixed by the password, so every instance derives the same hash."""
    return hashlib.sha256(b"spendie.env-salt.v1|" + password.encode()).digest()[:16]


def verify_password(password: str, stored: str) -> bool:
    """Check a password against a stored hash, in constant time."""
    try:
        scheme, salt_hex, key_hex = stored.split("$")
        if scheme != "scrypt":
            return False
        key = hashlib.scrypt(password.encode(), salt=bytes.fromhex(salt_hex),
                             n=_N, r=_R, p=_P, dklen=_DKLEN, maxmem=_MAXMEM)
    except (ValueError, TypeError):
        return False
    return hmac.compare_digest(key.hex(), key_hex)


def configured_hash() -> str | None:
    """The password hash this instance checks against, if one is set.

    A pre-computed hash is preferred, so the password itself need never be
    stored anywhere. Setting the plain password is allowed because it is what
    someone will reach for first, and refusing it would just push them to skip
    the password entirely — but it costs a hash on every cold start, and the
    setup docs say to use the hash.
    """
    stored = os.environ.get(HASH_ENV, "").strip()
    if stored:
        return stored
    plain = os.environ.get(PASSWORD_ENV, "").strip()
    if plain:
        # The salt is derived from the password rather than drawn at random,
        # and that is load-bearing: the session signing key comes from this
        # hash, so a per-boot salt gives every serverless instance a different
        # key. Signing in then succeeds on the instance that answered the login
        # and fails on the next one, which reads to the person as a password
        # screen that will not go away.
        #
        # A deterministic salt is weaker in the abstract — it cannot frustrate
        # a precomputed table. It costs nothing here, because this hash is
        # computed in memory from an environment variable and never stored,
        # logged or transmitted; anyone who can read it can already read the
        # password sitting next to it.
        return hash_password(plain, salt=_env_salt(plain))
    return None


def session_secret(password_hash: str) -> bytes:
    """A stable signing key derived from the password hash.

    Domain-separated so the value can never be confused with the hash itself,
    and so a leaked cookie signature says nothing about the password.
    """
    return hashlib.sha256(b"spendie.session.v1|" + password_hash.encode()).digest()


def required(hosted: bool) -> bool:
    """Whether this instance must ask for a password.

    Hosted: always. A deployment with no password set does not serve an open
    app; it serves an error telling you to set one.
    Local: only if you configured one.
    """
    return hosted or configured_hash() is not None
