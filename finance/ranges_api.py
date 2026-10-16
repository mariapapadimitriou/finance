"""Sort a date range and Sorted together (DR-01, DR-02; finance/ranges.py).

* GET    /api/ranges               every range, with its running total.
* POST   /api/ranges/preview       {name, first, last, category, bank_id?}:
  what it would do, without writing. A bank_id is the treasure chest that
  pays for the purchases (CAL-08); without one they count in the month.
* POST   /api/ranges               sort it. Answers with the range and what
  it did; a change of category elsewhere undoes nothing here — Remove does.
* PUT    /api/ranges/<id>          change it: every row goes back, then the
  new range is applied.
* DELETE /api/ranges/<id>          remove it: every row it sorted goes back.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import ranges
from .api import bp, store


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _bank_for(st, r: dict):
    """The chest a range is paid from, with what it holds — what was set
    aside less what it has paid for — or None."""
    from . import piggy
    bank_id = r.get("bank_id")
    if not bank_id:
        return None
    bank = st.piggy_bank(bank_id)
    if bank is None:
        raise ranges.Problem("That treasure chest is gone.")
    played = piggy.status(bank, st.bank_charges_by_month().get(bank_id, {}))
    return {"id": bank_id, "name": bank.name, "held": float(played["held"])}


def _words(p: dict, dry: bool = False, bank: dict | None = None, applied: bool = False) -> dict:
    """The sheet's summary: what moves, what it mostly was, what stays, and
    — paid from a chest — what that does to the month (CAL-07, CAL-08)."""
    n, cat, total = p["count"], p["category"], p["total"]
    what = f"{n} purchase{'' if n == 1 else 's'} · ${total:,.2f}"
    paid = f", paid from {bank['name']}" if bank else ""
    title = f"{what} become {cat}{paid}." if dry else f"Sorted {n} purchase{'' if n == 1 else 's'} as {cat}{paid}."
    staying = ranges.staying_words(p["staying"])
    effect = ""
    if bank:
        # What the chest will hold once it pays: a preview still has to pay,
        # unless this range is already paying from it.
        left = bank["held"] if applied or p.get("already_paying") else bank["held"] - total
        month = _month_name(p.get("first") or "")
        has = (f"has ${left:,.2f} left" if left >= -0.005
               else f"is ${-left:,.2f} behind, and catches up over the months ahead")
        effect = (f"{bank['name']} pays ${total:,.2f} and {has}. {month}’s spending drops by the "
                  f"same, so safe to spend goes up by ${total:,.2f}.")
        staying = f"The purchases keep {cat} and show “Paid from {bank['name']}”. " + staying
    return {"title": title, "mostly": ranges.mostly_words(p["mostly"]), "staying": staying,
            "effect": effect, "bank": bank["name"] if bank else None}


def _month_name(iso: str) -> str:
    try:
        return date.fromisoformat(iso[:10]).strftime("%B")
    except ValueError:
        return "The month"


@bp.get("/ranges")
def list_ranges():
    return jsonify({"ranges": ranges.listed(store())})


@bp.post("/ranges/preview")
def preview_range():
    body = request.get_json(silent=True) or {}
    try:
        r = ranges.clean(body)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    st = store()
    rid = body.get("id")
    try:
        bank = _bank_for(st, r)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    p = ranges.preview(st, st.all_transactions(), r["first"], r["last"], r["category"], _today(),
                       skip_range=int(rid) if isinstance(rid, int) else None)
    p["first"] = r["first"]
    if isinstance(rid, int):
        current = next((x for x in st.ranges() if x["id"] == rid), None)
        p["already_paying"] = bool(current and current.get("bank_id") == r["bank_id"])
    return jsonify({**{k: v for k, v in p.items() if k not in ("ids", "staying_rows")},
                    **_words(p, dry=True, bank=bank)})


@bp.post("/ranges")
def add_range():
    body = request.get_json(silent=True) or {}
    try:
        r = ranges.clean(body)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    st = store()
    try:
        _bank_for(st, r)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    rid = st.add_range(r["name"], r["first"], r["last"], r["category"], r["bank_id"])
    p = ranges.apply(st, rid, _today())
    p["first"] = r["first"]
    core._reclassify(st)
    listed = next(x for x in ranges.listed(st) if x["id"] == rid)
    return jsonify({"ok": True, "range": listed, "ids": p["ids"],
                    **_words(p, bank=_bank_for(st, r), applied=True)}), 201


@bp.put("/ranges/<int:rid>")
def change_range(rid: int):
    body = request.get_json(silent=True) or {}
    try:
        r = ranges.clean(body)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    st = store()
    try:
        _bank_for(st, r)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    if not any(x["id"] == rid for x in st.ranges()):
        return jsonify({"error": "No such range."}), 404
    ranges.restore(st, rid)               # the old chest, if any, stops paying
    st.update_range(rid, r["name"], r["first"], r["last"], r["category"], r["bank_id"])
    p = ranges.apply(st, rid, _today())
    p["first"] = r["first"]
    core._reclassify(st)
    listed = next(x for x in ranges.listed(st) if x["id"] == rid)
    return jsonify({"ok": True, "range": listed, "ids": p["ids"],
                    **_words(p, bank=_bank_for(st, r), applied=True)})


@bp.delete("/ranges/<int:rid>")
def remove_range(rid: int):
    st = store()
    if not any(x["id"] == rid for x in st.ranges()):
        return jsonify({"error": "No such range."}), 404
    back = ranges.restore(st, rid)
    st.delete_range(rid)
    core._reclassify(st)
    return jsonify({"ok": True, "restored": back,
                    "title": (f"Removed. {back} purchase{'' if back == 1 else 's'} went back."
                              if back else "Removed.")})
