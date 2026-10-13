"""Changing the sign-in email (Pearl S-02): a six-digit code to the new
address, the old one told once it's done. Mail is captured; the clock moves
by hand."""

from __future__ import annotations

import pytest

from finance import signin_codes, users
from tests.test_signin_codes import OWNER_PW, _env, app, clock, code_in, outbox  # noqa: F401


@pytest.fixture()
def c(app):  # noqa: F811
    client = app.test_client()
    r = client.post("/api/auth/login", json={"username": "mariapapas", "password": OWNER_PW})
    assert r.status_code == 200
    return client


def start(c, email):
    return c.post("/api/auth/email/start", json={"email": email})


def verify(c, code):
    return c.post("/api/auth/email/verify", json={"code": code})


def me(c):
    return c.get("/api/auth/status").get_json()["user"]


def test_needs_a_sign_in(app):  # noqa: F811
    anon = app.test_client()
    assert start(anon, "new@example.com").status_code == 401
    assert verify(anon, "123456").status_code == 401


def test_a_code_goes_to_the_new_address_and_the_old_one_is_told(c, outbox):  # noqa: F811
    r = start(c, "Maria.New@Example.com")
    body = r.get_json()
    assert r.status_code == 200 and body["sent_to"] == "maria.new@example.com"
    assert outbox[-1]["to"] == "maria.new@example.com"
    assert "sign-in email" in outbox[-1]["text"]
    # Nothing changes until the code is typed in.
    assert me(c)["email"] == "maria@example.com"

    r = verify(c, code_in(outbox[-1]))
    assert r.status_code == 200 and r.get_json()["user"]["email"] == "maria.new@example.com"
    assert me(c)["email"] == "maria.new@example.com" and me(c)["email_verified"]
    assert outbox[-1]["to"] == "maria@example.com"
    assert "maria.new@example.com" in outbox[-1]["text"]
    assert outbox[-1]["subject"] == "Your Pearl sign-in email changed"


def test_wrong_code_counts_down_then_expires(c, outbox):  # noqa: F811
    start(c, "new@example.com")
    good = code_in(outbox[-1])
    bad = "000000" if good != "000000" else "111111"
    r = verify(c, bad)
    assert r.status_code == 400 and r.get_json()["wrong"] and r.get_json()["left"] == 4
    for _ in range(3):
        verify(c, bad)
    r = verify(c, bad)
    assert r.status_code == 400 and r.get_json()["expired"]
    # Even the right code is dead now.
    assert verify(c, good).get_json().get("expired")
    assert me(c)["email"] == "maria@example.com"


def test_code_expires_after_ten_minutes(c, outbox, clock):  # noqa: F811
    start(c, "new@example.com")
    clock["now"] += signin_codes.TTL + 1
    r = verify(c, code_in(outbox[-1]))
    assert r.status_code == 400 and r.get_json()["expired"]
    assert me(c)["email"] == "maria@example.com"


def test_a_new_code_retires_the_old_and_resend_waits(c, outbox, clock):  # noqa: F811
    start(c, "new@example.com")
    first = code_in(outbox[-1])
    sent = len(outbox)
    r = start(c, "new@example.com")
    assert r.get_json()["resend_in"] > 0 and len(outbox) == sent
    clock["now"] += signin_codes.RESEND_AFTER + 1
    start(c, "new@example.com")
    second = code_in(outbox[-1])
    if first != second:
        assert verify(c, first).status_code == 400
    assert verify(c, second).status_code == 200


def test_too_many_codes_pause_it(c, outbox, clock):  # noqa: F811
    for _ in range(signin_codes.SENDS_PER_WINDOW):
        assert start(c, "new@example.com").status_code == 200
        clock["now"] += signin_codes.RESEND_AFTER + 1
    r = start(c, "new@example.com")
    assert r.status_code == 429 and r.get_json()["paused"]
    clock["now"] += signin_codes.WINDOW
    assert start(c, "new@example.com").status_code == 200


def test_an_address_another_account_uses(c, app, outbox):  # noqa: F811
    users.create_passwordless(app.config["STORE"], "sis@example.com", "Sis")
    r = start(c, "sis@example.com")
    assert r.status_code == 409


@pytest.mark.parametrize("email, status", [("not an email", 400),
                                           ("maria@example.com", 400)])
def test_bad_or_same_address(c, email, status):
    assert start(c, email).status_code == status


def test_sign_in_codes_are_not_affected(c, app, outbox):  # noqa: F811
    """A change code isn't a sign-in code, and doesn't hold one back."""
    start(c, "new@example.com")
    anon = app.test_client()
    r = anon.post("/api/auth/code/start", json={"email": "maria@example.com"})
    assert r.status_code == 200
    assert anon.post("/api/auth/code/verify", json={
        "email": "maria@example.com", "code": code_in(outbox[-1])}).status_code == 200
