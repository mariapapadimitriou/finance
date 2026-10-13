"""End-to-end API tests against a temporary ledger."""

import pytest

from app import create_app
from ledger_files import load_bundled, upload

AMEX = """Date,Description,Card Member,Account #,Amount
07/14/2026,SQ *BLUE BOTTLE COFFEE OAKLAND CA,M P,-31004,6.40
07/15/2026,NETFLIX.COM 866-579-7172 CA,M P,-31004,22.99
07/16/2026,WHOLE FOODS MKT 10229,M P,-31004,84.20
08/14/2026,SQ *BLUE BOTTLE COFFEE OAKLAND CA,M P,-31004,6.40
08/15/2026,NETFLIX.COM 866-579-7172 CA,M P,-31004,22.99
"""

CHASE = """Transaction Date,Post Date,Description,Category,Type,Amount,Memo
07/14/2026,07/16/2026,DOORDASH*THAI HOUSE,Food & Drink,Sale,-42.10,
07/20/2026,07/20/2026,Payment Thank You - Web,,Payment,500.00,
"""

# A year of monthly interest charges — enough history for the rule engine to
# have something real to say.
YEAR_OF_FEES = "Date,Description,Card Member,Account #,Amount\n" + "".join(
    f"{m:02d}/26/2026,INTEREST CHARGE ON PURCHASES,M P,-31004,31.40\n"
    for m in range(1, 13)
)


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "test.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


class TestImport:
    """CSV statements through the pipeline: no longer uploaded from the app
    (C1), but the demo ledger is built this way."""

    def test_import_reports_format_and_count(self, client):
        body = upload(client, AMEX, "amex.csv")
        assert body["imported"] == 5
        assert body["results"][0]["format_label"] == "American Express"

    def test_importing_twice_imports_nothing_the_second_time(self, client):
        upload(client, AMEX, "amex.csv")
        second = upload(client, AMEX, "amex.csv")
        assert second["imported"] == 0
        assert second["duplicates"] == 5

    def test_multiple_cards_aggregate_into_one_ledger(self, client):
        upload(client, AMEX, "amex.csv")
        upload(client, CHASE, "chase.csv")

        accounts = client.get("/api/accounts").get_json()["accounts"]
        assert len(accounts) == 2

        total = client.get("/api/transactions?limit=500").get_json()["total"]
        assert total == 7


class TestTransactions:
    def test_filter_by_category(self, client):
        upload(client, AMEX, "amex.csv")
        r = client.get("/api/transactions?category=Coffee").get_json()
        assert r["total"] == 2
        assert all(t["category"] == "Coffee" for t in r["transactions"])

    def test_filter_by_month(self, client):
        upload(client, AMEX, "amex.csv")
        assert client.get("/api/transactions?month=2026-08").get_json()["total"] == 2

    def test_search(self, client):
        upload(client, AMEX, "amex.csv")
        assert client.get("/api/transactions?q=Netflix").get_json()["total"] == 2

    def test_recategorize_one_transaction(self, client):
        upload(client, AMEX, "amex.csv")
        txns = client.get("/api/transactions?q=Netflix").get_json()["transactions"]

        r = client.patch(f"/api/transactions/{txns[0]['id']}",
                         json={"category": "Entertainment"})
        assert r.status_code == 200

        updated = client.get("/api/transactions?q=Netflix").get_json()["transactions"]
        changed = [t for t in updated if t["id"] == txns[0]["id"]][0]
        assert changed["category"] == "Entertainment"
        assert changed["category_source"] == "user"

    def test_applying_to_a_merchant_updates_every_row(self, client):
        upload(client, AMEX, "amex.csv")
        txns = client.get("/api/transactions?q=Netflix").get_json()["transactions"]

        r = client.patch(f"/api/transactions/{txns[0]['id']}",
                         json={"category": "Entertainment", "apply_to_merchant": True})
        assert r.get_json()["updated"] == 2

        after = client.get("/api/transactions?category=Entertainment").get_json()
        assert after["total"] == 2

    def test_merchant_override_survives_a_later_import(self, client):
        """Teaching the categorizer once must stick for future statements."""
        upload(client, AMEX, "amex.csv")
        txns = client.get("/api/transactions?q=Netflix").get_json()["transactions"]
        client.patch(f"/api/transactions/{txns[0]['id']}",
                     json={"category": "Entertainment", "apply_to_merchant": True})

        september = """Date,Description,Card Member,Account #,Amount
09/15/2026,NETFLIX.COM 866-579-7172 CA,M P,-31004,22.99
"""
        upload(client, september, "amex-sept.csv")

        newest = client.get("/api/transactions?month=2026-09").get_json()["transactions"]
        assert newest[0]["category"] == "Entertainment"

    def test_rejects_an_unknown_category(self, client):
        upload(client, AMEX, "amex.csv")
        txns = client.get("/api/transactions").get_json()["transactions"]
        r = client.patch(f"/api/transactions/{txns[0]['id']}", json={"category": "Nonsense"})
        assert r.status_code == 400

    def test_missing_transaction_is_a_404(self, client):
        r = client.patch("/api/transactions/deadbeef", json={"category": "Dining"})
        assert r.status_code == 404


