"""AI gateway, Phase 1 (AI plan v2, 2026-11-27): routing and escalation,
budget caps and the kill switch, AI off with no key, usage rows and cost
math, frozen prompts, data minimisation.

No network: every test uses FakeClient, and `anthropic` is never called.
"""

from __future__ import annotations

import ast
import os
import pathlib
import time

import pytest

from finance import users
from finance.ai import budget, client as client_mod, config, prompts, router, safety, usage
from finance.store import Store

ROOT = pathlib.Path(__file__).resolve().parent.parent
NOW = time.mktime((2026, 11, 27, 12, 0, 0, 0, 0, -1))
TOOLS = [
    {"name": "spending", "description": "Spending in a month.",
     "input_schema": {"type": "object", "properties": {"month": {"type": "string"}}}},
    {"name": "cards", "description": "Her cards.",
     "input_schema": {"type": "object", "properties": {}}},
]
QUESTION = [{"role": "user", "content": "How much did I spend on food in November?"}]


class FakeClient:
    """Stands in for client.Client: replays a script of replies or errors,
    one per call, and remembers what it was sent."""

    def __init__(self, *script):
        self.script = list(script)
        self.calls = []

    def send(self, *, model, system, messages, tools=None, max_tokens=1024, effort="low"):
        safety.check(system, messages, tools or [])
        self.calls.append({"model": model, "system": system, "messages": messages,
                           "tools": tools, "max_tokens": max_tokens, "effort": effort})
        step = self.script.pop(0)
        if isinstance(step, Exception):
            raise step
        step = dict(step)
        step.setdefault("stop_reason", "end_turn")
        return client_mod.Reply(model=model, **step)


def ok(text="You spent $412.30 on food in November.", **kw):
    base = {"text": text, "input_tokens": 120, "cache_read_tokens": 900,
            "cache_write_tokens": 0, "output_tokens": 40, "request_id": "req_1"}
    base.update(kw)
    return base


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


def ask(base, fake, **kw):
    kw.setdefault("user_id", 1)
    tools = kw.pop("tools", TOOLS)
    return router.ask("ask", None, QUESTION, tools, base=base, client=fake, now=NOW, **kw)


# ── Routing and escalation ───────────────────────────────────────────────

def test_haiku_answers_by_default(base):
    fake = FakeClient(ok())
    a = ask(base, fake)
    assert a.ok and not a.fall_back and a.model == "claude-haiku-5-5"
    assert a.text.startswith("You spent")
    assert [c["model"] for c in fake.calls] == ["claude-haiku-5-5"]
    assert fake.calls[0]["system"] == prompts.load("ask@1")
    assert fake.calls[0]["effort"] == "low"


def test_model_ids_live_only_in_config():
    for path in (ROOT / "finance").rglob("*.py"):
        if path.name == "config.py" and path.parent.name == "ai":
            continue
        src = path.read_text(encoding="utf-8")
        assert "claude-haiku" not in src and "claude-sonnet" not in src, path
    assert config.DEFAULT_MODEL == "claude-haiku-5-5"
    assert config.ESCALATION_MODEL == "claude-sonnet-5-5"


@pytest.mark.parametrize("kind", ["server", "timeout", "connection"])
def test_a_failed_call_escalates_to_sonnet_once(base, kind):
    fake = FakeClient(client_mod.ClientError(kind), ok())
    a = ask(base, fake)
    assert a.ok and a.model == "claude-sonnet-5-5" and a.attempts == 2
    assert [c["model"] for c in fake.calls] == ["claude-haiku-5-5", "claude-sonnet-5-5"]
    got = usage.rows(base)
    assert [r["outcome"] for r in got] == [f"error:{kind}", "ok"]
    assert len({r["ask_id"] for r in got}) == 1


def test_both_failing_falls_back(base):
    fake = FakeClient(client_mod.ClientError("server"), client_mod.ClientError("server"))
    a = ask(base, fake)
    assert a.fall_back and a.reason == "error:server" and a.text == ""


