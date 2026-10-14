"""A nickname she gives an account (Profile › Accounts) names it everywhere,
and never replaces the bank's own name underneath."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    import finance.api as api
    monkeypatch.setattr(api, "_today_iso", lambda: "2026-10-12")
    app = create_app(str(tmp_path / "nick.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.add_plaid_item("item-1", "tok", "TD")
        c.st.note_account("chq", name="TD Everyday Chequing ••1111", item_id="item-1",
                          account_type="depository", subtype="checking")
        rows = [Transaction(date="2026-10-0%d" % d, description="COFFEE", merchant="Coffee",
                            amount=4.5, category="Coffee", account_id="chq",
                            account_name="TD Everyday Chequing ••1111", source="plaid",
                            raw={"account_type": "depository"}) for d in (2, 3)]
        ingest(c.st, IngestResult(rows, "chq"))
        c.put("/api/accounts/chq/settings", json={"nickname": "Bills account"})
        yield c


def test_the_transactions_list_and_its_filter_use_the_nickname(client):
    listed = client.get("/api/transactions/list", query_string={"month": "2026-10"}).get_json()
    assert {t["account"] for t in listed["transactions"]} == {"Bills account"}
    accounts = client.get("/api/accounts").get_json()
    rows = accounts if isinstance(accounts, list) else accounts.get("accounts", [])
    assert next(a for a in rows if a["account_id"] == "chq")["nickname"] == "Bills account"


def test_the_bank_name_underneath_is_kept(client):
    t = client.st.all_transactions()[0]
    assert t.account_name == "TD Everyday Chequing ••1111"
    assert t.account_label == "Bills account"
    rule = client.st.account_sync_rules()["chq"]
    assert rule["account_name"] == "TD Everyday Chequing ••1111" and rule["label"] == "Bills account"


def test_clearing_it_goes_back_to_the_bank_name(client):
    client.put("/api/accounts/chq/settings", json={"nickname": ""})
    assert client.st.all_transactions()[0].account_label == "TD Everyday Chequing ••1111"


def test_rules_name_the_account_by_its_nickname(client):
    client.st.add_exclusion_rule({"account_id": "chq", "reason": "Not mine"})
    rules = client.get("/api/rules").get_json()["rules"]
    assert any(r["kind"] == "exclusion" and r["name"] == "Bills account" for r in rules)


def test_needs_a_look_names_the_account_by_its_nickname(client):
    from finance import review
    t = client.st.all_transactions()[0]
    assert review._brief(t)["account_name"] == "Bills account"
