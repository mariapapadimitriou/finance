"""Recurring transfers (2026-10-27): confirming one from Needs a look, and
the rules on Profile › Categories and rules. See finance/recurring_transfers.py."""

from __future__ import annotations

from flask import jsonify, request

from . import api as _api
from .api import bp, store
from .categorize import CATEGORIES
from . import recurring_transfers as rt


def _today_iso() -> str:
    """Pearl's one clock, read when asked: a name imported from `api`
    kept the clock as it was at import, so a frozen day (tests, the
    logic review's 2026-11-07) never reached these endpoints and Income
    and bills used the real date instead."""
    return _api._today_iso()


# What a recurring transfer can be, as Needs a look offers it.
KINDS = {
    "saved": ("Saved", "Into savings"),
    "moved": ("Transfers", "Moved to another of my accounts"),
    "rent": ("Rent & Housing", "Rent"),
}


def _series_for(st, key: str) -> dict | None:
    from .review import for_store
    review = for_store(st, today=_today_iso())
    return next((it for it in review.get("recurring_transfer") or [] if it["key"] == key), None)


def _said(series: dict, what: str, how: str | None = None, status: str | None = None) -> None:
    """Her answer about a recurring transfer, against the detector's
    version (THL-310). A rule's id is its series' key."""
    from .signals import outcome
    outcome(store(), "recurring_transfers", series["key"], "bill", what, today=_today_iso(),
            how=how, status=status, txn_ids=series.get("ids") or ())


@bp.post("/recurring-transfers")
def confirm_recurring_transfer():
    """"Yes, it repeats": save the rule for the series asked about (`key`),
    as `kind` (saved, moved, rent) or a spending `category`. Every transfer
    matching its amount and schedule, here now or still to come, is sorted
    that way. Answers like the other sorting answers: title, detail, undo."""
    from .impact import snapshot, undo_payload
    from .transfers import apply_transfer_matches
    st = store()
    body = request.get_json(silent=True) or {}
    item = _series_for(st, str(body.get("key") or ""))
    if item is None:
        return jsonify({"error": "That question has already been answered."}), 404
    kind = body.get("kind")
    if kind in KINDS:
        category, what = KINDS[kind]
    else:
        category = body.get("category")
        if category not in CATEGORIES or category in ("Income", "Unsorted transfers"):
            return jsonify({"error": "Say what it is."}), 400
        what = category
    s = item["series"]
    before = snapshot(st, st.all_transactions())
    if body.get("once"):
        # "Just these" (product owner, 2026-11-24): these ones sorted as her
        # own answers, no rule, nothing to come. The question goes; the next
        # one for the amount is asked on its own.
        st.write_categories({fp: (category, "user") for fp in s["ids"]})
        st.dismiss_review(s["key"])
        _said(s, "yes", how="once")
        apply_transfer_matches(st)
        undo = undo_payload(before, snapshot(st, st.all_transactions()))
        undo["undismiss"] = [s["key"]]
        count = len(s["ids"])
        return jsonify({"ok": True, "rule": None,
                        "title": f"{what if kind in KINDS else what}: {'both' if count == 2 else f'all {count}'} sorted.",
                        "detail": "Just these; nothing from now on.", "undo": undo})
    rule = rt.rule_from(s, category, " ".join(str(body.get("label") or "").split())[:60])
    existing = {r["id"]: r for r in st.recurring_transfers()}
    was = existing.get(rule["id"])
    # Every payday (2026-10-28) takes over a calendar rule of hers that only
    # caught half of it ("around the 15th"); Undo brings that one back.
    replaced = {rid: existing[rid] for rid in s.get("replaces") or [] if rid in existing}
    for rid in replaced:
        st.delete_recurring_transfer(rid)
    st.set_recurring_transfer(rule)
    st.dismiss_review(s["key"])
    _said(s, "yes", how="rule")
    apply_transfer_matches(st)
    txns = st.all_transactions()
    pays = rt.paydays(txns)
    sorted_now = sum(1 for t in txns if rt.matches(t, rule, pays))
    undo = undo_payload(before, snapshot(st, txns))
    undo["marks"] = {"recurring_transfers": {rule["id"]: was, **replaced}}
    undo["undismiss"] = [s["key"]]
    to = f" to {s['to']}" if s["to"] else ""
    return jsonify({
        "ok": True, "rule": rule,
        "title": f"Recurring: ${s['amount']:,.2f}{to}, {s['when']}.",
        "detail": (f"Sorted as {what.lower() if kind in KINDS else what}, the {sorted_now} here "
                   "and every one like it from now on."),
        "undo": undo,
    })


