"""Levels: saved and invested, as a ladder of round numbers to climb."""

from __future__ import annotations

import pytest

from finance import levels

TODAY = "2026-10-05"


class TestTheLadder:
    @pytest.mark.parametrize("balance,name,earned", [
        (0, None, 0), (999, None, 0), (1000, "$1k club", 1),
        (12_000, "$10k club", 3), (100_000, "Six figures", 6),
        (2_000_000, "Millionaire", 9)])
    def test_the_level_for_a_balance(self, balance, name, earned):
        r = levels.compute(balance, 500, 500, TODAY)
        assert (r["level"] or {}).get("name") == name
        assert r["stars"] == {"earned": earned, "total": 9}

    def test_the_next_level_lands_sooner_at_a_faster_pace(self):
        r = levels.compute(12_000, 500, 800, TODAY)
        nxt = r["next"]
        assert nxt["name"] == "$25k club" and nxt["left"] == 13_000
        assert nxt["pace_months"] < nxt["plan_months"]
        assert nxt["plan_eta"] > nxt["pace_eta"]

    def test_the_top_has_no_next_level(self):
        assert levels.compute(1_500_000, 0, 0, TODAY)["next"] is None

    def test_nothing_going_in_never_climbs(self):
        r = levels.compute(0, 0, 0, TODAY)
        assert r["next"]["plan_months"] is None and r["next"]["plan_eta"] is None
        growth = next(m for m in r["milestones"] if m["id"] == "growth")
        assert not growth["done"] and growth["eta"] is None


class TestMilestones:
    def test_growth_beats_deposits(self):
        # 5% a year on $120k is $500 a month: exactly what goes in.
        assert levels.growth_month(120_000, 500) == 0
        n = levels.growth_month(10_000, 500)
        assert n is not None and n > 0
        r = levels.compute(10_000, 500, 500, TODAY)
        growth = next(m for m in r["milestones"] if m["id"] == "growth")
        assert not growth["done"] and growth["eta"]

    def test_coast_fire_only_when_set_up(self):
        ids = {m["id"] for m in levels.compute(5000, 500, 500, TODAY)["milestones"]}
        assert "coast" not in ids
        coast = {"coasting": False, "coast_month": "2040-01"}
        r = levels.compute(5000, 500, 500, TODAY, coast)
        m = next(m for m in r["milestones"] if m["id"] == "coast")
        assert m == {"id": "coast", "label": "Coast FIRE", "done": False,
                     "eta": "2040-01"}


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "lv.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


class TestTheEndpoint:
    def test_a_balance_sets_the_level(self, client):
        r = client.put("/api/invested", json={"balance": 12_000})
        assert r.status_code == 200 and r.get_json()["source"] == "saved"
        body = client.get("/api/projections").get_json()
        assert body["levels"]["level"]["name"] == "$10k club"
        assert body["invested"]["opening"] == 12_000

    def test_goals_come_out_before_investing(self, client):
        client.post("/api/goals", json={"name": "Japan", "target": 4000,
                                        "monthly": 300})
        body = client.get("/api/projections").get_json()
        assert body["investing_monthly"] == 600
        assert body["levels"]["monthly_plan"] == 600
        assert body["invested"]["monthly"] == 600

    def test_the_retirement_figure_stands_in_until_one_is_typed(self, client):
        assert client.put("/api/coastfire", json={
            "age": 31, "retire_age": 65, "invested": 30_000,
            "spending": 50_000}).status_code == 200
        body = client.get("/api/projections").get_json()
        assert body["invested_balance"]["source"] == "retirement"
        assert body["levels"]["level"]["name"] == "$25k club"
        assert any(m["id"] == "coast" for m in body["levels"]["milestones"])

    @pytest.mark.parametrize("balance", [-1, "lots", None])
    def test_a_bad_balance_is_refused(self, client, balance):
        assert client.put("/api/invested", json={"balance": balance}).status_code == 400
