"""Growth › Projections: what could happen next (Pearl THL-197, GR-33 to GR-36).

Three look-ahead questions, each answered as a range and never one figure:

* **This month** (THL-191, GR-34): what she has spent so far, the bills still
  to come, and the rest of the month at her usual pace. The rest of the month
  is read off her own months (`usual_month.covered_months`, unusual months
  left out): what each of them spent after today's day of the month, bills
  left out because they are counted by name. The range runs from the
  quietest of those months to the busiest. "What you can spend" is the
  month's income less what she sets aside (safe-to-spend's rows before
  spending and bills), so what is left is that less the likely spend.
* **The next 30 days** (THL-192, GR-35): her chequing balance today, the
  paydays and bills ahead on one timeline, and her usual everyday spending
  between them, a day at a time. Paydays and bills come from the income and
  bills check (`income_bills`, THL-127) when she has run it; a bill she
  hasn't confirmed is still shown, marked as not confirmed.
* **Savings in a year** (THL-194, GR-36): what the Anchor and the treasure
  chests hold now, plus twelve months at her pace — the quietest and the best
  of the months the Anchor's pace rests on (`anchor.pace`) — and the same
  with a little more each month (the what-if).

A transaction she marked as a one-off (THL-71) is left out of every pace
and range here — it says nothing about what comes next — though it still
counts in what she has spent so far.

Everything is in whole cents. Ranges are rounded outwards to a figure she can
read ($10 for a month, $100 for a year), so the low end is never higher than
the arithmetic and the high end never lower.
"""

from __future__ import annotations

import calendar
import math
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount
from .models import Transaction

DAYS_AHEAD = 30
# With only one month to go on, or none, the range is this much either side.
SPREAD = 0.15


def cents(x: float | None) -> int:
    return int(round((x or 0) * 100))


def floor_to(c: int, step_c: int) -> int:
    return math.floor(c / step_c) * step_c


def ceil_to(c: int, step_c: int) -> int:
    return math.ceil(c / step_c) * step_c


