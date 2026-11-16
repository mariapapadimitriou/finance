"""Splits and paybacks that hold up (THL-291; finance/parts.py, finance/splits.py).

* POST   /api/transactions/<id>/split/let-go      {name}: let the rest of their part go.
* DELETE /api/transactions/<id>/split/let-go      {name}: put it back.
* POST   /api/transactions/<id>/split/cash        {name, amount, day?, via?, app?, extra?}: paid
                                                  back in cash, or `via: "app"` through another
                                                  app; `extra` says what paid over is (S-11c).
* DELETE /api/transactions/<id>/split/cash/<cid>  unlink that payment from this purchase, with Undo.
* GET    /api/split/apps                          apps she has named before (SPLIT-14).
* GET    /api/transactions/<id>/cash-matches      cash a deposit could be holding.
* POST   /api/transactions/<id>/parts             {parts, later, replace?, split?}: split a
                                                  deposit into parts. A payback part with
                                                  `let_go` lets the rest of that person's
                                                  share go once it's linked (PB-13b).
* POST   /api/transactions/<id>/parts/preview     {parts}: what saving them changes (S-12 v2).
* DELETE /api/transactions/<id>/parts             unlink every part, on the deposit or a part.
* GET    /api/transactions/<id>/owing             what the sender still owes, for a deposit's
                                                  parts, and what its parts already pay back.
* GET    /api/owed                                Owed to you, You owe, paid back this month.
* GET    /api/transactions/<id>/credit            S-35c: a linked payback credited to no one, and
                                                  the open shares it could be (SPLIT-22b).
* POST   /api/transactions/<id>/credit            {person, charge?}: who sent it, with Undo.
* GET    /api/transactions/<id>/paid-back-candidates  ?person=: money in that could be their
                                                  payback on this purchase, and how each would
                                                  split into part or all. Read-only.
* POST   /api/transactions/<id>/paid-back         {deposit, person, amount?, let_go?}: link from
                                                  the purchase side, through save_parts.
* GET    /api/transactions/<id>/paid-back-find    ?q=: PB-22 "What paid back your share?":
                                                  LIKELY money in, or a search by name or
                                                  amount, with why each matches. Read-only.
* POST   /api/transactions/<id>/paid-back-take    {deposit, take?}: PB-24, a deposit already
                                                  paying back another purchase; its free part,
                                                  or with `take` more from the other, with Undo.
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


def _gifts_on(st, charge_id: str, name: str) -> list[tuple[str, int, int]]:
    """TEST-18b: deposits whose parts pay this person's share here with a
    gift beside it: (deposit id, gift cents, payback cents)."""
    out = []
    for deposit, parts in st.parts().items():
        mine = [x for x in parts if x["kind"] == "payback" and (x.get("detail") or {}).get("charge") == charge_id
                and sp.same_person((x.get("detail") or {}).get("person") or "", name)]
        gift = [x for x in parts if x["kind"] == "gift"]
        if mine and gift:
            out.append((deposit, sum(sp._cents(x["amount"]) for x in gift),
                        sum(sp._cents(x["amount"]) for x in mine)))
    return out


def extra_gift(st, charge_id: str, name: str) -> float:
    """What of this person's money on this purchase she called a gift."""
    bank = sum(g for _, g, _ in _gifts_on(st, charge_id, name))
    cash = sum(sp._cents(c["amount"]) for c in st.split_cash()
               if c["txn_id"] == charge_id and sp.same_person(c["name"], name) and c.get("kind") == "gift")
    return (bank + cash) / 100


