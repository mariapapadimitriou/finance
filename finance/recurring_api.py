"""Recurring transfers (2026-10-27): confirming one from Needs a look, and
the rules on Profile › Categories and rules. See finance/recurring_transfers.py."""

from __future__ import annotations

from flask import jsonify, request

from .api import _today_iso, bp, store
from .categorize import CATEGORIES
from . import recurring_transfers as rt

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
    rule = rt.rule_from(s, category, " ".join(str(body.get("label") or "").split())[:60])
    before = snapshot(st, st.all_transactions())
    was = next((r for r in st.recurring_transfers() if r["id"] == rule["id"]), None)
    st.set_recurring_transfer(rule)
    st.dismiss_review(s["key"])
    apply_transfer_matches(st)
    sorted_now = sum(1 for t in st.all_transactions() if rt.matches(t, rule))
    undo = undo_payload(before, snapshot(st, st.all_transactions()))
    undo["marks"] = {"recurring_transfers": {rule["id"]: was}}
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
    """Stop treating a series as recurring. What it sorted keeps its category."""
    from .transfers import apply_transfer_matches
    st = store()
    rule = next((r for r in st.recurring_transfers() if r["id"] == rule_id), None)
    if rule is None:
        return jsonify({"error": "No such rule."}), 404
    keep = {t.fingerprint: (t.category, "user") for t in st.all_transactions()
            if rt.matches(t, rule) and t.category_source not in ("user", "merchant_override")}
    st.delete_recurring_transfer(rule_id)
    if keep:
        st.write_categories(keep)
    apply_transfer_matches(st)
    return jsonify({"ok": True})
