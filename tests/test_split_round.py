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
        # SPLIT-15: the replaced part rejoined the payment first, so the
        # rest is one $100 remainder of the $250, not two $50 records.
        assert [(c["amount"], c.get("of")) for c in left] == [(100.0, 250.0)]


class TestWhichApp:
    """SPLIT-14, S-06 v3 / v3a: Another app, named."""

    def test_the_app_name_is_kept_trimmed_and_capped(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 42.06, "day": day(1), "via": "app", "app": "  PayPal  "})
        assert r.status_code == 201 and r.get_json()["title"] == "Sam paid $42.06 through PayPal."
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert sam["app_name"] == "PayPal" and sam["app"] == 42.06 and sam["owes"] == 0
        long = "A" * 45
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                    json={"name": "Sam", "amount": 1, "day": day(0), "via": "app", "app": long})
        assert people(client, i["LOBLAWS"])["Sam"]["app_name"] == "A" * 30

    def test_blank_is_another_app_and_cash_never_keeps_a_name(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}, {"name": "Priya"}])
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 28.04, "via": "app", "app": "   "})
        assert r.get_json()["title"] == "Sam paid $28.04 through another app."
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                    json={"name": "Priya", "amount": 28.04, "via": "cash", "app": "PayPal"})
        p = people(client, i["LOBLAWS"])
        assert p["Sam"]["app_name"] is None and p["Priya"]["app_name"] is None
        assert client.get("/api/split/apps").get_json()["apps"] == []

    def test_used_before_newest_first_one_per_name(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        for n, app in enumerate(["Wise", "paypal", "PayPal", "Revolut", "Cash App", "Zelle"]):
            client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 1, "day": day(10 - n), "via": "app", "app": app})
        assert client.get("/api/split/apps").get_json()["apps"] == ["Zelle", "Cash App", "Revolut", "PayPal"]

    def test_owed_to_you_says_which_app(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                    json={"name": "Sam", "amount": 42.06, "day": when, "via": "app", "app": "PayPal"})
        back = client.get("/api/owed").get_json()["paid_back"]
        assert [(b["name"], b.get("app"), b.get("app_name")) for b in back] == [("Sam", True, "PayPal")]


