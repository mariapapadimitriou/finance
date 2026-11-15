"""Trips: the endpoints (finance/trips.py).

* GET    /api/trips                    every trip, with its totals
* POST   /api/trips                    Make a trip {ids, name} (TR-07, TR-08)
* GET    /api/trips/<id>               the trip's page (TR-02, TR-03): totals, months, categories, rows
* PUT    /api/trips/<id>               Rename {name} (renames its tag too) · Add {add} · Remove some {remove}
* DELETE /api/trips/<id>               It wasn't a trip: the trip and its tag go, the rows stay
                                        (?undo=1: Undo after Make a trip; its dates aren't skipped)
* POST   /api/trips/<id>/restore       Undo on "Not a trip" (TR-13): the same trip back, dates unskipped
* GET    /api/trips/asks               TR-01: likely trips Pearl asks about (two signals agree)
* POST   /api/trips/asks/<id>/yes      Yes: one trip, named for its place
* POST   /api/trips/asks/<id>/skip     Skip: never asked about those dates again
"""

from __future__ import annotations

from flask import jsonify, request

from . import api as core
from . import trips
from .api import bp, store


def _ids(body) -> list[str]:
    ids = body.get("ids") if isinstance(body, dict) else None
    return [str(i) for i in ids] if isinstance(ids, list) else []


@bp.get("/trips")
def trips_list():
    st = store()
    txns = st.all_transactions()
    out = [trips.summary(st, t, txns) for t in trips.all_trips(st).values()]
    return jsonify({"trips": sorted(out, key=lambda t: t["start"], reverse=True)})


@bp.post("/trips")
def trips_make():
    st = store()
    body = request.get_json(silent=True) or {}
    try:
        trip = trips.create(st, _ids(body), body.get("name") or "", "you", core._today_iso())
    except trips.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "trip": trips.summary(st, trip)})


@bp.get("/trips/asks")
def trips_asks():
    st = store()
    return jsonify({"asks": trips.candidates(st, st.all_transactions(), core._today_iso())})


@bp.post("/trips/asks/<cid>/yes")
def trips_ask_yes(cid: str):
    st = store()
    try:
        trip = trips.ask_yes(st, cid, core._today_iso())
    except trips.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    if trip is None:
        return jsonify({"error": "Nothing to say yes to."}), 404
    return jsonify({"ok": True, "trip": trips.summary(st, trip)})


@bp.post("/trips/asks/<cid>/skip")
def trips_ask_skip(cid: str):
    st = store()
    if not trips.ask_skip(st, cid, core._today_iso()):
        return jsonify({"error": "Nothing to skip."}), 404
    return jsonify({"ok": True})


@bp.get("/trips/<trip_id>")
def trips_one(trip_id: str):
    st = store()
    trip = trips.all_trips(st).get(trip_id)
    if trip is None:
        return jsonify({"error": "That trip isn’t there any more."}), 404
    # TR-02m: each row says its billing currency, so one in another reads "−$142.00 USD".
    rows = {t.fingerprint: {**r, "currency": (t.currency or "").upper() or "CAD"}
            for t, r in core._txlist_rows(st, everything=True)}
    return jsonify({"trip": trips.summary(st, trip),
                    "rows": sorted((rows[i] for i in trip["ids"] if i in rows),
                                   key=lambda r: r["date"], reverse=True)})


@bp.put("/trips/<trip_id>")
def trips_change(trip_id: str):
    st = store()
    body = request.get_json(silent=True) or {}
    try:
        if body.get("name") is not None:
            trip = trips.rename(st, trip_id, body["name"])
        else:
            add = [str(i) for i in body.get("add") or []]
            remove = [str(i) for i in body.get("remove") or []]
            trip = trips.change(st, trip_id, add, remove)
            if trip.get("ended"):
                return jsonify({"ok": True, "ended": True})
    except KeyError:
        return jsonify({"error": "That trip isn’t there any more."}), 404
    except trips.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "trip": trips.summary(st, trip)})


@bp.delete("/trips/<trip_id>")
def trips_end(trip_id: str):
    st = store()
    # TR-02c: Undo on "Trip to Montréal made" takes back only what she just did.
    undo = request.args.get("undo") in ("1", "true")
    trip = trips.end(st, trip_id, skip=not undo)
    if trip is None:
        return jsonify({"error": "That trip isn’t there any more."}), 404
    return jsonify({"ok": True, "count": len(trip["ids"])})


@bp.post("/trips/<trip_id>/restore")
def trips_restore(trip_id: str):
    st = store()
    try:
        trip = trips.restore(st, trip_id)
    except trips.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    if trip is None:
        return jsonify({"error": "There’s nothing to put back."}), 404
    return jsonify({"ok": True, "trip": trips.summary(st, trip)})
