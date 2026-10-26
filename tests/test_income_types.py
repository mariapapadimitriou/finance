"""Income by type, pay cadence, drawdowns and money lent."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import income
from finance.analytics import counts_as_spending, invested_in, monthly_totals
from finance.categorize import categorize
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def row(amount, description, when, account="chq", kind="depository", category=None):
    t = Transaction(date=when, description=description, amount=amount,
                    account_id=account, account_name=account,
                    raw={"account_type": kind})
    if category:
        t.category, t.category_source = category, "user"
    return t


def biweekly(first: date, n: int, amount=2400.0):
    return [row(-amount, "PAYROLL ACME CORP", (first + timedelta(days=14 * i)).isoformat(),
                category="Income") for i in range(n)]


class TestGuess:
    @pytest.mark.parametrize("text,kind", [
        ("PAYROLL ACME CORP", "salary"), ("DIRECT DEP ACME", "salary"),
        ("INTEREST PAID", "interest"), ("CANADA RIT", "tax_refund"),
        ("CANADA CCB", "government"), ("GST CREDIT", "government"),
        ("SOMETHING ELSE", "other"),
    ])
    def test_kinds(self, text, kind):
        t = row(-100, text, "2026-09-01", category="Income")
        assert income.guess(t) == kind

    def test_bonus_is_a_big_paycheque(self):
        rows = biweekly(date(2026, 6, 5), 6)
        big = row(-9000, "PAYROLL ACME CORP", "2026-09-10", category="Income")
        kinds = income.classify(rows + [big])
        assert kinds[big.fingerprint] == "bonus"
        assert kinds[rows[0].fingerprint] == "salary"

    def test_your_type_is_never_overwritten(self):
        t = row(-100, "PAYROLL ACME", "2026-09-01", category="Income")
        t.income_type, t.income_type_source = "gifts", "user"
        assert t.fingerprint not in income.classify([t])


class TestCadence:
    def test_biweekly_is_26_over_12_and_flags_three_pay_months(self):
        rows = biweekly(date(2026, 4, 3), 14)
        pay = income.cadence(rows, today="2026-10-09")
        assert pay["cadence"] == "biweekly"
        assert pay["monthly"] == round(2400 * 26 / 12, 2)
        # Fridays from April 3: May and July... hold three.
        months = {}
        for t in rows:
            months[t.date[:7]] = months.get(t.date[:7], 0) + 1
        assert pay["three_pay_months"] == sorted(m for m, n in months.items()
                                                 if n == 3 and m >= "2026-04")

    def test_monthly(self):
        rows = [row(-5200, "PAYROLL ACME", f"2026-0{m}-25", category="Income")
                for m in range(4, 10)]
        pay = income.cadence(rows, today="2026-10-09")
        assert pay["cadence"] == "monthly" and pay["monthly"] == 5200

    def test_too_little_to_tell(self):
        assert income.cadence(biweekly(date(2026, 9, 1), 2), today="2026-10-09") is None


class TestSavingsAndLending:
    def test_money_back_from_a_brokerage_is_a_drawdown(self):
        assert categorize("QUESTRADE INC", "QUESTRADE INC")[0] == "Saved"
        out = row(1000, "QUESTRADE INC", "2026-09-03", category="Saved")
        back = row(-400, "QUESTRADE INC", "2026-09-20", category="Saved")
        assert invested_in([out, back], "2026-09") == 600

    def test_lent_is_neither_spending_nor_income(self):
        lent = row(200, "SEND E-TFR SAM", "2026-09-03", category="Lent")
        repaid = row(-200, "E-TFR FROM SAM", "2026-09-20", category="Lent")
        assert not counts_as_spending(lent)
        m = monthly_totals([lent, repaid])[0]
        assert m["spend"] == 0 and m["income"] == 0


def test_types_are_stored_and_yours_win(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "inc.db"))
    st = app.config["STORE"]
    ingest(st, IngestResult(transactions=biweekly(date(2026, 6, 5), 4)
                            + [row(-50, "MYSTERY DEPOSIT", "2026-09-30", category="Income")],
                            account_id="chq"))
    by = {t.description: t for t in st.all_transactions()}
    assert by["PAYROLL ACME CORP"].income_type == "salary"
    mystery = by["MYSTERY DEPOSIT"]
    assert mystery.income_type == "other"
    c = app.test_client()
    assert c.put(f"/api/transactions/{mystery.fingerprint}/income-type",
                 json={"kind": "nope"}).status_code == 400
    r = c.put(f"/api/transactions/{mystery.fingerprint}/income-type", json={"kind": "gifts"})
    assert r.get_json()["transaction"]["income_type"] == "gifts"
    # Re-sorting the ledger keeps your choice.
    from finance.pipeline import recategorize_all
    recategorize_all(st)
    assert st.get_transaction(mystery.fingerprint).income_type == "gifts"


def test_undo_puts_a_guessed_bonus_back(tmp_path):
    """Undoing "what kind of income?" on a bonus-sized deposit leaves Pearl's
    guess, and so its question, as they were: the card she reopened to
    answer again must still have something to ask (2026-10-26)."""
    from app import create_app
    from finance.review import for_store, ids_in
    app = create_app(str(tmp_path / "bonus.db"))
    st = app.config["STORE"]
    today = date.today()
    ingest(st, IngestResult(transactions=biweekly(today - timedelta(days=70), 4)
                            + [row(-9000, "PAYROLL ACME CORP BONUS", (today - timedelta(days=3)).isoformat(),
                                   category="Income")],
                            account_id="chq"))
    bonus = next(t for t in st.all_transactions() if t.description.endswith("BONUS"))
    assert bonus.income_type == "bonus"
    assert bonus.fingerprint in ids_in(for_store(st))
    c = app.test_client()
    r = c.put(f"/api/transactions/{bonus.fingerprint}/income-type", json={"kind": "salary"})
    assert bonus.fingerprint not in ids_in(for_store(st))
    assert c.post("/api/transactions/undo", json=r.get_json()["undo"]).status_code == 200
    back = st.get_transaction(bonus.fingerprint)
    assert (back.income_type, back.income_type_source) == ("bonus", "rule")
    assert bonus.fingerprint in ids_in(for_store(st))
