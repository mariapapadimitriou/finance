"""Passkeys: the server half of adding one and signing in with it.

The signature checks themselves are py_webauthn's and are patched here; the
browser end runs for real in the Playwright walk with a virtual authenticator.
"""

from __future__ import annotations

import json
import re
from types import SimpleNamespace

import pytest

from app import create_app
from finance import auth, mailer, passkeys, users

OWNER_PW = "maria's password"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV,
                users.OWNER_USERNAME_ENV, users.OWNER_EMAIL_ENV, "SPENDIE_SECRET_KEY",
                "AWS_LAMBDA_FUNCTION_NAME", "SPENDIE_PUBLIC_URL",
                "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password(OWNER_PW))
    monkeypatch.setenv(mailer.USER_ENV, "pearl@gmail.com")
    monkeypatch.setenv(mailer.PASSWORD_ENV, "app password")


@pytest.fixture()
def app(tmp_path, monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append(text))
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    a.outbox = sent
    return a


@pytest.fixture()
def fake_webauthn(monkeypatch):
    seen = {}

    def reg(**kw):
        seen["reg"] = kw
        return SimpleNamespace(credential_id=b"cred-1", credential_public_key=b"pk",
                               sign_count=0)

    def authn(**kw):
        seen["auth"] = kw
        return SimpleNamespace(new_sign_count=kw["credential_current_sign_count"] + 1)

    monkeypatch.setattr(passkeys, "verify_registration_response", reg)
    monkeypatch.setattr(passkeys, "verify_authentication_response", authn)
    return seen


def signed_up(app):
    c = app.test_client()
    c.post("/api/auth/code/start", json={"email": "alex@example.com",
                                         "first_name": "Alex", "create": True})
    code = re.search(r"\b(\d{6})\b", app.outbox[-1]).group(1)
    c.post("/api/auth/code/verify", json={"email": "alex@example.com", "code": code})
    return c


def test_register_then_sign_in(app, fake_webauthn):
    c = signed_up(app)
    opts = c.post("/api/auth/passkey/register/options").get_json()
    assert opts["rp"] == {"id": "localhost", "name": "Pearl"}
    assert opts["user"]["name"] == "alex@example.com"
    assert opts["authenticatorSelection"]["residentKey"] == "required"

    r = c.post("/api/auth/passkey/register/verify",
               json={"id": "Y3JlZC0x", "response": {"transports": ["internal"]}})
    assert r.status_code == 200 and r.get_json()["user"]["passkeys"] == 1
    assert fake_webauthn["reg"]["expected_rp_id"] == "localhost"
    assert "http://localhost" in fake_webauthn["reg"]["expected_origin"]
    # The challenge is used once.
    assert c.post("/api/auth/passkey/register/verify", json={}).status_code == 400

    c.post("/api/auth/logout")
    other = app.test_client()
    opts = other.post("/api/auth/passkey/options").get_json()
    assert opts["rpId"] == "localhost" and opts.get("allowCredentials", []) == []
    r = other.post("/api/auth/passkey/verify", json={"id": "Y3JlZC0x"})
    assert r.status_code == 200 and r.get_json()["user"]["email"] == "alex@example.com"
    assert fake_webauthn["auth"]["credential_current_sign_count"] == 0
    stored = passkeys.for_user(app.config["STORE"], r.get_json()["user"]["id"])
    assert stored[0]["sign_count"] == 1 and json.loads(stored[0]["transports"]) == ["internal"]


def test_unknown_passkey_is_refused(app, fake_webauthn):
    c = app.test_client()
    c.post("/api/auth/passkey/options")
    r = c.post("/api/auth/passkey/verify", json={"id": "bm9wZQ"})
    assert r.status_code == 401
    assert c.get("/api/transactions?limit=1").status_code == 401


def test_bad_signature_is_refused(app, fake_webauthn, monkeypatch):
    c = signed_up(app)
    c.post("/api/auth/passkey/register/options")
    c.post("/api/auth/passkey/register/verify", json={"id": "Y3JlZC0x"})

    def boom(**kw):
        raise ValueError("bad signature")

    monkeypatch.setattr(passkeys, "verify_authentication_response", boom)
    other = app.test_client()
    other.post("/api/auth/passkey/options")
    assert other.post("/api/auth/passkey/verify",
                      json={"id": "Y3JlZC0x"}).status_code == 401


def test_verify_without_options_is_refused(app, fake_webauthn):
    c = app.test_client()
    assert c.post("/api/auth/passkey/verify", json={"id": "x"}).status_code == 400


def test_register_needs_sign_in(app):
    c = app.test_client()
    assert c.post("/api/auth/passkey/register/options").status_code == 401
