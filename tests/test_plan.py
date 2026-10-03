"""Safe-to-spend, gamification, projections and manual entry."""

from datetime import date

import pytest

from finance import manual, money_plan, projections, spend_plan
from finance.piggy import Bank
from finance.categorize import apply_categories
from finance.models import Transaction


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


class TestCanIBuyThis:
    def _state(self):
        # $310 over January's 31 days is $10 a day. 1 January 2025 is a
        # Wednesday, so the 3rd sits in a five-day week (Wed 1 – Sun 5) worth
        # $50, with $5 already spent in it.
        rows = [dining("2025-01-01", 5.0)]
        apply_categories(rows)
        return spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 3))

    def test_it_answers_against_the_week(self):
        week = self._state()["week"]
        assert (week["first_day"], week["last_day"]) == (1, 5)
        assert week["left"] == pytest.approx(45.0)

    def test_an_affordable_purchase_says_what_is_left(self):
        r = spend_plan.simulate(self._state(), 10.0)
        assert r["affordable"] is True
        assert r["leaves_week"] == pytest.approx(35.0)
        assert "rest of the week" in r["message"]

    def test_an_unaffordable_one_says_by_how_much(self):
        r = spend_plan.simulate(self._state(), 100.0)
        assert r["affordable"] is False
        assert r["short_by"] == pytest.approx(55.0)

    def test_it_offers_to_spread_the_shortfall(self):
        r = spend_plan.simulate(self._state(), 100.0)
        spread = next(o for o in r["options"] if o["kind"] == "spread")
        assert spread["new_daily"] < self._state()["flat_daily"]

    def test_it_offers_a_piggy_bank_that_can_cover_it(self):
        bank = Bank(id=1, name="Fun", target=200.0, opening=200.0)
        r = spend_plan.simulate(self._state(), 100.0, [(bank, 200.0)])
        cover = next(o for o in r["options"] if o["kind"] == "cover")
        assert cover["viable"] is True
        assert cover["bank_id"] == 1

    def test_a_bank_that_is_too_small_is_shown_as_not_viable(self):
        bank = Bank(id=1, name="Fun", target=200.0, opening=10.0)
        r = spend_plan.simulate(self._state(), 100.0, [(bank, 10.0)])
        cover = next(o for o in r["options"] if o["kind"] == "cover")
        assert cover["viable"] is False

    def test_spreading_below_zero_is_flagged_as_not_viable(self):
        rows = [dining("2025-01-01", 300.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 30))
        r = spend_plan.simulate(state, 500.0)
        spread = next(o for o in r["options"] if o["kind"] == "spread")
        assert spread["viable"] is False


class TestProseFormatting:
    """Server-written sentences are read by a person, not parsed."""

    def test_a_negative_never_renders_as_a_dollar_minus(self):
        state = spend_plan.compute([], 300.0, "2025-01", today=date(2025, 1, 31))
        state["week"]["left"] = -56.89
        state["remaining"] = -56.89
        state["days_left"] = 1
        r = spend_plan.simulate(state, 250.0)
        blob = r["message"] + " ".join(o["detail"] + o["label"] for o in r["options"])
        assert "$-" not in blob
        assert "already" in r["message"]

    def test_spreading_says_the_month_ran_out_rather_than_a_negative_daily(self):
        state = spend_plan.compute([], 300.0, "2025-01", today=date(2025, 1, 31))
        state["week"]["left"] = -56.89
        state["remaining"] = -56.89
        state["days_left"] = 1
        spread = spend_plan.simulate(state, 250.0)["options"][0]
        assert spread["viable"] is False
        assert "nothing left" in spread["detail"].lower()


class TestHowAmIDoing:
    def test_nothing_spent_reads_as_good(self):
        state = spend_plan.compute([], 310.0, "2025-01", today=date(2025, 1, 10))
        assert spend_plan.how_am_i_doing(state)["tone"] == "good"

    def test_on_pace_reads_as_good(self):
        rows = [dining(f"2025-01-{d:02d}", 10.0) for d in range(1, 11)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 10))
        assert spend_plan.how_am_i_doing(state)["tone"] == "good"

    def test_heavy_overspending_reads_as_critical(self):
        rows = [dining("2025-01-01", 400.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 10))
        status = spend_plan.how_am_i_doing(state)
        assert status["tone"] == "critical"
        assert status["projected_over"] > 0

    def test_it_reports_the_projection_it_judged_on(self):
        rows = [dining("2025-01-01", 40.0)]
        apply_categories(rows)
        state = spend_plan.compute(rows, 310.0, "2025-01", today=date(2025, 1, 4))
        # $40 over 4 days, carried across 31 days.
        assert spend_plan.how_am_i_doing(state)["projected_month_end"] == pytest.approx(310.0)


