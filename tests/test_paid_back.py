"""Paid back (product owner, 2026-11-15; Figma Proposals › "Paid back"
1351:8769, THL-289, THL-291, THL-181): one "Paid back" tile, then who paid
her back. For a person, how much of their share this was is her choice:
"Part of it" (PB-13, the amount she says) or "All of it"; when the money is
less than they owe, "All of it" asks "Let the other $45.00 go?" (PB-13b).

The app saves either through POST /api/transactions/<id>/parts: a payback
part for the amount she chose, and `let_go` on it for Let it go. One Undo
takes it all back."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")


def day(n):
    return f"{MONTH}-{28 - n:02d}"


def tx(desc, amount, category="", when=None, merchant=None):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id="chq", account_name="TD Chequing",
                       raw={"account_type": "depository"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "paid_back.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    ingest(c.st, IngestResult(list(rows), "chq"))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def detail(c, tid):
    return c.get(f"/api/transactions/{tid}").get_json()


def person(c, charge, name):
    return next(p for p in detail(c, charge)["splitting"]["people"] if p["name"] == name)


def owing(c, charge):
    return {p["name"]: (p["paid"], p["owes"]) for p in detail(c, charge)["splitting"]["people"]}


def parts(c, deposit, *given, later=False):
    return c.post(f"/api/transactions/{deposit}/parts", json={"parts": list(given), "later": later})


def undo(c, reply):
    r = c.post("/api/transactions/undo", json=reply["undo"])
    assert r.status_code == 200, r.get_json()


class TestPartOfIt:
    """PB-13 "Part of it · $15.00": the deposit's amount, or what she types."""

    def setup(self, client, sent=15.0):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -sent, when=day(1), merchant="Sam Lee"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        return i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]

    def test_part_of_it_counts_what_came_in_and_sam_still_owes_the_rest(self, client):
        pai, dep = self.setup(client)
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Sam"})
        assert r.status_code == 200, r.get_json()
        # PB-14's toast.
        assert r.get_json()["title"] == "Sam paid back $15.00"
        assert owing(client, pai) == {"Sam": (15.0, 45.0)}
        assert person(client, pai, "Sam")["let_go"] is None
        undo(client, r.get_json())
        assert owing(client, pai) == {"Sam": (0.0, 60.0)}
        assert not detail(client, dep).get("parts")

    def test_a_smaller_amount_leaves_the_rest_to_sort(self, client):
        """She changed $15.00 to $10.00: Sam paid $10.00; the other $5.00 is
        sorted next (S-11 v2) or later, never put on Sam by Pearl."""
        pai, dep = self.setup(client)
        r = parts(client, dep, {"kind": "payback", "amount": 10.0, "charge": pai, "person": "Sam"}, later=True)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Sorted 1 part. $5.00 left to sort."
        assert owing(client, pai) == {"Sam": (10.0, 50.0)}

    def test_part_of_it_and_a_gift_keep_the_parts_title(self, client):
        pai, dep = self.setup(client, sent=20.0)
        r = parts(client, dep, {"kind": "payback", "amount": 10.0, "charge": pai, "person": "Sam"},
                  {"kind": "gift", "amount": 10.0})
        assert r.status_code == 200, r.get_json()
        # Two kinds of money: the parts' own title.
        assert r.get_json()["title"] == "Sorted into 2 parts."
        assert owing(client, pai) == {"Sam": (10.0, 50.0)}


class TestAllOfIt:
    """PB-13 "All of it · $60.00"; PB-13b when the money is less."""

    def setup(self, client, sent=15.0):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -sent, when=day(1), merchant="Sam Lee"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        return i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]

    def test_let_it_go_marks_sam_paid_in_full_and_the_rest_stays_hers(self, client):
        pai, dep = self.setup(client)
        share = detail(client, pai)["splitting"]["you"]
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Sam",
                                "let_go": True})
        assert r.status_code == 200, r.get_json()
        # PB-13b's toast.
        assert r.get_json()["title"] == "Sam paid in full · $45.00 let go"
        sam = person(client, pai, "Sam")
        assert (sam["paid"], sam["owes"]) == (15.0, 0.0)
        assert sam["let_go"]["was"] == 60.0
        # "…and the other $45.00 stays yours."
        assert detail(client, pai)["splitting"]["you"] == round(share + 45.0, 2)

    def test_one_undo_puts_back_the_payback_and_what_sam_owes(self, client):
        pai, dep = self.setup(client)
        share = detail(client, pai)["splitting"]["you"]
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Sam",
                                "let_go": True})
        undo(client, r.get_json())
        sam = person(client, pai, "Sam")
        assert (sam["amount"], sam["paid"], sam["owes"], sam["let_go"]) == (60.0, 0.0, 60.0, None)
        assert detail(client, pai)["splitting"]["you"] == share
        assert not detail(client, dep).get("parts")

    def test_sam_still_owes_it_is_part_of_it(self, client):
        """PB-13b's "Sam still owes it": recorded as Part of it (PB-14)."""
        pai, dep = self.setup(client)
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Sam"})
        assert r.get_json()["title"] == "Sam paid back $15.00"
        assert owing(client, pai) == {"Sam": (15.0, 45.0)}

    def test_all_of_it_when_it_covers_the_share_lets_nothing_go(self, client):
        pai, dep = self.setup(client, sent=60.0)
        r = parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam",
                                "let_go": True})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Sam paid back $60.00"
        sam = person(client, pai, "Sam")
        assert (sam["paid"], sam["owes"], sam["let_go"]) == (60.0, 0.0, None)

    def test_more_than_owed_is_all_of_it_then_the_extra(self, client):
        """$75.00 for a $60.00 share: All of it, then what the extra is (S-11 v2)."""
        pai, dep = self.setup(client, sent=75.0)
        r = parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"},
                  {"kind": "overpaid", "amount": 15.0, "person": "Sam"})
        assert r.status_code == 200, r.get_json()
        assert owing(client, pai) == {"Sam": (60.0, 0.0)}


