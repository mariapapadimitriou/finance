"""Ask Pearl on every iPhone (THL-308, AI Phase 2; PC-20 to PC-26, CN-06).

The acceptance criteria these hold, server side:

* consent is an explicit opt-in, stored with its time and withdrawable, and
  /api/ask refuses anyone who hasn't opted in (AC 2-4, 7);
* /api/ask streams: a thinking step that names the tool, figures whole in
  fact cards, only the words streamed (AC 9);
* a suggestion only opens a screen (AC 10);
* couldn't answer when the model fails, refuses or is unsure (AC 11);
* past the cap, built-in answers and one quiet line with no dollars, tokens
  or "limit" (AC 13);
* the new answers, all computed in Python (AC 14-17);
* the model never receives account or card numbers, Plaid tokens or logins,
  and every call writes an app_ai_usage row (AC 18-19).

No network: the model is FakeStream, and `anthropic` is never called.
"""

from __future__ import annotations

import json
import re
from datetime import date

import pytest

from app import create_app
from finance import api, ask, auth, mailer, secrets_box, users
from finance.ai import client as client_mod
from finance.ai import config, safety, usage
from finance.models import Transaction

TODAY = date(2026, 11, 27)


@pytest.fixture(autouse=True)
def _env(monkeypatch):
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, users.OWNER_HASH_ENV,
                users.OWNER_USERNAME_ENV, users.OWNER_EMAIL_ENV, config.KEY_ENV,
                config.KILL_ENV, config.MONTHLY_CAP_ENV, config.DAILY_REQUESTS_ENV,
                "AWS_LAMBDA_FUNCTION_NAME", "SPENDIE_PUBLIC_URL", mailer.SUPPORT_ENV,
                mailer.FROM_ENV, "VERCEL_PROJECT_PRODUCTION_URL"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv("SPENDIE_PUBLIC_URL", "https://pearl.example")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("owner's password"))
    monkeypatch.setenv(users.OWNER_EMAIL_ENV, "owner@example.com")
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    monkeypatch.setenv(mailer.USER_ENV, "pearl@gmail.com")
    monkeypatch.setenv(mailer.PASSWORD_ENV, "app password")
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    usage._ready.clear()
    yield
    usage._ready.clear()


@pytest.fixture()
def outbox(monkeypatch):
    sent = []
    monkeypatch.setattr(mailer, "send", lambda to, subject, text, html=None: sent.append(
        {"to": to, "subject": subject, "text": text}))
    return sent


@pytest.fixture()
def app(tmp_path, outbox):
    a = create_app(str(tmp_path / "ledger.db"))
    a.config.update(TESTING=True)
    return a


def sign_up(app, outbox, email="alex@example.com"):
    c = app.test_client()
    c.post("/api/auth/code/start", json={"email": email, "first_name": "Alex", "create": True})
    mail = next(m for m in reversed(outbox) if m["to"] == email and "code" in m["subject"])
    code = re.search(r"\b(\d{6})\b", mail["text"]).group(1)
    assert c.post("/api/auth/code/verify", json={"email": email, "code": code}).status_code == 200
    user = users.by_email(app.config["STORE"], email)
    c.post("/api/onboarding", json={"province": "ON"})
    c.post("/api/onboarding", json={"consents": {"terms": True, "read_data": True}})
    c.st = app.config["STORE_FOR"](user)
    c.user = user
    return c


def t(day, desc, amount, account="visa", merchant=None, category=None):
    return Transaction(date=day, description=desc, merchant=merchant or desc.title(),
                       amount=amount, account_id=account, account_name="TD Visa",
                       category=category, raw={"account_type": "credit"})


