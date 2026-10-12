"""Home when data is missing or thin (THL-137 E-01 to E-04; THL-72, THL-69,
THL-47, THL-70), and the THL-9 decisions E1 to E5 and S7.

Every state is checked for what E10 forbids: a NaN, a misleading $0, or a
number nobody can stand behind.
"""

import json
import math
from datetime import date

import pytest

from finance import safe_to_spend as sts
from finance.models import Transaction

TODAY = date(2026, 10, 9)


def tx(day, merchant, amount, category, account="chq", **kw):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant,
                       amount=amount, category=category, account_id=account, **kw)


def state(rows, *, types=None, failed=False, income=0.0, rent=0.0, **kw):
    s = sts.compute(rows, TODAY, told_income=income, told_rent=rent, **kw)
    return s, sts.home_state(rows, TODAY, s, account_types=types, linking_failed=failed,
                             told_income=income, told_rent=rent)


def freelancer(october_in=1900.00):
    """Three full months of client payments, nothing regular about them."""
    rows = [tx("2026-07-01", "Rent", 1650.00, "Rent & Housing")]
    for d, who, amt in (("2026-07-08", "Client A", -1700.00), ("2026-07-27", "Client B", -1400.00),
                        ("2026-08-05", "Client C", -4800.00),
                        ("2026-09-02", "Client A", -2500.00), ("2026-09-21", "Client D", -1400.00),
                        ("2026-10-03", "Client B", -october_in)):
        rows.append(tx(d, who, amt, "Income"))
    rows.append(tx("2026-10-05", "Loblaws", 120.00, "Groceries"))
    return rows


def new_user():
    """Linked two weeks ago."""
    return [tx("2026-09-25", "Loblaws", 80.00, "Groceries", account="visa"),
            tx("2026-10-02", "Pai", 45.00, "Dining", account="visa")]


def calm(s, h):
    """Nothing E10 forbids."""
    for v in (s["amount"], s["shown"], s["per_day"], s["over_by"]):
        assert v is None or (isinstance(v, (int, float)) and not math.isnan(v))
    assert json.dumps(s).count("NaN") == 0 and json.dumps(h).count("NaN") == 0
    if s["state"] == "ok":
        assert s["shown"] is not None


class TestCautiousIncome:
    """E-03, THL-47, THL-70."""

    def test_lowest_of_the_last_three_full_months(self):
        c = sts.cautious_income(freelancer(), TODAY)
        assert c["lowest"] == 3100.00 and c["month"] == "2026-07"
        assert c["highest"] == 4800.00
        assert [m["amount"] for m in c["months"]] == [3100.00, 4800.00, 3900.00]

    def test_it_is_the_income_and_labelled_cautious(self):
        s, h = state(freelancer())
        assert s["income_source"] == "cautious" and s["estimate"] == "cautious"
        assert h["kind"] == "irregular"
        income = next(r for r in s["rows"] if r["key"] == "income")
        assert income["amount"] == 3100.00
        assert [line["label"] for line in income["lines"]] == [
            "Client B", "Still expected, being cautious"]
        calm(s, h)

    def test_more_arriving_than_the_cautious_figure_counts(self):
        """E4: the larger of the cautious figure and what has arrived."""
        s, _ = state(freelancer(october_in=3500.00))
        assert next(r for r in s["rows"] if r["key"] == "income")["amount"] == 3500.00

    def test_shown_rounded_down_to_ten(self):
        s, _ = state(freelancer())
        assert s["amount"] == 3100.00 - 120.00                 # no bills, no goal
        assert s["shown"] == 2980
        s2, _ = state(freelancer() + [tx("2026-10-06", "Shop", 5.55, "Shopping")])
        assert s2["amount"] == 2974.45 and s2["shown"] == 2970

    def test_needs_three_full_months(self):
        rows = [r for r in freelancer() if r.date >= "2026-08-01"]
        assert sts.cautious_income(rows, TODAY) is None

    def test_a_month_with_no_income_means_no_cautious_figure(self):
        rows = [r for r in freelancer() if not r.date.startswith("2026-08")]
        assert sts.cautious_income(rows, TODAY) is None

    def test_an_amount_she_gives_replaces_it(self):
        s, h = state(freelancer(), income=4000.0, overridden=True)
        assert s["income_source"] == "told" and s["overridden"] is True
        assert s["estimate"] is None
        assert h["kind"] == "normal"
        assert next(r for r in s["rows"] if r["key"] == "income")["amount"] == 4000.00


