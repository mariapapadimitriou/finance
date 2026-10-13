"""Connecting a bank again replaces the accounts it brings back instead of
doubling every purchase, keeping what she said about them and their rows."""

import pytest

from finance import plaid_link, secrets_box
from finance.store import Store

KEY = "unit-test-key-that-is-definitely-long-enough"


def accounts(prefix):
    return [{"account_id": f"{prefix}-card", "name": "TD Visa", "mask": "4321",
             "type": "credit", "subtype": "credit card"},
            {"account_id": f"{prefix}-chq", "name": "TD Chequing", "mask": "1111",
             "type": "depository", "subtype": "checking"}]


def txn(tid, account, name="LOBLAWS", amount=50.0):
    return {"transaction_id": tid, "date": "2026-10-02", "name": name, "amount": amount,
            "account_id": account, "iso_currency_code": "CAD",
            "personal_finance_category": {"primary": "FOOD_AND_DRINK"}}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class FakePlaid:
    def __init__(self):
        self.feeds = {}          # access token -> page
        self.removed = []

    def transactions_sync(self, request):
        token = request.to_dict()["access_token"]
        return _Resp({"has_more": False, "next_cursor": "c", "modified": [],
                      "removed": [], **self.feeds[token]})

    def item_remove(self, request):
        self.removed.append(request.to_dict()["access_token"])
        return _Resp({"removed": True})


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    client = FakePlaid()
    monkeypatch.setattr(plaid_link, "_client", lambda: client)
    monkeypatch.setattr(plaid_link, "configured", lambda: True)
    return Store(str(tmp_path / "r.db")), client


def test_reconnecting_replaces_the_old_connection(setup):
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"), "added": [txn("t1", "a-card")]}
    plaid_link.sync_all(st)
    st.set_account_sync("a-chq", True)            # you switched chequing on
    st.set_joint("a-chq", "Family")

    # Connected again: a new item, new account ids, the same accounts.
    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": accounts("b"),
                            "added": [txn("u1", "b-card"), txn("u2", "b-chq", "RENT", 900)]}
    plaid_link.sync_all(st)

    rows = st.all_transactions()
    assert sorted((t.account_id, t.description) for t in rows) == \
        [("b-card", "LOBLAWS"), ("b-chq", "RENT")]
    assert [i["item_id"] for i in st.plaid_items()] == ["item-2"]
    assert plaid.removed == ["tok-1"]                        # revoked at Plaid
    rules = st.account_sync_rules()
    assert rules["b-chq"]["enabled"] and rules["b-chq"]["decided_by"] == "user"
    assert st.joint_accounts() == {"b-chq": "Family"}


def test_a_different_login_at_the_same_bank_stays(setup):
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"), "added": [txn("t1", "a-card")]}
    plaid_link.sync_all(st)
    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": [{"account_id": "fam", "name": "Family Chequing",
                                          "mask": "7777", "type": "depository",
                                          "subtype": "checking"}],
                            "added": []}
    plaid_link.sync_all(st)
    assert {i["item_id"] for i in st.plaid_items()} == {"item-1", "item-2"}
    assert plaid.removed == []


def test_a_reconnect_that_shares_fewer_accounts_still_replaces_them(setup):
    """The reported bug: the second time she shared only the card, so the
    old connection wasn't replaced and the card showed up twice."""
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"),
                            "added": [txn("t1", "a-card"), txn("t2", "a-chq", "RENT", 900)]}
    plaid_link.sync_all(st)
    st.set_account_sync("a-chq", True)

    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": accounts("b")[:1], "added": [txn("u1", "b-card")]}
    plaid_link.sync_all(st)

    rows = sorted((t.account_id, t.description) for t in st.all_transactions())
    assert rows == [("a-chq", "RENT"), ("b-card", "LOBLAWS")]       # one card, not two
    assert {i["item_id"] for i in st.plaid_items()} == {"item-1", "item-2"}
    assert plaid.removed == []                    # the old login still has the chequing
    rules = st.account_sync_rules()
    assert rules["a-card"]["enabled"] is False   # the old login skips the card now

    # Its next sync brings the card again; it isn't counted twice.
    plaid.feeds["tok-1"]["added"] = [txn("t3", "a-card", "COSTCO", 80)]
    plaid_link.sync_all(st)
    assert all(t.account_id != "a-card" for t in st.all_transactions())


def test_what_she_said_about_the_rows_comes_back_with_them(setup):
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"), "added": [txn("t1", "a-card")]}
    plaid_link.sync_all(st)
    [old] = st.all_transactions()
    st.set_transaction_category(old.fingerprint, "Dining")
    st.set_share(old.fingerprint, 20.0)
    st.set_note(old.fingerprint, "Team lunch")

    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": accounts("b"), "added": [txn("u1", "b-card")]}
    plaid_link.sync_all(st)

    [new] = st.all_transactions()
    assert new.account_id == "b-card" and new.fingerprint != old.fingerprint
    assert new.category == "Dining" and new.category_source == "user"
    assert new.my_share == 20.0
    assert st.notes() == {new.fingerprint: "Team lunch"}
