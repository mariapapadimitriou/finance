"""HTTP API.

Every route is read-only against your local SQLite file except the import,
category and budget endpoints. Nothing here reaches the network apart from the
optional Claude call on the Savings tab and a Plaid sync you configure.
"""

from __future__ import annotations

from datetime import timedelta

from flask import Blueprint, current_app, jsonify, request

from .analytics import (
    bill_categories,
    bills_paid,
    share_amount,
    spend_amount,
    budget_status,
    by_category,
    by_merchant,
    daily_series,
    fixed_vs_discretionary,
    month_over_month,
    month_pace,
    monthly_totals,
    summary as build_summary,
    weekday_profile,
)
from .categorize import (CATEGORIES, TRAVEL_BANK_CATEGORIES, is_discretionary,
                         is_spend_category)
from .db import storage_mode
from .ingest import all_sources, get_source, parse_csv, parse_statement
from .insights import (detect_recurring, findings_summary, generate_findings,
                       observe, recurring_summary)
from .pipeline import ingest, recategorize_all
from .categorize import apply_categories
from .dedupe import split_new
from .trips import apply_trips
from .trips import summarize, validate
from . import manual, projections, spend_plan
from .store import Store

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


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
    # `storage` is what the Import tab reads before it promises anything: on a
    # serverless instance with no database, an upload survives only until that
    # instance is recycled, and the UI has to say so rather than let it vanish
    # quietly an hour later.
    return jsonify({
        "ok": True,
        "transactions": len(_txns()),
        "storage": storage_mode(),
    })


@bp.get("/sources")
def sources():
    return jsonify({
        "sources": [s.status().to_dict() for s in all_sources()],
    })


@bp.get("/categories")
def categories():
    return jsonify({
        "categories": [
            {"name": name, **meta} for name, meta in CATEGORIES.items()
        ],
        "overrides": store().overrides(),
    })


def _category_groups_payload(st) -> dict:
    from . import groups as budget_lines

    grouping = st.category_groups()
    lines = budget_lines.lines(grouping)
    funded = st.bank_funded_categories()
    return {
        "groups": grouping,
        "categories": budget_lines.spend_categories(),
        "lines": [
            {"name": name, "members": members,
             "bank_funded": budget_lines.line_bank_funded(members, funded),
             "daily": budget_lines.line_daily(members)}
            for name, members in lines.items()
        ],
        # Named lines that are not categories — the ones you made up — so the
        # picker can offer them as somewhere to put a category.
        "named": sorted({p for p in grouping.values() if p not in CATEGORIES}),
    }


@bp.get("/category-groups")
def get_category_groups():
    """Which categories share a budget line."""
    return jsonify(_category_groups_payload(store()))


@bp.put("/category-groups")
def set_category_groups():
    """Replace the grouping, carrying saved budgets across.

    Folding lines together adds their saved budgets, so a figure tuned by hand
    survives regrouping. See `groups.carry_budgets` for what happens when a
    line is broken up.
    """
    from . import groups as budget_lines

    body = request.get_json(silent=True) or {}
    st = store()
    proposed = body.get("groups", body)
    owners = {c: bank_id for bank_id, cats in st.bank_categories().items()
              for c in cats}

    # Joining a line a piggy bank pays for means the bank pays for this too:
    # putting Lodging under Travel is saying the hotel is part of the trip.
    # Decided before validating, so the line checks as all bank-paid; written
    # only once it has passed, so a refused grouping changes nothing.
    adopted: dict[str, int] = {}
    if isinstance(proposed, dict):
        # A named line ("Trips") belongs to the bank paying for what is in it.
        line_owner = {p: owners[c] for c, p in proposed.items()
                      if isinstance(p, str) and c in owners}
        for category, parent in proposed.items():
            if not isinstance(parent, str) or category in owners:
                continue
            bank_id = owners.get(parent, line_owner.get(parent))
            if bank_id is not None:
                adopted[category] = bank_id
    funded = set(owners) | set(adopted)

    clean, error = budget_lines.validate(proposed, funded)
    if error:
        return jsonify({"error": error}), 400

    names = {b.id: b.name for b in st.piggy_banks()}
    for bank_id in set(adopted.values()):
        mine = [c for c, b in owners.items() if b == bank_id]
        st.set_bank_categories(bank_id, mine + [c for c, b in adopted.items() if b == bank_id])

    old = st.category_groups()
    carried = budget_lines.carry_budgets(st.budgets(), old, clean, funded)
    st.set_category_groups(clean)
    for key in list(st.budgets()):
        if key not in carried:
            st.set_budget(key, 0)
    for line, amount in carried.items():
        st.set_budget(line, amount)
    return jsonify({"ok": True,
                    "adopted": {c: names.get(b, "") for c, b in adopted.items()},
                    **_category_groups_payload(st)})


# ── Import ───────────────────────────────────────────────────────────────────

@bp.post("/import")
def import_files():
    """Accept CSV or PDF statements.

    Multipart is the real path — PDFs are binary and must not be decoded. The
    JSON form is kept for CSV text and for tests, and accepts base64 for
    binary payloads.
    """
    payloads: list[dict] = []

    if request.files:
        for f in request.files.getlist("files") or list(request.files.values()):
            data = f.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return jsonify({"error": f"{f.filename} exceeds the 25 MB limit."}), 413
            payloads.append({"name": f.filename or "upload", "data": data,
                             "account_name": request.form.get("account_name") or None})
    else:
        body = request.get_json(silent=True) or {}
        for item in body.get("files", []):
            content = item.get("content", "")
            if item.get("encoding") == "base64":
                import base64
                content = base64.b64decode(content)
            payloads.append({
                "name": item.get("name", "upload.csv"),
                "data": content,
                "account_name": item.get("account_name"),
            })

    if not payloads:
        return jsonify({"error": "No files supplied."}), 400

    results = []
    for p in payloads:
        results.append(ingest(store(), _parse_upload(p), filename=p["name"]))

    return jsonify({
        "results": results,
        "imported": sum(r["imported"] for r in results),
        "duplicates": sum(r["duplicates"] for r in results),
    })


def _may_use_bundled() -> bool:
    """The bundled statements are the owner's own card. Nobody else's ledger
    may see or load them; with no sign-in (a local copy) there is only one."""
    from flask import g
    user = g.get("user")
    return user is None or bool(user.owner)


@bp.get("/import/bundled")
def bundled_available():
    """Statement sets shipped with the app, and whether each is already loaded."""
    from seed_data.bundled import available
    if not _may_use_bundled():
        return jsonify({"bundled": []})
    s = store()
    loaded = {a["account_id"] for a in s.accounts()}
    return jsonify({"bundled": [{**b, "loaded": b["account_id"] in loaded}
                                for b in available()]})


@bp.post("/import/bundled")
def bundled_import():
    """Load one shipped statement set into the ledger.

    Separate from the upload route because there is no file to choose: a closed
    card's history is fixed, and the account it belongs to is decided here
    rather than guessed from a filename. Safe to call twice — the rows go
    through the same pipeline as an upload, so the second call finds duplicates
    and inserts nothing.
    """
    from seed_data.bundled import read

    if not _may_use_bundled():
        return jsonify({"error": "These statements belong to another account."}), 403
    key = (request.get_json(silent=True) or {}).get("key", "")
    try:
        text, entry = read(key)
    except KeyError:
        return jsonify({"error": f"No statements are bundled under '{key}'."}), 404
    except FileNotFoundError:
        return jsonify({"error": "The bundled file is missing from this build."}), 410

    result = parse_csv(content=text, filename=entry["file"],
                       account_name=entry["account_name"],
                       account_id=entry["account_id"])
    out = ingest(store(), result, filename=f"{entry['label']} (bundled)")
    return jsonify(out)

def _is_pdf(name: str, data) -> bool:
    if name.lower().endswith(".pdf"):
        return True
    head = data[:5] if isinstance(data, bytes) else data[:5].encode("latin-1", "ignore")
    return head.startswith(b"%PDF")


