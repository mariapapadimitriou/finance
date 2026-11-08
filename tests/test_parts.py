"""THL-291: splits and paybacks that hold up — split methods, a deposit
split into parts (the leftover can be anything), cash in hand, Let it go,
and Owed to you. Each test is one of the ticket's acceptance criteria."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
# Every row in last month, so a month's totals hold them whatever today is.
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def day(n):
    return f"{MONTH}-{28 - n:02d}"


def tx(desc, amount, category="", when=None, merchant=None, account="chq", kind="depository"):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name="TD Chequing",
                       raw={"account_type": kind})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "parts.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def month_totals(c):
    return c.get("/api/transactions/list", query_string={"month": MONTH}).get_json()["month_totals"]


def split(c, tid, **body):
    return c.put(f"/api/transactions/{tid}/split", json=body)


class TestSplitMethods:
    def test_amounts_can_be_short_but_not_over(self, client):
        """2026-11-08: a split saves before every part is known; what nobody
        has been given yet stays hers. More than the charge still can't."""
        i = add(client, tx("PAI", 85.0, "Dining"))
        d = split(client, i["PAI"], mode="amount", you=30,
                  people=[{"name": "Priya", "amount": 30}, {"name": "Sam", "amount": 20}]).get_json()
        assert d["splitting"]["you"] == 35.0
        assert [p["amount"] for p in d["splitting"]["people"]] == [30.0, 20.0]
        r = split(client, i["PAI"], mode="amount", you=40,
                  people=[{"name": "Priya", "amount": 30}, {"name": "Sam", "amount": 20}])
        assert r.status_code == 400 and r.get_json()["error"] == "That’s $5.00 more than the charge."
        d = split(client, i["PAI"], mode="amount", include_me=False,
                  people=[{"name": "Priya", "amount": 30}]).get_json()
        assert d["splitting"]["you"] == 55.0

    def test_evenly_gives_the_extra_cent_to_you(self, client):
        i = add(client, tx("PAI", 85.0, "Dining"))
        d = split(client, i["PAI"], mode="even", people=[{"name": "Priya"}, {"name": "Sam"}]).get_json()
        assert d["splitting"]["you"] == 28.34
        assert [p["amount"] for p in d["splitting"]["people"]] == [28.33, 28.33]

    def test_percent_and_shares(self, client):
        i = add(client, tx("LOBLAWS", 84.12, "Groceries"))
        d = split(client, i["LOBLAWS"], mode="percent", you=50, people=[{"name": "Sam", "percent": 50}]).get_json()
        assert d["splitting"]["you"] == 42.06 and d["splitting"]["people"][0]["amount"] == 42.06
        d = split(client, i["LOBLAWS"], mode="shares", you=2, people=[{"name": "Sam", "shares": 1}]).get_json()
        assert d["splitting"]["people"][0]["amount"] == 28.04 and d["splitting"]["you"] == 56.08
        # Short of 100%: Sam's half is still half, and the rest is hers.
        d = split(client, i["LOBLAWS"], mode="percent", you=40, people=[{"name": "Sam", "percent": 50}]).get_json()
        assert d["splitting"]["people"][0]["amount"] == 42.06 and d["splitting"]["you"] == 42.06
        r = split(client, i["LOBLAWS"], mode="percent", you=60, people=[{"name": "Sam", "percent": 50}])
        assert r.get_json()["error"] == "That’s 10% too much."

    def test_all_for_them(self, client):
        i = add(client, tx("GIFT", 50.01, "Shopping"))
        d = split(client, i["GIFT"], mode="even", include_me=False,
                  people=[{"name": "Priya"}, {"name": "Sam"}]).get_json()
        assert d["splitting"]["you"] == 0
        assert sorted(p["amount"] for p in d["splitting"]["people"]) == [25.0, 25.01]


