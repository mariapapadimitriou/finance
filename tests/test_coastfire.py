"""CoastFIRE: when saving for retirement could stop."""

import pytest

from finance import coastfire as c

TODAY = "2026-10"


def inputs(**kw):
    body = {"age": 32, "retire_age": 65, "invested": 80_000, "spending": 60_000,
            "monthly": 1100, **kw}
    got, error = c.validate(body, TODAY)
    assert error is None, error
    return got


class TestTheNumbers:
    def test_the_fire_number_is_spending_over_the_withdrawal_rate(self):
        assert c.fire_number(60_000, 0, 4) == pytest.approx(1_500_000)

    def test_a_pension_lowers_what_the_portfolio_must_cover(self):
        assert c.fire_number(60_000, 20_000, 4) == pytest.approx(1_000_000)
        r = c.compute(inputs(pension=20_000), TODAY)
        assert r["from_portfolio"] == 40_000 and r["fire_number"] == 1_000_000

    def test_the_coast_number_is_the_fire_number_discounted(self):
        r = c.compute(inputs(), TODAY)
        assert r["coast_number"] == pytest.approx(1_500_000 / 1.05 ** 33, rel=1e-6)

    def test_a_higher_return_needs_less_now(self):
        coast = [row["coast_number"] for row in c.compute(inputs(), TODAY)["rates"]]
        assert coast == sorted(coast, reverse=True)


class TestTheCoastAge:
    def test_enough_invested_is_coasting_already(self):
        r = c.compute(inputs(invested=400_000, monthly=0), TODAY)
        assert r["coasting"] and r["coast_age"] == 32 and r["gap"] == 0
        # Left alone it overshoots, so retirement could come early.
        assert r["untouched_at_retirement"] > r["fire_number"]
        assert 32 < r["early_retire_age"] < 65

    def test_it_is_the_first_month_the_portfolio_catches_up(self):
        t = inputs(real_return=7)
        r = c.compute(t, TODAY)
        months = round((r["coast_age"] - 32) * 12)
        m = 1.07 ** (1 / 12) - 1
        n = r["months_to_retire"]

        def value(k):
            v = t.invested
            for _ in range(k):
                v = v * (1 + m) + t.monthly
            return v

        assert value(months) >= r["fire_number"] / (1 + m) ** (n - months) - 0.01
        assert value(months - 1) < r["fire_number"] / (1 + m) ** (n - months + 1)

    def test_saving_more_gets_there_sooner(self):
        slow = c.compute(inputs(real_return=7, monthly=1000), TODAY)["coast_age"]
        assert slow is not None
        fast = c.compute(inputs(real_return=7, monthly=2000), TODAY)["coast_age"]
        assert fast < slow

    def test_without_contributions_a_gap_never_closes(self):
        """Both the portfolio and the target grow at the same rate, so only
        contributions can close the distance."""
        r = c.compute(inputs(invested=10_000, monthly=0), TODAY)
        assert r["coast_age"] is None and not r["coasting"]

    def test_the_chart_crosses_at_the_coast_age(self):
        r = c.compute(inputs(real_return=7), TODAY)
        crossed = next(p for p in r["series"] if p["invested"] >= p["needed"])
        assert crossed["age"] - r["coast_age"] < 1
        assert r["series"][-1]["needed"] == pytest.approx(r["fire_number"])

    def test_the_full_fire_age_is_when_the_number_is_reached(self):
        r = c.compute(inputs(), TODAY)
        assert r["fire_age"] == pytest.approx(65.25)
        assert r["at_retirement"] < r["fire_number"]

    def test_what_it_would_take_arrives_exactly_on_time(self):
        base = inputs()
        need = c.compute(base, TODAY)["needed_monthly"]
        coast_by = c.compute(inputs(monthly=need["to_coast"]), TODAY)
        assert coast_by["coast_age"] == pytest.approx(42)
        fire_by = c.compute(inputs(monthly=need["to_fire_by_retirement"]), TODAY)
        assert fire_by["fire_age"] == pytest.approx(65)


class TestAgeMovesOn:
    def test_the_age_is_worked_out_from_when_it_was_typed(self):
        t = inputs()
        assert t.born == "1994-10"
        assert c.compute(t, "2030-10")["age"] == 36
        assert c.compute(t, "2030-09")["age"] == 35


class TestValidation:
    @pytest.mark.parametrize("bad", [
        {"age": 10}, {"age": 95}, {"retire_age": 30}, {"retire_age": 120},
        {"invested": -1}, {"spending": 0}, {"pension": 60_000},
        {"withdrawal": 1}, {"withdrawal": 12}, {"real_return": 20},
        {"monthly": -5}, {"age": "old"},
    ])
    def test_nonsense_is_refused(self, bad):
        body = {"age": 32, "retire_age": 65, "invested": 80_000,
                "spending": 60_000, "monthly": 1100, **bad}
        got, error = c.validate(body, TODAY)
        assert got is None and error


# ── The API ──────────────────────────────────────────────────────────────────

BODY = {"age": 32, "retire_age": 65, "invested": 80000, "spending": 60000,
        "monthly": 1100}


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "coast.db"))
    app.config.update(TESTING=True)
    with app.test_client() as cl:
        cl.put("/api/plan/setup", json={"income": 6000, "savings": 1000})
        yield cl


class TestTheEndpoints:
    def test_the_defaults_come_from_the_plan(self, client):
        body = client.get("/api/coastfire").get_json()
        assert body["saved"] is None and body["result"] is None
        assert body["defaults"]["plan_spending"] == 60_000
        assert body["defaults"]["plan_saving"] == 1000
        assert body["defaults"]["mortgage"] is None

    def test_a_preview_writes_nothing(self, client):
        r = client.post("/api/coastfire/preview", json=BODY)
        assert r.status_code == 200
        assert r.get_json()["result"]["fire_number"] == 1_500_000
        assert client.get("/api/coastfire").get_json()["saved"] is None

    def test_saving_remembers_it(self, client):
        client.put("/api/coastfire", json=BODY)
        body = client.get("/api/coastfire").get_json()
        assert body["saved"]["invested"] == 80000
        assert body["result"]["age"] == 32

    def test_it_changes_nothing_in_the_plan(self, client):
        before = client.get("/api/plan/setup").get_json()["leftover"]
        client.put("/api/coastfire", json=BODY)
        assert client.get("/api/plan/setup").get_json()["leftover"] == before

    def test_a_mortgage_that_ends_first_is_offered_to_take_out(self, client):
        client.put("/api/mortgage", json={"balance": 300000, "rate": 5,
                                          "years": 20})
        m = client.get("/api/coastfire").get_json()["defaults"]["mortgage"]
        assert m and m["yearly"] == pytest.approx(m["monthly"] * 12)

    def test_clearing_it(self, client):
        client.put("/api/coastfire", json=BODY)
        assert client.delete("/api/coastfire").status_code == 200
        assert client.get("/api/coastfire").get_json()["saved"] is None
        assert client.delete("/api/coastfire").status_code == 404

    @pytest.mark.parametrize("bad", [{"age": 5}, {"spending": -1},
                                     {"retire_age": 20}])
    def test_nonsense_is_a_400(self, client, bad):
        assert client.put("/api/coastfire", json={**BODY, **bad}).status_code == 400
        assert client.post("/api/coastfire/preview",
                           json={**BODY, **bad}).status_code == 400
