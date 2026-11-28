"""Quick sort's endpoints (THL-254; finance/quick_sort.py).

* GET  /api/quick-sort                 whether to show the prompt, and the cards.
* POST /api/quick-sort/seen            {ids, start}: Start or Later; once a day.
* PUT  /api/quick-sort/<id>            {action: right|category|marked|skip|undo, category?, title?,
                                        every?}: every = every open guess from the merchant (T-85).
* POST /api/quick-sort/done            the done screen: safe to spend before → after, rules saved.
* POST /api/quick-sort/pairs/<out>/<in>/<answer>   TR-30: yes, not_this, skip or undo.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import quick_sort
from .api import bp, store


def _today() -> date:
    return date.fromisoformat(core._today_iso())


@bp.get("/quick-sort")
def quick_sort_prompt():
    st = store()
    everything = request.args.get("all") in ("1", "true")
    return jsonify(quick_sort.prompt(st, st.all_transactions(), _today(), everything))


@bp.post("/quick-sort/seen")
def quick_sort_seen():
    st = store()
    body = request.get_json(silent=True) or {}
    ids = body.get("ids") or []
    if not isinstance(ids, list) or not all(isinstance(i, str) for i in ids) or len(ids) > 200:
        return jsonify({"error": "Which transactions?"}), 400
    return jsonify(quick_sort.begin(st, st.all_transactions(), _today(), ids, bool(body.get("start"))))


@bp.put("/quick-sort/<txn_id>")
def quick_sort_step(txn_id):
    st = store()
    body = request.get_json(silent=True) or {}
    out = quick_sort.step(st, st.all_transactions(), _today(), txn_id,
                          str(body.get("action") or ""), body.get("category"), body.get("title"),
                          every=body.get("every") if isinstance(body.get("every"), bool) else None,
                          rows=body["rows"] if isinstance(body.get("rows"), list) else None,
                          new_ones=body.get("new_ones") if isinstance(body.get("new_ones"), bool) else None)
    if isinstance(out, tuple):
        return jsonify(out[0]), out[1]
    return jsonify(out)


@bp.post("/quick-sort/done")
def quick_sort_done():
    st = store()
    return jsonify(quick_sort.finish(st, st.all_transactions(), _today()))


# ── TR-30 (AI4-Pair, THL-309): one card about one pair ──────────────────

@bp.post("/quick-sort/pairs/<out_id>/<in_id>/<answer>")
def quick_sort_pair(out_id, in_id, answer):
    """Yes links the two as one transfer (with the link's Undo); Not this
    and Skip leave both rows as they are. `undo` takes any of them back."""
    from . import pair_asks
    st = store()
    today = _today().isoformat()
    if answer == "undo":
        pair_asks.undo(st, out_id, in_id, today)
        return jsonify({"ok": True})
    if answer not in ("yes", "not_this", "skip"):
        return jsonify({"error": "Yes, Not this or Skip."}), 400
    p = pair_asks.lookup(st, out_id, in_id, today)
    if p is None:
        return jsonify({"error": "Pearl isn’t asking about these any more."}), 404
    if answer == "not_this":
        pair_asks.not_this(st, p, today)
        return jsonify({"ok": True})
    if answer == "skip":
        pair_asks.skip(st, p, today)
        return jsonify({"ok": True})
    out, status = core.link_rows(st, out_id, [in_id])
    if status != 200:
        return jsonify(out), status
    pair_asks.yes(st, p, today)
    return jsonify(out)
