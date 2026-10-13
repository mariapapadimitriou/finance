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


def _payload(st, month: str | None = None) -> dict:
    from . import recommendations as rec, usual_month

    today = _today()
    month = month or today.strftime("%Y-%m")
    txns = st.all_transactions()
    unusual = core._unusual_months(st)
    u_today = usual_month.usual(txns, today, unusual=unusual)
    # A past month is compared with the months before it (GR-25).
    u_month = u_today if month == today.strftime("%Y-%m") else usual_month.usual(
        txns, date(int(month[:4]), int(month[5:7]), 1), unusual=unusual)
    anchor = core._anchor(st, txns, today.isoformat())
    balances = st.balances()
    accounts = [{"account_id": a["account_id"], "balance": a["balance"],
                 "as_of": (balances.get(a["account_id"]) or {}).get("as_of")}
                for a in anchor["counting"]]
    body = gi.build(
        txns, today, month, u_today=u_today, u_month=u_month, unusual=unusual,
        banks=st.piggy_banks(), charges=st.bank_charges_by_month(),
        confirmed=st.confirmed_categories(), anchor=anchor, anchor_accounts=accounts,
        subscription_records=rec.subscription_records(txns, today),
        subscription_choices=core._json_setting(st, "subscription_choices", {}))
    # "For you" (THL-12 E08): Home's cards, at most two.
    sts = core._home_sts(st, txns, today)
    body["recommendations"] = core._recommendations(st, txns, today, sts, u_today)
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
    return jsonify(_payload(store(), month))


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
