"""This week's share of the month (THL-166) and "Can I afford it?" (THL-167).

The month's safe-to-spend stays the number; the week is a way of reading it.

Decisions this follows (THL-9 comment, 2026-10-12):

* W1: the month is re-split each Monday. This week's share is safe-to-spend
  as it stood at the start of the week × days in the week ÷ days left in the
  month then. Left this week = share − spent this week. What earlier weeks
  didn't spend is already in that starting number, so it rolls over on its
  own; it is shown as "includes $X from earlier weeks", never as a term in
  the sum.
* W2: weeks run Monday to Sunday and stop at the month's edge, so a partial
  week gets a share by its days.
* W3: bills are left out of the week. The month already takes them out
  before it is split, so counting them again would make the weeks stop
  adding up to the month.
* W4: overspending stays in the month: it lowers the weeks after, spread by
  days, rather than landing on next week alone.
* S6: days left include today.

So the weeks always reconcile: left this week + the rest of the month = the
month's safe-to-spend, to the cent.

"Can I afford it?" records nothing. It checks the month, with one line on the
week (A2). If it doesn't fit it says by how much, and whether November would
cover it if November looks like a usual month (A1): this month's income,
less this month's bills and what she sets aside.
"""

from __future__ import annotations

import calendar
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount
from .models import Transaction
from .safe_to_spend import (_cents, _dollars, _next_month, bill_charges, month_end,
                            round_down_10)


def week_bounds(today: date) -> tuple[date, date]:
    """Monday to Sunday, cut at the month's first and last days (W2)."""
    first, end = today.replace(day=1), month_end(today)
    monday = today - timedelta(days=today.weekday())
    return max(monday, first), min(monday + timedelta(days=6), end)


def week(transactions: list[Transaction], today: date, sts: dict) -> dict | None:
    """This week's share, what's left of it, and the rest of the month.
    None when the month has no number yet (E1)."""
    if sts.get("amount") is None:
        return None
    month = today.strftime("%Y-%m")
    start, end = week_bounds(today)
    first, last = today.replace(day=1), month_end(today)
    bills = bill_charges(transactions, today)

    earlier_c = this_week_c = 0
    for t in transactions:
        if (t.month != month or t.date > today.isoformat() or not counts_as_spending(t)
                or (t.merchant, t.date) in bills):
            continue
        c = _cents(spend_amount(t))
        if t.date >= start.isoformat():
            this_week_c += c
        else:
            earlier_c += c

    now_c = _cents(sts["amount"])
    at_start_c = now_c + this_week_c            # safe to spend on Monday morning
    week_days = (end - start).days + 1
    left_then = (last - start).days + 1
    share_c = max(at_start_c, 0) * week_days // left_then
    left_c = share_c - this_week_c
    rest_c = now_c - left_c                     # the weeks after this one

    # What the week would have had if every earlier week had spent just its
    # share: the month's spending money split evenly by days.
    month_days = (last - first).days + 1
    even_c = max(at_start_c + earlier_c, 0) * week_days // month_days
    rolled_c = share_c - even_c

    days = (end - today).days + 1
    over = left_c < 0
    left = _dollars(left_c)
    estimate = sts.get("estimate")
    return {
        "start": start.isoformat(), "end": end.isoformat(),
        "days": week_days, "days_left": days,
        "share": _dollars(share_c),
        "at_start": _dollars(at_start_c),
        "spent": _dollars(this_week_c),
        "left": left,
        "shown": round_down_10(left) if estimate and not over else left,
        "per_day": None if over else _dollars(left_c // days),
        "state": "over" if over else "ok",
        "over_by": _dollars(-left_c) if over else None,
        # Positive: earlier weeks left some over. Negative: they went over,
        # and this week (with every week after it) carries a little less.
        "rolled_over": _dollars(rolled_c),
        "rest_of_month": _dollars(rest_c),
        "rest_days": (last - end).days,
        "month_amount": sts["amount"],
        "estimate": estimate,
    }


def afford(transactions: list[Transaction], today: date, sts: dict, wk: dict | None,
           amount: float) -> dict:
    """What a purchase would do to the month and the week. Records nothing."""
    price_c = _cents(amount)
    # A rough or cautious month is checked against the number she is shown.
    base = sts["shown"] if sts["state"] == "ok" else sts["amount"]
    before_c = _cents(base)
    after_c = before_c - price_c
    fits = after_c >= 0
    left = sts["days_left"]
    out = {
        "amount": _dollars(price_c),
        "fits": fits,
        "before": _dollars(before_c),
        "after": _dollars(after_c) if fits else None,
        "per_day_after": _dollars(after_c // left) if fits else None,
        "days_left": left,
        "short_by": None if fits else _dollars(-after_c),
        "already_over": sts["state"] == "over",
        "estimate": sts.get("estimate"),
        "week": None,
        "next_month": None,
    }
    if wk:
        week_left_c = max(_cents(wk["left"]), 0)
        out["week"] = {"left": _dollars(week_left_c),
                       "within": price_c <= week_left_c,
                       "left_after": _dollars(week_left_c - price_c) if price_c <= week_left_c else None}
    if not fits:
        out["next_month"] = next_month(transactions, today, sts, price_c)
    return out


def next_month(transactions: list[Transaction], today: date, sts: dict, price_c: int) -> dict:
    """If next month looks like a usual month (A1): this month's income, less
    this month's bills (paid and still to come) and what she sets aside, all
    before any spending."""
    first = _next_month(today)
    month = today.strftime("%Y-%m")
    rows = {r["key"]: r for r in sts["rows"]}
    income_c = _cents(rows["income"]["amount"])
    bills = bill_charges(transactions, today)
    paid_c = sum(_cents(spend_amount(t)) for t in transactions
                 if t.month == month and t.date <= today.isoformat()
                 and counts_as_spending(t) and (t.merchant, t.date) in bills)
    bills_c = paid_c + _cents(rows["spent"].get("debt_paid") or 0) + _cents(rows["bills"]["amount"])
    set_aside_c = _cents(rows["set_aside"]["target"]) if "set_aside" in rows else 0
    room_c = income_c - bills_c - set_aside_c
    days = calendar.monthrange(first.year, first.month)[1]
    fits = 0 < price_c <= room_c
    return {"month": first.strftime("%Y-%m"), "fits": fits,
            "per_day_after": _dollars((room_c - price_c) // days) if fits else None}
