"""REFRESH-02 (THL-291, THL-289, THL-181): the split card's ••• menu (S-40)
and every screen after it, built as Pearl views. The server sends the
toasts (S-44) and Undo; the Unlink? sheet's new words (S-34sr, S-34kr);
and no stock iOS dialog is left in the split flow."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
ROOT = Path(__file__).resolve().parents[1]


def day(n):
    return f"{MONTH}-{10 + n:02d}"


def tx(desc, amount, category="", when=None, merchant=None):
    return Transaction(date=when or day(1), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "menus.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def people(c, tid):
    return {p["name"]: p for p in c.get(f"/api/transactions/{tid}").get_json()["splitting"]["people"]}


def adds_up(c, tid):
    for p in people(c, tid).values():
        assert round(min(p["paid"], p["amount"]) + p["owes"], 2) == p["amount"], p


def undo(c, reply):
    r = c.post("/api/transactions/undo", json=reply["undo"])
    assert r.status_code == 200, r.get_json()


def loblaws(c, *more):
    """Loblaws $150.00, five ways at $30.00 (REFRESH-02's example)."""
    i = add(c, tx("LOBLAWS", 150.0, "Groceries", when=day(1)), *more)
    r = c.put(f"/api/transactions/{i['LOBLAWS']}/split",
              json={"mode": "even", "people": [{"name": n} for n in ("Jo", "Sam", "Priya", "Alex")]})
    assert r.status_code == 200, r.get_json()
    return i


def without(c, tid, name):
    """S-40's Remove: the split as it is, without them, their share hers."""
    ps = people(c, tid)
    kept = [{"name": n, "amount": (p.get("let_go") or {}).get("was", p["amount"])}
            for n, p in ps.items() if n != name]
    total = 150.0
    return {"mode": "amount", "include_me": True, "people": kept,
            "you": round(total - sum(p["amount"] for p in kept), 2)}


class TestMarkPaidBack:
    """S-06rb → S-44b: the bank link answers with its toast and Undo."""

    def test_toast_and_undo(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM PRIYA", -30.0, when=day(3), merchant="Priya"))
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM PRIYA']}",
                        json={"person": "Priya"})
        reply = r.get_json()
        assert r.status_code == 200 and reply["toast"] == "Priya paid back $30.00"
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 0.0
        adds_up(client, i["LOBLAWS"])
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 30.0
        assert client.st.get_transaction(i["E-TRANSFER FROM PRIYA"]).repays is None
        adds_up(client, i["LOBLAWS"])

    def test_part_of_a_deposit_says_the_part(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM SAM", -50.0, when=day(3), merchant="Sam"))
        reply = client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM SAM']}",
                            json={"person": "Sam", "amount": 10}).get_json()
        assert reply["toast"] == "Sam paid back $10.00"
        assert people(client, i["LOBLAWS"])["Sam"]["owes"] == 20.0

    def test_cash_already_answers_with_undo(self, client):
        i = loblaws(client)
        reply = client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                            json={"name": "Priya", "amount": 30, "day": day(2)}).get_json()
        assert reply["undo"]
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 30.0


