"""Profile › Privacy (THL-115, THL-116, THL-117, THL-139): consents and their
log, notification preferences, the data download, the welcome email, and
deleting an account — which must remove everything of hers and nothing of
anyone else's.

Mail is captured, never sent; Plaid is a stand-in that records what it was
asked to revoke.
"""

from __future__ import annotations

import io
import json
import os
import re
import zipfile

import pytest

from app import create_app
from finance import auth, emails, mailer, plaid_link, secrets_box, users
from finance.models import Transaction

OWNER_PW = "maria's password"


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV,
                users.OWNER_USERNAME_ENV, users.OWNER_EMAIL_ENV,
                "AWS_LAMBDA_FUNCTION_NAME", "SPENDIE_PUBLIC_URL", mailer.SUPPORT_ENV,
                mailer.FROM_ENV, "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SPENDIE_PUBLIC_URL", "https://pearl.example")
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password(OWNER_PW))
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "maria@example.com")
    monkeypatch.setenv(mailer.USER_ENV, "pearl@gmail.com")
    monkeypatch.setenv(mailer.PASSWORD_ENV, "app password")


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None: sent.append(
        {"to": to, "subject": subject, "text": text, "html": html}))
    return sent


class FakePlaid:
    def __init__(self):
        self.removed = []

    def item_remove(self, request):
        self.removed.append(request.to_dict()["access_token"])
        return {}


@pytest.fixture()
def plaid(monkeypatch):
    fake = FakePlaid()
    monkeypatch.setattr(plaid_link, "_client", lambda: fake)
    return fake


@pytest.fixture()
def app(tmp_path, outbox):
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    return a


def code_in(mail) -> str:
    return re.search(r"\b(\d{6})\b", mail["text"]).group(1)


def sign_up(app, outbox, email, first="Alex"):
    c = app.test_client()
    c.post("/api/auth/code/start", json={"email": email, "first_name": first, "create": True})
    code = code_in(next(m for m in reversed(outbox) if m["to"] == email and "code" in m["subject"]))
    r = c.post("/api/auth/code/verify", json={"email": email, "code": code})
    assert r.status_code == 200
    return c, users.by_email(app.config["STORE"], email)


def owner(app):
    c = app.test_client()
    assert c.post("/api/auth/login", json={"username": "mariapapas",
                                           "password": OWNER_PW}).status_code == 200
    return c, users.by_username(app.config["STORE"], "mariapapas")


def fill(st, tag):
    """A little of everything a ledger holds."""
    st.add_transactions([
        Transaction(date="2026-09-03", description=f"{tag} COFFEE", amount=4.5,
                    account_id=f"{tag}-chq", account_name=f"{tag} Chequing", currency="CAD"),
        Transaction(date="2026-09-15", description=f"{tag} PAYROLL", amount=-2100,
                    account_id=f"{tag}-chq", account_name=f"{tag} Chequing", currency="CAD"),
    ])
    st.add_plaid_item(f"{tag}-item", f"access-{tag}", institution=f"{tag} Bank")
    st.set_budget("Groceries", 400)
    st.add_piggy_bank(f"{tag} trip", 1200, "annual", None, "2026-01")
    st.add_manual_account(f"{tag} Savings", "savings", 3000, "2026-10-01")
    st.set_setting("savings_target", "250")


# ── The welcome email (N-04) ─────────────────────────────────────────────

