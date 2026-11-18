"""PB-30 on every payback from a person (2026-11-16).

The product owner: "I still can't pick several purchases after saying
something is a payback." PB-30 (Figma Proposals › "Paybacks & undo"
1395:3405, note 1397:4697: "replaces S-35 ticks then PB-13 per person, and
PB-12's single pick when one person owes several") only ran when Pearl
already knew the sender. Now every path that ends in a person goes through
it, by the server calls the app makes:

1. Paid back › A person (PB-11), the sender known: GET …/owing gives `from`
   and their shares; PB-30 ticks them; one POST …/parts.
2. PQ-03 "Is X paying you back?": Something else, or a tile whose share is
   less than the money while they owe on other purchases, opens PB-30 for
   the tile's person (GET …/owing?person=); the single tap stays otherwise.
3. Who paid you back? (409 `who_paid`): after her pick, PB-30 for that
   person (GET …/owing?person=, then POST …/parts) instead of one share.
4. TP-03 from a joint account (already PB-30): still several shares.
5. No person (work, a refund from the shop): T-09w / T-09rs, unchanged.
6. A sender Pearl can't match: PP-01 first, then PB-30 for her pick; the
   sender is never added to a split.

Each: one deposit links two or three of one person's purchases, and one
Undo puts every link back.
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def buy(merchant, amount, n):
    return Transaction(date=ago(n), description=merchant.upper(), merchant=merchant, amount=amount,
                       category="Dining", account_id="amex", account_name="Amex Cobalt ••1001",
                       raw={"account_type": "credit"})


def sent(desc, amount, n=1, merchant=None):
    return Transaction(date=ago(n), description=desc, merchant=merchant or desc, amount=-amount, category="",
                       account_id="chq", account_name="Chequing ••4417", raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "payback_multi.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        yield c


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def ids(c):
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


# Anastasia owes on three purchases she split herself: $30 + $20 + $25.
SHARES = (("Costco", 90.0, 30.0, 12), ("Pizza Nova", 60.0, 20.0, 9), ("Pai", 75.0, 25.0, 6))


def setup(c, sender, amount=75.0, merchant=None):
    ingest(c.st, IngestResult([buy(m, a, n) for m, a, _, n in SHARES], "amex"))
    ingest(c.st, IngestResult([sent(sender, amount, merchant=merchant)], "chq"))
    i = ids(c)
    for m, _, share, _ in SHARES:
        ok(c.put(f"/api/transactions/{i[m.upper()]}/split", json={
            "mode": "amount", "people": [{"name": "Anastasia", "amount": share}, {"name": "Jo", "amount": share}]}))
    return {m: i[m.upper()] for m, *_ in SHARES}, i[sender]


def owes(c, charge):
    return {p["name"]: p["owes"] for p in c.get(f"/api/transactions/{charge}").get_json()["splitting"]["people"]}


def everyone(c, charges):
    return {m: owes(c, cid) for m, cid in charges.items()}


def split_people(c):
    return sorted({p["name"] for s in c.st.splits().values() for p in s["people"]})


def owing(c, deposit, person=None):
    """GET …/owing as PartsSheet's load() calls it."""
    return ok(c.get(f"/api/transactions/{deposit}/owing", query_string={"person": person} if person else {}))


def theirs(reply):
    """PB-30's rows: the sender's own shares with an amount (`theirShares`)."""
    return [o for o in reply["items"] if o.get("theirs") and not o.get("unknown") and o["owes"] >= 0.005]


def pb30(c, deposit, rows, **extra):
    """PB-30's one tap: every ticked share, in one request (`takeTicked`)."""
    return c.post(f"/api/transactions/{deposit}/parts", json={
        "parts": [{"kind": "payback", "amount": o["owes"], "charge": o["id"], "person": o["person"]} for o in rows],
        "later": False, **extra})


def undo(c, reply):
    ok(c.post("/api/transactions/undo", json=reply["undo"]))


def links_all_then_undo(c, charges, deposit, rows, n=3):
    before = everyone(c, charges)
    people = split_people(c)
    r = ok(pb30(c, deposit, rows))
    total = sum(o["owes"] for o in rows)
    assert r["title"] == f"Anastasia paid back {n} purchases · ${total:,.2f}"
    assert all(v["Anastasia"] == 0.0 for m, v in everyone(c, charges).items() if any(o["id"] == charges[m] for o in rows))
    # Never a person added: the sender's bank name joins no split.
    assert split_people(c) == people
    undo(c, r)
    assert everyone(c, charges) == before
    assert not c.st.parts().get(deposit)


