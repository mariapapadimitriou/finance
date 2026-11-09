"""The split round with designBOT (ios/bots/split-transactions-log.md,
2026-11-09): Edit split after people have paid (SPLIT-02), Edit on a
deposit in parts (SPLIT-03), split and link as one save (SPLIT-07), what
Check and save changes (SPLIT-09), odd cents in % (SPLIT-10), and another
app or cash partly deposited (SPLIT-11)."""

from __future__ import annotations

from calendar import month_name
from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
MONTH_NAME = month_name[int(MONTH[5:7])]


def day(n):
    return f"{MONTH}-{28 - n:02d}"


def tx(desc, amount, category="", when=None, merchant=None):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "round.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def people(c, tid):
    return {p["name"]: p for p in detail(c, tid)["splitting"]["people"]}


def split(c, tid, **body):
    return c.put(f"/api/transactions/{tid}/split", json=body)


def link(c, charge, inflow, person):
    r = c.post(f"/api/transactions/{charge}/paybacks/{inflow}", json={"person": person})
    assert r.status_code == 200, r.get_json()
    return r.get_json()


class TestEditAfterPaying:
    """SPLIT-02, S-03e / S-03f."""

    def setup(self, c):
        i = add(c, tx("LOBLAWS", 84.12, "Groceries"),
                tx("E-TRANSFER FROM PRIYA", -28.04, when=day(1), merchant="Priya"))
        split(c, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}, {"name": "Priya"}])
        link(c, i["LOBLAWS"], i["E-TRANSFER FROM PRIYA"], "Priya")
        return i

    def test_removing_someone_who_paid_unlinks_their_payback(self, client):
        i = self.setup(client)
        r = split(client, i["LOBLAWS"], mode="amount", you=56.08, people=[{"name": "Sam", "amount": 28.04}])
        assert r.status_code == 200, r.get_json()
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert (sam["paid"], sam["owes"]) == (0.0, 28.04), "Priya's money never counts for Sam"
        assert detail(client, i["E-TRANSFER FROM PRIYA"]).get("repays") is None
        # One Undo puts Priya and her payback back.
        assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        priya = people(client, i["LOBLAWS"])["Priya"]
        assert (priya["paid"], priya["owes"]) == (28.04, 0.0)

    def test_a_named_payback_is_never_moved_to_someone_else(self, client):
        i = self.setup(client)
        # Priya leaves the split some other way: her payback stays hers.
        client.st.set_split(i["LOBLAWS"], "amount", [{"name": "Sam", "amount": 28.04}], True)
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert sam["paid"] == 0.0 and sam["owes"] == 28.04

    def test_a_share_below_what_was_paid_is_owed_back(self, client):
        i = self.setup(client)
        r = split(client, i["LOBLAWS"], mode="amount", you=36.08,
                  people=[{"name": "Sam", "amount": 28.04}, {"name": "Priya", "amount": 20.0}])
        assert r.status_code == 200, r.get_json()
        priya = people(client, i["LOBLAWS"])["Priya"]
        assert (priya["owes"], priya["over"]) == (0.0, 8.04)
        you_owe = client.get("/api/owed").get_json()["you_owe"]
        assert you_owe[0]["name"] == "Priya" and you_owe[0]["total"] == 8.04
        assert you_owe[0]["items"][0]["split"] is True and you_owe[0]["items"][0]["charge_id"] == i["LOBLAWS"]

    def test_let_go_follows_the_share(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}, {"name": "Priya"}])
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 20, "day": day(2)})
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/let-go", json={"name": "Sam"})
        # Raised to $30: still $20 paid, and $10 let go.
        r = split(client, i["LOBLAWS"], mode="amount", you=26.08,
                  people=[{"name": "Sam", "amount": 30}, {"name": "Priya", "amount": 28.04}])
        assert r.status_code == 200, r.get_json()
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert sam["let_go"]["was"] == 30 and sam["paid"] == 20 and sam["owes"] == 0
        assert detail(client, i["LOBLAWS"])["splitting"]["you"] == round(84.12 - 20 - 28.04, 2)
        # Lowered to $15: nothing let go, and $5 overpaid.
        split(client, i["LOBLAWS"], mode="amount", you=41.08,
              people=[{"name": "Sam", "amount": 15}, {"name": "Priya", "amount": 28.04}])
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert sam["let_go"] is None and sam["over"] == 5.0

    def test_cash_in_a_deposit_blocks_removing_them(self, client):
        i = add(client, tx("PHO", 90.0, "Dining", when=day(6)),
                tx("DEPOSIT", -30.0, when=day(1), merchant="Deposit at branch"))
        split(client, i["PHO"], mode="even", people=[{"name": "Priya"}, {"name": "Sam"}])
        client.post(f"/api/transactions/{i['PHO']}/split/cash", json={"name": "Priya", "amount": 30, "day": day(4)})
        cid = client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"][0]["id"]
        client.post(f"/api/transactions/{i['DEPOSIT']}/parts",
                    json={"parts": [{"kind": "cash", "amount": 30, "cash_ids": [cid]}]})
        r = split(client, i["PHO"], mode="even", people=[{"name": "Sam"}])
        assert r.status_code == 400 and r.get_json()["error"] == "That cash is in a deposit. Unlink the deposit first."

    def test_it_opens_in_the_mode_it_was_saved_in(self, client):
        i = add(client, tx("PAI", 85.0, "Dining"))
        split(client, i["PAI"], mode="percent", you=40, people=[{"name": "Sam", "percent": 35},
                                                                 {"name": "Priya", "percent": 25}])
        s = detail(client, i["PAI"])["splitting"]
        assert s["mode"] == "percent" and [p["weight"] for p in s["people"]] == [35.0, 25.0]