class TestCashOnePayment:
    """SPLIT-15: a partly deposited cash payment is one payment."""

    def setup(self, c, when):
        i = add(c, tx("AIRBNB", 500.0, "Travel"),
                tx("DEPOSIT", -200.0, when=when, merchant="Deposit at branch"),
                tx("DEPOSIT 2", -50.0, when=when, merchant="Deposit at branch"))
        split(c, i["AIRBNB"], mode="even", people=[{"name": "Priya"}])
        c.post(f"/api/transactions/{i['AIRBNB']}/split/cash", json={"name": "Priya", "amount": 250, "day": when})
        cid = c.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"][0]["id"]
        r = c.post(f"/api/transactions/{i['DEPOSIT']}/parts",
                   json={"parts": [{"kind": "cash", "amount": 200, "cash_ids": [cid]}]})
        assert r.status_code == 200, r.get_json()
        return i

    def test_listed_once_with_what_was_deposited(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = self.setup(client, when)
        priya = people(client, i["AIRBNB"])["Priya"]
        assert priya["cash"] == 250 and priya["paid"] == 250 and priya["owes"] == 0
        assert [(p["amount"], p["deposited"], p["still"], p["deposited_on"]) for p in priya["payments"]] \
            == [(250.0, 200.0, 50.0, when)]
        back = client.get("/api/owed").get_json()["paid_back"]
        assert [(b["amount"], b["deposited"], b["still"]) for b in back] == [(250.0, 200.0, 50.0)]

    def test_the_rest_is_a_remainder_not_a_payment(self, client):
        i = self.setup(client, TODAY.replace(day=1).isoformat())
        left = client.get(f"/api/transactions/{i['DEPOSIT 2']}/cash-matches").get_json()["cash"]
        assert [(c["name"], c["amount"], c["of"]) for c in left] == [("Priya", 50.0, 250.0)]

    def test_unlinking_the_deposit_joins_it_back(self, client):
        i = self.setup(client, TODAY.replace(day=1).isoformat())
        assert len(client.st.split_cash()) == 2
        r = client.delete(f"/api/transactions/{i['DEPOSIT']}/parts")
        assert r.status_code == 200, r.get_json()
        rows = client.st.split_cash()
        assert [(c["amount"], c["deposit_id"]) for c in rows] == [(250.0, None)]
        priya = people(client, i["AIRBNB"])["Priya"]
        assert [(p["amount"], p["deposited"]) for p in priya["payments"]] == [(250.0, 0.0)]
        left = client.get(f"/api/transactions/{i['DEPOSIT 2']}/cash-matches").get_json()["cash"]
        assert [(c["amount"], c.get("of")) for c in left] == [(250.0, None)]


class TestRemoveOnlyHere:
    """SPLIT-16: removing someone unlinks only this purchase's part."""

    def setup(self, c):
        i = add(c, tx("LOBLAWS", 84.12, "Groceries"), tx("COSTCO", 63.92, "Shopping"),
                tx("E-TRANSFER FROM PRIYA", -60.0, when=day(1), merchant="Priya"))
        split(c, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}, {"name": "Priya"}])
        split(c, i["COSTCO"], mode="even", people=[{"name": "Priya"}])
        c.st.link_payback(i["LOBLAWS"], i["E-TRANSFER FROM PRIYA"], "Priya", 28.04)
        c.st.set_payback_more(i["E-TRANSFER FROM PRIYA"], [(i["COSTCO"], 31.96)])
        return i

    def test_the_alert_knows_it_paid_other_purchases(self, client):
        i = self.setup(client)
        priya = people(client, i["LOBLAWS"])["Priya"]
        assert priya["shared"] == [{"whole": 60.0, "here": 28.04, "others": ["COSTCO"], "word": "e-Transfer"}]
        assert people(client, i["LOBLAWS"])["Sam"]["shared"] == []

    def test_costco_stays_paid_and_the_rest_is_left_to_sort(self, client):
        i = self.setup(client)
        r = split(client, i["LOBLAWS"], mode="amount", you=56.08, people=[{"name": "Sam", "amount": 28.04}])
        assert r.status_code == 200, r.get_json()
        assert list(people(client, i["LOBLAWS"])) == ["Sam"]
        costco = people(client, i["COSTCO"])["Priya"]
        assert costco["paid"] == 31.96 and costco["owes"] == 0
        rest = next(q for q in client.get("/api/review").get_json()["money_in"] if q.get("rest"))
        assert rest["txn"]["amount"] == -28.04 and rest["rest"]["whole"] == 60.0
        assert "$28.04 left to sort from a $60.00 deposit." == rest["reason"]
        parts = detail(client, i["E-TRANSFER FROM PRIYA"])["parts"]
        assert sorted(p["kind"] for p in parts) == ["payback", "rest"]

    def test_undo_puts_the_link_back_on_loblaws(self, client):
        i = self.setup(client)
        r = split(client, i["LOBLAWS"], mode="amount", you=56.08, people=[{"name": "Sam", "amount": 28.04}])
        undo = r.get_json()["undo"]
        r = client.post("/api/transactions/undo", json=undo)
        assert r.status_code == 200, r.get_json()
        priya = people(client, i["LOBLAWS"])["Priya"]
        assert priya["paid"] == 28.04 and priya["owes"] == 0
        assert people(client, i["COSTCO"])["Priya"]["paid"] == 31.96
        t = next(x for x in client.st.all_transactions() if x.fingerprint == i["E-TRANSFER FROM PRIYA"])
        assert t.repays == i["LOBLAWS"] and t.also_repays == {i["COSTCO"]: 31.96} and not t.excluded
        assert not client.st.parts().get(i["E-TRANSFER FROM PRIYA"])
        assert not any(q.get("rest") for q in client.get("/api/review").get_json()["money_in"])

    def test_a_payback_for_only_this_purchase_goes_back_whole(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"),
                tx("E-TRANSFER FROM PRIYA", -28.04, when=day(1), merchant="Priya"))
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}, {"name": "Priya"}])
        link(client, i["LOBLAWS"], i["E-TRANSFER FROM PRIYA"], "Priya")
        split(client, i["LOBLAWS"], mode="amount", you=56.08, people=[{"name": "Sam", "amount": 28.04}])
        t = next(x for x in client.st.all_transactions() if x.fingerprint == i["E-TRANSFER FROM PRIYA"])
        assert t.repays is None and not client.st.parts().get(t.fingerprint)