@pytest.mark.parametrize("kind", ["bad_request", "auth", "permission", "not_found",
                                  "rate_limited", "other"])
def test_errors_a_bigger_model_cannot_fix_fall_back_without_escalating(base, kind):
    fake = FakeClient(client_mod.ClientError(kind))
    a = ask(base, fake)
    assert a.fall_back and a.reason == f"error:{kind}"
    assert len(fake.calls) == 1


def test_a_tool_call_to_no_offered_tool_escalates(base):
    bad = ok(text="", stop_reason="tool_use",
             tool_calls=[{"id": "t1", "name": "move_money", "input": {}}])
    good = ok(text="", stop_reason="tool_use",
              tool_calls=[{"id": "t2", "name": "spending", "input": {"month": "2026-11"}}])
    fake = FakeClient(bad, good)
    a = ask(base, fake)
    assert a.ok and a.model == "claude-sonnet-5-5"
    assert a.tool_calls[0]["name"] == "spending"
    assert [r["outcome"] for r in usage.rows(base)] == ["bad_tool", "ok"]


def test_a_tool_call_the_caller_rejects_escalates(base):
    call = ok(text="", stop_reason="tool_use",
              tool_calls=[{"id": "t1", "name": "spending", "input": {"month": "nope"}}])
    fake = FakeClient(call, call)
    a = ask(base, fake, valid_tool=lambda c: c["input"].get("month", "").startswith("20"))
    assert a.fall_back and a.reason == "bad_tool" and len(fake.calls) == 2


def test_low_confidence_escalates_then_accepts(base):
    fake = FakeClient(ok(text="maybe?"), ok(text="Groceries."))
    a = ask(base, fake, accept=lambda r: not r.text.endswith("?"))
    assert a.ok and a.text == "Groceries." and a.model == "claude-sonnet-5-5"


def test_a_refusal_falls_back_without_escalating(base):
    fake = FakeClient(ok(text="", stop_reason="refusal"))
    a = ask(base, fake)
    assert a.fall_back and a.reason == "refusal" and len(fake.calls) == 1
    assert usage.rows(base)[0]["stop_reason"] == "refusal"


def test_a_cut_off_answer_falls_back_without_escalating(base):
    fake = FakeClient(ok(text="You spent", stop_reason="max_tokens"))
    a = ask(base, fake)
    assert a.fall_back and a.reason == "max_tokens" and a.text == ""
    assert len(fake.calls) == 1


def test_an_unknown_route_falls_back(base):
    a = router.ask("nope", None, QUESTION, base=base, user_id=1, client=FakeClient(), now=NOW)
    assert a.fall_back and a.reason == "no_route"


# ── No key: AI is off ────────────────────────────────────────────────────

def test_no_key_means_no_client(monkeypatch):
    monkeypatch.delenv(config.KEY_ENV, raising=False)
    assert client_mod.from_env() is None
    monkeypatch.setenv(config.KEY_ENV, "   ")
    assert client_mod.from_env() is None


def test_no_key_falls_back_and_never_calls(base):
    a = router.ask("ask", None, QUESTION, TOOLS, base=base, user_id=1, now=NOW)
    assert a.fall_back and a.reason == "off"
    row = usage.rows(base)[0]
    assert row["outcome"] == "off" and row["model"] is None and row["cost_usd"] == 0


def test_a_key_builds_the_sdk_client_without_calling(monkeypatch):
    pytest.importorskip("anthropic")
    monkeypatch.setenv(config.KEY_ENV, "test-key-not-real")
    c = client_mod.from_env()
    assert isinstance(c, client_mod.Client)


# ── Budget caps and the kill switch ──────────────────────────────────────

def _spend(base, user_id, dollars, now=NOW, outcome="ok"):
    usage.record(base, user_id=user_id, ask_id=os.urandom(8).hex(), route="ask",
                 model=config.DEFAULT_MODEL, prompt="ask@1", cost_usd=dollars,
                 outcome=outcome, now=now)