@bp.delete("/recurring-transfers/<rule_id>")
def delete_recurring_transfer(rule_id: str):
    """Stop treating a series as recurring. What it sorted keeps its category.
    The answer carries the `undo` ("No longer recurring" with Undo, A+)."""
    from .impact import snapshot, undo_payload
    from .transfers import apply_transfer_matches
    st = store()
    rule = next((r for r in st.recurring_transfers() if r["id"] == rule_id), None)
    if rule is None:
        return jsonify({"error": "No such rule."}), 404
    before = snapshot(st)
    txns = st.all_transactions()
    pays = rt.paydays(txns)
    keep = {t.fingerprint: (t.category, "user") for t in txns
            if rt.matches(t, rule, pays) and t.category_source not in ("user", "merchant_override")}
    st.delete_recurring_transfer(rule_id)
    _said({"key": rule_id}, "stop")
    if keep:
        st.write_categories(keep)
    apply_transfer_matches(st)
    undo = undo_payload(before, snapshot(st))
    undo["marks"] = {"recurring_transfers": {rule_id: rule}}
    return jsonify({"ok": True, "undo": undo})


@bp.post("/transactions/<txn_id>/not-recurring")
def not_recurring(txn_id: str):
    """"Not this one" (product owner, 2026-11-24): a transfer a recurring rule
    sorted keeps its category as her own answer, so the rule leaves it alone
    and its row stops reading "Recurring"; the rule itself stays. Undo puts
    it back under the rule."""
    from .impact import snapshot, undo_payload
    from .transfers import apply_transfer_matches
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    txns = st.all_transactions()
    rule = rt.rule_for(t, st.recurring_transfers(), rt.paydays(txns))
    if rule is None or t.category_source in ("user", "merchant_override"):
        return jsonify({"error": "No recurring rule sorted this one."}), 409
    before = snapshot(st, txns)
    st.write_categories({t.fingerprint: (t.category, "user")})
    # One row, not the rule: the rule stays confirmed.
    _said({"key": rule["id"]}, "not_this", how="row", status="confirmed")
    apply_transfer_matches(st)
    undo = undo_payload(before, snapshot(st, st.all_transactions()))
    return jsonify({"ok": True, "title": "Not recurring: just this one.", "undo": undo})


# What each schedule comes to in a month, on average. Every payday goes by
# how often she's paid.
PER_MONTH = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1.0, "semimonthly": 2.0}


def _paydays_a_month(pays, today) -> float:
    from .income_bills import _cadence_of
    recent = [p for p in pays if p <= today][-8:]
    cadence = _cadence_of(recent) if len(recent) >= 3 else None
    return PER_MONTH.get(cadence or "", 1.0)
# What she called it, for the categories Needs a look offers by name.
WHAT = {category: words for category, words in KINDS.values()}
WHAT["Transfers"] = "Moved to another of my accounts"


@bp.get("/recurring-transfers")
def list_recurring_transfers():
    """Profile › Recurring transfers (2026-10-28): every one she confirmed,
    what it is, its schedule, the next one, and what a month of them comes
    to; and how many Needs a look is still asking about."""
    from datetime import date
    from .profile_api import _base_name
    from .review import for_store
    st = store()
    today = date.fromisoformat(_today_iso())
    nicknames = st.account_nicknames()
    accounts = {a["account_id"]: nicknames.get(a["account_id"])
                or _base_name(a.get("account_name") or a["account_id"]) for a in st.accounts()}
    txns = st.all_transactions()
    pays = rt.paydays(txns)
    out = []
    for r in st.recurring_transfers():
        rows = sorted((t for t in txns if rt.matches(t, r, pays)), key=lambda t: t.date, reverse=True)
        per = _paydays_a_month(pays, today) if r["cadence"] == "payday" else PER_MONTH.get(r["cadence"], 1.0)
        monthly = round(float(r["amount"]) * per, 2)
        nxt = rt.next_after(r, today, pays)
        out.append({
            "id": r["id"], "rule_id": f"recurring:{r['id']}",
            "name": r.get("label") or "Transfer",
            "account": accounts.get(r["account_id"], ""),
            "amount": round(float(r["amount"]), 2), "cadence": r["cadence"],
            "when": rt.when_words(r["cadence"], date.fromisoformat(r["anchor"][:10])),
            "category": r["category"], "what": WHAT.get(r["category"], r["category"]),
            "monthly": monthly,
            "next": nxt.isoformat() if nxt else None,
            "count": len(rows), "last": rows[0].date[:10] if rows else None,
            "transactions": [{"id": t.fingerprint, "date": t.date[:10], "amount": round(t.amount, 2)}
                             for t in rows[:12]],
        })
    asking = len(for_store(st, today=today.isoformat()).get("recurring_transfer") or [])
    return jsonify({"transfers": out, "count": len(out), "asking": asking,
                    "monthly": round(sum(r["monthly"] for r in out), 2)})
