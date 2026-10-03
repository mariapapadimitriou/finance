"""The insights written in advance, and the endpoint that serves them.

These replaced a paid bot. The thing that makes them worth having over one is
that they are deterministic and cannot quote a figure the rest of the app
disagrees with, so that is mostly what is tested here.
"""

from __future__ import annotations

import pytest

from finance.insights.profile import Profile, observe


def ids(rows):
    return {r["id"] for r in rows}


def find(rows, id_):
    return next((r for r in rows if r["id"] == id_), None)


class TestNothingIsSaidWithoutCause:
    def test_an_empty_profile_only_asks_for_a_plan(self):
        rows = observe(Profile())
        assert "no_plan" in ids(rows)
        # Nothing that needs income is allowed to fire without it.
        assert not {"heavy_commitments", "saving_little", "too_tight"} & ids(rows)

    def test_a_healthy_plan_says_little_and_nothing_alarming(self):
        p = Profile(income=5000.0, fixed_total=1500.0, savings=1000.0,
                    leftover=2500.0, daily=82.0, months_of_history=12,
                    budgets_set=6, shares={"Dining": 0.3, "Coffee": 0.2,
                                           "Shopping": 0.25, "Other": 0.25})
        rows = observe(p)
        assert "no_plan" not in ids(rows)
        assert "heavy_commitments" not in ids(rows)
        assert not [r for r in rows if r["severity"] == "act"]


class TestEachRuleFiresOnItsOwnCondition:
    def test_heavy_commitments(self):
        p = Profile(income=4000.0, fixed_total=2400.0, savings=200.0,
                    leftover=1400.0, daily=46.0, months_of_history=6)
        row = find(observe(p), "heavy_commitments")
        assert row and row["metric"] == "65%"
        assert row["figures"]["committed"] == 2600.0

    def test_commitments_past_seventy_percent_escalate_to_act(self):
        p = Profile(income=4000.0, fixed_total=3000.0, savings=200.0,
                    leftover=800.0, daily=26.0, months_of_history=6)
        assert find(observe(p), "heavy_commitments")["severity"] == "act"

    def test_saving_nothing_only_when_there_is_something_to_save(self):
        has_room = Profile(income=4000.0, fixed_total=1500.0, savings=0.0,
                           leftover=2500.0, daily=82.0, months_of_history=6)
        assert find(observe(has_room), "saving_nothing")

        no_room = Profile(income=4000.0, fixed_total=4200.0, savings=0.0,
                          leftover=-200.0, months_of_history=6)
        assert find(observe(no_room), "saving_nothing") is None

    def test_saving_little_and_saving_well_are_mutually_exclusive(self):
        little = Profile(income=4000.0, fixed_total=1500.0, savings=200.0,
                         leftover=2300.0, daily=75.0, months_of_history=6)
        assert find(observe(little), "saving_little")
        assert find(observe(little), "saving_well") is None

        well = Profile(income=4000.0, fixed_total=1500.0, savings=1000.0,
                       leftover=1500.0, daily=49.0, months_of_history=6)
        assert find(observe(well), "saving_well")
        assert find(observe(well), "saving_little") is None

    def test_a_daily_number_nobody_could_keep_to(self):
        p = Profile(income=4000.0, fixed_total=2000.0, savings=1800.0,
                    leftover=200.0, daily=6.5, months_of_history=6)
        row = find(observe(p), "too_tight")
        assert row and row["severity"] == "act" and row["tab"] == "plan"

    def test_spending_over_the_plan(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=6,
                    last_month="2026-08", last_month_discretionary=1800.0,
                    discretionary_budget=1200.0, budgets_set=5)
        row = find(observe(p), "over_the_plan")
        assert row and row["figures"]["over"] == 600.0
        assert "August" in row["detail"]

    def test_a_small_overrun_is_not_a_story(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=6,
                    last_month="2026-08", last_month_discretionary=1250.0,
                    discretionary_budget=1200.0, budgets_set=5)
        assert find(observe(p), "over_the_plan") is None

    def test_a_good_month_is_said_out_loud(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=6,
                    last_month="2026-08", last_month_discretionary=700.0,
                    discretionary_budget=1200.0, budgets_set=5)
        row = find(observe(p), "under_the_plan")
        assert row and row["severity"] == "good"

    def test_budgets_not_adopted(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=6,
                    budgets_set=0)
        assert find(observe(p), "budgets_not_adopted")

    def test_travel_with_no_bank_behind_it(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=12,
                    budgets_set=5, travel_last_year=3600.0)
        row = find(observe(p), "travel_no_bank")
        assert row and row["figures"]["monthly"] == 300.0
        assert row["tab"] == "piggy"

    def _plan(self, **kw):
        return Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                       leftover=2000.0, daily=65.0, months_of_history=12,
                       budgets_set=5, **kw)

    def test_travel_paid_for_by_a_bank_says_nothing(self):
        p = self._plan(travel_last_year=3600.0,
                       banks=[{"id": 1, "name": "Trip", "monthly": 300.0,
                               "available": 3600.0, "target": 3600.0,
                               "categories": ["Lodging", "Travel"]}])
        assert find(observe(p), "travel_no_bank") is None

    def test_a_bank_that_does_not_pay_for_travel_does_not_count(self):
        """A wedding fund keeps nothing off the week when a flight lands."""
        p = self._plan(travel_last_year=3600.0,
                       banks=[{"id": 1, "name": "Wedding", "monthly": 300.0,
                               "available": 3600.0, "target": 3600.0,
                               "categories": []}])
        assert find(observe(p), "travel_no_bank")

    def test_a_bank_over_this_year_is_reported_per_bank(self):
        """Not an error — it is the mechanism working — but it decides next
        year's contribution, so it is worth saying."""
        p = self._plan(banks=[{"id": 7, "name": "Trip", "monthly": 300.0,
                               "target": 3600.0, "spent_this_year": 3900.0,
                               "available": -300.0, "over": True,
                               "behind_by": 300.0, "basis": "first_year"}])
        row = find(observe(p), "bank_behind_7")
        assert row and row["severity"] == "watch"
        assert "Trip" in row["title"] and "$300" in row["title"]
        assert "$3,900" in row["detail"] and "$3,600" in row["detail"]

    def test_a_bank_repaying_last_year_says_why_the_week_is_tighter(self):
        p = self._plan(banks=[{"id": 7, "name": "Trip", "monthly": 325.0,
                               "target": 3600.0, "spent_last_year": 3900.0,
                               "available": 3600.0, "over": False,
                               "basis": "repaying", "cadence": "annual"}])
        row = find(observe(p), "bank_repaying_7")
        assert row and "$325" in row["detail"] and "$300" in row["detail"]

    def test_repaying_a_normal_year_is_not_news(self):
        p = self._plan(banks=[{"id": 7, "name": "Trip", "monthly": 250.0,
                               "target": 3600.0, "spent_last_year": 3000.0,
                               "available": 3600.0, "over": False,
                               "basis": "repaying", "cadence": "annual"}])
        assert not [r for r in observe(p) if r["id"].startswith("bank_")]

    def test_a_new_bank_is_not_called_fully_funded(self):
        """It can pay its whole target on day one; that money is advanced,
        not saved."""
        p = self._plan(banks=[{"id": 7, "name": "Trip", "monthly": 300.0,
                               "target": 3600.0, "available": 3600.0,
                               "held": 300.0, "over": False}])
        assert find(observe(p), "bank_ready_7") is None
        p.banks[0]["held"] = 3600.0
        assert find(observe(p), "bank_ready_7")

    def test_thin_history(self):
        row = find(observe(Profile(months_of_history=1)), "thin_history")
        assert row and "1 month" in row["title"]

    def test_subscriptions_as_a_share_of_what_is_spendable(self):
        p = Profile(income=4000.0, fixed_total=1500.0, savings=500.0,
                    leftover=2000.0, daily=65.0, months_of_history=12,
                    budgets_set=5, discretionary_budget=1000.0,
                    subscriptions_monthly=250.0)
        row = find(observe(p), "heavy_subscriptions")
        assert row and row["metric"] == "25%"


