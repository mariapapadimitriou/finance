"""Trips: declared date ranges that reclassify spending as Travel."""

import pytest

from finance.categorize import apply_categories
from finance.models import Transaction
from finance.trips import (
    Trip, apply_trips, covering_trip, summarize, validate,
)


def txn(date, desc, amount, category="", source="rule"):
    t = Transaction(date=date, description=desc, amount=amount, account_id="a")
    if category:
        t.category, t.category_source = category, source
    return t


NYC = Trip(id=1, name="New York", start_date="2025-05-15", end_date="2025-05-19")


class TestValidation:
    def test_accepts_a_sane_trip(self):
        assert validate("New York", "2025-05-15", "2025-05-19") is None

    def test_a_single_day_trip_is_fine(self):
        assert validate("Day out", "2025-05-15", "2025-05-15") is None

    def test_rejects_a_missing_name(self):
        assert validate("  ", "2025-05-15", "2025-05-19")

    def test_rejects_backwards_dates(self):
        assert "before it starts" in validate("X", "2025-05-19", "2025-05-15")

    def test_rejects_unparseable_dates(self):
        assert "YYYY-MM-DD" in validate("X", "last tuesday", "2025-05-19")

    def test_rejects_an_absurdly_long_trip(self):
        assert validate("X", "2020-01-01", "2025-01-01")


class TestCoverage:
    @pytest.mark.parametrize("day,covered", [
        ("2025-05-14", False),
        ("2025-05-15", True),    # inclusive start
        ("2025-05-17", True),
        ("2025-05-19", True),    # inclusive end
        ("2025-05-20", False),
    ])
    def test_boundaries_are_inclusive(self, day, covered):
        assert NYC.covers(day) is covered

    def test_nights_counts_the_span(self):
        assert NYC.nights == 4

    def test_overlapping_trips_resolve_to_the_earlier_one(self):
        later = Trip(id=2, name="Overlap", start_date="2025-05-18",
                     end_date="2025-05-25")
        assert covering_trip([later, NYC], "2025-05-18").name == "New York"

    def test_no_trip_covers_an_unrelated_date(self):
        assert covering_trip([NYC], "2025-08-01") is None


class TestReclassification:
    def test_spending_inside_the_dates_becomes_travel(self):
        rows = [
            txn("2025-05-16", "DREAM BABY NEW YORK NY", 22.84),
            txn("2025-05-18", "LOCANDA VERDE NEW YORK NY", 752.95),
        ]
        apply_categories(rows)
        assert {r.category for r in rows} == {"Alcohol & Bars", "Dining"}

        apply_trips(rows, [NYC])
        assert all(r.category == "Travel" for r in rows)
        assert all(r.category_source == "trip" for r in rows)

    def test_spending_outside_the_dates_is_untouched(self):
        rows = [txn("2025-06-01", "NUTBAR TORONTO ON", 16.95)]
        apply_categories(rows)
        apply_trips(rows, [NYC])
        assert rows[0].category == "Dining"

    def test_card_payments_are_never_travel(self):
        """A payment that lands mid-trip is still money moving, not spending."""
        rows = [txn("2025-05-17", "PAYMENT FROM - *****10*6822", -942.91)]
        apply_categories(rows)
        assert rows[0].category == "Transfers"
        apply_trips(rows, [NYC])
        assert rows[0].category == "Transfers"

    def test_fees_are_never_travel(self):
        rows = [txn("2025-05-17", "FOREIGN TRANSACTION FEE", 4.85)]
        apply_categories(rows)
        assert rows[0].category == "Fees & Interest"
        apply_trips(rows, [NYC])
        assert rows[0].category == "Fees & Interest"

    def test_a_category_you_set_by_hand_wins(self):
        """An explicit choice outranks the trip."""
        rows = [txn("2025-05-16", "DUANE READE NEW YORK NY", 37.06,
                    category="Health", source="user")]
        apply_trips(rows, [NYC])
        assert rows[0].category == "Health"

    def test_no_trips_changes_nothing(self):
        rows = [txn("2025-05-16", "DREAM BABY NEW YORK NY", 22.84)]
        apply_categories(rows)
        before = rows[0].category
        assert apply_trips(rows, []) == 0
        assert rows[0].category == before

    def test_reports_how_many_rows_moved(self):
        rows = [txn("2025-05-16", "A CAFE", 5.0), txn("2025-09-01", "A CAFE", 5.0)]
        apply_categories(rows)
        assert apply_trips(rows, [NYC]) == 1

    def test_applying_twice_is_idempotent(self):
        rows = [txn("2025-05-16", "DREAM BABY NEW YORK NY", 22.84)]
        apply_categories(rows)
        apply_trips(rows, [NYC])
        assert apply_trips(rows, [NYC]) == 0

    def test_removing_a_trip_reverts_the_rows(self):
        """Recategorizing without the trip puts merchants back where they were."""
        rows = [txn("2025-05-18", "LOCANDA VERDE NEW YORK NY", 752.95)]
        apply_categories(rows)
        apply_trips(rows, [NYC])
        assert rows[0].category == "Travel"

        apply_categories(rows)          # what recategorize_all does first
        apply_trips(rows, [])           # trip is gone
        assert rows[0].category == "Dining"


