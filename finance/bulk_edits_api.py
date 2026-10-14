"""Sort a date range: one category for every purchase in it (finance/bulk_edits.py)."""

from __future__ import annotations

from flask import jsonify, request

from . import bulk_edits
from .api import _reclassify, bp, store


def _body() -> dict:
    return request.get_json(silent=True) or {}


@bp.get("/bulk-edits")
def list_bulk_edits():
    st = store()
    return jsonify({"edits": bulk_edits.listing(st, st.all_transactions())})


@bp.post("/bulk-edits/preview")
def preview_bulk_edit():
    """What saving would change, and what stays as it is."""
    b = _body()
    problem = bulk_edits.validate(b.get("name") or "range", b.get("category") or "",
                                  b.get("start"), b.get("end"))
    if problem:
        return jsonify({"error": problem}), 400
    st = store()
    edit_id = b.get("edit_id")
    return jsonify(bulk_edits.preview(st.all_transactions(), b["start"], b["end"], b["category"],
                                      int(edit_id) if edit_id else None, st.bulk_edit_rows(),
                                      st.bulk_edit_rows_before()))


def _save(edit_id: int | None):
    b = _body()
    problem = bulk_edits.validate(b.get("name"), b.get("category") or "", b.get("start"),
                                  b.get("end"))
    if problem:
        return jsonify({"error": problem}), 400
    st = store()
    edit_id = bulk_edits.save(st, b["name"], b["category"], b["start"], b["end"], edit_id)
    _reclassify(st)
    edit = next(e for e in bulk_edits.listing(st, st.all_transactions()) if e["id"] == edit_id)
    return jsonify({"ok": True, "edit": edit})


@bp.post("/bulk-edits")
def create_bulk_edit():
    return _save(None)


@bp.put("/bulk-edits/<int:edit_id>")
def change_bulk_edit(edit_id: int):
    if not any(e["id"] == edit_id for e in store().bulk_edits()):
        return jsonify({"error": "No such edit."}), 404
    return _save(edit_id)


@bp.delete("/bulk-edits/<int:edit_id>")
def delete_bulk_edit(edit_id: int):
    st = store()
    if not any(e["id"] == edit_id for e in st.bulk_edits()):
        return jsonify({"error": "No such edit."}), 404
    put_back = bulk_edits.remove(st, edit_id)
    _reclassify(st)
    return jsonify({"ok": True, "put_back": put_back})
