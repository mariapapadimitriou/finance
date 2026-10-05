"""The Budgets tab lists the lines from Settings → Categories.

It used to list only lines with a saved budget or a share of the plan, and
the plan drops lines under 2% of spending — so a line you had set up in
Settings could be missing from Budgets, and the rest came in a different
order. Now every line is there, in the order Settings shows.
"""

from __future__ import annotations

import pytest


@pytest.fixture()
def ledger(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "lines.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        c.post("/api/plan/setup/apply")
        yield c


def settings_lines(c):
    return c.get("/api/category-groups").get_json()["lines"]


def budgets(c):
    return c.get("/api/budgets").get_json()


def travel_bank(c):
    r = c.post("/api/piggy", json={"name": "Travel", "target": 2400,
                                   "cadence": "annual",
                                   "categories": ["Travel", "Lodging"]})
    assert r.status_code in (200, 201), r.get_json()


def test_every_line_is_on_the_page_in_settings_order(ledger):
    body = budgets(ledger)
    lines = settings_lines(ledger)
    assert [r["category"] for r in body["rows"]] == [
        l["name"] for l in lines if not l["bank_funded"]]
    assert [r["category"] for r in body["bank_lines"]] == [
        l["name"] for l in lines if l["bank_funded"]]


def test_a_grouped_line_replaces_its_categories(ledger):
    ledger.put("/api/category-groups", json={"groups": {
        "Health": "Health & care", "Personal Care": "Health & care",
        "Coffee": "Dining"}})
    body = budgets(ledger)
    names = [r["category"] for r in body["rows"]]
    assert names == [l["name"] for l in settings_lines(ledger)
                     if not l["bank_funded"]]
    assert "Health" not in names and "Personal Care" not in names
    assert "Coffee" not in names
    line = next(r for r in body["rows"] if r["category"] == "Health & care")
    assert sorted(line["members"]) == ["Health", "Personal Care"]


def test_a_line_the_plan_gives_nothing_still_has_a_row(ledger):
    body = budgets(ledger)
    unplanned = [r for r in body["rows"] if r["plan_budget"] is None]
    assert unplanned, "the bundled ledger has lines below the plan's 2% cut"
    for r in unplanned:
        assert r["adopted"] is False
        assert r["budget"] == 0
        assert r["quiet"] is (r["spent"] == 0)


def test_saving_a_budget_on_a_quiet_line_adopts_it(ledger):
    quiet = next(r for r in budgets(ledger)["rows"] if r["quiet"])
    assert ledger.put("/api/budgets", json={
        "budgets": {quiet["category"]: 25}}).status_code == 200
    row = next(r for r in budgets(ledger)["rows"]
               if r["category"] == quiet["category"])
    assert row["adopted"] is True and row["budget"] == 25 and not row["quiet"]


def test_bank_paid_lines_say_which_bank(ledger):
    travel_bank(ledger)
    body = budgets(ledger)
    assert "Travel" not in {r["category"] for r in body["rows"]}
    paid = {l["category"]: l for l in body["bank_lines"]}
    assert set(paid) == {"Travel", "Lodging"}
    assert paid["Travel"]["bank"] == "Travel"


def test_using_the_plans_split_clears_lines_it_does_not_fund(ledger):
    quiet = next(r for r in budgets(ledger)["rows"] if r["plan_budget"] is None)
    ledger.put("/api/budgets", json={"budgets": {quiet["category"]: 25}})
    assert quiet["category"] in budgets(ledger)["budgets"]
    ledger.post("/api/plan/setup/apply")
    body = budgets(ledger)
    assert quiet["category"] not in body["budgets"]
    assert set(body["budgets"]) == set(body["plan_budgets"])