def test_the_monthly_cap_is_fifty_cents():
    # Set by the product owner, 2026-11-27.
    assert config.MONTHLY_CAP_USD_DEFAULT == 0.50
    assert config.monthly_cap_usd() == 0.50


def test_a_user_at_fifty_cents_falls_back(base):
    _spend(base, 1, 0.30)
    _spend(base, 1, 0.20)
    fake = FakeClient(ok())
    a = ask(base, fake)
    assert a.fall_back and a.reason == "over_budget" and fake.calls == []
    assert usage.rows(base)[-1]["outcome"] == "over_budget"


def test_just_under_the_cap_still_asks(base):
    _spend(base, 1, 0.4999)
    assert ask(base, FakeClient(ok())).ok


def test_the_cap_is_per_user_and_per_month(base):
    _spend(base, 1, 0.60)
    _spend(base, 2, 0.60, now=NOW - 40 * 86400)          # last month's
    assert ask(base, FakeClient(ok()), user_id=2).ok
    assert ask(base, FakeClient(ok()), user_id=1).reason == "over_budget"


def test_the_cap_can_be_set_from_the_environment(base, monkeypatch):
    monkeypatch.setenv(config.MONTHLY_CAP_ENV, "0.10")
    _spend(base, 1, 0.10)
    assert ask(base, FakeClient(ok())).reason == "over_budget"
    monkeypatch.setenv(config.MONTHLY_CAP_ENV, "not a number")
    assert config.monthly_cap_usd() == 0.50


def test_the_daily_request_cap(base, monkeypatch):
    monkeypatch.setenv(config.DAILY_REQUESTS_ENV, "2")
    assert ask(base, FakeClient(ok())).ok
    assert ask(base, FakeClient(client_mod.ClientError("server"), ok())).ok  # one question
    a = ask(base, FakeClient(ok()))
    assert a.fall_back and a.reason == "over_daily"


def test_fallbacks_do_not_count_towards_the_daily_cap(base, monkeypatch):
    monkeypatch.setenv(config.DAILY_REQUESTS_ENV, "1")
    _spend(base, 1, 0, outcome="off")
    _spend(base, 1, 0, outcome="over_budget")
    assert ask(base, FakeClient(ok())).ok


def test_escalation_rechecks_the_budget(base):
    # Haiku's answer itself takes her to the cap ($0.50 of output), so the
    # Sonnet retry is never sent.
    pricey = ok(text="maybe?", output_tokens=1_000_000)
    fake = FakeClient(pricey, ok())
    a = ask(base, fake, accept=lambda r: not r.text.endswith("?"))
    assert a.fall_back and a.reason == "over_budget"
    assert [c["model"] for c in fake.calls] == ["claude-haiku-5-5"]
    assert [r["outcome"] for r in usage.rows(base)] == ["low_confidence", "over_budget"]


def test_kill_switch_from_the_environment(base, monkeypatch):
    monkeypatch.setenv(config.KILL_ENV, "1")
    fake = FakeClient(ok())
    a = ask(base, fake)
    assert a.fall_back and a.reason == "killed" and fake.calls == []


def test_kill_switch_without_a_redeploy(base):
    budget.set_killed(base, True)
    assert ask(base, FakeClient(ok())).reason == "killed"
    budget.set_killed(base, False)
    assert ask(base, FakeClient(ok())).ok


def test_budget_never_raises_and_fails_closed(base, monkeypatch):
    def boom(*a, **k):
        raise RuntimeError("database gone")
    monkeypatch.setattr(usage, "month_cost", boom)
    v = budget.check(base, 1, now=NOW)
    assert v.fall_back and v.reason == "over_budget"


# ── Usage rows and cost math ─────────────────────────────────────────────

def test_cost_math_haiku():
    # 1,000 uncached in, 9,000 cache reads, 2,000 cache writes, 500 out.
    got = config.cost_usd("claude-haiku-5-5", 1000, 9000, 2000, 500)
    want = (1000 * 0.10 + 9000 * 0.10 * 0.1 + 2000 * 0.10 * 1.25 + 500 * 0.50) / 1e6
    assert got == pytest.approx(want)


