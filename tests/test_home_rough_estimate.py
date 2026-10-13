"""Home with a rough estimate (Pearl THL-125 H-03).

Once she skips the check's "We didn't spot a regular paycheque" (I-03),
Home doesn't go without a number: it makes a rough one from the deposits of
the last 30 days, shows it to the nearest $50, labelled, and asks for her
income as the one primary action.
"""

from datetime import date

import pytest

from finance import income_bills as ib
from finance import safe_to_spend as sts
from finance.models import Transaction

TODAY = date(2026, 10, 9)


def tx(day, merchant, amount, category, account="chq"):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant,
                       amount=amount, category=category, account_id=account)


def rows():
    """Two weeks of a chequing account: two client payments, some spending."""
    return [tx("2026-09-25", "Client A", -640.00, "Income"),
            tx("2026-09-26", "Loblaws", 80.00, "Groceries"),
            tx("2026-10-03", "Client B", -590.00, "Income"),
            tx("2026-10-05", "Pai", 45.00, "Dining")]


def skipped(**extra):
    return {**ib.empty(), "income_skipped": "2026-10-01", **extra}


class TestTheNumber:
    def test_without_skipping_there_is_still_no_number(self):
        s = sts.compute(rows(), TODAY)
        assert s["state"] == "needs_income" and s["amount"] is None

    def test_skipped_it_comes_from_the_deposits_seen(self):
        s = sts.compute(rows(), TODAY, confirm=skipped())
        assert s["income_source"] == "deposits" and s["estimate"] == "rough"
        income = next(r for r in s["rows"] if r["key"] == "income")
        assert income["amount"] == 1230.00
        # 1,230 in, 45 spent in October: 1,185, shown to the nearest $50.
        assert s["amount"] == 1185.00 and s["shown"] == 1200

    def test_only_the_last_30_days_count(self):
        old = rows() + [tx("2026-09-01", "Client C", -900.00, "Income")]
        s = sts.compute(old, TODAY, confirm=skipped())
        assert next(r for r in s["rows"] if r["key"] == "income")["amount"] == 1230.00

    def test_never_less_than_what_arrived_this_month(self):
        s = sts.compute(rows(), TODAY, confirm=skipped())
        income = next(r for r in s["rows"] if r["key"] == "income")
        assert income["amount"] >= 590.00

    def test_the_nearest_50_rounds_both_ways(self):
        assert sts.round_50(1124.99) == 1100
        assert sts.round_50(1125.00) == 1150
        assert sts.round_50(20.00) == 0

    def test_it_is_rough_even_with_months_of_history(self):
        """A month with no income means no cautious figure, and a long
        history doesn't make a number from deposits any less rough."""
        long = [tx("2026-06-15", "Loblaws", 60.00, "Groceries")] + rows()
        s = sts.compute(long, TODAY, confirm=skipped())
        assert s["income_source"] == "deposits" and s["estimate"] == "rough"

    def test_no_deposits_still_means_no_number(self):
        spending = [r for r in rows() if r.amount > 0]
        s = sts.compute(spending, TODAY, confirm=skipped())
        assert s["state"] == "needs_income"

    def test_her_income_wins_once_she_gives_it(self):
        s = sts.compute(rows(), TODAY, told_income=3000.00, confirm=skipped())
        assert s["income_source"] == "told"

    def test_it_doesnt_confirm_her_income_on_the_path(self):
        from finance.milestones import income_confirmed
        s = sts.compute(rows(), TODAY, confirm=skipped())
        assert not income_confirmed(s, skipped())

    def test_home_stops_asking_the_starter_questions(self):
        s = sts.compute(rows(), TODAY, confirm=skipped())
        h = sts.home_state(rows(), TODAY, s)
        assert h["asks_questions"] is False


# ── The endpoints ────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    import finance.api as api
    import finance.income_bills_api as iba
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    monkeypatch.setattr(iba, "_today_iso", lambda: TODAY.isoformat())
    app = create_app(str(tmp_path / "rough.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.application.config["STORE"].add_transactions(rows())
        yield c


def home(c):
    return c.get("/api/home").get_json()["safe_to_spend"]


class TestTheEndpoints:
    def test_skip_for_now_is_remembered_and_home_has_a_number(self, client):
        assert home(client)["state"] == "needs_income"
        r = client.post("/api/income-bills/expected/skip")
        assert r.status_code == 200
        s = home(client)
        assert s["income_source"] == "deposits" and s["shown"] == 1200

    def test_skipping_again_keeps_the_first_date(self, client):
        client.post("/api/income-bills/expected/skip")
        st = client.application.config["STORE"]
        first = ib.load(st)["income_skipped"]
        client.post("/api/income-bills/expected/skip")
        assert ib.load(st)["income_skipped"] == first == TODAY.isoformat()

    def test_adding_her_income_replaces_the_estimate(self, client):
        client.post("/api/income-bills/expected/skip")
        client.put("/api/income-bills/expected", json={"amount": 3000})
        s = home(client)
        assert s["income_source"] == "told" and s["estimate"] == "rough"
