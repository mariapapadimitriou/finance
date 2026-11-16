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

    def test_pb12_lists_sams_split_and_how_many_ways(self, client):
        """PB-12: "Sam’s share of Pai Northern Thai · owes $60.00" over
        "Wed, Nov 12 · split 2 ways"."""
        pai, dep = self.setup(client)
        r = client.get(f"/api/transactions/{dep}/owing").get_json()
        assert r["from"] == "Sam"
        assert [(x["id"], x["owes"], x["theirs"], x["ways"]) for x in r["items"]] == [(pai, 60.0, True, 2)]

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
        tiles = s[start:s.index("\n    ]", start)]
        assert tiles.count("CaseTile(") == 6
        assert 'label: "Paid back"' in tiles
        for gone in ("Paying me back", "Money back", "Work paying me back"):
            assert gone not in tiles, gone
        income = s[s.index("static let income: [CaseTile] = ["):]
        assert income[:income.index("\n    ]")].count("CaseTile(") == 4

    def test_who_paid_you_back_and_how_much(self):
        s = self.src("ios/Pearl/Views/Transactions/PaidBackViews.swift")
        for words in ('"Who paid you back?"', '"A person"', '"The shop"', '"Work"',
                      '"A refund · which purchase, all of it or your share"',
                      '"Let it go"', '"Let the other \\(Format.amount(rest)) go?"'):
            assert words in s, words
        parts = self.src("ios/Pearl/Views/Transactions/PartsFlow.swift")
        assert "How much of \\(possessive(firstName(o.person ?? who))) \\(Format.amount(o.owes))?" in parts
        # S-35 no longer takes min(share, what's left) on its own: a tick on
        # someone's share goes to PB-13 first (the min stays only for a
        # purchase with no one on it).
        toggle = parts[parts.index("private func toggle(_ o: Owing)"):]
        assert toggle.index("asksHowMuch(o)") < toggle.index("Double(min(cents(o.owes), room))")
        assert "startHowMuch(queue, asked: asked)" in parts
        for path in ("ios/Pearl/Views/Transactions/PaidBackViews.swift",
                     "ios/Pearl/Views/Transactions/PartsFlow.swift",
                     "ios/Pearl/Views/Review/AnswerSheet.swift"):
            code = self.src(path)
            for stock in (".confirmationDialog(", ".alert(", ".actionSheet("):
                assert stock not in code, (path, stock)
            assert "safe to spend" not in code.lower()

    def test_find_what_paid_it_back(self):
        """PB-20 to PB-24's words, as Pearl sheets (note 1352:10319)."""
        menus = self.src("ios/Pearl/Views/Transactions/SplitMenus.swift")
        for words in ('"Find what paid it back"', '"Work, a refund, or someone paying you"',
                      '"Your share \\(Format.amount(split.you)) · nothing paid it back yet"'):
            assert words in menus, words
        find = self.src("ios/Pearl/Views/Transactions/PaidBackFindViews.swift")
        for words in ('"What paid this back?"', '"Search deposits, or an amount"',
                      '"Your share"', '"\\(whose) share"', '"Next"',
                      '"No money in matches"', '"Clear search"',
                      "If it hasn’t arrived yet, Pearl asks when it does.",
                      '"Take \\(more) from \\(other)?"', '"Take \\(more)"',
                      '"Leave it on \\(other)"', '"Use only the \\(Format.amount(free))"',
                      "of this deposit is free, so it pays back your share first.",
                      '"All of this deposit pays back \\(other).'):
            assert words in find, words
        # LT-01 (TEXT-01): no "Next: …" footnote, no reason on every row.
        for gone in ("Next: who paid you back", "Likely · money in after", "What paid back your share?"):
            assert gone not in find, gone
        who = self.src("ios/Pearl/Views/Transactions/PaidBackViews.swift")
        for words in ('"On this split"', '"your employer"', '"this shop"'):
            assert words in who, words
        # Less text 2: "On this split", not "Sam is on this split"; money
        # Pearl can't place sits under OTHER MONEY IN.
        assert "is on this split" not in who
        assert '("other", "Other money in", other)' in find
        for code in (find, who):
            for stock in (".confirmationDialog(", ".alert(", ".actionSheet("):
                assert stock not in code, stock
            assert "safe to spend" not in code.lower()


