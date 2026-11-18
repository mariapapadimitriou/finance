"""Many purchases (Figma Proposals › "Many purchases" 1431:6590, note
1432:8062; approved 2026-11-17): the shop and Work pay back several of her
purchases in one save, as PB-30 does for a person.

MP-01 / MP-02's list is GET …/many-purchases; the one tap, MP-03's
leftover (S-11w / S-11m) and MP-04's part-paid newest all go in one POST
…/parts, and MP-05's one Undo puts every bit of it back. Demo data only.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def day(n: int) -> str:
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def row(desc, amount, account="chq", when=None, merchant=None, category="", kind="depository"):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account,
                       account_name={"chq": "Chequing ••4417", "amex": "Amex Cobalt ••1001"}[account],
                       raw={"account_type": kind})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "many.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        yield c


def add(c, account, *rows):
    ingest(c.st, IngestResult(list(rows), account))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def numbers(c):
    lst = ok(c.get("/api/transactions/list", query_string={"month": MONTH, "limit": 500}))
    return {"spent": lst["month_totals"]["spent"], "allowance": ok(c.get("/api/home"))["safe_to_spend"]["amount"]}


def world(c):
    rows = {t.fingerprint: (t.category, t.category_source, t.my_share, t.share_set, t.excluded, t.repays,
                            tuple(t.repays_all or ()), t.refunded, t.paid_back)
            for t in c.st.all_transactions()}
    return {"rows": rows, "splits": c.st.splits(), "parts": c.st.parts(), "payer": c.st.payback_people(),
            "kinds": c.st.payback_kinds(), "refunds": c.st.refunds(), "numbers": numbers(c)}


def many(c, dep, kind, q=""):
    return ok(c.get(f"/api/transactions/{dep}/many-purchases", query_string={"kind": kind, "q": q}))


def save(c, dep, parts, payer, later=False):
    return c.post(f"/api/transactions/{dep}/parts", json={"parts": parts, "later": later, "payer": payer})


def undo(c, reply):
    ok(c.post("/api/transactions/undo", json=reply["undo"]))


def owes(c, charge):
    return {p["name"]: p["owes"] for p in ok(c.get(f"/api/transactions/{charge}"))["splitting"]["people"]}


# ── MP-01 / MP-02: who's on the list ────────────────────────────────────

def test_work_lists_what_she_marked_as_work_and_what_work_paid_before(client):
    i = add(client, "amex",
            row("AIR CANADA", 112.30, "amex", when=ago(16), category="Travel", kind="credit"),
            row("UBER", 14.10, "amex", when=ago(15), category="Transport", kind="credit"),
            row("STAPLES", 23.80, "amex", when=ago(25), category="Shopping", kind="credit"),
            row("LOBLAWS", 61.00, "amex", when=ago(10), category="Groceries", kind="credit"),
            row("UBER ", 9.00, "amex", when=ago(60), category="Transport", kind="credit"))
    ok(client.post(f"/api/transactions/{i['AIR CANADA']}/mark", json={"case": "work"}))
    # Work paid an earlier Uber back, so Uber is likely next time.
    j = add(client, "chq", row("NORTHWIND OLD", -9.00, when=ago(55), merchant="Northwind Ltd"))
    ok(client.post(f"/api/transactions/{j['NORTHWIND OLD']}/parts", json={
        "parts": [{"kind": "reimbursement", "amount": 9.00, "charge": i["UBER "]}], "later": False}))
    j = add(client, "chq", row("NORTHWIND LTD", -126.40, when=ago(1), merchant="Northwind Ltd"))
    got = many(client, j["NORTHWIND LTD"], "work")
    ids = {o["id"]: o for o in got["items"]}
    assert set(ids) == {i["AIR CANADA"], i["UBER"]}
    assert ids[i["AIR CANADA"]]["work"] is True and ids[i["UBER"]]["amount"] == 14.10
    # Newest first, as PB-30 lists them.
    assert [o["date"] for o in got["items"]] == sorted((o["date"] for o in got["items"]), reverse=True)
    # MP-01's search adds any other purchase, by name or by amount.
    assert i["STAPLES"] in {o["id"] for o in many(client, j["NORTHWIND LTD"], "work", "staples")["items"]}
    assert i["LOBLAWS"] in {o["id"] for o in many(client, j["NORTHWIND LTD"], "work", "61.00")["items"]}


def test_her_share_of_a_split_is_the_row(client):
    i = add(client, "amex", row("PAI NORTHERN THAI", 120.0, "amex", when=day(4), category="Dining", kind="credit"))
    ok(client.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split",
                  json={"mode": "amount", "people": [{"name": "Sam", "amount": 60.0}]}))
    ok(client.post(f"/api/transactions/{i['PAI NORTHERN THAI']}/mark", json={"case": "work"}))
    j = add(client, "chq", row("NORTHWIND LTD", -60.0, when=day(1), merchant="Northwind Ltd"))
    got = many(client, j["NORTHWIND LTD"], "work", "pai")
    o = next(o for o in got["items"] if o["id"] == i["PAI NORTHERN THAI"])
    assert (o["amount"], o["share"], o["whole"]) == (60.0, True, 120.0)
    assert o["people"] == [{"name": "Sam", "owes": 60.0}]


def test_the_shop_lists_its_purchases_before_the_refund(client):
    i = add(client, "amex",
            row("COSTCO WHOLESALE", 42.99, "amex", when=ago(7), category="Groceries", kind="credit"),
            row("COSTCO GAS", 21.98, "amex", when=ago(13), category="Transport", kind="credit"),
            row("COSTCO WHOLESALE ", 18.00, "amex", when=ago(0), category="Groceries", kind="credit"),
            row("LOBLAWS", 42.99, "amex", when=ago(7), category="Groceries", kind="credit"))
    j = add(client, "chq", row("COSTCO REFUND", -64.97, when=ago(3), merchant="Costco"))
    got = many(client, j["COSTCO REFUND"], "shop")
    assert {o["id"] for o in got["items"]} == {i["COSTCO WHOLESALE"], i["COSTCO GAS"]}
    assert got["shop"] == "Costco"


def test_the_purchase_she_came_from_stays_on_the_list(client):
    """PB-22 › Work from a purchase not marked as work: MP-01 keeps it ticked."""
    i = add(client, "amex", row("STAPLES", 23.80, "amex", when=ago(5), category="Shopping", kind="credit"))
    j = add(client, "chq", row("NORTHWIND LTD", -23.80, when=ago(1), merchant="Northwind Ltd"))
    assert many(client, j["NORTHWIND LTD"], "work")["items"] == []
    got = ok(client.get(f"/api/transactions/{j['NORTHWIND LTD']}/many-purchases",
                        query_string={"kind": "work", "also": i["STAPLES"]}))
    assert [o["id"] for o in got["items"]] == [i["STAPLES"]] and got["items"][0]["likely"] is True


def test_asks_work_or_the_shop(client):
    j = add(client, "chq", row("NORTHWIND LTD", -60.0, when=day(1), merchant="Northwind Ltd"))
    assert client.get(f"/api/transactions/{j['NORTHWIND LTD']}/many-purchases").status_code == 400


# ── MP-03, MP-04, MP-05: one save, one Undo ─────────────────────────────

def _work(c):
    i = add(c, "amex",
            row("AIR CANADA", 112.30, "amex", when=day(9), category="Travel", kind="credit"),
            row("UBER", 14.10, "amex", when=day(8), category="Transport", kind="credit"),
            row("PAI NORTHERN THAI", 120.0, "amex", when=day(4), category="Dining", kind="credit"))
    ok(c.put(f"/api/transactions/{i['PAI NORTHERN THAI']}/split",
             json={"mode": "amount", "people": [{"name": "Sam", "amount": 60.0}]}))
    j = add(c, "chq", row("NORTHWIND LTD", -186.40, when=day(1), merchant="Northwind Ltd"))
    return i, j["NORTHWIND LTD"]


def test_mp01_all_add_up_one_tap_one_undo(client):
    i, dep = _work(client)
    before = world(client)
    parts = [{"kind": "reimbursement", "amount": 112.30, "charge": i["AIR CANADA"]},
             {"kind": "reimbursement", "amount": 14.10, "charge": i["UBER"]},
             {"kind": "reimbursement", "amount": 60.00, "charge": i["PAI NORTHERN THAI"]}]
    reply = ok(save(client, dep, parts, "Northwind"))
    assert reply["title"] == "Northwind paid back 3 · $186.40"
    # Work paid her share of Pai; Sam still owes his.
    assert owes(client, i["PAI NORTHERN THAI"]) == {"Sam": 60.0}
    undo(client, reply)
    assert world(client) == before


def test_mp03_left_over_is_answered_in_the_same_save(client):
    """MP-03: $172.30 of $186.40 ticked; "Next: the other $14.10" is S-11w,
    and its tile goes in the same request: one Undo for all of it."""
    i, dep = _work(client)
    before = world(client)
    parts = [{"kind": "reimbursement", "amount": 112.30, "charge": i["AIR CANADA"]},
             {"kind": "reimbursement", "amount": 60.00, "charge": i["PAI NORTHERN THAI"]},
             {"kind": "gift", "amount": 14.10}]
    reply = ok(save(client, dep, parts, "Northwind"))
    assert reply["title"] == "Northwind paid back 2 · $172.30"
    kinds = sorted(p["kind"] for p in client.st.parts()[dep])
    assert kinds == ["gift", "reimbursement", "reimbursement"]
    undo(client, reply)
    assert world(client) == before


def test_mp03_sort_the_rest_later_keeps_the_rest_in_needs_a_look(client):
    i, dep = _work(client)
    before = world(client)
    reply = ok(save(client, dep, [{"kind": "reimbursement", "amount": 112.30, "charge": i["AIR CANADA"]}],
                    "Northwind", later=True))
    assert reply["rest"] == 74.10
    undo(client, reply)
    assert world(client) == before


def _shop(c, measure=None):
    i = add(c, "amex",
            row("COSTCO WHOLESALE", 54.50, "amex", when=day(3), category="Groceries", kind="credit"),
            row("COSTCO GAS", 42.99, "amex", when=day(7), category="Transport", kind="credit"),
            row("COSTCO", 21.98, "amex", when=day(13), category="Groceries", kind="credit"))
    if measure is not None:
        # A refund from the shop counts as one when it lands (Pearl's
        # guess), so what moves is measured from before it came in.
        measure.update(numbers(c))
    j = add(c, "chq", row("COSTCO REFUND", -100.0, when=day(1), merchant="Costco"))
    return i, j["COSTCO REFUND"]


def test_mp04_too_much_part_pays_the_newest(client):
    """MP-04: $119.47 ticked for $100.00: the oldest in full, the newest
    (Nov 7) "$35.03 of it"."""
    was: dict = {}
    i, dep = _shop(client, was)
    before = world(client)
    rows = sorted(many(client, dep, "shop")["items"], key=lambda o: o["date"])
    assert [o["amount"] for o in rows] == [21.98, 42.99, 54.50]
    room, parts = 10000, []
    for o in rows:
        take = min(round(o["amount"] * 100), room)
        room -= take
        parts.append({"kind": "refund", "amount": take / 100, "charge": o["id"]})
    assert parts[-1]["amount"] == 35.03
    reply = ok(save(client, dep, parts, "Costco"))
    assert reply["title"] == "Costco paid back 3 · $100.00"
    assert client.st.get_transaction(i["COSTCO WHOLESALE"]).refunded == 35.03
    after = numbers(client)
    assert round(was["spent"] - after["spent"], 2) == 100.0
    undo(client, reply)
    assert world(client) == before


def test_mp03_the_shop_left_over_not_mine_in_the_same_save(client):
    """MP-03 for the shop: the rest goes to S-11m, where Not mine is a part."""
    i, dep = _shop(client)
    before = world(client)
    parts = [{"kind": "refund", "amount": 54.50, "charge": i["COSTCO WHOLESALE"]},
             {"kind": "refund", "amount": 21.98, "charge": i["COSTCO"]},
             {"kind": "not_mine", "amount": 23.52}]
    reply = ok(save(client, dep, parts, "Costco"))
    assert reply["title"] == "Costco paid back 2 · $76.48"
    undo(client, reply)
    assert world(client) == before


def test_mp03_her_share_refunded_and_part_of_sams_share(client):
    """S-11m inside the same save: her share of a split purchase refunded,
    and the rest "Part of Sam's share"."""
    i = add(client, "amex", row("COSTCO", 120.0, "amex", when=day(5), category="Groceries", kind="credit"),
            row("COSTCO GAS", 20.0, "amex", when=day(4), category="Transport", kind="credit"))
    ok(client.put(f"/api/transactions/{i['COSTCO']}/split",
                  json={"mode": "amount", "people": [{"name": "Sam", "amount": 60.0}]}))
    j = add(client, "chq", row("COSTCO REFUND", -100.0, when=day(1), merchant="Costco"))
    dep = j["COSTCO REFUND"]
    rows = {o["id"]: o for o in many(client, dep, "shop")["items"]}
    assert rows[i["COSTCO"]]["share"] is True and rows[i["COSTCO"]]["people"] == [{"name": "Sam", "owes": 60.0}]
    before = world(client)
    parts = [{"kind": "refund", "amount": 60.0, "charge": i["COSTCO"], "share": True},
             {"kind": "refund", "amount": 20.0, "charge": i["COSTCO GAS"]},
             {"kind": "refund", "amount": 20.0, "charge": i["COSTCO"], "person": "Sam"}]
    reply = ok(save(client, dep, parts, "Costco"))
    assert reply["title"] == "Costco paid back 2 · $80.00"
    assert owes(client, i["COSTCO"]) == {"Sam": 40.0}
    undo(client, reply)
    assert world(client) == before


def test_not_mine_still_needs_a_refund(client):
    i, dep = _work(client)
    r = save(client, dep, [{"kind": "reimbursement", "amount": 112.30, "charge": i["AIR CANADA"]},
                           {"kind": "not_mine", "amount": 74.10}], "Northwind")
    assert r.status_code == 400


def test_more_than_came_in_is_refused_and_nothing_saved(client):
    i, dep = _shop(client)
    before = world(client)
    r = save(client, dep, [{"kind": "refund", "amount": 54.50, "charge": i["COSTCO WHOLESALE"]},
                           {"kind": "refund", "amount": 50.00, "charge": i["COSTCO GAS"]}], "Costco")
    assert r.status_code == 400
    assert world(client) == before
