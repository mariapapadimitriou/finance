"""Split my part is a row in Options, where Split with others is on any
purchase, not the page's big button (product owner, 2026-11-25; S-01jr)."""

from pathlib import Path

SRC = (Path(__file__).resolve().parents[1]
       / "ios/Pearl/Views/Transactions/TransactionDetailView.swift").read_text()


def between(a, b):
    return SRC[SRC.index(a):SRC.index(b)]


def test_not_the_pages_button():
    primary = between("private var pagePrimary", "private var notATransferLink")
    assert "Split my part" not in primary and "splitting = true" not in primary


def test_in_split_with_others_place():
    # P2 (fewer taps): Split with others has its own card; on a joint
    # purchase Split my part takes its place.
    row = between("@ViewBuilder private var splitRow: some View", "/// P2a: one More row")
    assert "if canSplitJoint && (showsShareBar || jointCharge) {\n            APCard { jointSplitRow }" in row
    assert "} else if canSplit {" in row


def test_the_row_says_why_when_none_of_it_is_hers():
    row = between("private var jointSplitRow", "private func deposit(rest")
    assert '"None of it is yours to split."' in row and ".disabled(busy || none)" in row
    assert "Split it with friends" not in row