class TestProjections:
    def test_a_card_payment_is_not_income(self):
        """The bug that would project savings out of your own debt repayment."""
        rows = [txn("2025-01-25", "PAYMENT FROM - ****", -1000.0),
                dining("2025-01-02", 50.0)]
        apply_categories(rows)
        r = projections.project(rows, None, 0.0)
        assert r["available"] is False
        assert "take-home pay" in r["reason"]

    def test_with_income_it_projects_both_lines(self):
        """Without a plan there is nothing to follow, so the second line falls
        back to the pace with the cuts applied."""
        rows = [dining(f"2025-0{m}-05", 200.0) for m in range(1, 5)]
        apply_categories(rows)
        r = projections.project(rows, 3000.0, 1200.0, months_ahead=12)
        assert r["available"] is True
        assert r["monthly_cuts"] == pytest.approx(100.0)
        assert r["monthly_on_plan"] is None
        assert r["at_12"]["on_plan"] > r["at_12"]["pace"]

    def test_with_a_plan_the_second_line_is_what_the_plan_puts_away(self):
        """The fix for "it says I will never make money": the plan line is the
        savings figure, which does not depend on the spending history at all."""
        rows = [dining(f"2025-0{m}-05", 2000.0) for m in range(1, 5)]
        apply_categories(rows)
        # $3,000 in, $1,500 of rent and $400 put away leaves $1,100 — against
        # $2,000 a month of actual spending.
        rent = money_plan.FixedCost(id=1, name="Rent", amount=1500.0,
                                    category="Rent & Housing")
        plan = money_plan.plan(3000.0, [rent], 400.0)
        r = projections.project(rows, 3000.0, 0.0, months_ahead=12, plan=plan)

        # Spending far above the leftover, so the recent pace goes backwards.
        assert r["monthly_surplus"] < 0
        # The plan still accumulates, because following it means spending the
        # budget rather than the history.
        assert r["monthly_on_plan"] == pytest.approx(400.0)
        assert r["at_12"]["on_plan"] == pytest.approx(4800.0)
        assert r["at_12"]["pace"] < 0

    def test_commitments_are_not_subtracted_twice(self):
        """`leftover` already excludes them; a commitment paid by card was in
        the spending as well, so both came off and the surplus read low."""
        rows = [txn("2025-01-20", "ROGERS WIRELESS", 65.0),
                txn("2025-02-20", "ROGERS WIRELESS", 65.0),
                dining("2025-01-05", 100.0), dining("2025-02-05", 100.0)]
        apply_categories(rows)
        for t in rows:
            if "ROGERS" in t.description:
                t.category, t.category_source = "Phone & Internet", "user"

        phone = money_plan.FixedCost(id=1, name="Phone", amount=65.0,
                                     category="Phone & Internet")
        plan = money_plan.plan(3000.0, [phone], 0.0)
        r = projections.project(rows, 3000.0, 0.0, plan=plan)

        # The phone category is out of the figure the leftover is measured
        # against, though still in the headline typical month.
        assert r["plan_spend"] < r["typical_monthly_spend"]
        assert r["typical_monthly_spend"] - r["plan_spend"] == pytest.approx(65.0)

    def test_it_states_that_one_card_is_not_all_your_spending(self):
        rows = [dining("2025-01-05", 200.0)]
        apply_categories(rows)
        r = projections.project(rows, 3000.0, 0.0)
        assert "imported" in r["caveat"]

    def test_confidence_reflects_how_little_data_there_is(self):
        thin = [dining("2025-01-05", 200.0)]
        apply_categories(thin)
        assert projections.project(thin, 3000.0, 0.0)["confidence"] == "thin"

    def test_an_empty_ledger_projects_nothing(self):
        assert projections.project([], 3000.0, 0.0)["available"] is False

    def test_goal_eta_answers_under_each_scenario(self):
        rows = [dining(f"2025-0{m}-05", 200.0) for m in range(1, 5)]
        apply_categories(rows)
        r = projections.project(rows, 3000.0, 6000.0)
        eta = projections.goal_eta(r, 10000.0)
        assert eta["plan_months"] <= eta["pace_months"]

    def test_a_goal_is_reachable_on_the_plan_even_when_the_pace_says_never(self):
        rows = [dining(f"2025-0{m}-05", 2000.0) for m in range(1, 5)]
        apply_categories(rows)
        rent = money_plan.FixedCost(id=1, name="Rent", amount=1500.0,
                                    category="Rent & Housing")
        plan = money_plan.plan(3000.0, [rent], 400.0)
        r = projections.project(rows, 3000.0, 0.0, plan=plan)
        eta = projections.goal_eta(r, 4800.0)

        assert eta["pace_months"] is None          # going backwards
        assert eta["plan_months"] == 12


