"""One sentence about yesterday, or silence.

The useful moment for a budgeting app is the morning after: you spent too
much yesterday, nobody has told you, and today starts exactly like yesterday
did. The rules below exist because a nudge that gets ignored is worse than
no nudge at all.
"""

from __future__ import annotations

from datetime import date

import pytest

from finance import nudge
from finance.models import Transaction
from finance.spend_plan import compute


def dining(day, amount):
    return Transaction(date=day, description="X", amount=amount, account_id="a",
                       account_name="a", source="csv", category="Dining")


def state_for(rows, today, budget=900.0):
    return compute(rows, budget, f"{today.year:04d}-{today.month:02d}", today=today)


class TestWhenItSpeaks:
    def test_a_day_well_over_the_share_is_reported(self):
        rows = [dining("2026-10-01", 30), dining("2026-10-02", 200)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        assert n["kind"] == "over"
        assert "$200" in n["headline"]

    def test_it_says_what_today_now_costs(self):
        """A report without a consequence is just a telling-off."""
        rows = [dining("2026-10-01", 30), dining("2026-10-02", 200)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        assert "a day for the rest of the month" in n["detail"]

    def test_a_day_well_under_is_also_worth_saying(self):
        rows = [dining("2026-10-01", 30), dining("2026-10-02", 2)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        assert n["kind"] == "under"
        assert "carries forward" in n["detail"]


class TestWhenItStaysQuiet:
    def test_an_ordinary_day_produces_nothing(self):
        """A banner that appears daily stops being read by Friday."""
        rows = [dining("2026-10-01", 30), dining("2026-10-02", 29)]
        today = date(2026, 10, 3)
        assert nudge.for_yesterday(rows, state_for(rows, today), today) is None

    def test_a_few_dollars_over_is_not_a_story(self):
        rows = [dining("2026-10-02", 32)]
        today = date(2026, 10, 3)
        assert nudge.for_yesterday(rows, state_for(rows, today), today) is None

    def test_a_day_with_no_data_is_not_a_day_with_no_spending(self):
        """Guessing which would make it untrustworthy on its first wrong day."""
        rows = [dining("2026-10-01", 30)]
        today = date(2026, 10, 3)
        assert nudge.for_yesterday(rows, state_for(rows, today), today) is None

    def test_it_says_nothing_on_the_first_of_the_month(self):
        """Yesterday belongs to a month that has already been settled."""
        rows = [dining("2026-09-30", 400)]
        today = date(2026, 10, 1)
        assert nudge.for_yesterday(rows, state_for(rows, today), today) is None

    def test_it_does_not_speak_about_a_month_it_has_no_plan_for(self):
        rows = [dining("2026-10-02", 200)]
        today = date(2026, 10, 3)
        stale = compute(rows, 900.0, "2026-09", today=today)
        assert nudge.for_yesterday(rows, stale, today) is None

    def test_no_budget_means_no_opinion(self):
        rows = [dining("2026-10-02", 200)]
        today = date(2026, 10, 3)
        assert nudge.for_yesterday(rows, state_for(rows, today, 0.0), today) is None


class TestWhatItWillNotDo:
    def test_it_never_suggests_spending_the_surplus(self):
        """Nothing in this app pays out for buying something."""
        rows = [dining("2026-10-01", 1), dining("2026-10-02", 1)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        text = f"{n['headline']} {n['detail']}".lower()
        for word in ("treat", "reward", "deserve", "go ahead", "enjoy"):
            assert word not in text

    def test_it_reports_the_day_rather_than_judging_the_person(self):
        rows = [dining("2026-10-01", 30), dining("2026-10-02", 400)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        text = f"{n['headline']} {n['detail']}".lower()
        for word in ("should", "bad", "failed", "discipline", "splurge"):
            assert word not in text

    def test_a_month_already_past_its_budget_is_told_plainly(self):
        rows = [dining("2026-10-01", 500), dining("2026-10-02", 600)]
        today = date(2026, 10, 3)
        n = nudge.for_yesterday(rows, state_for(rows, today), today)
        assert "past its budget" in n["detail"]
