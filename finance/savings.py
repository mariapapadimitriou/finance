"""Savings this month (2026-10-14): two running totals for the current month.

Pearl can't read a savings balance — her savings account may not be in
Plaid, and an investment account's activity never is — so savings is what
she nets, not what an account holds. Every screen shows the current month:

* **Put away** — the transfers she marked as saving (category Saved: into a
  savings or investment account, or the part of a charge marked as saved),
  less the transfers she marked as coming back out (Saved, money in). The
  treasure chests aren't in it: they fill from her Anchor, not from the
  month (THL-230). The same figure every other screen calls saving
  (`put_away_month`); spending and income never move it.
* **Left over** — what came in less what went out this month, by the one
  income rule (`safe_to_spend.income_for_month`) and the one spending gate.
"""

from __future__ import annotations

from datetime import date

from .analytics import counts_as_spending, is_others, spend_amount
from .models import Transaction


def chest_adds(store) -> dict[str, float]:
    """{month: money added to treasure chests by hand that month}."""
    out: dict[str, float] = {}
    for d in store.draws():
        if d["amount"] < 0:                             # add_to_chest writes a negative draw
            out[d["month"]] = out.get(d["month"], 0.0) + -float(d["amount"])
    return out


def put_away_month(store, transactions: list[Transaction], month: str) -> float:
    """What was moved to savings in a month — the one saving figure
    (THL-230): transfers marked Saved (less those marked as taken back out)
    and the saved part of split charges (`invested_in`). Safe to spend, the
    carryover, the usual month, Insights and Home all use it."""
    from .analytics import invested_in
    return round(invested_in(transactions, month), 2)


def this_month(store, transactions: list[Transaction], today: date) -> dict:
    """Both totals for the current month, each with what went into it."""
    from .safe_to_spend import income_for_month
    month = today.strftime("%Y-%m")
    put_in = taken_out = spent = 0.0
    for t in transactions:
        if t.month != month or t.excluded or is_others(t):
            continue
        if (t.category or "") == "Saved":
            if t.amount > 0:
                put_in += t.amount
            else:
                taken_out += -t.amount
            continue
        if t.invested:
            put_in += t.invested
        if counts_as_spending(t):
            spent += spend_amount(t)
    income, estimate = income_for_month(store, transactions, month, today)
    return {
        "month": month,
        "put_away": {"contributions": round(put_in, 2), "withdrawals": round(taken_out, 2),
                     "net": round(put_in - taken_out, 2)},
        "left_over": {"income": round(income, 2), "spent": round(spent, 2),
                      "net": round(income - spent, 2), "estimate": estimate},
    }
