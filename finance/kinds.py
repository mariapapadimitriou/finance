"""Fixed or variable: a second lens on spending (2026-10-14).

Essentials and Lifestyle say what a purchase was for. Fixed and Variable say
whether it was going to happen anyway: a bill lands at the same place for
about the same amount every month whether or not she thinks about it;
groceries, petrol and dinners are decided week by week, Essentials or not.

A charge is **Fixed** when it is one of the bills Pearl already sees —
`safe_to_spend.recurring_bills` (rent, utilities, phone, insurance,
subscriptions, loan payments: anything monthly or less often at the same
place, plus Essentials every week or two such as childcare or a transit
pass), rent by e-Transfer, and the bills she confirmed in Income and bills.
Everything else that counts as spending is **Variable**.

Her own word wins: a category marked always Fixed or always Variable
(Profile › Categories and rules, `category_kinds`) decides for every charge
in it. Income, transfers and savings are neither.
"""

from __future__ import annotations

import json
from datetime import date

from .categorize import CATEGORIES, NON_SPEND
from .models import Transaction

KINDS = ("fixed", "variable")
KIND_LABELS = {"fixed": "Fixed", "variable": "Variable"}
SETTING = "category_kinds"
RENT = "Rent & Housing"


def category_kinds(store) -> dict[str, str]:
    """{category: "fixed" | "variable"} for the categories she decided."""
    try:
        data = json.loads(store.setting(SETTING) or "{}")
    except (TypeError, ValueError):
        return {}
    return {c: k for c, k in data.items() if k in KINDS and c in CATEGORIES} \
        if isinstance(data, dict) else {}


def set_category_kind(store, category: str, kind: str | None) -> dict[str, str]:
    """Mark a category always Fixed or always Variable, or None to let
    Pearl decide again. Returns what's set."""
    if category not in CATEGORIES or category in NON_SPEND or category == "Unsorted transfers":
        raise ValueError("Choose a spending category.")
    if kind not in KINDS and kind is not None:
        raise ValueError("Fixed, variable, or let Pearl decide.")
    data = category_kinds(store)
    if kind is None:
        data.pop(category, None)
    else:
        data[category] = kind
    store.set_setting(SETTING, json.dumps(data, sort_keys=True))
    return data


def fixed_charges(transactions: list[Transaction], today: date,
                  confirm: dict | None = None) -> set[tuple[str, str]]:
    """(merchant, date) of every charge that was a bill."""
    from .income_bills import bills
    from .safe_to_spend import bill_charges
    out = set(bill_charges(transactions, today))
    if confirm:
        for b in bills(transactions, today, confirm):
            if b.get("counts") is True and b.get("merchant"):
                out.update((b["merchant"], d) for d in b.get("dates") or [])
    return out


def bill_merchants(confirm: dict | None) -> set[str]:
    """Merchants she added as bills by hand (What was this? › A bill), whose
    every charge is Fixed: an added bill has no dates of its own."""
    return {" ".join(str(b.get("name") or "").lower().split())
            for b in (confirm or {}).get("added") or [] if b.get("name")}


def kind_map(store, transactions: list[Transaction], today: date) -> dict[str, str]:
    """{txn_id: kind} for every row that counts as spending."""
    from .analytics import counts_as_spending
    from .income_bills import load
    chosen = category_kinds(store)
    confirm = load(store)
    fixed = fixed_charges(transactions, today, confirm)
    added = bill_merchants(confirm)
    out = {}
    for t in transactions:
        if not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        if cat in chosen:
            out[t.fingerprint] = chosen[cat]
        elif (t.merchant, t.date) in fixed or cat == RENT \
                or " ".join((t.merchant or "").lower().split()) in added:
            out[t.fingerprint] = "fixed"
        else:
            out[t.fingerprint] = "variable"
    return out


def pearl_decides(store, transactions: list[Transaction], today: date) -> dict[str, str]:
    """{category: kind} as Pearl would call it on its own, from the charges
    of the last three months — what "Pearl decides · Fixed" shows in
    Categories and rules (CR-01). A category with no recent charge is
    Variable, the default."""
    from .analytics import counts_as_spending
    from .income_bills import load
    confirm = load(store)
    fixed = fixed_charges(transactions, today, confirm)
    added = bill_merchants(confirm)
    since = today.replace(day=1)
    for _ in range(2):
        since = (since.replace(day=1) - __import__("datetime").timedelta(days=1)).replace(day=1)
    votes: dict[str, list[int]] = {}
    for t in transactions:
        if t.date[:10] < since.isoformat() or not counts_as_spending(t):
            continue
        cat = t.category or "Other"
        is_fixed = ((t.merchant, t.date) in fixed or cat == RENT
                    or " ".join((t.merchant or "").lower().split()) in added)
        votes.setdefault(cat, [0, 0])[0 if is_fixed else 1] += 1
    out = {}
    for cat in CATEGORIES:
        if cat in NON_SPEND or cat == "Unsorted transfers":
            continue
        f, v = votes.get(cat, [0, 0])
        out[cat] = "fixed" if f > v or cat == RENT else "variable"
    return out


def kind_of(t: Transaction, kinds: dict[str, str] | None) -> str | None:
    """A row's kind, or None when it isn't spending (or no map was built)."""
    return (kinds or {}).get(t.fingerprint)
