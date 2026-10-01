"""A bot you can ask about your own spending.

The rule engine on the Savings tab finds what it was written to find. This is
for the rest: the questions nobody could enumerate in advance — "why was May
so expensive", "what changed since I started tracking", "is the gym worth it
given how little I go".

It is given tools rather than a dump of the ledger, which matters for three
reasons. It can look things up it was not handed, so a follow-up question
works. It cites figures it actually read instead of ones it remembered. And
what leaves this machine is bounded by what the tools return, which is
aggregates and the fields of a charge — a date, a merchant, an amount, a
category. There are no account numbers in this ledger to send, and nothing
here sends a card name or a bank connection.

It is advisory and it says so. Every number on every other tab is computed
locally by code you can read; nothing here writes to the ledger, changes a
budget, or moves money. The worst a wrong answer can do is be wrong.
"""

from __future__ import annotations

import json
import os

from anthropic import beta_tool

# Opus for this: the useful questions are comparative and multi-step — "is
# this worth it given how little I use it" is a different kind of work from
# summarising a table, and a thin answer to a money question is worse than no
# answer.
MODEL = os.environ.get("CLAUDE_MODEL", "claude-opus-5-5")
MAX_TOKENS = 8000
MAX_TURNS = 12

SYSTEM_PROMPT = """You are a plain-spoken financial analyst with read-only \
access to one person's own card spending, through the tools provided.

How to work:

- Look things up. You have tools for categories, merchants, individual \
charges, monthly totals, budgets, subscriptions and their spending plan. Call \
them rather than guessing, and call them again for a follow-up question.
- Every figure you cite must come from a tool result. If a tool returns \
nothing, say so rather than estimating.
- Answer the question asked, then stop. No preamble, no recap of what they \
just asked, no closing offer of further help.
- Be concrete: name merchants, months and amounts.
- Short paragraphs. No headings or bullet lists unless comparing three or \
more things.

What to be careful about:

- Their ledger may not be complete. Months before their chosen start date are \
excluded deliberately, and a gap in the data is not a month of no spending — \
check the months available before comparing periods.
- Card payments and transfers are not spending; they are already excluded \
from the totals the tools return. Do not count a payment as income.
- Treat them as an adult making deliberate trade-offs. No moralising about \
coffee, no praise for restraint, and never suggest they spend something they \
have not spent. If the honest answer is "this is fine", say that.
- You cannot change anything — no budgets, no categories, no transactions. If \
they ask you to, tell them which tab does it."""


def is_available() -> bool:
    return bool(os.environ.get("ANTHROPIC_API_KEY"))


def status() -> dict:
    if is_available():
        return {"available": True, "model": MODEL,
                "detail": "Ask about anything in your ledger."}
    return {
        "available": False,
        "model": MODEL,
        "detail": "Set ANTHROPIC_API_KEY in the project's environment "
                  "variables and redeploy. Everything else on this tab is "
                  "computed locally and works without it.",
    }


