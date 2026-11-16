"""Paybacks & undo (Figma Proposals › "Paybacks & undo" 1395:3376, approved
2026-11-16; THL-289, THL-291, THL-181, THL-301).

PB-30: one e-Transfer pays back several purchases in one request, so one
Undo puts every link back. PB-41 / PB-42: link first, edit later; one link's
How much, Which purchase and Who paid change it in place, each with Undo.

Also the purchase side: one deposit paying back two people's shares, each
linked from the purchase (`POST …/paid-back`), used to refuse the second."""

from __future__ import annotations

import pytest

from tests.test_paid_back import add, client, day, detail, owing, parts, tx, undo  # noqa: F401


def _split(c, charge, *people):
    r = c.put(f"/api/transactions/{charge}/split", json={
        "mode": "amount", "people": [{"name": n, "amount": a} for n, a in people]})
    assert r.status_code == 200, r.get_json()


def _paybacks(c, dep):
    return sorted((p["kind"], p["amount"], p.get("person"), (p.get("charge") or {}).get("merchant"))
                  for p in detail(c, dep).get("parts") or [])


class TestOneDepositTwoPeopleFromThePurchase:
    """Sam sends $80.00 for himself and Jo. From the purchase, Sam's share is
    linked, then Jo's from the same e-Transfer."""

    def setup(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -80.0, when=day(1), merchant="Sam Lee"))
        _split(client, i["PAI NORTHERN THAI"], ("Sam", 40), ("Jo", 40))
        return i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]

    def link(self, client, pai, dep, who, **more):
        return client.post(f"/api/transactions/{pai}/paid-back", json={"deposit": dep, "person": who, **more})

    def test_the_second_person_links_from_the_same_deposit(self, client):
        pai, dep = self.setup(client)
        first = self.link(client, pai, dep, "Sam")
        assert first.status_code == 200, first.get_json()
        second = self.link(client, pai, dep, "Jo")
        # Before the fix: 400 "Pick the money that paid it back." (the
        # deposit was in parts, so it no longer counted as free).
        assert second.status_code == 200, second.get_json()
        assert second.get_json()["title"] == "Jo paid back $40.00"
        assert owing(client, pai) == {"Sam": (40.0, 0.0), "Jo": (40.0, 0.0)}
        assert _paybacks(client, dep) == [("payback", 40.0, "Jo", "PAI NORTHERN THAI"),
                                          ("payback", 40.0, "Sam", "PAI NORTHERN THAI")]

    def test_undo_takes_back_only_the_second_link(self, client):
        pai, dep = self.setup(client)
        self.link(client, pai, dep, "Sam")
        second = self.link(client, pai, dep, "Jo")
        undo(client, second.get_json())
        assert owing(client, pai) == {"Sam": (40.0, 0.0), "Jo": (0.0, 40.0)}
        kinds = _paybacks(client, dep)
        assert ("payback", 40.0, "Sam", "PAI NORTHERN THAI") in kinds
        assert ("rest", 40.0, None, None) in kinds

    def test_only_what_is_left_of_it(self, client):
        pai, dep = self.setup(client)
        self.link(client, pai, dep, "Sam")
        r = self.link(client, pai, dep, "Jo", amount=50)
        assert r.status_code == 400 and r.get_json()["error"] == "Make it between $0.01 and $40.00."

    def test_a_deposit_with_nothing_left_is_refused(self, client):
        pai, dep = self.setup(client)
        parts(client, dep, {"kind": "payback", "amount": 40.0, "charge": pai, "person": "Sam"},
              {"kind": "gift", "amount": 40.0})
        r = self.link(client, pai, dep, "Jo")
        assert r.status_code == 400 and r.get_json()["error"] == "Pick the money that paid it back."


