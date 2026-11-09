"""Splits and paybacks that hold up (THL-291; finance/parts.py, finance/splits.py).

* POST   /api/transactions/<id>/split/let-go      {name}: let the rest of their part go.
* DELETE /api/transactions/<id>/split/let-go      {name}: put it back.
* POST   /api/transactions/<id>/split/cash        {name, amount, day?, via?, app?, extra?}: paid
                                                  back in cash, or `via: "app"` through another
                                                  app; `extra` says what paid over is (S-11c).
* DELETE /api/transactions/<id>/split/cash/<cid>  forget that cash.
* GET    /api/split/apps                          apps she has named before (SPLIT-14).
* GET    /api/transactions/<id>/cash-matches      cash a deposit could be holding.
* POST   /api/transactions/<id>/parts             {parts, later, replace?, split?}: split a
                                                  deposit into parts.
* POST   /api/transactions/<id>/parts/preview     {parts}: what saving them changes (S-12 v2).
* DELETE /api/transactions/<id>/parts             unlink every part, on the deposit or a part.
* GET    /api/transactions/<id>/owing             what the sender still owes, for a deposit's
                                                  parts, and what its parts already pay back.
* GET    /api/owed                                Owed to you, You owe, paid back this month.
* GET    /api/transactions/<id>/credit            S-35c: a linked payback credited to no one, and
                                                  the open shares it could be (SPLIT-22b).
* POST   /api/transactions/<id>/credit            {person, charge?}: who sent it, with Undo.
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
    paid now; a cash deposit later asks whether it holds this.

    S-11c (SPLIT-19, 2026-11-09): when they paid more than they owe, `extra`
    says what the rest is, in pieces that add up to it: `overpaid` (she owes
    it back), `payback` (another open share, `charge` and `person`), `gift`
    (money in, once, that day) and `returned` (she gave it back). Every
    record shares the payment's origin, so it is listed, deposited and
    undone as the one payment she recorded."""
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
    # SPLIT-14 (S-06 v3): which app, typed; optional, trimmed, up to 30.
    app = " ".join(str(body.get("app") or "").split())[:30] or None if via else None
    pieces = None
    if body.get("extra") is not None:
        pieces, problem = _extra_pieces(st, t, split, p, amount, body.get("extra"))
        if problem:
            return jsonify({"error": problem}), 400
    if pieces is None:
        cid = st.add_split_cash(txn_id, p["name"], amount, day, via, app)
    else:
        cid = _record_extra(st, t, p["name"], amount, day, via, app, pieces)
    title = (f"{p['name']} paid ${amount:,.2f} through {app or 'another app'}." if via
             else f"{p['name']} paid ${amount:,.2f} in cash.")
    return jsonify({"ok": True, "id": cid, "title": title,
                    # The Sorted toast's Undo takes the whole payment back.
                    "undo": {"cash_payment": cid},
                    "detail": core.transaction_detail(txn_id).get_json()}), 201


EXTRA_KINDS = ("overpaid", "payback", "gift", "returned")


def _cents(x) -> int:
    return int(round(float(x) * 100))


def _extra_pieces(st, t, split: dict, p: dict, amount: float, extra) -> tuple[list | None, str | None]:
    """S-11c: the pieces of what they paid over what they owe, checked
    before anything is saved. (pieces, None) or (None, the problem)."""
    txns = st.all_transactions()
    payer = st.payback_people()
    status = next(s for s in sp.people_status(t, split, txns, payer) if s["name"] == p["name"])
    over = _cents(amount) - _cents(status["owes"])
    if over < 1:
        return None, f"{p['name']} didn’t pay more than they owe."
    if not isinstance(extra, list) or not extra or len(extra) > dp.MAX_PARTS:
        return None, f"${over / 100:,.2f} of the extra isn’t said yet."
    by_id = {x.fingerprint: x for x in txns}
    splits = st.splits()
    out, given = [], 0
    for e in extra:
        if not isinstance(e, dict) or e.get("kind") not in EXTRA_KINDS:
            return None, "Say what each piece of the extra is."
        try:
            cents = _cents(e.get("amount"))
        except (TypeError, ValueError):
            return None, "Give each piece of the extra an amount."
        if cents < 1:
            return None, "A piece of the extra has to be more than nothing."
        piece = {"kind": e["kind"], "amount": cents / 100}
        if e["kind"] == "payback":
            # Paying me back: another open share, theirs or anyone's (S-09).
            cid = str(e.get("charge") or "")
            charge, other = by_id.get(cid), splits.get(cid)
            if charge is None or other is None or cid == t.fingerprint:
                return None, "Pick the share it pays back."
            who = _person(other, str(e.get("person") or p["name"]))
            if who is None:
                return None, "They aren’t in that split."
            owes = next((s["owes"] for s in sp.people_status(charge, other, txns, payer)
                         if s["name"] == who["name"]), 0.0)
            if cents > _cents(owes):
                return None, f"That’s more than {who['name']} owes on {charge.merchant}."
            piece.update(charge=cid, person=who["name"])
        given += cents
        out.append(piece)
    if given < over:
        return None, f"${(over - given) / 100:,.2f} of the extra isn’t said yet."
    if given > over:
        return None, f"That’s ${(given - over) / 100:,.2f} more than the extra."
    for kind in ("returned",):
        if sum(1 for x in out if x["kind"] == kind) > 1:
            return None, "Say what each piece of the extra is."
    return out, None


