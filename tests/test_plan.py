"""The weekly allowance (spend_plan), piggy-bank draws and manual entry."""

from datetime import date

import pytest

from finance import manual, spend_plan
from finance.categorize import apply_categories
from finance.models import Transaction
from ledger_files import upload


def txn(d, desc, amount, category="", source="rule"):
    t = Transaction(date=d, description=desc, amount=amount, account_id="a")
    if category:
        t.category, t.category_source = category, source
    return t


def dining(d, amount):
    return txn(d, "NUTBAR TORONTO ON", amount, category="Dining")


# ── Safe to spend ────────────────────────────────────────────────────────────

class TestSafeToSpend:
    def test_unspent_days_roll_forward(self):
        """Spend nothing for four days and day five carries all of it."""
        state = spend_plan.compute([], 310.0, "2025-01", today=date(2025, 1, 5))
        assert state["flat_daily"] == pytest.approx(10.0)
        assert state["carried_in"] == pytest.approx(40.0)
        assert state["safe_today"] == pytest.approx(50.0)

    def test_spending_exactly_the_allowance_carries_nothing(self):
        rows = [dining(f"2025-01-0{d}", 10.0) for d in range(1, 5)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 5))
        assert state["carried_in"] == pytest.approx(0.0)
        assert state["safe_today"] == pytest.approx(10.0)

    def test_overspending_shows_a_negative_number_not_a_lie(self):
        """The strict arithmetic is still reported, and still unflattering."""
        rows = [dining("2025-01-01", 100.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))
        assert state["carried_in"] == pytest.approx(-90.0)
        assert state["safe_today"] == pytest.approx(-80.0)
        assert state["over_strict"] is True

    def test_a_shortfall_is_spread_rather_than_dumped_on_tomorrow(self):
        """What the day leads with after you go over.

        Strict rollover would have today start at −$80, which is honest and
        unusable: an allowance already failed before breakfast is one you
        stop reading. The month still has to balance, so the shortfall is
        divided over the days that remain instead.
        """
        rows = [dining("2025-01-01", 100.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))

        assert state["behind"] is True
        assert state["recovering"] is True
        assert state["safe_today_effective"] == pytest.approx(7.0)
        # The figure shown is usable, so the day does not read as already lost.
        assert state["over"] is False

    def test_a_surplus_still_rolls_straight_onto_today(self):
        """Carrying your own restraint forward is the point of the plan."""
        rows = [dining("2025-01-01", 1.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))
        assert state["behind"] is False
        assert state["safe_today_effective"] == pytest.approx(state["safe_today"])
        assert state["safe_today"] > state["flat_daily"]

    def test_a_month_past_its_budget_is_over_either_way(self):
        """Spreading cannot rescue a month with nothing left to divide."""
        rows = [dining("2025-01-01", 400.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))
        assert state["recovering"] is False
        assert state["over"] is True
        assert state["over_strict"] is True

    def test_spreading_divides_the_shortfall_over_the_days_left(self):
        rows = [dining("2025-01-01", 100.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))
        # $210 left over 30 remaining days.
        assert state["days_left"] == 30
        assert state["spread_daily"] == pytest.approx(7.0)

    def test_committed_costs_do_not_count(self):
        """Rent can't be influenced by a daily number, so it stays out of it."""
        rows = [txn("2025-01-01", "PROPERTY MGMT", 1500.0, category="Rent & Housing"),
                dining("2025-01-01", 10.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 1))
        assert state["spent_mtd"] == pytest.approx(10.0)

    def test_card_payments_do_not_count(self):
        rows = [txn("2025-01-01", "PAYMENT FROM - ****", -500.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 1))
        assert state["spent_mtd"] == pytest.approx(0.0)

    def test_covering_from_a_bucket_raises_the_month_budget(self):
        rows = [dining("2025-01-01", 100.0)]
        apply_categories(rows)
        plain = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 2))
        covered = spend_plan.compute(rows, 310.0, "2025-01",
                                     today=date(2025, 1, 2), covered=90.0)
        assert covered["budget"] == pytest.approx(400.0)
        assert covered["safe_today"] > plain["safe_today"]

    def test_a_finished_month_reports_its_final_state(self):
        rows = [dining("2025-01-15", 100.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 6, 1))
        assert state["day"] == 31
        assert state["days_left"] == 1


