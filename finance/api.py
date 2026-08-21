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
    month_over_month,
    monthly_totals,
    summary as build_summary,
    weekday_profile,
)
from .categorize import CATEGORIES
from .ingest import all_sources, get_source, parse_csv
from .insights import detect_recurring, findings_summary, generate_findings, recurring_summary
from .pipeline import ingest, recategorize_all
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
    return jsonify({"ok": True, "transactions": len(_txns())})


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
    """Accept one or more CSV uploads (multipart) or inline CSV text (JSON)."""
    payloads = []

    if request.files:
        for f in request.files.getlist("files") or list(request.files.values()):
            data = f.read()
            if len(data) > MAX_UPLOAD_BYTES:
                return jsonify({"error": f"{f.filename} exceeds the 25 MB limit."}), 413
            payloads.append({
                "name": f.filename or "upload.csv",
                "content": _decode(data),
                "account_name": request.form.get("account_name") or None,
            })
    else:
        body = request.get_json(silent=True) or {}
        for item in body.get("files", []):
            payloads.append({
                "name": item.get("name", "upload.csv"),
                "content": item.get("content", ""),
                "account_name": item.get("account_name"),
            })

    if not payloads:
        return jsonify({"error": "No files supplied."}), 400

    results = []
    for p in payloads:
        parsed = parse_csv(
            content=p["content"], filename=p["name"], account_name=p.get("account_name")
        )
        results.append(ingest(store(), parsed, filename=p["name"]))

    return jsonify({
        "results": results,
        "imported": sum(r["imported"] for r in results),
        "duplicates": sum(r["duplicates"] for r in results),
    })


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
    return jsonify({"accounts": store().accounts()})


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
