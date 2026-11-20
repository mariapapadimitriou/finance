"""Needs a look from Cash flow (product owner, after #398): the month card's
"N need a look" row is one tap target with a chevron that opens the Needs a
look page (ReviewView, G1-NeedsALook). No Sort capsule, no need-a-look list
filter. Quick sort stays on that page's top card, on Home's Sort now, and
pops up on open with only what's new. Read from the Swift source; nothing
here needs a simulator."""

import re
from pathlib import Path

APP = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def code(path):
    return re.sub(r"//[^\n]*", "", (APP / path).read_text(encoding="utf-8"))


TV = code("Views/Transactions/TransactionsView.swift")
SCROLL = code("Views/Transactions/CashFlowScroll.swift")
REVIEW = code("Views/Review/ReviewView.swift")
QS = code("Views/Review/QuickSortView.swift")
HOME = code("Views/Home/HomeView.swift")
APPV = code("App/PearlApp.swift")


def test_the_card_row_opens_needs_a_look():
    assert "CFLookRow(count: count) { showingLook = true }" in TV
    assert ".navigationDestination(isPresented: $showingLook) { ReviewView() }" in TV


def test_the_card_has_no_sort_and_no_look_filter():
    row = SCROLL[SCROLL.index("struct CFLookRow"):]
    assert row.count("Button(") == 1                       # one tap target
    assert 'Image(systemName: "chevron.right")' in row
    assert "Sort" not in row.replace("Needs a look", "")
    assert "pickOnCard(.look)" not in TV and "case .look" not in SCROLL
    # Cash flow doesn't open Quick sort itself any more.
    assert "QuickSortView(" not in TV and "api/quick-sort" not in TV


def test_spent_saved_came_in_still_filter():
    assert "case spent, saved, cameIn\n" in SCROLL
    assert "pick: { pickOnCard($0) }" in TV


def test_needs_a_look_has_quick_sort_on_top():
    header = REVIEW[REVIEW.index("private var header: some View"):]
    assert "QuickSortCard(" in header and "sorting = true" in header
    assert "QuickSortView(asks: quick" in REVIEW


def test_home_sort_now_still_opens_quick_sort():
    assert 'Button("Sort now", action: onSort)' in HOME
    assert 'api.get("api/quick-sort", query: ["all": "1"])' in HOME


def test_on_open_quick_sort_deals_only_whats_new():
    offer = APPV[APPV.index("private func offerQuickSort()"):APPV.index("private func page<")]
    assert "prompt.show" in offer
    assert "quickSort = prompt.newAsks" in offer
    assert "quickSortPatterns = prompt.newPatterns" in offer
    assert "quickSortTrips = prompt.newTrips" in offer
    assert "guard !offered else { return }" in offer        # once per launch
    assert "case show, review, new" in QS


def test_quick_sort_marks_its_pattern_and_trip_cards_seen():
    begin = QS[QS.index("private func begin() async"):]
    begin = begin[:begin.index("\n    }\n")]
    assert "patterns.map(\\.key) + trips.map(\\.key)" in begin
    assert 'var key: String { "pat:" + id }' in QS