class TestAnalyticsEndpoints:
    def test_summary_on_an_empty_ledger(self, client):
        assert client.get("/api/summary").get_json()["empty"] is True

    def test_summary_excludes_card_payments_from_spend(self, client):
        upload(client, CHASE, "chase.csv")
        body = client.get("/api/summary").get_json()
        categories = {c["category"] for c in body["categories_all_time"]}
        assert "Transfers" not in categories
        assert body["total_spend"] == pytest.approx(42.10)

    def test_insights_month(self, client):
        upload(client, AMEX, "amex.csv")
        body = client.get("/api/insights/month?month=2026-07").get_json()
        assert body["where"]["groups"][0]["categories"] or body["where"]["groups"][1]["categories"]
        assert client.get("/api/breakdown?month=2026-07").status_code == 404

    def test_recurring_endpoint_shape(self, client):
        upload(client, AMEX, "amex.csv")
        body = client.get("/api/recurring").get_json()
        assert "recurring" in body and "summary" in body

class TestBundledStatements:
    """The owner's closed card, read as a real-world ledger. The button that
    loaded it went with file import (C1)."""

    def test_loading_brings_the_rows_in(self, client):
        body = load_bundled(client)
        assert body["imported"] == 207
        assert body["date_range"] == ["2025-03-19", "2026-08-05"]

    def test_loading_twice_adds_nothing(self, client):
        load_bundled(client)
        again = load_bundled(client)
        assert again["imported"] == 0
        assert again["duplicates"] == 207

    def test_the_rows_land_in_one_named_account(self, client):
        load_bundled(client)
        accounts = client.get("/api/accounts").get_json()["accounts"]
        assert len(accounts) == 1
        assert accounts[0]["account_id"] == "scotiabank_amex"
        assert accounts[0]["account_name"] == "Scotiabank Amex (closed)"

    def test_purchases_are_spending_and_payments_are_not(self, client):
        """The export writes purchases positive; the schema said otherwise."""
        load_bundled(client)
        rows = client.get("/api/transactions?limit=500").get_json()["transactions"]
        by_desc = {t["description"]: t for t in rows}
        assert by_desc["QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY)"]["amount"] > 0
        payment = by_desc["PAYMENT FROM-**********"]
        assert payment["amount"] < 0
        assert payment["category"] == "Transfers"

    def test_a_redemption_does_not_reduce_the_spending_total(self, client):
        load_bundled(client)
        rows = client.get("/api/transactions?limit=500").get_json()["transactions"]
        credits = [t for t in rows if "SCENE+" in t["description"]]
        assert len(credits) == 2
        assert all(t["category"] == "Transfers" for t in credits), credits


class TestAccountSyncDecisions:
    """Choosing which of a bank's accounts to keep, from inside the app."""

    def _seen(self, client):
        """Two accounts a bank handed over, as a sync would record them."""
        st = client.application.config["STORE"]
        st.note_account("card-1", name="TD Cash Back Visa ••4242",
                        item_id="item-1", enabled=True, account_type="credit",
                        subtype="credit card")
        st.note_account("chq-1", name="TD Everyday Chequing ••1111",
                        item_id="item-1", enabled=False, account_type="depository",
                        subtype="chequing")
        return st

    def test_accounts_with_no_rows_are_still_listed(self, client):
        """An account cannot be switched off if it never appears."""
        self._seen(client)
        rows = client.get("/api/accounts").get_json()["accounts"]
        by_id = {r["account_id"]: r for r in rows}
        assert by_id["chq-1"]["transactions"] == 0
        assert by_id["chq-1"]["syncs"] is False
        assert by_id["card-1"]["syncs"] is True

    def test_turning_one_off_records_a_choice(self, client):
        st = self._seen(client)
        r = client.put("/api/accounts/card-1/sync", json={"enabled": False})
        assert r.status_code == 200
        rule = st.account_sync_rules()["card-1"]
        assert rule["enabled"] is False
        assert rule["decided_by"] == "user"

    def test_turning_one_back_on_records_a_choice(self, client):
        st = self._seen(client)
        client.put("/api/accounts/chq-1/sync", json={"enabled": True})
        rule = st.account_sync_rules()["chq-1"]
        assert rule["enabled"] is True
        assert rule["decided_by"] == "user"

    def test_the_flag_is_required(self, client):
        self._seen(client)
        assert client.put("/api/accounts/card-1/sync", json={}).status_code == 400

    def test_removing_an_account_also_stops_it_syncing(self, client):
        st = self._seen(client)
        r = client.delete("/api/accounts/card-1")
        assert r.status_code == 200
        assert r.get_json()["stopped_syncing"] is True
        assert st.account_sync_rules()["card-1"]["enabled"] is False

    def test_removal_can_leave_the_connection_alone(self, client):
        st = self._seen(client)
        r = client.delete("/api/accounts/card-1?stop_syncing=0")
        assert r.get_json()["stopped_syncing"] is False
        assert st.account_sync_rules()["card-1"]["enabled"] is True

    def test_an_unknown_account_is_still_a_404(self, client):
        assert client.delete("/api/accounts/nope").status_code == 404

    def test_an_imported_account_has_no_sync_state(self, client):
        """A statement has no bank behind it, so there is nothing to switch."""
        load_bundled(client)
        rows = client.get("/api/accounts").get_json()["accounts"]
        scotia = next(r for r in rows if r["account_id"] == "scotiabank_amex")
        assert scotia["syncs"] is None
