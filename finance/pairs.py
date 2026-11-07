"""Pearl says what it knows first: pair cards.

When the ledger itself points at the answer to a money-in question, the card
asks that, and one Yes settles both sides. Only with evidence, and the
evidence is said out loud: the same store and amount, the exact amount, the
friend's own message, an even share, or money both ways with one person.
Two possible answers means no pair: the ordinary question is asked instead.
"""

from __future__ import annotations

from datetime import date

from .etransfers import memo, party
from .models import Transaction

LOOKBACK_DAYS = 120


def _on(iso: str) -> str:
    return date.fromisoformat(iso[:10]).strftime("%b %-d")


def _money(x: float) -> str:
    return f"${abs(x):,.0f}" if abs(x) == round(abs(x)) else f"${abs(x):,.2f}"


def _share_word(n: int) -> str:
    return {2: "Half", 3: "A third", 4: "A quarter"}.get(n, f"1/{n}")


def _open_outs(review: dict) -> dict[str, dict]:
    """Money out still asked about as Saved or spent?, by id."""
    return {t["id"]: t for t in (review.get("unsorted") or {}).get("transfers", []) if not t.get("skipped")}


def _both_ways(t: Transaction, who: str, txns: list[Transaction], outs: dict[str, dict]) -> dict | None:
    """Money in from someone and money out to the same person, still unsorted."""
    from .splits import same_person
    got = -t.amount
    hits = []
    for o in txns:
        if o.fingerprint not in outs or o.amount <= 0:
            continue
        to = party(o) or {}
        name = to.get("name") or o.merchant
        if not name or not same_person(name, who):
            continue
        if abs((date.fromisoformat(t.date[:10]) - date.fromisoformat(o.date[:10])).days) > LOOKBACK_DAYS:
            continue
        hits.append(o)
    if len(hits) != 1:
        return None
    o = hits[0]
    if o.date[:10] <= t.date[:10] and got <= o.amount + 0.005:
        # She sent it first: a loan coming back, in whole or in part.
        return {"kind": "lent", "question": f"Did you lend {who} {_money(o.amount)}?",
                "evidence": f"You sent {who} {_money(o.amount)} on {_on(o.date)}; {_money(got)} came back on {_on(t.date)}.",
                "line": "Yes marks both as a loan, not spending or income.",
                "steps": [{"id": t.fingerprint, "body": {"case": "lent_back"}},
                          {"id": o.fingerprint, "body": {"case": "lent"}}],
                "other": o.fingerprint}
    if t.date[:10] <= o.date[:10] and o.amount <= got + 0.005:
        # They sent it first: she's paying a loan back.
        return {"kind": "borrowed", "question": f"Paying {who} back?",
                "evidence": f"{who} sent you {_money(got)} on {_on(t.date)}; you sent {_money(o.amount)} on {_on(o.date)}.",
                "line": "Yes marks both as a loan, not spending or income.",
                "steps": [{"id": t.fingerprint, "body": {"case": "borrowed"}},
                          {"id": o.fingerprint, "body": {"case": "paying_back"}}],
                "other": o.fingerprint}
    return None


