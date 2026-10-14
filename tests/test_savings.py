"""Savings so far: put away, and left over, since the day she started
(finance/savings.py)."""

from __future__ import annotations

from datetime import date

import pytest

from finance import savings
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
            tx("2026-08-20", "Old pay", -3000.0, "Income"),          # before the start
            tx("2026-08-22", "TFR-TO 3333", 900.0, "Saved"),
            tx("2026-09-01", "Northwind", -2150.0, "Income"),
            tx("2026-09-03", "Pai", 45.0, "Dining"),
            tx("2026-09-05", "TFR-TO 3333", 500.0, "Saved"),           # put away
            tx("2026-09-20", "TFR-FR 3333", -200.0, "Saved"),          # taken back out
            tx("2026-10-01", "Northwind", -2150.0, "Income"),
            tx("2026-10-02", "Rogers", 85.0, "Phone & Internet"),
            tx("2026-10-03", "TD Visa Payment", 400.0, "Transfers"),    # neither
        ]
        # Ingest re-sorts the rows in place; what the bank said, by date and name.
        wanted = {(r.date, r.merchant): r.category for r in rows}
        ingest(c.st, IngestResult(rows, "chq"))
        c.st.set_categories({t.fingerprint: (wanted[(t.date, t.merchant)], "plaid")
                             for t in c.st.all_transactions()})
        c.st.set_setting(savings.SINCE, "2026-09-01")
        yield c


def test_both_totals_since_the_start(client):
    s = client.get("/api/home").get_json()["savings"]
    assert s["since"] == "2026-09-01"
    assert s["put_away"] == {"contributions": 500.0, "withdrawals": 200.0, "net": 300.0}
    assert s["left_over"] == {"income": 4300.0, "spent": 130.0, "net": 4170.0}


def test_nothing_before_the_start_counts(client):
    client.st.set_setting(savings.SINCE, "2026-08-01")
    s = client.get("/api/home").get_json()["savings"]
    assert s["put_away"]["contributions"] == 1400.0
    assert s["left_over"]["income"] == 7300.0


def test_the_start_is_when_she_started_over_or_the_first_day(client):
    client.st.set_setting(savings.SINCE, "")
    assert savings.since(client.st, None) == "2026-08-20"             # the first row

    class U:
        onboarded_at = 1788436800.0                                   # 2026-09-03 UTC
    assert savings.since(client.st, U()) == "2026-09-03"
    savings.start_over(client.st, date(2026, 10, 14))
    assert savings.since(client.st, U()) == "2026-10-14"


def test_marking_money_in_as_taken_out_of_savings(client):
    """A deposit sorted as Saved comes off what's put away, and isn't income."""
    t = next(t for t in client.st.all_transactions() if t.merchant == "Northwind"
             and t.date == "2026-10-01")
    client.patch(f"/api/transactions/{t.fingerprint}", json={"category": "Saved"})
    s = client.get("/api/home").get_json()["savings"]
    assert s["put_away"]["withdrawals"] == 2350.0 and s["put_away"]["net"] == -1850.0
    assert s["left_over"]["income"] == 2150.0


def test_starting_over_starts_the_count_today(client):
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert client.st.setting(savings.SINCE) == "2026-10-14"
    s = client.get("/api/home").get_json()["savings"]
    assert s["since"] == "2026-10-14" and s["put_away"]["net"] == 0 and s["left_over"]["net"] == 0