def test_cost_math_sonnet_batch_and_long_prompts():
    assert config.cost_usd("claude-sonnet-5-5", 1_000_000, 0, 0, 100_000) == pytest.approx(3.0)
    assert config.cost_usd("claude-sonnet-5-5", 1_000_000, 0, 0, 100_000,
                           batch=True) == pytest.approx(1.5)
    # Haiku over 100K tokens of prompt uses the second rate card.
    assert config.cost_usd("claude-haiku-5-5", 200_000, 0, 0, 0) == pytest.approx(0.10)
    assert config.cost_usd("unknown-model", 1000, 0, 0, 1000) == 0.0


def test_a_typical_question_costs_a_fraction_of_a_cent():
    # About 4k in (mostly cached), 300 out: the plan's measuring stick.
    assert config.cost_usd("claude-haiku-5-5", 400, 3600, 0, 300) < 0.0003


def test_a_usage_row_records_everything(base):
    fake = FakeClient(ok(input_tokens=200, cache_read_tokens=3000, cache_write_tokens=500,
                         output_tokens=80, request_id="req_abc"))
    a = ask(base, fake, user_id=7)
    (row,) = usage.rows(base)
    assert row["user_id"] == 7 and row["route"] == "ask"
    assert row["model"] == "claude-haiku-5-5" and row["prompt"] == "ask@1"
    assert (row["input_tokens"], row["cache_read_tokens"], row["cache_write_tokens"],
            row["output_tokens"]) == (200, 3000, 500, 80)
    assert row["cost_usd"] == pytest.approx(config.cost_usd("claude-haiku-5-5", 200, 3000, 500, 80))
    assert a.cost_usd == pytest.approx(row["cost_usd"])
    assert row["outcome"] == "ok" and row["stop_reason"] == "end_turn"
    assert row["request_id"] == "req_abc" and row["latency_ms"] >= 0
    assert row["month"] == "2026-11" and row["day"] == "2026-11-27"


def test_usage_rows_do_not_move_the_ledger_version(base):
    before = base.version()
    ask(base, FakeClient(ok()))
    assert base.version() == before


def test_summary_cost_per_user_and_escalation_rate(base):
    ask(base, FakeClient(ok()), user_id=1)
    ask(base, FakeClient(client_mod.ClientError("server"), ok()), user_id=1)
    ask(base, FakeClient(ok()), user_id=2)
    budget.set_killed(base, True)
    ask(base, FakeClient(ok()), user_id=2)
    s = usage.summary(base, "2026-11")
    by = {u["user_id"]: u for u in s["per_user"]}
    assert by[1]["asked"] == 2 and by[1]["escalated"] == 1 and by[1]["escalation_rate"] == 0.5
    assert by[2]["asked"] == 1 and by[2]["skipped"] == 1
    assert s["asked"] == 3 and s["escalated"] == 1
    assert s["escalation_rate"] == pytest.approx(0.3333, abs=1e-4)
    assert s["total_cost_usd"] == pytest.approx(sum(r["cost_usd"] for r in usage.rows(base)),
                                                abs=1e-6)
    assert usage.summary(base, "2026-10")["per_user"] == []


def test_usage_is_kept_with_the_account_list_not_a_ledger(base):
    # account_deletion empties every non-app_ table of the shared database;
    # the bill must survive that.
    ask(base, FakeClient(ok()))
    from finance import account_deletion
    assert "app_ai_usage" not in account_deletion._ledger_tables(base)


# ── Prompts ──────────────────────────────────────────────────────────────

def test_prompts_load_by_id_and_version():
    text = prompts.load("ask@1")
    assert "Allowance" in text and "Never say \"safe to spend\"" in text
    assert prompts.published() == ["ask@1"]


@pytest.mark.parametrize("ref", ["ask", "ask@0", "ask@v1", "ask@2", "../ask@1", ""])
def test_unknown_or_malformed_prompts_are_refused(ref):
    with pytest.raises(prompts.PromptError):
        prompts.load(ref)


