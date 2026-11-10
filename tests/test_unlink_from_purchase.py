"""SPLIT-25 (THL-291 "Unlinking any part from either side restores both
sides"): unlink a payback from the purchase it paid back, for every kind of
payback (S-34k), each with Undo, and Paid back + Owes = share after each
(THL-181)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def day(n):
    return f"{MONTH}-{10 + n:02d}"


def tx(desc, amount, category="", when=None, merchant=None):
    return Transaction(date=when or day(1), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "unlink.db"))
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


def adds_up(c, tid):
    """THL-181: on the split card, Paid back + Owes = share for everyone."""
    for p in people(c, tid).values():
        assert round(min(p["paid"], p["amount"]) + p["owes"], 2) == p["amount"], p


def link_of(c, tid, name, kind=None):
    links = people(c, tid)[name]["links"]
    return next(x for x in links if kind is None or x["kind"] == kind)


def undo(c, reply):
    r = c.post("/api/transactions/undo", json=reply["undo"])
    assert r.status_code == 200, r.get_json()


def loblaws(c, *more):
    i = add(c, tx("LOBLAWS", 120.0, "Groceries", when=day(1)), *more)
    c.put(f"/api/transactions/{i['LOBLAWS']}/split",
          json={"mode": "even", "people": [{"name": "Jo"}, {"name": "Sam"}, {"name": "Priya"}]})
    return i


def unlink(c, charge, inflow, **q):
    r = c.delete(f"/api/transactions/{charge}/paybacks/{inflow}", query_string=q)
    assert r.status_code == 200, r.get_json()
    return r.get_json()


class TestBankPayback:
    """S-34k: an e-Transfer for this purchase only."""

    def test_unlink_from_the_purchase_and_undo(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM SAM", -30.0, when=day(3), merchant="Sam"))
        client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        link = link_of(client, i["LOBLAWS"], "Sam")
        assert link["kind"] == "bank" and link["inflow"] == i["E-TRANSFER FROM SAM"]
        assert link["sheet"]["line"] == "Sam will owe you $30.00 again. The e-Transfer goes back to Needs a look."
        assert link["view"]["label"] == "View the e-Transfer" and link["sheet"]["button"] == "Unlink"
        reply = unlink(client, i["LOBLAWS"], i["E-TRANSFER FROM SAM"])
        assert reply["title"] == "Unlinked · Sam owes $30.00"
        assert people(client, i["LOBLAWS"])["Sam"]["owes"] == 30.0
        assert client.st.get_transaction(i["E-TRANSFER FROM SAM"]).repays is None
        adds_up(client, i["LOBLAWS"])
        undo(client, reply)
        sam = people(client, i["LOBLAWS"])["Sam"]
        assert (sam["paid"], sam["owes"]) == (30.0, 0.0)
        adds_up(client, i["LOBLAWS"])

    def test_the_deposit_side_unlink_still_works(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM SAM", -30.0, when=day(3), merchant="Sam"))
        client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        unlink(client, i["LOBLAWS"], i["E-TRANSFER FROM SAM"], whole=1)
        assert client.st.get_transaction(i["E-TRANSFER FROM SAM"]).repays is None

    def test_a_payback_not_on_this_purchase_is_refused(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM SAM", -30.0, when=day(3), merchant="Sam"))
        r = client.delete(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM SAM']}")
        assert r.status_code == 404


class TestSharedBankPayback:
    """S-34s: Jo's $60.00 e-Transfer paid back Loblaws and Pizza Nova."""

    def setup(self, c):
        i = loblaws(c, tx("PIZZA NOVA", 60.0, "Dining", when=day(2)),
                    tx("E-TRANSFER FROM JO", -60.0, when=day(5), merchant="Jo"))
        c.put(f"/api/transactions/{i['PIZZA NOVA']}/split", json={"mode": "even", "people": [{"name": "Jo"}]})
        c.st.link_payback(i["LOBLAWS"], i["E-TRANSFER FROM JO"], "Jo", 30.0)
        c.st.set_payback_more(i["E-TRANSFER FROM JO"], [(i["PIZZA NOVA"], 30.0)])
        return i

    def test_the_sheet_asks_about_only_this_purchase(self, client):
        i = self.setup(client)
        link = link_of(client, i["LOBLAWS"], "Jo")
        assert link["sheet"]["ask"] == "This $60.00 also paid back PIZZA NOVA. Unlink only LOBLAWS’ $30.00?"
        assert link["sheet"]["line"] == ("Jo will owe you $30.00 again on LOBLAWS. PIZZA NOVA stays paid back, "
                                         "and this $30.00 goes back to Needs a look as left to sort.")
        assert link["sheet"]["button"] == "Unlink $30.00" and link["goes"] == "left_to_sort"
        assert link["message"].startswith("Part of a $60.00 e-Transfer on ")
        # The second purchase lists it too (it was missing before SPLIT-25).
        repaid = detail(client, i["PIZZA NOVA"])["repaid_by"]
        assert [(r["id"], r["paid"]) for r in repaid] == [(i["E-TRANSFER FROM JO"], 30.0)]

    def test_only_this_purchase_comes_off_and_undo(self, client):
        i = self.setup(client)
        reply = unlink(client, i["LOBLAWS"], i["E-TRANSFER FROM JO"])
        assert reply["title"] == "Unlinked · Jo owes $30.00"
        assert people(client, i["LOBLAWS"])["Jo"]["owes"] == 30.0
        assert people(client, i["PIZZA NOVA"])["Jo"]["owes"] == 0.0
        rest = [q for q in client.get("/api/review").get_json()["money_in"] if q.get("rest")]
        assert len(rest) == 1 and rest[0]["txn"]["amount"] == -30.0
        adds_up(client, i["LOBLAWS"]), adds_up(client, i["PIZZA NOVA"])
        undo(client, reply)
        t = client.st.get_transaction(i["E-TRANSFER FROM JO"])
        assert t.repays == i["LOBLAWS"] and t.also_repays == {i["PIZZA NOVA"]: 30.0}
        assert people(client, i["LOBLAWS"])["Jo"]["owes"] == 0.0
        assert not any(q.get("rest") for q in client.get("/api/review").get_json()["money_in"])
        adds_up(client, i["LOBLAWS"])

    def test_from_the_second_purchase_too(self, client):
        i = self.setup(client)
        reply = unlink(client, i["PIZZA NOVA"], i["E-TRANSFER FROM JO"])
        assert people(client, i["PIZZA NOVA"])["Jo"]["owes"] == 30.0
        assert people(client, i["LOBLAWS"])["Jo"]["owes"] == 0.0
        adds_up(client, i["PIZZA NOVA"])
        undo(client, reply)
        assert people(client, i["PIZZA NOVA"])["Jo"]["owes"] == 0.0


