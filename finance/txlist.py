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

Two more things a row can be (Pearl THL-71, THL-165): a one-off she marked
("Unusual · left out of your usual month"), still counted here; and the
second copy of a likely duplicate, listed as not counted until she answers,
then hidden if she says it was the same purchase (`duplicates`).
"""

from __future__ import annotations

import re
from collections import defaultdict
from datetime import date

from . import duplicates as dup
from .analytics import counts_as_spending, is_others, share_amount, spend_amount
from .categorize import CATEGORY_GROUPS, group_of, is_unsure
from .etransfers import party
from .income import is_income
from .models import Transaction
from .transfers import RULED

PAGE = 25
NOTE_MAX = 140

# Sources that mean a person, not Pearl, chose the category.
_CHOSEN = {"user", "merchant_override"}

_CARD_PAYMENT = re.compile(
    r"\b(visa|mastercard|master card|amex|american express|credit card|card payment|"
    r"payment\W*thank you|pmt thank you|autopay)\b", re.I)


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def _account_label(t: Transaction) -> str:
    return (t.account_label or "").replace("••", "··")


def _is_card_payment(t: Transaction) -> bool:
    raw = t.raw or {}
    if str(raw.get("account_type", "")).lower() == "credit":
        return True
    if str(raw.get("issuer_category", "")).lower().startswith("loan_payments_credit_card"):
        return True
    return bool(_CARD_PAYMENT.search(f"{t.merchant} {t.description}"))


def _who(t: Transaction) -> str:
    return str((t.raw or {}).get("counterparty") or t.merchant or "").strip()


def _key(merchant: str) -> str:
    return " ".join((merchant or "").lower().split())


def _name(t: Transaction | None, ctx: "Context") -> str:
    """What to call a row's merchant: her name for it, else the bank's."""
    if t is None:
        return ""
    return ctx.names.get(_key(t.merchant)) or t.merchant or t.description


class Context:
    """What a row needs to know about the others: the charge a repayment paid
    for, who paid back a split, and what the piggy banks are called."""

    def __init__(self, transactions: list[Transaction], confirmed: dict[str, str],
                 notes: dict[str, str], banks: dict[int, str],
                 splits: dict[str, dict] | None = None, kinds: dict[str, str] | None = None,
                 tags: dict[str, list[str]] | None = None,
                 saved_to: dict[str, str] | None = None,
                 refunds: dict[str, str] | None = None,
                 payback_kinds: dict[str, str] | None = None,
                 names: dict[str, str] | None = None,
                 accounts: dict[str, str] | None = None):
        self.by_id = {t.fingerprint: t for t in transactions}
        # Fixed or Variable, per spending row (finance/kinds.py).
        self.kinds = kinds or {}
        self.confirmed = confirmed
        self.notes = notes
        self.banks = banks
        # What was this? (2026-10-14, finance/marks.py): her tags, which
        # account a Saved row went to, the purchase a refund is of, which
        # repayments were reimbursements, her names for merchants, and what
        # each account is called (for "Put away to TD TFSA").
        self.tags = tags or {}
        self.saved_to = saved_to or {}
        self.refunds = refunds or {}
        self.payback_kinds = payback_kinds or {}
        self.names = names or {}
        self.accounts = accounts or {}
        self.reimbursed = {t.repays for t in transactions
                           if t.repays and self.payback_kinds.get(t.fingerprint) == "reimbursement"}
        self.names_for = {t.fingerprint for t in transactions if _key(t.merchant) in self.names}
        # Who a split charge was split with, as you named them (THL-124).
        self.split_with = {cid: [p["name"] for p in sp["people"]]
                           for cid, sp in (splits or {}).items()}
        # Rows with a copy still waiting for an answer (D-01), and the copies:
        # both sides say where they came from.
        self.twins = {t.duplicate_of for t in transactions if _waiting(t)}
        self.paid_by: dict[str, list[str]] = defaultdict(list)
        for t in transactions:
            if t.repays:
                name = _who(t)
                if name and name not in self.paid_by[t.repays]:
                    self.paid_by[t.repays].append(name)


def _waiting(t: Transaction) -> bool:
    """The copy of a likely duplicate, counted once until she answers."""
    return (t.duplicate_state == dup.PENDING and bool(t.duplicate_of)
            and t.excluded == dup.REASON)


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

    copy = t.excluded == dup.REASON and dup.is_copy(t)
    if copy and t.duplicate_state == dup.PENDING:
        # D-01: counted once until she checks; a question, so a dashed chip.
        chip = "Possible duplicate"
        note = "Possible duplicate · counted once until you check"
    elif copy:
        chip, structural = "Duplicate", True
        note = "Same purchase as another · hidden"
    elif t.excluded:
        chip, structural = "Left out", True
        note = f"Left out · {t.excluded}"
    elif is_others(t) and t.joint and inflow and not t.joint_from and not t.share_set:
        # Into a joint account from outside: hers or theirs? (finance/joint.py)
        chip = "Whose?"
        note, note_link = f"Yours or {t.joint}’s? Tell us", True
    elif is_others(t) and t.joint and inflow:
        who = t.joint_person or t.joint
        chip, structural = f"{who}’s", True
        note = f"{who} put this in · pays for part of this month’s joint spending"
    elif is_others(t):
        chip, structural = "Not yours", True
        note = (f"{t.joint}’s · you said this one was theirs" if t.joint
                else "Not yours")
    elif t.repays and ctx.payback_kinds.get(t.fingerprint) == "reimbursement":
        charge = ctx.by_id.get(t.repays)
        chip, structural, group = "Reimbursement", True, "transfer"
        note = (f"Reimbursed you for {_name(charge, ctx)} · not income" if charge
                else "Reimbursement · not income")
    elif t.repays:
        charge = ctx.by_id.get(t.repays)
        chip, structural, group = "Repayment", True, "transfer"
        note = (f"Paid back to me · for {_name(charge, ctx)} · comes off your spending" if charge
                else "Paid back to me · comes off your spending")
    elif cat == "Unsorted transfers":
        chip, counts = "Not sorted yet", "spending"
        note, note_link = "Saved or spent? Tell us", True
    elif cat == "Transfers":
        chip, structural = "Transfer", True
        note = ("Transfer · card payment · the purchases already counted" if _is_card_payment(t)
                else "Transfer · not counted")
    elif cat == "Saved":
        where = ctx.accounts.get(ctx.saved_to.get(t.fingerprint, ""), "")
        note = ((f"Taken out of {where} · not income" if where
                 else "Taken out of savings · not income") if inflow
                else (f"Put away to {where} · not counted as spending" if where
                      else "Put away · not counted as spending"))
    elif cat == "Lent":
        note = ("Paid back a loan · not income" if inflow
                else "Lent · not counted as spending")
    elif cat == "Borrowed":
        note = ("Borrowed · not income" if inflow
                else "Paid back what you borrowed · not counted as spending")
    elif cat == "Income":
        counts = "income" if is_income(t) else "none"
    elif counts_as_spending(t):
        counts = "spending"
        amount = abs(share_amount(t))
        if inflow:
            charge = ctx.by_id.get(ctx.refunds.get(t.fingerprint, ""))
            note = (f"Refund of {_name(charge, ctx)} · comes off {cat}" if charge
                    else f"Refund · comes off {cat}")
    else:
        # A charge something else paid for: a piggy bank, or friends in full.
        amount = abs(share_amount(t))
        if t.bank_id is not None:
            bank = ctx.banks.get(t.bank_id, "piggy bank")
            note = f"Paid from {bank} · not this month’s spending"
        elif t.paid_back and t.fingerprint in ctx.reimbursed:
            note = "Reimbursed · not your spending"
        elif t.paid_back:
            note = "Paid back in full · not your spending"

    # A split is a charge that is partly hers: not one that is wholly someone
    # else's, and not one left out.
    split = ((t.my_share is not None or bool(t.paid_back)) and counts == "spending"
             and cat not in ("Transfers", "Unsorted transfers", "Income")
             and abs(abs(share_amount(t)) - abs(t.amount)) >= 0.005)
    if split and counts == "spending" and abs(amount - abs(t.amount)) >= 0.005:
        paid = ctx.paid_by.get(t.fingerprint) or []
        names = ctx.split_with.get(t.fingerprint) or paid
        with_whom = (f" · {', '.join(paid)} paid you back" if paid
                     else " · split with " + ", ".join(names) if names
                     else f" · {t.joint} paid the rest" if t.joint else "")
        note = f"Your share of {money(t.amount)}{with_whom}"

    one_off = t.one_off and counts in ("spending", "income")
    if one_off and not note:
        note = "Unusual · left out of your usual month"

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
    # A question, not an answer (2026-10-14): only when Pearl really isn't
    # sure — the same rows Needs a look asks about. A merchant one of
    # Pearl's own rules recognised, or a category Plaid was confident of,
    # is just the category; it doesn't need confirming, and a list where
    # every row wears a question mark says nothing.
    unsure = is_unsure(t) or cat == "Other"
    suggested = (chip in ("Not sorted yet", "Possible duplicate", "Whose?")
                 or (not structural and not confirmed and unsure))

    raw = t.raw or {}
    # An e-Transfer reads as the person it was from or to (finance/etransfers.py).
    who = party(t)
    # Decided by a rule of hers: "Apply to all from…" or "Remember where
    # these go". The chip says so, so it's clear why it won't change.
    ruled = t.category_source in ("merchant_override", RULED)
    refund_of = ctx.by_id.get(ctx.refunds.get(t.fingerprint, ""))
    return {
        "id": t.fingerprint,
        "date": t.date[:10],
        "merchant": _name(t, ctx) if t.fingerprint in ctx.names_for
        else ((who or {}).get("name") or t.merchant or t.description),
        "bank_merchant": t.merchant,
        "etransfer": who,
        "description": t.description,
        "logo": raw.get("logo_url") or "",
        "account_id": t.account_id,
        "account": _account_label(t),
        "pending": bool(raw.get("pending")),
        "category": cat,
        "category_source": t.category_source,
        "ruled": ruled,
        "group": group,
        "kind": ctx.kinds.get(t.fingerprint),
        "tags": list(ctx.tags.get(t.fingerprint, [])),
        "saved_to": ctx.saved_to.get(t.fingerprint),
        "saved_to_label": ctx.accounts.get(ctx.saved_to.get(t.fingerprint, ""), ""),
        "refund_of": ({"id": refund_of.fingerprint, "merchant": _name(refund_of, ctx),
                       "date": refund_of.date[:10], "amount": abs(refund_of.amount)}
                      if refund_of else None),
        "reimbursement": ctx.payback_kinds.get(t.fingerprint) == "reimbursement",
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
        "excluded": "" if copy else (t.excluded or ""),
        # THL-71: only a row that counts can be a one-off — not a transfer,
        # a repayment you linked, or a row left out.
        "one_off": one_off,
        "one_off_since": t.one_off_since if one_off else None,
        "can_one_off": counts in ("spending", "income") and not t.repays,
        # THL-165: the pair it is in, while the question is open or answered.
        "duplicate": ({"of": t.duplicate_of, "state": t.duplicate_state}
                      if copy or t.duplicate_state == dup.DIFFERENT else None),
        "source_label": (dup.source_label(t)
                         if _waiting(t) or t.fingerprint in ctx.twins else ""),
        "joint": t.joint or "",
        "share_set": bool(t.share_set),
        "joint_from": t.joint_from or "",
        "joint_person": t.joint_person or "",
        "joint_people": list(t.joint_people or []),
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
    """Rows that are yours: not excluded, not another joint member's — and
    the copy of a likely duplicate, shown as not counted until she answers.
    A copy she said was the same purchase is not listed."""
    return [t for t in transactions if not is_others(t) or _waiting(t)]


def left_out(transactions: list[Transaction]) -> list[Transaction]:
    """Rows you excluded, listed on their own so they can be put back."""
    return [t for t in transactions if t.excluded and t.excluded != dup.REASON]


def theirs(transactions: list[Transaction]) -> list[Transaction]:
    """Rows on a joint account that are another member's until you say they
    were yours, listed on their own so you can."""
    return [t for t in transactions if not t.excluded and is_others(t)]


def select(rows: list[tuple[Transaction, dict]], *, month: str | None = None,
           account: str | None = None, group: str | None = None,
           category: str | None = None, counts: str | None = None,
           q: str | None = None, tag: str | None = None,
           merchant: str | None = None, amount_min: float | None = None,
           amount_max: float | None = None, pending: bool = False,
           look: bool = False, ids: set[str] | None = None,
           day: str | None = None, first: str | None = None,
           last: str | None = None) -> list[tuple[Transaction, dict]]:
    """The rows the filters keep. `month` of "all" keeps every month and
    "last3" the last three calendar months, this one included."""
    months = None
    if month == "last3":
        months = set(_last_months(3))
    out = []
    for t, r in rows:
        if months is not None:
            if r["date"][:7] not in months:
                continue
        elif month and month != "all" and r["date"][:7] != month:
            continue
        if day and r["date"][:10] != day[:10]:
            continue
        # A range of days (the calendar's Select days, CAL-06).
        if first and r["date"][:10] < first[:10]:
            continue
        if last and r["date"][:10] > last[:10]:
            continue
        if account and r["account_id"] != account:
            continue
        if group in ("fixed", "variable"):
            if r.get("kind") != group:
                continue
        elif group and r["group"] != group:
            continue
        if category and r["category"] != category:
            continue
        if counts and r["counts"] != counts:
            continue
        if tag and tag not in r.get("tags", []):
            continue
        if merchant and r["merchant"].strip().lower() != merchant.strip().lower():
            continue
        if amount_min is not None and r["amount"] < amount_min - 0.005:
            continue
        if amount_max is not None and r["amount"] > amount_max + 0.005:
            continue
        if pending and not r["pending"]:
            continue
        if look and not r["suggested"]:
            continue
        if ids is not None and r["id"] not in ids:
            continue
        if q and not matches(r, q):
            continue
        out.append((t, r))
    out.sort(key=lambda p: (p[1]["date"], p[1]["id"]), reverse=True)
    return out


def _last_months(n: int) -> list[str]:
    """This month and the n-1 before it."""
    today = date.today()
    y, m = today.year, today.month
    out = []
    for _ in range(n):
        out.append(f"{y:04d}-{m:02d}")
        m -= 1
        if m == 0:
            y, m = y - 1, 12
    return out


def grouped(rows: list[tuple[Transaction, dict]], by: str) -> list[dict]:
    """The rows under headers by merchant or by category (VF-01): each
    group its name, how many, what they came to, and its rows in date
    order. Biggest spending first; money in and money that doesn't count
    after, so the page reads top down."""
    out: dict[str, dict] = {}
    for t, r in rows:
        name = r["merchant"] if by == "merchant" else r["category"]
        key = name.strip().lower()
        g = out.setdefault(key, {"name": name, "logo": r["logo"] if by == "merchant" else "",
                                 "count": 0, "spent": 0.0, "income": 0.0, "not_counted": 0.0,
                                 "rows": []})
        g["count"] += 1
        g["rows"].append(r)
        if r["counts"] == "spending":
            g["spent"] += spend_amount(t)
        elif r["counts"] == "income":
            g["income"] += -t.amount
        else:
            g["not_counted"] += r["amount"]
    groups = list(out.values())
    for g in groups:
        for k in ("spent", "income", "not_counted"):
            g[k] = round(g[k], 2)
    groups.sort(key=lambda g: (-g["spent"], -g["income"], -g["not_counted"], g["name"].lower()))
    return groups


def owed(transactions: list[Transaction], splits: dict, payer: dict) -> dict | None:
    """Who still owes her on the splits she's watching: one line over the
    list ("Priya owes you $194.20 for 2 purchases")."""
    from .splits import open_repayments
    rows = open_repayments(transactions, splits, payer)
    if not rows:
        return None
    names: list[str] = []
    ids: list[str] = []
    for r in rows:
        if r["name"] not in names:
            names.append(r["name"])
        if r["charge"].fingerprint not in ids:
            ids.append(r["charge"].fingerprint)
    return {"names": names, "total": round(sum(r["owes"] for r in rows), 2),
            "count": len(ids), "ids": ids}


def by_merchant(rows: list[tuple[Transaction, dict]]) -> list[dict]:
    """The rows folded by merchant, biggest spending first: where "I didn't
    know I spent that much at X" shows up."""
    out: dict[str, dict] = {}
    for t, r in rows:
        key = r["merchant"].strip().lower()
        g = out.setdefault(key, {"merchant": r["merchant"], "logo": r["logo"], "count": 0,
                                 "spent": 0.0, "income": 0.0, "not_counted": 0.0,
                                 "last": r["date"]})
        g["count"] += 1
        g["last"] = max(g["last"], r["date"])
        if not g["logo"]:
            g["logo"] = r["logo"]
        if r["counts"] == "spending":
            g["spent"] += spend_amount(t)
        elif r["counts"] == "income":
            g["income"] += -t.amount
        else:
            g["not_counted"] += r["amount"]
    groups = list(out.values())
    for g in groups:
        for k in ("spent", "income", "not_counted"):
            g[k] = round(g[k], 2)
    groups.sort(key=lambda g: (-g["spent"], -g["income"], -g["not_counted"], g["merchant"].lower()))
    return groups


