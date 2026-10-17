"""Quick sort's endpoints (THL-254; finance/quick_sort.py).

* GET  /api/quick-sort                 whether to show the prompt, and the cards.
* POST /api/quick-sort/seen            {ids, start}: Start or Later; once a day.
* PUT  /api/quick-sort/<id>            {action: right|category|marked|skip, category?, title?}.
* POST /api/quick-sort/done            the done screen: Allowance before → after, rules saved.
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
    return jsonify(quick_sort.prompt(st, st.all_transactions(), _today()))


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
                          str(body.get("action") or ""), body.get("category"), body.get("title"))
    if isinstance(out, tuple):
        return jsonify(out[0]), out[1]
    return jsonify(out)


@bp.post("/quick-sort/done")
def quick_sort_done():
    st = store()
    return jsonify(quick_sort.finish(st, st.all_transactions(), _today()))
