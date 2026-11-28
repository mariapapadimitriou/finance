"""Twin build round 2, Cash flow (REDESIGN-18, -19, -20; boards G1-PaidWith,
G1-Add, G1-Months, G1-FilterOpen, G1-Results, G1-Days, G1-PConfirm,
G1-TxNote, G1-TxSheets, G1-MoneyIn, G1-NeedsMore, G1-PearlSorted,
G1-QuickMore, G1-QuickAsk, G1-TxPage) and the round's follow-ups, read from
the Swift source. Nothing here needs a simulator."""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "ios", "Pearl")


def read(*parts):
    with open(os.path.join(APP, *parts), encoding="utf-8") as f:
        return re.sub(r"//[^\n]*", "", f.read())


TX = ("Views", "Transactions")


class TestFollowUps(unittest.TestCase):
    def test_card_counts_its_own_month_and_has_no_streak(self):
        # CF-SCROLL (AP-CashFlow r7): the card's count is the month's own
        # open questions (6), the badge still everything (8); no mini streak.
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn("let open = review.shownAsks.filter { !$0.skipped }", tv)
        self.assertIn("by[String(ask.t.date.prefix(7)), default: 0] += 1", tv)
        self.assertIn("let count = month.flatMap { lookByMonth[$0] } ?? 0", tv)
        self.assertNotIn("SortStreak(", tv)
        self.assertNotIn("review.sortedToday + review.pearlSorted", tv)
        self.assertIn('case youSorted = "you_sorted"', read("API", "Models.swift"))
        rv = read("Views", "Review", "ReviewView.swift")
        self.assertNotIn("(review?.sortedToday ?? 0) + (review?.pearlSorted ?? 0)", rv)

    def test_pay_from_a_piggy_bank_is_parked(self):
        d = read(*TX, "TransactionDetailView.swift")
        self.assertIn("t.bankId != nil && !t.inflow", d)

    def test_your_plan_questions_are_parked(self):
        rv = read("Views", "Review", "ReviewView.swift")
        # Saved needs a Yes (2026-11-20): "Is X where you save?" is asked before the plan.
        self.assertIn('YourPlanGate.shown ? asks : asks.filter { $0.kind != .check || $0.item.key.hasPrefix("chk:saver:") }', rv)
        self.assertNotIn("review.asks", rv)
        self.assertNotIn("review?.asks", rv)
        qs = read("Views", "Review", "QuickSortView.swift")
        self.assertNotIn("review?.asks", qs)
        self.assertNotIn("review.asks", qs)
        tv = read(*TX, "TransactionsView.swift")
        # TEST-35: the count is the rows Needs a look lists (shownAsks), so
        # parked plan questions, trips and patterns stay out of it.
        self.assertIn("review.shownAsks.filter { !$0.skipped }", tv)
        self.assertIn("var listedOpen: Int { shownAsks.filter { !$0.skipped }.count }", rv)

    def test_cash_flow_opens_filtered_to_a_category(self):
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn("final class CashFlowFocus: ObservableObject", tv)
        self.assertIn(".onReceive(CashFlowFocus.shared.$request)", tv)
        self.assertIn("filters = request.category.map { TxFilters(categories: [$0]) } ?? TxFilters()", tv)
        home = read("Views", "Home", "HomeView.swift")
        self.assertIn("CashFlowFocus.shared.show(category: name, month: target.month)", home)


class TestBoards(unittest.TestCase):
    def test_paid_with_is_a_pearl_sheet(self):
        add = read(*TX, "AddTransactionSheet.swift")
        self.assertNotIn("Menu {", add)
        self.assertIn("struct PaidWithSheet: View", add)
        self.assertIn('option(id: "cash", face: "$", name: "Cash", line: "Not in a bank")', add)
        self.assertIn('Button("Cancel") { dismiss() }', add)
        self.assertIn('"Looks like one already there:"', add)

    def test_add_to_bills_has_no_stock_menus(self):
        bills = read(*TX, "AddToBillsSheet.swift")
        self.assertNotIn("Menu {", bills)
        self.assertIn("CFRadioSheet(", bills)

    def test_choose_a_month_answers_on_tap(self):
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn("Button { chosen = m; onDone(m) }", tv)
        self.assertNotIn('Button("Done") { onDone(chosen ?? current) }', tv)

    def test_filters_show_as_chips_each_with_its_clear(self):
        # CF-SCROLL (G1-Months T-67, G1-Scroll T-53): the card's chip and
        # Filters' chips under the card, each with its own ✕ (cf.css .fchip).
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn("CFChipWrap(chips: chipItems)", tv)
        self.assertIn("for chip in filters.chips(accounts: filterAccounts)", tv)
        # fix/filters-expanded: Accounts is a drill-in row again, All accounts first.
        self.assertIn('option("All accounts", on: filters.accounts.isEmpty)', tv)

    def test_results_states(self):
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn("CFLoadingRows()", tv)
        self.assertIn('CFState(title: "Couldn’t load your transactions", line: error, action: "Try again", warn: true)', tv)
        self.assertIn('CFBanner(text: "Getting your latest transactions…", busy: true)', tv)

    def test_leave_out_reason_is_optional(self):
        tv = read(*TX, "TransactionsView.swift")
        self.assertIn('needs: .nothing, identifier: "leave-out-reason", reveal: "Add a reason"', tv)
        self.assertIn('let reason = typed.isEmpty ? "Left out" : typed', tv)

    def test_confirm_sheet_is_the_a_plus_sheet(self):
        c = read("Views", "Components", "PearlConfirmSheet.swift")
        self.assertIn("APSheetTitle(title: title, close: onClose)", c)
        self.assertIn("APErrorLine(text: failed)", c)
        self.assertNotIn("CautionBanner(text: failed)", c)

    def test_days_sorted_together_options(self):
        cal = read(*TX, "CalendarView.swift")
        self.assertIn('title: "Days sorted together"', cal)
        self.assertIn('sub: "Dates, category or name"', cal)
        self.assertIn("destructive: true", cal)

    def test_purchase_page_sheets(self):
        d = read(*TX, "TransactionDetailView.swift")
        self.assertIn('primary: "Unlink", secondary: "Keep linked"', d)
        self.assertIn('message: "Pearl stops pairing them and asks what each one was."', d)
        self.assertIn('primary: "Delete \\(t.merchant)"', d)
        self.assertIn('Text("\\(note.count) of 200")', d)

    def test_needs_a_look_states(self):
        rv = read("Views", "Review", "ReviewView.swift")
        self.assertIn('"Only skipped ones left"', rv)
        self.assertIn('"Couldn’t load Needs a look"', rv)
        self.assertIn('"Undone. Back in Needs a look"', rv)
        self.assertIn('Text("Nothing yet")', rv)

    def test_quick_sort_card_says_one_line(self):
        qs = read("Views", "Review", "QuickSortView.swift")
        self.assertIn('"Tap the card to pick something else."', qs)
        self.assertIn('"\\(ask.t.name) varies, so just this one."', qs)
        self.assertIn("CardFace(dashed:", qs)


if __name__ == "__main__":
    unittest.main()
