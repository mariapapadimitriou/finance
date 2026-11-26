"""REFRESH-18 (product owner, 2026-11-25): overpaid and underpaid shares of a
split. finance/over_under.py owns the rules; Claude Design › Cash flow ›
G2-OverCard to G2-SmallLands, notes n-overunder and n-small. THL-289,
THL-291, THL-181, THL-301, THL-260. Demo data only."""

from __future__ import annotations

import ast
import pathlib
from datetime import date, timedelta

import pytest

from finance import over_under as ou
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

ROOT = pathlib.Path(__file__).resolve().parent.parent
TODAY = date.today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
KLEV, PAPPAS = "Georgia Klev", "Georgia Pappas"


def day(n):
    return f"{MONTH}-{28 - n:02d}"


def tx(desc, amount, category="", when=None, merchant=None, account="chq"):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "over.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def person(c, tid, name=KLEV):
    return next(p for p in detail(c, tid)["splitting"]["people"] if p["name"] == name)


def spent(c, tid):
    """What the purchase costs her now, what Spent and Allowance count."""
    from finance.analytics import spend_amount
    return spend_amount(c.st.get_transaction(tid))


def totals(c):
    t = c.get("/api/transactions/list", query_string={"month": MONTH}).get_json()["month_totals"]
    return t["spent"], t["income"]


def review(c, key="over"):
    return [q for q in c.get("/api/review").get_json()["money_in"] if q.get(key)]


def owed(c):
    return c.get("/api/owed").get_json()


def undo(c, r):
    out = c.post("/api/transactions/undo", json=r["undo"])
    assert out.status_code == 200, out.get_json()


def bistro(c, *pays, whole=80.0, people=((KLEV, 40.0),)):
    """Corner Bistro split with `people`, and money in from Georgia Klev
    (or a (amount, name) pair)."""
    rows = [tx("CORNER BISTRO", whole, "Dining", when=day(20), merchant="Corner Bistro")]
    for n, p in enumerate(pays):
        amount, who = p if isinstance(p, tuple) else (p, KLEV)
        rows.append(tx(f"E-TRANSFER FROM {who.upper()} {n}", -amount, when=day(12 - n), merchant=who))
    i = add(c, *rows)
    r = c.put(f"/api/transactions/{i['CORNER BISTRO']}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": a} for n, a in people]})
    assert r.status_code == 200, r.get_json()
    return i["CORNER BISTRO"], [i[k] for k in sorted((k for k in i if k.startswith("E-TRANSFER")),
                                                     key=lambda k: int(k.split()[-1]))]


def mark(c, dep, cid, name=KLEV, **more):
    r = c.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": cid, "person": name, **more})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def link(c, dep, cid, name=KLEV, **more):
    r = c.post(f"/api/transactions/{cid}/paybacks/{dep}", json={"person": name, **more})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def parts(c, dep, cid, name=KLEV, amount=None, **more):
    whole = -c.st.get_transaction(dep).amount
    r = c.post(f"/api/transactions/{dep}/parts", json={
        "parts": [{"kind": "payback", "amount": amount or whole, "charge": cid, "person": name}], "later": True, **more})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def paid_back(c, dep, cid, name=KLEV, **more):
    r = c.post(f"/api/transactions/{cid}/paid-back", json={"deposit": dep, "person": name, **more})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def credit(c, dep, cid, name=KLEV):
    """Linked with no name, then Who sent this?."""
    c.st.link_payback(cid, dep, None)
    c.st.set_payback_person(dep, "Someone Else")      # credited to nobody
    r = c.post(f"/api/transactions/{dep}/credit", json={"person": name})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def many(c, dep, cid, name=KLEV):
    return mark(c, dep, cid, name, charges=[{"id": cid}])


def cash(c, cid, amount, name=KLEV, **more):
    r = c.post(f"/api/transactions/{cid}/split/cash", json={"name": name, "amount": amount, "day": day(5), **more})
    assert r.status_code == 201, r.get_json()
    return r.get_json()


def app_pay(c, cid, amount, name=KLEV):
    return cash(c, cid, amount, name, via="app", app="PayPal")


def let_go(c, cid, name=KLEV):
    r = c.post(f"/api/transactions/{cid}/split/let-go", json={"name": name})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def say(c, cid, *pieces, name=KLEV, **more):
    r = c.post(f"/api/transactions/{cid}/split/extra", json={"name": name, "pieces": list(pieces), **more})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


LINKS = {"mark": mark, "many": many, "link": link, "parts": parts, "paid-back": paid_back, "credit": credit}
BY_HAND = {"cash": cash, "app": app_pay}


# ── The cutoff ────────────────────────────────────────────────────────────

@pytest.mark.parametrize("diff,share,small", [
    (2.00, 20.00, True), (2.01, 100.00, False), (2.00, 19.99, False), (1.00, 10.00, True), (1.01, 10.00, False),
    (0.01, 0.10, True), (0.01, 0.09, False), (0.00, 20.00, False), (-1.00, 20.00, False), (0.70, 7.00, True),
    (0.30, 3.00, True), (1.98, 19.80, True)])
def test_up_to_two_dollars_and_ten_percent(diff, share, small):
    assert ou.is_small(diff, share) is small
    assert (ou.SMALL_MAX, ou.SMALL_SHARE) == (2.00, 0.10)


# ── A small difference settles by itself, from every path (S-04s) ─────────

@pytest.mark.parametrize("path", LINKS)
def test_rounded_down_is_let_go(client, path):
    cid, (dep,) = bistro(client, 19.0, whole=40.0, people=((KLEV, 20.0),))
    before = spent(client, cid)
    r = LINKS[path](client, dep, cid)
    p = person(client, cid)
    assert (p["paid"], p["owes"], p["amount"]) == (19.0, 0.0, 19.0)
    assert p["let_go"]["was"] == 20.0 and p["let_go"]["auto"] is True
    assert (before, spent(client, cid)) == (40.0, 21.0), "the $1.00 becomes her spending"
    assert owed(client)["owes_you"] == [] and owed(client)["you_owe"] == [] and review(client) == []
    assert (r.get("toast") or r["title"]) == f"{KLEV} paid back $19.00 · $1.00 let go"
    assert detail(client, cid)["cost"]["share"] == 21.0
    undo(client, r)
    p = person(client, cid)
    assert (p["owes"], p["amount"], p["let_go"], p["paid"]) == (20.0, 20.0, None, 0.0)
    assert spent(client, cid) == 40.0 and client.st.splits()[cid]["people"][0].get("extra") is None


