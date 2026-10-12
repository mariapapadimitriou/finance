"""Bugs found in testing: THL-180 to THL-183."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from finance.transfers import display_name

TODAY = date.today()


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, description, account="chq", when=None, kind="depository",
        category=None, who=None, issuer=""):
    raw = {"account_type": kind, "issuer_category": issuer}
    if who:
        raw["counterparty"] = who
    t = Transaction(date=when or day(1), description=description, amount=amount,
                    account_id=account, account_name=account, raw=raw)
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "bugs.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t.fingerprint for t in st.all_transactions()}


# ── THL-180: e-Transfers say who ─────────────────────────────────────────────

class TestETransferNames:
    def test_from_the_counterparty(self):
        t = row(-40, "INTERAC E-TRANSFER", who="Priya")
        assert display_name(t) == "e-Transfer from Priya"

    def test_to_a_name_in_the_description(self):
        t = row(60, "SEND E-TFR M. PAPAS ***Q7k")
        assert display_name(t) == "e-Transfer to M. Papas"

    def test_nobody_named_is_still_an_e_transfer(self):
        assert display_name(row(25, "SEND E-TFR ***Q7k")) == "e-Transfer"

    def test_anything_else_keeps_its_merchant(self):
        t = row(5, "STARBUCKS 1234 TORONTO ON", account="card", kind="credit")
        assert display_name(t) == t.merchant

    def test_the_list_names_them_and_search_finds_them(self, client):
        load(client.st, row(-40, "INTERAC E-TRANSFER", who="Priya", when=day(2)),
             row(12, "TIM HORTONS", account="card", kind="credit", when=day(2)))
        found = client.get("/api/transactions/list",
                           query_string={"month": day(2)[:7], "q": "priya"}).get_json()
        rows = found["transactions"]
        assert [r["merchant"] for r in rows] == ["e-Transfer from Priya"]


# ── THL-181: splits credit every repayment ───────────────────────────────────

def test_a_nameless_e_transfer_for_exactly_what_someone_owes_is_offered(client):
    ids = load(client.st,
               row(90, "SUSHI NAMI", account="card", kind="credit", when=day(5),
                   category="Dining"),
               row(-30, "INTERAC E-TRANSFER 4821", when=day(1),
                   issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    client.put(f"/api/transactions/{ids['SUSHI NAMI']}/split",
               json={"mode": "even", "people": [{"name": "Priya"}, {"name": "Sam"}]})
    # Even split of $90 three ways: both owe $30, so the amount alone is ambiguous.
    d = client.get(f"/api/transactions/{ids['INTERAC E-TRANSFER 4821']}").get_json()
    assert d["repayment"]["suggestion"] is None
    client.put(f"/api/transactions/{ids['SUSHI NAMI']}/split",
               json={"mode": "amount", "people": [{"name": "Priya", "amount": 30},
                                                  {"name": "Sam", "amount": 20}]})
    d = client.get(f"/api/transactions/{ids['INTERAC E-TRANSFER 4821']}").get_json()
    s = d["repayment"]["suggestion"]
    assert s["name"] == "Priya" and s["by_name"] is False


def test_every_linked_repayment_counts_for_someone(client):
    ids = load(client.st,
               row(90, "SUSHI NAMI", account="card", kind="credit", when=day(5),
                   category="Dining"),
               row(-30, "INTERAC E-TRANSFER 4821", when=day(2),
                   issuer="TRANSFER_IN_ACCOUNT_TRANSFER"),
               row(-20, "INTERAC E-TRANSFER 7710", when=day(1),
                   issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    charge = ids["SUSHI NAMI"]
    client.put(f"/api/transactions/{charge}/split",
               json={"mode": "amount", "people": [{"name": "Priya", "amount": 30},
                                                  {"name": "Sam", "amount": 30}]})
    # Linked without a person: the $30 fits both, the $20 neither exactly.
    for key in ("INTERAC E-TRANSFER 4821", "INTERAC E-TRANSFER 7710"):
        client.post(f"/api/transactions/{charge}/paybacks/{ids[key]}")
    s = client.get(f"/api/transactions/{charge}").get_json()["splitting"]
    assert {u["amount"] for u in s["unassigned"]} == {30, 20}
    # Pearl asks; saying who credits them.
    client.post(f"/api/transactions/{charge}/paybacks/{ids['INTERAC E-TRANSFER 4821']}",
                json={"person": "Sam"})
    s = client.get(f"/api/transactions/{charge}").get_json()["splitting"]
    sam = next(p for p in s["people"] if p["name"] == "Sam")
    assert sam["paid"] + sam["owes"] == pytest.approx(sam["amount"])
    assert sam["owes"] == 0
    # $20 is not what Priya owes ($30), so Pearl still asks who sent it.
    assert [u["amount"] for u in s["unassigned"]] == [20]


def test_a_split_recorded_after_the_e_transfer_is_still_offered(client):
    ids = load(client.st,
               row(-30, "E-TRANSFER RECEIVED PRIYA", who="Priya", when=day(4),
                   issuer="TRANSFER_IN_ACCOUNT_TRANSFER"),
               row(90, "SUSHI NAMI", account="card", kind="credit", when=day(1),
                   category="Dining"))
    client.put(f"/api/transactions/{ids['SUSHI NAMI']}/split",
               json={"mode": "even", "people": [{"name": "Priya"}, {"name": "Sam"}]})
    d = client.get(f"/api/transactions/{ids['E-TRANSFER RECEIVED PRIYA']}").get_json()
    assert [s["charge_id"] for s in d["repayment"]["splits"]] == [ids["SUSHI NAMI"]]


# ── THL-182: a trip lists everything in its dates ────────────────────────────

def test_a_trip_says_what_it_does_not_count_and_counts_it_on_request(client):
    ids = load(client.st,
               row(80, "LOCANDA VERDE NEW YORK NY", account="card", kind="credit", when=day(4)),
               row(45, "WHOLE FOODS NEW YORK NY", account="card", kind="credit", when=day(3),
                   category="Groceries"),
               row(39, "FOREIGN TRANSACTION FEE", account="card", kind="credit", when=day(3),
                   category="Fees & Interest"))
    trip_id = client.post("/api/trips", json={"name": "New York", "start_date": day(5),
                                              "end_date": day(2)}).get_json()["id"]
    trip = client.get(f"/api/trips/{trip_id}").get_json()
    assert [r["id"] for r in trip["counted"]] == [ids["LOCANDA VERDE NEW YORK NY"]]
    why = {r["id"]: r["reason"] for r in trip["not_counted"]}
    assert why[ids["WHOLE FOODS NEW YORK NY"]] == "You filed it as Groceries"
    assert "Fees" in why[ids["FOREIGN TRANSACTION FEE"]]
    after = client.post(f"/api/trips/{trip_id}/include",
                        json={"txn_id": ids["WHOLE FOODS NEW YORK NY"]}).get_json()
    assert ids["WHOLE FOODS NEW YORK NY"] in [r["id"] for r in after["counted"]]
    assert after["total"] == pytest.approx(125)


def test_a_trip_paid_from_a_bank_says_what_it_covered_and_could_not(client):
    bank = client.post("/api/piggy", json={"name": "Travel", "target": 1200,
                                           "cadence": "annual",
                                           "categories": ["Travel"]}).get_json()["id"]
    load(client.st, row(500, "AIR CANADA", account="card", kind="credit", when=day(3)))
    trip_id = client.post("/api/trips", json={"name": "Montreal", "start_date": day(4),
                                              "end_date": day(2)}).get_json()["id"]
    trip = client.get(f"/api/trips/{trip_id}").get_json()
    paid = trip["banks"][0]
    assert paid["id"] == bank and paid["paid"] == 500
    assert paid["held"] + paid["short"] == pytest.approx(500)
    assert trip["from_month"] == 0


# ── THL-183: an even split alone is not a suggestion ─────────────────────────

def test_dividing_evenly_is_not_enough_to_suggest_a_charge(client):
    load(client.st,
         row(100, "UBER EATS", account="card", kind="credit", when=day(6),
             category="Food Delivery"),
         row(-25, "E-TRANSFER RECEIVED SAM", when=day(3), who="Sam",
             issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    item = client.get("/api/review").get_json()["money_in"][0]
    assert item["guess"]["action"] != "payback"
    assert item["candidates"] and not item["candidates"][0]["likely"]
    assert "1/" not in item["reason"]