def _record_extra(st, t, name: str, amount: float, day: str, via, app, pieces: list) -> int:
    """The payment and its extra, as records sharing one origin (the first).
    What they owed, plus any they overpaid, stays on this split; a payback
    goes to the share it pays; a gift is money in that day; given back pays
    nobody. Returns the payment's id."""
    over = sum(_cents(x["amount"]) for x in pieces)
    kept = _cents(amount) - over + sum(_cents(x["amount"]) for x in pieces if x["kind"] == "overpaid")
    root = st.add_split_cash(t.fingerprint, name, kept / 100, day, via, app)
    for x in pieces:
        if x["kind"] == "payback":
            st.add_split_cash(x["charge"], x["person"], x["amount"], day, via, app, root)
        elif x["kind"] in ("gift", "returned"):
            cid = st.add_split_cash(t.fingerprint, name, x["amount"], day, via, app, root, x["kind"])
            if x["kind"] == "gift":
                _gift_row(st, cid, root, name, x["amount"], day, via, app)
    core._reclassify(st)
    return root


GIFT_SOURCE = "split_gift"


def _gift_row(st, cash_id: int, root: int, name: str, amount: float, day: str, via, app) -> None:
    """A gift from a cash or app payment's extra (S-11c): money in of kind
    Gift, once, on the payment's day, so income and Allowance count it.
    It is no bank transaction, so Transactions doesn't list it."""
    from .models import Transaction
    how = (app or "Another app") if via == "app" else "Cash"
    row = Transaction(date=day, description=f"A gift · {name} · {how}", merchant=name, amount=-round(amount, 2),
                      account_id="split-cash", account_name=how, category="Income", category_source="user",
                      source=GIFT_SOURCE, seq=cash_id,
                      raw={"split_gift": cash_id, "origin": root, "counterparty": name,
                           "via": via or "cash", "app": app})
    st.add_transactions([row])
    st.set_income_type(row.fingerprint, "gifts", "user")
    st.set_party(row.fingerprint, name)


def remove_payment(st, root: int) -> str | None:
    """Undo (SPLIT-19): the whole payment, by origin: what stayed on the
    split, the paybacks on other shares, the gift and what was given back.
    Returns a problem in words, or None."""
    pieces = [c for c in st.split_cash() if (c.get("origin") or c["id"]) == root]
    if not pieces:
        return "No such cash."
    if any(c["deposit_id"] for c in pieces):
        return "That cash is in a deposit. Unlink the deposit first."
    ids = {c["id"] for c in pieces}
    for x in st.all_transactions():
        if x.source == GIFT_SOURCE and (x.raw or {}).get("split_gift") in ids:
            st.delete_transaction(x.fingerprint)
    for i in ids:
        st.remove_split_cash(i)
    return None


@bp.get("/split/apps")
def split_apps():
    """S-06 v3 "Used before" (SPLIT-14): the apps she has named, newest
    first, up to 4. Her own data; no app names are built in."""
    return jsonify({"apps": store().split_apps()})


