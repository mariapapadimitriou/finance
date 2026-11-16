"""Paybacks 2 (Figma Proposals › "Paybacks 2" 1406:5084, approved by the
product owner 2026-11-16; THL-289, THL-291, THL-181, THL-301, THL-305,
THL-172).

TP-01 to TP-05: a transfer that was really someone paying her back. $240.00
leaves Joint ••1123 (hers and Mom's) and lands in her Chequing the same day,
so Pearl pairs it as a transfer. It was Mom paying back her shares of three
purchases. Saying so (TP-03, PB-30 with `joint_payback`):

* the money in is a payback: each linked share stops counting as hers, so
  Spent drops and the Allowance rises by $240.00 (Rule A);
* the joint side's money out is Mom's, marked the way a joint charge she
  says is the other person's is (her share 0), all of it even on a 50/50
  account (decision 1), one "I say" on an account that's hers unless she
  says;
* it comes off Mom's "them" deposits that month (decision 2,
  finance/joint.py `payback_reduces_their_contribution`), only on accounts
  with no set share;
* Undo, or Unlink all, puts everything back, the transfer pairing too.

PP-01 / PP-02: PB-42's Who paid › A person picks someone else, on the split
or not (PB-15), with "Priya paid this back, not Sam. Sam owes $26.65 again."
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import joint
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from finance.transfers import transfer_pairs

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def day(n):
    d = TODAY - timedelta(days=n)
    return (d if d.strftime("%Y-%m") == MONTH else TODAY.replace(day=1)).isoformat()


def tx(desc, amount, account="chq", when=None, category="", merchant=None):
    names = {"chq": "Chequing ••4417", "jnt": "Joint ••1123", "sav": "Savings ••0932"}
    return Transaction(date=when or day(1), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name=names[account],
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "paybacks2.db"))
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


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def owes(c, charge):
    return {p["name"]: p["owes"] for p in detail(c, charge)["splitting"]["people"]}


def numbers(c):
    """The month's Spent and the Allowance on Home."""
    lst = c.get("/api/transactions/list", query_string={"month": MONTH, "limit": 500}).get_json()
    return {"spent": lst["month_totals"]["spent"], "allowance": c.get("/api/home").get_json()["safe_to_spend"]["amount"]}


def pairs(c):
    return transfer_pairs(c.st.all_transactions(), today=TODAY.isoformat())


def state(c, *ids):
    """What Undo must put back exactly: each row's category, its source, her
    share and whether she set it."""
    by = {t.fingerprint: t for t in c.st.all_transactions()}
    return {i: (by[i].category, by[i].category_source, by[i].my_share, by[i].share_set, by[i].excluded)
            for i in ids}


SHARES = (("COSTCO", 240.0, 120.0, 8), ("SHOPPERS", 129.0, 64.5, 7), ("AIR CANADA", 111.0, 55.5, 6),
          ("LOBLAWS", 84.2, 42.1, 5))


@pytest.fixture()
def mom(client):
    """Four purchases on Chequing, each split with Mom; $240.00 out of
    Joint ••1123 (her and Mom's) into Chequing the same day."""
    add(client, "chq", tx("NORTHWIND LTD PAYROLL", -3000.0, when=day(9), category="Income",
                          merchant="Northwind Ltd"),
        *(tx(m, a, when=day(n), category="Shopping") for m, a, _, n in SHARES),
        tx("TFR-FR 1123", -240.0, when=day(1)))
    i = add(client, "jnt", tx("TFR-TO 4417", 240.0, "jnt", when=day(1)))
    ok(client.put("/api/accounts/jnt/joint", json={"label": "Joint"}))
    ok(client.put("/api/accounts/jnt/settings", json={"joint_people": ["Mom"]}))
    for m, _, share, _ in SHARES:
        ok(client.put(f"/api/transactions/{i[m]}/split", json={
            "mode": "amount", "people": [{"name": "Mom", "amount": share}]}))
    return i


def payback(c, i, person="Mom", charges=("COSTCO", "SHOPPERS", "AIR CANADA")):
    """TP-03's one tap: Mom's ticked shares, and the joint side."""
    got = {m: share for m, _, share, _ in SHARES}
    return c.post(f"/api/transactions/{i['TFR-FR 1123']}/parts", json={
        "parts": [{"kind": "payback", "amount": got[m], "charge": i[m], "person": "Mom"} for m in charges],
        "later": False, "joint_payback": {"out": i["TFR-TO 4417"], "person": person}})


