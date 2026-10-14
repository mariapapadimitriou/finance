"""Trips' endpoints (THL-174): mark a date range's spending as Travel."""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import trips
from .api import _reclassify, _today_iso, bp, store


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _today() -> date:
    return date.fromisoformat(_today_iso())


@bp.get("/trips")
def list_trips():
    st = store()
    return jsonify({"trips": trips.listing(st, st.all_transactions())})


@bp.post("/trips/preview")
def preview_trip():
    """What saving would move to Travel, and what stays as it is."""
    b = _body()
    problem = trips.validate(b.get("name") or "trip", b.get("start"), b.get("end"))
    if problem:
        return jsonify({"error": problem}), 400
    st = store()
    trip_id = b.get("trip_id")
    return jsonify(trips.preview(st.all_transactions(), b["start"], b["end"], _today(),
                                 int(trip_id) if trip_id else None, st.trip_rows(),
                                 st.trip_rows_before()))


def _save(trip_id: int | None):
    b = _body()
    problem = trips.validate(b.get("name"), b.get("start"), b.get("end"))
    if problem:
        return jsonify({"error": problem}), 400
    st = store()
    trip_id = trips.save(st, b["name"], b["start"], b["end"], _today(), trip_id)
    _reclassify(st)
    trip = next(t for t in trips.listing(st, st.all_transactions()) if t["id"] == trip_id)
    return jsonify({"ok": True, "trip": trip})


@bp.post("/trips")
def create_trip():
    return _save(None)


@bp.put("/trips/<int:trip_id>")
def edit_trip(trip_id: int):
    if not any(t["id"] == trip_id for t in store().marked_trips()):
        return jsonify({"error": "No such trip."}), 404
    return _save(trip_id)


@bp.delete("/trips/<int:trip_id>")
def delete_trip(trip_id: int):
    st = store()
    if not any(t["id"] == trip_id for t in st.marked_trips()):
        return jsonify({"error": "No such trip."}), 404
    moved = trips.remove(st, trip_id)
    _reclassify(st)
    return jsonify({"ok": True, "put_back": moved})