class TestOddCents:
    """SPLIT-10, S-15 v2: thirds in % are rounding, not a gap."""

    def test_thirds_with_you(self, client):
        i = add(client, tx("PAI", 85.0, "Dining"))
        d = split(client, i["PAI"], mode="percent", you=33.33,
                  people=[{"name": "Sam", "percent": 33.33}, {"name": "Priya", "percent": 33.33}]).get_json()
        assert [p["amount"] for p in d["splitting"]["people"]] == [28.33, 28.33]
        assert d["splitting"]["you"] == 28.34

    def test_thirds_without_you_go_from_the_top(self, client):
        i = add(client, tx("GIFT", 10.03, "Shopping"))
        d = split(client, i["GIFT"], mode="percent", include_me=False,
                  people=[{"name": n, "percent": 25} for n in ("A", "B", "C", "D")]).get_json()
        assert [p["amount"] for p in d["splitting"]["people"]] == [2.51, 2.51, 2.51, 2.50]
        d = split(client, i["GIFT"], mode="even", include_me=False,
                  people=[{"name": n} for n in ("A", "B", "C", "D")]).get_json()
        assert [p["amount"] for p in d["splitting"]["people"]] == [2.51, 2.51, 2.51, 2.50]

    def test_a_real_gap_stays_yours(self, client):
        i = add(client, tx("PAI", 85.0, "Dining"))
        d = split(client, i["PAI"], mode="percent", you=30, people=[{"name": "Sam", "percent": 50}]).get_json()
        assert d["splitting"]["people"][0]["amount"] == 42.5 and d["splitting"]["you"] == 42.5


