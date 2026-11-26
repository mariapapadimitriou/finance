"""Setup finds pay the bank didn't call income, pay that varies, and weekly
pay (product owner, 2026-11-25: "Pearl is unable to detect my sister's
income, even though she has a recurring payment from a single merchant").

* A deposit from one payer, 3 or more on a schedule, is offered as pay
  whatever the bank's label (Transfers, Other), and only asked: a Yes sorts
  that payer's deposits as income with a pay rule, a No never asks again.
  Her own transfers, money moved from an account Pearl can't see, refunds,
  paybacks and e-Transfers (their own question) aren't offered.
* Pay that varies (hours, tips) within half its usual amount is offered at
  its usual amount.
* Weekly pay gives the Allowance its income, as other schedules do.

Demo data only, through the endpoints the app calls.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "pay.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def deposits(c, desc, amounts, every=14, label="TRANSFER_IN_DEPOSIT", account="chq"):
    rows = [Transaction(date=(TODAY - timedelta(days=3 + every * i)).isoformat(), description=desc,
                        amount=-a, account_id=account, account_name=account,
                        raw={"account_type": "depository", "issuer_category": label})
            for i, a in enumerate(amounts)]
    # History from well before, so the Allowance has months to go on.
    rows.append(Transaction(date=(TODAY - timedelta(days=200)).isoformat(), description="COFFEE", amount=4.0,
                            account_id=account, account_name=account, raw={"account_type": "depository"}))
    ingest(c.st, IngestResult(rows, account))


def offered(c):
    """Pay offered, by the bank's words it came from, any case."""
    rows = c.get("/api/income-bills").get_json()["candidates"]
    return _Offered({p["payer"].lower(): p for p in rows})


class _Offered(dict):
    def __getitem__(self, desc):
        return next(v for k, v in self.items() if k in desc.lower() or desc.lower() in k)

    def __contains__(self, desc):
        return any(k in desc.lower() or desc.lower() in k for k in self)


def allowance(c):
    return c.get("/api/home").get_json()["safe_to_spend"]


@pytest.mark.parametrize("label", ["TRANSFER_IN_DEPOSIT", ""])
def test_pay_the_bank_called_a_transfer_is_offered(client, label):
    deposits(client, "ACME CORP", [2100.0] * 6, label=label)
    row = next(t for t in client.st.all_transactions() if t.amount < 0)
    assert row.category != "Income"
    pay = offered(client)["ACME CORP"]
    assert (pay["cadence"], pay["amount"], pay["salary"]) == ("biweekly", 2100.0, False)
    # Asked, never assumed.
    assert allowance(client)["state"] == "needs_income"


def test_yes_makes_it_income_and_the_allowance_has_it(client):
    deposits(client, "ACME CORP", [2100.0] * 6)
    r = client.post("/api/income-bills/pay/answer", json={"payer": offered(client)["ACME CORP"]["payer"], "answer": "yes"})
    assert r.status_code == 200, r.get_json()
    assert {t.category for t in client.st.all_transactions() if t.amount < 0} == {"Income"}
    assert allowance(client)["state"] != "needs_income"
    # And the next one is income as it lands.
    deposits(client, "ACME CORP", [2100.0], every=0)
    assert {t.category for t in client.st.all_transactions() if t.amount < 0} == {"Income"}


def test_no_is_never_asked_again(client):
    deposits(client, "ACME CORP", [2100.0] * 6)
    client.post("/api/income-bills/pay/answer", json={"payer": offered(client)["ACME CORP"]["payer"], "answer": "no"})
    assert "ACME CORP" not in offered(client)
    assert {t.category for t in client.st.all_transactions() if t.amount < 0} != {"Income"}


@pytest.mark.parametrize("desc", ["TFR-FR TANGERINE 4417", "INTERNET TRANSFER", "INTERAC E-TRANSFER FROM ACME CORP"])
def test_not_offered_as_pay(client, desc):
    deposits(client, desc, [500.0] * 6, every=30, label="TRANSFER_IN_ACCOUNT_TRANSFER")
    assert desc not in offered(client)


def test_her_own_transfer_is_not_pay(client):
    rows = []
    for i in range(4):
        d = (TODAY - timedelta(days=3 + 30 * i)).isoformat()
        rows.append(Transaction(date=d, description="ONLINE BANKING SAVINGS", amount=300.0, account_id="sav",
                                account_name="Savings",
                                raw={"account_type": "depository", "issuer_category": "TRANSFER_OUT_ACCOUNT_TRANSFER"}))
    ingest(client.st, IngestResult(rows, "sav"))
    deposits(client, "ONLINE BANKING CHEQUING", [300.0] * 4, every=30)
    assert "ONLINE BANKING CHEQUING" not in offered(client)


def test_pay_that_varies_is_offered_at_its_usual_amount(client):
    deposits(client, "PAYROLL ACME CORP", [1500, 2100, 1800, 2400, 1600, 2200], label="INCOME_WAGES")
    pay = offered(client)["PAYROLL ACME CORP"]
    assert pay["cadence"] == "biweekly" and pay["amount"] == 1950.0


def test_more_than_half_off_is_not_a_schedule(client):
    deposits(client, "PAYROLL ACME CORP", [300, 2100, 900, 2400], label="INCOME_WAGES")
    assert "PAYROLL ACME CORP" not in offered(client)


def test_weekly_pay_gives_the_allowance_its_income(client):
    deposits(client, "PAYROLL ACME CORP", [700.0] * 8, every=7, label="INCOME_WAGES")
    assert offered(client)["PAYROLL ACME CORP"]["cadence"] == "weekly"
    sts = allowance(client)
    assert sts["state"] != "needs_income" and sts["income_source"] == "detected"
