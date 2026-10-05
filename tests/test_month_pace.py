"""This month's running total, beside a usual month's."""

from datetime import date

import pytest

from finance.analytics import by_category, month_pace
from finance.models import Transaction


def txn(day: str, amount: float, category="Dining") -> Transaction:
    return Transaction(date=day, description=f"SHOP {day} {amount}", amount=amount,
                       account_id="a", category=category)


ROWS = [
    # Three earlier months, $300, $600 and $900, all on the 10th…
    txn("2026-07-10", 300), txn("2026-08-10", 600), txn("2026-09-10", 900),
    # …one before them that is too old to count…
    txn("2026-06-05", 5000),
    # …and this month so far, plus a transfer that is not spending.
    txn("2026-10-02", 40), txn("2026-10-04", 60),
    txn("2026-10-03", 999, category="Transfers"),
]


class TestMonthPace:
    def test_the_running_total_ends_at_the_months_spend(self):
        p = month_pace(ROWS, "2026-10", today=date(2026, 10, 5))
        assert p["through"] == 5 and len(p["this"]) == 5
        assert p["this"] == [0, 40, 40, 100, 100]
        spent = sum(r["amount"] for r in by_category(ROWS, "2026-10") if r["amount"] > 0)
        assert p["total"] == pytest.approx(spent)

    def test_the_usual_month_is_the_three_before_it(self):
        p = month_pace(ROWS, "2026-10", today=date(2026, 10, 5))
        assert p["compared"] == ["2026-07", "2026-08", "2026-09"]
        assert len(p["average"]) == 31
        assert p["average"][8] == 0             # before the 10th
        assert p["average"][9] == pytest.approx(600)
        assert p["average_total"] == pytest.approx(600)

    def test_a_finished_month_runs_to_its_end(self):
        p = month_pace(ROWS, "2026-09", today=date(2026, 10, 5))
        assert p["through"] == 30 and p["total"] == 900
        assert p["compared"] == ["2026-06", "2026-07", "2026-08"]

    def test_nothing_before_it_means_no_comparison(self):
        p = month_pace(ROWS, "2026-06", today=date(2026, 10, 5))
        assert p["average"] == [] and p["average_total"] is None