class TestPath1PaidBackAPersonSenderKnown:
    """PB-11 › A person with the sender's name on a split: PB-30 straight away."""

    def test_owing_names_her_and_lists_all_three(self, client):
        charges, dep = setup(client, "INTERAC E-TRANSFER FROM ANASTASIA PAPAS", merchant="Anastasia Papas")
        r = owing(client, dep)
        assert r["from"] == "Anastasia"
        assert sorted(o["id"] for o in theirs(r)) == sorted(charges.values())

    def test_three_purchases_one_save_one_undo(self, client):
        charges, dep = setup(client, "INTERAC E-TRANSFER FROM ANASTASIA PAPAS", merchant="Anastasia Papas")
        links_all_then_undo(client, charges, dep, theirs(owing(client, dep)))

    def test_pb30u_less_ticked_leaves_the_rest_to_sort(self, client):
        # $75.00 in, Costco and Pizza Nova ticked ($50): the other $25.00 is S-11c's.
        charges, dep = setup(client, "INTERAC E-TRANSFER FROM ANASTASIA PAPAS", merchant="Anastasia Papas")
        rows = [o for o in theirs(owing(client, dep)) if o["id"] != charges["Pai"]]
        r = client.post(f"/api/transactions/{dep}/parts", json={
            "parts": [{"kind": "payback", "amount": o["owes"], "charge": o["id"], "person": o["person"]} for o in rows]
            + [{"kind": "gift", "amount": 25.0}], "later": False})
        ok(r)
        assert owes(client, charges["Pai"])["Anastasia"] == 25.0
        assert owes(client, charges["Costco"])["Anastasia"] == 0.0
        undo(client, r.get_json())
        assert owes(client, charges["Costco"])["Anastasia"] == 30.0


class TestPath6SenderUnmatchedAsksFirst:
    """"A PAPAS" is no one on her splits by name: PP-01 lists who owes; her
    pick reloads …/owing for that person, and PB-30 ticks their shares."""

    SENDER = "INTERAC E-TRANSFER FROM A PAPAS"

    def test_owing_names_no_one_so_the_app_asks(self, client):
        charges, dep = setup(client, self.SENDER)
        r = owing(client, dep)
        assert r["from"] is None
        # PP-01's people: everyone who owes her.
        assert {o["person"] for o in r["items"]} == {"Anastasia", "Jo"}

    def test_her_pick_makes_them_the_sender(self, client):
        charges, dep = setup(client, self.SENDER)
        r = owing(client, dep, person="Anastasia")
        assert r["from"] == "Anastasia"
        assert sorted(o["id"] for o in theirs(r)) == sorted(charges.values())
        assert all(o["person"] == "Anastasia" for o in theirs(r))

    def test_three_purchases_one_save_one_undo(self, client):
        charges, dep = setup(client, self.SENDER)
        links_all_then_undo(client, charges, dep, theirs(owing(client, dep, person="Anastasia")))

    def test_two_of_three(self, client):
        charges, dep = setup(client, self.SENDER, amount=50.0)
        rows = [o for o in theirs(owing(client, dep, person="Anastasia")) if o["id"] != charges["Pai"]]
        links_all_then_undo(client, charges, dep, rows, n=2)


class TestPath3WhoPaidThenPB30:
    """PQ-03's tile 409s with `who_paid`; her pick opens PB-30 for that
    person, not one share."""

    SENDER = "INTERAC E-TRANSFER FROM A PAPAS"

    def ask(self, client, charges, dep):
        r = client.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": charges["Costco"]})
        assert r.status_code == 409
        return r.get_json()["who_paid"]

    def test_the_ask_carries_the_deposit_for_pb30s_header(self, client):
        # PB-30's header: "+$75.00 · Fri, Nov 14" and the sender.
        charges, dep = setup(client, self.SENDER)
        ask = self.ask(client, charges, dep)
        assert ask["deposit"] == dep
        assert ask["amount"] == 75.0
        assert ask["date"] == ago(1)
        assert ask["sender"]
        assert not client.st.get_transaction(dep).repays

    def test_her_pick_links_all_three_in_one_save(self, client):
        charges, dep = setup(client, self.SENDER)
        ask = self.ask(client, charges, dep)
        r = owing(client, ask["deposit"], person="Anastasia")
        assert r["from"] == "Anastasia"
        links_all_then_undo(client, charges, ask["deposit"], theirs(r))


