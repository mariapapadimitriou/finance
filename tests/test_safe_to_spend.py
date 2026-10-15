"""Safe to spend for the month and the sheet behind it (THL-44, THL-46).

The main fixture is the person drawn in the Handoff File's X-01 on Friday
October 9: two $2,150 paycheques, five bills still to come, $3,144.34 spent,
$150 still to set aside, so $642.18 safe to spend.
"""

from datetime import date, timedelta

import pytest

from finance import safe_to_spend as sts
from finance.models import Transaction

TODAY = date(2026, 10, 9)


def tx(day, merchant, amount, category, account="chq", **kw):
    # Pay says so in its description, as a bank's direct deposit does; that
    # is how the pipeline tells salary from other income.
    pay = kw.get("income_type") == "salary"
    description = f"{merchant.upper()} PAYROLL" if pay else merchant.upper()
    return Transaction(date=day, description=description, merchant=merchant,
                       amount=amount, category=category, account_id=account, **kw)


def history():
    """Three earlier months that make the pay and the bills regular."""
    rows = []
    for d in ("2026-07-16", "2026-08-01", "2026-08-14", "2026-09-01", "2026-09-16"):
        rows.append(tx(d, "Northwind Ltd", -2150.00, "Income", income_type="salary"))
    for m, hydro in (("07", 60.00), ("08", 64.00), ("09", 57.00)):
        rows += [
            tx(f"2026-{m}-01", "Parkside Properties", 2000.00, "Rent & Housing"),
            tx(f"2026-{m}-12", "Rogers", 85.00, "Phone & Internet", account="visa"),
            tx(f"2026-{m}-20", "Belair Insurance", 190.00, "Insurance"),
            tx(f"2026-{m}-21", "Hydro One", hydro, "Utilities"),
            tx(f"2026-{m}-22", "Netflix", 16.49, "Streaming", account="visa"),
            tx(f"2026-{m}-25", "Spotify", 11.99, "Streaming", account="visa"),
        ]
    return rows


def october():
    return [
        tx("2026-10-01", "Northwind Ltd", -2150.00, "Income", income_type="salary"),
        tx("2026-10-01", "Parkside Properties", 2000.00, "Rent & Housing"),
        tx("2026-10-05", "Loblaws", 732.00, "Groceries", account="visa"),
        tx("2026-10-06", "Pai", 332.34, "Dining", account="visa"),
        # Pending tonight: counts already.
        tx("2026-10-09", "Bar Raval", 40.00, "Dining", account="visa", raw={"pending": True}),
        # A $120 dinner split three ways: only her $40 is hers.
        tx("2026-10-03", "Grey Gardens", 120.00, "Dining", account="visa", my_share=40.00),
        # A friend paying back their share is not income.
        tx("2026-10-04", "Sam Lee", -40.00, "Income", repays="some-charge"),
        # Paying the card and moving money to savings are not spending.
        tx("2026-10-07", "TD Visa payment", 500.00, "Transfers"),
        tx("2026-10-08", "To savings", 150.00, "Saved"),
    ]


def alex(**kw):
    return sts.compute(history() + october(), TODAY, **kw)


def row(result, key):
    return next(r for r in result["rows"] if r["key"] == key)


class TestTheNumber:
    def test_matches_the_handoff_file(self):
        r = alex()
        assert r["state"] == "ok"
        assert row(r, "income")["amount"] == 4300.00
        assert row(r, "bills")["amount"] == 363.48
        assert row(r, "spent")["amount"] == 3144.34
        assert row(r, "saved")["amount"] == 150.00          # moved to savings (THL-230)
        assert r["amount"] == 642.18

    def test_the_sheet_adds_up_to_the_number_shown(self):
        r = alex()
        rows = {x["key"]: x["amount"] for x in r["rows"]}
        total = rows["income"] - rows["bills"] - rows["spent"] - rows.get("saved", 0)
        assert round(total, 2) == r["amount"]

    @pytest.mark.parametrize("moved", [0.0, 150.0, 1234.57])
    def test_it_adds_up_to_the_cent_whatever_the_inputs(self, moved):
        rows = history() + october() + [
            tx("2026-10-02", "Shop", 0.01, "Shopping"),
            tx("2026-10-02", "Shop", 33.333, "Shopping"),
        ]
        r = sts.compute(rows, TODAY, moved_to_savings=moved)
        cents = {x["key"]: round(x["amount"] * 100) for x in r["rows"]}
        expected = cents["income"] - cents["bills"] - cents["spent"] - cents.get("saved", 0)
        assert round(r["amount"] * 100) == expected

    def test_days_left_include_today(self):
        r = alex()
        assert r["days_left"] == 23                      # Oct 9 to Oct 31
        assert r["per_day"] == 27.92                     # $642.18 ÷ 23, never rounded up
        assert sts.days_left(date(2026, 10, 31)) == 1

    def test_next_pay(self):
        assert alex()["next_pay"] == "2026-10-16"