class TestFromThePurchase:
    """Paid back from the purchase side (2026-11-15, no UI yet): candidates
    for one person's share, read-only, and a link that goes through the
    same save as PB-13 on the deposit side."""

    def setup(self, client, sent=15.0):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -sent, when=day(1), merchant="Sam Lee"),
                tx("E-TRANSFER FROM PRIYA", -58.0, when=day(2), merchant="Priya"),
                tx("NORTHWIND LTD PAYROLL", -1980.0, "Income", when=day(5)))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        return i

    def dump(self, client, tmp_path):
        import sqlite3
        con = sqlite3.connect(str(tmp_path / "paid_back.db"))
        try:
            return "\n".join(con.iterdump())
        finally:
            con.close()

    def test_candidates_list_theirs_first_and_how_each_splits(self, client):
        i = self.setup(client)
        r = client.get(f"/api/transactions/{i['PAI NORTHERN THAI']}/paid-back-candidates",
                       query_string={"person": "Sam"})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert (body["person"], body["owes"], body["share"]) == ("Sam", 60.0, 60.0)
        first = body["candidates"][0]
        assert (first["id"], first["amount"], first["from_person"]) == (i["E-TRANSFER FROM SAM LEE"], 15.0, True)
        assert first["split"] == {"kind": "part", "part": 15.0, "all": 60.0, "let_go": 45.0, "extra": 0.0}
        ids = [c["id"] for c in body["candidates"]]
        # Closest to what Sam owes next; pay is still money in, so it can be listed, last.
        assert ids.index(i["E-TRANSFER FROM PRIYA"]) < ids.index(i["NORTHWIND LTD PAYROLL"])
        payroll = next(c for c in body["candidates"] if c["id"] == i["NORTHWIND LTD PAYROLL"])
        assert payroll["split"] == {"kind": "more", "part": None, "all": 60.0, "let_go": 0.0, "extra": 1920.0}

    def test_listing_changes_nothing(self, client, tmp_path):
        i = self.setup(client)
        before = self.dump(client, tmp_path)
        for _ in range(2):
            client.get(f"/api/transactions/{i['PAI NORTHERN THAI']}/paid-back-candidates",
                       query_string={"person": "Sam"})
        assert self.dump(client, tmp_path) == before

    def test_someone_not_on_the_split(self, client):
        i = self.setup(client)
        r = client.get(f"/api/transactions/{i['PAI NORTHERN THAI']}/paid-back-candidates",
                       query_string={"person": "Jordan"})
        assert r.status_code == 400 and r.get_json()["error"] == "Pick someone on this split."

    def test_a_linked_deposit_is_no_longer_a_candidate(self, client):
        i = self.setup(client)
        pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]
        parts(client, dep, {"kind": "payback", "amount": 15.0, "charge": pai, "person": "Sam"})
        ids = [c["id"] for c in client.get(f"/api/transactions/{pai}/paid-back-candidates",
                                           query_string={"person": "Sam"}).get_json()["candidates"]]
        assert dep not in ids


def _two(tmp_path):
    """Two apps with the same rows, to link one from each side."""
    from app import create_app
    out = []
    for n in ("deposit", "purchase"):
        app = create_app(str(tmp_path / f"{n}.db"))
        app.config.update(TESTING=True)
        c = app.test_client()
        c.st = app.config["STORE"]
        out.append(c)
    return out


def _state(c, i):
    pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]
    split = detail(c, pai)["splitting"]
    people = [(p["name"], p["amount"], p["paid"], p["owes"], (p["let_go"] or {}).get("was"))
              for p in split["people"]]
    kinds = sorted((p["kind"], p["amount"], p.get("person")) for p in detail(c, dep).get("parts") or [])
    return split["you"], people, kinds


