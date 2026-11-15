"""A bill payment out of a joint account split 50/50 (2026-11-15).

The product owner's joint account is set to 50% (AM-04). A bill payment out
of it, which Plaid codes LOAN_PAYMENTS or TRANSFER_OUT, isn't matched to any
of her accounts, so it waits as an Unsorted transfer ("Saved or spent? Tell
us") and counts as spent until she answers. The totals counted half of it,
but the row said the whole payment was hers, and so Whose was it? opened on
"Mine" instead of her 50%. Demo data only."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(amount, description, code=""):
    return Transaction(date=day(1), description=description, amount=amount,
                       account_id="sis", account_name="Joint chequing ••1234", source="plaid",
                       raw={"account_type": "depository", "issuer_category": code})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "joint-bill.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        set_plan(c, income=5200, savings=900)
        st = c.application.config["STORE"]
        ingest(st, IngestResult([row(140, "BILL PAYMENT XYZ CORP", "LOAN_PAYMENTS_OTHER_PAYMENT"),
                                 row(60, "BILL PAYMENT QRS LTD", "TRANSFER_OUT_ACCOUNT_TRANSFER"),
                                 row(120, "LOBLAWS", "FOOD_AND_DRINK_GROCERIES")], "sis"))
        assert c.put("/api/accounts/sis/joint", json={"label": "Sister", "people": ["Sam"]}).status_code == 200
        assert c.put("/api/accounts/sis/settings", json={"joint_share": 50}).status_code == 200
        yield c


def rows(c):
    out = c.get("/api/transactions/list?limit=100").get_json()["transactions"]
    return {r["description"]: r for r in out}


@pytest.mark.parametrize("name,full", [("BILL PAYMENT XYZ CORP", 140.0), ("BILL PAYMENT QRS LTD", 60.0)])
def test_bill_payment_shows_her_half(client, name, full):
    r = rows(client)[name]
    # Waiting to be sorted, and counted as spent meanwhile.
    assert r["category"] == "Unsorted transfers" and r["counts"] == "spending"
    assert r["joint_share"] == 50 and not r["share_set"]
    assert r["full_amount"] == full
    assert r["joint_part"] == full / 2
    # The bug: this was the whole payment.
    assert r["amount"] == full / 2
    detail = client.get(f"/api/transactions/{r['id']}").get_json()
    assert detail["amount"] == full / 2 and detail["full_amount"] == full


def test_row_and_totals_agree(client):
    r = rows(client)
    shown = sum(x["amount"] for x in r.values() if x["counts"] == "spending")
    m = next(m for m in client.get("/api/summary").get_json()["monthly"] if m["month"] == MONTH)
    # Half of 140 + 60 + 120.
    assert shown == 160 == m["spend"]


def test_part_of_it_saves_on_a_bill_payment(client):
    """Whose was it? → Part of it, on the bill payment: her part saves, and
    the row shows it; Mine puts it back to the account's 50%."""
    i = rows(client)["BILL PAYMENT XYZ CORP"]["id"]
    assert client.put(f"/api/transactions/{i}/share", json={"my_share": 100, "always": False}).status_code == 200
    r = rows(client)["BILL PAYMENT XYZ CORP"]
    assert r["share_set"] and r["amount"] == 100
    assert client.put(f"/api/transactions/{i}/share", json={"my_share": None}).status_code == 200
    assert rows(client)["BILL PAYMENT XYZ CORP"]["amount"] == 70
