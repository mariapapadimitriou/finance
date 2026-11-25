"""Round 5 minors (testingBOT TEST-35 to TEST-46) and the Pearl date sheet
(G0-DateSheet, DP-01 to DP-03): source checks for the iPhone app."""

from __future__ import annotations

import pathlib
import re

PEARL = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def read(*parts: str) -> str:
    return (PEARL.joinpath(*parts)).read_text(encoding="utf-8")


def every_swift() -> dict[str, str]:
    return {str(p.relative_to(PEARL)): p.read_text(encoding="utf-8") for p in PEARL.rglob("*.swift")}


# ── G0-DateSheet ────────────────────────────────────────────────────────────

def test_no_stock_date_picker_anywhere():
    """TEST-46: every date is picked on the Pearl date sheet."""
    for name, src in every_swift().items():
        code = re.sub(r"//.*", "", src)
        assert not re.search(r"\bDatePicker\s*\(", code), name


def test_date_sheet_parts():
    s = read("Views", "Components", "PearlDateSheet.swift")
    # The readout is the real date, "Tue, Nov 17"; Done writes it; Close keeps the old one.
    assert 'formatter("EEEMMMd")' in s and "Pearl.display(.title2)" in s
    assert 'PearlSheetButtons(primary: "Done")' in s and "selection = draft" in s
    assert "APSheetTitle(title: title) { dismiss() }" in s
    # Six rows of seven, always; 44 pt days; the arrows' words.
    assert "ForEach(0..<6" in s and "while out.count < 42" in s
    assert ".frame(width: 44, height: 44)" in s
    assert '"Previous month"' in s and '"Next month"' in s and ".opacity(enabled ? 1 : 0.35)" in s
    # Out of range: muted at 40%, not tappable, hidden from VoiceOver.
    assert "Pearl.muted.opacity(0.4)" in s and ".disabled(!allowed)" in s and ".accessibilityHidden(!allowed)" in s
    # Today first, then the day; selected as a trait.
    assert '(today ? "Today, " : "") + PearlDateText.spoken(day)' in s
    # Motion: a selection haptic; Reduce Motion a 200 ms cross-fade.
    assert "UISelectionFeedbackGenerator().selectionChanged()" in s
    assert ".easeInOut(duration: 0.2)" in s and "if reduceMotion { return .opacity }" in s
    # No red.
    assert "danger" not in s


def test_every_date_field_opens_the_sheet():
    add = read("Views", "Transactions", "AddTransactionSheet.swift")
    assert 'title: "When was it?", selection: $day,\n                        range: .pastOnly, quickPicks: true' in add
    bills = read("Views", "Transactions", "AddToBillsSheet.swift")
    assert 'title: "When is it due next?", selection: $next,\n                        range: .todayOnward)' in bills
    split = read("Views", "Transactions", "SplitFlow.swift")
    assert 'title: "When did \\(person.name) pay you?"' in split and "range: .pastOnly, quickPicks: true" in split
    pay = read("Views", "Onboarding", "PayAndBillsView.swift")
    assert pay.count('title: "When is it due next?"') == 2 and pay.count("range: .todayOnward") == 2
    cal = read("Views", "Transactions", "CalendarView.swift")
    assert 'title: "Last day", date: $to,\n                                     range: PearlDateRange(earliest: from, latest: Date()))' in cal
    assert 'title: "First day", date: $from, range: .pastOnly)' in cal


# ── The minors ──────────────────────────────────────────────────────────────

def test_35_one_number():
    rv = read("Views", "Review", "ReviewView.swift")
    assert "var listedOpen: Int { shownAsks.filter { !$0.skipped }.count }" in rv
    assert "reviewCount = review.listedOpen" in read("App", "PearlApp.swift")


def test_41_months_say_their_result():
    tv = read("Views", "Transactions", "TransactionsView.swift")
    assert 'api.get("api/transactions/months")' in tv


def test_42_edit_split_opens_on_edit_split():
    split = read("Views", "Transactions", "SplitFlow.swift")
    assert 'if t.splitting != nil { return "Edit split" }' in split
    page = read("Views", "Transactions", "TransactionDetailView.swift")
    assert "SplitSheet(t: t, api: app.api, recent: recent, with: t.splitting?.people.map(\\.name),\n                       onHold:" in page


def test_43_account_marks_and_digits():
    add = read("Views", "Transactions", "AddTransactionSheet.swift")
    assert "APFace.initials(AccountWords.bank(a))" in add
    assert 'digits.isEmpty ? nil : "\\u{2022}\\u{2022}" + digits' in add


def test_44_rules_empty_state():
    rules = read("Views", "Profile", "CategoriesRulesView.swift")
    assert "Turn on Always for a shop, and it shows up here." in rules
    assert "Do the same for every…" not in rules


def test_45_select_target_and_guess_said_once():
    ap = read("Theme", "APlus.swift")
    assert ".frame(minWidth: 44, minHeight: 44)" in ap
    tv = read("Views", "Transactions", "TransactionsView.swift")
    chip = tv[tv.index("struct GuessChip"):tv.index("struct SelectTick")]
    assert ".accessibilityElement(children: .ignore)" in chip


def test_46_smaller_things():
    menus = read("Views", "Transactions", "SplitMenus.swift")
    # REFRESH-18 (S-40b2): the payments are a card of their own, still with no
    # label and no card when nothing is paid.
    assert "if !links.isEmpty {\n            APSheetLabel(text: p.settledInFull ? \"Paid with\" : \"Paid so far\")\n" \
           "            APOptionCard {\n                ForEach(Array(links.enumerated())" in menus
    assert "if !links.isEmpty { APSheetLabel(text: \"Paid so far\") }\n                APOptionCard {\n" \
           "                    ForEach(links)" in menus
    parts = read("Views", "Transactions", "PartsFlow.swift")
    assert "tickedShares.count + unsplitPaid.count > 0\n            && tickedShares.allSatisfy" in parts
    assert "private var likelyUnsplit: [UnsplitRow]" in parts
    split = read("Views", "Transactions", "SplitFlow.swift")
    assert "case .share: out.append(.yours)" not in split
    tv = read("Views", "Transactions", "TransactionsView.swift")
    assert 'CFGlassButton(label: "Add a transaction", action: { adding = true })' in tv
    answer = read("Views", "Review", "AnswerSheet.swift")
    assert "leadsWithLikely: !(fromPage && ask.kind == .category) || otherGuess" in answer


# ── Round 6 follow-ups ──────────────────────────────────────────────────────

def test_r6_needs_a_look_card_counts_the_rows():
    rv = read("Views", "Review", "ReviewView.swift")
    assert "+ (review?.tripAsks.count ?? 0) : quick.count," in rv
    assert "QuickSortCard(count: quick.count + (review?.patternAsks" not in rv


def test_r6_statement_accounts_keep_their_digits():
    acc = read("Views", "Profile", "AccountsViews.swift")
    assert '(listPill(a) == nil || a.isHand || a.status == "manual") ? line(a) : ""' in acc


def test_r6_other_guess_leads_with_yes():
    answer = read("Views", "Review", "AnswerSheet.swift")
    assert '(ask.item.guess?.text ?? (otherGuess ? "Other" : nil))' in answer


def test_r6_months_are_prefetched():
    tv = read("Views", "Transactions", "TransactionsView.swift")
    assert "Task { await MonthSheet.prefetch(app.api) }" in tv
    assert "_left = State(initialValue: Self.remembered)" in tv