class TestManualEntry:
    def test_it_builds_a_normal_transaction(self):
        t = manual.build("2025-01-05", "blue bottle coffee", "6.40")
        assert t.date == "2025-01-05"
        assert t.amount == pytest.approx(6.40)
        assert t.source == "manual"

    @pytest.mark.parametrize("d,desc,amt", [
        ("nonsense", "coffee", "5"),
        ("2025-01-05", "", "5"),
        ("2025-01-05", "coffee", "abc"),
    ])
    def test_unusable_input_is_refused(self, d, desc, amt):
        assert manual.build(d, desc, amt) is None

    def test_a_same_amount_nearby_row_is_reported(self):
        existing = [dining("2025-01-05", 24.30)]
        apply_categories(existing)
        candidate = manual.build("2025-01-06", "nutbar", "24.30")
        matches = manual.find_possible_duplicates(candidate, existing)
        assert matches and matches[0]["days_apart"] == 1

    def test_a_different_amount_is_not_a_match(self):
        existing = [dining("2025-01-05", 24.30)]
        apply_categories(existing)
        candidate = manual.build("2025-01-05", "nutbar", "31.00")
        assert manual.find_possible_duplicates(candidate, existing) == []

    def test_a_distant_row_is_not_a_match(self):
        existing = [dining("2025-01-05", 24.30)]
        apply_categories(existing)
        candidate = manual.build("2025-02-20", "nutbar", "24.30")
        assert manual.find_possible_duplicates(candidate, existing) == []


class TestManualApi:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def test_adding_a_transaction_by_hand(self, client):
        r = client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "Blue Bottle Coffee", "amount": 6.40})
        assert r.status_code == 200
        assert r.get_json()["category"] == "Coffee"
        assert client.get("/api/transactions").get_json()["total"] == 1

    def test_the_same_entry_twice_is_refused(self, client):
        payload = {"date": "2025-01-05", "description": "Blue Bottle Coffee",
                   "amount": 6.40}
        client.post("/api/transactions", json=payload)
        r = client.post("/api/transactions", json=payload)
        assert r.status_code == 409
        assert r.get_json()["duplicate"] is True
        assert client.get("/api/transactions").get_json()["total"] == 1

    def test_a_similar_entry_asks_before_adding(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "Blue Bottle Coffee", "amount": 6.40})
        r = client.post("/api/transactions", json={
            "date": "2025-01-06", "description": "Coffee", "amount": 6.40})
        assert r.status_code == 409
        assert r.get_json()["needs_confirmation"] is True

    def test_confirming_adds_it(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "Blue Bottle Coffee", "amount": 6.40})
        r = client.post("/api/transactions", json={
            "date": "2025-01-06", "description": "Coffee", "amount": 6.40,
            "confirm": True})
        assert r.status_code == 200
        assert client.get("/api/transactions").get_json()["total"] == 2

    def test_an_import_does_not_re_add_a_manual_row(self, client):
        """The other direction: the statement arrives carrying what you typed."""
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "BLUE BOTTLE COFFEE", "amount": 6.40})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/05/2025,BLUE BOTTLE COFFEE,M P,-31004,6.40\n")
        upload(client, csv, "a.csv")
        rows = client.get("/api/transactions").get_json()["transactions"]
        assert len(rows) == 1
        # The statement's version is the one kept: it knows the real card.
        assert rows[0]["source"] != "manual"

    def test_a_loose_match_still_supersedes_the_placeholder(self, client):
        """The point of the placeholder: the typed date and descriptor are rough."""
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "coffee w/ Sam", "amount": 6.40})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/07/2025,SQ *BLUE BOTTLE 4471,M P,-31004,6.40\n")
        upload(client, csv, "a.csv")
        assert client.get("/api/transactions").get_json()["total"] == 1

    def test_a_category_set_by_hand_survives_the_import(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "coffee w/ Sam", "amount": 6.40,
            "category": "Gifts & Charity"})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/06/2025,SQ *BLUE BOTTLE 4471,M P,-31004,6.40\n")
        upload(client, csv, "a.csv")
        rows = client.get("/api/transactions").get_json()["transactions"]
        assert len(rows) == 1
        assert rows[0]["category"] == "Gifts & Charity"
        assert rows[0]["category_source"] == "user"

    def test_two_typed_rows_are_replaced_by_two_real_ones(self, client):
        for day in ("2025-01-05", "2025-01-06"):
            client.post("/api/transactions", json={
                "date": day, "description": "coffee", "amount": 6.40,
                "confirm": True})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/05/2025,SQ *BLUE BOTTLE,M P,-31004,6.40\n"
               "01/06/2025,SQ *BLUE BOTTLE,M P,-31004,6.40\n")
        upload(client, csv, "a.csv")
        rows = client.get("/api/transactions").get_json()["transactions"]
        assert len(rows) == 2
        assert all(r["source"] != "manual" for r in rows)

    def test_an_unrelated_import_leaves_the_placeholder_alone(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "coffee", "amount": 6.40})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/05/2025,LOBLAWS 1042,M P,-31004,84.12\n")
        upload(client, csv, "a.csv")
        assert client.get("/api/transactions").get_json()["total"] == 2

    def test_bad_input_is_rejected(self, client):
        assert client.post("/api/transactions", json={"description": "x"}).status_code == 400

    def test_a_manual_row_can_be_deleted(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "Coffee", "amount": 6.40})
        tid = client.get("/api/transactions").get_json()["transactions"][0]["id"]
        assert client.delete(f"/api/transactions/{tid}").status_code == 200
        assert client.get("/api/transactions").get_json()["total"] == 0


