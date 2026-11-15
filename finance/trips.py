"""Trips (product owner, 2026-11-15; Figma Proposals › Trips 1327:4973,
note 1329:69536 · THL-122, THL-123, THL-226, THL-263).

A trip is its own thing: a name, its transactions, their dates, a total and
a page. It adds a tag with the same name, and the two stay in step: renaming
the trip renames the tag, and taking the tag off (Tags, TR-09) ends the trip.
A trip never moves money between months: each row still counts in its own.

AI only detects; she confirms. Pearl asks about a likely trip with one Quick
sort card (TR-01), and only when two signals agree (product owner):

* a run of first-time merchants: at least RUN_MIN rows on two or more days,
  no more than RUN_GAP days apart, at merchants she has never paid before;
* and at least one of: a flight (Travel) or a hotel (Lodging) in the two
  weeks before or during it, foreign transaction fees during it, or a city
  (where Plaid gives one) that isn't the one she's usually in.

Nothing groups until she says Yes. Skip and Pearl never asks about those
dates again (`SKIPPED_KEY`). She can make a trip herself from Select (TR-07,
TR-08). There is no currency conversion anywhere in Pearl: each amount is as
its card was billed, so a trip across currencies is totalled per currency.
"""

from __future__ import annotations

import json
import re
import uuid
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .categorize import NON_SPEND, merchant_key
from .models import Transaction

TRIPS_KEY = "trips"                 # {id: trip}
SKIPPED_KEY = "trip_skipped"        # [[start, end]] she skipped: never asked again
ENDED_KEY = "trip_ended"            # {id: {trip, skipped}}: what Undo on TR-13 puts back
ENDED_KEEP = 20                     # the last few ended trips, for Undo
RUN_MIN = 4                         # first-time merchant rows in a run
RUN_GAP = 2                         # days between them, at most
RUN_SPAN = 21                       # a run this long isn't a trip
BEFORE = 14                         # a flight or hotel booked up to two weeks before
SETTLE = 30                         # days of history before anything counts as "new"
LOOKBACK = 120                      # only trips that ended in the last four months
FEE = re.compile(r"\b(foreign transaction fee|forex fee|fx fee|foreign fee|non-sterling|conversion fee)\b", re.I)


class Problem(ValueError):
    """Something she can fix: shown as it is."""


def _json(st, key: str, default):
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _save(st, key: str, value) -> None:
    st.set_setting(key, json.dumps(value, sort_keys=True))


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# ── Trips ──────────────────────────────────────────────────────────────────

def all_trips(st) -> dict[str, dict]:
    out = _json(st, TRIPS_KEY, {})
    return out if isinstance(out, dict) else {}


def trip_of(st) -> dict[str, dict]:
    """txn id → the trip it's in."""
    return {i: t for t in all_trips(st).values() for i in t["ids"]}


def _clean_name(st, name, keep: str | None = None) -> str:
    from . import marks
    try:
        cleaned = marks.clean_tags([str(name or "")])
    except marks.Problem as exc:
        raise Problem(str(exc)) from exc
    if not cleaned:
        raise Problem("Name the trip.")
    name = cleaned[0]
    if any(t["name"].lower() == name.lower() and t["id"] != keep for t in all_trips(st).values()):
        raise Problem("You already have a trip with that name.")
    return name


def _spans(st, ids: list[str]) -> tuple[str, str]:
    days = sorted(t.date[:10] for t in (st.get_transaction(i) for i in ids) if t is not None)
    return days[0], days[-1]


def create(st, ids: list[str], name: str, by: str, today: str, place: str | None = None) -> dict:
    """Make a trip of these rows (Pearl's ask said Yes, or Select › Make a trip)."""
    ids = list(dict.fromkeys(i for i in ids if st.get_transaction(i) is not None))
    if not ids:
        raise Problem("Pick the transactions first.")
    taken = trip_of(st)
    if any(i in taken for i in ids):
        raise Problem("Some of these are already in a trip.")
    name = _clean_name(st, name)
    start, end = _spans(st, ids)
    trip = {"id": uuid.uuid4().hex[:12], "name": name, "ids": ids, "start": start, "end": end,
            "place": place, "by": by, "at": _now(), "day": today}
    trips = all_trips(st)
    trips[trip["id"]] = trip
    _save(st, TRIPS_KEY, trips)
    st.tag_rows(ids, [name], [])
    return trip


def rename(st, trip_id: str, name: str) -> dict:
    """Renames its tag too (TR-04)."""
    trips = all_trips(st)
    trip = trips.get(trip_id)
    if trip is None:
        raise KeyError(trip_id)
    new = _clean_name(st, name, keep=trip_id)
    if new != trip["name"]:
        st.tag_rows(trip["ids"], [new], [trip["name"]])
        trip["name"] = new
        _save(st, TRIPS_KEY, trips)
    return trip


