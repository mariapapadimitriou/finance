"""A budget worked out forwards from income, not backwards from last month.

The old budget was a median of past spending, which cannot ask you to spend
less: it is a description of a habit wearing a plan's clothes, and a bad year
quietly becomes the target. The total now comes from arithmetic on figures
you decide — income, commitments, savings — and history is used only to
decide how that total divides.
"""

from __future__ import annotations

import pytest

from finance import money_plan
from finance.money_plan import FixedCost
from finance.models import Transaction


def txn(month, category, amount):
    return Transaction(date=f"{month}-15", description=category, amount=amount,
                       account_id="a", account_name="a", source="csv",
                       category=category)


def fixed(*pairs):
    return [FixedCost(i, n, a) for i, (n, a) in enumerate(pairs, 1)]


class TestTheArithmetic:
    def test_what_is_left_is_income_minus_everything_decided(self):
        p = money_plan.plan(5200, fixed(("Rent", 2100), ("Hydro", 95)), 900)
        assert p["fixed_total"] == 2195
        assert p["leftover"] == 2105
        assert p["leftover_share"] == pytest.approx(0.4048, abs=1e-3)

    def test_savings_is_subtracted_not_left_over(self):
        """Money you decided to put away is not money you may spend."""
        with_saving = money_plan.plan(5000, fixed(("Rent", 2000)), 1000)
        without = money_plan.plan(5000, fixed(("Rent", 2000)), 0)
        assert without["leftover"] - with_saving["leftover"] == 1000

    def test_committing_more_than_you_earn_is_called_out(self):
        p = money_plan.plan(3000, fixed(("Rent", 2600)), 800)
        assert p["leftover"] == -400
        assert p["verdict"] == "negative"

    def test_a_very_thin_margin_is_flagged_rather_than_accepted(self):
        p = money_plan.plan(5000, fixed(("Rent", 4000)), 800)
        assert p["verdict"] == "tight"

    def test_an_unusually_large_remainder_is_also_worth_a_word(self):
        p = money_plan.plan(5000, fixed(("Rent", 500)), 0)
        assert p["verdict"] == "loose"

    def test_no_income_means_no_plan_yet(self):
        p = money_plan.plan(0, [], 0)
        assert p["verdict"] == "unset"
        assert p["complete"] is False


class TestUsualSpendingFirst:
    """Each line starts at what you usually spend; the rest is a buffer.

    Splitting the whole leftover in proportion to history handed every line
    far more than you ever spend whenever the leftover was large — a budget
    of $2,227 beside "usually $298".
    """

    MONTHS = ["2026-01", "2026-02", "2026-03", "2026-04", "2026-05"]

    def ledger(self):
        out = []
        for m, dining in zip(self.MONTHS, [100, 120, 110, 900, 105]):
            out += [txn(m, "Groceries", 400), txn(m, "Dining", dining)]
        out.append(txn("2026-02", "Gifts & Charity", 240))   # once in five months
        out.append(txn("2026-06", "Groceries", 50))         # the month under way
        return out

    def test_a_line_is_its_median_month(self):
        typical = money_plan.typical_monthly(self.ledger())
        assert typical["Groceries"] == 400
        assert typical["Dining"] == 110      # the $900 month does not set it

    def test_the_month_under_way_is_left_out(self):
        assert money_plan.typical_monthly(self.ledger())["Groceries"] == 400

    def test_an_occasional_line_is_spread_over_the_year(self):
        assert money_plan.typical_monthly(self.ledger())["Gifts & Charity"] == 48

    def test_bank_funded_categories_are_left_out(self):
        typical = money_plan.typical_monthly(self.ledger(),
                                             bank_funded={"Dining"})
        assert "Dining" not in typical

    def test_lines_follow_the_grouping(self):
        typical = money_plan.typical_monthly(
            self.ledger(), groups={"Groceries": "Food", "Dining": "Food"})
        assert typical["Food"] == 510

    def test_what_is_left_over_is_the_buffer(self):
        s = money_plan.split(self.ledger(), 1000)
        assert s["budgets"] == {"Groceries": 400, "Dining": 110,
                                "Gifts & Charity": 48}
        assert s["buffer"] == 442 and s["short"] == 0
        assert sum(s["budgets"].values()) + s["buffer"] == 1000

    def test_a_tight_plan_scales_every_line_down_to_fit(self):
        s = money_plan.split(self.ledger(), 279)
        assert s["buffer"] == 0
        assert s["short"] == pytest.approx(279, abs=0.01)
        assert round(sum(s["budgets"].values()), 2) == 279
        assert s["budgets"]["Groceries"] == pytest.approx(200, abs=0.02)

    def test_nothing_to_divide(self):
        assert money_plan.split(self.ledger(), 0)["budgets"] == {}
        assert money_plan.split([], 500) == {
            "budgets": {}, "buffer": 500, "short": 0.0, "typical": {}}

    def test_the_weekly_pool_leaves_the_buffer_out(self):
        pool = money_plan.monthly_allowance(
            3000, fixed(("Rent", 1500)), 500, 0, self.ledger())
        # Dining and Gifts are discretionary; Groceries is not; the $842
        # buffer is no one's.
        assert pool == 158
