"""Finding a purchase that landed in the ledger twice under two accounts.

The importer never merges across accounts, deliberately — two $12 lunches on
two cards are two lunches. That leaves one real gap: the same card arriving
from two sources, a PDF statement and then a Plaid backfill of the same
months. Nothing matches on merchant, because a printed statement and an API
do not write descriptors the same way, so only the amount and the date line up.
"""

import pytest

from finance import audit
from finance.models import Transaction


def txn(date, desc, amount, account="a", source="pdf", name=None):
    t = Transaction(date=date, description=desc, amount=amount,
                    account_id=account, account_name=name or account,
                    source=source)
    return t


class TestCrossAccountDuplicates:
    def test_the_same_card_from_two_sources_is_found(self):
        """The case that matters: a statement, then Plaid backfilling it."""
        rows = [
            txn("2025-11-14", "MOS MOS COFFEE 211849841 TORONTO ON", 8.08,
                account="scotia_pdf", source="pdf"),
            txn("2025-11-14", "Mos Mos Coffee", 8.08,
                account="plaid_acct", source="plaid"),
        ]
        found = audit.cross_account_duplicates(rows)
        assert len(found) == 1
        assert found[0]["amount"] == 8.08
        assert {r["source"] for r in found[0]["rows"]} == {"pdf", "plaid"}

    def test_a_posting_delay_between_sources_is_tolerated(self):
        """A statement shows the posted date, Plaid usually the authorised one."""
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-17", "COFFEE", 8.08, account="b", source="plaid")]
        assert len(audit.cross_account_duplicates(rows)) == 1

    def test_far_apart_is_not_a_duplicate(self):
        rows = [txn("2025-11-01", "COFFEE", 8.08, account="a"),
                txn("2025-11-28", "COFFEE", 8.08, account="b")]
        assert audit.cross_account_duplicates(rows) == []

    def test_two_cards_are_left_to_the_importer(self):
        """Same account is the importer's job and it already did it."""
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-14", "COFFEE", 8.08, account="a")]
        assert audit.cross_account_duplicates(rows) == []

    def test_the_same_amount_at_different_shops_still_surfaces(self):
        """Reported, not removed — $23.73 twice in a week on two cards is
        usually a coincidence, and the person decides."""
        rows = [txn("2025-11-14", "IQ FOOD CO", 23.73, account="a"),
                txn("2025-11-15", "SOUP NUTSY", 23.73, account="b")]
        found = audit.cross_account_duplicates(rows)
        assert len(found) == 1
        assert found[0]["same_merchant"] is False

    def test_the_likeliest_are_listed_first(self):
        rows = [
            txn("2025-11-14", "IQ FOOD CO", 23.73, account="a"),
            txn("2025-11-18", "SOUP NUTSY", 23.73, account="b"),
            txn("2025-11-14", "MOS MOS COFFEE", 8.08, account="a"),
            txn("2025-11-14", "MOS MOS COFFEE", 8.08, account="b"),
        ]
        found = audit.cross_account_duplicates(rows)
        assert found[0]["same_merchant"] is True
        assert found[0]["days_apart"] == 0

    def test_refunds_and_payments_are_skipped(self):
        """A negative amount is money coming back; two of them are not a
        double charge."""
        rows = [txn("2025-11-14", "REFUND", -50.0, account="a"),
                txn("2025-11-14", "REFUND", -50.0, account="b")]
        assert audit.cross_account_duplicates(rows) == []

    def test_a_clean_ledger_reports_nothing(self):
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-15", "LUNCH", 23.73, account="b")]
        assert audit.cross_account_duplicates(rows) == []


class TestAccountOverlap:
    """The coarser read: did two account ids cover the same card?"""

    def test_the_same_card_twice_shows_a_high_overlap(self):
        rows = []
        for i, amount in enumerate([8.08, 23.73, 15.24, 31.00, 6.40, 44.10,
                                    12.95]):
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount,
                            account="scotia_pdf", source="pdf"))
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount,
                            account="plaid_acct", source="plaid"))
        [overlap] = audit.overlapping_accounts(rows)
        assert overlap["overlap"] == 1.0
        assert overlap["same_source"] is False

    def test_two_genuinely_different_cards_do_not(self):
        rows = [txn("2025-11-10", "A", 8.08, account="card1"),
                txn("2025-11-11", "B", 23.73, account="card1"),
                txn("2025-11-10", "C", 91.10, account="card2"),
                txn("2025-11-12", "D", 44.20, account="card2")]
        assert audit.overlapping_accounts(rows) == []

    def test_a_tiny_account_makes_no_claim(self):
        """One shared amount out of one is 100% and means nothing. The
        row-level list still reports the charge itself."""
        rows = [txn("2025-11-09", "COFFEE", 8.08, account="big", source="pdf"),
                txn("2025-11-09", "Coffee", 8.08, account="tiny", source="plaid")]
        for i, amount in enumerate([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount, account="big"))
        assert audit.overlapping_accounts(rows) == []
        assert len(audit.cross_account_duplicates(rows)) == 1

    def test_accounts_that_never_coexisted_are_skipped(self):
        """A closed card and its replacement share amounts but not months."""
        rows = [txn("2025-02-10", "A", 8.08, account="old"),
                txn("2026-02-10", "A", 8.08, account="new")]
        assert audit.overlapping_accounts(rows) == []


class TestReport:
    def test_it_says_what_it_checked_and_what_it_will_not_do(self):
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-14", "Coffee", 8.08, account="b", source="plaid")]
        out = audit.report(rows)
        assert out["checked"] == 2
        assert out["duplicate_count"] == 1
        assert "not removed" in out["note"]

    def test_the_list_is_capped_but_the_count_is_not(self):
        """A truncated list must not read as a smaller problem."""
        rows = []
        for i in range(150):
            rows.append(txn("2025-11-14", "X", 10.0 + i, account="a"))
            rows.append(txn("2025-11-14", "X", 10.0 + i, account="b"))
        out = audit.report(rows)
        assert len(out["duplicates"]) == 100
        assert out["duplicate_count"] == 150
