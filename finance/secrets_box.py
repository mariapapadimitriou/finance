"""Encrypting the Plaid access tokens before they touch the database.

A Plaid access token is a standing credential: with it, anyone can read the
transaction history of the linked account until the item is revoked. Every
other value in this ledger is a fact about money already spent; this one is a
key, and it is the only thing here worth encrypting.

The point is separating two compromises that are otherwise one. The tokens live
in Postgres and the encryption key lives in the deployment's environment, so a
database dump — a leaked connection string, a backup left somewhere, a support
ticket with a snapshot attached — yields ciphertext and nothing else. Someone
would need both.

Fernet, from `cryptography`, does the actual work: AES-128-CBC with an
HMAC-SHA256 tag, which means a tampered token is rejected rather than decrypted
into something unpredictable.

The key comes from `SPENDIE_SECRET_KEY`. It is not derived from the password,
deliberately: changing your password should not make your linked banks
undecryptable, and a password is chosen by a human while this needs to be
random. If Plaid is configured and this is missing, linking refuses rather than
storing a bank credential in the clear.
"""

from __future__ import annotations

import base64
import hashlib
import os

KEY_ENV = "SPENDIE_SECRET_KEY"


class SecretsUnavailable(RuntimeError):
    """Raised when something needs to encrypt but no key is configured."""


def _fernet():
    key = os.environ.get(KEY_ENV, "").strip()
    if not key:
        raise SecretsUnavailable(
            f"{KEY_ENV} is not set. Generate one with "
            f"`python -m finance.secrets_box` and add it to the environment "
            f"before linking a bank account."
        )
    try:
        from cryptography.fernet import Fernet
    except ImportError as exc:  # pragma: no cover - dependency is declared
        raise SecretsUnavailable(
            "The `cryptography` package is required to store bank tokens."
        ) from exc

    # Accept either a real Fernet key or any sufficiently long passphrase,
    # because someone will paste the latter. A passphrase is stretched into a
    # valid key rather than rejected, and a Fernet key is used as-is so that
    # the documented `generate_key()` output works without translation.
    if len(key) == 44 and key.endswith("="):
        return Fernet(key.encode())
    if len(key) < 32:
        raise SecretsUnavailable(
            f"{KEY_ENV} is too short to be a key. Use at least 32 characters, "
            f"or generate one with `python -m finance.secrets_box`."
        )
    derived = hashlib.sha256(b"spendie.secretbox.v1|" + key.encode()).digest()
    return Fernet(base64.urlsafe_b64encode(derived))


def available() -> bool:
    try:
        _fernet()
        return True
    except SecretsUnavailable:
        return False


def encrypt(plaintext: str) -> str:
    return _fernet().encrypt(plaintext.encode()).decode()


def decrypt(ciphertext: str) -> str:
    return _fernet().decrypt(ciphertext.encode()).decode()


def generate_key() -> str:
    from cryptography.fernet import Fernet
    return Fernet.generate_key().decode()


if __name__ == "__main__":  # pragma: no cover
    print(generate_key())
