"""A payback on a purchase she already split (2026-11-16).

The product owner: "The suggestion to pay back from a transfer doesn't pay
back a split I created; it just adds a new split." Costco $90.00, split with
Anastasia $30.00 by her. Anastasia's e-Transfer comes in and the bank names
the sender its own way ("PAPAS ANASTASIA", "MS ANASTASIA PAPAS", "A
PAPAS"). PQ-03's "Yes, Costco" (POST …/mark {case: payback, charge}) put
the sender on the split beside Anastasia (splits.add_payer): Anastasia still
owed $30.00 and her own share fell to $30.00.

Now (splits.payer_on_split, marks._payer_on_splits):
* the sender is matched to the person on the split, loosely (any word is
  their first name, the words run together start with it, or the money's
  text names them), and credited;
* otherwise, even when only one person still owes (product owner,
  2026-11-16: always ask), nothing is saved and the reply is 409 `who_paid`, the split's
  people for PP-01 (`WhoPaidPicker`); her tap sends the mark with `person`;
* a split she set up never gains a person from a payback. A split made only
  by paybacks still grows with each payer (THL-260).
"""

from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pytest

from finance import splits as sp
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def buy(merchant, amount, n=4):
    return Transaction(date=ago(n), description=merchant.upper(), merchant=merchant, amount=amount,
                       category="Groceries", account_id="amex", account_name="Amex Cobalt ••1001",
                       raw={"account_type": "credit"})


def sent(desc, amount=30.0, n=1, account="chq"):
    names = {"chq": "Chequing ••4417", "jnt": "Joint ••1123"}
    return Transaction(date=ago(n), description=desc, merchant=desc, amount=-amount, category="",
                       account_id=account, account_name=names[account], raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "existing_split.db"))
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


def setup(c, sender, people=(("Anastasia", 30.0),)):
    ingest(c.st, IngestResult([buy("Costco", 90.0)], "amex"))
    ingest(c.st, IngestResult([sent(sender)], "chq"))
    i = ids(c)
    ok(c.put(f"/api/transactions/{i['COSTCO']}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": a} for n, a in people]}))
    return i["COSTCO"], i[sender]


def people(c, charge):
    d = c.get(f"/api/transactions/{charge}").get_json()["splitting"]["people"]
    return {p["name"]: (p["paid"], p["owes"]) for p in d}


def yes(c, deposit, charge, **extra):
    """PQ-03's tile, as the app sends it (ReviewView `.payback`)."""
    return c.post(f"/api/transactions/{deposit}/mark", json={"case": "payback", "charge": charge, **extra})


class TestTheSenderIsTheFriendOnTheSplit:
    """The bank's name for Anastasia, however it writes it: she's credited."""

    @pytest.mark.parametrize("sender", [
        "INTERAC E-TRANSFER FROM PAPAS ANASTASIA",      # last name first
        "INTERAC E-TRANSFER FROM MS ANASTASIA PAPAS",   # a title first
        "INTERAC E-TRANSFER FROM ANASTASIAPAPAS",       # run together, all caps
        "INTERAC E-TRANSFER FROM ANASTASIA",            # first name only
        "INTERAC E-TRANSFER FROM ANASTASIA PAPAS",      # the full name
    ])
    def test_yes_credits_anastasia_and_adds_no_one(self, client, sender):
        charge, deposit = setup(client, sender)
        ok(yes(client, deposit, charge))
        assert people(client, charge) == {"Anastasia": (30.0, 0.0)}
        assert [p["name"] for p in client.st.splits()[charge]["people"]] == ["Anastasia"]
        assert client.st.get_transaction(charge).my_share == 60.0
        assert len(client.st.splits()) == 1

    def test_the_link_names_her_as_she_is_on_the_split(self, client):
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM PAPAS ANASTASIA")
        ok(yes(client, deposit, charge))
        assert client.st.payback_people()[deposit] == "Anastasia"

    def test_a_split_name_with_a_last_name_and_a_handle(self, client):
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM ANASTASIAPAPAS",
                                people=(("Anastasia Papas", 30.0),))
        ok(yes(client, deposit, charge))
        assert people(client, charge) == {"Anastasia Papas": (30.0, 0.0)}

    def test_the_tile_says_whose_share_and_the_app_sends_it(self, client):
        # PQ-03b: "Costco · Anastasia's share", and its `person`.
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM PAPAS ANASTASIA")
        items = client.get("/api/review").get_json()["money_in"]
        q = next(i for i in items if i["txn"]["id"] == deposit)["payback"]
        tile = next(t for t in q["tiles"] if t["charge"] == charge)
        assert tile["kind"] == "split" and tile["person"] == "Anastasia"
        ok(yes(client, deposit, charge, person=tile["person"]))
        assert people(client, charge) == {"Anastasia": (30.0, 0.0)}


