"""Splits and paybacks that hold up (THL-291; finance/parts.py, finance/splits.py).

* POST   /api/transactions/<id>/split/let-go      {name}: let the rest of their part go.
* DELETE /api/transactions/<id>/split/let-go      {name}: put it back.
* POST   /api/transactions/<id>/split/cash        {name, amount, day?}: paid back in cash.
* DELETE /api/transactions/<id>/split/cash/<cid>  forget that cash.
* GET    /api/transactions/<id>/cash-matches      cash a deposit could be holding.
* POST   /api/transactions/<id>/parts             {parts, later}: split a deposit into parts.
* DELETE /api/transactions/<id>/parts             unlink every part, on the deposit or a part.
* GET    /api/transactions/<id>/owing             what the sender still owes, for a deposit's parts.
* GET    /api/owed                                Owed to you, You owe, paid back this month.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import parts as dp
from . import splits as sp
from .api import bp, store


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _body() -> dict:
    return request.get_json(silent=True) or {}


def _split_or_error(st, txn_id: str):
    t = st.get_transaction(txn_id)
    split = st.splits().get(txn_id)
    if t is None or split is None:
        return None, None, (jsonify({"error": "This purchase isn’t split."}), 404)
    return t, split, None


def _person(split: dict, name: str) -> dict | None:
    return next((p for p in split["people"] if p["name"] == name or sp.same_person(p["name"], name)),
                None)


def _reshare(st, t, split: dict) -> None:
    """Write the split back and her share with it."""
    people = [{"name": p["name"], "amount": p["amount"]} for p in split["people"]]
    st.set_split(t.fingerprint, split["mode"], people, split["watch"])
    st.set_share(t.fingerprint, sp.your_part(t, people))


@bp.post("/transactions/<txn_id>/split/let-go")
def split_let_go(txn_id: str):
    """S-08 / S-20: what they still owe becomes hers. Their part shrinks to
    what they've paid, so her share (and her spending) grows by the rest."""
    st = store()
    t, split, err = _split_or_error(st, txn_id)
    if err:
        return err
    p = _person(split, str(_body().get("name") or ""))
    if p is None:
        return jsonify({"error": "They aren’t in this split."}), 404
    status = next(s for s in sp.people_status(t, split, st.all_transactions(), st.payback_people())
                  if s["name"] == p["name"])
    if status["owes"] < 0.005:
        return jsonify({"error": f"{p['name']} doesn’t owe anything on this."}), 400
    st.set_let_go(txn_id, p["name"], p["amount"], _today().isoformat())
    p["amount"] = round(status["paid"], 2)
    _reshare(st, t, split)
    core._reclassify(st)
    return jsonify({"ok": True, "title": f"Let it go. {p['name']}’s ${status['owes']:,.2f} is yours now.",
                    "detail": core.transaction_detail(txn_id).get_json()})


@bp.delete("/transactions/<txn_id>/split/let-go")
def split_let_go_undo(txn_id: str):
    st = store()
    t, split, err = _split_or_error(st, txn_id)
    if err:
        return err
    p = _person(split, str(_body().get("name") or request.args.get("name") or ""))
    if p is None or not p.get("let_go"):
        return jsonify({"error": "Nothing was let go."}), 404
    p["amount"] = p["let_go"]["was"]
    st.clear_let_go(txn_id, p["name"])
    _reshare(st, t, split)
    core._reclassify(st)
    return jsonify({"ok": True, "title": f"{p['name']} owes you again.",
                    "detail": core.transaction_detail(txn_id).get_json()})


@bp.post("/transactions/<txn_id>/split/cash")
def split_cash(txn_id: str):
    """S-06 Cash in hand: paid back with no bank transaction. It counts as
    paid now; a cash deposit later asks whether it holds this."""
    st = store()
    t, split, err = _split_or_error(st, txn_id)
    if err:
        return err
    body = _body()
    p = _person(split, str(body.get("name") or ""))
    if p is None:
        return jsonify({"error": "They aren’t in this split."}), 404
    try:
        amount = round(float(body.get("amount")), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "How much did they pay?"}), 400
    if amount < 0.01:
        return jsonify({"error": "How much did they pay?"}), 400
    day = str(body.get("day") or _today().isoformat())[:10]
    try:
        date.fromisoformat(day)
    except ValueError:
        return jsonify({"error": "When did they pay?"}), 400
    cid = st.add_split_cash(txn_id, p["name"], amount, day)
    return jsonify({"ok": True, "id": cid, "title": f"{p['name']} paid ${amount:,.2f} in cash.",
                    "detail": core.transaction_detail(txn_id).get_json()}), 201


