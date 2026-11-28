"""Pearl sorts for you: Off · Rules · Smart (AI Phase 4, THL-309; CN-07,
CN-08, AI-03r / AI-03s, CN-09) and Profile › AI usage, owner only (AU-01).

No network: a fake client stands in for Anthropic, and answers from a
script or a rule. Smart only ever picks among the answers Python allows,
never sorts what Python's evidence gate wouldn't, and any failure is Rules.
"""

from __future__ import annotations

import json
import re
from datetime import date, timedelta

import pytest

from finance import pattern_sort as ps
from finance import smart_sort, users
from finance.ai import client as client_mod
from finance.ai import config, safety, usage
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from finance.store import Store

TODAY = date.today()
DEMO_EMAIL = "owner@example.com"


def day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def tx(desc, amount, when, category=""):
    return Transaction(date=when, description=desc, merchant=desc.title(), amount=amount,
                       category=category, account_id="visa", account_name="TD Visa",
                       raw={"account_type": "credit", "category_confidence": "LOW"})


class Fake:
    """Answers each `pick` with `rule(enum, body)` -> (answer, reason), or
    a scripted Reply / error. Remembers what it was sent."""

    def __init__(self, rule=None, script=None):
        self.rule = rule
        self.script = list(script or [])
        self.calls = []

    def send(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
        safety.check(system, messages, tools or [])
        self.calls.append({"model": model, "system": system, "messages": messages, "tools": tools})
        if self.script:
            step = self.script.pop(0)
            if isinstance(step, Exception):
                raise step
            return client_mod.Reply(model=model, input_tokens=90, output_tokens=12, **step)
        enum = tools[0]["input_schema"]["properties"]["answer"]["enum"]
        body = json.loads(messages[0]["content"])
        answer, reason = self.rule(enum, body)
        return client_mod.Reply(model=model, stop_reason="tool_use", input_tokens=90, output_tokens=12,
                                tool_calls=[{"id": "t1", "name": "pick",
                                             "input": {"answer": answer, "reason": reason}}])


def agree(enum, body):
    return enum[0], "Looks like " + body["shop"] + ". You said " + enum[0] + " there [NUM1] times."


@pytest.fixture()
def client(tmp_path, monkeypatch):
    for env in (config.KEY_ENV, config.KILL_ENV, config.MONTHLY_CAP_ENV, config.DAILY_REQUESTS_ENV):
        monkeypatch.delenv(env, raising=False)
    usage._ready.clear()
    from app import create_app
    app = create_app(str(tmp_path / "smart.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.base = Store(str(tmp_path / "base.db"))
        users.ensure_table(c.base)
        yield c
    usage._ready.clear()


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "visa"))


def ids(c, desc):
    return [t.fingerprint for t in c.st.all_transactions() if t.description == desc]


def answer(c, tid, category):
    r = c.post(f"/api/transactions/{tid}/mark",
               json={"case": "spending", "category": category, "remember": False})
    assert r.status_code == 200, r.get_json()


def history(c, desc, cats, start=90):
    add(c, *[tx(desc, 20.0 + i, day(start - i * 7)) for i in range(len(cats))])
    for tid, cat in zip(sorted(ids(c, desc), key=lambda i: c.st.get_transaction(i).date), cats):
        answer(c, tid, cat)


def yes_to_every_pattern(c):
    for ask in c.get("/api/pattern-sort/asks").get_json()["asks"]:
        assert c.post(f"/api/pattern-sort/asks/{ask['id']}/yes").status_code == 200


def smart_on(c):
    ps.switched_on(c.st)
    yes_to_every_pattern(c)
    smart_sort.set_mode(c.base, c.st, None, smart_sort.SMART, consent=True)


def new_row(c, desc, amount=31.0, n=1):
    before = set(ids(c, desc))
    add(c, tx(desc, amount, day(n)))
    return next(i for i in ids(c, desc) if i not in before)


def run(c, fake, user_id=1):
    return smart_sort.run(c.st, TODAY.isoformat(), base=c.base, user_id=user_id, client=fake)


def card(c, tid):
    review = c.get("/api/review").get_json()
    return next((i for i in review["unsure_category"] if i["txn"]["id"] == tid), None)


# ── The setting ──────────────────────────────────────────────────────────

class TestSetting:
    def test_ai_sort_maps_to_rules_and_off_and_nobody_is_smart(self):
        assert smart_sort.mode_from({"ai_sort": {"value": True}}) == "rules"
        assert smart_sort.mode_from({"ai_sort": {"value": False}}) == "off"
        assert smart_sort.mode_from({}) == "off"
        assert smart_sort.mode_from({"ai_sort": {"value": True},
                                     "ai_sort_smart": {"value": True}}) == "smart"

    def test_smart_the_first_time_needs_her_turn_on(self, client):
        ps.switched_on(client.st)
        r = client.put("/api/privacy/sorting", json={"mode": "smart"})
        assert r.status_code == 409 and r.get_json()["needs_consent"]
        # Not now: nothing changed, still Rules.
        assert client.get("/api/privacy").get_json()["sorting"]["mode"] == "rules"
        r = client.put("/api/privacy/sorting", json={"mode": "smart", "consent": True})
        assert r.status_code == 200 and r.get_json()["sorting"] == {"mode": "smart", "asked": True,
                                                                     "patterns": 0}
        # Back to Rules and Smart again: asked once, so no sheet.
        assert client.put("/api/privacy/sorting", json={"mode": "rules"}).get_json()["sorting"]["mode"] == "rules"
        assert client.put("/api/privacy/sorting", json={"mode": "smart"}).status_code == 200

    def test_rules_and_smart_keep_the_switch_off_moves_it(self, client):
        ps.switched_on(client.st, at="2026-01-01T00:00:00+00:00")
        start = ps._json(client.st, ps.BASELINE_KEY, None)
        client.put("/api/privacy/sorting", json={"mode": "smart", "consent": True})
        client.put("/api/privacy/sorting", json={"mode": "rules"})
        assert ps._json(client.st, ps.BASELINE_KEY, None) == start
        client.put("/api/privacy/sorting", json={"mode": "off"})
        assert not ps.is_on(client.st) and not smart_sort.is_smart(client.st)
        assert client.put("/api/privacy/sorting", json={"mode": "rules"}).get_json()["sorting"]["mode"] == "rules"

    def test_a_mode_that_isnt_one(self, client):
        assert client.put("/api/privacy/sorting", json={"mode": "magic"}).status_code == 400

    def test_off_keeps_her_patterns(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        client.put("/api/privacy/sorting", json={"mode": "off"})
        assert client.get("/api/privacy").get_json()["sorting"]["patterns"] == 1
        assert ps.learned(client.st)[0]["confirmed"]


# ── Smart's sync ─────────────────────────────────────────────────────────

class TestPatterns:
    def test_claude_agrees_and_words_the_reason(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        tid = new_row(client, "NORTHSIDE PANTRY")
        fake = Fake(agree)
        got = run(client, fake)
        assert [r["txn"] for r in got["sorted"]] == [tid]
        assert client.st.get_transaction(tid).category == "Groceries"
        # Python allowed one answer; the model saw no amount and no count.
        tool = fake.calls[0]["tools"][0]
        assert tool["strict"] and tool["input_schema"]["properties"]["answer"]["enum"] == ["Groceries", "none"]
        sent = fake.calls[0]["messages"][0]["content"]
        assert "Northside Pantry" in sent and "31" not in sent
        assert not re.search(r"\d", re.sub(r"\[NUM\d+\]", "", sent))
        rec = got["sorted"][0]
        assert rec["smart_line"] == "Looks like Northside Pantry. You said Groceries there 5 times."
        row = client.get(f"/api/pattern-sort/{rec['id']}").get_json()
        assert row["reason"] == rec["smart_line"] and row["reason_by"] == "claude"
        # CN-09: back to Rules, and the plain wording at once.
        smart_sort.set_mode(client.base, client.st, None, smart_sort.RULES)
        assert "reason" not in client.get(f"/api/pattern-sort/{rec['id']}").get_json()
        assert ps.learned(client.st)[0]["on"]

    def test_claude_disagrees_so_quick_sort_and_never_by_itself(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        tid = new_row(client, "NORTHSIDE PANTRY")
        got = run(client, Fake(lambda enum, body: ("none", "Hard to tell from the name.")))
        assert got["sorted"] == [] and got["held"] == 1
        assert client.st.get_transaction(tid).category_source != "pattern"
        it = card(client, tid)
        assert it["guess"] == "Groceries" and (it.get("why") or {}).get("by") != "claude"
        # Never sorted by Pearl by itself, in Smart or Rules.
        smart_sort.set_mode(client.base, client.st, None, smart_sort.RULES)
        assert ps.run(client.st, TODAY.isoformat()) == []
        # A detection, against smart_sort@1.
        from finance.signals.ledger import rows
        d = rows(client.st, "smart_sort")[0]
        assert d["version"] == "1" and d["evidence"]["facts"]["agree"] is False

    def test_rules_never_calls_claude(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        ps.switched_on(client.st)
        yes_to_every_pattern(client)
        tid = new_row(client, "NORTHSIDE PANTRY")
        r = client.post("/api/pattern-sort/run").get_json()
        assert r["sorted"] == 1 and r["rows"][0]["txn"] == tid and "reason" not in r["rows"][0]
        assert usage.rows(client.base) == []


class TestHarderCases:
    def test_close_answers_claude_picks_among_them_and_nothing_sorts(self, client):
        history(client, "CORNER MARKET", ["Groceries", "Groceries", "Dining", "Dining", "Groceries"])
        smart_on(client)
        tid = new_row(client, "CORNER MARKET")
        fake = Fake(lambda enum, body: ("Groceries", "Looks like Corner Market, mostly Groceries."))
        got = run(client, fake)
        assert got["sorted"] == [] and got["guessed"] == 1
        enum = fake.calls[0]["tools"][0]["input_schema"]["properties"]["answer"]["enum"]
        assert set(enum) == {"Groceries", "Dining", "none"}
        it = card(client, tid)
        assert it["guess"] == "Groceries" and it["why"]["by"] == "claude" and "unsure" not in it
        assert it["why"]["text"] == "Looks like Corner Market, mostly Groceries."
        # Her Yes is Claude's pick, for this row alone.
        r = client.put(f"/api/quick-sort/{tid}", json={"action": "right", "every": False, "rows": []})
        assert r.status_code == 200, r.get_json()
        t = client.st.get_transaction(tid)
        assert t.category == "Groceries"
        from finance.signals.ledger import outcomes
        assert [o["outcome"] for o in outcomes(client.st, "smart_sort")] == ["yes"]

    def test_a_pick_against_a_clear_leader_shows_pythons(self, client):
        history(client, "CORNER MARKET", ["Groceries", "Groceries", "Groceries", "Dining", "Dining"])
        smart_on(client)
        tid = new_row(client, "CORNER MARKET")
        run(client, Fake(lambda enum, body: ("Dining", "Looks like Corner Market, so Dining.")))
        it = card(client, tid)
        assert it["guess"] == "Groceries" and (it.get("why") or {}).get("by") != "claude"
        assert tid in ps._json(client.st, ps.HELD_KEY, [])

    def test_a_new_shop_picks_from_pythons_likeliest(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 2)
        smart_on(client)
        tid = new_row(client, "QUILLON AND SONS")
        fake = Fake(lambda enum, body: (enum[0], "Looks like Quillon And Sons."))
        run(client, fake)
        enum = fake.calls[-1]["tools"][0]["input_schema"]["properties"]["answer"]["enum"]
        assert 2 <= len(enum) <= 5 and enum[-1] == "none" and "Other" not in enum
        assert card(client, tid)["guess"] == enum[0]

    def test_a_reason_with_a_number_of_its_own_is_thrown_away(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        new_row(client, "NORTHSIDE PANTRY")
        got = run(client, Fake(lambda enum, body: (enum[0], "You said Groceries 5 times.")))
        # Rules sorted it, in Python's words.
        assert len(got["sorted"]) == 1 and "smart_line" not in got["sorted"][0]
        assert usage.rows(client.base)[-1]["outcome"] == "bad_tool"


class TestFallback:
    @pytest.mark.parametrize("script,reason", [
        ([client_mod.ClientError("server")], "error:server"),
        ([{"stop_reason": "refusal"}], "refusal"),
    ])
    def test_a_failure_is_rules_for_the_rest_of_the_sync(self, client, script, reason):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        new_row(client, "NORTHSIDE PANTRY", n=1)
        new_row(client, "NORTHSIDE PANTRY", amount=44.0, n=2)
        fake = Fake(agree, script=script)
        got = run(client, fake)
        assert got["fallback"] == reason and len(fake.calls) == 1
        assert len(got["sorted"]) == 2 and not any("smart_line" in r for r in got["sorted"])
        assert usage.rows(client.base)[-1]["outcome"] == reason

    def test_no_key_and_over_the_cap(self, client, monkeypatch):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 5)
        smart_on(client)
        new_row(client, "NORTHSIDE PANTRY")
        got = smart_sort.run(client.st, TODAY.isoformat(), base=client.base, user_id=1)
        assert got["fallback"] == "off" and len(got["sorted"]) == 1
        assert usage.rows(client.base)[-1]["outcome"] == "off"
        monkeypatch.setenv(config.MONTHLY_CAP_ENV, "0")
        new_row(client, "NORTHSIDE PANTRY", amount=50.0, n=2)
        fake = Fake(agree)
        got = run(client, fake)
        assert got["fallback"] == "over_budget" and fake.calls == []

    def test_every_call_is_a_usage_row(self, client):
        history(client, "CORNER MARKET", ["Groceries", "Dining"])
        smart_on(client)
        new_row(client, "CORNER MARKET")
        new_row(client, "QUILLON AND SONS")
        fake = Fake(agree)
        run(client, fake)
        rows = usage.rows(client.base)
        assert len(rows) == len(fake.calls) == 2
        assert {r["route"] for r in rows} == {"sort_reason"} and {r["prompt"] for r in rows} == {"sort_reason@1"}


class TestReasons:
    def test_rules_line_is_pythons(self, client):
        history(client, "NORTHSIDE PANTRY", ["Groceries"] * 3)
        ps.switched_on(client.st)
        tid = new_row(client, "NORTHSIDE PANTRY")
        client.st.write_categories({tid: ("Groceries", "issuer")})
        it = card(client, tid)
        assert it is None or it.get("unsure") or it["why"]["text"] == "Like your last 3 at Northside Pantry."


# ── AU-01 ────────────────────────────────────────────────────────────────

class TestUsagePage:
    @pytest.fixture()
    def hosted(self, tmp_path, monkeypatch):
        from app import create_app
        from finance import auth, mailer, secrets_box
        for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV, users.OWNER_USERNAME_ENV,
                    users.OWNER_EMAIL_ENV, "AWS_LAMBDA_FUNCTION_NAME", config.KEY_ENV):
            monkeypatch.delenv(key, raising=False)
        monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("a demo password"))
        monkeypatch.setenv(users.OWNER_EMAIL_ENV, "first@example.com")
        monkeypatch.setenv(mailer.USER_ENV, "pearl@example.com")
        monkeypatch.setenv(mailer.PASSWORD_ENV, "app password")
        monkeypatch.setenv("VERCEL", "1")
        monkeypatch.setenv("SPENDIE_PUBLIC_URL", "https://pearl.example")
        monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
        sent = []
        monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None: sent.append(
            {"to": to, "subject": subject, "text": text}))
        usage._ready.clear()
        a = create_app(str(tmp_path / "ledger.db"))
        a.config.update(TESTING=True)
        a.sent = sent
        yield a
        usage._ready.clear()

    def sign_up(self, app, email):
        c = app.test_client()
        r = c.post("/api/auth/code/start", json={"email": email, "first_name": "Alex", "create": True})
        assert r.status_code == 200, r.get_json()
        mail = next(m for m in reversed(app.sent) if m["to"] == email and "code" in m["subject"])
        code = re.search(r"\b(\d{6})\b", mail["text"]).group(1)
        assert c.post("/api/auth/code/verify", json={"email": email, "code": code}).status_code == 200
        return c, users.by_email(app.config["STORE"], email)

    def test_owner_only(self, hosted, monkeypatch):
        monkeypatch.setenv("PEARL_OWNER_EMAILS", f"someone@example.com, {DEMO_EMAIL.upper()}")
        owner, me = self.sign_up(hosted, DEMO_EMAIL)
        other, them = self.sign_up(hosted, "friend@example.com")
        base = hosted.config["STORE"]
        usage.record(base, user_id=me.id, ask_id="a", route="ask", outcome="ok", model="m",
                     cost_usd=0.21)
        usage.record(base, user_id=them.id, ask_id="b", route="ask", outcome="ok", model="m",
                     cost_usd=0.50)
        usage.record(base, user_id=them.id, ask_id="b", route="ask", outcome="ok", model="m",
                     attempt=2, cost_usd=0.05)
        r = other.get("/api/ai-usage")
        assert r.status_code == 404 and "cost" not in r.get_data(as_text=True)
        assert other.get("/api/profile").get_json()["ai_usage"] is False
        assert owner.get("/api/profile").get_json()["ai_usage"] is True
        got = owner.get("/api/ai-usage").get_json()
        assert got["questions"] == 2 and got["escalated"] == 1 and got["escalation_rate"] == 0.5
        assert got["cap_usd"] == 0.5 and got["at_cap"] == 1 and got["people"] == 3  # with the deployment's first account
        assert got["highest_usd"] == 0.55 and got["you_usd"] == 0.21
        assert round(got["cost_usd"], 2) == 0.76

    def test_nobody_is_the_owner_without_the_setting(self, hosted, monkeypatch):
        monkeypatch.delenv("PEARL_OWNER_EMAILS", raising=False)
        c, _ = self.sign_up(hosted, DEMO_EMAIL)
        assert c.get("/api/ai-usage").status_code == 404

    def test_smart_consent_is_stored_with_its_time(self, hosted):
        c, me = self.sign_up(hosted, DEMO_EMAIL)
        c.post("/api/onboarding", json={"province": "ON"})
        c.post("/api/onboarding", json={"consents": {"terms": True, "read_data": True}})
        c.post("/api/onboarding", json={"consents": {"insights": True, "ai_sort": True}})
        assert c.get("/api/privacy").get_json()["sorting"]["mode"] == "rules"
        # Not through the consents door: only with the setting.
        assert c.put("/api/privacy/consents", json={"key": "ai_sort_smart", "value": True}).status_code == 400
        assert c.put("/api/privacy/sorting", json={"mode": "smart"}).status_code == 409
        r = c.put("/api/privacy/sorting", json={"mode": "smart", "consent": True}).get_json()
        assert r["sorting"]["mode"] == "smart" and isinstance(r["consents"]["ai_sort_smart"]["at"], float)
        log = users.consent_log(hosted.config["STORE"], me.id)
        assert ("ai_sort_smart", True) in [(e["consent"], e["value"]) for e in log]
        # Off from Smart: both off; Rules again is Rules, not Smart.
        r = c.put("/api/privacy/sorting", json={"mode": "off"}).get_json()
        assert r["sorting"]["mode"] == "off" and r["consents"]["ai_sort_smart"]["value"] is False
        assert c.put("/api/privacy/sorting", json={"mode": "rules"}).get_json()["sorting"]["mode"] == "rules"