def _parse_upload(payload: dict):
    """Route an uploaded file to the importer that understands it."""
    name, data = payload["name"], payload["data"]

    if _is_pdf(name, data):
        if isinstance(data, str):
            data = data.encode("latin-1", "ignore")
        return parse_statement(data, filename=name,
                               account_name=payload.get("account_name"))

    text = _decode(data) if isinstance(data, bytes) else data
    return parse_csv(content=text, filename=name,
                     account_name=payload.get("account_name"))


def _decode(data: bytes) -> str:
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            return data.decode(enc)
        except UnicodeDecodeError:
            continue
    return data.decode("utf-8", errors="replace")


@bp.post("/sync/<source_key>")
def sync_source(source_key: str):
    """Pull from a non-CSV source. Returns setup guidance when unconfigured."""
    src = get_source(source_key)
    if src is None:
        return jsonify({"error": f"Unknown source '{source_key}'."}), 404

    status = src.status()
    if not status.available:
        return jsonify({"error": status.detail, "setup": status.to_dict()}), 501

    # Plaid has its own endpoints, which read the stored token rather than
    # taking one from the caller. Routing it here keeps one way to sync and
    # stops this generic path from accepting an arbitrary access token.
    if source_key == "plaid":
        from . import plaid_link
        return jsonify(plaid_link.sync_all(store()))

    body = request.get_json(silent=True) or {}
    try:
        results = src.fetch(**body)
    except (RuntimeError, ValueError) as exc:
        return jsonify({"error": str(exc)}), 502

    out = [ingest(store(), r, filename=f"{source_key} sync") for r in results]
    return jsonify({
        "results": out,
        "imported": sum(r["imported"] for r in out),
        "duplicates": sum(r["duplicates"] for r in out),
    })


@bp.get("/imports")
def imports():
    return jsonify({"imports": store().import_history()})


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


def _txlist_rows(st, excluded: bool = False, everything: bool = False):
    """Every row of yours, described for the transactions list — or, with
    `excluded`, only the rows you left out."""
    from . import txlist
    txns = st.all_transactions()
    ctx = txlist.Context(txns, st.confirmed_categories(), st.notes(),
                         {b.id: b.name for b in st.piggy_banks()})
    if everything:
        rows = txlist.visible(txns) + txlist.left_out(txns)
    else:
        rows = txlist.left_out(txns) if excluded else txlist.visible(txns)
    return [(t, txlist.describe(t, ctx)) for t in rows]


@bp.get("/transactions/list")
def transactions_list():
    """The transactions list (THL-122): one page of rows and the totals above.

    Filters combine: month (YYYY-MM), account, group (essentials, lifestyle,
    income, savings, transfer) or category, counts (spending | income | none)
    and q, which searches merchant, description, your note and amount.
    excluded=1 lists the rows you left out instead. The totals cover every
    matching row, not just the page.
    """
    from . import txlist
    from .categorize import CATEGORY_GROUPS
    a = request.args
    group = (a.get("group") or "").lower() or None
    if group and group not in CATEGORY_GROUPS:
        return jsonify({"error": "Unknown group."}), 400
    try:
        limit = max(1, min(int(a.get("limit", txlist.PAGE)), 200))
        offset = max(0, int(a.get("offset", 0)))
    except ValueError:
        return jsonify({"error": "limit and offset are numbers."}), 400
    month = a.get("month") or None
    filters = {"month": month, "account": a.get("account") or None, "group": group,
               "category": a.get("category") or None, "counts": a.get("counts") or None,
               "q": a.get("q") or None}
    rows = _txlist_rows(store(), excluded=a.get("excluded") in ("1", "true"))
    chosen = txlist.select(rows, **filters)
    return jsonify({
        "transactions": [r for _, r in chosen[offset:offset + limit]],
        "total": len(chosen),
        "totals": txlist.totals(chosen),
        "focus": txlist.focus(rows, month=month, account=filters["account"],
                              group=group, category=filters["category"]),
        "groups": CATEGORY_GROUPS,
    })


@bp.get("/transactions/<txn_id>")
def transaction_detail(txn_id: str):
    """One row as the list describes it, for the detail panel."""
    for t, r in _txlist_rows(store(), everything=True):
        if t.fingerprint == txn_id:
            return jsonify(r)
    return jsonify({"error": "No such transaction."}), 404


@bp.put("/transactions/<txn_id>/confirm")
def confirm_transaction(txn_id: str):
    """"Yes, that's right": the category stops being a suggestion, and the
    review queue stops asking about it."""
    st = store()
    t = st.get_transaction(txn_id)
    if t is None:
        return jsonify({"error": "No such transaction."}), 404
    st.confirm_category(txn_id, t.category or "Other")
    st.dismiss_review("cat:" + txn_id)
    return jsonify({"ok": True, "category": t.category or "Other"})


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


@bp.patch("/transactions/<txn_id>")
def update_transaction(txn_id: str):
    body = request.get_json(silent=True) or {}
    category = body.get("category")
    if not category or category not in CATEGORIES:
        return jsonify({"error": "A valid category is required."}), 400

    txn = store().get_transaction(txn_id)
    if txn is None:
        return jsonify({"error": "No such transaction."}), 404

    # "Apply to merchant" is what makes correction worth doing once rather than
    # every month: it teaches the categorizer permanently.
    if body.get("apply_to_merchant"):
        updated = store().set_override(txn.merchant, category)
        return jsonify({"ok": True, "updated": updated, "scope": "merchant",
                        "merchant": txn.merchant})

    store().set_transaction_category(txn_id, category)
    return jsonify({"ok": True, "updated": 1, "scope": "transaction"})


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
        if raw is None or (isinstance(raw, str) and not raw.strip()):
            st.set_share(txn_id, None)
        else:
            try:
                share = round(float(raw), 2)
            except (TypeError, ValueError):
                return jsonify({"error": "Your share has to be an amount."}), 400
            if abs(share) > abs(txn.amount) + 0.005 or (share * txn.amount) < 0:
                return jsonify({"error": "Your share has to be between nothing "
                                         "and the whole amount."}), 400
            st.set_share(txn_id, share)
        apply_transfer_matches(st)
        return jsonify({"ok": True, "my_share": st.get_transaction(txn_id).my_share})
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
    return jsonify({"ok": True, "my_share": st.get_transaction(txn_id).my_share})


# ── Where transfers went, and who paid you back ──────────────────────────────

def _txn_brief(t) -> dict:
    return {"id": t.fingerprint, "date": t.date, "merchant": t.merchant,
            "description": t.description, "amount": t.amount,
            "account_id": t.account_id, "account_name": t.account_name or "",
            "category": t.category}


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
    """Say where a group of transfers went, in one go. `remember` makes it
    the rule for those names from now on."""
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
    return jsonify({"ok": True, "sorted": len(rows), "learned": learned})


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


# How far either side of a charge a repayment is looked for.
_PAYBACK_BEFORE_DAYS = 3
_PAYBACK_AFTER_DAYS = 45
_PAYBACK_NAMES = ("e-transfer", "etransfer", "e-tfr", "etfr", "interac",
                  "transfer", "venmo", "zelle", "wise")


def _payback_candidates(charge, txns) -> list[dict]:
    from datetime import date as _date
    start = _date.fromisoformat(charge.date[:10])
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
    already = 0.0 if inflow.repays == txn_id else (charge.paid_back or 0.0)
    if already - inflow.amount > charge.amount + 0.005:
        return jsonify({"error": "That's more than the charge — friends can't pay "
                                 "back more than it cost."}), 400
    st.link_payback(txn_id, inflow_id)
    # Never income: Plaid sometimes calls an e-transfer in "income".
    if inflow.category != "Transfers":
        st.set_transaction_category(inflow_id, "Transfers")
    apply_transfer_matches(st)
    return list_paybacks(txn_id)