def change(st, trip_id: str, add: list[str] | None = None, remove: list[str] | None = None) -> dict:
    """Add transactions / Remove some… (TR-04). A trip left empty ends."""
    trips = all_trips(st)
    trip = trips.get(trip_id)
    if trip is None:
        raise KeyError(trip_id)
    taken = trip_of(st)
    add = [i for i in (add or []) if st.get_transaction(i) is not None and i not in trip["ids"]]
    if any(i in taken for i in add):
        raise Problem("Some of these are already in a trip.")
    remove = [i for i in (remove or []) if i in trip["ids"]]
    trip["ids"] = [i for i in trip["ids"] if i not in remove] + add
    if not trip["ids"]:
        end(st, trip_id)
        return {**trip, "ended": True}
    st.tag_rows(add, [trip["name"]], [])
    st.tag_rows(remove, [], [trip["name"]])
    trip["start"], trip["end"] = _spans(st, trip["ids"])
    _save(st, TRIPS_KEY, trips)
    return trip


def end(st, trip_id: str, skip: bool = True) -> dict | None:
    """It wasn't a trip, or its tag was removed: the trip and its tag go; the
    transactions stay as they are, in their own months. Pearl won't ask about
    those dates again. Kept for Undo (TR-13), which puts it back exactly.

    `skip=False` is Undo after Make a trip (TR-02c): she only just made it, so
    its dates aren't marked as asked about, and there's nothing to put back."""
    trips = all_trips(st)
    trip = trips.pop(trip_id, None)
    if trip is None:
        return None
    st.tag_rows(trip["ids"], [], [trip["name"]])
    _save(st, TRIPS_KEY, trips)
    if skip:
        added = _skip_dates(st, trip["start"], trip["end"])
        ended = _json(st, ENDED_KEY, {})
        ended = ended if isinstance(ended, dict) else {}
        ended[trip_id] = {"trip": trip, "skipped": added, "at": _now()}
        keep = sorted(ended, key=lambda k: ended[k].get("at") or "")[-ENDED_KEEP:]
        _save(st, ENDED_KEY, {k: ended[k] for k in keep})
    return trip


def restore(st, trip_id: str) -> dict | None:
    """Undo on "Not a trip" (TR-13): the same trip back (its id, name, rows,
    place, who made it and when) with its tag, and its dates no longer marked
    as skipped unless they were before it ended. None if there's nothing to
    put back."""
    ended = _json(st, ENDED_KEY, {})
    ended = ended if isinstance(ended, dict) else {}
    entry = ended.get(trip_id)
    if not isinstance(entry, dict) or trip_id in all_trips(st):
        return None
    trip = dict(entry["trip"])
    taken = trip_of(st)
    if any(i in taken for i in trip["ids"]):
        raise Problem("Some of these are already in a trip.")
    trip["ids"] = [i for i in trip["ids"] if st.get_transaction(i) is not None]
    if not trip["ids"]:
        raise Problem("Those transactions aren’t there any more.")
    trip["name"] = _clean_name(st, trip["name"])
    if entry.get("skipped"):
        _unskip_dates(st, trip["start"], trip["end"])
    trip["start"], trip["end"] = _spans(st, trip["ids"])
    trips = all_trips(st)
    trips[trip_id] = trip
    _save(st, TRIPS_KEY, trips)
    st.tag_rows(trip["ids"], [trip["name"]], [])
    ended.pop(trip_id, None)
    _save(st, ENDED_KEY, ended)
    return trip


def by_tag(st, tag: str) -> dict | None:
    return next((t for t in all_trips(st).values() if t["name"] == tag), None)


# ── What a trip adds up to ─────────────────────────────────────────────────

def _month_name(month: str) -> str:
    return date.fromisoformat(month + "-01").strftime("%B")


def summary(st, trip: dict, txns: list[Transaction] | None = None) -> dict:
    """Totals per billing currency (no conversion, ever), the months its rows
    count in, and its categories (TR-03)."""
    by_id = {t.fingerprint: t for t in (txns if txns is not None else st.all_transactions())}
    rows = [by_id[i] for i in trip["ids"] if i in by_id]
    totals: dict[str, float] = {}
    cats: dict[str, dict] = {}
    for t in rows:
        cur = (t.currency or "").upper() or "CAD"
        totals[cur] = round(totals.get(cur, 0.0) + t.amount, 2)
        c = cats.setdefault(t.category or "Other", {"category": t.category or "Other", "count": 0, "totals": {}})
        c["count"] += 1
        c["totals"][cur] = round(c["totals"].get(cur, 0.0) + t.amount, 2)
    months = sorted({t.date[:7] for t in rows})
    return {**trip, "count": len(rows),
            "totals": [{"currency": c, "amount": a} for c, a in sorted(totals.items(), key=lambda x: -abs(x[1]))],
            "months": months, "month_names": [_month_name(m) for m in months],
            "categories": sorted(cats.values(), key=lambda c: -sum(abs(v) for v in c["totals"].values()))}


# ── Asking (TR-01) ─────────────────────────────────────────────────────────

def _skipped(st) -> list[list[str]]:
    out = _json(st, SKIPPED_KEY, [])
    return out if isinstance(out, list) else []


def _skip_dates(st, start: str, end_: str) -> bool:
    """True if these dates weren't skipped already."""
    s = _skipped(st)
    if [start, end_] in s:
        return False
    s.append([start, end_])
    _save(st, SKIPPED_KEY, s)
    return True


