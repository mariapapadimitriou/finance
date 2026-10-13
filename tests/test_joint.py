"""Joint accounts: spending on one is hers by default, less what the other
person put in that month; money in counts once she says whose it was."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from ledger_files import set_plan

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
        set_plan(c, income=5200, savings=900)
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


def test_mine_by_default(client):
    m = month(client)
    # Loblaws, and the e-transfer out until it's sorted.
    assert m["spend"] == 200
    assert m["income"] == 0 and m["inflows"] == 0  # money in waits for an answer
    accounts = {a["account_id"]: a for a in client.get("/api/accounts").get_json()["accounts"]}
    assert accounts["fam"]["joint"] == "Family"


def test_mine_and_part(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 0})
    assert month(client)["spend"] == 80           # this one's theirs
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": 40})
    assert month(client)["spend"] == 120
    client.put(f"/api/transactions/{i['LOBLAWS']}/share", json={"my_share": None})
    assert month(client)["spend"] == 200


def test_a_deposit_can_be_mine_too(client):
    i = ids(client)
    r = client.put(f"/api/transactions/{i['PAYROLL DEPOSIT DAD']}/share",
                   json={"my_share": -1000})
    assert r.status_code == 200
    assert month(client)["income"] == 1000


def test_always_mine_at_a_name(client):
    i = ids(client)
    client.put(f"/api/transactions/{i['LOBLAWS']}/mine-always", json={"on": True})
    st = client.application.config["STORE"]
    ingest(st, IngestResult([row(30, "LOBLAWS", "fam"),
                             row(-75, "E-TRANSFER FROM SISTER", "fam")], "fam"))
    sister = ids(client)["E-TRANSFER FROM SISTER"]
    client.put(f"/api/transactions/{sister}/joint-from", json={"who": "them"})
    # Names always hers aren't paid for by what the other person puts in:
    # her $75 goes to the $80 e-transfer out, the rest of the joint spending.
    assert month(client)["spend"] == 120 + 30 + 5


def test_your_transfer_into_it_is_matched(client):
    rows = {t["description"]: t for t in client.get("/api/transactions").get_json()["transactions"]}
    assert rows["TFR-TO 2222222"]["category"] == "Transfers"


def test_her_transfer_out_of_it_is_hers_to_sort(client):
    assert client.get("/api/transfers/unsorted").get_json()["count"] == 1


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


# ── Who put money in (option b: theirs pays for joint spending) ──────────

def sister_in(client, amount, ref="1"):
    st = client.application.config["STORE"]
    t = row(-amount, f"E-TRANSFER {ref} FROM SISTER", "fam")
    t.merchant = "Sister"
    ingest(st, IngestResult([t], "fam"))
    return ids(client)[f"E-TRANSFER {ref} FROM SISTER"]


def answer(client, tid, who, remember=False):
    return client.put(f"/api/transactions/{tid}/joint-from",
                      json={"who": who, "remember": remember})


def test_her_sisters_deposit_pays_for_part_of_the_months_spending(client):
    tid = sister_in(client, 60)
    assert answer(client, tid, "them").status_code == 200
    # $60 of $200 joint spending (Loblaws, and the e-transfer out until it's
    # sorted) was her sister's, so 70% of each is hers.
    assert month(client)["spend"] == 84 + 56
    assert month(client)["income"] == 0


def test_more_put_in_than_spent_leaves_nothing_never_less(client):
    answer(client, sister_in(client, 500), "them")
    assert month(client)["spend"] == 0


def test_her_own_money_in_is_a_transfer_not_income(client):
    i = ids(client)
    r = answer(client, i["PAYROLL DEPOSIT DAD"], "me")
    assert r.status_code == 200
    m = month(client)
    assert m["income"] == 0 and m["spend"] == 200
    row_ = next(t for t in client.get("/api/transactions").get_json()["transactions"]
                if t["id"] == i["PAYROLL DEPOSIT DAD"])
    assert row_["category"] == "Transfers"


def test_remembered_for_that_sender(client):
    answer(client, sister_in(client, 30), "them", remember=True)
    sister_in(client, 30, ref="2")
    # Same sender, so both are hers: $60 of $200.
    assert month(client)["spend"] == 84 + 56


def test_asking_again_and_bad_answers(client):
    tid = sister_in(client, 60)
    answer(client, tid, "them")
    assert answer(client, tid, None).status_code == 200
    assert month(client)["spend"] == 200
    assert answer(client, tid, "dad").status_code == 400
    assert answer(client, ids(client)["LOBLAWS"], "them").status_code == 400   # not money in


def test_needs_a_look_asks_who_put_it_in(client):
    review = client.get("/api/review").get_json()
    asked = {q["txn"]["description"] for q in review["joint_in"]}
    assert asked == {"PAYROLL DEPOSIT DAD"}       # the TFR-FR is her own, matched
    assert review["joint_in"][0]["label"] == "Family"
    answer(client, ids(client)["PAYROLL DEPOSIT DAD"], "them")
    assert client.get("/api/review").get_json()["joint_in"] == []


def test_a_set_share_still_wins(client):
    client.put("/api/accounts/fam/settings", json={"joint_share": 50})
    answer(client, sister_in(client, 60), "them")
    assert month(client)["spend"] == 100            # half of everything, as she set
