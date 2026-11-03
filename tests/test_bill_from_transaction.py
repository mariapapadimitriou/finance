"""Add to your bills? (T-32): a purchase becomes a bill, with how often it
repeats, the next payment, her share and its category."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def tx(desc, amount, when, category="Groceries"):
    return Transaction(date=when.isoformat(), description=desc, merchant=desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "bill.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def bills(c):
    return c.get("/api/income-bills").get_json()["bills"]


def test_a_new_bill_from_a_purchase(client):
    i = add(client, tx("LOBLAWS", 84.12, TODAY - timedelta(days=2)))
    s = client.get(f"/api/transactions/{i['LOBLAWS']}/bill").get_json()
    assert s["cadence"] == "monthly" and s["share"] == 100 and s["category"] == "Groceries"
    assert s["next"] > TODAY.isoformat() and s["is_bill"] is False
    r = client.post(f"/api/transactions/{i['LOBLAWS']}/bill",
                    json={"cadence": "weekly", "next": s["next"], "share": 50, "category": "Groceries"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["title"] == "LOBLAWS is in your bills: $42.06 every week."
    b = next(b for b in bills(client) if b["key"] == r.get_json()["key"])
    assert (b["amount"], b["cadence"], b["category"], b["counts"]) == (42.06, "weekly", "Groceries", True)


def test_a_bill_pearl_found_is_the_one_that_counts(client):
    rows = [tx("ROGERS", 95.0, TODAY - timedelta(days=30 * k), category="Phone & Internet")
            for k in range(1, 5)]
    i = add(client, *rows)
    tid = next(iter(i.values()))
    before = len(bills(client))
    r = client.post(f"/api/transactions/{tid}/bill", json={"cadence": "monthly",
                                                          "next": (TODAY + timedelta(days=5)).isoformat()})
    assert r.status_code == 200, r.get_json()
    assert not r.get_json()["key"].startswith("added:")
    assert len(bills(client)) == before
    assert next(b for b in bills(client) if b["key"] == r.get_json()["key"])["counts"] is True


def test_what_it_refuses(client):
    i = add(client, tx("LOBLAWS", 84.12, TODAY), tx("PAY", -500.0, TODAY, category="Income"))
    nxt = (TODAY + timedelta(days=7)).isoformat()
    assert client.post(f"/api/transactions/{i['PAY']}/bill",
                       json={"cadence": "weekly", "next": nxt}).status_code == 400
    assert client.post(f"/api/transactions/{i['LOBLAWS']}/bill",
                       json={"cadence": "daily", "next": nxt}).status_code == 400
    assert client.post(f"/api/transactions/{i['LOBLAWS']}/bill",
                       json={"cadence": "weekly", "next": nxt, "share": 0}).status_code == 400
