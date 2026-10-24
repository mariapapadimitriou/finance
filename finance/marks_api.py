"""What was this? — the endpoints (2026-10-14; finance/marks.py).

* GET  /api/transactions/<id>/cases       the cases that apply to this row,
  with what each needs (a category, an account, a candidate purchase), the
  savings accounts money can go to, and the rule each can remember.
* GET  /api/transactions/<id>/charges     ?q=: any purchase this money coming
  in could pay back, by name or amount, newest first (for "Which purchase?").
* POST /api/transactions/<id>/mark        {case, ...}: do one. `?dry=1` says
  what it would do (the line under the choices) without writing. The answer
  carries the impact and an Undo, like a change of category (R-03).
* POST /api/transactions/batch/mark       {ids, case, ...}: the same answer
  for a selection, one Undo. Only the cases that need nothing per row.
* PUT  /api/transactions/<id>/tags        {tags: [...]}: her tags on a row.
* POST /api/transactions/batch/tags       {ids, add: [...], remove: [...]}.
* GET  /api/tags                          every tag, with counts and totals.
* PUT  /api/tags/<tag>                    {name} renames it; {name: null}
  takes it off every row.
* PUT  /api/merchants/name                {merchant, name}: her name for a
  merchant, shown everywhere it is named; an empty name goes back to the
  bank's.
* PUT  /api/rules/categories              {category, hidden}: keep a category
  she never uses out of the pickers.

Every undo goes through POST /api/transactions/undo, which takes `marks`
beside the category rows.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import marks
from .api import bp, store

MAX_BATCH = 500
# Cases a selection can answer at once: nothing to pick per row.
BATCH_CASES = {"spending", "moved", "saved", "lent", "borrowed", "lent_back", "own",
               "out_of_savings", "work", "not_mine", "paying_back"}


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _row(st, txn_id: str):
    return next((t for t in st.all_transactions() if t.fingerprint == txn_id), None)


@bp.get("/transactions/<txn_id>/cases")
def transaction_cases(txn_id: str):
    st = store()
    txns = st.all_transactions()
    t = next((x for x in txns if x.fingerprint == txn_id), None)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    return jsonify(marks.cases(st, t, txns))


@bp.get("/transactions/<txn_id>/charges")
def transaction_charges(txn_id: str):
    """Purchases this money coming in could pay back, searched by name or
    amount (?q=); for the sort card's "Which purchase?" step."""
    st = store()
    txns = st.all_transactions()
    t = next((x for x in txns if x.fingerprint == txn_id), None)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if t.amount >= 0:
        return jsonify({"charges": []})
    return jsonify({"charges": marks.search_charges(t, txns, request.args.get("q", ""),
                                                    st.merchant_names())})


def _impact_for(st, before_txns, after_txns, t, res: dict) -> dict:
    return core._impact(st, before_txns, after_txns, res["from"], res["to"], t.date[:7])


@bp.post("/transactions/<txn_id>/mark")
def mark_transaction(txn_id: str):
    from .impact import snapshot, undo_payload
    from .transfers import apply_transfer_matches
    body = request.get_json(silent=True) or {}
    st = store()
    txns = st.all_transactions()
    t = next((x for x in txns if x.fingerprint == txn_id), None)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    case = str(body.get("case") or "")
    known = {c["key"]: c for c in (marks.OUT_CASES if t.amount > 0 else marks.IN_CASES)}
    if case not in known:
        return jsonify({"error": "Say what this was."}), 400
    if request.args.get("dry"):
        after = marks.preview(t, txns, body)
        if after is None:
            return jsonify({"line": known[case]["effect"], "case": case})
        impact = core._impact(st, txns, after, t.category or "Other",
                              next(x for x in after if x.fingerprint == txn_id).category or "Other",
                              t.date[:7])
        line = impact["line"] or known[case]["effect"]
        return jsonify({"line": line, "case": case, **impact})
    if case == "shared":
        return jsonify({"error": "Split it from the transaction instead."}), 400
    before = snapshot(st, txns)
    try:
        res = marks.apply(st, t, body, _today())
    except marks.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    core._reclassify(st)
    after_txns = st.all_transactions()
    impact = _impact_for(st, txns, after_txns, t, res)
    undo = undo_payload(before, snapshot(st, after_txns))
    if res["marks"]:
        undo["marks"] = res["marks"]
    return jsonify({"ok": True, "id": txn_id, "case": case, "title": res["title"],
                    "detail": res.get("detail") or impact.get("detail") or "", "impact": impact,
                    "remember": res["remember"], "undo": undo})


