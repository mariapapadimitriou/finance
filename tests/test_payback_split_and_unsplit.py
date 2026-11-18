"""One payback over split and unsplit purchases (product owner, 2026-11-18).

"If transaction C pays back transaction A and B, and for transaction A, I
marked it as a split where someone needs to pay me back, and transaction B,
I haven't marked anything. Both A and B should show up when I say C paid
back. For A it shows the splits, and for B I should be able to select it
and mark how much of B the repayment paid for."

Server side only (the iPhone UI waits on a design):

* GET …/owing?person=Sam lists Sam's open shares (`items`, as before) and
  her other recent spending that isn't split (`unsplit`), plus `q` matches.
* POST …/parts takes both in one save: a payback part with `new_split: true`
  on an unsplit purchase splits it with exactly that person, their share X
  paid in full by this money, hers the rest.
* One Undo puts back the credits and the splits it made.

Demo data only, through the endpoints the app calls.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import spend_amount
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def day(n: int) -> str:
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(desc, amount, account="chq", when=None, merchant=None, category="", kind="depository"):
    names = {"chq": "Chequing ••4417", "amex": "Amex Cobalt ••1001"}
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name=names.get(account, account),
                       raw={"account_type": kind})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "unsplit.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        yield c


def add(c, account, *rows):
    ingest(c.st, IngestResult(list(rows), account))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def numbers(c):
    lst = ok(c.get("/api/transactions/list", query_string={"month": MONTH, "limit": 500}))
    return {"spent": lst["month_totals"]["spent"], "allowance": ok(c.get("/api/home"))["safe_to_spend"]["amount"]}


def world(c):
    rows = {t.fingerprint: (t.category, t.category_source, t.my_share, t.share_set, t.excluded, t.repays,
                            tuple(t.repays_all or ()))
            for t in c.st.all_transactions()}
    return {"rows": rows, "splits": c.st.splits(), "parts": c.st.parts(), "payer": c.st.payback_people(),
            "kinds": c.st.payback_kinds(), "numbers": numbers(c)}


def cost(c, tid) -> float:
    return round(spend_amount(c.st.get_transaction(tid)), 2)


def owes(c, tid):
    return {p["name"]: p["owes"] for p in ok(c.get(f"/api/transactions/{tid}"))["splitting"]["people"]}


def owing(c, dep, person="Sam", q=None):
    args = {"person": person, **({"q": q} if q else {})}
    return ok(c.get(f"/api/transactions/{dep}/owing", query_string=args))


def parts(c, dep, body):
    return c.post(f"/api/transactions/{dep}/parts", json=body)


def setup(c, sent=75.0, split_a=True, jo=True):
    """A: Loblaws $90 split evenly with Sam ($45 his). B: Pizza Nova $60,
    not split. Noise that must never be offered for B: a transfer, income,
    a split purchase with someone else. C: Sam's e-Transfer."""
    i = add(c, "amex",
            row("LOBLAWS", 90.0, "amex", when=day(6), category="Groceries", kind="credit"),
            row("PIZZA NOVA", 60.0, "amex", when=day(4), category="Dining", kind="credit"),
            row("COSTCO", 120.0, "amex", when=day(5), category="Shopping", kind="credit"))
    if split_a:
        ok(c.put(f"/api/transactions/{i['LOBLAWS']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 45.0}]}))
    if jo:
        ok(c.put(f"/api/transactions/{i['COSTCO']}/split", json={
            "mode": "amount", "people": [{"name": "Jo", "amount": 60.0}]}))
    j = add(c, "chq",
            row("TFR-TO SAVINGS", 200.0, when=day(4), category="Transfers"),
            row("PAYROLL NORTHWIND", -2000.0, when=day(5), category="Income"),
            row("INTERAC E-TRANSFER FROM SAM LEE", -sent, when=day(1), merchant="Sam Lee"))
    return i["LOBLAWS"], i["PIZZA NOVA"], i["COSTCO"], j["INTERAC E-TRANSFER FROM SAM LEE"], j


# ── Candidates ──────────────────────────────────────────────────────────

def test_owing_lists_shares_and_unsplit_purchases(client):
    a, b, costco, dep, j = setup(client)
    r = owing(client, dep)
    assert r["from"] == "Sam"
    assert [i["id"] for i in r["items"] if i["theirs"]] == [a]
    unsplit = r["unsplit"]
    ids = [u["id"] for u in unsplit]
    assert b in ids
    # Never: anything split (hers with Sam or with Jo), transfers, income, the money itself.
    assert a not in ids and costco not in ids and dep not in ids
    assert j["TFR-TO SAVINGS"] not in ids and j["PAYROLL NORTHWIND"] not in ids
    pizza = next(u for u in unsplit if u["id"] == b)
    assert pizza == {"id": b, "merchant": "PIZZA NOVA", "date": day(4), "amount": 60.0,
                     "category": "Dining", "pending": False, "max": 60.0, "query": False}


def test_unsplit_ranks_close_in_amount_first_and_q_finds_older(client):
    a, b, costco, dep, _ = setup(client, sent=30.0)
    add(client, "amex",
        row("UBER EATS", 31.0, "amex", when=day(5), category="Dining", kind="credit"),
        row("OLD BOOKSHOP", 30.0, "amex", when=(TODAY - timedelta(days=200)).isoformat(),
            category="Shopping", kind="credit"))
    ids = [u["id"] for u in owing(client, dep)["unsplit"]]
    uber = next(t.fingerprint for t in client.st.all_transactions() if t.description == "UBER EATS")
    old = next(t.fingerprint for t in client.st.all_transactions() if t.description == "OLD BOOKSHOP")
    assert ids[0] == uber            # $31 is closest to the $30 that came in
    assert old not in ids            # too old to offer without a search
    found = owing(client, dep, q="bookshop")["unsplit"]
    assert [u["id"] for u in found][:1] == [old] and found[0]["query"] is True
    assert old in [u["id"] for u in owing(client, dep, q="30.00")["unsplit"]]


# ── Save ────────────────────────────────────────────────────────────────

def test_c_pays_back_a_share_and_part_of_unsplit_b(client):
    a, b, _, dep, _ = setup(client, sent=75.0)
    before = world(client)
    b_cost = cost(client, b)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}]}))
    assert reply["title"] == "Sam paid back 2 purchases · $75.00"
    assert owes(client, a)["Sam"] == 0.0
    # B is split with exactly Sam: his share is $30, paid in full by this money.
    split = client.st.splits()[b]
    assert [(p["name"], p["amount"]) for p in split["people"]] == [("Sam", 30.0)]
    assert owes(client, b) == {"Sam": 0.0}
    assert client.st.get_transaction(b).my_share == 30.0
    assert cost(client, b) == round(b_cost - 30.0, 2)
    after = numbers(client)
    assert round(before["numbers"]["spent"] - after["spent"], 2) == 75.0
    assert round(after["allowance"] - before["numbers"]["allowance"], 2) == 75.0
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before
    assert b not in client.st.splits()


