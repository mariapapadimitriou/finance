"""PDF statement parsing, and the credit handling that depends on it."""

import pytest

from finance.analytics import coverage_gaps, summary
from finance.categorize import apply_categories, categorize
from finance.ingest.pdf_source import (
    PdfSource, _resolve_year, parse_statement,
)
from datetime import date


class TestYearResolution:
    """Statement lines carry "Feb 19" with no year; the period supplies it."""

    def test_date_inside_the_period(self):
        got = _resolve_year("Mar 5", date(2025, 2, 21), date(2025, 3, 20))
        assert got == date(2025, 3, 5)

    def test_transaction_just_before_the_period_start(self):
        # A charge made before the period can post inside it.
        got = _resolve_year("Feb 19", date(2025, 2, 21), date(2025, 3, 20))
        assert got == date(2025, 2, 19)

    def test_period_spanning_a_year_boundary_picks_the_right_year(self):
        start, end = date(2024, 12, 21), date(2025, 1, 20)
        assert _resolve_year("Dec 28", start, end) == date(2024, 12, 28)
        assert _resolve_year("Jan 5", start, end) == date(2025, 1, 5)

    def test_impossible_date_is_rejected(self):
        assert _resolve_year("Feb 30", date(2025, 2, 21), date(2025, 3, 20)) is None

    def test_garbage_is_rejected(self):
        assert _resolve_year("nonsense", date(2025, 2, 21), date(2025, 3, 20)) is None


# A miniature statement in the real layout, including the awkward parts:
# a wallet continuation line, a credit with a trailing minus, and a
# description glued to its city.
STATEMENT = """\
StatementPeriod Feb 21, 2025 -Mar 20, 2025
StatementDate Mar 20, 2025
Account# 3773 XXXXXX 04876
Transactions since your last statement
TRANS. POST
REF.# DATE DATE DETAILS AMOUNT($)
001 Feb 19 Feb 21 RABBA #155 Q4 TORONTO ON 18.03
(APPLE PAY)
002 Feb 24 Feb 25 ARABICA (EATON) 001 TORONTO ON 20.23
(APPLE PAY)
003 Feb 28 Feb 28 PAYMENT FROM - *****10*6822 942.91-
004 Mar 13 Mar 15 IQ FOOD CO. FCP 213133251TORONTO ON 19.38
005 Mar 14 Mar 17 NATIONAL BOWL TORONTO ON 386.69
SUB-TOTAL CREDITS-3773 XXXXXX 04876 $942.91-
SUB-TOTAL DEBITS-3773 XXXXXX 04876 $444.33
"""


@pytest.fixture()
def parsed(monkeypatch):
    monkeypatch.setattr("finance.ingest.pdf_source.extract_text",
                        lambda data: STATEMENT)
    return parse_statement(b"%PDF-fake", "statement.pdf")


class TestStatementParsing:
    def test_all_transactions_found(self, parsed):
        assert len(parsed.transactions) == 5

    def test_wallet_continuation_lines_are_not_transactions(self, parsed):
        assert not any("APPLE PAY" in t.description for t in parsed.transactions)

    def test_years_come_from_the_statement_period(self, parsed):
        assert parsed.transactions[0].date == "2025-02-19"
        assert parsed.transactions[-1].date == "2025-03-14"

    def test_purchases_are_positive(self, parsed):
        rabba = next(t for t in parsed.transactions if "RABBA" in t.description)
        assert rabba.amount == 18.03

    def test_trailing_minus_marks_a_credit(self, parsed):
        payment = next(t for t in parsed.transactions if "PAYMENT" in t.description)
        assert payment.amount == -942.91

    def test_totals_reconcile_with_the_statement(self, parsed):
        debits = sum(t.amount for t in parsed.transactions if t.amount > 0)
        credits = -sum(t.amount for t in parsed.transactions if t.amount < 0)
        assert debits == pytest.approx(444.33)
        assert credits == pytest.approx(942.91)

    def test_description_glued_to_its_city_is_separated(self, parsed):
        iq = next(t for t in parsed.transactions if "IQ FOOD" in t.description)
        assert "213133251TORONTO" not in iq.description

    def test_account_identity_from_the_statement(self, parsed):
        assert "4876" in parsed.account_name
        assert parsed.account_id == "scotiabank_04876"

    def test_currency_is_cad(self, parsed):
        assert all(t.currency == "CAD" for t in parsed.transactions)

    def test_a_statement_with_no_period_is_reported_not_guessed(self, monkeypatch):
        monkeypatch.setattr("finance.ingest.pdf_source.extract_text",
                            lambda data: "some other document")
        r = parse_statement(b"%PDF-fake", "x.pdf")
        assert r.transactions == []
        assert any("statement period" in w.lower() for w in r.warnings)

    def test_a_scan_with_no_text_layer_says_so(self, monkeypatch):
        monkeypatch.setattr(
            "finance.ingest.pdf_source.extract_text",
            lambda data: "StatementPeriod Feb 21, 2025 -Mar 20, 2025\n")
        r = parse_statement(b"%PDF-fake", "scan.pdf")
        assert r.transactions == []
        assert any("scan" in w.lower() for w in r.warnings)


