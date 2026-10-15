"""Sort a date range and Sorted together (DR-01, DR-02; finance/ranges.py).

* GET    /api/ranges               every range, with its running total.
* POST   /api/ranges/preview       {name, first, last, category}: what it
  would do, without writing.
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


def _words(p: dict, dry: bool = False) -> dict:
    n, cat = p["count"], p["category"]
    what = f"{n} purchase{'' if n == 1 else 's'} · ${p['total']:,.2f}"
    title = f"{what} become {cat}." if dry else f"Sorted {n} purchase{'' if n == 1 else 's'} as {cat}."
    mostly = p["mostly"]
    mostly_line = ""
    if mostly:
        names = mostly if len(mostly) == 1 else ", ".join(mostly[:-1]) + " and " + mostly[-1]
        mostly_line = f"Mostly {names}."
    s = p["staying"]
    stays = []
    if s["bills"]:
        stays.append(f"{s['bills']} bill{'s' if s['bills'] != 1 else ''} and subscriptions"
                     if s["bills"] != 1 else "1 bill")
    if s["deposits"]:
        stays.append(f"{s['deposits']} deposit{'s' if s['deposits'] != 1 else ''}")
    if s["transfers"]:
        stays.append(f"{s['transfers']} transfer{'s' if s['transfers'] != 1 else ''}")
    staying = (f"Staying as they are: {', '.join(stays)}. " if stays else "")
    staying += "Money in, transfers, card payments, savings and lending never change."
    return {"title": title, "mostly": mostly_line, "staying": staying}


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
    p = ranges.preview(st, st.all_transactions(), r["first"], r["last"], r["category"], _today(),
                       skip_range=int(rid) if isinstance(rid, int) else None)
    return jsonify({**{k: v for k, v in p.items() if k != "ids"}, **_words(p, dry=True)})


@bp.post("/ranges")
def add_range():
    body = request.get_json(silent=True) or {}
    try:
        r = ranges.clean(body)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    st = store()
    rid = st.add_range(r["name"], r["first"], r["last"], r["category"])
    p = ranges.apply(st, rid, _today())
    core._reclassify(st)
    listed = next(x for x in ranges.listed(st) if x["id"] == rid)
    return jsonify({"ok": True, "range": listed, "ids": p["ids"], **_words(p)}), 201


@bp.put("/ranges/<int:rid>")
def change_range(rid: int):
    body = request.get_json(silent=True) or {}
    try:
        r = ranges.clean(body)
    except ranges.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    st = store()
    if not st.update_range(rid, r["name"], r["first"], r["last"], r["category"]):
        return jsonify({"error": "No such range."}), 404
    p = ranges.apply(st, rid, _today())
    core._reclassify(st)
    listed = next(x for x in ranges.listed(st) if x["id"] == rid)
    return jsonify({"ok": True, "range": listed, "ids": p["ids"], **_words(p)})


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