class TestCash:
    def test_cash_is_forgotten_and_undo(self, client):
        i = loblaws(client)
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 30, "day": day(2)})
        link = link_of(client, i["LOBLAWS"], "Sam")
        assert link["kind"] == "cash" and link["view"] is None
        assert link["sheet"]["line"] == ("Sam will owe you $30.00 again. The cash you marked is forgotten, "
                                         "so nothing goes to Needs a look.")
        r = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/cash/{link['cash_id']}")
        assert r.status_code == 200, r.get_json()
        reply = r.get_json()
        assert reply["title"] == "Unlinked · Sam owes $30.00" and client.st.split_cash() == []
        adds_up(client, i["LOBLAWS"])
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Sam"]["paid"] == 30.0
        adds_up(client, i["LOBLAWS"])

    def test_cash_that_also_paid_another_purchase(self, client):
        """SPLIT-19: only this purchase's piece goes."""
        i = loblaws(client, tx("PIZZA NOVA", 60.0, "Dining", when=day(2)))
        client.put(f"/api/transactions/{i['PIZZA NOVA']}/split", json={"mode": "even", "people": [{"name": "Sam"}]})
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                        json={"name": "Sam", "amount": 60, "day": day(2),
                              "extra": [{"kind": "payback", "charge": i["PIZZA NOVA"], "person": "Sam", "amount": 30}]})
        assert r.status_code == 201, r.get_json()
        link = link_of(client, i["LOBLAWS"], "Sam")
        assert link["sheet"]["ask"] == "This $60.00 cash also paid back PIZZA NOVA. Unlink only LOBLAWS’ $30.00?"
        r = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/cash/{link['cash_id']}")
        reply = r.get_json()
        assert people(client, i["LOBLAWS"])["Sam"]["owes"] == 30.0
        assert people(client, i["PIZZA NOVA"])["Sam"]["paid"] == 30.0
        adds_up(client, i["LOBLAWS"]), adds_up(client, i["PIZZA NOVA"])
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Sam"]["paid"] == 30.0
        assert people(client, i["PIZZA NOVA"])["Sam"]["paid"] == 30.0

    def test_cash_a_deposit_holds(self, client):
        i = loblaws(client, tx("DEPOSIT", -200.0, when=day(8), merchant="Deposit at branch"))
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 30, "day": day(2)})
        cid = client.get(f"/api/transactions/{i['DEPOSIT']}/cash-matches").get_json()["cash"][0]["id"]
        r = client.post(f"/api/transactions/{i['DEPOSIT']}/parts",
                        json={"parts": [{"kind": "cash", "amount": 30, "cash_ids": [cid]},
                                        {"kind": "gift", "amount": 170}]})
        assert r.status_code == 200, r.get_json()
        link = link_of(client, i["LOBLAWS"], "Sam")
        assert link["deposit"]["id"] == i["DEPOSIT"] and link["view"]["label"] == "View the deposit"
        assert "Your $200.00 deposit on" in link["sheet"]["line"]
        assert link["sheet"]["line"].endswith("keeps its other parts, and this $30.00 goes back to Needs a look "
                                              "as left to sort.")
        r = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/cash/{link['cash_id']}")
        assert r.status_code == 200, r.get_json()
        reply = r.get_json()
        assert people(client, i["LOBLAWS"])["Sam"]["owes"] == 30.0
        parts = detail(client, i["DEPOSIT"])["parts"]
        assert sorted((p["kind"], p["amount"]) for p in parts) == [("gift", 170.0), ("rest", 30.0)]
        adds_up(client, i["LOBLAWS"])
        undo(client, reply)
        parts = detail(client, i["DEPOSIT"])["parts"]
        assert sorted((p["kind"], p["amount"]) for p in parts) == [("cash", 30.0), ("gift", 170.0)]
        assert people(client, i["LOBLAWS"])["Sam"]["paid"] == 30.0
        assert [c["deposit_id"] is not None for c in client.st.split_cash()] == [True]
        adds_up(client, i["LOBLAWS"])

    def test_another_app(self, client):
        i = loblaws(client)
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                    json={"name": "Priya", "amount": 30, "day": day(2), "via": "app", "app": "PayPal"})
        link = link_of(client, i["LOBLAWS"], "Priya")
        assert link["kind"] == "app" and link["sheet"]["name"] == "PayPal from Priya"
        assert link["sheet"]["line"] == ("Priya will owe you $30.00 again. The PayPal payment is forgotten, "
                                         "so nothing goes to Needs a look.")
        reply = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/cash/{link['cash_id']}").get_json()
        assert reply["title"] == "Unlinked · Priya owes $30.00"
        adds_up(client, i["LOBLAWS"])
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Priya"]["paid"] == 30.0


