"""HTTP API.

Every route is read-only against your local SQLite file except the import,
category and budget endpoints. Nothing here reaches the network apart from the
optional /api/narrative call and a Plaid sync you explicitly configure.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

from . import narrative
from .analytics import (
    budget_status,
    by_category,
    by_merchant,
    daily_series,
    fixed_vs_discretionary,
    month_over_month,
    monthly_totals,
    summary as build_summary,
    weekday_profile,
)
from .categorize import CATEGORIES
from .db import storage_mode
from .ingest import all_sources, get_source, parse_csv, parse_statement
from .insights import detect_recurring, findings_summary, generate_findings, recurring_summary
from .pipeline import ingest, recategorize_all
from .categorize import apply_categories
from .dedupe import split_new
from .trips import apply_trips
from .trips import summarize, validate
from . import gamify, manual, projections, spend_plan
from .store import Store

bp = Blueprint("api", __name__, url_prefix="/api")

MAX_UPLOAD_BYTES = 25 * 1024 * 1024


def store() -> Store:
    return current_app.config["STORE"]


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
        "narrative": narrative.status(),
    })


@bp.get("/categories")
def categories():
    return jsonify({
        "categories": [
            {"name": name, **meta} for name, meta in CATEGORIES.items()
        ],
        "overrides": store().overrides(),
    })


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


@bp.get("/import/bundled")
def bundled_available():
    """Statement sets shipped with the app, and whether each is already loaded."""
    from seed_data.bundled import available
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

@bp.get("/transactions")
def transactions():
    txns, total = store().query_transactions(
        month=request.args.get("month"),
        category=request.args.get("category"),
        account_id=request.args.get("account"),
        search=request.args.get("q"),
        start=request.args.get("start"),
        end=request.args.get("end"),
        limit=min(int(request.args.get("limit", 200)), 1000),
        offset=int(request.args.get("offset", 0)),
    )
    return jsonify({
        "transactions": [t.to_dict() for t in txns],
        "total": total,
    })


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

    return jsonify({"accounts": rows})


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
    removed = st.reset(keep_banks=keep_banks)
    return jsonify({
        "ok": True,
        "transactions_removed": before,
        "removed": removed,
        "banks_kept": keep_banks,
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
    st.set_account_sync(account_id, bool(body["enabled"]),
                        name=name, item_id=rule.get("item_id", ""))
    return jsonify({"ok": True, "account_id": account_id,
                    "enabled": bool(body["enabled"])})


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
    txns = _txns()
    month = request.args.get("month")
    return jsonify({
        "month": month,
        "split": fixed_vs_discretionary(txns, month),
        "categories": by_category(txns, month),
        "merchants": by_merchant(txns, month, limit=int(request.args.get("limit", 25))),
        "changes": month_over_month(txns, month) if month else [],
        "monthly": monthly_totals(txns),
        "daily": daily_series(txns, int(request.args.get("days", 90))),
        "weekday": weekday_profile(txns),
    })


@bp.get("/recurring")
def recurring():
    found = detect_recurring(_txns())
    return jsonify({"recurring": found, "summary": recurring_summary(found)})


@bp.get("/insights")
def insights():
    txns = _txns()
    findings = generate_findings(txns, store().dismissed())
    return jsonify({
        "findings": findings,
        "summary": findings_summary(findings),
        "narrative": narrative.status(),
    })


@bp.post("/insights/<insight_id>/dismiss")
def dismiss_insight(insight_id: str):
    store().dismiss(insight_id)
    return jsonify({"ok": True})


@bp.delete("/insights/<insight_id>/dismiss")
def restore_insight(insight_id: str):
    store().undismiss(insight_id)
    return jsonify({"ok": True})


@bp.post("/narrative")
def run_narrative():
    """Optional Claude read. Sends aggregates only — see finance/narrative.py."""
    txns = _txns()
    if not txns:
        return jsonify({"available": False, "text": "",
                        "detail": "Import some transactions first."})

    s = build_summary(txns, store().budgets())
    found = generate_findings(txns, store().dismissed())
    rec = detect_recurring(txns)

    if request.args.get("preview") == "1":
        return jsonify({"payload": narrative.build_payload(s, found, rec),
                        **narrative.status()})

    try:
        return jsonify(narrative.analyze(s, found, rec))
    except Exception as exc:  # noqa: BLE001 - surface API failures to the UI
        return jsonify({"available": False, "text": "",
                        "detail": f"Claude request failed: {exc}"}), 502


# ── Spend plan: safe to spend, buckets, "how am I doing" ─────────────────
# See finance/spend_plan.py for the model and why only discretionary spending
# counts toward it.

def _plan_month(default_from_data: bool = True) -> str:
    """The month the plan is being asked about. Defaults to the real one."""
    asked = request.args.get("month")
    if asked:
        return asked
    from datetime import date as _d
    return _d.today().strftime("%Y-%m")


def _plan_state(st, month: str) -> dict:
    txns = st.all_transactions()
    amount = st.float_setting("monthly_amount", 0.0)
    if amount <= 0:
        amount = spend_plan.suggest_monthly_amount(txns)
    return spend_plan.compute(txns, amount, month, covered=st.covered_in(month))


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
        sums = [round(sum(t.amount for t in txns
                          if t.month == m and spend_plan.counts_toward_plan(t)), 2)
                for m in prior]
        baseline = round(statistics.median(sums), 2)

    return jsonify({
        "state": state,
        "status": spend_plan.how_am_i_doing(state, baseline),
        "buckets": [b.to_dict() for b in st.buckets()],
        "draws": st.draws(month),
        "configured": st.float_setting("monthly_amount", 0.0) > 0,
        "suggested": spend_plan.suggest_monthly_amount(txns),
        "has_data_this_month": month in months_with_data,
        "months_with_data": months_with_data,
    })


@bp.put("/plan")
def set_plan():
    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("monthly_amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Monthly amount must be a number."}), 400
    if amount < 0:
        return jsonify({"error": "Monthly amount cannot be negative."}), 400

    store().set_setting("monthly_amount", amount)
    return jsonify({"ok": True, "monthly_amount": amount})


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

    st = store()
    month = _plan_month()
    state = _plan_state(st, month)
    return jsonify(spend_plan.simulate(state, amount, st.buckets()))


@bp.put("/buckets")
def set_bucket():
    body = request.get_json(silent=True) or {}
    name = (body.get("name") or "").strip()
    if not name:
        return jsonify({"error": "Give the bucket a name."}), 400
    try:
        balance = float(body.get("balance", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Balance must be a number."}), 400

    return jsonify({"ok": True, "id": store().set_bucket(name, balance)})


@bp.delete("/buckets/<int:bucket_id>")
def remove_bucket(bucket_id: int):
    if not store().delete_bucket(bucket_id):
        return jsonify({"error": "No such bucket."}), 404
    return jsonify({"ok": True})


@bp.post("/buckets/<int:bucket_id>/cover")
def cover_from_bucket(bucket_id: int):
    """Draw on a bucket to cover this month's overspend."""
    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a number."}), 400
    if amount <= 0:
        return jsonify({"error": "Enter an amount above zero."}), 400

    st = store()
    month = body.get("month") or _plan_month()
    if not st.draw_from_bucket(bucket_id, month, amount, body.get("note", "")):
        return jsonify({"error": "That bucket doesn't have enough in it."}), 400
    return jsonify({"ok": True, "state": _plan_state(st, month)})


