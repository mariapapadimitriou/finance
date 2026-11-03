"""Setup's Your pay and bills (O-10f, O-10g): pay into a joint account asks
whose it is, and someone's regular e-Transfers ask what they are — their
share of a bill comes off that bill."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def tx(desc, amount, days_ago, account, merchant, category):
    return Transaction(date=(TODAY - timedelta(days=days_ago)).isoformat(), description=desc,
                       merchant=merchant, amount=amount, category=category, account_id=account,
                       account_name=account, raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "asks.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def payload(c):
    return c.get("/api/income-bills").get_json()


def joint_pay(c):
    rows = [tx(f"MAPLE CO PAYROLL {k}", -1980.0, 3 + 14 * k, "sav", "Maple Co", "Income") for k in range(4)]
    ingest(c.st, IngestResult(rows, "sav"))
    c.st.set_joint_people("sav", ["Sam"])
    return rows


def sam_etransfers(c):
    rows = [tx(f"INTERAC E-TRANSFER {k} SAM", -725.0, 2 + 30 * k, "chq", "Sam", "Other") for k in range(3)]
    ingest(c.st, IngestResult(rows, "chq"))
    return rows


def test_joint_pay_asks_whose_it_is(client):
    joint_pay(client)
    asks = payload(client)["asks"]
    ask = next(a for a in asks if a["kind"] == "joint")
    assert (ask["name"], ask["people"], ask["cadence"], ask["amount"]) == ("Maple Co", ["Sam"], "biweekly", 1980.0)
    assert not any(c["payer"] == "Maple Co" for c in payload(client)["candidates"])
    # Both of us, remembered for Maple Co: her half is the pay setup offers.
    r = client.put(f"/api/transactions/{ask['txn']}/joint-from", json={"who": "both", "remember": True})
    assert r.status_code == 200
    p = payload(client)
    assert not any(a["kind"] == "joint" for a in p["asks"])
    pay = next(c for c in p["candidates"] if c["payer"] == "Maple Co")
    assert pay["amount"] == 990.0


def test_this_isnt_regular_pay(client):
    joint_pay(client)
    r = client.post("/api/income-bills/pay/answer", json={"payer": "Maple Co", "answer": "no"})
    assert r.status_code == 200
    assert not r.get_json()["asks"]


def test_sams_share_of_rent_comes_off_rent(client):
    sam_etransfers(client)
    ask = next(a for a in payload(client)["asks"] if a["kind"] == "etransfer")
    assert (ask["person"], ask["amount"], ask["cadence"]) == ("Sam", 725.0, "monthly")
    rent = client.post("/api/income-bills/bills", json={
        "name": "Rent", "amount": 1450, "cadence": "monthly",
        "next": (TODAY + timedelta(days=10)).isoformat()}).get_json()
    key = next(b["key"] for b in rent["bills"] if b["name"] == "Rent")
    r = client.post("/api/income-bills/etransfer", json={"payer": "Sam", "answer": "share", "bill": key})
    assert r.status_code == 200, r.get_json()
    bill = next(b for b in r.get_json()["bills"] if b["key"] == key)
    assert bill["amount"] == 725.0 and bill["shared"] == {"person": "Sam", "amount": 725.0}
    assert not r.get_json()["asks"]
    assert all(client.st.get_transaction(i).excluded for i in ask["ids"])
    assert r.get_json()["totals"]["bills"] == 725.0


def test_paying_me_back_is_not_income(client):
    sam_etransfers(client)
    ask = next(a for a in payload(client)["asks"] if a["kind"] == "etransfer")
    r = client.post("/api/income-bills/etransfer", json={"payer": "Sam", "answer": "payback"})
    assert r.status_code == 200, r.get_json()
    assert not r.get_json()["asks"]
    assert all(client.st.get_transaction(i).category != "Income" for i in ask["ids"])
    assert client.post("/api/income-bills/etransfer", json={"payer": "Sam", "answer": "else"}).status_code == 404
