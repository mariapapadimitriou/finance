"""Many purchases (Figma Proposals › "Many purchases" 1431:6590, note
1432:8062; approved by the product owner 2026-11-17; THL-289, THL-291,
THL-181, THL-301). The shop and Work pay back several of her purchases at
once, as PB-30 does for a person.

* GET /api/transactions/<id>/many-purchases?kind=work|shop&q=
      MP-01 / MP-02's list for money in: her own purchases, or her share of
      split ones, with what's still hers on each. `kind=work`: the ones she
      marked as work, or at a merchant work reimbursed before. `kind=shop`:
      the ones at that shop, before the refund. `q` (a name or an amount)
      adds any other purchase. `also` keeps one purchase on the list (the
      one she came from, PB-22 › The shop / Work). Read-only.

Saving is POST …/parts (finance/parts_api.py `save_parts`): every ticked
purchase as a `reimbursement` or `refund` part (her share of a split one
with `share: true` on a refund; work always pays her share), plus what the
rest is (S-11w / S-11m) in the same request, so one Undo puts it all back.
`payer` there gives MP-05's toast, "Northwind paid back 3 · $186.40".
"""

from __future__ import annotations

import re
from datetime import date

from flask import jsonify, request

from . import splits as sp
from .api import bp, store
from .categorize import NON_SPEND, merchant_key
from .marks import REFUND_DAYS, REIMBURSEMENT, waiting_reimbursed

SEARCH_DAYS = 365
LIMIT = 20


def _cents(x) -> int:
    return int(round(float(x) * 100))


def _words(name: str) -> list[str]:
    return [w for w in re.split(r"[^0-9a-z]+", (name or "").lower()) if w]


def same_shop(shop: str, merchant: str) -> bool:
    """"Amazon" and "AMAZON MKTPL", "Amazon.ca": the shop's name, or its
    first word when that word starts the purchase's name. Never a list of
    merchants: only the names on the two rows."""
    if not shop or not merchant:
        return False
    if merchant_key(shop) == merchant_key(merchant):
        return True
    a, b = _words(shop), _words(merchant)
    return bool(a) and bool(b) and len(a[0]) >= 3 and a[0] == b[0]


def reimbursed_merchants(st, txns) -> set[str]:
    """Merchants work paid her back for before: the purchases a deposit
    marked as a reimbursement is linked to, and reimbursement parts."""
    kinds = st.payback_kinds()
    by_id = {t.fingerprint: t for t in txns}
    ids: set[str] = set()
    for x in txns:
        if x.amount < 0 and kinds.get(x.fingerprint) == REIMBURSEMENT:
            ids.update(x.repays_all)
    for stored in st.parts().values():
        for p in stored:
            if p.get("kind") == "reimbursement" and (p.get("detail") or {}).get("charge"):
                ids.add(p["detail"]["charge"])
    return {merchant_key(by_id[i].merchant) for i in ids if i in by_id} - {""}


def _left(st, c, deposit, txns, splits, payer) -> tuple[float, bool, list[dict]]:
    """(what's still hers on it, whether that's her share of a split, who
    on the split still owes): her share less what came back for it, or the
    purchase less what was paid back or refunded."""
    split = splits.get(c.fingerprint)
    mine = sp.your_share_left(c, split, txns, payer, deposit) if split else None
    if mine is not None:
        people = [{"name": p["name"], "owes": round(p["owes"], 2)}
                  for p in sp.people_status(c, split, txns, payer) if p["owes"] >= 0.005]
        return round(mine, 2), True, people
    left = c.amount - (c.paid_back or 0.0) - (c.refunded or 0.0) + deposit.part_for(c.fingerprint)
    return round(left, 2), False, []


