"""Your share of a charge, when friends paid you back the rest.

The card shows $120; your share was $40. Only $40 should count, everywhere
spending is measured, in the month it was spent — while the Transactions tab
still shows the $120 that was charged.
"""

from __future__ import annotations

from datetime import date

import pytest


@pytest.fixture()
def ledger(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "shares.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        c.post("/api/plan/setup/apply")
        yield c


def add_charge(c, amount=120.0, category="Dining", description="DINNER WITH FRIENDS"):
    r = c.post("/api/transactions", json={
        "date": date.today().isoformat(), "description": description,
        "amount": amount, "category": category, "confirm": True})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def plan(c):
    return c.get(f"/api/plan?month={date.today():%Y-%m}").get_json()


def dining_spent(c):
    body = c.get(f"/api/budgets?month={date.today():%Y-%m}").get_json()
    row = next((r for r in body["rows"] if r["category"] == "Dining"), None)
    return row["spent"] if row else 0.0


def month_total(c):
    return c.get(f"/api/breakdown?month={date.today():%Y-%m}").get_json()["pace"]["total"]


class TestYourShareIsWhatCounts:
    def test_only_your_share_counts_everywhere(self, ledger):
        txn = add_charge(ledger)
        before = plan(ledger), dining_spent(ledger), month_total(ledger)
        r = ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 40})
        assert r.status_code == 200 and r.get_json()["my_share"] == 40.0
        after = plan(ledger), dining_spent(ledger), month_total(ledger)

        assert after[0]["state"]["week"]["spent"] == pytest.approx(
            before[0]["state"]["week"]["spent"] - 80, abs=0.01)
        assert after[0]["status"]["spent"] == pytest.approx(
            before[0]["status"]["spent"] - 80, abs=0.01)
        assert after[0]["spent_in_total"] == pytest.approx(
            before[0]["spent_in_total"] - 80, abs=0.01)
        assert after[1] == pytest.approx(before[1] - 80, abs=0.01)
        assert after[2] == pytest.approx(before[2] - 80, abs=0.01)

    def test_the_card_amount_is_still_shown(self, ledger):
        txn = add_charge(ledger)
        ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 40})
        rows = ledger.get("/api/transactions?q=DINNER WITH FRIENDS").get_json()["transactions"]
        row = next(t for t in rows if t["id"] == txn)
        assert row["amount"] == 120.0 and row["my_share"] == 40.0

    def test_paid_back_in_full_counts_for_nothing(self, ledger):
        txn = add_charge(ledger)
        before = plan(ledger)["status"]["spent"]
        ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 0})
        assert plan(ledger)["status"]["spent"] == pytest.approx(before - 120, abs=0.01)

    def test_clearing_it_puts_the_whole_charge_back(self, ledger):
        txn = add_charge(ledger)
        before = plan(ledger)["status"]["spent"]
        ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 40})
        r = ledger.put(f"/api/transactions/{txn}/share", json={"my_share": None})
        assert r.get_json()["my_share"] is None
        assert plan(ledger)["status"]["spent"] == pytest.approx(before, abs=0.01)

    def test_the_whole_amount_is_the_same_as_no_split(self, ledger):
        txn = add_charge(ledger)
        r = ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 120})
        assert r.get_json()["my_share"] is None


class TestWhatIsRefused:
    @pytest.mark.parametrize("share", [121, -1, "lots"])
    def test_a_share_outside_the_charge(self, ledger, share):
        txn = add_charge(ledger)
        r = ledger.put(f"/api/transactions/{txn}/share", json={"my_share": share})
        assert r.status_code == 400

    def test_money_that_came_back(self, ledger):
        txn = add_charge(ledger, amount=-25.0, description="REFUND")
        r = ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 10})
        assert r.status_code == 400

    def test_an_unknown_charge(self, ledger):
        assert ledger.put("/api/transactions/nope/share",
                          json={"my_share": 1}).status_code == 404


class TestPiggyBanksPayYourShare:
    def test_a_bank_takes_only_your_share(self, ledger):
        r = ledger.post("/api/piggy", json={"name": "Travel", "target": 6000,
                                            "cadence": "annual",
                                            "categories": ["Travel", "Lodging"]})
        bank_id = r.get_json()["id"]

        def available():
            return next(b for b in ledger.get("/api/piggy").get_json()["banks"]
                        if b["id"] == bank_id)["available"]

        start = available()
        week = plan(ledger)["state"]["week"]["spent"]
        txn = add_charge(ledger, amount=3000.0, category="Lodging", description="GROUP CABIN")
        assert available() == pytest.approx(start - 3000, abs=0.01)
        ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 1000})
        assert available() == pytest.approx(start - 1000, abs=0.01)
        assert plan(ledger)["state"]["week"]["spent"] == pytest.approx(week, abs=0.01)


class TestItStays:
    def test_a_reimport_keeps_the_share_and_adds_nothing(self, ledger):
        st = ledger.application.config["STORE"]
        txn = st.all_transactions()[0]
        ledger.put(f"/api/transactions/{txn.fingerprint}/share",
                   json={"my_share": round(txn.amount / 2, 2)})
        count = len(st.all_transactions())
        ledger.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        assert len(st.all_transactions()) == count
        again = st.get_transaction(txn.fingerprint)
        assert again.my_share == pytest.approx(round(txn.amount / 2, 2))

    def test_a_reset_clears_shares(self, ledger):
        txn = add_charge(ledger)
        ledger.put(f"/api/transactions/{txn}/share", json={"my_share": 40})
        st = ledger.application.config["STORE"]
        st.reset()
        with st.conn() as c:
            assert c.execute("SELECT COUNT(*) AS n FROM txn_shares").fetchone()["n"] == 0


def test_a_share_belongs_to_its_own_account(tmp_path, monkeypatch):
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
    txn = add_charge(maria)
    assert maria.put(f"/api/transactions/{txn}/share",
                     json={"my_share": 40}).status_code == 200
    assert sister.put(f"/api/transactions/{txn}/share",
                      json={"my_share": 1}).status_code == 404
