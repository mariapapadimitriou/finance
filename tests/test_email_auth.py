"""A reset link by email for a forgotten password — the only email sent.

Mail is captured, never sent: `mailer.send` is replaced with a list.
"""

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
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "Maria@Example.com")


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setenv(mailer.USER_ENV, "spendie@gmail.com")
    monkeypatch.setenv(mailer.PASSWORD_ENV, "app password")
    monkeypatch.setattr(mailer, "send", lambda to, subject, text: sent.append(
        {"to": to, "subject": subject, "text": text}))
    return sent


@pytest.fixture()
def clock(monkeypatch):
    t = {"now": 1_800_000_000.0}
    monkeypatch.setattr(users, "now", lambda: t["now"])
    return t


@pytest.fixture()
def app(tmp_path, outbox, clock):
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    return a


def login(c, username="mariapapas", password=OWNER_PW):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def signed_in(c) -> bool:
    return c.get("/api/transactions?limit=1").status_code == 200


class TestSignInIsJustAPassword:
    def test_no_code_is_sent(self, app, outbox):
        c = app.test_client()
        r = login(c).get_json()
        assert r["signed_in"] is True and "needs_code" not in r
        assert signed_in(c)
        assert outbox == []

    def test_the_owners_email_comes_from_the_environment(self, app):
        owner = users.by_username(app.config["STORE"], "mariapapas")
        assert owner.email == "maria@example.com"


class TestSignUp:
    def test_needs_an_email(self, app):
        r = app.test_client().post("/api/auth/signup", json={
            "username": "sister", "password": "a long enough password"})
        assert r.status_code == 400

    def test_signs_straight_in_and_keeps_the_email(self, app, outbox):
        c = app.test_client()
        r = c.post("/api/auth/signup", json={
            "username": "sister", "email": "Sis@Example.com",
            "password": "a long enough password"}).get_json()
        assert r["signed_in"] is True and signed_in(c)
        assert users.by_username(app.config["STORE"], "sister").email == "sis@example.com"
        assert outbox == []

    def test_one_email_one_account(self, app):
        r = app.test_client().post("/api/auth/signup", json={
            "username": "sister", "email": "MARIA@example.com",
            "password": "a long enough password"})
        assert r.status_code == 409


class TestForgottenPassword:
    def link_token(self, mail) -> str:
        return re.search(r"\?reset=([\w-]+)", mail["text"]).group(1)

    def test_the_answer_never_says_whether_an_account_exists(self, app, outbox):
        c = app.test_client()
        a = c.post("/api/auth/forgot", json={"identifier": "nobody"}).get_json()
        b = c.post("/api/auth/forgot", json={"identifier": "mariapapas"}).get_json()
        assert a == b
        assert len(outbox) == 1 and outbox[0]["to"] == "maria@example.com"

    def test_works_by_email_too(self, app, outbox):
        app.test_client().post("/api/auth/forgot", json={"identifier": "maria@example.com"})
        assert len(outbox) == 1

    def test_the_link_sets_a_new_password_once(self, app, outbox):
        elsewhere = app.test_client()
        login(elsewhere)
        assert signed_in(elsewhere)

        c = app.test_client()
        c.post("/api/auth/forgot", json={"identifier": "mariapapas"})
        token = self.link_token(outbox[-1])
        r = c.post("/api/auth/reset", json={"token": token, "password": "brand new password"})
        assert r.status_code == 200 and signed_in(c)
        assert not signed_in(elsewhere), "a reset signs every other session out"
        assert c.post("/api/auth/reset", json={
            "token": token, "password": "another new password"}).status_code == 400
        assert login(app.test_client(), password="brand new password").status_code == 200

    def test_the_link_expires(self, app, outbox, clock):
        c = app.test_client()
        c.post("/api/auth/forgot", json={"identifier": "mariapapas"})
        clock["now"] += users.RESET_TTL + 1
        r = c.post("/api/auth/reset", json={"token": self.link_token(outbox[-1]),
                                            "password": "brand new password"})
        assert r.status_code == 400

    def test_three_an_hour_at_most(self, app, outbox):
        c = app.test_client()
        for _ in range(5):
            c.post("/api/auth/forgot", json={"identifier": "mariapapas"})
        assert len(outbox) == users.RESETS_PER_HOUR

    def test_the_link_uses_the_deployments_own_address(self, app, outbox, monkeypatch):
        monkeypatch.setenv("SPENDIE_PUBLIC_URL", "https://spendie.example")
        app.test_client().post("/api/auth/forgot", json={"identifier": "mariapapas"},
                               headers={"Host": "evil.example"})
        assert "https://spendie.example/?reset=" in outbox[-1]["text"]


class TestChangingEmail:
    def test_is_saved_and_the_old_address_is_told(self, app, outbox):
        c = app.test_client()
        login(c)
        r = c.post("/api/auth/email", json={"email": "new@example.com"})
        assert r.status_code == 200
        assert users.by_username(app.config["STORE"], "mariapapas").email == "new@example.com"
        assert [m["to"] for m in outbox] == ["maria@example.com"]

    def test_a_reset_goes_to_the_new_address(self, app, outbox):
        c = app.test_client()
        login(c)
        c.post("/api/auth/email", json={"email": "new@example.com"})
        app.test_client().post("/api/auth/forgot", json={"identifier": "mariapapas"})
        assert outbox[-1]["to"] == "new@example.com"

    def test_two_accounts_cannot_share_one(self, app):
        app.test_client().post("/api/auth/signup", json={
            "username": "sister", "email": "sis@example.com",
            "password": "a long enough password"})
        c = app.test_client()
        login(c)
        assert c.post("/api/auth/email", json={"email": "sis@example.com"}).status_code == 409


class TestWithoutEmailSetUp:
    def test_forgot_says_so(self, tmp_path, monkeypatch):
        monkeypatch.delenv(mailer.USER_ENV, raising=False)
        monkeypatch.delenv(mailer.PASSWORD_ENV, raising=False)
        a = create_app(str(tmp_path / "l.db"))
        c = a.test_client()
        assert login(c).get_json()["signed_in"] is True
        assert signed_in(c)
        assert c.post("/api/auth/forgot", json={"identifier": "x"}).status_code == 503
