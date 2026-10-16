"""The expense calendar's endpoints (THL-255; finance/calendar_view.py).

* GET /api/calendar?month=YYYY-MM   the month: cells, totals, what's coming up.
* GET /api/calendar/day/<date>      one day: what was spent, what's due, why it's shaded.
* GET /api/calendar/range?first&last  Select days (CAL-06): what was spent in
  those days by category, and what in them isn't counted.
"""

from __future__ import annotations

import re
from datetime import date

from flask import jsonify, request

from . import api as core
from . import calendar_view
from .api import bp, store

MONTH = re.compile(r"^\d{4}-(0[1-9]|1[0-2])$")
DAY = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def _today() -> date:
    return date.fromisoformat(core._today_iso())


@bp.get("/calendar")
def calendar_month():
    st = store()
    today = _today()
    month = request.args.get("month") or today.strftime("%Y-%m")
    if not MONTH.match(month):
        return jsonify({"error": "month is YYYY-MM."}), 400
    txns = st.all_transactions()
    return jsonify(calendar_view.month_view(st, txns, today, month))


@bp.get("/calendar/day/<iso>")
def calendar_day(iso):
    if not DAY.match(iso):
        return jsonify({"error": "A day is YYYY-MM-DD."}), 400
    try:
        date.fromisoformat(iso)
    except ValueError:
        return jsonify({"error": "That isn’t a day."}), 400
    st = store()
    txns = st.all_transactions()
    return jsonify(calendar_view.day_view(st, txns, _today(), iso))


@bp.get("/calendar/range")
def calendar_range():
    first, last = request.args.get("first", ""), request.args.get("last", "")
    if not (DAY.match(first) and DAY.match(last)):
        return jsonify({"error": "first and last are YYYY-MM-DD."}), 400
    try:
        a, b = date.fromisoformat(first), date.fromisoformat(last)
    except ValueError:
        return jsonify({"error": "That isn’t a day."}), 400
    if b < a:
        a, b = b, a
    if (b - a).days > 366:
        return jsonify({"error": "A range is a year at most."}), 400
    st = store()
    txns = st.all_transactions()
    return jsonify(calendar_view.range_view(st, txns, _today(), a.isoformat(), b.isoformat()))
