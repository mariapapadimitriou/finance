"""Two accounts that are one: merging them by hand.

The automatic check (`plaid_link.doubled_items`) knows two copies of a card
only by the last four digits and the kind of account, from the bank. When
that isn't enough — a statement imported before the bank was linked, a
connection since disconnected, a bank that sends no digits — she says it
herself: "Same account as…" on the account's page.

Each row of the copy she merges away finds its twin in the account she
keeps: the same row under the kept account's id, else the same amount
within a few days that no other row has claimed. A twin keeps its place and
takes her answers (categories, splits, notes…) unless it has its own. A row
with no twin moves across, so no history is lost. Then the copy goes: it
stops syncing, leaves the Accounts list, and a bank connection with nothing
else listed is disconnected.
"""

from __future__ import annotations

from collections import defaultdict
from dataclasses import replace
from datetime import date

# How far apart two records of one purchase can be: a statement's date and a
# bank feed's differ by the days it took to post.
TWIN_DAYS = 3


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def merge(store, from_id: str, into_id: str) -> dict:
    """Merge account `from_id` into `into_id`. Returns what happened."""
    rows = store.all_transactions()
    copy = sorted((t for t in rows if t.account_id == from_id), key=lambda t: (t.date, t.seq))
    kept = [t for t in rows if t.account_id == into_id]
    by_id = {t.fingerprint: t for t in kept}
    pool: dict[str, list] = defaultdict(list)
    for t in kept:
        pool[f"{t.amount:.2f}"].append(t)
    name = kept[0].account_name if kept else None

    claimed: set[str] = set()
    mapping: dict[str, str] = {}
    categories: dict[str, str] = {}
    moved = []
    for t in copy:
        same = replace(t, account_id=into_id).fingerprint
        twin = by_id.get(same) if same not in claimed else None
        if twin is None:
            near = [k for k in pool[f"{t.amount:.2f}"]
                    if k.fingerprint not in claimed and _days(k.date, t.date) <= TWIN_DAYS]
            twin = min(near, key=lambda k: _days(k.date, t.date)) if near else None
        if twin is not None:
            claimed.add(twin.fingerprint)
            mapping[t.fingerprint] = twin.fingerprint
            if t.category_source == "user" and twin.category_source != "user":
                categories[twin.fingerprint] = t.category
            continue
        again = replace(t, account_id=into_id, account_name=name or t.account_name)
        moved.append(again)
        mapping[t.fingerprint] = again.fingerprint

    store.add_transactions(moved)
    store.rekey_rows(mapping)
    store.forget_rows({t.fingerprint for t in copy})
    for txn_id, category in categories.items():
        store.set_transaction_category(txn_id, category)
    return {"matched": len(copy) - len(moved), "moved": len(moved)}
