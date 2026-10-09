"""Pearl's sign-up and sign-in by emailed code.

Mail is captured, never sent. The clock is moved by hand.
"""

from __future__ import annotations

import re

import pytest

from app import create_app
from finance import auth, mailer, signin_codes, users

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


def start(c, email, first_name=None, create=False):
    return c.post("/api/auth/code/start",
                  json={"email": email, "first_name": first_name, "create": create})


def test_signup_by_code_makes_a_passwordless_account(app, outbox, clock):
    c = app.test_client()
    assert start(c, "Alex@Example.com", "Alex", create=True).get_json()["ok"]
    assert outbox[-1]["to"] == "alex@example.com"
    assert "Your Pearl code" in outbox[-1]["subject"]
    # Nothing exists until the code is typed in.
    assert users.by_email(app.config["STORE"], "alex@example.com") is None

    r = c.post("/api/auth/code/verify",
               json={"email": "alex@example.com", "code": code_in(outbox[-1])})
    body = r.get_json()
    assert r.status_code == 200 and body["signed_in"] and body["created"]
    u = body["user"]
    assert u["first_name"] == "Alex" and u["email_verified"]
    assert u["has_password"] is False
    assert u["onboarding"] == {"done": False, "step": "province", "province": None,
                               "waitlist": False, "consents": {}}
    assert c.get("/api/auth/status").get_json()["user"]["email"] == "alex@example.com"


def test_existing_owner_is_already_onboarded_and_password_still_works(app):
    c = app.test_client()
    r = c.post("/api/auth/login", json={"username": "mariapapas", "password": OWNER_PW})
    assert r.status_code == 200
    me = c.get("/api/auth/status").get_json()["user"]
    assert me["onboarding"]["done"] is True and me["has_password"] is True


def test_owner_can_sign_in_by_code(app, outbox):
    c = app.test_client()
    start(c, "maria@example.com")
    assert "sign in to Pearl" in outbox[-1]["text"]
    r = c.post("/api/auth/code/verify",
               json={"email": "maria@example.com", "code": code_in(outbox[-1])})
    assert r.status_code == 200 and r.get_json()["created"] is False
    assert r.get_json()["user"]["username"] == "mariapapas"


def test_same_answer_for_known_and_unknown_addresses(app, outbox):
    c = app.test_client()
    known = start(c, "maria@example.com").get_json()
    unknown = start(c, "nobody@example.com").get_json()
    assert known.keys() == unknown.keys()
    # The stranger is told there's no account, and no code can sign them in.
    assert "no Pearl account" in outbox[-1]["text"]
    assert not re.search(r"\b\d{6}\b", outbox[-1]["text"])
    r = c.post("/api/auth/code/verify", json={"email": "nobody@example.com",
                                              "code": "123456"})
    assert r.status_code == 400
    assert users.by_email(app.config["STORE"], "nobody@example.com") is None


def test_wrong_code_counts_down_then_dies(app, outbox):
    c = app.test_client()
    start(c, "alex@example.com", "Alex", create=True)
    good = code_in(outbox[-1])
    bad = "000000" if good != "000000" else "111111"
    lefts = []
    for _ in range(signin_codes.TRIES - 1):
        r = c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                                  "code": bad})
        lefts.append(r.get_json()["left"])
    assert lefts == [4, 3, 2, 1]
    r = c.post("/api/auth/code/verify", json={"email": "alex@example.com", "code": bad})
    assert r.get_json().get("expired")
    # Even the right code is dead now.
    r = c.post("/api/auth/code/verify", json={"email": "alex@example.com", "code": good})
    assert r.get_json().get("expired")


def test_code_expires_after_ten_minutes(app, outbox, clock):
    c = app.test_client()
    start(c, "alex@example.com", "Alex", create=True)
    clock["now"] += signin_codes.TTL + 1
    r = c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                              "code": code_in(outbox[-1])})
    assert r.status_code == 400 and r.get_json()["expired"]


def test_new_code_replaces_old_and_resend_waits(app, outbox, clock):
    c = app.test_client()
    start(c, "alex@example.com", "Alex", create=True)
    first = code_in(outbox[-1])
    assert len(outbox) == 1
    start(c, "alex@example.com", "Alex", create=True)       # too soon: nothing sent
    assert len(outbox) == 1
    clock["now"] += signin_codes.RESEND_AFTER + 1
    start(c, "alex@example.com", "Alex", create=True)
    second = code_in(outbox[-1])
    if first != second:
        r = c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                                  "code": first})
        assert r.status_code == 400
    r = c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                              "code": second})
    assert r.status_code == 200


def test_too_many_codes_takes_a_short_break(app, outbox, clock):
    c = app.test_client()
    for _ in range(signin_codes.SENDS_PER_WINDOW):
        assert start(c, "alex@example.com", "Alex", create=True).status_code == 200
        clock["now"] += signin_codes.RESEND_AFTER + 1
    r = start(c, "alex@example.com", "Alex", create=True)
    assert r.status_code == 429 and r.get_json()["paused"]
    clock["now"] += signin_codes.WINDOW
    assert start(c, "alex@example.com", "Alex", create=True).status_code == 200


def test_sign_up_needs_a_first_name_and_mail(app, monkeypatch):
    c = app.test_client()
    assert start(c, "alex@example.com", "", create=True).status_code == 400
    monkeypatch.delenv(mailer.USER_ENV)
    r = start(c, "alex@example.com", "Alex", create=True)
    assert r.status_code == 503


def test_passwordless_hash_never_matches_a_password(app, outbox):
    c = app.test_client()
    start(c, "alex@example.com", "Alex", create=True)
    c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                          "code": code_in(outbox[-1])})
    u = users.by_email(app.config["STORE"], "alex@example.com")
    assert u.password_hash.startswith(users.NO_PASSWORD)
    for guess in ("", "none", u.password_hash, u.password_hash[5:]):
        assert users.authenticate(app.config["STORE"], u.username, guess) is None


def test_a_used_code_does_not_hold_back_the_next(app, outbox):
    c = app.test_client()
    start(c, "alex@example.com", "Alex", create=True)
    c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                          "code": code_in(outbox[-1])})
    c.post("/api/auth/logout")
    # Seconds later, signing back in sends a new code straight away.
    start(c, "alex@example.com")
    assert len(outbox) == 2 and "sign in to Pearl" in outbox[-1]["text"]
    r = c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                              "code": code_in(outbox[-1])})
    assert r.status_code == 200
