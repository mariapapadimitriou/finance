"""One review queue: every uncertain row with a best guess and a reason."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

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
    app = create_app(str(tmp_path / "rev.db"))
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
    return {t.description: t for t in st.all_transactions()}


def queue(c):
    return c.get("/api/review").get_json()


def test_a_friends_share_is_matched_to_the_dinner(client):
    rows = load(client.st,
                row(100, "UBER EATS", account="card", kind="credit", when=day(6),
                    category="Food Delivery"),
                row(-25, "E-TRANSFER RECEIVED SAM", when=day(3), who="Sam",
                    issuer="TRANSFER_IN_ACCOUNT_TRANSFER"),
                row(-25.5, "E-TRANSFER RECEIVED JO", when=day(2), who="Jo",
                    issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    q = queue(client)
    items = {i["txn"]["description"]: i for i in q["money_in"]}
    assert set(items) == {"E-TRANSFER RECEIVED SAM", "E-TRANSFER RECEIVED JO"}
    sam = items["E-TRANSFER RECEIVED SAM"]
    assert sam["guess"]["action"] == "payback"
    assert sam["guess"]["charge"]["id"] == rows["UBER EATS"].fingerprint
    assert sam["guess"]["charge"]["split"] == 4
    assert "1/4" in sam["reason"]
    # Accepting it is the ordinary payback link, and the item goes away.
    client.post(f"/api/transactions/{rows['UBER EATS'].fingerprint}/paybacks/"
                f"{rows['E-TRANSFER RECEIVED SAM'].fingerprint}")
    q = queue(client)
    assert [i["txn"]["description"] for i in q["money_in"]] == ["E-TRANSFER RECEIVED JO"]


def test_money_from_your_own_account_is_not_asked_about(client):
    load(client.st, row(300, "TFR-TO 1234567", account="chq"),
         row(-300, "TFR-FR 9999999", account="sav"))
    assert queue(client)["money_in"] == []


def test_unknown_money_in_with_no_match_guesses_your_own(client):
    load(client.st, row(-75, "E-TRANSFER RECEIVED MOM", who="Mom",
                        issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    item = queue(client)["money_in"][0]
    assert item["guess"] == {"action": "own"} and item["candidates"] == []


def test_dismissing_settles_an_item(client):
    rows = load(client.st, row(-75, "E-TRANSFER RECEIVED MOM", who="Mom",
                               issuer="TRANSFER_IN_ACCOUNT_TRANSFER"))
    key = "in:" + rows["E-TRANSFER RECEIVED MOM"].fingerprint
    assert client.post("/api/review/dismiss", json={"key": key}).status_code == 200
    assert queue(client)["money_in"] == []
    assert client.post("/api/review/dismiss", json={}).status_code == 400


def test_unsure_and_other_categories(client):
    rows = load(client.st, row(42, "MYSTERY SHOP 123", account="card", kind="credit"))
    q = queue(client)
    assert [i["txn"]["id"] for i in q["unsure_category"]] == [rows["MYSTERY SHOP 123"].fingerprint]
    assert q["unsure_category"][0]["guess"] == "Other"


def test_income_type_guesses_and_three_paycheque_months(client):
    first = TODAY - timedelta(days=14 * 13)
    pays = [row(-2400, "PAYROLL ACME", when=(first + timedelta(days=14 * i)).isoformat(),
                category="Income") for i in range(14)]
    load(client.st, *pays, row(-60, "ODD DEPOSIT", when=day(2), category="Income"))
    q = queue(client)
    assert [i["txn"]["description"] for i in q["income_type"]] == ["ODD DEPOSIT"]
    assert q["income_type"][0]["guess"] == "other"
    assert q["three_pay_month"], "biweekly pay over half a year holds a third paycheque"
    assert "26" in q["three_pay_month"][0]["reason"]


def test_unsorted_transfers_are_in_the_queue_and_count(client):
    load(client.st, row(200, "SEND E-TFR ***X", who="Landlord Co"))
    q = queue(client)
    assert q["unsorted"]["count"] == 1 and q["unsorted"]["groups"][0]["merchant"] == "Landlord Co"
    assert q["count"] >= 1
    # The old endpoint answers the same.
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


def test_excluded_rows_are_never_asked_about(client):
    rows = load(client.st, row(42, "MYSTERY SHOP 123", account="card", kind="credit"))
    client.put(f"/api/transactions/{rows['MYSTERY SHOP 123'].fingerprint}/exclude",
               json={"reason": "Not mine"})
    assert queue(client)["unsure_category"] == []


def test_each_transfer_is_its_own_item(client):
    rows = load(client.st,
                row(200, "SEND E-TFR ***A", who="Landlord Co", when=day(9)),
                row(200, "SEND E-TFR ***B", who="Landlord Co", when=day(2)))
    q = queue(client)
    listed = q["unsorted"]["transfers"]
    assert [t["to"] for t in listed] == ["Landlord Co", "Landlord Co"]
    assert q["unsorted"]["count"] == 2 and q["count"] >= 2
    # Sorting one leaves the other waiting.
    client.post("/api/transfers/sort", json={"ids": [rows["SEND E-TFR ***A"].fingerprint],
                                             "category": "Saved"})
    left = queue(client)["unsorted"]["transfers"]
    assert [t["id"] for t in left] == [rows["SEND E-TFR ***B"].fingerprint]