def test_b_fully_covered(client):
    a, b, _, dep, _ = setup(client, sent=105.0)
    before = world(client)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 60.0, "person": "Sam", "new_split": True}]}))
    assert owes(client, b) == {"Sam": 0.0}
    assert client.st.get_transaction(b).my_share == 0.0
    assert cost(client, b) == 0.0
    assert round(before["numbers"]["spent"] - numbers(client)["spent"], 2) == 105.0
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before


def test_x_over_b_is_refused(client):
    a, b, _, dep, _ = setup(client, sent=200.0)
    before = world(client)
    r = parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 60.01, "person": "Sam", "new_split": True}],
        "later": True})
    assert r.status_code == 400
    assert r.get_json()["error"] == "PIZZA NOVA was $60.00. Make it $60.00 or less."
    assert world(client) == before


def test_total_over_the_deposit_is_refused(client):
    a, b, _, dep, _ = setup(client, sent=75.0)
    before = world(client)
    r = parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 40.0, "person": "Sam", "new_split": True}]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "The parts add up to $10.00 more than came in."
    assert world(client) == before


@pytest.mark.parametrize("bad, error", [
    ({"amount": 0}, "A part has to be more than nothing."),
    ({"person": ""}, "Say who paid you back."),
])
def test_needs_an_amount_and_a_named_person(client, bad, error):
    a, b, _, dep, _ = setup(client, sent=30.0)
    before = world(client)
    part = {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True, **bad}
    r = parts(client, dep, {"parts": [part]})
    assert r.status_code == 400 and r.get_json()["error"] == error
    assert world(client) == before


def test_new_split_on_a_purchase_already_split_is_refused(client):
    a, b, costco, dep, _ = setup(client, sent=30.0)
    r = parts(client, dep, {"parts": [
        {"kind": "payback", "charge": costco, "amount": 30.0, "person": "Sam", "new_split": True}]})
    assert r.status_code == 400
    assert r.get_json()["error"] == "COSTCO is already split. Pick a share on it instead."


def test_a_leftover(client):
    """S-11: the rest is sorted in the same save (here, a gift), or left to sort."""
    a, b, _, dep, _ = setup(client, sent=100.0)
    before = world(client)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True},
        {"kind": "gift", "amount": 25.0}]}))
    assert sorted(p["kind"] for p in reply["parts"]) == ["gift", "payback", "payback"]
    assert owes(client, b) == {"Sam": 0.0}
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before
    # Left to sort: "$25.00 left to sort", and the split is still made.
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}],
        "later": True}))
    assert reply["rest"] == 25.0
    assert reply["title"] == "Sorted 2 parts. $25.00 left to sort."
    assert client.st.get_transaction(b).my_share == 30.0
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before


def test_no_split_at_all_only_unsplit_b(client):
    """Sam on none of her splits: the unsplit purchases are still offered."""
    a, b, _, dep, _ = setup(client, sent=30.0, split_a=False)
    r = owing(client, dep)
    assert [i for i in r["items"] if i["theirs"]] == []
    ids = [u["id"] for u in r["unsplit"]]
    assert a in ids and b in ids
    before = world(client)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}]}))
    assert reply["title"] == "Sam paid back $30.00"
    assert owes(client, b) == {"Sam": 0.0}
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before