class TestOrdering:
    def test_what_needs_doing_comes_before_what_is_going_well(self):
        p = Profile(income=4000.0, fixed_total=2400.0, savings=1000.0,
                    leftover=600.0, daily=6.0, months_of_history=12,
                    budgets_set=0)
        severities = [r["severity"] for r in observe(p)]
        assert severities == sorted(
            severities, key=lambda s: {"act": 0, "watch": 1, "good": 2}[s])

    def test_a_dismissed_observation_is_withheld(self):
        p = Profile(months_of_history=0)
        assert "no_plan" in ids(observe(p))
        assert "no_plan" not in ids(observe(p, dismissed={"no_plan"}))


class TestEveryObservationIsActionable:
    """An insight you cannot do anything with is just a mood."""

    def test_anything_needing_action_names_a_tab_to_do_it_on(self):
        profiles = [
            Profile(),
            Profile(income=4000.0, fixed_total=3000.0, savings=200.0,
                    leftover=800.0, daily=6.0, months_of_history=1,
                    budgets_set=0, uncategorised_share=0.4,
                    last_month="2026-08", last_month_discretionary=2000.0,
                    discretionary_budget=500.0),
        ]
        for p in profiles:
            for row in observe(p):
                if row["severity"] != "act":
                    continue
                assert row["tab"], f"{row['id']} has nothing to act on"
                assert row["action"], f"{row['id']} has no action label"


class TestTheEndpoint:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def test_insights_carries_observations(self, client):
        body = client.get("/api/insights").get_json()
        assert "observations" in body
        assert "no_plan" in ids(body["observations"])

    def test_setting_up_a_plan_changes_what_is_said(self, client):
        client.put("/api/plan/setup", json={"income": 5000, "savings": 800})
        rows = client.get("/api/insights").get_json()["observations"]
        assert "no_plan" not in ids(rows)

    def test_an_observation_never_contradicts_the_tab_it_points_at(self, client):
        """The figures come from the same functions the tabs use."""
        client.put("/api/plan/setup", json={"income": 5000, "savings": 100})
        rows = client.get("/api/insights").get_json()["observations"]
        setup = client.get("/api/plan/setup").get_json()

        row = find(rows, "saving_little")
        assert row
        assert row["figures"]["savings"] == setup["savings"]