@bp.delete("/transactions/<txn_id>/paybacks/<inflow_id>")
def remove_payback(txn_id: str, inflow_id: str):
    from .transfers import apply_transfer_matches
    st = store()
    inflow = st.get_transaction(inflow_id)
    if inflow is None or inflow.repays != txn_id:
        return jsonify({"error": "That money isn't linked to this charge."}), 404
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

    from .analytics import currency_mix, ledger_currency

    banks = {i["item_id"]: i.get("institution") or "" for i in st.plaid_items()}
    imported = st.imports_by_account()
    joint = st.joint_accounts()
    balances = st.balances()
    for row in rows:
        _label_account(row, banks, imported)
        row["joint"] = joint.get(row["account_id"])
        # What the bank says the account holds (or, for a card, what's owed).
        row["balance"] = balances.get(row["account_id"])

    txns = st.all_transactions()
    return jsonify({
        "accounts": rows,
        "currency": ledger_currency(txns),
        # Totals add amounts together, so two currencies in one ledger make
        # every total wrong in a way no label can rescue. Said plainly here
        # rather than silently formatted as whichever is commoner.
        "currency_mix": currency_mix(txns),
    })


@bp.post("/reset")
def reset_ledger():
    """Empty the ledger. Irreversible, so it asks for the word in writing."""
    body = request.get_json(silent=True) or {}
    if str(body.get("confirm", "")).strip().lower() != "erase":
        return jsonify({
            "error": 'Type "erase" to confirm. This cannot be undone.',
            "needs_confirmation": True,
        }), 400

    st = store()
    keep_banks = bool(body.get("keep_banks", True))
    before = len(st.all_transactions())
    revoked = 0
    if not keep_banks:
        # Disconnected at Plaid too, not only forgotten here: a connection
        # left live keeps counting against the Plaid plan's limit.
        from . import plaid_link
        for item in st.plaid_items():
            revoked += 1 if plaid_link.unlink(st, item["item_id"]) else 0
    removed = st.reset(keep_banks=keep_banks)
    return jsonify({
        "ok": True,
        "transactions_removed": before,
        "removed": removed,
        "banks_kept": keep_banks,
        "revoked_at_plaid": revoked,
        "note": ("Bank connections kept, and their sync positions rewound so "
                 "the next sync re-fetches everything."
                 if keep_banks else "Bank connections removed too."),
    })


@bp.get("/audit/duplicates")
def audit_duplicates():
    """Rows that may describe the same purchase under two account ids."""
    from . import audit
    return jsonify(audit.report(_txns()))


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


@bp.get("/ledger/start")
def get_ledger_start():
    """The earliest date that counts, and what sits before it."""
    st = store()
    start = st.ledger_start()
    rows = st.all_transactions()
    earlier = [t for t in rows if start and t.date < start]
    return jsonify({
        "start": start,
        "earliest": min((t.date for t in rows), default=None),
        "latest": max((t.date for t in rows), default=None),
        "total": len(rows),
        "before_start": len(earlier),
    })


@bp.put("/ledger/start")
def set_ledger_start():
    """Set the earliest date that counts, and optionally remove what precedes it.

    Two things, because either alone is a trap. Deleting without recording the
    date leaves the next Plaid sync free to backfill the same months straight
    back — a fresh link fetches two years. Recording without deleting leaves
    the rows that prompted it sitting in every total.
    """
    from datetime import date as _date

    body = request.get_json(silent=True) or {}
    raw = str(body.get("start", "")).strip()

    if raw:
        try:
            _date.fromisoformat(raw)
        except ValueError:
            return jsonify({"error": "Send a date as YYYY-MM-DD."}), 400

    st = store()
    st.set_ledger_start(raw)
    removed = st.delete_before(raw) if (raw and body.get("trim")) else 0
    return jsonify({"ok": True, "start": raw, "removed": removed})

@bp.delete("/transactions")
def clear():
    account = request.args.get("account")
    deleted = store().clear_transactions(account)
    return jsonify({"ok": True, "deleted": deleted})


@bp.post("/recategorize")
def recategorize():
    return jsonify({"ok": True, "updated": recategorize_all(store())})


# ── Analytics ────────────────────────────────────────────────────────────────

@bp.get("/summary")
def summary():
    return jsonify(build_summary(_txns(), store().budgets()))


@bp.get("/breakdown")
def breakdown():
    st = store()
    txns = st.all_transactions()
    month = request.args.get("month")
    fixed = st.fixed_costs()
    bills = bill_categories(fixed)
    return jsonify({
        "month": month,
        # Bills the plan already set aside are shown apart from the headline:
        # a mortgage isn't this month's spending to watch.
        "bills": bills_paid(txns, month, fixed) if month and bills else None,
        "split": fixed_vs_discretionary(txns, month),
        "categories": by_category(txns, month),
        "merchants": by_merchant(txns, month, limit=int(request.args.get("limit", 25))),
        "changes": month_over_month(txns, month) if month else [],
        "monthly": monthly_totals(txns),
        "daily": daily_series(txns, int(request.args.get("days", 90))),
        "weekday": weekday_profile(txns),
        "pace": month_pace(txns, month, exclude=bills) if month else None,
    })


@bp.get("/recurring")
def recurring():
    found = detect_recurring(_txns())
    return jsonify({"recurring": found, "summary": recurring_summary(found)})


@bp.get("/insights")
def insights():
    st = store()
    txns = _txns()
    dismissed = st.dismissed()
    findings = generate_findings(txns, dismissed)
    summary = findings_summary(findings)
    profile = _profile(st, txns, summary)
    observations = observe(profile, dismissed)
    # What would be showing if nothing had been hidden, so a hidden insight
    # can be brought back by name rather than by typing its id.
    hidden = []
    if dismissed:
        hidden = ([{"id": f["id"], "title": f["title"]}
                   for f in generate_findings(txns, set()) if f["id"] in dismissed]
                  + [{"id": o["id"], "title": o["title"]}
                     for o in observe(profile, set()) if o["id"] in dismissed])
    return jsonify({
        "findings": findings,
        "summary": summary,
        # Written in advance, shown when they apply. See
        # finance/insights/profile.py — this is what replaced the paid bot.
        "observations": observations,
        "hidden": hidden,
    })


def _profile(st, txns, findings_summary_: dict):
    """Assemble what the pre-written observations are allowed to look at.

    Every figure comes from the function the corresponding tab uses, so an
    observation cannot contradict the page it sends you to.
    """
    from . import money_plan, piggy
    from .analytics import last_complete_month
    from .insights.profile import Profile
    from .insights.recurring import detect_recurring, recurring_summary

    income = st.float_setting("monthly_income", 0.0)
    savings = st.float_setting("savings_target", 0.0)
    fixed = st.fixed_costs()
    bank_monthly = _bank_monthly(st)
    result = money_plan.plan(income, fixed, savings, bank_monthly)
    shares = money_plan.variable_shares(txns, bank_funded=st.bank_funded_categories())
    discretionary = money_plan.discretionary_shares(txns, bank_funded=st.bank_funded_categories())

    allowance, from_plan = _allowance(st, txns)
    last = last_complete_month(txns) or ""
    last_spend = round(sum(spend_amount(t) for t in txns if t.month == last
                           and spend_plan.counts_toward_plan(t)), 2)

    months = sorted({t.month for t in txns})
    travel = _travel_last_year(txns)

    banks = _bank_status(st)

    return Profile(
        income=income,
        fixed_total=result["fixed_total"],
        savings=savings,
        bank_monthly=bank_monthly,
        leftover=result["leftover"],
        daily=round(allowance / money_plan.days_in_month(
            _plan_month()), 2) if allowance > 0 else 0.0,
        months_of_history=len(months),
        last_month=last,
        last_month_discretionary=last_spend,
        # Only compare spending against a budget the plan actually decided. A
        # fallback drawn from past spending would be comparing your history
        # with itself, which can never be over.
        discretionary_budget=allowance if from_plan else 0.0,
        shares=discretionary,
        uncategorised_share=shares.get("Other", 0.0),
        subscriptions_monthly=recurring_summary(
            detect_recurring(txns))["monthly_total"],
        budgets_set=len(st.budgets()),
        banks=banks,
        travel_last_year=travel,
        findings_weighted_annual=findings_summary_.get("weighted_annual", 0.0),
    )


# ── Setting up ───────────────────────────────────────────────────────────────

