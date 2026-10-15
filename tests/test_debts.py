"""Debts, including balances from before Pearl (THL-49, THL-128 D-01 to D-03).

The fixture is D-02's person on Friday October 9: a TD Visa owing $1,860
($1,420 from before Pearl, $440 new this month) and a $3,000 student loan,
with $55 and $120 minimums.
"""

from datetime import date

import pytest

from finance import debts, safe_to_spend as sts, secrets_box
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx

RULES = {
    "visa": {"account_name": "TD Visa ••1102", "account_type": "credit", "account_subtype": "credit card"},
    "loan": {"account_name": "Student loan (NSLSC)", "account_type": "loan", "account_subtype": "student"},
    "chq": {"account_name": "TD Chequing ••4410", "account_type": "depository", "account_subtype": "checking"},
    "clean": {"account_name": "Amex ••3005", "account_type": "credit", "account_subtype": "credit card"},
}
BALANCES = {"visa": {"current": 1860.00}, "loan": {"current": 3000.00},
            "chq": {"current": 5200.00}, "clean": {"current": 300.00}}
FIRST = {"visa": {"day": "2026-09-20", "current": 1420.00},
         "clean": {"day": "2026-09-20", "current": 300.00}}
DETAILS = {"visa": {"rate": 20.99, "minimum": 55, "due_day": 22},
           "loan": {"minimum": 120, "due_day": 28}}


def card_rows(extra=()):
    return [
        tx("2026-10-03", "Loblaws", 200.00, "Groceries", account="visa"),
        tx("2026-10-06", "Pai", 240.00, "Dining", account="visa"),
        # The Amex is cleared every month: September's $300 paid on Oct 2.
        tx("2026-09-12", "Indigo", 300.00, "Shopping", account="clean"),
        tx("2026-10-02", "Amex payment", -300.00, "Transfers", account="clean"),
        tx("2026-10-05", "Indigo", 300.00, "Shopping", account="clean"),
        *extra,
    ]


def build(rows=None, balances=BALANCES, first=FIRST, details=DETAILS, today=TODAY):
    return debts.build(RULES, balances, first, card_rows() if rows is None else rows,
                       details, today)


def by_id(result):
    return {d["account_id"]: d for d in result["debts"]}


class TestWhatCountsAsADebt:
    def test_the_handoff_files_two_debts(self):
        r = build()
        assert r["count"] == 2 and r["total"] == 4860.00 and r["minimums"] == 175.00
        visa = by_id(r)["visa"]
        assert (visa["before_pearl"], visa["carried"], visa["new_this_month"]) == (1420.00, 1420.00, 440.00)
        assert visa["kind"] == "card" and visa["due_date"] == "2026-10-22" and visa["rate"] == 20.99
        loan = by_id(r)["loan"]
        assert loan["kind"] == "student_loan" and loan["rate"] is None and loan["minimum"] == 120

    def test_a_card_cleared_every_month_is_spending_not_debt(self):
        """D4: only balances carried from before Pearl or an earlier month."""
        assert "clean" not in by_id(build())

    def test_a_bank_account_is_never_a_debt(self):
        assert "chq" not in by_id(build())

    def test_payments_reduce_the_before_pearl_part_first(self):
        """D3: $300 paid on Oct 8 comes off the $1,420 from before Pearl."""
        rows = card_rows([tx("2026-10-08", "Payment - thank you", -300.00, "Transfers", account="visa")])
        balances = {**BALANCES, "visa": {"current": 1560.00}}
        visa = by_id(build(rows, balances))["visa"]
        assert visa["before_pearl"] == 1120.00 and visa["new_this_month"] == 440.00

    def test_a_card_linked_this_month_is_all_before_pearl(self):
        first = {**FIRST, "visa": {"day": "2026-10-07", "current": 1860.00}}
        visa = by_id(build(card_rows(), first=first))["visa"]
        assert visa["before_pearl"] == 1860.00 and visa["before_pearl_at_month_start"] == 1860.00

    def test_nothing_owed_no_debts(self):
        r = build(balances={"chq": {"current": 100.0}})
        assert r == {"debts": [], "count": 0, "total": 0.0, "minimums": None, "missing_details": 0}

    def test_missing_details_are_counted(self):
        assert build()["missing_details"] == 1              # the loan has no rate
        assert build(details={})["minimums"] is None