@pytest.mark.parametrize("path", LINKS)
def test_rounded_up_is_a_quiet_line(client, path):
    cid, (dep,) = bistro(client, 20.23, whole=40.0, people=((KLEV, 20.0),))
    r = LINKS[path](client, dep, cid)
    p = person(client, cid)
    assert p["extra"] == {"state": "small", "amount": 0.23, "owe": 0.0, "said": [], "line": None, "note": None, "moved": 0}
    assert p["owes"] == 0.0 and spent(client, cid) == 20.0 and totals(client)[1] == 0.0
    # Today 1: $20.23 on $20.00 listed $0.23 under You owe.
    assert owed(client)["you_owe"] == [] and review(client) == []
    assert (r.get("toast") or r["title"]) == f"{KLEV} paid back $20.00 · $0.23 extra"
    assert owed(client)["paid_back"] == [] or owed(client)["paid_back"][0]["amount"] == 20.0
    undo(client, r)
    assert client.st.splits()[cid]["people"][0].get("extra") is None


@pytest.mark.parametrize("path", BY_HAND)
def test_cash_and_other_apps_settle_the_same_way(client, path):
    cid, _ = bistro(client, whole=59.54, people=(("Priya", 20.0), (KLEV, 19.77)))
    r = BY_HAND[path](client, cid, 19.0, "Priya")
    assert r["title"] == "Priya paid back $19.00 · $1.00 let go"
    assert person(client, cid, "Priya")["let_go"]["was"] == 20.0 and spent(client, cid) == 40.54
    up = BY_HAND[path](client, cid, 20.0)
    assert person(client, cid)["extra"]["state"] == "small" and person(client, cid)["extra"]["amount"] == 0.23
    # S-04s's numbers: −$20.77, "$59.54 split · $38.77 back", your share $20.77.
    cost = detail(client, cid)["cost"]
    assert (spent(client, cid), cost["back"], cost["to_come"], cost["share"]) == (20.77, 38.77, 0.0, 20.77)
    undo(client, up)
    undo(client, r)
    p = person(client, cid, "Priya")
    assert (p["owes"], p["let_go"], p["paid"]) == (20.0, None, 0.0)


def test_the_cutoff_needs_both(client):
    cid, deps = bistro(client, 13.5, 38.0, whole=200.0, people=((KLEV, 15.0), ("Priya", 40.01)))
    mark(client, deps[0], cid)                       # $1.50 of $15.00: not more than 10%
    assert person(client, cid)["let_go"]["was"] == 15.0
    mark(client, deps[1], cid, "Priya")              # $2.01 short
    assert person(client, cid, "Priya")["owes"] == 2.01 and person(client, cid, "Priya")["let_go"] is None


def test_judged_on_everything_paid(client):
    """$10 of $20 isn't small; $10 then $9 is."""
    cid, (a, b) = bistro(client, 10.0, 9.0, whole=40.0, people=((KLEV, 20.0),))
    r = mark(client, a, cid)
    assert "let go" not in r["title"] and person(client, cid)["owes"] == 10.0
    r = mark(client, b, cid)
    p = person(client, cid)
    assert (p["owes"], p["let_go"]["was"], spent(client, cid)) == (0.0, 20.0, 21.0)
    undo(client, r)
    assert person(client, cid)["owes"] == 10.0 and person(client, cid)["let_go"] is None


@pytest.mark.parametrize("second,owes,gone,extra", [(1.0, 0.0, 0.0, None), (5.0, 0.0, 0.0, 4.0), (0.4, 0.0, 0.6, None)])
def test_the_second_payment_takes_the_small_one_back(client, second, owes, gone, extra):
    """$19 then $1: paid back; $19 then $5: $1 taken back, $4.00 asked."""
    cid, (a, b) = bistro(client, 19.0, second, whole=40.0, people=((KLEV, 20.0),))
    mark(client, a, cid)
    r = mark(client, b, cid)
    p = person(client, cid)
    assert p["owes"] == owes and round(20.0 - p["amount"], 2) == gone
    assert bool(p["let_go"]) is (gone > 0)
    assert ((p.get("extra") or {}).get("amount"), (p.get("extra") or {}).get("state")) == \
        (extra, "ask" if extra else None)
    assert spent(client, cid) == round(20.0 + gone, 2) and "you let go" not in r["title"]
    undo(client, r)
    p = person(client, cid)
    assert (p["let_go"]["was"], p["let_go"]["auto"], p["amount"], spent(client, cid)) == (20.0, True, 19.0, 21.0)
    assert "extra" not in p


def test_each_person_on_their_own_share(client):
    cid, deps = bistro(client, 19.0, (19.0, "Priya"), (19.0, "Alex"), whole=80.0,
                       people=((KLEV, 20.0), ("Priya", 20.0), ("Alex", 20.0)))
    for d, n in zip(deps, (KLEV, "Priya", "Alex")):
        mark(client, d, cid, n)
    assert spent(client, cid) == 23.0 and [person(client, cid, n)["owes"] for n in (KLEV, "Priya", "Alex")] == [0, 0, 0]


def test_undo_let_it_go_makes_the_share_hers(client):
    cid, (a, b) = bistro(client, 19.0, 0.5, whole=40.0, people=((KLEV, 20.0),))
    mark(client, a, cid)
    r = client.delete(f"/api/transactions/{cid}/split/let-go", json={"name": KLEV}).get_json()
    assert r["toast"] == f"{KLEV} owes you $1.00 again"
    p = person(client, cid)
    assert (p["owes"], p["let_go"], spent(client, cid)) == (1.0, None, 21.0)
    # Its Undo puts the let go back, Pearl's as it was (S-04s2).
    undo(client, r)
    p = person(client, cid)
    assert (p["owes"], p["let_go"]["auto"], spent(client, cid)) == (0.0, True, 21.0)
    client.delete(f"/api/transactions/{cid}/split/let-go", json={"name": KLEV})
    # $0.50 more: $0.50 left isn't settled again.
    mark(client, b, cid)
    assert person(client, cid)["owes"] == 0.5 and person(client, cid)["let_go"] is None


# ── $55 on a $40 share: the same from every path (bug 2) ──────────────────

@pytest.mark.parametrize("path,more", [("mark", {}), ("mark", {"amount": 40.0}), ("many", {}), ("link", {}),
                                       ("link", {"amount": 40.0}), ("parts", {}), ("parts", {"amount": 40.0}),
                                       ("paid-back", {}), ("paid-back", {"amount": 40.0}), ("credit", {}),
                                       ("cash", {}), ("app", {})])
def test_55_on_40_ends_the_same(client, path, more):
    cid, deps = bistro(client, 55.0)
    if path in BY_HAND:
        r = BY_HAND[path](client, cid, 55.0)
    else:
        r = LINKS[path](client, deps[0], cid, **more)
    p = person(client, cid)
    assert (p["paid"], p["owes"], p["over"], p["amount"]) == (55.0, 0.0, 15.0, 40.0)
    assert p["extra"] == {"state": "ask", "amount": 15.0, "owe": 0.0, "said": [], "line": None, "note": None, "moved": 0}
    assert spent(client, cid) == 40.0 and totals(client)[1] == 0.0, "never money in before she says"
    assert owed(client)["you_owe"] == [] and owed(client)["owes_you"] == []
    (q,) = review(client)
    assert q["over"] == {"charge": cid, "merchant": "Corner Bistro", "name": KLEV, "amount": 15.0, "share": 40.0,
                         "note": None, "word": None if path in BY_HAND else "e-Transfer"}
    assert not review(client, "rest")
    if path not in BY_HAND:
        assert q["txn"]["id"] == deps[0] and q["txn"]["amount"] == -55.0
    assert (r.get("toast") or r["title"]) == f"{KLEV} paid back $40.00 · $15.00 extra"
    undo(client, r)
    p = person(client, cid)
    assert (p["paid"], p["owes"]) == (0.0, 40.0) and review(client) == [] and "extra" not in p