class TestPartOfADeposit:
    """S-26: Dad's $228.00 of a $600.00 deposit."""

    def test_only_the_part_goes_and_undo(self, client):
        i = add(client, tx("AIR CANADA", 456.0, "Travel", when=day(1)),
                tx("E-TRANSFER FROM DAD", -600.0, when=day(4), merchant="Dad"))
        client.put(f"/api/transactions/{i['AIR CANADA']}/split", json={"mode": "even", "people": [{"name": "Dad"}]})
        r = client.post(f"/api/transactions/{i['E-TRANSFER FROM DAD']}/parts",
                        json={"parts": [{"kind": "payback", "amount": 228, "charge": i["AIR CANADA"], "person": "Dad"},
                                        {"kind": "gift", "amount": 372}]})
        assert r.status_code == 200, r.get_json()
        link = link_of(client, i["AIR CANADA"], "Dad")
        assert link["kind"] == "part" and link["deposit"]["amount"] == 600.0
        assert link["sheet"]["line"] == ("Dad will owe you $228.00 again. Your $600.00 deposit keeps its other "
                                         "parts, and this $228.00 goes back to Needs a look as left to sort.")
        reply = unlink(client, i["AIR CANADA"], link["inflow"])
        assert reply["title"] == "Unlinked · Dad owes $228.00"
        parts = detail(client, i["E-TRANSFER FROM DAD"])["parts"]
        assert sorted((p["kind"], p["amount"]) for p in parts) == [("gift", 372.0), ("rest", 228.0)]
        adds_up(client, i["AIR CANADA"])
        undo(client, reply)
        parts = detail(client, i["E-TRANSFER FROM DAD"])["parts"]
        assert sorted((p["kind"], p["amount"]) for p in parts) == [("gift", 372.0), ("payback", 228.0)]
        assert people(client, i["AIR CANADA"])["Dad"]["owes"] == 0.0
        adds_up(client, i["AIR CANADA"])