class TestMinimumsAsBills:
    def bills(self, rows=None, recurring=(), **kw):
        rows = card_rows() if rows is None else rows
        return debts.bills(build(rows, **kw)["debts"], rows, TODAY, list(recurring))

    def test_both_minimums_are_still_to_come(self):
        """D1: in "Bills still to come", with their due dates."""
        b = self.bills()
        assert [(x["label"], x["date"], x["amount"]) for x in b["lines"]] == [
            ("TD Visa ••1102 minimum", "2026-10-22", 55.00),
            ("Student loan (NSLSC) minimum", "2026-10-28", 120.00)]
        assert b["paid"] == 0

    def test_a_card_minimum_counts_only_up_to_the_before_pearl_balance(self):
        """D2: $30 left from before Pearl, so $30 of the $55 is a bill."""
        first = {**FIRST, "visa": {"day": "2026-09-20", "current": 30.00}}
        b = self.bills(first=first)
        assert next(x for x in b["lines"] if "TD Visa" in x["label"])["amount"] == 30.00
        first = {**FIRST, "visa": {"day": "2026-09-20", "current": 0.00}}
        assert all("TD Visa" not in x["label"] for x in self.bills(first=first)["lines"])

    def test_a_paid_minimum_moves_into_spent(self):
        rows = card_rows([tx("2026-10-08", "Payment - thank you", -100.00, "Transfers", account="visa")])
        b = self.bills(rows, balances={**BALANCES, "visa": {"current": 1760.00}})
        assert all("TD Visa" not in x["label"] for x in b["lines"])
        assert b["paid"] == 55.00

    def test_a_loan_paid_from_chequing(self):
        rows = card_rows([tx("2026-10-05", "NSLSC", 120.00, "Transfers")])
        b = self.bills(rows)
        assert [x["label"] for x in b["lines"]] == ["TD Visa ••1102 minimum"]
        assert b["paid"] == 120.00

    def test_a_loan_payment_already_counted_as_spending_is_not_added_twice(self):
        rows = card_rows([tx("2026-10-05", "NSLSC", 120.00, "Education")])
        b = self.bills(rows)
        assert len(b["lines"]) == 1 and b["paid"] == 0

    def test_a_loan_that_is_already_a_detected_bill_gets_no_second_one(self):
        b = self.bills(recurring=[{"merchant": "NSLSC Student Loan", "category": "Education"}])
        assert [x["label"] for x in b["lines"]] == ["TD Visa ••1102 minimum"]

    def test_late_until_paid(self):
        b = debts.bills(build(today=date(2026, 10, 25))["debts"], card_rows(), date(2026, 10, 25), [])
        assert b["lines"][0]["late"] is True

    @pytest.mark.parametrize("name,merchant,match", [
        ("Student loan (NSLSC)", "NSLSC", True),
        ("Student loan (NSLSC)", "Student Aid Alberta", False),
        ("TD Visa ••1102", "Visa Debit purchase", False),
        ("Ford Credit Auto Loan", "FORD CREDIT CANADA", True),
    ])
    def test_matching_a_payment_to_a_lender(self, name, merchant, match):
        assert debts.names_match(name, merchant) is match


