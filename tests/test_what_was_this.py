"""What was this? (2026-10-14; finance/marks.py, finance/marks_api.py): one
list of cases, applied through the same tables everything else reads, with
tags, savings accounts, refunds, reimbursements, merchant names, hidden
categories, and the list's new filters and views."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def in_month(d=1):
    return f"{MONTH}-{d:02d}"


def days_ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, description, account="chq", when=None, kind="depository",
        category=None, who=None, merchant=None, mask=""):
    raw = {"account_type": kind, "issuer_category": ""}
    if who:
        raw["counterparty"] = who
    t = Transaction(date=when or in_month(2), description=description, amount=amount,
                    account_id=account, account_name=account + (f" ••{mask}" if mask else ""),
                    raw=raw, merchant=merchant or "")
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "w.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t.fingerprint for t in st.all_transactions()}


def listing(c, **params):
    params.setdefault("month", MONTH)
    res = c.get("/api/transactions/list", query_string=params)
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def by_desc(data):
    return {r["description"]: r for r in data["transactions"]}


def mark(c, tid, **body):
    res = c.post(f"/api/transactions/{tid}/mark", json=body)
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def cases(c, tid):
    res = c.get(f"/api/transactions/{tid}/cases")
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def undo(c, payload):
    res = c.post("/api/transactions/undo", json=payload["undo"])
    assert res.status_code == 200, res.get_json()


# ── The cases ────────────────────────────────────────────────────────────

def test_money_out_offers_the_cases_and_names_what_each_does(client):
    ids = load(client.st, row(120, "SEND E-TFR ***Q7K", who="M. Papas"))
    d = cases(client, ids["SEND E-TFR ***Q7K"])
    assert d["direction"] == "out"
    keys = [c["key"] for c in d["cases"]]
    assert keys == ["spending", "bill", "shared", "moved", "saved", "lent", "paying_back",
                    "work", "not_mine"]
    saved = next(c for c in d["cases"] if c["key"] == "saved")
    # One savings bucket (2026-10-23): no account to pick.
    assert saved["needs"] is None and saved["remember"] == "destination"
    assert saved["remember_label"] == "Do this for every transfer to M. Papas from now on"
    assert saved["effect"] == "Adds to your total saved. It isn’t spending."
    assert d["current"] is None            # not sorted yet
    assert d["best"] == "saved"            # Pearl's best guess for a transfer to a person
    assert d["accounts"] == []             # no savings account to pick from yet


def test_money_in_offers_its_cases(client):
    ids = load(client.st, row(-300, "E-TRANSFER FROM SAM", who="Sam"))
    d = cases(client, ids["E-TRANSFER FROM SAM"])
    assert d["direction"] == "in"
    assert [c["key"] for c in d["cases"]] == [
        "pay", "regular_pay", "payback", "refund", "reimbursement", "own", "out_of_savings",
        "borrowed", "lent_back", "not_mine"]
    assert d["income_kinds"]["salary"] == "Salary"


def test_a_purchase_with_a_rule_for_the_merchant(client):
    ids = load(client.st, row(14.5, "SQ *ROASTED NUT", account="card", kind="credit",
                              merchant="Roasted Nut"),
               row(9.0, "SQ *ROASTED NUT", account="card", kind="credit",
                   merchant="Roasted Nut", when=in_month(5)))
    tid = ids["SQ *ROASTED NUT"]
    res = mark(client, tid, case="spending", category="Coffee", remember=True)
    assert res["title"] == "Moved to Coffee." and res["remember"]
    rows = list(by_desc(listing(client)).values())
    assert {r["category"] for r in rows} == {"Coffee"}
    assert all(r["ruled"] for r in rows)                 # the chip can say so
    assert client.st.overrides() == {"roasted nut": "Coffee"}
    undo(client, res)
    assert client.st.overrides() == {}


def test_savings_is_one_bucket_with_no_account_to_pick(client):
    """2026-10-23: put into savings adds to her total saved, taken out comes
    off it; which account is never asked, and none is named."""
    ids = load(client.st, row(500, "TFR-TO 12343333"), row(-120, "TFR-FR 12343333", when=in_month(6)))
    tid, back = ids["TFR-TO 12343333"], ids["TFR-FR 12343333"]
    r = client.post("/api/accounts/manual", json={"name": "Wealthsimple TFSA", "kind": "investment",
                                                  "balance": 1000, "last4": "3333"})
    aid = r.get_json()["account"]["id"]
    client.st.set_saved_to(tid, aid)           # an answer from before: no longer named
    res = mark(client, tid, case="saved", account=aid)
    assert res["title"] == "Put into savings."
    listed = by_desc(listing(client))["TFR-TO 12343333"]
    assert listed["category"] == "Saved" and listed["saved_to"] is None and listed["saved_to_label"] == ""
    assert listed["note"] == "Saved · adds to your total saved"
    assert client.st.saved_to() == {}
    assert client.get("/api/home").get_json()["savings"]["put_away"]["contributions"] == 500.0
    out = mark(client, back, case="out_of_savings")
    assert out["title"] == "Taken out of savings."
    assert by_desc(listing(client))["TFR-FR 12343333"]["note"] == "Taken out of savings · comes off your total saved"
    d = cases(client, back)
    assert next(c for c in d["cases"] if c["key"] == "out_of_savings")["needs"] is None
    # Undo puts the old answer back as it was.
    undo(client, res)
    assert client.st.saved_to() == {tid: aid}


def test_a_linked_investment_account_is_offered_too(client):
    client.st.note_account("inv1", name="RRSP ••4444", item_id="it", account_type="investment",
                           subtype="rrsp")
    client.st.set_account_setting("inv1", nickname="My RRSP")
    ids = load(client.st, row(200, "TRANSFER TO 4444"))
    d = cases(client, ids["TRANSFER TO 4444"])
    assert d["accounts"] == [{"id": "inv1", "label": "My RRSP", "kind": "investment",
                              "source": "linked", "anchor": False, "sub": "Investment"}]


def test_moved_remembers_the_destination(client):
    ids = load(client.st, row(80, "SEND E-TFR ***ABC", who="Landlord Co"))
    res = mark(client, ids["SEND E-TFR ***ABC"], case="moved", remember=True)
    assert res["remember"] and client.st.destinations() == {"to:landlord co": "Transfers"}
    assert by_desc(listing(client))["SEND E-TFR ***ABC"]["chip"]["label"] == "Transfer"


def test_a_bill_counts_as_spending_and_as_one_of_her_bills(client):
    ids = load(client.st, row(85, "ROGERS", account="card", kind="credit", merchant="Rogers"))
    res = mark(client, ids["ROGERS"], case="bill", category="Phone & Internet")
    assert res["title"] == "Counted as a bill, in Phone & Internet."
    bills = client.get("/api/income-bills").get_json()["bills"]
    assert any(b["name"] == "Rogers" and b["ticked"] for b in bills)
    assert by_desc(listing(client))["ROGERS"]["kind"] == "fixed"


def test_lent_borrowed_and_paying_back(client):
    ids = load(client.st, row(200, "SEND E-TFR SAM", who="Sam"),
               row(-150, "E-TFR FROM ALEX", who="Alex", when=in_month(3)),
               row(150, "SEND E-TFR ALEX", who="Alex", when=in_month(9)))
    mark(client, ids["SEND E-TFR SAM"], case="lent")
    mark(client, ids["E-TFR FROM ALEX"], case="borrowed")
    res = mark(client, ids["SEND E-TFR ALEX"], case="paying_back")
    assert res["title"] == "Sorted as paying back what you borrowed."
    rows = by_desc(listing(client))
    assert rows["SEND E-TFR SAM"]["note"] == "Lent · not counted as spending"
    assert rows["E-TFR FROM ALEX"]["note"] == "Borrowed · not income"
    assert rows["SEND E-TFR ALEX"]["note"] == "Paid back what you borrowed · not counted as spending"
    assert listing(client)["totals"] == {"spent": 0, "income": 0, "not_counted": 500, "count": 3}
    # Paying back something that was never in Pearl is spending.
    res = mark(client, ids["SEND E-TFR ALEX"], case="paying_back", counted=False,
               category="Shopping")
    assert by_desc(listing(client))["SEND E-TFR ALEX"]["category"] == "Shopping"


def test_a_work_expense_and_its_reimbursement_both_vanish(client):
    ids = load(client.st, row(240, "AIR CANADA", account="card", kind="credit",
                              merchant="Air Canada", when=in_month(2)),
               row(-240, "PAYROLL EXPENSES", when=in_month(9)))
    flight, back = ids["AIR CANADA"], ids["PAYROLL EXPENSES"]
    res = mark(client, flight, case="work")
    assert res["title"] == "Left out until it’s reimbursed."
    assert listing(client)["totals"]["spent"] == 0
    left = by_desc(listing(client, excluded=1))["AIR CANADA"]
    assert left["note"] == "Left out · Work expense · waiting to be reimbursed"
    assert cases(client, flight)["current"] == "work"
    # The deposit's reimbursement case offers the flight first.
    d = cases(client, back)
    cand = next(c for c in d["cases"] if c["key"] == "reimbursement")["candidates"]
    assert cand[0]["id"] == flight and cand[0]["work"] and cand[0]["exact"]
    res = mark(client, back, case="reimbursement", charge=flight)
    assert res["title"] == "Reimbursement for Air Canada. Both are out of your numbers."
    rows = by_desc(listing(client))
    assert rows["PAYROLL EXPENSES"]["chip"]["label"] == "Reimbursement"
    assert rows["PAYROLL EXPENSES"]["note"] == "Reimbursed you for Air Canada · not income"
    assert rows["PAYROLL EXPENSES"]["reimbursement"] is True
    assert rows["AIR CANADA"]["note"] == "Reimbursed · not your spending"
    assert rows["AIR CANADA"]["counts"] == "none" and rows["AIR CANADA"]["excluded"] == ""
    assert listing(client)["totals"]["spent"] == 0 and listing(client)["totals"]["income"] == 0
    assert cases(client, back)["current"] == "reimbursement"
    undo(client, res)
    rows = by_desc(listing(client, excluded=1))
    assert rows["AIR CANADA"]["note"].startswith("Left out · Work expense")
    assert client.st.payback_kinds() == {}


def test_a_refund_nets_in_the_purchases_category(client):
    ids = load(client.st, row(89, "LULULEMON", account="card", kind="credit",
                              merchant="Lululemon", category="Shopping", when=in_month(3)),
               row(-89, "LULULEMON", account="card", kind="credit", merchant="Lululemon",
                   when=in_month(8)))
    buy = ids["LULULEMON"]
    back = next(t.fingerprint for t in client.st.all_transactions() if t.amount < 0)
    d = cases(client, back)
    cand = next(c for c in d["cases"] if c["key"] == "refund")["candidates"]
    assert cand[0]["id"] == buy and cand[0]["exact"]
    res = mark(client, back, case="refund", charge=buy)
    assert res["title"] == "Refund of Lululemon. Comes off Shopping."
    data = listing(client)
    r = next(x for x in data["transactions"] if x["id"] == back)
    # Linked, it comes off the purchase and doesn't count again (2026-10-24).
    assert r["category"] == "Shopping" and r["counts"] == "none" and r["chip"]["label"] == "Refund"
    assert r["note"] == "Refund of Lululemon · came off it"
    p_ = next(x for x in data["transactions"] if x["id"] == buy)
    assert p_["amount"] == 0 and p_["counts"] == "none"
    assert r["refund_of"]["id"] == buy
    assert data["totals"]["spent"] == 0 and data["totals"]["income"] == 0
    # The purchase says so too (2026-10-23), in its row and its panel.
    p = next(x for x in data["transactions"] if x["id"] == buy)
    day = int(in_month(8)[8:10])
    assert p["note"] == f"Refunded in full on {p['note'].split(' on ')[1]}" and p["note"].endswith(f" {day}")
    assert [r["id"] for r in p["refunded_by"]] == [back] and p["refunded_by"][0]["amount"] == 89
    assert r["refunded_by"] == []
    detail = client.get(f"/api/transactions/{buy}").get_json()
    assert [x["id"] for x in detail["refunded_by"]] == [back]
    assert cases(client, back)["current"] == "refund"
    # Without a purchase to point at, a category is enough.
    res = mark(client, back, case="refund", category="Groceries")
    assert res["title"] == "Refund. Comes off Groceries."
    p = next(x for x in listing(client)["transactions"] if x["id"] == buy)
    assert p["refunded_by"] == [] and "efund" not in p["note"]


def test_a_partial_refund_says_how_much_came_back(client):
    ids = load(client.st, row(120, "ZARA", account="card", kind="credit", merchant="Zara",
                              category="Shopping", when=in_month(3)),
               row(-40, "ZARA RETURN", account="card", kind="credit", merchant="Zara",
                   when=in_month(9)))
    mark(client, ids["ZARA RETURN"], case="refund", charge=ids["ZARA"])
    p = next(x for x in listing(client)["transactions"] if x["id"] == ids["ZARA"])
    assert p["note"].startswith("$40.00 refunded on ")
    assert p["refunded_by"][0]["amount"] == 40


def test_someone_paying_me_back_links_to_the_charge(client):
    ids = load(client.st, row(80, "SUSHI NAMI", account="card", kind="credit",
                              merchant="Sushi Nami", category="Dining", when=in_month(2)),
               row(-20, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)))
    dinner, back = ids["SUSHI NAMI"], ids["E-TRANSFER FROM PRIYA"]
    cand = next(c for c in cases(client, back)["cases"] if c["key"] == "payback")["candidates"]
    assert cand[0]["id"] == dinner and cand[0]["share"] == 4
    res = mark(client, back, case="payback", charge=dinner, person="Priya")
    assert res["title"] == "Sushi Nami is now split with Priya."
    assert res["detail"] == "Their $20.00 comes off what you spent, so your share is $60.00. Not income."
    rows = by_desc(listing(client))
    assert rows["SUSHI NAMI"]["amount"] == 60 and rows["E-TRANSFER FROM PRIYA"]["chip"]["label"] == "Repayment"
    assert cases(client, back)["current"] == "payback"


def test_pay_sets_the_kind_and_makes_it_income(client):
    ids = load(client.st, row(-2000, "DEPOSIT NORTHWIND"))
    res = mark(client, ids["DEPOSIT NORTHWIND"], case="pay", income_kind="salary")
    assert res["title"] == "Counted as income: Salary."
    assert listing(client)["totals"]["income"] == 2000
    assert cases(client, ids["DEPOSIT NORTHWIND"])["income_kind"] == "salary"


def test_not_mine_leaves_it_out_with_a_rule_if_asked(client):
    ids = load(client.st, row(45, "NETFLIX", account="card", kind="credit", merchant="Netflix"))
    res = mark(client, ids["NETFLIX"], case="not_mine", reason="My sister’s", remember=True)
    assert res["title"] == "Left out."
    assert listing(client)["transactions"] == []
    assert by_desc(listing(client, excluded=1))["NETFLIX"]["note"] == "Left out · My sister’s"
    rules = client.get("/api/rules").get_json()["rules"]
    assert any(r["kind"] == "exclusion" and r["name"] == "Netflix" for r in rules)
    undo(client, res)
    assert by_desc(listing(client))["NETFLIX"]["counts"] == "spending"


def test_on_a_joint_account_not_mine_is_theirs(client):
    ids = load(client.st, row(60, "COSTCO", account="fam", category="Groceries"))
    client.put("/api/accounts/fam/joint", json={"label": "Alex"})
    d = cases(client, ids["COSTCO"])
    nm = next(c for c in d["cases"] if c["key"] == "not_mine")
    assert nm["label"] == "Alex’s, not mine" and nm["needs"] is None
    assert "shared" not in {c["key"] for c in d["cases"]}
    res = mark(client, ids["COSTCO"], case="not_mine")
    assert res["title"] == "Counted as Alex’s."
    assert listing(client)["transactions"] == []
    undo(client, res)
    assert listing(client)["totals"]["spent"] == 60


def test_someone_else_put_this_into_a_joint_account(client):
    ids = load(client.st, row(-200, "E-TRANSFER FROM ALEX", account="fam", category="Transfers"))
    client.put("/api/accounts/fam/joint", json={"label": "Alex"})
    client.put("/api/accounts/fam/settings", json={"joint_people": ["Alex", "Jo"]})
    d = cases(client, ids["E-TRANSFER FROM ALEX"])
    assert d["joint_people"] == ["Alex", "Jo"]
    assert any(c["key"] == "joint_them" for c in d["cases"])
    res = mark(client, ids["E-TRANSFER FROM ALEX"], case="joint_them", person="Jo", remember=True)
    assert res["title"] == "Jo put this in."
    r = listing(client, joint=1)["transactions"][0]
    assert r["chip"]["label"] == "Joint added"


def test_part_of_it_was_put_away(client):
    ids = load(client.st, row(500, "TFR-TO 9999", category="Shopping"))
    res = mark(client, ids["TFR-TO 9999"], case="saved_part", amount=300)
    assert res["title"] == "$300.00 of it put away."
    r = by_desc(listing(client))["TFR-TO 9999"]
    assert r["amount"] == 200 and r["counts"] == "spending"
    assert client.get("/api/home").get_json()["savings"]["put_away"]["contributions"] == 300.0
    assert client.post(f"/api/transactions/{ids['TFR-TO 9999']}/mark",
                       json={"case": "saved_part", "amount": 500}).status_code == 400


def test_the_preview_says_what_it_would_do_without_writing(client):
    ids = load(client.st, row(120, "SEND E-TFR ***Q7K", who="M. Papas"))
    tid = ids["SEND E-TFR ***Q7K"]
    r = client.post(f"/api/transactions/{tid}/mark?dry=1", json={"case": "saved"}).get_json()
    assert "line" in r and r["line"]
    r = client.post(f"/api/transactions/{tid}/mark?dry=1", json={"case": "lent"}).get_json()
    assert r["line"]
    assert by_desc(listing(client))["SEND E-TFR ***Q7K"]["category"] == "Unsorted transfers"
    assert client.post(f"/api/transactions/{tid}/mark", json={"case": "pay"}).status_code == 400
    assert client.post(f"/api/transactions/{tid}/mark", json={"case": "shared"}).status_code == 400


def test_a_selection_answers_at_once_with_one_undo(client):
    ids = load(client.st, row(50, "SEND E-TFR A", who="A"), row(60, "SEND E-TFR B", who="B"),
               row(70, "SEND E-TFR C", who="C"))
    res = client.post("/api/transactions/batch/mark",
                      json={"ids": list(ids.values()), "case": "moved"}).get_json()
    assert res["updated"] == 3 and res["title"] == "Marked 3 as Moved between my accounts."
    assert listing(client)["totals"]["spent"] == 0
    undo(client, res)
    assert listing(client)["totals"]["spent"] == 180
    res = client.post("/api/transactions/batch/mark",
                      json={"ids": list(ids.values())[:2], "case": "spending",
                            "category": "Gifts & Charity"}).get_json()
    assert res["title"] == "Marked 2 as Gifts & Charity."
    assert client.post("/api/transactions/batch/mark",
                       json={"ids": list(ids.values()), "case": "refund"}).status_code == 400


# ── Tags ─────────────────────────────────────────────────────────────────

def test_tags_group_rows_without_moving_them(client):
    ids = load(client.st, row(900, "FLIGHTS", account="card", kind="credit", category="Travel",
                              when=in_month(1)),
               row(40, "TAPAS", account="card", kind="credit", category="Dining", when=in_month(3)),
               row(30, "LOBLAWS", account="card", kind="credit", category="Groceries",
                   when=in_month(4)))
    r = client.put(f"/api/transactions/{ids['FLIGHTS']}/tags", json={"tags": ["Ibiza", " ibiza ", "Work"]})
    assert r.status_code == 200 and r.get_json()["tags"] == ["Ibiza", "Work"]
    r = client.post("/api/transactions/batch/tags",
                    json={"ids": [ids["TAPAS"]], "add": ["Ibiza"]}).get_json()
    assert r["title"] == "Tagged Ibiza."
    data = listing(client, tag="Ibiza")
    assert {x["description"] for x in data["transactions"]} == {"FLIGHTS", "TAPAS"}
    assert data["focus"] == {"label": "Ibiza", "kind": "spending", "total": 940, "usual": None} \
        or data["focus"]["total"] == 940
    assert data["tags"] == ["Ibiza", "Work"]
    assert by_desc(listing(client))["FLIGHTS"]["tags"] == ["Ibiza", "Work"]
    tags = client.get("/api/tags").get_json()["tags"]
    assert tags[0] == {"tag": "Ibiza", "count": 2, "spent": 940, "first": in_month(1),
                       "last": in_month(3)}
    # Across every month, with a tag, the total is the tag's whole total.
    assert listing(client, month="all", tag="Ibiza")["focus"]["usual"] is None
    # Rename, then take it off.
    assert client.put("/api/tags/Ibiza", json={"name": "Spain"}).get_json()["rows"] == 2
    assert listing(client, tag="Spain")["total"] == 2
    assert client.put("/api/tags/Spain", json={"name": None}).get_json()["rows"] == 2
    assert listing(client)["tags"] == ["Work"]
    assert client.put("/api/tags/Nope", json={"name": "x"}).status_code == 404
    # Undo of a batch tag.
    undo(client, r)
    assert by_desc(listing(client))["TAPAS"]["tags"] == []


# ── Views and filters ────────────────────────────────────────────────────

def test_by_merchant_and_by_category_views(client):
    load(client.st, row(12, "COFFEE A", account="card", kind="credit", category="Coffee",
                        merchant="Pilot", when=in_month(1)),
         row(8, "COFFEE B", account="card", kind="credit", category="Coffee", merchant="Pilot",
             when=in_month(2)),
         row(60, "LOBLAWS", account="card", kind="credit", category="Groceries",
             merchant="Loblaws", when=in_month(3)),
         row(-2000, "PAYROLL", category="Income", when=in_month(1)))
    data = listing(client, by="merchant")
    assert data["transactions"] == [] and data["total"] == 4
    assert [(m["name"], m["count"], m["spent"]) for m in data["groups_of"]][:2] == [
        ("Loblaws", 1, 60), ("Pilot", 2, 20)]
    assert data["groups_of"][2]["income"] == 2000
    cats = listing(client, by="category")["groups_of"]
    assert [(c["name"], c["spent"]) for c in cats][:2] == [("Groceries", 60), ("Coffee", 20)]
    assert listing(client, merchant="pilot")["total"] == 2
    assert listing(client, merchant="Pilot")["focus"]["total"] == 20
    assert client.get("/api/transactions/list?by=x").status_code == 400


def test_counts_amount_pending_and_needs_a_look_filters(client):
    ids = load(client.st, row(12, "ZXQ WIDGETS", account="card", kind="credit", merchant="Zxq",
                              when=in_month(1)),
               row(250, "IKEA", account="card", kind="credit", category="Home", when=in_month(2)),
               row(-2000, "PAYROLL", category="Income", when=in_month(1)),
               row(300, "VISA PAYMENT", category="Transfers", when=in_month(3)))
    assert listing(client, counts="income")["total"] == 1
    assert listing(client, counts="none")["total"] == 1
    assert listing(client, amount_min=100, amount_max=500)["total"] == 2
    assert listing(client, amount_max=20)["total"] == 1
    assert listing(client, look=1)["total"] == 1            # only the row filed as Other
    assert listing(client, pending=1)["total"] == 0
    assert client.get("/api/transactions/list?counts=x").status_code == 400
    assert listing(client, month="all")["total"] == 4


def test_a_merchant_nickname_shows_everywhere_the_merchant_is_named(client):
    ids = load(client.st, row(14.5, "SQ *THE ROASTED NUT", account="card", kind="credit",
                              merchant="Roasted Nut", category="Coffee"))
    r = client.put("/api/merchants/name", json={"merchant": "Roasted Nut", "name": "The Nut"})
    assert r.status_code == 200
    row_ = by_desc(listing(client))["SQ *THE ROASTED NUT"]
    assert row_["merchant"] == "The Nut" and row_["bank_merchant"] == "Roasted Nut"
    rules = client.get("/api/rules").get_json()
    assert rules["names"] == [{"merchant": "Roasted Nut", "key": "roasted nut", "name": "The Nut"}]
    assert client.delete("/api/rules/name:roasted nut").status_code == 200
    assert by_desc(listing(client))["SQ *THE ROASTED NUT"]["merchant"] == "Roasted Nut"


def test_hidden_categories_leave_the_pickers_but_not_the_rows(client):
    load(client.st, row(20, "PETS R US", account="card", kind="credit", category="Pets"))
    r = client.put("/api/rules/categories", json={"category": "Pets", "hidden": True})
    assert r.status_code == 200 and r.get_json()["hidden"] == ["Pets"]
    cats = client.get("/api/categories").get_json()
    assert cats["hidden"] == ["Pets"]
    assert next(c for c in cats["categories"] if c["name"] == "Pets")["hidden"] is True
    assert by_desc(listing(client))["PETS R US"]["category"] == "Pets"
    assert client.put("/api/rules/categories", json={"category": "Income", "hidden": True}).status_code == 400
    client.put("/api/rules/categories", json={"category": "Pets", "hidden": False})
    assert client.get("/api/categories").get_json()["hidden"] == []


def test_start_over_clears_the_answers_too(client):
    ids = load(client.st, row(500, "TFR-TO 3333"))
    client.put(f"/api/transactions/{ids['TFR-TO 3333']}/tags", json={"tags": ["x"]})
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert client.st.tags() == {} and client.st.saved_to() == {}


def _guess(amount, description, merchant, when):
    t = row(amount, description, account="card", kind="credit", merchant=merchant, when=when)
    t.raw["category_confidence"] = "LOW"
    t.raw["issuer_category"] = "GENERAL_MERCHANDISE_OTHER"
    return t


def test_a_rule_is_for_its_merchant_name_only(client):
    """2026-10-24 (Maria): a rule for "Lyft" sorts Lyft only. "Lyft Ride Tue
    6PM" and other names that start the same stay Pearl's own guess, and
    still wait in Needs a look."""
    from finance.review import for_store, ids_in
    ids = load(client.st,
               _guess(18, "LYFT", "Lyft", in_month(2)),
               _guess(11, "LYFT", "Lyft", in_month(3)),
               _guess(21, "LYFT *RIDE TUE 6PM", "Lyft Ride Tue 6PM", in_month(4)),
               _guess(12, "LYFTOPIA", "Lyftopia", in_month(7)))
    mark(client, ids["LYFT"], case="spending", category="Transport", remember=True)
    by = {}
    for t in client.st.all_transactions():
        by.setdefault(t.description, []).append(t)
    assert all(t.category == "Transport" for t in by["LYFT"])
    assert by["LYFT *RIDE TUE 6PM"][0].category != "Transport"
    assert by["LYFTOPIA"][0].category != "Transport"
    assert ids["LYFT *RIDE TUE 6PM"] in ids_in(for_store(client.st))


def test_apply_to_all_and_editing_the_rule_stay_on_one_name(client):
    ids = load(client.st,
               _guess(18, "UBER EATS", "Uber Eats", in_month(2)),
               _guess(21, "UBER* EATS PENDING", "Uber Eats Pending", in_month(4)))
    eats = ids["UBER EATS"]
    pre = client.post(f"/api/transactions/{eats}/category/preview",
                      json={"category": "Dining", "apply_to_merchant": True}).get_json()
    assert pre["merchant_count"] == 1
    client.patch(f"/api/transactions/{eats}", json={"category": "Dining", "apply_to_merchant": True})
    assert client.put("/api/rules/merchant:uber eats", json={"category": "Groceries"}).status_code == 200
    by = {t.description: t.category for t in client.st.all_transactions()}
    assert by["UBER EATS"] == "Groceries" and by["UBER* EATS PENDING"] not in ("Dining", "Groceries")


def test_a_new_row_under_another_spelling_is_not_ruled(client):
    ids = load(client.st, _guess(18, "LYFT", "Lyft", in_month(2)))
    mark(client, ids["LYFT"], case="spending", category="Transport", remember=True)
    load(client.st, _guess(25, "LYFT *RIDE THU 9PM", "Lyft Ride Thu 9PM", in_month(9)),
         _guess(14, "LYFT", "Lyft", in_month(10)))
    by = {(t.description, t.date): t for t in client.st.all_transactions()}
    ride = next(t for (d, _), t in by.items() if d == "LYFT *RIDE THU 9PM")
    assert ride.category_source != "merchant_override"
    assert all(t.category == "Transport" for (d, _), t in by.items() if d == "LYFT")


def test_undo_puts_every_quick_answer_back_in_needs_a_look(client):
    """2026-10-23: "Yes, Groceries", an income type, who put a joint deposit
    in, and a payback link all came back with no Undo, so Undo on the
    Sorted card left the card instead of asking again."""
    from finance.review import for_store, ids_in

    def asked(tid):
        return tid in ids_in(for_store(client.st))

    t = row(23.5, "QWX MARKET", account="card", kind="credit", merchant="Qwx Market")
    t.raw["category_confidence"] = "LOW"
    t.raw["issuer_category"] = "FOOD_AND_DRINK_GROCERIES"
    ids = load(client.st, t, row(-412.5, "DEPOSIT NORTHWIND"),
               row(80, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami", category="Dining"),
               row(-20, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)),
               row(-500, "E-TRANSFER FROM ALEX KIM", account="joint", who="Alex Kim", when=in_month(6)))
    client.st.set_joint("joint", "Alex")
    client.st.set_joint_people("joint", ["Alex"])
    cat, pay, dinner, back, joint = (ids["QWX MARKET"], ids["DEPOSIT NORTHWIND"], ids["SUSHI NAMI"],
                                     ids["E-TRANSFER FROM PRIYA"], ids["E-TRANSFER FROM ALEX KIM"])
    client.st.set_transaction_category(pay, "Income")
    client.st.set_income_type(pay, "other", "rule")

    for tid, call in [
        (cat, lambda: client.put(f"/api/transactions/{cat}/confirm")),
        (pay, lambda: client.put(f"/api/transactions/{pay}/income-type", json={"kind": "salary"})),
        (joint, lambda: client.put(f"/api/transactions/{joint}/joint-from", json={"who": "me"})),
        (back, lambda: client.post(f"/api/transactions/{dinner}/paybacks/{back}", json={})),
    ]:
        assert asked(tid), tid
        res = call()
        assert res.status_code == 200, res.get_json()
        assert not asked(tid), tid
        u = res.get_json()["undo"]
        assert u, tid
        assert client.post("/api/transactions/undo", json=u).status_code == 200
        assert asked(tid), tid


def test_a_rule_for_a_name_every_etransfer_shares_is_never_made_or_used(client):
    """2026-10-23: TD sends every e-Transfer as "Interac e-Transfer". Remember
    on one put into savings made a rule for that name, and her sister's
    deposit into their joint account came up Saved · taken out of savings."""
    from finance.categorize import is_generic_transfer_name
    for name in ("Interac e-Transfer", "E-transfer", "Send E-tfr Q7K", "E-transfer K2P",
                 "Internet Transfer", "Mobile Deposit"):
        assert is_generic_transfer_name(name), name
    for name in ("E-transfer From Elena", "Lyft", "Wealthsimple Invest", "Landlord Co", "Transfer Wise"):
        assert not is_generic_transfer_name(name), name

    client.st.set_joint("joint", "Elena")
    client.st.set_joint_people("joint", ["Elena"])
    client.st.set_joint_share("joint", 50)
    out = row(200, "E-TRANSFER", merchant="Interac e-Transfer", when=in_month(3))
    dep = row(-250, "E-TRANSFER", account="joint", merchant="Interac e-Transfer", when=in_month(9))
    load(client.st, out, dep)
    oid = next(t.fingerprint for t in client.st.all_transactions() if t.amount > 0)
    did = next(t.fingerprint for t in client.st.all_transactions() if t.amount < 0)
    d = cases(client, oid)
    assert d["learnable"] is False
    assert next(c for c in d["cases"] if c["key"] == "saved")["remember"] is None
    res = mark(client, oid, case="saved", remember=True)
    assert res["remember"] is False and client.st.overrides() == {}
    assert client.st.get_transaction(oid).category == "Saved"            # this one, as she said
    assert client.st.get_transaction(did).category != "Saved"            # not her sister's deposit
    # A rule like that from before is ignored, and the deposit is asked about.
    client.st.set_joint_share("joint", None)
    client.st.set_joint("joint", "Elena")
    with client.st.conn() as c:
        c.execute("INSERT INTO merchant_overrides (merchant_key, category) VALUES (?, ?)",
                  ("interac e-transfer", "Saved"))
    from finance.pipeline import recategorize_all
    recategorize_all(client.st)
    assert client.st.get_transaction(did).category != "Saved"
    from finance.review import for_store
    assert any(i["txn"]["id"] == did for i in for_store(client.st)["joint_in"])


def test_a_named_merchant_rule_still_works_and_skips_joint_deposits(client):
    client.st.set_joint("joint", "Elena")
    ids = load(client.st, row(14.5, "SQ *ROASTED NUT", account="card", kind="credit", merchant="Roasted Nut"),
               row(-40, "ROASTED NUT", account="joint", merchant="Roasted Nut", when=in_month(6)))
    mark(client, ids["SQ *ROASTED NUT"], case="spending", category="Coffee", remember=True)
    assert client.st.overrides() == {"roasted nut": "Coffee"}
    joint = next(t for t in client.st.all_transactions() if t.account_id == "joint")
    assert joint.category_source != "merchant_override"          # straight away, too
    from finance.pipeline import recategorize_all
    recategorize_all(client.st)
    joint = next(t for t in client.st.all_transactions() if t.account_id == "joint")
    assert joint.category_source != "merchant_override"


def test_a_split_from_the_sort_card_settles_it_and_undoes(client):
    """2026-10-23: Split with others, from Needs a look or Quick sort, is an
    answer: the category is settled, it leaves Needs a look, and Undo puts
    the split, the share and the category back."""
    from finance.review import for_store, ids_in
    t = row(80, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami")
    t.raw["category_confidence"] = "LOW"
    t.raw["issuer_category"] = "FOOD_AND_DRINK_RESTAURANT"
    ids = load(client.st, t, row(120, "INTERNET TRANSFER 000123 TO 4444", when=in_month(5)))
    sushi, tfr = ids["SUSHI NAMI"], ids["INTERNET TRANSFER 000123 TO 4444"]
    assert {sushi, tfr} <= ids_in(for_store(client.st))
    body = {"mode": "even", "people": [{"name": "Priya", "amount": 40}], "watch": True, "settle": True}
    res = client.put(f"/api/transactions/{sushi}/split", json=body)
    assert res.status_code == 200, res.get_json()
    got = client.st.get_transaction(sushi)
    assert got.category_source == "user" and got.my_share == 40
    assert sushi not in ids_in(for_store(client.st))
    assert client.post("/api/transactions/undo", json=res.get_json()["undo"]).status_code == 200
    back = client.st.get_transaction(sushi)
    assert back.category_source != "user" and not client.st.splits().get(sushi) and not back.share_set
    assert sushi in ids_in(for_store(client.st))
    # An unsorted transfer gets the category she picked.
    res = client.put(f"/api/transactions/{tfr}/split", json={**body, "people": [{"name": "Sam", "amount": 60}],
                                                            "category": "Dining"})
    assert client.st.get_transaction(tfr).category == "Dining"
    assert tfr not in ids_in(for_store(client.st))


def test_both_people_in_a_split_show_paid_back(client):
    """2026-10-24: a split with two people, each paying back by e-Transfer.
    One bank leaves the sender off, and one name is "Sam Lee" for the Sam in
    the split: both still show Paid back."""
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(-30, "E-TRANSFER ***K2P", when=in_month(4)),
               row(-30, "E-TRANSFER FROM SAM LEE", who="Sam Lee", when=in_month(5)))
    sushi = ids["SUSHI NAMI"]
    client.put(f"/api/transactions/{sushi}/split",
               json={"mode": "even", "people": [{"name": "Priya", "amount": 30}, {"name": "Sam", "amount": 30}],
                     "watch": True})
    mark(client, ids["E-TRANSFER ***K2P"], case="payback", charge=sushi)                       # no name at all
    mark(client, ids["E-TRANSFER FROM SAM LEE"], case="payback", charge=sushi, person="Sam Lee")
    people = {p["name"]: p for p in client.get(f"/api/transactions/{sushi}").get_json()["splitting"]["people"]}
    assert people["Sam"]["owes"] == 0 and people["Sam"]["paid_on"]
    assert people["Priya"]["owes"] == 0 and people["Priya"]["paid_on"]
    row_ = next(r for r in listing(client)["transactions"] if r["id"] == sushi)
    assert row_["note"] == "Your share of $90.00 · Priya, Sam paid you back"


def test_link_unlink_and_relink_net_every_time(client):
    """2026-10-24: a payback, a reimbursement and a refund can each be linked,
    unlinked and linked again, and the purchase nets every time."""
    ids = load(client.st,
               row(80, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami", category="Dining", when=in_month(2)),
               row(-20, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)),
               row(400, "AIR CANADA", account="card", kind="credit", merchant="Air Canada", category="Travel", when=in_month(3)),
               row(-400, "DEPOSIT EMPLOYER EXPENSES", when=in_month(5)),
               row(120, "ZARA", account="card", kind="credit", merchant="Zara", category="Shopping", when=in_month(3)),
               row(-40, "ZARA RETURN", account="card", kind="credit", merchant="Zara", when=in_month(7)))

    def amount(key):
        return next(r for r in listing(client)["transactions"] if r["id"] == ids[key])["amount"]

    spent = listing(client)["totals"]["spent"]
    for _ in range(3):
        mark(client, ids["E-TRANSFER FROM PRIYA"], case="payback", charge=ids["SUSHI NAMI"], person="Priya")
        mark(client, ids["DEPOSIT EMPLOYER EXPENSES"], case="reimbursement", charge=ids["AIR CANADA"])
        mark(client, ids["ZARA RETURN"], case="refund", charge=ids["ZARA"])
        assert (amount("SUSHI NAMI"), amount("AIR CANADA"), amount("ZARA")) == (60, 0, 80)
        assert client.delete(f"/api/transactions/{ids['SUSHI NAMI']}/paybacks/{ids['E-TRANSFER FROM PRIYA']}").status_code == 200
        assert client.delete(f"/api/transactions/{ids['AIR CANADA']}/paybacks/{ids['DEPOSIT EMPLOYER EXPENSES']}").status_code == 200
        assert client.delete(f"/api/transactions/{ids['ZARA RETURN']}/refund").status_code == 200
        assert (amount("SUSHI NAMI"), amount("AIR CANADA"), amount("ZARA")) == (80, 400, 120)
    assert client.st.refunds() == {} and not any(t.repays for t in client.st.all_transactions())
    # The split Priya's payback made goes with it each time (THL-260).
    assert client.st.splits() == {} and not client.st.get_transaction(ids["SUSHI NAMI"]).share_set
    # The month's spending ends where it started.
    assert listing(client)["totals"]["spent"] == spent


def _split_people(client, tid):
    data = client.get(f"/api/transactions/{tid}").get_json()
    return {p["name"]: p for p in (data.get("splitting") or {}).get("people", [])}


def test_a_payback_to_an_unsplit_purchase_makes_the_split(client):
    """THL-260: Paid back → a purchase that was never split. The purchase
    becomes a split with whoever sent it, paid back, and one Undo takes back
    both the link and the split."""
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(-30, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)),
               row(-30, "E-TRANSFER FROM SAM LEE", who="Sam Lee", when=in_month(5)))
    sushi = ids["SUSHI NAMI"]
    res = mark(client, ids["E-TRANSFER FROM PRIYA"], case="payback", charge=sushi, person="Priya")
    assert res["title"] == "Sushi Nami is now split with Priya."
    split = client.st.splits()[sushi]
    assert split["people"] == [{"name": "Priya", "amount": 30.0}]
    assert client.st.get_transaction(sushi).my_share == 60
    people = _split_people(client, sushi)
    assert people["Priya"]["owes"] == 0 and people["Priya"]["paid_on"]
    # A second friend joins the same split.
    mark(client, ids["E-TRANSFER FROM SAM LEE"], case="payback", charge=sushi, person="Sam Lee")
    assert [p["name"] for p in client.st.splits()[sushi]["people"]] == ["Priya", "Sam Lee"]
    assert next(r for r in listing(client)["transactions"] if r["id"] == sushi)["amount"] == 30
    # Unlinking Sam takes only Sam out.
    assert client.delete(f"/api/transactions/{sushi}/paybacks/{ids['E-TRANSFER FROM SAM LEE']}").status_code == 200
    assert [p["name"] for p in client.st.splits()[sushi]["people"]] == ["Priya"]
    assert client.st.get_transaction(sushi).my_share == 60


def test_one_undo_takes_back_the_link_and_the_split(client):
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(-30, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)))
    sushi = ids["SUSHI NAMI"]
    res = mark(client, ids["E-TRANSFER FROM PRIYA"], case="payback", charge=sushi, person="Priya")
    undo(client, res)
    t = client.st.get_transaction(sushi)
    assert client.st.splits() == {} and not t.share_set and not t.paid_back
    assert not client.st.get_transaction(ids["E-TRANSFER FROM PRIYA"]).repays


def test_a_payback_with_no_name_still_just_nets(client):
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(-30, "E-TRANSFER ***K2P", when=in_month(4)))
    sushi = ids["SUSHI NAMI"]
    res = mark(client, ids["E-TRANSFER ***K2P"], case="payback", charge=sushi)
    assert res["title"] == "Linked to Sushi Nami. Not income."
    assert client.st.splits() == {}
    assert next(r for r in listing(client)["transactions"] if r["id"] == sushi)["amount"] == 60


def test_someone_already_in_the_split_is_not_added_again(client):
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(-30, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)))
    sushi = ids["SUSHI NAMI"]
    client.put(f"/api/transactions/{sushi}/split",
               json={"mode": "even", "people": [{"name": "Priya", "amount": 45}], "watch": True})
    mark(client, ids["E-TRANSFER FROM PRIYA"], case="payback", charge=sushi, person="Priya")
    assert client.st.splits()[sushi]["people"] == [{"name": "Priya", "amount": 45.0}]
    assert client.st.get_transaction(sushi).my_share == 45
    # Unlinking leaves her split alone: she still owes her part.
    client.delete(f"/api/transactions/{sushi}/paybacks/{ids['E-TRANSFER FROM PRIYA']}")
    assert client.st.splits()[sushi]["people"] == [{"name": "Priya", "amount": 45.0}]


def test_moving_a_payback_to_another_purchase_moves_its_person(client):
    ids = load(client.st, row(90, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                              category="Dining", when=in_month(2)),
               row(60, "CINEPLEX", account="card", kind="credit", merchant="Cineplex",
                   category="Entertainment", when=in_month(3)),
               row(-30, "E-TRANSFER FROM PRIYA", who="Priya", when=in_month(4)))
    back = ids["E-TRANSFER FROM PRIYA"]
    mark(client, back, case="payback", charge=ids["SUSHI NAMI"], person="Priya")
    res = mark(client, back, case="payback", charge=ids["CINEPLEX"], person="Priya")
    splits = client.st.splits()
    assert ids["SUSHI NAMI"] not in splits and splits[ids["CINEPLEX"]]["people"] == [{"name": "Priya", "amount": 30.0}]
    assert not client.st.get_transaction(ids["SUSHI NAMI"]).share_set
    # Undo puts her back on the first purchase.
    undo(client, res)
    splits = client.st.splits()
    assert ids["CINEPLEX"] not in splits and splits[ids["SUSHI NAMI"]]["people"] == [{"name": "Priya", "amount": 30.0}]
    assert client.st.get_transaction(back).repays == ids["SUSHI NAMI"]


def test_answers_on_the_transaction_page_leave_needs_a_look(client):
    """2026-10-25 (Maria): sorting from Transactions still left rows in Needs
    a look. A split, a share, and any answer about a joint deposit now count
    as answered; Undo asks again."""
    from finance.review import for_store, ids_in

    def asked(tid):
        return tid in ids_in(for_store(client.st))

    ids = load(client.st,
               row(40, "MYSTERY SHOP", account="card", kind="credit", merchant="Mystery Shop", when=in_month(9)),
               row(60, "CORNER STORE", account="card", kind="credit", merchant="Corner Store", when=in_month(8)),
               row(-300, "TFR-FR 7781", account="fam", when=in_month(4)),
               row(-250, "TFR-FR 9932", account="fam", when=in_month(5)),
               row(-120, "TFR-FR 4410", account="fam", when=in_month(6)))
    client.put("/api/accounts/fam/joint", json={"label": "Joint"})
    shop, corner = ids["MYSTERY SHOP"], ids["CORNER STORE"]
    assert asked(shop) and asked(corner)
    # A split from the page settles its category, as the sort card's does.
    res = client.put(f"/api/transactions/{shop}/split", json={
        "mode": "even", "people": [{"name": "Priya", "amount": 20}], "watch": True, "settle": True}).get_json()
    assert not asked(shop)
    undo(client, res)
    assert asked(shop)
    # So does saying her share.
    client.put(f"/api/transactions/{corner}/share", json={"my_share": 30})
    assert not asked(corner)
    # A joint deposit sorted any way but "someone else's" was hers, and counts.
    dep, dep2, dep3 = ids["TFR-FR 7781"], ids["TFR-FR 9932"], ids["TFR-FR 4410"]
    assert asked(dep) and asked(dep2) and asked(dep3)
    res = mark(client, dep, case="pay", income_kind="salary")
    assert not asked(dep) and client.st.get_transaction(dep).joint_from == "me"
    assert listing(client)["totals"]["income"] == 300
    undo(client, res)
    assert asked(dep) and not client.st.get_transaction(dep).joint_from
    res = client.patch(f"/api/transactions/{dep2}", json={"category": "Transfers"}).get_json()
    assert not asked(dep2)
    undo(client, res)
    assert asked(dep2)
    client.put(f"/api/transactions/{dep3}/income-type", json={"kind": "gifts"})
    assert not asked(dep3) and client.st.get_transaction(dep3).joint_from == "me"


def test_a_joint_income_deposit_is_one_question(client):
    """Income into a joint account is asked on its joint card (Is this
    income? → what kind), not again under Income: one deposit, one
    question, counted once (2026-10-26)."""
    from finance.review import for_store
    ids = load(client.st, row(-500, "DEPOSIT FAM", account="fam", category="Income", when=in_month(4)))
    client.put("/api/accounts/fam/joint", json={"label": "Joint"})
    r = for_store(client.st)
    tid = ids["DEPOSIT FAM"]
    assert [it["key"] for it in r["joint_in"]] == [f"joint:{tid}"]
    assert all(it["txn"]["id"] != tid for it in r["income_type"])
    assert r["count"] == 1


def test_a_cash_deposit_is_not_income(client):
    """"No, it's a cash deposit" (2026-10-26): her own cash going in, so not
    income, and not taken off what she withdrew."""
    ids = load(client.st, row(-2000, "PAYROLL ACME", category="Income", when=in_month(1)),
               row(-300, "ATM DEPOSIT", when=in_month(5)))
    tid = ids["ATM DEPOSIT"]
    assert any(c["key"] == "cash" for c in cases(client, tid)["cases"])
    before = listing(client)["totals"]
    res = mark(client, tid, case="cash")
    assert res["title"] == "Sorted as a cash deposit."
    t = client.st.get_transaction(tid)
    assert (t.category, t.category_source) == ("Transfers", "user")
    after = listing(client)["totals"]
    assert after["income"] == before["income"] == 2000 and after["spent"] == 0
    own = mark(client, tid, case="own")                # the same as her own money moving
    assert listing(client)["totals"] == after
    undo(client, own)
    from finance.review import for_store, ids_in
    assert tid not in ids_in(for_store(client.st))
    undo(client, res)
    assert client.st.get_transaction(tid).category != "Transfers"