class TestSeveralPeople:
    """S-35's ticks, then PB-13 for each person (S-35 now leads into PB-13)."""

    def test_each_person_part_or_all_and_one_undo(self, client):
        i = add(client, tx("PIZZA NOVA", 90.0, "Dining", when=day(10)),
                tx("INTERAC E-TRANSFER", -50.0, when=day(1)))
        pizza, dep = i["PIZZA NOVA"], i["INTERAC E-TRANSFER"]
        client.put(f"/api/transactions/{pizza}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 30}, {"name": "Priya", "amount": 30}]})
        r = parts(client, dep, {"kind": "payback", "amount": 30.0, "charge": pizza, "person": "Sam"},
                  {"kind": "payback", "amount": 20.0, "charge": pizza, "person": "Priya", "let_go": True})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Sorted into 2 parts."
        assert owing(client, pizza) == {"Sam": (30.0, 0.0), "Priya": (20.0, 0.0)}
        assert person(client, pizza, "Priya")["let_go"]["was"] == 30.0
        undo(client, r.get_json())
        assert owing(client, pizza) == {"Sam": (0.0, 30.0), "Priya": (0.0, 30.0)}
        assert person(client, pizza, "Priya")["let_go"] is None


class TestLetGoIsChecked:
    def setup(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -15.0, when=day(1), merchant="Sam Lee"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        return i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]

    def test_only_a_payback_by_someone_on_the_split(self, client):
        pai, dep = self.setup(client)
        r = parts(client, dep, {"kind": "gift", "amount": 15.0, "let_go": True})
        assert r.status_code == 400 and r.get_json()["error"] == "Only a payback can let the rest go."
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Jordan",
                                "let_go": True})
        assert r.status_code == 400 and r.get_json()["error"] == "Pick someone on this split."
        # Nothing was saved.
        assert owing(client, pai) == {"Sam": (0.0, 60.0)}
        assert not detail(client, dep).get("parts")

    def test_a_purchase_that_isnt_split(self, client):
        i = add(client, tx("AIRBNB MONTREAL", 300.0, "Lodging", when=day(12)))
        _, dep = self.setup(client)
        r = parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": i["AIRBNB MONTREAL"],
                                "person": "Sam", "let_go": True})
        assert r.status_code == 400 and r.get_json()["error"] == "Pick someone on this split."


class TestNoSplit:
    """PB-15: Sam isn't on a split; the purchase she picks counts the whole
    amount as paid back by Sam (the existing T-09 mark)."""

    def test_the_whole_amount_counts_for_the_purchase(self, client):
        i = add(client, tx("AIRBNB MONTREAL", 300.0, "Lodging", when=day(12)),
                tx("E-TRANSFER FROM SAM LEE", -15.0, when=day(1), merchant="Sam Lee"))
        air, dep = i["AIRBNB MONTREAL"], i["E-TRANSFER FROM SAM LEE"]
        assert client.get(f"/api/transactions/{dep}/owing").get_json()["from"] is None
        r = client.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": air,
                                                               "person": "Sam Lee"})
        assert r.status_code == 200, r.get_json()
        sam = person(client, air, "Sam Lee")
        assert sam["paid"] == 15.0


class TestTilesBySource:
    """PB-10: one "Paid back" tile replaces three; six not-income tiles,
    the four income tiles as they were. By source (no simulator)."""

    def src(self, path):
        from pathlib import Path
        return (Path(__file__).resolve().parents[1] / path).read_text(encoding="utf-8")

    def test_one_paid_back_tile(self):
        s = self.src("ios/Pearl/Views/Transactions/CategorySheet.swift")
        start = s.index("static let notIncome: [CaseTile] = [")
        tiles = s[start:s.index("]", start + len("static let notIncome: [CaseTile] = ["))]
        assert tiles.count("CaseTile(") == 6
        assert 'label: "Paid back"' in tiles
        for gone in ("Paying me back", "Money back", "Work paying me back"):
            assert gone not in tiles, gone
        income = s[s.index("static let income: [CaseTile] = ["):]
        assert income[:income.index("]")].count("CaseTile(") == 4

    def test_who_paid_you_back_and_how_much(self):
        s = self.src("ios/Pearl/Views/Transactions/PaidBackViews.swift")
        for words in ('"Who paid you back?"', '"A person"', '"The shop"', '"Work"',
                      '"A refund · which purchase, all of it or your share"',
                      '"Let it go"', '"Let the other \\(Format.amount(rest)) go?"'):
            assert words in s, words
        parts = self.src("ios/Pearl/Views/Transactions/PartsFlow.swift")
        assert "How much of \\(possessive(firstName(o.person ?? who))) \\(Format.amount(o.owes))?" in parts
        # S-35 no longer takes min(share, what's left) on its own.
        assert "picked[o.id] = Double(min(cents(o.owes), room)) / 100" not in parts
        for path in ("ios/Pearl/Views/Transactions/PaidBackViews.swift",
                     "ios/Pearl/Views/Transactions/PartsFlow.swift",
                     "ios/Pearl/Views/Review/AnswerSheet.swift"):
            code = self.src(path)
            for stock in (".confirmationDialog(", ".alert(", ".actionSheet("):
                assert stock not in code, (path, stock)
            assert "safe to spend" not in code.lower()