@bp.get("/setup")
def setup_steps():
    """What is left to set up, from the data the app already has.

    Nothing is stored to track this — every step is true or false because of
    something already in the ledger or the plan, so a step done some other way
    (a bank opened from Transactions, budgets adopted from a notice) ticks
    itself. Two steps are optional and can be skipped: not everyone wants an
    older history trimmed off, and not everyone travels. A skip is kept with
    the dismissed insights, the store that already exists for "not for me".
    """
    st = store()
    skipped = st.dismissed()
    grouping = st.category_groups()
    from . import groups as budget_lines
    lines = budget_lines.lines(grouping)
    funded = st.bank_funded_categories()
    budgeted = {k for k in st.budgets()
                if k in lines and not budget_lines.line_bank_funded(lines[k], funded)}

    steps = [
        {"id": "start", "optional": True,
         "label": "Choose the date your ledger counts from",
         "detail": "Set it before connecting a card — a new connection "
                   "backfills two years, and this keeps the old months out.",
         "done": bool(st.ledger_start()), "tab": "accounts",
         "action": "Choose a date"},
        {"id": "data", "optional": False,
         "label": "Connect a card, or load a statement",
         "detail": "Everything else is worked out from these.",
         "done": bool(st.accounts()), "tab": "banks",
         "action": "Connect"},
        {"id": "income", "optional": False,
         "label": "Enter your take-home pay",
         "detail": "Card statements can't see your pay, so the plan starts here.",
         "done": st.float_setting("monthly_income", 0.0) > 0, "tab": "plan",
         "action": "Enter it"},
        {"id": "commitments", "optional": False,
         "label": "Add rent and your other commitments",
         "detail": "Anything paid by transfer never reaches a card statement.",
         "done": bool(st.fixed_costs()), "tab": "plan",
         "action": "Add them"},
        {"id": "travel", "optional": True,
         "label": "Open a piggy bank for your big spending",
         "detail": "Travel, say: a bank that pays for it keeps the trips "
                   "off your weekly allowance.",
         "done": bool(funded), "tab": "piggy",
         "action": "Open one"},
        {"id": "budgets", "optional": False,
         "label": "Split your monthly total across categories",
         "detail": "Pick the categories to focus on and give each a monthly "
                   "target; together they add up to what the plan leaves.",
         "done": bool(budgeted) and _focus(st) is not None, "tab": "budgets",
         "action": "Set them"},
    ]
    for step in steps:
        step["skipped"] = step["optional"] and f"setup.{step['id']}" in skipped

    outstanding = [s for s in steps if not s["done"] and not s["skipped"]]
    return jsonify({"steps": steps, "remaining": len(outstanding)})


@bp.post("/insights/<insight_id>/dismiss")
def dismiss_insight(insight_id: str):
    store().dismiss(insight_id)
    return jsonify({"ok": True})


@bp.delete("/insights/<insight_id>/dismiss")
def restore_insight(insight_id: str):
    store().undismiss(insight_id)
    return jsonify({"ok": True})


# ── Spend plan: safe to spend, and "how am I doing" ──────────────────────
# See finance/spend_plan.py for the model and why only discretionary spending
# counts toward it.

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


@bp.get("/plan/week")
def plan_week():
    """One week's result, as it finished — the arrows on the Allowance card.

    The same arithmetic as the live card (`spend_plan.compute`), asked as of
    the week's last day, so a past week shows exactly what it ended on.
    Weeks run Monday to Sunday and stop at a month's edge, so the week before
    a month's first one is the previous month's last.
    """
    from datetime import date, timedelta

    try:
        on = date.fromisoformat(request.args.get("on") or "")
    except ValueError:
        return jsonify({"error": "Ask for a date as YYYY-MM-DD."}), 400
    today = date.today()
    if on > today:
        return jsonify({"error": "That week hasn't happened yet."}), 400

    st = store()
    txns = st.all_transactions()
    amount, _ = _allowance(st, txns)
    month = on.strftime("%Y-%m")
    first, last = spend_plan.week_bounds(month, on.day)
    start, end = on.replace(day=first), on.replace(day=last)
    state = spend_plan.compute(txns, amount, month, today=min(end, today),
                               covered=st.covered_in(month))

    earliest = min((t.date for t in txns), default=None)
    before = start - timedelta(days=1)
    live_month = today.strftime("%Y-%m")
    live_first = today.replace(day=spend_plan.week_bounds(live_month, today.day)[0])
    after = end + timedelta(days=1)
    return jsonify({
        "month": month,
        "week": state["week"],
        "remaining": state["remaining"],
        "done": end < today,
        "previous": (before.isoformat()
                     if earliest and before.isoformat() >= earliest else None),
        # Null when the next week is the one under way: the live card has it.
        "next": after.isoformat() if after < live_first else None,
    })


def _derivation(st, txns, allowance: float, from_plan: bool) -> dict:
    """How the Plan tab's leftover becomes Today's weekly number.

    Four terms, in the order they apply. Reporting only the last one is what
    made the two tabs look inconsistent: the Plan's leftover has to cover
    groceries and the other essentials, and the daily allowance deliberately
    does not, so the figures differ by exactly that amount and nothing said so.
    """
    from . import money_plan

    if not from_plan:
        return {"from_plan": False, "fallback": allowance}

    income = st.float_setting("monthly_income", 0.0)
    result = money_plan.plan(income, st.fixed_costs(),
                             st.float_setting("savings_target", 0.0),
                             _bank_monthly(st))
    if _focus(st) is not None:
        saved = st.budgets()
        buffer = round(result["leftover"] - sum(saved.values()), 2)
        budgets = {c: v for c, v in saved.items()}
    else:
        divided = money_plan.split(txns, result["leftover"],
                                   bank_funded=st.bank_funded_categories())
        budgets, buffer = divided["budgets"], divided["buffer"]

    # The categories actually making up the essential half, biggest first,
    # rather than a hardcoded example. The note used to read "groceries,
    # transport" — but Transport is flagged discretionary in categorize.py, so
    # it sits in the other column, and the one explanation on the page whose
    # job is to be auditable named a category that contradicted it.
    essential_categories = [
        c for c, _ in sorted(budgets.items(), key=lambda kv: -kv[1])
        if not is_discretionary(c)
    ]

    return {
        "from_plan": True,
        "income": result["income"],
        "fixed_total": result["fixed_total"],
        "savings": result["savings"],
        "banks": result["banks"],
        # "Yours to spend" on the Plan tab.
        "leftover": result["leftover"],
        # The leftover is essentials + the weekly number + the buffer, which
        # belongs to neither until you assign it.
        "essentials": round(result["leftover"] - buffer - allowance, 2),
        "buffer": buffer,
        "essential_categories": essential_categories,
        "discretionary": allowance,
    }


@bp.get("/plan")
def plan():
    st = store()
    txns = st.all_transactions()
    month = _plan_month()
    state = _plan_state(st, month)

    months_with_data = sorted({t.month for t in txns})
    baseline = None
    prior = [m for m in months_with_data if m < month]
    if prior:
        import statistics
        sums = [round(sum(spend_amount(t) for t in txns
                          if t.month == m and spend_plan.counts_toward_plan(t)), 2)
                for m in prior]
        baseline = round(statistics.median(sums), 2)

    allowance, from_plan = _allowance(st, txns)
    return jsonify({
        "state": state,
        "status": spend_plan.how_am_i_doing(state, baseline),
        "banks": _bank_status(st),
        # Every month's, not just this one: they are only here to be undone,
        # and one from a month ago is still holding money out of its bank.
        "draws": st.draws(),
        "allocated_this_month": st.allocated_in(month),
        # Everything that went out this month — rent, groceries, and what a
        # piggy bank paid for too — net of refunds. The weekly number counts
        # only part of this; this is the whole of it.
        "spent_in_total": round(sum(
            share_amount(t) for t in txns
            if t.month == month and is_spend_category(t.category or "Other")), 2),
        "from_banks": st.allocated_in(month),
        # What's in your bank accounts and owed on your cards right now.
        "position": _position(st),
        # The part of that total that was bills the plan set aside.
        "bills_in_total": bills_paid(txns, month, st.fixed_costs())["paid"],
        # The whole chain from the Plan tab's figure down to the weekly number,
        # so the two pages can be read against each other. They are not the
        # same number and used to look as though they should be: what the Plan
        # calls "yours to spend" has the groceries still in it.
        "derivation": _derivation(st, txns, allowance, from_plan),
        # "Configured" now means the plan can derive the number, rather than
        # that somebody once typed one in. There is no longer anywhere to type
        # one: the Plan tab is the only place a budget is decided.
        "configured": from_plan,
        "has_data_this_month": month in months_with_data,
        "months_with_data": months_with_data,
    })