class TestWorkPayingMeBack:
    def test_it_waits_again_and_undo(self, client):
        from finance.marks import WORK_REASON
        i = add(client, tx("HOTEL", 84.12, "Lodging", when=day(1)),
                tx("ACME EXPENSE", -84.12, when=day(6), merchant="Acme Corp"))
        client.st.exclude(i["HOTEL"], WORK_REASON)
        r = client.post(f"/api/transactions/{i['ACME EXPENSE']}/mark",
                        json={"case": "reimbursement", "charge": i["HOTEL"]})
        assert r.status_code == 200, r.get_json()
        row = detail(client, i["HOTEL"])["repaid_by"][0]
        assert row["link"]["kind"] == "reimbursement" and row["link"]["was_waiting"] is True
        assert row["link"]["sheet"]["line"] == ("HOTEL goes back to waiting to be reimbursed. "
                                                "The $84.12 from Acme Corp goes back to Needs a look.")
        reply = unlink(client, i["HOTEL"], i["ACME EXPENSE"])
        assert reply["title"] == "Unlinked · HOTEL is waiting to be reimbursed"
        assert client.st.get_transaction(i["HOTEL"]).excluded == WORK_REASON
        undo(client, reply)
        hotel = client.st.get_transaction(i["HOTEL"])
        assert not hotel.excluded and client.st.get_transaction(i["ACME EXPENSE"]).repays == i["HOTEL"]
        # Unlinked again after Undo, it still waits.
        unlink(client, i["HOTEL"], i["ACME EXPENSE"])
        assert client.st.get_transaction(i["HOTEL"]).excluded == WORK_REASON


class TestRefund:
    def test_from_the_purchase_and_undo(self, client):
        i = add(client, tx("LOBLAWS", 120.0, "Groceries", when=day(1)),
                tx("LOBLAWS REFUND", -8.5, "Groceries", when=day(7), merchant="Loblaws"))
        client.post(f"/api/transactions/{i['LOBLAWS REFUND']}/mark", json={"case": "refund", "charge": i["LOBLAWS"]})
        row = detail(client, i["LOBLAWS"])["refunded_by"][0]
        assert row["link"]["sheet"]["title"] == "Unlink refund?"
        assert row["link"]["sheet"]["line"] == ("The $8.50 stops coming off LOBLAWS. It stays in Groceries and "
                                                "goes back to Needs a look.")
        r = client.delete(f"/api/transactions/{i['LOBLAWS REFUND']}/refund")
        reply = r.get_json()
        assert reply["title"] == "Refund unlinked" and client.st.refunds() == {}
        undo(client, reply)
        assert client.st.refunds() == {i["LOBLAWS REFUND"]: i["LOBLAWS"]}


class TestMadeTheSplit:
    """THL-260: the person comes off this split only."""

    def test_comes_off_this_split_and_undo(self, client):
        i = add(client, tx("SUSHI", 90.0, "Dining", when=day(1)),
                tx("E-TRANSFER FROM PRIYA", -30.0, when=day(3), merchant="Priya"))
        client.post(f"/api/transactions/{i['E-TRANSFER FROM PRIYA']}/mark",
                    json={"case": "payback", "charge": i["SUSHI"], "person": "Priya"})
        link = link_of(client, i["SUSHI"], "Priya")
        assert link["made_split"] is True
        assert link["sheet"]["line"] == ("Priya joined this split when you linked this e-Transfer, so Priya comes "
                                         "off the split too. The e-Transfer goes back to Needs a look.")
        reply = unlink(client, i["SUSHI"], i["E-TRANSFER FROM PRIYA"])
        assert reply["title"] == "Unlinked · Priya taken off the split"
        assert client.st.splits() == {}
        undo(client, reply)
        assert people(client, i["SUSHI"])["Priya"]["owes"] == 0.0
        adds_up(client, i["SUSHI"])


class TestSwiftWiring:
    """S-05v → S-05o → S-34s/S-34k → S-05t, by source (no simulator run)."""

    def src(self, path):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / path).read_text()

    def test_every_paid_back_row_opens_the_options(self):
        s = self.src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        assert ".disabled(p.owes < 0.005 && p.letGo == nil)" not in s
        # REFRESH-02: every row and its ••• open S-40, whose hint is "Shows options."
        assert "Shows options." in s and "PersonOptionsSheet(" in s

    def test_the_sheet_and_toast(self):
        s = self.src("ios/Pearl/Views/Transactions/TransactionDetailView.swift")
        assert "UnlinkLinkSheet" in s and "Paid back with" not in s
        assert "[\"whole\": \"1\"]" in s and "\"Linked again\"" in s

    def test_no_stock_dialog_for_the_options(self):
        """Product owner, 2026-11-09: S-05o and S-34s aren't stock iOS
        dialogs. REFRESH-02 drew them (S-05or, S-34sr/kr); the split card's
        people open S-40 instead (tests/test_split_menus.py)."""
        opts = self.src("ios/Pearl/Views/Transactions/PaybackOptions.swift")
        assert "struct PaybackOptionsSheet" in opts and "struct UnlinkLinkSheet" in opts
        assert ".confirmationDialog" not in opts and ".alert" not in opts
        detail = self.src("ios/Pearl/Views/Transactions/TransactionDetailView.swift")
        split = self.src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        assert "PaybackOptionsSheet(" in detail and "PersonOptionsSheet(" in split
        assert "confirmationDialog(linkOptions" not in detail and "Unlink…\", role: .destructive" not in split
