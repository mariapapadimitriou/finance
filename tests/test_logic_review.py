"""The logic review's scenarios (2026-11-07): three critics found these
Allowance and answer gaps by running Pearl's own code. Each test is one of
their examples, with the answer they agreed was right. Home's Allowance is
the number checked, since that is what she sees.
"""

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date(2026, 11, 7)
MONTH = TODAY.isoformat()[:7]


def prev(n=1):
    d = TODAY.replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.isoformat()[:7]


def row(amount, description, when, account="chq", kind="depository", category=None, who=None,
        merchant=None, issuer="", **raw):
    extra = {"account_type": kind, "issuer_category": issuer, **raw}
    if who:
        extra["counterparty"] = who
    t = Transaction(date=when, description=description, amount=amount, account_id=account,
                    account_name=account, raw=extra, merchant=merchant or "")
    if category:
        t.category, t.category_source = category, "user"
    return t


class World:
    def __init__(self, app):
        self.app = app
        self.c = app.test_client()
        self.st = app.config["STORE"]

    def load(self, *rows):
        by = {}
        for r in rows:
            by.setdefault(r.account_id, []).append(r)
        for account, txns in by.items():
            ingest(self.st, IngestResult(transactions=txns, account_id=account))
        return {t.description: t.fingerprint for t in self.st.all_transactions()}

    def home(self):
        return self.c.get("/api/home").get_json()["safe_to_spend"]

    def rows(self):
        return {r["key"]: r["amount"] for r in self.home().get("rows", [])}

    def allowance(self):
        return self.home().get("amount")

    def mark(self, txn_id, **body):
        r = self.c.post(f"/api/transactions/{txn_id}/mark", json=body)
        assert r.status_code == 200, r.get_json()
        return r.get_json()

    def t(self, txn_id):
        return self.st.get_transaction(txn_id)


