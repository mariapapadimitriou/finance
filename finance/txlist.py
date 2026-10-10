"""The transactions list (THL-122): what each row says, and the totals above it.

Every row answers four questions the screen asks of it:

* what to show as the amount — your share, never with a minus sign;
* whether it counts — as spending, as income, or not at all ("Counts = No":
  transfers between your accounts, card payments, money paid back to you,
  savings and loans);
* what chip it wears — the category, or Transfer / Repayment / Not sorted yet —
  and whether that chip is only Pearl's suggestion;
* the one-line note that explains anything unusual about it.

The rules come from analytics (`counts_as_spending`, `share_amount`,
`spend_amount`, `is_others`) so the list and the month can never disagree:
pending charges count, a split counts for your share, and a row that is not
yours at all is not listed.
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from .analytics import counts_as_spending, is_others, share_amount, spend_amount
from .categorize import CATEGORY_GROUPS, group_of
from .income import is_income
from .models import Transaction

PAGE = 25
NOTE_MAX = 140

# Sources that mean a person, not Pearl, chose the category.
_CHOSEN = {"user", "merchant_override", "trip"}

_CARD_PAYMENT = re.compile(
    r"\b(visa|mastercard|master card|amex|american express|credit card|card payment|"
    r"payment\W*thank you|pmt thank you|autopay)\b", re.I)


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def _account_label(t: Transaction) -> str:
    return (t.account_name or t.account_id or "").replace("••", "··")


def _is_card_payment(t: Transaction) -> bool:
    raw = t.raw or {}
    if str(raw.get("account_type", "")).lower() == "credit":
        return True
    if str(raw.get("issuer_category", "")).lower().startswith("loan_payments_credit_card"):
        return True
    return bool(_CARD_PAYMENT.search(f"{t.merchant} {t.description}"))


def _who(t: Transaction) -> str:
    return str((t.raw or {}).get("counterparty") or t.merchant or "").strip()


class Context:
    """What a row needs to know about the others: the charge a repayment paid
    for, who paid back a split, and what the piggy banks are called."""

    def __init__(self, transactions: list[Transaction], confirmed: dict[str, str],
                 notes: dict[str, str], banks: dict[int, str]):
        self.by_id = {t.fingerprint: t for t in transactions}
        self.confirmed = confirmed
        self.notes = notes
        self.banks = banks
        self.paid_by: dict[str, list[str]] = defaultdict(list)
        for t in transactions:
            if t.repays:
                name = _who(t)
                if name and name not in self.paid_by[t.repays]:
                    self.paid_by[t.repays].append(name)


def describe(t: Transaction, ctx: Context) -> dict:
    """Everything the list and the detail panel show for one row."""
    cat = t.category or "Other"
    group = group_of(cat)
    inflow = t.amount < 0
    amount = abs(t.amount)
    counts = "none"          # spending | income | none
    chip = cat
    structural = False       # a chip Pearl worked out from your accounts, not a guess
    note, note_link = "", False

    if t.excluded:
        chip, structural = "Left out", True
        note = f"Left out · {t.excluded}"
    elif is_others(t):
        chip, structural = "Not yours", True
        note = f"{t.joint}’s · joint account, not yours unless you say so"
    elif t.repays:
        charge = ctx.by_id.get(t.repays)
        chip, structural, group = "Repayment", True, "transfer"
        note = (f"Paid you back for {charge.merchant} · not income" if charge
                else "Paid you back · not income")
    elif cat == "Unsorted transfers":
        chip, counts = "Not sorted yet", "spending"
        note, note_link = "Saved or spent? Tell us", True
    elif cat == "Transfers":
        chip, structural = "Transfer", True
        note = ("Card payment · not counted as spending" if _is_card_payment(t)
                else "Between your accounts · not counted")
    elif cat == "Saved":
        note = ("Taken out of savings · not income" if inflow
                else "Put away · not counted as spending")
    elif cat == "Lent":
        note = ("Paid back a loan · not income" if inflow
                else "Lent · not counted as spending")
    elif cat == "Income":
        counts = "income" if is_income(t) else "none"
    elif counts_as_spending(t):
        counts = "spending"
        amount = abs(share_amount(t))
        if inflow:
            note = "Refund"
    else:
        # A charge something else paid for: a piggy bank, or friends in full.
        amount = abs(share_amount(t))
        if t.bank_id is not None:
            bank = ctx.banks.get(t.bank_id, "piggy bank")
            note = f"Paid from {bank} · not this month’s spending"
        elif t.paid_back:
            note = "Paid back in full · not your spending"

    # A split is a charge that is partly hers: not one that is wholly someone
    # else's, and not one left out.
    split = ((t.my_share is not None or bool(t.paid_back)) and counts == "spending"
             and cat not in ("Transfers", "Unsorted transfers", "Income")
             and abs(abs(share_amount(t)) - abs(t.amount)) >= 0.005)
    if split and counts == "spending" and abs(amount - abs(t.amount)) >= 0.005:
        names = ctx.paid_by.get(t.fingerprint) or []
        with_whom = (" · split with " + ", ".join(names) if names
                     else " · joint account" if t.joint else "")
        note = f"Your share of {money(t.amount)}{with_whom}"

    if counts == "spending" and cat == "Unsorted transfers":
        toward = "Spending until it’s sorted"
    elif counts == "spending":
        toward = f"{CATEGORY_GROUPS[group]} · safe to spend"
    elif counts == "income":
        toward = "Income"
    else:
        toward = "Not counted"

    confirmed = (t.category_source in _CHOSEN
                 or ctx.confirmed.get(t.fingerprint) == cat)
    suggested = chip == "Not sorted yet" or (not structural and not confirmed)

    raw = t.raw or {}
    return {
        "id": t.fingerprint,
        "date": t.date[:10],
        "merchant": t.merchant or t.description,
        "description": t.description,
        "logo": raw.get("logo_url") or "",
        "account_id": t.account_id,
        "account": _account_label(t),
        "pending": bool(raw.get("pending")),
        "category": cat,
        "category_source": t.category_source,
        "group": group,
        "chip": {"label": chip, "suggested": suggested},
        "suggested": suggested,
        "amount": round(amount, 2),
        "full_amount": round(abs(t.amount), 2),
        "inflow": inflow,
        "counts": counts,
        "counts_toward": toward,
        "note": note,
        "note_link": note_link,
        "my_note": ctx.notes.get(t.fingerprint, ""),
        "split": split,
        "repays": t.repays,
        "excluded": t.excluded or "",
        "joint": t.joint or "",
        "share_set": bool(t.share_set),
        "bank_id": t.bank_id,
        "bank_auto": bool(t.bank_auto),
    }


# ── Filters ──────────────────────────────────────────────────────────────

def _amount_query(q: str) -> str | None:
    """"24.80", "$24.8", "1,290" → the digits to look for in an amount."""
    s = q.strip().replace("$", "").replace(",", "")
    return s if re.fullmatch(r"\d+(\.\d{0,2})?", s) else None


def _amount_matches(value: float, q: str) -> bool:
    text = f"{abs(value):.2f}"
    if "." in q:
        return text.startswith(q)
    return text.split(".")[0] == q


def matches(row: dict, q: str) -> bool:
    """Search: merchant, the bank's description, your note, and the amount."""
    q = (q or "").strip()
    if not q:
        return True
    num = _amount_query(q)
    if num is not None and (_amount_matches(row["amount"], num)
                            or _amount_matches(row["full_amount"], num)):
        return True
    needle = q.lower()
    return any(needle in (row.get(k) or "").lower()
               for k in ("merchant", "description", "my_note"))


