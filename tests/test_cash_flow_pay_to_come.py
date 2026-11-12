"""T-01r3 (TEST-05, Figma section 20 1266:27822): before this month's pay
has come in, Cash flow's summary shows "Spent so far", "Pay expected <day>"
and "Pay to come $X" instead of a red Over. The figures are the Allowance's
(THL-127): what it still expects this month, and the next payday.
"""

from __future__ import annotations

import os
import sys
from datetime import date, timedelta

import pytest

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path[:0] = [os.path.join(os.path.dirname(HERE), "ios", "tools")]


@pytest.fixture()
def client(tmp_path, monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    import run_journeys
    db = str(tmp_path / "demo.db")
    run_journeys.seed(db)
    from app import create_app
    app = create_app(db)
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def income_row(c):
    sts = c.get("/api/home").get_json()["safe_to_spend"]
    return sts, next(r for r in sts["rows"] if r["key"] == "income")


def test_pay_to_come_is_what_the_allowance_still_expects(client):
    month = date.today().strftime("%Y-%m")
    totals = client.get(f"/api/transactions/list?month={month}").get_json()["month_totals"]
    sts, income = income_row(client)
    waiting = [ln for ln in income["lines"] if not ln.get("arrived")]
    expected = round(sum(ln["amount"] for ln in waiting), 2)
    if expected < 0.5:
        assert "pay" not in totals, "Once the pay is in, T-01r comes back"
        return
    assert totals["pay"]["to_come"] == pytest.approx(expected)
    days = sorted(ln["date"] for ln in waiting if ln.get("date"))
    assert totals["pay"]["expected"] in (days[0] if days else None, sts.get("next_pay"))


def test_a_past_month_has_no_pay_to_come(client):
    last = (date.today().replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    totals = client.get(f"/api/transactions/list?month={last}").get_json()["month_totals"]
    assert "pay" not in totals