def test_published_prompts_are_frozen_and_cache_friendly():
    import hashlib
    import re
    for ref, digest in prompts.FROZEN.items():
        raw = pathlib.Path(prompts.path(ref)).read_bytes()
        assert hashlib.sha256(raw).hexdigest() == digest, f"{ref} changed: add a new version"
        text = raw.decode()
        assert not re.search(r"\b20\d\d-\d\d-\d\d\b|\{\{|\{[a-z_]+\}", text), ref
        assert "safe to spend" not in text.lower().replace('never say "safe to spend"', "")


def test_vercel_ships_the_prompt_files():
    # The .md prompts aren't Python, so Vercel's bundle leaves them out unless
    # includeFiles names them; without them the gateway falls back ("no_prompt").
    import json
    root = pathlib.Path(__file__).resolve().parents[1]
    inc = json.loads((root / "vercel.json").read_text())["functions"]["app.py"]["includeFiles"]
    assert "public/**" in inc and "finance/ai/prompts/**" in inc


def test_every_route_names_a_published_prompt():
    for name, cfg in config.ROUTES.items():
        assert cfg["prompt"] in prompts.FROZEN, name
        assert cfg["effort"] in ("low", "medium", "high")


def test_a_changed_prompt_falls_back(base, monkeypatch):
    monkeypatch.setitem(prompts.FROZEN, "ask@1", "0" * 64)
    prompts.load.cache_clear()
    try:
        assert ask(base, FakeClient(ok())).reason == "no_prompt"
    finally:
        monkeypatch.undo()
        prompts.load.cache_clear()


def test_requests_are_laid_out_for_the_cache():
    a = client_mod.build_request("m", "SYSTEM", QUESTION, list(reversed(TOOLS)), 100, "low")
    b = client_mod.build_request("m", "SYSTEM", QUESTION, TOOLS, 100, "low")
    assert a == b                                           # tool order is deterministic
    assert [t["name"] for t in a["tools"]] == ["cards", "spending"]
    assert a["system"] == [{"type": "text", "text": "SYSTEM",
                            "cache_control": {"type": "ephemeral"}}]
    assert a["output_config"] == {"effort": "low"}
    assert "temperature" not in a and "thinking" not in a


# ── Data minimisation ────────────────────────────────────────────────────

@pytest.mark.parametrize("text", [
    "my account 004512345678 has",
    "card 4111 1111 1111 1111",
    "card 4111-1111-1111-1111",
    "token access-sandbox-1b2c3d4e-aaaa-bbbb-cccc-1234567890ab",
    "public-production-9f8e7d6c-1111",
    "key sk-ant-api03-abcdefghijklmnopqrstuvwxyz",
])
def test_account_numbers_and_tokens_are_refused(text):
    with pytest.raises(safety.UnsafePayload):
        safety.check([{"role": "user", "content": text}])


@pytest.mark.parametrize("text", [
    "You spent $1,234.56 at Corner Grocer on 2026-11-27.",
    "Card ending 1234, 3 payments, Nov 3.",
    "$12,345,678.90 is a lot",
])
def test_ordinary_answers_pass(text):
    safety.check([{"role": "user", "content": text}])


def test_forbidden_keys_are_refused_whatever_their_value():
    for key in ("access_token", "account_number", "plaid_item", "routing", "item_id"):
        with pytest.raises(safety.UnsafePayload):
            safety.check([{"role": "user", "content": [{"type": "text", "text": "hi",
                                                         key: "x"}]}])


def test_redact_keeps_the_last_four():
    assert safety.redact("acct 004512345678 card 4111 1111 1111 1234") == \
        "acct ••••5678 card ••••1234"
    safety.check(safety.redact("token access-sandbox-1b2c3d4e-aaaa-bbbb"))


def test_an_unsafe_question_never_reaches_the_model(base):
    fake = FakeClient(ok())
    a = router.ask("ask", None, [{"role": "user", "content": "acct 004512345678"}], TOOLS,
                   base=base, user_id=1, client=fake, now=NOW)
    assert a.fall_back and a.reason == "blocked" and fake.calls == []
    assert usage.rows(base)[0]["outcome"] == "blocked"


