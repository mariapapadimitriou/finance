"""TEST-31 Money back (product owner, 2026-11-14): a refund ("Money back")
of your own share of a split purchase gets the same options as work paying
it back. Pai Northern Thai $120.00, split with Sam ($60.00 each); the
restaurant gives money back on your part."""

from __future__ import annotations

from finance.marks import REFUND_SHARE
from test_reimburse_your_share import TODAY, add, client, costs, dinner, sam, splitting, tx  # noqa: F401


def money_back(c, deposit, charge, share=True):
    return c.post(f"/api/transactions/{deposit}/mark",
                  json={"case": "refund", "charge": charge, "share": share})


def refund_candidates(c, deposit):
    cases = c.get(f"/api/transactions/{deposit}/cases").get_json()
    item = next(x for x in cases["cases"] if x["key"] == "refund")
    return item.get("candidates") or []


class TestYourShareIsAMatch:
    def test_listed_beside_all_of_it(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        got = [c for c in refund_candidates(client, i["PAI NORTHERN THAI REFUND"])
               if c["id"] == i["PAI NORTHERN THAI"]]
        assert [(c.get("share", False), c.get("left"), c["exact"]) for c in got] == \
            [(True, 60.0, True), (False, None, False)]
        assert got[0]["split_with"] == ["Sam"] and got[1]["split_with"] == ["Sam"]

    def test_another_merchant_matches_by_amount(self, client):
        """Money back from somewhere else matches her share by its amount."""
        i = dinner(client, tx("UBER EATS CREDIT", -60.0, merchant="Uber Eats"))
        got = [c for c in refund_candidates(client, i["UBER EATS CREDIT"]) if c["id"] == i["PAI NORTHERN THAI"]]
        assert got and got[0].get("share")


class TestFullShare:
    def test_counts_for_you_not_sam(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        r = money_back(client, dep, tid)
        assert r.status_code == 200, r.get_json()
        assert "extra" not in r.get_json()
        assert splitting(client, tid)["mine"]["reimbursed"] == 60.0
        assert sam(client, tid)["owes"] == 60.0 and sam(client, tid)["amount"] == 60.0
        # Rule A: the dinner costs $60.00 now, Sam's part still counts until he pays.
        assert costs(client, tid) == 60.0
        assert client.st.payback_kinds()[dep] == REFUND_SHARE
        d = client.get(f"/api/transactions/{dep}").get_json()
        # T-41m: it reads as a refund, for her share.
        assert d["counts"] != "income" and d["chip"]["label"] == "Refund"
        assert d["refund_of"]["share"] is True and d["refund_of"]["paid"] == 60.0
        assert d["repays_charge"]["kind"] == REFUND_SHARE and d["repays_charge"]["person"] == "me"

    def test_undo(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        tid = i["PAI NORTHERN THAI"]
        body = money_back(client, i["PAI NORTHERN THAI REFUND"], tid).get_json()
        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        assert "mine" not in splitting(client, tid) and costs(client, tid) == 120.0

    def test_all_of_it_is_still_a_refund_of_the_purchase(self, client):
        """"All of it" keeps today's refund: it shrinks every part the way
        the purchase was split (decision 6), so Sam's part goes too."""
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -120.0, merchant="Pai Northern Thai"))
        tid = i["PAI NORTHERN THAI"]
        r = money_back(client, i["PAI NORTHERN THAI REFUND"], tid, share=False)
        assert r.status_code == 200, r.get_json()
        assert sam(client, tid)["amount"] == 0.0 and sam(client, tid)["owes"] == 0.0
        assert costs(client, tid) == 0.0

    def test_answering_all_of_it_after_your_share_moves_it(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        money_back(client, dep, tid)
        money_back(client, dep, tid, share=False)
        assert "mine" not in splitting(client, tid)
        assert client.st.get_transaction(dep).repays is None
        assert client.get(f"/api/transactions/{dep}").get_json().get("refund_of") is not None

    def test_not_in_the_split_changes_nothing(self, client):
        i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", merchant="Pai Northern Thai"),
                tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split",
                   json={"mode": "even", "include_me": False, "people": [{"name": "Sam"}]})
        r = money_back(client, i["PAI NORTHERN THAI REFUND"], i["PAI NORTHERN THAI"])
        assert r.status_code == 400
        assert client.st.get_transaction(i["PAI NORTHERN THAI REFUND"]).repays is None


class TestPartial:
    def test_the_rest_stays_yours(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -45.0, merchant="Pai Northern Thai"))
        tid = i["PAI NORTHERN THAI"]
        body = money_back(client, i["PAI NORTHERN THAI REFUND"], tid).get_json()
        assert body["detail"] == "$15.00 of your share stays yours."
        assert splitting(client, tid)["mine"]["stays"] == 15.0
        assert costs(client, tid) == 75.0