@bp.post("/transactions/batch/mark")
def batch_mark():
    from .impact import snapshot, undo_payload
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_BATCH \
            or not all(isinstance(i, str) for i in ids):
        return jsonify({"error": "Choose at least one transaction."}), 400
    ids = list(dict.fromkeys(ids))
    case = str(body.get("case") or "")
    if case not in BATCH_CASES:
        return jsonify({"error": "That answer is one transaction at a time."}), 400
    st = store()
    txns = st.all_transactions()
    by_id = {t.fingerprint: t for t in txns}
    if any(i not in by_id for i in ids):
        return jsonify({"error": "No such transaction."}), 404
    before = snapshot(st, txns)
    merged: dict = {}
    done = 0
    one = dict(body, remember=False)        # never a rule for a whole selection
    for i in ids:
        t = by_id[i]
        keys = {c["key"] for c in (marks.OUT_CASES if t.amount > 0 else marks.IN_CASES)}
        if case not in keys:
            continue
        try:
            res = marks.apply(st, t, one, _today())
        except marks.Problem as exc:
            return jsonify({"error": str(exc)}), 400
        for k, v in res["marks"].items():
            merged.setdefault(k, {}).update(v)
        done += 1
    core._reclassify(st)
    after_txns = st.all_transactions()
    undo = undo_payload(before, snapshot(st, after_txns))
    if merged:
        undo["marks"] = merged
    label = next(c["label"] for c in marks.OUT_CASES + marks.IN_CASES if c["key"] == case)
    if case == "spending":
        label = body.get("category") or label
    before_left, after_left = core._safe_left(st, txns), core._safe_left(st, after_txns)
    delta = round(after_left - before_left, 2)
    title = (f"Marked {done} as {label}." if done != 1 else f"Marked as {label}.")
    detail = ("" if abs(delta) < 0.005 else
              f"Allowance is ${abs(delta):,.2f} {'more' if delta > 0 else 'less'}.")
    return jsonify({"ok": True, "ids": ids[:done] if done == len(ids) else ids, "updated": done,
                    "title": title, "detail": detail, "undo": undo})


# ── Tags ─────────────────────────────────────────────────────────────────

@bp.put("/transactions/<txn_id>/tags")
def set_transaction_tags(txn_id: str):
    st = store()
    if st.get_transaction(txn_id) is None:
        return jsonify({"error": "No such transaction."}), 404
    try:
        tags = marks.clean_tags((request.get_json(silent=True) or {}).get("tags"))
    except marks.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    was = st.tags().get(txn_id, [])
    st.set_tags(txn_id, tags)
    return jsonify({"ok": True, "tags": tags, "undo": {"marks": {"tags": {txn_id: was}}}})


@bp.post("/transactions/batch/tags")
def batch_tags():
    body = request.get_json(silent=True) or {}
    ids = body.get("ids")
    if not isinstance(ids, list) or not ids or len(ids) > MAX_BATCH \
            or not all(isinstance(i, str) for i in ids):
        return jsonify({"error": "Choose at least one transaction."}), 400
    try:
        add = marks.clean_tags(body.get("add") or [])
        remove = marks.clean_tags(body.get("remove") or [])
    except marks.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    if not add and not remove:
        return jsonify({"error": "Type a tag."}), 400
    st = store()
    known = {t.fingerprint for t in st.all_transactions()}
    if any(i not in known for i in ids):
        return jsonify({"error": "No such transaction."}), 404
    tags = st.tags()
    was = {i: tags.get(i, []) for i in ids}
    st.tag_rows(ids, add, remove)
    n = len(ids)
    if add:
        title = (f"Tagged {n} {', '.join(add)}." if n > 1 else f"Tagged {', '.join(add)}.")
    else:
        title = f"Took {', '.join(remove)} off {n}." if n > 1 else f"Took {', '.join(remove)} off."
    return jsonify({"ok": True, "ids": ids, "title": title, "detail": "",
                    "undo": {"marks": {"tags": was}}})


@bp.get("/tags")
def list_tags():
    from . import txlist
    rows = core._txlist_rows(store(), everything=True)
    return jsonify({"tags": txlist.tag_totals(rows)})


@bp.put("/tags/<path:tag>")
def rename_tag(tag: str):
    body = request.get_json(silent=True) or {}
    st = store()
    if tag not in {t for tags in st.tags().values() for t in tags}:
        return jsonify({"error": "No such tag."}), 404
    name = body.get("name")
    if name is not None:
        try:
            cleaned = marks.clean_tags([name])
        except marks.Problem as exc:
            return jsonify({"error": str(exc)}), 400
        if not cleaned:
            return jsonify({"error": "Type a name."}), 400
        name = cleaned[0]
    n = st.rename_tag(tag, name)
    return jsonify({"ok": True, "rows": n, "tag": name})


# ── Merchant names ───────────────────────────────────────────────────────

@bp.put("/merchants/name")
def set_merchant_name():
    body = request.get_json(silent=True) or {}
    merchant = " ".join(str(body.get("merchant") or "").split())
    name = " ".join(str(body.get("name") or "").split())[:60]
    if not merchant:
        return jsonify({"error": "Which merchant?"}), 400
    st = store()
    st.set_merchant_name(merchant, name or None)
    return jsonify({"ok": True, "merchant": merchant, "name": name or None})


# ── Hidden categories ────────────────────────────────────────────────────

@bp.put("/rules/categories")
def set_category_hidden():
    body = request.get_json(silent=True) or {}
    try:
        hidden = marks.set_hidden(store(), str(body.get("category") or ""),
                                 bool(body.get("hidden")))
    except marks.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    return jsonify({"ok": True, "hidden": sorted(hidden)})
