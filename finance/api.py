"""HTTP API.

Every route is read-only against your local SQLite file except the import,
category and budget endpoints. Nothing here reaches the network apart from the
optional Claude call on the Savings tab and a Plaid sync you configure.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request

from .analytics import (
    share_amount,
    spend_amount,
    summary as build_summary,
)
from .categorize import CATEGORIES, TRAVEL_BANK_CATEGORIES, is_spend_category
from .db import storage_mode
from .insights import detect_recurring, recurring_summary
from .categorize import apply_categories, group_of
from .dedupe import split_new
from . import manual, spend_plan
from .store import Store

bp = Blueprint("api", __name__, url_prefix="/api")


def store() -> Store:
    """The signed-in account's ledger, or the only one when nobody signs in."""
    from flask import g
    user = g.get("user")
    if user is None:
        return current_app.config["STORE"]
    return current_app.config["STORE_FOR"](user)


def _txns():
    return store().all_transactions()


# ── Meta ─────────────────────────────────────────────────────────────────────

@bp.get("/health")
def health():
    # `storage` says how durable this instance's ledger is: on a serverless
    # instance with no database, it lasts only until the instance is recycled.
    return jsonify({
        "ok": True,
        "transactions": len(_txns()),
        "storage": storage_mode(),
    })


@bp.get("/categories")
def categories():
    from .marks import hidden_categories
    hidden = hidden_categories(store())
    return jsonify({
        "categories": [
            # The group (Essentials, Lifestyle…) is what Change category
            # (R-02) lays its chips out by. `hidden` is a category she never
            # uses (Profile › Categories and rules): out of the pickers, but
            # still a category wherever it already is.
            {"name": name, "group": group_of(name), "hidden": name in hidden, **meta}
            for name, meta in CATEGORIES.items()
        ],
        "overrides": store().overrides(),
        "hidden": sorted(hidden),
    })


# ── Transactions ─────────────────────────────────────────────────────────────

# The Category filter's "Not sure" option.
UNSURE_FILTER = "__unsure__"
# Rows you left out, wherever they are.
EXCLUDED_FILTER = "__excluded__"


@bp.get("/transactions")
def transactions():
    from .categorize import is_unsure
    limit = min(int(request.args.get("limit", 200)), 1000)
    offset = int(request.args.get("offset", 0))
    category = request.args.get("category")
    excluded_only = category == EXCLUDED_FILTER
    unsure_only = category == UNSURE_FILTER or excluded_only
    txns, total = store().query_transactions(
        month=request.args.get("month"),
        category=None if unsure_only else category,
        account_id=request.args.get("account"),
        search=request.args.get("q"),
        start=request.args.get("start"),
        end=request.args.get("end"),
        limit=100000 if unsure_only else limit,
        offset=0 if unsure_only else offset,
    )
    if unsure_only:
        # Categories Plaid itself wasn't sure of: worth a second look.
        txns = [t for t in txns if (t.excluded if excluded_only else is_unsure(t))]
        total = len(txns)
        txns = txns[offset:offset + limit]
    rows = []
    for t in txns:
        row = t.to_dict()
        row["logo"] = (t.raw or {}).get("logo_url") or ""
        row["unsure"] = is_unsure(t)
        rows.append(row)
    # Money that paid back a charge says which one, so the row can read
    # "paid back · Uber Eats $80" without the page looking it up.
    charges = {}
    for row in rows:
        cid = row.get("repays")
        if cid:
            if cid not in charges:
                charges[cid] = store().get_transaction(cid)
            c = charges[cid]
            row["repays_merchant"] = c.merchant if c else ""
            row["repays_amount"] = c.amount if c else None
    return jsonify({
        "transactions": rows,
        "total": total,
    })


def _txlist_rows(st, excluded: bool = False, joint: bool = False, everything: bool = False):
    """Every row of yours, described for the transactions list — or, with
    `excluded`, only the rows you left out; with `joint`, only the rows on a
    joint account that are someone else's."""
    from datetime import date as _date
    from . import kinds, marks, txlist
    txns = st.all_transactions()
    ctx = txlist.Context(txns, st.confirmed_categories(), st.notes(),
                         {b.id: b.name for b in st.piggy_banks()}, splits=st.splits(),
                         kinds=kinds.kind_map(st, txns, _date.fromisoformat(_today_iso())),
                         tags=st.tags(), saved_to=st.saved_to(), refunds=st.refunds(),
                         payback_kinds=st.payback_kinds(), names=st.merchant_names(),
                         accounts=marks.account_labels(st), payer=st.payback_people(),
                         recurring=st.recurring_transfers())
    if everything:
        rows = txlist.visible(txns) + txlist.left_out(txns) + txlist.theirs(txns)
    elif excluded:
        rows = txlist.left_out(txns)
    elif joint:
        rows = txlist.theirs(txns)
    else:
        rows = txlist.visible(txns)
    return [(t, txlist.describe(t, ctx)) for t in rows]


