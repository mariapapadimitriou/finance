"""The expense calendar (THL-245 CAL-01 to CAL-06; THL-255).

A month, day by day. Past days say how the month was going at the end of
that day: on or under her usual pace (a faint lagoon with a ✓), or ahead of
it (a faint rose with a ▲). Nothing is shaded when there is no usual month
to compare with, or before her accounts were linked. No day carries a
spending figure: safe to spend stays monthly. Upcoming days show what's due
— bills and pay from the same lines safe to spend counts, and the treasure
chests' monthly amounts moving from the Anchor on the 1st (THL-230), which
is money moving, not spending.

Everything is worked out from the ledger on every request, so a late
transaction or a re-sorted one changes the shading the next time the page
loads. The pace is the usual month as it stood at the start of the month
shown (`usual_month.usual`): what she usually has spent by each day.
"""

from __future__ import annotations

import calendar as cal
from collections import defaultdict
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount
from .models import Transaction
from .safe_to_spend import _counts_as_income

# "Moving money" (CAL-01): transfers between her own pockets this month.
MOVING = {"Transfers", "Saved"}
# A day is "ahead" once it is past the usual by more than this (cents noise).
EPSILON = 0.005


def _month_add(month: str, n: int) -> str:
    y, m = int(month[:4]), int(month[5:7])
    total = y * 12 + m - 1 + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _days_in(month: str) -> int:
    return cal.monthrange(int(month[:4]), int(month[5:7]))[1]


def month_name(month: str) -> str:
    return cal.month_name[int(month[5:7])]