def test_unlink_all_takes_the_new_split_off(client):
    """S-34 Unlink (DELETE …/parts) leaves B unsplit too, not owed by Sam."""
    a, b, _, dep, _ = setup(client, sent=75.0)
    ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": a, "amount": 45.0, "person": "Sam"},
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}]}))
    ok(client.delete(f"/api/transactions/{dep}/parts"))
    assert b not in client.st.splits()
    assert client.st.get_transaction(b).my_share is None
    assert owes(client, a)["Sam"] == 45.0


# ── No one owes her (2026-11-18, after #380): PB-30, OTHER PURCHASES only ──

def test_sender_on_no_split_and_no_one_owes(client):
    """Sam is on none of her splits and no one owes her anything: …/owing
    has no shares at all, and still offers her unsplit purchases, as Sam
    (picked, or T-14's answer) or as whoever the money names."""
    a, b, costco, dep, _ = setup(client, sent=30.0, split_a=False, jo=False)
    for r in (owing(client, dep), ok(client.get(f"/api/transactions/{dep}/owing"))):
        assert r["items"] == [] and r["from"] is None
        ids = [u["id"] for u in r["unsplit"]]
        assert {a, b, costco} <= set(ids) and dep not in ids
    # The app's PB-30 is for the name the money shows when no one is asked.
    assert ok(client.get(f"/api/transactions/{dep}/owing"))["named"] == "Sam Lee"


def test_only_new_split_parts_then_undo(client):
    """PB-30 with OTHER PURCHASES only: two purchases ticked, all of one and
    part of the other, "Mark 2 paid back"; one Undo leaves both unsplit."""
    a, b, costco, dep, _ = setup(client, sent=75.0, split_a=False, jo=False)
    before = world(client)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": b, "amount": 60.0, "person": "Sam Lee", "new_split": True},
        {"kind": "payback", "charge": a, "amount": 15.0, "person": "Sam Lee", "new_split": True}]}))
    assert reply["title"] == "Sam Lee paid back 2 purchases · $75.00"
    assert owes(client, b) == {"Sam Lee": 0.0} and owes(client, a) == {"Sam Lee": 0.0}
    assert client.st.get_transaction(b).my_share == 0.0
    assert client.st.get_transaction(a).my_share == 75.0
    assert round(before["numbers"]["spent"] - numbers(client)["spent"], 2) == 75.0
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before
    assert a not in client.st.splits() and b not in client.st.splits()


def test_only_new_split_with_the_rest_left_or_sorted(client):
    """S-11 after PB-30: what the ticks don't use is sorted in the same save
    (a gift) or left to sort; Undo puts it all back either way."""
    a, b, _, dep, _ = setup(client, sent=50.0, split_a=False, jo=False)
    before = world(client)
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True},
        {"kind": "gift", "amount": 20.0}]}))
    assert sorted(p["kind"] for p in reply["parts"]) == ["gift", "payback"]
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}], "later": True}))
    assert reply["rest"] == 20.0
    ok(client.post("/api/transactions/undo", json=reply["undo"]))
    assert world(client) == before


def test_others_owe_but_not_the_sender(client):
    """Jo owes her on Costco; Sam doesn't. As Sam: none of Jo's shares are
    Sam's, and the unsplit purchases are offered; a save as Sam never
    touches Jo's split."""
    a, b, costco, dep, _ = setup(client, sent=30.0, split_a=False)
    r = owing(client, dep)
    assert r["from"] is None and [i for i in r["items"] if i["theirs"]] == []
    assert b in [u["id"] for u in r["unsplit"]]
    jo = client.st.splits()[costco]
    reply = ok(parts(client, dep, {"parts": [
        {"kind": "payback", "charge": b, "amount": 30.0, "person": "Sam", "new_split": True}]}))
    assert client.st.splits()[costco] == jo
    assert owes(client, costco) == {"Jo": 60.0}
    ok(client.post("/api/transactions/undo", json=reply["undo"]))


def test_also_keeps_pb22s_purchase_first(client):
    """PB-22 from an old purchase that isn't split: …/owing?also= lists it
    first in OTHER PURCHASES, however old or far from the amount."""
    a, b, _, dep, _ = setup(client, sent=30.0, split_a=False, jo=False)
    add(client, "amex", row("OLD BOOKSHOP", 300.0, "amex", when=(TODAY - timedelta(days=200)).isoformat(),
                            category="Shopping", kind="credit"))
    old = next(t.fingerprint for t in client.st.all_transactions() if t.description == "OLD BOOKSHOP")
    assert old not in [u["id"] for u in owing(client, dep)["unsplit"]]
    r = ok(client.get(f"/api/transactions/{dep}/owing", query_string={"person": "Sam", "also": old}))
    assert r["unsplit"][0]["id"] == old and b in [u["id"] for u in r["unsplit"]]
    # Something that can't be split (the money itself) is never offered.
    r = ok(client.get(f"/api/transactions/{dep}/owing", query_string={"person": "Sam", "also": dep}))
    assert dep not in [u["id"] for u in r["unsplit"]]
