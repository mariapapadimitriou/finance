"""THL-114: sign-up with an email and a strong password, confirmed by an
emailed code; sign-in with them, and an email code on a device that isn't
trusted yet; a fifteen-minute reset that follows the same rules.

Mail is captured, never sent. The clock is moved by hand.
"""

from __future__ import annotations

import re

import pytest

from app import create_app
from finance import auth, mailer, passwords, signin_codes, users

OWNER_PW = "maria's password"
GOOD = "seashell harbour lantern"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV,
                users.OWNER_USERNAME_ENV, users.OWNER_EMAIL_ENV, "SPENDIE_SECRET_KEY",
                "AWS_LAMBDA_FUNCTION_NAME", "SPENDIE_PUBLIC_URL",
                "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password(OWNER_PW))
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "maria@example.com")


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setenv(mailer.USER_ENV, "pearl@gmail.com")
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


def sign_up(c, outbox, email="alex@example.com", password=GOOD):
    r = c.post("/api/auth/signup/start", json={"email": email, "password": password})
    assert r.status_code == 200, r.get_json()
    r = c.post("/api/auth/code/verify", json={"email": email, "code": code_in(outbox[-1])})
    assert r.get_json()["signed_in"] is True
    return r


def signed_in(c) -> bool:
    return c.get("/api/transactions?limit=1").status_code == 200


def login(c, email="alex@example.com", password=GOOD):
    return c.post("/api/auth/login", json={"email": email, "password": password,
                                           "two_step": "email"})


class TestRules:
    def test_twelve_characters(self):
        r = passwords.rules("short pass", "alex@example.com")
        assert not r["length"] and r["more"] == 2 and r["label"] == "Too short"
        assert passwords.rules(GOOD)["ok"]

    def test_common_ones_fail_however_long(self):
        for pw in ("password1234", "qwertyuiop12", "123456789012", "aaaaaaaaaaaaaa",
                   "Password!2024"):
            assert not passwords.rules(pw)["common"], pw

    def test_not_the_email(self):
        assert not passwords.rules("alex.example.com!", "alex@example.com")["email"]
        assert not passwords.rules("my-alex-is-long-enough", "alex@example.com")["email"]
        assert passwords.rules(GOOD, "alex@example.com")["email"]

    def test_no_symbol_or_number_rules(self):
        r = passwords.rules("correct horse battery")
        assert r["ok"] and r["segments"] >= 3

    def test_the_check_endpoint_says_the_same(self, app):
        r = app.test_client().post("/api/auth/password/check",
                                   json={"password": "alexwashere1", "email": "alex@example.com"})
        body = r.get_json()
        assert body["length"] and not body["email"] and not body["ok"]


class TestSignUp:
    def test_a_code_then_an_account_with_that_password(self, app, outbox):
        c = app.test_client()
        r = c.post("/api/auth/signup/start", json={"email": "Alex@Example.com", "password": GOOD})
        assert r.get_json()["sent_to"] == "alex@example.com"
        assert users.by_email(app.config["STORE"], "alex@example.com") is None
        sign_up(c, outbox)
        assert signed_in(c)
        user = users.by_email(app.config["STORE"], "alex@example.com")
        assert user.email_verified and auth.verify_password(GOOD, user.password_hash)

    def test_a_weak_password_sends_nothing(self, app, outbox):
        r = app.test_client().post("/api/auth/signup/start",
                                   json={"email": "alex@example.com", "password": "too short"})
        assert r.status_code == 400 and r.get_json()["weak"]
        assert outbox == []

    def test_an_email_already_in_use_says_so(self, app, outbox):
        c = app.test_client()
        sign_up(c, outbox)
        r = app.test_client().post("/api/auth/signup/start",
                                   json={"email": "alex@example.com", "password": GOOD})
        assert r.status_code == 409 and r.get_json()["taken"]