class TestSafeToSpend:
    def rows(self):
        return history() + october()

    def compute(self, debt_bills=None):
        return sts.compute(self.rows(), TODAY, debt_bills=debt_bills)

    def test_carried_balances_are_never_subtracted(self):
        """$4,860 owed, no minimums added: the number doesn't move."""
        b = debts.bills(build(details={})["debts"], self.rows(), TODAY, [])
        assert self.compute(b)["amount"] == self.compute()["amount"] == 642.18

    def test_minimums_are_bills_and_the_sheet_still_adds_up(self):
        b = debts.bills(build()["debts"], card_rows(), TODAY, [])
        r = self.compute(b)
        bills = next(x for x in r["rows"] if x["key"] == "bills")
        assert bills["amount"] == round(363.48 + 175, 2) and bills["count"] == 7
        assert r["amount"] == round(642.18 - 175, 2)
        cents = {x["key"]: round(x["amount"] * 100) for x in r["rows"]}
        assert cents["income"] - cents["bills"] - cents["spent"] - cents["saved"] == round(r["amount"] * 100)

    def test_paying_a_minimum_does_not_change_the_number(self):
        unpaid = debts.bills(build()["debts"], card_rows(), TODAY, [])
        rows = card_rows([tx("2026-10-08", "Payment - thank you", -55.00, "Transfers", account="visa")])
        paid = debts.bills(build(rows, {**BALANCES, "visa": {"current": 1805.00}})["debts"], rows, TODAY, [])
        before, after = self.compute(unpaid), self.compute(paid)
        assert after["amount"] == before["amount"]
        spent = next(x for x in after["rows"] if x["key"] == "spent")
        assert {"label": "Debt payments", "amount": 55.00} in spent["lines"]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "debts.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    st = app.config["STORE"]
    st.add_transactions(history() + [t for t in october() if t.my_share is None and not t.repays]
                        + card_rows())
    for aid, rule in RULES.items():
        st.note_account(aid, name=rule["account_name"], account_type=rule["account_type"],
                        subtype=rule["account_subtype"])
    st.set_balance("visa", 1420.00, None, 5000, "CAD", "2026-09-20")      # first sync
    st.set_balance("visa", 1860.00, None, 5000, "CAD", "2026-10-09")
    st.set_balance("loan", 3000.00, None, None, "CAD", "2026-10-09")
    st.set_balance("chq", 5200.00, 5200.00, None, "CAD", "2026-10-09")
    with app.test_client() as c:
        yield c, st


class TestTheApi:
    def test_first_sync_is_the_before_pearl_balance(self, client):
        _, st = client
        assert st.first_balances()["visa"] == {"day": "2026-09-20", "current": 1420.00}

    def test_home_and_the_debts_page(self, client):
        c, _ = client
        home = c.get("/api/home").get_json()
        assert home["debts"]["count"] == 2 and home["debts"]["total"] == 4860.00
        page = c.get("/api/debts").get_json()
        assert [d["name"] for d in page["debts"]] == ["Student loan (NSLSC)", "TD Visa ••1102"]

    def test_adding_the_details_makes_the_minimum_a_bill(self, client):
        c, _ = client
        before = c.get("/api/home").get_json()["safe_to_spend"]["amount"]
        r = c.put("/api/debts/loan", json={"rate": "5.7%", "minimum": "$120", "due_day": 28})
        assert r.status_code == 200
        loan = next(d for d in r.get_json()["debts"] if d["account_id"] == "loan")
        assert (loan["rate"], loan["minimum"], loan["due_day"]) == (5.7, 120.0, 28)
        after = c.get("/api/home").get_json()["safe_to_spend"]
        assert after["amount"] == round(before - 120, 2)
        assert c.put("/api/debts/loan", json={"minimum": ""}).get_json()["debts"][0]["minimum"] is None

    @pytest.mark.parametrize("body", [{"rate": 140}, {"rate": "abc"}, {"minimum": -5},
                                      {"due_day": 32}, {"due_day": 2.5}])
    def test_details_are_checked(self, client, body):
        c, _ = client
        r = c.put("/api/debts/loan", json=body)
        assert r.status_code == 400 and r.get_json()["field"] == next(iter(body))

    def test_only_debts_take_details(self, client):
        c, _ = client
        assert c.put("/api/debts/chq", json={"rate": 2}).status_code == 404
        assert c.put("/api/debts/nope", json={"rate": 2}).status_code == 404
