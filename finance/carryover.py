"""Last month's surplus or shortfall, carried into this one (THL-212).

When a month ends, the next adjusts for how it really went (Maria,
2026-10-13). What carries is the month's result: the income that
actually arrived, less everything counted as spent (bills included). What
she put away is reported beside it, never subtracted — money moved to
savings is still hers (2026-10-14) — and transfers she hasn't sorted are
left out. An income that came in under what she planned with, or a month
she overspent, both show up here; so does money left over.

* A shortfall is asked about each time: take it from this month, or spread
  it over two or three. Until she answers, nothing changes.
* Money to spare is suggested for saving — her Anchor, or a treasure chest —
  or spending this month. Unanswered for seven days, it's added to this
  month's Allowance.

A month is skipped when Pearl didn't see all of it (her first linked month)
or no income arrived in it. The result is worked out again each time until
she answers, so a charge that posts late still counts; her answer fixes it.

Kept as one setting, `carryover`: {"2026-09": {"amount", "found_on",
"choice", "decided_on"}}.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount, invested_in
from .safe_to_spend import _cents, _counts_as_income, _dollars, already_spent, month_end

SETTING = "carryover"
ANSWER_DAYS = 7
SHORT_CHOICES = {"now": 1, "spread2": 2, "spread3": 3}
SPARE_CHOICES = {"save": 0, "chest": 0, "spend": 1}
# Less than this either way isn't worth a question.
MIN_C = 1000


def _prev(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y - 1}-12" if m == 1 else f"{y}-{m - 1:02d}"


def _next(month: str) -> str:
    y, m = map(int, month.split("-"))
    return f"{y + 1}-01" if m == 12 else f"{y}-{m + 1:02d}"


def _months_after(start: str, month: str) -> int:
    """How many months `month` is after `start` (0 when the same)."""
    (y1, m1), (y2, m2) = map(int, start.split("-")), map(int, month.split("-"))
    return (y2 - y1) * 12 + (m2 - m1)


def result(transactions, month: str, saved: float | None = None) -> dict | None:
    """The month's result — counted income less counted spending — or None
    when it can't be told. What she put away (`saved`) is reported beside
    it but never subtracted (2026-10-14): money moved to savings is still
    hers, not a shortfall; and transfers she hasn't sorted are left out."""
    if not transactions or min(t.date for t in transactions) > f"{month}-03":
        return None                                     # Pearl didn't see all of it
    income_c = sum(_cents(-t.amount) for t in transactions
                   if t.month == month and _counts_as_income(t))
    if income_c <= 0:
        return None
    end = month_end(date.fromisoformat(f"{month}-01"))
    spent_c = already_spent(transactions, end)["amount_c"]
    # A transfer she hasn't sorted counts as spending on Home until she does
    # (an undecided dollar is assumed gone), but it isn't the month's result:
    # left out here, and said so, rather than reported as a shortfall.
    unsorted_c = sum(_cents(spend_amount(t)) for t in transactions
                     if t.month == month and t.category == "Unsorted transfers"
                     and counts_as_spending(t))
    spent_c -= unsorted_c
    saved_c = _cents(saved if saved is not None else invested_in(transactions, month))
    return {"month": month, "income": _dollars(income_c), "spent": _dollars(spent_c),
            "saved": _dollars(saved_c), "unsorted": _dollars(unsorted_c),
            "amount": _dollars(income_c - spent_c)}


def load(store) -> dict:
    try:
        data = json.loads(store.setting(SETTING) or "{}")
    except (TypeError, ValueError):
        data = {}
    return data if isinstance(data, dict) else {}


def save(store, data: dict) -> None:
    store.set_setting(SETTING, json.dumps(data, sort_keys=True))


def question(store, transactions, today: date) -> dict | None:
    """Last month's result, for Home to ask about: None when there's nothing
    to say. Recorded the first time it's seen, so the 7 days can run."""
    month = _prev(today.strftime("%Y-%m"))
    data = load(store)
    entry = data.get(month)
    if entry is None or entry.get("choice") is None:
        from .savings import put_away_month
        r = result(transactions, month, saved=put_away_month(store, transactions, month))
        if r is None or abs(_cents(r["amount"])) < MIN_C:
            return None
        found = (entry or {}).get("found_on") or today.isoformat()
        entry = {**(entry or {}), "amount": r["amount"], "found_on": found,
                 "choice": None, "income": r["income"], "spent": r["spent"], "saved": r["saved"],
                 "unsorted": r["unsorted"]}
        if data.get(month) != entry:
            data[month] = entry
            save(store, data)
    kind = "short" if entry["amount"] < 0 else "spare"
    deadline = (date.fromisoformat(entry["found_on"]) + timedelta(days=ANSWER_DAYS)).isoformat()
    auto = kind == "spare" and entry.get("choice") is None and today.isoformat() >= deadline
    return {"month": month, "kind": kind, "amount": abs(entry["amount"]),
            "income": entry.get("income"), "spent": entry.get("spent"),
            "saved": entry.get("saved"), "unsorted": entry.get("unsorted") or 0.0, "choice": entry.get("choice") or ("spend" if auto else None),
            "auto": auto, "deadline": deadline if kind == "spare" else None}


def answer(store, month: str, choice: str, today: date) -> dict | None:
    """Her answer for a month; None when the choice doesn't fit it."""
    data = load(store)
    entry = data.get(month)
    if entry is None:
        return None
    allowed = SHORT_CHOICES if entry["amount"] < 0 else SPARE_CHOICES
    if choice not in allowed:
        return None
    entry.update(choice=choice, decided_on=today.isoformat())
    save(store, data)
    return entry


def applied(store, today: date) -> dict | None:
    """What carries into this month: {"amount_c" (signed), "parts"}, or None.

    A shortfall spread over n months comes off this one and the next n-1, in
    cents, the first month taking any odd cent. Money to spare she chose to
    spend, or left for 7 days, is added here."""
    this = today.strftime("%Y-%m")
    total_c, parts = 0, []
    for month, e in sorted(load(store).items()):
        choice = e.get("choice")
        amount_c = _cents(e.get("amount") or 0)
        if choice is None and amount_c > 0 and e.get("found_on"):
            due = date.fromisoformat(e["found_on"]) + timedelta(days=ANSWER_DAYS)
            choice = "spend" if today >= due else None
        n = (SHORT_CHOICES if amount_c < 0 else SPARE_CHOICES).get(choice or "", 0)
        i = _months_after(_next(month), this)
        if not n or not 0 <= i < n:
            continue
        each = abs(amount_c) // n
        part = each + (abs(amount_c) - each * n if i == 0 else 0)
        signed = part if amount_c > 0 else -part
        total_c += signed
        parts.append({"from": month, "amount": _dollars(abs(signed)),
                      "kind": "short" if amount_c < 0 else "spare", "index": i + 1, "of": n})
    return {"amount_c": total_c, "parts": parts} if parts else None
