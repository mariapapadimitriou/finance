"""Savings so far (2026-10-14): two running totals from the day she started.

Pearl can't read a savings balance — her savings account may not be in
Plaid, and an investment account's activity never is — so savings is what
she nets from a starting point, not what an account holds:

* **Put away** — the transfers she marked as saving (category Saved: into a
  savings or investment account, or the part of a charge marked as saved),
  less the ones she marked as coming back out (Saved, money in). Only what
  she said counts; spending and income never move it.
* **Left over** — everything she earned less everything she spent since the
  start, whether or not it went anywhere.

The starting point is the day she started using Pearl (`onboarded_at`), or
the day she started over (`savings_since`), or failing both the first day
there is a transaction. Nothing before it counts.
"""

from __future__ import annotations

from datetime import date, datetime, timezone

from .analytics import counts_as_spending, is_others, spend_amount
from .models import Transaction

SINCE = "savings_since"


def since(store, user=None, transactions: list[Transaction] | None = None) -> str | None:
    """The starting point as an ISO date, or None with nothing to start from."""
    told = store.setting(SINCE)
    if told:
        return str(told)[:10]
    started = getattr(user, "onboarded_at", None)
    if started:
        return datetime.fromtimestamp(float(started), tz=timezone.utc).date().isoformat()
    rows = transactions if transactions is not None else store.all_transactions()
    first = min((t.date[:10] for t in rows), default=None)
    return first


def start_over(store, today: date) -> None:
    """Starting fresh starts the count again today."""
    store.set_setting(SINCE, today.isoformat())


def so_far(transactions: list[Transaction], start: str | None) -> dict:
    """Both totals since `start`, each with what went into it."""
    put_in = taken_out = income = spent = 0.0
    for t in transactions:
        if not start or t.date[:10] < start or t.excluded or is_others(t):
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
        elif (t.category or "") == "Income" and t.amount < 0:
            income += -t.amount
    return {
        "since": start,
        "put_away": {"contributions": round(put_in, 2), "withdrawals": round(taken_out, 2),
                     "net": round(put_in - taken_out, 2)},
        "left_over": {"income": round(income, 2), "spent": round(spent, 2),
                      "net": round(income - spent, 2)},
    }
