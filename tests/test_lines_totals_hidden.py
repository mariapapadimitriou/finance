"""The month's whole spend, and hidden insights. (Lodging joining Travel
went with budget lines, C1.)"""

from __future__ import annotations

from datetime import date

import pytest
from ledger_files import add_fixed, load_bundled


@pytest.fixture()
def ledger(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "lines.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        load_bundled(c)
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        add_fixed(c, "Rent", 2100, "Rent & Housing")
        c.post("/api/plan/setup/apply")
        yield c


def store(c):
    return c.application.config["STORE"]


def bank(c, categories, name="Travel"):
    r = c.post("/api/piggy", json={"name": name, "target": 6000,
                                   "cadence": "annual", "categories": categories})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


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
