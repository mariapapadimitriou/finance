"""The product owner's $30.00 e-Transfer from "anastasia papadimitriou"
(2026-11-17, main at 7389863): Paid back › A person opened Who paid you
back? (PP-01) with no one in it, over a spinner that never ended.

The bank's merchant on an e-Transfer is often only "E-Transfer"; the person
is in the description or Plaid's payer, which is how the list shows them.
GET …/owing matched the merchant, so the Anastasia of her splits wasn't the
sender and the app asked. Now …/owing reads the e-Transfer's person, as
…/candidates does, and a clear first-name match is hers (#372).
"""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

from tests.test_payback_existing_split import ago, buy, client, ids, ok  # noqa: F401

SENT = [
    ("E-TRANSFER RECEIVED anastasia papadimitriou", "E-Transfer", {}),
    ("Interac e-Transfer", "Interac e-Transfer", {"payer": "anastasia papadimitriou"}),
    ("e-Transfer", None, {"counterparty": "anastasia papadimitriou"}),
    ("anastasia papadimitriou", "anastasia papadimitriou", {}),
]


def setup(c, desc, merchant, raw, people=(("Anastasia", 30.0),)):
    ingest(c.st, IngestResult([buy("Costco", 90.0)], "amex"))
    t = Transaction(date=ago(1), description=desc, merchant=merchant, amount=-30.0, category="",
                    account_id="chq", account_name="Chequing ••4417",
                    raw={"account_type": "depository", **raw})
    ingest(c.st, IngestResult([t], "chq"))
    i = ids(c)
    ok(c.put(f"/api/transactions/{i['COSTCO']}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": a} for n, a in people]}))
    return i["COSTCO"], i[desc]


@pytest.mark.parametrize("desc,merchant,raw", SENT)
def test_etransfer_from_full_name_is_the_split_person(client, desc, merchant, raw):
    costco, dep = setup(client, desc, merchant, raw)
    r = ok(client.get(f"/api/transactions/{dep}/owing"))
    assert r["from"] == "Anastasia"
    assert r["named"] is None
    owing = [i for i in r["items"] if i["person"] and i["owes"] >= 0.005]
    assert owing, "the owing list is never empty while she's owed"
    assert [(i["id"], i["person"], i["theirs"], i["owes"]) for i in owing] == [(costco, "Anastasia", True, 30.0)]


def test_someone_else_owing_still_lists_them(client):
    """A sender on none of her splits: no `from`, and everyone who owes her
    is listed for PP-01, never an empty list."""
    _, dep = setup(client, "E-TRANSFER RECEIVED Jordan Smith", "E-Transfer", {})
    r = ok(client.get(f"/api/transactions/{dep}/owing"))
    assert r["from"] is None
    assert [i["person"] for i in r["items"] if i["owes"] >= 0.005] == ["Anastasia"]


def test_picked_person_wins_over_the_bank(client):
    """PP-01's pick (…/owing?person=) is who it's from, whatever the bank says."""
    _, dep = setup(client, "E-TRANSFER RECEIVED Jordan Smith", "E-Transfer", {},
                   people=(("Anastasia", 15.0), ("Sam", 15.0)))
    r = ok(client.get(f"/api/transactions/{dep}/owing?person=Sam"))
    assert r["from"] == "Sam"
    assert [i["person"] for i in r["items"] if i["theirs"]] == ["Sam"]


def test_nobody_owing_is_empty_for_pb15(client):
    """No one owes her: no items, and the name for PB-15."""
    ingest(client.st, IngestResult([Transaction(
        date=ago(1), description="E-TRANSFER RECEIVED Jordan Smith", merchant="E-Transfer", amount=-30.0,
        category="", account_id="chq", account_name="Chequing ••4417", raw={"account_type": "depository"})], "chq"))
    dep = ids(client)["E-TRANSFER RECEIVED Jordan Smith"]
    r = ok(client.get(f"/api/transactions/{dep}/owing"))
    assert r["from"] is None and r["items"] == []
    assert r["named"] == "Jordan Smith"