def test_more_than_the_whole_purchase_is_all_theirs(client):
    for path in ("mark", "link"):
        cid, deps = bistro(client, 100.0)
        r = LINKS[path](client, deps[0], cid)
        assert person(client, cid)["extra"]["amount"] == 60.0 and spent(client, cid) == 40.0
        undo(client, r)


def test_part_of_it_stays_part_of_it(client):
    """$20 of $55, less than the share: she said part, and the rest is left to sort."""
    cid, (dep,) = bistro(client, 55.0)
    paid_back(client, dep, cid, amount=20.0)
    p = person(client, cid)
    assert (p["paid"], p["owes"]) == (20.0, 20.0) and review(client) == [] and review(client, "rest")


# ── Saying what the extra is (S-11e) ──────────────────────────────────────

@pytest.mark.parametrize("path", ["mark", "parts", "cash"])
@pytest.mark.parametrize("kind,line,toast,income", [
    ("overpaid", "You owe $15.00 back", f"You owe {KLEV} $15.00", 0.0),
    ("gift", "$15.00 gift", f"$15.00 from {KLEV} is a gift", 15.0),
    ("returned", "You sent $15.00 back", "You sent $15.00 back", 0.0)])
def test_said_in_one_gone_from_all(client, path, kind, line, toast, income):
    cid, deps = bistro(client, 55.0)
    cash(client, cid, 55.0) if path == "cash" else LINKS[path](client, deps[0], cid)
    r = say(client, cid, {"kind": kind, "amount": 15.0})
    p = person(client, cid)
    assert p["extra"]["line"] == line and r["toast"] == toast and p["owes"] == 0.0
    assert review(client) == [] and spent(client, cid) == 40.0 and totals(client)[1] == income
    you = owed(client)["you_owe"]
    assert (you[0]["total"] if you else 0.0) == (15.0 if kind == "overpaid" else 0.0)
    undo(client, r)
    p = person(client, cid)
    assert (p["paid"], p["extra"]["state"], p["extra"]["amount"]) == (55.0, "ask", 15.0)
    assert totals(client)[1] == 0.0 and len(review(client)) == 1 and owed(client)["you_owe"] == []


@pytest.mark.parametrize("path", ["mark", "parts", "cash"])
def test_two_pieces_and_the_rest_still_asked(client, path):
    """S-11e2, S-04o3: "$10.00 gift · $5.00 for Pizza Nova"."""
    cid, deps = bistro(client, 55.0)
    pizza = add(client, tx("PIZZA NOVA", 50.0, "Dining", when=day(19), merchant="Pizza Nova"))["PIZZA NOVA"]
    client.put(f"/api/transactions/{pizza}/split", json={"mode": "amount", "people": [{"name": KLEV, "amount": 20.10}]})
    cash(client, cid, 55.0) if path == "cash" else LINKS[path](client, deps[0], cid)
    one = say(client, cid, {"kind": "gift", "amount": 10.0})
    p = person(client, cid)
    assert (p["extra"]["state"], p["extra"]["amount"], p["extra"]["line"]) == ("ask", 5.0, "$10.00 gift")
    assert (p["extra"]["note"], p["extra"]["moved"]) == ("$10.00 was a gift.", 10.0), "S-11e2"
    assert review(client)[0]["over"]["amount"] == 5.0 and totals(client)[1] == 10.0
    two = say(client, cid, {"kind": "payback", "amount": 5.0, "charge": pizza})
    p = person(client, cid)
    assert p["extra"]["line"] == "$10.00 gift · $5.00 for Pizza Nova" and p["owes"] == 0.0
    assert review(client) == [] and person(client, pizza)["owes"] == 15.10 and totals(client)[1] == 10.0
    assert two["toast"] == f"{KLEV} paid back $5.00"
    undo(client, two)
    assert person(client, pizza)["owes"] == 20.10 and person(client, cid)["extra"]["amount"] == 5.0
    undo(client, one)
    assert person(client, cid)["extra"]["amount"] == 15.0 and totals(client)[1] == 0.0


def test_part_owed_back_part_asked(client):
    cid, (dep,) = bistro(client, 55.0)
    mark(client, dep, cid)
    say(client, cid, {"kind": "overpaid", "amount": 10.0})
    p = person(client, cid)
    assert (p["extra"]["state"], p["extra"]["amount"], p["extra"]["owe"]) == ("ask", 5.0, 10.0)
    assert owed(client)["you_owe"][0]["total"] == 10.0 and review(client)[0]["over"]["amount"] == 5.0


def test_a_share_the_extra_pays_settles_too(client):
    cid, (dep,) = bistro(client, 55.0)
    pizza = add(client, tx("PIZZA NOVA", 50.0, "Dining", when=day(19), merchant="Pizza Nova"))["PIZZA NOVA"]
    client.put(f"/api/transactions/{pizza}/split", json={"mode": "amount", "people": [{"name": KLEV, "amount": 15.5}]})
    mark(client, dep, cid)
    r = say(client, cid, {"kind": "payback", "amount": 15.0, "charge": pizza})
    assert person(client, pizza)["let_go"]["was"] == 15.5 and spent(client, pizza) == 35.0
    undo(client, r)
    assert person(client, pizza)["let_go"] is None and person(client, pizza)["owes"] == 15.5
    assert person(client, cid)["extra"]["amount"] == 15.0


def test_it_can_pay_a_purchase_that_isnt_split(client):
    """S-11e3 is PB-30: an unsplit purchase she ticks is split with them."""
    for path in ("mark", "parts"):
        cid, (dep,) = bistro(client, 55.0)
        taxi = add(client, tx("TAXI", 30.0, "Transport", when=day(18), merchant="Taxi"))["TAXI"]
        LINKS[path](client, dep, cid)
        r = say(client, cid, {"kind": "payback", "amount": 15.0, "charge": taxi, "new_split": True})
        assert spent(client, taxi) == 15.0 and person(client, taxi)["paid"] == 15.0
        undo(client, r)
        assert detail(client, taxi).get("splitting") is None and person(client, cid)["extra"]["amount"] == 15.0
        c2 = client.delete(f"/api/transactions/{cid}/paybacks/{dep}")
        if c2.status_code != 200:
            client.delete(f"/api/transactions/{dep}/parts")


def test_something_elses_tiles(client):
    cid, (dep,) = bistro(client, 55.0)
    mark(client, dep, cid)
    r = say(client, cid, {"kind": "income", "income_kind": "other", "amount": 15.0})
    assert person(client, cid)["extra"]["line"] == "$15.00 · Income" and totals(client)[1] == 15.0
    undo(client, r)
    assert totals(client)[1] == 0.0


