"""testingBOT's Round 2 findings (ios/bots/testing-log.md) that the server
can catch.

TEST-20: "Which payment was it?" (S-06rb) for Priya suggested and pre-ticked
Sam's $30.00, because a quarter of $120.00 "looked even". Only Priya's own
money may be suggested, and "Amount matches" only when it does.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, "tests")
from ledger_files import set_plan  # noqa: E402
from test_splits import charge, etransfer_in, load  # noqa: E402

TODAY = date.today()


def day(n=0):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "round2.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        set_plan(c, income=5200, savings=900)
        yield c


def pizza(c, mode="unknown"):
    """Pizza Nova $120.00 with Priya, Sam, Jo and Alex; Sam sent $30.00 (a
    quarter, the amount that "looked even") and Priya $25.00."""
    ids = load(c.st, charge(120.00, "PIZZA NOVA", "Dining", when=day(0)),
               etransfer_in(30.00, "Sam Lee", when=day(0)),
               etransfer_in(25.00, "Priya Shah", when=day(0)))
    tid = ids["PIZZA NOVA"]
    names = ["Priya", "Sam", "Jo", "Alex"]
    body = {"mode": mode, "watch": True, "people": [{"name": n} for n in names]}
    if mode == "amount":
        body.update(include_me=True, you=30.00,
                    people=[{"name": "Priya", "amount": 25.00}, {"name": "Sam", "amount": 30.00},
                            {"name": "Jo", "amount": 20.00}, {"name": "Alex", "amount": 15.00}])
    r = c.put(f"/api/transactions/{tid}/split", json=body)
    assert r.status_code == 200, r.get_json()
    return tid, ids


def candidates(c, tid, person):
    r = c.get(f"/api/transactions/{tid}/paybacks", query_string={"person": person})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["candidates"]


def test_not_sure_yet_suggests_only_their_own_payment(client):
    tid, _ = pizza(client)
    rows = candidates(client, tid, "Priya")
    assert rows[0]["party"] == "Priya Shah", "Priya's own money leads"
    likely = [r for r in rows if r["likely"]]
    assert [r["party"] for r in likely] == ["Priya Shah"]
    # Not sure yet has no amount to match: never "Amount matches".
    assert all(r.get("match") is None for r in rows)
    sam = next(r for r in rows if r["party"] == "Sam Lee")
    assert sam["likely"] is False


def test_someone_with_no_payment_gets_nothing_pre_ticked(client):
    tid, _ = pizza(client)
    rows = candidates(client, tid, "Jo")
    assert not any(r["likely"] for r in rows), "Sam's $30.00 must never be ticked for Jo"


def test_amount_matches_only_when_it_is_theirs_and_it_does(client):
    tid, _ = pizza(client, mode="amount")
    priya = candidates(client, tid, "Priya")
    assert priya[0]["party"] == "Priya Shah" and priya[0]["likely"] and priya[0]["match"] == "amount"
    assert not next(r for r in priya if r["party"] == "Sam Lee")["likely"]
    # Jo owes $20.00: neither $25.00 nor $30.00 is Jo's, nor matches.
    jo = candidates(client, tid, "Jo")
    assert not any(r["likely"] or r.get("match") for r in jo)


def test_two_senders_with_the_same_amount(client):
    ids = load(client.st, charge(90.00, "NOPA", "Dining", when=day(0)),
               etransfer_in(30.00, "Sam Lee", when=day(0)),
               etransfer_in(30.00, "Priya Shah", when=day(0)))
    tid = ids["NOPA"]
    r = client.put(f"/api/transactions/{tid}/split", json={
        "mode": "even", "watch": True, "people": [{"name": "Priya"}, {"name": "Sam"}]})
    assert r.status_code == 200, r.get_json()
    for who, sender in (("Priya", "Priya Shah"), ("Sam", "Sam Lee")):
        rows = candidates(client, tid, who)
        assert [r["party"] for r in rows if r["likely"]] == [sender]
        assert rows[0]["party"] == sender