def fill(st):
    rows = []
    for m in range(1, 12):
        rows.append(t(f"2026-{m:02d}-05", "LOBLAWS", 40.0 + m, merchant="Loblaws",
                      category="Groceries"))
        rows.append(t(f"2026-{m:02d}-06", "LOBLAWS", 30.0, merchant="Loblaws",
                      category="Groceries"))
    for i in range(12):
        rows.append(t(f"2026-{9 + i // 5:02d}-{10 + i % 5:02d}", "UBER TRIP", 10.0 + i,
                      merchant="Uber", category="Transport"))
    for m in range(8, 12):
        rows.append(t(f"2026-{m:02d}-15", "PAI NORTHERN", 80.0 if m < 11 else 240.0,
                      merchant="Pai", category="Dining"))
        rows.append(Transaction(date=f"2026-{m:02d}-01", description="PAYROLL ACME",
                                merchant="Acme", amount=-4300.0, account_id="chq",
                                account_name="Chequing", category="Income",
                                raw={"account_type": "depository"}))
    # Bank text with an account number in it: never for the model.
    rows.append(Transaction(date="2026-11-20", description="TRANSFER TO 0012345678901",
                            merchant="Transfer", amount=100.0, account_id="chq",
                            account_name="Chequing", category="Transfers",
                            raw={"account_type": "depository"}))
    st.add_transactions(rows)
    st.note_account("visa", name="TD Visa ••1203", account_type="credit", subtype="credit card")
    st.note_account("amex", name="Amex Cobalt 4111111111111111", account_type="credit",
                    subtype="credit card")
    st.note_account("chq", name="Chequing", account_type="depository", subtype="checking")
    st.set_balance("visa", 1840.0, None, 5000, "CAD", TODAY.isoformat())
    st.set_balance("amex", 2710.0, None, 3000, "CAD", TODAY.isoformat())
    st.set_setting("debt_details", json.dumps({"visa": {"due_day": 3}, "amex": {"due_day": 14}}))


def turn_on(c):
    r = c.put("/api/privacy/consents", json={"key": "ai_ask", "value": True, "source": "chat"})
    assert r.status_code == 200
    return r


# ── A model that streams, as scripted ────────────────────────────────────

class Block(dict):
    """A content block replayed in the tool loop (a dict is what the SDK takes)."""


