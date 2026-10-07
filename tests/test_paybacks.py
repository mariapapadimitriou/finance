"""Friends paying you back for a charge: it comes off the charge, and is
neither income nor money in."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.pipeline import ingest
from finance.models import Transaction

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"
START = TODAY.replace(day=1)


def d(n):
    return min(START + timedelta(days=n), TODAY).isoformat()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "pb.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        yield c


def load(c, rows, account, kind):
    st = c.application.config["STORE"]
    txns = [Transaction(date=when, description=desc, amount=amt, account_id=account,
                        account_name=account, raw={"account_type": kind,
                                                   **({"issuer_category": cat} if cat else {})})
            for when, desc, amt, cat in rows]
    ingest(st, IngestResult(transactions=txns, account_id=account))
    return {t.description: t.fingerprint for t in st.all_transactions()}


@pytest.fixture()
def dinner(client):
    ids = load(client, [(d(0), "UBER EATS TORONTO", 80, None)], "card", "credit")
    ids |= load(client, [(d(1), "E-TRANSFER FROM ANNA", -20, None),
                         (d(2), "E-TRANSFER FROM BEN", -20, None),
                         (d(3), "CAL MARTIN", -20, "INCOME_OTHER_INCOME"),
                         (d(1), "PAYROLL DEPOSIT", -60, None)], "chq", "depository")
    return ids


def month(c):
    return next(m for m in c.get("/api/summary").get_json()["monthly"]
                if m["month"] == MONTH)


def link(c, charge, inflow):
    return c.post(f"/api/transactions/{charge}/paybacks/{inflow}")


class TestPaidBack:
    def test_three_friends_leave_you_a_quarter(self, client, dinner):
        charge = dinner["UBER EATS TORONTO"]
        before = month(client)
        for name in ("E-TRANSFER FROM ANNA", "E-TRANSFER FROM BEN", "CAL MARTIN"):
            r = link(client, charge, dinner[name])
            assert r.status_code == 200, r.get_json()
        after = month(client)
        assert after["spend"] == pytest.approx(before["spend"] - 60)
        assert r.get_json()["share"] == 20 and r.get_json()["paid_back"] == 60
        # Not money in, and Cal's (which Plaid called income) isn't income.
        assert after["inflows"] == pytest.approx(before["inflows"] - 40)
        assert after["income"] == pytest.approx(before["income"] - 20)

    def test_the_rows_say_what_they_paid_for(self, client, dinner):
        charge = dinner["UBER EATS TORONTO"]
        link(client, charge, dinner["E-TRANSFER FROM ANNA"])
        rows = {t["description"]: t for t in
                client.get("/api/transactions").get_json()["transactions"]}
        anna = rows["E-TRANSFER FROM ANNA"]
        assert anna["repays"] == charge and anna["repays_amount"] == 80
        assert anna["repays_merchant"]
        assert rows["UBER EATS TORONTO"]["paid_back"] == 20

    def test_one_inflow_repays_one_charge(self, client, dinner):
        other = load(client, [(d(0), "PIZZA PLACE", 40, None)], "card", "credit")["PIZZA PLACE"]
        link(client, dinner["UBER EATS TORONTO"], dinner["E-TRANSFER FROM ANNA"])
        assert link(client, other, dinner["E-TRANSFER FROM ANNA"]).status_code == 400

    def test_no_more_than_the_charge(self, client, dinner):
        small = load(client, [(d(0), "TIM HORTONS", 15, None)], "card", "credit")["TIM HORTONS"]
        assert link(client, small, dinner["E-TRANSFER FROM ANNA"]).status_code == 400

    def test_a_typed_share_wins(self, client, dinner):
        charge = dinner["UBER EATS TORONTO"]
        client.put(f"/api/transactions/{charge}/share", json={"my_share": 30})
        link(client, charge, dinner["E-TRANSFER FROM ANNA"])
        body = client.get(f"/api/transactions/{charge}/paybacks").get_json()
        assert body["share"] == 30

    def test_unlinking_puts_the_charge_back(self, client, dinner):
        charge = dinner["UBER EATS TORONTO"]
        before = month(client)["spend"]
        link(client, charge, dinner["E-TRANSFER FROM ANNA"])
        r = client.delete(f"/api/transactions/{charge}/paybacks/{dinner['E-TRANSFER FROM ANNA']}")
        assert r.status_code == 200 and r.get_json()["linked"] == []
        assert month(client)["spend"] == pytest.approx(before)

    def test_candidates_put_even_splits_by_e_transfer_first(self, client, dinner):
        body = client.get(f"/api/transactions/{dinner['UBER EATS TORONTO']}/paybacks").get_json()
        names = [c["description"] for c in body["candidates"]]
        assert names[:3] == ["E-TRANSFER FROM ANNA", "E-TRANSFER FROM BEN",
                             "CAL MARTIN"]
        # The payroll is offered last if at all: not an even split, not a name.
        assert "PAYROLL DEPOSIT" not in names[:3]
        assert body["candidates"][0]["likely"]

    def test_a_paid_back_inflow_is_never_a_transfers_other_end(self, client, dinner):
        st = client.application.config["STORE"]
        charge = dinner["UBER EATS TORONTO"]
        for name in ("E-TRANSFER FROM ANNA", "E-TRANSFER FROM BEN", "CAL MARTIN"):
            link(client, charge, dinner[name])
        # $20 leaving another bank account the same day Anna's arrived.
        load(client, [(d(1), "SEND E-TFR ***q", 20, None)], "sav", "depository")
        sent = next(t for t in st.all_transactions() if t.description == "SEND E-TFR ***q")
        assert sent.category == "Unsorted transfers"

    def test_refused_the_wrong_way_round(self, client, dinner):
        assert link(client, dinner["E-TRANSFER FROM ANNA"],
                    dinner["UBER EATS TORONTO"]).status_code == 400