@bp.post("/plan/simulate")
def simulate_purchase():
    """Can I buy this, and what does it cost me if not."""
    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a number."}), 400
    if amount <= 0:
        return jsonify({"error": "Enter an amount above zero."}), 400

    from . import piggy

    st = store()
    month = _plan_month()
    state = _plan_state(st, month)
    charges = st.bank_charges_by_month()
    pots = [(b, piggy.status(b, charges.get(b.id, {}))["balance"])
            for b in st.piggy_banks()]
    return jsonify(spend_plan.simulate(state, amount, pots))


# ── Projections ──────────────────────────────────────────────────────────

@bp.get("/projections")
def projection():
    st = store()
    txns = st.all_transactions()
    income = st.float_setting("monthly_income", 0.0) or None

    findings = generate_findings(txns, st.dismissed())
    weighted = findings_summary(findings).get("weighted_annual", 0.0)

    # `savings` asks "what if I put this much away" without writing it down.
    # The slider on the tab drags it, and every figure that comes back is from
    # the same arithmetic the saved one would use — the alternative was the
    # browser recomputing a preview, which is how two versions of one sum
    # start disagreeing.
    saved_savings = st.float_setting("savings_target", 0.0)
    savings = saved_savings
    previewing = False
    if request.args.get("savings") is not None:
        try:
            savings = max(float(request.args["savings"]), 0.0)
            previewing = abs(savings - saved_savings) > 0.005
        except (TypeError, ValueError):
            return jsonify({"error": "savings must be a number."}), 400

    # The plan, when there is one. Without it the projection cannot see rent and
    # ends up treating it as money available to save.
    from . import money_plan
    fixed = st.fixed_costs()
    banks = _bank_monthly(st)
    plan = money_plan.plan(income or 0.0, fixed, savings,
                           banks) if income else None

    committed = bill_categories(fixed)
    pace = projections.current_pace(txns, _today_iso(), exclude=committed)
    result = projections.project(txns, income, weighted,
                                 int(request.args.get("months", 12)), plan=plan,
                                 pace=pace)
    # What the slider may ask for: everything that is not already promised.
    # Past this the plan has nothing left to divide, and the weekly number is
    # zero before the month starts.
    result["savings_ceiling"] = round(
        max((income or 0.0) - sum(f.amount for f in fixed) - banks, 0.0), 2)
    result["savings_saved"] = round(saved_savings, 2)
    result["savings_previewing"] = previewing
    target = request.args.get("target")
    if target:
        try:
            result["goal"] = projections.goal_eta(result, float(target))
        except (TypeError, ValueError):
            pass
    # Kept separate from the projection's own `monthly_income`, which may have
    # been inferred from payroll landing on an imported card. This one is the
    # figure you typed, and is null until you do.
    result["configured_income"] = income
    # What actually went into investments this month, beside the saving the
    # plan asks for — whether you put away what you meant to.
    from .analytics import invested_in
    this_month = _today_iso()[:7]
    result["invested_month"] = {"month": this_month,
                                "amount": invested_in(txns, this_month),
                                "saving": round(saved_savings, 2)}
    return jsonify(result)


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
        "credentials": plaid_link.credential_shape(),
        "items": st.plaid_items(),
    })


@bp.post("/plaid/check")
def plaid_check():
    """Does Plaid accept these keys? Answered without creating an Item."""
    from . import plaid_link
    return jsonify(plaid_link.check_credentials())


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
    try:
        return jsonify(plaid_link.create_link_token())
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
    return jsonify(plaid_link.sync_all(store()))


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
    apply_trips([candidate], st.trips())
    st.add_transactions([candidate])

    return jsonify({"ok": True, "id": candidate.fingerprint,
                    "merchant": candidate.merchant,
                    "category": candidate.category})


@bp.delete("/transactions/<txn_id>")
def delete_transaction(txn_id: str):
    if not store().delete_transaction(txn_id):
        return jsonify({"error": "No such transaction."}), 404
    return jsonify({"ok": True})


# ── Trips ────────────────────────────────────────────────────────────────
# Declared date ranges whose spending is reclassified as Travel. See
# finance/trips.py for why this is declared rather than inferred.

# ── The money plan: income, commitments, and what is left ────────────────────

@bp.get("/plan/setup")
def plan_setup():
    """The arithmetic behind the budget, and what it implies per category."""
    from . import money_plan

    st = store()
    txns = st.all_transactions()
    income = st.float_setting("monthly_income", 0.0)
    savings = st.float_setting("savings_target", 0.0)
    fixed = st.fixed_costs()

    banks = _bank_monthly(st)
    result = money_plan.plan(income, fixed, savings, banks)
    shares = money_plan.variable_shares(txns, bank_funded=st.bank_funded_categories())
    divided = money_plan.split(txns, result["leftover"],
                               bank_funded=st.bank_funded_categories())
    historical = divided["typical"]
    typical_total = round(sum(historical.values()), 2)

    stored_rate = st.setting("savings_rate")
    return jsonify({
        **result,
        # What actually came in, was spent and stayed, to check the plan on.
        "observed": _observed_with_growth(st, txns),
        # The saving goal as a share of income — what you set, or what the
        # dollar figure comes to when only that was ever set.
        "savings_rate": (round(float(stored_rate), 4) if stored_rate not in (None, "")
                         else round(savings / income, 4) if income > 0 and savings
                         else None),
        "typical_total": typical_total,
        "headroom": money_plan.headroom(result["leftover"], typical_total),
        # What the daily allowance would divide: the discretionary slice,
        # since groceries come out of the leftover but not out of a daily
        # pocket-money figure.
        "daily_pool": money_plan.discretionary_pool(divided["budgets"]),
        # Divided by this month's real length, the same divisor Today uses, so
        # the two tabs cannot print different numbers for one figure. The month
        # travels with it, because Today may be showing an earlier one when the
        # current month has nothing imported yet — and then the two figures
        # differ for a reason that has to be visible.
        "days_this_month": money_plan.days_in_month(_plan_month()),
        # A full week's worth of the discretionary pool, so the plan quotes
        # the same weekly figure Today leads with rather than the browser
        # working one out.
        "weekly_share": round(money_plan.discretionary_pool(divided["budgets"])
            / money_plan.days_in_month(_plan_month()) * 7, 2),
        "month": _plan_month(),
        "shares": shares,
        "categories": money_plan.explain(result["leftover"], shares, historical,
                                         budgets_override=divided["budgets"]),
        "suggested_budgets": divided["budgets"],
        # What the leftover has beyond your usual spending, and what it is
        # short of it — see money_plan.split.
        "buffer": divided["buffer"],
        "short": divided["short"],
        "has_history": bool(shares),
        "uncategorised": money_plan.uncategorised_warning(shares),
        "current_budgets": st.budgets(),
        # Each bank's contribution beside the total, so a leftover that looks
        # small can be traced to the holiday it is paying for.
        "bank_lines": _bank_status(st),
        "bank_funded": sorted(st.bank_funded_categories()),
    })


def _position(st):
    from . import balances as bal
    return bal.position(st.balances(), st.account_sync_rules(), st.joint_accounts())


def _observed_with_growth(st, txns):
    """What came in, was spent and stayed — and, beside it, how much your
    accounts actually grew, which is the bank's own answer to the same
    question."""
    from . import balances as bal
    from . import money_plan

    seen = money_plan.observed(txns, _today_iso())
    if not seen:
        return seen
    growth = bal.monthly_growth([m["month"] for m in seen["months"]], st.balances(),
                                st.account_sync_rules(), st.joint_accounts(), txns)
    if growth:
        for m in seen["months"]:
            m["grew"] = growth["months"].get(m["month"])
        seen["grew"] = round(sum(growth["months"].values()) / len(growth["months"]), 2)
        seen["grew_accounts"] = growth["accounts"]
    return seen


