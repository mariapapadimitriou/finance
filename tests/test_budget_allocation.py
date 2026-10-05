"""You split the monthly total yourself.

The plan works out one figure — what is left after pay, commitments, saving
and piggy banks. You pick the categories to focus on, give each a target, and
everything together has to add up to that figure. The rest are 0 unless you
give them something. The weekly allowance is the discretionary part of it.
"""

from __future__ import annotations

import pytest

TOL = 0.011


@pytest.fixture()
def ledger(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "alloc.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        c.post("/api/plan/fixed", json={"name": "Rent", "amount": 2100,
                                        "category": "Rent & Housing"})
        yield c


def budgets(c):
    return c.get("/api/budgets").get_json()


def allocate(c, focus, amounts):
    return c.put("/api/budgets/allocation", json={"focus": focus, "budgets": amounts})


def test_the_monthly_total_is_what_the_plan_leaves(ledger):
    setup = ledger.get("/api/plan/setup").get_json()
    body = budgets(ledger)
    assert body["monthly_total"] == setup["leftover"] == 2200
    assert body["focus"] is None


def test_every_row_has_its_average_and_median_month(ledger):
    for r in budgets(ledger)["rows"]:
        assert r["average"] >= 0 and r["median"] >= 0
    dining = next(r for r in budgets(ledger)["rows"] if r["category"] == "Dining")
    assert dining["average"] > 0


def test_a_split_that_adds_up_is_saved(ledger):
    r = allocate(ledger, ["Dining", "Groceries"],
                 {"Dining": 400, "Groceries": 600, "Shopping": 1200})
    assert r.status_code == 200, r.get_json()
    body = budgets(ledger)
    assert body["focus"] == ["Dining", "Groceries"]
    assert body["budgets"] == {"Dining": 400, "Groceries": 600, "Shopping": 1200}
    assert body["allocated"] == 2200
    assert body["drift"] is None
    rows = {r["category"]: r for r in body["rows"]}
    assert rows["Dining"]["focus"] and not rows["Shopping"]["focus"]
    assert body["other"]["budget"] == 1200
    # A line given nothing is $0, not whatever the plan's own split said.
    assert all(r["budget"] == 0 for r in body["rows"]
               if r["category"] not in body["budgets"])


def test_the_rest_default_to_zero(ledger):
    allocate(ledger, ["Dining"], {"Dining": 1000, "Coffee": 1200})
    allocate(ledger, ["Dining"], {"Dining": 2200})
    assert budgets(ledger)["budgets"] == {"Dining": 2200}


@pytest.mark.parametrize("amounts", [{"Dining": 2000}, {"Dining": 2300}])
def test_a_split_that_does_not_add_up_is_refused(ledger, amounts):
    r = allocate(ledger, ["Dining"], amounts)
    assert r.status_code == 400
    assert "2,200.00" in r.get_json()["error"]
    assert budgets(ledger)["focus"] is None


def test_every_focus_category_needs_a_number(ledger):
    r = allocate(ledger, ["Dining", "Coffee"], {"Dining": 2200})
    assert r.status_code == 400 and "Coffee" in r.get_json()["error"]
    assert allocate(ledger, ["Dining", "Coffee"],
                    {"Dining": 2200, "Coffee": 0}).status_code == 200


def test_focus_is_required_and_must_be_budgetable(ledger):
    assert allocate(ledger, [], {"Dining": 2200}).status_code == 400
    assert allocate(ledger, ["Income"], {"Income": 2200}).status_code == 400
    ledger.post("/api/piggy", json={"name": "Travel", "target": 1200,
                                    "cadence": "annual",
                                    "categories": ["Travel", "Lodging"]})
    total = budgets(ledger)["monthly_total"]
    assert allocate(ledger, ["Travel"], {"Travel": total}).status_code == 400


def test_the_weekly_allowance_is_the_discretionary_part(ledger):
    allocate(ledger, ["Dining", "Groceries"],
             {"Dining": 400, "Groceries": 600, "Shopping": 1200})
    plan = ledger.get("/api/plan").get_json()
    # Dining and Shopping count toward the week; Groceries is budgeted monthly.
    assert plan["state"]["monthly_amount"] == pytest.approx(1600, abs=TOL)
    d = plan["derivation"]
    assert d["discretionary"] == pytest.approx(1600, abs=TOL)
    assert d["essentials"] == pytest.approx(600, abs=TOL)
    assert d["buffer"] == pytest.approx(0, abs=TOL)


def test_a_mixed_line_counts_its_weekly_share(ledger):
    ledger.put("/api/category-groups", json={"groups": {
        "Health": "Health & care", "Personal Care": "Health & care"}})
    total = budgets(ledger)["monthly_total"]
    allocate(ledger, ["Health & care"], {"Health & care": 100, "Dining": total - 100})
    amount = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]
    assert total - 100 < amount < total


def test_when_the_plan_moves_the_split_is_reported(ledger):
    allocate(ledger, ["Dining"], {"Dining": 2200})
    ledger.put("/api/plan/setup", json={"income": 5300, "savings": 900})
    drift = budgets(ledger)["drift"]
    assert drift is not None and drift["gap"] == pytest.approx(-100, abs=TOL)


def test_the_setup_step_is_done_by_the_split(ledger):
    def step():
        return next(s for s in ledger.get("/api/setup").get_json()["steps"]
                    if s["id"] == "budgets")
    assert not step()["done"]
    allocate(ledger, ["Dining"], {"Dining": 2200})
    assert step()["done"]


def test_without_a_plan_there_is_nothing_to_split(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "empty.db"))
    app.config.update(TESTING=True)
    c = app.test_client()
    c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
    r = allocate(c, ["Dining"], {"Dining": 100})
    assert r.status_code == 400 and "plan" in r.get_json()["error"]
