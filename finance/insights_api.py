"""Growth › Insights endpoints (Pearl THL-186 GR-24 to GR-27, THL-196 GR-28
to GR-32). The maths is in `growth_insights`.

* GET /api/insights/month?month=YYYY-MM: everything the page and its detail
  views draw for that month (this month when left out).
* PUT /api/insights/unusual: "Leave September out of my usual" (THL-59). The
  same list the Anchor's pace leaves out, so Goals, Home and Insights agree.
* PUT /api/insights/subscriptions: Keep or Review one subscription (THL-63).
  Review only sets a reminder for next month; nothing is sent and nothing is
  cancelled.

Every write returns the month again, so a screen never works out a total.
"""

from __future__ import annotations

import json
import re
from datetime import date

from flask import jsonify, request

from . import api as core
from . import growth_insights as gi
from .api import bp, store

_MONTH = re.compile(r"\d{4}-(0[1-9]|1[0-2])")


def _today() -> date:
    return date.fromisoformat(core._today_iso())


SPANS = (3, 6, 12)
SHOW = ("essentials", "lifestyle", "fixed", "variable")


def _filters(args) -> dict:
    """The page's filters (2026-10-14): one account, a span of months,
    one-offs left out, and one group or kind."""
    span = args.get("span")
    show = (args.get("show") or "").lower()
    return {"account": args.get("account") or None,
            "span": int(span) if span and span.isdigit() and int(span) in SPANS else 12,
            "one_offs": "out" if args.get("one_offs") == "out" else "in",
            "show": show if show in SHOW else None}


def _apply(txns, f: dict, kinds: dict[str, str]):
    """The rows the filters keep. Only spending is narrowed by a group or a
    kind; income and what's put away stay, so the money chart still adds up."""
    from .analytics import counts_as_spending
    from .categorize import group_of
    out = []
    for t in txns:
        if f["account"] and t.account_id != f["account"]:
            continue
        if f["one_offs"] == "out" and t.one_off:
            continue
        if f["show"] and counts_as_spending(t):
            if f["show"] in ("fixed", "variable"):
                if kinds.get(t.fingerprint, "variable") != f["show"]:
                    continue
            elif group_of(t.category or "Other") != f["show"]:
                continue
        out.append(t)
    return out


def _accounts(st) -> list[dict]:
    names = st.account_nicknames()
    return sorted(({"id": a["account_id"],
                    "name": names.get(a["account_id"]) or a.get("account_name") or a["account_id"]}
                   for a in st.accounts()), key=lambda a: a["name"].lower())


def _payload(st, month: str | None = None, filters: dict | None = None) -> dict:
    from . import kinds as kinds_mod, recommendations as rec, usual_month

    today = _today()
    month = month or today.strftime("%Y-%m")
    f = filters or _filters({})
    everything = st.all_transactions()
    # Fixed or Variable is decided on the whole ledger, then the filters apply.
    kinds = kinds_mod.kind_map(st, everything, today)
    txns = _apply(everything, f, kinds)
    unusual = core._unusual_months(st)
    u_today = usual_month.usual(txns, today, unusual=unusual, kinds=kinds)
    # A past month is compared with the months before it (GR-25).
    u_month = u_today if month == today.strftime("%Y-%m") else usual_month.usual(
        txns, date(int(month[:4]), int(month[5:7]), 1), unusual=unusual, kinds=kinds)
    anchor = core._anchor(st, txns, today.isoformat())
    balances = st.balances()
    accounts = [{"account_id": a["account_id"], "balance": a["balance"],
                 "as_of": (balances.get(a["account_id"]) or {}).get("as_of")}
                for a in anchor["counting"]]
    # One income for every month shown (safe_to_spend.income_for_month).
    from . import savings
    from .safe_to_spend import income_for_month
    wanted = {t.month for t in txns} | {month, today.strftime("%Y-%m")}
    income_by, estimated = {}, set()
    for m in sorted(wanted):
        amount, est = income_for_month(st, txns, m, today)
        income_by[m] = gi.cents(amount)
        if est:
            estimated.add(m)
    body = gi.build(
        txns, today, month, u_today=u_today, u_month=u_month, unusual=unusual,
        banks=st.piggy_banks(), charges=st.bank_charges_by_month(),
        income=income_by, estimated=estimated, adds=savings.chest_adds(st),
        kinds=kinds, n=f["span"],
        confirmed=st.confirmed_categories(), anchor=anchor, anchor_accounts=accounts,
        subscription_records=rec.subscription_records(txns, today),
        subscription_choices=core._json_setting(st, "subscription_choices", {}))
    # "For you" (THL-12 E08): Home's cards, at most two — from the whole
    # ledger, as Home shows them.
    sts = core._home_sts(st, everything, today)
    u_all = u_today if txns is everything else usual_month.usual(everything, today, unusual=unusual)
    body["recommendations"] = core._recommendations(st, everything, today, sts, u_all)
    body["filters"] = f
    body["accounts"] = _accounts(st)
    body["kind_labels"] = kinds_mod.KIND_LABELS
    return body


def _month_arg(value) -> tuple[str | None, str | None]:
    if value in (None, ""):
        return None, None
    if not isinstance(value, str) or not _MONTH.fullmatch(value):
        return None, "Months look like 2026-09."
    if value > _today().strftime("%Y-%m"):
        return None, "That month hasn't happened yet."
    return value, None


@bp.get("/insights/month")
def insights_month():
    month, error = _month_arg(request.args.get("month"))
    if error:
        return jsonify({"error": error}), 400
    return jsonify(_payload(store(), month, _filters(request.args)))


@bp.put("/insights/unusual")
def insights_unusual():
    """Leave a full month out of the usual month, or put it back."""
    body = request.get_json(silent=True) or {}
    month, error = _month_arg(body.get("month"))
    if error or not month:
        return jsonify({"error": error or "Say which month."}), 400
    if month >= _today().strftime("%Y-%m"):
        return jsonify({"error": "Only a month that has ended can be left out."}), 400
    st = store()
    months = core._unusual_months(st)
    if body.get("unusual", True):
        months.add(month)
    else:
        months.discard(month)
    st.set_setting("anchor_unusual", json.dumps(sorted(months)))
    return jsonify(_payload(st, month))


@bp.put("/insights/subscriptions")
def insights_subscription():
    """Keep (nothing changes) or Review (a reminder next month), or clear it."""
    body = request.get_json(silent=True) or {}
    merchant = str(body.get("merchant") or "").strip()
    choice = body.get("choice")
    if not merchant:
        return jsonify({"error": "Say which subscription."}), 400
    if choice not in ("keep", "review", None):
        return jsonify({"error": "Choose Keep or Review."}), 400
    st = store()
    choices = core._json_setting(st, "subscription_choices", {})
    if choice is None:
        choices.pop(merchant, None)
    else:
        today = _today()
        choices[merchant] = {"choice": choice, "on": today.isoformat(),
                             "remind": gi.add_months(today.strftime("%Y-%m"), 1)
                             if choice == "review" else None}
    st.set_setting("subscription_choices", json.dumps(choices))
    return jsonify(_payload(st))
