"""Emptying the ledger, and having it stay empty.

The trap this exists to close: the seeder loads a committed ledger into an
empty database on cold start, and after a reset the database is very much
empty. Without a marker, a reset would appear to work and then quietly undo
itself the next time a serverless instance started cold.
"""

import json

import pytest

from app import create_app, seed_ledger_if_empty
from finance.models import Transaction
from finance.store import Store


def txn(date="2025-11-14", desc="MOS MOS COFFEE", amount=8.08, account="a"):
    return Transaction(date=date, description=desc, amount=amount,
                       account_id=account, account_name=account, source="pdf")


@pytest.fixture()
def store(tmp_path):
    st = Store(str(tmp_path / "t.db"))
    st.add_transactions([txn(), txn("2025-11-15", "IQ FOOD CO", 23.73)])
    st.set_override("mos mos coffee", "Coffee")
    st.set_budget("Dining", 200.0)
    st.add_trip("Lisbon", "2025-11-01", "2025-11-07")
    bank = st.add_piggy_bank("Fun", 400.0, "annual", None, "2025-11", 400.0)
    st.allocate(st.all_transactions()[0].fingerprint, bank, 40.0)
    st.dismiss("finding-1")
    st.set_setting("monthly_income", 4200.0)
    return st


class TestReset:
    def test_it_empties_the_ledger(self, store):
        store.reset()
        assert store.all_transactions() == []

    def test_it_takes_everything_derived_from_it(self, store):
        """A budget or an override for a merchant you no longer have any
        transactions from is clutter, not history."""
        store.reset()
        assert store.overrides() == {}
        assert store.budgets() == {}
        assert store.trips() == []
        assert store.dismissed() == set()
        # The piggy banks themselves are a standing decision and survive, but
        # what was charged to them cannot: those transactions are gone.
        assert store.allocations() == {}

    def test_it_reports_what_it_removed(self, store):
        removed = store.reset()
        assert removed["transactions"] == 2
        assert removed["trips"] == 1

    def test_the_spending_plan_goes_too(self, store):
        """Yours rather than imported, but a plan sized to a ledger that no
        longer exists is a number with nothing behind it."""
        store.reset()
        assert store.float_setting("monthly_income", 0.0) == 0.0


class TestSeedingAfterReset:
    def test_an_empty_ledger_is_normally_seeded(self, tmp_path, monkeypatch):
        st = Store(str(tmp_path / "t.db"))
        assert st.seed_suppressed() is False

    def test_a_reset_ledger_is_not_re_seeded(self, store, tmp_path,
                                             monkeypatch):
        """The whole point: without this the committed file reloads on the
        next cold start and the reset silently undoes itself."""
        store.reset()
        assert store.seed_suppressed() is True

        seed = tmp_path / "transactions.json"
        seed.write_text(json.dumps({"transactions": [
            {"date": "2025-01-01", "description": "SEEDED", "amount": 5.0,
             "merchant": "Seeded", "account_id": "seed"}]}))
        monkeypatch.setattr("seed_data.export.SEED_FILE", str(seed))

        assert seed_ledger_if_empty(store) == 0
        assert store.all_transactions() == []

    def test_without_the_marker_the_seed_would_load(self, tmp_path, monkeypatch):
        """Proves the previous test is testing the marker and not the file
        simply being unreadable."""
        st = Store(str(tmp_path / "fresh.db"))
        seed = tmp_path / "transactions.json"
        seed.write_text(json.dumps({"transactions": [
            {"date": "2025-01-01", "description": "SEEDED", "amount": 5.0,
             "merchant": "Seeded", "account_id": "seed"}]}))
        monkeypatch.setattr("seed_data.export.SEED_FILE", str(seed))
        assert seed_ledger_if_empty(st) == 1


class TestBankConnections:
    @pytest.fixture(autouse=True)
    def _key(self, monkeypatch):
        monkeypatch.setenv("SPENDIE_SECRET_KEY",
                           "unit-test-key-that-is-definitely-long-enough")

    def test_connections_are_kept_by_default(self, store):
        store.add_plaid_item("item-1", "tok", "TD")
        store.reset()
        assert len(store.plaid_items()) == 1

    def test_their_cursors_are_rewound(self, store):
        """A cursor left pointing past an emptied ledger means the next sync
        reports nothing new and the cards stay empty for good."""
        store.add_plaid_item("item-1", "tok", "TD")
        store.set_plaid_cursor("item-1", "cursor-abc")
        store.reset()
        item = store.plaid_items()[0]
        assert not item["cursor"]
        assert item["synced_before"] is False

    def test_they_can_be_removed_as_well(self, store):
        store.add_plaid_item("item-1", "tok", "TD")
        removed = store.reset(keep_banks=False)
        assert store.plaid_items() == []
        assert removed["bank connections"] == 1


class TestResetApi:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def test_it_refuses_without_the_word(self, client):
        """Irreversible, so a stray request cannot do it."""
        r = client.post("/api/reset", json={})
        assert r.status_code == 400
        assert r.get_json()["needs_confirmation"] is True

    def test_a_wrong_word_is_refused(self, client):
        assert client.post("/api/reset", json={"confirm": "yes"}).status_code == 400

    def test_the_word_does_it(self, client):
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/05/2025,BLUE BOTTLE COFFEE,M P,-31004,6.40\n")
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
        assert client.get("/api/transactions").get_json()["total"] == 1

        r = client.post("/api/reset", json={"confirm": "erase"})
        assert r.status_code == 200
        assert r.get_json()["transactions_removed"] == 1
        assert client.get("/api/transactions").get_json()["total"] == 0

    def test_the_word_is_not_case_sensitive(self, client):
        assert client.post("/api/reset", json={"confirm": "ERASE"}).status_code == 200