@bp.put("/plan/setup")
def save_plan_setup():
    """Income and the savings figure. Commitments have their own endpoints."""
    body = request.get_json(silent=True) or {}
    st = store()
    rate = None
    if body.get("savings_rate") is not None:
        try:
            rate = float(body["savings_rate"])
        except (TypeError, ValueError):
            return jsonify({"error": "The saving goal must be a percentage."}), 400
        if not 0 <= rate <= 0.9:
            return jsonify({"error": "The saving goal has to be between 0% and 90% "
                                     "of income."}), 400
    for key, field in (("monthly_income", "income"),
                       ("savings_target", "savings")):
        if field in body:
            try:
                value = max(float(body[field]), 0.0)
            except (TypeError, ValueError):
                return jsonify({"error": f"{field} must be a number."}), 400
            st.set_setting(key, value)
    income = st.float_setting("monthly_income", 0.0)
    if rate is not None:
        st.set_setting("savings_rate", round(rate, 4))
    elif "savings" in body:
        # A dollar figure (Ahead's slider): the goal's share follows it.
        st.set_setting("savings_rate",
                       round(float(body["savings"]) / income, 4) if income > 0 else "")
    # The goal is a share of income, so the dollars follow income.
    stored = st.setting("savings_rate")
    if stored not in (None, "") and "savings" not in body:
        st.set_setting("savings_target", round(float(stored) * income))
    return jsonify({"ok": True})


@bp.post("/plan/setup/apply")
def apply_plan_budgets():
    """Adopt the category budgets the plan implies.

    Separate from saving the figures, because turning the arithmetic into
    budgets replaces whatever is there — a choice worth making deliberately
    rather than as a side effect of editing your rent.
    """
    from . import money_plan

    st = store()
    income = st.float_setting("monthly_income", 0.0)
    savings = st.float_setting("savings_target", 0.0)
    result = money_plan.plan(income, st.fixed_costs(), savings, _bank_monthly(st))
    if result["leftover"] <= 0:
        return jsonify({"error": "There is nothing left to budget. "
                                 "Check your income and commitments."}), 400

    from . import groups as budget_lines

    txns = st.all_transactions()
    grouping = st.category_groups()
    budgets = money_plan.split(txns, result["leftover"], groups=grouping,
                               bank_funded=st.bank_funded_categories())["budgets"]
    if not budgets:
        return jsonify({"error": "Not enough spending history yet to know how "
                                 "to divide it. Import a month or two first."}), 400

    for line, amount in budgets.items():
        st.set_budget(line, amount)

    # A saved budget the plan's split no longer gives anything to — a line
    # too small to fund, a category since folded into another, or one a piggy
    # bank now pays for — would otherwise survive every re-apply, dividing
    # money the plan no longer has for it. Applying the split replaces it all.
    lines = budget_lines.lines(grouping)
    for key in list(st.budgets()):
        if key not in budgets or key not in lines or budget_lines.line_bank_funded(
                lines[key], st.bank_funded_categories()):
            st.set_budget(key, 0)

    # The budgets cover everything the leftover has to pay for; the daily
    # number governs only the discretionary slice of it. That slice is not
    # saved — Today derives it from this same arithmetic on every request, so
    # there is no copy of it to fall out of date. It is worked out per
    # category, never per line, so how you group a budget cannot move it.
    pool = money_plan.discretionary_pool(money_plan.split(
        txns, result["leftover"], bank_funded=st.bank_funded_categories())["budgets"])
    return jsonify({"ok": True, "budgets": budgets,
                    "monthly_amount": pool,
                    "leftover": result["leftover"]})


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


def _paid_by(st) -> list[dict]:
    """Each bank that pays for something, and what: the Budgets note."""
    owned = st.bank_categories()
    return [{"bank": b.name, "id": b.id, "categories": owned[b.id]}
            for b in st.piggy_banks() if owned.get(b.id)]


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
        return None, (error + " Change the grouping in Settings → Categories "
                      "first, or choose the whole line.")
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

    bank_id = st.add_piggy_bank(
        name, target, cadence, target_date if cadence == piggy.ONCE else None,
        _d.today().isoformat()[:7], opening, str(body.get("note") or ""))
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


@bp.get("/plan/fixed")
def list_fixed():
    st = store()
    return jsonify({"fixed": [f.to_dict() for f in st.fixed_costs()]})


@bp.post("/plan/fixed")
def add_fixed():
    body = request.get_json(silent=True) or {}
    name = str(body.get("name", "")).strip()
    if not name:
        return jsonify({"error": "Give the commitment a name."}), 400
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a number."}), 400
    if amount <= 0:
        return jsonify({"error": "A commitment costs more than nothing."}), 400

    cost_id = store().add_fixed_cost(name, amount,
                                     str(body.get("category") or "Other"))
    return jsonify({"ok": True, "id": cost_id})


@bp.patch("/plan/fixed/<int:cost_id>")
def edit_fixed(cost_id: int):
    body = request.get_json(silent=True) or {}
    existing = next((f for f in store().fixed_costs() if f.id == cost_id), None)
    if existing is None:
        return jsonify({"error": "No such commitment."}), 404
    try:
        amount = float(body.get("amount", existing.amount))
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a number."}), 400
    store().update_fixed_cost(
        cost_id, str(body.get("name") or existing.name), amount,
        str(body.get("category") or existing.category))
    return jsonify({"ok": True})


@bp.delete("/plan/fixed/<int:cost_id>")
def remove_fixed(cost_id: int):
    if not store().delete_fixed_cost(cost_id):
        return jsonify({"error": "No such commitment."}), 404
    return jsonify({"ok": True})



def _today_iso() -> str:
    from datetime import date as _date
    return _date.today().isoformat()


@bp.get("/nudge")
def nudge():
    """One sentence about yesterday, or nothing at all."""
    from datetime import date as _date

    from . import nudge as nudge_mod
    from .spend_plan import compute

    st = store()
    txns = st.all_transactions()
    month = _date.today().strftime("%Y-%m")
    amount, _ = _allowance(st, txns)
    state = compute(txns, amount, month)
    return jsonify({"nudge": nudge_mod.for_yesterday(txns, state)})


@bp.get("/trips/suggestions")
def trip_suggestions():
    """Trips the ledger can see, which nobody has had to remember.

    Suggested only. Declaring a trip recategorises every charge inside it, so
    the dates and the charges behind them are shown and the decision stays
    with the person.
    """
    from .trip_finder import suggest_trips

    st = store()
    found = suggest_trips(st.all_transactions(),
                          declared=[t.to_dict() for t in st.trips()])
    return jsonify({"suggestions": found})


@bp.get("/trips")
def trips():
    st = store()
    txns = st.all_transactions()
    rows = [t.to_dict(summarize(t, txns)) for t in st.trips()]
    travel = [t for t in txns if t.category == "Travel" and t.amount > 0]
    return jsonify({
        "trips": rows,
        "summary": {
            "count": len(rows),
            "total": round(sum(r["total"] for r in rows), 2),
            "travel_spend": round(sum(share_amount(t) for t in travel), 2),
        },
    })


@bp.post("/trips")
def add_trip():
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    start, end = body.get("start_date", ""), body.get("end_date", "")

    problem = validate(name, start, end)
    if problem:
        return jsonify({"error": problem}), 400

    trip_id = store().add_trip(name, start, end)
    # Recategorize immediately so the dashboard reflects the trip at once.
    updated = recategorize_all(store())
    return jsonify({"ok": True, "id": trip_id, "recategorized": updated})


@bp.patch("/trips/<int:trip_id>")
def edit_trip(trip_id: int):
    body = request.get_json(silent=True) or {}
    name = body.get("name", "")
    start, end = body.get("start_date", ""), body.get("end_date", "")

    problem = validate(name, start, end)
    if problem:
        return jsonify({"error": problem}), 400

    if not store().update_trip(trip_id, name, start, end):
        return jsonify({"error": "No such trip."}), 404

    return jsonify({"ok": True, "recategorized": recategorize_all(store())})


