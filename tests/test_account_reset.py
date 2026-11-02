"""Reset (iPhone Profile, 2026-11-02): back to the start of onboarding — the
banks unlinked, everything Start over clears gone — while signing in stays."""

from __future__ import annotations

import pytest

from app import create_app
from finance import auth, plaid_link, secrets_box, users
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

OWNER_PW = "maria's password"


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_USERNAME_ENV, "SPENDIE_SECRET_KEY",
                "AWS_LAMBDA_FUNCTION_NAME", "SPENDIE_PUBLIC_URL", "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password(OWNER_PW))
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "maria@example.com")
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    revoked = []

    def unlink(store, item_id):
        revoked.append(item_id)
        store.delete_plaid_item(item_id)
        return True

    monkeypatch.setattr(plaid_link, "unlink", unlink)
    app = create_app(str(tmp_path / "reset.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.revoked = revoked
        c.st = app.config["STORE"]
        r = c.post("/api/auth/login", json={"username": "mariapapas", "password": OWNER_PW})
        assert r.get_json()["signed_in"] is True
        c.post("/api/onboarding", json={"done": True})
        c.st.add_plaid_item("item-1", "tok", "TD")
        c.st.note_account("chq", name="TD Chequing ••1111", item_id="item-1",
                          account_type="depository", subtype="checking")
        ingest(c.st, IngestResult([Transaction(
            date="2026-10-02", description="PAI", merchant="Pai", amount=45.0, category="Dining",
            account_id="chq", account_name="TD Chequing ••1111", source="plaid",
            raw={"account_type": "depository"})], "chq"))
        c.st.set_setting("home_income", "4300")
        yield c


def reset(c, confirm="reset"):
    return c.post("/api/account/reset", json={"confirm": confirm})


def test_needs_confirming(client):
    assert reset(client, confirm="").status_code == 400
    assert client.st.plaid_items() and client.st.all_transactions()


def test_back_to_onboarding_with_nothing_left(client):
    body = reset(client).get_json()
    assert body["ok"] and body["banks"] == 1
    assert body["user"]["onboarding"]["done"] is False
    assert client.revoked == ["item-1"]
    assert client.st.plaid_items() == []
    assert client.st.all_transactions() == []
    assert client.st.setting("home_income", "") == ""


def test_signing_in_stays(client):
    reset(client)
    status = client.get("/api/auth/status").get_json()
    assert status["signed_in"] is True
    assert status["user"]["email"] == "maria@example.com"
    assert status["user"]["onboarding"]["done"] is False


def test_needs_an_account(tmp_path, monkeypatch):
    monkeypatch.delenv("VERCEL", raising=False)
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV):
        monkeypatch.delenv(key, raising=False)
    app = create_app(str(tmp_path / "local.db"))
    app.config.update(TESTING=True)
    r = app.test_client().post("/api/account/reset", json={"confirm": "reset"})
    assert r.status_code == 400 and r.get_json()["no_account"]