@bp.delete("/transactions/<txn_id>/split/cash/<int:cash_id>")
def split_cash_undo(txn_id: str, cash_id: int):
    st = store()
    cash = next((c for c in st.split_cash() if c["id"] == cash_id and c["txn_id"] == txn_id), None)
    if cash is None:
        return jsonify({"error": "No such cash."}), 404
    if cash["deposit_id"]:
        return jsonify({"error": "That cash is in a deposit. Unlink the deposit first."}), 400
    st.remove_split_cash(cash_id)
    return jsonify({"ok": True, "detail": core.transaction_detail(txn_id).get_json()})


@bp.get("/transactions/<txn_id>/cash-matches")
def cash_matches(txn_id: str):
    """S-13 Is this cash you were paid?: cash she marked as paid back that
    no deposit holds yet, from before this one, closest amount first."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None or t.amount >= 0:
        return jsonify({"cash": []})
    by_id = {x.fingerprint: x for x in st.all_transactions()}
    got = -t.amount
    rows = [c for c in st.split_cash() if not c["deposit_id"] and c["day"] <= t.date[:10]]
    rows.sort(key=lambda c: (c["amount"] > got + 0.005, abs(c["amount"] - got), c["day"]))
    return jsonify({"cash": [{"id": c["id"], "name": c["name"], "amount": c["amount"], "day": c["day"],
                              "merchant": (by_id.get(c["txn_id"]).merchant if by_id.get(c["txn_id"]) else "")}
                             for c in rows]})


@bp.post("/transactions/<txn_id>/parts")
def split_into_parts(txn_id: str):
    """S-10 to S-12, S-27, S-28, S-36: a deposit split into parts."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    body = _body()
    try:
        out = dp.apply(st, t, body.get("parts"), bool(body.get("later")))
    except dp.Problem as exc:
        return jsonify({"error": str(exc)}), 400
    core._reclassify(st)
    return jsonify({"ok": True, **out, "undo": {"parts": txn_id}})


@bp.delete("/transactions/<txn_id>/parts")
def unlink_parts(txn_id: str):
    """S-34 Unlink?: every part goes, from the deposit or from any part."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    deposit = (t.raw or {}).get("part_of") if not st.parts().get(txn_id) else txn_id
    if not deposit or not st.parts().get(deposit):
        return jsonify({"error": "This isn’t in parts."}), 404
    n = dp.undo(st, deposit)
    core._reclassify(st)
    return jsonify({"ok": True, "id": deposit, "removed": n, "title": "Unlinked. It’s one deposit again."})


@bp.get("/owed")
def owed_to_you():
    st = store()
    return jsonify(dp.owed(st, st.all_transactions(), _today()))


@bp.get("/transactions/<txn_id>/owing")
def owing(txn_id: str):
    """S-09 What did this pay back?: the purchases whoever sent this deposit
    still owes on, their share first; then everyone else's, for a deposit
    from someone Pearl doesn't know by that name."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None or t.amount >= 0:
        return jsonify({"from": None, "items": []})
    sender = t.party or t.merchant or ""
    rows = dp.owed(st, st.all_transactions(), _today())["owes_you"]
    mine = [r for r in rows if sp.same_person(r["name"], sender)]
    rest = [r for r in rows if r not in mine]
    items = [{"id": i["charge_id"], "merchant": i["merchant"], "date": i["date"], "owes": i["owes"],
              "share": i["amount"], "paid": i["paid"], "person": r["name"], "theirs": r in mine}
             for r in mine + rest for i in r["items"]]
    return jsonify({"from": mine[0]["name"] if mine else None, "items": items})
