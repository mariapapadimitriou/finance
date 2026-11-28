"""Same money moving? One Quick sort card about one pair (TR-30, AI4-Pair;
THL-309, THL-122, THL-123, THL-226).

Pearl already sees most moves between her accounts by itself
(transfers.match_transfers: the same amount on another of her accounts
within two days, four onto a card). What it can't be sure of it used to ask
about twice, one row at a time: "Where did this go?" on the money out, and
"What's this money in?" on the arrival. When the two are very likely the
same money, Quick sort asks once, about the pair:

    Out of TD Chequing $500.00 / Onto TD Visa $500.00
    One payment moving between your accounts?   Same amount, a day apart.
    Not this · Skip · Yes

A pair is asked about only when all of these hold (precision first):

* the money out is still an Unsorted transfer from a bank account, nothing
  she sorted herself, linked or took apart;
* the arrival is on another of her accounts (a card for a card payment),
  the same amount to the cent, from the same day to `ASK_DAYS` after,
  not already the other end of something, and only Pearl's guess of what
  it is (never income she confirmed, a payback, a loan payment);
* neither end is an e-Transfer naming someone else
  (transfers.person_to_person): a friend's money is never her own;
* each has exactly one such partner: two possible arrivals for one $300
  out, or two outs for one arrival, and Pearl asks nothing.

Nothing changes until her Yes (AI detects, she confirms). Yes links the two
as one transfer (PUT /transactions/<id>/links's own code), with Undo. Not
this: never asked about that pair again, and each row is asked about on its
own as before. Skip: not in Quick sort again; the rows' own questions stay in
Needs a look. One card per pair: while a pair is asked, its two rows' own
questions are folded into it, so nothing is asked twice. Every answer is
recorded against transfers.pair_ask@version (THL-310).
"""

from __future__ import annotations

import json
import re
from datetime import date

from .models import Transaction

DETECTOR = "transfers.pair_ask"
ASK_DAYS = 7                       # "within a few days": a weekend and a holiday
REJECTED_KEY = "pair_asks_not_this"    # [[out id, in id]] she said Not this to
SKIPPED_KEY = "pair_asks_skipped"      # [[out id, in id]] she skipped in Quick sort
KEEP = 500


def _json(st, key: str) -> list:
    raw = st.setting(key)
    try:
        out = json.loads(raw) if raw else []
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def _add(st, key: str, pair: list[str]) -> None:
    rows = [p for p in _json(st, key) if p != pair]
    rows.append(pair)
    st.set_setting(key, json.dumps(rows[-KEEP:]))


def _drop(st, key: str, pair: list[str]) -> None:
    rows = _json(st, key)
    if pair in rows:
        rows.remove(pair)
        st.set_setting(key, json.dumps(rows))


def _kind(t: Transaction) -> str:
    return str((t.raw or {}).get("account_type", "")).lower()


def _account(t: Transaction) -> str:
    """"TD Chequing": the account's name on the card, without its digits."""
    return re.sub(r"\s*[\u2022\u00b7]{2}\s*\w+$", "", t.account_label or "").strip()


def _gap_words(days: int) -> str:
    if days == 0:
        return "Same amount, the same day."
    if days == 1:
        return "Same amount, a day apart."
    return f"Same amount, {days} days apart."


def find(transactions: list[Transaction], today: str | None = None,
         answered: set[tuple[str, str]] = frozenset()) -> list[dict]:
    """Every pair worth one question, newest first (pure: no store)."""
    from . import transfers as tr
    paired = tr.transfer_pairs(transactions, today=today)
    taken = set(paired) | set(paired.values()) | tr.matched_inflows(transactions, today=today)
    outs = [t for t in transactions
            if t.amount > 0 and tr._is_bank(t) and t.category == tr.UNSORTED
            and t.category_source not in tr._DECIDED and not tr.others(t)
            and not t.transfer_link and not t.unpaired and t.fingerprint not in taken
            and not tr.person_to_person(t)]
    if not outs:
        return []
    arrivals: dict[int, list[Transaction]] = {}
    for x in transactions:
        if (x.amount < 0 and x.fingerprint not in taken and not tr._theirs(x) and not x.repays
                and not x.transfer_link and not x.unpaired and _kind(x) in ("depository", "credit")
                and ((x.category or "") in tr._MOVED - {tr.UNSORTED} or tr._guessed_arrival(x))
                and x.category_source not in tr._DECIDED and not tr.person_to_person(x)):
            arrivals.setdefault(tr._cents(-x.amount), []).append(x)

    def gap(t, x) -> int:
        return (date.fromisoformat(x.date[:10]) - date.fromisoformat(t.date[:10])).days

    options: dict[str, list[Transaction]] = {}
    wanted: dict[str, list[str]] = {}
    for t in outs:
        found = [x for x in arrivals.get(tr._cents(t.amount), [])
                 if x.account_id != t.account_id and 0 <= gap(t, x) <= ASK_DAYS]
        options[t.fingerprint] = found
        for x in found:
            wanted.setdefault(x.fingerprint, []).append(t.fingerprint)
    out = []
    for t in outs:
        found = options[t.fingerprint]
        if len(found) != 1 or len(wanted[found[0].fingerprint]) != 1:
            continue                         # more than one way to pair: ask nothing
        x = found[0]
        if (t.fingerprint, x.fingerprint) in answered:
            continue
        days = gap(t, x)
        out.append({
            "key": f"pair:{t.fingerprint}:{x.fingerprint}", "id": f"{t.fingerprint}:{x.fingerprint}",
            "out": t.fingerprint, "in": x.fingerprint,
            "kind": "card_payment" if _kind(x) == "credit" else "transfer_pair",
            "amount": round(t.amount, 2), "days": days, "reason": _gap_words(days),
            "from_account": _account(t), "to_account": _account(x),
            "out_date": t.date[:10], "in_date": x.date[:10],
            "txn": {"id": t.fingerprint, "date": t.date[:10]},
        })
    out.sort(key=lambda p: (p["out_date"], p["out"]), reverse=True)
    return out


