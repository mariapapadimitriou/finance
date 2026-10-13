"""The income and bills check's endpoints (Pearl THL-45, THL-127 I-01 to
I-06), and Profile › Income and bills, which shows the same answers.

Every write returns the whole check again, so a screen never has to work
out a total itself. See `income_bills` for what each answer means and how
safe-to-spend and the path use it.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import income_bills as ib
from .api import _today_iso, bp, store

_ROW_FIELDS = ("key", "name", "amount", "varies", "cadence", "next", "day", "category",
               "counts", "ticked", "source", "edited", "question", "recipient", "rent")


def _payload(st) -> dict:
    today = date.fromisoformat(_today_iso())
    txns = st.all_transactions()
    state = ib.load(st)
    told = st.float_setting("home_income", 0.0)
    rows = ib.bills(txns, today, state)
    return {
        "today": today.isoformat(),
        "checked": {"income": state["income_on"], "bills": state["bills_on"]},
        "pays": state["pays"],
        "candidates": ib.pay_candidates(txns, today, state),
        "expected": {"amount": told or None, "varies": bool(state["varies"])},
        "bills": [{k: r[k] for k in _ROW_FIELDS if k in r} for r in rows],
        "rent_question": ib.rent_question(rows),
        "totals": {"income": ib.income_each_month(state, told),
                   "bills": ib.bills_each_month(rows)},
    }


def _sync_plan_income(st, state: dict) -> None:
    """Keep the plan's take-home pay (`monthly_income`, which Projections,
    Goals' saving goal and the older budgets still read) on her confirmed
    income: the page that used to set it is this one now. A saving goal set
    as a share of take-home follows it, as it did there."""
    income = ib.income_each_month(state, st.float_setting("home_income", 0.0))
    if not income:
        return
    st.set_setting("monthly_income", income)
    rate = st.setting("savings_rate")
    if rate not in (None, ""):
        st.set_setting("savings_target", round(float(rate) * income))


def _error(text: str, status: int = 400):
    return jsonify({"error": text}), status


def _body() -> dict:
    body = request.get_json(silent=True)
    return body if isinstance(body, dict) else {}


@bp.get("/income-bills")
def income_bills_get():
    return jsonify(_payload(store()))


@bp.post("/income-bills/pay/answer")
def income_bills_pay_answer():
    """I-01: "Yes, that's my pay" or "No, it's something else"."""
    body = _body()
    st = store()
    state = ib.load(st)
    payer = ib.clean_name(body.get("payer"))
    answer = body.get("answer")
    if answer not in ("yes", "no"):
        return _error("Say whether it’s your pay.")
    today = date.fromisoformat(_today_iso())
    found = next((c for c in ib.pay_candidates(st.all_transactions(), today, state)
                  if c["payer"] == payer), None)
    if found is None:
        return _error("We couldn’t find that deposit any more.", 404)
    if answer == "yes":
        state["pays"].append({"id": ib.next_id(state, "p"), "payer": payer,
                              "name": found["name"], "amount": found["amount"],
                              "cadence": found["cadence"], "next": found["next"]})
        state["income_on"] = state["income_on"] or today.isoformat()
    else:
        state["pay_no"] = sorted(set(state["pay_no"]) | {payer})
    ib.save(st, state)
    _sync_plan_income(st, state)
    return jsonify(_payload(st))


@bp.post("/income-bills/pay")
def income_bills_pay_add():
    """I-02 saved for new pay: a deposit she corrected, or another source."""
    pay, error = ib.pay_from(_body())
    if error:
        return _error(error)
    st = store()
    state = ib.load(st)
    if pay["payer"]:
        state["pays"] = [p for p in state["pays"] if p.get("payer") != pay["payer"]]
    state["pays"].append({"id": ib.next_id(state, "p"), **pay})
    state["income_on"] = state["income_on"] or _today_iso()
    ib.save(st, state)
    _sync_plan_income(st, state)
    return jsonify(_payload(st))


@bp.put("/income-bills/pay/<pay_id>")
def income_bills_pay_edit(pay_id: str):
    """I-02 saved for pay she already confirmed."""
    st = store()
    state = ib.load(st)
    current = next((p for p in state["pays"] if p["id"] == pay_id), None)
    if current is None:
        return _error("No such pay.", 404)
    pay, error = ib.pay_from({**_body(), "payer": current.get("payer")})
    if error:
        return _error(error)
    current.update(pay)
    ib.save(st, state)
    _sync_plan_income(st, state)
    return jsonify(_payload(st))


@bp.delete("/income-bills/pay/<pay_id>")
def income_bills_pay_remove(pay_id: str):
    st = store()
    state = ib.load(st)
    kept = [p for p in state["pays"] if p["id"] != pay_id]
    if len(kept) == len(state["pays"]):
        return _error("No such pay.", 404)
    state["pays"] = kept
    ib.save(st, state)
    _sync_plan_income(st, state)
    return jsonify(_payload(st))


@bp.put("/income-bills/expected")
def income_bills_expected():
    """I-03: the income she expects each month. The same figure as the one
    she tells Home (`home_income`), so there is one, not two."""
    body = _body()
    amount = ib.clean_amount(body.get("amount"))
    if amount is None:
        return _error("Enter what you expect each month after tax, like 3800.")
    st = store()
    state = ib.load(st)
    st.set_setting("home_income", str(amount))
    state["varies"] = bool(body.get("varies"))
    state["income_on"] = state["income_on"] or _today_iso()
    ib.save(st, state)
    _sync_plan_income(st, state)
    return jsonify(_payload(st))


@bp.post("/income-bills/expected/skip")
def income_bills_expected_skip():
    """I-03's "Skip for now": remembered, so Home can make a rough estimate
    from the deposits it has seen (H-03) until she gives her income."""
    st = store()
    state = ib.load(st)
    state["income_skipped"] = state["income_skipped"] or _today_iso()
    ib.save(st, state)
    return jsonify(_payload(st))


@bp.put("/income-bills/bills")
def income_bills_confirm():
    """I-04's "Confirm n bills": what she left ticked counts, what she
    unticked doesn't."""
    ticked = _body().get("ticked")
    if not isinstance(ticked, dict):
        return _error("Say which bills to count.")
    st = store()
    state = ib.load(st)
    today = date.fromisoformat(_today_iso())
    known = {r["key"]: r for r in ib.bills(st.all_transactions(), today, state)}
    for key, on in ticked.items():
        row = known.get(key)
        if row is None or row["source"] == "added":
            continue
        entry = state["bills"].setdefault(key, {})
        entry["state"] = "yes" if on else "no"
    state["bills_on"] = state["bills_on"] or today.isoformat()
    ib.save(st, state)
    return jsonify(_payload(st))


