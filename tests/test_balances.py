"""What your accounts hold, from every sync, wound back through the
transactions to any earlier day."""

from __future__ import annotations

from datetime import date

import pytest

from finance import balances as bal
from finance import plaid_link, secrets_box
from finance.models import Transaction

KEY = "unit-test-key-that-is-definitely-long-enough"
TODAY = date.today()


def t(when, amount, account):
    return Transaction(date=when, description="x", amount=amount, account_id=account)


class TestWindingBack:
    def test_a_bank_account(self):
        rows = [t("2026-09-20", 100, "chq"), t("2026-09-25", -2000, "chq")]
        # Today it holds 5,000: before the pay came in and the 100 went out it held 3,100.
        assert bal.balance_on(5000, "depository", "2026-09-19", "2026-10-01", rows) == 3100

    def test_a_card(self):
        rows = [t("2026-09-20", 300, "card"), t("2026-09-25", -500, "card")]
        # Owes 800 today; before 300 of charges and a 500 payment it owed 1,000.
        assert bal.balance_on(800, "credit", "2026-09-19", "2026-10-01", rows) == 1000


@pytest.fixture()
def synced(tmp_path, monkeypatch):
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)

    class Resp:
        def __init__(self, p):
            self.p = p

        def to_dict(self):
            return self.p

    class Fake:
        def transactions_sync(self, request):
            return Resp({"has_more": False, "next_cursor": "c", "modified": [], "removed": [],
                         "added": [], "accounts": [
                             {"account_id": "chq", "name": "Chequing", "mask": "1111",
                              "type": "depository", "subtype": "checking",
                              "balances": {"current": 4000, "available": 3900,
                                           "iso_currency_code": "CAD"}},
                             {"account_id": "card", "name": "Visa", "mask": "2222",
                              "type": "credit", "subtype": "credit card",
                              "balances": {"current": 800, "limit": 5000,
                                           "iso_currency_code": "CAD"}},
                             {"account_id": "sav", "name": "Savings", "mask": "3333",
                              "type": "depository", "subtype": "savings",
                              "balances": {"current": 10000}}]})

    monkeypatch.setattr(plaid_link, "_client", lambda: Fake())
    monkeypatch.setattr(plaid_link, "configured", lambda: True)
    from app import create_app
    app = create_app(str(tmp_path / "b.db"))
    app.config.update(TESTING=True)
    st = app.config["STORE"]
    st.add_plaid_item("item-1", "tok", "TD")
    plaid_link.sync_all(st)
    with app.test_client() as c:
        yield st, c


def test_every_sync_records_balances_even_for_switched_off_accounts(synced):
    st, c = synced
    b = st.balances()
    assert b["chq"]["current"] == 4000 and b["chq"]["available"] == 3900
    assert b["card"]["limit"] == 5000
    st.set_account_sync("sav", False)
    plaid_link.sync_all(st)
    assert st.balances()["sav"]["current"] == 10000   # switched off, still known
    rows = {a["account_id"]: a for a in c.get("/api/accounts").get_json()["accounts"]}
    assert rows["card"]["balance"]["current"] == 800


def test_removing_the_bank_forgets_its_balances(synced):
    st, c = synced
    plaid_link.unlink(st, "item-1")
    assert st.balances() == {}
