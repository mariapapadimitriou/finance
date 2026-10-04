"""The mortgage calculator: the arithmetic, and the commitment it owns."""

import pytest

from finance import mortgage as m

TODAY = "2026-10"


def terms(**kw):
    base = dict(balance=500_000, rate=5, years=25, as_of=TODAY)
    return m.Terms(**{**base, **kw})


class TestThePayment:
    def test_canadian_compounds_semi_annually(self):
        """5% compounded twice a year is an effective 5.0625%, so the payment
        is a little under what an American calculator gives."""
        assert m.effective_annual(5, "canadian") == pytest.approx(0.050625)
        assert m.payment(500_000, 5, 25, "monthly", "canadian") == pytest.approx(
            2908.03, abs=0.01)

    def test_monthly_compounding_is_the_us_figure(self):
        assert m.payment(500_000, 5, 25, "monthly", "monthly") == pytest.approx(
            2922.96, abs=0.01)
        assert (m.payment(500_000, 5, 25, "monthly", "monthly")
                > m.payment(500_000, 5, 25, "monthly", "canadian"))

    def test_accelerated_is_the_monthly_payment_halved(self):
        monthly = m.payment(500_000, 5, 25, "monthly", "canadian")
        assert m.payment(500_000, 5, 25, "accelerated_biweekly",
                         "canadian") == pytest.approx(monthly / 2, abs=0.01)
        assert m.payment(500_000, 5, 25, "accelerated_weekly",
                         "canadian") == pytest.approx(monthly / 4, abs=0.01)

    def test_a_zero_rate_is_the_balance_divided_up(self):
        assert m.payment(120_000, 0, 10, "monthly", "canadian") == 1000.0
        assert m.compute(terms(balance=120_000, rate=0, years=10),
                         TODAY)["total_interest"] == 0


class TestTheSchedule:
    @pytest.mark.parametrize("frequency", list(m.FREQUENCIES))
    @pytest.mark.parametrize("compounding", m.COMPOUNDING)
    def test_the_principal_paid_is_the_balance(self, frequency, compounding):
        rows = m.schedule(terms(frequency=frequency, compounding=compounding))
        assert sum(r["principal"] for r in rows) == pytest.approx(500_000, abs=0.01)
        assert rows[-1]["balance"] == pytest.approx(0, abs=0.01)

    def test_it_ends_when_the_amortization_does(self):
        r = m.compute(terms(), TODAY)
        assert r["payoff_month"] == "2051-10"
        assert r["years_left"] == pytest.approx(25)

    def test_accelerated_bi_weekly_pays_off_sooner_and_costs_less(self):
        monthly = m.compute(terms(), TODAY)
        fast = m.compute(terms(frequency="accelerated_biweekly"), TODAY)
        assert fast["payoff_month"] < monthly["payoff_month"]
        assert fast["years_left"] < 22
        assert fast["total_interest"] < monthly["total_interest"]

    def test_plain_bi_weekly_saves_almost_nothing(self):
        monthly = m.compute(terms(), TODAY)
        biweekly = m.compute(terms(frequency="biweekly"), TODAY)
        assert biweekly["payoff_month"] == monthly["payoff_month"]
        assert biweekly["monthly_equivalent"] == pytest.approx(
            monthly["monthly_equivalent"], rel=0.002)

    def test_interest_and_principal_add_up_to_what_is_paid(self):
        r = m.compute(terms(), TODAY)
        assert r["total_paid"] == pytest.approx(
            r["total_interest"] + r["total_principal"], abs=0.01)
        assert sum(y["interest"] for y in r["by_year"]) == pytest.approx(
            r["total_interest"], abs=1)
        assert r["interest_share"] == pytest.approx(
            r["total_interest"] / r["total_paid"], abs=0.0001)

    def test_early_payments_are_mostly_interest(self):
        r = m.compute(terms(), TODAY)
        assert r["next_month"]["interest"] > r["next_month"]["principal"]
        assert r["by_year"][-1]["principal"] > r["by_year"][-1]["interest"]