class TestSameAsTheDepositSide:
    """Linking from the purchase side is the deposit side's link: same
    state, same toast, and the same Undo."""

    def rows(self):
        return (tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -15.0, when=day(1), merchant="Sam Lee"))

    @pytest.mark.parametrize("ask", [{}, {"let_go": True}, {"amount": 10.0}])
    def test_both_sides_agree(self, tmp_path, ask):
        a, b = _two(tmp_path)
        ia, ib = add(a, *self.rows()), add(b, *self.rows())
        for c, i in ((a, ia), (b, ib)):
            c.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
                "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        amount = ask.get("amount", 15.0)
        part = {"kind": "payback", "amount": amount, "charge": ia["PAI NORTHERN THAI"], "person": "Sam"}
        if ask.get("let_go"):
            part["let_go"] = True
        ra = parts(a, ia["E-TRANSFER FROM SAM LEE"], part, later=amount < 15.0)
        rb = b.post(f"/api/transactions/{ib['PAI NORTHERN THAI']}/paid-back",
                    json={"deposit": ib["E-TRANSFER FROM SAM LEE"], "person": "Sam", **ask})
        assert ra.status_code == rb.status_code == 200, (ra.get_json(), rb.get_json())
        assert ra.get_json()["title"] == rb.get_json()["title"]
        assert _state(a, ia) == _state(b, ib)
        undo(a, ra.get_json())
        undo(b, rb.get_json())
        assert _state(a, ia) == _state(b, ib)
        assert _state(b, ib)[1] == [("Sam", 60.0, 0.0, 60.0, None)]

    def test_more_than_they_owe_or_the_deposit_is_refused(self, tmp_path):
        _, b = _two(tmp_path)
        i = add(b, *self.rows())
        b.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        r = b.post(f"/api/transactions/{i['PAI NORTHERN THAI']}/paid-back",
                   json={"deposit": i["E-TRANSFER FROM SAM LEE"], "person": "Sam", "amount": 20})
        assert r.status_code == 400 and r.get_json()["error"] == "Make it between $0.01 and $15.00."
        assert _state(b, i)[1] == [("Sam", 60.0, 0.0, 60.0, None)]