@bp.post("/income-bills/bills")
def income_bills_add():
    """I-05: a bill Pearl missed."""
    bill, error = ib.bill_from(_body())
    if error:
        return _error(error)
    st = store()
    state = ib.load(st)
    state["added"].append({"id": ib.next_id(state, "b"), **bill})
    ib.save(st, state)
    return jsonify(_payload(st))


@bp.put("/income-bills/bills/<path:key>")
def income_bills_edit(key: str):
    """I-05 for a bill she can already see: her amount and schedule win, and
    it counts."""
    bill, error = ib.bill_from(_body())
    if error:
        return _error(error)
    st = store()
    state = ib.load(st)
    if key.startswith("added:"):
        current = next((b for b in state["added"] if f"added:{b['id']}" == key), None)
        if current is None:
            return _error("No such bill.", 404)
        current.update(bill)
    else:
        today = date.fromisoformat(_today_iso())
        if key not in {r["key"] for r in ib.bills(st.all_transactions(), today, state)}:
            return _error("No such bill.", 404)
        state["bills"][key] = {"state": "yes", **bill}
    ib.save(st, state)
    return jsonify(_payload(st))


@bp.delete("/income-bills/bills/<path:key>")
def income_bills_remove(key: str):
    """I-05's "Remove this bill": no confirmation, and Undo puts it back
    (the reply carries what was removed)."""
    st = store()
    state = ib.load(st)
    if key.startswith("added:"):
        removed = next((b for b in state["added"] if f"added:{b['id']}" == key), None)
        if removed is None:
            return _error("No such bill.", 404)
        state["added"] = [b for b in state["added"] if b is not removed]
    else:
        today = date.fromisoformat(_today_iso())
        row = next((r for r in ib.bills(st.all_transactions(), today, state) if r["key"] == key),
                   None)
        if row is None:
            return _error("No such bill.", 404)
        removed = {"name": row["name"], "amount": row["amount"], "cadence": row["cadence"],
                   "next": row["next"], "varies": row["varies"]}
        state["bills"][key] = {**{k: v for k, v in state["bills"].get(key, {}).items()},
                               "state": "no"}
    ib.save(st, state)
    return jsonify({**_payload(st), "removed": {"key": key, **removed}})


@bp.post("/income-bills/rent")
def income_bills_rent():
    """I-04's "Yes, it's my rent": the e-Transfers to that recipient are
    Rent (Essentials) from now on, the bill counts, and the answer is kept
    for that recipient."""
    from .transfers import apply_transfer_matches

    body = _body()
    key = str(body.get("key") or "")
    st = store()
    state = ib.load(st)
    today = date.fromisoformat(_today_iso())
    series = next((s for s in ib.rent_series(st.all_transactions(), today) if s["key"] == key),
                  None)
    if series is None:
        return _error("We couldn’t find those e-Transfers any more.", 404)
    recipient = key[len("rent:"):]
    state["rent"][recipient] = "yes"
    state["bills"][key] = {"state": "yes"}
    st.set_destination(recipient, ib.RENT, series["recipient"])
    for tid in series["ids"]:
        st.set_transaction_category(tid, ib.RENT)
    apply_transfer_matches(st)
    ib.save(st, state)
    return jsonify(_payload(st))
