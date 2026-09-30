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


def summarize(trip: Trip, transactions) -> dict:
    """What a trip cost, for display beside it."""
    rows = [t for t in transactions if trip.covers(t.date) and t.amount > 0
            and t.category not in NEVER_TRAVEL]
    total = round(sum(t.amount for t in rows), 2)
    return {
        "transactions": len(rows),
        "total": total,
        "per_day": round(total / max(trip.nights + 1, 1), 2),
        "merchants": len({t.merchant for t in rows}),
    }