class TestFindWhatPaidItBack:
    """PB-20 to PB-24 (approved 2026-11-15, Proposals › "Paid back" 1351:8769,
    note 1352:10319): from her own row on a split, "What paid back your
    share?" lists LIKELY money in after the purchase from work, the shop or
    someone on the split, newest first, with why each matches; search takes
    a name or an amount (PB-23 when nothing does). PB-24: a deposit already
    paying back another purchase links its free part at once, and only
    takes more from the other purchase when she says Take."""

    def setup(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("NORTHWIND LTD PAYROLL", -1980.0, "Income", when=day(20), merchant="Northwind Ltd"),
                tx("NORTHWIND LTD EXPENSES", -60.0, when=day(8), merchant="Northwind Ltd"),
                tx("PAI NORTHERN THAI REFUND", -120.0, when=day(7), merchant="PAI NORTHERN THAI"),
                tx("E-TRANSFER FROM SAM LEE", -15.0, when=day(6), merchant="Sam Lee"),
                tx("COFFEE CO", -60.4, when=day(5)),
                tx("AIR CANADA", 40.0, "Travel", when=day(12)),
                tx("E-TRANSFER FROM SAM BEFORE", -60.0, when=day(14), merchant="Sam Lee"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split", json={
            "mode": "amount", "people": [{"name": "Sam", "amount": 60}]})
        return i

    def find(self, client, i, q=None):
        r = client.get(f"/api/transactions/{i['PAI NORTHERN THAI']}/paid-back-find",
                       query_string={"q": q} if q is not None else {})
        assert r.status_code == 200, r.get_json()
        return r.get_json()

    def test_likely_is_work_the_shop_and_the_split_after_the_purchase_newest_first(self, client):
        i = self.setup(client)
        body = self.find(client, i)
        assert (body["merchant"], body["amount"], body["share"], body["left"], body["date"]) == \
            ("PAI NORTHERN THAI", 120.0, 60.0, 60.0, day(10))
        rows = [(r["id"], r["payer"], r["amount"], r["kind"], r["person"], r["why"]) for r in body["candidates"]]
        assert rows == [
            (i["E-TRANSFER FROM SAM LEE"], "Sam", 15.0, "person", "Sam", ""),
            (i["PAI NORTHERN THAI REFUND"], "PAI NORTHERN THAI", 120.0, "shop", None, "refund"),
            (i["NORTHWIND LTD EXPENSES"], "Northwind Ltd", 60.0, "work", None, "work"),
        ]
        # Before the purchase, or from no one she knows: not likely.
        assert all(r["taken"] is None for r in body["candidates"])

    def test_search_by_amount_or_name(self, client):
        i = self.setup(client)
        sixty = self.find(client, i, "$60")
        assert [(r["payer"], r["why"]) for r in sixty["candidates"]] == [
            ("COFFEE CO", "same as your share"), ("Northwind Ltd", "work")]
        assert [r["payer"] for r in self.find(client, i, "northwind")["candidates"]] == ["Northwind Ltd"]
        # PB-23: nothing for about $999, said back to her.
        none = self.find(client, i, "999")
        assert none["candidates"] == [] and none["about"] == 999.0

    def test_finding_changes_nothing(self, client, tmp_path):
        i = self.setup(client)
        before = TestFromThePurchase().dump(client, tmp_path)
        for q in (None, "$60", "northwind"):
            self.find(client, i, q)
        assert TestFromThePurchase().dump(client, tmp_path) == before

    def test_only_her_share_of_a_split(self, client):
        i = self.setup(client)
        r = client.get(f"/api/transactions/{i['AIR CANADA']}/paid-back-find")
        assert r.status_code == 404

    def taken(self, client, i):
        dep = i["NORTHWIND LTD EXPENSES"]
        r = parts(client, dep, {"kind": "reimbursement", "amount": 40.0, "charge": i["AIR CANADA"]}, later=True)
        assert r.status_code == 200, r.get_json()
        return dep

    def deposit_parts(self, client, dep):
        return [(p["kind"], p["amount"], (p.get("charge") or {}).get("merchant")) for p in detail(client, dep)["parts"]]

    def test_pb24_says_what_is_free_and_what_it_would_take(self, client):
        i = self.setup(client)
        self.taken(client, i)
        row = self.find(client, i, "northwind")["candidates"][0]
        assert row["kind"] == "work"
        assert row["taken"] == {"free": 20.0, "need": 60.0, "more": 40.0,
                                "other": {"id": i["AIR CANADA"], "merchant": "AIR CANADA"}}

    @pytest.mark.parametrize("take", [False, True])
    def test_pb24_links_the_free_part_or_takes_more_with_one_undo(self, client, take):
        i = self.setup(client)
        dep, pai = self.taken(client, i), i["PAI NORTHERN THAI"]
        before = self.deposit_parts(client, dep)
        r = client.post(f"/api/transactions/{pai}/paid-back-take", json={"deposit": dep, "take": take})
        assert r.status_code == 200, r.get_json()
        if take:
            assert r.get_json()["title"] == "Moved $40.00 from AIR CANADA"
            assert self.deposit_parts(client, dep) == [("reimbursement", 60.0, "PAI NORTHERN THAI")]
            assert detail(client, pai)["splitting"]["mine"]["reimbursed"] == 60.0
        else:
            assert r.get_json()["title"] == "Linked $20.00 · PAI NORTHERN THAI"
            assert self.deposit_parts(client, dep) == [("reimbursement", 40.0, "AIR CANADA"),
                                                       ("reimbursement", 20.0, "PAI NORTHERN THAI")]
            mine = detail(client, pai)["splitting"]["mine"]
            assert (mine["reimbursed"], mine["stays"]) == (20.0, 40.0)
        undo(client, r.get_json())
        assert self.deposit_parts(client, dep) == before
        assert detail(client, pai)["splitting"].get("mine") is None

    def test_pb24_when_the_free_part_covers_it(self, client):
        i = self.setup(client)
        i.update(add(client, tx("NORTHWIND LTD TRAVEL", -100.0, when=day(4), merchant="Northwind Ltd")))
        dep, pai = i["NORTHWIND LTD TRAVEL"], i["PAI NORTHERN THAI"]
        parts(client, dep, {"kind": "reimbursement", "amount": 40.0, "charge": i["AIR CANADA"]}, later=True)
        row = next(r for r in self.find(client, i, "northwind")["candidates"] if r["id"] == dep)
        assert row["taken"]["more"] == 0.0
        r = client.post(f"/api/transactions/{pai}/paid-back-take", json={"deposit": dep})
        assert r.status_code == 200 and r.get_json()["title"] == "Linked $60.00 · PAI NORTHERN THAI"

    def test_pb24_with_nothing_free_needs_take(self, client):
        i = self.setup(client)
        dep, pai = i["NORTHWIND LTD EXPENSES"], i["PAI NORTHERN THAI"]
        parts(client, dep, {"kind": "reimbursement", "amount": 40.0, "charge": i["AIR CANADA"]},
              {"kind": "gift", "amount": 20.0})
        row = next(r for r in self.find(client, i, "northwind")["candidates"] if r["id"] == dep)
        assert row["taken"]["free"] == 0.0 and row["taken"]["more"] == 40.0
        r = client.post(f"/api/transactions/{pai}/paid-back-take", json={"deposit": dep, "take": False})
        assert r.status_code == 400 and r.get_json()["error"] == "None of this deposit is free."
        r = client.post(f"/api/transactions/{pai}/paid-back-take", json={"deposit": dep, "take": True})
        assert r.status_code == 200 and r.get_json()["title"] == "Moved $40.00 from AIR CANADA"

    def test_pb24_on_a_payback_linked_whole(self, client):
        i = self.setup(client)
        i.update(add(client, tx("TACOS", 80.0, "Dining", when=day(11)),
                     tx("E-TRANSFER FROM SAM AGAIN", -60.0, when=day(3), merchant="Sam Lee")))
        tacos, dep, pai = i["TACOS"], i["E-TRANSFER FROM SAM AGAIN"], i["PAI NORTHERN THAI"]
        client.put(f"/api/transactions/{tacos}/split", json={"mode": "amount", "people": [{"name": "Sam", "amount": 40}]})
        client.st.link_payback(tacos, dep, "Sam", amount=40.0)
        row = next(r for r in self.find(client, i)["candidates"] if r["id"] == dep)
        assert (row["kind"], row["person"]) == ("person", "Sam")
        assert row["taken"] == {"free": 20.0, "need": 60.0, "more": 40.0,
                                "other": {"id": tacos, "merchant": "TACOS"}}
        r = client.post(f"/api/transactions/{pai}/paid-back-take", json={"deposit": dep})
        assert r.status_code == 200 and r.get_json()["title"] == "Linked $20.00 · PAI NORTHERN THAI"
        assert owing(client, pai)["Sam"] == (20.0, 40.0)
        assert owing(client, tacos)["Sam"] == (40.0, 0.0)
        undo(client, r.get_json())
        x = client.st.get_transaction(dep)
        assert (x.repays, x.repays_amount, client.st.payback_people().get(dep)) == (tacos, 40.0, "Sam")
        assert owing(client, pai)["Sam"] == (0.0, 60.0)

    def test_a_deposit_already_on_this_purchase_isnt_listed(self, client):
        i = self.setup(client)
        dep, pai = i["NORTHWIND LTD EXPENSES"], i["PAI NORTHERN THAI"]
        r = client.post(f"/api/transactions/{dep}/mark", json={"case": "reimbursement", "charge": pai, "share": True})
        assert r.status_code == 200, r.get_json()
        assert dep not in [c["id"] for c in self.find(client, i, "northwind")["candidates"]]


