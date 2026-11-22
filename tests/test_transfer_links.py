"""Link transfers (product owner, 2026-11-22): $200 moved from one account to
a second and on into a joint one; two legs paired and one was left on its
own. Legs she links are one movement of money: every one a transfer, none
asked about, the list shows them as one line, and Undo takes the link back."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from finance.transfers import UNSORTED
from ledger_files import set_plan

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, description, account, days_ago):
    return Transaction(date=ago(days_ago), description=description, amount=amount,
                       account_id=account, account_name={"chq": "Chequing", "sav": "Savings"}[account],
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "api.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        # Four days apart: too far for Pearl to pair them on its own.
        ingest(st, IngestResult(transactions=[row(200, "SEND E-TFR ***abc", "chq", 5),
                                              row(200, "SEND E-TFR ***old", "chq", 30)], account_id="chq"))
        ingest(st, IngestResult(transactions=[row(-200, "RZ363 TFR-FR", "sav", 1)], account_id="sav"))
        yield c


def ids(client):
    return {t.description: t.fingerprint for t in client.application.config["STORE"].all_transactions()}


def txn(client, tid):
    return client.get(f"/api/transactions/{tid}").get_json()


def listed(client):
    month = TODAY.strftime("%Y-%m")
    rows = client.get("/api/transactions/list", query_string={"month": month, "limit": 200}).get_json()["transactions"]
    return {r["id"]: r for r in rows}


def test_on_their_own_each_leg_is_asked_about(client):
    i = ids(client)
    assert txn(client, i["SEND E-TFR ***abc"])["category"] == UNSORTED
    asked = {m["txn"]["id"] for m in client.get("/api/review").get_json()["money_in"]}
    assert i["RZ363 TFR-FR"] in asked


def test_candidates_are_the_same_amount_within_a_week(client):
    i = ids(client)
    body = client.get(f"/api/transactions/{i['SEND E-TFR ***abc']}/link-candidates").get_json()
    assert [r["id"] for r in body["rows"]] == [i["RZ363 TFR-FR"]]
    assert body["rows"][0]["linked"] is False and body["rows"][0]["account_name"]


def test_linking_makes_the_legs_one_transfer(client):
    i = ids(client)
    out, into = i["SEND E-TFR ***abc"], i["RZ363 TFR-FR"]
    r = client.put(f"/api/transactions/{out}/links", json={"ids": [into]})
    assert r.status_code == 200 and r.get_json()["title"].startswith("Linked")
    assert txn(client, out)["category"] == "Transfers"
    assert txn(client, into)["category"] == "Transfers"
    # Neither is a question any more.
    review = client.get("/api/review").get_json()
    assert into not in {m["txn"]["id"] for m in review["money_in"]}
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1   # only the old one
    # The page shows the other leg; the list shows them as one line.
    assert [l["id"] for l in txn(client, out)["links"]] == [into]
    rows = listed(client)
    assert rows[out]["transfer"]["other_id"] == into and into not in rows
    # The candidates now come back ticked.
    body = client.get(f"/api/transactions/{into}/link-candidates").get_json()
    assert body["rows"][0]["id"] == out and body["rows"][0]["linked"] is True


def test_unlink_sorts_each_one_again(client):
    i = ids(client)
    out, into = i["SEND E-TFR ***abc"], i["RZ363 TFR-FR"]
    client.put(f"/api/transactions/{out}/links", json={"ids": [into]})
    r = client.put(f"/api/transactions/{out}/links", json={"ids": []})
    assert r.status_code == 200 and r.get_json()["title"].startswith("Unlinked")
    assert txn(client, out)["category"] == UNSORTED and "links" not in txn(client, out)
    assert into in {m["txn"]["id"] for m in client.get("/api/review").get_json()["money_in"]}


def test_undo_puts_the_link_back_as_it_was(client):
    i = ids(client)
    out, into = i["SEND E-TFR ***abc"], i["RZ363 TFR-FR"]
    undo = client.put(f"/api/transactions/{out}/links", json={"ids": [into]}).get_json()["undo"]
    assert undo["marks"]["transfer_links"] == {out: None, into: None}
    assert client.post("/api/transactions/undo", json=undo).status_code == 200
    assert txn(client, out)["category"] == UNSORTED and "links" not in txn(client, out)


def test_a_leg_sorted_by_hand_becomes_a_transfer_too(client):
    i = ids(client)
    out, into = i["SEND E-TFR ***abc"], i["RZ363 TFR-FR"]
    client.application.config["STORE"].set_transaction_category(out, "Gifts")
    assert txn(client, out)["category"] == "Gifts"
    client.put(f"/api/transactions/{out}/links", json={"ids": [into]})
    assert txn(client, out)["category"] == "Transfers"


def test_only_rows_pearl_knows(client):
    i = ids(client)
    out = i["SEND E-TFR ***abc"]
    assert client.put(f"/api/transactions/{out}/links", json={"ids": ["nope"]}).status_code == 400
    assert client.put(f"/api/transactions/{out}/links", json={"ids": [out]}).status_code == 400
    assert client.put("/api/transactions/nope/links", json={"ids": [out]}).status_code == 404