class TestOffer:
    """TP-01: "Mom paid me back" on money in from a joint account."""

    def test_the_two_ends_are_paired_as_a_transfer(self, client, mom):
        assert pairs(client).get(mom["TFR-TO 4417"]) == mom["TFR-FR 1123"]

    def test_the_money_in_offers_the_joint_accounts_other_owner(self, client, mom):
        transfer = detail(client, mom["TFR-FR 1123"])["transfer"]
        assert transfer["joint"]["people"] == ["Mom"]
        assert "1123" in transfer["joint"]["account"]
        assert not transfer.get("mine_only")

    def test_never_on_the_money_out(self, client, mom):
        assert "joint" not in detail(client, mom["TFR-TO 4417"])["transfer"]

    def test_with_two_other_owners_both_are_offered(self, client, mom):
        ok(client.put("/api/accounts/jnt/settings", json={"joint_people": ["Mom", "Dad"]}))
        assert detail(client, mom["TFR-FR 1123"])["transfer"]["joint"]["people"] == ["Mom", "Dad"]

    def test_never_for_money_she_moves_into_the_joint_account(self, client, mom):
        i = add(client, "chq", tx("TFR-TO 1123", 75.0, when=day(2)))
        i = add(client, "jnt", tx("TFR-FR 4417", -75.0, "jnt", when=day(2)))
        out, into = (client.st.get_transaction(i[k]) for k in ("TFR-TO 1123", "TFR-FR 4417"))
        assert joint.payback_offer(into, out) is None
        assert "joint" not in (detail(client, into.fingerprint).get("transfer") or {})

    def test_tp05_between_two_accounts_only_hers(self, client, mom):
        """TP-05: no Paid back, and the callout says why."""
        add(client, "sav", tx("TFR-TO 4417 SAV", 60.0, "sav", when=day(3)))
        i = add(client, "chq", tx("TFR-FR 0932", -60.0, when=day(3)))
        transfer = detail(client, i["TFR-FR 0932"])["transfer"]
        assert transfer.get("mine_only") is True and "joint" not in transfer
        r = payback(client, {**mom, "TFR-FR 1123": i["TFR-FR 0932"], "TFR-TO 4417": i["TFR-TO 4417 SAV"]})
        assert r.status_code == 400


class TestTheMoneyIn:
    """The $240.00 is a payback: Mom's shares are paid, and Spent and the
    Allowance move by $240.00 (Rule A)."""

    def test_toast_and_shares(self, client, mom):
        r = ok(payback(client, mom))
        # TP-04's ink toast.
        assert r["title"] == "Mom paid back 3 purchases · $240.00"
        assert [owes(client, mom[m])["Mom"] for m, *_ in SHARES] == [0.0, 0.0, 0.0, 42.1]

    def test_spent_drops_and_the_allowance_rises(self, client, mom):
        before = numbers(client)
        ok(payback(client, mom))
        after = numbers(client)
        assert after["spent"] == round(before["spent"] - 240.0, 2)
        assert after["allowance"] == round(before["allowance"] + 240.0, 2)

    def test_it_stops_being_a_transfer(self, client, mom):
        ok(payback(client, mom))
        assert mom["TFR-TO 4417"] not in pairs(client)
        assert "transfer" not in detail(client, mom["TFR-FR 1123"])

    def test_tp04_the_page_says_where_it_came_from(self, client, mom):
        ok(payback(client, mom))
        jp = detail(client, mom["TFR-FR 1123"])["joint_payback"]
        assert jp["person"] == "Mom" and jp["out_id"] == mom["TFR-TO 4417"]
        assert "1123" in jp["account"] and "4417" in jp["into"]

    def test_a_payback_part_with_no_name_is_moms(self, client, mom):
        r = client.post(f"/api/transactions/{mom['TFR-FR 1123']}/parts", json={
            "parts": [{"kind": "payback", "amount": 120.0, "charge": mom["COSTCO"]},
                      {"kind": "payback", "amount": 120.0, "charge": mom["SHOPPERS"]}],
            "joint_payback": {"out": mom["TFR-TO 4417"], "person": "mom"}})
        ok(r)
        assert owes(client, mom["COSTCO"])["Mom"] == 0.0