class TestWhoFromTheDeposit(TestFindWhatPaidItBack):
    """PB-11 from the deposit (PAID-03): Pearl picks the kind the way PB-22
    reads it from the purchase side, by who sent it: someone on a split
    before it, the same shop, or whoever pays her."""

    def who(self, client, tid):
        r = client.get(f"/api/transactions/{tid}/paid-back-who")
        assert r.status_code == 200, r.get_json()
        return r.get_json()

    def test_a_person_on_a_split_the_shop_and_work(self, client):
        i = self.setup(client)
        assert self.who(client, i["E-TRANSFER FROM SAM LEE"]) == {"kind": "person", "person": "Sam"}
        assert self.who(client, i["PAI NORTHERN THAI REFUND"]) == {"kind": "shop", "person": None}
        assert self.who(client, i["NORTHWIND LTD EXPENSES"]) == {"kind": "work", "person": None}
        assert self.who(client, i["COFFEE CO"]) == {"kind": None, "person": None}

    def test_only_a_split_from_before_it(self, client):
        i = self.setup(client)
        # Sam's e-Transfer on day(14) came before the split purchase (day(10)).
        assert self.who(client, i["E-TRANSFER FROM SAM BEFORE"])["kind"] is None

    def test_money_out_and_unknown(self, client):
        i = self.setup(client)
        assert self.who(client, i["AIR CANADA"]) == {"kind": None, "person": None}
        assert client.get("/api/transactions/nope/paid-back-who").status_code == 404
