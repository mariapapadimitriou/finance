"""Her usual month, per group and per category, and how it usually builds up
day by day (THL-184), for the Home snapshot (THL-48) and budgets (THL-168).

* Usual month = the average of the last three full months, for Essentials,
  Lifestyle and every spending category. Transfers and card payments never
  count (`counts_as_spending`), and neither does a transaction she marked
  as a one-off (THL-71): a tax refund, moving costs, a big one-time
  purchase. A one-off still counts in its own month and in safe to spend;
  it just isn't what a usual month looks like.
* The usual-by-day curve says how much she has usually spent by each day of
  the month. It drives the snapshot's pace tick and the ±10% pace rule.
* With fewer than three full months there is no curve: the pace falls back to
  the straight day-of-month fraction, and the payload says so. With no full
  month there is no usual month at all, and comparisons wait (THL-9 E2).

A month counts only when the history covers it from its first day, so a
first partial month never drags the average down.

A month she marks as unusual (a move, a car repair; THL-59, the same list
Goals' Anchor pace leaves out, `anchor_unusual`) is left out, and the next
older full month is pulled in instead, up to LOOKBACK months back, so the
usual month still rests on three when there are three to be had. Home's
snapshot, budgets and Growth › Insights all read it this way.
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
LOOKBACK = 12             # how far back to look past unusual months
GROUPS = ("essentials", "lifestyle")
GROUP_LABELS = {"essentials": "Essentials", "lifestyle": "Lifestyle"}


def _cents(x: float) -> int:
    return int(round(x * 100))


def _dollars(c: float) -> float:
    return round(c / 100, 2)


def covered_months(transactions: list[Transaction], today: date,
                   n: int = USUAL_MONTHS, unusual: set[str] | frozenset = frozenset()
                   ) -> list[str]:
    """Up to `n` full months before this one that the history covers from
    their first day, oldest first. Months marked unusual are skipped and an
    older one taken instead, looking back at most LOOKBACK months."""
    if not transactions:
        return []
    first = min(t.date for t in transactions)
    out, cursor = [], today.replace(day=1)
    for _ in range(LOOKBACK if unusual else n):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        if first > cursor.isoformat() or len(out) >= n:
            break
        month = cursor.strftime("%Y-%m")
        if month not in unusual:
            out.append(month)
    return out[::-1]


def _days(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def usual(transactions: list[Transaction], today: date,
          unusual: set[str] | frozenset = frozenset(),
          kinds: dict[str, str] | None = None) -> dict:
    """The usual month and its daily curve, in dollars, unusual months left out.

    {"months": [...], "curve": "daily" | "day_fraction" | None,
     "groups": {group: {"usual": float, "by_day": [31 floats] | None}},
     "categories": {category: {"usual": float, "group": str}}}
    """
    months = covered_months(transactions, today, unusual=unusual)
    if not months:
        return {"months": [], "curve": None, "groups": {}, "kinds": {}, "categories": {}}
    wanted = set(months)
    by_cat: dict[str, int] = defaultdict(int)
    # Cents spent on each day, per group and month — and per kind (Fixed or
    # Variable, finance/kinds.py), the second lens.
    daily: dict[str, dict[str, list[int]]] = {
        g: {m: [0] * (_days(m) + 1) for m in months} for g in GROUPS}
    daily_kind: dict[str, dict[str, list[int]]] = {
        k: {m: [0] * (_days(m) + 1) for m in months} for k in ("fixed", "variable")}
    for t in transactions:
        if t.month not in wanted or not in_usual(t):
            continue
        c = _cents(spend_amount(t))
        cat = t.category or "Other"
        by_cat[cat] += c
        g = group_of(cat)
        if g in daily:
            daily[g][t.month][int(t.date[8:10])] += c
            k = (kinds or {}).get(t.fingerprint, "variable")
            daily_kind[k][t.month][int(t.date[8:10])] += c

    n = len(months)
    curve = "daily" if n >= CURVE_MONTHS else "day_fraction"

    def summarise(per_month: dict[str, list[int]]) -> dict:
        total = sum(sum(days) for days in per_month.values())
        by_day = None
        if curve == "daily":
            by_day = []
            for day in range(1, 32):
                # By day 31 a 30-day month has already had all of its days.
                upto = [sum(days[1:min(day, len(days) - 1) + 1]) for days in per_month.values()]
                by_day.append(_dollars(sum(upto) / n))
        return {"usual": _dollars(total / n), "by_day": by_day}

    groups = {g: summarise(daily[g]) for g in GROUPS}
    kinds_out = {k: summarise(daily_kind[k]) for k in ("fixed", "variable")} if kinds else {}
    categories = {cat: {"usual": _dollars(c / n), "group": group_of(cat)}
                  for cat, c in sorted(by_cat.items(), key=lambda kv: -kv[1])
                  if group_of(cat) in GROUPS and c > 0}
    return {"months": months, "curve": curve, "groups": groups, "kinds": kinds_out,
            "categories": categories}


def in_usual(t: Transaction) -> bool:
    """Whether a row may shape an average: spending that isn't a one-off.
    Projections, budgets, Insights and the trend card ask this of the months
    they average over (THL-71)."""
    return counts_as_spending(t) and not t.one_off


def one_off_effect(transactions: list[Transaction], txn: Transaction, today: date,
                   unusual: set[str] | frozenset = frozenset()) -> dict | None:
    """What marking `txn` a one-off does to a usual month of its group, for
    U-02's toast and U-03's line: {group, label, usual, without, in_usual}.

    `usual` is the usual month with it left out and `without` with it in.
    When its month is one of the months the usual month averages, both are
    worked out on the ledger. When it isn't yet (this month, usually),
    `without` is what a usual month would rise to with this purchase in it:
    its share of the months averaged. None when it isn't Essentials or
    Lifestyle spending, or there is no usual month yet.
    """
    from dataclasses import replace
    g = group_of(txn.category or "Other")
    if g not in GROUPS or not counts_as_spending(txn):
        return None
    flagged = txn.one_off_since or today.isoformat()
    on = [replace(t, one_off_since=flagged) if t.fingerprint == txn.fingerprint else t
          for t in transactions]
    off = [replace(t, one_off_since=None) if t.fingerprint == txn.fingerprint else t
           for t in transactions]
    u_on = usual(on, today, unusual)
    if not u_on["months"] or g not in u_on["groups"]:
        return None
    left_out = u_on["groups"][g]["usual"]
    if txn.month in u_on["months"]:
        kept_in = usual(off, today, unusual)["groups"][g]["usual"]
        inside = True
    else:
        kept_in = _dollars(_cents(left_out) + _cents(spend_amount(txn)) / len(u_on["months"]))
        inside = False
    return {"group": g, "label": GROUP_LABELS[g], "usual": left_out, "without": kept_in,
            "in_usual": inside}


def snapshot(transactions: list[Transaction], today: date, sts: dict, u: dict, *,
             comparisons_from: str | None = None, saved: float | None = None,
             kinds: dict[str, str] | None = None) -> dict:
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
    spent_kind: dict[str, int] = defaultdict(int)
    for t in transactions:
        if t.month == month and t.date <= today.isoformat() and counts_as_spending(t):
            spent[group_of(t.category or "Other")] += _cents(spend_amount(t))
            spent_kind[(kinds or {}).get(t.fingerprint, "variable")] += _cents(spend_amount(t))
    for g in GROUPS:
        grp = u["groups"].get(g)
        by_today = None
        if grp and grp["by_day"]:
            by_today = grp["by_day"][today.day - 1]
        rows.append({"key": g, "label": GROUP_LABELS[g], "spent": _dollars(spent[g]),
                     "usual": grp["usual"] if grp else None, "usual_by_today": by_today})

    if saved is None:
        saved = invested_in(transactions, month)
    # Put away (THL-230): what she moved to savings, with no plan to measure
    # it against; chests fill from her Anchor, not from the month.
    rows.append({"key": "savings", "label": "Put away", "saved": saved, "planned": None,
                 "goal": None})
    if kinds is not None:
        # The same month through the other lens (finance/kinds.py).
        from .kinds import KIND_LABELS, KINDS
        for k in KINDS:
            grp = (u.get("kinds") or {}).get(k)
            by_today = grp["by_day"][today.day - 1] if grp and grp["by_day"] else None
            rows.append({"key": k, "label": KIND_LABELS[k], "spent": _dollars(spent_kind[k]),
                         "usual": grp["usual"] if grp else None, "usual_by_today": by_today,
                         "lens": "kind"})

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
