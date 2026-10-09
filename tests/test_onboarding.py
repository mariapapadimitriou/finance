"""Pearl's onboarding state: province, the Quebec waitlist, consents, and the
gate that keeps a bank from being linked before the required agreements."""

from __future__ import annotations

import re

import pytest

from app import create_app
from finance import auth, mailer, users

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
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append(text))
    return sent


@pytest.fixture()
def client(tmp_path, outbox):
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    c = a.test_client()
    c.post("/api/auth/code/start", json={"email": "alex@example.com",
                                         "first_name": "Alex", "create": True})
    code = re.search(r"\b(\d{6})\b", outbox[-1]).group(1)
    assert c.post("/api/auth/code/verify",
                  json={"email": "alex@example.com", "code": code}).status_code == 200
    c.app = a
    return c


def step(c, **body):
    return c.post("/api/onboarding", json=body)


def test_province_moves_on_and_quebec_waits(client):
    r = step(client, province="QC")
    assert r.get_json()["user"]["onboarding"]["step"] == "province"
    assert step(client, step="protect").status_code == 400
    r = step(client, waitlist=True)
    assert r.get_json()["user"]["onboarding"]["waitlist"] is True
    # Chose the wrong province: Ontario clears the waitlist and moves on.
    r = step(client, province="ON")
    ob = r.get_json()["user"]["onboarding"]
    assert ob["province"] == "ON" and ob["waitlist"] is False and ob["step"] == "protect"
    assert step(client, province="XX").status_code == 400


def test_consents_need_both_required_and_are_timestamped(client):
    step(client, province="ON")
    r = step(client, consents={"terms": True, "read_data": False})
    assert r.status_code == 400 and r.get_json()["missing"] == ["read_data"]
    r = step(client, consents={"terms": True, "read_data": True, "tips": True})
    ob = r.get_json()["user"]["onboarding"]
    assert ob["step"] == "bank"
    assert ob["consents"]["tips"]["value"] is True
    assert ob["consents"]["improve"]["value"] is False
    assert all("at" in v for v in ob["consents"].values())


def test_bank_linking_waits_for_consent(client):
    step(client, province="ON")
    r = client.post("/api/plaid/link-token")
    assert r.status_code == 403
    step(client, consents={"terms": True, "read_data": True})
    assert client.post("/api/plaid/link-token").status_code != 403


def test_cannot_skip_to_bank(client):
    step(client, province="ON")
    assert step(client, step="bank").status_code == 400
    assert step(client, step="consents").status_code == 200


def test_done_finishes_onboarding(client):
    step(client, province="BC")
    step(client, consents={"terms": True, "read_data": True})
    r = step(client, done=True)
    assert r.get_json()["user"]["onboarding"]["done"] is True
    me = client.get("/api/auth/status").get_json()["user"]
    assert me["onboarding"]["done"] is True


def test_onboarding_needs_sign_in(tmp_path):
    a = create_app(str(tmp_path / "ledger.db"))
    c = a.test_client()
    assert c.get("/api/onboarding").status_code == 401
    assert c.post("/api/onboarding", json={"province": "ON"}).status_code == 401


def test_migration_runs_once(tmp_path):
    a = create_app(str(tmp_path / "ledger.db"))
    base = a.config["STORE"]
    owner = users.by_username(base, "mariapapas")
    assert owner.onboarded_at is not None
    later = users.create_passwordless(base, "new@example.com", "New")
    users.ensure_table(base)                  # e.g. the next cold start
    assert users.by_id(base, later.id).onboarded_at is None
