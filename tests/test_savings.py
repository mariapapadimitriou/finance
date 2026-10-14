"""Savings this month: put away, and left over, for the current month
(finance/savings.py)."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def tx(day, merchant, amount, category, **kw):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, account_id="chq", account_name="chq",
                       raw={"account_type": "depository"}, **kw)


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    import finance.api as api
    monkeypatch.setattr(api, "_today_iso", lambda: "2026-10-14")
    app = create_app(str(tmp_path / "s.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        rows = [
            tx("2026-09-01", "Northwind", -2150.0, "Income"),
            tx("2026-09-05", "TFR-TO 3333", 500.0, "Saved"),           # last month: not shown
            tx("2026-10-01", "Northwind", -2150.0, "Income"),
            tx("2026-10-02", "Rogers", 85.0, "Phone & Internet"),
            tx("2026-10-03", "Pai", 45.0, "Dining"),
            tx("2026-10-05", "TFR-TO 3333", 400.0, "Saved"),           # put away
            tx("2026-10-09", "TFR-FR 3333", -150.0, "Saved"),          # taken back out
            tx("2026-10-10", "TD Visa Payment", 300.0, "Transfers"),    # neither
        ]
        # Ingest re-sorts the rows in place; what the bank said, by date and name.
        wanted = {(r.date, r.merchant): r.category for r in rows}
        ingest(c.st, IngestResult(rows, "chq"))
        c.st.set_categories({t.fingerprint: (wanted[(t.date, t.merchant)], "plaid")
                             for t in c.st.all_transactions()})
        yield c


def test_both_totals_for_this_month(client):
    s = client.get("/api/home").get_json()["savings"]
    assert s["month"] == "2026-10"
    assert s["put_away"] == {"contributions": 400.0, "chests": 0.0, "withdrawals": 150.0,
                             "net": 250.0}
    assert s["left_over"] == {"income": 2150.0, "spent": 130.0, "net": 2020.0, "estimate": False}


def test_money_added_to_a_chest_counts_as_put_away(client):
    chest = client.st.add_piggy_bank("Holidays", 1200, "annual", None, "2026-07")
    client.st.add_draw(chest, "2026-10", -200.0, "Added")
    s = client.get("/api/home").get_json()["savings"]
    assert s["put_away"]["chests"] == 100.0 + 200.0           # the monthly amount, and the add
    assert s["put_away"]["net"] == 250.0 + 300.0


def test_marking_money_in_as_taken_out_of_savings(client):
    """A deposit sorted as Saved comes off what's put away, and isn't income."""
    t = next(t for t in client.st.all_transactions() if t.merchant == "Northwind"
             and t.date == "2026-10-01")
    client.patch(f"/api/transactions/{t.fingerprint}", json={"category": "Saved"})
    s = client.get("/api/home").get_json()["savings"]
    assert s["put_away"]["withdrawals"] == 2300.0 and s["put_away"]["net"] == -1900.0
    assert s["left_over"]["income"] == 0.0
