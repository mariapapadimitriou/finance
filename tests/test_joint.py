"""Joint accounts: a row you can't match to your own accounts is another
member's, until you say it was yours."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(amount, description, account, category=None):
    return Transaction(date=day(1), description=description, amount=amount,
                       account_id=account, account_name=account,
                       raw={"account_type": "depository"}, category=category)


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "joint.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 900})
        st = c.application.config["STORE"]
        ingest(st, IngestResult([row(120, "LOBLAWS", "fam"),
                                 row(-1000, "PAYROLL DEPOSIT DAD", "fam"),
                                 row(-500, "TFR-FR 1111111", "fam"),
                                 row(80, "SEND E-TFR ***Mom1", "fam")], "fam"))
        ingest(st, IngestResult([row(500, "TFR-TO 2222222", "chq")], "chq"))
        c.put("/api/accounts/fam/joint", json={"label": "Family"})
        yield c


def month(c):
    return next(m for m in c.get("/api/summary").get_json()["monthly"] if m["month"] == MONTH)


def ids(c):
    return {t["description"]: t["id"] for t in c.get("/api/transactions").get_json()["transactions"]}


def test_theirs_by_default(client):
    m = month(client)
    assert m["spend"] == 0                    # Loblaws is theirs until you say
    assert m["income"] == 0 and m["inflows"] == 0
    accounts = {a["account_id"]: a for a in client.get("/api/accounts").get_json()["accounts"]}
    assert accounts["fam"]["joint"] == "Family"


def test_mine_and_part(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 120})
    assert month(client)["spend"] == 120
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 40})
    assert month(client)["spend"] == 40
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": None})
    assert month(client)["spend"] == 0


def test_a_deposit_can_be_mine_too(client):
    i = ids(client)
    r = client.put(f"/api/transactions/{i['PAYROLL DEPOSIT DAD']}/share",
                   json={"my_share": -1000})
    assert r.status_code == 200
    assert month(client)["income"] == 1000


def test_always_mine_at_a_name(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/mine-always", json={"on": True})
    assert month(client)["spend"] == 120
    st = client.application.config["STORE"]
    ingest(st, IngestResult([row(30, "LOBLAWS", "fam")], "fam"))
    assert month(client)["spend"] == 150


def test_your_transfer_into_it_is_matched(client):
    rows = {t["description"]: t for t in client.get("/api/transactions").get_json()["transactions"]}
    assert rows["TFR-TO 2222222"]["category"] == "Transfers"


def test_another_members_transfer_out_is_never_yours_to_sort(client):
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 0


def test_unmarking_restores_normal_counting(client):
    client.put("/api/accounts/fam/joint", json={"label": None})
    # Loblaws, and the e-transfer out, which is waiting to be sorted again.
    assert month(client)["spend"] == 200
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


@pytest.mark.parametrize("share", [200, -50, "lots"])
def test_bad_shares_are_refused(client, share):
    i = ids(client)
    assert client.put(f"/api/transactions/{i['LOBLAWS']}/share",
                      json={"my_share": share}).status_code == 400