# ── 2026-11-09, product owner decisions: SPLIT-01 (b′), SPLIT-04/05 (S-11 v2),
#    SPLIT-06 (a, held for the Quick sort card) ─────────────────────────────

class TestShortOnlyWithYou:
    """SPLIT-01 (b′), S-03b v2: the rest stays hers only when she's in it."""

    def test_short_with_you_keeps_the_rest(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        d = split(client, i["LOBLAWS"], mode="amount", you=40, people=[{"name": "Sam", "amount": 40}]).get_json()
        assert d["splitting"]["you"] == 44.12, "Your share $44.12 · $4.12 of it is the rest"

    def test_short_without_you_is_left_to_assign(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        r = split(client, i["LOBLAWS"], mode="amount", include_me=False, people=[{"name": "Sam", "amount": 80}])
        assert r.status_code == 400 and r.get_json()["error"] == "$4.12 left to assign."
        assert "splitting" not in detail(client, i["LOBLAWS"]) or not detail(client, i["LOBLAWS"])["splitting"]

    def test_percent_short_without_you_is_left_to_assign(self, client):
        i = add(client, tx("PAI", 85.0, "Dining"))
        r = split(client, i["PAI"], mode="percent", include_me=False,
                  people=[{"name": "Sam", "percent": 50}, {"name": "Priya", "percent": 40}])
        assert r.status_code == 400 and r.get_json()["error"] == "10% left to assign."

    def test_exact_without_you_still_saves(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        d = split(client, i["LOBLAWS"], mode="amount", include_me=False,
                  people=[{"name": "Sam", "amount": 84.12}]).get_json()
        assert d["splitting"]["you"] == 0


class TestRestTiles:
    """SPLIT-04, S-11 v2: every tile on "What's the other $172?" is a part."""

    def deposit(self, c, *more):
        return add(c, tx("FLIGHT", 856.0, "Travel", when=day(20)),
                   tx("E-TRANSFER FROM DAD", -600.0, when=day(1), merchant="Dad"), *more)

    def save(self, c, dep, parts):
        r = c.post(f"/api/transactions/{dep}/parts", json={"parts": parts})
        assert r.status_code == 200, r.get_json()
        return r.get_json()

    def test_gift_and_dad_overpaid_in_two_passes(self, client):
        """THL-291 AC: the same $172 as $100 gift + $72 they overpaid."""
        i = self.deposit(client)
        split(client, i["FLIGHT"], mode="even", people=[{"name": "Dad"}])
        self.save(client, i["E-TRANSFER FROM DAD"], [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT"], "person": "Dad"},
            {"kind": "gift", "amount": 100}, {"kind": "overpaid", "amount": 72, "person": "Dad"}])
        owed = client.get("/api/owed").get_json()
        assert owed["you_owe"][0]["name"] == "Dad" and owed["you_owe"][0]["total"] == 72.0

    def test_lent_me_this_and_money_i_lent_back(self, client):
        i = self.deposit(client)
        out = self.save(client, i["E-TRANSFER FROM DAD"], [
            {"kind": "loan", "amount": 400}, {"kind": "lent_back", "amount": 200}])
        cats = {p["kind"]: p["category"] for p in out["parts"]}
        assert cats == {"loan": "Borrowed", "lent_back": "Lent"}

    def test_not_mine_is_not_a_part(self, client):
        i = self.deposit(client)
        r = client.post(f"/api/transactions/{i['E-TRANSFER FROM DAD']}/parts",
                        json={"parts": [{"kind": "not_mine", "amount": 600}]})
        assert r.status_code == 400

    def test_work_paying_me_back_counts_the_expense_again_and_unlink_leaves_it_out(self, client):
        i = add(client, tx("HOTEL", 300.0, "Lodging", when=day(20)),
                tx("ACME PAYROLL EXP", -500.0, when=day(1), merchant="Acme"))
        r = client.post(f"/api/transactions/{i['HOTEL']}/mark", json={"case": "work"})
        assert r.status_code == 200, r.get_json()
        assert detail(client, i["HOTEL"])["excluded"]
        dep = i["ACME PAYROLL EXP"]
        out = self.save(client, dep, [{"kind": "reimbursement", "amount": 300, "charge": i["HOTEL"]},
                                      {"kind": "income", "amount": 200, "income_kind": "other"}])
        part = next(p for p in out["parts"] if p["kind"] == "reimbursement")
        assert part["charge"]["id"] == i["HOTEL"]
        assert not detail(client, i["HOTEL"])["excluded"], "reimbursed in full, so it counts, paid back"
        assert detail(client, part["id"])["repays"] == i["HOTEL"]
        assert client.delete(f"/api/transactions/{dep}/parts").status_code == 200
        assert detail(client, i["HOTEL"])["excluded"], "unlinked: waiting to be reimbursed again"

    def test_reimbursement_needs_the_expense(self, client):
        i = self.deposit(client)
        r = client.post(f"/api/transactions/{i['E-TRANSFER FROM DAD']}/parts",
                        json={"parts": [{"kind": "reimbursement", "amount": 600}]})
        assert r.status_code == 400 and r.get_json()["error"] == "Pick the expense it reimburses."


class TestHeldSplitFromQuickSort:
    """SPLIT-06 (a), T-98s: Yes on the card saves the held split and the
    category in one request, and one Undo puts both back."""

    def test_yes_saves_split_and_category_and_undo_restores_both(self, client):
        i = add(client, tx("LOBLAWS", 84.12, ""))
        before = detail(client, i["LOBLAWS"])["category"]
        r = split(client, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}], category="Groceries", settle=True)
        assert r.status_code == 200, r.get_json()
        d = detail(client, i["LOBLAWS"])
        assert d["category"] == "Groceries" and d["splitting"]["you"] == 42.06
        assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        d = detail(client, i["LOBLAWS"])
        assert not d.get("splitting") and d["category"] == before


class TestHeldSplitFromQuickSortSheet:
    """SPLIT-20 (SPLIT-06 (a) everywhere): Quick sort's sheet holds a split
    for the card, as the card's page does, instead of saving it at once."""

    IOS = __import__("pathlib").Path(__file__).resolve().parents[1] / "ios" / "Pearl"

    def read(self, rel):
        return (self.IOS / rel).read_text(encoding="utf-8")

    def test_the_sheet_passes_on_hold_when_it_holds(self):
        sheet = self.read("Views/Review/AnswerSheet.swift")
        assert "onHold: holds && onHeldSplit != nil ?" in sheet
        assert "onHeldSplit(split, name)" in sheet

    def test_quick_sort_holds_the_split_on_the_card(self):
        quick = self.read("Views/Review/QuickSortView.swift")
        assert "onHeldSplit: { split, category in" in quick
        assert "split: split)" in quick
        # Skip still forgets it, and Yes sends it with the category in one request.
        assert "drafts[ask.id]?.split = nil" in quick
        assert "split.answer(ask.t.id, category: splitCategory(ask, draft))" in quick


class TestOtherIncomeKinds:
    """SPLIT-18, S-11k / T-08k: Other income asks which kind: Interest,
    Government credits, Tax refund or Other income (finance/income.py)."""

    @pytest.mark.parametrize("kind", ["interest", "government", "tax_refund", "other"])
    def test_a_part_can_be_each_kind(self, client, kind):
        i = add(client, tx("E-TRANSFER FROM DAD", -600.0, when=day(1), merchant="Dad"))
        r = client.post(f"/api/transactions/{i['E-TRANSFER FROM DAD']}/parts", json={"parts": [
            {"kind": "gift", "amount": 428}, {"kind": "income", "amount": 172, "income_kind": kind}]})
        assert r.status_code == 200, r.get_json()
        part = next(p for p in r.get_json()["parts"] if p["kind"] == "income")
        assert part["income_kind"] == kind

    @pytest.mark.parametrize("kind", ["interest", "government", "tax_refund", "other"])
    def test_the_shared_page_saves_each_kind(self, client, kind):
        i = add(client, tx("NORTHWIND LTD", -85.0, when=day(1), merchant="Northwind Ltd"))
        tid = i["NORTHWIND LTD"]
        r = client.post(f"/api/transactions/{tid}/mark", json={"case": "pay", "income_kind": kind})
        assert r.status_code == 200, r.get_json()
        d = detail(client, tid)
        assert d["category"] == "Income" and d["income_type"] == kind


class TestCashExtra:
    """SPLIT-19, S-11c: what the extra from cash or another app is. Sam
    owes $42.06 on Loblaws and pays $60.00 cash: the $17.94 is said in
    pieces, every record shares the payment's origin, and Undo takes it all."""

    def setup(self, c, **pay):
        i = add(c, tx("LOBLAWS", 84.12, "Groceries", when=day(6)),
                tx("PIZZA NOVA", 30.0, "Dining", when=day(7)),
                tx("DEPOSIT", -60.0, when=day(0), merchant="Deposit at branch"))
        split(c, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        split(c, i["PIZZA NOVA"], mode="amount", people=[{"name": "Sam", "amount": 10.0},
                                                         {"name": "Priya", "amount": 10.0}])
        return i

    def pay(self, c, i, extra, **more):
        return c.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                      json={"name": "Sam", "amount": 60, "day": day(4), "extra": extra, **more})

    def test_the_extra_has_to_add_up(self, client):
        i = self.setup(client)
        r = self.pay(client, i, [{"kind": "gift", "amount": 10}])
        assert r.status_code == 400 and r.get_json()["error"] == "$7.94 of the extra isn’t said yet."
        r = self.pay(client, i, [{"kind": "gift", "amount": 20}])
        assert r.status_code == 400 and r.get_json()["error"] == "That’s $2.06 more than the extra."
        assert client.st.split_cash() == []

    def test_only_when_they_paid_more(self, client):
        i = self.setup(client)
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 42.06, "extra": [{"kind": "gift", "amount": 1}]})
        assert r.status_code == 400 and r.get_json()["error"] == "Sam didn’t pay more than they owe."

    def test_overpaid_stays_under_you_owe(self, client):
        i = self.setup(client)
        assert self.pay(client, i, [{"kind": "overpaid", "amount": 17.94}]).status_code == 201
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert (sam["paid"], sam["owes"], sam["over"]) == (60.0, 0.0, 17.94)

    def test_paying_me_back_pays_other_shares(self, client):
        i = self.setup(client)
        r = self.pay(client, i, [{"kind": "payback", "amount": 10, "charge": i["PIZZA NOVA"]},
                                 {"kind": "payback", "amount": 7.94, "charge": i["PIZZA NOVA"],
                                  "person": "Priya"}])
        assert r.status_code == 201, r.get_json()
        assert people(client, i["LOBLAWS"])["Sam"]["paid"] == 42.06
        pizza = people(client, i["PIZZA NOVA"])
        assert (pizza["Sam"]["owes"], pizza["Priya"]["owes"]) == (0.0, 2.06)
        root = r.get_json()["id"]
        assert {c.get("origin") or c["id"] for c in client.st.split_cash()} == {root}

    def test_a_payback_cant_be_more_than_the_share(self, client):
        i = self.setup(client)
        r = self.pay(client, i, [{"kind": "payback", "amount": 17.94, "charge": i["PIZZA NOVA"]}])
        assert r.status_code == 400 and r.get_json()["error"] == "That’s more than Sam owes on PIZZA NOVA."

    def test_a_gift_is_money_in_once_and_not_a_bank_row(self, client):
        from finance.analytics import monthly_totals
        i = self.setup(client)
        before = next(m for m in monthly_totals(client.st.all_transactions()) if m["month"] == MONTH)["income"]
        r = self.pay(client, i, [{"kind": "gift", "amount": 17.94}])
        assert r.status_code == 201, r.get_json()
        after = next(m for m in monthly_totals(client.st.all_transactions()) if m["month"] == MONTH)["income"]
        assert round(after - before, 2) == 17.94
        listed = client.get("/api/transactions").get_json()["transactions"]
        assert not any(t["description"].startswith("A gift · Sam") for t in listed)
        assert people(client, i["LOBLAWS"])["Sam"]["paid"] == 42.06

    def test_gave_it_back_keeps_what_was_owed(self, client):
        i = self.setup(client)
        assert self.pay(client, i, [{"kind": "returned", "amount": 17.94}]).status_code == 201
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert (sam["paid"], sam["owes"], sam.get("over", 0.0)) == (42.06, 0.0, 0.0)
        pay = sam["payments"][0]
        assert (pay["amount"], pay["whole"], pay["given_back"]) == (42.06, 60.0, 17.94)
        # A later deposit is offered only what she kept.
        cash = client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"]
        assert [c["amount"] for c in cash] == [42.06]

    def test_a_later_deposit_takes_every_piece_and_the_gift_counts_once(self, client):
        from finance.analytics import monthly_totals
        i = self.setup(client)
        before = next(m for m in monthly_totals(client.st.all_transactions()) if m["month"] == MONTH)["income"]
        self.pay(client, i, [{"kind": "gift", "amount": 10}, {"kind": "overpaid", "amount": 7.94}])
        cash = client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"]
        assert [(c["name"], c["amount"], len(c["ids"])) for c in cash] == [("Sam", 60.0, 2)]
        r = client.post(f"/api/transactions/{i['DEPOSIT']}/parts",
                        json={"parts": [{"kind": "cash", "amount": 60, "cash_ids": cash[0]["ids"]}]})
        assert r.status_code == 200, r.get_json()
        after = next(m for m in monthly_totals(client.st.all_transactions()) if m["month"] == MONTH)["income"]
        assert round(after - before, 2) == 10.0, "the deposit is moving money; the gift counted once"
        assert all(c["deposit_id"] for c in client.st.split_cash())

    def test_undo_removes_the_whole_payment(self, client):
        i = self.setup(client)
        r = self.pay(client, i, [{"kind": "gift", "amount": 5},
                                 {"kind": "payback", "amount": 10, "charge": i["PIZZA NOVA"]},
                                 {"kind": "returned", "amount": 2.94}])
        assert r.status_code == 201, r.get_json()
        assert r.get_json()["undo"]["cash_payment"] == r.get_json()["id"]
        assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        assert client.st.split_cash() == []
        assert not any(t.source == "split_gift" for t in client.st.all_transactions())
        assert people(client, i["PIZZA NOVA"])["Sam"]["owes"] == 10.0
        assert people(client, i["LOBLAWS"])["Sam"]["owes"] == 42.06

    def test_another_app_extra_is_never_offered_to_a_deposit(self, client):
        i = self.setup(client)
        r = self.pay(client, i, [{"kind": "gift", "amount": 17.94}], via="app", app="PayPal")
        assert r.status_code == 201
        assert client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"] == []

    def test_without_extra_it_is_recorded_whole_as_before(self, client):
        i = self.setup(client)
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 60})
        assert r.status_code == 201
        assert people(client, i["LOBLAWS"])["Sam"]["over"] == 17.94


