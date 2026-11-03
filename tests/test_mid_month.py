"""Started mid-month (O-11d): when Pearl's history starts partway through
this month, the first Allowance is for the rest of it."""

from __future__ import annotations

from datetime import date

from finance.models import Transaction
from finance.safe_to_spend import compute, started_on

TODAY = date(2026, 11, 25)


def tx(day, amount, desc="LOBLAWS", category="Groceries"):
    return Transaction(date=day, description=desc, merchant=desc, amount=amount, category=category,
                       account_id="chq", account_name="TD Chequing", raw={"account_type": "depository"})


def test_history_from_the_20th_is_the_rest_of_the_month():
    rows = [tx("2026-11-20", 40.0), tx("2026-11-22", 60.0)]
    assert started_on(rows, TODAY) == date(2026, 11, 20)
    sts = compute(rows, TODAY, told_income=3000)
    assert sts["from"] == "2026-11-20"
    income = next(r for r in sts["rows"] if r["key"] == "income")
    assert income["amount"] == 1100.0                    # 11 of November's 30 days
    assert sts["amount"] == 1000.0                       # less the $100 spent


def test_a_pay_seen_after_the_start_still_counts_in_full():
    rows = [tx("2026-11-20", 40.0), tx("2026-11-21", -2500.0, "PAYROLL ACME", "Income")]
    sts = compute(rows, TODAY, told_income=3000)
    income = next(r for r in sts["rows"] if r["key"] == "income")
    assert income["amount"] == 2500.0                    # never less than what arrived


def test_history_from_before_this_month_is_the_whole_month():
    rows = [tx("2026-10-28", 30.0), tx("2026-11-22", 60.0)]
    assert started_on(rows, TODAY) is None
    sts = compute(rows, TODAY, told_income=3000)
    assert sts["from"] is None
    assert next(r for r in sts["rows"] if r["key"] == "income")["amount"] == 3000.0


def test_starting_on_the_first_is_the_whole_month():
    assert started_on([tx("2026-11-01", 10.0)], TODAY) is None
