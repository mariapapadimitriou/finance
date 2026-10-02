"""HTTP API.

Every route is read-only against your local SQLite file except the import,
category and budget endpoints. Nothing here reaches the network apart from the
optional Claude call on the Savings tab and a Plaid sync you configure.
"""

from __future__ import annotations

from flask import Blueprint, current_app, jsonify, request

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

    from .analytics import currency_mix, ledger_currency

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
    st = store()
    txns = _txns()
    dismissed = st.dismissed()
    findings = generate_findings(txns, dismissed)
    summary = findings_summary(findings)
    return jsonify({
        "findings": findings,
        "summary": summary,
        # Written in advance, shown when they apply. See
        # finance/insights/profile.py — this is what replaced the paid bot.
        "observations": observe(_profile(st, txns, summary), dismissed),
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
    shares = money_plan.variable_shares(txns)
    discretionary = money_plan.discretionary_shares(txns)

    allowance, from_plan = _allowance(st, txns)
    last = last_complete_month(txns) or ""
    last_spend = round(sum(t.amount for t in txns if t.month == last
                           and spend_plan.counts_toward_plan(t)), 2)

    months = sorted({t.month for t in txns})
    recent = set(months[-12:])
    travel = round(sum(t.amount for t in txns if t.month in recent
                       and t.amount > 0 and (t.category or "") == "Travel"), 2)

    charges = st.bank_charges_by_month()
    banks = [b.to_dict(piggy.status(b, charges.get(b.id, {})))
             for b in st.piggy_banks()]

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
    piggy bank and the daily number moves with it.

    Before the plan has an income in it there is nothing to derive, and a brand
    new ledger should still show something, so the fallback is your own median
    discretionary month. The second return value says which of the two you are
    looking at, because a budget taken from last year's spending deserves to be
    labelled as one.
    """
    from . import money_plan

    txns = st.all_transactions() if txns is None else txns
    income = st.float_setting("monthly_income", 0.0)
    if income > 0:
        amount = money_plan.monthly_allowance(
            income, st.fixed_costs(), st.float_setting("savings_target", 0.0),
            _bank_monthly(st), money_plan.variable_shares(txns))
        if amount > 0:
            return amount, True
    return spend_plan.suggest_monthly_amount(txns), False


def _plan_state(st, month: str) -> dict:
    txns = st.all_transactions()
    amount, _ = _allowance(st, txns)
    return spend_plan.compute(txns, amount, month, covered=st.covered_in(month))


def _derivation(st, txns, allowance: float, from_plan: bool) -> dict:
    """How the Plan tab's leftover becomes Today's daily number.

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
    shares = money_plan.variable_shares(txns)
    budgets = money_plan.category_budgets(result["leftover"], shares)

    # The categories actually making up the essential half, biggest first,
    # rather than a hardcoded example. The note used to read "groceries,
    # transport" — but Transport is flagged discretionary in categorize.py, so
    # it sits in the other column, and the one explanation on the page whose
    # job is to be auditable named a category that contradicted it.
    from .categorize import is_discretionary
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
        "essentials": round(result["leftover"] - allowance, 2),
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
        sums = [round(sum(t.amount for t in txns
                          if t.month == m and spend_plan.counts_toward_plan(t)), 2)
                for m in prior]
        baseline = round(statistics.median(sums), 2)

    allowance, from_plan = _allowance(st, txns)
    return jsonify({
        "state": state,
        "status": spend_plan.how_am_i_doing(state, baseline),
        "banks": _bank_status(st),
        "draws": st.draws(month),
        "allocated_this_month": st.allocated_in(month),
        # The whole chain from the Plan tab's figure down to the daily number,
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

    # The plan, when there is one. Without it the projection cannot see rent and
    # ends up treating it as money available to save.
    from . import money_plan
    plan = money_plan.plan(income or 0.0, st.fixed_costs(),
                           st.float_setting("savings_target", 0.0),
                           _bank_monthly(st)) if income else None

    result = projections.project(txns, income, weighted,
                                 int(request.args.get("months", 12)), plan=plan)
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
    shares = money_plan.variable_shares(txns)
    historical = _typical_by_category(txns)
    typical_total = round(sum(historical.get(c, 0.0) for c in shares), 2)

    return jsonify({
        **result,
        "typical_total": typical_total,
        "headroom": money_plan.headroom(result["leftover"], typical_total),
        # What the daily allowance would divide: the discretionary slice,
        # since groceries come out of the leftover but not out of a daily
        # pocket-money figure.
        "daily_pool": money_plan.discretionary_pool(
            money_plan.category_budgets(result["leftover"], shares)),
        # Divided by this month's real length, the same divisor Today uses, so
        # the two tabs cannot print different numbers for one figure. The month
        # travels with it, because Today may be showing an earlier one when the
        # current month has nothing imported yet — and then the two figures
        # differ for a reason that has to be visible.
        "days_this_month": money_plan.days_in_month(_plan_month()),
        "month": _plan_month(),
        "shares": shares,
        "categories": money_plan.explain(result["leftover"], shares, historical),
        "suggested_budgets": money_plan.category_budgets(result["leftover"], shares),
        "has_history": bool(shares),
        "uncategorised": money_plan.uncategorised_warning(shares),
        "current_budgets": st.budgets(),
        # Each bank's contribution beside the total, so a leftover that looks
        # small can be traced to the holiday it is paying for.
        "bank_lines": _bank_status(st),
    })


@bp.put("/plan/setup")
def save_plan_setup():
    """Income and the savings figure. Commitments have their own endpoints."""
    body = request.get_json(silent=True) or {}
    st = store()
    for key, field in (("monthly_income", "income"),
                       ("savings_target", "savings")):
        if field in body:
            try:
                value = max(float(body[field]), 0.0)
            except (TypeError, ValueError):
                return jsonify({"error": f"{field} must be a number."}), 400
            st.set_setting(key, value)
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

    shares = money_plan.variable_shares(st.all_transactions())
    budgets = money_plan.category_budgets(result["leftover"], shares)
    if not budgets:
        return jsonify({"error": "Not enough spending history yet to know how "
                                 "to divide it. Import a month or two first."}), 400

    for category, amount in budgets.items():
        st.set_budget(category, amount)

    # The budgets cover everything the leftover has to pay for; the daily
    # number governs only the discretionary slice of it. That slice is not
    # saved — Today derives it from this same arithmetic on every request, so
    # there is no copy of it to fall out of date.
    return jsonify({"ok": True, "budgets": budgets,
                    "monthly_amount": money_plan.discretionary_pool(budgets),
                    "leftover": result["leftover"]})


# ── Piggy banks ──────────────────────────────────────────────────────────────
# Annual costs turned into a monthly commitment, and spending charged to them
# instead of to the month it fell in. See finance/piggy.py for the arithmetic.

def _bank_status(st) -> list[dict]:
    """Every bank with its derived figures, biggest contribution first."""
    from . import piggy

    charges = st.bank_charges_by_month()
    rows = [b.to_dict(piggy.status(b, charges.get(b.id, {})))
            for b in st.piggy_banks()]
    rows.sort(key=lambda r: (-r["monthly"], r["name"]))
    return rows


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
    })


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

    bank_id = st.add_piggy_bank(
        name, target, cadence, target_date if cadence == piggy.ONCE else None,
        _d.today().isoformat()[:7], opening, str(body.get("note") or ""))
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

    st.update_piggy_bank(bank_id, name, target, cadence,
                         target_date if cadence == piggy.ONCE else None,
                         opening, str(body.get("note", bank.note) or ""))
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
        # The whole charge leaves the month. What it costs you is the catch-up
        # on the months ahead, which is the figure worth reporting.
        "covered": round(txn.amount, 2),
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


@bp.post("/piggy/<int:bank_id>/cover")
def cover_from_bank(bank_id: int):
    """Draw on a bank to cover this month's overspend.

    Distinct from allocating a charge: this is not "the holiday paid for the
    flights", it is "the month went over and the holiday fund is lending it
    the difference". Both empty the bank, so both are checked against what is
    actually in it.
    """
    from . import piggy

    body = request.get_json(silent=True) or {}
    try:
        amount = float(body.get("amount", 0))
    except (TypeError, ValueError):
        return jsonify({"error": "Amount must be a number."}), 400
    if amount <= 0:
        return jsonify({"error": "Enter an amount above zero."}), 400

    st = store()
    bank = st.piggy_bank(bank_id)
    if bank is None:
        return jsonify({"error": "No such piggy bank."}), 404

    month = str(body.get("month") or _plan_month())
    available = piggy.status(
        bank, st.bank_charges_by_month().get(bank_id, {}))["balance"]
    if not st.draw_from_bank(bank_id, month, amount, available,
                             str(body.get("note") or "")):
        return jsonify({"error": f"{bank.name} only has "
                                 f"${available:,.2f} in it."}), 400
    return jsonify({"ok": True})


@bp.get("/plan/fixed")
def list_fixed():
    return jsonify({"fixed": [f.to_dict() for f in store().fixed_costs()]})


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


def _typical_by_category(transactions) -> dict[str, float]:
    """Median monthly spend per category — shown beside the new budget.

    Over every category a budget now covers, essentials included. Restricting
    it to discretionary ones left the largest line on the page — groceries —
    with no "you usually spend" to compare against, which is precisely the
    comparison that makes a budget believable.
    """
    import statistics
    from .analytics import counts_as_spending, spend_amount

    per: dict[str, dict[str, float]] = {}
    for t in transactions:
        category = t.category or "Other"
        if t.amount <= 0 or not counts_as_spending(t):
            continue
        per.setdefault(category, {})
        per[category][t.month] = (per[category].get(t.month, 0.0)
                                  + spend_amount(t))
    return {c: round(statistics.median(m.values()), 2) for c, m in per.items() if m}

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
    status = budget_status(txns, b, month)

    # Spending in categories nothing budgets is still spending. Reporting
    # only the budgeted lines made the month look smaller than the Overview
    # said it was, with no way to see where the difference went.
    covered = round(sum(r["spent"] for r in status), 2)
    everything = round(sum(r["amount"] for r in by_category(txns, month)), 2)
    unbudgeted = [
        {"category": r["category"], "amount": r["amount"]}
        for r in by_category(txns, month)
        if r["category"] not in b and r["amount"] > 0
    ]

    return jsonify({
        "budgets": b,
        "month": month,
        "status": status,
        # What you usually spend, beside each budget. The old "suggested"
        # figure was a rival budget seeded from past spending, which could
        # never ask for less than last month; the Plan tab owns budgets now.
        "typical": _typical_by_category(txns),
        "covered_spend": covered,
        "month_spend": everything,
        "unbudgeted_spend": round(everything - covered, 2),
        "unbudgeted": sorted(unbudgeted, key=lambda r: -r["amount"]),
        # Whether these budgets still divide the money the plan actually has.
        "drift": _budget_drift(store(), txns, b),
    })


def _budget_drift(st, txns, saved: dict) -> dict | None:
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
    from . import money_plan

    income = st.float_setting("monthly_income", 0.0)
    if income <= 0 or not saved:
        return None

    result = money_plan.plan(income, st.fixed_costs(),
                             st.float_setting("savings_target", 0.0),
                             _bank_monthly(st))
    leftover = result["leftover"]
    shares = money_plan.variable_shares(txns)
    plan_budgets = money_plan.category_budgets(leftover, shares)

    saved_total = round(sum(saved.values()), 2)
    gap = round(saved_total - leftover, 2)
    if abs(gap) <= 1:
        return None

    return {
        "saved_total": saved_total,
        "plan_total": leftover,
        "gap": gap,
        # Named so the notice can say where the difference went rather than
        # just that there is one.
        "banks": result["banks"],
        "savings": result["savings"],
        "fixed_total": result["fixed_total"],
        "plan_budgets": plan_budgets,
    }


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
