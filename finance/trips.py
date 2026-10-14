"""Trips (THL-174, 2026-10-13): a date range whose spending she sorts as
Travel in one go.

A week away produces restaurant, coffee, transit and shop charges that look
exactly like the same charges at home. Sorted one by one they scatter over
eight categories and quietly inflate her usual Dining and Coffee; and
there are dozens to sort. So she marks the trip — a name and its dates —
and everything she was spending on while away becomes Travel, on its own:
no list to tick (2026-10-14). The panel says what moves and what stays.

Simple (2026-10-14): every purchase in the dates becomes Travel — bills,
subscriptions, fees, places she goes often, purchases she sorted herself.
Only what isn't spending stays as it is: money in, money moving between
her accounts, card payments, savings and lending, and rows that aren't hers
(left out, or another joint member's). Removing the trip puts each row back
to the category it had; a trip row she re-sorts by hand afterwards keeps
her choice.

New rows that arrive inside a trip's dates later (a pending charge posting)
join it by the same rule. Changing a trip's dates re-applies the rule;
removing a trip puts its rows back. Rows a trip moved carry
`category_source = 'trip'` and a `trip_rows` entry that remembers the
category each had before, which is what it goes back to.
"""

from __future__ import annotations

from datetime import date

from .categorize import apply_categories

from .models import Transaction

TRAVEL = "Travel"
SOURCE = "trip"
# Not spending on a trip, wherever it lands.
NOT_TRIP = {"Income", "Transfers", "Unsorted transfers", "Saved", "Lent"}
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






def why_not(t: Transaction) -> str | None:
    """Why a row stays as it is, or None when it becomes Travel: excluded,
    money_in, repayment or transfer. Every purchase becomes Travel."""
    from .txlist import _is_card_payment
    if t.excluded:
        return "excluded"
    if t.amount <= 0 and not t.repays:
        return "money_in"
    if t.repays:
        return "repayment"
    if (t.category or "Other") in NOT_TRIP or _is_card_payment(t):
        return "transfer"
    return None


def in_range(transactions: list[Transaction], start: str, end: str) -> list[Transaction]:
    return sorted((t for t in transactions if start <= t.date[:10] <= end),
                  key=lambda t: (t.date, t.fingerprint))


def sort_out(transactions: list[Transaction], start: str, end: str, today: date,
             trip_id: int | None = None, trip_rows: dict | None = None
             ) -> tuple[list[Transaction], dict[str, int]]:
    """The rows in the dates that become Travel, and how many stay as they
    are, by reason (another trip's rows: "other_trip")."""
    from .txlist import visible
    trip_rows = trip_rows or {}
    moving, staying = [], {}
    for t in in_range(visible(transactions), start, end):
        owner = trip_rows.get(t.fingerprint)
        if owner and t.category_source == "user":
            reason = "yours"                    # re-sorted by hand after the trip
        elif owner == trip_id and trip_id is not None:
            moving.append(t)
            continue
        else:
            reason = "other_trip" if owner else why_not(t)
        if reason is None:
            moving.append(t)
        else:
            staying[reason] = staying.get(reason, 0) + 1
    return moving, staying


def preview(transactions: list[Transaction], start: str, end: str, today: date,
            trip_id: int | None = None, trip_rows: dict | None = None,
            before: dict | None = None) -> dict:
    """What saving would do: how much moves to Travel, from which
    categories, and what stays as it is."""
    moving, staying = sort_out(transactions, start, end, today, trip_id, trip_rows)
    before = before or {}
    by_cat: dict[str, list[float]] = {}
    for t in moving:
        cat = (before.get(t.fingerprint) if t.category == TRAVEL else None) or t.category or "Other"
        by_cat.setdefault(cat, []).append(t.amount)
    categories = sorted(({"category": c, "count": len(a), "total": round(sum(a), 2)}
                         for c, a in by_cat.items()), key=lambda c: -c["total"])
    return {"count": len(moving), "total": round(sum(t.amount for t in moving), 2),
            "categories": categories, "staying": staying,
            "staying_count": sum(staying.values()),
            "in_dates": len(moving) + sum(staying.values())}


def _move(store, rows: list[Transaction], trip_id: int) -> None:
    store.add_trip_rows(trip_id, [(t.fingerprint, t.category, t.category_source) for t in rows])
    # Marking the trip is her own choice, so it may move a row she sorted;
    # what it was is remembered and comes back with the trip.
    store.write_categories({t.fingerprint: (TRAVEL, SOURCE) for t in rows})


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


def save(store, name: str, start: str, end: str, today: date,
         trip_id: int | None = None) -> int:
    """Create a trip (or change one): its spending becomes Travel, and rows
    no longer in its dates go back."""
    name = " ".join(name.split())[:MAX_NAME]
    if trip_id is None:
        trip_id = store.add_marked_trip(name, start, end)
    else:
        store.update_marked_trip(trip_id, name, start, end)
    transactions = store.all_transactions()
    by_id = {t.fingerprint: t for t in transactions}
    owned = store.trip_rows()
    moving, _ = sort_out(transactions, start, end, today, trip_id, owned)
    wanted = {t.fingerprint for t in moving}
    had = {i for i, tid in owned.items() if tid == trip_id}
    _put_back(store, [by_id[i] for i in had - wanted if i in by_id])
    _move(store, [by_id[i] for i in wanted - had], trip_id)
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
    from .txlist import visible
    moved = 0
    for trip in trips:
        rows = [t for t in visible(new) if trip["start_date"] <= t.date[:10] <= trip["end_date"]
                and why_not(t) is None]
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