class TestWelcome:
    def test_sent_once_when_the_account_is_made(self, app, outbox):
        sign_up(app, outbox, "alex@example.com")
        welcome = [m for m in outbox if m["subject"].startswith("Welcome")]
        assert len(welcome) == 1 and welcome[0]["to"] == "alex@example.com"
        assert welcome[0]["subject"] == "Welcome to Pearl, Alex"
        text = welcome[0]["text"]
        for line in ("You’ve taken the first step. Here’s what happens next.",
                     "1. Link your accounts", "So Pearl sees your whole picture. Read-only, always.",
                     "2. See your safe to spend",
                     "What you can spend this month without second-guessing.",
                     "3. Follow your path", "Know your money, keep a cushion, grow it. One milestone at a time.",
                     "Open Pearl: https://pearl.example",
                     "Know what’s yours. Keep a cushion. Grow what you’ve got.",
                     "You’re getting this because you created a Pearl account."):
            assert line in text, line
        html = welcome[0]["html"]
        assert "Welcome to Pearl, Alex" in html and 'href="https://pearl.example"' in html
        assert "Open Pearl" in html and "Follow your path" in html

    def test_signing_in_again_sends_no_welcome(self, app, outbox):
        sign_up(app, outbox, "alex@example.com")
        c = app.test_client()
        c.post("/api/auth/code/start", json={"email": "alex@example.com"})
        c.post("/api/auth/code/verify", json={"email": "alex@example.com",
                                              "code": code_in(outbox[-1])})
        assert sum(m["subject"].startswith("Welcome") for m in outbox) == 1

    def test_without_a_first_name(self):
        subject, text, html = emails.welcome(None, "https://p.example")
        assert subject == "Welcome to Pearl" and "None" not in text + html

    def test_a_mail_server_that_fails_does_not_stop_sign_up(self, app, outbox, monkeypatch):
        def boom(to, subject, text, html=None):
            if html:
                raise OSError("down")
            outbox.append({"to": to, "subject": subject, "text": text, "html": None})
        monkeypatch.setattr(mailer, "send", boom)
        sign_up(app, outbox, "alex@example.com")


# ── Consents and their log (CN-01 to CN-05) ──────────────────────────────