def day_words(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{cal.month_abbr[d.month]} {d.day}"


def long_day(iso: str) -> str:
    d = date.fromisoformat(iso[:10])
    return f"{cal.day_name[d.weekday()]}, {cal.month_name[d.month]} {d.day}"


# ── The pace, day by day ────────────────────────────────────────────────

def usual_by_day(usual: dict, day: int, days: int) -> float | None:
    """What she has usually spent by the end of `day`, Essentials and
    Lifestyle together; None when there is no usual month."""
    groups = (usual or {}).get("groups") or {}
    total = 0.0
    seen = False
    for key in ("essentials", "lifestyle"):
        g = groups.get(key)
        if not g or not g.get("usual"):
            continue
        seen = True
        if g.get("by_day"):
            total += g["by_day"][min(day, len(g["by_day"])) - 1]
        else:
            total += g["usual"] * day / days
    return round(total, 2) if seen else None


def spent_by_day(transactions: list[Transaction], month: str) -> dict[int, float]:
    """What was spent on each day of the month (what counts as spending,
    her share, less what a chest paid)."""
    out: dict[int, float] = defaultdict(float)
    for t in transactions:
        if t.month == month and counts_as_spending(t):
            out[int(t.date[8:10])] += spend_amount(t)
    return {d: round(v, 2) for d, v in out.items()}


def states(transactions: list[Transaction], today: date, month: str, usual: dict) -> dict[int, str]:
    """{day: "on" | "ahead" | "none" | "today" | "future"} for the month.
    A day counts once it has ended; today is outlined and not shaded."""
    days = _days_in(month)
    first = min((t.date[:10] for t in transactions), default=None)
    per_day = spent_by_day(transactions, month)
    cum = 0.0
    out = {}
    for d in range(1, days + 1):
        iso = f"{month}-{d:02d}"
        cum += per_day.get(d, 0.0)
        if iso == today.isoformat():
            out[d] = "today"
            continue
        if iso > today.isoformat():
            out[d] = "future"
            continue
        usual_to_here = usual_by_day(usual, d, days)
        if usual_to_here is None or first is None or iso < first:
            out[d] = "none"
        elif cum > usual_to_here + EPSILON:
            out[d] = "ahead"
        else:
            out[d] = "on"
    return out


def flips(st_by_day: dict[int, str]) -> list[int]:
    """The days spending moved ahead of the usual pace (on → ahead)."""
    out, prev = [], None
    for d in sorted(st_by_day):
        s = st_by_day[d]
        if s == "ahead" and prev in (None, "on", "none"):
            out.append(d)
        if s in ("on", "ahead", "none"):
            prev = s
    return out


# ── What's due ──────────────────────────────────────────────────────────

def due_items(st, transactions: list[Transaction], today: date, sts: dict,
              until: date) -> list[dict]:
    """Bills and pay from today to `until`, and the chests' monthly amounts
    on each 1st in between. Bills and pay this month are safe to spend's own
    lines; next month's bills are the recurring ones expected then."""
    from . import api as core, safe_to_spend, income_bills
    out: list[dict] = []
    rows = {r["key"]: r for r in sts.get("rows", [])}
    month = today.strftime("%Y-%m")

    def add(kind, label, amount, iso, note=""):
        if not iso or iso < today.isoformat() or iso > until.isoformat():
            return
        out.append({"kind": kind, "label": label, "amount": round(float(amount), 2),
                    "date": iso[:10], "note": note})

    for b in (rows.get("bills") or {}).get("lines", []):
        if b.get("date") and not b.get("late"):
            note = "Estimated" if b.get("estimate") else ("Suggested" if b.get("suggested") else "")
            add("bill", b["label"], b["amount"], b["date"], note)
    for line in (rows.get("income") or {}).get("lines", []):
        if not line.get("arrived") and line.get("date"):
            add("pay", "Pay", line["amount"], line["date"], f"{line['label']} · expected" if line.get("label") else "expected")
    # Next month's bills, as they're expected from their history.
    nxt = _month_add(month, 1)
    if until.strftime("%Y-%m") >= nxt:
        first_next = date.fromisoformat(f"{nxt}-01")
        try:
            for b in safe_to_spend.bills_to_come(transactions, first_next,
                                                 st.float_setting("home_rent", 0.0),
                                                 income_bills.load(st)):
                if b.get("date"):
                    note = "Estimated" if b.get("estimate") else ""
                    add("bill", b["label"], b["amount"], b["date"], note)
        except Exception:  # pragma: no cover - the calendar never breaks on bills
            pass
        pay_next = sts.get("next_pay")
        pay_amount = next((line["amount"] for line in (rows.get("income") or {}).get("lines", [])
                           if line.get("kind") == "salary"), None)
        if pay_next and pay_next[:7] == nxt and pay_amount:
            add("pay", "Pay", pay_amount, pay_next, "expected")
    # The chests fill from the Anchor on the 1st (THL-230).
    cursor = date.fromisoformat(f"{_month_add(month, 1)}-01")
    chests = core._bank_status(st)
    while cursor <= until:
        for c in chests:
            monthly = c["monthly"] if c["monthly"] > 0.005 else c["base_monthly"]
            start = c.get("start_month") or ""
            if monthly > 0.005 and cursor.strftime("%Y-%m") >= start:
                add("chest", f"{c['name']} from Anchor", monthly, cursor.isoformat())
        cursor = date.fromisoformat(f"{_month_add(cursor.strftime('%Y-%m'), 1)}-01")
    order = {"pay": 0, "bill": 1, "chest": 2}
    out.sort(key=lambda x: (x["date"], order[x["kind"]], x["label"]))
    return out


# ── The pages ───────────────────────────────────────────────────────────

def _usual_for(st, transactions, month: str) -> dict:
    from . import api as core, usual_month
    first = date.fromisoformat(f"{month}-01")
    return usual_month.usual(transactions, first, unusual=core._unusual_months(st))


def totals(transactions: list[Transaction], month: str, upto: date) -> dict:
    spent = income = moving = 0.0
    end = upto.isoformat()
    for t in transactions:
        if t.month != month or t.date[:10] > end or t.excluded:
            continue
        if counts_as_spending(t):
            spent += spend_amount(t)
        elif _counts_as_income(t):
            income += -t.amount
        elif t.category in MOVING and t.amount > 0:
            moving += t.amount
    return {"spent": round(spent, 2), "income": round(income, 2), "moving": round(moving, 2)}


def spent_rows(transactions: list[Transaction], iso: str, names: dict | None = None) -> list[dict]:
    """What was spent on a day, biggest first."""
    rows = []
    for t in transactions:
        if t.date[:10] != iso or t.excluded or not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        label = cat if cat != "Unsorted transfers" else "Not sorted yet"
        rows.append({"id": t.fingerprint, "merchant": (names or {}).get(t.fingerprint) or t.merchant or t.description,
                     "category": label, "unusual": bool(t.one_off_since),
                     "amount": round(spend_amount(t), 2)})
    rows.sort(key=lambda r: -r["amount"])
    return rows


def reason(state: str, day: int, st_by_day: dict[int, str], rows: list[dict]) -> str:
    """One calm line on why a day is shaded (CAL-02, CAL-03)."""
    if state == "future":
        return "Upcoming days only show what’s due. Safe to spend already counts these."
    if state == "today":
        return "Today isn’t finished. It’s shaded once the day ends."
    if state == "none":
        return "Nothing to compare with yet: Pearl needs a full month to know your usual pace."
    if state == "on":
        return "On or under your usual pace by the end of this day."
    if day in flips(st_by_day):
        total = sum(r["amount"] for r in rows)
        big = rows[0] if rows else None
        if big and total > 0 and big["amount"] >= total * 0.5:
            return f"Spending moved ahead of your usual pace after this day, mostly from one {big['merchant']} purchase."
        return "Spending moved ahead of your usual pace after this day."
    return "Spending was still ahead of your usual pace at the end of this day."


def month_view(st, transactions: list[Transaction], today: date, month: str,
               sts: dict | None = None) -> dict:
    from . import api as core
    sts = sts if sts is not None else core._home_sts(st, transactions, today)
    usual = _usual_for(st, transactions, month)
    st_by_day = states(transactions, today, month, usual)
    days = _days_in(month)
    first = date.fromisoformat(f"{month}-01")
    # Sunday first, six rows (CAL-01).
    lead = (first.weekday() + 1) % 7
    grid_start = first - timedelta(days=lead)
    grid_end = grid_start + timedelta(days=41)
    due_until = max(grid_end, date.fromisoformat(f"{_month_add(today.strftime('%Y-%m'), 1)}-{_days_in(_month_add(today.strftime('%Y-%m'), 1)):02d}"))
    due = due_items(st, transactions, today, sts, due_until) if grid_end >= today else []
    by_date: dict[str, list[dict]] = defaultdict(list)
    for item in due:
        by_date[item["date"]].append(item)
    cells = []
    cursor = grid_start
    for _ in range(42):
        iso = cursor.isoformat()
        in_month = iso[:7] == month
        d = cursor.day
        if in_month:
            state = st_by_day.get(d, "none")
        elif iso < today.isoformat():
            state = "outside"
        elif iso == today.isoformat():
            state = "today"
        else:
            state = "future"
        cells.append({"date": iso, "day": d, "in_month": in_month, "state": state,
                      "due": by_date.get(iso, [])})
        cursor += timedelta(days=1)
    upto = today if month == today.strftime("%Y-%m") else date.fromisoformat(f"{month}-{days:02d}")
    this_month = month == today.strftime("%Y-%m")
    return {
        "month": month, "label": f"{month_name(month)} {month[:4]}", "today": today.isoformat(),
        "this_month": this_month,
        "prev": {"month": _month_add(month, -1), "label": month_name(_month_add(month, -1))},
        "next": {"month": _month_add(month, 1), "label": month_name(_month_add(month, 1))},
        "totals": {**totals(transactions, month, upto), "so_far": this_month or month > today.strftime("%Y-%m")},
        "cells": cells,
        "has_usual": any(s in ("on", "ahead") for s in st_by_day.values()),
        "coming_up": [i for i in due if i["date"] >= today.isoformat()][:6],
        "legend": [
            {"key": "on", "label": "On or under your usual pace by the end of the day"},
            {"key": "ahead", "label": "Spending moved ahead of your usual pace"},
            {"key": "none", "label": "No data yet"},
            {"key": "today", "label": "Today"},
        ],
    }


def day_view(st, transactions: list[Transaction], today: date, iso: str,
             sts: dict | None = None) -> dict:
    from . import api as core
    sts = sts if sts is not None else core._home_sts(st, transactions, today)
    month = iso[:7]
    usual = _usual_for(st, transactions, month)
    st_by_day = states(transactions, today, month, usual)
    day = int(iso[8:10])
    state = st_by_day.get(day, "future")
    names = {}
    try:
        stored = st.merchant_names()
        names = {t.fingerprint: stored.get(" ".join((t.merchant or "").lower().split()))
                 for t in transactions if t.date[:10] == iso}
        names = {k: v for k, v in names.items() if v}
    except Exception:  # pragma: no cover
        names = {}
    rows = spent_rows(transactions, iso, names) if iso <= today.isoformat() else []
    due = []
    if iso >= today.isoformat():
        due = [i for i in due_items(st, transactions, today, sts, date.fromisoformat(iso))
               if i["date"] == iso]
    return {
        "date": iso, "label": long_day(iso), "state": state,
        "reason": reason(state, day, st_by_day, rows),
        "spent": rows, "spent_total": round(sum(r["amount"] for r in rows), 2),
        "due": due, "past": iso < today.isoformat(), "today": iso == today.isoformat(),
    }


def strip(st, transactions: list[Transaction], today: date, sts: dict | None = None) -> dict:
    """CAL-06: one cell per day of this month, and a line naming what's
    next and when spending moved ahead, if it did."""
    from . import api as core
    sts = sts if sts is not None else core._home_sts(st, transactions, today)
    month = today.strftime("%Y-%m")
    usual = _usual_for(st, transactions, month)
    st_by_day = states(transactions, today, month, usual)
    days = _days_in(month)
    end = date.fromisoformat(f"{month}-{days:02d}")
    due = due_items(st, transactions, today, sts, end + timedelta(days=35))
    due_days = {i["date"] for i in due}
    cells = [{"date": f"{month}-{d:02d}", "day": d, "state": st_by_day[d],
              "due": f"{month}-{d:02d}" in due_days} for d in range(1, days + 1)]
    parts = []
    soon = due[:2]
    if soon:
        words = [f"{'pay' if i['kind'] == 'pay' else i['label']} on {day_words(i['date'])}" for i in soon]
        parts.append(f"Next: {words[0]}{', then ' + words[1] if len(words) > 1 else ''}.")
    else:
        parts.append("Nothing due before the month ends.")
    moved = flips(st_by_day)
    if moved:
        parts.append(f"Spending moved ahead of your usual pace on {day_words(cells[moved[-1] - 1]['date'])}.")
    elif any(s == "on" for s in st_by_day.values()):
        parts.append("On or under your usual pace so far.")
    return {"month": month, "label": month_name(month), "cells": cells, "line": " ".join(parts)}
