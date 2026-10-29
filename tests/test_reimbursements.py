"""Reimbursements (2026-10-29): one deposit for several work expenses, and
linking a deposit that already came from the expense's side."""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "tests")
from test_what_was_this import client, load, mark, row, undo  # noqa: E402,F401

TODAY = date.today()


def ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def setup(c, deposit=-160.0, work=True):
    taxi = row(45.0, "UBER TRIP", account="cc", kind="credit", when=ago(20), merchant="Uber")
    hotel = row(115.0, "MARRIOTT", account="cc", kind="credit", when=ago(18), merchant="Marriott")
    taxi.category, taxi.category_source = "Transport", "user"
    hotel.category, hotel.category_source = "Lodging", "user"
    pay = row(deposit, "ACME CORP EXPENSES", when=ago(3), merchant="Acme Corp Expenses")
    pay.raw["issuer_category"] = "TRANSFER_IN_DEPOSIT"
    ids = load(c.st, taxi, hotel, pay)
    if work:
        for k in ("UBER TRIP", "MARRIOTT"):
            mark(c, ids[k], case="work")
    return ids["UBER TRIP"], ids["MARRIOTT"], ids["ACME CORP EXPENSES"]


def rows(c):
    return {t.fingerprint: t for t in c.st.all_transactions()}


def cases(c, tid):
    return {x["key"]: x for x in c.get(f"/api/transactions/{tid}/cases").get_json()["cases"]}


class TestFromTheDeposit:
    def test_work_expenses_smaller_than_the_deposit_are_offered(self, client):
        taxi, hotel, pay = setup(client)
        offered = {x["id"]: x for x in cases(client, pay)["reimbursement"]["candidates"]}
        assert {taxi, hotel} <= set(offered)
        assert offered[taxi]["left"] == 45 and offered[hotel]["left"] == 115

    def test_one_deposit_reimburses_two_expenses(self, client):
        taxi, hotel, pay = setup(client)
        res = mark(client, pay, case="reimbursement", charges=[{"id": taxi}, {"id": hotel}])
        assert res["title"] == "Reimbursement for 2 expenses: Marriott and Uber. Both are out of your numbers."
        r = rows(client)
        assert set(r[pay].repays_all) == {taxi, hotel} and r[pay].paid_part == 160
        assert r[taxi].paid_back == 45 and r[hotel].paid_back == 115
        assert not r[taxi].excluded and not r[hotel].excluded
        assert client.st.payback_kinds()[pay] == "reimbursement"
        assert taxi not in client.st.splits()                # never a split
        listed = {x["id"]: x for x in client.get("/api/transactions/list", query_string={"month": ago(3)[:7]})
                  .get_json()["transactions"]}
        assert listed[pay]["note"] in ("Reimbursed you for Uber and Marriott · not income",
                                       "Reimbursed you for Marriott and Uber · not income")

    def test_undo(self, client):
        taxi, hotel, pay = setup(client)
        res = mark(client, pay, case="reimbursement", charges=[{"id": taxi}, {"id": hotel}])
        undo(client, res)
        r = rows(client)
        assert r[pay].repays is None and r[pay].also_repays == {}
        assert r[taxi].excluded and r[hotel].excluded           # waiting again


class TestFromTheExpense:
    def test_a_work_expense_offers_deposits_that_came(self, client):
        taxi, hotel, pay = setup(client, work=False)
        work = cases(client, taxi)["work"]
        assert work["needs"] == "reimbursed"
        [d] = [x for x in work["candidates"] if x["id"] == pay]
        assert d["amount"] == 160 and d["left"] == 160

    def test_no_deposit_yet_means_no_question(self, client):
        taxi = row(45.0, "UBER TRIP", account="cc", kind="credit", when=ago(2), merchant="Uber")
        ids = load(client.st, taxi)
        assert cases(client, ids["UBER TRIP"])["work"]["needs"] is None

    def test_link_two_expenses_to_one_deposit_from_each_side(self, client):
        taxi, hotel, pay = setup(client, work=False)
        res = mark(client, taxi, case="work", reimbursed_by=pay)
        assert res["title"].startswith("Reimbursed by Acme Corp Expenses on ")
        mark(client, hotel, case="work", reimbursed_by=pay)
        r = rows(client)
        assert set(r[pay].repays_all) == {taxi, hotel}
        assert r[taxi].paid_back == 45 and r[hotel].paid_back == 115 and r[pay].paid_part == 160
        assert not r[taxi].excluded and not r[hotel].excluded
        # The deposit is used up: nothing left to offer a third expense.
        lunch = row(30.0, "TIM HORTONS", account="cc", kind="credit", when=ago(10), merchant="Tim Hortons")
        lunch.category, lunch.category_source = "Dining", "user"
        lid = load(client.st, lunch)["TIM HORTONS"]
        assert pay not in {x["id"] for x in cases(client, lid)["work"]["candidates"] or []}
        r2 = client.post(f"/api/transactions/{lid}/mark", json={"case": "work", "reimbursed_by": pay})
        assert r2.status_code == 400 and "used up" in r2.get_json()["error"]

    def test_partly_reimbursed_stays_left_out_for_the_rest(self, client):
        taxi, hotel, pay = setup(client, deposit=-100.0, work=False)
        res = mark(client, hotel, case="work", reimbursed_by=pay)
        assert "the other $15.00 stays left out" in res["detail"]
        r = rows(client)
        assert r[hotel].paid_back == 100 and r[hotel].excluded

    def test_a_friends_payback_is_not_offered(self, client):
        taxi, hotel, pay = setup(client, work=False)
        dinner = row(80.0, "SUSHI", account="cc", kind="credit", when=ago(15), merchant="Sushi")
        dinner.category, dinner.category_source = "Dining", "user"
        friend = row(-40.0, "E-TRANSFER RECEIVED SAM", when=ago(5), who="Sam")
        ids = load(client.st, dinner, friend)
        mark(client, ids["E-TRANSFER RECEIVED SAM"], case="payback", charge=ids["SUSHI"])
        offered = {x["id"] for x in cases(client, taxi)["work"]["candidates"]}
        assert ids["E-TRANSFER RECEIVED SAM"] not in offered and pay in offered
        r = client.post(f"/api/transactions/{taxi}/mark",
                        json={"case": "work", "reimbursed_by": ids["E-TRANSFER RECEIVED SAM"]})
        assert r.status_code == 400 and "paid back something else" in r.get_json()["error"]

    def test_undo_from_the_expense(self, client):
        taxi, hotel, pay = setup(client, work=False)
        mark(client, taxi, case="work", reimbursed_by=pay)
        res = mark(client, hotel, case="work", reimbursed_by=pay)
        undo(client, res)
        r = rows(client)
        assert r[pay].repays_all == [taxi]


