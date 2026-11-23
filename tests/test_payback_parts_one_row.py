"""A deposit split into parts that all paid purchases back is one row in
Cash flow (product owner, 2026-11-23): the deposit, saying what it paid
back, not one row per part on its date. Its page still lists the parts."""

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
    app = create_app(str(tmp_path / "p.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        ingest(st, IngestResult(transactions=[row(40, "GOODLIFE FITNESS", ago(9)), row(25, "CINEPLEX", ago(8)),
                                              row(35, "SUSHI NAMI", ago(7)),
                                              row(-100, "INTERAC E-TRANSFER FROM DENISE", ago(2))], account_id="a"))
        yield c


def ids(client):
    return {t.description: t.fingerprint for t in client.application.config["STORE"].all_transactions()}


def listed(client):
    month = TODAY.strftime("%Y-%m")
    return {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": month, "limit": 100}).get_json()["transactions"]}


def test_three_paybacks_are_one_row(client):
    i = ids(client)
    dep = i["INTERAC E-TRANSFER FROM DENISE"]
    r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "charge": i["GOODLIFE FITNESS"], "amount": 40, "person": "Denise"},
        {"kind": "payback", "charge": i["CINEPLEX"], "amount": 25, "person": "Denise"},
        {"kind": "payback", "charge": i["SUSHI NAMI"], "amount": 35, "person": "Denise"}]})
    assert r.status_code == 200, r.get_json()
    rows = listed(client)
    line = rows[dep]
    assert line["chip"]["label"] == "Paid back" and line["counts"] == "none" and line["excluded"] == ""
    assert line["note"] == "Paid back · Denise · 3 purchases"
    # No part rows on the deposit's date.
    assert not any(r.get("part_of") or (r["date"] == ago(2) and r["id"] != dep) for r in rows.values())
    # The page lists what it paid back; nothing counts twice.
    page = client.get(f"/api/transactions/{dep}").get_json()
    assert [p["charge"]["merchant"] for p in page["parts"]] == ["Goodlife Fitness", "Cineplex", "Sushi Nami"]
    assert page["excluded"] == ""
    # The purchases cost her nothing now.
    totals = client.get("/api/transactions/list", query_string={"month": TODAY.strftime("%Y-%m")}).get_json()["month_totals"]
    assert totals["spent"] == 0


def test_a_mixed_deposit_still_shows_its_parts(client):
    i = ids(client)
    dep = i["INTERAC E-TRANSFER FROM DENISE"]
    r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "charge": i["GOODLIFE FITNESS"], "amount": 40, "person": "Denise"},
        {"kind": "gift", "amount": 60}]})
    assert r.status_code == 200, r.get_json()
    rows = listed(client)
    assert dep not in rows                      # the deposit is left out, its parts stand
    assert sum(1 for r in rows.values() if r["date"] == ago(2)) == 2


def test_one_payback_part_is_the_deposit_row_too(client):
    i = ids(client)
    dep = i["INTERAC E-TRANSFER FROM DENISE"]
    client.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "charge": i["GOODLIFE FITNESS"], "amount": 100, "person": "Denise"}]})
    rows = listed(client)
    assert rows[dep]["note"] == "Paid back · Denise · Goodlife Fitness"
    assert sum(1 for r in rows.values() if r["date"] == ago(2)) == 1