class TestPaymentNamesWhatItPaid:
    """SPLIT-19 list line (round 10): a cash or app payment whose extra paid
    back other shares is one payment that names every purchase it paid:
    "Sam · Cash · $60.00 · Nov 13 · paid back Loblaws and Pizza Nova"."""

    def setup(self, c, when):
        i = add(c, tx("LOBLAWS", 84.12, "Groceries", when=day(6)),
                tx("PIZZA NOVA", 30.0, "Dining", when=day(7)),
                tx("COSTCO", 40.0, "Groceries", when=day(8)))
        split(c, i["LOBLAWS"], mode="even", people=[{"name": "Sam"}])
        split(c, i["PIZZA NOVA"], mode="amount", people=[{"name": "Sam", "amount": 10.0},
                                                         {"name": "Priya", "amount": 10.0}])
        split(c, i["COSTCO"], mode="even", people=[{"name": "Sam"}])
        return i

    def pay(self, c, i, when, extra, **more):
        r = c.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                   json={"name": "Sam", "amount": 60, "day": when, "extra": extra, **more})
        assert r.status_code == 201, r.get_json()
        return r

    def test_the_payment_names_every_purchase_its_own_first(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = self.setup(client, when)
        self.pay(client, i, when, [{"kind": "payback", "amount": 10, "charge": i["PIZZA NOVA"]},
                                   {"kind": "gift", "amount": 7.94}])
        pay = people(client, i["LOBLAWS"])["Sam"]["payments"][0]
        assert pay["paid_back"] == ["LOBLAWS", "PIZZA NOVA"]
        # The other purchase's share sees the same payment, its first purchase first.
        other = people(client, i["PIZZA NOVA"])["Sam"]["payments"][0]
        assert other["paid_back"] == ["LOBLAWS", "PIZZA NOVA"]

    def test_owed_to_you_lists_it_once_for_what_paid_back(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = self.setup(client, when)
        self.pay(client, i, when, [{"kind": "payback", "amount": 10, "charge": i["PIZZA NOVA"]},
                                   {"kind": "payback", "amount": 7.94, "charge": i["PIZZA NOVA"],
                                    "person": "Priya"}])
        back = client.get("/api/owed").get_json()["paid_back"]
        assert [(b["name"], b["merchant"], b["amount"], b.get("cash"), b["paid_back"]) for b in back] \
            == [("Sam", "LOBLAWS", 60.0, True, ["LOBLAWS", "PIZZA NOVA"])]

    def test_three_purchases_are_all_named(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = self.setup(client, when)
        self.pay(client, i, when, [{"kind": "payback", "amount": 10, "charge": i["PIZZA NOVA"]},
                                   {"kind": "payback", "amount": 7.94, "charge": i["COSTCO"]}],
                 via="app", app="PayPal")
        back = client.get("/api/owed").get_json()["paid_back"]
        assert [(b["amount"], b.get("app_name"), b["paid_back"]) for b in back] \
            == [(60.0, "PayPal", ["LOBLAWS", "PIZZA NOVA", "COSTCO"])]

    def test_a_payment_for_one_purchase_names_nothing(self, client):
        when = TODAY.replace(day=1).isoformat()
        i = self.setup(client, when)
        self.pay(client, i, when, [{"kind": "gift", "amount": 17.94}])
        assert "paid_back" not in people(client, i["LOBLAWS"])["Sam"]["payments"][0]
        back = client.get("/api/owed").get_json()["paid_back"]
        assert [(b["amount"], "paid_back" in b) for b in back] == [(42.06, False)]


class TestPearlAsksWhoItWas:
    """SPLIT-21, THL-181 "If Pearl can't tell who, it asks" (S-35a 1030:41556,
    S-35b 1030:41984): a payback that names nobody on the split counts for
    someone only when exactly one share still owed is its amount. Two, or
    none, and it waits for her to say who. Paybacks dated before ASK_FROM
    keep the old guess, so nothing she has already seen changes."""

    IOS = __import__("pathlib").Path(__file__).resolve().parents[1] / "ios" / "Pearl"

    def setup(self, c, bought, came, amount, who=None, merchant="Interac e-Transfer"):
        deposit = Transaction(date=came, description="INTERAC E-TRANSFER", merchant=merchant,
                              amount=-amount, category="", account_id="chq", account_name="TD Chequing",
                              raw={"account_type": "depository", **({"counterparty": who} if who else {})})
        i = add(c, tx("PIZZA NOVA", 90.0, "Dining", when=bought), deposit)
        r = split(c, i["PIZZA NOVA"], mode="amount", people=[{"name": "Sam", "amount": 30.0},
                                                             {"name": "Priya S.", "amount": 30.0}])
        assert r.status_code == 200, r.get_json()
        return i["PIZZA NOVA"], i["INTERAC E-TRANSFER"]

    def owes(self, c, charge):
        return {n: p["owes"] for n, p in people(c, charge).items()}

    def test_two_shares_fit_so_it_counts_for_nobody(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 30.0)
        link(client, charge, deposit, None)
        assert self.owes(client, charge) == {"Sam": 30.0, "Priya S.": 30.0}

    def test_none_fits_so_it_counts_for_nobody(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 25.0)
        link(client, charge, deposit, None)
        # Before THL-181 this went to Sam, the first who still owed.
        assert self.owes(client, charge) == {"Sam": 30.0, "Priya S.": 30.0}

    def test_exactly_one_share_fits_so_it_counts_for_them(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 30.0)
        link(client, charge, deposit, None)
        # Sam pays by name; now only Priya's $30.00 is the unnamed one's amount.
        named = Transaction(date="2026-11-17", description="E-TRANSFER FROM SAM", merchant="Sam",
                            amount=-30.0, category="", account_id="chq", account_name="TD Chequing",
                            raw={"account_type": "depository", "counterparty": "Sam"})
        i = add(client, named)
        link(client, charge, i["E-TRANSFER FROM SAM"], "Sam")
        assert self.owes(client, charge) == {"Sam": 0.0, "Priya S.": 0.0}

    def test_one_that_names_someone_on_the_split_is_theirs(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 30.0)
        link(client, charge, deposit, "Priya S.")
        assert self.owes(client, charge) == {"Sam": 30.0, "Priya S.": 0.0}

    def test_an_old_payback_keeps_what_it_showed(self, client):
        from finance.splits import ASK_FROM
        assert ASK_FROM == "2026-11-10"
        # Both fit, and before ASK_FROM it went to the first who owed, as it always had.
        charge, deposit = self.setup(client, "2026-10-20", "2026-10-25", 30.0)
        link(client, charge, deposit, None)
        assert self.owes(client, charge) == {"Sam": 0.0, "Priya S.": 30.0}
        # And one that fit nobody still went to the first who owed.
        other = Transaction(date="2026-10-26", description="DEPOSIT 25", merchant="Deposit", amount=-25.0,
                            category="", account_id="chq", account_name="TD Chequing",
                            raw={"account_type": "depository"})
        i = add(client, other)
        link(client, charge, i["DEPOSIT 25"], None)
        assert self.owes(client, charge) == {"Sam": 0.0, "Priya S.": 5.0}

    def test_owing_names_someone_who_is_on_no_split(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 45.0, who="Jordan")
        r = client.get(f"/api/transactions/{deposit}/owing").get_json()
        assert r["from"] is None and r["named"] == "Jordan"
        assert sorted((x["person"], x["owes"]) for x in r["items"]) == [("Priya S.", 30.0), ("Sam", 30.0)]

    def test_owing_names_nobody_when_the_bank_left_the_name_off(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 30.0)
        r = client.get(f"/api/transactions/{deposit}/owing").get_json()
        assert r["from"] is None and r["named"] is None

    def test_owing_from_someone_on_a_split_is_theirs(self, client):
        charge, deposit = self.setup(client, "2026-11-02", "2026-11-16", 30.0, who="Sam", merchant="Sam")
        r = client.get(f"/api/transactions/{deposit}/owing").get_json()
        assert r["from"] == "Sam" and r["named"] is None

    def test_the_sheet_asks_instead_of_ticking(self):
        flow = (self.IOS / "Views/Transactions/PartsFlow.swift").read_text(encoding="utf-8")
        # S-35a / S-35b sections and lines.
        assert 'label("Could be either")' in flow
        assert "each owe \\(amount), so Pearl won’t guess. Tick who sent it." in flow
        assert "isn’t on any of your splits, and no one owes \\(amount)." in flow
        assert '"No one owes \\(amount). \\(tail)"' in flow
        assert 'let tail = "Tick what it paid back, or search for the purchase."' in flow
        # Only the one exact fit is ticked; two or none, nothing is.
        assert "if sender == nil, fits.count == 1 { toggle(fits[0]) }" in flow
        assert "fits.count != 1" in flow
        # Next stays off until she ticks one; what's left goes to S-11 v2.
        assert '.buttonStyle(NacreButtonStyle()).disabled(picked.isEmpty)' in flow
        assert "parts.isEmpty || asked ? .kind : .progress" in flow
        # VoiceOver: "Sam, Pizza Nova, November 2, 30 dollars, not selected".
        assert '.accessibilityValue(on ? "selected" : "not selected")' in flow
        assert "Format.monthDay(o.date)" in flow
        assert "named = r.named" in flow