class TestRemoveFromS40:
    """S-44d: Remove saves at once (PUT …/split), with a toast and Undo,
    for someone who paid nothing too."""

    def test_paid_nothing(self, client):
        i = loblaws(client)
        r = client.put(f"/api/transactions/{i['LOBLAWS']}/split", json=without(client, i["LOBLAWS"], "Priya"))
        reply = r.get_json()
        assert r.status_code == 200, reply
        assert reply["toast"] == "Priya removed · $30.00 back to your share"
        assert "Priya" not in people(client, i["LOBLAWS"])
        assert reply["splitting"]["you"] == 60.0
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 30.0
        adds_up(client, i["LOBLAWS"])

    def test_someone_let_go_says_their_whole_share(self, client):
        i = loblaws(client)
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/let-go", json={"name": "Alex"})
        reply = client.put(f"/api/transactions/{i['LOBLAWS']}/split",
                           json=without(client, i["LOBLAWS"], "Alex")).get_json()
        assert reply["toast"] == "Alex removed · $30.00 back to your share"

    def test_someone_who_paid_unlinks_with_undo(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM JO", -30.0, when=day(3), merchant="Jo"))
        client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM JO']}", json={"person": "Jo"})
        reply = client.put(f"/api/transactions/{i['LOBLAWS']}/split",
                           json=without(client, i["LOBLAWS"], "Jo")).get_json()
        assert reply["toast"] == "Jo removed · $30.00 back to your share"
        assert client.st.get_transaction(i["E-TRANSFER FROM JO"]).repays is None
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Jo"]["paid"] == 30.0
        adds_up(client, i["LOBLAWS"])

    def test_change_share_has_no_removed_toast(self, client):
        i = loblaws(client)
        body = without(client, i["LOBLAWS"], "nobody")
        for p in body["people"]:
            if p["name"] == "Priya":
                p["amount"] = 20.0
        body["you"] = 40.0
        reply = client.put(f"/api/transactions/{i['LOBLAWS']}/split", json=body).get_json()
        assert "toast" not in reply and reply["undo"]
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 20.0
        undo(client, reply)
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 30.0


class TestLetGo:
    """S-08r → S-44c, and S-40d's Undo let it go → S-44e."""

    def test_let_go_and_back(self, client):
        i = loblaws(client)
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/let-go", json={"name": "Priya"}).get_json()
        assert r["toast"] == "Let go · the $30.00 is your spending now"
        back = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/let-go",
                             query_string={"name": "Priya"}).get_json()
        assert back["toast"] == "Priya owes you $30.00 again"
        assert people(client, i["LOBLAWS"])["Priya"]["owes"] == 30.0
        adds_up(client, i["LOBLAWS"])

    def test_the_rest_after_a_part(self, client):
        i = loblaws(client)
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 10, "day": day(2)})
        r = client.post(f"/api/transactions/{i['LOBLAWS']}/split/let-go", json={"name": "Sam"}).get_json()
        assert r["toast"] == "Let go · the $20.00 is your spending now"
        back = client.delete(f"/api/transactions/{i['LOBLAWS']}/split/let-go",
                             query_string={"name": "Sam"}).get_json()
        assert back["toast"] == "Sam owes you $20.00 again"
        adds_up(client, i["LOBLAWS"])


