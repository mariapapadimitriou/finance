"""The income and bills check's endpoints (Pearl THL-45, THL-127 I-01 to
I-06), and Profile › Income and bills, which shows the same answers.

Every write returns the whole check again, so a screen never has to work
out a total itself. See `income_bills` for what each answer means and how
safe-to-spend and the path use it.

* GET  /api/transactions/<id>/bill   what "Add to your bills?" (T-32) starts
  with for this purchase: how often, the next payment, her share.
* POST /api/transactions/<id>/bill   {cadence, next, share, category}: it's
  a bill. One Pearl already found for that merchant is the one that counts.
"""

from __future__ import annotations

from datetime import date

from flask import jsonify, request

from . import income_bills as ib
from .api import _today_iso, bp, store

_ROW_FIELDS = ("key", "name", "amount", "full", "share", "varies", "cadence", "next", "day", "category",
               "counts", "ticked", "source", "edited", "question", "recipient", "rent", "shared")


def _payload(st) -> dict:
    today = date.fromisoformat(_today_iso())
    txns = st.all_transactions()
    state = ib.load(st)
    told = st.float_setting("home_income", 0.0)
    rows = ib.bills(txns, today, state)
    from .safe_to_spend import usual_income
    usual = usual_income(txns, today)
    estimate = usual["average"] if usual else None
    return {
        "today": today.isoformat(),
        "checked": {"income": state["income_on"], "bills": state["bills_on"]},
        "pays": state["pays"],
        "candidates": ib.pay_candidates(txns, today, state),
        "asks": ib.pay_asks(txns, today, state),
        # Her own amount (it overrides the rest), and Pearl's estimate from
        # her last three months (2026-10-13, THL-45).
        "expected": {"amount": told or None, "varies": bool(state["varies"]),
                     "estimate": estimate, "months": usual["months"] if usual else []},
        "bills": [{k: r[k] for k in _ROW_FIELDS if k in r} for r in rows],
        "rent_question": ib.rent_question(rows),
        "totals": {"income": ib.income_each_month(state, told, estimate),
                   "bills": ib.bills_each_month(rows, st.float_setting("home_rent", 0.0))},
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
    txns = st.all_transactions()
    found = next((c for c in ib.pay_candidates(txns, today, state) if c["payer"] == payer), None)
    if found is None and answer == "no" and any(a["payer"] == payer for a in ib.pay_asks(txns, today, state)):
        # O-10f's "This isn't regular pay", before it's a candidate.
        found = {"payer": payer}
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


@bp.delete("/income-bills/expected")
def income_bills_expected_clear():
    """"Use Pearl's estimate": her own amount goes, and safe to spend uses her
    pay, or her usual income from the last three months, again."""
    st = store()
    st.set_setting("home_income", "")
    return jsonify(_payload(st))


@bp.get("/income-bills/saving")
def income_bills_saving_get():
    """O-10s: how much of her pay she means to save, as she last said."""
    return jsonify(_saving(store()))


@bp.put("/income-bills/saving")
def income_bills_saving():
    """O-10s "How much do you want to save?" (2026-11-04): a share of each
    paycheque, 1% to 50%. Kept as `savings_rate`; the saving goal
    (`savings_target`) follows her income, as on Income and bills."""
    raw = _body().get("pct")
    try:
        pct = float(raw)
    except (TypeError, ValueError):
        return _error("Choose how much of your pay to save.")
    if not 0 <= pct <= 50:
        return _error("Choose a share of your pay from 0% to 50%.")
    st = store()
    st.set_setting("savings_rate", str(round(pct / 100, 4)))
    _sync_plan_income(st, ib.load(st))
    return jsonify(_saving(st))


def _saving(st) -> dict:
    """{pct, per_pay, cadence, monthly}: the share and what it comes to."""
    state = ib.load(st)
    rate = st.float_setting("savings_rate", 0.0)
    income = ib.income_each_month(state, st.float_setting("home_income", 0.0)) or 0.0
    pay = (state.get("pays") or [None])[0]
    return {"pct": round(rate * 100, 2) if rate else None,
            "monthly": round(rate * income, 2),
            "per_pay": round(rate * pay["amount"], 2) if pay else None,
            "cadence": pay["cadence"] if pay else None}


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


# ── A bill from a transaction (T-32) ─────────────────────────────────────

_EVERY = {"weekly": "every week", "biweekly": "every 2 weeks", "monthly": "every month",
          "bimonthly": "every 2 months", "quarterly": "every 3 months",
          "semiannual": "every 6 months", "annual": "every year"}
_STEP_DAYS = {"weekly": 7, "biweekly": 14}
_STEP_MONTHS = {"monthly": 1, "bimonthly": 2, "quarterly": 3, "semiannual": 6, "annual": 12}


def _next_after(day: date, cadence: str, today: date) -> date:
    """The first payment after this one that isn't in the past."""
    from datetime import timedelta
    nxt = day
    while nxt <= day or nxt < today:
        if cadence in _STEP_DAYS:
            nxt = nxt + timedelta(days=_STEP_DAYS[cadence])
        else:
            nxt = ib._add_months(nxt, _STEP_MONTHS.get(cadence, 1), day.day)
    return nxt


def _found_bill(rows: list[dict], merchant: str) -> dict | None:
    return next((r for r in rows if r["source"] == "found" and r.get("merchant") == merchant), None)


def _charge_or_error(st, txn_id: str):
    t = st.get_transaction(txn_id)
    if t is None:
        return None, _error("No such transaction.", 404)
    if t.amount <= 0:
        return None, _error("Only money going out can be a bill.")
    return t, None


@bp.get("/transactions/<txn_id>/bill")
def transaction_bill_get(txn_id: str):
    st = store()
    t, err = _charge_or_error(st, txn_id)
    if err:
        return err
    today = date.fromisoformat(_today_iso())
    rows = ib.bills(st.all_transactions(), today, ib.load(st))
    found = _found_bill(rows, t.merchant)
    # The bill this merchant is already on, found or added by hand: what the
    # transaction page's Regular bill switch turns off.
    current = next((r for r in rows if r.get("merchant") == t.merchant and r.get("counts")), None)
    cadence = found["cadence"] if found and found["cadence"] in ib.BILL_CADENCES else "monthly"
    nxt = found["next"] if found else _next_after(date.fromisoformat(t.date[:10]), cadence,
                                                   today).isoformat()
    share = round(t.my_share / t.amount * 100) if t.my_share is not None and t.amount else 100
    return jsonify({"name": t.merchant, "amount": round(t.amount, 2), "cadence": cadence,
                    "next": nxt, "share": max(1, min(100, share)), "category": t.category or "Other",
                    "is_bill": bool(found and found["counts"]),
                    "bill_key": current["key"] if current else None})


@bp.post("/transactions/<txn_id>/bill")
def transaction_bill_add(txn_id: str):
    from .categorize import CATEGORIES
    st = store()
    t, err = _charge_or_error(st, txn_id)
    if err:
        return err
    body = _body()
    cadence = body.get("cadence")
    if cadence not in ib.BILL_CADENCES:
        return _error("Choose how often it’s due.")
    nxt = ib.clean_date(body.get("next"))
    if nxt is None:
        return _error("Choose the next due date.")
    try:
        share = float(body.get("share", 100))
    except (TypeError, ValueError):
        share = -1
    if not 0 < share <= 100:
        return _error("Your share is between 1% and 100%.")
    category = body.get("category") or t.category or "Other"
    if category not in CATEGORIES:
        return _error("Choose a category.")
    amount = round(t.amount * share / 100, 2)
    today = date.fromisoformat(_today_iso())
    state = ib.load(st)
    found = _found_bill(ib.bills(st.all_transactions(), today, state), t.merchant)
    if found:
        key = found["key"]
        state["bills"][key] = {"state": "yes", "name": t.merchant, "amount": amount,
                               "cadence": cadence, "next": nxt}
    else:
        bill = {"id": ib.next_id(state, "b"), "name": t.merchant, "amount": amount,
                "cadence": cadence, "next": nxt, "varies": False, "merchant": t.merchant,
                "category": category}
        state["added"].append(bill)
        key = f"added:{bill['id']}"
    state["bills_on"] = state["bills_on"] or today.isoformat()
    ib.save(st, state)
    return jsonify({"ok": True, "key": key,
                    "title": f"{t.merchant} is in your bills: ${amount:,.2f} {_EVERY[cadence]}."})


# ── O-10g: someone's regular e-Transfers ─────────────────────────────────

@bp.post("/income-bills/etransfer")
def income_bills_etransfer():
    """"What is it?" for someone's regular e-Transfers: their share of a bill
    (`bill` is its key: it counts net of their part, and their e-Transfers so
    far leave her numbers), paying her back (not income), or something else
    (left for Needs a look). Setup doesn't ask again."""
    from . import marks
    body = _body()
    st = store()
    state = ib.load(st)
    today = date.fromisoformat(_today_iso())
    txns = st.all_transactions()
    payer = ib.clean_name(body.get("payer"))
    ask = next((a for a in ib.pay_asks(txns, today, state)
                if a["kind"] == "etransfer" and a["payer"] == payer), None)
    if ask is None:
        return _error("We couldn’t find those e-Transfers any more.", 404)
    answer = body.get("answer")
    if answer not in ("share", "payback", "else"):
        return _error("Say what they are.")
    by_id = {t.fingerprint: t for t in txns}
    if answer == "share":
        bill = next((r for r in ib.bills(txns, today, state) if r["key"] == body.get("bill")), None)
        if bill is None:
            return _error("Choose the bill it’s for.")
        state["shares"][payer] = {"bill": bill["key"], "person": ask["person"],
                                  "amount": ask["amount"], "cadence": ask["cadence"]}
        for i in ask["ids"]:
            st.exclude(i, f"{ask['person']}’s share of {bill['name']}")
    elif answer == "payback":
        for i in ask["ids"]:
            try:
                marks.apply(st, by_id[i], {"case": "lent_back"}, today)
            except marks.Problem as exc:
                return _error(str(exc))
    state["etransfer_done"] = sorted(set(state["etransfer_done"]) | {payer})
    ib.save(st, state)
    from .api import _reclassify
    _reclassify(st)
    return jsonify(_payload(st))