class TestPartialAndLetGo:
    def test_paid_part_then_let_the_rest_go(self, client):
        i = add(client, tx("SUSHI", 50.0, "Dining"), tx("E-TRANSFER FROM SAM", -10.0, when=day(1)))
        split(client, i["SUSHI"], mode="amount", people=[{"name": "Sam", "amount": 25}])
        client.post(f"/api/transactions/{i['SUSHI']}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        sam = detail(client, i["SUSHI"])["splitting"]["people"][0]
        assert (sam["paid"], sam["owes"]) == (10.0, 15.0)
        spent = month_totals(client)["spent"]
        r = client.post(f"/api/transactions/{i['SUSHI']}/split/let-go", json={"name": "Sam"})
        assert r.status_code == 200
        assert month_totals(client)["spent"] == spent + 15
        sam = detail(client, i["SUSHI"])["splitting"]["people"][0]
        assert sam["owes"] == 0 and sam["let_go"]["was"] == 25
        client.delete(f"/api/transactions/{i['SUSHI']}/split/let-go", json={"name": "Sam"})
        assert detail(client, i["SUSHI"])["splitting"]["people"][0]["owes"] == 15
        assert month_totals(client)["spent"] == spent


class TestParts:
    def setup_flight(self, client):
        i = add(client, tx("FLIGHT TO ATHENS", 856.0, "Travel", when=day(20)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        split(client, i["FLIGHT TO ATHENS"], mode="amount", people=[{"name": "Dad", "amount": 428}])
        return i

    def test_what_dad_owes_comes_first(self, client):
        i = self.setup_flight(client)
        r = client.get(f"/api/transactions/{i['E-TRANSFER FROM DAD']}/owing").get_json()
        assert r["from"] == "Dad"
        assert [(x["id"], x["owes"], x["theirs"]) for x in r["items"]] == [(i["FLIGHT TO ATHENS"], 428.0, True)]

    def test_dads_600_needs_the_rest_sorted(self, client):
        i = self.setup_flight(client)
        dep = i["E-TRANSFER FROM DAD"]
        payback = {"kind": "payback", "amount": 428, "charge": i["FLIGHT TO ATHENS"], "person": "Dad"}
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [payback]})
        assert r.status_code == 400 and r.get_json()["error"] == "$172.00 left to sort."
        income = month_totals(client)["income"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [payback], "later": True}).get_json()
        assert r["rest"] == 172
        dad = detail(client, i["FLIGHT TO ATHENS"])["splitting"]["people"][0]
        assert dad["owes"] == 0
        rest = next(q for q in client.get("/api/review").get_json()["money_in"] if q.get("rest"))
        assert rest["rest"] == {"whole": 600.0, "sorted": 428.0}
        assert month_totals(client)["income"] == income, "the $172 counts as nothing until sorted"
        # The $172 is a gift: safe to spend's income grows by it.
        rid = rest["txn"]["id"]
        r = client.post(f"/api/transactions/{rid}/parts", json={"parts": [{"kind": "gift", "amount": 172}]})
        assert r.status_code == 200, r.get_json()
        assert month_totals(client)["income"] == income + 172
        assert not any(q.get("rest") for q in client.get("/api/review").get_json()["money_in"])

    def test_the_172_in_two_parts_one_owed_back(self, client):
        i = self.setup_flight(client)
        dep = i["E-TRANSFER FROM DAD"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT TO ATHENS"], "person": "Dad"},
            {"kind": "gift", "amount": 100},
            {"kind": "overpaid", "amount": 72, "person": "Dad"}]})
        assert r.status_code == 200, r.get_json()
        owed = client.get("/api/owed").get_json()
        assert owed["you_owe"][0]["name"] == "Dad" and owed["you_owe"][0]["total"] == 72
        assert [p["kind"] for p in detail(client, dep)["parts"]] == ["payback", "gift", "overpaid"]

    def test_undo_makes_it_one_deposit_again(self, client):
        i = self.setup_flight(client)
        dep = i["E-TRANSFER FROM DAD"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT TO ATHENS"], "person": "Dad"},
            {"kind": "gift", "amount": 172}]}).get_json()
        assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
        assert "parts" not in detail(client, dep)
        assert detail(client, i["FLIGHT TO ATHENS"])["splitting"]["people"][0]["owes"] == 428

    def test_one_deposit_two_purchases_and_unlink(self, client):
        i = add(client, tx("FLIGHT", 856.0, "Travel", when=day(20)), tx("LOBLAWS", 128.0, "Groceries", when=day(10)),
                tx("E-TRANSFER FROM DAD", -492.0, when=day(2), merchant="Dad"))
        split(client, i["FLIGHT"], mode="amount", people=[{"name": "Dad", "amount": 428}])
        split(client, i["LOBLAWS"], mode="even", people=[{"name": "Dad"}])
        dep = i["E-TRANSFER FROM DAD"]
        income = month_totals(client)["income"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": 428, "charge": i["FLIGHT"], "person": "Dad"},
            {"kind": "payback", "amount": 64, "charge": i["LOBLAWS"], "person": "Dad"}]})
        assert r.status_code == 200, r.get_json()
        assert detail(client, i["FLIGHT"])["splitting"]["people"][0]["owes"] == 0
        assert detail(client, i["LOBLAWS"])["splitting"]["people"][0]["owes"] == 0
        assert month_totals(client)["income"] == income, "a payback is never income"
        part = detail(client, dep)["parts"][0]["id"]
        r = client.delete(f"/api/transactions/{part}/parts")
        assert r.status_code == 200 and r.get_json()["removed"] == 2
        assert detail(client, i["FLIGHT"])["splitting"]["people"][0]["owes"] == 428
        assert "parts" not in detail(client, dep)

    def test_one_purchase_two_deposits(self, client):
        i = add(client, tx("FLIGHT", 856.0, "Travel", when=day(20)),
                tx("E-TRANSFER FROM DAD", -200.0, when=day(5), merchant="Dad"),
                tx("E-TRANSFER FROM DAD 2", -400.0, when=day(2), merchant="Dad"))
        split(client, i["FLIGHT"], mode="amount", people=[{"name": "Dad", "amount": 428}])
        client.post(f"/api/transactions/{i['FLIGHT']}/paybacks/{i['E-TRANSFER FROM DAD']}", json={"person": "Dad"})
        client.post(f"/api/transactions/{i['E-TRANSFER FROM DAD 2']}/parts", json={"parts": [
            {"kind": "payback", "amount": 228, "charge": i["FLIGHT"], "person": "Dad"},
            {"kind": "gift", "amount": 172}]})
        dad = detail(client, i["FLIGHT"])["splitting"]["people"][0]
        assert (dad["paid"], dad["owes"]) == (428.0, 0.0)


