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


class TestBundledStatements:
    """A closed card's statements: loaded on request, never by themselves."""

    def test_the_set_is_listed_with_its_size(self, client):
        body = client.get("/api/import/bundled").get_json()
        scotia = next(b for b in body["bundled"] if b["key"] == "scotiabank_amex")
        assert scotia["rows"] == 207
        assert scotia["loaded"] is False

    def test_loading_brings_the_rows_in(self, client):
        r = client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        body = r.get_json()
        assert r.status_code == 200
        assert body["imported"] == 207
        assert body["date_range"] == ["2025-03-19", "2026-08-05"]

    def test_loading_twice_adds_nothing(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        again = client.post("/api/import/bundled",
                            json={"key": "scotiabank_amex"}).get_json()
        assert again["imported"] == 0
        assert again["duplicates"] == 207

    def test_the_rows_land_in_one_named_account(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        accounts = client.get("/api/accounts").get_json()["accounts"]
        assert len(accounts) == 1
        assert accounts[0]["account_id"] == "scotiabank_amex"
        assert accounts[0]["account_name"] == "Scotiabank Amex (closed)"

    def test_the_listing_says_so_once_it_is_loaded(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        body = client.get("/api/import/bundled").get_json()
        assert body["bundled"][0]["loaded"] is True

    def test_an_unknown_set_is_a_404(self, client):
        assert client.post("/api/import/bundled",
                           json={"key": "nonesuch"}).status_code == 404

    def test_purchases_are_spending_and_payments_are_not(self, client):
        """The export writes purchases positive; the schema said otherwise."""
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        rows = client.get("/api/transactions?limit=500").get_json()["transactions"]
        by_desc = {t["description"]: t for t in rows}
        assert by_desc["QUEEN'S CROSS FOOD HALL TORONTO ON (APPLE PAY)"]["amount"] > 0
        payment = by_desc["PAYMENT FROM-**********"]
        assert payment["amount"] < 0
        assert payment["category"] == "Transfers"

    def test_a_redemption_does_not_reduce_the_spending_total(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
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
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        rows = client.get("/api/accounts").get_json()["accounts"]
        scotia = next(r for r in rows if r["account_id"] == "scotiabank_amex")
        assert scotia["syncs"] is None


class TestWhereTheLedgerStarts:
    """Months where only some cards were imported read as restraint.

    They are not restraint, they are months with cards missing, and averaged
    in with complete ones they drag every trend down. Cutting them has to
    persist: a fresh Plaid link backfills two years, so a one-time deletion
    would be undone by the next sync.
    """

    def _loaded(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})

    def test_it_reports_what_is_there_before_anything_is_set(self, client):
        self._loaded(client)
        body = client.get("/api/ledger/start").get_json()
        assert body["start"] == ""
        assert body["earliest"] == "2025-03-19"
        assert body["latest"] == "2026-08-05"
        assert body["total"] == 207

    def test_setting_a_date_alone_removes_nothing(self, client):
        self._loaded(client)
        r = client.put("/api/ledger/start", json={"start": "2026-03-01"})
        assert r.get_json()["removed"] == 0
        assert client.get("/api/ledger/start").get_json()["total"] == 207

    def test_trimming_removes_what_precedes_it(self, client):
        self._loaded(client)
        r = client.put("/api/ledger/start",
                       json={"start": "2026-03-01", "trim": True})
        assert r.get_json()["removed"] == 92
        after = client.get("/api/ledger/start").get_json()
        assert after["total"] == 115
        assert after["earliest"] >= "2026-03-01"
        assert after["before_start"] == 0

    def test_a_later_import_cannot_put_them_back(self, client):
        """The whole point. A one-time deletion would not survive a sync."""
        self._loaded(client)
        client.put("/api/ledger/start",
                   json={"start": "2026-03-01", "trim": True})
        again = client.post("/api/import/bundled",
                            json={"key": "scotiabank_amex"}).get_json()
        assert again["imported"] == 0
        assert again["before_start"] == 92
        assert client.get("/api/ledger/start").get_json()["total"] == 115

    def test_an_upload_is_filtered_the_same_way(self, client):
        client.put("/api/ledger/start", json={"start": "2026-07-01"})
        r = upload(client, AMEX, "amex.csv").get_json()
        assert r["results"][0]["before_start"] == 0   # AMEX fixture is July 2026
        client.put("/api/ledger/start", json={"start": "2027-01-01"})
        r = upload(client, CHASE, "chase.csv").get_json()
        assert r["imported"] == 0
        assert r["results"][0]["before_start"] > 0

    def test_a_bad_date_is_refused(self, client):
        assert client.put("/api/ledger/start",
                          json={"start": "March 2026"}).status_code == 400

    def test_clearing_the_date_lets_everything_count_again(self, client):
        self._loaded(client)
        client.put("/api/ledger/start", json={"start": "2026-03-01"})
        client.put("/api/ledger/start", json={"start": ""})
        assert client.get("/api/ledger/start").get_json()["start"] == ""
        # The rows were never deleted, so they count again immediately.
        assert client.get("/api/ledger/start").get_json()["total"] == 207

    def test_trends_use_only_what_remains(self, client):
        self._loaded(client)
        before = client.get("/api/summary").get_json()["total_spend"]
        client.put("/api/ledger/start",
                   json={"start": "2026-03-01", "trim": True})
        after = client.get("/api/summary").get_json()["total_spend"]
        assert after < before


class TestThePlanEndpoints:
    """Income and commitments in, category budgets out."""

    def setup_plan(self, client, income=5200, savings=900):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        client.put("/api/plan/setup", json={"income": income, "savings": savings})
        client.post("/api/plan/fixed", json={"name": "Rent", "amount": 2100,
                                             "category": "Rent & Housing"})

    def test_the_arithmetic_is_reported_with_its_working(self, client):
        self.setup_plan(client)
        p = client.get("/api/plan/setup").get_json()
        assert p["income"] == 5200
        assert p["fixed_total"] == 2100
        assert p["savings"] == 900
        assert p["leftover"] == 2200
        assert p["verdict"] == "ok"

    def test_commitments_can_be_added_changed_and_removed(self, client):
        self.setup_plan(client)
        cost_id = client.post("/api/plan/fixed",
                              json={"name": "Hydro", "amount": 95}).get_json()["id"]
        client.patch(f"/api/plan/fixed/{cost_id}", json={"amount": 110})
        fixed = client.get("/api/plan/fixed").get_json()["fixed"]
        assert next(f for f in fixed if f["id"] == cost_id)["amount"] == 110
        assert client.delete(f"/api/plan/fixed/{cost_id}").status_code == 200
        assert client.get("/api/plan/setup").get_json()["fixed_total"] == 2100

    def test_a_commitment_needs_a_name_and_a_cost(self, client):
        assert client.post("/api/plan/fixed", json={"amount": 10}).status_code == 400
        assert client.post("/api/plan/fixed",
                           json={"name": "X", "amount": 0}).status_code == 400

    def test_applying_sets_budgets_that_sum_to_the_leftover(self, client):
        self.setup_plan(client)
        applied = client.post("/api/plan/setup/apply").get_json()
        assert applied["leftover"] == 2200
        assert sum(applied["budgets"].values()) == pytest.approx(2200, abs=0.011)

    def test_the_daily_pool_is_only_the_discretionary_part(self, client):
        """Groceries come out of the leftover and are not pocket money."""
        self.setup_plan(client)
        applied = client.post("/api/plan/setup/apply").get_json()
        assert applied["monthly_amount"] < applied["leftover"]

    def test_applying_also_drives_the_daily_number(self, client):
        """The daily figure divides the same pool, or they disagree."""
        self.setup_plan(client)
        applied = client.post("/api/plan/setup/apply").get_json()
        plan = client.get("/api/plan").get_json()
        assert plan["state"]["monthly_amount"] == applied["monthly_amount"]

    def test_the_budget_is_not_last_months_spending(self, client):
        """The point of the whole thing."""
        self.setup_plan(client, income=3500, savings=200)
        applied = client.post("/api/plan/setup/apply").get_json()
        assert applied["leftover"] == 1200
        p = client.get("/api/plan/setup").get_json()
        assert p["typical_total"] != p["leftover"]

    def test_nothing_left_to_budget_is_refused_with_a_reason(self, client):
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        client.put("/api/plan/setup", json={"income": 1000, "savings": 1200})
        r = client.post("/api/plan/setup/apply")
        assert r.status_code == 400
        assert "nothing left" in r.get_json()["error"].lower()

    def test_no_history_is_refused_rather_than_guessed(self, client):
        client.put("/api/plan/setup", json={"income": 5000, "savings": 500})
        r = client.post("/api/plan/setup/apply")
        assert r.status_code == 400
        assert "history" in r.get_json()["error"].lower()

    def test_income_must_be_a_number(self, client):
        assert client.put("/api/plan/setup",
                          json={"income": "lots"}).status_code == 400

    def test_the_nudge_endpoint_answers_even_with_nothing_to_say(self, client):
        self.setup_plan(client)
        body = client.get("/api/nudge").get_json()
        assert "nudge" in body