class TestTheJointSide:
    """The $240.00 out of Joint ••1123 is Mom's money, none of it hers."""

    def test_it_is_moms_like_a_charge_marked_theirs(self, client, mom):
        ok(payback(client, mom))
        out = client.st.get_transaction(mom["TFR-TO 4417"])
        assert out.my_share == 0.0 and out.share_set
        assert client.st.joint_paybacks()[out.fingerprint]["person"] == "Mom"

    def test_mine_unless_i_say_counts_it_as_one_i_say(self, client, mom):
        """On an account that's hers unless she says (no set share), this is
        the same "I say" as Whose was it? › theirs on a joint charge."""
        add(client, "jnt", tx("METRO", 30.0, "jnt", when=day(2), category="Groceries"))
        metro = next(t for t in client.st.all_transactions() if t.description == "METRO")
        ok(client.put(f"/api/transactions/{metro.fingerprint}/share", json={"my_share": 0}))
        ok(payback(client, mom))
        out = client.st.get_transaction(mom["TFR-TO 4417"])
        said = client.st.get_transaction(metro.fingerprint)
        assert (out.my_share, out.share_set) == (said.my_share, said.share_set) == (0.0, True)

    def test_on_a_50_50_account_it_is_all_moms(self, client, mom):
        ok(client.put("/api/accounts/jnt/settings", json={"joint_share": 50}))
        assert client.st.get_transaction(mom["TFR-TO 4417"]).my_share == 120.0
        ok(payback(client, mom))
        assert client.st.get_transaction(mom["TFR-TO 4417"]).my_share == 0.0

    def test_someone_not_on_the_account_is_refused(self, client, mom):
        r = payback(client, mom, person="Sam")
        assert r.status_code == 400
        assert mom["TFR-TO 4417"] not in client.st.joint_paybacks()
        assert pairs(client).get(mom["TFR-TO 4417"]) == mom["TFR-FR 1123"]


class TestContributions:
    """Decision 2: the $240.00 comes off Mom's "them" deposits that month
    (finance/joint.py `payback_reduces_their_contribution`)."""

    def moms_deposit(self, client, amount=500.0):
        i = add(client, "jnt", tx("E-TRANSFER FROM MOM", -amount, "jnt", when=day(3), merchant="Mom"))
        ok(client.put(f"/api/transactions/{i['E-TRANSFER FROM MOM']}/joint-from",
                      json={"who": "them", "person": "Mom"}))

    def test_the_sign_is_one_constant(self):
        # payback_reduces_their_contribution: it comes off, not on.
        assert joint.THEIR_PAYBACK_SIGN == -1
        assert joint.payback_reduces_their_contribution(500.0, 240.0) == 260.0

    def test_it_comes_off_moms_them_deposits_that_month(self, client, mom):
        self.moms_deposit(client)
        assert joint.their_contributions(client.st)[("jnt", MONTH)] == 500.0
        ok(payback(client, mom))
        # See finance/joint.py payback_reduces_their_contribution.
        assert joint.their_contributions(client.st)[("jnt", MONTH)] == 260.0

    def test_only_on_accounts_with_no_set_share(self, client, mom):
        self.moms_deposit(client)
        ok(client.put("/api/accounts/jnt/settings", json={"joint_share": 50}))
        ok(payback(client, mom))
        assert ("jnt", MONTH) not in joint.their_contributions(client.st)

    def test_undo_gives_it_back(self, client, mom):
        self.moms_deposit(client)
        r = ok(payback(client, mom))
        ok(client.post("/api/transactions/undo", json=r["undo"]))
        assert joint.their_contributions(client.st)[("jnt", MONTH)] == 500.0


class TestUndo:
    """TP-04's Undo unlinks everything and puts the transfer pairing back."""

    def test_undo_restores_everything_exactly(self, client, mom):
        ids = (mom["TFR-FR 1123"], mom["TFR-TO 4417"])
        was_pairs, was_state, was_numbers = pairs(client), state(client, *ids), numbers(client)
        was_owes = {m: owes(client, mom[m]) for m, *_ in SHARES}
        r = ok(payback(client, mom))
        ok(client.post("/api/transactions/undo", json=r["undo"]))
        assert pairs(client) == was_pairs
        assert state(client, *ids) == was_state
        assert numbers(client) == was_numbers
        assert {m: owes(client, mom[m]) for m, *_ in SHARES} == was_owes
        assert client.st.joint_paybacks() == {}
        assert detail(client, mom["TFR-FR 1123"])["transfer"]["joint"]["people"] == ["Mom"]
        assert "joint_payback" not in detail(client, mom["TFR-FR 1123"])

    def test_undo_on_a_50_50_account_puts_half_back(self, client, mom):
        ok(client.put("/api/accounts/jnt/settings", json={"joint_share": 50}))
        r = ok(payback(client, mom))
        ok(client.post("/api/transactions/undo", json=r["undo"]))
        out = client.st.get_transaction(mom["TFR-TO 4417"])
        assert (out.my_share, out.share_set) == (120.0, False)

    def test_unlink_all_makes_it_a_transfer_again(self, client, mom):
        ids = (mom["TFR-FR 1123"], mom["TFR-TO 4417"])
        was_pairs, was_state = pairs(client), state(client, *ids)
        ok(payback(client, mom))
        r = ok(client.delete(f"/api/transactions/{mom['TFR-FR 1123']}/parts"))
        assert r["title"] == "Unlinked. It’s a transfer again."
        assert pairs(client) == was_pairs
        assert state(client, *ids) == was_state
        assert client.st.joint_paybacks() == {}

    def test_change_what_it_paid_back_keeps_the_joint_side(self, client, mom):
        """PB-41's Change what it paid back saves the parts again; the money
        out stays Mom's."""
        ok(payback(client, mom))
        r = client.post(f"/api/transactions/{mom['TFR-FR 1123']}/parts", json={
            "parts": [{"kind": "payback", "amount": 120.0, "charge": mom["COSTCO"], "person": "Mom"},
                      {"kind": "payback", "amount": 64.5, "charge": mom["SHOPPERS"], "person": "Mom"},
                      {"kind": "payback", "amount": 42.1, "charge": mom["LOBLAWS"], "person": "Mom"},
                      {"kind": "gift", "amount": 13.4}], "replace": True})
        ok(r)
        assert client.st.get_transaction(mom["TFR-TO 4417"]).my_share == 0.0
        assert mom["TFR-TO 4417"] in client.st.joint_paybacks()


