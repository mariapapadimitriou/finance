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


def payer_of(t: Transaction) -> str:
    """Who paid a deposit, as one key: the name its regular-pay rule would
    use, else the merchant."""
    from .pay_rules import key_of
    found = key_of(t)
    return found[0] if found else "payer:" + " ".join((t.merchant or t.description or "").lower().split())


# A payer whose usual deposit is under this share of the main payer's is a
# side payout (a health-spending claim, an expense reimbursement), not a
# paycheque that sets how often she's paid or how big a paycheque is.
SIDE_PAYOUT_SHARE = 0.25


# How many deposits make a payer regular: one or two can be a one-off (a
# lump sum, a refund sent as "Direct deposit"), never a pay schedule.
REGULAR_DEPOSITS = 3


def _main_pay(rows: list[Transaction], ruled: set[str] | None = None) -> list[Transaction]:
    """Salary deposits from the payers that pay her, without side payouts
    or one-offs (2026-10-29). Two jobs both count.

    Her pay is what she said with a regular-pay rule (`ruled`: deposits a
    rule covers, or sorted by one). Without a rule, it's a payer that pays
    her regularly — three deposits or more — and the biggest of those sets
    the bar: a payer whose usual deposit is under a quarter of it is a side
    payout. Which came first doesn't matter; all of it is worked out again
    each time. A one-off lump sum, however big, never sets the bar."""
    ruled = ruled or set()
    by_payer: dict[str, list[Transaction]] = {}
    for t in rows:
        by_payer.setdefault(payer_of(t), []).append(t)
    if len(by_payer) < 2:
        return rows
    hers = {k for k, g in by_payer.items()
            if any(t.fingerprint in ruled or t.category_source == "pay_rule" for t in g)}
    regular = {k for k, g in by_payer.items() if len(g) >= REGULAR_DEPOSITS}
    usual = {k: statistics.median(-t.amount for t in g) for k, g in by_payer.items()}
    judged = hers or regular
    if not judged:
        return rows                     # nothing regular yet to tell them apart
    top = max(usual[k] for k in judged)
    keep = hers | {k for k in regular if usual[k] >= top * SIDE_PAYOUT_SHARE}
    return [t for t in rows if payer_of(t) in keep]


def classify(transactions: list[Transaction], salary: set[str] | None = None) -> dict[str, str]:
    """{txn_id: kind} for every income row whose type wasn't chosen by you.
    `salary` are the deposits a regular pay rule of hers covers (2026-10-28)."""
    rows = [t for t in transactions if is_income(t)]
    salary = salary or set()
    kinds = {t.fingerprint: "salary" if t.fingerprint in salary else guess(t) for t in rows}
    # A bonus is bigger than the usual paycheque from the same payer
    # (2026-10-29). Measured against every deposit that looks like pay, a
    # few small ones — health-spending claims, expense payouts, also sent as
    # "Direct deposit" — pulled the usual down until real paycheques read as
    # bonuses. And what her regular-pay rule covers is her regular pay,
    # whatever it comes to: its amount varies with taxable benefits.
    by_payer: dict[str, list[Transaction]] = {}
    for t in rows:
        if kinds[t.fingerprint] == "salary":
            by_payer.setdefault(payer_of(t), []).append(t)
    # A payer with too few deposits to have a usual of its own ("PAYROLL
    # ACME BONUS" beside "PAYROLL ACME") is measured against her main pay.
    main = [-t.amount for t in _main_pay([t for g in by_payer.values() for t in g], salary)]
    main_usual = statistics.median(main) if len(main) >= 3 else None
    for group in by_payer.values():
        usual = statistics.median(-t.amount for t in group) if len(group) >= 3 else main_usual
        if usual is None:
            continue
        for t in group:
            if t.fingerprint not in salary and -t.amount > usual * BONUS_FACTOR:
                kinds[t.fingerprint] = "bonus"
    yours = {t.fingerprint for t in rows if t.income_type_source == "user"}
    return {tid: k for tid, k in kinds.items() if tid not in yours}


def apply_income_types(store, transactions: list[Transaction] | None = None) -> int:
    from .pay_rules import salary_ids
    txns = transactions if transactions is not None else store.all_transactions()
    current = {t.fingerprint: t.income_type for t in txns}
    salary = salary_ids(txns, store.pay_rules())
    changes = {tid: k for tid, k in classify(txns, salary).items() if current.get(tid) != k}
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
    pay = [t for t in transactions
           if is_income(t) and kind_of(t) == "salary" and t.date[:10] >= start.isoformat()]
    for t in _main_pay(pay):
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
