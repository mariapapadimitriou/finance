"""Also 8 older ones? (REFRESH-17): what to ask, Yes, and Leave them in
Transfers. See finance/older_transfers.py."""

from __future__ import annotations

from flask import jsonify, request

from . import older_transfers as older
from .api import _reclassify, bp, store


def _row(t) -> dict:
    from .analytics import share_amount
    return {"id": t.fingerprint, "date": t.date[:10], "amount": round(t.amount, 2),
            "mine": round(share_amount(t) if t.joint else t.amount, 2)}


@bp.get("/transactions/<txn_id>/older")
def older_ones(txn_id: str):
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    rows = older.find(st, t)
    share = t.joint_split if t.joint_split is not None else t.joint_share
    return jsonify({"id": t.fingerprint, "category": t.category,
                    "account": t.account_label or "",
                    # Her part of them, for "your half" / "your 60%".
                    "share": share if t.joint and share is not None and share < 100 else None,
                    "older": [_row(x) for x in rows]})


@bp.post("/transactions/<txn_id>/older")
def sort_older(txn_id: str):
    """Yes: the ones listed, sorted as this one is. Each is checked again: one
    answered or matched meanwhile is left alone, and the count says so."""
    from .impact import snapshot, undo_payload
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or not all(isinstance(i, str) for i in ids):
        return jsonify({"error": "Choose at least one transaction."}), 400
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    txns = st.all_transactions()
    chosen = [x for x in older.find(st, t, txns) if x.fingerprint in set(ids)]
    if not chosen:
        return jsonify({"error": "Those are already sorted."}), 409
    before = snapshot(st, txns)
    st.write_categories({x.fingerprint: (t.category, "user") for x in chosen})
    _reclassify(st)
    undo = undo_payload(before, snapshot(st, st.all_transactions()))
    return jsonify({"ok": True, "moved": len(chosen),
                    "title": f"{len(chosen)} more moved to {t.category}", "undo": undo})


@bp.post("/transactions/<txn_id>/older/no")
def leave_older(txn_id: str):
    """Leave them in Transfers: not asked again for this name and account."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    st.dismiss_review(older.key_for(t))
    return jsonify({"ok": True})
