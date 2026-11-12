"""TEST-18 (THL-303's extension, product owner 2026-11-10): Not sure yet with
you in it. "I had some too" is on by default; you can set your own share,
and what's left (the purchase − linked paybacks − your share) goes to
whoever hasn't paid. Setting it turns the split into a set split, and Undo
goes back to Not sure yet. Anyone who has paid is locked at what they paid.
Rule A holds throughout: the whole purchase counts until it's paid back.

The example is designBOT's: Pizza Nova $120.00, five ways (you, Priya, Sam,
Jo and Alex). Priya, Sam and Jo paid $25.00 each; you set $17.00; Alex owes
$28.00.
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
    app = create_app(str(tmp_path / "you_row.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        set_plan(c, income=5200, savings=900)
        yield c


def allowance(c) -> float:
    return c.get("/api/home").get_json()["safe_to_spend"]["amount"]


def splitting(c, tid) -> dict:
    d = c.get(f"/api/transactions/{tid}").get_json()
    return d.get("transaction", d)["splitting"]


def owes(c, tid) -> dict:
    return {p["name"]: p["owes"] for p in splitting(c, tid)["people"]}


def pizza_nova(c, paid=("Priya", "Sam", "Jo"), me=True):
    senders = {"Priya": "Priya Shah", "Sam": "Sam Lee", "Jo": "Jo Park", "Alex": "Alex Kim"}
    rows = [charge(120.00, "PIZZA NOVA 22", "Pizza Nova", when=day(0))]
    rows += [etransfer_in(25.00, senders[n], when=day(0)) for n in paid]
    ids = load(c.st, *rows)
    tid = ids["PIZZA NOVA 22"]
    r = c.put(f"/api/transactions/{tid}/split", json={
        "mode": "unknown", "watch": True, "include_me": me,
        "people": [{"name": n} for n in ("Priya", "Sam", "Jo", "Alex")]})
    assert r.status_code == 200, r.get_json()
    for n in paid:
        inflow = ids[f"E-TRANSFER RECEIVED {senders[n].upper()}"]
        r = c.post(f"/api/transactions/{tid}/paybacks/{inflow}", json={"person": n})
        assert r.status_code == 200, r.get_json()
    return tid


def set_share(c, tid, you, others: dict, ok=True):
    people = [{"name": "Priya", "amount": 25.0}, {"name": "Sam", "amount": 25.0}]
    people += [{"name": n, "amount": a} for n, a in others.items()]
    r = c.put(f"/api/transactions/{tid}/split", json={
        "mode": "amount", "watch": True, "include_me": True, "you": you, "your_share": True,
        "people": people})
    assert (r.status_code == 200) is ok, r.get_json()
    return r.get_json()


class TestYouInIt:
    def test_i_had_some_too_is_on_by_default_and_kept(self, client):
        tid = pizza_nova(client)
        assert splitting(client, tid)["me"] is True
        assert client.st.splits()[tid]["me"] is True

    def test_not_in_it_is_kept(self, client):
        tid = pizza_nova(client, me=False)
        assert splitting(client, tid)["me"] is False

    def test_it_counts_45_until_paid_back(self, client):
        tid = pizza_nova(client)
        assert splitting(client, tid)["still"] == pytest.approx(45.00)


class TestSetYourShare:
    def test_s47b_17_gives_alex_the_28_left_and_the_allowance_stays(self, client):
        """S-47b: one person left, so Alex gets what's left: $28.00."""
        tid = pizza_nova(client, paid=("Priya", "Sam", "Jo"))
        before = allowance(client)
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": True, "you": 17, "your_share": True,
            "people": [{"name": "Priya", "amount": 25}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 28}]})
        assert r.status_code == 200, r.get_json()
        s = r.get_json()["splitting"]
        assert s["mode"] == "amount" and s["you"] == pytest.approx(17.00)
        assert owes(client, tid) == {"Priya": 0.0, "Sam": 0.0, "Jo": 0.0, "Alex": 28.0}
        # Rule A: setting it doesn't move the Allowance; Alex's $28 still counts.
        assert allowance(client) == pytest.approx(before)
        # Undo goes back to Not sure yet.
        u = client.post("/api/transactions/undo", json=r.get_json()["undo"])
        assert u.status_code == 200, u.get_json()
        assert splitting(client, tid)["mode"] == "unknown"
        assert allowance(client) == pytest.approx(before)

    def test_when_alex_pays_only_your_17_stays_counted(self, client):
        tid = pizza_nova(client)
        set_share(client, tid, 17, {"Jo": 25, "Alex": 28})
        before = allowance(client)
        ids = load(client.st, etransfer_in(28.00, "Alex Kim", when=day(0)))
        r = client.post(f"/api/transactions/{tid}/paybacks/{ids['E-TRANSFER RECEIVED ALEX KIM']}",
                        json={"person": "Alex"})
        assert r.status_code == 200, r.get_json()
        assert allowance(client) == pytest.approx(before + 28.00)
        rows = client.get("/api/transactions/list", query_string={"month": TODAY.isoformat()[:7]}).get_json()
        assert next(x for x in rows["transactions"] if x["id"] == tid)["amount"] == pytest.approx(17.00)

    def test_s47c_two_unpaid_split_what_is_left_evenly(self, client):
        """S-47c: Jo and Alex haven't paid; $53.00 left, $26.50 each."""
        tid = pizza_nova(client, paid=("Priya", "Sam"))
        set_share(client, tid, 17, {"Jo": 26.50, "Alex": 26.50})
        assert owes(client, tid) == {"Priya": 0.0, "Sam": 0.0, "Jo": 26.5, "Alex": 26.5}

    def test_s47d_amounts_that_dont_add_up_are_refused(self, client):
        """S-47d: "$13.00 left to assign", nothing saved."""
        tid = pizza_nova(client, paid=("Priya", "Sam"))
        r = set_share(client, tid, 17, {"Jo": 20, "Alex": 20}, ok=False)
        assert r["error"] == "$13.00 left to assign."
        assert splitting(client, tid)["mode"] == "unknown"

    def test_s47e_your_share_more_than_whats_left_is_refused(self, client):
        """S-47e: "Your share can be up to $45.00"."""
        tid = pizza_nova(client)
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": True, "you": 50, "your_share": True,
            "people": [{"name": "Priya", "amount": 25}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 0}]})
        assert r.status_code == 400
        assert r.get_json()["error"] in ("Your share can be up to $45.00.",
                                         "That’s $5.00 more than the charge.")
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": True, "you": 46, "your_share": True,
            "people": [{"name": "Priya", "amount": 25}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 0}]})
        assert r.status_code == 400
        assert r.get_json()["error"] == "Your share can be up to $45.00."