class TestUnlinkSheetWords:
    """S-34sr / S-34kr: title, payment card, buttons and footnote."""

    def link(self, c, tid, name):
        return people(c, tid)[name]["links"][0]["sheet"]

    def test_e_transfer_this_purchase_only(self, client):
        i = loblaws(client, tx("E-TRANSFER FROM SAM", -30.0, when=day(3), merchant="Sam"))
        client.post(f"/api/transactions/{i['LOBLAWS']}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        s = self.link(client, i["LOBLAWS"], "Sam")
        assert s["heading"] == "Unlink Sam’s e-Transfer?" and s["overline"] == "UNLINK"
        assert s["card"]["label"].startswith("e-Transfer from Sam · ") and s["card"]["amount"] == 30.0
        assert (s["confirm"], s["keep"], s["note"]) == ("Unlink $30.00", "Keep linked", None)

    def test_shared_e_transfer(self, client):
        i = loblaws(client, tx("PIZZA NOVA", 60.0, "Dining", when=day(2)),
                    tx("E-TRANSFER FROM JO", -60.0, when=day(5), merchant="Jo"))
        client.put(f"/api/transactions/{i['PIZZA NOVA']}/split", json={"mode": "even", "people": [{"name": "Jo"}]})
        client.st.link_payback(i["LOBLAWS"], i["E-TRANSFER FROM JO"], "Jo", 30.0)
        client.st.set_payback_more(i["E-TRANSFER FROM JO"], [(i["PIZZA NOVA"], 30.0)])
        s = self.link(client, i["LOBLAWS"], "Jo")
        assert s["heading"] == "This $60.00 also paid back PIZZA NOVA. Unlink only LOBLAWS’ $30.00?"
        assert s["card"]["amount"] == 60.0 and s["confirm"] == "Unlink $30.00"
        assert s["note"] == "To unlink the whole $60.00, open the e-Transfer and unlink it there."

    def test_cash_and_app(self, client):
        i = loblaws(client)
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash", json={"name": "Sam", "amount": 30, "day": day(2)})
        client.post(f"/api/transactions/{i['LOBLAWS']}/split/cash",
                    json={"name": "Priya", "amount": 30, "day": day(3), "via": "app", "app": "PayPal"})
        cash, app = self.link(client, i["LOBLAWS"], "Sam"), self.link(client, i["LOBLAWS"], "Priya")
        assert cash["heading"] == "Unlink Sam’s cash?" and cash["card"]["label"].startswith("Cash · ")
        assert app["heading"] == "Unlink Priya’s PayPal payment?" and app["card"]["label"].startswith("PayPal · ")

    def test_refund(self, client):
        i = add(client, tx("LOBLAWS", 120.0, "Groceries", when=day(1)),
                tx("LOBLAWS REFUND", -8.5, "Groceries", when=day(7), merchant="Loblaws"))
        client.post(f"/api/transactions/{i['LOBLAWS REFUND']}/mark", json={"case": "refund", "charge": i["LOBLAWS"]})
        s = client.get(f"/api/transactions/{i['LOBLAWS']}").get_json()["refunded_by"][0]["link"]["sheet"]
        assert (s["heading"], s["overline"], s["confirm"], s["keep"]) == (
            "Unlink refund?", "REFUND", "Unlink refund", "Keep it")
        assert s["card"]["label"].startswith("Loblaws refund · ")

    def test_made_the_split(self, client):
        i = add(client, tx("SUSHI", 90.0, "Dining", when=day(1)),
                tx("E-TRANSFER FROM PRIYA", -30.0, when=day(3), merchant="Priya"))
        client.post(f"/api/transactions/{i['E-TRANSFER FROM PRIYA']}/mark",
                    json={"case": "payback", "charge": i["SUSHI"], "person": "Priya"})
        s = self.link(client, i["SUSHI"], "Priya")
        assert s["heading"] == "Unlink Priya’s e-Transfer?" and s["confirm"] == "Unlink and take Priya off"


class TestSwiftWiring:
    """By source (no simulator run): no stock iOS dialog in the split flow,
    and every REFRESH-02 screen wired."""

    def src(self, path):
        return (ROOT / path).read_text()

    SPLIT_FILES = ["ios/Pearl/Views/Transactions/SplitFlow.swift",
                   "ios/Pearl/Views/Transactions/PaybackOptions.swift",
                   "ios/Pearl/Views/Transactions/SplitMenus.swift"]

    def test_no_stock_dialogs_in_the_split_flow(self):
        for path in self.SPLIT_FILES:
            s = self.src(path)
            for stock in (".confirmationDialog(", ".alert(", ".actionSheet(", "ActionSheet("):
                assert stock not in s, (path, stock)

    def test_detail_page_split_dialogs_are_gone(self):
        s = self.src("ios/Pearl/Views/Transactions/TransactionDetailView.swift")
        # Only the Delete dialog stays (not a split flow; a later pass).
        assert len(re.findall(r"\.confirmationDialog\(", s)) == 1
        assert ".confirmationDialog(\"Delete" in s and ".alert(" not in s

    def test_s40_from_the_card(self):
        split = self.src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        menus = self.src("ios/Pearl/Views/Transactions/SplitMenus.swift")
        assert "PersonOptionsSheet(" in split and "Options for \\(p.name)" in split
        assert "Shows options." in split
        for words in ("Mark paid back", "Mark the rest paid back", "Let the rest go", "Undo let it go",
                      "Change the split", "Paid so far", "Paid with", "Opens How to split"):
            assert words in menus, words

    def test_each_screen_exists(self):
        menus = self.src("ios/Pearl/Views/Transactions/SplitMenus.swift")
        flow = self.src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        opts = self.src("ios/Pearl/Views/Transactions/PaybackOptions.swift")
        for name in ("struct PersonOptionsSheet", "struct RemindSheet", "struct RemovePersonSheet",
                     "struct PearlToast", "struct CautionBanner", "struct PearlOptionRow"):
            assert name in menus, name
        assert "struct LetGoSheet" in flow and "interactiveDismissDisabled(busy)" in flow
        assert "Couldn’t let that go. Nothing changed. Try again." in flow
        assert "How did \\(person.name) pay?" in flow and "Which payment was it?" in flow
        assert "struct PaybackOptionsSheet" in opts and "Opens it here in Pearl" in opts
        assert "link.sheet.heading" in opts and "dismissDisabled: busy" in opts

    def test_remind_copy(self):
        menus = self.src("ios/Pearl/Views/Transactions/SplitMenus.swift")
        assert "Thanks for the \\(Format.amount(p.paid)). Your share of" in menus
        assert "so \\(Format.amount(p.owes)) to go." in menus
        assert "UIPasteboard.general.string" in menus

    def test_let_go_copy_says_allowance(self):
        flow = self.src("ios/Pearl/Views/Transactions/SplitFlow.swift")
        assert "already counts in full until it’s paid back, so your Allowance doesn’t change." in flow
        for path in self.SPLIT_FILES:
            assert "safe to spend" not in self.src(path).lower()

    def test_undo_failed_toast(self):
        detail = self.src("ios/Pearl/Views/Transactions/TransactionDetailView.swift")
        assert "Couldn’t undo that. Nothing changed." in detail and "Try again" in detail

    def test_view_stays_in_the_app(self):
        for path in self.SPLIT_FILES + ["ios/Pearl/Views/Transactions/TransactionDetailView.swift"]:
            s = self.src(path)
            assert "openURL" not in s and "UIApplication.shared.open" not in s, path
