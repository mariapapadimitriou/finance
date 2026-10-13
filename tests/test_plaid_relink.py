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


def test_accounts_doubled_before_the_fix_are_merged_on_the_next_sync(setup, monkeypatch):
    """Her ledger today: a reconnect from before replacement worked account
    by account left the card under both connections, counted twice."""
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"),
                            "added": [txn("t1", "a-card"), txn("t2", "a-chq", "RENT", 900)]}
    plaid_link.sync_all(st)
    [old_card] = [t for t in st.all_transactions() if t.account_id == "a-card"]
    st.set_note(old_card.fingerprint, "Groceries for the cottage")
    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": accounts("b")[:1], "added": [txn("u1", "b-card")]}
    real = plaid_link._replace_superseded
    monkeypatch.setattr(plaid_link, "_replace_superseded", lambda *a: {})   # the old behaviour
    plaid_link.sync_all(st)
    assert sorted(t.account_id for t in st.all_transactions()) == ["a-card", "a-chq", "b-card"]
    assert plaid_link.doubled_items(st) == ["item-2"]

    monkeypatch.setattr(plaid_link, "_replace_superseded", real)
    plaid.feeds["tok-1"]["added"] = []
    plaid_link.sync_all(st)

    rows = sorted((t.account_id, t.description) for t in st.all_transactions())
    assert rows == [("a-chq", "RENT"), ("b-card", "LOBLAWS")]        # counted once
    [card] = [t for t in st.all_transactions() if t.account_id == "b-card"]
    assert st.notes() == {card.fingerprint: "Groceries for the cottage"}
    assert plaid_link.doubled_items(st) == []
    plaid_link.sync_all(st)                                          # and it stays that way
    assert len(st.all_transactions()) == 2


def test_two_different_cards_are_not_doubled(setup):
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"), "added": []}
    st.add_plaid_item("item-2", "tok-2", "RBC")
    plaid.feeds["tok-2"] = {"accounts": [{"account_id": "rbc", "name": "RBC Visa", "mask": "9999",
                                          "type": "credit", "subtype": "credit card"}], "added": []}
    plaid_link.sync_all(st)
    assert plaid_link.doubled_items(st) == []


def test_a_merge_never_leaves_a_row_asked_about_against_itself(setup):
    """Seen in production: 224 rows each a "possible duplicate" of
    themselves after a reconnect merged two copies of a card, so the real
    rows were hidden as copies."""
    st, plaid = setup
    st.add_plaid_item("item-1", "tok-1", "TD")
    plaid.feeds["tok-1"] = {"accounts": accounts("a"), "added": [txn("t1", "a-card")]}
    plaid_link.sync_all(st)
    st.add_plaid_item("item-2", "tok-2", "TD")
    plaid.feeds["tok-2"] = {"accounts": accounts("b")[:1], "added": [txn("u1", "b-card")]}
    real = plaid_link._replace_superseded
    plaid_link._replace_superseded = lambda *a: {}            # the old behaviour: both copies
    try:
        plaid_link.sync_all(st)
    finally:
        plaid_link._replace_superseded = real
    old = next(t for t in st.all_transactions() if t.account_id == "a-card")
    new = next(t for t in st.all_transactions() if t.account_id == "b-card")
    st.add_duplicate(old.fingerprint, new.fingerprint)     # "Is this the same purchase?"

    plaid_link.sync_all(st)

    [row] = st.all_transactions()
    assert row.account_id == "b-card" and not row.excluded   # counted, not hidden
    assert st.duplicates() == {}


def test_rows_already_asked_about_against_themselves_are_cleared_on_open(setup):
    st, _ = setup
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    ingest(st, IngestResult([Transaction(date="2026-10-02", description="CHIPOTLE", amount=14.35,
                                         account_id="card", account_name="card")], "card"))
    [row] = st.all_transactions()
    st.add_duplicate(row.fingerprint, row.fingerprint)
    assert st.all_transactions()[0].excluded                 # hidden as a copy of itself
    again = Store(st.path)
    assert again.duplicates() == {} and not again.all_transactions()[0].excluded
