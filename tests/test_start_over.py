"""Start over (Profile › Your data): the transactions and her organizing go,
the banks stay and bring the history back, and goals and account setup stay."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def tx(day, merchant, amount, category="Dining", account="chq"):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, account_id=account, account_name="TD Chequing ••1111",
                       source="plaid", raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    app = create_app(str(tmp_path / "start.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        st = c.st = app.config["STORE"]
        st.add_plaid_item("item-1", "tok", "TD")
        st.set_plaid_cursor("item-1", "cursor-9")
        st.note_account("chq", name="TD Chequing ••1111", item_id="item-1",
                        account_type="depository", subtype="checking")
        st.note_account("chq-copy", name="TD Chequing ••1111", item_id="item-1",
                        account_type="depository", subtype="checking")
        ingest(st, IngestResult([tx("2026-10-02", "Pai", 45.0), tx("2026-10-03", "Rogers", 85.0),
                                 tx("2026-10-04", "Northwind", -2150.0, "Income")], "chq"))
        pai, rogers = [t.fingerprint for t in st.all_transactions()
                       if t.merchant in ("Pai", "Rogers")]
        # Answers about transactions.
        st.set_transaction_category(pai, "Gifts")
        st.confirm_category(rogers, "Phone & Internet")
        st.set_note(pai, "Birthday dinner")
        st.exclude(rogers, "manual")
        st.skip_review("u:" + pai)
        # Rules, income and bills, budgets.
        st.set_override("Pai", "Dining")
        st.set_destination("acct:3333", "Saved")
        st.set_setting("income_bills", '{"pays": []}')
        st.set_setting("home_income", "4300")
        st.set_setting("carryover", "{}")
        st.set_budget("Dining", 300)
        st.set_setting("category_budgets", '{"Dining": 300}')
        # Kept: goals, account setup.
        chest = st.add_piggy_bank("Travel", 2000, "annual", None, "2026-01")
        st.add_draw(chest, "2026-09", 150.0, "top-up")
        st.allocate(pai, chest, 45.0)
        st.set_account_setting("chq", nickname="Everyday")
        st.set_account_setting("chq-copy", removed=True)
        st.set_joint("chq", "Family")
        st.set_joint_share("chq", 60)
        st.set_setting("anchor_accounts", '["sav"]')
        yield c


def start_over(c, confirm="start over"):
    return c.post("/api/data/start-over", json={"confirm": confirm})


def test_it_clears_the_transactions_and_her_organizing(client):
    r = start_over(client)
    assert r.status_code == 200 and r.get_json()["resync"] is True
    st = client.st
    assert st.all_transactions() == []
    assert st.notes() == {}
    assert not st.skipped_reviews()
    assert st.overrides() == {} and st.destinations() == {} and st.exclusion_rules() == []
    assert st.budgets() == {}
    for key in ("income_bills", "home_income", "carryover", "category_budgets"):
        assert st.setting(key) in (None, ""), key


def test_it_keeps_the_banks_goals_and_account_setup(client):
    start_over(client)
    st = client.st
    item = st.plaid_items()[0]
    assert item["cursor"] in (None, "") and item["last_synced"] is None   # re-downloads all
    assert set(st.account_sync_rules()) == {"chq", "chq-copy"}
    settings = st.account_settings()
    assert settings["chq"]["nickname"] == "Everyday"
    assert settings["chq-copy"]["removed"] is True                       # the hidden copy
    assert st.joint_accounts() == {"chq": "Family"} and st.joint_shares()["chq"] == 60
    assert [b.name for b in st.piggy_banks()] == ["Travel"]
    assert [d["amount"] for d in st.draws()] == [150.0]
    assert st.setting("anchor_accounts") == '["sav"]'
    assert st.seed_suppressed()


@pytest.mark.parametrize("confirm", ["", "yes", "start", None])
def test_it_needs_the_words(client, confirm):
    r = client.post("/api/data/start-over", json={"confirm": confirm} if confirm is not None else {})
    assert r.status_code == 400 and "start over" in r.get_json()["error"]
    assert len(client.st.all_transactions()) == 3


def test_the_next_sync_brings_the_history_back_unsorted_by_her(client, monkeypatch):
    from finance import plaid_link
    start_over(client)

    class Plaid:
        def transactions_sync(self, req):
            return type("R", (), {"to_dict": lambda s: {
                "accounts": [{"account_id": "chq", "name": "TD Chequing", "mask": "1111",
                              "type": "depository", "subtype": "checking"}],
                "added": [{"transaction_id": "p1", "date": "2026-10-02", "name": "PAI",
                           "amount": 45.0, "account_id": "chq", "iso_currency_code": "CAD",
                           "personal_finance_category": {"primary": "FOOD_AND_DRINK"}}],
                "modified": [], "removed": [], "has_more": False, "next_cursor": "c1"}})()

    monkeypatch.setattr(plaid_link, "_client", lambda: Plaid())
    monkeypatch.setattr(plaid_link, "configured", lambda: True)
    assert client.post("/api/plaid/sync", json={"force": True}).status_code == 200
    [row] = client.st.all_transactions()
    assert row.category_source != "user" and not row.excluded
