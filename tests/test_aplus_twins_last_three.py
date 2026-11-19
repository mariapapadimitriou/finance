"""The last three approved Claude Design twins, read from the Swift source:
PP-01's load error (G2-ALink), TP-04 and TP-05 (G2b-JointIn, rethought).
Nothing here needs a simulator."""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "ios", "Pearl")
TX = ("Views", "Transactions")


def read(*parts):
    with open(os.path.join(APP, *parts), encoding="utf-8") as f:
        return re.sub(r"//[^\n]*", "", f.read())


def between(src, start, end):
    i = src.index(start)
    return src[i:src.index(end, i + len(start))]


class TestWhoPaidLoadError(unittest.TestCase):
    """PP-01 (G2-ALink): Couldn't load who owes you, with Try again."""

    def setUp(self):
        self.src = read(*TX, "JointPaybackViews.swift")
        self.picker = between(self.src, "struct WhoPaidPicker", "struct WhoPaidAskSheet")

    def test_a_failed_load_is_an_error_not_an_empty_list(self):
        load = between(self.picker, "private func load()", "static func onSplit")
        self.assertIn('try await api.get("api/people/recent")', load)
        self.assertNotIn("try? await", load)
        self.assertIn("loadFailed = true", load)
        self.assertIn("catch is CancellationError", load)

    def test_the_error_line_and_try_again_replace_the_lists(self):
        self.assertIn('APErrorLine(text: "Couldn’t load who owes you. Try again.")', self.picker)
        self.assertIn('Button("Try again") { Task { await load() } }', self.picker)
        self.assertIn(".buttonStyle(APSecondaryButtonStyle())", self.picker)
        body = between(self.picker, "var body: some View", "private var loadError")
        self.assertRegex(body, r"searchField\s+if loadFailed \{\s+loadError\s+\} else \{\s+lists")
        self.assertNotIn(".alert(", self.picker)


class TestTP04(unittest.TestCase):
    """TP-04 (G2b-JointIn, rethought): a shorter hero and toast."""

    def setUp(self):
        self.d = read(*TX, "TransactionDetailView.swift")
        self.j = read(*TX, "JointPaybackViews.swift")

    def test_hero_is_from_mom_over_the_account_and_day(self):
        name = between(self.d, "private var heroName: String", "private var heroDateLine")
        self.assertIn('return "From \\(jp.person)"', name)
        self.assertNotIn("jp.account", name)
        line = between(self.d, "private var heroDateLine: String", "private var heroAmount")
        self.assertIn('"\\(jp.account) · \\(Format.weekdayDay(t.date))"', line)
        self.assertNotIn("into \\(jp.into)", line)
        self.assertIn("CFRing(name: t.jointPayback?.person ?? t.merchant", self.d)

    def test_label_names_her_shares_and_rows_keep_the_day(self):
        self.assertIn('"Paid back \\(n) of \\(possessive($0.person)) share', self.d)
        self.assertIn("t.jointPayback != nil ? Format.short(p.charge?.date ?? t.date)", self.d)

    def test_toast_is_who_and_how_much(self):
        self.assertIn("onSaved(MarkReply(title: Self.shortTitle(reply.title)", self.j)
        fn = between(self.j, "static func shortTitle", "\n    }\n")
        self.assertIn("purchases", fn)
        # The server keeps its title; the app shortens it (PB-30 elsewhere is unchanged).
        self.assertIn('f"{names[0]} paid back {len(charges)} purchases · ${paid:,.2f}"',
                      open(os.path.join(ROOT, "finance", "parts_api.py"), encoding="utf-8").read())


class TestTP05(unittest.TestCase):
    """TP-05 (G2b-JointIn, rethought): no options list, one quiet link, one line."""

    def setUp(self):
        self.d = read(*TX, "TransactionDetailView.swift")

    def test_own_layout_without_options(self):
        legs = between(self.d, "private func transferLegs", "private func jointLegs")
        self.assertIn("} else if mineOnlyIn(transfer) {", legs)
        mine = between(self.d, "private func mineLegs", "private func legsLine")
        self.assertIn("legsLine(transfer)", mine)
        self.assertIn("NoPaidBackCallout()", mine)
        self.assertNotIn('section("Options")', mine)
        self.assertNotIn('section("How it counts")', mine)
        plain = between(self.d, "private func plainLegs", "private func unpairSheet")
        self.assertNotIn("NoPaidBackCallout", plain)

    def test_the_one_quiet_link_at_the_foot(self):
        primary = between(self.d, "private var pagePrimary", "private var notATransferLink")
        self.assertIn("mineOnlyIn(transfer)", primary)
        self.assertEqual(primary.count("notATransferLink"), 2)
        link = between(self.d, "private var notATransferLink", "private var sharePaidBack")
        self.assertIn('Text("This isn’t a transfer")', link)
        self.assertIn("unpairing = true", link)

    def test_the_one_line(self):
        j = read(*TX, "JointPaybackViews.swift")
        self.assertIn('Text("Both accounts are only yours.")', j)


if __name__ == "__main__":
    unittest.main()