class TestMoneyComingIn:
    def test_two_paycheques_one_arrived_one_expected(self):
        income = row(alex(), "income")
        assert income["paycheques"] == 2 and income["payer"] == "Northwind Ltd"
        arrived = [line["arrived"] for line in income["lines"] if line["kind"] == "salary"]
        assert arrived == [True, False]

    def test_a_friend_paying_back_is_left_out(self):
        assert all(line["label"] != "Sam Lee" for line in row(alex(), "income")["lines"])

    def test_biweekly_pay_projects_every_two_weeks(self):
        rows = [tx(d, "Acme", -1000.00, "Income", income_type="salary")
                for d in ("2026-08-21", "2026-09-04", "2026-09-18", "2026-10-02")]
        income = sts.income_this_month(rows, TODAY)
        assert income["amount"] == 3000.00              # Oct 2, Oct 16, Oct 30
        assert income["next_pay"] == "2026-10-16"

    def test_a_paycheque_a_day_early_is_not_counted_twice(self):
        rows = history()[:5] + [tx("2026-09-30", "Northwind Ltd", -2150.00, "Income",
                                   income_type="salary")]
        income = sts.income_this_month(rows, TODAY)
        # Sep 30 was the Oct 1 pay arriving early; only Oct 16 is still to come.
        assert income["amount"] == 2150.00

    def test_pay_that_stopped_is_not_expected(self):
        rows = [tx(d, "Acme", -1000.00, "Income", income_type="salary")
                for d in ("2026-06-05", "2026-06-19", "2026-07-03", "2026-07-17")]
        assert sts.income_this_month(rows, TODAY)["amount"] is None

    def test_without_regular_pay_it_uses_what_she_told_us(self):
        rows = [tx("2026-10-02", "Client A", -900.00, "Income")]
        income = sts.income_this_month(rows, TODAY, entered_monthly=3000.0)
        assert income["source"] == "entered" and income["amount"] == 3000.00

    def test_what_she_told_us_never_hides_money_that_arrived(self):
        rows = [tx("2026-10-02", "Client A", -3500.00, "Income")]
        income = sts.income_this_month(rows, TODAY, entered_monthly=3000.0)
        assert income["amount"] == 3500.00

    def test_no_income_means_no_number(self):
        """E1: ask for income rather than show a guess."""
        rows = [tx("2026-10-05", "Loblaws", 80.00, "Groceries")]
        r = sts.compute(rows, TODAY)
        assert r["state"] == "needs_income"
        assert r["amount"] is None and r["per_day"] is None and r["rows"] == []