def _days(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def add_months(month: str, n: int) -> str:
    total = int(month[:4]) * 12 + int(month[5:7]) - 1 + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _spread(values: list[int]) -> tuple[int, int]:
    """The quietest and busiest of `values`, or a band round the only one."""
    if not values:
        return 0, 0
    low, high = min(values), max(values)
    if len(values) == 1 or low == high:
        return round(low * (1 - SPREAD)), round(high * (1 + SPREAD))
    return low, high


# ── This month (GR-34) ────────────────────────────────────────────────────

def rest_of_month(transactions: list[Transaction], today: date, months: list[str],
                  bills: set[tuple[str, str]]) -> dict:
    """Everyday spending still to come this month: in each of her usual
    months, what went out after today's day of the month, bills left out.

    With no full month to go on, this month's own pace so far is carried to
    its end instead."""
    day = today.day
    month = today.strftime("%Y-%m")
    days_left = _days(month) - day
    if days_left <= 0:
        return {"low": 0, "high": 0, "basis": "done", "months": []}
    wanted = set(months)
    after: dict[str, int] = {m: 0 for m in months}
    so_far = 0
    for t in transactions:
        # A one-off (THL-71) is no guide to what comes next.
        if not counts_as_spending(t) or t.one_off or (t.merchant, t.date) in bills:
            continue
        if t.month in wanted and int(t.date[8:10]) > day:
            after[t.month] += cents(spend_amount(t))
        elif t.month == month and t.date <= today.isoformat():
            so_far += cents(spend_amount(t))
    if months:
        low, high = _spread([after[m] for m in months])
        return {"low": max(low, 0), "high": max(high, 0), "basis": "usual", "months": months}
    pace = round(so_far / day * days_left)
    low, high = _spread([pace])
    return {"low": max(low, 0), "high": max(high, 0), "basis": "this_month", "months": []}


def month_end(transactions: list[Transaction], today: date, sts: dict, months: list[str],
              bills: set[tuple[str, str]], spent_c: int | None = None) -> dict:
    """GR-34: spent so far, bills still to come, the likely spend by the
    month's end and what that leaves of what she can spend."""
    month = today.strftime("%Y-%m")
    rows = {r["key"]: r for r in sts.get("rows") or []}
    if spent_c is None:
        spent_c = cents(rows["spent"]["amount"]) if "spent" in rows else 0
    bill_lines = (rows.get("bills") or {}).get("lines") or []
    bills_c = sum(cents(b["amount"]) for b in bill_lines)
    rest = rest_of_month(transactions, today, months, bills)

    low_c = floor_to(spent_c + bills_c + rest["low"], 1000)
    high_c = max(ceil_to(spent_c + bills_c + rest["high"], 1000), low_c)
    can_spend_c = None
    if "income" in rows:
        can_spend_c = cents(rows["income"]["amount"]) - cents(
            (rows.get("set_aside") or {}).get("amount") or 0)

    # Spending to date, a day at a time, for the line that ends at today.
    by_day = [0] * (today.day + 1)
    for t in transactions:
        if t.month == month and t.date <= today.isoformat() and counts_as_spending(t):
            by_day[int(t.date[8:10])] += cents(spend_amount(t))
    running, line = 0, []
    for d in range(1, today.day + 1):
        running += by_day[d]
        line.append({"day": d, "spent": running})

    ahead = [{"date": b["date"], "label": b["label"], "amount": cents(b["amount"]),
              "confirmed": bool(b.get("confirmed"))}
             for b in bill_lines if b.get("date") and b["date"] > today.isoformat()]

    out = {
        "month": month, "day": today.day, "days_in_month": _days(month),
        "spent": spent_c, "bills": bills_c, "bills_ahead": ahead,
        "rest": rest, "spend": {"low": low_c, "high": high_c},
        "can_spend": can_spend_c, "left": None, "line": line,
        "has_history": bool(months) or spent_c > 0,
    }
    if can_spend_c is None:
        out["state"] = "no_income" if out["has_history"] else "none"
        return out
    left = {"low": can_spend_c - high_c, "high": can_spend_c - low_c}
    out["left"] = left
    out["state"] = ("over" if left["high"] < 0 else "tight" if left["low"] < 0 else "ok")
    if not out["has_history"]:
        out["state"] = "none"
    return out


# ── The next 30 days (GR-35) ──────────────────────────────────────────────

def everyday_per_day(transactions: list[Transaction], today: date, months: list[str],
                     bills: set[tuple[str, str]]) -> dict:
    """Her usual everyday spending a day, bills left out: the quietest and
    busiest of her usual months, and the middle of them, in cents."""
    wanted = set(months)
    totals: dict[str, int] = {m: 0 for m in months}
    month = today.strftime("%Y-%m")
    so_far = 0
    for t in transactions:
        # A one-off (THL-71) is no guide to what comes next.
        if not counts_as_spending(t) or t.one_off or (t.merchant, t.date) in bills:
            continue
        if t.month in wanted:
            totals[t.month] += cents(spend_amount(t))
        elif t.month == month and t.date <= today.isoformat():
            so_far += cents(spend_amount(t))
    if months:
        rates = [totals[m] / _days(m) for m in months]
        low, high = _spread([round(r) for r in rates])
        return {"low": low, "high": high, "usual": round(sum(rates) / len(rates))}
    usual = round(so_far / today.day) if today.day else 0
    low, high = _spread([usual])
    return {"low": low, "high": high, "usual": usual}


def next_30_days(today: date, *, balance_c: int | None, paydays: list[dict],
                 bills: list[dict], per_day: dict, days: int = DAYS_AHEAD) -> dict:
    """GR-35: the expected balance each day for the next `days` days, the
    paydays and bills on the way, and the lowest point.

    `paydays` and `bills` are {date, label, amount (cents)}; bills also carry
    `confirmed`. With no balance there is still a timeline of what's coming,
    but no line and no lowest point."""
    end = today + timedelta(days=days)
    within = lambda e: today.isoformat() < e["date"] <= end.isoformat()  # noqa: E731
    events = ([{**p, "kind": "payday"} for p in paydays if within(p)]
              + [{**b, "kind": "bill"} for b in bills if within(b)])
    events.sort(key=lambda e: (e["date"], e["kind"] != "payday", e["label"].lower()))
    out = {"start": today.isoformat(), "end": end.isoformat(), "days": days,
           "events": events, "per_day": per_day, "balance": balance_c,
           "series": [], "lowest": None}
    if balance_c is None:
        out["state"] = "no_balance"
        return out

    by_date: dict[str, int] = {}
    for e in events:
        by_date[e["date"]] = by_date.get(e["date"], 0) + (
            e["amount"] if e["kind"] == "payday" else -e["amount"])
    series = []
    usual = low = high = balance_c
    for n in range(days + 1):
        d = (today + timedelta(days=n)).isoformat()
        if n:
            moved = by_date.get(d, 0)
            usual += moved - per_day["usual"]
            # The low line spends the most each day, the high line the least.
            low += moved - per_day["high"]
            high += moved - per_day["low"]
        series.append({"date": d, "balance": usual, "low": low, "high": high})
    out["series"] = series
    point = min(series[1:] or series, key=lambda s: (s["balance"], s["date"]))
    paydays_on = {e["date"] for e in events if e["kind"] == "payday"}
    following = (date.fromisoformat(point["date"]) + timedelta(days=1)).isoformat()
    out["lowest"] = {"date": point["date"], "amount": round(point["balance"], -3),
                     "low": point["low"], "high": point["high"],
                     "before_payday": following in paydays_on}
    out["state"] = "covered" if point["balance"] >= 0 else "short"
    return out


# ── Savings in a year (GR-36) ─────────────────────────────────────────────

def chest_opens(*names: str) -> str:
    """"New laptop chest opens"; "Trip chest opens", not "Trip chest chest";
    "New laptop chest and Trip chest open" when two open in one month."""
    chests = [n if n.lower().endswith("chest") else f"{n} chest" for n in names]
    if len(chests) == 1:
        return f"{chests[0]} opens"
    return f"{', '.join(chests[:-1])} and {chests[-1]} open"


def savings_in_a_year(today: date, *, now_c: int, pace: dict | None, extra_c: int = 0,
                      history: list[dict] | None = None, chests: list[dict] | None = None
                      ) -> dict:
    """GR-36: what her savings could hold in twelve months at her current
    pace, and with `extra_c` more each month (the what-if)."""
    month = today.strftime("%Y-%m")
    target = add_months(month, 12)
    low_m = max(cents(pace["quietest"]["saved"]), 0) if pace else 0
    high_m = max(cents(pace["best"]["saved"]), 0) if pace else 0
    usual_m = max(cents(pace["usual"]), 0) if pace else 0

    def at(monthly_low: int, monthly_high: int) -> dict:
        return {"low": floor_to(now_c + 12 * monthly_low, 10000),
                "high": max(ceil_to(now_c + 12 * monthly_high, 10000),
                            floor_to(now_c + 12 * monthly_low, 10000))}

    by_month: dict[str, list[str]] = {}
    for c in chests or []:
        if c.get("ready_by") and month < c["ready_by"] <= target and c.get("target"):
            by_month.setdefault(c["ready_by"], []).append(c["name"])
    opens = [{"month": m, "label": chest_opens(*names)} for m, names in by_month.items()]
    return {
        "month": month, "by": target, "now": now_c,
        "pace": ({"low": low_m, "high": high_m, "usual": usual_m,
                  "months": [m["month"] for m in pace["used"]]} if pace else None),
        "current": at(low_m, high_m),
        "what_if": at(low_m + extra_c, high_m + extra_c) if extra_c > 0 else None,
        "extra": extra_c,
        "history": history or [],
        "opens": sorted(opens, key=lambda o: o["month"]),
        "state": "ok" if pace and high_m > 0 else "no_pace" if pace else "no_history",
    }
