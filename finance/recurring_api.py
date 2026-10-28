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


# What each schedule comes to in a month, on average.
PER_MONTH = {"weekly": 52 / 12, "biweekly": 26 / 12, "monthly": 1.0}
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
    out = []
    for r in st.recurring_transfers():
        rows = sorted((t for t in txns if rt.matches(t, r)), key=lambda t: t.date, reverse=True)
        monthly = round(float(r["amount"]) * PER_MONTH.get(r["cadence"], 1.0), 2)
        out.append({
            "id": r["id"], "rule_id": f"recurring:{r['id']}",
            "name": r.get("label") or "Transfer",
            "account": accounts.get(r["account_id"], ""),
            "amount": round(float(r["amount"]), 2), "cadence": r["cadence"],
            "when": rt.when_words(r["cadence"], date.fromisoformat(r["anchor"][:10])),
            "category": r["category"], "what": WHAT.get(r["category"], r["category"]),
            "monthly": monthly,
            "next": rt.next_after(r, today).isoformat(),
            "count": len(rows), "last": rows[0].date[:10] if rows else None,
            "transactions": [{"id": t.fingerprint, "date": t.date[:10], "amount": round(t.amount, 2)}
                             for t in rows[:12]],
        })
    asking = len(for_store(st, today=today.isoformat()).get("recurring_transfer") or [])
    return jsonify({"transfers": out, "count": len(out), "asking": asking,
                    "monthly": round(sum(r["monthly"] for r in out), 2)})