def by_category(rows: list[tuple[Transaction, dict]]) -> list[dict]:
    """The rows folded by category, biggest first, each with its group."""
    out: dict[str, dict] = {}
    for t, r in rows:
        cat = r["category"]
        g = out.setdefault(cat, {"category": cat, "group": r["group"], "count": 0,
                                 "spent": 0.0, "income": 0.0, "not_counted": 0.0})
        g["count"] += 1
        if r["counts"] == "spending":
            g["spent"] += spend_amount(t)
        elif r["counts"] == "income":
            g["income"] += -t.amount
        else:
            g["not_counted"] += r["amount"]
    groups = list(out.values())
    for g in groups:
        for k in ("spent", "income", "not_counted"):
            g[k] = round(g[k], 2)
    groups.sort(key=lambda g: (-g["spent"], -g["income"], -g["not_counted"], g["category"]))
    return groups


def tag_totals(rows: list[tuple[Transaction, dict]]) -> list[dict]:
    """Every tag, how many rows wear it and what they came to."""
    out: dict[str, dict] = {}
    for t, r in rows:
        for tag in r.get("tags", []):
            g = out.setdefault(tag, {"tag": tag, "count": 0, "spent": 0.0, "first": r["date"],
                                     "last": r["date"]})
            g["count"] += 1
            g["first"], g["last"] = min(g["first"], r["date"]), max(g["last"], r["date"])
            if r["counts"] == "spending":
                g["spent"] += spend_amount(t)
    groups = list(out.values())
    for g in groups:
        g["spent"] = round(g["spent"], 2)
    groups.sort(key=lambda g: g["tag"].lower())
    return groups


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
          group: str | None, category: str | None, tag: str | None = None,
          merchant: str | None = None) -> dict | None:
    """With a group, category, tag or merchant chosen: its total this month
    against a usual month — the average of the three full months before,
    counting only months the ledger covers. With every month shown, the
    total is across all of them and there is no usual month."""
    if not month or not (group or category or tag or merchant):
        return None
    key = group or (group_of(category) if category else "spending")
    kind = {"income": "income", "savings": "none", "transfer": "none"}.get(key, "spending")
    from .kinds import KIND_LABELS
    label = (tag or merchant or category or CATEGORY_GROUPS.get(group)
             or KIND_LABELS.get(group) or group)

    def total(m: str, usual: bool = False) -> float:
        rows = select(all_rows, month=m, account=account, group=group, category=category,
                      tag=tag, merchant=merchant)
        if usual:
            # A one-off (THL-71) isn't part of a usual month.
            rows = [(t, r) for t, r in rows if not t.one_off]
        return _focus_value(totals(rows), kind)

    if month == "all":
        return {"label": label, "kind": kind, "total": round(total("all"), 2), "usual": None}
    first = min((r["date"][:7] for _, r in all_rows), default=month)
    prior = [m for m in _months_before(month, 3) if m >= first]
    usual = round(sum(total(m, True) for m in prior) / len(prior), 2) if prior else None
    return {"label": label, "kind": kind, "total": round(total(month), 2), "usual": usual}