@bp.delete("/transactions/<txn_id>/split/cash/<int:cash_id>")
def split_cash_undo(txn_id: str, cash_id: int):
    st = store()
    cash = next((c for c in st.split_cash() if c["id"] == cash_id and c["txn_id"] == txn_id), None)
    if cash is None:
        return jsonify({"error": "No such cash."}), 404
    if cash["deposit_id"]:
        return jsonify({"error": "That cash is in a deposit. Unlink the deposit first."}), 400
    if cash.get("origin"):
        st.remove_split_cash(cash_id)
    else:
        # SPLIT-19: the payment itself goes with every piece of its extra.
        problem = remove_payment(st, cash_id)
        if problem:
            return jsonify({"error": problem}), 400
        core._reclassify(st)
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
    every = st.split_cash()
    # SPLIT-15: what the whole payment was, so a remainder reads "$50.00
    # left of $250.00 cash", never as a payment of its own.
    whole: dict[int, float] = {}
    for c in every:
        root = c.get("origin") or c["id"]
        whole[root] = round(whole.get(root, 0.0) + c["amount"], 2)
    # What was given back (SPLIT-19) was never hers to deposit.
    whole = {k: round(v - sum(c["amount"] for c in every
                              if (c.get("origin") or c["id"]) == k and c.get("kind") == "returned"), 2)
             for k, v in whole.items()}
    free = [c for c in every if not c["deposit_id"] and c["day"] <= t.date[:10]
            and c.get("via") != "app" and c.get("kind") != "returned"]
    # SPLIT-19 (S-11c): one payment is one row, "Sam · $60.00 cash · Nov 13",
    # whatever its extra paid: every piece no deposit holds yet, first one first.
    groups: dict[int, list[dict]] = {}
    for c in free:
        groups.setdefault(c.get("origin") or c["id"], []).append(c)
    rows = []
    for root, pieces in groups.items():
        pieces.sort(key=lambda c: (c.get("kind") is not None, c["id"]))
        first = pieces[0]
        rows.append({"first": first, "ids": [c["id"] for c in pieces], "root": root,
                     "amount": round(sum(c["amount"] for c in pieces), 2)})
    rows.sort(key=lambda r: (r["amount"] > got + 0.005, abs(r["amount"] - got), r["first"]["day"]))
    out = []
    for r in rows:
        c = by_id.get(r["first"]["txn_id"])
        row = {"id": r["first"]["id"], "name": r["first"]["name"], "amount": r["amount"],
               "day": r["first"]["day"], "merchant": c.merchant if c else ""}
        if len(r["ids"]) > 1:
            row["ids"] = r["ids"]
        of = whole.get(r["root"], r["amount"])
        if of > r["amount"] + 0.005:
            row["of"] = of
        out.append(row)
    return jsonify({"cash": out})


@bp.post("/transactions/<txn_id>/parts")
def split_into_parts(txn_id: str):
    """S-10 to S-12, S-27, S-28, S-36: a deposit split into parts."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    return save_parts(st, t, _body())


def save_parts(st, t, body: dict):
    """POST …/parts, and the web's What was this? on S-21xm (THL-301)."""
    txn_id = t.fingerprint
    kept = 0
    if body.get("extra"):
        # S-11xm (THL-301): the answer is for the extra part only.
        body = dict(body)
        given = body.get("parts")
        body["parts"], problem = extra_parts(st, t, given)
        if problem:
            return jsonify({"error": problem}), 400
        kept = len(body["parts"]) - len(given)
    # S-24 held (SPLIT-07, 2026-11-09): the purchase to split with the
    # sender is split in this same save, so leaving halfway splits nothing.
    held, problem = _held_split(st, body.get("split"))
    if problem:
        return jsonify({"error": problem}), 400
    was = None
    # SPLIT-22b (S-35c, extra to S-11 v2): a payback already linked becomes
    # parts, so its Undo links it back as it was, not just unlinked.
    linked_was = ({"paybacks": {txn_id: {"charge": t.repays, "kind": st.payback_kinds().get(txn_id),
                                         "person": st.payback_people().get(txn_id),
                                         "amount": t.repays_amount}},
                   "payback_more": {txn_id: st.payback_more(txn_id)}}
                  if t.repays and not st.parts().get(txn_id) else None)
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
    if kept:
        # The toast counts her answer, not the credit it kept (S-11xm).
        n = len(out["parts"]) - kept - (1 if out["rest"] else 0)
        out["title"] = (f"Sorted {n} part{'' if n == 1 else 's'}. {dp._money(out['rest'])} left to sort."
                        if out["rest"] else f"Sorted into {n} part{'' if n == 1 else 's'}.")
    if held:
        # One Undo puts the parts, the link and the split back (S-12d).
        undo["marks"] = {"splits": {held[0].fingerprint: was}}
        out["title"] = f"{held[0].merchant} split and ${round(-t.amount):,} sorted"
    if linked_was:
        undo["marks"] = {**(undo.get("marks") or {}), **linked_was}
    return jsonify({"ok": True, **out, "undo": undo})


