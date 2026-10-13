"""Category budgets (THL-168, designed in THL-185 B-01 to B-03).

Every spending category starts with a budget equal to her usual month for it
(THL-184's three-month average), so there's nothing to fill in. She changes
one as a share of usual, and the dollars always go with the percent. Budgets
sit under the monthly safe-to-spend; they don't replace it.

Decisions this follows (THL-9 comment, 2026-10-12):

* B1: status uses the snapshot's ±10% pace rule: on track, on pace to go
  over, or over. Over and on pace to go over are champagne, with words.
* B2: every Essentials and Lifestyle category with a usual month above $0
  gets one, except rent and mortgage. A category that's all bills shows
  "All paid" once they're in, with no pace tick: bills don't build up day by
  day. The five largest come first.
* B3: a budget is kept as a percent of usual, 50% to 150% in 5% steps, so it
  follows her usual month as that moves.
* B4: Home's card counts the budgets over or on pace to go over, and hides
  at 0.
* E2: budgets start after one full month; until then there's no usual month
  to start from.
* THL-71: a one-off is left out of the months a budget's pace is read from,
  as it is from the usual month; in this month it still counts as spent.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from .analytics import counts_as_spending, spend_amount
from .models import Transaction
from .safe_to_spend import _cents, _dollars, bill_charges

PACE_BAND = 0.10
CURVE_MONTHS = 3
PCT_MIN, PCT_MAX, PCT_STEP = 50, 150, 5
PRESETS = (70, 80, 90, 100, 110)
LEFT_OUT = {"Rent & Housing"}
# A category is a bill category when this much of its usual month is bills.
BILL_SHARE = 0.8
TOP = 5


def valid_pct(pct) -> bool:
    return (isinstance(pct, (int, float)) and PCT_MIN <= pct <= PCT_MAX
            and float(pct) % PCT_STEP == 0)


def pace_status(spent_c: int, by_today_c: int, budget_c: int) -> str:
    """over-month, over (on pace to go over), under or on: the same rule as
    the snapshot (THL-110's paceStatus)."""
    if budget_c > 0 and spent_c > budget_c:
        return "over-month"
    if by_today_c <= 0:
        return "over" if spent_c > 0 else "on"
    diff = (spent_c - by_today_c) / by_today_c
    if diff > PACE_BAND:
        return "over"
    if diff < -PACE_BAND:
        return "under"
    return "on"


def build(transactions: list[Transaction], today: date, usual: dict, pcts: dict[str, float],
          bills_to_come: list[dict], comparisons_from: str | None = None) -> dict:
    """Every budget this month, largest first, with its status."""
    month = today.strftime("%Y-%m")
    days = calendar.monthrange(today.year, today.month)[1]
    if not usual.get("months"):
        return {"ready": False, "starts": comparisons_from, "month": month, "rows": [],
                "needs_look": 0}

    covered = set(usual["months"])
    bills = bill_charges(transactions, today)
    bill_c: dict[str, int] = defaultdict(int)
    all_c: dict[str, int] = defaultdict(int)
    by_today_c: dict[str, int] = defaultdict(int)
    spent_c: dict[str, int] = defaultdict(int)
    for t in transactions:
        if not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        c = _cents(spend_amount(t))
        if t.month in covered:
            # A one-off (THL-71) isn't part of a usual month, so it shapes
            # neither the budget nor its pace; this month it still counts.
            if t.one_off:
                continue
            all_c[cat] += c
            if int(t.date[8:10]) <= today.day:
                by_today_c[cat] += c
            if (t.merchant, t.date) in bills:
                bill_c[cat] += c
        elif t.month == month and t.date <= today.isoformat():
            spent_c[cat] += c

    def fraction(cat: str) -> float:
        """How far through a usual month she usually is by today, for this
        category: its own curve with three months behind it (a category's,
        not its group's, so rent on the 1st doesn't move Groceries), the day
        of the month before that."""
        if usual["curve"] == "daily" and all_c[cat] > 0:
            return min(by_today_c[cat] / all_c[cat], 1.0)
        return today.day / days
    to_come_c: dict[str, int] = defaultdict(int)
    for b in bills_to_come:
        if b.get("category"):
            to_come_c[b["category"]] += _cents(b["amount"])

    rows = []
    for cat, info in usual["categories"].items():
        if cat in LEFT_OUT or info["usual"] <= 0:
            continue
        pct = pcts.get(cat, 100)
        usual_c = _cents(info["usual"])
        budget_c = usual_c * pct // 100
        spent = spent_c.get(cat, 0)
        is_bill = all_c[cat] > 0 and bill_c[cat] >= all_c[cat] * BILL_SHARE
        row = {"category": cat, "group": info["group"], "usual": info["usual"], "pct": pct,
               "budget": _dollars(budget_c), "spent": _dollars(spent), "bill": is_bill,
               "by_today": None, "to_come": _dollars(to_come_c.get(cat, 0))}
        if is_bill:
            # Bills are paid on their day, not a little each day: no pace.
            if spent > budget_c * (1 + PACE_BAND):
                row["status"] = "over-month"
            else:
                row["status"] = "to_come" if to_come_c.get(cat) else "paid"
        else:
            by_c = int(budget_c * fraction(cat))
            row["by_today"] = _dollars(by_c)
            row["status"] = pace_status(spent, by_c, budget_c)
        row["over_by"] = _dollars(spent - budget_c) if row["status"] == "over-month" else None
        rows.append(row)
    rows.sort(key=lambda r: (-r["budget"], r["category"]))
    return {"ready": True, "starts": None, "month": month, "day": today.day,
            "days_in_month": days, "months_of_history": len(usual["months"]),
            "rows": rows, "top": TOP,
            "needs_look": sum(1 for r in rows if r["status"] in ("over", "over-month"))}