def _tools(store):
    """Read-only views of the ledger, as tools.

    Defined inside a function so each one closes over the store for this
    request. None of them writes; there is deliberately no tool that can.
    """
    from . import money_plan
    from .analytics import by_category, by_merchant, monthly_totals
    from .analytics import budget_status as budget_rows
    from .insights import detect_recurring, generate_findings

    @beta_tool
    def months_available() -> str:
        """List the months the ledger has data for, with each month's total
        spending. Call this first when comparing periods — a month that is
        absent was never imported, which is not the same as a month of no
        spending."""
        rows = monthly_totals(store.all_transactions())
        return json.dumps([
            {"month": r["month"], "spend": r["spend"],
             "transactions": r["transactions"]}
            for r in rows if r["transactions"] > 0])

    @beta_tool
    def spending_by_category(month: str = "") -> str:
        """Spending per category, largest first. `month` as "2026-05", or
        empty for all time. Card payments and transfers are already excluded."""
        return json.dumps(by_category(store.all_transactions(), month or None)[:30])

    @beta_tool
    def top_merchants(month: str = "", limit: int = 15) -> str:
        """The merchants with the most spending, largest first. `month` as
        "2026-05", or empty for all time."""
        rows = by_merchant(store.all_transactions(), month or None)
        return json.dumps(rows[:max(1, min(limit, 50))])

    @beta_tool
    def find_charges(merchant: str = "", month: str = "",
                     category: str = "", min_amount: float = 0.0) -> str:
        """Individual charges matching any combination of a merchant substring,
        a month ("2026-05"), a category, and a minimum amount. Returns at most
        60, newest first, with date, merchant, amount and category."""
        rows = []
        for t in store.all_transactions():
            if t.amount <= 0 or t.amount < min_amount:
                continue
            if month and t.month != month:
                continue
            if category and (t.category or "") != category:
                continue
            if merchant and merchant.lower() not in (t.merchant or "").lower():
                continue
            rows.append({"date": t.date, "merchant": t.merchant,
                         "amount": round(t.amount, 2),
                         "category": t.category or "Other"})
        rows.sort(key=lambda r: r["date"], reverse=True)
        return json.dumps({"matched": len(rows), "charges": rows[:60]})

    @beta_tool
    def subscriptions() -> str:
        """Recurring charges detected by cadence and amount stability, with
        what each costs per year and whether it is still arriving."""
        rows = detect_recurring(store.all_transactions())
        return json.dumps([
            {k: r[k] for k in ("merchant", "category", "cadence", "amount",
                               "annual_cost", "active", "confidence",
                               "first_seen", "last_seen")}
            for r in rows])

    @beta_tool
    def budgets(month: str = "") -> str:
        """Each category's budget against what has been spent this month, with
        a projection of where the month lands."""
        txns = store.all_transactions()
        months = sorted({t.month for t in txns})
        return json.dumps(budget_rows(txns, store.budgets(),
                                      month or (months[-1] if months else None)))

    @beta_tool
    def the_plan() -> str:
        """Their monthly plan: take-home pay, fixed commitments, what they are
        saving, and what is left to spend. The leftover covers groceries and
        other essentials as well as discretionary spending."""
        income = store.float_setting("monthly_income", 0.0)
        savings = store.float_setting("savings_target", 0.0)
        result = money_plan.plan(income, store.fixed_costs(), savings)
        shares = money_plan.variable_shares(store.all_transactions())
        result["discretionary_pool"] = money_plan.discretionary_pool(
            money_plan.category_budgets(result["leftover"], shares))
        return json.dumps(result)

    @beta_tool
    def savings_findings() -> str:
        """What the local rule engine has already found worth cutting, with
        each finding's annual saving, confidence and how much effort it is."""
        txns = store.all_transactions()
        found = generate_findings(txns, store.dismissed())
        return json.dumps([
            {k: f[k] for k in ("title", "detail", "kind", "annual_saving",
                               "confidence", "effort") if k in f}
            for f in found[:20]])

    return [months_available, spending_by_category, top_merchants, find_charges,
            subscriptions, budgets, the_plan, savings_findings]


def ask(store, question: str, history: list[dict] | None = None) -> dict:
    """Answer one question, looking things up as needed.

    `history` is prior turns as {role, content} so a follow-up has context.
    Returns the answer and which tools were consulted, because an answer you
    cannot audit is worth less than one you can.
    """
    if not is_available():
        return {"available": False, "answer": "", **status()}

    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    tools = _tools(store)

    messages = [*(history or []), {"role": "user", "content": question}]

    runner = client.beta.messages.tool_runner(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        max_iterations=MAX_TURNS,
        system=SYSTEM_PROMPT,
        thinking={"type": "adaptive"},
        tools=tools,
        messages=messages,
    )

    consulted: list[str] = []
    final = None
    for message in runner:
        for block in message.content:
            if block.type == "tool_use" and block.name not in consulted:
                consulted.append(block.name)
        final = message

    if final is None:
        return {"available": True, "answer": "",
                "error": "No reply came back.", "consulted": consulted}

    if final.stop_reason == "refusal":
        return {"available": True, "answer": "",
                "error": "That request was declined.", "consulted": consulted}

    answer = "".join(b.text for b in final.content if b.type == "text").strip()
    return {
        "available": True,
        "answer": answer,
        "consulted": consulted,
        "model": MODEL,
        "truncated": final.stop_reason == "max_tokens",
    }
