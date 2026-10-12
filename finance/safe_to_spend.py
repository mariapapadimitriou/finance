"""Safe to spend for the calendar month (Pearl E05: THL-44, THL-46).

One number, and every input behind it:

    safe to spend = money coming in this month
                  − bills still to come
                  − already spent (pending included)
                  − set aside for goals

The explanation sheet (X-01) lists exactly these four rows, so the sheet adds
up to the number by construction. Every amount is held in whole cents while
it is worked out and rounded once, at the edge, so the rows always sum to the
total to the cent.

Decisions this follows (THL-9 comment, 2026-10-12):

* S8: "already spent" is all spending, pending included, Essentials and
  Lifestyle alike. Transfers between her own accounts, card payments and
  friends' share of a split never count. A bill moves out of "still to come"
  and into "already spent" once it is paid.
* S9: a suggested bill counts straight away, and one past its usual date
  stays "still to come" until the month ends. Income counts once it is a
  regular, detected paycheque or she has told us what she earns.
* S5: set aside is what a monthly saving goal still needs this month: the
  goal less what has already been saved. No goal, no row.
* S6: days left include today.
* E1: with no income detected and none entered there is no number at all;
  Home asks for her income instead of guessing.

Debt minimums (THL-49) and the cautious figure for irregular income
(THL-47, THL-70) join this in later steps.
"""

from __future__ import annotations

import calendar
from collections import Counter
from datetime import date, timedelta

from .analytics import counts_as_spending, invested_in, is_others, spend_amount
from .categorize import group_of, is_spend_category
from .income import cadence, is_income, kind_of
from .insights.recurring import detect_recurring
from .models import Transaction

# A paycheque that lands a few days early is the one expected, not an extra.
PAY_TOLERANCE_DAYS = 5
# Pay stops counting as regular once this long has passed with none arriving
# (two cycles, plus the tolerance): a job that ended is not income to expect.
STALE_PAY_DAYS = {"biweekly": 28 + PAY_TOLERANCE_DAYS,
                  "semimonthly": 31 + PAY_TOLERANCE_DAYS,
                  "monthly": 62 + PAY_TOLERANCE_DAYS}
# An amount this far from the usual one makes a bill an estimate (Hydro, not
# Netflix).
ESTIMATE_CENTS = 50


def _cents(x: float) -> int:
    return int(round(x * 100))


def _dollars(c: int) -> float:
    return round(c / 100, 2)


def month_end(d: date) -> date:
    return d.replace(day=calendar.monthrange(d.year, d.month)[1])


def days_left(today: date) -> int:
    """Days left in the month, today included (S6)."""
    return (month_end(today) - today).days + 1


def _on_day(year: int, month: int, day: int) -> date:
    """`day` of a month, or its last day when the month is shorter. A pay day
    or bill on the 28th or later is taken as month end."""
    last = calendar.monthrange(year, month)[1]
    return date(year, month, last if day >= 28 else min(day, last))


def _next_month(d: date) -> date:
    return (d.replace(day=1) + timedelta(days=32)).replace(day=1)


# ── Money coming in ──────────────────────────────────────────────────────

def _received(transactions: list[Transaction], month: str, today: date) -> list[Transaction]:
    """Income that has arrived this month. A friend paying back their share
    of something is never income (THL-125): it comes off the charge instead."""
    return sorted(
        (t for t in transactions
         if t.month == month and t.date <= today.isoformat()
         and is_income(t) and not t.repays and not is_others(t)),
        key=lambda t: t.date)


def _pay_days_of_month(days: list[date]) -> list[int]:
    """The days of the month pay is due on, from the last four paydays.

    Pay due on the 1st lands on the 30th when the 1st is a weekend, so the
    last few days of a month count as the turn of the next one. Paydays
    within a few days of each other are the same payday.
    """
    values = []
    for d in days[-4:]:
        length = calendar.monthrange(d.year, d.month)[1]
        day = d.day - length if d.day > length - PAY_TOLERANCE_DAYS else d.day
        values.append((day, d))
    values.sort()
    groups: list[list[tuple[int, date]]] = [[values[0]]]
    for v in values[1:]:
        if v[0] - groups[-1][-1][0] <= PAY_TOLERANCE_DAYS:
            groups[-1].append(v)
        else:
            groups.append([v])
    out = []
    for g in groups:
        # Pay due on a weekend comes early, never late, so the latest day in
        # the group is the day it is due.
        day = max(v[0] for v in g)
        out.append(31 if day <= 0 else day)     # the turn of the month, at its end
    return sorted(set(out))


