"""End-to-end API tests against a temporary ledger."""

import pytest

from app import create_app

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


def upload(client, content, name="export.csv"):
    return client.post("/api/import", json={"files": [{"name": name, "content": content}]})


class TestImport:
    def test_import_reports_format_and_count(self, client):
        r = upload(client, AMEX, "amex.csv")
        assert r.status_code == 200
        body = r.get_json()
        assert body["imported"] == 5
        assert body["results"][0]["format_label"] == "American Express"

    def test_importing_twice_imports_nothing_the_second_time(self, client):
        upload(client, AMEX, "amex.csv")
        second = upload(client, AMEX, "amex.csv").get_json()
        assert second["imported"] == 0
        assert second["duplicates"] == 5

    def test_multiple_cards_aggregate_into_one_ledger(self, client):
        upload(client, AMEX, "amex.csv")
        upload(client, CHASE, "chase.csv")

        accounts = client.get("/api/accounts").get_json()["accounts"]
        assert len(accounts) == 2

        total = client.get("/api/transactions?limit=500").get_json()["total"]
        assert total == 7

    def test_rejects_an_empty_request(self, client):
        assert client.post("/api/import", json={"files": []}).status_code == 400

    def test_import_history_is_recorded(self, client):
        upload(client, AMEX, "amex.csv")
        history = client.get("/api/imports").get_json()["imports"]
        assert history[0]["filename"] == "amex.csv"
        assert history[0]["imported"] == 5


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

    def test_breakdown(self, client):
        upload(client, AMEX, "amex.csv")
        body = client.get("/api/breakdown?month=2026-07").get_json()
        assert body["categories"]
        assert body["merchants"][0]["merchant"] == "Whole Foods Mkt"

    def test_insights_endpoint_shape(self, client):
        upload(client, AMEX, "amex.csv")
        body = client.get("/api/insights").get_json()
        assert "findings" in body and "summary" in body
        assert "narrative" in body

    def test_recurring_endpoint_shape(self, client):
        upload(client, AMEX, "amex.csv")
        body = client.get("/api/recurring").get_json()
        assert "recurring" in body and "summary" in body

    def test_dismissing_an_insight_hides_it(self, client):
        upload(client, YEAR_OF_FEES, "amex-year.csv")
        findings = client.get("/api/insights").get_json()["findings"]
        assert findings

        target = findings[0]["id"]
        client.post(f"/api/insights/{target}/dismiss")
        after = client.get("/api/insights").get_json()["findings"]
        assert all(f["id"] != target for f in after)

        client.delete(f"/api/insights/{target}/dismiss")
        restored = client.get("/api/insights").get_json()["findings"]
        assert any(f["id"] == target for f in restored)


class TestBudgets:
    def test_set_and_read_back(self, client):
        upload(client, AMEX, "amex.csv")
        r = client.put("/api/budgets", json={"budgets": {"Coffee": 60, "Dining": 300}})
        assert r.status_code == 200

        body = client.get("/api/budgets?month=2026-07").get_json()
        assert body["budgets"]["Coffee"] == 60
        coffee = [s for s in body["status"] if s["category"] == "Coffee"][0]
        assert coffee["spent"] == 6.40
        assert coffee["remaining"] == pytest.approx(53.60)

    def test_rejects_unknown_category(self, client):
        assert client.put("/api/budgets", json={"budgets": {"Nope": 10}}).status_code == 400

    def test_zero_clears_a_budget(self, client):
        client.put("/api/budgets", json={"budgets": {"Coffee": 60}})
        client.put("/api/budgets", json={"budgets": {"Coffee": 0}})
        assert "Coffee" not in client.get("/api/budgets").get_json()["budgets"]


class TestSources:
    def test_csv_is_available_and_plaid_reports_setup_steps(self, client):
        body = client.get("/api/sources").get_json()
        sources = {s["key"]: s for s in body["sources"]}

        assert sources["csv"]["available"] is True
        # Plaid is implemented but unconfigured — it must explain itself
        # rather than simply appearing broken.
        assert sources["plaid"]["available"] is False
        assert sources["plaid"]["setup_steps"]

    def test_syncing_an_unconfigured_source_returns_setup_guidance(self, client):
        r = client.post("/api/sync/plaid", json={})
        assert r.status_code == 501
        assert r.get_json()["setup"]["setup_steps"]

    def test_unknown_source_is_a_404(self, client):
        assert client.post("/api/sync/nope", json={}).status_code == 404

    def test_narrative_preview_sends_aggregates_only(self, client):
        """The privacy contract: no raw transaction rows leave the machine."""
        upload(client, AMEX, "amex.csv")
        payload = client.post("/api/narrative?preview=1").get_json()["payload"]

        assert "categories_this_month" in payload
        assert "transactions" not in payload
        blob = str(payload)
        assert "31004" not in blob          # no account numbers
        assert "SQ *BLUE BOTTLE" not in blob  # no raw descriptors