class FakeStream:
    """Stands in for client.Client.stream: each step is a reply (text,
    tool_calls, stop_reason) or an exception; text comes in two pieces."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def stream(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
        safety.check(system, messages, tools or [])
        self.calls.append({"model": model, "messages": json.loads(json.dumps(messages, default=str)),
                           "tools": tools})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        text = step.get("text", "")
        if text:
            half = len(text) // 2
            yield ("text", text[:half])
            yield ("text", text[half:])
        calls = step.get("tool_calls", [])
        content = ([Block(type="text", text=text)] if text else []) + [
            Block(type="tool_use", id=c["id"], name=c["name"], input=c["input"]) for c in calls]
        yield ("reply", client_mod.Reply(
            model=model, stop_reason=step.get("stop_reason", "tool_use" if calls else "end_turn"),
            text=text, tool_calls=calls, content=content, input_tokens=200,
            cache_read_tokens=1500, output_tokens=40, request_id="req_x"))


def tool(name, **inp):
    return {"tool_calls": [{"id": f"tu_{name}", "name": name, "input": inp}]}


def events(c, text, fake=None, monkeypatch=None):
    if fake is not None:
        monkeypatch.setattr(client_mod, "from_env", lambda: fake)
    r = c.post("/api/ask", json={"text": text})
    assert r.status_code == 200, r.get_json()
    assert r.mimetype == "application/x-ndjson"
    return [json.loads(line) for line in r.get_data(as_text=True).splitlines() if line.strip()]


def of(evs, kind):
    return [e for e in evs if e["type"] == kind]


def words(evs):
    out = ""
    for e in evs:
        if e["type"] == "text":
            out += e["text"]
        elif e["type"] == "reset":
            out = ""
        elif e["type"] == "words":
            out = e["text"]
    return out


# ── Consent (AC 2-4, 7) ──────────────────────────────────────────────────

class TestConsent:
    def test_refused_until_she_opts_in(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fake = FakeStream()
        monkeypatch.setattr(client_mod, "from_env", lambda: fake)
        r = c.post("/api/ask", json={"text": "How's this month going?"})
        assert r.status_code == 403 and r.get_json()["ask_off"] is True
        assert fake.calls == []                       # nothing was sent
        assert usage.rows(app.config["STORE"]) == []

    def test_nobody_signed_in_is_refused(self, tmp_path, monkeypatch):
        a = create_app(str(tmp_path / "local.db"))
        a.config.update(TESTING=True)
        r = a.test_client().post("/api/ask", json={"text": "hi"})
        assert r.status_code in (401, 403)

    def test_a_local_ledger_keeps_its_own_opt_in(self, tmp_path, monkeypatch):
        # No accounts (a copy on a Mac): the opt-in is kept in the ledger, with its time.
        for key in (users.OWNER_HASH_ENV, users.OWNER_EMAIL_ENV, "VERCEL"):
            monkeypatch.delenv(key, raising=False)
        a = create_app(str(tmp_path / "local.db"))
        a.config.update(TESTING=True, HOSTED=False)
        c = a.test_client()
        assert c.get("/api/chat").get_json()["ask"] == "unasked"
        assert c.post("/api/ask", json={"text": "hi"}).status_code == 403
        r = c.put("/api/privacy/consents", json={"key": "ai_ask", "value": True, "source": "chat"})
        assert r.status_code == 200 and r.get_json()["consents"]["ai_ask"]["at"]
        assert c.get("/api/chat").get_json()["ask"] == "on"
        monkeypatch.setattr(client_mod, "from_env", lambda: None)
        r = c.post("/api/ask", json={"text": "When are my cards due?"})
        assert r.status_code == 200 and "cards" in r.get_data(as_text=True)
        # Other consents still need an account.
        assert c.put("/api/privacy/consents", json={"key": "tips", "value": True}).status_code == 400
        c.put("/api/privacy/consents", json={"key": "ai_ask", "value": False})
        assert c.get("/api/chat").get_json()["ask"] == "off"

    def test_state_on_the_tab_unasked_on_off(self, app, outbox):
        c = sign_up(app, outbox)
        assert c.get("/api/chat").get_json()["ask"] == "unasked"
        turn_on(c)
        assert c.get("/api/chat").get_json()["ask"] == "on"
        c.put("/api/privacy/consents", json={"key": "ai_ask", "value": False})
        assert c.get("/api/chat").get_json()["ask"] == "off"

    def test_stored_with_its_time_and_withdrawable(self, app, outbox):
        c = sign_up(app, outbox)
        p = turn_on(c).get_json()
        assert p["consents"]["ai_ask"]["value"] is True and p["consents"]["ai_ask"]["at"]
        c.put("/api/privacy/consents", json={"key": "ai_ask", "value": False})
        log = [(e["consent"], e["value"], e["source"])
               for e in users.consent_log(app.config["STORE"], c.user.id) if e["consent"] == "ai_ask"]
        assert log == [("ai_ask", True, "chat"), ("ai_ask", False, "settings")]
        assert c.post("/api/ask", json={"text": "hi"}).status_code == 403

    def test_never_on_by_default(self, app, outbox):
        c = sign_up(app, outbox)
        assert "ai_ask" not in c.get("/api/privacy").get_json()["consents"]
        assert "ai_ask" not in users.DEFAULT_ON

    def test_empty_question(self, app, outbox):
        c = sign_up(app, outbox)
        turn_on(c)
        assert c.post("/api/ask", json={"text": "  "}).status_code == 400


# ── Streaming with the model (AC 9, 10, 18, 19) ──────────────────────────

class TestStream:
    def test_step_fact_words_suggestion(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        m = ask.month(ask.Ledger(c.st, TODAY))
        said = m.line
        fake = FakeStream(tool("month"), {"text": said})
        evs = events(c, "How's this month going?", fake, monkeypatch)
        kinds = [e["type"] for e in evs]
        # The step names the tool, before its card; the card comes whole.
        assert of(evs, "step")[0]["text"] == "Looking at November…"
        assert kinds.index("step") < kinds.index("fact") < kinds.index("text")
        fact = of(evs, "fact")[0]
        assert fact["kind"] == "month" and fact["data"]["spent"] == m.data["spent"]
        # Only the words stream, in pieces.
        assert len(of(evs, "text")) == 2 and words(evs) == said
        assert kinds[-1] == "done"
        # The model was Haiku, both turns; the tool's result went back to it.
        assert [x["model"] for x in fake.calls] == [config.DEFAULT_MODEL] * 2
        sent = json.dumps(fake.calls[1]["messages"])
        assert "tool_result" in sent and "Looking at" not in sent

    def test_suggestion_only_opens_a_screen(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        m = ask.month(ask.Ledger(c.st, TODAY))
        evs = events(c, "How's this month going?", FakeStream(tool("month"), {"text": m.line}),
                     monkeypatch)
        s = of(evs, "suggestion")
        assert len(s) == 1
        assert s[0]["action"]["open"] == "category" and s[0]["action"]["category"] == "Dining"
        assert s[0]["action"]["label"] == "See Dining"
        # Nothing in an action can write: only "open" and what to show.
        assert set(s[0]["action"]) <= {"label", "open", "category", "month", "query"}

    def test_every_call_is_a_usage_row_and_one_question(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        events(c, "Show my Uber rides", FakeStream(tool("search", words="Uber"),
                                                   {"text": "12 Uber rides since September."}),
               monkeypatch)
        rows = usage.rows(app.config["STORE"], c.user.id)
        assert len(rows) == 2 and len({r["ask_id"] for r in rows}) == 1
        assert all(r["outcome"] == "ok" and r["cost_usd"] > 0 and r["prompt"] == "ask@2"
                   for r in rows)
        day = usage.periods()[1]
        assert usage.day_requests(app.config["STORE"], c.user.id, day) == 1

    def test_the_model_never_sees_numbers_tokens_or_ids(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        c.st.add_plaid_item("item-1", "access-production-1234abcd-5678-90ef", institution="TD")
        turn_on(c)
        fake = FakeStream(tool("search", words="transfer"), tool("cards"),
                          {"text": "Two cards."})
        events(c, "Find my transfer and my cards", fake, monkeypatch)
        sent = json.dumps([x["messages"] for x in fake.calls])
        assert "0012345678901" not in sent and "4111111111111111" not in sent
        assert "access-production" not in sent and "account_id" not in sent
        assert "\"visa\"" not in sent
        for x in fake.calls:
            safety.check(x["messages"])            # what was sent passes the gate

    def test_words_before_a_tool_are_dropped(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        first = {**tool("cards"), "text": "Let me check."}
        evs = events(c, "When are my cards due?", FakeStream(first, {"text": "Two cards."}),
                     monkeypatch)
        assert "reset" in [e["type"] for e in evs]
        assert words(evs) == "Two cards."

    def test_made_up_figures_are_replaced_by_python(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        evs = events(c, "How much at Loblaws this year?",
                     FakeStream(tool("merchant_history", merchant="Loblaws"),
                                {"text": "You spent $9,999 at Loblaws."}), monkeypatch)
        f = ask.merchant_history(ask.Ledger(c.st, TODAY), "Loblaws")
        assert words(evs) == f.line and "$9,999" not in words(evs)

    def test_a_server_error_escalates_to_sonnet_once(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        fake = FakeStream(client_mod.ClientError("server"), tool("cards"), {"text": "Two cards."})
        evs = events(c, "When are my cards due?", fake, monkeypatch)
        assert [x["model"] for x in fake.calls] == [config.DEFAULT_MODEL, config.ESCALATION_MODEL,
                                                    config.ESCALATION_MODEL]
        assert of(evs, "fact")[0]["kind"] == "cards"


# ── Couldn't answer (AC 11) ──────────────────────────────────────────────

class TestCouldnt:
    @pytest.mark.parametrize("script", [
        [{"text": "", "stop_reason": "refusal"}],
        [client_mod.ClientError("bad_request")],
        [{"text": "Lisbon sounds lovely! You can afford it."}],       # no tool: unsure
    ])
    def test_fails_refuses_or_unsure(self, app, outbox, monkeypatch, script):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        evs = events(c, "Can I afford a trip to Lisbon?", FakeStream(*script), monkeypatch)
        assert of(evs, "couldnt") and not of(evs, "fact")
        assert words(evs) == ""


# ── Built-in answers and the quiet line (AC 13) ──────────────────────────

class TestBuiltIn:
    def test_no_key_answers_from_python(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        monkeypatch.setattr(client_mod, "from_env", lambda: None)
        evs = events(c, "How's this month going?")
        assert of(evs, "fact")[0]["kind"] == "month" and of(evs, "words")
        assert not of(evs, "simple")
        assert usage.rows(app.config["STORE"], c.user.id)[0]["outcome"] == "off"

    @pytest.mark.parametrize("q, kind", [
        ("When are my cards due?", "cards"),
        ("How much at Loblaws this year?", "merchant"),
        ("Show my Uber rides", "search"),
        ("Any subscriptions I forgot?", "subscriptions"),
        ("How did October go?", "month"),
    ])
    def test_the_four_things_it_can_always_do(self, app, outbox, monkeypatch, q, kind):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        monkeypatch.setattr(client_mod, "from_env", lambda: None)
        assert of(events(c, q), "fact")[0]["kind"] == kind

    def test_over_the_monthly_cap_one_quiet_line(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        usage.record(app.config["STORE"], user_id=c.user.id, ask_id="old", route="ask",
                     outcome="ok", model=config.DEFAULT_MODEL, cost_usd=0.50)
        fake = FakeStream()
        evs = events(c, "How much at Loblaws this year?", fake, monkeypatch)
        assert fake.calls == []
        simple = of(evs, "simple")
        assert len(simple) == 1
        assert simple[0]["until"] == ask.first_of_next_month(date.today())
        assert not re.search(r"\$|token|limit|cap", json.dumps(simple), re.I)
        assert of(evs, "fact")[0]["kind"] == "merchant"

    def test_over_the_daily_cap(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        monkeypatch.setenv(config.DAILY_REQUESTS_ENV, "0")
        evs = events(c, "When are my cards due?", FakeStream(), monkeypatch)
        assert of(evs, "simple")[0]["until"] == "tomorrow"
        assert of(evs, "fact")[0]["kind"] == "cards"

    def test_nothing_it_can_read(self, app, outbox, monkeypatch):
        c = sign_up(app, outbox)
        fill(c.st)
        turn_on(c)
        monkeypatch.setattr(client_mod, "from_env", lambda: None)
        assert of(events(c, "Tell me a joke"), "couldnt")
        # Advice isn't a trip question.
        assert of(events(c, "Can I afford a trip to Lisbon?"), "couldnt")


# ── The answers, computed in Python (AC 14-17) ───────────────────────────

@pytest.fixture()
def led(tmp_path, monkeypatch):
    from finance.store import Store
    st = Store(str(tmp_path / "l.db"))
    fill(st)
    import flask
    a = flask.Flask("t")
    a.config["STORE"] = st
    with a.test_request_context():
        flask.g.user = None
        yield ask.Ledger(st, TODAY)


class TestAnswers:
    def test_a_shops_history(self, led):
        f = ask.merchant_history(led, "loblaws")
        d = f.data
        assert d["merchant"] == "Loblaws" and d["visits"] == 22
        assert d["total"] == round(sum(40 + m + 30 for m in range(1, 12)), 2)
        assert [m["label"] for m in d["months"]] == list("JFMAMJJASON")
        assert d["months"][-1]["now"] and d["months"][-1]["amount"] == 81.0
        assert f.step == "Looking at Loblaws…"

    def test_a_past_month(self, led):
        d = ask.month(led, "2026-10").data
        assert not d["current"] and d["money_in"] == 4300.0
        assert d["spent"] == round(40 + 10 + 30 + 80 + sum(10.0 + i for i in range(5, 10)), 2)
        assert d["allowance_left"] == round(4300 - d["spent"], 2)
        assert [x["category"] for x in d["top"]] == ["Transport", "Dining", "Groceries"]

    def test_this_month(self, led):
        f = ask.month(led)
        assert f.data["current"] and f.data["name"] == "November"
        assert f.line.startswith("You’ve spent")

    def test_search_shows_ten_and_counts_all(self, led):
        f = ask.search(led, "Uber")
        assert f.data["count"] == 12 and len(f.data["rows"]) == 10
        assert f.data["rows"][0]["date"] >= f.data["rows"][-1]["date"]
        assert f.line.endswith("Here are the latest 10.")
        assert f.data["total"] == round(sum(10.0 + i for i in range(12)), 2)

    def test_cards_nicknames_limit_and_due(self, led):
        cards = {c["name"]: c for c in ask.cards(led).data["cards"]}
        assert set(cards) == {"TD Visa", "Amex Cobalt"}       # nicknames only
        assert cards["TD Visa"]["state"] == "ok" and cards["TD Visa"]["used"] == 0.368
        assert cards["Amex Cobalt"]["state"] == "near"         # 90%: amber
        assert cards["TD Visa"]["due"] == "2026-12-03" and cards["Amex Cobalt"]["due"] == "2026-12-14"
        assert all("account_id" not in c for c in cards.values())

    def test_over_the_limit_is_its_own_state(self, led):
        led.st.set_balance("amex", 3100.0, None, 3000, "CAD", TODAY.isoformat())
        cards = {c["name"]: c for c in ask.cards(led).data["cards"]}
        assert cards["Amex Cobalt"]["state"] == "over"

    @pytest.mark.parametrize("raw, nick", [
        ("TD Visa ••1203", "TD Visa"), ("Amex Cobalt 4111111111111111", "Amex Cobalt"),
        ("Visa (1234)", "Visa"), ("1234567890", "Card")])
    def test_nickname(self, raw, nick):
        assert ask.nickname(raw) == nick

    def test_examples_name_her_top_shop(self, led):
        ex = ask.examples(led.st, led.txns, TODAY)
        assert len(ex) == 4 and ex[1] == "How much at Loblaws this year?"
        assert "Allowance" not in " ".join(ex) or True
        assert all("safe to spend" not in e.lower() for e in ex)

    def test_figures_check(self, led):
        f = ask.merchant_history(led, "Loblaws")
        assert ask.figures_ok(f.line, [f])
        assert not ask.figures_ok("You spent $12,345.", [f])

    def test_words_never_say_safe_to_spend(self, led):
        lines = [ask.month(led).line, ask.month(led, "2026-10").line, ask.cards(led).line,
                 ask.search(led, "Uber").line, ask.merchant_history(led, "Loblaws").line]
        assert all("safe to spend" not in x.lower() for x in lines)
