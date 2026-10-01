"""Spotting a trip in the ledger instead of asking someone to remember it.

Declaring a trip is one of the most useful things you can do here: a week of
restaurants in Costa Rica read as Dining is both wrong and loud, inflating a
category and setting off a "you're eating out more" finding that is really
"you went on holiday". The Trips tab has always been able to fix that — but
only if you remember the dates and go and type them in, which nobody does.

The evidence is already in the ledger. A card charged abroad carries the
conversion on the descriptor — Scotiabank writes "AMT 9,700.00 CRC" after the
merchant — and a Plaid row carries the currency as its own field. Either way a
foreign charge is identifiable without guessing, so a run of days where most
of the spending is foreign is a trip, and the dates can be proposed rather
than remembered.

This suggests and never decides. A suggestion is shown with the charges behind
it and added only when someone says so, because the one thing worse than not
finding a trip is silently recategorising a fortnight of real spending.
"""

from __future__ import annotations

import re
from collections import Counter
from datetime import date, timedelta

# "AMT 2,800.00 CRC" / "AMT 14.84 USD" — a conversion the issuer appended.
# The code is matched as three letters at the end of that clause rather than
# against a list, so a currency nobody here has thought of still counts.
_FOREIGN_AMOUNT = re.compile(
    r"\bAMT\s+[\d,.]+\s+([A-Z]{3})\b", re.I)

# Share of a day's charges that must be foreign before the day counts as
# abroad. Not all of them: a subscription renews mid-holiday, and the airport
# coffee on the way home is charged at home.
DAY_THRESHOLD = 0.5

# A travel day with nothing bought, or a day spent entirely in cash, should
# not split one holiday into two.
MAX_GAP_DAYS = 2

# Below these a suggestion is not worth making: a single foreign charge is an
# online order from abroad, not a trip.
MIN_DAYS = 3
MIN_CHARGES = 4


def foreign_currency(t, home: str = "") -> str | None:
    """The currency a charge was made in, when it was not the home one."""
    marker = _FOREIGN_AMOUNT.search(t.description or "")
    if marker:
        code = marker.group(1).upper()
        if not home or code != home:
            return code
    # Plaid reports the currency as a field, which needs no parsing.
    code = (getattr(t, "currency", "") or "").upper()
    if home and code and code != home:
        return code
    return None


def home_currency(transactions) -> str:
    """Whatever most of the ledger is denominated in."""
    counts = Counter((getattr(t, "currency", "") or "").upper()
                     for t in transactions if getattr(t, "currency", ""))
    return counts.most_common(1)[0][0] if counts else ""


# Words that begin a two-word place name and are never the whole of one.
_PLACE_LEAD = {"san", "santa", "santo", "la", "las", "el", "los", "puerto",
               "playa", "port", "saint", "st", "new", "mount", "lake"}


def _place(description: str) -> str:
    """The town on a foreign descriptor, as the issuer wrote it.

    Issuers append a truncated province after the town — "PUNTARENAS PUN",
    "ALAJUELA ALA" — and taking the last word blindly names the trip "Pun".
    A trailing short word that merely abbreviates one before it is dropped,
    and a leading "San" or "Playa" is kept, because "Jose" is not a place.
    """
    head = _FOREIGN_AMOUNT.split(description or "")[0]
    head = re.sub(r"\(.*?\)", " ", head)
    words = re.findall(r"[A-Za-z']{2,}", head)

    while len(words) > 1 and len(words[-1]) <= 3 and any(
            w.lower().startswith(words[-1].lower()) and w.lower() != words[-1].lower()
            for w in words[:-1]):
        words.pop()

    while words and len(words[-1]) < 4:
        words.pop()
    if not words:
        return ""

    town = words[-1].title()
    if len(words) > 1 and words[-2].lower() in _PLACE_LEAD:
        town = f"{words[-2].title()} {town}"
    return town


def suggest_trips(transactions, declared=()) -> list[dict]:
    """Runs of days whose spending was mostly foreign.

    `declared` is the trips already recorded; a suggestion overlapping one of
    them is dropped, so adding a trip makes its suggestion go away rather than
    offering it again forever.
    """
    rows = [t for t in transactions if t.amount > 0 and t.date]
    if not rows:
        return []

    home = home_currency(rows)

    by_day: dict[str, list] = {}
    for t in rows:
        by_day.setdefault(t.date, []).append(t)

    abroad = {}
    for day, items in by_day.items():
        foreign = [t for t in items if foreign_currency(t, home)]
        if foreign and len(foreign) / len(items) >= DAY_THRESHOLD:
            abroad[day] = foreign

    runs = _group_runs(sorted(abroad))
    taken = [(d.get("start_date", ""), d.get("end_date", "")) for d in declared]

    out = []
    for days in runs:
        charges = [t for d in days for t in abroad[d]]
        if len(days) < MIN_DAYS or len(charges) < MIN_CHARGES:
            continue
        start, end = days[0], days[-1]
        if any(s and e and s <= end and start <= e for s, e in taken):
            continue
        places = Counter(p for p in (_place(t.description) for t in charges) if p)
        currencies = Counter(foreign_currency(t, home) for t in charges)
        out.append({
            "start_date": start,
            "end_date": end,
            "days": (date.fromisoformat(end) - date.fromisoformat(start)).days + 1,
            "charges": len(charges),
            "total": round(sum(t.amount for t in charges), 2),
            "currencies": [c for c, _ in currencies.most_common(3)],
            "places": [p for p, _ in places.most_common(3)],
            "name": _name(places, currencies),
        })

    out.sort(key=lambda s: s["start_date"], reverse=True)
    return out


def _name(places: Counter, currencies: Counter) -> str:
    """A name worth accepting unedited, from what the descriptors said."""
    if places:
        return places.most_common(1)[0][0]
    if currencies:
        return f"{currencies.most_common(1)[0][0]} trip"
    return "Trip"


def _group_runs(days: list[str]) -> list[list[str]]:
    """Consecutive days, allowing a short gap inside one run."""
    runs: list[list[str]] = []
    for day in days:
        if runs and (date.fromisoformat(day)
                     - date.fromisoformat(runs[-1][-1])) <= timedelta(days=MAX_GAP_DAYS + 1):
            runs[-1].append(day)
        else:
            runs.append([day])
    return runs
