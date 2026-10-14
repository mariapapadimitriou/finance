"""Trips (THL-174, 2026-10-13): a date range whose spending she sorts as
Travel in one go.

A week away produces restaurant, coffee, transit and shop charges that look
exactly like the same charges at home. Sorted one by one they scatter over
eight categories and quietly inflate her usual Dining and Coffee; and
there are dozens to sort. So she marks the trip — a name and its dates —
and everything she was spending on while away becomes Travel, after a
preview where she can untick anything that wasn't.

What starts unticked: anything that isn't spending on the trip — income,
money moving between her accounts, card payments, savings, lending, fees
and interest, repayments — anything that recurs (rent, bills,
subscriptions), rows she left out, and rows she already sorted herself
(her category is never overwritten).

New rows that arrive inside a trip's dates later (a pending charge posting)
join it by the same rule. Removing a trip, or unticking a row, puts it back
to what its merchant says it is. Rows a trip moved carry
`category_source = 'trip'` and a `trip_rows` entry that remembers the
category each had before, which is what it goes back to.
"""

from __future__ import annotations

from datetime import date

from .categorize import apply_categories
from .insights.recurring import detect_recurring
from .models import Transaction

TRAVEL = "Travel"
SOURCE = "trip"
# Not spending on a trip, wherever it lands.
NOT_TRIP = {"Income", "Transfers", "Unsorted transfers", "Saved", "Lent", "Fees & Interest",
            TRAVEL}
MAX_NAME = 60


def validate(name: str, start: str, end: str) -> str | None:
    if not (name or "").strip():
        return "Give the trip a name, like Costa Rica."
    try:
        a, b = date.fromisoformat(start), date.fromisoformat(end)
    except (TypeError, ValueError):
        return "Choose the day it started and the day it ended."
    if b < a:
        return "The trip ends before it starts."
    if (b - a).days > 92:
        return "A trip can be up to three months."
    return None


def _recurring(transactions: list[Transaction], today: date) -> set[tuple[str, str]]:
    out = set()
    for rec in detect_recurring(transactions, as_of=today.isoformat()):
        out.update((rec["merchant"], d) for d in rec["dates"])
    return out


def why_not(t: Transaction, recurring: set) -> str | None:
    """Why a row starts unticked, or None when it's trip spending."""
    from .txlist import _is_card_payment
    if t.excluded:
        return "You left it out"
    if t.category_source == "user":
        return "You sorted it yourself"
    if t.amount <= 0 and not t.repays:
        return "Money in"
    if t.repays:
        return "A repayment"
    if (t.category or "Other") in NOT_TRIP or _is_card_payment(t):
        return "Not spending"
    if (t.merchant, t.date) in recurring:
        return "A regular bill or subscription"
    return None


def in_range(transactions: list[Transaction], start: str, end: str) -> list[Transaction]:
    return sorted((t for t in transactions if start <= t.date[:10] <= end),
                  key=lambda t: (t.date, t.fingerprint))


def preview(transactions: list[Transaction], start: str, end: str, today: date,
            trip_id: int | None = None, trip_rows: dict | None = None) -> dict:
    """Every row in the dates, with whether it starts ticked and why not."""
    recurring = _recurring(transactions, today)
    trip_rows = trip_rows or {}
    rows = []
    for t in in_range(transactions, start, end):
        mine = trip_id is not None and trip_rows.get(t.fingerprint) == trip_id
        reason = None if mine else why_not(t, recurring)
        if not mine and trip_rows.get(t.fingerprint):
            reason = "In another trip"
        rows.append({"id": t.fingerprint, "date": t.date[:10], "merchant": t.merchant,
                     "amount": round(t.amount, 2), "category": t.category,
                     "ticked": reason is None, "why_not": reason})
    total = round(sum(r["amount"] for r in rows if r["ticked"]), 2)
    return {"rows": rows, "total": total, "ticked": sum(r["ticked"] for r in rows)}


def _move(store, rows: list[Transaction], trip_id: int) -> None:
    store.add_trip_rows(trip_id, [(t.fingerprint, t.category, t.category_source) for t in rows])
    store.set_categories({t.fingerprint: (TRAVEL, SOURCE) for t in rows})


def _put_back(store, rows: list[Transaction]) -> None:
    """Back to the category each had before the trip, unless she has since
    sorted it herself; a row with nothing remembered goes back to what its
    merchant says it is."""
    before = store.remove_trip_rows([t.fingerprint for t in rows])
    back = [t for t in rows if t.category_source == SOURCE]
    unknown = [t for t in back if not (before.get(t.fingerprint) or (None,))[0]]
    apply_categories(unknown, store.overrides())
    changes = {t.fingerprint: (t.category, t.category_source) for t in unknown}
    for t in back:
        category, source = before.get(t.fingerprint) or (None, None)
        if category:
            changes[t.fingerprint] = (category, source or "rule")
    store.set_categories(changes)


def save(store, name: str, start: str, end: str, ids: list[str],
         trip_id: int | None = None) -> int:
    """Create a trip (or change one) and move exactly the rows she ticked."""
    name = " ".join(name.split())[:MAX_NAME]
    if trip_id is None:
        trip_id = store.add_marked_trip(name, start, end)
    else:
        store.update_marked_trip(trip_id, name, start, end)
    by_id = {t.fingerprint: t for t in store.all_transactions()}
    owned = store.trip_rows()
    wanted = {i for i in ids if i in by_id and owned.get(i, trip_id) == trip_id}
    had = {i for i, tid in owned.items() if tid == trip_id}
    _put_back(store, [by_id[i] for i in had - wanted if i in by_id])
    _move(store, [by_id[i] for i in wanted - had
                  if by_id[i].category_source != "user"], trip_id)
    return trip_id


def remove(store, trip_id: int) -> int:
    by_id = {t.fingerprint: t for t in store.all_transactions()}
    rows = [by_id[i] for i, tid in store.trip_rows().items() if tid == trip_id and i in by_id]
    _put_back(store, rows)
    store.delete_marked_trip(trip_id)
    return len(rows)


def join_new(store, new: list[Transaction], today: date) -> int:
    """Rows that just arrived inside a trip's dates join it by the same rule."""
    trips = store.marked_trips()
    if not trips or not new:
        return 0
    recurring = _recurring(store.all_transactions(), today)
    moved = 0
    for trip in trips:
        rows = [t for t in new if trip["start_date"] <= t.date[:10] <= trip["end_date"]
                and why_not(t, recurring) is None]
        if rows:
            _move(store, rows, trip["id"])
            moved += len(rows)
    return moved


def listing(store, transactions: list[Transaction]) -> list[dict]:
    rows = store.trip_rows()
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for trip in store.marked_trips():
        mine = [by_id[i] for i, tid in rows.items() if tid == trip["id"] and i in by_id]
        out.append({**trip, "count": len(mine),
                    "total": round(sum(t.amount for t in mine), 2)})
    return out


def names(store) -> dict[str, str]:
    """{txn_id: trip name}, for the list's "Travel · Costa Rica trip"."""
    by_trip = {t["id"]: t["name"] for t in store.marked_trips()}
    return {i: by_trip[tid] for i, tid in store.trip_rows().items() if tid in by_trip}