class TestEmailStepOnANewDevice:
    def test_the_device_she_signed_up_on_is_trusted(self, app, outbox):
        c = app.test_client()
        sign_up(c, outbox)
        c.post("/api/auth/logout")
        r = login(c).get_json()
        assert r["signed_in"] is True and "code_needed" not in r

    def test_a_new_device_needs_the_code(self, app, outbox):
        sign_up(app.test_client(), outbox)
        phone = app.test_client()
        r = login(phone).get_json()
        assert r["signed_in"] is False and r["code_needed"] and r["sent_to"] == "alex@example.com"
        assert not signed_in(phone)
        r = phone.post("/api/auth/login/code", json={"code": code_in(outbox[-1])})
        assert r.get_json()["signed_in"] is True and signed_in(phone)
        # Trusted from now on: no code the next time.
        phone.post("/api/auth/logout")
        assert login(phone).get_json()["signed_in"] is True

    def test_a_wrong_password_sends_no_code(self, app, outbox):
        sign_up(app.test_client(), outbox)
        sent = len(outbox)
        r = login(app.test_client(), password="not the password at all")
        assert r.status_code == 401 and r.get_json()["error"] == "That email and password don't match."
        assert len(outbox) == sent

    def test_wrong_codes_count_down_then_pause(self, app, outbox):
        sign_up(app.test_client(), outbox)
        phone = app.test_client()
        login(phone)
        good = code_in(outbox[-1])
        bad = "000000" if good != "000000" else "111111"
        lefts = [phone.post("/api/auth/login/code", json={"code": bad}).get_json().get("left")
                 for _ in range(signin_codes.TRIES - 1)]
        assert lefts == [4, 3, 2, 1]
        phone.post("/api/auth/login/code", json={"code": bad})
        r = phone.post("/api/auth/login/code", json={"code": good})
        assert r.status_code == 429 and r.get_json()["paused"]
        assert "Try again in" in r.get_json()["error"]

    def test_resend_sends_a_new_code(self, app, outbox, clock):
        sign_up(app.test_client(), outbox)
        phone = app.test_client()
        login(phone)
        first = code_in(outbox[-1])
        clock["now"] += signin_codes.RESEND_AFTER + 1
        r = phone.post("/api/auth/login/resend")
        assert r.status_code == 200
        assert phone.post("/api/auth/login/code", json={"code": first}).status_code == 400
        assert phone.post("/api/auth/login/code",
                          json={"code": code_in(outbox[-1])}).get_json()["signed_in"]

    def test_a_code_without_the_password_step_does_nothing(self, app, outbox):
        sign_up(app.test_client(), outbox)
        r = app.test_client().post("/api/auth/login/code", json={"code": "123456"})
        assert r.status_code == 400 and r.get_json()["expired"]

    def test_signing_out_with_forget_asks_again(self, app, outbox):
        c = app.test_client()
        sign_up(c, outbox)
        c.post("/api/auth/logout", json={"forget_device": True})
        assert login(c).get_json()["code_needed"]

    def test_the_web_keeps_its_own_flow(self, app):
        # Without two_step, sign-in by username and password is unchanged.
        r = app.test_client().post("/api/auth/login",
                                   json={"username": "mariapapas", "password": OWNER_PW})
        assert r.get_json()["signed_in"] is True


class TestReset:
    def _link(self, app, outbox, c):
        sign_up(c, outbox)
        c.post("/api/auth/forgot", json={"identifier": "alex@example.com"})
        mail = outbox[-1]
        assert "15 minutes" in mail["text"]
        return re.search(r"reset=([\w-]+)", mail["text"]).group(1)

    def test_fifteen_minutes(self, app, outbox, clock):
        c = app.test_client()
        token = self._link(app, outbox, c)
        clock["now"] += 15 * 60 + 1
        r = c.post("/api/auth/reset", json={"token": token, "password": "a brand new harbour"})
        assert r.status_code == 400

    def test_the_same_rules_and_a_failed_try_keeps_the_link(self, app, outbox):
        c = app.test_client()
        token = self._link(app, outbox, c)
        r = c.post("/api/auth/reset", json={"token": token, "password": "alex.example.com!"})
        assert r.status_code == 400
        r = c.post("/api/auth/reset", json={"token": token, "password": "a brand new harbour"})
        assert r.get_json()["signed_in"] is True

    def test_signs_out_other_devices(self, app, outbox):
        other = app.test_client()
        token = self._link(app, outbox, other)
        assert signed_in(other)
        app.test_client().post("/api/auth/reset",
                               json={"token": token, "password": "a brand new harbour"})
        assert not signed_in(other)
