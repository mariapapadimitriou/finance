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
* E1: with no income detected and none given there is no number at all;
  Home asks for her income instead of guessing.
* E4 (THL-47, THL-70): when pay isn't regular, income is cautious: the
  lowest of the last three full months, or what has already arrived if that
  is more. An amount she gives instead lasts until she changes it, and each
  time she overrides the cautious figure is recorded.
* S7, E5: rough and cautious numbers are shown rounded down to $10; the
  sheet keeps the exact rows and says what was rounded.
* D1, D2 (THL-49): debt minimums due this month are bills; see `debts`.

Data states (THL-14 / E10, THL-137 E-01 to E-04) are chosen by `home_state`.
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


def _full_months_before(today: date, n: int) -> list[str]:
    """The `n` calendar months before this one, oldest first."""
    out, cursor = [], today.replace(day=1)
    for _ in range(n):
        cursor = (cursor - timedelta(days=1)).replace(day=1)
        out.append(cursor.strftime("%Y-%m"))
    return out[::-1]


def cautious_income(transactions: list[Transaction], today: date) -> dict | None:
    """The lowest month of income in the last three full months (E10).

    Needs history covering all three months and income in each; a month with
    nothing in it says the figure can't be trusted, so there is none.
    """
    if not transactions:
        return None
    months = _full_months_before(today, 3)
    first = min(t.date for t in transactions)
    if first > f"{months[0]}-01":
        return None
    totals = {m: 0 for m in months}
    for t in transactions:
        if t.month in totals and is_income(t) and not t.repays and not is_others(t):
            totals[t.month] += _cents(-t.amount)
    if min(totals.values()) <= 0:
        return None
    low = min(months, key=lambda m: (totals[m], m))
    return {"lowest": _dollars(totals[low]), "month": low,
            "highest": _dollars(max(totals.values())),
            "months": [{"month": m, "amount": _dollars(totals[m])} for m in months]}


def _at_least(amount: float, received_c: int, lines: list, label: str) -> int:
    """An expected monthly figure, never less than what has already arrived;
    the part still to come becomes one line."""
    want_c = _cents(amount)
    rest_c = max(want_c - received_c, 0)
    if rest_c:
        lines.append({"label": label, "date": None, "amount": _dollars(rest_c),
                      "arrived": False, "kind": "expected"})
    return received_c + rest_c


