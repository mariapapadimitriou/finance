"""Trips (product owner, 2026-11-15; Figma Proposals › Trips 1327:4973,
note 1329:69536 · THL-122, THL-123, THL-226, THL-263).

A trip is its own thing: a name, its transactions, their dates, a total and
a page. It adds a tag with the same name, and the two stay in step: renaming
the trip renames the tag, and taking the tag off (Tags, TR-09) ends the trip.
A trip never moves money between months: each row still counts in its own.

AI only detects; she confirms. Pearl asks about a likely trip with one Quick
sort card (TR-01), and only when two signals agree (product owner). Four
kinds of signal:

* new places: a run of first-time merchants, at least RUN_MIN rows on two
  or more days, no more than RUN_GAP days apart. Not in her first SETTLE
  days of history, when every merchant is new;
* away: a run of spending, as long, in a city (where Plaid gives one) that
  isn't home. Home is the city she's mostly in around then, so a move
  doesn't make months of her life "away"; a second trip to the same place,
  same hotel and restaurants, is still away;
* a booking: a flight (Travel) in the two weeks before or during it, or a
  hotel (Lodging) then that isn't in her home city;
* foreign transaction fees during it (on two days or more, a run too);
* gone from home: with away only, nothing spent in her home city on any of
  those days, where she spends there most days around them (a road trip
  with no booking, to a place she's been before).

A run of one kind and a second kind with it make an ask; one alone never
does. Runs that touch are one trip. A stay longer than RUN_SPAN days isn't
a trip (a work stint), and the same away city again within STINT_GAP days
is the same stay. Her whole history counts, back to the first day: after
Start over she's asked about every trip again, newest first.

Nothing groups until she says Yes. Skip and Pearl never asks about those
dates again (`SKIPPED_KEY`). She can make a trip herself from Select (TR-07,
TR-08). There is no currency conversion anywhere in Pearl: each amount is as
its card was billed, so a trip across currencies is totalled per currency.
"""

from __future__ import annotations

import json
import re
import uuid
from bisect import bisect_left, bisect_right
from collections import Counter
from datetime import date, datetime, timedelta, timezone

from .categorize import NON_SPEND, merchant_key
from .models import Transaction

TRIPS_KEY = "trips"                 # {id: trip}
SKIPPED_KEY = "trip_skipped"        # [[start, end]] she skipped: never asked again
ENDED_KEY = "trip_ended"            # {id: {trip, skipped}}: what Undo on TR-13 puts back
ENDED_KEEP = 20                     # the last few ended trips, for Undo
RUN_MIN = 4                         # rows in a run of new places or away
RUN_GAP = 2                         # days between them, at most
RUN_SPAN = 21                       # a run this long isn't a trip
STINT_GAP = 7                       # the same away city again within a week: the same stay
BEFORE = 14                         # a flight or hotel booked up to two weeks before
SETTLE = 30                         # days of history before a merchant counts as "new"
HOME_MONTHS = 2                     # home: her usual city within two months either side
HOME_MIN = 10                       # rows with a city needed to say so; else her usual city overall
AROUND = 28                         # "gone from home": the days either side that show her usual
STEADY_DAYS = 14                    # at least this many of them in her history
STEADY_SHARE = 0.5                  # and she spent in her home city on at least half
FEE =re.compile(r"\b(foreign transaction fee|forex fee|fx fee|foreign fee|non-sterling|conversion fee)\b", re.I)


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


def _day(t: Transaction) -> str:
    return t.date[:10]


def _gap(a: str, b: str) -> int:
    return (date.fromisoformat(b) - date.fromisoformat(a)).days


def _month_no(day: str) -> int:
    return int(day[:4]) * 12 + int(day[5:7]) - 1


def _homes(txns: list[Transaction]):
    """Her home city on a given day: the city she's mostly in within
    HOME_MONTHS either side, or her usual city overall where that window
    has too few cities to say. Never a fixed place (no city is hard-coded)."""
    by_month: dict[int, Counter] = {}
    for t in txns:
        c = _city(t)
        if c:
            by_month.setdefault(_month_no(_day(t)), Counter())[c] += 1
    overall = sum(by_month.values(), Counter())
    usual = overall.most_common(1)[0][0] if overall else ""
    homes: dict[int, str] = {}
    for m in by_month:
        near = sum((by_month.get(m + k, Counter()) for k in range(-HOME_MONTHS, HOME_MONTHS + 1)), Counter())
        homes[m] = near.most_common(1)[0][0] if sum(near.values()) >= HOME_MIN else usual
    return lambda day: homes.get(_month_no(day), usual)


def _runs(rows: list[Transaction], gap: int = RUN_GAP) -> list[list[Transaction]]:
    """Rows (in date order) no more than `gap` days apart, together."""
    runs: list[list[Transaction]] = []
    for t in rows:
        if runs and _gap(_day(runs[-1][-1]), _day(t)) <= gap:
            runs[-1].append(t)
        else:
            runs.append([t])
    return runs


def _main_city(run: list[Transaction]) -> str:
    return Counter(_city(t) for t in run).most_common(1)[0][0]


def _stints(runs: list[list[Transaction]]) -> list[list[Transaction]]:
    """The same away city again within STINT_GAP days is the same stay: a
    month's work there with weekends off is one long stint, not four trips."""
    out: list[list[Transaction]] = []
    for run in runs:
        if out and _main_city(out[-1]) == _main_city(run) and _gap(_day(out[-1][-1]), _day(run[0])) <= STINT_GAP:
            out[-1] = out[-1] + run
        else:
            out.append(run)
    return out