@bp.get("/transactions/list")
def transactions_list():
    """The transactions list (THL-122): one page of rows and the totals above.

    Filters combine: month (YYYY-MM), account, group (essentials, lifestyle,
    income, savings, transfer) or category, counts (spending | income | none)
    and q, which searches merchant, description, your note and amount.
    excluded=1 lists the rows you left out instead, and joint=1 the rows on a
    joint account that are someone else's; recurring=1 keeps only the
    subscriptions' charges. The totals cover every
    matching row, not just the page.
    """
    from . import txlist
    from .categorize import CATEGORY_GROUPS
    a = request.args
    group = (a.get("group") or "").lower() or None
    if group and group not in CATEGORY_GROUPS and group not in ("fixed", "variable"):
        return jsonify({"error": "Unknown group."}), 400
    try:
        limit = max(1, min(int(a.get("limit", txlist.PAGE)), 1000))
        offset = max(0, int(a.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit and offset are numbers."}), 400
    month = a.get("month") or None
    counts = a.get("counts") or None
    if counts not in (None, "spending", "income", "none"):
        return jsonify({"error": "counts is spending, income or none."}), 400

    def _amount(key):
        raw = a.get(key)
        if raw in (None, ""):
            return None
        try:
            return round(abs(float(raw)), 2)
        except ValueError:
            return None

    filters = {"month": month, "account": a.get("account") or None, "group": group,
               "category": a.get("category") or None, "counts": counts,
               "q": a.get("q") or None, "tag": a.get("tag") or None,
               "merchant": a.get("merchant") or None,
               "amount_min": _amount("amount_min"), "amount_max": _amount("amount_max"),
               "pending": a.get("pending") in ("1", "true"),
               "look": a.get("look") in ("1", "true"),
               "day": a.get("day") or None,
               "first": a.get("first") or None, "last": a.get("last") or None}
    st = store()
    rows = _txlist_rows(st, excluded=a.get("excluded") in ("1", "true"),
                        joint=a.get("joint") in ("1", "true"))
    # "Priya owes you $194.20 for 2 purchases" (WW-01), and the rows behind it.
    owed = txlist.owed([t for t, _ in rows], st.splits(), st.payback_people())
    if a.get("owed") in ("1", "true"):
        filters["ids"] = set(owed["ids"]) if owed else set()
    if a.get("recurring") in ("1", "true"):
        # "Review subscriptions" (THL-63, R3): the subscriptions' charges only.
        from datetime import date as _date
        from .recommendations import subscription_records
        charges = {(r["merchant"], d)
                   for r in subscription_records([t for t, _ in rows],
                                                 _date.fromisoformat(_today_iso()))
                   for d in r["dates"]}
        rows = [(t, r) for t, r in rows if (t.merchant, t.date[:10]) in charges]
    # Needs a look is the review's own set (2026-10-22), whatever the month,
    # so the filter shows the same number as the badge; and a dashed chip
    # only ever marks one of them.
    from .review import for_store, ids_in
    looking = ids_in(for_store(st))
    rows = [(t, r if not r.get("suggested") or r["id"] in looking else {**r, "suggested": False,
                                                                       "chip": {**(r.get("chip") or {}), "suggested": False}})
            for t, r in rows]
    if filters["look"]:
        filters["ids"] = looking if "ids" not in filters else (filters["ids"] & looking)
        filters["look"] = False
        for k in ("month", "day", "first", "last"):
            filters[k] = None
    chosen = txlist.select(rows, **filters)
    # The month's cards stay the month's when Spent or Came in filters the
    # list (2026-10-26): what counts is a view of the rows, not of the totals.
    whole = txlist.select(rows, **{**filters, "counts": None}) if filters.get("counts") else chosen
    # A transfer between two of her accounts is one line, not two (2026-10-22).
    from .transfers import transfer_pairs
    pairs = transfer_pairs(st.all_transactions(), today=_today_iso())
    every = chosen      # the totals keep both ends: money moved, nothing counted
    chosen = txlist.collapse_transfers(chosen, pairs)
    filters.pop("ids", None)
    by = a.get("by") or "day"
    if by not in ("day", "merchant", "category"):
        return jsonify({"error": "by is day, merchant or category."}), 400
    out = {
        "transactions": [r for _, r in chosen[offset:offset + limit]] if by == "day" else [],
        "owed": owed,
        "total": len(chosen),
        "totals": txlist.totals(every),
        "month_totals": txlist.totals(whole),
        # ALT-04: the Outflows and Inflows cards.
        "flows": txlist.flows(rows, filters, _date_today()),
        "focus": txlist.focus(rows, month=month, account=filters["account"],
                              group=group, category=filters["category"],
                              tag=filters["tag"], merchant=filters["merchant"]),
        # Copies waiting for "Is this the same purchase?" (THL-165 D-01).
        "duplicates": sum(1 for _, r in rows
                          if (r.get("duplicate") or {}).get("state") == "pending"),
        "groups": CATEGORY_GROUPS,
        "kinds": {"fixed": "Fixed", "variable": "Variable"},
        # Her tags, for the filter (every row, not just the month's), with
        # what each comes to (VF-02).
        "tags": [g["tag"] for g in txlist.tag_totals(rows)],
        "tag_totals": txlist.tag_totals(rows),
        "by": by,
    }
    # By merchant or by category (VF-01): the rows under headers, the whole
    # selection (capped), so "I didn't know I spent that much at X" shows up.
    if by != "day":
        out["groups_of"] = txlist.grouped(chosen[:500], by)
    return jsonify(out)


@bp.get("/transactions/<txn_id>")
def transaction_detail(txn_id: str):
    """One row as the list describes it, for the detail panel — with, for a
    split charge, who owes what (S-04), and for money in, the split it
    probably pays back and the others it could (S-02, S-03)."""
    from . import splits as sp
    st = store()
    rows = _txlist_rows(st, everything=True)
    for t, r in rows:
        if t.fingerprint != txn_id:
            continue
        txns = [x for x, _ in rows]
        splits, payer = st.splits(), st.payback_people()
        r = dict(r)
        # U-03: when it was left out, and a usual month of its group.
        from .transactions_extras_api import one_off_line
        r["one_off_line"] = one_off_line(st, txns, t)
        split = splits.get(txn_id)
        if split and t.amount > 0:
            r["splitting"] = {
                "mode": split["mode"], "watch": split["watch"],
                "you": round(t.my_share if t.my_share is not None else t.amount, 2),
                "people": sp.people_status(t, split, txns, payer),
            }
        if t.amount > 0:
            r["repaid_by"] = [dict(_txn_brief(x), person=payer.get(x.fingerprint))
                              for x in txns if x.repays == txn_id]
        # The other end of a transfer between her accounts (2026-10-22).
        from .transfers import transfer_pairs
        from .txlist import _is_card_payment as txlist_card_payment
        pairs = transfer_pairs(st.all_transactions(), today=_today_iso())
        back = {arr: out for out, arr in pairs.items()}
        other_id = pairs.get(txn_id) or back.get(txn_id)
        other = next((x for x, xr in rows if x.fingerprint == other_id), None) if other_id else None
        if other is not None:
            orow = next(xr for x, xr in rows if x.fingerprint == other_id)
            r["transfer"] = {"from": r.get("account", "") if txn_id in pairs else orow.get("account", ""),
                             "to": orow.get("account", "") if txn_id in pairs else r.get("account", ""),
                             "other_id": other_id, "other_date": other.date[:10]}
            if (r.get("chip") or {}).get("label") == "Transfer" and not txlist_card_payment(t):
                r["note"] = "Transfer between your accounts · not counted"
        if t.repays:
            charge = next((x for x in txns if x.fingerprint == t.repays), None)
            if charge is not None:
                r["repays_charge"] = dict(_txn_brief(charge),
                                          person=payer.get(txn_id))
        elif t.amount < 0 and not t.excluded:
            options, by_name = sp.for_inflow(t, txns, splits, payer)
            r["repayment"] = {"suggestion": sp.suggest(t, txns, splits, payer),
                              "splits": options, "from_sender": by_name}
        return jsonify(r)
    return jsonify({"error": "No such transaction."}), 404


@bp.put("/transactions/<txn_id>/split")
def set_transaction_split(txn_id: str):
    """Split a charge with people, evenly or by amount (S-01). Your part
    becomes your share, so only it counts anywhere; each other person's
    part is a repayment to watch for."""
    from . import splits as sp
    body = request.get_json(silent=True) or {}
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if t.amount <= 0 or t.repays:
        return jsonify({"error": "Only a charge can be split."}), 400
    if t.joint:
        return jsonify({"error": "On a joint account, say whose it was instead."}), 400
    mode = body.get("mode")
    people, problem = sp.validate(t, mode, body.get("people"))
    if problem:
        return jsonify({"error": problem}), 400
    from .categorize import CATEGORIES, is_unsure
    from .impact import snapshot, undo_payload
    category = body.get("category")
    if category is not None and category not in CATEGORIES:
        return jsonify({"error": "Choose a category."}), 400
    before = snapshot(st, st.all_transactions())
    was = {"split": st.splits().get(txn_id), "share": t.my_share if t.share_set else None}
    st.set_split(txn_id, mode, people, bool(body.get("watch", True)))
    st.set_share(txn_id, sp.your_part(t, people))
    # Split from the sort card (2026-10-23): a split is an answer, so the
    # category it counts toward is settled too — the one she picked, or the
    # guess it already had — and it stops being asked about.
    if category or (body.get("settle") and (is_unsure(t) or (t.category or "Other") in ("Other", "Unsorted transfers"))):
        st.set_transaction_category(txn_id, category or t.category or "Other")
    out = transaction_detail(txn_id)
    data = out.get_json() if hasattr(out, "get_json") else None
    if isinstance(data, dict):
        undo = undo_payload(before, snapshot(st, st.all_transactions()))
        undo["marks"] = {"splits": {txn_id: was}}
        return jsonify(dict(data, undo=undo))
    return out


@bp.delete("/transactions/<txn_id>/split")
def clear_transaction_split(txn_id: str):
    """It was all mine after all: the split goes, and the whole charge counts."""
    st = store()
    if st.get_transaction(txn_id) is None:
        return jsonify({"error": "No such transaction."}), 404
    st.clear_split(txn_id)
    st.set_share(txn_id, None)
    return transaction_detail(txn_id)


@bp.put("/transactions/<txn_id>/confirm")
def confirm_transaction(txn_id: str):
    """"Yes, that's right": the category stops being a suggestion, and the
    review queue stops asking about it."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    already = st.confirmed_categories().get(txn_id) == (t.category or "Other")
    st.confirm_category(txn_id, t.category or "Other")
    st.dismiss_review("cat:" + txn_id)
    # Undo takes it back to a question (2026-10-23): without this, Undo on
    # "Yes, Groceries" did nothing and the card left Needs a look.
    return jsonify({"ok": True, "category": t.category or "Other",
                    "undo": None if already else {"rows": [], "unconfirm": [txn_id]}})


@bp.delete("/transactions/<txn_id>/confirm")
def unconfirm_transaction(txn_id: str):
    store().unconfirm_category(txn_id)
    return jsonify({"ok": True})


@bp.put("/transactions/<txn_id>/note")
def set_transaction_note(txn_id: str):
    """Your private note on a transaction; empty removes it."""
    from .txlist import NOTE_MAX
    st = store()
    if st.get_transaction(txn_id) is None:
        return jsonify({"error": "No such transaction."}), 404
    note = " ".join(str((request.get_json(silent=True) or {}).get("note") or "").split())
    if len(note) > NOTE_MAX:
        return jsonify({"error": f"A note is {NOTE_MAX} characters at most."}), 400
    st.set_note(txn_id, note)
    return jsonify({"ok": True, "note": note})


# ── Changing a category, and what it did (THL-123) ─────────────────────────

def _safe_left(st, txns) -> float:
    """Safe to spend: what is left of this week, as Allowance shows it."""
    from datetime import date as _date
    month = _date.today().isoformat()[:7]
    amount, _ = _allowance(st, txns)
    return spend_plan.compute(txns, amount, month,
                              covered=st.covered_in(month))["week"]["left"]


def _month_spent(txns, month: str) -> float:
    """Spent in a month, as the transactions list totals it."""
    from .analytics import counts_as_spending
    return round(sum(spend_amount(t) for t in txns
                     if t.date[:7] == month and counts_as_spending(t)), 2)


def _month_name(month: str) -> str:
    from datetime import date as _date
    return _date.fromisoformat(month + "-01").strftime("%B")


def _impact(st, before_txns, after_txns, cat_from: str, cat_to: str, month: str) -> dict:
    from .impact import describe
    return describe(_safe_left(st, before_txns), _safe_left(st, after_txns),
                    cat_from, cat_to, _month_spent(before_txns, month),
                    _month_spent(after_txns, month), _month_name(month))


def _merchant_rows(t, txns) -> list:
    """The rows "Apply to all from <merchant>" re-files: the same name, and
    the same Plaid merchant under another spelling (as `set_override` does).
    Not names that merely start the same (2026-10-24): a rule is for one name."""
    key = (t.merchant or "").strip().lower()
    names = [x for x in txns if (x.merchant or "").strip().lower() == key]
    entities = {(x.raw or {}).get("merchant_entity_id") for x in names} - {None, ""}
    return names + [x for x in txns if x not in names and x.category_source != "user"
                    and (x.raw or {}).get("merchant_entity_id") in entities]


@bp.post("/transactions/<txn_id>/category/preview")
def preview_category(txn_id: str):
    """What choosing this category would do, before it is saved: the line
    under the chips on Change category. Nothing is written."""
    from dataclasses import replace
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    if not category or category not in CATEGORIES:
        return jsonify({"error": "A valid category is required."}), 400
    st = store()
    txns = st.all_transactions()
    t = next((x for x in txns if x.fingerprint == txn_id), None)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    rows = _merchant_rows(t, txns)
    ids = {x.fingerprint for x in rows} if body.get("apply_to_merchant") else {txn_id}
    after = [replace(x, category=category, category_source="user")
             if x.fingerprint in ids else x for x in txns]
    out = _impact(st, txns, after, t.category or "Other", category, t.date[:7])
    return jsonify(dict(out, merchant=t.merchant, merchant_count=len(rows)))


@bp.patch("/transactions/<txn_id>")
def update_transaction(txn_id: str):
    from .impact import snapshot, undo_payload
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    if not category or category not in CATEGORIES:
        return jsonify({"error": "A valid category is required."}), 400

    st = store()
    txn = st.get_transaction(txn_id)
    if txn is None:
        return jsonify({"error": "No such transaction."}), 404
    before_txns = st.all_transactions()
    before = snapshot(st, before_txns)

    # "Apply to merchant" is what makes correction worth doing once rather than
    # every month: it teaches the categorizer permanently.
    from .categorize import is_generic_transfer_name
    if body.get("apply_to_merchant") and not is_generic_transfer_name(txn.merchant):
        updated = st.set_override(txn.merchant, category)
        out = {"ok": True, "updated": updated, "scope": "merchant",
               "merchant": txn.merchant}
    else:
        st.set_transaction_category(txn_id, category)
        out = {"ok": True, "updated": 1, "scope": "transaction"}
    # A joint deposit she gave a category to is hers (2026-10-25): "Who put
    # this in?" is answered, and it counts.
    from .joint import claim_deposit
    claimed: dict = {}
    claim_deposit(st, txn, claimed)
    after_txns = st.all_transactions()
    out["impact"] = _impact(st, before_txns, after_txns, txn.category or "Other",
                            category, txn.date[:7])
    out["undo"] = undo_payload(before, snapshot(st, after_txns))
    if claimed:
        out["undo"]["marks"] = claimed
    return jsonify(out)


@bp.post("/transactions/undo")
def undo_change():
    """Put back what a change of category did: the rows it re-filed, and any
    rule it wrote ("Apply to all", "Remember where these go"). The body is the
    `undo` a change returned."""
    from .impact import SOURCE
    from .transfers import apply_transfer_matches
    body = request.get_json(silent=True) or {}
    rows = body.get("rows") or []
    overrides = body.get("overrides") or {}
    dests = body.get("destinations") or {}
    if not isinstance(rows, list) or not isinstance(overrides, dict) \
            or not isinstance(dests, dict) or len(rows) > 5000:
        return jsonify({"error": "Nothing to undo."}), 400
    st = store()
    known = {t.fingerprint for t in st.all_transactions()}
    changes = {}
    for r in rows:
        if not isinstance(r, dict):
            return jsonify({"error": "Nothing to undo."}), 400
        rid, cat, src = r.get("id"), r.get("category"), r.get("source")
        if rid not in known or cat not in CATEGORIES or not isinstance(src, str) \
                or not SOURCE.fullmatch(src):
            return jsonify({"error": "That change can’t be undone."}), 400
        changes[rid] = (cat, src)
    for key, cat in overrides.items():
        if not isinstance(key, str) or len(key) > 200 or (cat is not None and cat not in CATEGORIES):
            return jsonify({"error": "That change can’t be undone."}), 400
    for key, d in dests.items():
        if not isinstance(key, str) or len(key) > 200 or (
                d is not None and (not isinstance(d, dict) or d.get("category") not in CATEGORIES)):
            return jsonify({"error": "That change can’t be undone."}), 400
    # One-offs, duplicate answers and confirmations (THL-71, THL-165, THL-83).
    from .transactions_extras_api import undo_extras
    extra, problem = undo_extras(st, body)
    if problem:
        return jsonify({"error": problem}), 400
    for key, cat in overrides.items():
        st.restore_override(key, cat)
    for key, d in dests.items():
        if d is None:
            st.clear_destination(key)
        else:
            st.set_destination(key, d["category"], str(d.get("label") or "")[:200])
    st.write_categories(changes)
    apply_transfer_matches(st)
    if isinstance(body.get("marks"), dict) and body["marks"].get("income_type"):
        # A kind Pearl had guessed (a bonus, say) comes back as Pearl's
        # guess again, so its question does too (2026-10-26).
        from .income import apply_income_types
        apply_income_types(st)
    return jsonify({"ok": True, "undone": len(changes) + extra})


@bp.put("/transactions/<txn_id>/invested")
def set_transaction_invested(txn_id: str):
    """How much of a transaction went into investments.

    For when only part of it did — a transfer split between an investment
    account and something else. The rest still counts as whatever it is. A
    transaction that was put away in full is categorised Saved
    instead.
    """
    body = request.get_json(silent=True) or {}
    st = store()
    txn = st.get_transaction(txn_id)
    if txn is None:
        return jsonify({"error": "No such transaction."}), 404
    if txn.amount <= 0:
        return jsonify({"error": "Only money going out can be invested."}), 400

    raw = body.get("amount")
    if raw is None or (isinstance(raw, str) and not raw.strip()):
        st.set_invested(txn_id, None)
        return jsonify({"ok": True, "invested": None})
    try:
        amount = round(float(raw), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "The invested amount has to be a number."}), 400
    if amount < 0:
        return jsonify({"error": "The invested amount can't be below zero."}), 400
    if amount > txn.amount + 0.005:
        return jsonify({"error": "You can't invest more than the transaction."}), 400
    st.set_invested(txn_id, amount or None)
    return jsonify({"ok": True, "invested": st.get_transaction(txn_id).invested})


@bp.put("/transactions/<txn_id>/share")
def set_transaction_share(txn_id: str):
    """How much of a charge was yours, when friends paid you back the rest.

    Only your share counts toward your week, your month and your budgets, in
    the month you spent it. Empty or null puts the whole charge back.
    """
    body = request.get_json(silent=True) or {}
    st = store()
    txn = st.get_transaction(txn_id)
    if txn is None:
        return jsonify({"error": "No such transaction."}), 404
    raw = body.get("my_share")
    if txn.joint:
        # On a joint account the share is what says whose it was: the whole
        # of it (yours), nothing (theirs, the default) or part — and that
        # applies to money coming in as much as going out.
        from .transfers import apply_transfer_matches
        rule = ""
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            # "Mine" on a charge from a name she always splits: all hers this
            # once, said outright, or the split would come straight back.
            st.set_share(txn_id, txn.amount if txn.joint_split is not None and txn.amount > 0
                         else None)
        else:
            try:
                share = round(float(raw), 2)
            except (TypeError, ValueError):
                return jsonify({"error": "Your share has to be an amount."}), 400
            if abs(share) > abs(txn.amount) + 0.005 or (share * txn.amount) < 0:
                return jsonify({"error": "Your share has to be between nothing "
                                         "and the whole amount."}), 400
            st.set_share(txn_id, share)
            # Split once, split always (2026-10-26): part of a charge says
            # how she shares that name on this account, so every charge
            # there from it is split the same way, unless she says no.
            part = txn.amount > 0 and 0.005 < share < txn.amount - 0.005
            if part and body.get("always", True) is not False:
                pct = share / txn.amount * 100
                st.set_joint_split(txn.account_id, txn.merchant, pct)
                rule = (f"Every {txn.merchant} charge on this joint account is split "
                        f"this way from now on: {pct:.0f}% yours.")
            elif part or body.get("always") is False:
                st.set_joint_split(txn.account_id, txn.merchant, None)
        apply_transfer_matches(st)
        return jsonify({"ok": True, "my_share": st.get_transaction(txn_id).my_share, "rule": rule})
    if txn.amount <= 0:
        return jsonify({"error": "Only a charge can be split. This is money "
                                 "that came back."}), 400

    if raw is None or (isinstance(raw, str) and not raw.strip()):
        st.set_share(txn_id, None)
        return jsonify({"ok": True, "my_share": None})
    try:
        share = round(float(raw), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "Your share has to be an amount."}), 400
    if share < 0:
        return jsonify({"error": "Your share can't be below zero."}), 400
    if share > txn.amount + 0.005:
        return jsonify({"error": "Your share can't be more than the charge."}), 400
    # The whole charge is the same as no split at all.
    st.set_share(txn_id, None if abs(share - txn.amount) < 0.005 else share)
    # Saying her share answers the row (2026-10-25): its category stops
    # being a question, as a split from the sort card does.
    from .categorize import is_unsure
    if txn.category_source != "user" and (is_unsure(txn) or (txn.category or "Other") == "Other"):
        st.confirm_category(txn_id, txn.category or "Other")
        st.dismiss_review("cat:" + txn_id)
    return jsonify({"ok": True, "my_share": st.get_transaction(txn_id).my_share})


# ── Where transfers went, and who paid you back ──────────────────────────────

def _txn_brief(t) -> dict:
    out = {"id": t.fingerprint, "date": t.date, "merchant": t.merchant,
           "description": t.description, "amount": t.amount,
           "account_id": t.account_id, "account_name": t.account_name or "",
           "category": t.category}
    if t.repays:
        # How much of it paid its charge back (2026-10-26).
        out["paid_part"] = t.paid_part
    return out


@bp.get("/transfers/unsorted")
def unsorted_transfers():
    """Money that left a bank account for somewhere Spendie can't see, waiting
    for you to say whether it was spent or saved. Counted as spent meanwhile.

    Also grouped by who it went to, so twelve e-transfers to one person are
    one decision, not twelve.
    """
    from .review import unsorted_groups
    return jsonify(unsorted_groups(_txns()))


@bp.post("/transfers/sort")
def sort_transfers():
    """Say where transfers went: Saved, a spending category, or Transfers
    (moved between your own accounts). `remember` makes it the rule for those
    names from now on. Says what that did to safe to spend, with an undo."""
    from .impact import snapshot, undo_payload
    from .transfers import apply_transfer_matches
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    ids = [i for i in (body.get("ids") or []) if isinstance(i, str)]
    if category not in CATEGORIES:
        return jsonify({"error": "A valid category is required."}), 400
    if not ids:
        return jsonify({"error": "Nothing to sort."}), 400
    from .transfers import destination
    st = store()
    rows = [t for t in (st.get_transaction(i) for i in ids) if t is not None]
    if not rows:
        return jsonify({"error": "Nothing to sort."}), 404
    before_txns = st.all_transactions()
    before = snapshot(st, before_txns)
    learned = 0
    for t in rows:
        where = destination(t) if body.get("remember") else None
        if where:
            # A rule for where it went, applied only to what matching leaves
            # unmatched — so a transfer whose other end turns up stays neutral.
            st.set_destination(where[0], category, where[1])
            learned += 1
        else:
            st.set_transaction_category(t.fingerprint, category)
    apply_transfer_matches(st)
    after_txns = st.all_transactions()
    first = rows[0]
    return jsonify({"ok": True, "sorted": len(rows), "learned": learned,
                    "impact": _impact(st, before_txns, after_txns,
                                      first.category or "Other", category, first.date[:7]),
                    "undo": undo_payload(before, snapshot(st, after_txns))})


@bp.get("/transfers/saved")
def saved_transfers():
    """What counts as saved over the last few months, so it can be checked
    and undone: transfers marked Saved, and the saved part of anything else."""
    from datetime import date as _date
    try:
        months = max(1, min(int(request.args.get("months", 2)), 24))
    except (TypeError, ValueError):
        months = 2
    d = _date.today().replace(day=1)
    for _ in range(months - 1):
        d = (d - timedelta(days=1)).replace(day=1)
    since = d.isoformat()
    rows = []
    for t in _txns():
        if t.date < since:
            continue
        if t.category == "Saved":
            rows.append(dict(_txn_brief(t), saved=t.amount, part=False))
        elif t.invested:
            rows.append(dict(_txn_brief(t), saved=t.invested, part=True))
    rows.sort(key=lambda r: r["date"], reverse=True)
    return jsonify({"since": since, "rows": rows,
                    "total": round(sum(r["saved"] for r in rows), 2)})


@bp.post("/transactions/<txn_id>/unsort")
def unsort_transaction(txn_id: str):
    """Undo where you said something went.

    If the choice was remembered for its name, the rule goes too and every
    row of that name is sorted afresh; otherwise just this row is. A partly
    saved row loses its saved part. Whatever Spendie would have chosen comes
    back, so a transfer to nowhere it can see is waiting to be sorted again.
    """
    from .categorize import apply_categories
    from .transfers import RULED, apply_transfer_matches, destination
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if t.invested and t.category != "Saved":
        st.set_invested(txn_id, None)
        return jsonify({"ok": True, "undone": 1})
    if t.category_source == RULED:
        where = destination(t)
        if where:
            st.clear_destination(where[0])
        apply_transfer_matches(st)
        return jsonify({"ok": True, "undone": 1,
                        "category": st.get_transaction(txn_id).category})
    key = t.merchant.strip().lower()
    if key in st.overrides():
        st.clear_override(t.merchant)
        rows = [r for r in st.all_transactions() if r.merchant.strip().lower() == key]
    else:
        rows = [t]
    for r in rows:
        if r.category_source in ("user", "merchant_override"):
            r.category_source = "rule"
    apply_categories(rows, st.overrides())
    st.write_categories({r.fingerprint: (r.category, r.category_source) for r in rows})
    apply_transfer_matches(st)
    return jsonify({"ok": True, "undone": len(rows),
                    "category": st.get_transaction(txn_id).category})


# How far either side of a purchase a repayment is looked for: friends often
# pay before a card purchase posts.
_PAYBACK_BEFORE_DAYS = 7
_PAYBACK_AFTER_DAYS = 45
_PAYBACK_NAMES = ("e-transfer", "etransfer", "e-tfr", "etfr", "interac",
                  "transfer", "venmo", "zelle", "wise")


def _payback_candidates(charge, txns) -> list[dict]:
    from datetime import date as _date
    from .splits import bought_on
    start = bought_on(charge)
    remaining = round(charge.amount - (charge.paid_back or 0.0), 2)
    out = []
    for t in txns:
        if t.amount >= 0 or t.repays or t.fingerprint == charge.fingerprint:
            continue
        if t.category not in ("Transfers", "Income", "Other"):
            continue
        gap = (_date.fromisoformat(t.date[:10]) - start).days
        if gap < -_PAYBACK_BEFORE_DAYS or gap > _PAYBACK_AFTER_DAYS:
            continue
        amount = -t.amount
        if amount > remaining + 0.005:
            continue
        name = f"{t.merchant} {t.description}".lower()
        by_name = any(k in name for k in _PAYBACK_NAMES)
        # $20 back on an $80 charge is a quarter: one of four people.
        even = any(abs(charge.amount / n - amount) < 0.51 for n in range(2, 11))
        out.append((0 if by_name else 1, 0 if even else 1, abs(gap), t))
    out.sort(key=lambda r: r[:3])
    return [dict(_txn_brief(t), likely=(a == 0 and b == 0)) for a, b, _, t in out[:12]]


@bp.get("/transactions/<txn_id>/paybacks")
def list_paybacks(txn_id: str):
    st = store()
    charge = st.get_transaction(txn_id)
    if charge is None:
        return jsonify({"error": "No such transaction."}), 404
    txns = st.all_transactions()
    linked = [t for t in txns if t.repays == txn_id]
    return jsonify({
        "charge": _txn_brief(charge),
        "paid_back": round(charge.paid_back or 0.0, 2),
        "share": round(share_amount(charge), 2) if charge.amount > 0 else None,
        "linked": [_txn_brief(t) for t in sorted(linked, key=lambda t: t.date)],
        "candidates": (_payback_candidates(charge, txns)
                       if charge.amount > 0 else []),
    })


@bp.post("/transactions/<txn_id>/paybacks/<inflow_id>")
def add_payback(txn_id: str, inflow_id: str):
    """Say this money coming in was a friend paying you back for that charge.

    The charge then costs you what is left, and the money in counts as
    nothing — not income, not money in — because it was never yours.
    """
    from .transfers import apply_transfer_matches
    st = store()
    charge = st.get_transaction(txn_id)
    inflow = st.get_transaction(inflow_id)
    if charge is None or inflow is None:
        return jsonify({"error": "No such transaction."}), 404
    if charge.amount <= 0:
        return jsonify({"error": "Only a charge can be paid back."}), 400
    if inflow.amount >= 0:
        return jsonify({"error": "Only money coming in can pay back a charge."}), 400
    if inflow.repays and inflow.repays != txn_id:
        return jsonify({"error": "That money already paid back another charge."}), 400
    body = request.get_json(silent=True) or {}
    # Part of it (2026-10-26): how much of the money in paid this back; all
    # of it unless she says less, and the rest counts as money in.
    from .marks import Problem, _payback_part
    try:
        part = _payback_part(inflow, body)
    except Problem as e:
        return jsonify({"error": str(e)}), 400
    paying = part if part is not None else -inflow.amount
    already = (charge.paid_back or 0.0) - (inflow.paid_part if inflow.repays == txn_id else 0.0)
    if already + paying > charge.amount + 0.005:
        return jsonify({"error": "That's more than the charge — friends can't pay "
                                 "back more than it cost."}), 400
    person = body.get("person")
    if person is not None:
        names = [p["name"] for p in (st.splits().get(txn_id) or {}).get("people", [])]
        if person not in names:
            return jsonify({"error": "That person isn't in this split."}), 400
    from .impact import snapshot, undo_payload
    before = snapshot(st, st.all_transactions())
    was = {"charge": inflow.repays, "kind": st.payback_kinds().get(inflow_id),
           "person": st.payback_people().get(inflow_id), "amount": inflow.repays_amount}
    split_was = {}
    if inflow.repays and inflow.repays != txn_id:
        from .splits import drop_payer
        moved = drop_payer(st, inflow)
        if moved is not None:
            split_was[inflow.repays] = moved
    st.link_payback(txn_id, inflow_id, person, part)
    # Never income: Plaid sometimes calls an e-transfer in "income".
    if inflow.category != "Transfers":
        st.set_transaction_category(inflow_id, "Transfers")
    apply_transfer_matches(st)
    out = list_paybacks(txn_id)
    # An Undo for the link (2026-10-23), as every other answer has.
    data = out.get_json() if hasattr(out, "get_json") else None
    if isinstance(data, dict):
        undo = undo_payload(before, snapshot(st, st.all_transactions()))
        undo["marks"] = {"paybacks": {inflow_id: was}, **({"splits": split_was} if split_was else {})}
        return jsonify(dict(data, undo=undo))
    return out


@bp.delete("/transactions/<inflow_id>/refund")
def unlink_refund(inflow_id: str):
    """Forget which purchase a refund is of (2026-10-24). It stays in its
    category, so it still comes off that category's spending, in its month."""
    st = store()
    if st.get_transaction(inflow_id) is None:
        return jsonify({"error": "No such transaction."}), 404
    if inflow_id not in st.refunds():
        return jsonify({"error": "That refund isn't linked to a purchase."}), 404
    st.link_refund(inflow_id, None)
    return transaction_detail(inflow_id)


@bp.delete("/transactions/<txn_id>/paybacks/<inflow_id>")
def remove_payback(txn_id: str, inflow_id: str):
    from .transfers import apply_transfer_matches
    st = store()
    inflow = st.get_transaction(inflow_id)
    if inflow is None or inflow.repays != txn_id:
        return jsonify({"error": "That money isn't linked to this charge."}), 404
    # A payback that made its sender's place in the split takes them out
    # again (THL-260): the charge costs what it did before.
    from .splits import drop_payer
    drop_payer(st, inflow)
    st.unlink_payback(inflow_id)
    apply_transfer_matches(st)
    return list_paybacks(txn_id)


# Plaid's account subtypes, as a person would say them.
_KIND_LABELS = {
    "credit card": "Credit card", "checking": "Chequing", "savings": "Savings",
    "money market": "Savings", "cd": "GIC", "gic": "GIC", "mortgage": "Mortgage",
    "line of credit": "Line of credit", "student": "Student loan",
    "paypal": "PayPal", "prepaid": "Prepaid card",
}
_TYPE_LABELS = {"credit": "Credit card", "depository": "Bank account",
                "investment": "Investment", "brokerage": "Investment",
                "loan": "Loan"}
# A statement format that says nothing about the bank.
_GENERIC_FORMATS = {"csv / statement export", "pdf statement", "plaid", "manual",
                    "empty file", "csv", ""}


def _statement_bank(format_label: str) -> str:
    """The bank a statement format names: "Scotiabank statement (PDF)" →
    "Scotiabank", "American Express" → "American Express"."""
    import re
    name = re.sub(r"\s*\((?:pdf|csv|headerless)\)\s*$", "", format_label or "", flags=re.I)
    name = re.sub(r"\s+statement$", "", name, flags=re.I).strip()
    return "" if name.lower() in _GENERIC_FORMATS else name


def _label_account(row: dict, banks: dict[str, str], imported: dict[str, dict]) -> None:
    """Add what a person needs to tell accounts apart: the bank, what kind of
    account it is, and its last four digits — or, for a statement, the file."""
    import re
    name = row.get("account_name") or ""
    m = re.search(r"••\s*(\d{2,4})\s*$", name)
    row["mask"] = m.group(1) if m else ""
    subtype = (row.get("plaid_subtype") or "").lower()
    ptype = (row.get("plaid_type") or "").lower()
    if row.get("source") == "plaid":
        row["institution"] = banks.get(row.get("item_id") or "", "")
        if ptype == "investment" or subtype in ("tfsa", "rrsp", "fhsa", "resp",
                                                "brokerage", "rrif", "lira"):
            row["kind_label"] = "Investment"
        else:
            row["kind_label"] = (_KIND_LABELS.get(subtype) or _TYPE_LABELS.get(ptype)
                                 or (subtype.title() if subtype else "Account"))
        row["imported_from"] = None
    else:
        imp = imported.get(row.get("account_id") or "") or {}
        row["institution"] = _statement_bank(imp.get("format_label", ""))
        row["kind_label"] = ("Added by hand" if row.get("source") == "manual"
                             else "Card statement")
        row["imported_from"] = imp or None


@bp.put("/accounts/<account_id>/joint")
def set_account_joint(account_id: str):
    """Say an account is shared, and with whom; null says it's yours alone.

    On a joint account, a row that can't be matched to your own accounts is
    another member's — not your spending, income or money in — until you say
    it was yours.
    """
    from .transfers import apply_transfer_matches
    body = request.get_json(silent=True) or {}
    label = body.get("label")
    if label is not None:
        label = " ".join(str(label).split())[:40]
        if not label:
            return jsonify({"error": "Say who it's shared with."}), 400
    st = store()
    st.set_joint(account_id, label)
    apply_transfer_matches(st)
    return jsonify({"ok": True, "joint": label})


@bp.put("/transactions/<txn_id>/mine-always")
def set_mine_always(txn_id: str):
    """On joint accounts, purchases at this name are always yours."""
    body = request.get_json(silent=True) or {}
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    st.set_joint_mine(t.merchant, bool(body.get("on")))
    return jsonify({"ok": True})


@bp.put("/transactions/<txn_id>/party")
def set_transaction_party(txn_id: str):
    """Who an e-Transfer was from or to, when the bank didn't say (or said it
    wrong); an empty name goes back to the bank's."""
    from .etransfers import is_etransfer
    name = " ".join(str((request.get_json(silent=True) or {}).get("name") or "").split())[:60]
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if not is_etransfer(t):
        return jsonify({"error": "Only an e-Transfer has someone it was from or to."}), 400
    st.set_party(txn_id, name or None)
    return jsonify({"ok": True, "name": name or None})


@bp.put("/transactions/<txn_id>/joint-from")
def set_joint_from(txn_id: str):
    """Who put this money into a joint account: "me" (her own money, from an
    account not in Pearl) or "them" (the other person, whose money pays for
    that much of the month's joint spending), or null to ask again.
    `remember` answers for every deposit from that sender too. `person` is
    which of the people she shares the account with put it in."""
    from .joint import ME, THEM
    body = request.get_json(silent=True) or {}
    who = body.get("who")
    if who not in (ME, THEM, None):
        return jsonify({"error": "Say who put it in: you, or the other person."}), 400
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    if not t.joint or t.amount >= 0:
        return jsonify({"error": "Only money into a joint account is asked about."}), 400
    person = " ".join(str(body.get("person") or "").split()) or None
    if person and (who != THEM or person not in t.joint_people):
        return jsonify({"error": "Choose one of the people you share this account with."}), 400
    from .impact import snapshot, undo_payload
    before = snapshot(st, st.all_transactions())
    was = {"who": t.joint_from, "person": t.joint_person}
    st.set_joint_deposit(txn_id, who, person)
    if body.get("remember"):
        st.set_joint_deposit_rule(t.account_id, t.merchant, who, person)
    # Her own money moving between her pockets is never income.
    # Her own money into the joint account is her money moving: a transfer,
    # never income or savings (2026-10-23).
    if who == ME and t.category in ("Income", "Saved", "Other", "Unsorted transfers"):
        st.set_transaction_category(txn_id, "Transfers")
    undo = undo_payload(before, snapshot(st, st.all_transactions()))
    undo["marks"] = {"joint_from": {txn_id: was}}
    return jsonify({"ok": True, "who": who, "person": person, "undo": undo})


@bp.get("/accounts")
def accounts():
    """Every account this app knows about, and whether it syncs.

    Two sets that mostly overlap: accounts with transactions in the ledger,
    and accounts a bank has handed over. An account can be in either alone —
    an imported statement has rows but no bank behind it, and an account
    switched off before its first sync has a decision recorded and no rows.
    Both belong in one list, because the question being asked of it is "what
    is in here, and what keeps arriving", and a list missing the second kind
    cannot answer why a removed account came back.
    """
    st = store()
    from .analytics import currency_mix, ledger_currency
    txns = st.all_transactions()
    return jsonify({
        "accounts": _account_rows(st),
        "currency": ledger_currency(txns),
        # Totals add amounts together, so two currencies in one ledger make
        # every total wrong in a way no label can rescue. Said plainly here
        # rather than silently formatted as whichever is commoner.
        "currency_mix": currency_mix(txns),
    })


def _account_rows(st) -> list[dict]:
    """Every account with rows or a sync decision, labelled, with how it
    counts (AM-02): `counted`, `nickname`, `removed` and her joint share."""
    kinds = st.account_kinds()
    rules = st.account_sync_rules()

    rows = []
    for a in st.accounts():
        kind = kinds.get(a["account_id"], {})
        rule = rules.get(a["account_id"])
        plaid_type = kind.get("type", "") or (rule or {}).get("account_type", "")
        rows.append({
            **a,
            "plaid_type": plaid_type,
            "plaid_subtype": (kind.get("subtype", "")
                              or (rule or {}).get("account_subtype", "")),
            # Only Plaid rows carry a type, so an imported statement is never
            # mislabelled as "not a card" for want of one.
            "is_card": (plaid_type or ("credit" if a.get("source") != "plaid"
                                       else "")) == "credit",
            "syncs": rule["enabled"] if rule else None,
            "decided_by": (rule or {}).get("decided_by", ""),
            "item_id": (rule or {}).get("item_id", ""),
        })

    seen = {a["account_id"] for a in rows}
    for aid, rule in rules.items():
        if aid in seen:
            continue
        rows.append({
            "account_id": aid,
            "account_name": rule["account_name"],
            "transactions": 0,
            "first_date": None,
            "last_date": None,
            "total_spend": 0.0,
            "currency": "",
            "source": "plaid",
            "plaid_type": rule["account_type"],
            "plaid_subtype": rule["account_subtype"],
            "is_card": rule["account_type"] == "credit",
            "syncs": rule["enabled"],
            "decided_by": rule["decided_by"],
            "item_id": rule["item_id"],
        })

    banks = {i["item_id"]: i.get("institution") or "" for i in st.plaid_items()}
    imported = st.imports_by_account()
    joint = st.joint_accounts()
    shares = st.joint_shares()
    people = st.joint_people()
    balances = st.balances()
    settings = st.account_settings()
    for row in rows:
        _label_account(row, banks, imported)
        row["joint"] = joint.get(row["account_id"])
        row["joint_share"] = shares.get(row["account_id"])
        row["joint_people"] = people.get(row["account_id"], [])
        # What the bank says the account holds (or, for a card, what's owed).
        row["balance"] = balances.get(row["account_id"])
        mine = settings.get(row["account_id"], {})
        row["counted"] = mine.get("counted", True)
        row["nickname"] = mine.get("nickname", "")
        row["removed"] = mine.get("removed", False)
    return rows


@bp.delete("/accounts/<path:account_id>")
def delete_account(account_id: str):
    """Remove an account and everything imported from it.

    Deleting the rows is only half of it for a connected account: the bank
    still holds it, and the next sync fetches the lot again. So removal also
    records that this account is not to be synced, which is what the person
    meant. `stop_syncing=0` deletes the rows and leaves the connection alone.
    """
    st = store()
    known = any(a["account_id"] == account_id for a in st.accounts())
    rules = st.account_sync_rules()
    if not known and account_id not in rules:
        return jsonify({"error": "No such account."}), 404

    stop = request.args.get("stop_syncing", "1") != "0"
    removed = st.clear_transactions(account_id) if known else 0
    if stop:
        st.set_account_sync(account_id, False,
                            name=rules.get(account_id, {}).get("account_name", ""),
                            item_id=rules.get(account_id, {}).get("item_id", ""))
    return jsonify({"ok": True, "removed": removed, "stopped_syncing": stop})


@bp.put("/accounts/<path:account_id>/sync")
def set_account_sync(account_id: str):
    """Turn syncing for one account on or off.

    Recorded as the person's decision, which the per-sync defaults will not
    revise — so switching a chequing account back on survives the next sync,
    and switching a card off survives it too.
    """
    body = request.get_json(silent=True) or {}
    if "enabled" not in body:
        return jsonify({"error": "Send {\"enabled\": true} or false."}), 400

    st = store()
    rule = st.account_sync_rules().get(account_id, {})
    name = rule.get("account_name") or next(
        (a["account_name"] for a in st.accounts()
         if a["account_id"] == account_id), "")
    enabling = bool(body["enabled"]) and not rule.get("enabled", True)
    st.set_account_sync(account_id, bool(body["enabled"]),
                        name=name, item_id=rule.get("item_id", ""))
    # Switched on after being off: its transactions were dropped while it was
    # off and the bank's cursor moved past them, so the next sync has to start
    # from the beginning to bring its history in.
    rewound = False
    if enabling and rule.get("item_id"):
        st.rewind_plaid_cursor(rule["item_id"])
        rewound = True
    return jsonify({"ok": True, "account_id": account_id,
                    "enabled": bool(body["enabled"]), "resync": rewound})


@bp.delete("/transactions")
def clear():
    account = request.args.get("account")
    deleted = store().clear_transactions(account)
    return jsonify({"ok": True, "deleted": deleted})


# ── Analytics ────────────────────────────────────────────────────────────────

@bp.get("/summary")
def summary():
    return jsonify(build_summary(_txns(), store().budgets()))


@bp.get("/recurring")
def recurring():
    found = detect_recurring(_txns())
    return jsonify({"recurring": found, "summary": recurring_summary(found)})


# ── The weekly allowance (spend_plan) ────────────────────────────────────
# The pages that showed it (Today, the Plan, the prototype Projections) are
# gone, but two things still read it: Change category's impact line (R-02,
# `_safe_left`) and Goals' "this month" figure (`_goals_safe_to_spend`). See
# finance/spend_plan.py for the model.

def _plan_month(default_from_data: bool = True) -> str:
    """The month the plan is being asked about. Defaults to the real one."""
    asked = request.args.get("month")
    if asked:
        return asked
    from datetime import date as _d
    return _d.today().strftime("%Y-%m")


def _bank_monthly(st) -> float:
    """What the piggy banks take out of this month, for the plan's arithmetic.

    Includes the catch-up on any bank that has been spent ahead of its funding,
    since that is money genuinely leaving this month.
    """
    from . import piggy
    return piggy.total_monthly(st.piggy_banks(), st.bank_charges_by_month())


def _allowance(st, txns=None) -> tuple[float, bool]:
    """What may be spent day to day this month, and whether the plan set it.

    Derived from the plan every time it is asked for, so the Today tab and the
    Plan tab cannot drift apart: change your income, add a commitment or open a
    piggy bank and the weekly number moves with it.

    Before the plan has an income in it there is nothing to derive, and a brand
    new ledger should still show something, so the fallback is your own median
    discretionary month. The second return value says which of the two you are
    looking at, because a budget taken from last year's spending deserves to be
    labelled as one.
    """
    from . import money_plan

    txns = st.all_transactions() if txns is None else txns
    income = st.float_setting("monthly_income", 0.0)
    if income > 0 and _focus(st) is not None:
        # Once you have split the monthly total yourself, the weekly number is
        # the part of that split that goes to discretionary categories.
        from . import groups as budget_lines
        lines = budget_lines.lines(st.category_groups())
        return money_plan.weekly_pool(st.budgets(), lines, txns), True
    if income > 0:
        amount = money_plan.monthly_allowance(
            income, st.fixed_costs(), st.float_setting("savings_target", 0.0),
            _bank_monthly(st), txns, bank_funded=st.bank_funded_categories())
        if amount > 0:
            return amount, True
    return spend_plan.suggest_monthly_amount(txns), False


def _plan_state(st, month: str) -> dict:
    txns = st.all_transactions()
    amount, _ = _allowance(st, txns)
    return spend_plan.compute(txns, amount, month, covered=st.covered_in(month))


# ── Plaid ────────────────────────────────────────────────────────────────
# The access token never crosses this boundary. Link hands the browser a
# public token, the browser hands it here, and what comes back is an item id.
# See finance/plaid_link.py.

@bp.get("/plaid/items")
def plaid_items():
    from . import plaid_link, secrets_box
    st = store()
    return jsonify({
        "configured": plaid_link.configured(),
        "environment": plaid_link.environment(),
        "encryption_ready": secrets_box.available(),
        "items": st.plaid_items(),
    })


@bp.post("/plaid/link-token")
def plaid_link_token():
    from . import plaid_link, secrets_box
    if not plaid_link.configured():
        return jsonify({"error": "Plaid isn't configured on this deployment."}), 501
    # Checked before Link opens rather than after: finishing the bank login
    # only to be told the token can't be stored would be a wasted trip, and
    # the alternative — storing it unencrypted — is not on the table.
    if not secrets_box.available():
        return jsonify({
            "error": "No encryption key is set, so a bank token can't be "
                     "stored safely. Set SPENDIE_SECRET_KEY and redeploy.",
        }), 503
    # With an item_id, Link opens in update mode to sign in to that bank again
    # (THL-120 C-04); the connection, its accounts and its history stay.
    item_id = str((request.get_json(silent=True) or {}).get("item_id") or "")
    access_token = None
    if item_id:
        access_token = store().plaid_token(item_id)
        if not access_token:
            return jsonify({"error": "That bank isn't linked any more."}), 404
    try:
        return jsonify(plaid_link.create_link_token(access_token=access_token))
    except Exception as exc:                          # noqa: BLE001
        return jsonify({"error": plaid_link.explain(exc),
                        "environment": plaid_link.environment()}), 502


@bp.post("/plaid/exchange")
def plaid_exchange():
    from . import plaid_link, secrets_box
    if not plaid_link.configured():
        return jsonify({"error": "Plaid isn't configured on this deployment."}), 501
    if not secrets_box.available():
        return jsonify({"error": "No encryption key is set."}), 503

    body = request.get_json(silent=True) or {}
    public_token = (body.get("public_token") or "").strip()
    if not public_token:
        return jsonify({"error": "No public_token supplied."}), 400

    try:
        item = plaid_link.exchange_public_token(
            store(), public_token, (body.get("institution") or "").strip())
    except Exception as exc:                          # noqa: BLE001
        return jsonify({"error": plaid_link.explain(exc)}), 502

    # Pull straight away so the card isn't linked-but-empty.
    try:
        synced = plaid_link.sync_all(store())
    except Exception as exc:                          # noqa: BLE001
        return jsonify({**item, "linked": True,
                        "sync_error": str(exc)})
    return jsonify({**item, "linked": True, "sync": synced})


@bp.post("/plaid/sync")
def plaid_sync():
    from . import plaid_link
    if not plaid_link.configured():
        return jsonify({"error": "Plaid isn't configured on this deployment."}), 501
    st = store()
    # Opening the app asks without `force`; linking, reconnecting and
    # switching an account on ask with it.
    if not (request.get_json(silent=True) or {}).get("force") and plaid_link.synced_recently(st):
        # Synced a moment ago, but a bank may still be owed its one-time
        # details refresh (2026-10-22): run just that, not a whole sync.
        refreshed = plaid_link.refresh_details_once(st, st.plaid_items())
        # New sorting rules apply at once, not only after the next full sync.
        from .categorize import RULES_VERSION
        from .pipeline import recategorize_all
        if st.setting("categories_version") != str(RULES_VERSION):
            recategorize_all(st)
            st.set_setting("categories_version", RULES_VERSION)
        return jsonify({"items": [], "imported": 0, "recent": True, "details_refreshed": refreshed})
    return jsonify(plaid_link.sync_all(st))


@bp.delete("/plaid/items/<item_id>")
def plaid_unlink(item_id: str):
    from . import plaid_link
    st = store()
    if not any(i["item_id"] == item_id for i in st.plaid_items()):
        return jsonify({"error": "No such linked bank."}), 404
    revoked = plaid_link.unlink(st, item_id)
    return jsonify({"ok": True, "revoked_at_plaid": revoked})


# ── Manual transactions ──────────────────────────────────────────────────

@bp.post("/transactions")
def add_manual_transaction():
    """Add a purchase by hand, refusing to create a duplicate silently."""
    body = request.get_json(silent=True) or {}

    candidate = manual.build(
        body.get("date", ""), body.get("description", ""), body.get("amount"),
        category=body.get("category", ""),
    )
    if candidate is None:
        return jsonify({"error": "Need a valid date, description and amount."}), 400
    if body.get("category") and body["category"] not in CATEGORIES:
        return jsonify({"error": f"Unknown category '{body['category']}'."}), 400

    st = store()
    existing = st.all_transactions()

    # An exact match is a duplicate outright; anything looser is reported so
    # you can decide, unless you already said to add it anyway.
    new, dupes = split_new([candidate], existing)
    if not new:
        return jsonify({
            "error": "That looks like a transaction already in your ledger.",
            "duplicate": True,
            "matches": manual.find_possible_duplicates(candidate, existing),
        }), 409

    matches = manual.find_possible_duplicates(candidate, existing)
    if matches and not body.get("confirm"):
        return jsonify({
            "needs_confirmation": True,
            "message": "Found something similar already — add it anyway?",
            "matches": matches,
            "preview": {"merchant": candidate.merchant, "date": candidate.date,
                        "amount": candidate.amount},
        }), 409

    if not candidate.category:
        apply_categories([candidate], st.overrides())
    st.add_transactions([candidate])
    if matches and body.get("confirm"):
        # She said it's a different purchase: never ask again (THL-165).
        st.add_duplicate(candidate.fingerprint, matches[0]["id"], state="different")

    return jsonify({"ok": True, "id": candidate.fingerprint,
                    "merchant": candidate.merchant,
                    "category": candidate.category})


@bp.delete("/transactions/<txn_id>")
def delete_transaction(txn_id: str):
    if not store().delete_transaction(txn_id):
        return jsonify({"error": "No such transaction."}), 404
    return jsonify({"ok": True})


# ── Counted accounts ─────────────────────────────────────────────────────────
# The accounts whose balances count (AM-02), for the Anchor, debts and
# Growth › Projections' next 30 days.


def _counted_rules(st) -> dict[str, dict]:
    """The bank accounts whose balances count (AM-02), with the balances
    added by hand (AM-05) beside them as if a bank had reported them."""
    hidden = st.not_counted() | {aid for aid, s in st.account_settings().items()
                                 if s["removed"]}
    rules = {aid: r for aid, r in st.account_sync_rules().items() if aid not in hidden}
    for m in st.manual_accounts():
        if not m["counted"]:
            continue
        rules[m["account_id"]] = {
            "account_id": m["account_id"], "account_name": m["name"], "item_id": "",
            "enabled": True, "decided_by": "user",
            "account_type": "credit" if m["kind"] == "credit" else "depository",
            "account_subtype": "credit card" if m["kind"] == "credit" else m["kind"]}
    return rules


def _counted_balances(st) -> dict[str, dict]:
    """Bank-reported balances, with those added by hand (AM-05)."""
    out = dict(st.balances())
    for m in st.manual_accounts():
        out[m["account_id"]] = {"current": m["balance"], "available": None, "limit": None,
                                "currency": "", "as_of": m["updated_on"]}
    return out


# ── Piggy banks ──────────────────────────────────────────────────────────────
# Annual costs turned into a monthly commitment, and spending charged to them
# instead of to the month it fell in. See finance/piggy.py for the arithmetic.

def _bank_status(st) -> list[dict]:
    """Every bank with its derived figures, biggest contribution first."""
    from . import piggy

    charges = st.bank_charges_by_month()
    owned = st.bank_categories()
    rows = [{**b.to_dict(piggy.status(b, charges.get(b.id, {}))),
             "categories": owned.get(b.id, [])}
            for b in st.piggy_banks()]
    rows.sort(key=lambda r: (-r["monthly"], r["name"]))
    return rows


def _bank_categories(st, body: dict, bank_id: int | None):
    """The categories a bank form asked for, or the error to send back.

    `None` with no error means the form did not say, so nothing changes.
    """
    from . import groups as budget_lines

    if "categories" not in body:
        return None, None
    wanted = body.get("categories") or []
    if not isinstance(wanted, list) or not all(isinstance(c, str) for c in wanted):
        return None, "Categories must be a list of names."
    wanted = sorted({c.strip() for c in wanted if c.strip()})

    allowed = set(budget_lines.spend_categories())
    for category in wanted:
        if category not in allowed:
            return None, f"'{category}' is not spending a bank can pay for."

    names = {b.id: b.name for b in st.piggy_banks()}
    for other, categories in st.bank_categories().items():
        if other == bank_id:
            continue
        taken = [c for c in wanted if c in categories]
        if taken:
            return None, (f"{', '.join(taken)} {'is' if len(taken) == 1 else 'are'} "
                          f"already paid for by your {names.get(other, 'other')} "
                          "bank. A category can belong to one bank.")

    # A budget line holds either categories a bank pays for or ones with a
    # budget, never both — see groups.validate. Checked against the
    # ownership this change would leave.
    funded = {c for other, cats in st.bank_categories().items()
              if other != bank_id for c in cats} | set(wanted)
    _, error = budget_lines.validate(st.category_groups(), funded)
    if error:
        return None, error + " Choose the whole line instead."
    return wanted, None


def _travel_last_year(txns) -> float:
    """What travel cost over the last twelve months the ledger covers.

    Gross, not netted against a bank: this is the size of the cost a bank
    would have to be collecting for, which is the question being asked of it.
    """
    recent = set(sorted({t.month for t in txns})[-12:])
    return round(sum(share_amount(t) for t in txns if t.month in recent
                     and t.amount > 0 and (t.category or "") == "Travel"), 2)


def _suggested_bank(txns, banks: list) -> dict | None:
    """The bank to offer when there is not one yet.

    Travel, because it is the category the budget deliberately has no line
    for: its share is excluded from the split on the understanding that a
    bank is collecting for it instead. Offering anything else first would
    leave the one cost the plan does not cover uncovered.

    The target comes from her own last year of travel, rounded up to a round
    number, because a figure she can recognise is one she can correct. With
    no travel in the ledger there is nothing to suggest and the field is left
    empty rather than filled with a number from nowhere.
    """
    import math

    if banks:
        return None
    annual = _travel_last_year(txns)
    target = int(math.ceil(annual / 100.0) * 100) if annual >= 240 else None
    return {"name": "Travel", "cadence": "annual",
            "target": target, "annual_spend": annual,
            "categories": list(TRAVEL_BANK_CATEGORIES)}


@bp.get("/piggy")
def list_banks():
    st = store()
    rows = _bank_status(st)
    return jsonify({
        "banks": rows,
        "monthly_total": round(sum(r["monthly"] for r in rows), 2),
        "balance_total": round(sum(r["balance"] for r in rows), 2),
        # What opening one costs the month, so the Plan tab's leftover and this
        # page quote the same figure.
        "income": st.float_setting("monthly_income", 0.0),
        # The first bank anyone should open, prefilled from their own history.
        "suggested": _suggested_bank(st.all_transactions(), rows),
        "bank_funded": sorted(st.bank_funded_categories()),
        # What a bank can be told to pay for: any spending category.
        "spend_categories": _spend_categories(),
    })


def _spend_categories() -> list[str]:
    from . import groups as budget_lines
    return budget_lines.spend_categories()


@bp.post("/piggy")
def add_bank():
    from . import piggy

    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    cadence = str(body.get("cadence") or piggy.ANNUAL)
    target_date = (str(body.get("target_date")).strip()
                   if body.get("target_date") else None)
    try:
        target = float(body.get("target", 0))
        opening = float(body.get("opening", 0) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Amounts must be numbers."}), 400

    error = piggy.validate(name, target, cadence, target_date)
    if error:
        return jsonify({"error": error}), 400
    if opening < 0:
        return jsonify({"error": "What is already set aside cannot be negative."}), 400
    if opening > target:
        return jsonify({"error": "That is already more than the target. "
                                 "Raise the target, or lower what is set aside."}), 400

    from datetime import date as _d
    st = store()
    if any(b.name.lower() == name.lower() for b in st.piggy_banks()):
        return jsonify({"error": f"You already have a piggy bank called {name}."}), 400
    categories, error = _bank_categories(st, body, None)
    if error:
        return jsonify({"error": error}), 400

    from . import anchor as anchor_math
    today = _d.fromisoformat(_today_iso())
    # A treasure chest fills from the Anchor on the 1st (THL-230): one
    # started today (`from: next_first`, the Save page) takes its first
    # amount on the next 1st, unless today is the 1st. A piggy bank opened
    # the older way still starts this month.
    start = today.strftime("%Y-%m")
    if body.get("from") == "next_first" and today.day != 1:
        start = anchor_math.add_months(start, 1)
    bank_id = st.add_piggy_bank(
        name, target, cadence, target_date if cadence == piggy.ONCE else None,
        start, opening, str(body.get("note") or ""))
    if categories is not None:
        st.set_bank_categories(bank_id, categories)
    return jsonify({"ok": True, "id": bank_id})


@bp.patch("/piggy/<int:bank_id>")
def edit_bank(bank_id: int):
    from . import piggy

    body = request.get_json(silent=True) or {}
    st = store()
    bank = st.piggy_bank(bank_id)
    if bank is None:
        return jsonify({"error": "No such piggy bank."}), 404

    name = str(body.get("name", bank.name)).strip()
    cadence = str(body.get("cadence") or bank.cadence)
    target_date = body.get("target_date", bank.target_date)
    target_date = str(target_date).strip() if target_date else None
    try:
        target = float(body.get("target", bank.target))
        opening = float(body.get("opening", bank.opening) or 0)
    except (TypeError, ValueError):
        return jsonify({"error": "Amounts must be numbers."}), 400

    # A bank already past its date keeps that date on an unrelated edit:
    # re-validating it would reject renaming a trip you have come back from.
    check_date = target_date if target_date != bank.target_date else None
    error = piggy.validate(name, target, cadence,
                           target_date if cadence == piggy.ONCE else None,
                           today=None if check_date else bank.start_month + "-01")
    if error:
        return jsonify({"error": error}), 400
    if any(b.name.lower() == name.lower() and b.id != bank_id
           for b in st.piggy_banks()):
        return jsonify({"error": f"You already have a piggy bank called {name}."}), 400
    categories, error = _bank_categories(st, body, bank_id)
    if error:
        return jsonify({"error": error}), 400

    st.update_piggy_bank(bank_id, name, target, cadence,
                         target_date if cadence == piggy.ONCE else None,
                         opening, str(body.get("note", bank.note) or ""))
    if categories is not None:
        st.set_bank_categories(bank_id, categories)
    return jsonify({"ok": True})


@bp.delete("/piggy/<int:bank_id>")
def remove_bank(bank_id: int):
    """Close a bank, putting whatever was charged to it back into its months."""
    st = store()
    charged = st.charged_to_banks().get(bank_id, 0.0)
    if not st.delete_piggy_bank(bank_id):
        return jsonify({"error": "No such piggy bank."}), 404
    return jsonify({"ok": True, "released": round(charged, 2)})


@bp.post("/piggy/<int:bank_id>/allocate")
def allocate_to_bank(bank_id: int):
    """Charge a transaction to a bank, which pays it whether or not it can yet.

    The whole charge leaves the month. A $2,000 trip against a travel fund
    holding $200 leaves the fund $1,800 behind, and it repays itself out of the
    months ahead by raising its own contribution — so the trip does come off
    each month's target, which is the point of having declared it.

    Capping the charge at the balance was the obvious-looking alternative and
    it fails the case the feature exists for: the month you take the trip is
    exactly the month that must not absorb it.
    """
    from . import piggy

    body = request.get_json(silent=True) or {}
    txn_id = str(body.get("txn_id", "")).strip()
    if not txn_id:
        return jsonify({"error": "Which transaction?"}), 400

    st = store()
    bank = st.piggy_bank(bank_id)
    if bank is None:
        return jsonify({"error": "No such piggy bank."}), 404
    txn = st.get_transaction(txn_id)
    if txn is None:
        return jsonify({"error": "No such transaction."}), 404
    if txn.amount <= 0:
        return jsonify({"error": "Only a charge can come out of a piggy bank. "
                                 "A refund or a payment is money coming back."}), 400

    st.allocate(txn_id, bank_id, txn.amount)
    played = piggy.status(bank, st.bank_charges_by_month().get(bank_id, {}))
    return jsonify({
        "ok": True,
        "charge": round(txn.amount, 2),
        # The whole charge leaves the month, whatever the bank holds. What is
        # worth reporting is what the bank has left this year.
        "covered": round(txn.amount, 2),
        "available": played["available"],
        "over": played["over"],
        "behind_by": played["behind_by"],
        "monthly": played["monthly"],
        "base_monthly": played["base_monthly"],
        "caught_up_by": played["caught_up_by"],
        "behind": played["behind"],
        "bank": bank.name,
    })


@bp.delete("/piggy/allocations/<txn_id>")
def unallocate_from_bank(txn_id: str):
    """Put a charge back into the month it happened in."""
    if not store().unallocate(txn_id):
        return jsonify({"error": "That charge isn't allocated to a piggy bank."}), 404
    return jsonify({"ok": True})


@bp.delete("/piggy/draws/<int:draw_id>")
def undo_draw(draw_id: int):
    """Put back money a bank lent the month.

    Asking "can I buy this?" used to take the money out there and then, before
    anything was bought. It no longer does; this undoes the ones it took.
    """
    if not store().delete_draw(draw_id):
        return jsonify({"error": "No such draw."}), 404
    return jsonify({"ok": True})


# ── Goals: the Anchor, treasure chests and the saving goal ──────────────────
# The Save page (Pearl Handoff, THL-131, THL-132, THL-179; THL-229/THL-230).
# The Anchor is the cash savings she picks, less what her treasure chests
# hold; chests are the piggy banks above under the name the page gives them,
# filling from the Anchor each month; the saving goal is the plan's. See
# finance/anchor.py.

# Plaid subtypes the Anchor can count. Chequing is offered but unticked: it is
# everyday spending, usually best left out. Investment accounts aren't offered.
_ANCHOR_SAVINGS = {"savings", "money market", "hsa", "cash management"}
_ANCHOR_CHEQUING = {"checking", "chequing", "prepaid", "paypal"}


def _date_today():
    from datetime import date as _d
    return _d.fromisoformat(_today_iso())


def _today_iso() -> str:
    from datetime import date as _d
    return _d.today().isoformat()


def _json_setting(st, key: str, default):
    import json
    raw = st.setting(key)
    if raw in (None, ""):
        return default
    try:
        return json.loads(raw)
    except (TypeError, ValueError):
        return default


def _unusual_months(st) -> set[str]:
    """Months she left out of her usual (THL-59): a move, a car repair. One
    list, read by the Anchor's pace, the usual month (Home's snapshot,
    budgets) and Growth › Insights."""
    return set(_json_setting(st, "anchor_unusual", []))


def _anchor_accounts(st) -> list[dict]:
    """Accounts the Anchor could count, with what each holds now: linked
    savings and chequing accounts, and savings accounts added by hand
    (AM-10's "Part of my Anchor")."""
    import re
    balances = _counted_balances(st)
    hand = {m["account_id"]: m for m in st.manual_accounts()}
    out = []
    for aid, rule in _counted_rules(st).items():
        ptype = (rule["account_type"] or "").lower()
        subtype = (rule["account_subtype"] or "").lower()
        if ptype != "depository" and subtype not in _ANCHOR_SAVINGS | _ANCHOR_CHEQUING:
            continue
        held = (balances.get(aid) or {}).get("current")
        if held is None:
            continue
        name = rule["account_name"]
        m = re.search(r"••\s*(\d{2,4})\s*$", name)
        by_hand = hand.get(aid)
        out.append({
            "account_id": aid,
            "name": rule.get("label") or name,
            "mask": (by_hand.get("last4") or "") if by_hand else (m.group(1) if m else ""),
            "kind": "savings" if subtype in _ANCHOR_SAVINGS else "chequing",
            "balance": round(float(held), 2),
            "suggested": subtype in _ANCHOR_SAVINGS,
            "source": "hand" if by_hand else "linked",
        })
    out.sort(key=lambda a: (a["kind"] != "savings", a["name"].lower()))
    return out


def _chests_held(st, rows: list[dict] | None = None) -> float:
    """What the treasure chests hold now, together (never below nothing)."""
    rows = _bank_status(st) if rows is None else rows
    return round(sum(max(r["held"], 0.0) for r in rows), 2)


def _anchor(st, txns, today: str) -> dict:
    """Everything the Anchor card, its detail and its projection need
    (THL-230): the picked savings less what the chests hold, how many months
    of Essentials that covers, and when it is likely to cover three."""
    from . import anchor as anchor_math
    from .analytics import invested_in
    from .growth_insights import chest_monthly

    available = _anchor_accounts(st)
    chosen = set(_json_setting(st, "anchor_accounts", []))
    started = st.setting("anchor_started") not in (None, "") or bool(chosen)
    counting = [a for a in available if a["account_id"] in chosen]
    savings = sum(a["balance"] for a in counting)
    banks = _bank_status(st)
    chests = _chests_held(st, banks)
    unusual = _unusual_months(st)
    suggestion = anchor_math.essentials(txns, today, unusual=unusual)
    usual = suggestion["amount"] if suggestion else None
    earned = st.setting("anchor_earned_on") not in (None, "")
    status = anchor_math.status(savings, chests, usual, earned)
    # Three months is reached once: the first time it is, say so for good.
    if started and status["full"] and not earned:
        st.set_setting("anchor_earned_on", today)

    charges = st.bank_charges_by_month()
    piggy_banks = st.piggy_banks()

    def chests_took(month: str) -> float:
        return chest_monthly(piggy_banks, charges, month) / 100.0

    months = anchor_math.saved_by_month(txns, today, chests_by_month=chests_took)
    pace = anchor_math.pace(months, unusual)
    projection = anchor_math.projection(status["to_go"], pace, today) if started else None
    if projection and projection["state"] == "none":
        from .insights.recurring import detect_recurring, recurring_summary
        projection["subscriptions_monthly"] = round(
            recurring_summary(detect_recurring(txns))["monthly_total"], 2)

    return {
        "started": started,
        "started_on": st.setting("anchor_started") or None,
        "earned_on": st.setting("anchor_earned_on") or None,
        "accounts": sorted(chosen),
        **status,
        "counting": counting,
        "available_accounts": available,
        "suggestion": suggestion,
        "pace_months": [{**m, "unusual": m["month"] in unusual} for m in months[:6]],
        "unusual": sorted(unusual),
        "pace": pace,
        "projection": projection,
        "recent": anchor_math.recent_saves(txns),
        # This month so far, for the hero's "+$300 this month": transfers
        # marked Saved, less any taken back out.
        "saved_this_month": invested_in(txns, today[:7]) if started else 0.0,
        # What the chests take from the Anchor each month now.
        "chests_monthly": round(chests_took(today[:7]), 2),
    }


def _chest(row: dict) -> dict:
    """A piggy bank as the Goals page shows it: a treasure chest.

    What is in it is what has been set aside less what it has paid for, never
    shown below nothing. It is ready to open once that reaches the target.
    Ready by is the date for a dated chest, and the end of its year for one
    that comes round every year.
    """
    held = max(row["held"], 0.0)
    target = row["target"]
    # Before its first 1st a chest takes nothing yet; the card still says what
    # it will take, never "$0 a month".
    monthly = row["monthly"] if row["monthly"] > 0.005 else row["base_monthly"]
    ready_by = (row["target_date"][:7] if row["cadence"] == "once" and row["target_date"]
                else row["year_end"])
    return {
        "id": row["id"],
        "name": row["name"],
        "target": target,
        "cadence": row["cadence"],
        "target_date": row["target_date"],
        "start_month": row["start_month"],
        "opening": row["opening"],
        "monthly": round(monthly, 2),
        "base_monthly": row["base_monthly"],
        "catch_up": row["catch_up"],
        "catching_up": row["catch_up"] > 0.005,
        "caught_up_by": row["caught_up_by"],
        "held": round(held, 2),
        "to_go": round(max(target - held, 0.0), 2),
        "share": round(min(held / target, 1.0), 4) if target > 0 else 0.0,
        "ready": target > 0 and held >= target - 0.005,
        "ready_by": ready_by,
        "categories": row.get("categories", []),
    }


@bp.get("/home")
def home():
    """What the bare Home draws (2026-10-21), and the month's numbers behind
    the rest of the app: safe to spend, the usual month, savings so far,
    how many transactions need a look, and any bank connection that needs
    her. The path, wins, calendar strip, carry-over question, cards, budgets
    and snapshot that the old Home drew are gone with it.
    """
    from datetime import date as _date
    from . import milestones, safe_to_spend, savings, usual_month, weekly

    st = store()
    today = _date.fromisoformat(_today_iso())
    txns = st.all_transactions()
    told_income = st.float_setting("home_income", 0.0)
    told_rent = st.float_setting("home_rent", 0.0)
    debts = _debts(st, txns, today)
    sts = _home_sts(st, txns, today, debts)
    types = {aid: r.get("account_type") or ""
             for aid, r in st.account_sync_rules().items() if r.get("enabled")}
    failed = any(i.get("last_error") for i in st.plaid_items())
    state = safe_to_spend.home_state(
        txns, today, sts, account_types=types, linking_failed=failed,
        told_income=told_income, told_rent=told_rent)
    from . import kinds as kinds_mod
    kinds = kinds_mod.kind_map(st, txns, today)
    usual = usual_month.usual(txns, today, unusual=_unusual_months(st), kinds=kinds)
    from .review import for_store
    review = for_store(st)
    return jsonify({
        "month": today.strftime("%Y-%m"),
        "today": today.isoformat(),
        "safe_to_spend": sts,
        "data_state": state,
        "review_count": review.get("count", 0),
        "savings": savings.this_month(st, txns, today),
        "connections": milestones.connections(st.plaid_items(), st.account_sync_rules()),
        "usual_month": usual,
        "week": weekly.week(txns, today, sts),
        "debts": debts,
        # Insights' "For you" cards and the usual-month snapshot read here too.
        "recommendations": _recommendations(st, txns, today, sts, usual),
        "snapshot": usual_month.snapshot(
            txns, today, sts, usual,
            comparisons_from=state["comparisons_from"],
            saved=savings.put_away_month(st, txns, today.strftime("%Y-%m")), kinds=kinds),
    })


def _home_sts(st, txns, today, debts: dict | None = None) -> dict:
    """Safe to spend this month, from the ledger and what she told us, with
    debt minimums among the bills (THL-49 D1, D2)."""
    from . import carryover, debts as debt_math, income_bills, safe_to_spend, savings
    debts = debts if debts is not None else _debts(st, txns, today)
    return safe_to_spend.compute(
        txns, today,
        entered_income=st.float_setting("monthly_income", 0.0),
        told_income=st.float_setting("home_income", 0.0),
        told_rent=st.float_setting("home_rent", 0.0),
        overridden=bool(_json_setting(st, "income_overrides", [])),
        debt_bills=debt_math.bills(debts["debts"], txns, today,
                                   safe_to_spend.recurring_bills(txns, today)),
        confirm=income_bills.load(st),
        carry=carryover.applied(st, today),
        moved_to_savings=savings.put_away_month(st, txns, today.strftime("%Y-%m")),
    )


def _recommendations(st, txns, today, sts: dict, usual: dict) -> list[dict]:
    """Up to two cards (THL-12 E08), the biggest yearly impact first."""
    from . import anchor as anchor_math, recommendations as rec
    anchor = _anchor(st, txns, today.isoformat())
    chequing = {a["account_id"]: a["balance"] for a in _anchor_accounts(st)
                if a["kind"] == "chequing"}
    income = next((r for r in sts.get("rows", []) if r["key"] == "income"), None)
    essentials = anchor_math.essentials(txns, today.isoformat())
    cards = [
        rec.trend(txns, today, usual),
        rec.subscriptions(txns, today),
        rec.pace(anchor, (income or {}).get("paycheques") or 1),
        rec.idle(anchor, rec.lowest_balance(chequing, txns, today),
                 essentials["average"] if essentials else None),
    ]
    return rec.choose(cards, _json_setting(st, "rec_dismissed", {}), today)


@bp.put("/recommendations/<kind>/dismiss")
def dismiss_recommendation(kind):
    """ "Not for me" (THL-62): hide this type for 30 days."""
    import json
    from . import recommendations as rec
    if kind not in rec.TYPES:
        return jsonify({"error": "No such suggestion."}), 404
    st = store()
    dismissed = _json_setting(st, "rec_dismissed", {})
    dismissed[kind] = _today_iso()
    st.set_setting("rec_dismissed", json.dumps(dismissed))
    return jsonify({"type": kind, "hidden_until": _hidden_until(dismissed[kind])})


@bp.delete("/recommendations/<kind>/dismiss")
def undo_dismiss_recommendation(kind):
    """Undo on the toast: show this type again."""
    import json
    from . import recommendations as rec
    if kind not in rec.TYPES:
        return jsonify({"error": "No such suggestion."}), 404
    st = store()
    dismissed = _json_setting(st, "rec_dismissed", {})
    dismissed.pop(kind, None)
    st.set_setting("rec_dismissed", json.dumps(dismissed))
    return jsonify({"type": kind, "hidden_until": None})


def _hidden_until(on: str) -> str:
    from datetime import date as _date, timedelta
    from . import recommendations as rec
    return (_date.fromisoformat(on) + timedelta(days=rec.DISMISS_DAYS)).isoformat()


def _debts(st, txns, today) -> dict:
    """Every debt (THL-49), with the rate and minimum she added (D-03)."""
    from . import debts as debt_math
    return debt_math.build(_counted_rules(st), _counted_balances(st), st.first_balances(),
                           txns, _json_setting(st, "debt_details", {}), today)


def _category_budgets(st, txns, today, sts: dict, usual: dict | None = None,
                      comparisons_from: str | None = None) -> dict:
    """Budgets per category (THL-168), from her usual month and the % she set."""
    from . import category_budgets, usual_month
    usual = (usual if usual is not None
             else usual_month.usual(txns, today, unusual=_unusual_months(st)))
    bills = next((r["lines"] for r in sts.get("rows", []) if r["key"] == "bills"), [])
    return category_budgets.build(txns, today, usual, _json_setting(st, "category_budgets", {}),
                                  bills, comparisons_from)


@bp.get("/category-budgets")
def category_budgets_page():
    """B-01: every budget this month, largest first."""
    from datetime import date as _date
    from . import safe_to_spend, usual_month
    st = store()
    today = _date.fromisoformat(_today_iso())
    txns = st.all_transactions()
    sts = _home_sts(st, txns, today)
    covered = usual_month.covered_months(txns, today, unusual=_unusual_months(st))
    starts = None
    if not covered:
        state = safe_to_spend.home_state(txns, today, sts,
                                         told_income=st.float_setting("home_income", 0.0),
                                         told_rent=st.float_setting("home_rent", 0.0))
        starts = state.get("comparisons_from")
    return jsonify(_category_budgets(st, txns, today, sts, comparisons_from=starts))


@bp.put("/category-budgets")
def set_category_budget():
    """B-02: one budget as a percent of usual, 50% to 150% in 5% steps (B3).
    100% clears it back to the usual month."""
    import json
    from . import category_budgets

    body = request.get_json(silent=True) or {}
    category = str(body.get("category") or "").strip()
    pct = body.get("pct")
    if not category:
        return jsonify({"error": "Choose a category."}), 400
    if isinstance(pct, bool) or not category_budgets.valid_pct(pct):
        return jsonify({"error": "Choose a share of usual from 50% to 150%, in steps of 5%."}), 400
    st = store()
    pcts = _json_setting(st, "category_budgets", {})
    if int(pct) == 100:
        pcts.pop(category, None)
    else:
        pcts[category] = int(pct)
    st.set_setting("category_budgets", json.dumps(pcts))
    return category_budgets_page()


@bp.get("/debts")
def debts_page():
    """D-02: every debt, the total, and this month's minimums."""
    from datetime import date as _date
    st = store()
    return jsonify(_debts(st, st.all_transactions(), _date.fromisoformat(_today_iso())))


@bp.put("/debts/<account_id>")
def debt_details(account_id):
    """D-03: the rate, minimum and due day the bank doesn't share. Each can
    be cleared by sending it empty."""
    import json
    from . import debts as debt_math

    st = store()
    rule = st.account_sync_rules().get(account_id)
    if not rule or not debt_math.kind_of(rule):
        return jsonify({"error": "That account isn't one Pearl sees as a debt."}), 404
    body = request.get_json(silent=True) or {}
    details = _json_setting(st, "debt_details", {})
    entry = dict(details.get(account_id) or {})
    limits = {"rate": (0, 100, "Enter the interest rate as a percent, like 5.7."),
              "minimum": (0, 1_000_000, "Enter the minimum payment, like 120."),
              "due_day": (1, 31, "Enter the day of the month it's due, from 1 to 31.")}
    for key, (low, high, message) in limits.items():
        if key not in body:
            continue
        raw = body[key]
        if raw in (None, ""):
            entry.pop(key, None)
            continue
        try:
            value = float(str(raw).replace("%", "").replace("$", "").replace(",", ""))
        except ValueError:
            return jsonify({"error": message, "field": key}), 400
        if not low <= value <= high or (key == "due_day" and value != int(value)):
            return jsonify({"error": message, "field": key}), 400
        entry[key] = int(value) if key == "due_day" else round(value, 2)
    if entry:
        details[account_id] = entry
    else:
        details.pop(account_id, None)
    st.set_setting("debt_details", json.dumps(details))
    return debts_page()


FOCUS_KEY = "budget_focus"


def _focus(st) -> list[str] | None:
    """The budget lines you chose to focus on, or None before you have.

    None is the state before setup: the plan's own split still drives the
    weekly number until you have divided the monthly total yourself.
    """
    import json

    raw = st.setting(FOCUS_KEY)
    if raw is None:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return [v for v in value if isinstance(v, str)] if isinstance(value, list) else None


# ── Exclusions ───────────────────────────────────────────────────────────────
# Leave a transaction out, or every transaction like it. An exclusion is your
# decision and wins over every rule; excluded rows stay listed and can be put
# back. See finance/exclusions.py.

def _reclassify(st) -> None:
    from .pipeline import classify_ledger
    classify_ledger(st)


@bp.put("/transactions/<txn_id>/exclude")
def exclude_transaction(txn_id: str):
    st = store()
    if st.get_transaction(txn_id) is None:
        return jsonify({"error": "No such transaction."}), 404
    body = request.get_json(silent=True) or {}
    reason = " ".join(str(body.get("reason") or "").split())[:200]
    if not reason:
        return jsonify({"error": "Say why, so you can tell later."}), 400
    st.exclude(txn_id, reason)
    _reclassify(st)
    return jsonify({"ok": True, "transaction": st.get_transaction(txn_id).to_dict()})


@bp.delete("/transactions/<txn_id>/exclude")
def include_transaction(txn_id: str):
    st = store()
    if not st.include(txn_id):
        t = st.get_transaction(txn_id)
        if t is not None and t.account_id in st.not_counted():
            return jsonify({"error": "This account isn’t in your budget. You can count "
                                     "it again from Profile › Accounts."}), 409
        return jsonify({"error": "That transaction isn't excluded."}), 404
    _reclassify(st)
    return jsonify({"ok": True, "transaction": st.get_transaction(txn_id).to_dict()})


@bp.get("/exclusions")
def list_exclusions():
    st = store()
    rules = st.exclusion_rules()
    if any(r.get("account_id") for r in rules):
        names = {}
        for t in st.all_transactions():
            names.setdefault(t.account_id, t.account_label)
        for r in rules:
            r["account_name"] = names.get(r.get("account_id") or "", r.get("account_id"))
    return jsonify({"rules": rules})


@bp.post("/exclusions")
def add_exclusion():
    """A rule for every transaction like this, now and later. `?dry=1` says
    how many it would catch without saving it."""
    from .exclusions import clean, matching
    st = store()
    rule, problem = clean(request.get_json(silent=True) or {})
    if problem:
        return jsonify({"error": problem}), 400
    txns = st.all_transactions()
    caught = [t for t in matching(rule, txns)]
    if request.args.get("dry"):
        return jsonify({"matches": len(caught),
                        "total": round(sum(abs(t.amount) for t in caught), 2),
                        "sample": [_txn_brief(t) for t in caught[:5]]})
    rule_id = st.add_exclusion_rule(rule)
    _reclassify(st)
    return jsonify({"ok": True, "id": rule_id, "matches": len(caught)}), 201


@bp.delete("/exclusions/<int:rule_id>")
def delete_exclusion(rule_id: int):
    st = store()
    if not st.delete_exclusion_rule(rule_id):
        return jsonify({"error": "No such rule."}), 404
    _reclassify(st)
    return jsonify({"ok": True})


# ── Income types ─────────────────────────────────────────────────────────────

@bp.put("/transactions/<txn_id>/income-type")
def set_income_type(txn_id: str):
    from .income import KINDS
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    kind = (request.get_json(silent=True) or {}).get("kind")
    if kind not in KINDS:
        return jsonify({"error": "Choose a kind of income."}), 400
    from .impact import snapshot, undo_payload
    before = snapshot(st, st.all_transactions())
    was = t.income_type if t.income_type_source == "user" else None
    if t.category != "Income":
        # Calling something a gift or a paycheque makes it income.
        st.set_transaction_category(txn_id, "Income")
    st.set_income_type(txn_id, kind, "user")
    from .joint import claim_deposit
    claimed: dict = {}
    claim_deposit(st, t, claimed)
    _reclassify(st)
    undo = undo_payload(before, snapshot(st, st.all_transactions()))
    undo["marks"] = {"income_type": {txn_id: was}, **claimed}
    return jsonify({"ok": True, "transaction": st.get_transaction(txn_id).to_dict(), "undo": undo})


# ── Review ───────────────────────────────────────────────────────────────────

@bp.get("/review")
def review_queue():
    from .review import for_store
    return jsonify(for_store(store()))


@bp.post("/review/dismiss")
def dismiss_review():
    key = str((request.get_json(silent=True) or {}).get("key") or "")
    if not key or ":" not in key:
        return jsonify({"error": "Which item?"}), 400
    store().dismiss_review(key)
    return jsonify({"ok": True})


@bp.post("/review/skip")
def skip_review():
    """Needs a look's "Skip for now" (THL-213): into Skipped, kept between
    visits; `{"skip": false}` puts it back in the queue."""
    body = request.get_json(silent=True) or {}
    key = str(body.get("key") or "")
    if not key or ":" not in key:
        return jsonify({"error": "Which item?"}), 400
    store().skip_review(key, body.get("skip", True) is not False)
    return jsonify({"ok": True})


# The Profile pages, Growth › Insights and Growth › Projections register on this
# blueprint too; imported last so they can use the helpers above.
from . import income_bills_api, insights_api, privacy_api, profile_api  # noqa: E402,F401,I001
from . import marks_api, ranges_api, transactions_extras_api  # noqa: E402,F401
from . import calendar_api, quick_sort_api  # noqa: E402,F401
from . import recurring_api  # noqa: E402,F401