class TestLocked:
    def test_a_payer_is_locked_at_what_they_paid_when_settling(self, client):
        tid = pizza_nova(client)
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": True, "you": 22,
            "people": [{"name": "Priya", "amount": 20}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 28}]})
        assert r.status_code == 400
        # TEST-18b: on Settle up, Pearl asks what Priya's extra is (S-48b).
        assert r.get_json()["error"] == "Say what Priya’s extra $5.00 is."
        # S-47 (your_share) never asks: a payer stays exactly as paid.
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": True, "you": 22, "your_share": True,
            "people": [{"name": "Priya", "amount": 20}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 28}]})
        assert r.get_json()["error"] == "Priya’s $25.00 is linked. Unlink the payback to change Priya’s share."

    def test_s45a2_not_in_it_alex_owes_whats_left(self, client):
        """S-45a2: she isn't in it and only Alex hasn't paid: Alex owes $45.00."""
        tid = pizza_nova(client, me=False)
        r = client.put(f"/api/transactions/{tid}/split", json={
            "mode": "amount", "watch": True, "include_me": False,
            "people": [{"name": "Priya", "amount": 25}, {"name": "Sam", "amount": 25},
                       {"name": "Jo", "amount": 25}, {"name": "Alex", "amount": 45}]})
        assert r.status_code == 200, r.get_json()
        assert owes(client, tid)["Alex"] == 45.0
        assert splitting(client, tid)["me"] is False and splitting(client, tid)["you"] == 0