def _windows(kinds: dict[str, list[list[Transaction]]]) -> list[dict]:
    """Every run, with the runs that touch it (RUN_GAP days or less), as one
    span of dates with the kinds of run in it."""
    spans = sorted((_day(r[0]), _day(r[-1]), k) for k, runs in kinds.items() for r in runs)
    out: list[dict] = []
    for start, end_, kind in spans:
        if out and _gap(out[-1]["end"], start) <= RUN_GAP:
            out[-1]["end"] = max(out[-1]["end"], end_)
            out[-1]["kinds"].add(kind)
        else:
            out.append({"start": start, "end": end_, "kinds": {kind}})
    return out


def candidates(st, txns: list[Transaction], today: str) -> list[dict]:
    """Likely trips Pearl may ask about, across her whole history: two kinds
    of signal agree, none overlapping a trip or dates she skipped, newest
    first (the one she remembers best, and the one that matters to this
    month, comes first; each is still its own question). None while a
    bank's history is still coming in (after Start over or a new link): a
    recent slice alone would make every merchant look new."""
    if not st.plaid_history_ready():
        return []
    spend = sorted((t for t in txns if _spending(t) or FEE.search(t.description or "")),
                   key=lambda t: (t.date, t.fingerprint))
    if not spend:
        return []
    first_day = min(_day(t) for t in txns)
    settled = (date.fromisoformat(first_day) + timedelta(days=SETTLE)).isoformat()
    home = _homes(txns)
    first_seen: dict[str, str] = {}
    for t in spend:
        k = merchant_key(t.merchant or "")
        if k and k not in first_seen:
            first_seen[k] = _day(t)
    fee_rows = [t for t in spend if FEE.search(t.description or "")]
    # What she spent there: not the flight, the hotel or the fee, which are
    # signals of their own.
    there = [t for t in spend if t.amount > 0 and (t.category or "") not in ("Travel", "Lodging")
             and not FEE.search(t.description or "")]
    new = [t for t in there if _day(t) >= settled and first_seen.get(merchant_key(t.merchant or "")) == _day(t)]
    away = [t for t in there if _city(t) and _city(t) != home(_day(t))]

    def enough(run: list[Transaction], rows: int) -> bool:
        return len(run) >= rows and len({_day(t) for t in run}) >= 2

    windows = _windows({
        "new": [r for r in _runs(new) if enough(r, RUN_MIN)],
        "away": [r for r in _stints(_runs(away)) if enough(r, RUN_MIN)],
        "fees": [r for r in _runs(fee_rows) if enough(r, 2)],
    })
    flights_all = [t for t in spend if t.category == "Travel"]
    hotels_all = [t for t in spend if t.category == "Lodging" and not (_city(t) and _city(t) == home(_day(t)))]
    there_days = [_day(t) for t in there]
    at_home = {_day(t) for t in there if _city(t) and _city(t) == home(_day(t))}

    def gone_from_home(start: str, end_: str) -> bool:
        """Nothing spent at home those days, where she spends there most days
        around them: a home with steady daily spending, so a quiet spell
        isn't taken for being away."""
        s, e = date.fromisoformat(start), date.fromisoformat(end_)
        if any((s + timedelta(days=i)).isoformat() in at_home for i in range((e - s).days + 1)):
            return False
        near = [d for d in ((s - timedelta(days=i)).isoformat() for i in range(1, AROUND + 1))
                if d >= first_day] + \
               [d for d in ((e + timedelta(days=i)).isoformat() for i in range(1, AROUND + 1))
                if d < today]
        return len(near) >= STEADY_DAYS and sum(d in at_home for d in near) >= STEADY_SHARE * len(near)
    busy = [(t["start"], t["end"]) for t in all_trips(st).values()] + [tuple(s) for s in _skipped(st)]
    taken = trip_of(st)
    out = []
    for w in windows:
        start, end_ = w["start"], w["end"]
        span = _gap(start, end_) + 1
        if span > RUN_SPAN or end_ >= today:
            continue                                        # a stint, or not over yet
        if any(_overlaps((start, end_), b) for b in busy):
            continue
        before = (date.fromisoformat(start) - timedelta(days=BEFORE)).isoformat()
        after = (date.fromisoformat(end_) + timedelta(days=3)).isoformat()
        flights = [t for t in flights_all if before <= _day(t) <= end_]
        hotels = [t for t in hotels_all if before <= _day(t) <= end_]
        fees = [t for t in fee_rows if start <= _day(t) <= after]
        inside = there[bisect_left(there_days, start):bisect_right(there_days, end_)]
        with_city = [t for t in inside if _city(t)]
        elsewhere = Counter(_city(t) for t in with_city if _city(t) != home(_day(t)))
        top = elsewhere.most_common(1)
        place = top[0][0] if top and top[0][1] * 2 >= len(with_city) else None
        away_ = "away" in w["kinds"] or place is not None
        signals = ["new" in w["kinds"], away_, bool(flights or hotels), "fees" in w["kinds"] or bool(fees),
                   away_ and gone_from_home(start, end_)]
        if sum(signals) < 2:
            continue                                        # one signal is not enough
        rows = inside + flights + hotels + fees
        picked = {t.fingerprint: t for t in sorted(rows, key=lambda t: t.date)}
        ids = [i for i in picked if i not in taken]
        trip = {"id": f"{start}:{end_}", "key": f"trip:{start}:{end_}", "ids": ids,
                "start": start, "end": end_, "days": span, "place": place,
                "flight": bool(flights), "hotel": bool(hotels), "fees": bool(fees),
                "name": f"Trip to {place}" if place else ""}
        out.append({**summary(st, trip, [picked[i] for i in ids]), **trip})
    out.sort(key=lambda c: (c["end"], c["start"]), reverse=True)
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
