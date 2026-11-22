"""Her own money into a joint account (product owner, 2026-11-22): $200 went
from account A to B, then B to the family account C. A→B paired, but C's
arrival asked "Whose?" and B's departure showed as a lone transfer. Money
Pearl saw leave her own account is hers: the deposit is answered Me, the
legs pair in the list, and nothing asks."""

from __future__ import annotations

import os
from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, desc, acct, when):
    return Transaction(date=when, description=desc, amount=amount, account_id=acct,
                       account_name={"a": "Chequing", "b": "Savings", "fam": "Family"}[acct],
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "x.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        ingest(st, IngestResult(transactions=[row(200, "TFR-TO 1234567", "a", ago(3))], account_id="a"))
        ingest(st, IngestResult(transactions=[row(-200, "TFR-FR 7654321", "b", ago(3)),
                                              row(200, "RZ363 TFR-TO", "b", ago(2))], account_id="b"))
        ingest(st, IngestResult(transactions=[row(-200, "RZ363 TFR-FR", "fam", ago(2)),
                                              row(-150, "MOM E-TRANSFER", "fam", ago(1))], account_id="fam"))
        c.put("/api/accounts/fam/joint", json={"label": "Family", "people": ["Mom"]})
        yield c


def by_desc(client):
    return {t.description: t for t in client.application.config["STORE"].all_transactions()}


def test_the_arrival_from_her_own_account_is_hers_and_the_legs_pair(client):
    t = by_desc(client)
    into = t["RZ363 TFR-FR"]
    assert into.joint_from == "me" and into.category == "Transfers"
    out = t["RZ363 TFR-TO"]
    assert out.category == "Transfers"
    month = TODAY.strftime("%Y-%m")
    rows = {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": month, "limit": 100}).get_json()["transactions"]}
    # One line for the whole chain (2026-11-22): A's departure, ending in Family.
    assert out.fingerprint not in rows and into.fingerprint not in rows
    line = rows[t["TFR-TO 1234567"].fingerprint]["transfer"]
    assert line["other_id"] == into.fingerprint and out.fingerprint in line["legs"]
    review = client.get("/api/review").get_json()
    assert into.fingerprint not in {j["txn"]["id"] for j in review["joint_in"]}
    page = client.get(f"/api/transactions/{into.fingerprint}").get_json()
    assert page["joint_from"] == "me" and page["transfer"]["other_id"] == out.fingerprint


def test_a_deposit_from_outside_still_asks(client):
    t = by_desc(client)
    mom = t["MOM E-TRANSFER"]
    assert mom.joint_from is None
    assert mom.fingerprint in {j["txn"]["id"] for j in client.get("/api/review").get_json()["joint_in"]}


def test_her_answer_stands(client):
    t = by_desc(client)
    into = t["RZ363 TFR-FR"]
    assert client.put(f"/api/transactions/{into.fingerprint}/joint-from", json={"who": "them"}).status_code == 200
    assert by_desc(client)["RZ363 TFR-FR"].joint_from == "them"


def test_before_the_match_answers_it_the_rows_still_read_as_one_transfer(client):
    """Until the ledger is sorted again (a sync or an edit), the deposit has
    no answer yet; the list must not show the transfer line and a "Whose?"
    row for the same money."""
    t = by_desc(client)
    into, out = t["RZ363 TFR-FR"], t["RZ363 TFR-TO"]
    client.application.config["STORE"].set_joint_deposit(into.fingerprint, None)
    assert by_desc(client)["RZ363 TFR-FR"].joint_from is None
    rows = listed(client)
    assert into.fingerprint not in rows and out.fingerprint not in rows
    assert rows[t["TFR-TO 1234567"].fingerprint]["transfer"]["other_id"] == into.fingerprint
    page = client.get(f"/api/transactions/{into.fingerprint}").get_json()
    assert page["chip"]["label"] == "Transfer" and page["transfer"]["other_id"] == out.fingerprint


def listed(client):
    month = TODAY.strftime("%Y-%m")
    return {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": month, "limit": 100}).get_json()["transactions"]}


def test_the_chain_is_one_line_from_the_first_account_to_the_last(client):
    """Product owner, 2026-11-22: A→B and B→C consolidated into one line."""
    t = by_desc(client)
    head = t["TFR-TO 1234567"]
    rows = listed(client)
    for leg in ("TFR-FR 7654321", "RZ363 TFR-TO", "RZ363 TFR-FR"):
        assert t[leg].fingerprint not in rows
    line = rows[head.fingerprint]["transfer"]
    assert line["other_id"] == t["RZ363 TFR-FR"].fingerprint
    assert "Family" in line["to"] and len(line["via"]) == 1 and "Savings" in line["via"][0]
    assert line["legs"] == [head.fingerprint, t["TFR-FR 7654321"].fingerprint,
                            t["RZ363 TFR-TO"].fingerprint, t["RZ363 TFR-FR"].fingerprint]
    page = client.get(f"/api/transactions/{head.fingerprint}").get_json()
    assert page["transfer"]["other_id"] == t["RZ363 TFR-FR"].fingerprint and page["transfer"]["via"] == line["via"]
    # The middle legs' own pages still show their own pair.
    mid = client.get(f"/api/transactions/{t['RZ363 TFR-TO'].fingerprint}").get_json()
    assert mid["transfer"]["other_id"] == t["RZ363 TFR-FR"].fingerprint and "via" not in mid["transfer"]


def test_money_that_left_again_weeks_later_is_not_a_chain(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "y.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        ingest(st, IngestResult(transactions=[row(200, "TFR-TO 1234567", "a", ago(20))], account_id="a"))
        ingest(st, IngestResult(transactions=[row(-200, "TFR-FR 7654321", "b", ago(20)),
                                              row(200, "RZ363 TFR-TO", "b", ago(2))], account_id="b"))
        ingest(st, IngestResult(transactions=[row(-200, "RZ363 TFR-FR", "fam", ago(2))], account_id="fam"))
        c.put("/api/accounts/fam/joint", json={"label": "Family"})
        t = {x.description: x for x in st.all_transactions()}
        rows = listed(c)
        assert rows[t["TFR-TO 1234567"].fingerprint]["transfer"]["other_id"] == t["TFR-FR 7654321"].fingerprint
        assert rows[t["RZ363 TFR-TO"].fingerprint]["transfer"]["other_id"] == t["RZ363 TFR-FR"].fingerprint
        assert "via" not in rows[t["TFR-TO 1234567"].fingerprint]["transfer"]
