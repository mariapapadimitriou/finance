"""Investments: money saved, never spent — in full, or part of a transaction."""

from __future__ import annotations

from datetime import date

import pytest

from finance import groups
from finance.analytics import counts_as_spending, invested_in
from finance.categorize import CATEGORIES, categorize
from finance.models import Transaction

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


class TestTheCategory:
    def test_it_exists_is_not_spending_and_is_no_budget_line(self):
        assert "Investments" in CATEGORIES
        t = Transaction(date=TODAY.isoformat(), description="X", amount=500,
                        account_id="a", category="Investments")
        assert not counts_as_spending(t)
        assert "Investments" not in groups.spend_categories()

    @pytest.mark.parametrize("merchant,code", [
        ("QUESTRADE INC", ""),
        ("WEALTHSIMPLE INVEST", ""),
        ("E-TRANSFER QUESTRADE WEALTH", ""),
        ("TFSA CONTRIBUTION", ""),
        ("", "TRANSFER_OUT_INVESTMENT_AND_RETIREMENT_FUNDS"),
    ])
    def test_investment_transfers_are_recognised(self, merchant, code):
        assert categorize(merchant, "", code)[0] == "Investments"

    def test_money_back_from_investments_is_a_transfer(self):
        assert categorize("", "", "TRANSFER_IN_INVESTMENT_AND_RETIREMENT_FUNDS")[0] == "Transfers"

    def test_a_wealthsimple_card_is_not_an_investment(self):
        assert categorize("WEALTHSIMPLE CASH", "", "")[0] != "Investments"


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "inv.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


def add(c, amount, category="Shopping", description="BIG TRANSFER"):
    r = c.post("/api/transactions", json={
        "date": TODAY.isoformat(), "description": description, "amount": amount,
        "category": category, "confirm": True})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def spent(c):
    return c.get(f"/api/plan?month={MONTH}").get_json()["status"]["spent"]


def shopping(c):
    rows = c.get(f"/api/budgets?month={MONTH}").get_json()["rows"]
    return next((r["spent"] for r in rows if r["category"] == "Shopping"), 0)


class TestPartOfATransaction:
    def test_only_the_rest_counts_as_spending(self, client):
        txn = add(client, 1000)
        before_spent, before_shop = spent(client), shopping(client)
        r = client.put(f"/api/transactions/{txn}/invested", json={"amount": 600})
        assert r.status_code == 200 and r.get_json()["invested"] == 600
        assert spent(client) == pytest.approx(before_spent - 600, abs=0.01)
        assert shopping(client) == pytest.approx(before_shop - 600, abs=0.01)

        client.put(f"/api/transactions/{txn}/invested", json={"amount": None})
        assert spent(client) == pytest.approx(before_spent, abs=0.01)

    def test_the_card_still_shows_the_whole_amount(self, client):
        txn = add(client, 1000)
        client.put(f"/api/transactions/{txn}/invested", json={"amount": 600})
        rows = client.get("/api/transactions?q=BIG TRANSFER").get_json()["transactions"]
        row = next(t for t in rows if t["id"] == txn)
        assert row["amount"] == 1000 and row["invested"] == 600

    def test_a_piggy_bank_never_pays_for_the_invested_part(self, client):
        bank = client.post("/api/piggy", json={"name": "Stuff", "target": 6000,
                                               "cadence": "annual",
                                               "categories": ["Shopping"]}).get_json()["id"]

        def available():
            return next(b for b in client.get("/api/piggy").get_json()["banks"]
                        if b["id"] == bank)["available"]
        start = available()
        txn = add(client, 1000)
        client.put(f"/api/transactions/{txn}/invested", json={"amount": 600})
        assert available() == pytest.approx(start - 400, abs=0.01)

    @pytest.mark.parametrize("amount", [1001, -1, "lots"])
    def test_what_is_refused(self, client, amount):
        txn = add(client, 1000)
        assert client.put(f"/api/transactions/{txn}/invested",
                          json={"amount": amount}).status_code == 400

    def test_money_coming_back_cannot_be_invested(self, client):
        txn = add(client, -50, description="REFUND")
        assert client.put(f"/api/transactions/{txn}/invested",
                          json={"amount": 10}).status_code == 400

    def test_a_reset_clears_it(self, client):
        txn = add(client, 1000)
        client.put(f"/api/transactions/{txn}/invested", json={"amount": 600})
        st = client.application.config["STORE"]
        st.reset()
        with st.conn() as c:
            assert c.execute("SELECT COUNT(*) AS n FROM txn_invested").fetchone()["n"] == 0


class TestAheadShowsIt:
    def test_invested_this_month_counts_both_ways_once(self, client):
        add(client, 500, category="Investments", description="QUESTRADE INC")
        part = add(client, 1000)
        client.put(f"/api/transactions/{part}/invested", json={"amount": 300})
        # An Investments row with a partial amount still counts once, in full.
        both = add(client, 200, category="Investments", description="TFSA CONTRIBUTION")
        client.put(f"/api/transactions/{both}/invested", json={"amount": 50})
        body = client.get("/api/projections").get_json()
        assert body["invested_month"] == {"month": MONTH, "amount": 1000.0,
                                          "saving": 900.0}

    def test_the_sum_itself(self):
        rows = [
            Transaction(date=f"{MONTH}-01", description="A", amount=500,
                        account_id="a", category="Investments"),
            Transaction(date=f"{MONTH}-02", description="B", amount=-100,
                        account_id="a", category="Investments"),
            Transaction(date=f"{MONTH}-03", description="C", amount=1000,
                        account_id="a", category="Shopping", invested=250),
        ]
        assert invested_in(rows, MONTH) == 650


def test_each_account_sees_its_own(tmp_path, monkeypatch):
    from app import create_app
    from finance import auth, users
    for key in (auth.PASSWORD_ENV, auth.HASH_ENV, "SPENDIE_SMTP_USER",
                "SPENDIE_SMTP_PASSWORD", "SPENDIE_SECRET_KEY"):
        monkeypatch.delenv(key, raising=False)
    monkeypatch.setenv("VERCEL", "1")
    monkeypatch.setenv(users.OWNER_HASH_ENV, auth.hash_password("owner password"))
    app = create_app(str(tmp_path / "l.db"))
    maria = app.test_client()
    maria.post("/api/auth/login", json={"username": "mariapapas",
                                        "password": "owner password"})
    sister = app.test_client()
    sister.post("/api/auth/signup", json={"username": "sister",
                                          "password": "a long enough password"})
    txn = add(maria, 1000)
    assert maria.put(f"/api/transactions/{txn}/invested",
                     json={"amount": 100}).status_code == 200
    assert sister.put(f"/api/transactions/{txn}/invested",
                      json={"amount": 1}).status_code == 404