def _paydays_after(pay: dict, after: date, until: date) -> list[date]:
    """Paydays expected after `after` and up to `until` that haven't landed.

    A payday counts as landed when a paycheque arrived within a few days of
    it, so pay that comes early is never counted twice.
    """
    days = sorted(date.fromisoformat(d) for d in pay["paydays"])
    last = days[-1]
    out: list[date] = []
    if pay["cadence"] == "biweekly":
        d = last + timedelta(days=14)
        while d <= until:
            if d > after:
                out.append(d)
            d += timedelta(days=14)
        return out
    pattern = _pay_days_of_month(days)
    if pay["cadence"] == "monthly":
        pattern = pattern[-1:]
    cursor = days[0].replace(day=1)
    while cursor <= until:
        for day in pattern:
            d = _on_day(cursor.year, cursor.month, day)
            landed = any(abs((d - p).days) <= PAY_TOLERANCE_DAYS for p in days)
            if after < d <= until and d > days[0] and not landed:
                out.append(d)
        cursor = _next_month(cursor)
    return sorted(set(out))


def income_this_month(transactions: list[Transaction], today: date,
                      entered_monthly: float = 0.0) -> dict:
    """What comes in this month: what has arrived plus what is still expected.

    Detected regular pay wins; otherwise the monthly income she gave us, never
    less than what has already arrived. With neither, `amount` is None.
    """
    month = today.strftime("%Y-%m")
    end = month_end(today)
    received = _received(transactions, month, today)
    received_c = sum(_cents(-t.amount) for t in received)
    lines = [{"label": t.merchant or t.description, "date": t.date,
              "amount": _dollars(_cents(-t.amount)), "arrived": True,
              "kind": kind_of(t)} for t in received]

    pay = cadence(transactions, today.isoformat())
    regular = (pay is not None and pay["cadence"] in STALE_PAY_DAYS
               and (today - date.fromisoformat(max(pay["paydays"]))).days
               <= STALE_PAY_DAYS[pay["cadence"]])
    next_pay = None
    if regular:
        salary_rows = [t for t in transactions
                       if is_income(t) and kind_of(t) == "salary"]
        payer = Counter(t.merchant or t.description for t in salary_rows).most_common(1)
        payer = payer[0][0] if payer else ""
        # Paydays this month that haven't landed, late ones included (S9).
        expected = _paydays_after(pay, today.replace(day=1) - timedelta(days=1), end)
        each_c = _cents(pay["paycheque"])
        for d in expected:
            lines.append({"label": payer, "date": d.isoformat(),
                          "amount": _dollars(each_c), "arrived": False, "kind": "salary"})
        upcoming = _paydays_after(pay, today, end + timedelta(days=62))
        next_pay = upcoming[0].isoformat() if upcoming else None
        amount_c = received_c + each_c * len(expected)
        paycheques = sum(1 for line in lines if line["kind"] == "salary")
        return {"amount": _dollars(amount_c), "source": "detected", "payer": payer,
                "paycheques": paycheques, "lines": lines, "next_pay": next_pay,
                "cadence": pay["cadence"]}

    if entered_monthly and entered_monthly > 0:
        entered_c = _cents(entered_monthly)
        rest_c = max(entered_c - received_c, 0)
        if rest_c:
            lines.append({"label": "Still expected this month", "date": None,
                          "amount": _dollars(rest_c), "arrived": False, "kind": "entered"})
        return {"amount": _dollars(received_c + rest_c), "source": "entered", "payer": "",
                "paycheques": 0, "lines": lines, "next_pay": None, "cadence": None}

    return {"amount": None, "source": None, "payer": "", "paycheques": 0,
            "lines": lines, "next_pay": None, "cadence": pay["cadence"] if pay else None}


# ── Bills still to come ──────────────────────────────────────────────────

def _is_bill(rec: dict) -> bool:
    """A live recurring spending charge. Something bought every week or two
    is a bill only when it is an Essential (childcare, a transit pass); a
    weekly coffee is a habit, and counting it as a bill would hold money back
    twice, once here and again when it is spent."""
    category = rec.get("category") or "Other"
    if not (rec.get("active", False) and is_spend_category(category)):
        return False
    if rec["cadence"] in ("weekly", "biweekly"):
        return group_of(category) == "essentials"
    return True