class TestPiggyDraws:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def _bank(self, client):
        return client.post("/api/piggy", json={
            "name": "Fun", "target": 1200, "cadence": "annual", "opening": 100,
        }).get_json()["id"]

    def test_there_is_no_endpoint_that_draws_any_more(self, client):
        bank_id = self._bank(client)
        r = client.post(f"/api/piggy/{bank_id}/cover", json={"amount": 50})
        assert r.status_code in (404, 405)

    def test_an_old_draw_can_be_undone(self, client):
        bank_id = self._bank(client)
        st = client.application.config["STORE"]
        month = date.today().strftime("%Y-%m")
        before = client.get("/api/piggy").get_json()["banks"][0]["available"]
        with st.conn() as c:
            c.execute("INSERT INTO piggy_draws (bank_id, month, amount, note) "
                      "VALUES (?,?,?,?)", (bank_id, month, 50.0, ""))
        drawn = client.get("/api/piggy").get_json()
        assert drawn["banks"][0]["available"] == pytest.approx(before - 50.0)
        assert st.covered_in(month) == pytest.approx(50.0)

        draw_id = next(d["id"] for d in st.draws() if d["amount"] > 0)
        assert client.delete(f"/api/piggy/draws/{draw_id}").status_code == 200
        undone = client.get("/api/piggy").get_json()
        assert undone["banks"][0]["available"] == pytest.approx(before)
        assert st.covered_in(month) == 0
        assert client.delete(f"/api/piggy/draws/{draw_id}").status_code == 404


class TestTheWeek:
    """The headline is a week: Monday to Sunday, clipped to the month."""

    def test_weeks_run_monday_to_sunday_clipped_to_the_month(self):
        # October 2026 starts on a Thursday and ends on a Saturday.
        assert spend_plan.week_bounds("2026-10", 1) == (1, 4)
        assert spend_plan.week_bounds("2026-10", 4) == (1, 4)
        assert spend_plan.week_bounds("2026-10", 5) == (5, 11)
        assert spend_plan.week_bounds("2026-10", 31) == (26, 31)

    def test_a_short_week_gets_its_days_share(self):
        state = spend_plan.compute([], 310.0, "2025-01", today=date(2025, 1, 2))
        week = state["week"]
        assert week["days"] == 5 and week["short"] is True
        assert week["allowance"] == pytest.approx(50.0)
        assert week["nominal"] == pytest.approx(70.0)

    def test_underspending_rolls_into_this_week(self):
        """Restraint is carried forward in full, the same choice the daily
        number makes. Spend nothing in week one and week two has both."""
        state = spend_plan.compute([], 310.0, "2025-01", today=date(2025, 1, 6))
        week = state["week"]
        assert (week["first_day"], week["last_day"]) == (6, 12)
        assert week["carried_in"] == pytest.approx(50.0)
        assert week["allowance"] == pytest.approx(70.0 + 50.0)

    def test_overspending_is_spread_not_dumped_on_the_next_week(self):
        rows = [dining("2025-01-02", 200.0)]          # $150 over week one
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 6))
        week = state["week"]
        assert week["behind"] is True
        # $110 left of the month over the 26 days from the 6th; this week is 7.
        assert week["allowance"] == pytest.approx(110.0 * 7 / 26, abs=0.01)
        assert week["allowance"] > 0

    def test_the_last_week_is_allowed_exactly_what_is_left(self):
        rows = [dining("2025-01-08", 120.0), dining("2025-01-15", 40.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 28))
        week = state["week"]
        assert week["last_day"] == 31
        assert week["allowance"] == pytest.approx(310.0 - 160.0, abs=0.01)

    def test_ahead_of_pace_a_week_never_exceeds_the_month(self):
        rows = [dining("2025-01-03", 20.0)]
        apply_categories(rows)
        for day in range(1, 32):
            state = spend_plan.compute(rows, 310.0, "2025-01",
                                       today=date(2025, 1, day))
            spent_before = sum(r.amount for r in rows
                               if int(r.date[8:]) < state["week"]["first_day"])
            assert state["week"]["allowance"] <= 310.0 - spent_before + 0.01

    def test_the_weeks_of_a_month_add_up_to_its_budget(self):
        """Spending exactly each week's allowance uses exactly the month."""
        rows, used = [], 0.0
        day = 1
        while day <= 31:
            state = spend_plan.compute(list(rows), 310.0, "2025-01",
                                       today=date(2025, 1, day))
            week = state["week"]
            if week["allowance"] > 0:
                rows.append(dining(f"2025-01-{day:02d}", round(week["allowance"], 2)))
                apply_categories(rows)
                used += round(week["allowance"], 2)
            day = week["last_day"] + 1
        assert used == pytest.approx(310.0, abs=0.05)

    def test_per_day_is_what_is_left_over_the_days_left_in_the_week(self):
        state = spend_plan.compute([], 310.0, "2025-01", today=date(2025, 1, 9))
        week = state["week"]                            # Thu 9 in Mon 6 – Sun 12
        assert week["days_left"] == 4
        assert week["per_day"] == pytest.approx(week["left"] / 4, abs=0.01)
