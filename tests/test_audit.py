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


class TestCrossAccountDuplicates:
    def test_the_same_card_from_two_sources_is_found(self):
        """The case that matters: a statement, then Plaid backfilling it."""
        rows = duplicated_card(desc_left="MOS MOS COFFEE 211849841 TORONTO ON",
                               desc_right="Mos Mos Coffee")
        found = audit.cross_account_duplicates(rows)
        assert len(found) == len(AMOUNTS)
        assert {r["source"] for r in found[0]["rows"]} == {"pdf", "plaid"}

    def test_a_posting_delay_between_sources_is_tolerated(self):
        """A statement shows the posted date, Plaid usually the authorised one."""
        rows = duplicated_card()
        # Shift every Plaid row three days later, as a posting delay would.
        for t in rows[1::2]:
            t.date = f"2025-11-{int(t.date[-2:]) + 3:02d}"
        assert len(audit.cross_account_duplicates(rows)) == len(AMOUNTS)

    def test_far_apart_is_not_a_duplicate(self):
        rows = duplicated_card()
        for t in rows[1::2]:
            t.date = f"2025-12-{int(t.date[-2:]):02d}"      # a month later
        assert audit.cross_account_duplicates(rows) == []

    def test_two_cards_are_left_to_the_importer(self):
        """Same account is the importer's job and it already did it."""
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-14", "COFFEE", 8.08, account="a")]
        assert audit.cross_account_duplicates(rows) == []

    def test_two_real_cards_sharing_an_amount_are_not_a_duplicate(self):
        """The noise this exists to suppress.

        Two cards in one wallet buy the same $23.73 lunch in the same week all
        the time. Calling that a duplicate is wrong, and at the volume it
        happens it hides the findings that are real.
        """
        rows = [txn("2025-11-14", "IQ FOOD CO", 23.73, account="td_visa"),
                txn("2025-11-15", "SOUP NUTSY", 23.73, account="ws_card")]
        assert audit.cross_account_duplicates(rows) == []

    def test_not_even_the_same_shop_on_the_same_day(self):
        """Two cards, one coffee shop, one price — still two coffees."""
        rows = [txn("2025-11-14", "MOS MOS COFFEE", 8.08, account="td_visa"),
                txn("2025-11-14", "MOS MOS COFFEE", 8.08, account="ws_card")]
        assert audit.cross_account_duplicates(rows) == []

    def test_a_wallet_full_of_coincidences_reports_nothing(self):
        """Two real cards, overlapping months, a third of their amounts
        shared — which is ordinary, and below the bar for one card."""
        rows = []
        for i, amount in enumerate(AMOUNTS):
            rows.append(txn(f"2025-11-{10 + i:02d}", "X", amount,
                            account="td_visa"))
        for i, amount in enumerate(AMOUNTS[:3] + [99.0, 88.5, 77.25, 66.1]):
            rows.append(txn(f"2025-11-{10 + i:02d}", "Y", amount,
                            account="ws_card"))
        assert audit.overlapping_accounts(rows) == []
        assert audit.cross_account_duplicates(rows) == []

    def test_the_likeliest_are_listed_first(self):
        rows = duplicated_card(desc_left="X", desc_right="X")
        # One pair the descriptors disagree on, four days apart.
        rows.append(txn("2025-11-25", "IQ FOOD CO", 55.55, account="scotia_pdf"))
        rows.append(txn("2025-11-29", "SOUP NUTSY", 55.55, account="plaid_acct",
                        source="plaid"))
        found = audit.cross_account_duplicates(rows)
        assert found[0]["same_merchant"] is True
        assert found[0]["days_apart"] == 0
        assert found[-1]["same_merchant"] is False

    def test_refunds_and_payments_are_skipped(self):
        """A negative amount is money coming back; two of them are not a
        double charge."""
        rows = duplicated_card()
        rows.append(txn("2025-11-14", "REFUND", -50.0, account="scotia_pdf"))
        rows.append(txn("2025-11-14", "REFUND", -50.0, account="plaid_acct",
                        source="plaid"))
        assert all(f["amount"] > 0 for f in audit.cross_account_duplicates(rows))

    def test_a_clean_ledger_reports_nothing(self):
        rows = [txn("2025-11-14", "COFFEE", 8.08, account="a"),
                txn("2025-11-15", "LUNCH", 23.73, account="b")]
        assert audit.cross_account_duplicates(rows) == []

    def test_an_explicit_empty_pair_set_compares_nothing(self):
        assert audit.cross_account_duplicates(duplicated_card(), set()) == []


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
        assert audit.cross_account_duplicates(rows) == []

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


class TestReport:
    def test_it_says_what_it_checked_and_what_it_will_not_do(self):
        rows = duplicated_card()
        out = audit.report(rows)
        assert out["checked"] == len(rows)
        assert out["duplicate_count"] == len(AMOUNTS)
        assert len(out["account_overlaps"]) == 1
        assert "not removed" in out["note"]

    def test_the_note_explains_why_two_cards_are_absent(self):
        """Someone looking for a pair they expected needs to know why."""
        out = audit.report(duplicated_card())
        assert "two different cards" in out["note"].lower()

    def test_the_list_is_capped_but_the_count_is_not(self):
        """A truncated list must not read as a smaller problem."""
        rows = []
        for i in range(150):
            rows.append(txn("2025-11-14", "X", 10.0 + i, account="a"))
            rows.append(txn("2025-11-14", "X", 10.0 + i, account="b",
                            source="plaid"))
        out = audit.report(rows)
        assert len(out["duplicates"]) == 100
        assert out["duplicate_count"] == 150