@pytest.mark.parametrize("path", ["mark", "cash"])
@pytest.mark.parametrize("first", ["overpaid", "gift", "returned"])
def test_change_what_the_extra_is(client, path, first):
    """S-40e2."""
    cid, deps = bistro(client, 55.0)
    cash(client, cid, 55.0) if path == "cash" else mark(client, deps[0], cid)
    say(client, cid, {"kind": first, "amount": 15.0})
    second = "gift" if first != "gift" else "overpaid"
    r = say(client, cid, {"kind": second, "amount": 15.0}, again=True)
    p = person(client, cid)
    assert p["extra"]["line"] == ("$15.00 gift" if second == "gift" else "You owe $15.00 back")
    assert totals(client)[1] == (15.0 if second == "gift" else 0.0) and spent(client, cid) == 40.0
    undo(client, r)
    assert person(client, cid)["extra"]["line"] == {"overpaid": "You owe $15.00 back", "gift": "$15.00 gift",
                                                    "returned": "You sent $15.00 back"}[first]
    assert totals(client)[1] == (15.0 if first == "gift" else 0.0)


def test_cant_say_more_than_the_extra(client):
    cid, (dep,) = bistro(client, 55.0)
    mark(client, dep, cid)
    r = client.post(f"/api/transactions/{cid}/split/extra",
                    json={"name": KLEV, "pieces": [{"kind": "gift", "amount": 15.01}]})
    assert r.status_code == 400 and r.get_json()["error"] == "Only $15.00 is extra. Make it $15.00 or less."
    assert person(client, cid)["extra"]["state"] == "ask" and totals(client)[1] == 0.0


def test_a_small_extra_can_still_be_said(client):
    """S-40s2: "What's the extra $0.23?"."""
    cid, (dep,) = bistro(client, 20.23, whole=40.0, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    say(client, cid, {"kind": "overpaid", "amount": 0.23})
    assert owed(client)["you_owe"][0]["total"] == 0.23


def test_cash_says_its_extra_as_it_is_marked(client):
    """S-11c: said on the cash, so the card says it too."""
    cid, _ = bistro(client)
    r = cash(client, cid, 55.0, extra=[{"kind": "overpaid", "amount": 5.0}, {"kind": "gift", "amount": 10.0}])
    assert person(client, cid)["extra"]["line"] == "$10.00 gift · You owe $5.00 back"
    assert review(client) == [] and owed(client)["you_owe"][0]["total"] == 5.0
    undo(client, r)
    assert "extra" not in person(client, cid) and totals(client)[1] == 0.0


def test_a_second_overpayment_is_asked_about(client):
    """What she said of the first stands; the rest is a new question."""
    cid, (a, b) = bistro(client, 55.0, 10.0)
    mark(client, a, cid)
    say(client, cid, {"kind": "overpaid", "amount": 15.0})
    r = mark(client, b, cid)
    p = person(client, cid)
    assert (p["extra"]["state"], p["extra"]["owe"], p["extra"]["amount"]) == ("ask", 15.0, 10.0)
    assert owed(client)["you_owe"][0]["total"] == 15.0
    undo(client, r)
    assert person(client, cid)["extra"]["state"] == "owe"


# ── Linked before this ships ──────────────────────────────────────────────

def test_linked_before_reads_as_owe(client):
    cid, (dep, more) = bistro(client, 55.0, 10.0)
    client.st.link_payback(cid, dep, KLEV)
    p = person(client, cid)
    assert (p["extra"]["state"], p["extra"]["owe"]) == ("owe", 15.0) and review(client) == []
    assert owed(client)["you_owe"][0]["total"] == 15.0
    # A new payment is asked about; the old $15.00 stays under You owe.
    mark(client, more, cid)
    p = person(client, cid)
    assert (p["extra"]["state"], p["extra"]["owe"], p["extra"]["amount"]) == ("ask", 15.0, 10.0)


def test_short_before_is_still_owed(client):
    cid, (dep,) = bistro(client, 19.0, whole=40.0, people=((KLEV, 20.0),))
    client.st.link_payback(cid, dep, KLEV)
    assert person(client, cid)["owes"] == 1.0 and person(client, cid)["let_go"] is None


# ── After a let go (S-04g2) ───────────────────────────────────────────────

@pytest.mark.parametrize("path", [*LINKS, *BY_HAND])
@pytest.mark.parametrize("second,gone,extra", [(15.0, 0.0, 0.0), (10.0, 5.0, 0.0), (20.0, 0.0, 5.0)])
def test_paying_takes_the_let_go_back(client, path, second, gone, extra):
    cid, deps = bistro(client, 25.0, second)
    mark(client, deps[0], cid)
    let_go(client, cid)
    assert spent(client, cid) == 55.0 and detail(client, cid)["cost"]["share"] == 55.0, "bug 6"
    r = BY_HAND[path](client, cid, second) if path in BY_HAND else LINKS[path](client, deps[1], cid)
    p = person(client, cid)
    assert p["owes"] == 0.0 and round(40.0 - p["amount"], 2) == gone and bool(p["let_go"]) is (gone > 0)
    assert spent(client, cid) == 40.0 + gone and owed(client)["you_owe"] == [], "bug 5"
    assert (p.get("extra") or {}).get("amount", 0.0) == extra
    said = r.get("toast") or r["title"]
    assert said == (f"{KLEV} paid back the $15.00 you let go" if gone == 0 else f"{KLEV} paid back $10.00")
    undo(client, r)
    p = person(client, cid)
    assert (p["amount"], p["let_go"]["was"], p["let_go"].get("auto")) == (25.0, 40.0, None)
    assert spent(client, cid) == 55.0 and "extra" not in p


def test_a_let_go_she_said_is_never_grown_by_pearl(client):
    cid, (a, b) = bistro(client, 25.0, 14.5)
    mark(client, a, cid)
    let_go(client, cid)
    mark(client, b, cid)
    p = person(client, cid)
    assert (p["amount"], p["let_go"]["was"], p["let_go"].get("auto")) == (39.5, 40.0, None)
    assert spent(client, cid) == 40.5


def test_above_the_cutoff_nothing_is_forgiven(client):
    cid, (dep,) = bistro(client, 25.0)
    mark(client, dep, cid)
    p = person(client, cid)
    assert (p["owes"], p["let_go"], spent(client, cid)) == (15.0, None, 55.0)


# ── Unlinking puts the let go right (bug 3) ───────────────────────────────

@pytest.mark.parametrize("pearls", [True, False])
@pytest.mark.parametrize("path", ["mark", "parts", "cash"])
def test_unlinking_takes_the_let_go_back(client, path, pearls):
    """Unlinking $19.00 after a $1.00 let go: owes $20.00, and her row isn't
    $61.00 of $80.00."""
    amount = 19.0 if pearls else 12.0
    cid, (dep,) = bistro(client, amount, people=((KLEV, 20.0), ("Priya", 20.0)))
    r = cash(client, cid, amount) if path == "cash" else LINKS[path](client, dep, cid)
    if not pearls:
        let_go(client, cid)
    was = person(client, cid)
    (row,) = was["links"]
    assert row["sheet"]["line"].startswith(f"{KLEV} owes you $20.00 again on Corner Bistro.")
    if path == "cash":
        r = client.delete(f"/api/transactions/{cid}/split/cash/{row['cash_id']}").get_json()
    else:
        r = client.delete(f"/api/transactions/{cid}/paybacks/{row['inflow']}").get_json()
    assert r["title"] == f"Unlinked · {KLEV} owes $20.00"
    p = person(client, cid)
    assert (p["owes"], p["let_go"], p["paid"]) == (20.0, None, 0.0)
    assert spent(client, cid) == 80.0 and detail(client, cid)["splitting"]["you"] == 40.0
    undo(client, r)
    p = person(client, cid)
    assert (p["paid"], p["owes"], p["amount"], p["let_go"]) == (was["paid"], 0.0, was["amount"], was["let_go"])


@pytest.mark.parametrize("path", ["mark", "parts"])
def test_unlinking_an_overpayment(client, path):
    """S-34kr1o: "owes you $40.00 again", never $55.00; the $55.00 goes back."""
    cid, (dep,) = bistro(client, 55.0)
    LINKS[path](client, dep, cid)
    (row,) = person(client, cid)["links"]
    assert row["sheet"]["line"] in (
        f"{KLEV} owes you $40.00 again on Corner Bistro. The $55.00 goes back to Needs a look.",
        f"{KLEV} owes you $40.00 again on Corner Bistro. This $55.00 goes back to Needs a look.")
    r = client.delete(f"/api/transactions/{cid}/paybacks/{row['inflow']}").get_json()
    p = person(client, cid)
    assert (p["owes"], p.get("extra")) == (40.0, None) and review(client) == []
    undo(client, r)
    assert person(client, cid)["extra"]["state"] == "ask"


def test_unlinking_one_of_two_says_what_it_covers(client):
    cid, (a, b) = bistro(client, 25.0, 30.0)
    mark(client, a, cid)
    mark(client, b, cid)
    lines = {x["amount"]: x["sheet"]["line"] for x in person(client, cid)["links"]}
    assert f"{KLEV} owes you $15.00 again" in lines[30.0] and f"{KLEV} owes you $10.00 again" in lines[25.0]
    client.delete(f"/api/transactions/{cid}/paybacks/{b}")
    p = person(client, cid)
    assert (p["owes"], p.get("extra")) == (15.0, None)


def test_taking_the_parts_apart_takes_the_let_go_back(client):
    cid, (dep,) = bistro(client, 19.0, whole=40.0, people=((KLEV, 20.0),))
    parts(client, dep, cid)
    client.delete(f"/api/transactions/{dep}/parts")
    p = person(client, cid)
    assert (p["owes"], p["let_go"], spent(client, cid)) == (20.0, None, 40.0)


def test_calling_the_payment_something_else_takes_the_let_go_back(client):
    cid, (dep,) = bistro(client, 19.0, whole=40.0, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    r = client.post(f"/api/transactions/{dep}/mark", json={"case": "pay", "income_kind": "gifts"}).get_json()
    p = person(client, cid)
    assert (p["owes"], p["let_go"], spent(client, cid)) == (20.0, None, 40.0)
    undo(client, r)
    assert person(client, cid)["let_go"]["auto"] is True and person(client, cid)["paid"] == 19.0


# ── Changing the share, and refunds ───────────────────────────────────────

def edit(c, cid, *people):
    r = c.put(f"/api/transactions/{cid}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": a} for n, a in people]})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


