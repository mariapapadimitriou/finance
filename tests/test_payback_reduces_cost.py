"""A payback lowers what a split purchase costs her, however it was linked
(product owner, 2026-11-16: "Even though I paid back my share for a split,
it doesn't adjust the transaction properly to reflect and reduce by the
amount I paid.").

Rule A (TEST-03, THL-291): the whole purchase counts until it's paid back,
and the Allowance rises by each payback as it comes. A payback Pearl can't
credit to anyone yet (no name, and its amount isn't exactly one open share:
S-05u, S-35c "Who sent this?", THL-181) is still money back for this
purchase: its deposit already says "comes off your spending", so it comes
off now. Saying who sent it later only moves it onto that person.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def day(n):
    d = TODAY - timedelta(days=n)
    return (d if d.strftime("%Y-%m") == MONTH else TODAY.replace(day=1)).isoformat()


def tx(desc, amount, category="", when=None, merchant=None):
    return Transaction(date=when or day(1), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "cost.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def numbers(c, pid):
    """What the purchase costs her everywhere she looks: its Cash flow row,
    the month's Spent, and the Allowance on Home."""
    lst = c.get("/api/transactions/list", query_string={"month": MONTH, "limit": 500}).get_json()
    row = next(r for r in lst["transactions"] if r["id"] == pid)
    home = c.get("/api/home").get_json()["safe_to_spend"]
    return {"row": row["amount"], "note": row["note"], "spent": lst["month_totals"]["spent"],
            "allowance": home["amount"]}


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


@pytest.fixture()
def dinner(client):
    """$150.00 split with Sam and Priya, $50.00 each; $50.00 back by an
    e-Transfer that names no one."""
    i = add(client, tx("NORTHWIND LTD PAYROLL", -3000.0, "Income", when=day(5), merchant="Northwind Ltd"),
            tx("PAI NORTHERN THAI", 150.0, "Dining", when=day(4)),
            tx("E-TRANSFER K2P", -50.0, when=day(2), merchant="E-Transfer"))
    pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER K2P"]
    ok(client.put(f"/api/transactions/{pai}/split", json={
        "mode": "amount", "people": [{"name": "Sam", "amount": 50}, {"name": "Priya", "amount": 50}]}))
    return pai, dep


LINKS = {
    # "Someone paying me back" from the deposit, a purchase picked.
    "mark": lambda c, pai, dep: c.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": pai}),
    # "Pays back something else" on What was this? (S-11 v2), no one ticked.
    "parts": lambda c, pai, dep: c.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "amount": 50.0, "charge": pai}]}),
    # The purchase's own Paid back search, no person.
    "purchase": lambda c, pai, dep: c.post(f"/api/transactions/{pai}/paybacks/{dep}", json={}),
}


@pytest.mark.parametrize("how", sorted(LINKS))
def test_a_payback_no_one_is_credited_with_yet_still_comes_off(client, dinner, how):
    pai, dep = dinner
    before = numbers(client, pai)
    assert (before["row"], before["spent"]) == (150.0, 150.0)
    ok(LINKS[how](client, pai, dep))
    # Pearl asks who sent it (S-05u): it's credited to no one, Sam and Priya still owe.
    split = client.get(f"/api/transactions/{pai}").get_json()["splitting"]
    assert [u["amount"] for u in split["uncredited"]] == [50.0]
    assert [(p["name"], p["owes"]) for p in split["people"]] == [("Sam", 50.0), ("Priya", 50.0)]
    after = numbers(client, pai)
    assert after["row"] == 100.0
    assert after["spent"] == 100.0
    assert after["allowance"] == round(before["allowance"] + 50.0, 2)
    assert after["note"] == "Split with Sam and Priya · $50.00 to come back"


def test_saying_who_sent_it_changes_nothing_she_spent(client, dinner):
    pai, dep = dinner
    ok(LINKS["mark"](client, pai, dep))
    asked = numbers(client, pai)
    r = ok(client.post(f"/api/transactions/{dep}/credit", json={"person": "Sam", "charge": pai}))
    assert numbers(client, pai) == asked
    split = client.get(f"/api/transactions/{pai}").get_json()["splitting"]
    assert [(p["name"], p["owes"]) for p in split["people"]] == [("Sam", 0.0), ("Priya", 50.0)]
    ok(client.post("/api/transactions/undo", json=r["undo"]))
    assert numbers(client, pai) == asked


def test_unlinking_it_puts_the_whole_purchase_back(client, dinner):
    pai, dep = dinner
    before = numbers(client, pai)
    ok(LINKS["mark"](client, pai, dep))
    ok(client.delete(f"/api/transactions/{pai}/paybacks/{dep}"))
    assert numbers(client, pai) == before


def test_one_person_and_part_of_their_share(client):
    """Sam owes $60.00 and $15.00 comes in with no name: Pearl won't guess
    it's Sam's (S-35c), but the dinner costs $15.00 less now."""
    i = add(client, tx("NORTHWIND LTD PAYROLL", -3000.0, "Income", when=day(5), merchant="Northwind Ltd"),
            tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(4)),
            tx("E-TRANSFER K2P", -15.0, when=day(2), merchant="E-Transfer"))
    pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER K2P"]
    ok(client.put(f"/api/transactions/{pai}/split", json={"mode": "amount", "people": [{"name": "Sam", "amount": 60}]}))
    before = numbers(client, pai)
    ok(LINKS["mark"](client, pai, dep))
    after = numbers(client, pai)
    assert (after["row"], after["spent"]) == (105.0, 105.0)
    assert after["allowance"] == round(before["allowance"] + 15.0, 2)


@pytest.mark.parametrize("kind", ["full", "part"])
def test_a_named_payback_from_either_side(tmp_path, kind):
    """The four ways she links Sam's money (the deposit's parts, the
    purchase's Paid back, Mark paid back from the bank, cash) agree."""
    from app import create_app
    sent = 60.0 if kind == "full" else 15.0
    seen = []
    for n, link in enumerate((
            lambda c, pai, dep: c.post(f"/api/transactions/{dep}/parts", json={"parts": [
                {"kind": "payback", "amount": sent, "charge": pai, "person": "Sam"}]}),
            lambda c, pai, dep: c.post(f"/api/transactions/{pai}/paid-back", json={"deposit": dep, "person": "Sam"}),
            lambda c, pai, dep: c.post(f"/api/transactions/{pai}/paybacks/{dep}", json={"person": "Sam"}),
            lambda c, pai, dep: c.post(f"/api/transactions/{pai}/split/cash",
                                       json={"name": "Sam", "amount": sent, "via": "cash"}))):
        app = create_app(str(tmp_path / f"{n}.db"))
        app.config.update(TESTING=True)
        c = app.test_client()
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        i = add(c, tx("NORTHWIND LTD PAYROLL", -3000.0, "Income", when=day(5), merchant="Northwind Ltd"),
                tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(4)),
                tx("E-TRANSFER FROM SAM LEE", -sent, when=day(2), merchant="Sam Lee"))
        pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]
        ok(c.put(f"/api/transactions/{pai}/split", json={"mode": "amount", "people": [{"name": "Sam", "amount": 60}]}))
        ok(link(c, pai, dep))
        got = numbers(c, pai)
        seen.append((got["row"], got["spent"]))
    assert set(seen) == {(120.0 - sent, 120.0 - sent)}