# ── Gamification ─────────────────────────────────────────────────────────
# Every reward is for restraint; nothing pays out for spending. See
# finance/gamify.py.

@bp.get("/progress")
def progress():
    st = store()
    txns = st.all_transactions()
    month = _plan_month()
    state = _plan_state(st, month)
    return jsonify(gamify.profile(txns, state["flat_daily"], st.trips()))


# ── Projections ──────────────────────────────────────────────────────────

@bp.get("/projections")
def projection():
    st = store()
    txns = st.all_transactions()
    income = st.float_setting("monthly_income", 0.0) or None

    findings = generate_findings(txns, st.dismissed())
    weighted = findings_summary(findings).get("weighted_annual", 0.0)

    result = projections.project(txns, income, weighted,
                                 int(request.args.get("months", 12)))
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
    return jsonify(result)


@bp.put("/projections/income")
def set_income():
    body = request.get_json(silent=True) or {}
    try:
        income = float(body.get("monthly_income", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Income must be a number."}), 400
    if income < 0:
        return jsonify({"error": "Income cannot be negative."}), 400
    store().set_setting("monthly_income", income)
    return jsonify({"ok": True, "monthly_income": income})


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
            "travel_spend": round(sum(t.amount for t in travel), 2),
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
    txns = _txns()
    months = sorted({t.month for t in txns})
    month = request.args.get("month") or (months[-1] if months else None)
    b = store().budgets()
    return jsonify({
        "budgets": b,
        "month": month,
        "status": budget_status(txns, b, month),
        "suggested": _suggest_budgets(txns),
    })


@bp.put("/budgets")
def set_budgets():
    body = request.get_json(silent=True) or {}
    updates = body.get("budgets", body)
    if not isinstance(updates, dict):
        return jsonify({"error": "Expected a mapping of category to amount."}), 400

    for category, amount in updates.items():
        if category not in CATEGORIES:
            return jsonify({"error": f"Unknown category '{category}'."}), 400
        try:
            store().set_budget(category, float(amount) if amount is not None else 0)
        except (TypeError, ValueError):
            return jsonify({"error": f"Invalid amount for '{category}'."}), 400

    return jsonify({"ok": True, "budgets": store().budgets()})


def _suggest_budgets(txns) -> dict:
    """Seed budgets from what you actually spend, not from a generic template.

    Discretionary categories are seeded 10% under your median as a nudge;
    essentials are seeded at the median, since you can't decide to use less
    electricity by writing a smaller number down.
    """
    from .analytics import category_baselines
    from .categorize import is_discretionary

    base = category_baselines(txns)
    out = {}
    for category, stats in base.items():
        # Fees and interest get no budget line: budgeting for them normalizes
        # something the savings engine is trying to get to zero.
        if stats["median"] < 20 or category in {"Income", "Transfers", "Fees & Interest"}:
            continue
        factor = 0.9 if is_discretionary(category) else 1.0
        out[category] = round(stats["median"] * factor, -1) or round(stats["median"], 2)
    return out
