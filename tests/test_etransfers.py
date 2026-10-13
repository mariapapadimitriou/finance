"""Who an e-Transfer was from or to (THL-122): the name she typed, the
bank feed's counterparty, or the words left once the bank's are taken out."""

from __future__ import annotations

import pytest

from finance.etransfers import _name_in, is_etransfer, party
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def tx(description, amount=-50.0, counterparty=None, merchant=""):
    raw = {"counterparty": counterparty} if counterparty else {}
    return Transaction(date="2026-10-05", description=description, amount=amount,
                       account_id="chq", account_name="chq", merchant=merchant, raw=raw)


@pytest.mark.parametrize("text, name", [
    ("E-TRANSFER RECEIVED PRIYA SHAH", "Priya Shah"),
    ("INTERAC E-TRF FROM SAM", "Sam"),
    ("Interac e-Transfer From: Jane O'Neil", "Jane O'Neil"),
    ("E-TRANSFER ***Q7k ANA LOPEZ", "Ana Lopez"),
    ("AUTODEPOSIT E-TRANSFER CA4Rk2Z MOM", "Mom"),
    ("SEND E-TFR ***Mom1", None),
    ("E-TRANSFER 104728302", None),
    ("INTERAC E-TRANSFER FEE", None),
])
def test_names_in_bank_wording(text, name):
    assert _name_in(text) == name


def test_direction_and_who_named_it():
    assert party(tx("E-TRANSFER RECEIVED PRIYA")) == {
        "direction": "from", "name": "Priya", "named_by": "bank"}
    sent = party(tx("SEND E-TFR ***Mom1", amount=80))
    assert sent == {"direction": "to", "name": None, "named_by": None}
    assert party(tx("LOBLAWS", amount=80)) is None


def test_the_feeds_counterparty_wins_over_the_description():
    t = tx("E-TRANSFER ***Q7k", counterparty="Ana Lopez")
    assert party(t)["name"] == "Ana Lopez"
    # A bank named as the counterparty is no one.
    assert party(tx("E-TRANSFER ***Q7k", counterparty="TD Bank"))["name"] is None


def test_the_name_she_typed_wins():
    t = tx("SEND E-TFR ***Mom1", amount=80)
    t.party = "Mom"
    assert party(t) == {"direction": "to", "name": "Mom", "named_by": "you"}
    assert is_etransfer(t)


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "et.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def listed(c, tid):
    rows = c.get("/api/transactions/list", query_string={"month": "2026-10"}).get_json()
    return next(r for r in rows["transactions"] if r["id"] == tid)


def test_the_list_shows_the_person_and_she_can_name_one(client):
    ingest(client.st, IngestResult([tx("E-TRANSFER RECEIVED PRIYA SHAH"),
                                    tx("SEND E-TFR ***Mom1", amount=80),
                                    tx("LOBLAWS", amount=30)], "chq"))
    ids = {t.description: t.fingerprint for t in client.st.all_transactions()}
    assert listed(client, ids["E-TRANSFER RECEIVED PRIYA SHAH"])["merchant"] == "Priya Shah"
    sent = ids["SEND E-TFR ***Mom1"]
    assert listed(client, sent)["etransfer"]["name"] is None
    r = client.put(f"/api/transactions/{sent}/party", json={"name": "  Mom  "})
    assert r.status_code == 200
    row = listed(client, sent)
    assert row["merchant"] == "Mom" and row["etransfer"]["named_by"] == "you"
    found = client.get("/api/transactions/list",
                       query_string={"month": "2026-10", "q": "mom"}).get_json()
    assert [r["id"] for r in found["transactions"]] == [sent]
    client.put(f"/api/transactions/{sent}/party", json={"name": ""})
    assert listed(client, sent)["etransfer"]["name"] is None
    assert client.put(f"/api/transactions/{ids['LOBLAWS']}/party",
                      json={"name": "Mom"}).status_code == 400


def test_a_name_she_typed_matches_a_split(client):
    """The bank said no name; she said Priya; Priya's split is suggested."""
    charge = Transaction(date="2026-10-04", description="SUSHI", amount=85.0,
                         account_id="card", account_name="card", raw={"account_type": "credit"})
    charge.category, charge.category_source = "Dining", "user"
    inflow = tx("E-TRANSFER ***Q7k", amount=-42.5)
    inflow.raw = {"account_type": "depository"}
    ingest(client.st, IngestResult([charge], "card"))
    ingest(client.st, IngestResult([inflow], "chq"))
    ids = {t.description: t.fingerprint for t in client.st.all_transactions()}
    client.put(f"/api/transactions/{ids['SUSHI']}/split",
               json={"mode": "even", "people": [{"name": "Priya"}]})
    detail = client.get(f"/api/transactions/{ids['E-TRANSFER ***Q7k']}").get_json()
    assert detail["repayment"]["suggestion"] is None
    client.put(f"/api/transactions/{ids['E-TRANSFER ***Q7k']}/party", json={"name": "Priya"})
    detail = client.get(f"/api/transactions/{ids['E-TRANSFER ***Q7k']}").get_json()
    assert detail["repayment"]["suggestion"]["charge_id"] == ids["SUSHI"]
