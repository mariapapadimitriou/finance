"""Add a transaction by hand from the iPhone (T-23, T-61, T-62): what it was
paid with, money in and its kind, and the duplicate check."""

from __future__ import annotations

from datetime import date

import pytest

TODAY = date.today().isoformat()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "add.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, **body):
    return c.post("/api/transactions", json={"date": TODAY, **body})


def test_cash_purchase(client):
    r = add(client, description="Farmers' market", amount=24, category="Groceries", account="cash")
    assert r.status_code == 200, r.get_json()
    d = client.get(f"/api/transactions/{r.get_json()['id']}").get_json()
    assert d["category"] == "Groceries" and d["amount"] == 24
    t = client.st.get_transaction(r.get_json()["id"])
    assert (t.account_id, t.account_name, t.source) == ("cash", "Cash", "manual")


def test_paid_with_a_hand_account(client):
    acct = client.st.add_manual_account("Costco Mastercard", "credit", 0, TODAY)
    r = add(client, description="Costco", amount=80, category="Groceries", account=acct)
    assert r.status_code == 200, r.get_json()
    assert client.st.get_transaction(r.get_json()["id"]).account_name == "Costco Mastercard"
    assert add(client, description="X", amount=5, account="hand:999").status_code == 400


def test_money_in_with_its_kind(client):
    r = add(client, description="Cash gift", amount=-150, category="Income", account="cash",
            income_kind="gifts")
    assert r.status_code == 200, r.get_json()
    d = client.get(f"/api/transactions/{r.get_json()['id']}").get_json()
    assert d["counts"] == "income" and d["income_type"] == "gifts"
    assert add(client, description="Y", amount=-5, category="Income", income_kind="lottery").status_code == 400


def test_a_second_one_asks_first(client):
    add(client, description="Farmers' market", amount=24, category="Groceries", account="cash")
    r = add(client, description="Market", amount=24, category="Groceries", account="cash")
    assert r.status_code == 409
    body = r.get_json()
    assert body.get("needs_confirmation") or body.get("duplicate")
