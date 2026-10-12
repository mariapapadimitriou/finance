"""Her usual month, per group and per category, and how it usually builds up
day by day (THL-184), for the Home snapshot (THL-48) and budgets (THL-168).

* Usual month = the average of the last three full months, for Essentials,
  Lifestyle and every spending category. Transfers and card payments never
  count (`counts_as_spending`); one-offs do until THL-71 can mark them.
* The usual-by-day curve says how much she has usually spent by each day of
  the month. It drives the snapshot's pace tick and the ±10% pace rule.
* With fewer than three full months there is no curve: the pace falls back to
  the straight day-of-month fraction, and the payload says so. With no full
  month there is no usual month at all, and comparisons wait (THL-9 E2).

A month counts only when the history covers it from its first day, so a
first partial month never drags the average down.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date, timedelta

from .analytics import counts_as_spending, invested_in, spend_amount
from .categorize import group_of
from .models import Transaction

USUAL_MONTHS = 3          # the usual month is the average of this many
CURVE_MONTHS = 3          # a daily curve needs this many behind it
GROUPS = ("essentials", "lifestyle")
GROUP_LABELS = {"essentials": "Essentials", "lifestyle": "Lifestyle"}


def _cents(x: float) -> int:
    return int(round(x * 100))


def _dollars(c: float) -> float:
    return round(c / 100, 2)


def covered_months(transactions: list[Transaction], today: date,
                   n: int = USUAL_MONTHS) -> list[str]:
    """Up to `n` full months before this one that the history covers from
    their first day, oldest first."""
    if not transactions:
        return []
    first = min(t.date for t in transactions)
    out, cursor = [], today.replace(day=1)
    for _ in range(n):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        if first <= cursor.isoformat():
            out.append(cursor.strftime("%Y-%m"))
    return out[::-1]


def _days(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def usual(transactions: list[Transaction], today: date) -> dict:
    """The usual month and its daily curve, in dollars.

    {"months": [...], "curve": "daily" | "day_fraction" | None,
     "groups": {group: {"usual": float, "by_day": [31 floats] | None}},
     "categories": {category: {"usual": float, "group": str}}}
    """
    months = covered_months(transactions, today)
    if not months:
        return {"months": [], "curve": None, "groups": {}, "categories": {}}
    wanted = set(months)
    by_cat: dict[str, int] = defaultdict(int)
    # Cents spent on each day, per group and month.
    daily: dict[str, dict[str, list[int]]] = {
        g: {m: [0] * (_days(m) + 1) for m in months} for g in GROUPS}
    for t in transactions:
        if t.month not in wanted or not counts_as_spending(t):
            continue
        c = _cents(spend_amount(t))
        cat = t.category or "Other"
        by_cat[cat] += c
        g = group_of(cat)
        if g in daily:
            daily[g][t.month][int(t.date[8:10])] += c

    n = len(months)
    curve = "daily" if n >= CURVE_MONTHS else "day_fraction"
    groups = {}
    for g in GROUPS:
        total = sum(sum(days) for days in daily[g].values())
        by_day = None
        if curve == "daily":
            by_day = []
            for day in range(1, 32):
                # By day 31 a 30-day month has already had all of its days.
                upto = [sum(days[1:min(day, len(days) - 1) + 1]) for days in daily[g].values()]
                by_day.append(_dollars(sum(upto) / n))
        groups[g] = {"usual": _dollars(total / n), "by_day": by_day}
    categories = {cat: {"usual": _dollars(c / n), "group": group_of(cat)}
                  for cat, c in sorted(by_cat.items(), key=lambda kv: -kv[1])
                  if group_of(cat) in GROUPS and c > 0}
    return {"months": months, "curve": curve, "groups": groups, "categories": categories}


def snapshot(transactions: list[Transaction], today: date, sts: dict, u: dict, *,
             savings_target: float = 0.0, anchor_started: bool = False,
             comparisons_from: str | None = None) -> dict:
    """The Home snapshot (H-01): Income, Essentials, Lifestyle and Savings.

    Income compares what has arrived with what's expected this month;
    Essentials and Lifestyle with her usual month and where she usually is
    by today; Savings with the monthly plan, or just what's saved with none.
    """
    month = today.strftime("%Y-%m")
    days = _days(month)
    rows = []

    income = next((r for r in sts.get("rows", []) if r["key"] == "income"), None)
    received = round(sum(line["amount"] for line in income["lines"] if line.get("arrived")), 2) \
        if income else round(sum(-t.amount for t in transactions
                                 if t.month == month and t.category == "Income"
                                 and t.amount < 0 and not t.repays and not t.excluded), 2)
    rows.append({"key": "income", "label": "Income", "received": received,
                 "expected": income["amount"] if income else None,
                 "next_pay": sts.get("next_pay"),
                 "cautious": sts.get("cautious") if sts.get("income_source") == "cautious" else None})

    spent: dict[str, int] = defaultdict(int)
    for t in transactions:
        if t.month == month and t.date <= today.isoformat() and counts_as_spending(t):
            spent[group_of(t.category or "Other")] += _cents(spend_amount(t))
    for g in GROUPS:
        grp = u["groups"].get(g)
        by_today = None
        if grp and grp["by_day"]:
            by_today = grp["by_day"][today.day - 1]
        rows.append({"key": g, "label": GROUP_LABELS[g], "spent": _dollars(spent[g]),
                     "usual": grp["usual"] if grp else None, "usual_by_today": by_today})

    saved = invested_in(transactions, month)
    rows.append({"key": "savings", "label": "Savings", "saved": saved,
                 "planned": savings_target or None,
                 "goal": ("anchor" if anchor_started else "saving_goal") if savings_target else None})

    return {"month": month, "day": today.day, "days_in_month": days,
            "months_of_history": len(u["months"]), "curve": u["curve"],
            "usual_months": u["months"], "comparisons_from": comparisons_from,
            "rows": rows, "extra_went_to": _extra_went_to(rows, today.day, days)}


def _extra_went_to(rows: list[dict], day: int, days: int) -> str | None:
    """Over the plan: the group furthest past where it usually is by today,
    for "Lifestyle is where the extra went" (H-02)."""
    best, gap = None, 0.0
    for r in rows:
        if r["key"] not in GROUPS or not r.get("usual"):
            continue
        by_today = r["usual_by_today"] if r["usual_by_today"] is not None \
            else r["usual"] * day / days
        if r["spent"] - by_today > gap:
            best, gap = r["label"], r["spent"] - by_today
    return best