@pytest.fixture
def w(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv("PEARL_PWNED_CHECK", "0")
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    app = create_app(str(tmp_path / "w.db"))
    app.config.update(TESTING=True)
    return World(app)


def pay():
    return [row(-5000, "PAYROLL ACME", f"{m}-01", category="Income") for m in (prev(3), prev(2), prev(1), MONTH)]


class TestPaybacksAndReimbursements:
    def test_a_reimbursement_comes_off_once(self, w):
        ids = w.load(*pay(), row(500, "HOTEL", f"{MONTH}-02", category="Lodging"),
                     row(-500, "ACME EXPENSE", f"{MONTH}-05", merchant="Acme Expenses"))
        w.mark(ids["ACME EXPENSE"], case="reimbursement", charge=ids["HOTEL"])
        assert w.allowance() == 5000

    def test_a_payback_part_of_a_deposit_comes_off_once(self, w):
        ids = w.load(*pay(), row(428, "FLIGHT", f"{MONTH}-01", category="Travel"),
                     row(-600, "INTERAC E-TRANSFER FROM DAD", f"{MONTH}-03", who="Dad"))
        w.c.post(f"/api/transactions/{ids['INTERAC E-TRANSFER FROM DAD']}/parts",
                 json={"parts": [{"kind": "payback", "amount": 428, "charge": ids["FLIGHT"], "person": "Dad"},
                                 {"kind": "gift", "amount": 172}]})
        assert w.allowance() == 5172


class TestIncome:
    def test_income_she_named_counts_however_it_came(self, w):
        ids = w.load(*pay(), row(-300, "INTERAC E-TRANSFER FROM SAM LEE", f"{MONTH}-03", who="Sam Lee"))
        w.mark(ids["INTERAC E-TRANSFER FROM SAM LEE"], case="pay", income_kind="bonus")
        assert w.allowance() == 5300

    def test_someone_elses_pay_is_not_expected_as_hers(self, w):
        ids = w.load(*[row(-3000, f"PAY {d}", d, account="joint", merchant="Bigco Payroll",
                           issuer="income_wages")
                       for d in (f"{prev(2)}-10", f"{prev(2)}-24", f"{prev(1)}-08", f"{prev(1)}-22",
                                 f"{MONTH}-05")])
        w.st.set_joint("joint", "Family")
        for i in ids.values():
            w.c.put(f"/api/transactions/{i}/joint-from", json={"who": "them"})
        assert w.rows().get("income", 0) == 0

    def test_one_early_paycheque_doesnt_teach_a_new_schedule(self, w):
        from finance import income_bills as ib, safe_to_spend as s
        cheque = lambda d: row(-2000, f"P {d}", d, merchant="Acme", issuer="income_wages")
        w.load(*[cheque(d) for d in ("2026-09-16", "2026-10-01", "2026-10-16", "2026-10-30")])
        w.c.post("/api/income-bills/pay/answer", json={"payer": "Acme", "answer": "yes"})
        assert w.rows()["income"] == 2000
        w.load(*[cheque(d) for d in ("2026-11-16", "2026-12-01", "2026-12-16")])
        dec = s.compute(w.st.all_transactions(), date(2026, 12, 20), confirm=ib.load(w.st))
        assert dec["rows"][0]["amount"] == 4000

    def test_removing_her_pay_takes_it_out_of_the_allowance(self, w):
        w.load(row(-2000, "ACME", f"{MONTH}-01", merchant="Acme", issuer="income_wages"))
        r = w.c.post("/api/income-bills/pay", json={"name": "Acme", "payer": "Acme", "amount": 2000,
                                                   "cadence": "biweekly", "next": f"{MONTH}-15"}).get_json()
        w.c.delete(f"/api/income-bills/pay/{r['pays'][0]['id']}")
        assert w.home().get("income_source") != "entered"


class TestBills:
    def test_a_bill_that_posts_late_is_still_due_this_month(self, w):
        w.load(*pay(), *[row(1000, f"U{d}", d, merchant="Hydro Co", category="Utilities")
                         for d in (f"{prev(3)}-30", f"{prev(2)}-30", f"{MONTH}-02")])
        assert w.rows()["bills"] == 1000

    def test_rent_paid_early_is_this_months(self, w):
        w.load(*pay(), *[row(2000, f"R{d}", d, merchant="Landlord", category="Rent & Housing")
                         for d in (f"{prev(3)}-01", f"{prev(2)}-01", f"{prev(2)}-30", f"{prev(1)}-30")])
        assert w.rows()["bills"] == 0

    def test_a_bill_paid_early_isnt_held_back_again(self, w):
        w.load(*pay(), *[row(100, f"N{m}", f"{m}-20", merchant="Netflix", category="Streaming")
                         for m in (prev(3), prev(2), prev(1))])
        assert w.rows()["bills"] == 100
        w.load(row(100, "Nnow", f"{MONTH}-06", merchant="Netflix", category="Streaming"))
        assert w.rows()["bills"] == 0

    def test_an_added_bill_paid_early_counts_once(self, w):
        ids = w.load(*pay(), row(60, "GYM A", f"{prev(1)}-15", merchant="Gym Club", category="Fitness"))
        w.c.post(f"/api/transactions/{ids['GYM A']}/bill",
                 json={"cadence": "monthly", "next": f"{MONTH}-15", "share": 100, "category": "Fitness"})
        w.load(row(60, "GYM Y", f"{MONTH}-06", merchant="Gym Club", category="Fitness"))
        rows = w.rows()
        assert rows["bills"] == 0 and rows["spent"] == 60

    def test_an_added_bill_and_the_found_one_are_one_bill(self, w):
        ids = w.load(*pay(), row(20, "NETFLIX A", f"{prev(3)}-20", merchant="Netflix", category="Streaming"))
        w.c.post(f"/api/transactions/{ids['NETFLIX A']}/bill",
                 json={"cadence": "monthly", "next": f"{MONTH}-20", "share": 100, "category": "Streaming"})
        w.load(row(20, "NETFLIX B", f"{prev(2)}-20", merchant="Netflix", category="Streaming"),
               row(20, "NETFLIX C", f"{prev(1)}-20", merchant="Netflix", category="Streaming"))
        assert w.rows()["bills"] == 20


class TestSpending:
    def test_a_mystery_deposit_counts_for_nothing_until_answered(self, w):
        w.load(*pay(), row(-3000, "XYZ HOLDINGS", f"{MONTH}-05", merchant="XYZ Holdings"))
        assert w.allowance() == 5000
        assert w.c.get("/api/review").get_json()["money_in"]

    def test_a_piggy_bank_and_a_linked_refund_dont_go_below_nothing(self, w):
        ids = w.load(*pay(), row(1200, "FLIGHT", f"{MONTH}-03", category="Travel"),
                     row(-1200, "AC REFUND", f"{MONTH}-05", merchant="Flight"))
        w.st.set_setting("anchor_accounts", '["sav"]')
        w.c.post("/api/piggy", json={"name": "T", "target": 2400})
        bank = w.c.get("/api/piggy").get_json()["banks"][0]
        w.c.post(f"/api/piggy/{bank['id']}/allocate", json={"txn_id": ids["FLIGHT"], "amount": 1200})
        w.mark(ids["AC REFUND"], case="refund", charge=ids["FLIGHT"])
        assert w.rows()["spent"] == 0

    def test_a_piggy_bank_and_a_joint_share_dont_go_below_nothing(self, w):
        ids = w.load(*pay(), row(1000, "HOTEL", f"{MONTH}-02", account="joint", category="Lodging"))
        w.st.set_joint("joint", "Family")
        w.st.set_joint_share("joint", 50.0, "Family")
        # With savings in her Anchor the bank pays her whole share (decision 1).
        w.st.set_setting("anchor_accounts", '["sav"]')
        w.c.post("/api/piggy", json={"name": "T", "target": 3000})
        bank = w.c.get("/api/piggy").get_json()["banks"][0]
        w.c.post(f"/api/piggy/{bank['id']}/allocate", json={"txn_id": ids["HOTEL"], "amount": 1000})
        assert w.rows()["spent"] == 0

    def test_savings_on_a_joint_account_count_her_share(self, w):
        w.load(*pay(), row(1000, "SAVE", f"{MONTH}-03", account="joint", category="Saved"))
        w.st.set_joint("joint", "F")
        w.st.set_joint_share("joint", 50.0, "F")
        assert w.rows()["saved"] == 500


class TestSecondAnswers:
    def test_a_payback_then_pay_counts_as_pay(self, w):
        ids = w.load(*pay(), row(100, "DINNER", f"{MONTH}-02", category="Dining"),
                     row(-100, "INTERAC E-TRANSFER FROM ACME INC", f"{MONTH}-03", who="Acme Inc"))
        charge, money = ids["DINNER"], ids["INTERAC E-TRANSFER FROM ACME INC"]
        w.mark(money, case="payback", charge=charge)
        reply = w.mark(money, case="pay", income_kind="salary")
        rows = w.rows()
        assert rows["income"] == 5100 and rows["spent"] == 100
        w.c.post("/api/transactions/undo", json=reply["undo"])
        assert w.rows()["spent"] == 0 and w.t(money).repays is not None

    def test_a_refund_then_pay_isnt_counted_twice(self, w):
        ids = w.load(*pay(), row(100, "CC", f"{MONTH}-02", merchant="Canada Computers", category="Shopping"),
                     row(-100, "CC CR", f"{MONTH}-03", merchant="Canada Computers"))
        w.mark(ids["CC CR"], case="refund", charge=ids["CC"])
        w.mark(ids["CC CR"], case="pay", income_kind="salary")
        assert w.allowance() == 5000

    def test_not_mine_then_a_purchase_counts(self, w):
        ids = w.load(*pay(), row(80, "GROCERY", f"{MONTH}-02", account="joint", category="Groceries"))
        w.st.set_joint("joint", "Family")
        w.mark(ids["GROCERY"], case="not_mine")
        w.mark(ids["GROCERY"], case="spending", category="Groceries")
        assert w.rows()["spent"] == 80

    def test_lent_with_always_moves_this_row(self, w):
        ids = w.load(*pay(), row(50, "COSTCO", f"{MONTH}-02", merchant="Costco", category="Groceries"))
        reply = w.mark(ids["COSTCO"], case="lent", remember=True)
        assert w.t(ids["COSTCO"]).category == "Lent" and w.rows()["spent"] == 0
        w.c.post("/api/transactions/undo", json=reply["undo"])
        assert w.t(ids["COSTCO"]).category == "Groceries" and not w.st.overrides()

    def test_leave_out_every_can_be_undone_and_matches_the_whole_name(self, w):
        ids = w.load(*pay(), row(60, "SHELL 1", f"{MONTH}-02", merchant="Shell", category="Gas & Fuel"),
                     row(70, "SHELL 2", f"{MONTH}-03", merchant="Shell", category="Gas & Fuel"),
                     row(30, "SHELLFISH SHACK", f"{MONTH}-03", merchant="Shellfish Shack", category="Dining"))
        reply = w.mark(ids["SHELL 1"], case="not_mine", reason="Not mine", remember=True)
        from finance.exclusions import matches
        rule = w.st.exclusion_rules()[0]
        assert not matches(rule, w.t(ids["SHELLFISH SHACK"]))
        assert matches(rule, w.t(ids["SHELL 2"]))
        w.c.post("/api/transactions/undo", json=reply["undo"])
        assert w.rows()["spent"] == 160 and not w.st.exclusion_rules()


def test_the_allowance_message_uses_homes_number(w):
    ids = w.load(*pay(), row(200, "THING", f"{MONTH}-03", category="Dining", merchant="Thing Co"))
    line = w.c.post(f"/api/transactions/{ids['THING']}/mark?dry=1",
                    json={"case": "spending", "category": "Groceries"}).get_json()["line"]
    assert "stays the same" in line
    line = w.c.post(f"/api/transactions/{ids['THING']}/mark?dry=1", json={"case": "moved"}).get_json()["line"]
    assert "$200.00" in line


class TestMoreBills:
    def test_a_charge_she_left_out_is_not_a_bill(self, w):
        ids = w.load(*pay(), *[row(20, f"NF{m}", f"{m}-20", merchant="Netflix", category="Streaming")
                               for m in (prev(3), prev(2), prev(1))])
        for i in ids:
            if i.startswith("NF"):
                w.st.exclude(ids[i], "My sister's")
        assert w.rows()["bills"] == 0

    def test_her_share_of_a_bill_is_what_its_charge_counts(self, w):
        ids = w.load(*pay(), *[row(2000, f"R{m}", f"{m}-01", merchant="Landlord", category="Rent & Housing")
                               for m in (prev(3), prev(2), prev(1))])
        bills = w.c.get("/api/income-bills").get_json()["bills"]
        bill = next(b for b in bills if "Landlord" in b["name"] or b.get("rent"))
        assert w.c.put(f"/api/income-bills/bills/{bill['key']}",
                       json={"name": bill["name"], "amount": 2000, "cadence": "monthly",
                             "next": f"{MONTH}-01", "share": 50}).status_code == 200
        before = w.allowance()
        w.load(row(2000, "RNOW", f"{MONTH}-01", merchant="Landlord", category="Rent & Housing"))
        assert w.allowance() == before

    def test_told_rent_paid_by_an_unsorted_e_transfer_comes_off_once(self, w):
        w.load(*pay(), row(1500, "E-TRANSFER TO LANDLORD", f"{MONTH}-01", category="Unsorted transfers"))
        w.st.set_setting("home_rent", "1500")
        rows = w.rows()
        assert rows["bills"] == 0 and rows["spent"] == 1500


class TestFromLastMonth:
    def test_pay_that_came_early_for_this_month_counts_this_month(self, w):
        w.load(*[row(-3000, f"PAY {d}", d, merchant="Acme", issuer="income_wages")
                 for d in ("2026-08-01", "2026-09-01", "2026-10-01", "2026-10-30")],
               row(1200, "GROCER", f"{MONTH}-03", category="Groceries"))
        home = w.home()
        assert home["state"] == "ok"
        assert any(r["key"] == "from_last_month" for r in home["rows"])

    def test_a_payback_for_last_months_dinner_counts_this_month(self, w):
        ids = w.load(*pay(), row(800, "DINNER", f"{prev(1)}-25", category="Dining"),
                     row(-600, "INTERAC E-TRANSFER FROM SAM", f"{MONTH}-03", who="Sam"))
        before = w.allowance()
        w.mark(ids["INTERAC E-TRANSFER FROM SAM"], case="payback", charge=ids["DINNER"])
        assert w.allowance() == before + 600


def test_a_full_re_sort_keeps_her_yes(w):
    from finance.pipeline import recategorize_all
    ids = w.load(row(40, "ZED SHOP", f"{MONTH}-02", merchant="Zed Shop", issuer="GENERAL_MERCHANDISE",
                     category_confidence="LOW"))
    zed = ids["ZED SHOP"]
    w.c.put(f"/api/transactions/{zed}/confirm")
    category = w.t(zed).category
    w.st.set_override("Zed Shop", "Dining", move_rows=False)
    recategorize_all(w.st)
    assert w.t(zed).category == category


class TestRowsReplaced:
    def test_a_posted_row_keeps_what_she_said_about_the_pending_one(self, w):
        pend = row(120, "DINNER PENDING", f"{MONTH}-02", category=None, plaid_id="p-1", pending=True,
                   merchant="Bistro")
        ids = w.load(*pay(), pend)
        w.st.set_transaction_category(ids["DINNER PENDING"], "Dining")
        w.st.set_share(ids["DINNER PENDING"], 40.0)
        w.st.keep_answers_for({"posted-1": "p-1"})
        w.st.delete_transactions_from(["p-1"])
        w.load(row(120, "DINNER", f"{MONTH}-03", plaid_id="posted-1", merchant="Bistro"))
        posted = next(t for t in w.st.all_transactions() if t.description == "DINNER")
        assert posted.my_share == 40.0

    def test_a_reconnect_keeps_a_linked_refund(self, w):
        ids = w.load(*pay(), row(70, "SHOES", f"{MONTH}-02", category="Shopping", merchant="Shoe Co"),
                     row(-30, "SHOES CR", f"{MONTH}-04", merchant="Shoe Co"))
        w.mark(ids["SHOES CR"], case="refund", charge=ids["SHOES"])
        w.st.rekey_rows({ids["SHOES CR"]: "new-refund-id"})
        assert w.st.refunds().get("new-refund-id") == ids["SHOES"]


def test_unlinking_a_reimbursement_waits_for_one_again(w):
    from finance.marks import WORK_REASON
    ids = w.load(*pay(), row(500, "HOTEL", f"{MONTH}-02", category="Lodging"),
                 row(-500, "ACME EXPENSE", f"{MONTH}-05", merchant="Acme Expenses"))
    w.st.exclude(ids["HOTEL"], WORK_REASON)
    w.mark(ids["ACME EXPENSE"], case="reimbursement", charge=ids["HOTEL"])
    w.c.delete(f"/api/transactions/{ids['HOTEL']}/paybacks/{ids['ACME EXPENSE']}")
    assert w.t(ids["HOTEL"]).excluded == WORK_REASON


def test_money_into_an_investment_account_is_saved_either_way(w):
    w.load(*pay(), row(500, "TFR TO INVEST", f"{MONTH}-03", issuer="TRANSFER_OUT"),
           row(-500, "TFR FROM CHQ", f"{MONTH}-03", account="inv", kind="investment", issuer="TRANSFER_IN"))
    out = next(t for t in w.st.all_transactions() if t.description == "TFR TO INVEST")
    assert out.category == "Saved"


def test_this_is_my_regular_pay_can_be_undone(w):
    from finance import income_bills as ib
    ids = w.load(*[row(-2000, f"P{d}", d, merchant="Northwind", issuer="income_wages")
                   for d in (f"{prev(2)}-15", f"{prev(1)}-01", f"{prev(1)}-15", f"{MONTH}-01")])
    reply = w.mark(ids[f"P{MONTH}-01"], case="regular_pay", remember=True, cadence="semimonthly",
                   next=f"{MONTH}-15")
    assert [p["payer"] for p in ib.load(w.st)["pays"]] == ["Northwind"]
    assert w.c.post("/api/transactions/undo", json=reply["undo"]).status_code == 200
    assert ib.load(w.st)["pays"] == [] and not ib.load(w.st)["income_on"]


def test_a_refund_on_a_shared_purchase_is_shared_the_same_way():
    from finance.analytics import share_amount
    hotel = Transaction(date=f"{MONTH}-02", description="HOTEL", amount=400.0, account_id="chq",
                        merchant="Hotel", category="Lodging", my_share=200.0)
    hotel.refunded = 100.0
    assert share_amount(hotel) == 150.0


def test_a_payback_cant_be_more_than_whats_left_of_the_charge(w):
    ids = w.load(*pay(), row(80, "DINNER", f"{MONTH}-02", category="Dining"),
                 row(-500, "INTERAC E-TRANSFER FROM SAM", f"{MONTH}-03", who="Sam"))
    w.mark(ids["INTERAC E-TRANSFER FROM SAM"], case="payback", charge=ids["DINNER"])
    assert w.t(ids["INTERAC E-TRANSFER FROM SAM"]).repays_amount == 80


def test_a_card_refund_isnt_pay():
    from finance.categorize import categorize
    assert categorize("Canada Computers Refund", "CANADA COMPUTERS REFUND")[0] != "Income"


class TestPlanQuestions:
    def _savings(self, w):
        w.st.record_account_default("sav", "TD Savings ••2210", "item", False, "depository", "savings") \
            if hasattr(w.st, "record_account_default") else None

    def test_is_this_where_you_save_then_moves_count_as_put_away(self, w):
        from finance import checks
        rows = [*pay(), row(500, "TFR-TO 2210", f"{MONTH}-03", issuer="TRANSFER_OUT"),
                row(-500, "TFR-FR CHQ", f"{MONTH}-03", account="sav", issuer="TRANSFER_IN",
                    account_subtype="savings")]
        w.load(*rows)
        w.st.set_account_sync("sav", True, name="TD Savings ••2210")
        with w.st.conn() as c:
            c.execute("UPDATE account_sync SET account_type = 'depository', account_subtype = 'savings' "
                      "WHERE account_id = 'sav'")
        asks = w.c.get("/api/review").get_json()["checks"]
        assert [a["pair"]["question"] for a in asks] == ["Is TD Savings ••2210 where you save?"]
        assert w.rows()["saved"] == 0
        reply = w.c.post(f"/api/review/check/{asks[0]['key']}", json={"yes": True}).get_json()
        assert reply["ok"]
        assert w.rows()["saved"] == 500 and "sav" in checks.savers(w.st)
        assert not w.c.get("/api/review").get_json()["checks"]

    def test_still_paid_asks_when_pay_stops_and_no_stops_expecting_it(self, w):
        from finance import income_bills as ib
        w.load(*[row(-2000, f"P{m}", f"{m}-01", merchant="Acme", issuer="income_wages")
                 for m in ("2026-06", "2026-07", "2026-08")])
        w.c.post("/api/income-bills/pay", json={"name": "Acme", "payer": "Acme", "amount": 2000,
                                               "cadence": "monthly", "next": f"{MONTH}-01"})
        asks = w.c.get("/api/review").get_json()["checks"]
        assert [a["pair"]["question"] for a in asks] == ["Still paid by Acme?"]
        assert w.rows()["income"] == 2000, "still expected until she answers"
        w.c.post(f"/api/review/check/{asks[0]['key']}", json={"yes": False})
        assert ib.load(w.st)["pays"] == []


class TestPiggyBankShort:
    def _bank(self, w, ids, charge):
        w.c.post("/api/piggy", json={"name": "Trip", "target": 1200, "monthly": 100})
        bank = w.c.get("/api/piggy").get_json()["banks"][0]
        return w.c.post(f"/api/piggy/{bank['id']}/allocate",
                        json={"txn_id": ids[charge], "amount": 2000}).get_json()

    def test_without_anchor_savings_the_rest_stays_in_the_month(self, w):
        ids = w.load(*pay(), row(2000, "FLIGHT", f"{MONTH}-03", category="Travel"))
        out = self._bank(w, ids, "FLIGHT")
        assert out["covered"] < 2000 and out["short"] == 0
        assert w.rows()["spent"] == round(2000 - out["covered"], 2)

    def test_with_anchor_savings_the_shortfall_comes_off_the_anchor(self, w):
        ids = w.load(*pay(), row(2000, "FLIGHT", f"{MONTH}-03", category="Travel"))
        w.st.set_setting("anchor_accounts", '["sav"]')
        out = self._bank(w, ids, "FLIGHT")
        assert out["covered"] == 2000 and out["short"] > 0


class TestTheRest:
    def test_a_piggy_bank_isnt_charged_for_money_that_came_back(self, w):
        ids = w.load(*pay(), row(1200, "FLIGHT", f"{MONTH}-03", category="Travel"),
                     row(-400, "AC REFUND", f"{MONTH}-05", merchant="Flight"))
        w.st.set_setting("anchor_accounts", '["sav"]')
        w.c.post("/api/piggy", json={"name": "T", "target": 2400})
        bank = w.c.get("/api/piggy").get_json()["banks"][0]
        w.c.post(f"/api/piggy/{bank['id']}/allocate", json={"txn_id": ids["FLIGHT"], "amount": 1200})
        w.mark(ids["AC REFUND"], case="refund", charge=ids["FLIGHT"])
        assert w.c.get("/api/piggy").get_json()["banks"][0]["charged"] == 800

    def test_irregular_pay_added_by_hand_counts_what_came_in(self, w):
        w.load(row(-1200, "CLIENT A", f"{MONTH}-03", merchant="Client A", issuer="income_wages"))
        w.c.post("/api/income-bills/pay", json={"name": "Freelance", "amount": 3000, "cadence": "irregular"})
        assert w.rows()["income"] == 3000

    def test_it_changes_and_an_amount_are_one_answer(self, w):
        w.load(*pay())
        w.c.put("/api/income-bills/expected", json={"amount": 9000, "varies": False})
        assert w.home()["income_source"] == "told"
        w.c.put("/api/income-bills/expected", json={"varies": True})
        data = w.c.get("/api/income-bills").get_json()
        assert data["expected"]["varies"] is True and not data["expected"]["amount"]
        assert w.home()["income_source"] != "told"

    def test_a_shared_refund_shrinks_what_a_friend_owes(self, w):
        from finance import splits as sp
        ids = w.load(*pay(), row(400, "HOTEL", f"{MONTH}-02", category="Lodging", merchant="Hotel"),
                     row(-100, "HOTEL CR", f"{MONTH}-06", merchant="Hotel"))
        w.st.set_split(ids["HOTEL"], "even", [{"name": "Sam", "amount": 200.0}], True)
        w.st.set_share(ids["HOTEL"], 200.0)
        w.mark(ids["HOTEL CR"], case="refund", charge=ids["HOTEL"])
        charge = w.t(ids["HOTEL"])
        owed = sp.people_status(charge, w.st.splits()[ids["HOTEL"]], w.st.all_transactions(), {})
        assert owed[0]["owes"] == 150
