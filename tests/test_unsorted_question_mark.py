"""A transaction that's Not sorted yet: its card leads with a dashed ❓, like
a guess, and drops the "Saved or spent? Tell us" line (product owner,
2026-11-26)."""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "ios/Pearl/Views/Transactions/TransactionDetailView.swift").read_text()


def _asking_card() -> str:
    start = SRC.index("private var askingCard: some View")
    return SRC[start:SRC.index("// MARK: Linked transactions", start)]


def test_not_sorted_yet_leads_with_a_dashed_question_mark():
    card = _asking_card()
    assert 'if t.label == "Not sorted yet"' in card
    assert "UnsortedMark()" in card
    mark = SRC[SRC.index("struct UnsortedMark: View"):]
    mark = mark[:mark.index("\n}\n")]
    assert 'Text("❓")' in mark
    assert "dash: [5, 3]" in mark


def test_not_sorted_yet_has_no_tell_us_line():
    card = _asking_card()
    branch = card[card.index('if t.label == "Not sorted yet"'):card.index("} else {")]
    assert "t.note" not in branch and "sub:" not in branch


def test_whose_has_no_tell_us_line():
    card = _asking_card()
    branch = card[card.index('} else if t.label == "Whose?"'):]
    branch = branch[:branch.index("} else {")]
    assert "row(title: t.label, chevron: true)" in branch
