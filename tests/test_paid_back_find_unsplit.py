"""Mark as paid back from a purchase that isn't split (product owner,
2026-11-22): "What paid this back?" answered "Couldn't load your money in"
because the finder was only for her share of a split. On a whole purchase
her share is all of it, money in for about that much is LIKELY, and a
person's e-Transfer links as its payback."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, desc, when):
    return Transaction(date=when, description=desc, amount=amount, account_id="a", account_name="Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "f.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        ingest(st, IngestResult(transactions=[row(60, "GOODLIFE FITNESS", ago(6)),
                                              row(-60, "INTERAC E-TRANSFER FROM MOM", ago(2)),
                                              row(-500, "PAYROLL", ago(1))], account_id="a"))
        yield c


def ids(client):
    return {t.description: t.fingerprint for t in client.application.config["STORE"].all_transactions()}


def test_the_finder_works_on_a_whole_purchase(client):
    i = ids(client)
    body = client.get(f"/api/transactions/{i['GOODLIFE FITNESS']}/paid-back-find").get_json()
    assert body["share"] == 60 and body["left"] == 60 and body["amount"] == 60
    likely = {c["id"]: c for c in body["candidates"]}
    assert i["INTERAC E-TRANSFER FROM MOM"] in likely and likely[i["INTERAC E-TRANSFER FROM MOM"]]["likely"] is True
    assert i["PAYROLL"] not in likely
    found = client.get(f"/api/transactions/{i['GOODLIFE FITNESS']}/paid-back-find", query_string={"q": "500"}).get_json()
    assert [c["id"] for c in found["candidates"]] == [i["PAYROLL"]]


def test_a_persons_money_links_as_the_payback(client):
    i = ids(client)
    purchase, money = i["GOODLIFE FITNESS"], i["INTERAC E-TRANSFER FROM MOM"]
    r = client.post(f"/api/transactions/{money}/parts",
                    json={"parts": [{"kind": "payback", "charge": purchase, "amount": 60, "person": "Mom"}]})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["title"] == "Mom paid back $60.00"
    deposit = client.get(f"/api/transactions/{money}").get_json()
    assert [(p["kind"], p["person"], p["charge"]["id"]) for p in deposit["parts"]] == [("payback", "Mom", purchase)]
    # The purchase's PAID BACK lists the part that paid it.
    assert deposit["parts"][0]["id"] in {x["id"] for x in client.get(f"/api/transactions/{purchase}").get_json()["repaid_by"]}
    after = client.get(f"/api/transactions/{purchase}/paid-back-find").get_json()
    assert after["left"] == 0 and money not in {c["id"] for c in after["candidates"]}


def test_money_in_and_a_missing_purchase_are_refused(client):
    i = ids(client)
    assert client.get(f"/api/transactions/{i['PAYROLL']}/paid-back-find").status_code == 400
    assert client.get("/api/transactions/nope/paid-back-find").status_code == 404