def test_changing_the_share_takes_the_small_let_go_back(client):
    """$20.00 to $40.00 after a $1.00 let go was $21.00 let go, unsaid."""
    cid, (dep,) = bistro(client, 19.0, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    r = edit(client, cid, (KLEV, 40.0))
    p = person(client, cid)
    assert (p["amount"], p["owes"], p["let_go"]) == (40.0, 21.0, None)
    undo(client, r)
    assert person(client, cid)["let_go"] == {"was": 20.0, "day": p and TODAY.isoformat(), "auto": True}
    # Back down to $19.50: an edited share never settles anything.
    edit(client, cid, (KLEV, 19.5))
    assert person(client, cid)["owes"] == 0.5 and person(client, cid)["let_go"] is None


def test_changing_someone_elses_share_leaves_it(client):
    cid, (dep,) = bistro(client, 19.0, people=((KLEV, 20.0), ("Priya", 20.0)))
    mark(client, dep, cid)
    edit(client, cid, (KLEV, 20.0), ("Priya", 30.0))
    p = person(client, cid)
    assert (p["owes"], p["let_go"]["was"], p["let_go"]["auto"], p["amount"]) == (0.0, 20.0, True, 19.0)


@pytest.mark.parametrize("to,owes,gone", [(50.0, 10.0, 15.0), (30.0, 0.0, 5.0), (25.0, 0.0, 0.0)])
def test_a_let_go_she_said_never_grows(client, to, owes, gone):
    cid, (dep,) = bistro(client, 25.0)
    mark(client, dep, cid)
    let_go(client, cid)
    edit(client, cid, (KLEV, to))
    p = person(client, cid)
    assert p["owes"] == owes and round(((p["let_go"] or {}).get("was") or p["amount"]) - p["amount"], 2) == gone


def test_an_edit_over_what_they_paid_is_owed_as_today(client):
    """SPLIT-02: changing the share stays under Change share."""
    cid, (dep,) = bistro(client, 40.0)
    mark(client, dep, cid)
    edit(client, cid, (KLEV, 25.0))
    assert owed(client)["you_owe"][0]["total"] == 15.0 and review(client) == []


def test_an_edit_never_hides_a_small_one_grown_big(client):
    cid, (dep,) = bistro(client, 20.23, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    edit(client, cid, (KLEV, 10.0))
    assert person(client, cid)["extra"]["state"] == "ask" and person(client, cid)["extra"]["amount"] == 10.23


def test_a_refund_never_settles_anything(client):
    cid, (dep,) = bistro(client, 19.0, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    shop = add(client, tx("CORNER BISTRO REFUND", -8.0, when=day(2), merchant="Corner Bistro"))["CORNER BISTRO REFUND"]
    r = client.post(f"/api/transactions/{shop}/mark", json={"case": "refund", "charge": cid}).get_json()
    p = person(client, cid)
    # $20.00 less a tenth is $18.00; they paid $19.00. Pearl's let go is back.
    assert (p["amount"], p["let_go"], p["over"], p["owes"]) == (18.0, None, 1.0, 0.0)
    undo(client, r)
    p = person(client, cid)
    assert (p["amount"], p["let_go"]["auto"], p["owes"]) == (19.0, True, 0.0)


def test_a_refund_leaving_a_dollar_isnt_settled(client):
    cid, (dep,) = bistro(client, 17.0, people=((KLEV, 20.0),))
    mark(client, dep, cid)
    shop = add(client, tx("CORNER BISTRO REFUND", -8.0, when=day(2), merchant="Corner Bistro"))["CORNER BISTRO REFUND"]
    client.post(f"/api/transactions/{shop}/mark", json={"case": "refund", "charge": cid})
    assert person(client, cid)["owes"] == 1.0 and person(client, cid)["let_go"] is None


def test_letting_go_after_a_refund_lets_go_what_they_owe(client):
    cid, (dep,) = bistro(client, 10.0)
    shop = add(client, tx("CORNER BISTRO REFUND", -40.0, when=day(2), merchant="Corner Bistro"))["CORNER BISTRO REFUND"]
    client.post(f"/api/transactions/{shop}/mark", json={"case": "refund", "charge": cid})
    mark(client, dep, cid)
    let_go(client, cid)
    p = person(client, cid)
    assert (p["amount"], p["owes"], p["over"]) == (10.0, 0.0, 0.0) and owed(client)["you_owe"] == []


def test_paid_before_it_was_split_is_asked(client):
    i = add(client, tx("CORNER BISTRO", 80.0, "Dining", when=day(20), merchant="Corner Bistro"),
            tx("E-TRANSFER", -55.0, when=day(10), merchant=KLEV))
    client.st.link_payback(i["CORNER BISTRO"], i["E-TRANSFER"], KLEV)
    edit(client, i["CORNER BISTRO"], (KLEV, 40.0))
    assert person(client, i["CORNER BISTRO"])["extra"]["state"] == "ask" and owed(client)["you_owe"] == []


# ── One deposit over several shares ───────────────────────────────────────

def two_shares(c, pay, first=40.0, second=19.77):
    i = add(c, tx("PIZZA NOVA", 80.0, "Dining", when=day(21), merchant="Pizza Nova"),
            tx("CORNER BISTRO", 59.54, "Dining", when=day(20), merchant="Corner Bistro"),
            tx("E-TRANSFER FROM KLEV", -pay, when=day(10), merchant=KLEV))
    for cid, amount in ((i["PIZZA NOVA"], first), (i["CORNER BISTRO"], second)):
        edit(c, cid, (KLEV, amount))
    return i["PIZZA NOVA"], i["CORNER BISTRO"], i["E-TRANSFER FROM KLEV"]


def pay_two(c, how, dep, a, b, x, y):
    if how == "parts":
        r = c.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": x, "charge": a, "person": KLEV},
            {"kind": "payback", "amount": y, "charge": b, "person": KLEV}]})
    else:
        r = c.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "person": KLEV,
                                                          "charges": [{"id": a}, {"id": b}]})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


