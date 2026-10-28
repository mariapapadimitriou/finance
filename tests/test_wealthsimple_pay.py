"""Wealthsimple Pay (2026-10-28): "Cash Received - anastasiapapas" is a
person paying her back, not her own money moving."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.etransfers import handle, is_etransfer, memo, party, person_for
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from finance.splits import from_person, same_person

TODAY = date.today()


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def tx(description, amount=-42.0, account="ws", kind="depository", when=None,
       issuer="TRANSFER_IN_ACCOUNT_TRANSFER"):
    return Transaction(date=when or day(3), description=description, amount=amount,
                       account_id=account, account_name=account,
                       raw={"account_type": kind, "issuer_category": issuer,
                            "plaid_name": description})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "ws.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def ids(st):
    return {t.description: t.fingerprint for t in st.all_transactions()}


@pytest.mark.parametrize("text, tag", [
    ("Cash Received - Anastasiapapas", "Anastasiapapas"),
    ("CASH RECEIVED - anastasiapapas", "anastasiapapas"),
    ("Cash Sent - sam.lee", "sam.lee"),
    ("Cash received – $priya", "priya"),
    ("CASH DEPOSIT", None),
    ("Cash withdrawal - ATM 1234", None),
])
def test_the_handle(text, tag):
    assert handle(tx(text)) == tag


def test_it_reads_as_money_from_a_person():
    t = tx("Cash Received - Anastasiapapas")
    assert is_etransfer(t)
    assert party(t) == {"direction": "from", "handle": "Anastasiapapas",
                        "name": "Anastasiapapas", "named_by": "bank"}
    # The person she knows, when one of her names fits.
    assert party(t, ["Anastasia", "Sam"])["name"] == "Anastasia"
    # No message to find in it: "Cash" is Wealthsimple's word.
    assert memo(t) is None


def test_a_handle_is_the_one_person_it_starts_with():
    assert person_for("anastasiapapas", ["Anastasia Papas"]) == "Anastasia Papas"
    assert person_for("anastasiapapas", ["Ana", "Anastasia"]) is None     # two fit
    assert person_for("alexkim", ["Al"]) is None                          # too short
    assert person_for("samlee", ["Priya"]) is None


def test_the_split_person_is_matched_by_handle():
    t = tx("Cash Received - Anastasiapapas")
    assert from_person(t, "Anastasia")
    assert not from_person(t, "Priya")
    assert same_person("Anastasiapapas", "Anastasia")
    assert same_person("Anastasia", "Anastasiapapas")
    assert not same_person("Anastasia", "Sam")
    assert not same_person("Al", "Alexkim")


def test_her_split_is_suggested(client):
    charge = Transaction(date=day(6), description="SUSHI NAMI", amount=84.0,
                         account_id="card", account_name="card", raw={"account_type": "credit"})
    charge.category, charge.category_source = "Dining", "user"
    ingest(client.st, IngestResult([charge], "card"))
    ingest(client.st, IngestResult([tx("Cash Received - Anastasiapapas")], "ws"))
    i = ids(client.st)
    client.put(f"/api/transactions/{i['SUSHI NAMI']}/split",
               json={"mode": "even", "people": [{"name": "Anastasia"}]})
    item = client.get("/api/review").get_json()["money_in"][0]
    assert item["guess"]["action"] == "split"
    assert item["guess"]["split"]["name"] == "Anastasia"
    # The list shows her name, and that it's waiting.
    rows = client.get("/api/transactions/list", query_string={"month": day(3)[:7]}).get_json()
    row = next(r for r in rows["transactions"] if r["id"] == i["Cash Received - Anastasiapapas"])
    assert row["merchant"] == "Anastasia"
    assert row["chip"]["label"] == "Not sorted yet" and row["chip"]["suggested"]
    assert row["note"] == "Paid back or income? Tell us"


def test_with_no_split_it_asks_whether_she_is_paying_you_back(client):
    ingest(client.st, IngestResult([tx("Cash Received - Anastasiapapas")], "ws"))
    item = client.get("/api/review").get_json()["money_in"][0]
    assert item["from"] == "Anastasiapapas"
    assert item["guess"] == {"action": "person"}
    assert "own" not in item["reason"]


def test_once_sorted_the_list_says_what_it_is(client):
    ingest(client.st, IngestResult([tx("Cash Received - Anastasiapapas")], "ws"))
    tid = ids(client.st)["Cash Received - Anastasiapapas"]
    assert client.post(f"/api/transactions/{tid}/mark", json={"case": "own"}).status_code == 200
    rows = client.get("/api/transactions/list", query_string={"month": day(3)[:7]}).get_json()
    row = next(r for r in rows["transactions"] if r["id"] == tid)
    assert row["chip"]["label"] == "Transfer"


def test_two_paybacks_from_her_grow_one_place_in_the_split(client):
    """Linking by handle then by name is still one person."""
    charge = Transaction(date=day(10), description="COSTCO", amount=120.0,
                         account_id="card", account_name="card", raw={"account_type": "credit"})
    charge.category, charge.category_source = "Groceries", "user"
    ingest(client.st, IngestResult([charge], "card"))
    ingest(client.st, IngestResult([tx("Cash Received - Anastasiapapas", amount=-30.0, when=day(5)),
                                    tx("Cash Received - Anastasiapapas ", amount=-20.0, when=day(4))],
                                   "ws"))
    i = ids(client.st)
    first, second = sorted(t.fingerprint for t in client.st.all_transactions() if t.amount < 0)
    for inflow, person in ((first, "Anastasiapapas"), (second, "Anastasia")):
        res = client.post(f"/api/transactions/{inflow}/mark",
                          json={"case": "payback", "charge": i["COSTCO"], "person": person})
        assert res.status_code == 200, res.get_json()
    people = client.st.splits()[i["COSTCO"]]["people"]
    assert len(people) == 1 and people[0]["amount"] == 50.0


def test_money_you_sent_yourself_is_not_asked_as_a_payback(client, monkeypatch):
    from finance import review
    ingest(client.st, IngestResult([tx("E-TRANSFER RECEIVED MARIA PAPADIMITRIOU")], "chq"))
    monkeypatch.setattr(review, "_me", lambda: "Maria")
    item = client.get("/api/review").get_json()["money_in"][0]
    assert "from" not in item and item["guess"] == {"action": "own"}
