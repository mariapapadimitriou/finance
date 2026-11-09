"""Splits and paybacks that hold up (THL-291; finance/parts.py, finance/splits.py).

* POST   /api/transactions/<id>/split/let-go      {name}: let the rest of their part go.
* DELETE /api/transactions/<id>/split/let-go      {name}: put it back.
* POST   /api/transactions/<id>/split/cash        {name, amount, day?, via?}: paid back in
                                                  cash, or `via: "app"` through another app.
* DELETE /api/transactions/<id>/split/cash/<cid>  forget that cash.
* GET    /api/transactions/<id>/cash-matches      cash a deposit could be holding.
* POST   /api/transactions/<id>/parts             {parts, later, replace?, split?}: split a
                                                  deposit into parts.
* POST   /api/transactions/<id>/parts/preview     {parts}: what saving them changes (S-12 v2).
* DELETE /api/transactions/<id>/parts             unlink every part, on the deposit or a part.
* GET    /api/transactions/<id>/owing             what the sender still owes, for a deposit's
                                                  parts, and what its parts already pay back.
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
    people = [{"name": p["name"], "amount": p["amount"], "weight": p.get("weight")}
              for p in split["people"]]
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
    # Another app (SPLIT-11): paid, but no deposit ever holds it.
    via = "app" if body.get("via") == "app" else None
    cid = st.add_split_cash(txn_id, p["name"], amount, day, via)
    title = (f"{p['name']} paid ${amount:,.2f} through another app." if via
             else f"{p['name']} paid ${amount:,.2f} in cash.")
    return jsonify({"ok": True, "id": cid, "title": title,
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
    rows = [c for c in st.split_cash() if not c["deposit_id"] and c["day"] <= t.date[:10]
            and c.get("via") != "app"]
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
    # S-24 held (SPLIT-07, 2026-11-09): the purchase to split with the
    # sender is split in this same save, so leaving halfway splits nothing.
    held, problem = _held_split(st, body.get("split"))
    if problem:
        return jsonify({"error": problem}), 400
    was = None
    if held:
        charge, mode, people, watch = held
        was = {"split": st.splits().get(charge.fingerprint),
               "share": charge.my_share if charge.share_set else None}
        st.set_split(charge.fingerprint, mode, people, watch)
        st.set_share(charge.fingerprint, sp.your_part(charge, people))
    try:
        out = dp.apply(st, t, body.get("parts"), bool(body.get("later")), bool(body.get("replace")))
    except dp.Problem as exc:
        if held:
            from .marks import undo_marks
            undo_marks(st, {"splits": {held[0].fingerprint: was}})
        return jsonify({"error": str(exc)}), 400
    core._reclassify(st)
    undo: dict = {"parts": txn_id}
    if held:
        # One Undo puts the parts, the link and the split back (S-12d).
        undo["marks"] = {"splits": {held[0].fingerprint: was}}
        out["title"] = f"{held[0].merchant} split and ${round(-t.amount):,} sorted"
    return jsonify({"ok": True, **out, "undo": undo})


def _held_split(st, ask):
    """The split asked for with a deposit's parts: (charge, mode, people,
    watch), or a problem in words, checked before anything changes."""
    if not ask:
        return None, None
    if not isinstance(ask, dict):
        return None, "Say how to split it."
    charge = st.get_transaction(str(ask.get("charge") or ""))
    if charge is None:
        return None, "No such transaction."
    if charge.amount <= 0 or charge.repays:
        return None, "Only a charge can be split."
    if charge.joint:
        return None, "On a joint account, say whose it was instead."
    mode = ask.get("mode")
    people, problem = sp.validate(charge, mode, ask.get("people"), ask.get("you"),
                                  ask.get("include_me", True) is not False)
    if problem:
        return None, problem
    return (charge, mode, people, bool(ask.get("watch", True))), None


@bp.post("/transactions/<txn_id>/parts/preview")
def parts_preview(txn_id: str):
    """S-12 v2 WHAT CHANGES (SPLIT-09): what saving these parts does,
    month by month, without saving them. A payback lowers the purchase it
    pays back in that purchase's month; gift, income and overpaid land in
    the deposit's month, as Allowance."""
    from calendar import month_name
    from . import txlist
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    parts = _body().get("parts")
    if not isinstance(parts, list):
        return jsonify({"error": "Add a part."}), 400

    def label(month: str) -> str:
        return month_name[int(month[5:7])]

    rows = core._txlist_rows(st)
    by_id = {x.fingerprint: x for x, _ in rows}
    spent: dict[str, dict[str, float]] = {}

    def spend(month: str) -> dict[str, float]:
        if month not in spent:
            spent[month] = {g["category"]: g["spent"]
                            for g in txlist.by_category(txlist.select(rows, month=month))}
        return spent[month]

    lowers: dict[tuple[str, str], float] = {}
    allowance = 0.0
    for p in parts:
        if not isinstance(p, dict):
            continue
        try:
            amount = round(float(p.get("amount")), 2)
        except (TypeError, ValueError):
            continue
        kind = p.get("kind")
        if kind in ("payback", "refund"):
            charge = by_id.get(str(p.get("charge") or ""))
            if charge is None:
                continue
            key = (charge.date[:7], charge.category or "Other")
            lowers[key] = round(lowers.get(key, 0.0) + amount, 2)
        elif kind in ("gift", "income", "overpaid"):
            allowance = round(allowance + amount, 2)
    changes = []
    if allowance >= 0.005:
        changes.append({"label": f"Allowance · {label(t.date[:7])}", "delta": allowance})
    for (month, cat), amount in lowers.items():
        before = round(spend(month).get(cat, 0.0), 2)
        changes.append({"label": f"{cat} · {label(month)}", "before": before,
                        "after": round(before - amount, 2)})
    return jsonify({"changes": changes})


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
    txns = {x.fingerprint: x for x in st.all_transactions()}
    # S-32 (2026-11-04): a purchase that hasn't posted yet says so.
    items = [{"id": i["charge_id"], "merchant": i["merchant"], "date": i["date"], "owes": i["owes"],
              "share": i["amount"], "paid": i["paid"], "person": r["name"], "theirs": r in mine,
              "pending": bool(((getattr(txns.get(i["charge_id"]), "raw", None)) or {}).get("pending"))}
             for r in mine + rest for i in r["items"]]
    # S-10e (SPLIT-03): what this deposit's parts already pay back, so
    # Edit lists them ticked even though nobody owes on them any more.
    splits = st.splits()
    linked = []
    for p in st.parts().get(txn_id) or []:
        if p["kind"] != "payback":
            continue
        charge = txns.get(p["detail"].get("charge") or "")
        if charge is None:
            continue
        person = p["detail"].get("person")
        share = next((q["amount"] for q in (splits.get(charge.fingerprint) or {}).get("people", [])
                      if person and sp.same_person(q["name"], person)), None)
        linked.append({"id": charge.fingerprint, "merchant": charge.merchant, "date": charge.date[:10],
                       "amount": p["amount"], "person": person, "share": share})
    return jsonify({"from": mine[0]["name"] if mine else None, "items": items, "linked": linked})