class TestManyToMany:
    """2026-10-29: several deposits for one expense, and one deposit for several."""

    def test_two_deposits_reimburse_one_expense(self, client):
        hotel = row(300.0, "MARRIOTT", account="cc", kind="credit", when=ago(20), merchant="Marriott")
        hotel.category, hotel.category_source = "Lodging", "user"
        a = row(-200.0, "ACME EXPENSES ONE", when=ago(8), merchant="Acme Expenses")
        b = row(-100.0, "ACME EXPENSES TWO", when=ago(4), merchant="Acme Expenses")
        ids = load(client.st, hotel, a, b)
        h, d1, d2 = ids["MARRIOTT"], ids["ACME EXPENSES ONE"], ids["ACME EXPENSES TWO"]
        res = mark(client, h, case="work", reimbursed_by=[d1, d2])
        assert res["title"] == "Reimbursed by 2 deposits from Acme Expenses."
        r = rows(client)
        assert r[h].paid_back == 300 and not r[h].excluded
        assert r[d1].paid_part == 200 and r[d2].paid_part == 100

    def test_one_deposit_then_another_from_the_deposit_side(self, client):
        hotel = row(300.0, "MARRIOTT", account="cc", kind="credit", when=ago(20), merchant="Marriott")
        hotel.category, hotel.category_source = "Lodging", "user"
        a = row(-200.0, "ACME EXPENSES ONE", when=ago(8), merchant="Acme Expenses")
        b = row(-100.0, "ACME EXPENSES TWO", when=ago(4), merchant="Acme Expenses")
        ids = load(client.st, hotel, a, b)
        h, d1, d2 = ids["MARRIOTT"], ids["ACME EXPENSES ONE"], ids["ACME EXPENSES TWO"]
        mark(client, h, case="work")
        res = mark(client, d1, case="reimbursement", charge=h)
        assert res["title"] == "Part of Marriott reimbursed."
        assert rows(client)[h].excluded                      # $100 still to come
        offered = {x["id"]: x for x in cases(client, d2)["reimbursement"]["candidates"]}
        assert offered[h]["left"] == 100
        mark(client, d2, case="reimbursement", charge=h)
        r = rows(client)
        assert r[h].paid_back == 300 and not r[h].excluded

    def test_a_bigger_deposit_leaves_the_rest_as_money_in(self, client):
        taxi, hotel, pay = setup(client)
        res = mark(client, pay, case="reimbursement", charge=taxi)
        assert res["detail"] == "The other $115.00 of this deposit counts as money in."
        r = rows(client)
        assert r[taxi].paid_back == 45 and r[pay].paid_part == 45 and r[pay].unlinked_part == 115

    def test_more_deposits_than_it_needs_is_refused(self, client):
        taxi, hotel, pay = setup(client, work=False)
        extra = row(-50.0, "ACME EXPENSES LATE", when=ago(1), merchant="Acme Expenses")
        lid = load(client.st, extra)["ACME EXPENSES LATE"]
        r = client.post(f"/api/transactions/{taxi}/mark", json={"case": "work", "reimbursed_by": [pay, lid]})
        assert r.status_code == 400 and "more deposits than it needs" in r.get_json()["error"]


class TestSearch:
    def test_deposits_can_be_searched_by_name_or_amount(self, client):
        taxi, hotel, pay = setup(client, work=False)
        far = row(-45.0, "EXPENSIFY PAYOUT", when=ago(-200), merchant="Expensify")
        load(client.st, far)
        found = client.get(f"/api/transactions/{taxi}/deposits", query_string={"q": "acme"}).get_json()["deposits"]
        assert [d["merchant"] for d in found] == ["Acme Corp Expenses"]
        found = client.get(f"/api/transactions/{taxi}/deposits", query_string={"q": "45"}).get_json()["deposits"]
        assert [d["merchant"] for d in found] == ["Expensify"]          # a search looks further
        everything = client.get(f"/api/transactions/{taxi}/deposits").get_json()["deposits"]
        assert "Expensify" not in [d["merchant"] for d in everything]