@pytest.mark.parametrize("how", ["parts", "marks"])
def test_a_few_cents_over_two_shares(client, how):
    """PB-41s: $60.00 over $59.77, "Extra $0.23" on the deposit only."""
    a, b, dep = two_shares(client, 60.0)
    r = pay_two(client, how, dep, a, b, 40.0, 19.77)
    assert [person(client, c)["owes"] for c in (a, b)] == [0.0, 0.0]
    assert "extra" not in person(client, a) and "extra" not in person(client, b)
    rest = [p for p in detail(client, dep)["parts"] if p["kind"] == "rest"]
    assert [(p["amount"], p["small"]) for p in rest] == [(0.23, True)]
    assert review(client, "rest") == [] and totals(client)[1] == 0.0 and owed(client)["you_owe"] == []
    assert r["title"] == f"{KLEV} paid back 2 purchases · $59.77 · $0.23 extra"
    undo(client, r)
    assert [person(client, c)["owes"] for c in (a, b)] == [40.0, 19.77] and "parts" not in detail(client, dep)


@pytest.mark.parametrize("how", ["parts", "marks"])
def test_short_over_two_is_judged_on_the_last(client, how):
    a, b, dep = two_shares(client, 59.0, second=20.0)
    r = pay_two(client, how, dep, a, b, 40.0, 19.0)
    assert person(client, b)["let_go"]["was"] == 20.0 and person(client, b)["owes"] == 0.0
    assert r["title"] == f"{KLEV} paid back 2 purchases · $59.00 · $1.00 let go"
    undo(client, r)
    assert (person(client, b)["owes"], person(client, b)["let_go"]) == (20.0, None)


def test_only_the_last_share_is_let_go(client):
    a, b, dep = two_shares(client, 58.0, second=20.0)
    pay_two(client, "parts", dep, a, b, 39.0, 19.0)
    assert person(client, a)["owes"] == 1.0 and person(client, b)["owes"] == 0.0


@pytest.mark.parametrize("how", ["parts", "marks"])
def test_more_over_two_shares_is_still_a_question(client, how):
    a, b, dep = two_shares(client, 75.0)
    if how == "parts":
        client.post(f"/api/transactions/{dep}/parts", json={"later": True, "parts": [
            {"kind": "payback", "amount": 40.0, "charge": a, "person": KLEV},
            {"kind": "payback", "amount": 19.77, "charge": b, "person": KLEV}]})
    else:
        pay_two(client, "marks", dep, a, b, 0, 0)
    assert totals(client)[1] == 0.0 and [q["txn"]["amount"] for q in review(client, "rest")] == [-15.23]


# ── Two people, one first name (bug 1) ────────────────────────────────────

def test_two_georgias_on_one_split(client):
    cid, (a, b) = bistro(client, 19.0, (55.0, PAPPAS), whole=120.0, people=((KLEV, 20.0), (PAPPAS, 40.0)))
    mark(client, a, cid, KLEV)
    mark(client, b, cid, PAPPAS)
    k, p = person(client, cid, KLEV), person(client, cid, PAPPAS)
    assert (k["paid"], k["let_go"]["was"], p["paid"], p["extra"]["amount"]) == (19.0, 20.0, 55.0, 15.0)
    r = say(client, cid, {"kind": "overpaid", "amount": 15.0}, name=PAPPAS)
    assert r["toast"] == f"You owe {PAPPAS} $15.00" and "extra" not in person(client, cid, KLEV)
    assert [(r["name"], r["total"]) for r in owed(client)["you_owe"]] == [(PAPPAS, 15.0)]
    client.delete(f"/api/transactions/{cid}/split/let-go", json={"name": KLEV})
    assert person(client, cid, KLEV)["owes"] == 1.0 and person(client, cid, PAPPAS)["owes"] == 0.0


def test_cash_goes_to_the_georgia_it_is_for(client):
    cid, _ = bistro(client, whole=120.0, people=((KLEV, 40.0), (PAPPAS, 40.0)))
    cash(client, cid, 39.0, PAPPAS)
    assert (person(client, cid, PAPPAS)["owes"], person(client, cid, KLEV)["owes"]) == (0.0, 40.0)


def test_a_payback_never_adds_its_sender(client):
    cid, (dep,) = bistro(client, (55.0, "Jordan Lee"))
    r = client.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": cid})
    assert r.status_code == 409 and [p["name"] for p in detail(client, cid)["splitting"]["people"]] == [KLEV]


