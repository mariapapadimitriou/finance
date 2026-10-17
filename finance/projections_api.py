"""Growth › Projections and Unveil endpoints (Pearl THL-197 GR-33 to GR-37,
THL-135 GR-16, THL-130 GR-10). The maths is in `look_ahead`.

* GET /api/projections?extra=50: everything GR-33 to GR-36 draw — the
  Anchor line, this month (GR-34), the next 30 days (GR-35) and savings in a
  year (GR-36), with `extra` dollars more a month as the what-if. Integer
  cents; every projection a {low, high} range.
* PUT /api/projections/pace {monthly}: "Use this pace for my Anchor" (GR-36):
  the monthly saving goal Allowance sets aside.
* GET /api/unveil: the readiness checklist (GR-16) and her self-report.
* PUT /api/unveil {type}: "Mark Unveil done" (GR-37). Only the kind of account
  is asked — never where, a login or a balance. It makes the path's Unveil
  step done, as a linked investment account already does.
* DELETE /api/unveil: undo it (GR-37's "You can undo this in Profile").

GR-16 also carries "Read the basics" from Learn (THL-134, `learn.py`) and
the partner card's state (THL-136, post-MVP, `growth_api.py`). GR-21's "I
opened an account", after the partner, is this same self-report with
`via: "partner"`, so there is one record of it.

The growth calculator (GR-17, GR-18) is worked out on the device: it uses
nothing of hers but the two figures she types.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

from flask import jsonify, request

from . import api as core
from . import growth_insights as gi
from . import growth_api, learn, look_ahead
from .api import bp, store

ACCOUNT_TYPES = {"tfsa": "TFSA", "rrsp": "RRSP", "fhsa": "FHSA",
                 "non_registered": "Non-registered", "not_sure": "Not sure"}
REPORT_KEY = "unveil_reported"
MAX_EXTRA = 10_000


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _c(x) -> int:
    return look_ahead.cents(x)


# ── Paydays, bills and the balance ahead (GR-35) ──────────────────────────

def _paydays(txns, today: date, confirm: dict, end: date) -> list[dict]:
    """Paydays between tomorrow and `end`: her confirmed pay (THL-127 I-01,
    I-02) once she has answered; before that, regular pay Pearl can see."""
    from collections import Counter
    from .income import cadence, is_income, kind_of
    from .income_bills import occurrences
    from .safe_to_spend import STALE_PAY_DAYS, _paydays_after

    start = today + timedelta(days=1)
    pays = confirm.get("pays") or []
    out = []
    for p in pays:
        if p.get("cadence") == "irregular" or not p.get("next"):
            continue
        for d in occurrences(date.fromisoformat(p["next"]), p["cadence"], start, end):
            out.append({"date": d.isoformat(), "label": p["name"], "amount": _c(p["amount"])})
    if pays or confirm.get("income_on"):
        return out
    pay = cadence(txns, today.isoformat())
    if not pay or pay["cadence"] not in STALE_PAY_DAYS:
        return out
    if (today - date.fromisoformat(max(pay["paydays"]))).days > STALE_PAY_DAYS[pay["cadence"]]:
        return out
    payer = Counter(t.merchant or t.description for t in txns
                    if is_income(t) and kind_of(t) == "salary").most_common(1)
    label = payer[0][0] if payer else "Payday"
    return [{"date": d.isoformat(), "label": label, "amount": _c(pay["paycheque"])}
            for d in _paydays_after(pay, today, end)]


def _bills(txns, today: date, confirm: dict, end: date) -> list[dict]:
    """Bills between tomorrow and `end`, from the income and bills check: the
    ones she confirmed or added, and the ones Pearl found that she hasn't
    answered yet (counted, as Allowance counts them, but marked)."""
    from .income_bills import bills, occurrences
    start = today + timedelta(days=1)
    out = []
    for b in bills(txns, today, confirm):
        if b["counts"] is False or not b.get("next"):
            continue
        for d in occurrences(date.fromisoformat(b["next"]), b["cadence"], start, end):
            out.append({"date": d.isoformat(), "label": b["name"], "amount": _c(b["amount"]),
                        "confirmed": b["counts"] is True, "key": b["key"]})
    return out


def _chequing_balance(st) -> int | None:
    """What her counted chequing accounts hold now (AM-02, manual ones too),
    her share only on a joint account (AM-04); a joint account with no share
    set isn't counted. None with no chequing account to go on."""
    joint, shares = st.joint_accounts(), st.joint_shares()
    total, seen = 0, False
    for a in core._anchor_accounts(st):
        if a["kind"] != "chequing":
            continue
        share = 100.0
        if a["account_id"] in joint:
            share = shares.get(a["account_id"]) or 0.0
            if share <= 0:
                continue
        seen = True
        total += _c(a["balance"] * share / 100)
    return total if seen else None


