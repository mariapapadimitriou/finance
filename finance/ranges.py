"""Sort a date range (DR-01, DR-02; 2026-10-15): every purchase between two
dates given one category, like a trip — and Sorted together, the list of the
ranges she sorted, each with its running total, to change or remove.

Only purchases move: rows that count as spending and aren't a bill. Money
in, transfers, card payments, savings and lending never change, and neither
do the bills Pearl sees recurring (a phone bill paid on holiday is still a
phone bill). Each row a range sorts keeps what it was before, so removing
the range puts every row back, and changing one re-applies it from scratch.
"""

from __future__ import annotations

from datetime import date

from .analytics import counts_as_spending, is_others, spend_amount
from .categorize import CATEGORIES, NON_SPEND, group_of
from .models import Transaction

SOURCE = "range"
NAME_MAX = 60


class Problem(Exception):
    pass


def clean(body: dict) -> dict:
    """The fields of a range, or what's wrong with them."""
    name = " ".join(str(body.get("name") or "").split())[:NAME_MAX]
    first, last = str(body.get("first") or "")[:10], str(body.get("last") or "")[:10]
    try:
        d1, d2 = date.fromisoformat(first), date.fromisoformat(last)
    except ValueError:
        raise Problem("Choose the first and last day.") from None
    if d2 < d1:
        raise Problem("The last day comes before the first.")
    if (d2 - d1).days > 366:
        raise Problem("A range is a year at most.")
    category = body.get("category")
    if category not in CATEGORIES or category in NON_SPEND or category == "Unsorted transfers":
        raise Problem("Choose a spending category.")
    if not name:
        name = f"{category} · {first}"
    return {"name": name, "first": first, "last": last, "category": category}


def _in_range(t: Transaction, first: str, last: str) -> bool:
    return first <= t.date[:10] <= last


def preview(store, txns: list[Transaction], first: str, last: str, category: str,
            today: date, skip_range: int | None = None) -> dict:
    """What sorting the range would do: the purchases that become
    `category` (count, total, what they mostly were), and what stays as it
    is (bills, deposits, transfers)."""
    from .kinds import kind_map
    kinds = kind_map(store, txns, today)
    ranged = store.ranged_rows()
    moving, bills, deposits, transfers = [], 0, 0, 0
    by_cat: dict[str, float] = {}
    for t in txns:
        if not _in_range(t, first, last) or t.excluded or is_others(t):
            continue
        if t.amount < 0:
            deposits += 1
            continue
        cat = t.category or "Other"
        if cat in NON_SPEND or cat == "Unsorted transfers" or not counts_as_spending(t):
            transfers += 1
            continue
        if kinds.get(t.fingerprint) == "fixed":
            bills += 1
            continue
        if ranged.get(t.fingerprint) not in (None, skip_range):
            continue                      # another range already has it
        moving.append(t)
        by_cat[cat] = by_cat.get(cat, 0.0) + spend_amount(t)
    total = round(sum(spend_amount(t) for t in moving), 2)
    mostly = [c for c, _ in sorted(by_cat.items(), key=lambda kv: -kv[1]) if c != category][:3]
    return {"count": len(moving), "total": total, "category": category, "mostly": mostly,
            "staying": {"bills": bills, "deposits": deposits, "transfers": transfers},
            "ids": [t.fingerprint for t in moving]}


def apply(store, rid: int, today: date) -> dict:
    """Sort the range's purchases, remembering what each was."""
    r = next((x for x in store.ranges() if x["id"] == rid), None)
    if r is None:
        raise Problem("No such range.")
    restore(store, rid)
    txns = store.all_transactions()
    p = preview(store, txns, r["first"], r["last"], r["category"], today, skip_range=rid)
    by_id = {t.fingerprint: t for t in txns}
    before = {i: (by_id[i].category or "Other", by_id[i].category_source) for i in p["ids"]}
    store.set_range_rows(rid, before)
    store.write_categories({i: (r["category"], SOURCE) for i in p["ids"]})
    return p


def restore(store, rid: int) -> int:
    """Put back every row the range sorted that nobody changed since."""
    r = next((x for x in store.ranges() if x["id"] == rid), None)
    rows = store.range_rows(rid)
    if not rows:
        return 0
    current = {t.fingerprint: t for t in store.all_transactions()}
    back = {}
    for tid, (cat, src) in rows.items():
        t = current.get(tid)
        if t is None:
            continue
        if t.category_source == SOURCE and (r is None or t.category == r["category"]):
            back[tid] = (cat or "Other", src or "rule")
    if back:
        store.write_categories(back)
    store.set_range_rows(rid, {})
    return len(back)


def listed(store, txns: list[Transaction] | None = None) -> list[dict]:
    """Sorted together: every range with its running total."""
    txns = txns if txns is not None else store.all_transactions()
    by_id = {t.fingerprint: t for t in txns}
    out = []
    for r in store.ranges():
        ids = [i for i in store.range_rows(r["id"]) if i in by_id
               and by_id[i].category_source == SOURCE and by_id[i].category == r["category"]]
        total = round(sum(spend_amount(by_id[i]) for i in ids), 2)
        out.append({**r, "count": len(ids), "total": total, "group": group_of(r["category"])})
    return out
