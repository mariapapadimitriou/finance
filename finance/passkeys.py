"""Passkeys: sign in with Face ID, Touch ID, Windows Hello or a device PIN.

A passkey is a key pair made by your device for this site. The private half
never leaves the device; Pearl keeps only the public half and a counter, so a
stolen database holds nothing anyone can sign in with.

Passkeys here are discoverable: signing in doesn't ask who you are first, the
browser offers the passkeys it has for this site and says which account the
chosen one belongs to. The challenge each ceremony signs is kept in the signed
session cookie, and is used once.
"""

from __future__ import annotations

import json
import secrets
from urllib.parse import urlparse

from webauthn import (generate_authentication_options, generate_registration_options,
                      options_to_json, verify_authentication_response,
                      verify_registration_response)
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url
from webauthn.helpers.structs import (AuthenticatorSelectionCriteria,
                                      PublicKeyCredentialDescriptor,
                                      ResidentKeyRequirement,
                                      UserVerificationRequirement)

from . import users

RP_NAME = "Pearl"

_TABLE = """
CREATE TABLE IF NOT EXISTS app_passkeys (
    id             INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id        INTEGER NOT NULL,
    credential_id  TEXT NOT NULL UNIQUE,
    public_key     TEXT NOT NULL,
    sign_count     INTEGER NOT NULL DEFAULT 0,
    transports     TEXT,
    created_at     REAL NOT NULL,
    last_used_at   REAL
);
"""


def ensure_table(base) -> None:
    with base.conn() as c:
        c.executescript(_TABLE)


def relying_party(host_url: str) -> tuple[str, str]:
    """(RP ID, origin) for the address the page was loaded from."""
    u = urlparse(host_url)
    return u.hostname or "localhost", f"{u.scheme}://{u.netloc}"


def for_user(base, user_id: int) -> list[dict]:
    with base.conn() as c:
        rows = c.execute("SELECT * FROM app_passkeys WHERE user_id = ? ORDER BY id",
                         (int(user_id),)).fetchall()
    return [dict(r) for r in rows]


def count(base, user_id: int) -> int:
    return len(for_user(base, user_id))


def _by_credential(base, credential_id: str) -> dict | None:
    with base.conn() as c:
        r = c.execute("SELECT * FROM app_passkeys WHERE credential_id = ?",
                      (credential_id,)).fetchone()
    return dict(r) if r else None


# ── Adding a passkey (signed in) ─────────────────────────────────────────────

def registration_options(base, user, rp_id: str) -> tuple[str, str]:
    """(options JSON for the browser, challenge to keep in the session)."""
    challenge = secrets.token_bytes(32)
    options = generate_registration_options(
        rp_id=rp_id, rp_name=RP_NAME,
        user_id=str(user.id).encode(),
        user_name=user.email or user.username,
        user_display_name=user.first_name or user.email or user.username,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            resident_key=ResidentKeyRequirement.REQUIRED,
            user_verification=UserVerificationRequirement.PREFERRED),
        exclude_credentials=[
            PublicKeyCredentialDescriptor(id=base64url_to_bytes(p["credential_id"]))
            for p in for_user(base, user.id)],
    )
    return options_to_json(options), bytes_to_base64url(challenge)


def register(base, user, credential: dict, challenge: str, rp_id: str,
             origins: list[str]) -> None:
    """Check the browser's answer and keep the new passkey. Raises on failure."""
    verified = verify_registration_response(
        credential=credential, expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=rp_id, expected_origin=origins)
    transports = (credential.get("response") or {}).get("transports") or []
    with base.conn() as c:
        c.execute(
            "INSERT INTO app_passkeys (user_id, credential_id, public_key, "
            "sign_count, transports, created_at) VALUES (?, ?, ?, ?, ?, ?)",
            (int(user.id), bytes_to_base64url(verified.credential_id),
             bytes_to_base64url(verified.credential_public_key),
             int(verified.sign_count), json.dumps(transports), users.now()))


# ── Signing in with one ──────────────────────────────────────────────────────

def authentication_options(rp_id: str) -> tuple[str, str]:
    challenge = secrets.token_bytes(32)
    options = generate_authentication_options(
        rp_id=rp_id, challenge=challenge,
        user_verification=UserVerificationRequirement.PREFERRED)
    return options_to_json(options), bytes_to_base64url(challenge)


def authenticate(base, credential: dict, challenge: str, rp_id: str,
                 origins: list[str]):
    """The account this passkey belongs to, or None. Raises if the signature
    doesn't check out."""
    stored = _by_credential(base, str(credential.get("id") or ""))
    if stored is None:
        return None
    verified = verify_authentication_response(
        credential=credential, expected_challenge=base64url_to_bytes(challenge),
        expected_rp_id=rp_id, expected_origin=origins,
        credential_public_key=base64url_to_bytes(stored["public_key"]),
        credential_current_sign_count=int(stored["sign_count"]))
    with base.conn() as c:
        c.execute("UPDATE app_passkeys SET sign_count = ?, last_used_at = ? WHERE id = ?",
                  (int(verified.new_sign_count), users.now(), stored["id"]))
    return users.by_id(base, stored["user_id"])
