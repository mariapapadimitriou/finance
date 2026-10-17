"""Every debt she has, including balances from before Pearl (THL-49, THL-128).

A debt is what a linked account reports as owed and was carried, not just
bought this month:

* a credit card, for the part of its balance carried from before Pearl or
  from an earlier month. Purchases this month are spending already, so a
  card cleared every month is never a debt (D4);
* a loan (student, car, line of credit, mortgage), for its whole balance.

Decisions this follows (THL-9 comment, 2026-10-12):

* Carried balances are shown beside Allowance and never taken out of it.
* D1: minimum payments due this month are bills, and appear in "Bills still
  to come" until they're paid.
* D2: a card's minimum counts as a bill only up to the before-Pearl balance
  still owing, since its new purchases already count as spending. A loan's
  minimum counts in full.
* D3: the before-Pearl balance is what the card owed at the first sync.
  Payments reduce that part first.
* D4: no manual "add a debt"; she can add a rate and minimum the bank doesn't
  share (D-03). Banks in Canada don't share either through Plaid, so for now
  both come from her.

A minimum paid this month moves from "still to come" into "already spent",
like any other bill (S8). Card payments and most loan payments are transfers,
so the part that counts is added to spending here; a loan payment already
counted as spending (a student loan Pearl files under Education) isn't added
twice, and a loan whose payment is already a detected bill (a mortgage under
Rent & Housing) gets no second bill.
"""

from __future__ import annotations

import calendar
import re
from datetime import date, timedelta

from .analytics import counts_as_spending
from .balances import balance_on
from .models import Transaction
from .safe_to_spend import _cents, _dollars

KINDS = {"student": "student_loan", "mortgage": "mortgage", "auto": "loan",
         "line of credit": "line_of_credit", "credit card": "card"}
# Words in an account name that say what it is, not whose it is: no use for
# matching a payment to it.
_GENERIC = {"loan", "loans", "card", "visa", "mastercard", "amex", "account", "credit",
            "line", "the", "and", "of", "my", "student", "personal", "payment", "bank"}


def kind_of(rule: dict) -> str | None:
    """card, student_loan, mortgage, line_of_credit or loan; None for an
    account that can't owe anything."""
    t = (rule.get("account_type") or "").lower()
    sub = (rule.get("account_subtype") or "").lower()
    if t == "credit":
        return "line_of_credit" if sub == "line of credit" else "card"
    if t == "loan":
        return KINDS.get(sub, "loan")
    return None


def _tokens(text: str) -> set[str]:
    return {w for w in re.findall(r"[a-z0-9]+", (text or "").lower())
            if len(w) >= 3 and w not in _GENERIC and not w.isdigit()}


def names_match(account_name: str, merchant: str) -> bool:
    """A payment to this lender: a word they share that names it (NSLSC)."""
    return bool(_tokens(account_name) & _tokens(merchant))


def _due(today: date, day) -> str | None:
    """This month's due date: the day she gave, or the month's last day when
    the month is shorter."""
    if not day:
        return None
    last = calendar.monthrange(today.year, today.month)[1]
    return today.replace(day=min(int(day), last)).isoformat()


def _payments(rows: list[Transaction], after: str, upto: str) -> int:
    """Cents paid onto a card between two days (after < date <= upto)."""
    return sum(_cents(-t.amount) for t in rows
               if after < t.date[:10] <= upto and t.amount < 0 and t.category == "Transfers")


