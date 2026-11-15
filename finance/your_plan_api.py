"""Your plan's endpoints (YP-01 to YP-06; finance/your_plan.py). Every write
returns the whole page again, so the app adds nothing up.

* GET    /api/your-plan                  the plan, each row with her usual, and the Allowance it leaves
* POST   /api/your-plan/suggest          YP-06's Suggest a plan (never while in use)
* PUT    /api/your-plan/rows/<category>  {amount, source?}: YP-04's Save; the chat's Set it (source "chat")
* DELETE /api/your-plan/rows/<category>  YP-05's Remove
* POST   /api/your-plan/use              YP-02's Use this plan: the Allowance follows it from today
* POST   /api/your-plan/stop             YP-03's Stop using this plan
* POST   /api/your-plan/undo             Undo on YP-03's toast: as before Use this plan

Only use, and a change while it's in use, move the Allowance.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import api as core
from . import income_bills as ib
from . import your_plan as yp
from .api import bp, store


def _today() -> date:
    return date.fromisoformat(core._today_iso())


def _usual(st, txns, today) -> dict:
    from .usual_month import usual
    return usual(txns, today, unusual=core._unusual_months(st))


def _income_and_bills(st, txns, today) -> tuple[float | None, float]:
    """Income and bills a month, as Income and bills' own page counts them."""
    from .safe_to_spend import usual_income
    state = ib.load(st)
    usual = usual_income(txns, today)
    income = ib.income_each_month(state, st.float_setting("home_income", 0.0),
                                  usual["average"] if usual else None)
    bills = ib.bills_each_month(ib.bills(txns, today, state), st.float_setting("home_rent", 0.0))
    return income, bills


def _page(st, state: dict | None = None):
    today = _today()
    txns = st.all_transactions()
    income, bills = _income_and_bills(st, txns, today)
    return jsonify(yp.page(state if state is not None else yp.load(st), _usual(st, txns, today),
                           income, bills))


def _change(fn):
    st = store()
    try:
        state = fn(st, yp.load(st))
    except yp.PlanError as e:
        return jsonify({"error": e.words}), e.status
    yp.save(st, state)
    return _page(st, state)


def _body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@bp.get("/your-plan")
def your_plan_get():
    return _page(store())


@bp.post("/your-plan/suggest")
def your_plan_suggest():
    def go(st, state):
        today = _today()
        txns = st.all_transactions()
        return yp.suggest(state, txns, today, _usual(st, txns, today))
    return _change(go)


@bp.put("/your-plan/rows/<path:category>")
def your_plan_row_set(category):
    body = _body()
    source = "chat" if body.get("source") == "chat" else "you"
    return _change(lambda st, state: yp.set_row(state, category, body.get("amount"), source))


@bp.delete("/your-plan/rows/<path:category>")
def your_plan_row_remove(category):
    return _change(lambda st, state: yp.remove_row(state, category))


@bp.post("/your-plan/use")
def your_plan_use():
    return _change(lambda st, state: yp.use(state, _today()))


@bp.post("/your-plan/stop")
def your_plan_stop():
    return _change(lambda st, state: yp.stop(state))


@bp.post("/your-plan/undo")
def your_plan_undo():
    return _change(lambda st, state: yp.stop(state))
