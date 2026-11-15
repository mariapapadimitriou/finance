"""Pearl sorts for you, P1a: the endpoints (finance/pattern_sort.py).

* POST   /api/pattern-sort/run                 sort what can be, now (the app calls it on open)
* GET    /api/pattern-sort                     AI-01/AI-02: this week's count and the rows, each with its reason
* GET    /api/pattern-sort/<record>            AI-03: why Pearl sorted this one
* POST   /api/pattern-sort/<record>/undo       AI-03 Undo this one (and never again for that row)
* GET    /api/pattern-sort/rules               AI-05: learned rules, beside hers
* GET    /api/pattern-sort/rules/<id>          AI-06: one learned rule
* PUT    /api/pattern-sort/rules/<id>          AI-06's switch {on}
* POST   /api/pattern-sort/rules/<id>/stop     AI-04 Stop sorting like this (undoes every row), with Undo
* POST   /api/pattern-sort/rules/<id>/restart  Stop's Undo
"""

from __future__ import annotations

from flask import g, jsonify, request

from . import api as core
from . import pattern_sort as ps
from . import users
from .api import bp, store


def _consented() -> bool:
    user = g.get("user")
    if user is None:
        # Tests and the demo server have no signed-in user: the switch is the baseline.
        return ps.is_on(store())
    return bool((users.effective_consents(user).get("ai_sort") or {}).get("value"))


def _row(st, rec: dict) -> dict:
    t = st.get_transaction(rec["txn"])
    return {"id": rec["id"], "txn": rec["txn"], "pattern": rec["pattern"], "kind": rec["kind"],
            "line": rec["line"], "answer": rec["answer"], "count": rec["count"], "day": rec["day"],
            "merchant": (t.merchant or t.description) if t else "", "amount": t.amount if t else 0.0,
            "date": t.date[:10] if t else rec["day"]}


@bp.post("/pattern-sort/run")
def pattern_sort_run():
    st = store()
    if not _consented():
        return jsonify({"sorted": 0, "on": False})
    if not ps.is_on(st):
        # Switched on before this existed: from now on, never the past.
        ps.switched_on(st)
    new = ps.run(st, core._today_iso())
    if new:
        core._reclassify(st)
    return jsonify({"sorted": len(new), "on": True, "rows": [_row(st, r) for r in new]})


@bp.get("/pattern-sort")
def pattern_sort_list():
    st = store()
    today = core._today_iso()
    return jsonify({"on": _consented(), "week": ps.this_week(st, today),
                    "rows": [_row(st, r) for r in ps.records(st)]})


@bp.get("/pattern-sort/rules")
def pattern_sort_rules():
    return jsonify({"rules": ps.learned(store())})


@bp.get("/pattern-sort/rules/<path:pid>")
def pattern_sort_rule(pid: str):
    st = store()
    rule = next((r for r in ps.learned(st) if r["id"] == pid), None)
    if rule is None:
        return jsonify({"error": "No such rule."}), 404
    return jsonify({"rule": rule, "rows": [_row(st, r) for r in ps.records(st) if r["pattern"] == pid]})


@bp.put("/pattern-sort/rules/<path:pid>")
def pattern_sort_switch(pid: str):
    st = store()
    body = request.get_json(silent=True) or {}
    if not isinstance(body.get("on"), bool):
        return jsonify({"error": "Say on or off."}), 400
    if pid not in ps.patterns(st):
        return jsonify({"error": "No such rule."}), 404
    ps.set_enabled(st, pid, body["on"])
    return pattern_sort_rule(pid)


@bp.post("/pattern-sort/rules/<path:pid>/stop")
def pattern_sort_stop(pid: str):
    st = store()
    if pid not in ps.patterns(st):
        return jsonify({"error": "No such rule."}), 404
    undone = ps.stop(st, pid)
    core._reclassify(st)
    n = len(undone)
    return jsonify({"ok": True, "undone": n,
                    "title": f"Stopped · {n} back in Needs a look" if n else "Stopped",
                    "undo": {"pattern": pid, "records": [r["id"] for r in undone]}})


@bp.post("/pattern-sort/rules/<path:pid>/forget")
def pattern_sort_forget(pid: str):
    """AI-06 Forget this rule (asks first in the app): the rule goes; what it
    sorted stays; Pearl may learn it again from new answers."""
    st = store()
    if pid not in ps.patterns(st):
        return jsonify({"error": "No such rule."}), 404
    ps.forget(st, pid, core._today_iso())
    return jsonify({"ok": True, "title": "Forgotten"})


@bp.post("/pattern-sort/rules/<path:pid>/restart")
def pattern_sort_restart(pid: str):
    st = store()
    body = request.get_json(silent=True) or {}
    ps.restart(st, pid, [str(i) for i in body.get("records") or []])
    core._reclassify(st)
    return jsonify({"ok": True})


@bp.get("/pattern-sort/<rid>")
def pattern_sort_one(rid: str):
    st = store()
    rec = next((r for r in ps.records(st) if r["id"] == rid), None)
    if rec is None:
        return jsonify({"error": "That one isn’t sorted by Pearl any more."}), 404
    pat = ps.patterns(st).get(rec["pattern"]) or {}
    same = [r["txn"] for r in ps.records(st) if r["pattern"] == rec["pattern"]]
    return jsonify({**_row(st, rec), "label": ps.label(pat) if pat else rec["answer"],
                    "account": pat.get("account"), "sorted_by_pattern": same,
                    "pattern_count": pat.get("count", rec["count"])})


@bp.post("/pattern-sort/<rid>/undo")
def pattern_sort_undo(rid: str):
    st = store()
    rec = ps.undo(st, rid)
    if rec is None:
        return jsonify({"error": "Nothing to undo."}), 404
    core._reclassify(st)
    return jsonify({"ok": True, "title": "Undone · back in Needs a look", "txn": rec["txn"]})
