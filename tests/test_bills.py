"""Bills the plan already set aside are shown apart from everyday spending."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import bill_categories, bills_paid
from finance.money_plan import FixedCost
from finance.models import Transaction

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"
START = TODAY.replace(day=1)


def prev_month(n=1):
    d = START
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "bills.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 7000, "savings": 500})
        yield c


def add(c, when, description, amount, category):
    r = c.post("/api/transactions", json={"date": when, "description": description,
                                          "amount": amount, "category": category,
                                          "confirm": True})
    assert r.status_code == 200, r.get_json()


def october(c, mortgage=2400):
    add(c, START.isoformat(), "MORTGAGE PMT", mortgage, "Rent & Housing")
    add(c, START.isoformat(), "LOBLAWS", 900, "Groceries")
    add(c, TODAY.isoformat(), "RESTAURANT", 500, "Dining")
    for n in (1, 2):
        m = prev_month(n).isoformat()
        add(c, m, f"MORTGAGE PMT {n}", 2400, "Rent & Housing")
        add(c, m, f"LOBLAWS {n}", 1000, "Groceries")


class TestMonth:
    def test_the_headline_is_everyday_spending(self, client):
        client.post("/api/plan/fixed", json={"name": "Mortgage", "amount": 2400,
                                             "category": "Rent & Housing"})
        october(client)
        body = client.get(f"/api/breakdown?month={MONTH}").get_json()
        assert body["pace"]["total"] == pytest.approx(1400)
        # The months it's compared with leave the mortgage out too.
        assert body["pace"]["average_total"] == pytest.approx(1000)
        assert body["bills"]["paid"] == 2400 and body["bills"]["planned"] == 2400
        assert body["bills"]["items"][0]["name"] == "Mortgage"
        # The categories still have everything.
        assert any(c["category"] == "Rent & Housing" for c in body["categories"])

    def test_no_fixed_costs_no_change(self, client):
        october(client)
        body = client.get(f"/api/breakdown?month={MONTH}").get_json()
        assert body["bills"] is None
        assert body["pace"]["total"] == pytest.approx(3800)

    def test_allowance_splits_its_total(self, client):
        client.post("/api/plan/fixed", json={"name": "Mortgage", "amount": 2400,
                                             "category": "Rent & Housing"})
        october(client)
        body = client.get(f"/api/plan?month={MONTH}").get_json()
        assert body["spent_in_total"] == pytest.approx(3800)
        assert body["bills_in_total"] == pytest.approx(2400)


class TestTheSum:
    def test_paid_twice_shows_twice(self):
        rows = [Transaction(date=f"{MONTH}-01", description=f"MTG {i}", amount=2400,
                            account_id="a", category="Rent & Housing") for i in (1, 2)]
        out = bills_paid(rows, MONTH, [FixedCost(1, "Mortgage", 2400, "Rent & Housing")])
        assert out["paid"] == 4800 and out["planned"] == 2400

    def test_two_bills_in_one_category_are_one_line(self):
        fixed = [FixedCost(1, "Mortgage", 2400, "Rent & Housing"),
                 FixedCost(2, "Property tax", 300, "Rent & Housing")]
        out = bills_paid([], MONTH, fixed)
        assert len(out["items"]) == 1 and out["items"][0]["name"] == "Rent & Housing"
        assert out["planned"] == 2700

    def test_an_uncategorised_fixed_cost_takes_nothing_with_it(self):
        assert bill_categories([FixedCost(1, "Gym", 50, "Other")]) == set()