class TestMoreThanYourShare:
    def test_the_extra_is_asked_and_parts_keep_your_share(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -75.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        body = money_back(client, dep, tid).get_json()
        assert body["extra"] == {"amount": 15.0, "whole": 75.0, "share": 60.0, "charge": tid,
                                 "merchant": "Pai Northern Thai",
                                 "people": [{"name": "Sam", "owes": 60.0}]}
        assert body["detail"] == "$60.00 refunds your share of Pai Northern Thai."
        assert costs(client, tid) == 60.0 and sam(client, tid)["owes"] == 60.0
        # The extra's answer saves as parts: her share's money back, then a gift.
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "gift", "amount": 15}]})
        assert r.status_code == 200, r.get_json()
        s = splitting(client, tid)
        assert s["mine"]["reimbursed"] == 60.0 and sam(client, tid)["owes"] == 60.0
        assert costs(client, tid) == 60.0


class TestSamPaysToo:
    def test_costs_you_nothing(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"),
                   tx("E-TRANSFER FROM SAM", -60.0, merchant="Sam"))
        tid = i["PAI NORTHERN THAI"]
        money_back(client, i["PAI NORTHERN THAI REFUND"], tid)
        client.post(f"/api/transactions/{tid}/paybacks/{i['E-TRANSFER FROM SAM']}", json={"person": "Sam"})
        assert sam(client, tid)["owes"] == 0.0 and costs(client, tid) == 0.0

    def test_work_and_money_back_share_one_share(self, client):
        """Her share is one share: work's $40.00, then money back can only
        cover the $20.00 left."""
        i = dinner(client, tx("NORTHWIND LTD PAYROLL", -40.0, merchant="Northwind Ltd"),
                   tx("PAI NORTHERN THAI REFUND", -30.0, merchant="Pai Northern Thai"))
        tid = i["PAI NORTHERN THAI"]
        client.post(f"/api/transactions/{i['NORTHWIND LTD PAYROLL']}/mark",
                    json={"case": "reimbursement", "charge": tid, "share": True})
        body = money_back(client, i["PAI NORTHERN THAI REFUND"], tid).get_json()
        assert body["extra"]["amount"] == 10.0 and body["extra"]["share"] == 20.0
        assert splitting(client, tid)["mine"]["reimbursed"] == 60.0
        assert costs(client, tid) == 60.0


class TestUnlink:
    def test_unlink_refund_from_the_refund_page(self, client):
        """T-41m / S-40m: Unlink refund takes her share's refund off, with Undo."""
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        money_back(client, dep, tid)
        link = splitting(client, tid)["mine"]["links"][0]
        assert link["kind"] == "refund" and link["sheet"]["title"] == "Unlink refund?"
        assert link["view"]["label"] == "View the refund" and link["amount"] == 60.0
        r = client.delete(f"/api/transactions/{dep}/refund")
        assert r.status_code == 200, r.get_json()
        assert "mine" not in splitting(client, tid) and costs(client, tid) == 120.0
        assert client.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
        assert splitting(client, tid)["mine"]["reimbursed"] == 60.0