class TestCashInHand:
    def test_cash_counts_once(self, client):
        i = add(client, tx("PHO HUNG", 90.0, "Dining", when=day(6)),
                tx("DEPOSIT AT BRANCH", -200.0, when=day(1), merchant="Deposit at branch"))
        split(client, i["PHO HUNG"], mode="even", people=[{"name": "Priya"}, {"name": "Sam"}])
        r = client.post(f"/api/transactions/{i['PHO HUNG']}/split/cash",
                        json={"name": "Priya", "amount": 30, "day": day(4)})
        assert r.status_code == 201
        priya = detail(client, i["PHO HUNG"])["splitting"]["people"][0]
        assert priya["owes"] == 0 and priya["cash"] == 30
        assert client.get("/api/owed").get_json()["total"] == 30, "only Sam still owes"
        dep = i["DEPOSIT AT BRANCH"]
        cash = client.get(f"/api/transactions/{dep}/cash-matches").get_json()["cash"]
        assert cash[0]["name"] == "Priya" and cash[0]["amount"] == 30
        income = month_totals(client)["income"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "cash", "amount": 30, "cash_ids": [cash[0]["id"]]},
            {"kind": "income", "amount": 170, "income_kind": "other"}]})
        assert r.status_code == 200, r.get_json()
        assert month_totals(client)["income"] == income + 170, "the $30 isn't counted again"
        assert client.get(f"/api/transactions/{dep}/cash-matches").get_json()["cash"] == []
        # Unlinking frees the cash again.
        client.delete(f"/api/transactions/{dep}/parts")
        assert len(client.get(f"/api/transactions/{dep}/cash-matches").get_json()["cash"]) == 1


class TestFindingPayments:
    def test_part_of_a_bigger_e_transfer_can_pay_it_back(self, client):
        """S-26: Dad's $200 and $228 of his $600 pay back his $428."""
        i = add(client, tx("FLIGHT", 856.0, "Travel", when=day(20)),
                tx("E-TRANSFER FROM DAD", -200.0, when=day(8), merchant="Dad"),
                tx("E-TRANSFER FROM DAD 2", -600.0, when=day(2), merchant="Dad"))
        split(client, i["FLIGHT"], mode="amount", people=[{"name": "Dad", "amount": 428}])
        found = client.get(f"/api/transactions/{i['FLIGHT']}/paybacks").get_json()["candidates"]
        by_id = {c["id"]: c for c in found}
        assert by_id[i["E-TRANSFER FROM DAD 2"]]["part"] == 428.0       # all that's left, of $600
        client.post(f"/api/transactions/{i['FLIGHT']}/paybacks/{i['E-TRANSFER FROM DAD']}", json={"person": "Dad"})
        r = client.post(f"/api/transactions/{i['FLIGHT']}/paybacks/{i['E-TRANSFER FROM DAD 2']}",
                        json={"person": "Dad", "amount": 228})
        assert r.status_code == 200, r.get_json()
        dad = detail(client, i["FLIGHT"])["splitting"]["people"][0]
        assert (dad["paid"], dad["owes"]) == (428.0, 0.0)

    def test_a_deposit_splits_and_links_a_purchase(self, client):
        """S-24: Costco wasn't split; Dad's half of it is part of his $600."""
        i = add(client, tx("COSTCO", 212.40, "Shopping", when=day(10)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(2), merchant="Dad"))
        dep = i["E-TRANSFER FROM DAD"]
        hit = next(c for c in client.get(f"/api/transactions/{dep}/charges", query_string={"q": "cost"})
                   .get_json()["charges"] if c["id"] == i["COSTCO"])
        assert hit["split"] is False
        split(client, i["COSTCO"], mode="even", people=[{"name": "Dad"}])
        owes = detail(client, i["COSTCO"])["splitting"]["people"][0]["owes"]
        assert owes == 106.20
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "payback", "amount": owes, "charge": i["COSTCO"], "person": "Dad"}], "later": True})
        assert r.status_code == 200, r.get_json()
        assert detail(client, i["COSTCO"])["splitting"]["people"][0]["owes"] == 0