def test_a_place_a_payback_made_has_no_share_to_go_over(client):
    """THL-260: someone the payment itself put on the split grows with it."""
    i = add(client, tx("CORNER BISTRO", 80.0, "Dining", when=day(20), merchant="Corner Bistro"),
            tx("E-TRANSFER 1", -30.0, when=day(10), merchant=KLEV), tx("E-TRANSFER 2", -5.0, when=day(9), merchant=KLEV))
    cid = i["CORNER BISTRO"]
    mark(client, i["E-TRANSFER 1"], cid)
    mark(client, i["E-TRANSFER 2"], cid)
    p = person(client, cid)
    assert (p["amount"], p["paid"], p.get("extra"), spent(client, cid)) == (35.0, 35.0, None, 45.0)


def test_a_not_sure_yet_split_settles_nothing(client):
    cid, (dep,) = bistro(client, 19.0, whole=40.0, people=((KLEV, 20.0),))
    client.put(f"/api/transactions/{cid}/split", json={"mode": "unknown", "people": [{"name": KLEV}]})
    mark(client, dep, cid)
    assert person(client, cid)["let_go"] is None and "extra" not in person(client, cid)


def test_work_paying_all_of_it_forgives_nobody(client):
    cid, _ = bistro(client)
    work = add(client, tx("ACME", -79.0, when=day(5), merchant="Acme"))["ACME"]
    client.post(f"/api/transactions/{work}/mark", json={"case": "reimbursement", "charge": cid})
    assert person(client, cid)["owes"] == 1.0 and person(client, cid)["let_go"] is None


# ── Asking about it ───────────────────────────────────────────────────────

def question(c, dep):
    item = next(q for q in c.get("/api/review").get_json()["money_in"] if q["txn"]["id"] == dep)
    return item, item["payback"]["tiles"][0]


@pytest.mark.parametrize("pay,share,compare", [
    (55.0, 40.0, "$40.00 of $55.00 · $15.00 extra"),             # PQ-03o, bug 7
    (19.0, 20.0, "$19.00 of $20.00 · $1.00 let go"),             # PQ-03s
    (20.0, 19.77, "$19.77 of $20.00 · $0.23 extra"),
    (25.0, 40.0, f"$25.00 of {KLEV}’s $40.00 · {KLEV} still owes $15.00")])
def test_the_payback_question_says_it_first(client, pay, share, compare):
    cid, (dep,) = bistro(client, pay, people=((KLEV, share),))
    item, tile = question(client, dep)
    assert (tile["charge"], tile["compare"]) == (cid, compare)
    assert tile["title"] == f"Corner Bistro · {KLEV}’s share"
    # PQ-03c's toast is what marking it says (S-44s, S-44s2).
    if " extra" in compare or " let go" in compare:
        assert mark(client, dep, cid)["title"] == tile["toast"]


def test_a_share_she_undid_isnt_promised_a_let_go(client):
    cid, (dep,) = bistro(client, 19.0, people=((KLEV, 20.0),))
    client.st.set_split_extra(cid, KLEV, {"hers": True})
    assert question(client, dep)[1]["compare"] == f"$19.00 of {KLEV}’s $20.00 · {KLEV} still owes $1.00"


def test_money_after_a_let_go_is_asked_never_done(client):
    """S-21g, T-99g: "You let $15.00 go on Corner Bistro."."""
    cid, (a, b) = bistro(client, 25.0, 15.0)
    mark(client, a, cid)
    let_go(client, cid)
    item, tile = question(client, b)
    assert item["guess"]["action"] == "split" and item["guess"]["split"]["let_go"] is True
    assert item["reason"] == "You let $15.00 go on Corner Bistro." and item["guess"]["split"]["owes"] == 15.0
    assert tile["charge"] == cid and tile["compare"] == "You let $15.00 go"
    assert person(client, cid)["let_go"]["was"] == 40.0, "a question, nothing done"
    assert item["pair"]["evidence"] == "You let $15.00 go on Corner Bistro."
    r = client.post(f"/api/review/pair/{b}").get_json()
    assert person(client, cid)["let_go"] is None and spent(client, cid) == 40.0
    undo(client, r)
    assert person(client, cid)["let_go"]["was"] == 40.0


def test_a_second_payment_is_asked_about(client):
    """S-21p, T-99p."""
    cid, (a, b) = bistro(client, 25.0, 15.0)
    mark(client, a, cid)
    item, _ = question(client, b)
    assert (item["split"]["owes"], item["split"]["merchant"]) == (15.0, "Corner Bistro")
    assert item["pair"]["question"] == f"{KLEV} paying you back for Corner Bistro?"
    assert item["pair"]["evidence"] == f"{KLEV} owes you $15.00 for Corner Bistro."


@pytest.mark.parametrize("path", ["mark", "parts"])
def test_the_deposits_page_shows_its_extra(client, path):
    """PB-41o."""
    cid, (dep,) = bistro(client, 55.0)
    LINKS[path](client, dep, cid)
    d = detail(client, dep)
    over = d["repays_charge"]["over"] if path == "mark" else d["parts"][0]["over"]
    assert (over["name"], over["back"], over["extra"], over["state"], over["charge"]) == (KLEV, 40.0, 15.0, "ask", cid)
    # Bug 3, from the deposit's own Unlink.
    if path == "mark":
        assert "owes you $40.00 again on Corner Bistro" in d["repays_charge"]["link"]["sheet"]["line"]
    else:
        assert d["parts"][0]["again"] == 40.0


@pytest.mark.parametrize("path", ["mark", "parts"])
def test_unlinking_a_small_one_from_the_deposit(client, path):
    cid, (dep,) = bistro(client, 19.0, people=((KLEV, 20.0),))
    LINKS[path](client, dep, cid)
    d = detail(client, dep)
    if path == "mark":
        assert "owes you $20.00 again" in d["repays_charge"]["link"]["sheet"]["line"]
    else:
        assert d["parts"][0]["again"] == 20.0


def test_a_small_let_go_of_pearls_isnt_a_question(client):
    cid, (a, b) = bistro(client, 19.0, 1.0, people=((KLEV, 20.0),))
    mark(client, a, cid)
    item = next(q for q in client.get("/api/review").get_json()["money_in"] if q["txn"]["id"] == b)
    assert (item["guess"].get("split") or {}).get("let_go") is None


def test_skipping_the_extra_and_the_list_count(client):
    cid, (dep,) = bistro(client, 55.0)
    before = client.get("/api/review").get_json()["count"]
    mark(client, dep, cid)
    r = client.get("/api/review").get_json()
    assert r["count"] == before, "one question for the payment, before and after"
    assert [q["key"] for q in r["money_in"] if q.get("over")] == [f"over:{cid}:{KLEV}"]