# ── Manual entry ─────────────────────────────────────────────────────────────

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
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
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
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
        assert client.get("/api/transactions").get_json()["total"] == 1

    def test_a_category_set_by_hand_survives_the_import(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "coffee w/ Sam", "amount": 6.40,
            "category": "Gifts & Charity"})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/06/2025,SQ *BLUE BOTTLE 4471,M P,-31004,6.40\n")
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
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
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
        rows = client.get("/api/transactions").get_json()["transactions"]
        assert len(rows) == 2
        assert all(r["source"] != "manual" for r in rows)

    def test_an_unrelated_import_leaves_the_placeholder_alone(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "coffee", "amount": 6.40})
        csv = ("Date,Description,Card Member,Account #,Amount\n"
               "01/05/2025,LOBLAWS 1042,M P,-31004,84.12\n")
        client.post("/api/import", json={"files": [{"name": "a.csv", "content": csv}]})
        assert client.get("/api/transactions").get_json()["total"] == 2

    def test_bad_input_is_rejected(self, client):
        assert client.post("/api/transactions", json={"description": "x"}).status_code == 400

    def test_a_manual_row_can_be_deleted(self, client):
        client.post("/api/transactions", json={
            "date": "2025-01-05", "description": "Coffee", "amount": 6.40})
        tid = client.get("/api/transactions").get_json()["transactions"][0]["id"]
        assert client.delete(f"/api/transactions/{tid}").status_code == 200
        assert client.get("/api/transactions").get_json()["total"] == 0


class TestPlanApi:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def test_plan_endpoint_shape(self, client):
        body = client.get("/api/plan").get_json()
        assert "state" in body and "status" in body and "banks" in body

    def test_there_is_nowhere_left_to_type_a_daily_number(self, client):
        """It is derived from the Plan tab, so the setter is gone rather than
        deprecated: two ways to decide one figure is how they drift apart."""
        assert client.put("/api/plan", json={"monthly_amount": 600}).status_code == 405

    def test_banks_round_trip_and_cover(self, client):
        bank_id = client.post("/api/piggy", json={
            "name": "Fun", "target": 1200, "cadence": "annual", "opening": 100,
        }).get_json()["id"]
        r = client.post(f"/api/piggy/{bank_id}/cover",
                        json={"amount": 50, "month": "2025-01"})
        assert r.status_code == 200

        bank = client.get("/api/plan").get_json()["banks"][0]
        # The year's $1,200 is available from day one, so $50 out leaves
        # $1,150 to spend; what is really in it is what went in less the $50.
        assert bank["charged"] == pytest.approx(50.0)
        assert bank["balance"] == pytest.approx(1150.0)
        assert bank["available"] == pytest.approx(1150.0)
        assert bank["held"] == pytest.approx(bank["accrued"] - 50.0)

    def test_covering_more_than_the_bank_holds_is_refused(self, client):
        bank_id = client.post("/api/piggy", json={
            "name": "Fun", "target": 120, "cadence": "annual", "opening": 10,
        }).get_json()["id"]
        r = client.post(f"/api/piggy/{bank_id}/cover", json={"amount": 500})
        assert r.status_code == 400
        assert "only has" in r.get_json()["error"]

    def test_simulate_needs_a_positive_amount(self, client):
        assert client.post("/api/plan/simulate", json={"amount": 0}).status_code == 400

    def test_projections_respond(self, client):
        assert client.get("/api/projections").status_code == 200


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
