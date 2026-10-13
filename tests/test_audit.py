"""Finding a purchase that landed in the ledger twice under two accounts.

The importer never merges across accounts, deliberately — two $12 lunches on
two cards are two lunches. That leaves one real gap: the same card arriving
from two sources, a PDF statement and then a Plaid backfill of the same
months. Nothing matches on merchant, because a printed statement and an API
do not write descriptors the same way, so only the amount and the date line up.

Which is why the account-level question comes first. Two cards in one wallet
share amounts constantly — the same coffee, the same fare — so a matching
amount across two *different* cards is a coincidence, not a duplicate.
Comparing rows only within account pairs that look like one card is what
keeps the real finding from being buried in those coincidences.
"""

import pytest

from finance import audit
from finance.models import Transaction


def txn(date, desc, amount, account="a", source="pdf", name=None):
    t = Transaction(date=date, description=desc, amount=amount,
                    account_id=account, account_name=name or account,
                    source=source)
    return t


AMOUNTS = [8.08, 23.73, 15.24, 31.00, 6.40, 44.10, 12.95, 9.60, 17.50, 5.09]


def duplicated_card(left="scotia_pdf", right="plaid_acct", desc_left="X",
                    desc_right="X", amounts=None):
    """One card under two ids: the same months, the same amounts, twice.

    A duplicate import is never two rows — it is a statement's worth of them,
    which is what lets the account-level check recognise the pair at all. A
    two-row fixture would be testing a situation the real one never produces.
    """
    rows = []
    for i, amount in enumerate(amounts or AMOUNTS):
        day = f"2025-11-{10 + i:02d}"
        rows.append(txn(day, desc_left, amount, account=left, source="pdf"))
        rows.append(txn(day, desc_right, amount, account=right, source="plaid"))
    return rows


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
        """One shared amount out of one is 100% and means nothing.

        And since the row-level list now follows the account-level answer,
        nothing is claimed at either level. A single matching charge between
        two accounts is not evidence that they are one card.
        """
        rows = [txn("2025-11-09", "COFFEE", 8.08, account="big", source="pdf"),
                txn("2025-11-09", "Coffee", 8.08, account="tiny", source="plaid")]
        for i, amount in enumerate([1.0, 2.0, 3.0, 4.0, 5.0, 6.0]):
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount, account="big"))
        assert audit.overlapping_accounts(rows) == []

    def test_a_partial_overlap_is_below_the_bar(self):
        """Half the smaller account shared is still two cards, not one."""
        rows = []
        for i, amount in enumerate(AMOUNTS):
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount, account="a"))
        for i, amount in enumerate(AMOUNTS[:5] + [90.1, 91.2, 92.3, 93.4, 94.5]):
            rows.append(txn(f"2025-11-{10 + i:02d}", "Y", amount, account="b"))
        assert audit.overlapping_accounts(rows) == []

    def test_a_statement_contained_in_a_backfill_is_recognised(self):
        """Six months of statement inside two years of Plaid: the smaller
        side is almost wholly contained, which is the shape to catch."""
        rows = duplicated_card()
        for i, amount in enumerate([70.1, 71.2, 72.3, 73.4, 74.5, 75.6]):
            rows.append(txn(f"2025-11-{20 + i:02d}", "extra", amount,
                            account="plaid_acct", source="plaid"))
        [overlap] = audit.overlapping_accounts(rows)
        assert overlap["overlap"] == 1.0

    def test_accounts_that_never_coexisted_are_skipped(self):
        """A closed card and its replacement share amounts but not months."""
        rows = [txn("2025-02-10", "A", 8.08, account="old"),
                txn("2026-02-10", "A", 8.08, account="new")]
        assert audit.overlapping_accounts(rows) == []