class TestSummary:
    def test_totals_only_count_spending_inside_the_trip(self):
        rows = [
            txn("2025-05-16", "DREAM BABY NEW YORK NY", 22.84),
            txn("2025-05-18", "LOCANDA VERDE NEW YORK NY", 752.95),
            txn("2025-05-17", "PAYMENT FROM - *****10*6822", -942.91),
            txn("2025-07-01", "NUTBAR TORONTO ON", 16.95),
        ]
        apply_categories(rows)
        s = summarize(NYC, rows)
        assert s["transactions"] == 2
        assert s["total"] == pytest.approx(775.79)
        assert s["merchants"] == 2

    def test_per_day_divides_by_days_not_nights(self):
        rows = [txn("2025-05-16", "A CAFE", 100.0)]
        apply_categories(rows)
        # 15th to 19th inclusive is five days, not four.
        assert summarize(NYC, rows)["per_day"] == pytest.approx(20.0)


class TestApiRoundTrip:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def _seed(self, client):
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "05/16/2025,DREAM BABY NEW YORK NY,M P,-31004,22.84\n"
               "05/18/2025,LOCANDA VERDE NEW YORK NY,M P,-31004,752.95\n"
               "07/01/2025,NUTBAR TORONTO ON,M P,-31004,16.95\n")
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})

    def test_adding_a_trip_reclassifies_immediately(self, client):
        self._seed(client)
        r = client.post("/api/trips", json={
            "name": "New York", "start_date": "2025-05-15", "end_date": "2025-05-19"})
        assert r.status_code == 200

        travel = client.get("/api/transactions?category=Travel").get_json()
        assert travel["total"] == 2

    def test_removing_a_trip_puts_them_back(self, client):
        self._seed(client)
        trip_id = client.post("/api/trips", json={
            "name": "New York", "start_date": "2025-05-15",
            "end_date": "2025-05-19"}).get_json()["id"]

        client.delete(f"/api/trips/{trip_id}")
        assert client.get("/api/transactions?category=Travel").get_json()["total"] == 0
        assert client.get("/api/transactions?category=Dining").get_json()["total"] == 2

    def test_trip_listing_carries_its_totals(self, client):
        self._seed(client)
        client.post("/api/trips", json={
            "name": "New York", "start_date": "2025-05-15", "end_date": "2025-05-19"})

        body = client.get("/api/trips").get_json()
        assert body["summary"]["count"] == 1
        assert body["trips"][0]["total"] == pytest.approx(775.79)
        assert body["trips"][0]["nights"] == 4

    def test_a_bad_trip_is_rejected(self, client):
        r = client.post("/api/trips", json={
            "name": "X", "start_date": "2025-05-19", "end_date": "2025-05-15"})
        assert r.status_code == 400
        assert "before it starts" in r.get_json()["error"]

    def test_editing_a_trip_recategorizes(self, client):
        self._seed(client)
        trip_id = client.post("/api/trips", json={
            "name": "NY", "start_date": "2025-05-15",
            "end_date": "2025-05-19"}).get_json()["id"]

        # Widen it to swallow the Toronto charge too.
        client.patch(f"/api/trips/{trip_id}", json={
            "name": "NY", "start_date": "2025-05-15", "end_date": "2025-07-02"})
        assert client.get("/api/transactions?category=Travel").get_json()["total"] == 3

    def test_missing_trip_is_a_404(self, client):
        assert client.delete("/api/trips/999").status_code == 404
