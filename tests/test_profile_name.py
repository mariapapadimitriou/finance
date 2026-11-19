"""P-01n "Your name" (G5-Profile): her name changes from Profile on the
iPhone (POST /api/account/name). Her email stays as it is."""

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
    c.post("/api/auth/code/start", json={"email": "maya@example.com",
                                         "first_name": "Maya Park", "create": True})
    code = re.search(r"\b(\d{6})\b", outbox[-1]).group(1)
    assert c.post("/api/auth/code/verify",
                  json={"email": "maya@example.com", "code": code}).status_code == 200
    return c


def status_user(c):
    return c.get("/api/auth/status").get_json()["user"]


def test_changes_her_name_and_status_says_so(client):
    r = client.post("/api/account/name", json={"first_name": "  Maya   Lin "})
    assert r.status_code == 200
    assert r.get_json()["user"]["first_name"] == "Maya Lin"
    assert status_user(client)["first_name"] == "Maya Lin"
    # Undo on the toast is the same call with the old name.
    assert client.post("/api/account/name", json={"first_name": "Maya Park"}).status_code == 200
    assert status_user(client)["first_name"] == "Maya Park"


def test_email_and_onboarding_stay_as_they_were(client):
    before = status_user(client)
    client.post("/api/account/name", json={"first_name": "Maya Lin",
                                            "email": "other@example.com",
                                            "onboarding_step": "done"})
    after = status_user(client)
    assert after["email"] == before["email"] == "maya@example.com"
    assert after["onboarding"] == before["onboarding"]


@pytest.mark.parametrize("name", ["", "   ", None])
def test_an_empty_name_is_refused(client, name):
    r = client.post("/api/account/name", json={"first_name": name})
    assert r.status_code == 400
    assert status_user(client)["first_name"] == "Maya Park"


def test_a_long_name_is_cut_to_40(client):
    r = client.post("/api/account/name", json={"first_name": "A" * 60})
    assert r.get_json()["user"]["first_name"] == "A" * 40


def test_signed_out_cannot_change_it(tmp_path, outbox):
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    r = a.test_client().post("/api/account/name", json={"first_name": "Maya"})
    assert r.status_code == 401
