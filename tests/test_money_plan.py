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


class TestSharesComeFromHistoryAndTotalsDoNot:
    def rows(self):
        return [txn("2026-05", "Dining", 300), txn("2026-05", "Coffee", 100),
                txn("2026-06", "Dining", 300), txn("2026-06", "Coffee", 100)]

    def test_shares_are_proportions_of_one(self):
        shares = money_plan.discretionary_shares(self.rows())
        assert shares == {"Dining": 0.75, "Coffee": 0.25}

    def test_the_budget_total_is_the_leftover_not_the_history(self):
        """Spending $800 a month does not entitle you to $800 a month."""
        shares = money_plan.discretionary_shares(self.rows())
        budgets = money_plan.category_budgets(500, shares)
        assert sum(budgets.values()) == pytest.approx(500)
        assert budgets["Dining"] == 375
        assert budgets["Coffee"] == 125

    def test_a_smaller_pool_asks_for_less_in_the_same_proportions(self):
        shares = money_plan.discretionary_shares(self.rows())
        lean = money_plan.category_budgets(200, shares)
        assert lean["Dining"] / lean["Coffee"] == pytest.approx(3.0)
        assert sum(lean.values()) == pytest.approx(200)

    def test_essentials_and_transfers_are_not_in_the_split(self):
        """Rent is a commitment; a card payment is not spending at all."""
        rows = self.rows() + [txn("2026-05", "Rent & Housing", 2000),
                              txn("2026-05", "Transfers", 1500)]
        assert set(money_plan.discretionary_shares(rows)) == {"Dining", "Coffee"}

    def test_a_one_off_category_does_not_earn_a_permanent_line(self):
        rows = self.rows() + [txn("2026-05", "Pets", 4)]
        assert "Pets" not in money_plan.discretionary_shares(rows)

    def test_nothing_to_divide_yields_no_budgets(self):
        assert money_plan.category_budgets(0, {"Dining": 1.0}) == {}
        assert money_plan.category_budgets(500, {}) == {}


class TestWhatThePlanAdmits:
    def test_it_says_when_the_biggest_line_is_really_a_gap(self):
        warning = money_plan.uncategorised_warning({"Other": 0.4, "Dining": 0.6})
        assert warning and "uncategorised" in warning

    def test_a_small_other_is_not_worth_mentioning(self):
        assert money_plan.uncategorised_warning({"Other": 0.05, "Dining": 0.95}) is None

    def test_a_surplus_is_offered_as_saving_not_as_permission(self):
        """The app never pays out for spending, including here."""
        room = money_plan.headroom(2000, 1000)
        assert room["spare"] == 1000
        assert "saving" in room["note"]
        assert "spare money" not in room["note"].replace("not spare money", "")

    def test_no_headroom_when_the_plan_is_already_close(self):
        assert money_plan.headroom(1050, 1000) is None

    def test_the_comparison_shows_where_the_plan_asks_for_less(self):
        rows = money_plan.explain(500, {"Dining": 0.75, "Coffee": 0.25},
                                  {"Dining": 600.0, "Coffee": 50.0})
        dining = next(r for r in rows if r["category"] == "Dining")
        assert dining["budget"] == 375
        assert dining["typical"] == 600.0
        assert dining["change"] == -225