def bills_to_come(transactions: list[Transaction], today: date) -> list[dict]:
    """Recurring charges expected between now and the month's end that
    haven't been charged yet, suggested ones included (S9).

    A monthly bill already charged this month is paid; one that hasn't come
    by its usual day is still to come until the month ends, marked late.
    """
    month = today.strftime("%Y-%m")
    first, end = today.replace(day=1), month_end(today)
    out = []
    for rec in detect_recurring(transactions, as_of=today.isoformat()):
        if not _is_bill(rec):
            continue
        dates = [date.fromisoformat(d) for d in rec["dates"]]
        last = dates[-1]
        charged_this_month = any(d.strftime("%Y-%m") == month for d in dates)
        due: list[date] = []
        if rec["cadence"] in ("weekly", "biweekly"):
            step = timedelta(days=7 if rec["cadence"] == "weekly" else 14)
            d = last + step
            while d <= end:
                if d >= first:
                    due.append(d)
                d += step
        elif rec["cadence"] == "monthly":
            if not charged_this_month:
                due.append(_on_day(today.year, today.month, last.day))
        else:                                   # quarterly, semiannual, annual
            d = date.fromisoformat(rec["next_expected"])
            if first <= d <= end and not charged_this_month:
                due.append(d)

        estimate = abs(_cents(rec["amount"]) - _cents(rec["typical_amount"])) >= ESTIMATE_CENTS
        each_c = _cents(rec["typical_amount"] if estimate else rec["amount"])
        for d in due:
            out.append({"label": rec["merchant"], "date": d.isoformat(),
                        "amount": _dollars(each_c), "estimate": estimate,
                        "late": d < today, "category": rec["category"],
                        "suggested": True})
    out.sort(key=lambda b: (b["date"], b["label"]))
    return out


# ── Already spent ────────────────────────────────────────────────────────

GROUP_LABELS = {"essentials": "Essentials", "lifestyle": "Lifestyle",
                "transfer": "Transfers we couldn't place"}


def already_spent(transactions: list[Transaction], today: date) -> dict:
    """Everything spent this month so far, pending included (S8)."""
    month = today.strftime("%Y-%m")
    by_group: dict[str, int] = {}
    pending_c = 0
    for t in transactions:
        if t.month != month or t.date > today.isoformat() or not counts_as_spending(t):
            continue
        c = _cents(spend_amount(t))
        g = group_of(t.category or "Other")
        by_group[g] = by_group.get(g, 0) + c
        if (t.raw or {}).get("pending"):
            pending_c += c
    total_c = sum(by_group.values())
    lines = [{"label": GROUP_LABELS.get(g, g.title()), "amount": _dollars(c)}
             for g, c in sorted(by_group.items(), key=lambda kv: -kv[1]) if c]
    return {"amount_c": total_c, "pending": _dollars(pending_c), "lines": lines}


# ── The number ───────────────────────────────────────────────────────────

def compute(transactions: list[Transaction], today: date, *,
            entered_income: float = 0.0, savings_target: float = 0.0,
            anchor_started: bool = False) -> dict:
    """Safe to spend this month and the four rows behind it."""
    month = today.strftime("%Y-%m")
    left = days_left(today)
    income = income_this_month(transactions, today, entered_income)
    base = {"month": month, "today": today.isoformat(), "days_left": left,
            "next_pay": income["next_pay"], "income_source": income["source"]}
    if income["amount"] is None:
        return {**base, "state": "needs_income", "amount": None, "per_day": None,
                "over_by": None, "rows": []}

    bills = bills_to_come(transactions, today)
    spent = already_spent(transactions, today)
    rows = [
        {"key": "income", "amount_c": _cents(income["amount"]),
         "paycheques": income["paycheques"], "payer": income["payer"],
         "source": income["source"], "lines": income["lines"]},
        {"key": "bills", "amount_c": sum(_cents(b["amount"]) for b in bills),
         "count": len(bills),
         "first": bills[0]["date"] if bills else None,
         "last": bills[-1]["date"] if bills else None, "lines": bills},
        {"key": "spent", "amount_c": spent["amount_c"], "pending": spent["pending"],
         "lines": spent["lines"]},
    ]
    if savings_target > 0:
        target_c = _cents(savings_target)
        saved_c = _cents(invested_in(transactions, month))
        rows.append({"key": "set_aside", "amount_c": max(target_c - saved_c, 0),
                     "goal": "anchor" if anchor_started else "saving_goal",
                     "target": _dollars(target_c), "saved": _dollars(saved_c),
                     "lines": []})

    total_c = rows[0]["amount_c"] - sum(r["amount_c"] for r in rows[1:])
    for r in rows:
        r["amount"] = _dollars(r.pop("amount_c"))
    over = total_c < 0
    return {
        **base,
        "state": "over" if over else "ok",
        "amount": _dollars(total_c),
        "per_day": None if over else _dollars(total_c // left),
        "over_by": _dollars(-total_c) if over else None,
        "rows": rows,
    }