class TestOnePersonStillOwesStillAsks:
    """A sender Pearl can't place on the split, and only one person owes:
    Pearl asks anyway (product owner, 2026-11-16: always ask, never guess)."""

    @pytest.mark.parametrize("sender", ["INTERAC E-TRANSFER FROM A PAPAS",
                                        "INTERAC E-TRANSFER FROM STACY P"])
    def test_she_is_asked_and_nothing_is_saved(self, client, sender):
        charge, deposit = setup(client, sender)
        before = (client.st.splits()[charge], client.st.get_transaction(charge).my_share)
        r = yes(client, deposit, charge)
        assert r.status_code == 409
        assert [p["name"] for p in r.get_json()["who_paid"]["people"]] == ["Anastasia"]
        assert (client.st.splits()[charge], client.st.get_transaction(charge).my_share) == before
        assert not client.st.get_transaction(deposit).repays

    @pytest.mark.parametrize("sender", ["INTERAC E-TRANSFER FROM A PAPAS",
                                        "INTERAC E-TRANSFER FROM STACY P"])
    def test_her_pick_credits_that_person(self, client, sender):
        charge, deposit = setup(client, sender)
        ask = yes(client, deposit, charge).get_json()["who_paid"]
        ok(yes(client, ask["deposit"], ask["charge"], person="Anastasia"))
        assert people(client, charge) == {"Anastasia": (30.0, 0.0)}
        assert client.st.get_transaction(charge).my_share == 60.0

    def test_mom_on_the_split_and_anastasia_on_the_e_transfer(self, client):
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM ANASTASIA PAPAS", people=(("Mom", 30.0),))
        r = yes(client, deposit, charge)
        assert r.status_code == 409
        assert [p["name"] for p in r.get_json()["who_paid"]["people"]] == ["Mom"]
        ok(yes(client, deposit, charge, person="Mom"))
        assert people(client, charge) == {"Mom": (30.0, 0.0)}


class TestWhenItCouldBeEitherPearlAsks:
    """Two people owe and the sender is neither by name: PP-01."""

    def setup_two(self, client, sender="INTERAC E-TRANSFER FROM A PAPAS"):
        return setup(client, sender, people=(("Mom", 30.0), ("Jo", 30.0)))

    def test_nothing_is_saved_and_the_split_people_are_offered(self, client):
        charge, deposit = self.setup_two(client)
        before = (client.st.splits()[charge], client.st.get_transaction(charge).my_share)
        r = yes(client, deposit, charge)
        assert r.status_code == 409
        ask = r.get_json()["who_paid"]
        assert ask["charge"] == charge and ask["deposit"] == deposit
        assert ask["merchant"] == "Costco" and ask["amount"] == 30.0
        assert [(p["name"], p["owes"]) for p in ask["people"]] == [("Mom", 30.0), ("Jo", 30.0)]
        assert (client.st.splits()[charge], client.st.get_transaction(charge).my_share) == before
        assert not client.st.get_transaction(deposit).repays

    def test_her_pick_credits_that_person(self, client):
        charge, deposit = self.setup_two(client)
        ask = yes(client, deposit, charge).get_json()["who_paid"]
        ok(yes(client, ask["deposit"], ask["charge"], person="Jo"))
        assert people(client, charge) == {"Mom": (0.0, 30.0), "Jo": (30.0, 0.0)}
        assert client.st.get_transaction(charge).my_share == 30.0

    def test_two_people_with_the_sender_first_name_are_asked_about(self, client):
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM ANASTASIA PAPAS",
                                people=(("Anastasia P", 30.0), ("Anastasia K", 30.0)))
        r = yes(client, deposit, charge)
        assert r.status_code == 409
        assert [p["name"] for p in r.get_json()["who_paid"]["people"]] == ["Anastasia P", "Anastasia K"]

    def test_pb15_someone_named_never_joins_her_split(self, client):
        # Something else › PB-15 "Priya isn't on a split · pick the purchase".
        charge, deposit = self.setup_two(client, "INTERAC E-TRANSFER FROM PRIYA SHAH")
        r = yes(client, deposit, charge, person="Priya Shah")
        assert r.status_code == 409
        assert [p["name"] for p in client.st.splits()[charge]["people"]] == ["Mom", "Jo"]

    def test_a_not_sure_yet_split_asks_too(self, client):
        ingest(client.st, IngestResult([buy("Costco", 90.0)], "amex"))
        ingest(client.st, IngestResult([sent("INTERAC E-TRANSFER FROM PRIYA SHAH")], "chq"))
        i = ids(client)
        ok(client.put(f"/api/transactions/{i['COSTCO']}/split", json={
            "mode": "unknown", "people": [{"name": "Mom"}, {"name": "Jo"}]}))
        r = yes(client, i["INTERAC E-TRANSFER FROM PRIYA SHAH"], i["COSTCO"])
        assert r.status_code == 409
        assert [p["name"] for p in client.st.splits()[i["COSTCO"]]["people"]] == ["Mom", "Jo"]


class TestASplitMadeByPaybacksStillGrows:
    """THL-260: Pearl's own split from paybacks takes each new payer."""

    def test_a_second_friend_joins(self, client):
        ingest(client.st, IngestResult([buy("Costco", 90.0)], "amex"))
        ingest(client.st, IngestResult([sent("INTERAC E-TRANSFER FROM PRIYA SHAH"),
                                        sent("INTERAC E-TRANSFER FROM SAM LEE", n=0)], "chq"))
        i = ids(client)
        ok(yes(client, i["INTERAC E-TRANSFER FROM PRIYA SHAH"], i["COSTCO"]))
        ok(yes(client, i["INTERAC E-TRANSFER FROM SAM LEE"], i["COSTCO"]))
        assert [p["name"] for p in client.st.splits()[i["COSTCO"]]["people"]] == ["Priya Shah", "Sam Lee"]