class TestEditParts:
    """SPLIT-03, S-10e: Save changes replaces the parts in one save."""

    def setup(self, c):
        i = add(c, tx("FLIGHT", 856.0, "Travel", when=day(20)), tx("LOBLAWS", 128.0, "Groceries", when=day(10)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        split(c, i["FLIGHT"], mode="amount", people=[{"name": "Dad", "amount": 428}])
        split(c, i["LOBLAWS"], mode="even", people=[{"name": "Dad"}])
        dep = i["E-TRANSFER FROM DAD"]
        r = c.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT"], "person": "Dad"},
            {"kind": "payback", "amount": 64, "charge": i["LOBLAWS"], "person": "Dad"},
            {"kind": "gift", "amount": 108}]})
        assert r.status_code == 200, r.get_json()
        return i, dep

    def test_owing_lists_what_it_already_pays_back(self, client):
        i, dep = self.setup(client)
        linked = client.get(f"/api/transactions/{dep}/owing").get_json()["linked"]
        assert [(x["id"], x["amount"], x["person"], x["share"]) for x in linked] == [
            (i["FLIGHT"], 428.0, "Dad", 428.0), (i["LOBLAWS"], 64.0, "Dad", 64.0)]

    def test_save_changes_replaces(self, client):
        i, dep = self.setup(client)
        parts = [{"kind": "payback", "amount": 428, "charge": i["FLIGHT"], "person": "Dad"},
                 {"kind": "gift", "amount": 172}]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": parts})
        assert r.status_code == 400 and "already in parts" in r.get_json()["error"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": parts, "replace": True})
        assert r.status_code == 200, r.get_json()
        assert [(p["kind"], p["amount"]) for p in detail(client, dep)["parts"]] == [("payback", 428.0), ("gift", 172.0)]
        assert people(client, i["LOBLAWS"])["Dad"]["owes"] == 64.0, "Loblaws is owed again"

    def test_a_failed_replace_keeps_the_old_parts(self, client):
        i, dep = self.setup(client)
        r = client.post(f"/api/transactions/{dep}/parts", json={"replace": True, "parts": [
            {"kind": "gift", "amount": 700}]})
        assert r.status_code == 400
        assert [(p["kind"], p["amount"]) for p in detail(client, dep)["parts"]] == [
            ("payback", 428.0), ("payback", 64.0), ("gift", 108.0)]
        assert people(client, i["FLIGHT"])["Dad"]["owes"] == 0


class TestSplitAndLink:
    """SPLIT-07, S-24 held, S-12c, S-12d."""

    def test_one_save_and_one_undo(self, client):
        i = add(client, tx("COSTCO", 212.40, "Shopping", when=day(10)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        dep = i["E-TRANSFER FROM DAD"]
        body = {"parts": [{"kind": "payback", "amount": 106.20, "charge": i["COSTCO"], "person": "Dad"},
                          {"kind": "gift", "amount": 493.80}],
                "split": {"charge": i["COSTCO"], "mode": "even", "people": [{"name": "Dad"}]}}
        r = client.post(f"/api/transactions/{dep}/parts", json=body).get_json()
        assert r["title"] == "COSTCO split and $600 sorted"
        assert people(client, i["COSTCO"])["Dad"]["owes"] == 0
        assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
        assert "splitting" not in detail(client, i["COSTCO"])
        assert "parts" not in detail(client, dep)

    def test_a_failed_save_splits_nothing(self, client):
        i = add(client, tx("COSTCO", 212.40, "Shopping", when=day(10)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        dep = i["E-TRANSFER FROM DAD"]
        r = client.post(f"/api/transactions/{dep}/parts", json={
            "parts": [{"kind": "payback", "amount": 106.20, "charge": i["COSTCO"], "person": "Dad"}],
            "split": {"charge": i["COSTCO"], "mode": "even", "people": [{"name": "Dad"}]}})
        assert r.status_code == 400 and r.get_json()["error"] == "$493.80 left to sort."
        assert "splitting" not in detail(client, i["COSTCO"])


class TestPreview:
    """SPLIT-09, S-12 v2 WHAT CHANGES."""

    def test_payback_in_the_purchases_month_gift_in_allowance(self, client):
        i = add(client, tx("FLIGHT", 856.0, "Travel", when=day(20)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        dep = i["E-TRANSFER FROM DAD"]
        r = client.post(f"/api/transactions/{dep}/parts/preview", json={"parts": [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT"], "person": "Dad"},
            {"kind": "gift", "amount": 172}]}).get_json()
        assert r["changes"] == [{"label": f"Allowance · {MONTH_NAME}", "delta": 172.0},
                                {"label": f"Travel · {MONTH_NAME}", "before": 856.0, "after": 428.0}]
        assert "parts" not in detail(client, dep), "nothing saved"


class TestAnotherAppAndPartlyDeposited:
    """SPLIT-11, S-06 v2, S-13 v2."""

    def test_another_app_is_paid_but_never_cash(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries", when=day(6)),
                tx("DEPOSIT", -42.06, when=day(1), merchant="Deposit at branch"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 42.06, "day": day(4), "via": "app"})
        assert r.status_code == 201
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert (sam["owes"], sam["cash"], sam["app"]) == (0.0, 0.0, 42.06)
        assert client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"] == []

    def test_cash_partly_deposited_keeps_the_rest(self, client):
        i = add(client, tx("AIRBNB", 500.0, "Travel", when=day(10)),
                tx("DEPOSIT", -200.0, when=day(1), merchant="Deposit at branch"),
                tx("DEPOSIT 2", -50.0, when=day(0), merchant="Deposit at branch"))
        split(client, i["AIRBNB"], mode="even", people=[{"name": "Priya"}])
        client.post(f"/api/transactions/{i['AIRBNB']}/split/cash", json={"name": "Priya", "amount": 250, "day": day(8)})
        cid = client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"][0]["id"]
        r = client.post(f"/api/transactions/{i['DEPOSIT']}/parts",
                        json={"parts": [{"kind": "cash", "amount": 200, "cash_ids": [cid]}]})
        assert r.status_code == 200, r.get_json()
        priya = people(client, i["AIRBNB"])["Priya"]
        assert priya["owes"] == 0 and priya["cash"] == 250
        left = client.get(f"/api/transactions/{i['DEPOSIT 2']}/cash-matches").get_json()["cash"]
        assert [c["amount"] for c in left] == [50.0]
        # S-10e: the same cash part sent again with Save changes still fits.
        parts = detail(client, i["DEPOSIT"])["parts"]
        assert parts[0]["cash_ids"] == [cid]
        r = client.post(f"/api/transactions/{i['DEPOSIT']}/parts", json={"replace": True, "parts": [
            {"kind": "cash", "amount": 150, "cash_ids": parts[0]["cash_ids"]},
            {"kind": "gift", "amount": 50}]})
        assert r.status_code == 200, r.get_json()
        assert people(client, i["AIRBNB"])["Priya"]["cash"] == 250
        left = client.get(f"/api/transactions/{i['DEPOSIT 2']}/cash-matches").get_json()["cash"]
        assert sorted(c["amount"] for c in left) == [50.0, 50.0]
