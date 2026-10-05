"""Ahead draws the plan against your current pace, not your old median month."""

from __future__ import annotations

import pytest

from finance import money_plan, projections
from finance.models import Transaction


def dining(d, amount):
    t = Transaction(date=d, description="NUTBAR", amount=amount, account_id="a")
    t.category, t.category_source = "Dining", "user"
    return t


HISTORY = [dining(f"2026-0{m}-10", 2000.0) for m in range(1, 5)]   # a $2,000 habit


def test_the_pace_is_this_months_spending_carried_to_the_end():
    rows = HISTORY + [dining("2026-05-02", 150.0), dining("2026-05-09", 150.0)]
    pace = projections.current_pace(rows, "2026-05-10")
    assert pace["basis"] == "month"
    assert pace["spent"] == 300.0
    assert pace["projected_spend"] == pytest.approx(300 / 10 * 31, abs=0.01)


def test_the_first_week_uses_the_last_30_days():
    rows = HISTORY + [dining("2026-04-20", 600.0), dining("2026-05-02", 300.0)]
    pace = projections.current_pace(rows, "2026-05-03")
    assert pace["basis"] == "30 days"
    # 2026-04-04 to 2026-05-03: $2,000 on 04-10, $600, $300.
    assert pace["projected_spend"] == pytest.approx(2900 / 30 * 31, abs=0.01)


def test_a_month_with_nothing_imported_uses_the_latest_one_as_it_finished():
    pace = projections.current_pace(HISTORY, "2026-10-05")
    assert pace["month"] == "2026-04"
    assert pace["projected_spend"] == pytest.approx(2000.0)


def test_commitments_are_left_out():
    rent = Transaction(date="2026-05-01", description="RENT", amount=1500.0,
                       account_id="a")
    rent.category, rent.category_source = "Rent & Housing", "user"
    rows = [dining("2026-05-08", 100.0), rent]
    pace = projections.current_pace(rows, "2026-05-10",
                                    exclude={"Rent & Housing"})
    assert pace["spent"] == 100.0


def test_the_pace_line_follows_this_month_not_the_median():
    """Spending $2,000 a month historically, $300 by the 10th this month."""
    rows = HISTORY + [dining("2026-05-02", 150.0), dining("2026-05-09", 150.0)]
    plan = money_plan.plan(4000.0, [], 500.0)          # $3,500 to spend
    pace = projections.current_pace(rows, "2026-05-10")
    r = projections.project(rows, 4000.0, 0.0, plan=plan, pace=pace)
    assert r["basis"]["pace_spend"] == pytest.approx(930.0, abs=0.01)
    assert r["monthly_surplus"] == pytest.approx(500 + 3500 - 930, abs=0.01)
    assert r["ahead"] == pytest.approx(r["monthly_surplus"] - 500, abs=0.01)
    assert set(r["series"][0]) == {"month", "pace", "on_plan"}
    assert r["pace_month"]["leftover"] == 3500


def test_behind_plan_is_negative():
    rows = [dining("2026-05-05", 2000.0)]
    plan = money_plan.plan(3000.0, [], 500.0)          # $2,500 to spend
    pace = projections.current_pace(rows, "2026-05-10")   # lands at $6,200
    r = projections.project(rows, 3000.0, 0.0, plan=plan, pace=pace)
    assert r["ahead"] < 0


def test_the_endpoint_reports_the_pace(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "p.db"))
    c = app.test_client()
    c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
    c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
    body = c.get("/api/projections").get_json()
    assert body["pace_month"]["projected_spend"] >= 0
    assert body["ahead"] == pytest.approx(
        body["monthly_surplus"] - body["monthly_on_plan"], abs=0.01)
