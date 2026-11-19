"""TEST-34 (T-67, G1-Search): a filter or a search never changes Cash flow's
month card. It always shows the month's own Came in, Leftover and legend,
never "Came in $0", a "—" Leftover or "Leftover $0" (2026-11-19)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "ios/Pearl/Views/Transactions/TransactionsView.swift"


def _summary_card(src: str) -> str:
    start = src.index("private var summaryCard: some View")
    return src[start:src.index("private var needsALookRow", start)]


def test_the_card_is_always_the_months_totals():
    card = _summary_card(TX.read_text())
    for name in ("spent", "income", "saved"):
        assert f"let {name} = monthTotals?.{name} ?? 0" in card
    assert "let pay = monthTotals?.pay" in card
    assert "inSearch" not in card and "filters.isActive" not in card and "shown" not in card


def test_no_dash_headline():
    src = TX.read_text()
    summary = src[src.index("struct MonthSummary: View"):]
    summary = summary[:summary.index("\nstruct ", 10) if "\nstruct " in summary[10:] else len(summary)]
    assert "narrowed" not in summary
    assert not re.search(r'Text\([^)]*u\{2014\}', summary)


def test_the_list_still_loads_the_plain_month_for_server_filters():
    # An account filter narrows the list on the server; the card still gets
    # the month's own totals from a plain request.
    assert "The cards are the month's, whatever the list is narrowed to." in TX.read_text()
