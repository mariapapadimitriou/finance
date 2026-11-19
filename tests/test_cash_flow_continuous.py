"""CF-SCROLL (canvas v47, approved 2026-11-19): Cash flow is one continuous
list across months, the month card only chooses its own summary, Filters is
flat, and Quick sort's cards are one size with 56 pt circles."""

from __future__ import annotations

import re
from datetime import date, timedelta
from pathlib import Path

from tests.test_transactions_list import client, load, row  # noqa: F401  (fixture)

ROOT = Path(__file__).resolve().parent.parent
TX = ROOT / "ios/Pearl/Views/Transactions"
TV = (TX / "TransactionsView.swift").read_text()
SCROLL = (TX / "CashFlowScroll.swift").read_text()
QS = (ROOT / "ios/Pearl/Views/Review/QuickSortView.swift").read_text()
HOME = (ROOT / "ios/Pearl/Views/Home/HomeView.swift").read_text()


def _months_back(n: int) -> str:
    d = date.today().replace(day=1)
    for _ in range(n):
        d = (d - timedelta(days=1)).replace(day=1)
    return d.isoformat()[:7] + "-10"


# The server: pages run across months, newest first.

def test_pages_run_back_across_months_newest_first(client):  # noqa: F811
    load(client.st, *[row(5 + i, f"SHOP {i:02d}", account="card", kind="credit", category="Shopping",
                          when=_months_back(i // 4)) for i in range(12)])
    first = client.get("/api/transactions/list", query_string={"limit": 5}).get_json()
    assert first["total"] == 12 and len(first["transactions"]) == 5
    rest = client.get("/api/transactions/list", query_string={"limit": 5, "offset": 5}).get_json()
    last = client.get("/api/transactions/list", query_string={"limit": 5, "offset": 10}).get_json()
    rows = first["transactions"] + rest["transactions"] + last["transactions"]
    assert len({r["id"] for r in rows}) == 12
    dates = [r["date"] for r in rows]
    assert dates == sorted(dates, reverse=True)
    assert len({d[:7] for d in dates}) == 3


def test_a_card_chip_lists_exactly_what_the_card_adds_up(client):  # noqa: F811
    """Spent, Came in and Saved · a month: the rows the list gives for each
    add up to exactly the card's figure (shares, refunds, left-out and other
    months included in the data)."""
    month = date.today().isoformat()[:7]
    last = _months_back(1)
    ids = load(client.st,
               row(84.12, "LOBLAWS", account="card", kind="credit", category="Groceries", when=f"{month}-02"),
               row(120.00, "SUSHI NAMI", account="card", kind="credit", category="Dining out", when=f"{month}-03"),
               row(-20.00, "LOBLAWS REFUND", account="card", kind="credit", category="Groceries",
                   when=f"{month}-04"),
               row(61.20, "SHELL", account="card", kind="credit", category="Gas & Fuel", when=f"{month}-05"),
               row(-2150.00, "NORTHWIND PAYROLL", account="chq", category="Income", when=f"{month}-01"),
               row(-45.00, "E-TRANSFER FROM ANA", account="chq", category="Income", when=f"{month}-06"),
               row(500.00, "TO TANGERINE SAVINGS", account="chq", category="Saved", when=f"{month}-07"),
               row(-100.00, "FROM TANGERINE SAVINGS", account="chq", category="Saved", when=f"{month}-08"),
               row(200.00, "TFSA TOP UP", account="chq", category="Saved", when=f"{month}-09"),
               row(75.00, "COSTCO", account="card", kind="credit", category="Groceries", when=last),
               row(300.00, "TO SAVINGS LAST MONTH", account="chq", category="Saved", when=last))
    # Her share of a split, and a row she left out.
    assert client.put(f"/api/transactions/{ids['SUSHI NAMI']}/split", json={
        "mode": "amount", "people": [{"name": "Sam", "amount": 60.0}]}).status_code == 200
    assert client.put(f"/api/transactions/{ids['TFSA TOP UP']}/exclude",
                      json={"reason": "Not mine"}).status_code == 200
    assert client.put(f"/api/transactions/{ids['SHELL']}/exclude",
                      json={"reason": "Work"}).status_code == 200

    card = client.get("/api/transactions/list", query_string={"month": month, "limit": 1}).get_json()
    figures = {"spent": card["month_totals"]["spent"], "income": card["month_totals"]["income"],
               "saved": card["month_totals"]["saved"]}
    assert figures["spent"] > 0 and figures["income"] > 0 and figures["saved"] > 0
    for kind, figure in figures.items():
        got = client.get("/api/transactions/list",
                         query_string={"month": month, "kind": kind, "limit": 1000}).get_json()
        rows = got["transactions"]
        assert got["total"] == len(rows)
        assert all(r["date"][:7] == month for r in rows), kind
        assert round(sum(r["card_amount"] for r in rows), 2) == round(figure, 2), kind
        # The card's own totals are the same whatever the chip.
        assert got["month_totals"]["spent"] == figures["spent"]
        assert got["month_totals"]["income"] == figures["income"]
    saved = client.get("/api/transactions/list",
                       query_string={"month": month, "kind": "saved", "limit": 1000}).get_json()
    assert {r["description"] for r in saved["transactions"]} == {"TO TANGERINE SAVINGS", "FROM TANGERINE SAVINGS"}
    assert client.get("/api/transactions/list", query_string={"kind": "nope"}).status_code == 400


# The phone: one list, paged.

def test_the_list_asks_for_every_month_a_page_at_a_time():
    reload = TV[TV.index("    private func reload() async {"):TV.index("    /// A card chip's rows:")]
    assert 'p["month"]' not in reload
    assert 'p["offset"] = String(got.count)' in reload
    assert "private static let page = 200" in TV
    assert '.onAppear { Task { await loadMore() } }' in TV
    assert "LazyVStack(alignment: .leading, spacing: 0)" in TV
    assert "ForEach(blocks) { block in" in TV


def test_choosing_a_month_changes_only_the_card():
    months = TV[TV.index(".sheet(isPresented: $showMonths)"):][:400]
    assert "await loadCard()" in months and "reload()" not in months
    assert 'query: ["month": m, "limit": "1"]' in TV


def test_each_month_has_a_divider_and_sorts_group_within_it():
    build = SCROLL[SCROLL.index("static func build("):SCROLL.index("private static func dayBlocks")]
    assert "byMonth.keys.sorted(by: >)" in build
    assert ".divider(month: month, shown: !(i == 0 && hideFirst))" in build
    assert "categoryBlocks(rows, month: month" in build
    assert "CategoryPage(name: c.name, month: month" in TV


def test_the_month_pins_under_a_folding_bar_with_filters_and_add():
    assert "struct CFFoldedBar: View" in SCROLL
    bar = SCROLL[SCROLL.index("struct CFFoldedBar: View"):SCROLL.index("private struct CFBarButton")]
    assert '"Add a transaction"' in bar and '"Filters, on" : "Filters"' in bar
    assert "pin(month).offset(y: tracker.push)" in bar
    # Scrolling redraws only the bar: the tracker isn't this view's state.
    assert "@State private var tracker = CFScrollTracker()" in TV
    assert "@ObservedObject var tracker: CFScrollTracker" in bar


def test_card_figures_filter_by_month_and_kind():
    assert "case spent, saved, cameIn, look" in SCROLL
    assert 'var label: String { "\\(kind.label) \\u{00B7} \\(Format.monthName(month))" }' in SCROLL
    assert "kind.server != nil || (t.date.hasPrefix(month) && look.contains(t.id))" in SCROLL
    legend = TV[TV.index("    private var legend: some View {"):TV.index("    private func dot(")]
    assert "figure(.spent," in legend and "figure(.saved," in legend
    assert "figure(.leftover" not in legend
    assert "Capsule().strokeBorder(tone, lineWidth: 1.5)" in legend


def test_search_hides_the_card():
    assert "if !showCalendar && !inSearch { summaryCard" in TV


def test_filters_are_flat_with_no_month():
    sheet = TV[TV.index("struct FilterSheet: View {"):TV.index("struct FilterChipSection: View")]
    for gone in ("More filters", "monthRows", "Earlier months", "months: [String]", "initialMonth"):
        assert gone not in sheet, gone
    for title in ("Transaction type", "Spending type", "Accounts", "Category", "Only show", "Merchant", "Sort"):
        assert f'"{title}"' in sheet, title
    assert 'counted ? "Show \\(count(filters))" : "Show"' in sheet


def test_no_single_month_wording():
    assert "Nothing yet in" not in TV
    no_match = TV[TV.index("private var noMatchLine: String {"):][:700]
    assert "this month" not in no_match


def test_home_needs_a_look_has_no_streak():
    assert "SortStreak(" not in HOME


# Quick sort (QS-SAME).

def test_quick_sort_cards_are_one_size_and_never_grow():
    assert "static func cardHeight(room: CGFloat) -> CGFloat { min(420, max(room - 24, 280)) }" in QS
    face = QS[QS.index("private struct CardFace: ViewModifier"):][:1200]
    assert ".frame(height: height)" in face and ".clipped()" in face
    card = QS[QS.index("    private func card(_ ask: Ask) -> some View {"):QS.index("    private func cardHint(")]
    assert "lineLimit(3)" not in card
    assert "Text(t.name).font(Nacre.body).foregroundColor(Pearl.ink)\n                .lineLimit(1)" in card


def test_quick_sort_circles_keep_their_voiceover_words():
    assert "static let circle: CGFloat = 56" in QS
    buttons = QS[QS.index("    @ViewBuilder private var buttons: some View {"):QS.index("    /// QS-SAME: the circles' size.")]
    for label in ('label: "Skip"', 'label: "No"', '"Yes" : "Answer"'):
        assert label in buttons, label
    assert ".font(.system(size: 22, weight: .semibold))" in buttons
    assert ".frame(minWidth: 68, minHeight: 44)" in buttons
    assert "APSecondaryButtonStyle" not in buttons
    assert re.search(r"\.padding\(\.bottom, Self\.toastLift\)", QS)


def test_card_chips_use_the_servers_rows_for_the_card_figures():
    assert 'case .cameIn: return "income"' in SCROLL and 'case .saved: return "saved"' in SCROLL
    load = TV[TV.index("    private func loadCardRows() async {"):][:900]
    assert 'p["kind"] = kind' in load and 'p["month"] = c.month' in load
    assert "figure ? (cardRows ?? []) : rows" in TV
    # The old guess at Saved (a "savings" group) is gone.
    assert 't.group == "savings"' not in SCROLL


def test_long_cards_are_cut_into_lazy_slices_drawn_as_one():
    assert "static let slice = 50" in SCROLL
    cards = SCROLL[SCROLL.index("static func cards("):][:600]
    assert "top: i == 0, bottom: i + slice >= rows.count" in cards
    for build in ("dayBlocks", "groupBlocks"):
        body = SCROLL[SCROLL.index(f"private static func {build}"):][:900]
        assert "cards(" in body, build
    assert 'out += cards(rows, month: month, key: "all")' in SCROLL
    assert ".modifier(CFCardSlice(top: top, bottom: bottom))" in TV
