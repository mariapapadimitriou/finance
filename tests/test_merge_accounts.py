"""Merging two copies of one card by hand ("Same account as…"): rows in both
count once, her answers carry over, nothing is lost, and the copy goes."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n=1):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(amount, description, account, name, n=1, source="plaid"):
    return Transaction(date=day(n), description=description, amount=amount,
                       account_id=account, account_name=name,
                       raw={"account_type": "credit"}, source=source)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, Fernet.generate_key().decode())
    app = create_app(str(tmp_path / "merge.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=0)
        st = c.application.config["STORE"]
        st.add_plaid_item("item-new", "token", "Scotiabank")
        st.note_account("new", name="Scotia Gold Amex ••4876", item_id="item-new",
                        account_type="credit", subtype="credit card")
        # The bank feed's copy.
        ingest(st, IngestResult([row(80, "LOBLAWS #1032", "new", "Scotia Gold Amex ••4876", n=2),
                                 row(45, "PAI", "new", "Scotia Gold Amex ••4876", n=1)], "new"))
        # The same card from a statement she imported before linking: the same
        # Loblaws written differently and a day apart, the same Pai, and one
        # purchase the feed doesn't have.
        ingest(st, IngestResult([row(80, "LOBLAWS 1032 TORONTO", "old", "Gold Amex", n=3, source="csv"),
                                 row(45, "PAI", "old", "Gold Amex", n=1, source="csv"),
                                 row(30, "PRESTO", "old", "Gold Amex", n=4, source="csv")], "old"))
        c.st = st
        yield c


def spend(c):
    return next(m for m in c.get("/api/summary").get_json()["monthly"]
                if m["month"] == MONTH)["spend"]


def accounts(c):
    data = c.get("/api/accounts/overview").get_json()
    return {a["id"]: a for a in data["linked"] + data["added"]}


def ids(c, account):
    return {t.description: t.fingerprint for t in c.st.all_transactions() if t.account_id == account}


def test_doubled_until_merged_then_counted_once(client):
    assert spend(client) > 80 + 45 + 30              # the copy counts some twice
    old = ids(client, "old")
    client.st.set_note(old["LOBLAWS 1032 TORONTO"], "Cottage groceries")
    client.st.set_transaction_category(old["PRESTO"], "Transport")
    r = client.post("/api/accounts/old/merge", json={"into": "new"})
    assert r.status_code == 200, r.get_json()
    assert r.get_json()["matched"] == 2 and r.get_json()["moved"] == 1
    assert spend(client) == 80 + 45 + 30
    assert "old" not in accounts(client)
    new = ids(client, "new")
    assert set(new) == {"LOBLAWS #1032", "PAI", "PRESTO"}
    assert client.st.notes() == {new["LOBLAWS #1032"]: "Cottage groceries"}
    presto = next(t for t in client.st.all_transactions() if t.fingerprint == new["PRESTO"])
    assert presto.category == "Transport" and presto.category_source == "user"


def test_her_settings_follow_where_the_kept_one_has_none(client):
    client.put("/api/accounts/old/settings", json={"nickname": "Everyday Amex"})
    client.post("/api/accounts/old/merge", json={"into": "new"})
    assert accounts(client)["new"]["name"] == "Everyday Amex"


def test_refused_for_the_wrong_kind_or_a_hand_account(client):
    r = client.post("/api/accounts/manual", json={"name": "Cash", "kind": "chequing", "balance": 50})
    hand = r.get_json()["account"]["id"]
    assert client.post("/api/accounts/old/merge", json={"into": hand}).status_code == 400
    assert client.post("/api/accounts/old/merge", json={"into": "old"}).status_code == 404
    assert client.post("/api/accounts/old/merge", json={"into": "nope"}).status_code == 404
