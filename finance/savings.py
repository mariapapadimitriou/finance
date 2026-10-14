"""Savings so far (2026-10-14): two running totals from the day she started.

Pearl can't read a savings balance — her savings account may not be in
Plaid, and an investment account's activity never is — so savings is what
she nets from a starting point, not what an account holds:

* **Put away** — the transfers she marked as saving (category Saved: into a
  savings or investment account, or the part of a charge marked as saved)
  and the money going into her treasure chests, less the transfers she
  marked as coming back out (Saved, money in). The same figure every other
  screen calls saving (`put_away_month`); spending and income never move it.
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
from .safe_to_spend import _counts_as_income

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


def chest_adds(store) -> dict[str, float]:
    """{month: money added to treasure chests by hand that month}."""
    out: dict[str, float] = {}
    for d in store.draws():
        if d["amount"] < 0:                             # add_to_chest writes a negative draw
            out[d["month"]] = out.get(d["month"], 0.0) + -float(d["amount"])
    return out


def put_away_month(store, transactions: list[Transaction], month: str) -> float:
    """What was put away in a month — the one saving figure (2026-10-14):
    transfers marked Saved (less those marked as taken back out) and the
    saved part of split charges (`invested_in`), plus the treasure chests'
    monthly amounts and anything added to a chest by hand. Safe to spend,
    the carryover, the usual month, Growth and Savings so far all use it."""
    from .growth_insights import set_aside
    return round(set_aside(transactions, store.piggy_banks(), store.bank_charges_by_month(),
                           month, adds=chest_adds(store)) / 100.0, 2)


def so_far(store, transactions: list[Transaction], start: str | None, today: date) -> dict:
    """Both totals since `start`, each with what went into it. Income is
    `safe_to_spend.income_for_month` month by month (flagged when it's the
    planned figure rather than deposits Pearl saw); spending and Saved rows
    count from the start date itself."""
    from .growth_insights import chest_monthly
    from .safe_to_spend import income_for_month
    if not start:
        return {"since": None,
                "put_away": {"contributions": 0.0, "chests": 0.0, "withdrawals": 0.0, "net": 0.0},
                "left_over": {"income": 0.0, "spent": 0.0, "net": 0.0, "estimate": False}}
    put_in = taken_out = spent = 0.0
    for t in transactions:
        if t.date[:10] < start or t.excluded or is_others(t):
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
    # Month by month from the start: chest money, and income by the one rule.
    months = []
    m = start[:7]
    now = today.strftime("%Y-%m")
    while m <= now:
        months.append(m)
        y, mo = int(m[:4]), int(m[5:7])
        m = f"{y + (mo == 12):04d}-{(mo % 12) + 1:02d}"
    banks, charges, adds = store.piggy_banks(), store.bank_charges_by_month(), chest_adds(store)
    chests = sum(chest_monthly(banks, charges, mm) / 100.0 + adds.get(mm, 0.0) for mm in months)
    income = 0.0
    estimate = False
    for mm in months:
        amount, est = income_for_month(store, transactions, mm, today)
        if not est and mm == start[:7]:
            # Deposits before the start day don't count.
            amount = round(sum(-t.amount for t in transactions
                               if t.month == mm and t.date[:10] >= start
                               and _counts_as_income(t)), 2)
        income += amount
        estimate = estimate or est
    return {
        "since": start,
        "put_away": {"contributions": round(put_in, 2), "chests": round(chests, 2),
                     "withdrawals": round(taken_out, 2),
                     "net": round(put_in + chests - taken_out, 2)},
        "left_over": {"income": round(income, 2), "spent": round(spent, 2),
                      "net": round(income - spent, 2), "estimate": estimate},
    }