def income_this_month(transactions: list[Transaction], today: date,
                      entered_monthly: float = 0.0, *, told: float = 0.0,
                      overridden: bool = False) -> dict:
    """What comes in this month: what has arrived plus what is still expected.

    In order: detected regular pay; then what she told us on Home (starter
    questions, or "Use a different amount"); then the cautious figure when
    pay isn't regular; then the monthly income from the older plan page.
    Never less than what has already arrived. With none, `amount` is None.
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
                "cadence": pay["cadence"], "cautious": None, "overridden": False}

    none = {"payer": "", "paycheques": 0, "next_pay": None,
            "cadence": pay["cadence"] if pay else None, "cautious": None,
            "overridden": False}
    careful = cautious_income(transactions, today)
    if told and told > 0:
        amount_c = _at_least(told, received_c, lines, "Still expected this month")
        return {**none, "amount": _dollars(amount_c), "source": "told", "lines": lines,
                "cautious": careful, "overridden": overridden}
    if careful:
        amount_c = _at_least(careful["lowest"], received_c, lines,
                             "Still expected, being cautious")
        return {**none, "amount": _dollars(amount_c), "source": "cautious",
                "lines": lines, "cautious": careful}
    if entered_monthly and entered_monthly > 0:
        amount_c = _at_least(entered_monthly, received_c, lines, "Still expected this month")
        return {**none, "amount": _dollars(amount_c), "source": "entered", "lines": lines}
    return {**none, "amount": None, "source": None, "lines": lines}


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


RENT = "Rent & Housing"


def bills_to_come(transactions: list[Transaction], today: date,
                  told_rent: float = 0.0) -> list[dict]:
    """Recurring charges expected between now and the month's end that
    haven't been charged yet, suggested ones included (S9).

    A monthly bill already charged this month is paid; one that hasn't come
    by its usual day is still to come until the month ends, marked late.
    Rent she told us about (E-02's starter questions) is a bill until rent is
    seen: as a recurring charge, or paid this month.
    """
    month = today.strftime("%Y-%m")
    first, end = today.replace(day=1), month_end(today)
    out = []
    rent_seen = False
    for rec in detect_recurring(transactions, as_of=today.isoformat()):
        if not _is_bill(rec):
            continue
        rent_seen = rent_seen or rec["category"] == RENT
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
    if told_rent and told_rent > 0 and not rent_seen:
        paid_c = sum(_cents(spend_amount(t)) for t in transactions
                     if t.month == month and t.category == RENT and counts_as_spending(t))
        if paid_c < _cents(told_rent) * 0.8:
            out.append({"label": "Rent or mortgage", "date": None,
                        "amount": _dollars(_cents(told_rent)), "estimate": False,
                        "late": False, "category": RENT, "told": True})
    out.sort(key=lambda b: (b["date"] or "9999", b["label"]))
    return out


def recurring_bills(transactions: list[Transaction], today: date) -> list[dict]:
    """Every recurring charge that is a bill (`_is_bill`)."""
    return [r for r in detect_recurring(transactions, as_of=today.isoformat()) if _is_bill(r)]


def bill_charges(transactions: list[Transaction], today: date) -> set[tuple[str, str]]:
    """(merchant, date) of every charge that was a bill: a recurring bill's
    charges, and rent. The week leaves these out, because the month already
    takes bills out before it is split into weeks (W3)."""
    out = set()
    for rec in recurring_bills(transactions, today):
        out.update((rec["merchant"], d) for d in rec["dates"])
    out.update((t.merchant, t.date) for t in transactions if t.category == RENT)
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

# Under this many days of history the number is a rough estimate (E10).
LEARNING_DAYS = 30


def history_days(transactions: list[Transaction], today: date) -> int:
    """Days of history, counting the first day and today; 0 with none."""
    if not transactions:
        return 0
    first = date.fromisoformat(min(t.date for t in transactions))
    return max((today - first).days + 1, 0)


def round_down_10(amount: float) -> int:
    """Rough and cautious numbers are shown rounded down to $10 (S7)."""
    return int(amount // 10) * 10


def compute(transactions: list[Transaction], today: date, *,
            entered_income: float = 0.0, savings_target: float = 0.0,
            anchor_started: bool = False, told_income: float = 0.0,
            told_rent: float = 0.0, overridden: bool = False,
            debt_bills: dict | None = None) -> dict:
    """Safe to spend this month and the four rows behind it.

    `debt_bills` (from `debts.bills`) adds this month's debt minimums: the
    ones still to come join the bills, and what's been paid of them joins
    what's already spent (D1, D2)."""
    month = today.strftime("%Y-%m")
    left = days_left(today)
    income = income_this_month(transactions, today, entered_income,
                               told=told_income, overridden=overridden)
    days = history_days(transactions, today)
    estimate = ("rough" if days < LEARNING_DAYS
                else "cautious" if income["source"] == "cautious" else None)
    base = {"month": month, "today": today.isoformat(), "days_left": left,
            "next_pay": income["next_pay"], "income_source": income["source"],
            "estimate": estimate, "cautious": income["cautious"],
            "overridden": income["overridden"]}
    if income["amount"] is None:
        return {**base, "state": "needs_income", "amount": None, "shown": None,
                "per_day": None, "over_by": None, "rows": []}

    bills = bills_to_come(transactions, today, told_rent)
    spent = already_spent(transactions, today)
    debt_paid_c = 0
    if debt_bills:
        bills = sorted(bills + debt_bills["lines"], key=lambda b: (b["date"] or "9999", b["label"]))
        debt_paid_c = _cents(debt_bills["paid"])
        if debt_paid_c:
            spent["amount_c"] += debt_paid_c
            spent["lines"].append({"label": "Debt payments", "amount": _dollars(debt_paid_c)})
    dated = [b for b in bills if b["date"]]
    rows = [
        {"key": "income", "amount_c": _cents(income["amount"]),
         "paycheques": income["paycheques"], "payer": income["payer"],
         "source": income["source"], "cautious": income["cautious"],
         "lines": income["lines"]},
        {"key": "bills", "amount_c": sum(_cents(b["amount"]) for b in bills),
         "count": len(bills),
         "first": dated[0]["date"] if dated else None,
         "last": dated[-1]["date"] if dated else None, "lines": bills},
        {"key": "spent", "amount_c": spent["amount_c"], "pending": spent["pending"],
         "debt_paid": _dollars(debt_paid_c), "lines": spent["lines"]},
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
    amount = _dollars(total_c)
    shown = round_down_10(amount) if estimate and not over else amount
    return {
        **base,
        "state": "over" if over else "ok",
        "amount": amount,
        # What the card shows: rounded down to $10 for an estimate (S7, E5).
        "shown": shown,
        "per_day": None if over else _dollars(_cents(shown) // left),
        "over_by": _dollars(-total_c) if over else None,
        "rows": rows,
    }


# ── Which Home to draw (E10, THL-137) ────────────────────────────────────

def home_state(transactions: list[Transaction], today: date, sts: dict, *,
               account_types: dict[str, str] | None = None,
               linking_failed: bool = False, told_income: float = 0.0,
               told_rent: float = 0.0) -> dict:
    """Which of E-01 to E-04 Home is in, and the dates it promises.

    * no_data (E-01): nothing linked or imported, and no answers yet.
    * card_only (E-04): every account synced is a credit card, so nothing
      that comes in can be seen and there is no safe-to-spend.
    * learning (E-02): under 30 days of history (or answers but no data).
    * irregular (E-03): income is the cautious figure.
    * normal.

    `account_types` maps each synced account to its Plaid type.
    """
    days = history_days(transactions, today)
    first = (date.fromisoformat(min(t.date for t in transactions))
             if transactions else None)
    types = {t.lower() for t in (account_types or {}).values() if t}
    if not transactions and not told_income:
        kind = "no_data"
    elif transactions and types and types <= {"credit"}:
        kind = "card_only"
    elif days < LEARNING_DAYS:
        kind = "learning"
    elif sts.get("income_source") == "cautious":
        kind = "irregular"
    else:
        kind = "normal"

    learning_until = comparisons_from = None
    if first:
        learning_until = (first + timedelta(days=LEARNING_DAYS)).isoformat()
        # Comparisons with a usual month start after one full month (E2).
        full = first.replace(day=1) if first.day == 1 else _next_month(first)
        comparisons_from = _next_month(full).isoformat()

    out = {
        "kind": kind, "history_days": days,
        "first_date": first.isoformat() if first else None,
        "learning_until": learning_until, "comparisons_from": comparisons_from,
        "linking_failed": linking_failed and not transactions,
        "answers": {"income": told_income or None, "rent": told_rent or None},
        # Starter questions (E-02, E3) until she has given her income.
        "asks_questions": kind in ("learning", "no_data", "normal", "irregular")
                          and sts.get("state") == "needs_income",
    }
    # What Home can say before the snapshot can (E-02, E-04).
    spent = already_spent(transactions, today)
    out["spent_so_far"] = _dollars(spent["amount_c"])
    out["bills_found"] = sum(1 for rec in detect_recurring(transactions, as_of=today.isoformat())
                             if _is_bill(rec)) if transactions else 0
    if kind == "card_only":
        out["card_spending"] = {"amount": _dollars(spent["amount_c"]),
                                "lines": spent["lines"]}
    return out