def build(rules: dict[str, dict], balances: dict[str, dict], first: dict[str, dict],
          transactions: list[Transaction], details: dict[str, dict], today: date) -> dict:
    """Every debt, with what was carried, what's new and the minimum."""
    as_of = today.isoformat()
    month_start = today.replace(day=1)
    last_month_end = (month_start - timedelta(days=1)).isoformat()
    out = []
    for aid, rule in rules.items():
        kind = kind_of(rule)
        b = balances.get(aid) or {}
        current = b.get("current")
        if not kind or current is None or current < 1:
            continue
        current_c = _cents(current)
        d = details.get(aid) or {}
        debt = {"account_id": aid, "name": rule.get("label") or rule.get("account_name") or "Account",
                "kind": kind, "balance": _dollars(current_c),
                "rate": d.get("rate"), "minimum": d.get("minimum"),
                "due_day": d.get("due_day"),
                "due_date": _due(today, d.get("due_day")),
                "before_pearl": None, "before_pearl_at_month_start": None,
                "carried": _dollars(current_c), "new_this_month": 0.0}
        if kind in ("card", "line_of_credit"):
            rows = [t for t in transactions if t.account_id == aid]
            start = first.get(aid)
            before_c = before_start_c = 0
            if start:
                first_c = _cents(start["current"])
                before_c = max(first_c - _payments(rows, start["day"], as_of), 0)
                before_start_c = max(first_c - _payments(rows, start["day"], last_month_end), 0)
            before_c = min(before_c, current_c)
            # What the card owed when the month began, less what's been paid
            # since: anything left of it was carried in.
            then_c = _cents(balance_on(current, "credit", last_month_end, as_of, rows))
            carried_c = max(then_c - _payments(rows, last_month_end, as_of), 0)
            carried_c = min(max(carried_c, before_c), current_c)
            if carried_c < 100:
                continue                       # cleared every month: spending, not debt
            debt.update(before_pearl=_dollars(before_c),
                        before_pearl_at_month_start=_dollars(before_start_c),
                        carried=_dollars(carried_c),
                        new_this_month=_dollars(current_c - carried_c))
        out.append(debt)
    out.sort(key=lambda x: -x["balance"])
    minimums = [x["minimum"] for x in out if x["minimum"]]
    return {"debts": out, "count": len(out),
            "total": _dollars(sum(_cents(x["balance"]) for x in out)),
            "minimums": _dollars(sum(_cents(m) for m in minimums)) if minimums else None,
            "missing_details": sum(1 for x in out if not x["minimum"] or x["rate"] is None)}


def bills(debts: list[dict], transactions: list[Transaction], today: date,
          recurring_bills: list[dict]) -> dict:
    """This month's minimums as bills (D1, D2): the lines still to come, and
    what's been paid that counts as spending but isn't counted yet."""
    month = today.strftime("%Y-%m")
    to_come, paid_lines = [], []
    for d in debts:
        if not d.get("minimum"):
            continue
        min_c = _cents(d["minimum"])
        if d["kind"] in ("card", "line_of_credit"):
            amount_c = min(min_c, _cents(d["before_pearl_at_month_start"] or 0))
            rows = [t for t in transactions if t.account_id == d["account_id"]]
            paid_c = min(_payments(rows, f"{month}-00", today.isoformat()), amount_c)
            counted_c = paid_c
        else:
            # A payment Pearl already treats as a bill (a mortgage, a student
            # loan it found every month) is that bill: no second one.
            if any(names_match(d["name"], r["merchant"]) for r in recurring_bills):
                continue
            amount_c = min_c
            paid_c = counted_c = 0
            for t in transactions:
                if t.month != month or t.date > today.isoformat():
                    continue
                into_loan = t.account_id == d["account_id"] and t.amount < 0
                to_lender = (t.account_id != d["account_id"] and t.amount > 0
                             and names_match(d["name"], t.merchant))
                if into_loan or to_lender:
                    c = _cents(abs(t.amount))
                    paid_c += c
                    if to_lender and not counts_as_spending(t):
                        counted_c += c
            paid_c = min(paid_c, amount_c)
            counted_c = min(counted_c, paid_c)
        if counted_c:
            paid_lines.append({"label": d["name"], "amount": _dollars(counted_c)})
        left_c = amount_c - paid_c
        if left_c > 0:
            due = d.get("due_date")
            to_come.append({"label": f"{d['name']} minimum", "date": due,
                            "amount": _dollars(left_c), "estimate": False,
                            "late": bool(due) and due < today.isoformat(),
                            "category": "Debt", "debt": True})
    to_come.sort(key=lambda b: (b["date"] or "9999", b["label"]))
    return {"lines": to_come, "paid": _dollars(sum(_cents(p["amount"]) for p in paid_lines)),
            "paid_lines": paid_lines}
