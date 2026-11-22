"""Unlink from transfer (product owner, 2026-11-22): from the Cash flow row's
menu, a transfer line comes apart into its legs, each its own row, each a
transfer still; Link puts legs together again, and Undo puts the line back."""

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


def row(amount, desc, acct, when):
    return Transaction(date=when, description=desc, amount=amount, account_id=acct,
                       account_name={"a": "Chequing", "b": "Savings", "fam": "Family"}[acct],
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "u.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = app.config["STORE"]
        ingest(st, IngestResult(transactions=[row(200, "TFR-TO 1234567", "a", ago(3)),
                                              row(40, "COFFEE", "a", ago(3))], account_id="a"))
        ingest(st, IngestResult(transactions=[row(-200, "TFR-FR 7654321", "b", ago(3)),
                                              row(200, "RZ363 TFR-TO", "b", ago(2))], account_id="b"))
        ingest(st, IngestResult(transactions=[row(-200, "RZ363 TFR-FR", "fam", ago(2))], account_id="fam"))
        c.put("/api/accounts/fam/joint", json={"label": "Family"})
        yield c


def by_desc(client):
    return {t.description: t for t in client.application.config["STORE"].all_transactions()}


def listed(client):
    month = TODAY.strftime("%Y-%m")
    return {r["id"]: r for r in client.get("/api/transactions/list",
                                           query_string={"month": month, "limit": 100}).get_json()["transactions"]}


LEGS = ("TFR-TO 1234567", "TFR-FR 7654321", "RZ363 TFR-TO", "RZ363 TFR-FR")


def test_the_line_comes_apart_into_its_legs(client):
    t = by_desc(client)
    assert len(listed(client)) == 2                      # the chain's line, and the coffee
    r = client.post(f"/api/transactions/{t['TFR-TO 1234567'].fingerprint}/unpair")
    assert r.status_code == 200 and r.get_json()["title"].startswith("Unlinked")
    assert set(r.get_json()["legs"]) == {t[d].fingerprint for d in LEGS}
    rows = listed(client)
    assert len(rows) == 5
    for d in LEGS:
        leg = rows[t[d].fingerprint]
        assert leg["chip"]["label"] == "Transfer" and "transfer" not in leg and leg["counts"] == "none"
    # Still transfers, and nothing asks about them.
    review = client.get("/api/review").get_json()
    asked = {m["txn"]["id"] for m in review["money_in"]} | {j["txn"]["id"] for j in review["joint_in"]}
    assert not asked & {t[d].fingerprint for d in LEGS}
    page = client.get(f"/api/transactions/{t['RZ363 TFR-FR'].fingerprint}").get_json()
    assert page["unpaired"] is True and "transfer" not in page


def test_from_a_middle_leg_too_and_undo_puts_the_line_back(client):
    t = by_desc(client)
    undo = client.post(f"/api/transactions/{t['RZ363 TFR-TO'].fingerprint}/unpair").get_json()["undo"]
    assert len(listed(client)) == 5
    assert client.post("/api/transactions/undo", json=undo).status_code == 200
    rows = listed(client)
    assert len(rows) == 2 and len(rows[t["TFR-TO 1234567"].fingerprint]["transfer"]["legs"]) == 4


def test_linking_two_legs_again_pairs_them(client):
    t = by_desc(client)
    client.post(f"/api/transactions/{t['TFR-TO 1234567'].fingerprint}/unpair")
    out, into = t["RZ363 TFR-TO"].fingerprint, t["RZ363 TFR-FR"].fingerprint
    assert client.put(f"/api/transactions/{out}/links", json={"ids": [into]}).status_code == 200
    rows = listed(client)
    assert rows[out]["transfer"]["other_id"] == into and into not in rows
    assert t["TFR-TO 1234567"].fingerprint in rows and "transfer" not in rows[t["TFR-TO 1234567"].fingerprint]


def test_a_row_on_its_own_cannot_be_unpaired(client):
    t = by_desc(client)
    assert client.post(f"/api/transactions/{t['COFFEE'].fingerprint}/unpair").status_code == 400
    assert client.post("/api/transactions/nope/unpair").status_code == 404