def test_the_real_client_checks_before_sending(monkeypatch):
    pytest.importorskip("anthropic")
    c = client_mod.Client("test-key-not-real")

    def no_network(**kw):
        raise AssertionError("must not be called")
    monkeypatch.setattr(c._client.messages, "create", no_network)
    with pytest.raises(safety.UnsafePayload):
        c.send(model=config.DEFAULT_MODEL, system="s",
               messages=[{"role": "user", "content": "access-production-12345678abcd"}])


# ── The SDK's errors map to plain kinds ──────────────────────────────────

def test_sdk_errors_map_to_kinds(monkeypatch):
    anthropic = pytest.importorskip("anthropic")
    import httpx2

    req = httpx2.Request("POST", "https://api.anthropic.com/v1/messages")

    def status(cls, code):
        return cls("x", response=httpx2.Response(code, request=req), body=None)

    cases = [
        (status(anthropic.BadRequestError, 400), "bad_request"),
        (status(anthropic.AuthenticationError, 401), "auth"),
        (status(anthropic.PermissionDeniedError, 403), "permission"),
        (status(anthropic.NotFoundError, 404), "not_found"),
        (status(anthropic.RateLimitError, 429), "rate_limited"),
        (status(anthropic.InternalServerError, 500), "server"),
        (status(anthropic.APIStatusError, 529), "server"),
        (status(anthropic.APIStatusError, 418), "other"),
        (anthropic.APITimeoutError(request=req), "timeout"),
        (anthropic.APIConnectionError(request=req), "connection"),
    ]
    c = client_mod.Client("test-key-not-real")
    for err, kind in cases:
        def raise_it(**kw):
            raise err
        monkeypatch.setattr(c._client.messages, "create", raise_it)
        with pytest.raises(client_mod.ClientError) as got:
            c.send(model=config.DEFAULT_MODEL, system="s", messages=QUESTION)
        assert got.value.kind == kind, type(err)


def test_a_reply_reads_usage_and_refusals():
    from types import SimpleNamespace as NS
    msg = NS(model="claude-haiku-5-5", stop_reason="refusal",
             stop_details=NS(category="cyber"),
             content=[NS(type="thinking", thinking=""), NS(type="text", text="No.")],
             usage=NS(input_tokens=10, cache_read_input_tokens=None,
                      cache_creation_input_tokens=5, output_tokens=2))
    r = client_mod.to_reply(msg)
    assert (r.text, r.stop_reason, r.refusal_category) == ("No.", "refusal", "cyber")
    assert (r.input_tokens, r.cache_read_tokens, r.cache_write_tokens,
            r.output_tokens) == (10, 0, 5, 2)


# ── Only finance/ai/ talks to Anthropic ──────────────────────────────────

def _imports(path):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            yield from (a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            yield node.module.split(".")[0]


def test_only_finance_ai_imports_anthropic():
    ai_dir = ROOT / "finance" / "ai"
    offenders = []
    for path in [ROOT / "app.py", *(ROOT / "finance").rglob("*.py"), *(ROOT / "tests").rglob("*.py")]:
        if ai_dir in path.parents or path.name == "test_ai_gateway.py":
            continue
        if "anthropic" in set(_imports(path)):
            offenders.append(str(path.relative_to(ROOT)))
    assert offenders == []
    assert "anthropic" in set(_imports(ai_dir / "client.py"))


def test_no_endpoint_exposes_ai_yet():
    # Phase 2 adds /api/ask; Phase 1 is server plumbing only.
    src = (ROOT / "app.py").read_text(encoding="utf-8")
    assert "finance.ai" not in src and "/api/ask" not in src


def test_anthropic_is_a_requirement():
    reqs = (ROOT / "requirements.txt").read_text(encoding="utf-8")
    assert any(line.startswith("anthropic") for line in reqs.splitlines())