def extra_parts(st, t, given) -> tuple[list | None, str | None]:
    """S-11xm (THL-301, SPLIT-24): a payback over several purchases that's
    extra on only some of them. Her answer covers the extra part; what was
    credited stays a payback, to the same purchase and person, so saving
    takes the money off Loblaws and leaves Jo's $30.00 on Pizza Nova as it
    was. Returns every part to save, or the problem in her words."""
    q = sp.extra_question(t, st.all_transactions(), st.splits(), st.payback_people())
    if q is None:
        return None, "That’s been answered already. Pull to refresh."
    if not isinstance(given, list):
        return None, "Add a part."
    kept = [{"kind": "payback", "amount": c["amount"], "charge": c["id"], "person": c["person"]}
            for c in q.get("credited") or []]
    try:
        said = sum(_cents(p.get("amount")) for p in given if isinstance(p, dict))
    except (TypeError, ValueError):
        return None, "Give each part an amount."
    if said > _cents(q["amount"]):
        # S-11xm over (1043:1194): the line the app shows, in the same words.
        return None, (f"Only ${q['amount']:,.2f} of this is extra. {_credited_line(q)} stays as it is, "
                      f"so make it ${q['amount']:,.2f} or less.")
    return kept + given, None


def _credited_line(q: dict) -> str:
    """"Jo’s $30.00 for Pizza Nova"; "Jo’s $30.00 for Pizza Nova and Costco"."""
    by: dict[str, list[dict]] = {}
    for c in q.get("credited") or []:
        by.setdefault(c["person"], []).append(c)
    return " and ".join(
        f"{p.split()[0] if p else 'Their'}’s "
        f"${sum(_cents(c['amount']) for c in cs) / 100:,.2f} for {sp.and_list([c['merchant'] for c in cs])}"
        for p, cs in by.items())


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
        if kind in ("payback", "refund", "reimbursement"):
            charge = by_id.get(str(p.get("charge") or ""))
            # A work expense left out until it's reimbursed isn't spending.
            if charge is None or charge.excluded:
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
    # S-35b (THL-181, SPLIT-21): the name on a deposit from someone who isn't
    # on any of her splits, for "Jordan isn't on any of your splits, and no
    # one owes $45.00."; None when it names no one, or someone who is.
    named = None
    if not mine:
        from .etransfers import known_people, party as etransfer_party
        everyone = [q["name"] for s in splits.values() for q in s.get("people") or []]
        name = t.party or (etransfer_party(t, known_people(list(txns.values()), splits,
                                                           st.payback_people())) or {}).get("name")
        if name and not any(sp.same_person(n, name) for n in everyone):
            named = name
    return jsonify({"from": mine[0]["name"] if mine else None, "named": named, "items": items,
                    "linked": linked})


# ── Who sent this? (SPLIT-22b, THL-181; S-05u, S-35c, S-21u) ─────────────

@bp.get("/transactions/<txn_id>/credit")
def credit_question(txn_id: str):
    """S-35c: a payback already linked (from search, the web's Paid back or
    the API) that the ask rule credited to no one, with the open shares on
    the purchases it pays back. `question` is None when there's nothing to ask."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    return jsonify({"question": sp.credit_question(t, st.all_transactions(), st.splits(),
                                                   st.payback_people())})


@bp.post("/transactions/<txn_id>/credit")
def credit_payback(txn_id: str):
    """S-35c Save: say who sent a payback already linked. Only who it was
    changes; the link and how much went to each purchase stay. One request,
    with Undo ("Sam paid back $30.00 · Undo")."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if t.amount >= 0 or not t.repays:
        return jsonify({"error": "That money isn’t linked to a purchase."}), 400
    body = _body()
    asked = " ".join(str(body.get("person") or "").split())
    if not asked:
        return jsonify({"error": "Tick who sent it."}), 400
    charges = t.repays_all
    if body.get("charge") is not None:
        if body["charge"] not in charges:
            return jsonify({"error": "That money didn’t pay back that purchase."}), 400
        charges = [body["charge"]]
    splits = st.splits()
    name = next((p["name"] for cid in charges for p in (splits.get(cid) or {}).get("people", [])
                 if p["name"] == asked), None) or next(
        (p["name"] for cid in charges for p in (splits.get(cid) or {}).get("people", [])
         if sp.same_person(p["name"], asked)), None)
    if name is None:
        return jsonify({"error": "That person isn’t on a purchase this paid back."}), 400
    txns = st.all_transactions()
    by_id = {x.fingerprint: x for x in txns}

    def paid() -> float:
        payer = st.payback_people()
        total = 0.0
        for cid in t.repays_all:
            if cid in splits and cid in by_id:
                total += sum(p["paid"] for p in sp.people_status(by_id[cid], splits[cid], txns, payer)
                             if p["name"] == name)
        return round(total, 2)

    before = paid()
    was = st.payback_people().get(txn_id)
    st.set_payback_person(txn_id, name)
    got = round(paid() - before, 2)
    title = f"{name} paid back ${got:,.2f}" if got >= 0.005 else f"Sent by {name}."
    return jsonify({"ok": True, "title": title, "credited": got,
                    "undo": {"marks": {"payback_person": {txn_id: was}}}})
