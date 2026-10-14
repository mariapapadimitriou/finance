"""Confirming a new device (Pearl THL-114 A-07, A-08) and recovery codes.

Each test client is its own browser: its own cookies, so its own device.
Mail is captured, never sent. The clock is moved by hand.
"""

from __future__ import annotations

import re

import pytest

from app import create_app
from finance import auth, devices, mailer, users

OWNER_PW = "maria's password"
IPHONE = ("Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 "
          "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1")
MAC_CHROME = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
              "(KHTML, like Gecko) Chrome/130.0.0.0 Safari/537.36")


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
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, **kw: sent.append(
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


EMAIL = "alex@example.com"


def browser(app, agent=MAC_CHROME):
    c = app.test_client()
    c.environ_base["HTTP_USER_AGENT"] = agent
    return c


def code_sign_in(c, outbox, create=False):
    c.post("/api/auth/code/start", json={"email": EMAIL, "first_name": "Alex", "create": create})
    code = re.search(r"\b(\d{6})\b", outbox[-1]["text"]).group(1)
    return c.post("/api/auth/code/verify", json={"email": EMAIL, "code": code}).get_json()


@pytest.fixture()
def phone(app, outbox):
    """Alex made the account on an iPhone, so it's her trusted device."""
    c = browser(app, IPHONE)
    assert code_sign_in(c, outbox, create=True)["signed_in"]
    return c


def signed_in(c) -> bool:
    return c.get("/api/auth/status").get_json()["signed_in"]


class TestWhenItAsks:
    def test_the_first_device_is_trusted_without_asking(self, app, phone, outbox):
        phone.post("/api/auth/logout")
        assert code_sign_in(phone, outbox)["signed_in"]

    def test_a_new_browser_has_to_confirm_it_is_her(self, app, phone, outbox):
        laptop = browser(app)
        body = code_sign_in(laptop, outbox)
        assert body["confirm_device"] and not body["signed_in"]
        assert body["choices"]["approve"]["label"] == "Safari on iPhone"
        assert body["choices"]["recovery"] is False
        assert not signed_in(laptop)
        assert laptop.get("/api/home").status_code == 401

    def test_an_old_password_sign_in_asks_too(self, app, outbox):
        owner_phone = browser(app, IPHONE)
        assert owner_phone.post("/api/auth/login", json={
            "username": "mariapapas", "password": OWNER_PW}).get_json()["signed_in"]
        laptop = browser(app)
        body = laptop.post("/api/auth/login", json={
            "username": "mariapapas", "password": OWNER_PW}).get_json()
        assert body["confirm_device"] and not signed_in(laptop)

    def test_no_other_trusted_device_means_nothing_to_ask(self, app, phone, outbox, clock):
        clock["now"] += (devices.TRUST_DAYS + 1) * 86400      # the phone, unused for a month
        laptop = browser(app)
        assert code_sign_in(laptop, outbox)["signed_in"]

    def test_a_device_in_use_stays_trusted(self, app, phone, outbox, clock):
        for _ in range(devices.TRUST_DAYS + 5):
            clock["now"] += 86400
            phone.get("/api/home")
        assert code_sign_in(browser(app), outbox).get("confirm_device")


class TestApprovingOnTheOtherDevice:
    def ask(self, app, outbox, near=None):
        laptop = browser(app)
        code_sign_in(laptop, outbox)
        headers = {"X-Vercel-IP-City": "Toronto", "X-Vercel-IP-Country-Region": "ON"} if near else {}
        r = laptop.post("/api/auth/device/ask", headers=headers).get_json()
        return laptop, r

    def test_the_phone_sees_who_is_asking(self, app, phone, outbox):
        _, r = self.ask(app, outbox, near=True)
        assert r["from"] == "Chrome on Mac" and r["near"] == "Toronto, ON"
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        assert waiting["label"] == "Chrome on Mac" and waiting["near"] == "Toronto, ON"

    def test_approve_signs_the_new_browser_in_and_trusts_it(self, app, phone, outbox):
        laptop, _ = self.ask(app, outbox)
        assert laptop.get("/api/auth/device/status").get_json()["state"] == "pending"
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        assert phone.post(f"/api/auth/approvals/{waiting['id']}",
                          json={"approve": True}).status_code == 200
        body = laptop.get("/api/auth/device/status").get_json()
        assert body["signed_in"] and body["user"]["email"] == EMAIL
        assert signed_in(laptop)
        # Collected once, and the laptop is trusted from now on.
        assert phone.get("/api/auth/approvals").get_json()["approvals"] == []
        laptop.post("/api/auth/logout")
        assert code_sign_in(laptop, outbox)["signed_in"]

    def test_this_wasnt_me_refuses_and_emails_a_notice(self, app, phone, outbox):
        laptop, _ = self.ask(app, outbox, near=True)
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        phone.post(f"/api/auth/approvals/{waiting['id']}", json={"approve": False})
        assert laptop.get("/api/auth/device/status").get_json()["state"] == "denied"
        assert not signed_in(laptop)
        notice = outbox[-1]
        assert notice["to"] == EMAIL and notice["subject"] == "Someone tried to sign in to Pearl"
        assert "Chrome on Mac, near Toronto, ON" in notice["text"]

    def test_it_times_out_after_five_minutes(self, app, phone, outbox, clock):
        laptop, _ = self.ask(app, outbox)
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        clock["now"] += devices.APPROVAL_TTL + 1
        assert laptop.get("/api/auth/device/status").get_json()["state"] == "expired"
        assert phone.get("/api/auth/approvals").get_json()["approvals"] == []
        assert phone.post(f"/api/auth/approvals/{waiting['id']}",
                          json={"approve": True}).status_code == 404

    def test_only_her_own_devices_can_answer(self, app, phone, outbox):
        self.ask(app, outbox)
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        stranger = browser(app)
        stranger.post("/api/auth/login", json={"username": "mariapapas", "password": OWNER_PW})
        assert stranger.post(f"/api/auth/approvals/{waiting['id']}",
                             json={"approve": True}).status_code == 404
        assert browser(app).post(f"/api/auth/approvals/{waiting['id']}",
                                 json={"approve": True}).status_code == 401

    def test_another_browser_cannot_collect_the_approval(self, app, phone, outbox):
        laptop, _ = self.ask(app, outbox)
        [waiting] = phone.get("/api/auth/approvals").get_json()["approvals"]
        phone.post(f"/api/auth/approvals/{waiting['id']}", json={"approve": True})
        other = browser(app)
        assert other.get("/api/auth/device/status").status_code == 400
        assert not signed_in(other)

    def test_back_forgets_the_waiting_sign_in(self, app, phone, outbox):
        laptop, _ = self.ask(app, outbox)
        laptop.post("/api/auth/device/cancel")
        r = laptop.get("/api/auth/device/status")
        assert r.status_code == 400 and r.get_json()["expired"]


class TestRecoveryCodes:
    def test_ten_codes_shown_once_and_counted(self, app, phone):
        r = phone.post("/api/auth/recovery-codes").get_json()
        assert len(r["codes"]) == 10 and len(set(r["codes"])) == 10
        assert all(re.fullmatch(r"[2-9A-HJ-NP-Z]{4}-[2-9A-HJ-NP-Z]{4}", c) for c in r["codes"])
        assert r["user"]["recovery_codes"] == 10
        assert phone.get("/api/auth/status").get_json()["user"]["recovery_codes"] == 10

    def test_a_code_signs_a_new_browser_in_once(self, app, phone, outbox):
        codes = phone.post("/api/auth/recovery-codes").get_json()["codes"]
        laptop = browser(app)
        assert code_sign_in(laptop, outbox)["choices"]["recovery"] is True
        typed = codes[0].lower().replace("-", " ")             # as copied from paper
        body = laptop.post("/api/auth/device/recovery", json={"code": typed}).get_json()
        assert body["signed_in"] and body["user"]["recovery_codes"] == 9
        tablet = browser(app, IPHONE.replace("iPhone", "iPad"))
        code_sign_in(tablet, outbox)
        r = tablet.post("/api/auth/device/recovery", json={"code": codes[0]})
        assert r.status_code == 400 and r.get_json()["left"] == 4

    def test_new_codes_retire_the_old(self, app, phone, outbox):
        old = phone.post("/api/auth/recovery-codes").get_json()["codes"]
        phone.post("/api/auth/recovery-codes")
        laptop = browser(app)
        code_sign_in(laptop, outbox)
        assert laptop.post("/api/auth/device/recovery", json={"code": old[0]}).status_code == 400

    def test_five_wrong_codes_and_she_signs_in_again(self, app, phone, outbox):
        phone.post("/api/auth/recovery-codes")
        laptop = browser(app)
        code_sign_in(laptop, outbox)
        for _ in range(4):
            assert laptop.post("/api/auth/device/recovery",
                               json={"code": "AAAA-AAAA"}).get_json()["wrong"]
        r = laptop.post("/api/auth/device/recovery", json={"code": "AAAA-AAAA"}).get_json()
        assert r["expired"]
        assert laptop.post("/api/auth/device/ask").get_json()["expired"]

    def test_a_waiting_sign_in_runs_out(self, app, phone, outbox, clock):
        laptop = browser(app)
        code_sign_in(laptop, outbox)
        clock["now"] += 11 * 60
        assert laptop.post("/api/auth/device/ask").status_code == 400


class TestNamesAndForgetting:
    def test_device_names(self):
        assert devices.label_from(IPHONE) == "Safari on iPhone"
        assert devices.label_from(MAC_CHROME) == "Chrome on Mac"
        assert devices.label_from("Mozilla/5.0 (Windows NT 10.0) Chrome/130 Safari/537 Edg/130") \
            == "Edge on Windows"
        assert devices.label_from("Mozilla/5.0 (Android 14) Firefox/131") == "Firefox on Android"
        assert devices.label_from("") == "A browser"

    def test_near_only_when_the_host_says(self):
        assert devices.near_from({"X-Vercel-IP-City": "Qu%C3%A9bec",
                                  "X-Vercel-IP-Country-Region": "QC"}) == "Québec, QC"
        assert devices.near_from({}) is None

    def test_deleting_the_account_forgets_its_devices(self, app, phone):
        base = app.config["STORE"]
        user = users.by_email(base, EMAIL)
        devices.make_recovery_codes(base, user.id)
        users.forget(base, user)
        with base.conn() as c:
            assert c.execute("SELECT COUNT(*) AS n FROM app_devices").fetchone()["n"] == 0
        assert devices.recovery_left(base, user.id) == 0