class TestTheExtraTowardSomeonesShare:
    """S-11m / S-04m4 (decision 2, 2026-11-14): the extra can count toward
    what someone on the split still owes, up to what they owe."""

    def test_part_of_sams_share(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -75.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        money_back(client, dep, tid)
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "refund", "amount": 15, "charge": tid, "person": "Sam"}]})
        assert r.status_code == 200, r.get_json()
        s = sam(client, tid)
        assert (s["paid"], s["owes"]) == (15.0, 45.0)
        assert splitting(client, tid)["mine"]["reimbursed"] == 60.0
        assert costs(client, tid) == 45.0
        # Unlink is on Sam's ••• like any payment.
        assert [link["kind"] for link in s["links"]] == ["refund"]

    def test_never_more_than_they_owe(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -130.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "refund", "amount": 70, "charge": tid, "person": "Sam"}]})
        assert r.status_code == 400 and r.get_json()["error"] == "Sam owes $60.00. Make it $60.00 or less."
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "refund", "amount": 60, "charge": tid, "person": "Sam"},
            {"kind": "gift", "amount": 10}]})
        assert r.status_code == 200, r.get_json()
        assert sam(client, tid)["owes"] == 0.0 and costs(client, tid) == 0.0

    def test_only_someone_on_the_split(self, client):
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -75.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "refund", "amount": 15, "charge": tid, "person": "Jo"}]})
        assert r.status_code == 400 and r.get_json()["error"] == "Pick someone on this split."


class TestTheExtraTiles:
    def test_only_people_who_still_owe(self, client):
        """S-11m: a person tile for each person who still owes, in order."""
        i = add(client, tx("PIZZA NOVA", 120.0, "Dining", merchant="Pizza Nova"),
                tx("PIZZA NOVA REFUND", -50.0, merchant="Pizza Nova"),
                tx("E-TRANSFER FROM JO", -30.0, merchant="Jo"))
        tid = i["PIZZA NOVA"]
        client.put(f"/api/transactions/{tid}/split",
                   json={"mode": "even", "people": [{"name": "Jo"}, {"name": "Sam"}, {"name": "Priya"}]})
        client.post(f"/api/transactions/{tid}/paybacks/{i['E-TRANSFER FROM JO']}", json={"person": "Jo"})
        body = money_back(client, i["PIZZA NOVA REFUND"], tid).get_json()
        assert body["extra"]["amount"] == 20.0
        assert [p["name"] for p in body["extra"]["people"]] == ["Sam", "Priya"]

    def test_not_mine_is_a_part_here(self, client):
        """S-11m's Not mine: that part is left out."""
        i = dinner(client, tx("PAI NORTHERN THAI REFUND", -75.0, merchant="Pai Northern Thai"))
        tid, dep = i["PAI NORTHERN THAI"], i["PAI NORTHERN THAI REFUND"]
        money_back(client, dep, tid)
        r = client.post(f"/api/transactions/{dep}/parts", json={"parts": [
            {"kind": "refund", "amount": 60, "charge": tid, "share": True},
            {"kind": "not_mine", "amount": 15}]})
        assert r.status_code == 200, r.get_json()
        parts = r.get_json()["parts"]
        mine_not = next(p for p in parts if p["kind"] == "not_mine")
        assert client.st.get_transaction(mine_not["id"]).excluded == "Not mine"
        assert costs(client, tid) == 60.0


def test_her_row_says_refunded(client):
    """S-04m: the split card knows a refund covered her share."""
    i = dinner(client, tx("PAI NORTHERN THAI REFUND", -60.0, merchant="Pai Northern Thai"),
               tx("NORTHWIND LTD PAYROLL", -60.0, merchant="Northwind Ltd"))
    tid = i["PAI NORTHERN THAI"]
    money_back(client, i["PAI NORTHERN THAI REFUND"], tid)
    assert splitting(client, tid)["mine"]["kind"] == "refund"
    money_back(client, i["PAI NORTHERN THAI REFUND"], tid, share=False)
    client.post(f"/api/transactions/{i['NORTHWIND LTD PAYROLL']}/mark",
                json={"case": "reimbursement", "charge": tid, "share": True})
    assert splitting(client, tid)["mine"]["kind"] == "reimbursement"
