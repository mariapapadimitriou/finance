"""Rule A (TEST-03, THL-291 "Payback rule unchanged: the full purchase counts
until paid back; a payback is never income", THL-289; product owner
2026-11-10): a split purchase counts in full toward the Allowance, and each
payback (linked, cash, another app) raises it by its amount. Letting a share
go changes nothing: it was counted all along.

The example is testingBOT's: Gusto $127.50, Priya $42.50, Sam $30.00,
Jo $15.00, and you the rest ($40.00).
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
    app = create_app(str(tmp_path / "rule_a.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        set_plan(c, income=5200, savings=900)
        yield c


def allowance(c) -> float:
    return c.get("/api/home").get_json()["safe_to_spend"]["amount"]


def gusto(c):
    ids = load(c.st, charge(127.50, "TST* GUSTO 504", "Gusto", when=day(0)),
               etransfer_in(42.50, "Priya Shah", when=day(0)),
               etransfer_in(30.00, "Sam Lee", when=day(0)))
    return ids["TST* GUSTO 504"], ids


def split_by_amounts(c, tid):
    r = c.put(f"/api/transactions/{tid}/split", json={
        "mode": "amount", "watch": True,
        "people": [{"name": "Priya", "amount": 42.50}, {"name": "Sam", "amount": 30.00},
                   {"name": "Jo", "amount": 15.00}]})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def spent(c, tid) -> float:
    rows = c.get("/api/transactions/list", query_string={"month": TODAY.isoformat()[:7]}).get_json()["transactions"]
    return next(x["amount"] for x in rows if x["id"] == tid)


def test_splitting_doesnt_move_the_allowance_the_whole_purchase_still_counts(client):
    tid, _ = gusto(client)
    before = allowance(client)                 # Gusto counts $127.50 already
    split_by_amounts(client, tid)
    assert allowance(client) == pytest.approx(before)
    assert spent(client, tid) == pytest.approx(127.50)


def test_each_payback_raises_the_allowance_by_its_amount(client):
    tid, ids = gusto(client)
    split_by_amounts(client, tid)
    start = allowance(client)
    r = client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
    assert r.status_code == 200, r.get_json()
    assert allowance(client) == pytest.approx(start + 42.50)
    assert spent(client, tid) == pytest.approx(85.00)
    # Sam pays cash: it counts as paid at once.
    r = client.post(f"/api/transactions/{tid}/split/cash", json={"name": "Sam", "amount": 30.00})
    assert r.status_code in (200, 201), r.get_json()
    assert allowance(client) == pytest.approx(start + 72.50)
    assert spent(client, tid) == pytest.approx(55.00)


def test_letting_a_share_go_leaves_the_allowance_alone(client):
    tid, ids = gusto(client)
    split_by_amounts(client, tid)
    client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
    client.post(f"/api/transactions/{tid}/split/cash", json={"name": "Sam", "amount": 30.00})
    before = allowance(client)
    r = client.post(f"/api/transactions/{tid}/split/let-go", json={"name": "Jo"})
    assert r.status_code == 200, r.get_json()
    assert allowance(client) == pytest.approx(before)
    assert spent(client, tid) == pytest.approx(55.00)       # your $40 and Jo's $15
    # And back: Jo owes again, still nothing moves.
    client.delete(f"/api/transactions/{tid}/split/let-go", json={"name": "Jo"})
    assert allowance(client) == pytest.approx(before)


def test_the_split_from_the_start_is_127_50_then_each_payback(client):
    """The $127.50 example end to end, from before the purchase is split."""
    ids = load(client.st, etransfer_in(42.50, "Priya Shah", when=day(0)),
               etransfer_in(30.00, "Sam Lee", when=day(0)))
    empty = allowance(client)
    ids = load(client.st, charge(127.50, "TST* GUSTO 504", "Gusto", when=day(0)))
    tid = ids["TST* GUSTO 504"]
    split_by_amounts(client, tid)
    assert allowance(client) == pytest.approx(empty - 127.50)
    client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
    assert allowance(client) == pytest.approx(empty - 85.00)
    client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED SAM LEE']}")
    assert allowance(client) == pytest.approx(empty - 55.00)
    client.post(f"/api/transactions/{tid}/split/let-go", json={"name": "Jo"})
    assert allowance(client) == pytest.approx(empty - 55.00)


def test_the_page_says_whole_purchase_and_your_share(client):
    tid, _ = gusto(client)
    split_by_amounts(client, tid)
    d = client.get(f"/api/transactions/{tid}").get_json()
    t = d.get("transaction", d)
    assert t["full_amount"] == pytest.approx(127.50)
    assert t["splitting"]["you"] == pytest.approx(40.00)
    owed = {p["name"]: p["owes"] for p in t["splitting"]["people"]}
    assert owed == {"Priya": 42.50, "Sam": 30.00, "Jo": 15.00}


def test_not_sure_yet_is_unchanged(client):
    tid, ids = gusto(client)
    before = allowance(client)
    r = client.put(f"/api/transactions/{tid}/split", json={"mode": "unknown", "watch": True,
                                                           "people": [{"name": "Priya"}, {"name": "Sam"}]})
    assert r.status_code == 200, r.get_json()
    assert allowance(client) == pytest.approx(before)
    client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
    assert allowance(client) == pytest.approx(before + 42.50)


class TestCashFlowNote:
    """T-01r2 (product owner 2026-11-10): the split row says what's still to
    come back, that it all has, or that it's not sure yet."""

    def note(self, c, tid):
        rows = c.get("/api/transactions/list", query_string={"month": TODAY.isoformat()[:7]}).get_json()
        return next(x for x in rows["transactions"] if x["id"] == tid)["note"]

    def test_people_still_owe(self, client):
        tid, ids = gusto(client)
        split_by_amounts(client, tid)
        assert self.note(client, tid) == "Split with Priya +2 · $87.50 to come back"
        client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
        assert self.note(client, tid) == "Split with Priya +2 · $45.00 to come back"

    def test_two_people_by_name(self, client):
        tid, _ = gusto(client)
        client.put(f"/api/transactions/{tid}/split", json={"mode": "even", "watch": True,
                                                           "people": [{"name": "Priya"}, {"name": "Sam"}]})
        assert self.note(client, tid) == "Split with Priya and Sam · $85.00 to come back"

    def test_all_paid_back(self, client):
        ids = load(client.st, charge(59.33, "NOPA RESTAURANT", "Nopa Restaurant", when=day(0)),
                   etransfer_in(19.77, "Priya Shah", when=day(0)), etransfer_in(19.77, "Sam Lee", when=day(0)))
        tid = ids["NOPA RESTAURANT"]
        client.put(f"/api/transactions/{tid}/split", json={"mode": "even", "watch": True,
                                                           "people": [{"name": "Priya"}, {"name": "Sam"}]})
        client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
        client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED SAM LEE']}")
        assert self.note(client, tid) == "Your share of $59.33 · all paid back"

    def test_not_sure_yet(self, client):
        tid, ids = gusto(client)
        client.put(f"/api/transactions/{tid}/split", json={"mode": "unknown", "watch": True,
                                                           "people": [{"name": n} for n in ("Priya", "Sam", "Jo", "Alex")]})
        assert self.note(client, tid) == "Split 5 ways · not sure yet · $127.50 still counts"
        client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED PRIYA SHAH']}")
        assert self.note(client, tid) == "Split 5 ways · not sure yet · $85.00 still counts"
