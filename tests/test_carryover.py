"""Last month's surplus or shortfall, carried into this one (THL-212)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import carryover
from finance import safe_to_spend as sts
from finance.store import Store
from test_safe_to_spend import tx

OCT = date(2026, 10, 2)


def september(income=5500.0, spent=(2000.0, 3000.0), saved=0.0):
    """August to see all of September, then September itself."""
    rows = [tx("2026-08-01", "Northwind Ltd", -5500.0, "Income")]
    rows.append(tx("2026-09-01", "Northwind Ltd", -income, "Income"))
    rows += [tx(f"2026-09-{10 + i:02d}", f"Shop {i}", a, "Shopping") for i, a in enumerate(spent)]
    if saved:
        rows.append(tx("2026-09-20", "To savings", saved, "Saved"))
    return rows


@pytest.fixture()
def st(tmp_path):
    return Store(str(tmp_path / "c.db"))


class TestTheResult:
    def test_the_whole_month_income_less_spending_less_saving(self):
        r = carryover.result(september(income=5500.0, spent=(2000.0, 3000.0), saved=300.0),
                             "2026-09")
        assert r["income"] == 5500.0 and r["spent"] == 5000.0 and r["saved"] == 300.0
        assert r["amount"] == 200.0

    def test_short(self):
        assert carryover.result(september(income=4500.0), "2026-09")["amount"] == -500.0

    def test_a_month_pearl_didnt_see_all_of_is_skipped(self):
        rows = [r for r in september() if r.date >= "2026-09-05"]
        assert carryover.result(rows, "2026-09") is None

    def test_no_income_no_result(self):
        rows = [r for r in september() if not (r.date.startswith("2026-09") and r.amount < 0)]
        assert carryover.result(rows, "2026-09") is None


class TestAShortfall:
    def test_asked_and_nothing_changes_until_she_answers(self, st):
        q = carryover.question(st, september(income=4500.0), OCT)
        assert q["kind"] == "short" and q["amount"] == 500.0 and q["choice"] is None
        assert carryover.applied(st, OCT) is None

    @pytest.mark.parametrize("choice, months", [
        ("now", {"2026-10": -50000}),
        ("spread2", {"2026-10": -25000, "2026-11": -25000}),
        ("spread3", {"2026-10": -16668, "2026-11": -16666, "2026-12": -16666}),
    ])
    def test_each_choice_takes_it_from_the_right_months(self, st, choice, months):
        carryover.question(st, september(income=4500.0), OCT)
        assert carryover.answer(st, "2026-09", choice, OCT)
        for m in ("2026-10", "2026-11", "2026-12", "2027-01"):
            got = carryover.applied(st, date.fromisoformat(f"{m}-05"))
            assert (got or {}).get("amount_c", 0) == months.get(m, 0), m
        assert sum(months.values()) == -50000                    # to the cent

    def test_a_spare_choice_doesnt_fit_a_shortfall(self, st):
        carryover.question(st, september(income=4500.0), OCT)
        assert carryover.answer(st, "2026-09", "save", OCT) is None


class TestMoneyToSpare:
    def test_suggested_and_added_only_if_she_chooses_to_spend_it(self, st):
        q = carryover.question(st, september(income=6000.0), OCT)
        assert q["kind"] == "spare" and q["amount"] == 1000.0
        assert q["deadline"] == "2026-10-09"
        carryover.answer(st, "2026-09", "save", OCT)
        assert carryover.applied(st, OCT + timedelta(days=10)) is None

    def test_added_after_7_days_unanswered(self, st):
        carryover.question(st, september(income=6000.0), OCT)
        assert carryover.applied(st, OCT + timedelta(days=6)) is None
        later = OCT + timedelta(days=7)
        assert carryover.applied(st, later)["amount_c"] == 100000
        q = carryover.question(st, september(income=6000.0), later)
        assert q["auto"] is True and q["choice"] == "spend"
        assert carryover.applied(st, date(2026, 11, 3)) is None   # one month only

    def test_small_results_arent_asked_about(self, st):
        assert carryover.question(st, september(income=5005.0), OCT) is None


class TestTheNumber:
    def test_the_sheet_still_adds_up(self):
        rows = september()
        carry = {"amount_c": -25000, "parts": [{"from": "2026-09", "amount": 250.0,
                                                "kind": "short", "index": 1, "of": 2}]}
        plain = sts.compute(rows, OCT, told_income=5500.0)
        s = sts.compute(rows, OCT, told_income=5500.0, carry=carry)
        assert s["amount"] == round(plain["amount"] - 250.0, 2)
        c = next(r for r in s["rows"] if r["key"] == "carryover")
        assert c["amount"] == 250.0 and c["kind"] == "short" and c["parts"][0]["of"] == 2
        others = sum(r["amount"] for r in s["rows"] if r["key"] not in ("income", "carryover"))
        income = next(r for r in s["rows"] if r["key"] == "income")["amount"]
        assert round(income - others - c["amount"], 2) == s["amount"]

    def test_home_asks_and_the_answer_reaches_the_number(self, tmp_path, monkeypatch):
        from app import create_app
        import finance.api as api
        monkeypatch.setattr(api, "_today_iso", lambda: OCT.isoformat())
        app = create_app(str(tmp_path / "h.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            c.application.config["STORE"].add_transactions(september(income=4500.0))
            c.put("/api/home/answers", json={"income": 5500})
            home = c.get("/api/home").get_json()
            assert home["carryover"]["kind"] == "short" and home["carryover"]["amount"] == 500.0
            before = home["safe_to_spend"]["amount"]
            assert c.put("/api/carryover/2026-09", json={"choice": "spread2"}).status_code == 200
            after = c.get("/api/home").get_json()["safe_to_spend"]
            assert after["amount"] == round(before - 250.0, 2)
            assert c.put("/api/carryover/2026-09", json={"choice": "chest"}).status_code == 400