def this_month() -> str:
    return date.today().isoformat()[:7]


# ── Outflows and inflows, day by day (ALT-04, 2026-10-17) ─────────────────

def _days_in(month: str) -> int:
    import calendar
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def _by_day(chosen, month: str) -> tuple[list[float], list[float]]:
    """What went out and what came in on each day of `month`, counted flows
    only: spending (her share, less what a chest paid) and income. Transfers,
    card payments, savings and anything left out are not flows."""
    days = _days_in(month)
    out, inn = [0.0] * days, [0.0] * days
    for t, r in chosen:
        if r["date"][:7] != month:
            continue
        d = int(r["date"][8:10]) - 1
        if r["counts"] == "spending":
            out[d] += spend_amount(t)
        elif r["counts"] == "income":
            inn[d] += -t.amount
    return out, inn


def _running(daily: list[float]) -> list[float]:
    total, out = 0.0, []
    for v in daily:
        total += v
        out.append(round(total, 2))
    return out


def flows(rows, filters: dict, today) -> dict | None:
    """The two cards over the list: this month's outflows and inflows as a
    running total by day, and the same for an average of the three months
    before (the dashed line), with the same filters. None for "all months"
    or "last 3 months", where there is no one month to draw."""
    import re
    month = filters.get("month")
    if not month or not re.match(r"^\d{4}-\d{2}$", month):
        return None
    base = {**filters, "day": None, "first": None, "last": None}
    days = _days_in(month)
    this_month = today.strftime("%Y-%m")
    upto = days if month < this_month else (today.day if month == this_month else 0)
    out_d, in_d = _by_day(select(rows, **{**base, "month": month}), month)
    first = min((r["date"][:7] for _, r in rows), default=None)
    before = [m for m in _months_before(month, 3) if first and m >= first]
    usual = None
    if before:
        sums_out, sums_in = [0.0] * days, [0.0] * days
        for m in before:
            o, i = _by_day(select(rows, **{**base, "month": m}), m)
            ro, ri = _running(o), _running(i)
            for d in range(days):
                k = min(d, len(ro) - 1)
                sums_out[d] += ro[k]
                sums_in[d] += ri[k]
        n = len(before)
        usual = {"out": [round(v / n, 2) for v in sums_out], "in": [round(v / n, 2) for v in sums_in],
                 "months": n}
    return {
        "month": month, "days": days, "upto": upto,
        "out": _running(out_d)[:upto], "in": _running(in_d)[:upto],
        "usual": usual,
    }