def _unskip_dates(st, start: str, end_: str) -> None:
    s = _skipped(st)
    if [start, end_] in s:
        s.remove([start, end_])
        _save(st, SKIPPED_KEY, s)


def _overlaps(a: tuple[str, str], b: tuple[str, str]) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


def _city(t: Transaction) -> str:
    return " ".join(str((t.raw or {}).get("city") or "").split())


def _spending(t: Transaction) -> bool:
    return t.amount > 0 and not t.excluded and (t.category or "Other") not in NON_SPEND


def candidates(st, txns: list[Transaction], today: str) -> list[dict]:
    """Likely trips Pearl may ask about: two signals agree, none overlapping a
    trip or dates she skipped, ended in the last four months."""
    spend = sorted((t for t in txns if _spending(t) or FEE.search(t.description or "")),
                   key=lambda t: (t.date, t.fingerprint))
    if not spend:
        return []
    first_day = min(t.date[:10] for t in txns)
    settled = (date.fromisoformat(first_day) + timedelta(days=SETTLE)).isoformat()
    first_seen: dict[str, str] = {}
    for t in spend:
        k = merchant_key(t.merchant or "")
        if k and k not in first_seen:
            first_seen[k] = t.date[:10]
    new = [t for t in spend if t.amount > 0 and t.date[:10] >= settled
           and first_seen.get(merchant_key(t.merchant or "")) == t.date[:10]
           and (t.category or "") not in ("Travel", "Lodging") and not FEE.search(t.description or "")]
    runs: list[list[Transaction]] = []
    for t in new:
        if runs and (date.fromisoformat(t.date[:10]) - date.fromisoformat(runs[-1][-1].date[:10])).days <= RUN_GAP:
            runs[-1].append(t)
        else:
            runs.append([t])
    cities = Counter(_city(t) for t in txns if _city(t))
    home = cities.most_common(1)[0][0] if cities else ""
    busy = [(t["start"], t["end"]) for t in all_trips(st).values()] + [tuple(s) for s in _skipped(st)]
    taken = trip_of(st)
    oldest = (date.fromisoformat(today) - timedelta(days=LOOKBACK)).isoformat()
    out = []
    for run in runs:
        days = sorted({t.date[:10] for t in run})
        start, end_ = days[0], days[-1]
        span = (date.fromisoformat(end_) - date.fromisoformat(start)).days + 1
        if len(run) < RUN_MIN or len(days) < 2 or span > RUN_SPAN or end_ < oldest or end_ >= today:
            continue
        if any(_overlaps((start, end_), b) for b in busy):
            continue
        before = (date.fromisoformat(start) - timedelta(days=BEFORE)).isoformat()
        after = (date.fromisoformat(end_) + timedelta(days=3)).isoformat()
        flights = [t for t in spend if t.category == "Travel" and before <= t.date[:10] <= end_]
        hotels = [t for t in spend if t.category == "Lodging" and before <= t.date[:10] <= end_]
        fees = [t for t in spend if FEE.search(t.description or "") and start <= t.date[:10] <= after]
        away = Counter(_city(t) for t in run if _city(t) and _city(t) != home)
        place = away.most_common(1)[0][0] if away and away.most_common(1)[0][1] * 2 >= len(run) else None
        if not (flights or hotels or fees or place):
            continue                                        # one signal is not enough
        rows = [t for t in spend if t.amount > 0 and start <= t.date[:10] <= end_] + flights + hotels + fees
        ids = [i for i in dict.fromkeys(t.fingerprint for t in sorted(rows, key=lambda t: t.date))
               if i not in taken]
        trip = {"id": f"{start}:{end_}", "key": f"trip:{start}:{end_}", "ids": ids,
                "start": start, "end": end_, "days": span, "place": place,
                "flight": bool(flights), "hotel": bool(hotels), "fees": bool(fees),
                "name": f"Trip to {place}" if place else ""}
        out.append({**summary(st, {**trip, "id": trip["id"]}, txns), **trip})
    return out


def ask_yes(st, cid: str, today: str, txns: list[Transaction] | None = None) -> dict | None:
    """Yes on TR-01: the trip, named for its place (or "Trip" with none)."""
    txns = st.all_transactions() if txns is None else txns
    cand = next((c for c in candidates(st, txns, today) if c["id"] == cid), None)
    if cand is None:
        return None
    name = cand["name"] or _free_name(st, "Trip")
    return create(st, cand["ids"], name, "pearl", today, place=cand["place"])


def _free_name(st, base: str) -> str:
    names = {t["name"].lower() for t in all_trips(st).values()}
    if base.lower() not in names:
        return base
    n = 2
    while f"{base} {n}".lower() in names:
        n += 1
    return f"{base} {n}"


def ask_skip(st, cid: str, today: str, txns: list[Transaction] | None = None) -> bool:
    """Skip on TR-01: never asked about those dates again."""
    txns = st.all_transactions() if txns is None else txns
    cand = next((c for c in candidates(st, txns, today) if c["id"] == cid), None)
    if cand is None:
        return False
    _skip_dates(st, cand["start"], cand["end"])
    return True