class TestConsents:
    def test_onboarding_records_each_moment_with_a_time(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        c.post("/api/onboarding", json={"province": "ON"})
        # CN-01: no ticks, one "Agree and continue".
        r = c.post("/api/onboarding", json={"consents": {"terms": True, "read_data": True}})
        assert r.get_json()["user"]["onboarding"]["step"] == "bank"
        # CN-02 after linking, then CN-03.
        c.post("/api/onboarding", json={"consents": {"insights": True, "ai_sort": False},
                                        "step": "income"})
        c.post("/api/onboarding", json={"consents": {"tips": True}, "step": "path"})
        p = c.get("/api/privacy").get_json()
        assert {k: v["value"] for k, v in p["consents"].items()} == {
            "terms": True, "read_data": True, "insights": True, "ai_sort": False,
            "tips": True, "analytics": True}
        assert all(p["consents"][k]["at"] for k in ("terms", "read_data", "insights", "tips"))
        assert sorted((e["consent"], e["value"], e["source"]) for e in p["log"]) == sorted([
            ("terms", True, "onboarding"), ("read_data", True, "onboarding"),
            ("insights", True, "onboarding"), ("ai_sort", False, "onboarding"),
            ("tips", True, "onboarding")])
        assert [e["consent"] for e in p["log"]][-1] == "tips"

    def test_working_out_numbers_cannot_be_refused_in_onboarding(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        c.post("/api/onboarding", json={"province": "ON"})
        assert c.post("/api/onboarding",
                      json={"consents": {"insights": False}}).status_code == 400

    def test_optional_ones_change_in_settings_and_are_logged(self, app, outbox):
        c, alex = sign_up(app, outbox, "alex@example.com")
        c.post("/api/onboarding", json={"province": "ON"})
        c.post("/api/onboarding", json={"consents": {"terms": True, "read_data": True}})
        c.post("/api/onboarding", json={"consents": {"insights": True, "ai_sort": True}})
        r = c.put("/api/privacy/consents", json={"key": "ai_sort", "value": False})
        assert r.status_code == 200
        assert r.get_json()["consents"]["ai_sort"]["value"] is False
        c.put("/api/privacy/consents", json={"key": "analytics", "value": False})
        c.put("/api/privacy/consents", json={"key": "tips", "value": True})
        # The same answer twice is one entry.
        c.put("/api/privacy/consents", json={"key": "tips", "value": True})
        log = users.consent_log(app.config["STORE"], alex.id)
        assert [(e["consent"], e["value"], e["source"]) for e in log[-3:]] == [
            ("ai_sort", False, "settings"), ("analytics", False, "settings"),
            ("tips", True, "settings")]
        assert sum(e["consent"] == "tips" for e in log) == 1
        assert all(isinstance(e["at"], float) for e in log)

    def test_needed_ones_are_withdrawn_by_deleting_the_account(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        for key in ("terms", "read_data", "insights"):
            r = c.put("/api/privacy/consents", json={"key": key, "value": False})
            assert r.status_code == 400 and "delete your account" in r.get_json()["error"]
        assert c.put("/api/privacy/consents",
                     json={"key": "improve", "value": True}).status_code == 400
        assert c.put("/api/privacy/consents",
                     json={"key": "tips", "value": "yes"}).status_code == 400

    def test_set_up_before_cn02_counts_as_agreed_to_working_out_numbers(self, app, outbox):
        base = app.config["STORE"]
        _, alex = sign_up(app, outbox, "alex@example.com")
        users.update_onboarding(base, alex.id, consents={
            "terms": {"value": True, "at": 1.0}, "read_data": {"value": True, "at": 1.0},
            "improve": {"value": False, "at": 1.0}, "tips": {"value": False, "at": 1.0}})
        got = users.effective_consents(users.by_id(base, alex.id))
        assert got["insights"] == {"value": True, "at": 1.0}
        assert got["analytics"]["value"] is True and "improve" not in got

    def test_privacy_needs_a_sign_in(self, app):
        anon = app.test_client()
        assert anon.get("/api/privacy").status_code == 401
        assert anon.put("/api/privacy/consents", json={}).status_code == 401

    def test_who_to_write_to(self, app, outbox, monkeypatch):
        c, _ = sign_up(app, outbox, "alex@example.com")
        assert c.get("/api/privacy").get_json()["contact"] == "pearl@gmail.com"
        monkeypatch.setenv(mailer.SUPPORT_ENV, "Privacy <privacy@pearl.example>")
        assert c.get("/api/privacy").get_json()["contact"] == "privacy@pearl.example"

    def test_connections_for_how_we_protect_you(self, app, outbox):
        c, alex = sign_up(app, outbox, "alex@example.com")
        st = app.config["STORE_FOR"](alex)
        st.add_plaid_item("td", "access-td", institution="TD")
        st.set_plaid_error("td", "Sign in again", "ITEM_LOGIN_REQUIRED")
        st.add_plaid_item("eq", "access-eq", institution="EQ Bank")
        got = {x["institution"]: x["state"] for x in c.get("/api/privacy").get_json()["connections"]}
        assert got == {"TD": "needs_sign_in", "EQ Bank": "healthy"}
        assert "access" not in json.dumps(c.get("/api/privacy").get_json())


# ── Notifications (N-01, N-02) ───────────────────────────────────────────

class TestNotifications:
    def test_defaults_are_as_drawn(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        r = c.get("/api/notifications").get_json()
        assert r["email_ok"] is False
        p = r["prefs"]
        assert p["types"]["payday"] == {"phone": True, "email": True}
        assert p["types"]["weekly"] == {"phone": True, "email": False}
        assert p["quiet"] == {"from": "21:00", "to": "08:00"}
        assert p["lock_amounts"] is False and p["prompt"]["answer"] is None

    def test_saved_on_the_server(self, app, outbox):
        c, alex = sign_up(app, outbox, "alex@example.com")
        r = c.put("/api/notifications", json={"types": {"weekly": {"phone": False}},
                                              "quiet": {"from": "22:30"}, "lock_amounts": True})
        assert r.status_code == 200
        p = users.notification_prefs(users.by_id(app.config["STORE"], alex.id))
        assert p["types"]["weekly"]["phone"] is False and p["quiet"]["from"] == "22:30"
        assert p["quiet"]["to"] == "08:00" and p["lock_amounts"] is True

    def test_email_only_after_saying_yes_to_email(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        body = {"types": {"weekly": {"email": True}}}
        assert c.put("/api/notifications", json=body).status_code == 400
        c.put("/api/privacy/consents", json={"key": "tips", "value": True})
        r = c.put("/api/notifications", json=body)
        assert r.status_code == 200 and r.get_json()["email_ok"] is True
        assert r.get_json()["prefs"]["types"]["weekly"]["email"] is True

    def test_nonsense_is_refused(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        for body in ({"types": {"spam": {"phone": True}}}, {"types": {"payday": {"fax": True}}},
                     {"quiet": {"from": "25:00"}}, {"types": {"payday": {"phone": "yes"}}}):
            assert c.put("/api/notifications", json=body).status_code == 400, body

    def test_the_priming_answer(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        c.put("/api/notifications", json={"types": {"weekly": {"phone": False}}})
        r = c.post("/api/notifications/prompt", json={"answer": "not_now",
                                                      "milestone": "protect:1"})
        p = r.get_json()["prefs"]["prompt"]
        assert p["answer"] == "not_now" and p["asked"] == 1 and p["milestone"] == "protect:1"
        r = c.post("/api/notifications/prompt", json={"answer": "on"})
        p = r.get_json()["prefs"]
        assert p["prompt"]["asked"] == 2 and p["types"]["weekly"]["phone"] is True
        assert c.post("/api/notifications/prompt", json={"answer": "maybe"}).status_code == 400


# ── Your data (D-01, D-02) ───────────────────────────────────────────────

class TestExport:
    def test_her_data_and_only_hers(self, app, outbox):
        c, alex = sign_up(app, outbox, "alex@example.com")
        _, bea = sign_up(app, outbox, "bea@example.com", first="Bea")
        fill(app.config["STORE_FOR"](alex), "Alex")
        fill(app.config["STORE_FOR"](bea), "Bea")
        c.put("/api/privacy/consents", json={"key": "tips", "value": True})

        summary = c.get("/api/data/export").get_json()
        r = c.get("/api/data/export.zip")
        assert r.status_code == 200 and r.mimetype == "application/zip"
        assert "pearl-data.zip" in r.headers["Content-Disposition"]
        z = zipfile.ZipFile(io.BytesIO(r.data))
        assert sorted(z.namelist()) == ["accounts.csv", "settings.json", "transactions.csv"]
        assert summary["transactions"] == 2 and summary["accounts"] >= 2
        assert abs(summary["bytes"] - len(r.data)) < 200      # built twice, a different time

        txns = z.read("transactions.csv").decode("utf-8-sig")
        assert "ALEX COFFEE" in txns.upper() and "Bea" not in txns
        assert "money" in txns.splitlines()[0] and ",out," in txns and ",in," in txns
        accounts = z.read("accounts.csv").decode("utf-8-sig")
        assert "Alex Savings" in accounts and "Bea" not in accounts
        extra = json.loads(z.read("settings.json"))
        assert extra["profile"]["email"] == "alex@example.com"
        assert extra["consents"]["tips"]["value"] is True
        assert any(e["consent"] == "tips" for e in extra["consent_history"])
        assert extra["notifications"]["quiet"]["from"] == "21:00"
        assert extra["goals"][0]["name"] == "Alex trip"
        assert extra["budgets"] == {"Groceries": 400.0}
        assert extra["settings"]["savings_target"] == 250
        everything = z.read("transactions.csv") + z.read("accounts.csv") + z.read("settings.json")
        assert b"access-Alex" not in everything and b"Bea" not in everything


# ── Deleting the account (D-03 to D-05) ──────────────────────────────────

def ledger_file(app, user) -> str:
    path, _ = users.ledger_location(app.config["STORE"].path, user)
    return path


def everything_about(base, user_id, email) -> dict:
    with base.conn() as c:
        return {t: c.execute(f"SELECT COUNT(*) AS n FROM {t} WHERE {col} = ?",
                             (val,)).fetchone()["n"]
                for t, col, val in (("app_users", "id", user_id),
                                    ("app_passkeys", "user_id", user_id),
                                    ("app_codes", "user_id", user_id),
                                    ("app_codes", "email", email),
                                    ("app_consent_log", "user_id", user_id))}


class TestDeletion:
    def two_people(self, app, outbox):
        c, alex = sign_up(app, outbox, "alex@example.com")
        cb, bea = sign_up(app, outbox, "bea@example.com", first="Bea")
        for who, cl in ((alex, c), (bea, cb)):
            fill(app.config["STORE_FOR"](who), who.first_name)
            cl.post("/api/onboarding", json={"province": "ON"})
            cl.post("/api/onboarding", json={"consents": {"terms": True, "read_data": True}})
        return c, alex, cb, bea

    def delete_with_code(self, c, outbox):
        assert c.post("/api/account/delete/code").status_code == 200
        return c.post("/api/account/delete", json={"method": "code",
                                                   "code": code_in(outbox[-1])})

    def test_nothing_happens_without_confirming_its_her(self, app, outbox, plaid):
        c, alex, _, _ = self.two_people(app, outbox)
        assert c.post("/api/account/delete", json={}).status_code == 400
        assert c.post("/api/account/delete", json={"method": "password",
                                                   "password": "x"}).status_code == 400
        c.post("/api/account/delete/code")
        r = c.post("/api/account/delete", json={"method": "code", "code": "000000"})
        assert r.status_code == 400
        assert users.by_id(app.config["STORE"], alex.id) is not None
        assert os.path.exists(ledger_file(app, alex)) and plaid.removed == []

    def test_removes_everything_of_hers_and_nothing_of_anyone_elses(self, app, outbox, plaid):
        base = app.config["STORE"]
        c, alex, cb, bea = self.two_people(app, outbox)
        maria = users.by_username(base, "mariapapas")
        owner_rows = len(base.all_transactions())
        bea_before = app.config["STORE_FOR"](bea).all_transactions()
        alex_file = ledger_file(app, alex)
        assert os.path.exists(alex_file)

        r = self.delete_with_code(c, outbox)
        assert r.status_code == 200
        body = r.get_json()
        assert body["banks_disconnected"] == 1 and body["revoked_at_plaid"] == 1
        assert body["confirmation_sent_to"] == "alex@example.com"
        # Her bank was revoked at Plaid, and only hers.
        assert plaid.removed == ["access-Alex"]
        # Her ledger is gone, file and all.
        assert not any(os.path.exists(alex_file + s) for s in ("", "-wal", "-shm", "-journal"))
        assert alex.id not in app.config["STORES"]
        # Her sign-in and everything kept about it.
        assert everything_about(base, alex.id, "alex@example.com") == {
            "app_users": 0, "app_passkeys": 0, "app_codes": 0, "app_consent_log": 0}
        assert users.by_email(base, "alex@example.com") is None
        # Only that it existed, and when it went.
        with base.conn() as cc:
            kept = [dict(x) for x in cc.execute("SELECT * FROM app_deleted_accounts").fetchall()]
        assert [k["user_id"] for k in kept] == [alex.id] and kept[0]["deleted_at"]
        assert "alex" not in json.dumps(kept)
        # Signed out here, and the session is no good anywhere.
        assert c.get("/api/auth/status").get_json()["signed_in"] is False
        assert c.get("/api/privacy").status_code == 401

        # Bea and Maria are untouched.
        assert app.config["STORE_FOR"](bea).all_transactions() == bea_before
        assert [i["item_id"] for i in app.config["STORE_FOR"](bea).plaid_items()] == ["Bea-item"]
        assert cb.get("/api/privacy").status_code == 200
        assert everything_about(base, bea.id, "bea@example.com")["app_users"] == 1
        assert users.consent_log(base, bea.id)
        assert users.by_id(base, maria.id) is not None
        assert len(base.all_transactions()) == owner_rows

        # The confirmation (D-05).
        mail = outbox[-1]
        assert mail["to"] == "alex@example.com"
        assert mail["subject"] == "Your Pearl account is deleted"
        assert "disconnected your banks" in mail["text"]

    def test_the_same_email_starts_again_from_nothing(self, app, outbox, plaid):
        c, alex, _, _ = self.two_people(app, outbox)
        self.delete_with_code(c, outbox)
        c2, again = sign_up(app, outbox, "alex@example.com")
        assert again.id != alex.id and again.consents is None
        assert app.config["STORE_FOR"](again).all_transactions() == []

    def test_the_first_account_keeps_the_shared_tables(self, app, outbox, plaid):
        base = app.config["STORE"]
        _, alex, _, _ = self.two_people(app, outbox)
        c, maria = owner(app)
        fill(base, "Maria")
        alex_rows = app.config["STORE_FOR"](alex).all_transactions()
        assert base.all_transactions()

        r = c.post("/api/account/delete", json={"method": "password", "password": OWNER_PW})
        assert r.status_code == 200 and plaid.removed == ["access-Maria"]
        assert base.all_transactions() == [] and base.plaid_items() == []
        assert base.piggy_banks() == [] and base.budgets() == {}
        assert base.manual_accounts() == []
        assert base.seed_suppressed()            # not refilled on the next cold start
        assert users.by_id(base, maria.id) is None
        # Everyone else signs in and keeps their ledger.
        assert users.by_id(base, alex.id) is not None
        assert app.config["STORE_FOR"](alex).all_transactions() == alex_rows
        with base.conn() as cc:
            assert cc.execute("SELECT COUNT(*) AS n FROM app_users").fetchone()["n"] == 2

    def test_a_passkey_must_be_hers(self, app, outbox, plaid, monkeypatch):
        from finance import passkeys
        c, alex, _, bea = self.two_people(app, outbox)
        c.post("/api/account/delete/passkey-options")
        monkeypatch.setattr(passkeys, "authenticate", lambda *a, **k: bea)
        r = c.post("/api/account/delete", json={"method": "passkey", "credential": {}})
        assert r.status_code == 400 and users.by_id(app.config["STORE"], alex.id)
        c.post("/api/account/delete/passkey-options")
        monkeypatch.setattr(passkeys, "authenticate", lambda *a, **k: alex)
        r = c.post("/api/account/delete", json={"method": "passkey", "credential": {}})
        assert r.status_code == 200 and users.by_id(app.config["STORE"], alex.id) is None

    def test_a_passkey_needs_a_fresh_challenge(self, app, outbox, plaid):
        c, alex, _, _ = self.two_people(app, outbox)
        r = c.post("/api/account/delete", json={"method": "passkey", "credential": {}})
        assert r.status_code == 400 and users.by_id(app.config["STORE"], alex.id)

    def test_how_she_can_confirm(self, app, outbox):
        c, _ = sign_up(app, outbox, "alex@example.com")
        assert c.get("/api/account/delete").get_json()["methods"] == ["code"]
        co, _ = owner(app)
        assert co.get("/api/account/delete").get_json()["methods"] == ["code", "password"]

    def test_plaid_being_down_still_deletes(self, app, outbox, monkeypatch):
        class Down:
            def item_remove(self, request):
                raise OSError("down")
        monkeypatch.setattr(plaid_link, "_client", lambda: Down())
        c, alex, _, _ = self.two_people(app, outbox)
        r = self.delete_with_code(c, outbox)
        assert r.status_code == 200 and r.get_json()["revoked_at_plaid"] == 0
        assert users.by_id(app.config["STORE"], alex.id) is None
        assert not os.path.exists(ledger_file(app, alex))

    def test_needs_a_sign_in(self, app):
        anon = app.test_client()
        assert anon.post("/api/account/delete", json={}).status_code == 401
        assert anon.post("/api/account/delete/code").status_code == 401


def test_with_nobody_signing_in_the_pages_still_read(tmp_path, monkeypatch):
    """A local ledger with no accounts: the pages show what they can, and
    nothing can be saved to or deleted from an account that doesn't exist."""
    for key in ("VERCEL", users.OWNER_HASH_ENV):
        monkeypatch.delenv(key, raising=False)
    a = create_app(str(tmp_path / "ledger.db"))
    c = a.test_client()
    assert c.get("/api/privacy").get_json()["consents"] == {}
    assert c.get("/api/notifications").get_json()["prefs"]["quiet"]["from"] == "21:00"
    for r in (c.put("/api/privacy/consents", json={"key": "tips", "value": True}),
              c.put("/api/notifications", json={"lock_amounts": True}),
              c.post("/api/account/delete", json={"method": "code", "code": "123456"})):
        assert r.status_code == 400 and r.get_json()["no_account"] is True
