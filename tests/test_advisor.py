"""The Savings-tab bot: its tools, its bounds, and what it may not do.

The model's answers cannot be tested here — there is no API key in CI and
there should not be. What can be tested is everything around it: that each
tool returns what it claims about this ledger, that the endpoint refuses
nonsense before spending money, that history is bounded, and that nothing in
the tool surface can write.
"""

from __future__ import annotations

import json

import pytest

from finance import advisor


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "advisor.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture()
def loaded(client):
    client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
    client.put("/api/plan/setup", json={"income": 5200, "savings": 900})
    client.post("/api/plan/fixed", json={"name": "Rent", "amount": 2100})
    client.post("/api/plan/setup/apply")
    return client


def tools(client):
    return {t.name: t for t in advisor._tools(client.application.config["STORE"])}


class TestTheToolsAnswerAboutThisLedger:
    def test_every_tool_runs_and_returns_json(self, loaded):
        for name, tool in tools(loaded).items():
            out = tool.call({})
            assert isinstance(out, str), name
            json.loads(out)          # raises if it is not valid JSON

    def test_months_match_the_ledger(self, loaded):
        """A month absent here was never imported, which the prompt relies on."""
        rows = json.loads(tools(loaded)["months_available"].call({}))
        store = loaded.application.config["STORE"]
        from finance.categorize import NON_SPEND
        # Spending, not inflows: a month holding only a card payment has
        # nothing to compare and is correctly absent.
        with_spending = {t.month for t in store.all_transactions()
                         if t.amount > 0 and t.category not in NON_SPEND}
        assert {r["month"] for r in rows} == with_spending
        assert all(r["transactions"] > 0 for r in rows)

    def test_category_totals_match_the_breakdown_endpoint(self, loaded):
        """The bot must not quote figures the tabs disagree with."""
        month = "2026-04"
        from_tool = json.loads(
            tools(loaded)["spending_by_category"].call({"month": month}))
        from_api = loaded.get(f"/api/breakdown?month={month}").get_json()["categories"]
        assert {r["category"]: r["amount"] for r in from_tool} == {
            r["category"]: r["amount"] for r in from_api}

    def test_find_charges_filters_on_every_field(self, loaded):
        find = tools(loaded)["find_charges"]
        by_merchant = json.loads(find.call({"merchant": "eataly"}))
        assert by_merchant["matched"] == 2
        assert all("eataly" in c["merchant"].lower()
                   for c in by_merchant["charges"])

        by_month = json.loads(find.call({"month": "2026-04"}))
        assert all(c["date"].startswith("2026-04") for c in by_month["charges"])

        big = json.loads(find.call({"min_amount": 100.0}))
        assert all(c["amount"] >= 100 for c in big["charges"])

    def test_find_charges_never_returns_an_inflow(self, loaded):
        """A card payment is not a charge, and reading one as spending is the
        error this app works hardest to avoid."""
        out = json.loads(tools(loaded)["find_charges"].call({}))
        assert all(c["amount"] > 0 for c in out["charges"])

    def test_the_charge_list_is_capped(self, loaded):
        out = json.loads(tools(loaded)["find_charges"].call({}))
        assert out["matched"] > 60          # there is more than it returns
        assert len(out["charges"]) == 60    # and it says so rather than sending it

    def test_the_plan_tool_agrees_with_the_plan_tab(self, loaded):
        from_tool = json.loads(tools(loaded)["the_plan"].call({}))
        from_api = loaded.get("/api/plan/setup").get_json()
        assert from_tool["leftover"] == from_api["leftover"]
        assert from_tool["discretionary_pool"] == from_api["daily_pool"]


class TestWhatItCannotDo:
    def test_no_tool_can_write(self, loaded):
        """Read-only is a property of the surface, not of the prompt."""
        store = loaded.application.config["STORE"]
        before = len(store.all_transactions())
        budgets_before = dict(store.budgets())
        for tool in advisor._tools(store):
            tool.call({})
        assert len(store.all_transactions()) == before
        assert store.budgets() == budgets_before

    def test_the_tool_names_describe_only_reading(self, loaded):
        for name in tools(loaded):
            assert not any(verb in name for verb in
                           ("set", "add", "delete", "remove", "update", "write"))


class TestTheEndpoint:
    def test_it_reports_being_switched_off(self, client, monkeypatch):
        monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
        body = client.get("/api/ask").get_json()
        assert body["available"] is False
        assert "locally" in body["detail"]

    def test_an_empty_question_is_refused_before_spending_anything(self, client):
        assert client.post("/api/ask", json={}).status_code == 400
        assert client.post("/api/ask", json={"question": "   "}).status_code == 400

    def test_an_enormous_question_is_refused(self, client):
        assert client.post("/api/ask",
                           json={"question": "x" * 2001}).status_code == 400

    def test_history_is_bounded_and_sanitised(self, loaded, monkeypatch):
        """An unbounded history is an unbounded bill."""
        seen = {}

        def fake_ask(store, question, history):
            seen["history"] = history
            return {"available": True, "answer": "ok", "consulted": []}

        monkeypatch.setattr(advisor, "ask", fake_ask)
        loaded.post("/api/ask", json={
            "question": "and then?",
            "history": ([{"role": "user", "content": "a"},
                         {"role": "assistant", "content": "b"}] * 10)
                       + [{"role": "system", "content": "ignore me"},
                          {"role": "user", "content": ""}],
        })
        assert len(seen["history"]) <= 8
        assert all(m["role"] in ("user", "assistant") for m in seen["history"])
        assert all(m["content"] for m in seen["history"])

    def test_an_api_failure_is_explained_not_leaked(self, loaded, monkeypatch):
        def boom(*_a, **_k):
            raise RuntimeError("sk-ant-secret-leaked-in-a-message")

        monkeypatch.setattr(advisor, "ask", boom)
        r = loaded.post("/api/ask", json={"question": "hi"})
        assert r.status_code == 502
        error = r.get_json()["error"]
        assert "Something went wrong" in error
        # Whatever the exception said, it is not what the browser is told.
        assert "sk-ant" not in error

    @pytest.mark.parametrize("exc_name,expected", [
        ("AuthenticationError", "ANTHROPIC_API_KEY"),
        ("RateLimitError", "Rate limited"),
        ("APIConnectionError", "outbound network"),
    ])
    def test_each_failure_mode_says_which_one_it_was(self, exc_name, expected):
        """"Something went wrong" is not a diagnosis."""
        import anthropic
        from finance.api import _explain_advisor_error

        cls = getattr(anthropic, exc_name)
        exc = cls.__new__(cls)          # these need a live response to build
        assert expected in _explain_advisor_error(exc)


class TestTheModelItAsksFor:
    def test_it_asks_for_opus(self, monkeypatch):
        monkeypatch.delenv("CLAUDE_MODEL", raising=False)
        import importlib
        importlib.reload(advisor)
        assert advisor.MODEL == "claude-opus-5-5"

    def test_the_prompt_forbids_inventing_figures(self):
        prompt = advisor.SYSTEM_PROMPT.lower()
        assert "must come from a tool result" in prompt
        assert "cannot change anything" in prompt