@bp.post("/transactions/<txn_id>/split/answer")
def split_answer(txn_id: str):
    """S-48e (TEST-18b, approved section 19): change what she answered for a
    payer after settling. `answer` is "ask" (they owe the rest; for one who
    paid less), "share" (their share is what they sent; the difference is
    spread over her and the others), "owe" (she owes them the extra) or
    "gift" (the extra is a gift, a part on the deposit). Any gift she had
    said before comes off first, so the money is theirs again to answer."""
    st = store()
    t, split, err = _split_or_error(st, txn_id)
    if err:
        return err
    if split["mode"] == sp.UNSURE:
        return jsonify({"error": "Settle it first."}), 400
    body = _body()
    p = _person(split, str(body.get("name") or ""))
    if p is None:
        return jsonify({"error": "They aren’t in this split."}), 404
    answer = body.get("answer")
    if answer not in ("ask", "share", "owe", "gift"):
        return jsonify({"error": "Ask, their share, you owe them, or a gift?"}), 400
    name = p["name"]
    if any(c["txn_id"] == txn_id and sp.same_person(c["name"], name) and c.get("kind") == "gift"
           for c in st.split_cash()):
        # A cash gift is part of the payment record; Unlink and mark it again.
        return jsonify({"error": f"{possessive(name)} gift was cash. Unlink the payment to change it."}), 400
    gifts = _gifts_on(st, txn_id, name)
    for deposit, gift, payback in gifts:
        dp.undo(st, deposit)
        st.link_payback(txn_id, deposit, name, amount=(gift + payback) / 100)
    if gifts:
        core._reclassify(st)
    split = st.splits()[txn_id]
    p = _person(split, name)
    status = next(s for s in sp.people_status(t, split, st.all_transactions(), st.payback_people())
                  if s["name"] == name)
    sent, share = sp._cents(status["paid"]), sp._cents(p["amount"])
    if sent < 1:
        return jsonify({"error": f"{name} hasn’t paid anything yet."}), 400
    if answer == "share" and sent != share:
        # The difference goes to her and the others (S-48a: "spread over
        # you and Priya"; S-48b: "you and Sam carry less").
        others = [q for q in split["people"] if q is not p]
        rows = len(others) + (1 if split.get("me", True) else 0)
        delta = share - sent
        each, odd = divmod(abs(delta), max(rows, 1))
        sign = 1 if delta > 0 else -1
        # More to carry: the odd cent goes to the others first, so someone
        # who sent that much comes out matching (Priya's $40.00). Less to
        # carry: the odd cent comes off her, who had the extra cent.
        lead = odd if sign > 0 or rows == len(others) else 0
        for i, q in enumerate(others):
            q["amount"] = round(q["amount"] + sign * (each + (1 if i < lead else 0)) / 100, 2)
        p["amount"] = round(sent / 100, 2)
        if any(q["amount"] < 0 for q in split["people"]):
            return jsonify({"error": "That would leave someone below nothing."}), 400
    elif answer == "ask" and sent >= share:
        return jsonify({"error": f"{name} didn’t pay less than their share."}), 400
    elif answer in ("owe", "gift") and sent <= share:
        return jsonify({"error": f"{name} didn’t pay more than their share."}), 400
    _reshare(st, t, split)
    if answer == "gift":
        core._settle_extra(st, txn_id, {name: [{"kind": "gift", "amount": round((sent - share) / 100, 2)}]})
    core._reclassify(st)
    words = {"ask": f"{name} owes you ${(share - sent) / 100:,.2f}",
             "share": f"{possessive(name)} share is ${sent / 100:,.2f}",
             "owe": f"You owe {name} ${(sent - share) / 100:,.2f}",
             "gift": f"${(sent - share) / 100:,.2f} from {name} is a gift"}[answer]
    return jsonify({"ok": True, "toast": words, "detail": core.transaction_detail(txn_id).get_json()})


