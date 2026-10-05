"""Lodging joining Travel, the month's whole spend, and hidden insights."""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture()
def ledger(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "lines.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        c.post("/api/plan/fixed", json={"name": "Rent", "amount": 2100,
                                        "category": "Rent & Housing"})
        c.post("/api/plan/setup/apply")
        yield c


def store(c):
    return c.application.config["STORE"]


def bank(c, categories, name="Travel"):
    r = c.post("/api/piggy", json={"name": name, "target": 6000,
                                   "cadence": "annual", "categories": categories})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


class TestLodgingJoinsTravel:
    """Putting Lodging under Travel says the hotel is part of the trip, so the
    bank paying for the trip pays for the hotel too."""

    def test_the_bank_takes_lodging_on(self, ledger):
        bank_id = bank(ledger, ["Travel"])
        ledger.put("/api/budgets", json={"budgets": {"Lodging": 120}})
        r = ledger.put("/api/category-groups", json={"groups": {"Lodging": "Travel"}})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["adopted"] == {"Lodging": "Travel"}
        assert store(ledger).bank_categories()[bank_id] == ["Lodging", "Travel"]
        assert store(ledger).category_groups() == {"Lodging": "Travel"}
        assert "Lodging" not in store(ledger).budgets()

    def test_already_paid_for_is_just_grouped(self, ledger):
        bank_id = bank(ledger, ["Travel", "Lodging"])
        r = ledger.put("/api/category-groups", json={"groups": {"Lodging": "Travel"}})
        assert r.status_code == 200
        assert r.get_json()["adopted"] == {}
        assert store(ledger).bank_categories()[bank_id] == ["Lodging", "Travel"]

    def test_a_named_line_a_bank_pays_for_takes_newcomers(self, ledger):
        bank_id = bank(ledger, ["Travel"])
        r = ledger.put("/api/category-groups",
                       json={"groups": {"Travel": "Trips", "Lodging": "Trips"}})
        assert r.status_code == 200, r.get_json()
        assert store(ledger).bank_categories()[bank_id] == ["Lodging", "Travel"]

    def test_bank_paid_into_a_budgeted_line_is_still_refused(self, ledger):
        bank_id = bank(ledger, ["Travel"])
        r = ledger.put("/api/category-groups", json={"groups": {"Travel": "Dining"}})
        assert r.status_code == 400
        assert store(ledger).bank_categories()[bank_id] == ["Travel"]
        assert store(ledger).category_groups() == {}

    def test_without_banks_it_is_only_a_grouping(self, ledger):
        r = ledger.put("/api/category-groups", json={"groups": {"Lodging": "Travel"}})
        assert r.status_code == 200
        assert r.get_json()["adopted"] == {}
        assert store(ledger).bank_funded_categories() == set()


class TestSpentInTotal:
    def test_counts_rent_and_what_a_bank_paid(self, ledger):
        today = date.today()
        month = today.strftime("%Y-%m")
        bank(ledger, ["Travel"])
        before = ledger.get(f"/api/plan?month={month}").get_json()
        for body in ({"description": "AIR CANADA 4410", "amount": 900.0,
                      "category": "Travel"},
                     {"description": "LANDLORD RENT", "amount": 2100.0,
                      "category": "Rent & Housing"}):
            r = ledger.post("/api/transactions", json={
                "date": today.isoformat(), "confirm": True, **body})
            assert r.status_code == 200, r.get_json()
        after = ledger.get(f"/api/plan?month={month}").get_json()
        assert after["spent_in_total"] == pytest.approx(
            before["spent_in_total"] + 3000.0, abs=0.01)
        assert after["from_banks"] == pytest.approx(
            before["from_banks"] + 900.0, abs=0.01)

    def test_transfers_are_not_spending(self, ledger):
        today = date.today()
        month = today.strftime("%Y-%m")
        before = ledger.get(f"/api/plan?month={month}").get_json()["spent_in_total"]
        ledger.post("/api/transactions", json={
            "date": today.isoformat(), "description": "PAYMENT THANK YOU",
            "amount": 500.0, "category": "Transfer", "confirm": True})
        after = ledger.get(f"/api/plan?month={month}").get_json()["spent_in_total"]
        assert after == pytest.approx(before, abs=0.01)


class TestHiddenInsightsComeBackByName:
    def test_a_dismissed_one_is_listed_with_its_title(self, ledger):
        body = ledger.get("/api/insights").get_json()
        shown = body["findings"] + body["observations"]
        assert shown, "the fixture produces no insights, so this proves nothing"
        assert body["hidden"] == []
        first = shown[0]
        ledger.post(f"/api/insights/{first['id']}/dismiss")
        body = ledger.get("/api/insights").get_json()
        assert {"id": first["id"], "title": first["title"]} in body["hidden"]
        ledger.delete(f"/api/insights/{first['id']}/dismiss")
        assert ledger.get("/api/insights").get_json()["hidden"] == []
