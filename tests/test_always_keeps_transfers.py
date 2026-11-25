"""Always for a merchant leaves her own transfers alone (2026-11-25).

"Always Utilities for Maple Court" moved every row of that name, a $200 move
between two of her accounts included, which then counted as spending. A rule
for a name files what that name is paid; money that moved between her own
accounts is a transfer whatever it's called. Demo data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all
from finance.transfers import transfer_pairs

TODAY = date.today()
OUT, IN = "TRANSFER_OUT_ACCOUNT_TRANSFER", "TRANSFER_IN_ACCOUNT_TRANSFER"


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def tx(amount, ago, account="A", name="MAPLE COURT", code=None, **raw):
    return Transaction(date=day(ago), description=name, amount=amount, account_id=account,
                       account_name=account, source="plaid",
                       raw={"account_type": "depository",
                            "issuer_category": code or (OUT if amount > 0 else IN), **raw})


def load(st, *rows):
    for acct in {r.account_id for r in rows}:
        ingest(st, IngestResult([r for r in rows if r.account_id == acct], acct))


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "a.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def by(c):
    return {(t.account_id, t.amount, t.date): t for t in c.st.all_transactions()}


def cat(c, amount, ago, account="A"):
    return by(c)[(account, amount, day(ago))].category


def always(c, amount=60, ago=10):
    t = by(c)[("A", amount, day(ago))]
    r = c.post(f"/api/transactions/{t.fingerprint}/mark",
               json={"case": "spending", "category": "Utilities", "remember": True})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def ledger(c):
    load(c.st, tx(60, 10), tx(64, 80), tx(200, 120),
         tx(-200, 119, "B", "TRANSFER IN"))


def test_a_matched_transfer_stays_and_the_bills_move(client):
    ledger(client)
    always(client)
    assert cat(client, 60, 10) == cat(client, 64, 80) == "Utilities"
    assert cat(client, 200, 120) == "Transfers"
    assert len(transfer_pairs(client.st.all_transactions())) == 1


def test_it_holds_after_a_resort_and_a_sync(client):
    ledger(client)
    # As on a ledger already migrated: the rule stays a merchant rule.
    client.st.set_setting("destinations_migrated", "1")
    always(client)
    recategorize_all(client.st)
    assert client.st.overrides()
    assert cat(client, 200, 120) == "Transfers" and cat(client, 64, 80) == "Utilities"
    load(client.st, tx(200, 2), tx(-200, 1, "B", "TRANSFER IN"), tx(61, 3))
    assert cat(client, 200, 2) == "Transfers" and cat(client, 61, 3) == "Utilities"


def test_the_other_end_arriving_later_clears_it(client):
    load(client.st, tx(60, 10))
    always(client)
    load(client.st, tx(200, 3))
    assert cat(client, 200, 3) == "Utilities"
    load(client.st, tx(-200, 2, "B", "TRANSFER IN"))
    assert cat(client, 200, 3) == "Transfers"


@pytest.mark.parametrize("name", ["INTERAC E-TRANSFER FROM ALEX", "E-TRANSFER AUTODEPOSIT SAM"])
def test_a_friends_e_transfer_is_not_the_other_end_of_a_bill(client, name):
    load(client.st, tx(60, 10))
    always(client)
    load(client.st, tx(75, 4), tx(-75, 4, "B", name))
    assert cat(client, 75, 4) == "Utilities"


def test_a_transfer_with_no_rule_gets_its_arrival_first(client):
    load(client.st, tx(60, 10))
    always(client)
    load(client.st, tx(90, 5), tx(90, 4, name="SAVINGS MOVE"), tx(-90, 4, "B", "TRANSFER IN"))
    assert cat(client, 90, 5) == "Utilities" and cat(client, 90, 4) == "Transfers"


def test_a_purchase_under_a_rule_is_never_paired(client):
    load(client.st, tx(40, 9, name="LOBLAWS", code="FOOD_AND_DRINK_GROCERIES"),
         tx(-40, 9, "B", "TRANSFER IN"))
    client.st.set_override("Loblaws", "Groceries")
    assert cat(client, 40, 9) == "Groceries"


def test_a_rule_that_is_not_spending_is_left_as_she_said(client):
    ledger(client)
    t = by(client)[("A", 200, day(120))]
    client.st.set_override(t.merchant, "Saved")
    assert cat(client, 200, 120) == "Saved"


def test_the_one_she_answers_takes_her_answer(client):
    ledger(client)
    t = by(client)[("A", 200, day(120))]
    r = client.patch(f"/api/transactions/{t.fingerprint}",
                     json={"category": "Utilities", "apply_to_merchant": True})
    assert r.status_code == 200
    assert cat(client, 200, 120) == "Utilities" and cat(client, 64, 80) == "Utilities"


def test_the_counts_leave_it_out(client):
    ledger(client)
    t = by(client)[("A", 60, day(10))]
    p = client.post(f"/api/transactions/{t.fingerprint}/category/preview",
                    json={"category": "Utilities", "apply_to_merchant": True}).get_json()
    assert p["merchant_count"] == 2
    always(client)
    [rule] = [r for r in client.get("/api/rules").get_json()["rules"] if r["kind"] == "merchant"]
    n = client.get("/api/rules/earlier", query_string={"id": rule["id"], "category": "Shopping"}).get_json()
    assert n["count"] == 2


def test_undo_puts_everything_back(client):
    ledger(client)
    before = {k: (t.category, t.category_source) for k, t in by(client).items()}
    undo = always(client)["undo"]
    assert client.post("/api/transactions/undo", json=undo).status_code == 200
    assert {k: (t.category, t.category_source) for k, t in by(client).items()} == before