class TestCreditsAreNotSpending:
    """The regression that mattered most.

    A card payment that fails to categorize as a transfer nets against your
    purchases. On real statements that made total spending read 98% lower than
    it actually was, which is worse than showing nothing at all.
    """

    @pytest.mark.parametrize("description", [
        "PAYMENT FROM - *****10*6822",
        "PAYMENT THANK YOU",
        "ONLINE PAYMENT",
        "PRE-AUTHORIZED PAYMENT",
        "SCENE+ POINTS FOR CREDIT",
        "CREDIT BAL REFUND",
    ])
    def test_money_moving_onto_the_card_is_a_transfer(self, description):
        from finance.models import normalize_merchant
        category, _ = categorize(normalize_merchant(description), description)
        assert category == "Transfers", f"{description!r} landed in {category}"

    def test_payments_do_not_reduce_reported_spending(self, parsed):
        apply_categories(parsed.transactions)
        s = summary(parsed.transactions, {})
        # Purchases total 444.33; the 942.91 payment must not net against them.
        assert s["total_spend"] == pytest.approx(444.33)


class TestCoverageGaps:
    def test_missing_months_are_reported(self, parsed):
        from finance.models import Transaction
        rows = list(parsed.transactions)
        rows.append(Transaction(date="2025-06-04", description="NUTBAR",
                                amount=12.0, account_id="a"))
        apply_categories(rows)
        assert coverage_gaps(rows) == ["2025-04", "2025-05"]

    def test_gaps_are_excluded_from_the_monthly_average(self, parsed):
        """A month never imported is not a month of zero spending."""
        from finance.models import Transaction
        rows = [
            Transaction(date="2025-01-10", description="NUTBAR", amount=100.0,
                        account_id="a"),
            Transaction(date="2025-04-10", description="NUTBAR", amount=200.0,
                        account_id="a"),
        ]
        apply_categories(rows)
        s = summary(rows, {})
        # Feb and Mar were never imported. Counted as zero-spend months the
        # average would be 33.33; excluded (and with the partial latest month
        # left out as usual) only January remains.
        assert s["average_monthly_spend"] == pytest.approx(100.0)


class TestSourceStatus:
    def test_pdf_source_reports_itself(self):
        st = PdfSource().status()
        assert st.key == "pdf"
        assert st.setup_steps


class TestCategoryHabit:
    """A habit spread across many merchants, and the guard that keeps it honest."""

    def _rows(self, entries):
        from finance.models import Transaction
        rows = [Transaction(date=d, description=desc, amount=a, account_id="a")
                for d, desc, a in entries]
        apply_categories(rows)
        return rows

    def test_many_small_purchases_across_many_places_is_reported(self):
        from finance.insights.rules import category_habit
        from finance.insights.rules import _month_span
        # 40 lunches at 40 different restaurants over four months.
        entries = [(f"2025-0{1 + i % 4}-{(i % 27) + 1:02d}",
                    f"RESTAURANT {i} BISTRO TORONTO ON", 30.0) for i in range(40)]
        rows = self._rows(entries)
        found = category_habit(rows, _month_span(rows), covered=set())
        assert found, "a category-level habit should be reported"
        assert found[0].category == "Dining"
        assert "different places" in found[0].detail

    def test_a_category_dominated_by_one_purchase_is_not_a_habit(self):
        """Two concert tickets are an event, not a spending habit."""
        from finance.insights.rules import category_habit, _month_span
        entries = [("2025-01-05", "TICKETMASTER CANADA TORONTO ON", 1029.0),
                   ("2025-01-05", "TICKETMASTER CANADA TORONTO ON", 569.5)]
        entries += [(f"2025-0{1 + i % 4}-{(i % 27) + 1:02d}",
                     f"CINEPLEX {i} TORONTO ON", 12.0) for i in range(14)]
        rows = self._rows(entries)
        found = category_habit(rows, _month_span(rows), covered=set())
        assert all(f.category != "Entertainment" for f in found), \
            "a category carried by two big one-offs must not be called a habit"

    def test_spending_is_not_counted_twice(self):
        """A category already reported per-merchant is skipped here."""
        from finance.insights.rules import category_habit, _month_span
        entries = [(f"2025-0{1 + i % 4}-{(i % 27) + 1:02d}",
                    f"RESTAURANT {i} BISTRO TORONTO ON", 30.0) for i in range(40)]
        rows = self._rows(entries)
        span = _month_span(rows)
        assert category_habit(rows, span, covered={"Dining"}) == []