class TestBillsStillToCome:
    def test_the_five_bills_in_date_order(self):
        bills = row(alex(), "bills")
        names = [(b["label"], b["date"]) for b in bills["lines"]]
        assert names == [("Rogers", "2026-10-12"), ("Belair Insurance", "2026-10-20"),
                         ("Hydro One", "2026-10-21"), ("Netflix", "2026-10-22"),
                         ("Spotify", "2026-10-25")]
        assert bills["count"] == 5
        assert (bills["first"], bills["last"]) == ("2026-10-12", "2026-10-25")

    def test_a_paid_bill_is_already_spent_not_still_to_come(self):
        bills = row(alex(), "bills")["lines"]
        assert "Parkside Properties" not in {b["label"] for b in bills}

    def test_a_bill_that_varies_is_an_estimate_at_its_usual_amount(self):
        hydro = next(b for b in row(alex(), "bills")["lines"] if b["label"] == "Hydro One")
        assert hydro["estimate"] is True and hydro["amount"] == 60.00

    def test_a_late_bill_stays_until_month_end(self):
        r = sts.compute(history() + october(), date(2026, 10, 14))
        rogers = next(b for b in row(r, "bills")["lines"] if b["label"] == "Rogers")
        assert rogers["late"] is True

    def test_a_weekly_coffee_is_not_a_bill(self):
        start = date(2026, 9, 7)
        rows = history() + october() + [
            tx((start + timedelta(weeks=i)).isoformat(), "Tim Hortons", 4.50, "Coffee",
               account="visa") for i in range(5)]
        labels = {b["label"] for b in row(sts.compute(rows, TODAY), "bills")["lines"]}
        assert "Tim Hortons" not in labels


class TestAlreadySpent:
    def test_groups_and_pending(self):
        spent = row(alex(), "spent")
        assert spent["pending"] == 40.00
        assert {(x["label"], x["amount"]) for x in spent["lines"]} == {
            ("Essentials", 2732.00), ("Lifestyle", 412.34)}

    def test_transfers_card_payments_and_savings_never_count(self):
        spent = row(alex(), "spent")["amount"]
        assert spent == 3144.34          # the $500 card payment and $150 saved are not in it

    def test_an_unsorted_transfer_counts_until_sorted(self):
        rows = history() + october() + [tx("2026-10-08", "E-transfer", 816.00,
                                           "Unsorted transfers")]
        r = sts.compute(rows, TODAY)
        assert row(r, "spent")["amount"] == 3960.34


class TestMovedToSavings:
    """THL-230: only money she actually moved to savings comes off the month.
    Chests fill from her Anchor, so they never do; no plan or target does."""

    def test_the_saved_transfer_is_the_row(self):
        saved = row(alex(), "saved")
        assert saved["amount"] == 150.00 and saved["lines"] == []
        assert all(x["key"] != "set_aside" for x in alex()["rows"])

    def test_the_caller_can_hand_in_the_one_figure(self):
        assert row(alex(moved_to_savings=80.0), "saved")["amount"] == 80.00
        assert alex(moved_to_savings=80.0)["amount"] == round(642.18 + 150 - 80, 2)

    def test_never_below_nothing(self):
        """More taken out of savings than put in: nothing comes off the month."""
        rows = history() + october() + [tx("2026-10-09", "From savings", -400.00, "Saved")]
        assert row(sts.compute(rows, TODAY), "saved")["amount"] == 0.00
        assert row(alex(moved_to_savings=-50.0), "saved")["amount"] == 0.00


class TestPastThePlan:
    def test_over_plan_says_by_how_much_never_zero(self):
        rows = history() + october() + [tx("2026-10-08", "Air Canada", 726.18, "Travel",
                                           account="visa")]
        r = sts.compute(rows, TODAY)
        assert r["state"] == "over"
        assert r["over_by"] == 84.00
        assert r["amount"] == -84.00 and r["per_day"] is None
        assert r["next_pay"] == "2026-10-16"


class TestTheEndpoint:
    def test_home_returns_the_number(self, tmp_path, monkeypatch):
        from app import create_app
        from finance import api
        app = create_app(str(tmp_path / "home.db"))
        app.config.update(TESTING=True)
        st = app.config["STORE"]
        # Splits and repayments are stored through their own tables; the
        # unit tests above cover them. Here her $40 share is a plain charge.
        plain = [t for t in october() if t.my_share is None and not t.repays]
        st.add_transactions(history() + plain + [tx("2026-10-03", "Grey Gardens", 40.00,
                                                     "Dining", account="visa")])
        st.set_setting("savings_target", "300")
        monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
        with app.test_client() as c:
            body = c.get("/api/home").get_json()
        assert body["month"] == "2026-10"
        assert body["safe_to_spend"]["amount"] == 642.18
        assert body["safe_to_spend"]["days_left"] == 23
