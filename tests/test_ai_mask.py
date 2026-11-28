"""Masking in the AI gateway (AI Phase 2b, product owner 2026-11-27).

Her values reach the model only as placeholders ([AMT1], [DATE1],
[PERSON1], [CARD1], [SHOP1], [NUM1]), on every route; the reply is filled
back in on the server, and one that names an unknown placeholder or writes a
figure of its own falls back to Python. Smart sorting's `sort_reason` route
may send the shop name and nothing else. No network: a fake client.
"""

from __future__ import annotations

import json
import re

import pytest

from finance import users
from finance.ai import client as client_mod
from finance.ai import config, mask, router, safety, usage
from finance.store import Store

NOW = 1_795_000_000.0
KNOWN = {"shop": ["Loblaws", "Pai Northern Thai"], "person": ["Georgia Klev"],
         "card": ["TD Visa", "Amex Cobalt"]}
PLACEHOLDER = re.compile(r"\[(?:AMT|DATE|PERSON|CARD|SHOP|NUM)\d+\]")


class FakeClient:
    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def send(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
        safety.check(system, messages, tools or [])
        self.calls.append({"model": model, "messages": json.loads(json.dumps(messages))})
        step = dict(self.script.pop(0))
        step.setdefault("stop_reason", "end_turn")
        return client_mod.Reply(model=model, input_tokens=100, output_tokens=20, **step)


@pytest.fixture()
def base(tmp_path, monkeypatch):
    for env in (config.KEY_ENV, config.KILL_ENV, config.MONTHLY_CAP_ENV,
                config.DAILY_REQUESTS_ENV):
        monkeypatch.delenv(env, raising=False)
    usage._ready.clear()
    st = Store(str(tmp_path / "base.db"))
    users.ensure_table(st)
    yield st
    usage._ready.clear()


# ── The masker ───────────────────────────────────────────────────────────

class TestMasker:
    def test_each_kind_becomes_a_placeholder(self):
        m = mask.Masker(KNOWN)
        out = m.text("Georgia Klev paid $40.50 at loblaws on Nov 3 with my TD Visa, "
                     "12 times since 2025-10, in October 2025")
        assert "Georgia" not in out and "loblaws" not in out.lower() and "Visa" not in out
        assert not re.search(r"\d", PLACEHOLDER.sub("", out)), out
        assert set(re.findall(r"\[([A-Z]+)\d+\]", out)) == {"PERSON", "AMT", "SHOP", "DATE",
                                                             "CARD", "NUM"}

    def test_relative_words_and_categories_stay(self):
        m = mask.Masker(KNOWN)
        s = "How did Groceries go last month and this year, or on Saturday?"
        assert m.text(s) == s

    def test_stable_within_one_ask(self):
        m = mask.Masker(KNOWN)
        a = m.text("Loblaws $40")
        b = m.text("LOBLAWS again, $40")
        assert a == "[SHOP1] [AMT1]" and b == "[SHOP1] again, [AMT1]"
        assert m.fill("[SHOP1]") == "Loblaws"              # her spelling, not the model's

    def test_a_first_name_alone_is_masked(self):
        assert mask.Masker(KNOWN).text("Did Georgia pay?") == "Did [PERSON1] pay?"

    def test_keys_say_what_a_value_is(self):
        m = mask.Masker()                                    # nothing known by name
        got = m.value({"merchant": "Costco", "latest": [{"name": "Sobeys", "date": "Nov 2"}],
                       "cards": [{"name": "Scotia Gold"}], "people": ["Ana"],
                       "line": "Costco and Sobeys", "by_month": {"2026-01": "$3"},
                       "visits": 4, "year": 2026, "current": True})
        flat = json.dumps(got)
        for real in ("Costco", "Sobeys", "Scotia", "Ana", "Nov", "2026", "$3"):
            assert real not in flat, real
        assert got["line"] == f"{got['merchant']} and {got['latest'][0]['name']}"
        assert got["current"] is True
        assert got["year"].startswith("[DATE") and got["visits"].startswith("[NUM")

    def test_tool_input_is_filled_back_in(self):
        m = mask.Masker(KNOWN)
        m.text("at Loblaws in October")
        assert m.fill_value({"merchant": "[SHOP1]", "month": "[DATE1]", "n": 2}) == \
            {"merchant": "Loblaws", "month": "October", "n": 2}
        with pytest.raises(mask.UnknownPlaceholder):
            m.fill_value({"merchant": "[SHOP2]"})
        with pytest.raises(mask.UnknownPlaceholder):
            m.fill_value({"merchant": "[SHOP]"})

    @pytest.mark.parametrize("reply, why", [
        ("You spent [AMT1] at [SHOP1].", None),
        ("You spent [AMT7].", "mask_unknown"),
        ("You spent [MONEY1].", "mask_unknown"),
        ("You spent [AMT1] over 3 visits.", "mask_number"),
        ("That's $1,000.", "mask_number"),
        ("About [AMT1]0 a month.", "mask_number"),
        ("Twelve visits, more than usual.", None),
    ])
    def test_problem(self, reply, why):
        m = mask.Masker(KNOWN)
        m.text("Loblaws $40")
        assert m.problem(reply) == why

    def test_one_dollar_sign(self):
        m = mask.Masker()
        m.text("$40")
        assert m.fill("You spent $[AMT1].") == "You spent $40."
        assert m.fill("You spent [AMT1].") == "You spent $40."

    def test_the_stream_never_splits_a_placeholder(self):
        m = mask.Masker(KNOWN)
        m.text("Loblaws $40")
        gate = mask.ReplyGate(m)
        out = "".join(gate.feed(c) for c in ["You spent $", "[AM", "T1] at [", "SHOP1", "]."])
        out += gate.finish()
        assert out == "You spent $40 at Loblaws."

    def test_the_stream_stops_at_a_made_up_figure(self):
        m = mask.Masker(KNOWN)
        m.text("Loblaws")
        gate = mask.ReplyGate(m)
        shown = [gate.feed(c) for c in ["At [SHOP1] ", "you spent 4", "0 dollars."]]
        shown.append(gate.finish())
        assert "".join(shown) == "At Loblaws " and gate.bad == "mask_number"

    def test_account_numbers_are_still_refused(self):
        # Masking never hides a number the gateway must refuse.
        with pytest.raises(safety.UnsafePayload):
            safety.check([{"role": "user", "content": "Card 4111 1111 1111 1111"}])


# ── Every route, through the gateway ─────────────────────────────────────

def test_ask_masks_everything_and_fills_the_reply_back_in(base):
    fake = FakeClient({"text": "You spent [AMT1] at [SHOP1] with [PERSON1]."})
    q = [{"role": "user", "content": "Did I spend $81 at Loblaws with Georgia Klev on "
                                     "2026-11-05 on my TD Visa?"}]
    a = router.ask("ask", None, q, base=base, user_id=1, client=fake, now=NOW, known=KNOWN)
    sent = fake.calls[0]["messages"][0]["content"]
    assert sent == "Did I spend [AMT1] at [SHOP1] with [PERSON1] on [DATE1] on my [CARD1]?"
    assert a.ok and a.text == "You spent $81 at Loblaws with Georgia Klev."


@pytest.mark.parametrize("reply, outcome", [("You spent [AMT4].", "mask_unknown"),
                                            ("You spent $90.", "mask_number")])
def test_a_bad_reply_falls_back_and_is_recorded(base, reply, outcome):
    fake = FakeClient({"text": reply})
    q = [{"role": "user", "content": "How much at Loblaws?"}]
    a = router.ask("ask", None, q, base=base, user_id=1, client=fake, now=NOW, known=KNOWN)
    assert a.fall_back and a.reason == outcome and a.text == ""
    assert len(fake.calls) == 1                          # no bigger model for this
    assert usage.rows(base)[-1]["outcome"] == outcome


def test_tool_calls_come_back_filled_in(base):
    call = {"id": "t1", "name": "cards", "input": {"card": "[CARD1]"}}
    fake = FakeClient({"text": "", "tool_calls": [call], "stop_reason": "tool_use"})
    q = [{"role": "user", "content": "When is my TD Visa due?"}]
    tools = [{"name": "cards", "description": "Cards.", "input_schema": {"type": "object"}}]
    a = router.ask("ask", None, q, tools, base=base, user_id=1, client=fake, now=NOW,
                   known=KNOWN)
    assert a.ok and a.tool_calls[0]["input"] == {"card": "TD Visa"}


def test_sort_reason_sends_the_shop_name_and_nothing_else(base):
    """Smart sorting (Phase 4): the shop by name; no amount, date, person,
    card or count, even when the caller put them in."""
    assert config.ROUTES["sort_reason"]["mask"]["raw"] == ("shop",)
    fake = FakeClient({"text": "Looks like groceries at Loblaws."})
    q = [{"role": "user", "content": json.dumps({
        "shop": "Loblaws", "amount": "$81.00", "date": "2026-11-05", "people": ["Georgia Klev", "Ana"],
        "card": "TD Visa", "visits": 22, "note": "Georgia paid $40 on Nov 3 with Amex Cobalt"})}]
    a = router.ask("sort_reason", "ask@3", q, base=base, user_id=1, client=fake, now=NOW,
                   known=KNOWN)
    sent = json.dumps(fake.calls[0]["messages"])
    assert "Loblaws" in sent
    for real in ("81", "2026", "11-05", "Georgia", "Klev", "Ana", "TD Visa", "Amex", "Cobalt",
                 "22", "$40", "Nov 3"):
        assert real not in sent, real
    assert not re.search(r"\d", PLACEHOLDER.sub("", sent))
    assert a.ok and a.text == "Looks like groceries at Loblaws."


def test_sort_reason_has_its_own_frozen_prompt(base, monkeypatch):
    # Phase 4 (THL-309): sort_reason@1; a route without its prompt falls back.
    from finance.ai import prompts
    assert config.ROUTES["sort_reason"]["prompt"] == "sort_reason@1"
    text = prompts.load("sort_reason@1")
    assert "pick" in text and "[NUM1]" in text and " she " not in text
    monkeypatch.setitem(config.ROUTES["sort_reason"], "prompt", None)
    fake = FakeClient()
    a = router.ask("sort_reason", None, [{"role": "user", "content": "Loblaws"}], base=base,
                   user_id=1, client=fake, now=NOW)
    assert a.fall_back and a.reason == "no_prompt" and fake.calls == []


def test_every_route_has_an_allowlist_of_known_kinds():
    for name, cfg in config.ROUTES.items():
        raw = mask.policy(cfg)
        assert set(raw) <= set(mask.KINDS), name
    assert mask.policy(config.ROUTES["ask"]) == ()
    with pytest.raises(ValueError):
        mask.policy({"mask": {"raw": ("account_number",)}})


def test_no_route_may_send_an_account_number(base):
    for route in config.ROUTES:
        fake = FakeClient({"text": "ok"})
        q = [{"role": "user", "content": "Pay from 0012345678901"}]
        a = router.ask(route, "ask@3", q, base=base, user_id=1, client=fake, now=NOW)
        assert a.reason == "blocked" and fake.calls == [], route
