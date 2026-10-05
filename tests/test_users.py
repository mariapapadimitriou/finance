"""Accounts: sign-up, sign-in, and every ledger kept to its own account.

Isolation is the test that matters most here. Each account must see its own
transactions and plan and nothing of anyone else's.
"""

from __future__ import annotations

import pytest

from app import create_app
from finance import auth, users


@pytest.fixture(autouse=True)
def _clean_env(monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV,
                users.OWNER_USERNAME_ENV, "VERCEL", "AWS_LAMBDA_FUNCTION_NAME",
                "SPENDIE_SECRET_KEY", "SPENDIE_SMTP_USER", "SPENDIE_SMTP_PASSWORD",
                "SPENDIE_OWNER_EMAIL"):
        monkeypatch.delenv(key, raising=False)


@pytest.fixture()
def app(tmp_path, monkeypatch):
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("maria's password"))
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    return a


def sign_in(app, username, password):
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return c


def sign_up(app, username, password="a long enough password"):
    c = app.test_client()
    r = c.post("/api/auth/signup", json={"username": username, "password": password})
    assert r.status_code == 200, r.get_json()
    return c


def add_charge(c, description, amount):
    r = c.post("/api/transactions", json={
        "date": "2026-10-02", "description": description, "amount": amount,
        "category": "Dining", "confirm": True})
    assert r.status_code == 200, r.get_json()


def descriptions(c):
    return {t["description"] for t in
            c.get("/api/transactions?limit=500").get_json()["transactions"]}


class TestTheOwner:
    def test_is_created_from_the_environment(self, app):
        base = app.config["STORE"]
        owner = users.by_username(base, "mariapapas")
        assert owner is not None and owner.owner
        assert users.count(base) == 1

    def test_the_username_can_be_set(self, tmp_path, monkeypatch):
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("pw-pw-pw-pw"))
        monkeypatch.setenv(users.OWNER_USERNAME_ENV, "Someone")
        a = create_app(str(tmp_path / "l.db"))
        assert users.by_username(a.config["STORE"], "someone").owner

    def test_keeps_the_ledger_that_was_already_there(self, app):
        base = app.config["STORE"]
        before = len(base.all_transactions())
        c = sign_in(app, "mariapapas", "maria's password")
        add_charge(c, "MARIAS CAFE", 4.5)
        assert len(base.all_transactions()) == before + 1

    def test_is_only_created_once(self, app, monkeypatch):
        monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("different"))
        users.bootstrap_owner(app.config["STORE"])
        assert users.count(app.config["STORE"]) == 1
        sign_in(app, "mariapapas", "maria's password")


class TestSignUp:
    def test_a_new_account_is_signed_in_and_starts_empty(self, app):
        c = sign_up(app, "sister")
        status = c.get("/api/auth/status").get_json()
        assert status["signed_in"] and status["user"]["username"] == "sister"
        assert descriptions(c) == set()

    def test_usernames_are_case_insensitive_and_unique(self, app):
        sign_up(app, "Sister")
        r = app.test_client().post("/api/auth/signup", json={
            "username": "sister", "password": "another long password"})
        assert r.status_code == 409
        sign_in(app, "SISTER", "a long enough password")

    @pytest.mark.parametrize("name", ["ab", "has space", "x" * 33, "émile", ""])
    def test_bad_usernames_are_refused(self, app, name):
        r = app.test_client().post("/api/auth/signup", json={
            "username": name, "password": "a long enough password"})
        assert r.status_code == 400

    def test_short_passwords_are_refused(self, app):
        r = app.test_client().post("/api/auth/signup", json={
            "username": "sister", "password": "short"})
        assert r.status_code == 400

    def test_nobody_can_sign_up_as_the_owner(self, app):
        r = app.test_client().post("/api/auth/signup", json={
            "username": "mariapapas", "password": "a long enough password"})
        assert r.status_code == 409


class TestEachLedgerIsPrivate:
    def test_transactions_stay_with_their_account(self, app):
        maria = sign_in(app, "mariapapas", "maria's password")
        sister = sign_up(app, "sister")
        add_charge(maria, "ONLY MARIA", 10)
        add_charge(sister, "ONLY SISTER", 20)
        assert "ONLY MARIA" in descriptions(maria)
        assert "ONLY SISTER" not in descriptions(maria)
        assert descriptions(sister) == {"ONLY SISTER"}

    def test_the_plan_stays_with_its_account(self, app):
        maria = sign_in(app, "mariapapas", "maria's password")
        sister = sign_up(app, "sister")
        maria.put("/api/plan/setup", json={"income": 5200, "savings": 1040})
        sister.put("/api/plan/setup", json={"income": 3000, "savings": 600})
        assert maria.get("/api/plan/setup").get_json()["income"] == 5200
        assert sister.get("/api/plan/setup").get_json()["income"] == 3000

    def test_a_third_account_sees_neither(self, app):
        add_charge(sign_up(app, "sister"), "ONLY SISTER", 20)
        assert descriptions(sign_up(app, "brother")) == set()


class TestSessions:
    def test_signing_out_closes_the_ledger(self, app):
        c = sign_up(app, "sister")
        c.post("/api/auth/logout")
        assert c.get("/api/transactions").status_code == 401

    def test_changing_a_password_signs_other_sessions_out(self, app):
        here = sign_up(app, "sister")
        elsewhere = sign_in(app, "sister", "a long enough password")
        r = here.post("/api/auth/password", json={
            "current": "a long enough password", "new": "a brand new password"})
        assert r.status_code == 200
        assert here.get("/api/transactions").status_code == 200
        assert elsewhere.get("/api/transactions").status_code == 401
        sign_in(app, "sister", "a brand new password")

    def test_the_current_password_is_checked(self, app):
        c = sign_up(app, "sister")
        r = c.post("/api/auth/password", json={"current": "wrong", "new": "whatever-long"})
        assert r.status_code == 400

    def test_a_session_for_a_removed_account_is_refused(self, app):
        c = sign_up(app, "sister")
        with app.config["STORE"].conn() as conn:
            conn.execute("DELETE FROM app_users WHERE username = ?", ("sister",))
        assert c.get("/api/transactions").status_code == 401


class TestRunningLocally:
    def test_with_no_accounts_there_is_no_prompt(self, tmp_path):
        a = create_app(str(tmp_path / "l.db"))
        assert a.test_client().get("/api/transactions").status_code == 200

    def test_the_first_local_sign_up_takes_the_existing_ledger(self, tmp_path):
        a = create_app(str(tmp_path / "l.db"))
        c = a.test_client()
        add_charge(c, "ALREADY HERE", 3)
        c.post("/api/auth/signup", json={"username": "meme", "password": "long enough pw"})
        assert users.by_username(a.config["STORE"], "meme").owner
        assert "ALREADY HERE" in descriptions(c)
        assert a.test_client().get("/api/transactions").status_code == 401