def candidates(st, deposit, kind: str, q: str = "", also: str = "") -> dict:
    """MP-01 / MP-02's rows, newest first: LIKELY, or with `q` what a
    search by name or amount finds (likely ones keep `likely`)."""
    txns = st.all_transactions()
    splits, payer, names = st.splits(), st.payback_people(), st.merchant_names()
    when = date.fromisoformat(deposit.date[:10])
    shop = names.get(merchant_key(deposit.merchant)) or deposit.merchant or deposit.description or ""
    work = reimbursed_merchants(st, txns) if kind == "work" else set()
    needle = " ".join((q or "").lower().split())
    try:
        wanted = _cents(needle.replace("$", "").replace(",", "")) if needle else None
    except ValueError:
        wanted = None
    rows = []
    for c in txns:
        if c.amount <= 0 or c.fingerprint == deposit.fingerprint or (c.raw or {}).get("part_of"):
            continue
        if (c.category or "Other") in NON_SPEND or c.category == "Unsorted transfers":
            continue
        marked = waiting_reimbursed(c.excluded)
        if c.excluded and not marked:
            continue
        gap = (when - date.fromisoformat(c.date[:10])).days
        if gap < -3 or gap > (SEARCH_DAYS if needle else REFUND_DAYS):
            continue
        shown = names.get(merchant_key(c.merchant)) or c.merchant
        if kind == "shop":
            likely = gap >= 0 and gap <= REFUND_DAYS and (same_shop(shop, shown) or same_shop(shop, c.merchant))
        else:
            likely = gap <= REFUND_DAYS and (marked or merchant_key(c.merchant) in work
                                             or merchant_key(shown) in work)
        likely = likely or c.fingerprint == also
        if needle:
            hay = " ".join(x for x in (shown, c.merchant, c.description or "", c.category or "") if x).lower()
            if needle not in hay and not (wanted is not None and abs(_cents(c.amount) - wanted) <= 1):
                continue
        elif not likely:
            continue
        left, share, people = _left(st, c, deposit, txns, splits, payer)
        if left < 0.005:
            continue
        rows.append({"id": c.fingerprint, "date": c.date[:10], "merchant": shown, "amount": left,
                     "whole": round(c.amount, 2), "share": share, "work": marked, "likely": likely,
                     "people": people})
    rows.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    return {"kind": kind, "shop": shop, "date": deposit.date[:10], "amount": round(-deposit.amount, 2),
            "query": needle, "items": rows[:LIMIT]}


@bp.get("/transactions/<txn_id>/many-purchases")
def many_purchases(txn_id: str):
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    kind = request.args.get("kind")
    if kind not in ("work", "shop"):
        return jsonify({"error": "Say whether it was work or the shop."}), 400
    if t.amount >= 0:
        return jsonify({"error": "Only money coming in pays back purchases."}), 400
    q = " ".join(str(request.args.get("q") or "").split())[:80]
    return jsonify(candidates(st, t, kind, q, str(request.args.get("also") or "")))


# ── P5 · Which money paid this back? never a dead end (fewer taps) ───────
# TP-P5-FromPurchase (approved 2026-11-26): "No money in matches" went. The
# finder's own list (parts_api.paid_back_find: the split's people, then
# people who sent money, then work and the shop) comes first, then recent
# money in after the purchase that it didn't think likely, newest first, so
# she can always pick what paid it back. Listing links nothing.

RECENT_DAYS = 60
RECENT_LIMIT = 12
# Money in that is never a payback from a person: her pay and her savings
# (money onto a card is `never_pay`). e-Transfers stay, whatever they're sorted as.
_NOT_PAYBACKS = {"Income", "Savings"}


@bp.get("/transactions/<txn_id>/paid-back-recent")
def paid_back_recent(txn_id: str):
    """GET …/paid-back-find with q empty, then recent money in after the
    purchase (`RECENT_DAYS`), the same row shape. Read-only."""
    from datetime import timedelta
    from . import parts_api as pa
    from .txlist import never_pay
    reply = pa.paid_back_find(txn_id)
    if isinstance(reply, tuple):
        return reply
    body = reply.get_json()
    st = store()
    f, err = pa._find_or_error(st, txn_id)
    if err:
        return err
    seen = {c["id"] for c in body.get("candidates") or []}
    hi = (date.fromisoformat(f.after) + timedelta(days=RECENT_DAYS)).isoformat()
    more = []
    for x in f.txns:
        if x.amount >= 0 or not (f.after <= x.date[:10] <= hi) or x.fingerprint in seen:
            continue
        if (x.category or "") in _NOT_PAYBACKS or never_pay(x):
            continue
        r = f.row(x)
        if r is not None:
            more.append(r)
    more.sort(key=lambda r: (r["date"], r["id"]), reverse=True)
    body["candidates"] = list(body.get("candidates") or []) + more[:RECENT_LIMIT]
    return jsonify(body)