@bp.delete("/trips/<int:trip_id>")
def remove_trip(trip_id: int):
    if not store().delete_trip(trip_id):
        return jsonify({"error": "No such trip."}), 404
    # Rows fall back to their merchant category once the trip is gone.
    return jsonify({"ok": True, "recategorized": recategorize_all(store())})


# ── Budgets ──────────────────────────────────────────────────────────────────

@bp.get("/budgets")
def budgets():
    from . import groups as budget_lines
    from . import money_plan

    st = store()
    txns = _txns()
    months = sorted({t.month for t in txns})
    month = request.args.get("month") or (months[-1] if months else None)

    # Everything on this page is per budget line: a category, or several you
    # folded together in Settings → Categories. With no grouping every line is
    # one category and this is exactly the per-category page it used to be.
    grouping = st.category_groups()
    lines = budget_lines.lines(grouping)
    line_of = lambda c: budget_lines.line_of(c, grouping)          # noqa: E731
    owned = st.bank_funded_categories()
    funded = {name for name, members in lines.items()
              if budget_lines.line_bank_funded(members, owned)}

    # A saved budget only counts if it is for a line that exists and has a
    # budget at all. One saved before a category was folded away, or before it
    # became bank-funded, is not shown as though it still governed anything.
    b = {k: v for k, v in st.budgets().items()
         if k in lines and k not in funded}
    split = _plan_split(st, txns)
    plan_budgets = split["budgets"] if split else {}
    # "Usually", beside each budget: the same figure the plan starts each
    # line from, so a budget adopted from the plan reads as exactly that.
    typical = money_plan.typical_monthly(txns, groups=grouping)

    # One row per line in Settings → Categories, in that order, so this page
    # is the list you made there. A line used to appear only if it had a
    # saved budget or the plan's split gave it one, and the split drops lines
    # under 2% of spending — so a line you had just set up could be missing.
    # A line with nothing saved is drawn against the plan's figure, or $0
    # when the plan gives it nothing.
    order = [name for name in lines if name not in funded]
    # Once you have split the total yourself, a line you gave nothing is $0 —
    # not the plan's old figure for it.
    focus = _focus(st)
    limits = {name: b.get(name, 0.0 if focus is not None
                                 else plan_budgets.get(name, 0.0))
              for name in order}
    rows = budget_status(txns, limits, month, grouping)
    rows.sort(key=lambda r: order.index(r["category"]))
    history = money_plan.history_stats(txns, groups=grouping,
                                       bank_funded=st.bank_funded_categories())
    for row in rows:
        line = row["category"]
        members = lines.get(line, [line])
        row["adopted"] = line in b
        row["plan_budget"] = plan_budgets.get(line)
        row["typical"] = typical.get(line)
        row["members"] = members if len(members) > 1 or members[0] != line else []
        # Which side of the weekly number this line falls on — all, none or
        # part of it. Decided from its categories, because the weekly number
        # is, so the tag beside a budget cannot contradict the gate itself.
        row["daily"] = budget_lines.line_daily(members)
        row["essential"] = row["daily"] == "none"
        # Nothing set, nothing planned, nothing spent: still a line, but one
        # the page can fold away rather than draw as an empty bar.
        row["quiet"] = (not row["adopted"] and row["plan_budget"] is None
                        and row["spent"] == 0)
        # The guide beside a target: your average and median month here.
        stats = history.get(line, {})
        row["average"] = stats.get("average", 0.0)
        row["median"] = stats.get("median", 0.0)
        row["focus"] = focus is not None and line in focus

    # The saved budgets alone, which is what "covered" below has to mean.
    status = [r for r in rows if r["adopted"]]

    # This month's spending by line, once, for the three terms below.
    by_line: dict[str, float] = {}
    for r in by_category(txns, month):
        if r["amount"] > 0:
            by_line[line_of(r["category"])] = round(
                by_line.get(line_of(r["category"]), 0.0) + r["amount"], 2)

    # Spending in lines nothing budgets is still spending. Reporting only the
    # budgeted lines made the month look smaller than the Overview said it
    # was, with no way to see where the difference went.
    covered = round(sum(r["spent"] for r in status), 2)
    everything = round(sum(r["amount"] for r in by_category(txns, month)), 2)
    unbudgeted = [{"category": line, "amount": amount}
                  for line, amount in by_line.items()
                  if line not in b and line not in funded]

    # Travel is not missing a budget; it is funded somewhere else. What is
    # worth reporting is the part of it no bank has actually paid for —
    # `by_category` already nets off whatever was charged to one — because
    # that is the travel still coming out of this month.
    bank_funded = [{"category": line, "amount": amount}
                   for line, amount in by_line.items() if line in funded]
    bank_funded_total = round(sum(r["amount"] for r in bank_funded), 2)

    # The bank-paid lines, in Settings order too, so the page lists every
    # line you have — with which bank pays for it instead of a budget.
    payer = {c: p["bank"] for p in _paid_by(st) for c in p["categories"]}
    bank_lines = [{
        "category": name,
        "members": members if len(members) > 1 or members[0] != name else [],
        "bank": ", ".join(dict.fromkeys(payer[m] for m in members if m in payer)),
        "uncovered": by_line.get(name, 0.0),
    } for name, members in lines.items() if name in funded]

    return jsonify({
        "budgets": b,
        "month": month,
        # Every budgeted line in Settings → Categories, in that order, saved,
        # proposed by the plan, or neither yet.
        "rows": rows,
        # The lines a piggy bank pays for instead, in the same order.
        "bank_lines": bank_lines,
        # The saved lines alone — the same list, and the same meaning, this
        # key has always had.
        "status": status,
        # What you usually spend, beside each budget. The old "suggested"
        # figure was a rival budget seeded from past spending, which could
        # never ask for less than last month; the plan owns budgets now.
        "typical": typical,
        "covered_spend": covered,
        "month_spend": everything,
        # Three terms now, and they still sum to the month: what a budget
        # covered, what a bank is meant to, and what nothing does. Rolling the
        # middle one into the last would have the page report travel as a
        # missing budget line on the same screen that explains it has none.
        "budgetable_spend": round(everything - bank_funded_total, 2),
        "unbudgeted_spend": round(everything - covered - bank_funded_total, 2),
        "unbudgeted": sorted(unbudgeted, key=lambda r: -r["amount"]),
        # Lines a piggy bank pays for instead of a budget, and the spending in
        # them this month that no bank covered.
        "bank_funded": {
            "categories": sorted(funded),
            "unallocated": sorted(bank_funded, key=lambda r: -r["amount"]),
            "unallocated_total": bank_funded_total,
            "banks": len(st.piggy_banks()),
            # Which bank pays for which categories, for the one-line note.
            "paid_by": _paid_by(st),
        },
        # What the plan would give each line, and what it has to give out.
        # Top-level rather than inside `drift`, because the table shows this
        # column whether or not the two agree — and `drift` is None precisely
        # when they do.
        "plan_leftover": split["leftover"] if split else None,
        # Your own split of the monthly total: the lines you focus on, and
        # the total every budget together has to add up to.
        "focus": [f for f in focus if f in limits] if focus is not None else None,
        "monthly_total": split["leftover"] if split else None,
        "allocated": round(sum(b.values()), 2),
        "other": {
            "spent": round(sum(r["spent"] for r in rows if not r["focus"]), 2),
            "budget": round(sum(b.get(r["category"], 0.0) for r in rows
                                if not r["focus"]), 2),
        },
        "plan_budgets": plan_budgets,
        # What the plan leaves beyond your usual spending, assigned to no
        # line; and how far short of your usual spending it falls.
        "plan_buffer": split["buffer"] if split else None,
        "plan_short": split["short"] if split else None,
        # The leftover not covered by the budgets you have saved — the buffer
        # as it actually stands, once you have adopted or changed budgets.
        "unassigned": (round(split["leftover"] - sum(b.values()), 2)
                       if split and b else None),
        # Whether these budgets still divide the money the plan actually has.
        "drift": _budget_drift(split, b, allocated=focus is not None),
    })


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