class TestTheJointTransfer:
    """TP-03 / PB-30: a share found by search has no person; the joint
    account's owner ("Anastasia") isn't the split's "Mom"."""

    def test_it_is_credited_on_the_split_not_to_nobody(self, client):
        ingest(client.st, IngestResult([buy("Costco", 90.0)], "amex"))
        ingest(client.st, IngestResult([sent("TFR-FR 1123")], "chq"))
        out = Transaction(date=ago(1), description="TFR-TO 4417", merchant="TFR-TO 4417", amount=30.0,
                          category="", account_id="jnt", account_name="Joint ••1123",
                          raw={"account_type": "depository"})
        ingest(client.st, IngestResult([out], "jnt"))
        ok(client.put("/api/accounts/jnt/joint", json={"label": "Joint"}))
        ok(client.put("/api/accounts/jnt/settings", json={"joint_people": ["Anastasia"]}))
        i = ids(client)
        ok(client.put(f"/api/transactions/{i['COSTCO']}/split", json={
            "mode": "amount", "people": [{"name": "Mom", "amount": 30.0}]}))
        ok(client.post(f"/api/transactions/{i['TFR-FR 1123']}/parts", json={
            "parts": [{"kind": "payback", "amount": 30.0, "charge": i["COSTCO"]}], "later": False,
            "joint_payback": {"out": i["TFR-TO 4417"], "person": "Anastasia"}}))
        assert people(client, i["COSTCO"]) == {"Mom": (30.0, 0.0)}
        assert [p["name"] for p in client.st.splits()[i["COSTCO"]]["people"]] == ["Mom"]


class TestHerRealDataUndoes:
    """The bad answer already saved (the old `add_payer`: "Papas Anastasia"
    beside Anastasia, her share $30.00). Each way back restores her split
    exactly, and answering again credits Anastasia."""

    def bad(self, client):
        charge, deposit = setup(client, "INTERAC E-TRANSFER FROM PAPAS ANASTASIA")
        st = client.st
        t = st.get_transaction(charge)
        before = (st.splits()[charge], t.my_share, t.share_set, people(client, charge))
        # What the old server did on "Yes, Costco".
        st.link_payback(charge, deposit, "Papas Anastasia", None)
        sp.add_payer(st, st.get_transaction(charge), st.get_transaction(deposit), "Papas Anastasia")
        assert [p["name"] for p in st.splits()[charge]["people"]] == ["Anastasia", "Papas Anastasia"]
        assert st.get_transaction(charge).my_share == 30.0
        return charge, deposit, before

    def now(self, client, charge):
        t = client.st.get_transaction(charge)
        return (client.st.splits()[charge], t.my_share, t.share_set, people(client, charge))

    @pytest.mark.parametrize("whole", [False, True], ids=["from the purchase", "from the e-Transfer"])
    def test_unlink_puts_her_split_back(self, client, whole):
        charge, deposit, before = self.bad(client)
        r = client.delete(f"/api/transactions/{charge}/paybacks/{deposit}",
                          query_string={"whole": "1"} if whole else {})
        assert ok(r)["title"] == "Unlinked · Papas Anastasia taken off the split"
        assert self.now(client, charge) == before
        assert not client.st.get_transaction(deposit).repays
        # Answered again, it's Anastasia's.
        ok(yes(client, deposit, charge))
        assert people(client, charge) == {"Anastasia": (30.0, 0.0)}
        assert client.st.get_transaction(charge).my_share == 60.0


class TestTheAppAsks:
    """The app's side: the tile sends whose share, and a 409 `who_paid`
    opens PP-01 with only the split's people, never Someone new."""

    def src(self, path):
        return (IOS / path).read_text()

    def test_the_tile_sends_its_person(self):
        assert "person: $0.person" in self.src("Views/Review/AnswerSheet.swift")
        review = self.src("Views/Review/ReviewView.swift")
        assert 'if let person = person { body["person"] = person }' in review

    def test_who_paid_is_decoded_and_asked_where_answers_are_sent(self):
        assert 'case whoPaid = "who_paid"' in self.src("API/APIClient.swift")
        for path in ("Views/Review/ReviewView.swift", "Views/Review/QuickSortView.swift",
                     "Views/Transactions/TransactionDetailView.swift"):
            s = self.src(path)
            assert "e.whoPaid != nil" in s and "WhoPaidAskSheet(" in s, path

    def test_the_picker_lists_only_the_split(self):
        s = self.src("Views/Transactions/JointPaybackViews.swift")
        sheet = s[s.index("struct WhoPaidAskSheet"):]
        sheet = sheet[:sheet.index("\n}\n")]
        assert "pastSplits: false, someoneNew: false" in sheet and 'topLabel: "On this split"' in sheet