def answered(st) -> set[tuple[str, str]]:
    return {tuple(p) for p in _json(st, REJECTED_KEY) + _json(st, SKIPPED_KEY)
            if isinstance(p, list) and len(p) == 2}


def asks(st, transactions: list[Transaction], today: str | None = None) -> list[dict]:
    """The pairs Quick sort asks about now."""
    return find(transactions, today, answered(st))


# Review parts that ask about one row: while the row is in a pair, the pair asks.
_PARTS = ("money_in", "unsure_category", "who_sent", "income_type", "joint_in")


def fold(review: dict, pairs: list[dict]) -> None:
    """Put the pairs in the review as `pair_asks`, and take their rows' own
    questions out of it: one card per pair, one number for the app."""
    review["pair_asks"] = pairs
    if not pairs:
        return
    ids = {p["out"] for p in pairs} | {p["in"] for p in pairs}
    removed = removed_open = 0
    for part in _PARTS:
        items = review.get(part) or []
        keep = [it for it in items if (it.get("txn") or {}).get("id") not in ids]
        for it in items:
            if (it.get("txn") or {}).get("id") in ids:
                removed += 1
                removed_open += 0 if it.get("skipped") else 1
        review[part] = keep
    groups = review.get("unsorted") or {}
    rows = groups.get("transfers") or []
    kept = [t for t in rows if t["id"] not in ids]
    if len(kept) != len(rows):
        gone = [t for t in rows if t["id"] in ids]
        removed += len(gone)
        removed_open += sum(1 for t in gone if not t.get("skipped"))
        review["unsorted"] = {**groups, "transfers": kept, "count": len(kept),
                              "total": round(sum(t["amount"] for t in kept), 2),
                              "groups": [g for g in groups.get("groups") or [] if not set(g["ids"]) <= ids]}
    review["count"] = review.get("count", 0) - removed + len(pairs)
    review["open"] = review.get("open", 0) - removed_open + len(pairs)
    review["skipped"] = max(review.get("skipped", 0) - (removed - removed_open), 0)


# ── Her answers ───────────────────────────────────────────────────────────

def _said(st, p: dict, what: str, today: str, status: str | None = None) -> None:
    from .signals import outcome
    from .signals.model import evidence
    outcome(st, DETECTOR, p["out"], p["kind"], what, today=today, status=status,
            txn_ids=(p["out"], p["in"]),
            ev=evidence(count=2, first=p["out_date"], last=p["in_date"],
                        dates=[p["out_date"], p["in_date"]], amount=p["amount"], days_apart=p["days"]))


def lookup(st, out_id: str, in_id: str, today: str) -> dict | None:
    return next((p for p in asks(st, st.all_transactions(), today)
                 if p["out"] == out_id and p["in"] == in_id), None)


def forget_pairs(st, ids: list[str]) -> None:
    """Rows she unlinked herself: no pair among them is asked about again."""
    for a in ids:
        for b in ids:
            if a != b:
                _add(st, REJECTED_KEY, [a, b])


def not_this(st, p: dict, today: str) -> None:
    _add(st, REJECTED_KEY, [p["out"], p["in"]])
    _said(st, p, "not_this", today)


def skip(st, p: dict, today: str) -> None:
    _add(st, SKIPPED_KEY, [p["out"], p["in"]])
    _said(st, p, "skip", today)


def yes(st, p: dict, today: str) -> None:
    _said(st, p, "yes", today)


def undo(st, out_id: str, in_id: str, today: str) -> None:
    """Undo on a Yes (the link's own Undo puts the rows back) or a Not
    this / Skip: the pair can be asked again."""
    _drop(st, REJECTED_KEY, [out_id, in_id])
    _drop(st, SKIPPED_KEY, [out_id, in_id])
    from .signals import outcome
    outcome(st, DETECTOR, out_id, "transfer_pair", "undo", today=today)
