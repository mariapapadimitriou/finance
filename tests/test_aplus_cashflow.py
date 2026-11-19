"""A+ restyle, Cash flow (REDESIGN-08, -09, -14; boards AP-CashFlow,
AP-Transaction, AP-Sheet, G1-*, G2-SplitCard): the approved decisions,
read from the Swift source. Nothing here needs a simulator."""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "ios", "Pearl")


def read(*parts):
    with open(os.path.join(APP, *parts), encoding="utf-8") as f:
        return f.read()


def code(text):
    return re.sub(r"//[^\n]*", "", text)


class TestCashFlow(unittest.TestCase):
    def setUp(self):
        self.tv = code(read("Views", "Transactions", "TransactionsView.swift"))

    def test_profile_circle_on_the_title_row(self):
        self.assertIn('Text("Cash flow")', self.tv)
        self.assertIn("ProfileCircle()", self.tv)

    def test_need_a_look_has_the_mini_streak_and_a_tint_chip(self):
        self.assertIn("SortStreak(sorted: reviewSorted, toSort: reviewToSort, mini: true)", self.tv)
        self.assertIn("CFCount(n: reviewCount)", self.tv)
        kit = code(read("Views", "Transactions", "CashFlowKit.swift"))
        count = kit[kit.index("struct CFCount"):kit.index("struct CFChip")]
        self.assertIn("Pearl.action", count)
        self.assertNotIn("Pearl.danger", count)

    def test_filters_dot_is_ink(self):
        dot = self.tv[self.tv.index("if filtersOn {\n                        Circle()"):][:200]
        self.assertIn("Pearl.ink", dot)
        self.assertNotIn("Pearl.danger", dot)

    def test_search_is_a_well(self):
        self.assertIn(".wellStyle(focused: searching, capsule: true)", self.tv)

    def test_left_out_amount_has_no_sign(self):
        self.assertIn("return t.notCounted ? amount(t.amount) : money(t)", self.tv)

    def test_month_bar_spent_is_plum(self):
        self.assertIn("Capsule().fill(Pearl.moneyOut)", self.tv)


class TestTransactionPage(unittest.TestCase):
    def setUp(self):
        self.tdv = code(read("Views", "Transactions", "TransactionDetailView.swift"))

    def test_no_line_repeating_always(self):
        self.assertNotIn("purchases go to", self.tdv)
        self.assertIn("alwaysToggle(sub: nil)", self.tdv)

    def test_guess_is_a_dashed_rose_card(self):
        self.assertIn("GuessCardSurface(dashed: still)", self.tdv)
        surface = self.tdv[self.tdv.index("struct GuessCardSurface"):]
        self.assertIn("strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5", surface)

    def test_guess_from_the_list_hides_the_tab_bar(self):
        self.assertIn(".modifier(GuessHidesTabBar(on: guessFromList))", self.tdv)
        self.assertIn('Button("Skip")', self.tdv)

    def test_split_card_has_the_paid_back_bar(self):
        flow = code(read("Views", "Transactions", "SplitFlow.swift"))
        self.assertIn("PaidBackBar(segments: barSegments, spoken: barSpoken)", flow)
        self.assertIn('"See who else owes you"', flow)


class TestSheetsAndSorting(unittest.TestCase):
    def test_change_category_banner_is_one_line(self):
        cs = code(read("Views", "Transactions", "CategorySheet.swift"))
        self.assertIn('"Also moves the \\(others) earlier ones"', cs)
        self.assertIn('"Allowance \\(delta > 0 ? "+" : "\\u{2212}")\\(Format.whole(abs(delta)))"', cs)
        self.assertIn("CFBanner(text: line)", cs)

    def test_category_page_shows_its_icon(self):
        page = code(read("Views", "Transactions", "CategoryPage.swift"))
        self.assertIn("CFIcon(symbol: CategorySheet.symbol(for: name)", page)

    def test_add_a_transaction_fields_are_wells(self):
        add = code(read("Views", "Transactions", "AddTransactionSheet.swift"))
        self.assertIn('PearlField(label: "Name", placeholder: "Where was it?"', add)
        self.assertIn("APlus.well", add)

    def test_quick_sort_streak_on_top_and_no_notes(self):
        qs = code(read("Views", "Review", "QuickSortView.swift"))
        self.assertIn("SortStreak(sorted: sortedSoFar, toSort: remaining)", qs)
        self.assertNotIn("OwnBody { cardLines }", qs)
        self.assertIn('sorted > 1 ? "Sorted \\(sorted) · Always \\(label)" : "Always \\(label)"', qs)

    def test_pearl_sorted_opens_needs_a_look_on_pearl_sorted(self):
        ps = code(read("Views", "Review", "PearlSortsViews.swift"))
        self.assertIn('ReviewView(startFilter: "pearl")', ps)

    def test_never_safe_to_spend(self):
        for path in [("Views", "Transactions", "TransactionsView.swift"),
                     ("Views", "Transactions", "CashFlowKit.swift"),
                     ("Views", "Review", "QuickSortView.swift")]:
            self.assertNotIn("safe to spend", read(*path).lower())


if __name__ == "__main__":
    unittest.main()
