"""A pending charge never stays beside its posted twin, even when the feed is
started over (which never reports the pending row as removed)."""

import pytest

from finance import plaid_link, secrets_box
from finance.store import Store

KEY = "unit-test-key-that-is-definitely-long-enough"
CARD = [{"account_id": "acc1", "name": "TD Visa", "mask": "4321",
         "type": "credit", "subtype": "credit card"}]


def txn(tid, date, name, amount, pending=False, pending_id=None):
    return {"transaction_id": tid, "date": date, "name": name, "amount": amount,
            "account_id": "acc1", "iso_currency_code": "CAD", "pending": pending,
            "pending_transaction_id": pending_id,
            "personal_finance_category": {"primary": "FOOD_AND_DRINK"}}


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


class FakePlaid:
    def __init__(self):
        self.pages = []
        self.cursors = []

    def transactions_sync(self, request):
        self.cursors.append(request.to_dict().get("cursor"))
        page = self.pages.pop(0)
        return _Resp({"accounts": CARD, "added": [], "modified": [], "removed": [],
                      "has_more": False, "next_cursor": "c", **page})


@pytest.fixture()
def setup(tmp_path, monkeypatch):
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    client = FakePlaid()
    monkeypatch.setattr(plaid_link, "_client", lambda: client)
    monkeypatch.setattr(plaid_link, "configured", lambda: True)
    st = Store(str(tmp_path / "d.db"))
    st.add_plaid_item("item-1", "tok", "TD")
    return st, client


def rows(st):
    return sorted((t.date, t.description, t.amount) for t in st.all_transactions())


def test_a_posted_row_replaces_the_pending_one_it_names(setup):
    st, plaid = setup
    plaid.pages = [{"added": [txn("p1", "2026-10-02", "UBER EATS", 40, pending=True)]},
                   {"added": [txn("q1", "2026-10-02", "UBER EATS TORONTO", 40,
                                  pending_id="p1")]}]
    plaid_link.sync_all(st)
    plaid_link.sync_all(st)
    assert rows(st) == [("2026-10-02", "UBER EATS TORONTO", 40)]


def test_a_restarted_feed_clears_what_the_bank_no_longer_has(setup):
    st, plaid = setup
    plaid.pages = [{"added": [txn("p1", "2026-10-02", "SEND E-TFR", 500, pending=True),
                              txn("old", "2026-08-01", "COFFEE", 5)]}]
    plaid_link.sync_all(st)
    # Started over (an account switched on): only the posted row comes back,
    # and nothing says the pending one went away.
    st.rewind_plaid_cursor("item-1")
    plaid.pages = [{"added": [txn("q1", "2026-10-02", "SEND E-TFR ***Q7K", 500),
                              txn("old", "2026-08-01", "COFFEE", 5)]}]
    plaid_link.sync_all(st)
    assert rows(st) == [("2026-08-01", "COFFEE", 5), ("2026-10-02", "SEND E-TFR ***Q7K", 500)]


def test_two_real_coffees_the_same_day_both_stay(setup):
    st, plaid = setup
    two = [txn("a", "2026-10-02", "TIM HORTONS", 3), txn("b", "2026-10-02", "TIM HORTONS", 3)]
    plaid.pages = [{"added": two}]
    plaid_link.sync_all(st)
    st.rewind_plaid_cursor("item-1")
    plaid.pages = [{"added": two}]
    plaid_link.sync_all(st)
    assert len(st.all_transactions()) == 2


def test_rows_older_than_what_the_bank_sends_are_kept(setup):
    st, plaid = setup
    plaid.pages = [{"added": [txn("x", "2025-01-05", "OLD SHOP", 9),
                              txn("y", "2026-10-01", "NEW SHOP", 9)]}]
    plaid_link.sync_all(st)
    st.rewind_plaid_cursor("item-1")
    plaid.pages = [{"added": [txn("y", "2026-10-01", "NEW SHOP", 9)]}]
    plaid_link.sync_all(st)
    assert ("2025-01-05", "OLD SHOP", 9) in rows(st)


def test_the_existing_ledger_is_cleaned_once(setup):
    st, plaid = setup
    plaid.pages = [{"added": [txn("p1", "2026-10-02", "SEND E-TFR", 500, pending=True)]}]
    st.set_setting("plaid_reconciled", "1")
    plaid_link.sync_all(st)
    # An older ledger, from before the reconcile existed.
    with st.conn() as c:
        c.execute("DELETE FROM settings WHERE key = 'plaid_reconciled'")
    plaid.pages = [{"added": [txn("q1", "2026-10-02", "SEND E-TFR ***Q7K", 500)]},
                   {"added": []}]
    plaid_link.sync_all(st)
    assert plaid.cursors[-1] is None            # started over once
    assert rows(st) == [("2026-10-02", "SEND E-TFR ***Q7K", 500)]
    plaid_link.sync_all(st)
    assert plaid.cursors[-1] == "c"             # and only once