# ── The page ──────────────────────────────────────────────────────────────

def _anchor_line(anchor: dict) -> dict:
    """GR-33's "YOUR ANCHOR · Likely full between March and June 2027"."""
    if not anchor["started"]:
        return {"state": "not_started"}
    p = anchor.get("projection") or {"state": "none"}
    out = {"state": p["state"], "counted": _c(anchor["counted"]),
           "target": _c(anchor["target"])}
    if p["state"] == "range":
        out.update({"from": p["from"], "to": p["to"]})
    return out


def _savings_now(st, txns, today: date, anchor: dict) -> tuple[int, list[dict]]:
    """What the Anchor and chests hold now, and at the end of recent months
    (GR-32's measure, so Insights and Projections agree)."""
    month = today.strftime("%Y-%m")
    first = gi.first_month(txns) or month
    months = [m for m in gi.window(month, 6) if m >= min(first, month)]
    balances = st.balances()
    accounts = [{"account_id": a["account_id"], "balance": a["balance"],
                 "as_of": (balances.get(a["account_id"]) or {}).get("as_of")}
                for a in anchor["counting"]]
    s = gi.savings(txns, months, today, anchor=anchor, accounts=accounts,
                   banks=st.piggy_banks(), charges=st.bank_charges_by_month())
    return s["total"], [{"month": p["month"], "total": p["total"]} for p in s["series"]]


def payload(st, extra_c: int = 0) -> dict:
    from . import income_bills, safe_to_spend, usual_month

    today = _today()
    txns = st.all_transactions()
    unusual = core._unusual_months(st)
    sts = core._home_sts(st, txns, today)
    confirm = income_bills.load(st)
    months = usual_month.covered_months(txns, today, unusual=unusual)
    bill_charges = safe_to_spend.bill_charges(txns, today)
    spent_c = None
    if not sts.get("rows"):
        spent_c = safe_to_spend.already_spent(txns, today)["amount_c"]
    forecast = look_ahead.month_end(txns, today, sts, months, bill_charges, spent_c=spent_c)

    end = today + timedelta(days=look_ahead.DAYS_AHEAD)
    next30 = look_ahead.next_30_days(
        today, balance_c=_chequing_balance(st),
        paydays=_paydays(txns, today, confirm, end), bills=_bills(txns, today, confirm, end),
        per_day=look_ahead.everyday_per_day(txns, today, months, bill_charges))

    anchor = core._anchor(st, txns, today.isoformat())
    now_c, history = _savings_now(st, txns, today, anchor)
    chests = [core._chest(r) for r in core._bank_status(st)]
    savings = look_ahead.savings_in_a_year(today, now_c=now_c, pace=anchor["pace"],
                                           extra_c=extra_c, history=history, chests=chests)
    return {
        "today": today.isoformat(),
        "empty": not txns,
        "anchor": _anchor_line(anchor),
        "forecast": forecast,
        "next30": next30,
        "savings": savings,
        "saving_goal": _c(st.float_setting("savings_target", 0.0)),
    }


@bp.get("/projections")
def projections_page():
    try:
        extra = float(request.args.get("extra") or 0)
    except ValueError:
        return jsonify({"error": "Ask for an amount a month, like 50."}), 400
    if not 0 <= extra <= MAX_EXTRA:
        return jsonify({"error": "Ask for an amount a month, like 50."}), 400
    return jsonify(payload(store(), _c(extra)))


