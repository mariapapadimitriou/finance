"""The saving goal as a share of income, and what actually came in and stayed."""

from __future__ import annotations

import pytest

from finance.models import Transaction
from finance.money_plan import observed


def t(when, amount, category, account="chq", joint=None, share=None):
    return Transaction(date=when, description=category, amount=amount, account_id=account,
                       category=category, joint=joint, my_share=share)


MONTHS = [("2026-07", 5000), ("2026-08", 5200), ("2026-09", 5100)]


def ledger():
    rows = []
    for month, pay in MONTHS:
        rows += [t(f"{month}-01", -pay, "Income"),
                 t(f"{month}-03", 2000, "Rent & Housing"),
                 t(f"{month}-09", 1000, "Groceries"),
                 t(f"{month}-15", 500, "Saved")]
    rows.append(t("2026-10-02", -5000, "Income"))          # this month: partial
    rows.append(t("2026-10-03", 300, "Groceries"))
    return rows


class TestObserved:
    def test_three_full_months(self):
        o = observed(ledger(), "2026-10-08")
        assert [m["month"] for m in o["months"]] == ["2026-07", "2026-08", "2026-09"]
        assert o["income"] == 5100                          # the median
        assert o["stayed"] == pytest.approx((2000 + 2200 + 2100) / 3, abs=0.01)
        assert o["moved"] == 500

    def test_another_members_deposit_is_not_income(self):
        rows = ledger() + [t("2026-09-20", -3000, "Income", account="fam",
                             joint="Family", share=0.0)]
        assert observed(rows, "2026-10-08")["months"][-1]["income"] == 5100

    def test_nothing_to_measure(self):
        assert observed([t("2026-09-03", 40, "Groceries")], "2026-10-08") is None


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "goal.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def setup(c):
    return c.get("/api/plan/setup").get_json()


class TestTheGoal:
    def test_a_rate_sets_the_dollars(self, client):
        client.put("/api/plan/setup", json={"income": 5000, "savings_rate": 0.2})
        d = setup(client)
        assert d["savings"] == 1000 and d["savings_rate"] == 0.2

    def test_the_dollars_follow_income(self, client):
        client.put("/api/plan/setup", json={"income": 5000, "savings_rate": 0.2})
        client.put("/api/plan/setup", json={"income": 6000})
        assert setup(client)["savings"] == 1200

    def test_a_dollar_figure_moves_the_rate(self, client):
        client.put("/api/plan/setup", json={"income": 6000, "savings_rate": 0.2})
        client.put("/api/plan/setup", json={"savings": 1500})
        d = setup(client)
        assert d["savings"] == 1500 and d["savings_rate"] == 0.25

    @pytest.mark.parametrize("rate", [-0.1, 0.95, "lots"])
    def test_bad_rates_are_refused(self, client, rate):
        assert client.put("/api/plan/setup", json={"savings_rate": rate}).status_code == 400

    def test_observed_comes_with_the_plan(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([t("2025-01-01", -4000, "Income"),
                             t("2025-01-05", 1000, "Groceries")])
        o = setup(client)["observed"]
        assert o["income"] == 4000 and o["stayed"] == 3000
