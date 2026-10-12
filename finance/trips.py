"""Trips: date ranges that reclassify whatever falls inside them as Travel.

A week in New York produces restaurant, coffee, transit and shop charges that
are individually indistinguishable from the same charges at home. Categorized
by merchant they scatter across eight categories and quietly inflate every
one of them — the Dining baseline goes up, the "you're eating out more" finding
fires, and the real story (you took a trip) is nowhere.

Geography can't settle it either: a card descriptor's city is where the
merchant is registered, not where you were. Three charges in this ledger are
billed from Montreal and Quebec City months apart — a clothing chain's head
office, not travel.

So trips are declared, not inferred. You give the dates; everything inside
them becomes Travel.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from .analytics import share_amount

# Money moving onto the card is never travel spending, and neither is a fee
# that happens to land mid-trip.
NEVER_TRAVEL = {"Income", "Transfers", "Fees & Interest"}


@dataclass
class Trip:
    id: int | None
    name: str
    start_date: str
    end_date: str

    def covers(self, iso_date: str) -> bool:
        return self.start_date <= iso_date <= self.end_date

    @property
    def nights(self) -> int:
        return (date.fromisoformat(self.end_date)
                - date.fromisoformat(self.start_date)).days

    def to_dict(self, stats: dict | None = None) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "start_date": self.start_date,
            "end_date": self.end_date,
            "nights": self.nights,
        }
        if stats:
            d.update(stats)
        return d


def validate(name: str, start: str, end: str) -> str | None:
    """Return an error message, or None when the trip is usable."""
    if not (name or "").strip():
        return "Give the trip a name."
    try:
        s, e = date.fromisoformat(start), date.fromisoformat(end)
    except (ValueError, TypeError):
        return "Dates must be YYYY-MM-DD."
    if e < s:
        return "The trip ends before it starts."
    if (e - s).days > 365:
        return "That's longer than a year — split it into separate trips."
    return None


def covering_trip(trips: list[Trip], iso_date: str) -> Trip | None:
    """The first trip covering a date. Overlaps resolve to the earlier trip."""
    for t in sorted(trips, key=lambda x: (x.start_date, x.id or 0)):
        if t.covers(iso_date):
            return t
    return None


def apply_trips(transactions, trips: list[Trip]) -> int:
    """Move spending inside a trip's dates to Travel. Returns rows changed.

    Runs after normal categorization, so it overrides the merchant rules — the
    whole point is that a trip's restaurant is travel, not dining. It does not
    override a category you set by hand: an explicit choice stays yours.
    """
    if not trips:
        return 0

    changed = 0
    for t in transactions:
        if t.category_source == "user":
            continue
        if t.category in NEVER_TRAVEL:
            continue
        trip = covering_trip(trips, t.date)
        if trip is None:
            continue
        if t.category != "Travel" or t.category_source != "trip":
            t.category = "Travel"
            t.category_source = "trip"
            changed += 1
    return changed


def _why_not(t, trip: Trip, trips: list[Trip]) -> str | None:
    """Why a row inside a trip's dates isn't counted toward it, or None."""
    from .analytics import is_others
    if t.excluded:
        return f"Left out · {t.excluded}"
    if is_others(t):
        return f"{t.joint}’s, on a joint account"
    owner = covering_trip(trips, t.date[:10]) if trips else trip
    if owner is not None and owner.id != trip.id and t.category == "Travel":
        return f"Counted in {owner.name}, which covers the same day"
    if t.category == "Travel":
        return None
    if t.category == "Income":
        return "Money in, not spending"
    if t.category in ("Transfers", "Saved", "Lent"):
        return "Money moving between accounts, not spending"
    if t.category == "Fees & Interest":
        return "Fees and interest aren’t counted as travel"
    if t.category_source == "user":
        return f"You filed it as {t.category}"
    return f"Filed as {t.category}"


def breakdown(trip: Trip, transactions, trips: list[Trip] | None = None) -> dict:
    """Every transaction in a trip's dates: what counts toward it, and what
    doesn't and why (THL-182). A row filed by hand, a fee or a transfer stays
    out; it is listed so it can be moved in rather than silently missing."""
    counted, not_counted = [], []
    for t in sorted(transactions, key=lambda x: (x.date, x.fingerprint)):
        if not trip.covers(t.date[:10]):
            continue
        from .transfers import display_name
        row = {"id": t.fingerprint, "date": t.date[:10], "merchant": display_name(t),
               "amount": round(t.amount, 2), "share": round(share_amount(t), 2),
               "category": t.category, "bank_id": t.bank_id,
               "bank_amount": round(t.bank_amount or 0.0, 2)}
        why = _why_not(t, trip, trips or [trip])
        if why is None:
            counted.append(row)
        else:
            not_counted.append({**row, "reason": why})
    return {"counted": counted, "not_counted": not_counted}


def summarize(trip: Trip, transactions, trips: list[Trip] | None = None) -> dict:
    """What a trip cost, for display beside it: what counts toward it, which
    is its Travel spending in its dates."""
    ids = {r["id"] for r in breakdown(trip, transactions, trips)["counted"]}
    rows = [t for t in transactions if t.fingerprint in ids]
    total = round(sum(share_amount(t) for t in rows), 2)
    return {
        "transactions": len(rows),
        "total": total,
        "per_day": round(total / max(trip.nights + 1, 1), 2),
        "merchants": len({t.merchant for t in rows}),
    }
