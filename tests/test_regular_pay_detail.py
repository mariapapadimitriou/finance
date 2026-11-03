"""THL-198: a deposit's page says what kind of income it is and, once its
payer is her regular pay, how often it comes; marking it there, with how
often, puts it in Income and bills."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import income_bills as ib
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "pay.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        ingest(c.st, IngestResult([Transaction(
            date=day(4), description="NORTHWIND LTD PAYROLL", merchant="Northwind Ltd", amount=-2150.0,
            category="Income", account_id="chq", account_name="TD Chequing",
            raw={"account_type": "depository"})], "chq"))
        c.pay = c.st.all_transactions()[0].fingerprint
        yield c


def detail(c):
    return c.get(f"/api/transactions/{c.pay}").get_json()


def test_a_deposit_says_its_kind_and_no_regular_pay_yet(client):
    client.put(f"/api/transactions/{client.pay}/income-type", json={"kind": "bonus"})
    d = detail(client)
    assert d["income_type"] == "bonus"
    assert d["regular_pay"] is None


def test_once_its_payer_is_her_pay_it_says_how_often(client):
    client.post(f"/api/transactions/{client.pay}/mark", json={"case": "regular_pay", "remember": True})
    r = client.post("/api/income-bills/pay", json={
        "name": "Northwind Ltd", "payer": "Northwind Ltd", "amount": 2150,
        "cadence": "biweekly", "next": (TODAY + timedelta(days=10)).isoformat()})
    assert r.status_code == 200
    d = detail(client)
    assert d["income_type"] == "salary"
    assert d["regular_pay"]["cadence"] == "biweekly"
    assert d["regular_pay"]["next"] == (TODAY + timedelta(days=10)).isoformat()
    assert [p["payer"] for p in ib.load(client.st)["pays"]] == ["Northwind Ltd"]


def test_money_out_has_neither(client):
    ingest(client.st, IngestResult([Transaction(
        date=day(2), description="LOBLAWS", merchant="Loblaws", amount=40.0, category="Groceries",
        account_id="chq", account_name="TD Chequing", raw={"account_type": "depository"})], "chq"))
    out = next(t for t in client.st.all_transactions() if t.amount > 0).fingerprint
    d = client.get(f"/api/transactions/{out}").get_json()
    assert "income_type" not in d and "regular_pay" not in d
