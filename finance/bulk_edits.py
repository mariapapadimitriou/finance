"""Sort a date range (2026-10-14): one category for every purchase in it.

The simple rule that trips (THL-174) grew out of: she picks a range, a name
and a category, and every purchase in the range gets that category. Nothing
is weighed — bills, subscriptions, fees, regulars and purchases she sorted
herself all move. Only what isn't spending stays as it is: money in, money
moving between her accounts, card payments, savings and lending, and rows
that aren't hers (left out, or another joint member's).

Each edit is kept, with the rows it moved and what each was before, so the
list shows running totals and removing an edit puts every row back. Changing
an edit's range or category re-applies it. A row she re-sorts by hand
afterwards keeps her choice. A charge that posts later inside the range is
not sorted on its own; saving the edit again picks it up.

Rows an edit moved carry `category_source = 'bulk'` and a `bulk_edit_rows`
entry (finance/store.py).
"""

from __future__ import annotations

from datetime import date

from .categorize import CATEGORIES, apply_categories
from .models import Transaction

SOURCE = "bulk"
# Not spending, wherever it lands — never changed, and never a target.
NOT_SPENDING = {"Income", "Transfers", "Unsorted transfers", "Saved", "Lent"}
MAX_NAME = 60
MAX_DAYS = 92


def validate(name: str, category: str, start: str, end: str) -> str | None:
    if not (name or "").strip():
        return "Give it a name, like Costa Rica."
    if category not in CATEGORIES or category in NOT_SPENDING:
        return "Choose a spending category."
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        return "Choose the first day and the last day."
    if b < a:
        return "It ends before it starts."
    if (b - a).days > MAX_DAYS:
        return "A range can be up to three months."
    return None


def why_not(t: Transaction) -> str | None:
    """Why a row stays as it is, or None when it gets the category:
    excluded, money_in, repayment or transfer."""
    from .txlist import _is_card_payment
    if t.excluded:
        return "excluded"
    if t.amount <= 0 and not t.repays:
        return "money_in"
    if t.repays:
        return "repayment"
    if (t.category or "Other") in NOT_SPENDING or _is_card_payment(t):
        return "transfer"
    return None


def in_range(transactions: list[Transaction], start: str, end: str) -> list[Transaction]:
    return sorted((t for t in transactions if start <= t.date[:10] <= end),
                  key=lambda t: (t.date, t.fingerprint))


def sort_out(transactions: list[Transaction], start: str, end: str,
             edit_id: int | None = None, owned: dict | None = None
             ) -> tuple[list[Transaction], dict[str, int]]:
    """The rows in the range that get the category, and how many stay as
    they are, by reason ("other_edit": another edit's rows; "yours": one of
    this edit's rows she re-sorted by hand afterwards)."""
    from .txlist import visible
    owned = owned or {}
    moving, staying = [], {}
    for t in in_range(visible(transactions), start, end):
        owner = owned.get(t.fingerprint)
        if owner and t.category_source == "user":
            reason = "yours"
        elif owner == edit_id and edit_id is not None:
            moving.append(t)
            continue
        else:
            reason = "other_edit" if owner else why_not(t)
        if reason is None:
            moving.append(t)
        else:
            staying[reason] = staying.get(reason, 0) + 1
    return moving, staying


def preview(transactions: list[Transaction], start: str, end: str, category: str,
            edit_id: int | None = None, owned: dict | None = None,
            before: dict | None = None) -> dict:
    """What saving would do: how much gets the category, from which
    categories, and what stays as it is."""
    moving, staying = sort_out(transactions, start, end, edit_id, owned)
    before = before or {}
    by_cat: dict[str, list[float]] = {}
    for t in moving:
        was = (before.get(t.fingerprint) if t.category_source == SOURCE else None) \
            or t.category or "Other"
        by_cat.setdefault(was, []).append(t.amount)
    categories = sorted(({"category": c, "count": len(a), "total": round(sum(a), 2)}
                         for c, a in by_cat.items()), key=lambda c: -c["total"])
    return {"count": len(moving), "total": round(sum(t.amount for t in moving), 2),
            "category": category, "categories": categories, "staying": staying,
            "staying_count": sum(staying.values()),
            "in_dates": len(moving) + sum(staying.values())}


def _move(store, rows: list[Transaction], edit_id: int, category: str) -> None:
    """Rows new to this edit: remember what each was, then write."""
    store.add_bulk_edit_rows(edit_id, [(t.fingerprint, t.category, t.category_source)
                                       for t in rows])
    # Sorting the range is her own choice, so it may move a row she sorted;
    # what it was is remembered and comes back with the edit.
    store.write_categories({t.fingerprint: (category, SOURCE) for t in rows})


def _put_back(store, rows: list[Transaction]) -> None:
    """Back to the category each had before, unless she has since sorted it
    herself; a row with nothing remembered goes back to its merchant's."""
    before = store.remove_bulk_edit_rows([t.fingerprint for t in rows])
    back = [t for t in rows if t.category_source == SOURCE]
    unknown = [t for t in back if not (before.get(t.fingerprint) or (None,))[0]]
    apply_categories(unknown, store.overrides())
    changes = {t.fingerprint: (t.category, t.category_source) for t in unknown}
    for t in back:
        category, source = before.get(t.fingerprint) or (None, None)
        if category:
            changes[t.fingerprint] = (category, source or "rule")
    store.set_categories(changes)


def save(store, name: str, category: str, start: str, end: str,
         edit_id: int | None = None) -> int:
    """Create an edit (or change one): every purchase in the range gets the
    category; rows no longer in the range go back."""
    name = " ".join(name.split())[:MAX_NAME]
    if edit_id is None:
        edit_id = store.add_bulk_edit(name, category, start, end)
    else:
        store.update_bulk_edit(edit_id, name, category, start, end)
    transactions = store.all_transactions()
    by_id = {t.fingerprint: t for t in transactions}
    owned = store.bulk_edit_rows()
    moving, _ = sort_out(transactions, start, end, edit_id, owned)
    wanted = {t.fingerprint for t in moving}
    had = {i for i, eid in owned.items() if eid == edit_id}
    _put_back(store, [by_id[i] for i in had - wanted if i in by_id])
    _move(store, [by_id[i] for i in wanted - had], edit_id, category)
    # Rows it already had, written again: the category may have changed.
    kept = [by_id[i] for i in wanted & had if i in by_id and by_id[i].category_source == SOURCE]
    if kept:
        store.write_categories({t.fingerprint: (category, SOURCE) for t in kept})
    return edit_id


def remove(store, edit_id: int) -> int:
    by_id = {t.fingerprint: t for t in store.all_transactions()}
    rows = [by_id[i] for i, eid in store.bulk_edit_rows().items() if eid == edit_id and i in by_id]
    _put_back(store, rows)
    store.delete_bulk_edit(edit_id)
    return len(rows)


def listing(store, transactions: list[Transaction]) -> list[dict]:
    """Each edit with its running count and total, from the rows it owns."""
    rows = store.bulk_edit_rows()
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for edit in store.bulk_edits():
        mine = [by_id[i] for i, eid in rows.items() if eid == edit["id"] and i in by_id]
        out.append({**edit, "count": len(mine),
                    "total": round(sum(t.amount for t in mine), 2)})
    return out


def names(store) -> dict[str, str]:
    """{txn_id: edit name}, for the list's "Costa Rica · sorted together"."""
    by_edit = {e["id"]: e["name"] for e in store.bulk_edits()}
    return {i: by_edit[eid] for i, eid in store.bulk_edit_rows().items() if eid in by_edit}