def _plan_split(st, txns) -> dict | None:
    """The plan's arithmetic, and the category split it implies.

    Two callers need this: the drift notice below, and the budgets table, which
    shows what the plan would give a category beside what is saved. It used to
    be returned inside `drift` — which is None whenever the budgets already
    agree with the plan, so the one case where the comparison is reassuring was
    the one case the table could not draw it.
    """
    from . import money_plan

    income = st.float_setting("monthly_income", 0.0)
    if income <= 0:
        return None

    result = money_plan.plan(income, st.fixed_costs(),
                             st.float_setting("savings_target", 0.0),
                             _bank_monthly(st))
    # Split by budget line, which is a category unless you have folded some
    # together in Settings. The weekly number is not worked out here and never
    # sees the grouping — see finance/groups.py.
    divided = money_plan.split(txns, result["leftover"], groups=st.category_groups(),
                               bank_funded=st.bank_funded_categories())
    return {
        "leftover": result["leftover"],
        "budgets": divided["budgets"],
        "buffer": divided["buffer"],
        "short": divided["short"],
        "banks": result["banks"],
        "savings": result["savings"],
        "fixed_total": result["fixed_total"],
    }


def _budget_drift(split: dict | None, saved: dict,
                  allocated: bool = False) -> dict | None:
    """Do the saved budgets still add up to what the plan leaves?

    They are adopted once, from the plan's arithmetic, and then stay as they
    were. Anything that moves the plan afterwards — a raise, a new commitment,
    a change to the savings figure, opening a piggy bank — leaves them dividing
    a leftover that no longer exists. Before this, the Budgets tab went on
    reporting the old division in full confidence: budgets totalling $2,585
    against a plan with $1,910 in it, with the $675 of piggy banks spent twice
    and nothing on the page saying so.

    Reported rather than corrected, because a category may have been adjusted
    by hand on that tab, and silently reverting it would be this same bug
    pointing the other way.
    """
    if not split or not saved:
        return None

    # Budgets under the leftover are not drift: the rest is the buffer, which
    # the plan leaves unassigned on purpose. Only budgets that hand out more
    # than the plan has are a problem worth a notice.
    leftover = split["leftover"]
    saved_total = round(sum(saved.values()), 2)
    gap = round(saved_total - leftover, 2)
    # Your own split has to add up to the monthly total exactly, so once the
    # plan moves either way it no longer does. Before that, budgets under the
    # leftover only leave a buffer.
    if (abs(gap) if allocated else gap) <= 1:
        return None

    return {
        "saved_total": saved_total,
        "plan_total": leftover,
        "gap": gap,
        # Named so the notice can say where the difference went rather than
        # just that there is one.
        "banks": split["banks"],
        "savings": split["savings"],
        "fixed_total": split["fixed_total"],
    }


@bp.put("/budgets/allocation")
def set_allocation():
    """Your own split of the monthly total, saved all at once.

    `focus` is the budget lines you want to track closely, and every one of
    them needs a number (0 is a number: "no delivery this month"). Every
    other line is 0 unless you give it something. Together they have to add
    up to what the plan leaves — the monthly total — to the dollar, so the
    split is a division of money you have, not a wish list.
    """
    import json

    from . import groups as budget_lines

    st = store()
    body = request.get_json(silent=True) or {}
    focus = body.get("focus")
    amounts = body.get("budgets") or {}
    if not isinstance(focus, list) or not focus or not all(
            isinstance(f, str) for f in focus):
        return jsonify({"error": "Pick at least one category to focus on."}), 400
    if not isinstance(amounts, dict):
        return jsonify({"error": "Expected a mapping of category to amount."}), 400

    lines = budget_lines.lines(st.category_groups())
    funded = st.bank_funded_categories()
    budgetable = [n for n, members in lines.items()
                  if not budget_lines.line_bank_funded(members, funded)]
    focus = list(dict.fromkeys(focus))
    for name in [*focus, *amounts]:
        if name not in budgetable:
            return jsonify({"error": f"'{name}' isn't a category you can budget. "
                                     "Check Settings → Categories."}), 400

    clean: dict[str, float] = {}
    for name in budgetable:
        raw = amounts.get(name)
        if raw is None or raw == "":
            if name in focus:
                return jsonify({"error": f"{name} needs a monthly target."}), 400
            continue
        try:
            value = round(float(raw), 2)
        except (TypeError, ValueError):
            return jsonify({"error": f"{name} needs a number."}), 400
        if value < 0:
            return jsonify({"error": f"{name} can't be negative."}), 400
        clean[name] = value

    split = _plan_split(st, st.all_transactions())
    if not split or split["leftover"] <= 0:
        return jsonify({"error": "Finish the plan first — your take-home pay "
                                 "and commitments decide the monthly total."}), 400
    total = round(sum(clean.values()), 2)
    gap = round(split["leftover"] - total, 2)
    if abs(gap) > 0.5:
        return jsonify({"error": (
            f"Your budgets add up to ${total:,.2f}; they need to add up to your "
            f"monthly total of ${split['leftover']:,.2f} — "
            + (f"${gap:,.2f} left to assign." if gap > 0
               else f"${-gap:,.2f} too much.")),
            "monthly_total": split["leftover"], "allocated": total}), 400

    for name in budgetable:
        st.set_budget(name, clean.get(name, 0.0))
    # Anything saved under a name that is no longer a budget line goes too.
    for key in list(st.budgets()):
        if key not in budgetable:
            st.set_budget(key, 0)
    st.set_setting(FOCUS_KEY, json.dumps(focus))
    return jsonify({"ok": True, "focus": focus, "budgets": st.budgets(),
                    "monthly_total": split["leftover"]})


@bp.put("/budgets")
def set_budgets():
    body = request.get_json(silent=True) or {}
    updates = body.get("budgets", body)
    if not isinstance(updates, dict):
        return jsonify({"error": "Expected a mapping of category to amount."}), 400

    from . import groups as budget_lines

    # Budgets are per line: a category, or a name you folded several under.
    grouping = store().category_groups()
    lines = budget_lines.lines(grouping)
    funded = store().bank_funded_categories()

    for category, amount in updates.items():
        if category not in lines:
            if category in CATEGORIES:
                return jsonify({"error": (
                    f"{category} is budgeted as part of "
                    f"{budget_lines.line_of(category, grouping)} — set that "
                    "line instead, or take it out of the group in Settings "
                    "→ Categories.")}), 400
            return jsonify({"error": f"Unknown category '{category}'."}), 400
        if budget_lines.line_bank_funded(lines[category], funded):
            return jsonify({"error": (
                f"{category} is paid for by a piggy bank, not budgeted. Its "
                "money leaves the plan as the bank's monthly contribution, so "
                "a budget line here would set the same money aside twice.")}), 400
        try:
            store().set_budget(category, float(amount) if amount is not None else 0)
        except (TypeError, ValueError):
            return jsonify({"error": f"Invalid amount for '{category}'."}), 400

    return jsonify({"ok": True, "budgets": store().budgets()})


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
            names.setdefault(t.account_id, t.account_name or t.account_id)
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
    if t.category != "Income":
        # Calling something a gift or a paycheque makes it income.
        st.set_transaction_category(txn_id, "Income")
    st.set_income_type(txn_id, kind, "user")
    _reclassify(st)
    return jsonify({"ok": True, "transaction": st.get_transaction(txn_id).to_dict()})


# ── Review ───────────────────────────────────────────────────────────────────

@bp.get("/review")
def review_queue():
    from .review import build
    st = store()
    return jsonify(build(st.all_transactions(), dismissed=st.dismissed_reviews()))


@bp.post("/review/dismiss")
def dismiss_review():
    key = str((request.get_json(silent=True) or {}).get("key") or "")
    if not key or ":" not in key:
        return jsonify({"error": "Which item?"}), 400
    store().dismiss_review(key)
    return jsonify({"ok": True})