class TestUnderThirtyDays:
    """E-02, THL-69."""

    def test_no_income_asks_the_starter_questions(self):
        s, h = state(new_user(), types={"visa": "credit", "chq": "depository"})
        assert h["kind"] == "learning"
        assert s["state"] == "needs_income" and h["asks_questions"] is True
        assert s["amount"] is None and s["shown"] is None
        calm(s, h)

    def test_says_when_the_rest_appears(self):
        _, h = state(new_user(), types={"visa": "credit", "chq": "depository"})
        assert h["history_days"] == 15
        assert h["learning_until"] == "2026-10-25"
        assert h["comparisons_from"] == "2026-11-01"

    def test_answers_give_a_rough_estimate(self):
        s, h = state(new_user(), types={"visa": "credit", "chq": "depository"},
                     income=4300.0, rent=1650.0)
        assert s["estimate"] == "rough" and h["asks_questions"] is False
        bills = next(r for r in s["rows"] if r["key"] == "bills")
        assert bills["lines"] == [{"label": "Rent or mortgage", "date": None, "amount": 1650.00,
                                   "estimate": False, "late": False,
                                   "category": "Rent & Housing", "told": True}]
        assert s["amount"] == 4300.00 - 1650.00 - 45.00   # the $80 was in September
        assert s["shown"] == 2600
        calm(s, h)

    def test_rent_already_paid_is_not_held_back_twice(self):
        rows = new_user() + [tx("2026-10-01", "Landlord", 1650.00, "Rent & Housing")]
        s, _ = state(rows, types={"chq": "depository"}, income=4300.0, rent=1650.0)
        bills = next(r for r in s["rows"] if r["key"] == "bills")
        assert bills["amount"] == 0 and s["amount"] == 4300.00 - 1650.00 - 45.00

    def test_comparisons_start_the_month_after_a_full_month(self):
        rows = [tx("2026-09-01", "Loblaws", 80.00, "Groceries")]
        h = sts.home_state(rows, TODAY, sts.compute(rows, TODAY))
        assert h["comparisons_from"] == "2026-10-01"


class TestNoData:
    """E-01, THL-72."""

    def test_nothing_linked(self):
        s, h = state([])
        assert h["kind"] == "no_data" and h["linking_failed"] is False
        assert s["state"] == "needs_income" and s["rows"] == []
        calm(s, h)

    def test_linking_failed(self):
        _, h = state([], failed=True)
        assert h["linking_failed"] is True

    def test_two_answers_without_linking_give_a_rough_estimate(self):
        s, h = state([], income=3200.0, rent=1400.0)
        assert h["kind"] == "learning"
        assert s["estimate"] == "rough" and s["amount"] == 1800.00 and s["shown"] == 1800
        calm(s, h)


class TestCardOnly:
    """E-04, THL-137."""

    def test_only_a_card_means_spending_only(self):
        rows = [tx("2026-10-02", "Loblaws", 310.00, "Groceries", account="visa"),
                tx("2026-10-03", "Pai", 430.00, "Dining", account="visa")]
        _, h = state(rows, types={"visa": "credit"})
        assert h["kind"] == "card_only"
        assert h["card_spending"]["amount"] == 740.00
        assert {(x["label"], x["amount"]) for x in h["card_spending"]["lines"]} == {
            ("Essentials", 310.00), ("Lifestyle", 430.00)}

    def test_a_file_import_is_not_card_only(self):
        """No synced accounts to judge by: not E-04."""
        rows = [tx("2026-10-02", "Loblaws", 310.00, "Groceries", account="visa")]
        _, h = state(rows, types={})
        assert h["kind"] != "card_only"


class TestNeverZero:
    @pytest.mark.parametrize("amount,shown", [(9.99, 0), (10.00, 10), (642.18, 640)])
    def test_round_down_to_ten(self, amount, shown):
        assert sts.round_down_10(amount) == shown

    def test_a_per_day_figure_comes_from_what_is_shown(self):
        s, _ = state([], income=3200.0, rent=1400.0)
        assert s["per_day"] == round(1800 / 23 - 0.005, 2)


class TestTheEndpoint:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        from app import create_app
        from finance import api
        app = create_app(str(tmp_path / "home.db"))
        app.config.update(TESTING=True)
        monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
        with app.test_client() as c:
            yield app.config["STORE"], c

    def test_no_data_then_answers(self, client):
        st, c = client
        body = c.get("/api/home").get_json()
        assert body["data_state"]["kind"] == "no_data"
        body = c.put("/api/home/answers", json={"income": 3200, "rent": 1400}).get_json()
        assert body["data_state"]["kind"] == "learning"
        assert body["safe_to_spend"]["shown"] == 1800
        assert st.setting("home_income") == "3200.0"

    def test_an_override_is_recorded(self, client):
        st, c = client
        st.add_transactions(freelancer())
        assert c.get("/api/home").get_json()["data_state"]["kind"] == "irregular"
        body = c.put("/api/home/answers", json={"income": 4000, "override": True}).get_json()
        assert body["safe_to_spend"]["income_source"] == "told"
        log = json.loads(st.setting("income_overrides"))
        assert log == [{"on": "2026-10-09", "amount": 4000.0, "cautious": 3100.0}]

    def test_going_back_to_the_cautious_figure(self, client):
        st, c = client
        st.add_transactions(freelancer())
        c.put("/api/home/answers", json={"income": 4000, "override": True})
        body = c.put("/api/home/answers", json={"income": 0}).get_json()
        assert body["safe_to_spend"]["income_source"] == "cautious"
        assert body["data_state"]["kind"] == "irregular"

    def test_bad_amounts_are_refused(self, client):
        _, c = client
        r = c.put("/api/home/answers", json={"income": "lots"})
        assert r.status_code == 400 and "like 3200" in r.get_json()["error"]
        assert c.put("/api/home/answers", json={"rent": -5}).status_code == 400