class TestPB30OneRequest:
    """PB-30: the ticked shares go in one request (ids and amounts); the
    toast counts the purchases, and one Undo puts every link back."""

    def setup(self, client, sent=86.65):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("PIZZA NOVA", 79.95, "Dining", when=day(12)),
                tx("E-TRANSFER FROM SAM LEE", -sent, when=day(1), merchant="Sam Lee"))
        _split(client, i["PAI NORTHERN THAI"], ("Sam", 60))
        _split(client, i["PIZZA NOVA"], ("Sam", 26.65), ("Jo", 26.65))
        return i

    def test_two_purchases_one_toast_one_undo(self, client):
        i = self.setup(client)
        pai, pizza, dep = i["PAI NORTHERN THAI"], i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
        r = parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"},
                  {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"})
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Sam paid back 2 purchases · $86.65"
        assert owing(client, pai)["Sam"] == (60.0, 0.0)
        assert owing(client, pizza)["Sam"] == (26.65, 0.0)
        undo(client, r.get_json())
        assert owing(client, pai)["Sam"] == (0.0, 60.0)
        assert owing(client, pizza)["Sam"] == (0.0, 26.65)

    def test_pb30o_the_newest_part_paid(self, client):
        i = self.setup(client, sent=70.0)
        pai, pizza, dep = i["PAI NORTHERN THAI"], i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
        # The app sends the oldest in full and the newest part-paid.
        r = parts(client, dep, {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"},
                  {"kind": "payback", "amount": 43.35, "charge": pai, "person": "Sam"})
        assert r.status_code == 200, r.get_json()
        assert owing(client, pai)["Sam"] == (43.35, 16.65)

    def test_replace_has_its_own_undo(self, client):
        """PB-41 Change what it paid back reopens PB-30 and saves with
        `replace`; Undo puts the old links back, not nothing."""
        i = self.setup(client)
        pai, pizza, dep = i["PAI NORTHERN THAI"], i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
        parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"},
              {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"})
        r = client.post(f"/api/transactions/{dep}/parts", json={
            "parts": [{"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"}],
            "later": True, "replace": True})
        assert r.status_code == 200, r.get_json()
        assert owing(client, pizza)["Sam"] == (0.0, 26.65)
        undo(client, r.get_json())
        assert owing(client, pizza)["Sam"] == (26.65, 0.0)
        assert owing(client, pai)["Sam"] == (60.0, 0.0)

    def test_parts_list_each_share(self, client):
        """PB-41: "Sam’s share · all of it": each payback part says the share."""
        i = self.setup(client)
        pai, pizza, dep = i["PAI NORTHERN THAI"], i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
        parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"},
              {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"})
        shares = sorted((p["charge"]["merchant"], p["share"]) for p in detail(client, dep)["parts"])
        assert shares == [("PAI NORTHERN THAI", 60.0), ("PIZZA NOVA", 26.65)]


class TestPB42Change:
    """PB-42: How much, Which purchase and Who paid, on one link, from the
    purchase or the deposit (the same request), each with one Undo."""

    def setup(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("PIZZA NOVA", 79.95, "Dining", when=day(12)),
                tx("E-TRANSFER FROM SAM LEE", -86.65, when=day(1), merchant="Sam Lee"))
        _split(client, i["PAI NORTHERN THAI"], ("Sam", 60))
        _split(client, i["PIZZA NOVA"], ("Sam", 26.65), ("Jo", 26.65))
        pai, pizza, dep = i["PAI NORTHERN THAI"], i["PIZZA NOVA"], i["E-TRANSFER FROM SAM LEE"]
        parts(client, dep, {"kind": "payback", "amount": 60.0, "charge": pai, "person": "Sam"},
              {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"})
        part = next(p["id"] for p in detail(client, dep)["parts"] if p["charge"]["id"] == pizza)
        return pai, pizza, dep, part

    def change(self, client, charge, inflow, **body):
        return client.post(f"/api/transactions/{charge}/paybacks/{inflow}/change", json=body)

    def test_how_much_part_of_it(self, client):
        pai, pizza, dep, part = self.setup(client)
        r = self.change(client, pizza, part, amount=20)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Sam paid back $20.00"
        assert owing(client, pizza)["Sam"] == (20.0, 6.65)
        assert ("rest", 6.65, None, None) in _paybacks(client, dep)
        undo(client, r.get_json())
        assert owing(client, pizza)["Sam"] == (26.65, 0.0)
        assert ("rest", 6.65, None, None) not in _paybacks(client, dep)

    def test_how_much_is_bounded(self, client):
        pai, pizza, dep, part = self.setup(client)
        r = self.change(client, pizza, part, amount=30)
        assert r.status_code == 400 and r.get_json()["error"] == "Make it between $0.01 and $26.65."

    def test_which_purchase(self, client):
        pai, pizza, dep, part = self.setup(client)
        pai_part = next(p["id"] for p in detail(client, dep)["parts"] if p["charge"]["id"] == pai)
        # Make room on Pai first: Sam paid $40.00 of it with this.
        self.change(client, pai, pai_part, amount=40)
        pizza_part = next(p["id"] for p in detail(client, dep)["parts"]
                          if (p.get("charge") or {}).get("id") == pizza)
        r = self.change(client, pizza, pizza_part, to=pai)
        assert r.status_code == 200, r.get_json()
        assert r.get_json()["title"] == "Linked $20.00 · PAI NORTHERN THAI"
        assert owing(client, pai)["Sam"] == (60.0, 0.0)
        assert owing(client, pizza)["Sam"] == (0.0, 26.65)
        undo(client, r.get_json())
        assert owing(client, pizza)["Sam"] == (26.65, 0.0)

    def test_which_purchase_needs_them_on_it(self, client):
        pai, pizza, dep, part = self.setup(client)
        other = add(client, tx("COSTCO", 50.0, "Groceries", when=day(11)))["COSTCO"]
        r = self.change(client, pizza, part, to=other)
        assert r.status_code == 400 and r.get_json()["error"] == "Pick a purchase Sam is on."

    def test_who_paid_the_shop(self, client):
        pai, pizza, dep, part = self.setup(client)
        r = self.change(client, pizza, part, kind="shop")
        assert r.status_code == 200, r.get_json()
        assert ("refund", 26.65, None, "PIZZA NOVA") in _paybacks(client, dep)
        assert owing(client, pizza)["Sam"] == (0.0, 26.65)
        undo(client, r.get_json())
        assert owing(client, pizza)["Sam"] == (26.65, 0.0)

    def test_a_payback_linked_whole_becomes_parts_and_comes_back(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(10)),
                tx("E-TRANSFER FROM SAM LEE", -60.0, when=day(1), merchant="Sam Lee"))
        pai, dep = i["PAI NORTHERN THAI"], i["E-TRANSFER FROM SAM LEE"]
        _split(client, pai, ("Sam", 60))
        r = client.post(f"/api/transactions/{pai}/paybacks/{dep}", json={"person": "Sam"})
        assert r.status_code == 200, r.get_json()
        assert owing(client, pai)["Sam"] == (60.0, 0.0)
        r = self.change(client, pai, dep, amount=45)
        assert r.status_code == 200, r.get_json()
        assert owing(client, pai)["Sam"] == (45.0, 15.0)
        undo(client, r.get_json())
        assert owing(client, pai)["Sam"] == (60.0, 0.0)
        assert not detail(client, dep).get("parts")

    def test_a_link_this_purchase_doesnt_have(self, client):
        pai, pizza, dep, part = self.setup(client)
        r = self.change(client, pai, part, amount=10)
        assert r.status_code == 404

    @pytest.mark.parametrize("body", [{}, {"amount": "x"}, {"kind": "aliens"}])
    def test_nothing_to_change(self, client, body):
        pai, pizza, dep, part = self.setup(client)
        r = self.change(client, pizza, part, **body)
        assert r.status_code == 400


class TestLinkSaysWhatStays:
    """PB-42's Unlink… line: "Sam will owe you $26.65 again on Pizza Nova.
    Pai Northern Thai stays paid." The link says the share and what the
    same payment still pays back."""

    def test_stays_and_share(self, client):
        pai, pizza, dep, part = TestPB42Change().setup(client)
        sam = next(p for p in detail(client, pizza)["splitting"]["people"] if p["name"] == "Sam")
        link = sam["links"][0]
        assert link["stays"] == ["PAI NORTHERN THAI"]
        assert link["share"] == 26.65
