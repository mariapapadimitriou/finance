"""Codes by email at sign-in, and a reset link for a forgotten password.

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


def code_in(mail) -> str:
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


def login(c, username="mariapapas", password=OWNER_PW):
    return c.post("/api/auth/login", json={"username": username, "password": password})


def signed_in(c) -> bool:
    return c.get("/api/transactions?limit=1").status_code == 200


class TestTheOwnersEmail:
    def test_comes_from_the_environment_unconfirmed(self, app):
        owner = users.by_username(app.config["STORE"], "mariapapas")
        assert owner.email == "maria@example.com"
        assert owner.email_verified is False


class TestSignInWithACode:
    def test_a_right_password_asks_for_a_code_and_opens_nothing(self, app, outbox):
        c = app.test_client()
        r = login(c).get_json()
        assert r["needs_code"] is True and r["sent_to"] == "m•••@example.com"
        assert len(outbox) == 1 and outbox[0]["to"] == "maria@example.com"
        assert not signed_in(c)

    def test_the_code_signs_in_and_confirms_the_email(self, app, outbox):
        c = app.test_client()
        login(c)
        r = c.post("/api/auth/verify", json={"code": code_in(outbox[0])})
        assert r.status_code == 200
        assert signed_in(c)
        assert users.by_username(app.config["STORE"], "mariapapas").email_verified

    def test_a_wrong_code_does_not(self, app, outbox):
        c = app.test_client()
        login(c)
        assert c.post("/api/auth/verify", json={"code": "000000"}).status_code == 400
        assert not signed_in(c)

    def test_five_misses_retire_the_code(self, app, outbox):
        c = app.test_client()
        login(c)
        right = code_in(outbox[0])
        wrong = "111111" if right != "111111" else "222222"
        for _ in range(users.MAX_ATTEMPTS):
            c.post("/api/auth/verify", json={"code": wrong})
        assert c.post("/api/auth/verify", json={"code": right}).status_code == 400

    def test_a_code_expires(self, app, outbox, clock):
        c = app.test_client()
        login(c)
        clock["now"] += users.CODE_TTL + 1
        r = c.post("/api/auth/verify", json={"code": code_in(outbox[0])})
        assert r.status_code == 400

    def test_a_new_code_waits_a_minute_and_retires_the_old(self, app, outbox, clock):
        c = app.test_client()
        login(c)
        assert c.post("/api/auth/resend").status_code == 429
        clock["now"] += users.RESEND_AFTER + 1
        assert c.post("/api/auth/resend").status_code == 200
        old, new = code_in(outbox[0]), code_in(outbox[1])
        if old != new:
            assert c.post("/api/auth/verify", json={"code": old}).status_code == 400
        assert c.post("/api/auth/verify", json={"code": new}).status_code == 200

    def test_a_wrong_password_sends_nothing(self, app, outbox):
        assert login(app.test_client(), password="nope").status_code == 401
        assert outbox == []


class TestATrustedDevice:
    def sign_in_with_code(self, app, outbox, c):
        login(c)
        c.post("/api/auth/verify", json={"code": code_in(outbox[-1])})

    def test_is_not_asked_again(self, app, outbox):
        c = app.test_client()
        self.sign_in_with_code(app, outbox, c)
        c.delete_cookie("session")
        r = login(c).get_json()
        assert r.get("signed_in") is True and "needs_code" not in r
        assert len(outbox) == 1

    def test_another_device_is(self, app, outbox):
        self.sign_in_with_code(app, outbox, app.test_client())
        assert login(app.test_client()).get_json()["needs_code"] is True

    def test_signing_out_forgets_the_device(self, app, outbox, clock):
        c = app.test_client()
        self.sign_in_with_code(app, outbox, c)
        c.post("/api/auth/logout")
        clock["now"] += 61
        assert login(c).get_json()["needs_code"] is True

    def test_a_new_password_forgets_every_device(self, app, outbox, clock):
        c = app.test_client()
        self.sign_in_with_code(app, outbox, c)
        c.post("/api/auth/password", json={"current": OWNER_PW,
                                           "new": "a whole new password"})
        c.delete_cookie("session")
        clock["now"] += 61
        assert login(c, password="a whole new password").get_json()["needs_code"]


class TestSignUp:
    def test_needs_an_email(self, app):
        r = app.test_client().post("/api/auth/signup", json={
            "username": "sister", "password": "a long enough password"})
        assert r.status_code == 400

    def test_confirms_the_email_with_a_code(self, app, outbox):
        c = app.test_client()
        r = c.post("/api/auth/signup", json={
            "username": "sister", "email": "sis@example.com",
            "password": "a long enough password"}).get_json()
        assert r["needs_code"] is True and outbox[-1]["to"] == "sis@example.com"
        assert not signed_in(c)
        c.post("/api/auth/verify", json={"code": code_in(outbox[-1])})
        assert signed_in(c)
        assert users.by_username(app.config["STORE"], "sister").email_verified

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
        elsewhere.post("/api/auth/verify", json={"code": code_in(outbox[-1])})
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
    def test_is_saved_only_after_the_new_address_answers(self, app, outbox):
        c = app.test_client()
        login(c)
        c.post("/api/auth/verify", json={"code": code_in(outbox[-1])})
        r = c.post("/api/auth/email", json={"email": "new@example.com"}).get_json()
        assert r["needs_code"] and outbox[-1]["to"] == "new@example.com"
        base = app.config["STORE"]
        assert users.by_username(base, "mariapapas").email == "maria@example.com"
        c.post("/api/auth/email/verify", json={"code": code_in(outbox[-1])})
        assert users.by_username(base, "mariapapas").email == "new@example.com"
        assert outbox[-1]["to"] == "maria@example.com", "the old address is told"


class TestWithoutEmailSetUp:
    def test_sign_in_is_password_only(self, tmp_path, monkeypatch):
        monkeypatch.delenv(mailer.USER_ENV, raising=False)
        monkeypatch.delenv(mailer.PASSWORD_ENV, raising=False)
        a = create_app(str(tmp_path / "l.db"))
        c = a.test_client()
        assert login(c).get_json()["signed_in"] is True
        assert signed_in(c)
        assert c.post("/api/auth/forgot", json={"identifier": "x"}).status_code == 503
