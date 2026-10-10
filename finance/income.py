"""What kind of income each deposit is, and how often pay arrives.

Money categorised Income gets a type: salary, bonus, interest, gifts,
government, tax_refund or other. A type you chose is never overwritten; the
rest are worked out here from the description and Plaid's own category.

Pay is usually biweekly, which makes a calendar month a poor measure of it:
most months hold two paycheques and two a year hold three. So when salary
arrives about every two weeks, a typical month is one paycheque × 26 ÷ 12, and
the months with a third paycheque are pointed out rather than taken as a raise.
"""

from __future__ import annotations

import re
import statistics
from datetime import date, timedelta

from .models import Transaction

KINDS = {
    "salary": "Salary",
    "bonus": "Bonus / irregular",
    "interest": "Interest",
    "gifts": "Gifts received",
    "government": "Government credits",
    "tax_refund": "Tax refund",
    "other": "Other income",
}

_TAX_REFUND = re.compile(r"\b(canada rit|tax refund|cra refund|income tax ref\w*)\b", re.I)
_GOVERNMENT = re.compile(
    r"\b(canada (?:fed|carbon|ccb|gst|pro)\w*|gst ?c?|hst credit|ccb|caip|"
    r"climate action|child benefit|canada child|ei benefit|employment ins\w*|"
    r"cpp|oas|trillium|ontario (?:energy|trillium)|govt|government)\b", re.I)
_INTEREST = re.compile(r"\b(interest|int paid|interest earned|dividend\w*)\b", re.I)
_SALARY = re.compile(
    r"\b(payroll|direct dep\w*|salary|wages?|pay ?(?:roll|cheque|check)|"
    r"dep(?:osit)? payroll|pay(?:ment)? from employer|bi-?weekly pay)\b", re.I)

# A salary deposit this many times the usual paycheque is a bonus, not pay.
BONUS_FACTOR = 1.5


def _text(t: Transaction) -> str:
    raw = t.raw or {}
    return " ".join(str(x or "") for x in (
        t.description, t.merchant, raw.get("counterparty"), raw.get("issuer_category")))


def is_income(t: Transaction) -> bool:
    return (t.category or "") == "Income" and t.amount < 0 and not t.excluded


def guess(t: Transaction) -> str:
    """The type a deposit looks like, before bonuses are told apart."""
    text = _text(t)
    detail = str((t.raw or {}).get("issuer_category") or "").lower()
    if _TAX_REFUND.search(text) or detail == "income_tax_refund":
        return "tax_refund"
    if _GOVERNMENT.search(text) or detail in ("income_retirement_pension",
                                              "income_unemployment"):
        return "government"
    if _INTEREST.search(text) or detail in ("income_interest_earned", "income_dividends"):
        return "interest"
    if _SALARY.search(text) or detail == "income_wages":
        return "salary"
    return "other"


def classify(transactions: list[Transaction]) -> dict[str, str]:
    """{txn_id: kind} for every income row whose type wasn't chosen by you."""
    rows = [t for t in transactions if is_income(t)]
    kinds = {t.fingerprint: guess(t) for t in rows}
    pay = [-t.amount for t in rows if kinds[t.fingerprint] == "salary"]
    if len(pay) >= 3:
        usual = statistics.median(pay)
        for t in rows:
            if kinds[t.fingerprint] == "salary" and -t.amount > usual * BONUS_FACTOR:
                kinds[t.fingerprint] = "bonus"
    yours = {t.fingerprint for t in rows if t.income_type_source == "user"}
    return {tid: k for tid, k in kinds.items() if tid not in yours}


def apply_income_types(store, transactions: list[Transaction] | None = None) -> int:
    txns = transactions if transactions is not None else store.all_transactions()
    current = {t.fingerprint: t.income_type for t in txns}
    changes = {tid: k for tid, k in classify(txns).items() if current.get(tid) != k}
    return store.write_income_types(changes)


def kind_of(t: Transaction) -> str:
    return t.income_type or guess(t)


def cadence(transactions: list[Transaction], today: str | None = None) -> dict | None:
    """How often pay arrives, from the last six months of salary.

    {"cadence": "biweekly" | "semimonthly" | "monthly" | "irregular",
     "paycheque": median deposit, "monthly": a typical month,
     "three_pay_months": months that held a third paycheque}
    or None with fewer than three paycheques to go on.
    """
    end = date.fromisoformat(today) if today else date.today()
    start = end - timedelta(days=183)
    # Paycheques on the same day (a split deposit) count as one.
    by_day: dict[str, float] = {}
    for t in transactions:
        if is_income(t) and kind_of(t) == "salary" and t.date[:10] >= start.isoformat():
            by_day[t.date[:10]] = by_day.get(t.date[:10], 0.0) - t.amount
    days = sorted(by_day)
    if len(days) < 3:
        return None
    gaps = [(date.fromisoformat(b) - date.fromisoformat(a)).days
            for a, b in zip(days, days[1:])]
    gap = statistics.median(gaps)
    paycheque = round(statistics.median(by_day.values()), 2)
    # Every 14 days exactly is biweekly; twice a month on set dates gives gaps
    # that wander between 13 and 17 instead.
    fortnights = sum(1 for g in gaps if g == 14) / len(gaps)
    if fortnights >= 0.6:
        kind, per_month = "biweekly", paycheque * 26 / 12
    elif 25 <= gap <= 35:
        kind, per_month = "monthly", paycheque
    elif 10 <= gap <= 20:
        kind, per_month = "semimonthly", paycheque * 2
    else:
        kind, per_month = "irregular", None
    counts: dict[str, int] = {}
    for d in days:
        counts[d[:7]] = counts.get(d[:7], 0) + 1
    three = sorted(m for m, n in counts.items() if n >= 3) if kind == "biweekly" else []
    return {"cadence": kind, "paycheque": paycheque,
            "monthly": round(per_month, 2) if per_month else None,
            "three_pay_months": three, "paydays": days}


def by_type(transactions: list[Transaction], month: str) -> dict[str, float]:
    """Income in a month, split by type, largest first."""
    out: dict[str, float] = {}
    for t in transactions:
        if t.month == month and is_income(t):
            k = kind_of(t)
            out[k] = round(out.get(k, 0.0) - t.amount, 2)
    return dict(sorted(out.items(), key=lambda kv: -kv[1]))