class TestPayingExtra:
    def test_extra_shortens_it_and_cuts_the_interest(self):
        plain = m.compute(terms(), TODAY)
        extra = m.compute(terms(extra_monthly=300), TODAY)
        assert extra["payoff_month"] < plain["payoff_month"]
        assert extra["total_interest"] < plain["total_interest"]
        assert extra["committed_monthly"] == pytest.approx(
            plain["committed_monthly"] + 300)

    def test_what_it_saves_is_the_difference_from_paying_none(self):
        plain = m.compute(terms(), TODAY)
        extra = m.compute(terms(extra_monthly=300), TODAY)
        assert extra["saves"]["interest"] == pytest.approx(
            plain["total_interest"] - extra["total_interest"], abs=0.01)
        assert extra["saves"]["months"] == plain["months_left"] - extra["months_left"]
        assert extra["without_extra"]["payoff_month"] == plain["payoff_month"]

    def test_no_extra_reports_no_saving(self):
        assert m.compute(terms(), TODAY)["saves"] is None


class TestOverTime:
    def test_the_balance_now_is_rolled_forward_from_when_it_was_typed(self):
        t = terms()
        later = m.compute(t, "2028-03")
        rows = [r for r in m.schedule(t) if r["offset"] <= 17]
        assert later["balance_now"] == pytest.approx(rows[-1]["balance"], abs=0.01)
        assert later["balance_now"] < 500_000
        # Totals are what is left to pay, not what was paid already.
        assert later["total_principal"] == pytest.approx(later["balance_now"])
        assert later["payoff_month"] == "2051-10"

    def test_the_balance_at_renewal_matches_the_schedule(self):
        r = m.compute(terms(term_end="2031-10"), TODAY)
        rows = [x for x in m.schedule(terms()) if x["offset"] <= 60]
        assert r["renewal"]["balance"] == pytest.approx(rows[-1]["balance"], abs=0.01)
        assert r["renewal"]["principal"] == pytest.approx(
            500_000 - r["renewal"]["balance"], abs=0.01)

    def test_alternatives_trade_payment_for_interest(self):
        alts = m.compute(terms(), TODAY)["alternatives"]
        assert [a["years"] for a in alts] == [15, 20, 25, 30]
        pays = [a["payment"] for a in alts]
        costs = [a["total_interest"] for a in alts]
        assert pays == sorted(pays, reverse=True)
        assert costs == sorted(costs)
        assert alts[2]["payment"] == m.compute(terms(), TODAY)["payment"]


class TestValidation:
    def body(self, **kw):
        return {"balance": 400000, "rate": 4.5, "years": 25, **kw}

    def test_a_good_one_passes(self):
        t, error = m.validate(self.body(frequency="weekly", term_end="2029-06"),
                              "2026-10-04")
        assert error is None and t.as_of == "2026-10" and t.term_end == "2029-06"

    @pytest.mark.parametrize("bad", [
        {"balance": 0}, {"balance": "lots"}, {"rate": -1}, {"rate": 40},
        {"years": 0.5}, {"years": 41}, {"extra_monthly": -5},
        {"frequency": "daily"}, {"compounding": "daily"},
        {"term_end": "2026-09"}, {"term_end": "soon"},
    ])
    def test_nonsense_is_refused(self, bad):
        t, error = m.validate(self.body(**bad), "2026-10-04")
        assert t is None and error


# ── The API, and the commitment the mortgage owns ────────────────────────────

MORTGAGE = {"balance": 500000, "rate": 5, "years": 25, "frequency": "monthly",
            "compounding": "canadian"}


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "mortgage.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 9000, "savings": 900})
        yield c


def commitments(client):
    return client.get("/api/plan/setup").get_json()["fixed"]


