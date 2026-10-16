"""Sort a date range (DR-01, DR-02; 2026-10-15), now Select days on the
calendar (CAL-06 to CAL-09, 2026-10-16): every purchase between two dates
given one category, like a trip — and, if she wants, paid from a treasure
chest, so the purchases leave the month and come out of the chest instead.
Days sorted together lists the ranges she sorted, each with its running
total, under the calendar, to change or remove.

Only purchases move: rows that count as spending and aren't a bill. Money
in, transfers, card payments, savings and lending never change, and neither
do the bills Pearl sees recurring (a phone bill paid on holiday is still a
phone bill). Each row a range sorts keeps what it was before, so removing
the range puts every row back, and changing one re-applies it from scratch.
"""

from __future__ import annotations

from datetime import date

from .analytics import is_others, is_spend_category, share_amount
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
    bank_id = body.get("bank_id")
    if bank_id in ("", None):
        bank_id = None
    elif isinstance(bank_id, bool) or not isinstance(bank_id, (int, str)) \
            or not str(bank_id).isdigit():
        raise Problem("Choose a treasure chest, or none.")
    else:
        bank_id = int(bank_id)
    return {"name": name, "first": first, "last": last, "category": category, "bank_id": bank_id}


def mostly_words(mostly: list[str]) -> str:
    """"Mostly Lodging, Dining out and Transport." or nothing."""
    if not mostly:
        return ""
    names = mostly if len(mostly) == 1 else ", ".join(mostly[:-1]) + " and " + mostly[-1]
    return f"Mostly {names}."


def staying_words(s: dict) -> str:
    """What a range leaves alone, and why."""
    stays = []
    if s["bills"]:
        stays.append(f"{s['bills']} bill{'s' if s['bills'] != 1 else ''} and subscriptions"
                     if s["bills"] != 1 else "1 bill")
    if s["deposits"]:
        stays.append(f"{s['deposits']} deposit{'s' if s['deposits'] != 1 else ''}")
    if s["transfers"]:
        stays.append(f"{s['transfers']} transfer{'s' if s['transfers'] != 1 else ''}")
    out = (f"Staying as they are: {', '.join(stays)}. " if stays else "")
    return out + "Money in, transfers, card payments, savings and lending never change."


def _in_range(t: Transaction, first: str, last: str) -> bool:
    return first <= t.date[:10] <= last


def is_purchase(t: Transaction) -> bool:
    """A purchase for a range's purposes: spending of hers, whether or not a
    treasure chest paid for it (a trip a chest paid for is still the trip)."""
    cat = t.category or "Other"
    return (t.amount > 0 and not t.excluded and is_spend_category(cat)
            and cat not in NON_SPEND and cat != "Unsorted transfers")


def preview(store, txns: list[Transaction], first: str, last: str, category: str | None,
            today: date, skip_range: int | None = None) -> dict:
    """What sorting the range would do: the purchases that become
    `category` (count, total, what they mostly were), and what stays as it
    is (bills, deposits, transfers). With no category it is just the days'
    summary (CAL-06): what was spent, by category, and what isn't counted."""
    from .kinds import kind_map
    kinds = kind_map(store, txns, today)
    ranged = store.ranged_rows()
    moving, bills, deposits, transfers = [], 0, 0, 0
    by_cat: dict[str, float] = {}
    by_cat_n: dict[str, int] = {}
    staying_rows: list[dict] = []
    for t in txns:
        if not _in_range(t, first, last) or t.excluded or is_others(t):
            continue
        name = t.merchant or t.description
        if t.amount < 0:
            deposits += 1
            staying_rows.append({"id": t.fingerprint, "merchant": name, "why": "Money in",
                                 "amount": round(-t.amount, 2), "inflow": True})
            continue
        cat = t.category or "Other"
        if not is_purchase(t):
            transfers += 1
            staying_rows.append({"id": t.fingerprint, "merchant": name,
                                 "why": "Not sorted yet" if cat == "Unsorted transfers" else cat,
                                 "amount": round(t.amount, 2), "inflow": False})
            continue
        if kinds.get(t.fingerprint) == "fixed":
            bills += 1
            staying_rows.append({"id": t.fingerprint, "merchant": name, "why": "Bill",
                                 "amount": round(share_amount(t), 2), "inflow": False})
            continue
        if ranged.get(t.fingerprint) not in (None, skip_range):
            continue                      # another range already has it
        moving.append(t)
        by_cat[cat] = by_cat.get(cat, 0.0) + share_amount(t)
        by_cat_n[cat] = by_cat_n.get(cat, 0) + 1
    total = round(sum(share_amount(t) for t in moving), 2)
    ranked = sorted(by_cat.items(), key=lambda kv: -kv[1])
    mostly = [c for c, _ in ranked if c != category][:3]
    return {"count": len(moving), "total": total, "category": category, "mostly": mostly,
            "staying": {"bills": bills, "deposits": deposits, "transfers": transfers},
            "by_category": [{"category": c, "count": by_cat_n[c], "total": round(v, 2)}
                            for c, v in ranked],
            "staying_rows": staying_rows,
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
    # Paid from a treasure chest (CAL-08): the chest pays each purchase, so
    # they leave the month. Removing or changing the range puts them back.
    if r.get("bank_id") and store.piggy_bank(r["bank_id"]) is not None:
        for i in p["ids"]:
            store.allocate(i, r["bank_id"], by_id[i].amount)
    return p


def restore(store, rid: int) -> int:
    """Put back every row the range sorted that nobody changed since."""
    r = next((x for x in store.ranges() if x["id"] == rid), None)
    rows = store.range_rows(rid)
    if not rows:
        return 0
    current = {t.fingerprint: t for t in store.all_transactions()}
    back = {}
    bank_id = (r or {}).get("bank_id")
    for tid, (cat, src) in rows.items():
        t = current.get(tid)
        if t is None:
            continue
        if t.category_source == SOURCE and (r is None or t.category == r["category"]):
            back[tid] = (cat or "Other", src or "rule")
        if bank_id and t.bank_id == bank_id and not t.bank_auto:
            store.unallocate(tid)          # the chest stops paying for it
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
        total = round(sum(share_amount(by_id[i]) for i in ids), 2)
        bank = store.piggy_bank(r["bank_id"]) if r.get("bank_id") else None
        out.append({**r, "count": len(ids), "total": total, "group": group_of(r["category"]),
                    "bank": bank.name if bank else None,
                    "days": (date.fromisoformat(r["last"]) - date.fromisoformat(r["first"])).days + 1})
    return out