def visible(transactions: list[Transaction]) -> list[Transaction]:
    """Rows that are yours: not excluded, not another joint member's."""
    return [t for t in transactions if not is_others(t)]


def left_out(transactions: list[Transaction]) -> list[Transaction]:
    """Rows you excluded, listed on their own so they can be put back."""
    return [t for t in transactions if t.excluded]


def theirs(transactions: list[Transaction]) -> list[Transaction]:
    """Rows on a joint account that are another member's until you say they
    were yours, listed on their own so you can."""
    return [t for t in transactions if not t.excluded and is_others(t)]


def select(rows: list[tuple[Transaction, dict]], *, month: str | None = None,
           account: str | None = None, group: str | None = None,
           category: str | None = None, counts: str | None = None,
           q: str | None = None) -> list[tuple[Transaction, dict]]:
    out = []
    for t, r in rows:
        if month and r["date"][:7] != month:
            continue
        if account and r["account_id"] != account:
            continue
        if group and r["group"] != group:
            continue
        if category and r["category"] != category:
            continue
        if counts and r["counts"] != counts:
            continue
        if q and not matches(r, q):
            continue
        out.append((t, r))
    out.sort(key=lambda p: (p[1]["date"], p[1]["id"]), reverse=True)
    return out


# ── Totals ───────────────────────────────────────────────────────────────

def totals(rows: list[tuple[Transaction, dict]]) -> dict:
    """Spent so far, Income so far and Not counted, for the rows shown.

    Spent is what the month has to pay for: your share, pending included,
    less anything a piggy bank covered (`spend_amount`), refunds netted.
    """
    spent = income = not_counted = 0.0
    for t, r in rows:
        if r["counts"] == "spending":
            spent += spend_amount(t)
        elif r["counts"] == "income":
            income += -t.amount
        else:
            not_counted += r["amount"]
    return {"spent": round(spent, 2), "income": round(income, 2),
            "not_counted": round(not_counted, 2), "count": len(rows)}


def _focus_value(tot: dict, kind: str) -> float:
    return {"spending": tot["spent"], "income": tot["income"]}.get(kind, tot["not_counted"])


def _months_before(month: str, n: int) -> list[str]:
    y, m = int(month[:4]), int(month[5:7])
    out = []
    for _ in range(n):
        m -= 1
        if m == 0:
            y, m = y - 1, 12
        out.append(f"{y:04d}-{m:02d}")
    return out


def focus(all_rows: list[tuple[Transaction, dict]], *, month: str, account: str | None,
          group: str | None, category: str | None) -> dict | None:
    """With a group or category chosen: its total this month against a usual
    month — the average of the three full months before, counting only months
    the ledger covers."""
    if not month or not (group or category):
        return None
    key = group or group_of(category)
    kind = {"income": "income", "savings": "none", "transfer": "none"}.get(key, "spending")
    label = category or CATEGORY_GROUPS.get(group, group)

    def total(m: str) -> float:
        rows = select(all_rows, month=m, account=account, group=group, category=category)
        return _focus_value(totals(rows), kind)

    first = min((r["date"][:7] for _, r in all_rows), default=month)
    prior = [m for m in _months_before(month, 3) if m >= first]
    usual = round(sum(total(m) for m in prior) / len(prior), 2) if prior else None
    return {"label": label, "kind": kind, "total": round(total(month), 2), "usual": usual}


def this_month() -> str:
    return date.today().isoformat()[:7]
