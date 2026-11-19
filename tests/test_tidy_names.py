"""Tidy names (TEST-46, product owner 2026-11-19): display only, by rule,
never a list of merchants; her renames win."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.models import Transaction
from finance.tidy_names import tidy

TODAY = date.today()


@pytest.mark.parametrize("raw, city, shown", [
    ("Direct Deposit Payroll Acme", "", "Acme"),
    ("Payroll Acme Corp", "", "Acme Corp"),
    ("Dir Dep Northwind Ltd", "", "Northwind Ltd"),
    ("Bar Isabel Toronto", "Toronto", "Bar Isabel"),
    ("Pizza Nova North York", "North York", "Pizza Nova"),
    # Only when the bank's location says so.
    ("Bar Isabel Toronto", "", "Bar Isabel Toronto"),
    ("Bar Isabel Toronto", "Montréal", "Bar Isabel Toronto"),
    # Never the whole name, and not words that only look like pay.
    ("Toronto", "Toronto", "Toronto"),
    ("Payroll", "", "Payroll"),
    ("Deposit Acme", "", "Deposit Acme"),
    ("Pay Pal", "", "Pay Pal"),
])
def test_rules(raw, city, shown):
    assert tidy(raw, city) == shown


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "tidy.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def test_list_rows_are_tidy_and_renames_win(client):
    when = (TODAY - timedelta(days=1)).isoformat()
    client.st.add_transactions([
        Transaction(date=when, description="BAR ISABEL TORONTO", merchant="Bar Isabel Toronto", amount=100.0,
                    category="Alcohol & Bars", account_id="amex", account_name="Amex",
                    raw={"account_type": "credit", "city": "Toronto"}),
        Transaction(date=when, description="DIRECT DEPOSIT PAYROLL ACME", merchant="Direct Deposit Payroll Acme",
                    amount=-2000.0, category="Income", account_id="chq", account_name="TD",
                    raw={"account_type": "depository"})])
    rows = client.get("/api/transactions/list").get_json()["transactions"]
    names = {r["bank_merchant"]: r["merchant"] for r in rows}
    assert names["Bar Isabel Toronto"] == "Bar Isabel"
    assert names["Direct Deposit Payroll Acme"] == "Acme"
    # The stored merchant is untouched.
    assert {t.merchant for t in client.st.all_transactions()} == {"Bar Isabel Toronto", "Direct Deposit Payroll Acme"}
    # Her rename wins.
    client.st.set_merchant_name("Bar Isabel Toronto", "Isabel's")
    rows = client.get("/api/transactions/list").get_json()["transactions"]
    assert {r["bank_merchant"]: r["merchant"] for r in rows}["Bar Isabel Toronto"] == "Isabel's"
