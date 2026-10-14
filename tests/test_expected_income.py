"""Expected income (2026-10-13, THL-45, THL-47): from her previous months by
default, her own amount as an override, caution only when she asks for it."""

from __future__ import annotations

from finance import income_bills as ib
from finance import safe_to_spend as sts
from test_safe_to_spend import TODAY, history, october, row, tx

NORTHWIND = {"id": "p1", "payer": "Northwind Ltd", "name": "Northwind Ltd", "amount": 2150.00,
             "cadence": "semimonthly", "next": "2026-10-16"}


def clients(oct_in=None):
    """Three full months of client payments, nothing regular about them."""
    rows = [tx("2026-07-01", "Rent", 1650.0, "Rent & Housing")]   # history from July 1
    rows += [tx(d, who, -a, "Income") for d, who, a in (
        ("2026-07-08", "Client A", 3000.0), ("2026-08-05", "Client B", 4800.0),
        ("2026-09-02", "Client A", 3900.0))]
    if oct_in:
        rows.append(tx("2026-10-03", "Client B", -oct_in, "Income"))
    return rows


def state(**kw):
    s = ib.empty()
    s.update(kw)
    return s


def test_usual_income_is_the_average_of_the_last_three_full_months():
    u = sts.usual_income(clients(), TODAY)
    assert u == {"average": 3900.0, "months": ["2026-07", "2026-08", "2026-09"]}
    s = sts.compute(clients(), TODAY)
    assert s["income_source"] == "usual" and row(s, "income")["amount"] == 3900.0


def test_never_less_than_what_arrived_this_month():
    s = sts.compute(clients(oct_in=4500.0), TODAY)
    assert row(s, "income")["amount"] == 4500.0


def test_a_one_off_is_left_out_of_the_average():
    rows = clients() + [tx("2026-08-20", "Bonus", -1200.0, "Income")]
    assert sts.usual_income(rows, TODAY)["average"] == 4300.0
    rows[-1].one_off_since = "2026-08-21"
    assert sts.usual_income(rows, TODAY)["average"] == 3900.0


def test_pay_that_stopped_is_not_expected():
    rows = [r for r in clients() if not r.date.startswith("2026-09")]
    assert sts.usual_income(rows, TODAY) is None


def test_her_amount_overrides_even_confirmed_pay():
    said = state(income_on="2026-10-09", pays=[NORTHWIND])
    s = sts.compute(history() + october(), TODAY, confirm=said, told_income=6000.0)
    assert s["income_source"] == "told" and row(s, "income")["amount"] == 6000.0
    # Cleared, her pay is used again.
    s = sts.compute(history() + october(), TODAY, confirm=said)
    assert s["income_source"] == "confirmed"


def test_asking_for_caution_uses_the_lowest_month():
    s = sts.compute(clients(), TODAY, confirm=state(varies=True), told_income=5000.0)
    assert s["income_source"] == "cautious" and row(s, "income")["amount"] == 3000.0
    # Without the history for it, the amount she gave stands.
    s = sts.compute(clients()[-2:], TODAY, confirm=state(varies=True), told_income=5000.0)
    assert s["income_source"] == "told"


def test_regular_pay_keeps_its_schedule():
    """A pay schedule knows two paycheques from three; the average wouldn't."""
    s = sts.compute(history() + october(), TODAY)
    assert s["income_source"] == "detected"