class TestPath2PaybackQuestion:
    """PQ-03: the single tap stays; Something else, or a share smaller than
    the money with more owed elsewhere, opens PB-30 for the tile's person."""

    SENDER = "INTERAC E-TRANSFER FROM ANASTASIA PAPAS"

    def question(self, client, dep):
        items = client.get("/api/review").get_json()["money_in"]
        return next(i for i in items if i["txn"]["id"] == dep).get("payback")

    def test_the_single_tap_still_credits_one_share(self, client):
        charges, dep = setup(client, self.SENDER, amount=30.0, merchant="Anastasia Papas")
        q = self.question(client, dep)
        tile = next(t for t in q["tiles"] if t["charge"] == charges["Costco"])
        assert tile["person"] == "Anastasia"
        r = ok(client.post(f"/api/transactions/{dep}/mark",
                           json={"case": "payback", "charge": tile["charge"], "person": tile["person"]}))
        assert owes(client, charges["Costco"])["Anastasia"] == 0.0
        assert owes(client, charges["Pai"])["Anastasia"] == 25.0
        undo(client, r)
        assert owes(client, charges["Costco"])["Anastasia"] == 30.0

    def test_something_else_opens_pb30_for_the_tiles_person(self, client):
        charges, dep = setup(client, self.SENDER, amount=30.0, merchant="Anastasia Papas")
        q = self.question(client, dep)
        person = {t["person"] for t in q["tiles"] if t.get("person")}
        assert person == {"Anastasia"}
        # She unticks Costco: Pizza Nova in full, Pai part-paid (PB-30o).
        assert len(theirs(owing(client, dep, person="Anastasia"))) == 3
        r2 = ok(client.post(f"/api/transactions/{dep}/parts", json={
            "parts": [{"kind": "payback", "amount": 20.0, "charge": charges["Pizza Nova"], "person": "Anastasia"},
                      {"kind": "payback", "amount": 10.0, "charge": charges["Pai"], "person": "Anastasia"}],
            "later": False}))
        assert r2["title"] == "Anastasia paid back 2 purchases · $30.00"
        assert owes(client, charges["Pai"])["Anastasia"] == 15.0
        undo(client, r2)
        assert owes(client, charges["Pizza Nova"])["Anastasia"] == 20.0
        assert owes(client, charges["Pai"])["Anastasia"] == 25.0

    def test_more_money_than_the_tiles_share_ticks_the_others_too(self, client):
        # $75.00 in; the tile's share (Costco) is $30.00 and she owes on two
        # more: PB-30 with Costco ticked and the rest up to $75.00.
        charges, dep = setup(client, self.SENDER, amount=75.0, merchant="Anastasia Papas")
        r = owing(client, dep, person="Anastasia")
        mine = theirs(r)
        tile = next(o for o in mine if o["id"] == charges["Costco"])
        assert round(tile["owes"] * 100) < 7500 and len(mine) > 1
        links_all_then_undo(client, charges, dep, mine)


class TestPath4JointTransferTP03:
    """TP-03 already ran through PB-30: Mom's three shares, one save with
    the joint side, one Undo."""

    def test_three_shares_and_undo(self, client):
        from tests.test_paybacks_2 import SHARES as JS, add, tx, day, payback
        add(client, "chq", *(tx(m, a, when=day(n), category="Shopping") for m, a, _, n in JS),
            tx("TFR-FR 1123", -240.0, when=day(1)))
        i = add(client, "jnt", tx("TFR-TO 4417", 240.0, "jnt", when=day(1)))
        ok(client.put("/api/accounts/jnt/joint", json={"label": "Joint"}))
        ok(client.put("/api/accounts/jnt/settings", json={"joint_people": ["Mom"]}))
        for m, _, share, _ in JS:
            ok(client.put(f"/api/transactions/{i[m]}/split", json={
                "mode": "amount", "people": [{"name": "Mom", "amount": share}]}))
        # PartsSheet asks …/owing?person=Mom (the joint account's other owner).
        r = owing(client, i["TFR-FR 1123"], person="Mom")
        assert r["from"] == "Mom" and len(theirs(r)) == 4
        before = {m: owes(client, i[m]) for m, *_ in JS}
        reply = ok(payback(client, i))
        assert reply["title"] == "Mom paid back 3 purchases · $240.00"
        undo(client, reply)
        assert {m: owes(client, i[m]) for m, *_ in JS} == before
        assert client.st.joint_paybacks() == {}


class TestPath5NoPersonUnchanged:
    """Work and the shop keep T-09w / T-09rs: one purchase, no person."""

    def test_a_refund_from_the_shop_links_one_purchase(self, client):
        ingest(client.st, IngestResult([buy("Costco", 90.0, 5)], "amex"))
        ingest(client.st, IngestResult([sent("COSTCO REFUND", 90.0, merchant="Costco")], "chq"))
        i = ids(client)
        r = ok(client.post(f"/api/transactions/{i['COSTCO REFUND']}/mark",
                           json={"case": "refund", "charge": i["COSTCO"]}))
        refunded = lambda: client.get(f"/api/transactions/{i['COSTCO']}").get_json().get("refunded_by") or []
        assert len(refunded()) == 1
        assert client.st.splits() == {}
        undo(client, r)
        assert refunded() == []


class TestTheAppWiresIt:
    """The Swift side: PB-30 is where a person's payback goes."""

    def src(self, rel):
        return (IOS / rel).read_text()

    def test_a_person_asks_who_then_reloads_their_shares(self):
        # Paths 1 and 6: PP-01 (only the people who owe her, no Someone
        # new), then …/owing?person= for her pick.
        s = self.src("Views/Transactions/PartsFlow.swift")
        # Its rows are taken when it opens (2026-11-17, never empty).
        assert "onlyPast: ask.rows" in s and "someoneNew: false" in s
        assert "jointPerson ?? joint?.person ?? pickedPerson ?? person" in s
        assert "(paidBack || saidPerson) && (editing.isEmpty || repick)" in s

    def test_who_paid_ask_opens_pb30_for_the_pick(self):
        # Path 3.
        s = self.src("Views/Transactions/JointPaybackViews.swift")
        assert "paidBack: true, payer: name, person: name, mustTick: ask.charge" in s

    def test_pq03_tile_and_something_else(self):
        # Path 2.
        s = self.src("Views/Review/AnswerSheet.swift")
        assert "await tapTile(tile)" in s
        assert "person: partPerson, mustTick: mustTick" in s