def pair_for(item: dict, t: Transaction, txns: list[Transaction], outs: dict[str, dict],
             names: dict[str, str] | None = None) -> dict | None:
    """The question the evidence asks for one money-in row, or None."""
    from .marks import refund_candidates, reimbursement_candidates
    if item.get("rest"):
        return None
    got = round(-t.amount, 2)
    who = item.get("from") or (party(t) or {}).get("name")
    guess = item.get("guess") or {}
    charge = guess.get("charge") if isinstance(guess, dict) else None

    # A split waiting for this person's share, to the cent.
    split = guess.get("split") if isinstance(guess, dict) else None
    if guess.get("action") == "split" and split and split.get("exact"):
        half = abs(split["amount"] / 2 - got) < 0.01
        name = split["name"]
        return {"kind": "split", "question": f"{'Half' if half else f'{_money(got)}'} of {split['merchant']}?",
                "evidence": f"{name} owes you exactly {_money(got)} for {split['merchant']}, {_on(split['date'])}.",
                "line": f"Yes takes {_money(got)} off {split['merchant']}.",
                "steps": [{"id": t.fingerprint, "body": {"case": "payback", "charge": split["charge_id"]}}],
                "other": split["charge_id"]}

    # The friend's own message names the purchase.
    if guess.get("action") == "memo" and charge:
        return {"kind": "memo", "question": f"{who or 'They'}’s message says “{memo(t)}”. Paying you back for {charge['merchant']}?",
                "evidence": f"{charge['merchant']}, {_on(charge['date'])}, {_money(charge['amount'])}.",
                "line": f"Yes takes {_money(got)} off {charge['merchant']}.",
                "steps": [{"id": t.fingerprint, "body": {"case": "payback", "charge": charge["id"]}}],
                "other": charge["id"]}

    # The same store, the same amount: a refund. Both must point at one purchase.
    store = " ".join(w for w in (t.merchant or "").lower().split() if w not in ("refund", "return", "credit"))
    both = refund_candidates(t, txns, names)
    same = [c for c in both if c.get("exact") and " ".join((c.get("merchant") or "").lower().split()) == store]
    near = [c for c in both if " ".join((c.get("merchant") or "").lower().split()) == store]
    if not who and not same and len(near) == 1:
        same = near
    if len(same) == 1 and not who:
        c = same[0]
        return {"kind": "refund", "question": f"Money back for {c['merchant']}?",
                "evidence": (f"Same store and amount as {_on(c['date'])}." if c.get("exact")
                             else f"From the store you paid {_money(c['amount'])} on {_on(c['date'])}."),
                "line": f"Yes takes {_money(got)} off that purchase.",
                "steps": [{"id": t.fingerprint, "body": {"case": "refund", "charge": c["id"]}}],
                "other": c["id"]}

    # Someone they know: money both ways.
    if who:
        both = _both_ways(t, who, txns, outs)
        if both:
            return both

    # A share of one purchase, to the cent.
    if guess.get("action") == "payback" and charge and charge.get("likely") and who:
        n = charge.get("split") or 2
        if abs(charge["amount"] / n - got) < 0.01:
            return {"kind": "share", "question": f"{_share_word(n)} of {charge['merchant']}?",
                    "evidence": f"{who} sent exactly {_share_word(n).lower()} of {_money(charge['amount'])}, {_on(charge['date'])}.",
                    "line": f"Yes takes {_money(got)} off {charge['merchant']}.",
                    "steps": [{"id": t.fingerprint, "body": {"case": "payback", "charge": charge["id"]}}],
                    "other": charge["id"]}

    # The exact amount of one purchase, from a payer who isn't a person: work paying it back.
    from .categorize import is_generic_transfer_name
    if not who and (t.merchant or "").strip() and not is_generic_transfer_name(t.merchant):
        exact = [c for c in reimbursement_candidates(t, txns, names) if c.get("exact")]
        if len(exact) == 1:
            c = exact[0]
            payer = t.merchant or "They"
            return {"kind": "reimbursement", "question": f"Did {payer} pay for {c['merchant']}?",
                    "evidence": f"Exactly {_money(got)}, the same as {c['merchant']} on {_on(c['date'])}.",
                    "line": f"Yes takes {_money(got)} off that purchase. Neither counts.",
                    "steps": [{"id": t.fingerprint, "body": {"case": "reimbursement", "charge": c["id"]}}],
                    "other": c["id"]}
    return None


def annotate(st, review: dict, txns: list[Transaction], today: str | None) -> None:
    """Add `pair` to each money-in question the evidence can answer. A row
    answers one pair: the first question to claim it keeps it."""
    by_id = {t.fingerprint: t for t in txns}
    outs = _open_outs(review)
    names = st.merchant_names()
    claimed: set[str] = set()
    for it in review.get("money_in") or []:
        t = by_id.get(it["txn"]["id"])
        if t is None or it.get("skipped"):
            continue
        pair = pair_for(it, t, txns, outs, names)
        if not pair or pair["other"] in claimed:
            continue
        claimed.add(pair["other"])
        it["pair"] = pair


def apply(st, review: dict, txn_id: str, today: date) -> dict | None:
    """Yes on a pair card: every step, and the other row's question closed.
    Worked out again from the ledger: the app never says what to do."""
    from . import marks
    from .impact import snapshot, undo_payload
    item = next((i for i in review.get("money_in") or []
                 if i["txn"]["id"] == txn_id and i.get("pair")), None)
    if item is None:
        return None
    pair = item["pair"]
    before = snapshot(st)
    merged: dict = {}
    txns = st.all_transactions()
    by_id = {t.fingerprint: t for t in txns}
    for step in pair["steps"]:
        res = marks.apply(st, by_id[step["id"]], step["body"], today)
        for k, v in res["marks"].items():
            merged.setdefault(k, {}).update(v)
    other = pair["other"]
    # The purchase was fine as it was: it stops asking "Is this right?", and Yes is an answer.
    if other in by_id and not any(s["id"] == other for s in pair["steps"]):
        st.confirm_category(other, by_id[other].category or "Other")
        st.dismiss_review("cat:" + other)
    undo = undo_payload(before, snapshot(st))
    if merged:
        undo["marks"] = merged
    undo["unconfirm"] = [other]
    return {"ok": True, "title": pair["question"].rstrip("?") + ". Sorted both.",
            "also": [other], "undo": undo}