# ── PP-01 / PP-02: Who paid › A person (PB-42) ───────────────────────────

@pytest.fixture()
def pizza(client):
    """Pizza Nova $79.95 split 3 ways: Sam, Priya and Jo $26.65 each; Sam's
    $26.65 e-Transfer linked."""
    i = add(client, "chq", tx("PIZZA NOVA", 79.95, when=day(6), category="Dining"),
            tx("E-TRANSFER FROM SAM LEE", -26.65, when=day(2), merchant="Sam Lee"))
    pz, dep = i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
    ok(client.put(f"/api/transactions/{pz}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": 26.65} for n in ("Sam Lee", "Priya Shah", "Jo Martin")]}))
    ok(client.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "amount": 26.65, "charge": pz, "person": "Sam Lee"}]}))
    link = next(lk for p in detail(client, pz)["splitting"]["people"] for lk in p.get("links") or []
                if p["name"] == "Sam Lee")
    return pz, link["inflow"]


class TestWhoPaid:
    def change(self, client, pz, inflow, person):
        return client.post(f"/api/transactions/{pz}/paybacks/{inflow}/change",
                           json={"kind": "person", "person": person})

    def test_pp02_someone_else_on_the_split(self, client, pizza):
        pz, inflow = pizza
        r = ok(self.change(client, pz, inflow, "Priya Shah"))
        assert r["title"] == "Priya paid this back, not Sam. Sam owes $26.65 again."
        assert owes(client, pz) == {"Sam Lee": 26.65, "Priya Shah": 0.0, "Jo Martin": 26.65}

    def test_undo_puts_sam_back(self, client, pizza):
        pz, inflow = pizza
        r = ok(self.change(client, pz, inflow, "Priya Shah"))
        ok(client.post("/api/transactions/undo", json=r["undo"]))
        assert owes(client, pz) == {"Sam Lee": 0.0, "Priya Shah": 26.65, "Jo Martin": 26.65}

    def test_someone_new_gets_the_whole_payback_as_pb15_does(self, client, pizza):
        pz, inflow = pizza
        r = ok(self.change(client, pz, inflow, "Maya"))
        assert r["title"] == "Maya paid this back, not Sam. Sam owes $26.65 again."
        assert owes(client, pz)["Sam Lee"] == 26.65
        dep = client.st.get_transaction(inflow)
        parent = (dep.raw or {}).get("part_of") or inflow
        assert [(p["kind"], p["amount"], p["detail"].get("person")) for p in client.st.parts()[parent]] \
            == [("payback", 26.65, "Maya")]

    def test_a_name_is_needed(self, client, pizza):
        pz, inflow = pizza
        r = client.post(f"/api/transactions/{pz}/paybacks/{inflow}/change", json={"kind": "person", "person": " "})
        assert r.status_code == 400 and r.get_json()["error"] == "Say who paid it back."
        assert owes(client, pz)["Sam Lee"] == 0.0


class TestPeopleFromPastSplits:
    """PP-01's FROM PAST SPLITS: how many splits, and joint-account people say so."""

    def test_splits_and_joint(self, client, mom):
        people = {p["name"]: p for p in client.get("/api/people/recent").get_json()["people"]}
        assert people["Mom"]["splits"] == 4 and people["Mom"]["joint"] is True