def possessive(name: str) -> str:
    return f"{name}’" if name.lower().endswith("s") else f"{name}’s"


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
    # REFRESH-02 (S-44c): the toast, whose Undo is the DELETE below.
    return jsonify({"ok": True, "title": f"Let it go. {p['name']}’s ${status['owes']:,.2f} is yours now.",
                    "toast": f"Let go · ${status['owes']:,.2f}",
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
    paid = next((s["paid"] for s in sp.people_status(t, split, st.all_transactions(), st.payback_people())
                 if s["name"] == p["name"]), 0.0)
    owes = max(0.0, p["let_go"]["was"] - paid)
    p["amount"] = p["let_go"]["was"]
    st.clear_let_go(txn_id, p["name"])
    _reshare(st, t, split)
    core._reclassify(st)
    # REFRESH-02 (S-44e): "Alex owes you $30.00 again"; its Undo is the POST.
    return jsonify({"ok": True, "title": f"{p['name']} owes you again.",
                    "toast": f"{p['name']} owes you ${owes:,.2f} again",
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
    """Unlink a cash or app payment from this purchase (SPLIT-25, S-34k).
    `cash_id` is the payment (any of its records). Only this purchase's
    piece goes; cash a deposit holds comes out of the deposit, which is left
    with "$x left to sort". Returns the toast's `title` and its `undo`."""
    from . import unlink as ul
    st = store()
    cash = next((c for c in st.split_cash() if c["id"] == cash_id), None)
    if cash is None:
        return jsonify({"error": "No such cash."}), 404
    root = int(cash.get("origin") or cash["id"])
    name = next((c["name"] for c in st.split_cash() if int(c.get("origin") or c["id"]) == root
                 and c["txn_id"] == txn_id and c.get("kind") is None), None)
    marks, problem = ul.unlink_cash(st, txn_id, root)
    if problem:
        return jsonify({"error": problem}), 404
    core._reclassify(st)
    owes = core._owes_now(st, txn_id, name)
    title = f"Unlinked · {name} owes ${owes:,.2f}" if name and owes is not None else "Unlinked"
    return jsonify({"ok": True, "title": title, "undo": {"rows": [], "marks": marks},
                    "detail": core.transaction_detail(txn_id).get_json()})


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
    # PB-13b (Paid back, approved 2026-11-15): "All of it" when this money is
    # less than their share; Let it go marks them paid in full once it's linked.
    letting, problem = _let_go_asks(st, body.get("parts"))
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
        if charge.joint:
            was["joint_part"] = st.joint_parts().get(charge.fingerprint)
            if was["split"] is None and charge.share_set:
                st.set_joint_part(charge.fingerprint, charge.joint_part)
        st.set_split(charge.fingerprint, mode, people, watch)
        st.set_share(charge.fingerprint, None if mode == sp.UNSURE
                     else sp.your_part(charge, people, sp.split_base(charge) if charge.joint else None))
    try:
        out = dp.apply(st, t, body.get("parts"), bool(body.get("later")), bool(body.get("replace")))
    except dp.Problem as exc:
        if held:
            from .marks import undo_marks
            undo_marks(st, {"splits": {held[0].fingerprint: was}})
        return jsonify({"error": str(exc)}), 400
    let_marks, let_total = _let_go_after(st, letting)
    core._reclassify(st)
    undo: dict = {"parts": txn_id}
    if let_marks:
        # One Undo: the parts go, and what they owed is theirs again.
        undo["marks"] = let_marks
    person_title = None if (kept or held or out.get("rest")) else _paid_back_title(body.get("parts"), let_total)
    if person_title:
        out["title"] = person_title
    if kept:
        # The toast counts her answer, not the credit it kept (S-11xm).
        n = len(out["parts"]) - kept - (1 if out["rest"] else 0)
        out["title"] = (f"Sorted {n} part{'' if n == 1 else 's'}. {dp._money(out['rest'])} left to sort."
                        if out["rest"] else f"Sorted into {n} part{'' if n == 1 else 's'}.")
    if held:
        # One Undo puts the parts, the link and the split back (S-12d).
        marks = undo.get("marks") or {}
        undo["marks"] = {**marks, "splits": {**(marks.get("splits") or {}), held[0].fingerprint: was}}
        out["title"] = f"{held[0].merchant} split and ${round(-t.amount):,} sorted"
    if linked_was:
        undo["marks"] = {**(undo.get("marks") or {}), **linked_was}
    if out.get("reopened"):
        # SPLIT-C decision 4: Undo closes the split it opened again.
        undo["marks"] = {**(undo.get("marks") or {}), "split_closed": out.pop("reopened")}
    return jsonify({"ok": True, **out, "undo": undo})


def _let_go_asks(st, parts) -> tuple[list[tuple[str, str]], str | None]:
    """PB-13b: the payback parts that say `let_go`, as (purchase, person on
    its split), checked before anything is saved. A share can only be let go
    on a split with amounts, by someone on it."""
    out: list[tuple[str, str]] = []
    if not isinstance(parts, list):
        return out, None
    splits = st.splits()
    for p in parts:
        if not isinstance(p, dict) or not p.get("let_go"):
            continue
        if p.get("kind") != "payback":
            return [], "Only a payback can let the rest go."
        cid = str(p.get("charge") or "")
        split = splits.get(cid)
        if not split or split.get("mode") == sp.UNSURE:
            return [], "Pick someone on this split."
        who = _person(split, " ".join(str(p.get("person") or "").split()))
        if who is None:
            return [], "Pick someone on this split."
        if (cid, who["name"]) not in out:
            out.append((cid, who["name"]))
    return out, None


def _let_go_after(st, asks: list[tuple[str, str]]) -> tuple[dict, float]:
    """PB-13b Let it go, once the payback is linked: what they still owe
    becomes hers, as S-08's Let it go does (their part shrinks to what
    they've paid). Returns the Undo's marks (the split as it was, the let-go
    cleared) and how much was let go."""
    marks: dict = {}
    total = 0
    for cid, name in asks:
        t = st.get_transaction(cid)
        split = st.splits().get(cid)
        if t is None or split is None:
            continue
        p = _person(split, name)
        status = next((s for s in sp.people_status(t, split, st.all_transactions(), st.payback_people())
                       if s["name"] == name), None)
        if p is None or status is None or status["owes"] < 0.005 or p.get("let_go"):
            continue
        was = {"split": st.splits().get(cid), "share": t.my_share if t.share_set else None}
        marks.setdefault("splits", {}).setdefault(cid, was)
        marks.setdefault("let_go", {}).setdefault(cid, {})[name] = None
        st.set_let_go(cid, name, p["amount"], _today().isoformat())
        p["amount"] = round(status["paid"], 2)
        _reshare(st, t, split)
        total += _cents(status["owes"])
    return marks, total / 100


def _paid_back_title(parts, let_go: float) -> str | None:
    """PB-14's toast, "Sam paid back $15.00", or PB-13b's "Sam paid in full ·
    $45.00 let go", when every part pays back one person's share. None
    keeps the parts' own title."""
    if not isinstance(parts, list) or not parts:
        return None
    if any(not isinstance(p, dict) or p.get("kind") != "payback" or not str(p.get("person") or "").strip()
           for p in parts):
        return None
    names = [" ".join(str(p["person"]).split()) for p in parts]
    if any(not sp.same_person(n, names[0]) for n in names):
        return None
    if let_go >= 0.005:
        return f"{names[0]} paid in full · ${let_go:,.2f} let go"
    try:
        paid = sum(_cents(p.get("amount")) for p in parts) / 100
    except (TypeError, ValueError):
        return None
    return f"{names[0]} paid back ${paid:,.2f}"


# ── Paid back from the purchase side (2026-11-15; no UI yet) ─────────────
# From her own row on a split, "Find what paid it back" will list money in
# that could be one person's payback and run the same Paid back steps
# (PB-13, PB-13b). designBOT is still drawing it; the server is ready. The
# link goes through save_parts, the one path the deposit side uses.

CANDIDATE_DAYS_BEFORE = 30   # a payback can arrive before the purchase posts
CANDIDATE_DAYS_AFTER = 365
CANDIDATE_LIMIT = 20


def _share_or_error(st, charge_id: str, name: str):
    """(purchase, split, person, what they owe) or an error reply."""
    t, split, err = _split_or_error(st, charge_id)
    if err:
        return None, err
    if split.get("mode") == sp.UNSURE:
        return None, (jsonify({"error": "Pick someone on this split."}), 400)
    p = _person(split, " ".join(str(name or "").split()))
    if p is None:
        return None, (jsonify({"error": "Pick someone on this split."}), 400)
    status = next(s for s in sp.people_status(t, split, st.all_transactions(), st.payback_people())
                  if s["name"] == p["name"])
    return (t, split, p, round(status["owes"], 2)), None


def _free_deposit(st, x: Transaction) -> bool:
    """Money in that isn't linked, in parts, a part or left out: one the
    Paid back steps could still sort. (An e-Transfer reads as Transfers
    until it's sorted, so the category doesn't rule it out.)"""
    return (x.amount < 0 and not x.repays and not x.excluded and not (x.raw or {}).get("part_of")
            and not st.parts().get(x.fingerprint))


def _split_preview(amount: float, owes: float) -> dict:
    """How a deposit would split against what they owe: PB-13's Part of it
    (less than owed: what it pays and what PB-13b would let go), All of it,
    and the extra over it (S-11 v2 next)."""
    got, due = _cents(amount), _cents(owes)
    if got < due:
        return {"kind": "part", "part": got / 100, "all": due / 100, "let_go": (due - got) / 100, "extra": 0.0}
    return {"kind": "all" if got == due else "more", "part": None, "all": due / 100, "let_go": 0.0,
            "extra": (got - due) / 100}


@bp.get("/transactions/<txn_id>/paid-back-candidates")
def paid_back_candidates(txn_id: str):
    """Read-only: money in that could be `person`'s payback on this purchase,
    theirs first (sent by them), then closest to what they owe. Each says
    how it would split into part or all. Changes nothing."""
    from datetime import timedelta
    from .etransfers import known_people, party as etransfer_party
    st = store()
    share, err = _share_or_error(st, txn_id, request.args.get("person"))
    if err:
        return err
    t, split, p, owes = share
    day = date.fromisoformat(t.date[:10])
    lo = (day - timedelta(days=CANDIDATE_DAYS_BEFORE)).isoformat()
    hi = (day + timedelta(days=CANDIDATE_DAYS_AFTER)).isoformat()
    txns = st.all_transactions()
    people = known_people(txns, st.splits(), st.payback_people())
    rows = []
    for x in txns:
        if not (lo <= x.date[:10] <= hi) or not _free_deposit(st, x):
            continue
        sender = x.party or (etransfer_party(x, people) or {}).get("name") or x.merchant or ""
        rows.append({"id": x.fingerprint, "date": x.date[:10], "merchant": x.merchant or x.description,
                     "amount": round(-x.amount, 2), "from_person": sp.same_person(sender, p["name"]),
                     "split": _split_preview(-x.amount, owes)})
    rows.sort(key=lambda r: (not r["from_person"], abs(_cents(r["amount"]) - _cents(owes)), r["date"]))
    return jsonify({"person": p["name"], "owes": owes, "share": round(float(p["amount"]), 2),
                    "candidates": rows[:CANDIDATE_LIMIT]})


@bp.post("/transactions/<txn_id>/paid-back")
def paid_back_from_purchase(txn_id: str):
    """Link a deposit to this person's share from the purchase side:
    {deposit, person, amount?, let_go?}. `amount` is Part of it (default:
    all of the deposit, up to what they owe); `let_go` is PB-13b's Let it go.
    It builds the payback part PB-13 sends and saves it through save_parts,
    so the link, the toast and the Undo are the deposit side's. Whatever the
    deposit holds past this share stays "left to sort" in Needs a look."""
    st = store()
    body = _body()
    share, err = _share_or_error(st, txn_id, body.get("person"))
    if err:
        return err
    t, split, p, owes = share
    deposit = st.get_transaction(str(body.get("deposit") or ""))
    if deposit is None or not _free_deposit(st, deposit):
        return jsonify({"error": "Pick the money that paid it back."}), 400
    if owes < 0.005:
        return jsonify({"error": f"{p['name']} doesn’t owe anything on this."}), 400
    whole = round(-deposit.amount, 2)
    room = min(_cents(whole), _cents(owes))
    if body.get("amount") is None:
        amount = room
    else:
        try:
            amount = _cents(body.get("amount"))
        except (TypeError, ValueError):
            return jsonify({"error": "How much they paid back has to be an amount."}), 400
        if amount < 1 or amount > room:
            return jsonify({"error": f"Make it between $0.01 and ${room / 100:,.2f}."}), 400
    part = {"kind": "payback", "amount": amount / 100, "charge": t.fingerprint, "person": p["name"]}
    if body.get("let_go"):
        part["let_go"] = True
    return save_parts(st, deposit, {"parts": [part], "later": amount < _cents(whole)})


# ── PB-20 to PB-24: Find what paid it back (approved 2026-11-15) ─────────
# Figma Proposals › "Paid back" 1351:8769, note 1352:10319. Her own row's
# ••• on a split (PB-20) opens "What paid back your share?" (PB-22): LIKELY
# is money in after the purchase from work, the shop or someone on the
# split; from work or the shop it's within $1 of her share or of the whole
# purchase. Search takes a name or an amount. Nothing found is PB-23. Once
# she picks one, the app runs the usual steps (PB-11 with the kind picked,
# PB-13 / PB-13b, T-09w / T-09rs and the S-11 extras) on a free deposit.
# A deposit already linked to another purchase is PB-24: its free part
# links at once; taking more from the other purchase always asks first.

FIND_NEAR = 100   # cents: "within $1" of her share or the whole purchase


def _query_amount(q: str) -> int | None:
    """"$60", "60.00", "1,980": an amount in cents; None for words."""
    import math
    s = q.replace("$", "").replace(",", "").strip()
    try:
        v = float(s)
    except ValueError:
        return None
    return _cents(v) if math.isfinite(v) and v > 0 else None


def _employers(st, txns) -> set[str]:
    """Who pays her: pay and bonuses, and whoever reimbursed her before."""
    from .categorize import merchant_key
    from .marks import REIMBURSEMENT
    kinds = st.payback_kinds()
    out = set()
    for x in txns:
        if x.amount < 0 and (x.income_type in ("salary", "bonus") or kinds.get(x.fingerprint) == REIMBURSEMENT
                             or (x.raw or {}).get("part_kind") == "reimbursement"):
            out.add(merchant_key(x.merchant or x.description))
    out.discard("")
    return out


def _as_parts(st, x) -> tuple[list[dict], bool] | None:
    """A linked deposit's links as the parts that would say the same:
    (parts as asked, a rest left to sort). None when it isn't linked, or is
    linked in a way only its own page changes."""
    from .marks import REIMBURSEMENT, REFUND_SHARE
    stored = st.parts().get(x.fingerprint)
    if stored:
        return dp.as_asked(stored)
    whole = _cents(-x.amount)
    if x.repays:
        kind = st.payback_kinds().get(x.fingerprint)
        who = st.payback_people().get(x.fingerprint)
        named = {"person": who} if who and who != sp.ME else {}
        out = []
        for cid in x.repays_all:
            if kind == REIMBURSEMENT:
                part = {"kind": "reimbursement"}
            elif kind == REFUND_SHARE:
                part = {"kind": "refund", **(named or {"share": True})}
            elif kind is None:
                part = {"kind": "payback", **named}
            else:
                return None
            out.append({**part, "charge": cid, "amount": x.part_for(cid)})
        return out, sum(_cents(p["amount"]) for p in out) < whole
    if x.refund_of:
        return [{"kind": "refund", "charge": x.refund_of, "amount": whole / 100}], False
    return None


def _first_name(name: str) -> str:
    return (name or "").split()[0] if (name or "").split() else name


class _Find:
    """What PB-22 needs about one purchase: her share, what's left of it,
    who's on the split, who pays her."""

    def __init__(self, st, t, split):
        from .etransfers import known_people
        self.st, self.t, self.split = st, t, split
        self.txns = st.all_transactions()
        self.people = known_people(self.txns, st.splits(), st.payback_people())
        mine: dict = {}
        status = sp.people_status(t, split, self.txns, st.payback_people(), mine=mine)
        self.owes = {s["name"]: round(s["owes"], 2) for s in status}
        self.share = round(mine.get("amount", 0.0), 2)
        self.left = sp.your_share_left(t, split, self.txns, st.payback_people()) or 0.0
        self.whole = round(sp.split_base(t), 2)
        self.employers = _employers(st, self.txns)
        self.after = sp.bought_on(t).isoformat()

    def on_split(self, name: str | None) -> str | None:
        p = _person(self.split, " ".join(str(name or "").split())) if name else None
        return p["name"] if p else None

    def detected(self, x) -> tuple[str | None, str | None]:
        """(work | shop | person, who on the split) from who sent it."""
        from .categorize import merchant_key
        from .etransfers import party as etransfer_party
        sender = x.party or (etransfer_party(x, self.people) or {}).get("name") or ""
        for p in self.split["people"]:
            if (sender and sp.same_person(sender, p["name"])) or sp.from_person(x, p["name"]):
                return "person", p["name"]
        key = merchant_key(x.merchant or x.description)
        if key and key == merchant_key(self.t.merchant or self.t.description):
            return "shop", None
        if key in self.employers:
            return "work", None
        return None, None

    def need(self, kind: str, person: str | None) -> float:
        return self.owes.get(person, 0.0) if kind == "person" else round(self.left, 2)

    def row(self, x) -> dict | None:
        """One candidate, or None when it can't be one."""
        if x.amount >= 0 or (x.excluded and x.excluded != dp.SPLIT) or (x.raw or {}).get("part_of"):
            return None
        kind, person = self.detected(x)
        taken = None
        is_linked = bool(x.repays or x.refund_of or self.st.parts().get(x.fingerprint))
        linked = _as_parts(self.st, x) if is_linked else None
        if (is_linked or x.excluded) and linked is None:
            return None
        if linked is not None:
            asked, _ = linked
            if any(a.get("charge") == self.t.fingerprint for a in asked):
                return None   # It already pays this one back.
            free = _cents(-x.amount) - sum(_cents(a["amount"]) for a in asked)
            other = next((a for a in asked if a["kind"] in ("payback", "refund", "reimbursement")
                          and a.get("charge")), None)
            if other is not None:
                # PB-24 links at once, so it says what it is by what it already is.
                if other["kind"] == "reimbursement":
                    kind, person = "work", None
                elif other["kind"] == "refund" and not other.get("person"):
                    kind, person = "shop", None
                elif self.on_split(other.get("person")):
                    kind, person = "person", self.on_split(other.get("person"))
            if kind is None or (other is None and free < 1):
                return None
            need = _cents(self.need(kind, person))
            now = min(need, max(free, 0))
            more = min(need - now, _cents(other["amount"])) if other is not None else 0
            charge = self.st.get_transaction(other["charge"]) if other is not None else None
            taken = {"free": max(free, 0) / 100, "need": need / 100, "more": max(more, 0) / 100,
                     "other": ({"id": charge.fingerprint, "merchant": charge.merchant or charge.description}
                               if charge else None)}
        amount = _cents(-x.amount)
        bits = []
        if kind == "person":
            bits.append(f"{_first_name(person)} is on this split")
        else:
            if kind:
                bits.append({"work": "work", "shop": "a refund"}[kind])
            if abs(amount - _cents(self.share)) <= FIND_NEAR:
                bits.append("same as your share")
            elif abs(amount - _cents(self.whole)) <= FIND_NEAR:
                bits.append("the whole purchase")
        near = abs(amount - _cents(self.share)) <= FIND_NEAR or abs(amount - _cents(self.whole)) <= FIND_NEAR
        return {"id": x.fingerprint, "date": x.date[:10], "payer": x.merchant or x.description,
                "amount": amount / 100, "kind": kind, "person": person, "why": " · ".join(bits),
                "likely": kind == "person" or (kind is not None and near), "taken": taken}


def _find_or_error(st, txn_id: str):
    t, split, err = _split_or_error(st, txn_id)
    if err:
        return None, err
    if split.get("mode") == sp.UNSURE or not split.get("me", True) or t.my_share is None:
        return None, (jsonify({"error": "Find what paid it back is for your share of a split."}), 400)
    return _Find(st, t, split), None


@bp.get("/transactions/<txn_id>/paid-back-find")
def paid_back_find(txn_id: str):
    """PB-22 / PB-23, read-only: `q` empty lists LIKELY (money in after the
    purchase from work, the shop or someone on the split); a name or an
    amount searches all money in after it. Newest first. Each row says who
    it's from, why it matches, the kind PB-11 picks, and (PB-24) what of it
    is free when it already pays back something else."""
    from datetime import timedelta
    st = store()
    f, err = _find_or_error(st, txn_id)
    if err:
        return err
    q = " ".join(str(request.args.get("q") or "").split())[:80]
    wanted = _query_amount(q) if q else None
    hi = (date.fromisoformat(f.after) + timedelta(days=CANDIDATE_DAYS_AFTER)).isoformat()
    rows = []
    for x in f.txns:
        if not (f.after <= x.date[:10] <= hi) or x.amount >= 0:
            continue
        r = f.row(x)
        if r is None:
            continue
        if not q:
            keep = r["likely"]
        elif wanted is not None:
            keep = abs(_cents(r["amount"]) - wanted) <= FIND_NEAR
        else:
            text = " ".join(str(v) for v in (x.merchant, x.description, x.party, r["person"]) if v).lower()
            keep = q.lower() in text
        if keep:
            rows.append(r)
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return jsonify({"merchant": f.t.merchant or f.t.description, "date": f.after, "amount": f.whole,
                    "share": f.share, "left": round(f.left, 2), "query": q,
                    "about": (wanted / 100) if wanted is not None else f.share,
                    "candidates": rows[:CANDIDATE_LIMIT]})


@bp.get("/transactions/<txn_id>/paid-back-who")
def paid_back_who(txn_id: str):
    """PB-11 from the deposit (PAID-03): the kind Pearl picks for "Who paid
    you back?", read from who sent it the way PB-22 reads it from the
    purchase side (`_Find.detected`): someone on a split of a purchase in
    the year before it (one still open first) is "person"; the same shop as
    such a purchase is "shop"; whoever pays her is "work". {kind, person},
    both None when nothing says. Read-only."""
    from datetime import timedelta
    from .categorize import merchant_key
    from .etransfers import known_people
    from .etransfers import party as etransfer_party
    st = store()
    x = st.get_transaction(txn_id)
    if x is None:
        return jsonify({"error": "Transaction not found"}), 404
    nothing = {"kind": None, "person": None}
    if x.amount >= 0:
        return jsonify(nothing)
    txns = st.all_transactions()
    by_id = {t.fingerprint: t for t in txns}
    day = x.date[:10]
    lo = (date.fromisoformat(day) - timedelta(days=CANDIDATE_DAYS_AFTER)).isoformat()
    bought = [t for t in txns if t.amount > 0 and lo <= sp.bought_on(t).isoformat() <= day]
    splits = st.splits()
    people = known_people(txns, splits, st.payback_people())
    sender = x.party or (etransfer_party(x, people) or {}).get("name") or ""
    # Open splits first, the newest of each first.
    on_splits = sorted(((split, by_id[cid]) for cid, split in splits.items()
                        if cid in by_id and lo <= sp.bought_on(by_id[cid]).isoformat() <= day),
                       key=lambda pair: (pair[0].get("closed_at") is not None,
                                         -sp.bought_on(pair[1]).toordinal()))
    for split, _ in on_splits:
        for p in split["people"]:
            if (sender and sp.same_person(sender, p["name"])) or sp.from_person(x, p["name"]):
                return jsonify({"kind": "person", "person": p["name"]})
    key = merchant_key(x.merchant or x.description)
    if key and any(merchant_key(t.merchant or t.description) == key for t in bought):
        return jsonify({"kind": "shop", "person": None})
    if key and key in _employers(st, txns):
        return jsonify({"kind": "work", "person": None})
    return jsonify(nothing)


def _part_for(kind: str, charge: str, amount: float, person: str | None) -> dict:
    """The part that links money to this purchase, by who it's from."""
    if kind == "work":
        return {"kind": "reimbursement", "charge": charge, "amount": amount}
    if kind == "shop":
        return {"kind": "refund", "charge": charge, "amount": amount, "share": True}
    return {"kind": "payback", "charge": charge, "amount": amount, "person": person}


@bp.post("/transactions/<txn_id>/paid-back-take")
def paid_back_take(txn_id: str):
    """PB-24: a deposit that already pays back another purchase. {deposit,
    take}: its free part links to this purchase at once ("Linked $20.00 ·
    Pai Northern Thai"); with `take`, the rest this purchase needs comes off
    the other one too ("Moved $40.00 from Air Canada"). One Undo puts the
    deposit back exactly as it was."""
    from . import unlink
    from .marks import undo_marks
    st = store()
    f, err = _find_or_error(st, txn_id)
    if err:
        return err
    body = _body()
    x = st.get_transaction(str(body.get("deposit") or ""))
    row = f.row(x) if x is not None else None
    if row is None or row["taken"] is None:
        return jsonify({"error": "Pick the money that paid it back."}), 400
    taken, take = row["taken"], bool(body.get("take"))
    free, need, more = _cents(taken["free"]), _cents(taken["need"]), _cents(taken["more"]) if take else 0
    now = min(need, free)
    if need < 1:
        return jsonify({"error": "Nothing of this is left to pay back."}), 400
    if now + more < 1:
        return jsonify({"error": "None of this deposit is free."}), 400
    other = (taken["other"] or {}).get("id")

    def change(asked: list[dict]) -> list[dict]:
        out, left = [], more
        for a in asked:
            a = dict(a)
            if left and a.get("charge") == other and a["kind"] in ("payback", "refund", "reimbursement"):
                cut = min(left, _cents(a["amount"]))
                left -= cut
                a["amount"] = (_cents(a["amount"]) - cut) / 100
                if a["amount"] < 0.005:
                    continue
            out.append(a)
        return out + [_part_for(row["kind"], f.t.fingerprint, (now + more) / 100, row["person"])]

    whole = _cents(-x.amount)
    later = lambda parts: sum(_cents(a["amount"]) for a in parts) < whole
    if st.parts().get(x.fingerprint):
        info = unlink._take_down(st, x.fingerprint, change)
        try:
            unlink.put_back(st, x.fingerprint, info["new"], later(info["new"]), info["made"], info["cash"])
        except dp.Problem as exc:
            unlink.put_back(st, x.fingerprint, info["parts"], info["later"], info["made"], info["cash"])
            return jsonify({"error": str(exc)}), 400
        info.pop("new")
        marks: dict = {"reparts": [info]}
    else:
        asked, _ = _as_parts(st, x)
        marks = {}
        if x.repays:
            marks["paybacks"] = {x.fingerprint: {"charge": x.repays, "kind": st.payback_kinds().get(x.fingerprint),
                                                 "person": st.payback_people().get(x.fingerprint),
                                                 "amount": x.repays_amount}}
            marks["payback_more"] = {x.fingerprint: st.payback_more(x.fingerprint)}
        if x.refund_of:
            marks["refunds"] = {x.fingerprint: x.refund_of}
        new = change(asked)
        try:
            dp.apply(st, x, new, later(new))
        except dp.Problem as exc:
            undo_marks(st, marks)
            return jsonify({"error": str(exc)}), 400
    core._reclassify(st)
    title = (f"Moved ${more / 100:,.2f} from {taken['other']['merchant']}" if more
             else f"Linked ${now / 100:,.2f} · {f.t.merchant or f.t.description}")
    return jsonify({"ok": True, "title": title, "undo": {"parts": x.fingerprint, "marks": marks}})


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
        # S-11xm over (1043:1194): the line the app shows, in the same words (REFRESH-03).
        return None, f"Only ${q['amount']:,.2f} is extra. Make it ${q['amount']:,.2f} or less."
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
    base = None
    if charge.joint:
        # JOINT-B: Split my part from a deposit, as from the purchase.
        base = sp.split_base(charge)
        if base < 0.005:
            return None, "None of it is yours to split."
        from .joint import holder
        for p in ask.get("people") or []:
            who = holder(charge, str(p.get("name") or "")) if isinstance(p, dict) else None
            if who:
                return None, f"{who}{'’' if who.lower().endswith('s') else '’s'} part is already off."
    mode = ask.get("mode")
    people, problem = sp.validate(charge, mode, ask.get("people"), ask.get("you"),
                                  ask.get("include_me", True) is not False, base=base)
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
    every = st.splits()

    def ways(cid: str) -> int | None:
        """PB-12's "split 2 ways": the people on it, and her when she's in it."""
        s = every.get(cid)
        return len(s.get("people") or []) + (1 if s.get("me", True) else 0) if s else None

    # S-32 (2026-11-04): a purchase that hasn't posted yet says so.
    items = [{"id": i["charge_id"], "merchant": i["merchant"], "date": i["date"], "owes": i["owes"],
              "share": i["amount"], "paid": i["paid"], "person": r["name"], "theirs": r in mine,
              "ways": ways(i["charge_id"]),
              "pending": bool(((getattr(txns.get(i["charge_id"]), "raw", None)) or {}).get("pending"))}
             for r in mine + rest for i in r["items"]]
    # SPLIT-C (S-09u, S-35u): Not sure yet splits take any amount, up to what
    # the purchase still costs her (`owes`). The sender's come first; with
    # no name, everyone on one could have sent it.
    unsure = [r for r in sp.unsure_rows(list(txns.values()), st.splits(), st.payback_people())
              if r["still"] >= 0.005]
    theirs_u = [r for r in unsure if sender and sp.same_person(r["name"], sender)]
    for r in (theirs_u or ([] if mine else unsure)):
        c = r["charge"]
        items.insert(len([i for i in items if i["theirs"]]) if theirs_u else len(items),
                     {"id": c.fingerprint, "merchant": c.merchant, "date": c.date[:10], "owes": r["still"],
                      "share": None, "paid": r["paid"], "person": r["name"], "theirs": bool(theirs_u),
                      "unknown": True, "pending": bool((c.raw or {}).get("pending"))})
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
    frm = mine[0]["name"] if mine else (theirs_u[0]["name"] if theirs_u else None)
    return jsonify({"from": frm, "named": named if not theirs_u else None, "items": items,
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