@bp.put("/projections/pace")
def use_pace():
    """GR-36 "Use this pace for my Anchor": the monthly amount she sets aside,
    which Allowance takes out of the month (its "Set aside" row)."""
    body = request.get_json(silent=True) or {}
    try:
        monthly = round(float(body.get("monthly")), 2)
    except (TypeError, ValueError):
        return jsonify({"error": "Give an amount a month, like 300."}), 400
    if not 0 < monthly <= 1_000_000:
        return jsonify({"error": "Give an amount a month, like 300."}), 400
    st = store()
    st.set_setting("savings_target", monthly)
    income = st.float_setting("monthly_income", 0.0)
    # The goal's share of income follows the dollars, as the plan page did.
    st.set_setting("savings_rate", round(monthly / income, 4) if income > 0 else "")
    return jsonify(payload(st))


# ── Unveil (GR-16, GR-37, GR-10) ──────────────────────────────────────────

def _report(st) -> dict | None:
    raw = core._json_setting(st, REPORT_KEY, None)
    if not isinstance(raw, dict) or raw.get("type") not in ACCOUNT_TYPES:
        return None
    out = {"type": raw["type"], "label": ACCOUNT_TYPES[raw["type"]], "on": raw.get("on")}
    if raw.get("via") == "partner":
        out["via"] = "partner"
    return out


def _protect_left(path: dict) -> dict:
    """GR-23's "1 step left: your income covers your Essentials"."""
    if path["protect_done"]:
        return {}
    left = [s["key"] for s in path["steps"] if not s["done"]]
    return {"left": len(left), "next": left[0] if left else None}


def unveil(st) -> dict:
    """GR-16's checklist, GR-37's self-report and the path it moves."""
    from . import milestones, safe_to_spend, usual_month

    today = _today()
    txns = st.all_transactions()
    told_income = st.float_setting("home_income", 0.0)
    told_rent = st.float_setting("home_rent", 0.0)
    sts = core._home_sts(st, txns, today)
    types = {aid: r.get("account_type") or ""
             for aid, r in st.account_sync_rules().items() if r.get("enabled")}
    state = safe_to_spend.home_state(txns, today, sts, account_types=types,
                                     told_income=told_income, told_rent=told_rent)
    path = core._path(st, txns, today, sts, state, types)
    anchor = core._anchor(st, txns, today.isoformat())
    cards = {a for a, t in types.items() if (t or "").lower() == "credit"}
    cards |= {m["account_id"] for m in st.manual_accounts()
              if m["kind"] == "credit" and m["counted"]}
    months = usual_month.covered_months(txns, today)
    steady = milestones.cards_steady(txns, months, cards)
    checklist = [
        {"key": "protect", "done": path["protect_done"], **_protect_left(path)},
        {"key": "anchor", "done": bool(anchor["earned"]), "started": anchor["started"],
         "counted": _c(anchor["counted"]), "target": _c(anchor["target"]),
         "months": anchor.get("months"), "usual": anchor.get("usual")},
        {"key": "cards", **steady},
        # "Read the basics": the five Learn modules (THL-134 GR-14).
        learn.basics(st),
    ]
    report = _report(st)
    return {"checklist": checklist, "report": report, "path": path,
            "partner": growth_api.partner_state(st, path, report),
            "types": [{"key": k, "label": v} for k, v in ACCOUNT_TYPES.items()]}


@bp.get("/unveil")
def unveil_page():
    return jsonify(unveil(store()))


@bp.put("/unveil")
def report_account():
    body = request.get_json(silent=True) or {}
    kind = body.get("type")
    if kind not in ACCOUNT_TYPES:
        return jsonify({"error": "Choose the kind of account."}), 400
    via = body.get("via")
    if via not in (None, "self", "partner"):
        return jsonify({"error": "Say how you opened it: yourself or with the partner."}), 400
    st = store()
    record = {"type": kind, "on": _today().isoformat()}
    if via == "partner":
        record["via"] = "partner"
    st.set_setting(REPORT_KEY, json.dumps(record))
    growth_api.answered(st)
    growth_api.mark_unveil_seen(st)
    return jsonify(unveil(st))


@bp.delete("/unveil")
def undo_report():
    st = store()
    st.set_setting(REPORT_KEY, "")
    return jsonify(unveil(st))