def test_paid_back_this_month_says_what_paid_the_share(client):
    """S-14o: +$40.00 of the $55.00."""
    this = TODAY.isoformat()
    i = add(client, tx("CORNER BISTRO", 80.0, "Dining", when=this, merchant="Corner Bistro"),
            tx("E-TRANSFER", -55.0, when=this, merchant=KLEV))
    edit(client, i["CORNER BISTRO"], (KLEV, 40.0))
    mark(client, i["E-TRANSFER"], i["CORNER BISTRO"])
    assert [r["amount"] for r in owed(client)["paid_back"]] == [40.0]


# ── Storing it ────────────────────────────────────────────────────────────

def test_start_over_and_delete_clear_it(client):
    from finance import store as store_mod
    cid, (a, b) = bistro(client, 19.0, 55.0, people=((KLEV, 20.0), ("Priya", 40.0)))
    mark(client, a, cid)
    mark(client, b, cid, "Priya")
    assert "txn_split_extra" in store_mod._ROW_TABLES
    with client.st.conn() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM txn_split_extra").fetchone()["n"] == 1
    client.delete(f"/api/transactions/{cid}/split")
    with client.st.conn() as c:
        assert c.execute("SELECT COUNT(*) AS n FROM txn_split_extra").fetchone()["n"] == 0
    client.st.set_split_extra(cid, "Priya", {"state": "ask"})
    client.st.reset()
    with client.st.conn() as c:
        for table in ("txn_split_extra", "txn_split_let_go"):
            assert c.execute(f"SELECT COUNT(*) AS n FROM {table}").fetchone()["n"] == 0


def test_a_database_from_before_gets_the_column(tmp_path):
    import sqlite3

    from finance import db
    from finance.store import Store
    if db.database_url():
        pytest.skip("SQLite only")
    path = str(tmp_path / "old.db")
    with sqlite3.connect(path) as c:
        c.execute("CREATE TABLE txn_split_let_go (txn_id TEXT NOT NULL, name TEXT NOT NULL, was REAL NOT NULL, "
                  "day TEXT NOT NULL, PRIMARY KEY (txn_id, name))")
        c.execute("INSERT INTO txn_split_let_go VALUES ('x', 'Sam', 40, '2026-11-01')")
    st = Store(path)
    st.set_split("x", "amount", [{"name": "Sam", "amount": 25}], True)
    assert st.splits()["x"]["people"][0]["let_go"] == {"was": 40.0, "day": "2026-11-01"}
    st.set_let_go("x", "Sam", 40, "2026-11-01", auto=True)
    assert st.splits()["x"]["people"][0]["let_go"]["auto"] is True


def test_undo_of_removing_the_split_puts_it_back(client):
    cid, (dep,) = bistro(client, 55.0)
    mark(client, dep, cid)
    r = client.delete(f"/api/transactions/{cid}/split").get_json()
    undo(client, r)
    assert person(client, cid)["extra"]["state"] == "ask"


@pytest.mark.parametrize("pay", [15.0, 30.0, 14.0])
def test_which_payment_suggests_theirs_whatever_the_amount(client, pay):
    """S-06rb2: Georgia Pappas's money isn't Georgia Klev's."""
    cid, deps = bistro(client, 25.0, pay, (25.0, PAPPAS), whole=120.0, people=((KLEV, 40.0), (PAPPAS, 40.0)))
    mark(client, deps[0], cid)
    for after in (False, True):
        rows = client.get(f"/api/transactions/{cid}/paybacks", query_string={"person": KLEV}).get_json()["candidates"]
        assert [r["id"] for r in rows if r["likely"]] == [deps[1]] and deps[2] in [r["id"] for r in rows]
        if not after:
            let_go(client, cid)


# ── Every path that links runs it ─────────────────────────────────────────

# Each function in finance/ that links money to a share, and how it settles:
# "settles" calls over_under.settle itself (or save_parts, which does);
# anything else says why it needn't.
SETTLES = "settles"
CALLERS = {
    "marks.py:apply": SETTLES,
    "marks.py:_payback_many": SETTLES,
    "marks.py:_payback_shares": SETTLES,
    "marks.py:_link_reimbursing": "work paying her share, or an expense",
    "marks.py:_link_your_share": "her own share",
    "marks.py:undo_marks": "Undo puts back what was stored",
    "parts.py:apply": "saved by the endpoint, which settles",
    "parts.py:_your_share_part": "a refund; never settles",
    "parts.py:_reimburse": "work",
    "parts.py:_hold_cash": "cash already recorded, cut in two",
    "parts_api.py:save_parts": SETTLES,
    "parts_api.py:split_answer": "puts a gift back on the share, and stores her answer",
    "parts_api.py:split_cash": SETTLES,
    "parts_api.py:_record_extra": "split_cash settles",
    "parts_api.py:_say_extra": SETTLES,
    "parts_api.py:_say_plan": "_say_extra settles",
    "parts_api.py:credit_payback": SETTLES,
    "parts_api.py:_relink": "its callers settle",
    "parts_api.py:paid_back_from_purchase": SETTLES,
    "parts_api.py:paid_back_take": SETTLES,
    "parts_api.py:change_payback": SETTLES,
    "parts_api.py:split_into_parts": "through save_parts",
    "parts_api.py:_joint_payback": "through save_parts",
    "marks_api.py:mark_transaction": "through marks.apply and save_parts",
    "api.py:add_payback": SETTLES,
    "api.py:_settle_extra": "her answer, stored by over_under.say",
    "api.py:_edit_split": "an edit never settles anything",
    "unlink.py:put_back": "puts a deposit's parts back",
    "unlink.py:unlink_payback": "takes one off",
}
LINKERS = {"link_payback", "add_split_cash", "set_payback_more", "set_payback_person", "_relink", "save_parts",
           "_record_extra"}


def callers():
    out = {}
    for path in sorted((ROOT / "finance").glob("*.py")):
        if path.name == "store.py":
            continue
        for fn in ast.parse(path.read_text()).body:
            if not isinstance(fn, ast.FunctionDef):
                continue
            called = set()
            for n in ast.walk(fn):
                if isinstance(n, ast.Call):
                    f = n.func
                    name = f.attr if isinstance(f, ast.Attribute) else getattr(f, "id", "")
                    called.add(name)
                    if name == "apply" and isinstance(f, ast.Attribute) and getattr(f.value, "id", "") == "dp":
                        called.add("dp.apply")
            if called & (LINKERS | {"dp.apply"}):
                out[f"{path.name}:{fn.name}"] = called
    return out


def test_every_path_that_links_settles():
    found = callers()
    new = sorted(set(found) - set(CALLERS))
    assert not new, f"{new} links money to a share: run over_under.settle after it, and list it in CALLERS"
    assert not set(CALLERS) - set(found), sorted(set(CALLERS) - set(found))
    for where, how in CALLERS.items():
        if how == SETTLES:
            assert found[where] & {"settle", "save_parts"}, f"{where} links without settling"


def test_names_are_the_shared_helpers():
    src = (ROOT / "finance/over_under.py").read_text()
    assert "sp.pick(" in src and "same_person" not in src and ".split()[0]" not in src