class TestTheMortgageIsTheCommitment:
    def test_nothing_is_saved_to_begin_with(self, client):
        body = client.get("/api/mortgage").get_json()
        assert body["saved"] is None and body["result"] is None

    def test_a_preview_writes_nothing(self, client):
        r = client.post("/api/mortgage/preview", json=MORTGAGE)
        assert r.status_code == 200
        assert r.get_json()["result"]["payment"] == pytest.approx(2908.03, abs=0.01)
        assert client.get("/api/mortgage").get_json()["saved"] is None
        assert commitments(client) == []

    def test_saving_puts_its_monthly_cost_in_the_plan(self, client):
        before = client.get("/api/plan/setup").get_json()["leftover"]
        body = client.put("/api/mortgage", json=MORTGAGE).get_json()
        monthly = body["result"]["committed_monthly"]

        rows = commitments(client)
        assert len(rows) == 1
        assert rows[0]["name"] == "Mortgage" and rows[0]["from"] == "mortgage"
        assert rows[0]["amount"] == pytest.approx(monthly)
        after = client.get("/api/plan/setup").get_json()["leftover"]
        assert before - after == pytest.approx(monthly, abs=0.011)
        assert body["share_of_income"] == pytest.approx(monthly / 9000, abs=0.0001)

    def test_saving_again_updates_the_same_line(self, client):
        client.put("/api/mortgage", json=MORTGAGE)
        client.put("/api/mortgage", json={**MORTGAGE, "frequency": "accelerated_biweekly",
                                         "extra_monthly": 200})
        rows = commitments(client)
        assert len(rows) == 1
        saved = client.get("/api/mortgage").get_json()
        assert rows[0]["amount"] == pytest.approx(saved["result"]["committed_monthly"])
        assert saved["saved"]["frequency"] == "accelerated_biweekly"

    def test_a_mortgage_typed_by_hand_is_adopted_not_doubled(self, client):
        client.post("/api/plan/fixed", json={"name": "mortgage", "amount": 2500,
                                             "category": "Rent & Housing"})
        offered = client.get("/api/mortgage").get_json()["existing"]
        assert offered and offered["amount"] == 2500
        client.put("/api/mortgage", json=MORTGAGE)
        rows = commitments(client)
        assert len(rows) == 1 and rows[0]["amount"] == pytest.approx(2908.03, abs=0.01)
        assert client.get("/api/mortgage").get_json()["existing"] is None

    def test_its_line_can_only_be_changed_from_the_mortgage(self, client):
        client.put("/api/mortgage", json=MORTGAGE)
        cost = commitments(client)[0]["id"]
        for r in (client.patch(f"/api/plan/fixed/{cost}", json={"amount": 10}),
                  client.delete(f"/api/plan/fixed/{cost}")):
            assert r.status_code == 400
            assert "Mortgage" in r.get_json()["error"]
        assert commitments(client)[0]["amount"] == pytest.approx(2908.03, abs=0.01)

    def test_removing_it_takes_its_commitment_too(self, client):
        client.put("/api/mortgage", json=MORTGAGE)
        assert client.delete("/api/mortgage").status_code == 200
        assert commitments(client) == []
        assert client.get("/api/mortgage").get_json()["saved"] is None
        assert client.delete("/api/mortgage").status_code == 404

    def test_other_commitments_are_left_alone(self, client):
        client.post("/api/plan/fixed", json={"name": "Hydro", "amount": 90,
                                             "category": "Utilities"})
        client.put("/api/mortgage", json=MORTGAGE)
        client.delete("/api/mortgage")
        assert [r["name"] for r in commitments(client)] == ["Hydro"]

    def test_the_weekly_number_sees_the_same_payment(self, client):
        before = client.get("/api/plan").get_json()["derivation"]
        client.put("/api/mortgage", json=MORTGAGE)
        after = client.get("/api/plan").get_json()["derivation"]
        assert after["fixed_total"] - before["fixed_total"] == pytest.approx(2908.03, abs=0.011)
        assert before["leftover"] - after["leftover"] == pytest.approx(2908.03, abs=0.011)

    @pytest.mark.parametrize("bad", [{"balance": -1}, {"rate": 99},
                                     {"years": 100}, {"frequency": "daily"}])
    def test_nonsense_is_a_400(self, client, bad):
        assert client.put("/api/mortgage", json={**MORTGAGE, **bad}).status_code == 400
        assert client.post("/api/mortgage/preview",
                           json={**MORTGAGE, **bad}).status_code == 400
