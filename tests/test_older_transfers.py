"""Also 8 older ones? (REFRESH-17, product owner, 2026-11-25): after she
sorts a bank transfer as spending without a rule, Pearl asks once about the
older ones of that name it had left as transfers for their age. Demo data."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest, recategorize_all

TODAY = date.today()
OUT, IN = "TRANSFER_OUT_ACCOUNT_TRANSFER", "TRANSFER_IN_ACCOUNT_TRANSFER"


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def tx(amount, ago, account="sis", name="MAPLE COURT", **raw):
    return Transaction(date=day(ago), description=name, amount=amount, account_id=account,
                       account_name=f"{account} ••1123", source="plaid",
                       raw={"account_type": "depository",
                            "issuer_category": OUT if amount > 0 else IN, **raw})


def load(st, *rows):
    for acct in {r.account_id for r in rows}:
        ingest(st, IngestResult([r for r in rows if r.account_id == acct], acct))


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "o.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def row(c, amount, ago, account="sis"):
    return next(t for t in c.st.all_transactions()
                if (t.account_id, t.amount, t.date) == (account, amount, day(ago)))


def bill(c):
    """Ten months of it, a different amount each: 8 too old to ask about."""
    load(c.st, *[tx(60 + i, 15 + 30 * i) for i in range(10)])


def sort(c, amount=60, ago=15, remember=False, category="Utilities"):
    t = row(c, amount, ago)
    assert c.post(f"/api/transactions/{t.fingerprint}/mark",
                  json={"case": "spending", "category": category, "remember": remember}).status_code == 200
    return t.fingerprint


def older(c, i):
    r = c.get(f"/api/transactions/{i}/older")
    assert r.status_code == 200
    return r.get_json()


def test_the_older_ones_are_found_newest_first(client):
    bill(client)
    got = older(client, sort(client))
    # 45 days ago is still waiting in Needs a look: its own card, not here.
    assert [r["amount"] for r in got["older"]] == [62 + i for i in range(8)]
    assert got["category"] == "Utilities" and got["share"] is None


def test_nothing_before_she_answers(client):
    bill(client)
    assert older(client, row(client, 60, 15).fingerprint)["older"] == []


def test_yes_sorts_them_as_hers_with_no_rule_and_undo(client):
    bill(client)
    i = sort(client)
    before = {t.fingerprint: (t.category, t.category_source) for t in client.st.all_transactions()}
    ids = [r["id"] for r in older(client, i)["older"]]
    r = client.post(f"/api/transactions/{i}/older", json={"ids": ids}).get_json()
    assert r["moved"] == 8 and r["title"] == "8 more moved to Utilities"
    assert all(row(client, 62 + k, 75 + 30 * k).category == "Utilities" for k in range(8))
    assert row(client, 61, 45).category == "Unsorted transfers"
    assert client.st.overrides() == {} and client.st.destinations() == {}
    assert older(client, i)["older"] == []
    recategorize_all(client.st)
    assert row(client, 62, 75).category == "Utilities"
    assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
    assert {t.fingerprint: (t.category, t.category_source)
            for t in client.st.all_transactions()} == before
    # Undoing the Yes isn't a no.
    assert len(older(client, i)["older"]) == 8


def test_it_becomes_a_bill(client):
    bill(client)
    names = lambda: [b["name"] for b in client.get("/api/income-bills").get_json()["bills"]]  # noqa: E731
    i = sort(client)
    assert "Maple Court" not in names()
    client.post(f"/api/transactions/{i}/older", json={"ids": [r["id"] for r in older(client, i)["older"]]})
    assert "Maple Court" in names()


def test_leave_them_is_for_good_for_that_name_and_account(client):
    bill(client)
    load(client.st, tx(80, 16, "chq"), tx(81, 90, "chq"))
    i = sort(client)
    assert client.post(f"/api/transactions/{i}/older/no").status_code == 200
    assert older(client, i)["older"] == []
    assert older(client, sort(client, 61, 45))["older"] == []
    # The same name out of another account is still asked about.
    t = row(client, 80, 16, "chq")
    client.post(f"/api/transactions/{t.fingerprint}/mark", json={"case": "spending", "category": "Utilities"})
    assert [r["amount"] for r in older(client, t.fingerprint)["older"]] == [81]


def test_real_transfers_are_never_among_them(client):
    load(client.st, tx(60, 15), tx(64, 80), tx(200, 120), tx(-200, 119, "chq", "TRANSFER IN"),
         # A reversal, and two that add up to one arrival elsewhere.
         tx(70, 150), tx(-70, 150), tx(300, 200), tx(150, 200), tx(-450, 200, "chq", "TRANSFER IN"))
    assert [r["amount"] for r in older(client, sort(client))["older"]] == [64]


def test_her_own_answers_and_other_names_are_left(client):
    load(client.st, tx(60, 15), tx(64, 80), tx(65, 110), tx(66, 140, name="BIRCH COURT"))
    client.st.set_transaction_category(row(client, 65, 110).fingerprint, "Transfers")
    assert [r["amount"] for r in older(client, sort(client))["older"]] == [64]


@pytest.mark.parametrize("category", ["Saved", "Transfers"])
def test_only_after_spending(client, category):
    bill(client)
    i = row(client, 60, 15).fingerprint
    client.st.set_transaction_category(i, category)
    assert older(client, i)["older"] == []


def test_not_after_always(client):
    bill(client)
    assert older(client, sort(client, remember=True))["older"] == []


def test_not_for_a_name_every_transfer_shares(client):
    load(client.st, tx(60, 15, name="SEND E-TFR"), tx(64, 80, name="SEND E-TFR"))
    assert older(client, sort(client))["older"] == []


def test_one_answered_meanwhile_is_skipped(client):
    load(client.st, tx(60, 15), tx(64, 80), tx(65, 110))
    i = sort(client)
    ids = [r["id"] for r in older(client, i)["older"]]
    client.st.set_transaction_category(row(client, 64, 80).fingerprint, "Dining")
    r = client.post(f"/api/transactions/{i}/older", json={"ids": ids}).get_json()
    assert r["moved"] == 1 and r["title"] == "1 more moved to Utilities"
    assert row(client, 64, 80).category == "Dining"
    assert client.post(f"/api/transactions/{i}/older", json={"ids": ids}).status_code == 409


def test_a_row_that_was_not_listed_never_moves(client):
    bill(client)
    i = sort(client)
    stranger = row(client, 61, 45).fingerprint
    assert client.post(f"/api/transactions/{i}/older", json={"ids": [stranger]}).status_code == 409
    assert row(client, 61, 45).category == "Unsorted transfers"


def test_her_half_on_a_joint_account(client):
    load(client.st, tx(60, 15), tx(64, 80))
    assert client.put("/api/accounts/sis/joint", json={"label": "Sister", "people": ["Sam"]}).status_code == 200
    assert client.put("/api/accounts/sis/settings", json={"joint_share": 50}).status_code == 200
    got = older(client, sort(client))
    assert got["share"] == 50
    assert [(r["amount"], r["mine"]) for r in got["older"]] == [(64, 32)]


def test_why_there_is_no_rule(client):
    load(client.st, tx(60, 15, name="INTERAC E-TRANSFER"), tx(61, 15, name="MAPLE COURT"),
         tx(62, 15, name="INTERAC E-TRANSFER TO ALEX"), tx(63, 15, name="ONLINE BANKING PAYMENT"))
    why = {t.amount: client.get(f"/api/transactions/{t.fingerprint}/cases").get_json()["why"]
           for t in client.st.all_transactions()}
    assert why == {60: "common", 61: None, 62: None, 63: "common"}
    rows = client.get("/api/transactions/list?limit=50").get_json()["transactions"]
    assert {r["full_amount"] if r.get("full_amount") else r["amount"]: r["rule"]["why"] for r in rows} == why
