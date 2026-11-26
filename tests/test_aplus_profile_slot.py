"""The profile circle sits in one spot on every main tab (product owner,
2026-11-19): Home, Cash flow, Save, Wins and Pearl all pin it with the one
shared `profileCircleSlot`, so it doesn't move between tabs or when a
title folds. No tab draws it with its own padding. Read from the Swift
source; nothing here needs a simulator."""

import os
import re
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "ios", "Pearl")


def read(*parts):
    with open(os.path.join(APP, *parts), encoding="utf-8") as f:
        return f.read()


def code(text):
    """The source without // comments, so a comment can't pass or fail a check."""
    return re.sub(r"//[^\n]*", "", text)


TABS = {
    "Home": ("Views", "Home", "HomeView.swift"),
    "Cash flow": ("Views", "Transactions", "TransactionsView.swift"),
    "Save and Wins": ("App", "PearlApp.swift"),
    "Pearl": ("Chat", "PearlChatView.swift"),
}


class TestOneSharedPlacement(unittest.TestCase):
    def test_only_the_slot_draws_the_circle(self):
        # Anywhere else, ProfileCircle() would be a placement of its own.
        drawn = []
        for folder, _, files in os.walk(APP):
            for name in files:
                if not name.endswith(".swift"):
                    continue
                with open(os.path.join(folder, name), encoding="utf-8") as f:
                    if "ProfileCircle()" in code(f.read()):
                        drawn.append(name)
        self.assertEqual(drawn, ["ProfileCircle.swift"])
        circle = code(read("Views", "Components", "ProfileCircle.swift"))
        self.assertEqual(circle.count("ProfileCircle()"), 1)
        slot = circle[circle.index("func profileCircleSlot"):circle.index("enum ProfileName")]
        self.assertIn("ProfileCircle()", slot)
        self.assertIn("overlay(alignment: .topTrailing)", slot)
        self.assertIn(".padding(.top, ProfileSlot.top)", slot)
        self.assertIn(".padding(.trailing, ProfileSlot.trailing)", slot)

    def test_one_spot(self):
        circle = code(read("Views", "Components", "ProfileCircle.swift"))
        self.assertIn("static let top: CGFloat = 6", circle)
        self.assertIn("static let trailing: CGFloat = Pearl.gutter - 4", circle)
        self.assertIn("static let size: CGFloat = 44", circle)

    def test_every_main_tab_pins_it(self):
        for tab, path in TABS.items():
            with self.subTest(tab=tab):
                self.assertIn(".profileCircleSlot(", code(read(*path)))
        app = code(read("App", "PearlApp.swift"))
        blank = app[app.index("private struct BlankTab"):]
        self.assertIn(".profileCircleSlot()", blank)
        self.assertIn("page(.save) { BlankTab() }", app)
        self.assertIn("page(.wins) { BlankTab() }", app)

    def test_pinned_over_the_root_not_in_the_scroll(self):
        # On the root view, after the nacre: it doesn't scroll or fold away.
        for tab, path in TABS.items():
            with self.subTest(tab=tab):
                src = code(read(*path))
                at = src.index(".profileCircleSlot(")
                before = src[:at].rstrip()
                self.assertTrue(before.endswith(".nacreScreen()"), tab)

    def test_cash_flow_select_and_trip(self):
        tv = code(read("Views", "Transactions", "TransactionsView.swift"))
        self.assertIn(".profileCircleSlot(shown: !selecting || inTrip, enabled: !inTrip)", tv)


class TestHeadersLevelWithIt(unittest.TestCase):
    def test_home_date_row(self):
        home = code(read("Views", "Home", "HomeView.swift"))
        bar = home[home.index("struct HomeTopBar"):home.index("private struct HomeOrb")]
        self.assertIn(".padding(.top, ProfileSlot.top)", bar)
        # H-00r v2: the greeting under the date may wrap the row past 44.
        self.assertIn(".frame(minHeight: ProfileSlot.size)", bar)
        self.assertIn("Color.clear.frame(width: ProfileSlot.size, height: ProfileSlot.size)", bar)
        # The offline banner sits under the date, clear of the circle.
        feed = home[home.index("private struct HomeFeed"):home.index("struct HomeTopBar")]
        self.assertLess(feed.index("HomeTopBar(today: home.today)"), feed.index("OfflineBanner(since:"))

    def test_cash_flow_title_and_folded_bar(self):
        tv = code(read("Views", "Transactions", "TransactionsView.swift"))
        top = tv[tv.index('Text("Cash flow").font(Nacre.largeTitle)'):]
        self.assertIn(".padding(.top, ProfileSlot.top)", top[:600])
        scroll = code(read("Views", "Transactions", "CashFlowScroll.swift"))
        bar = scroll[scroll.index("private var bar: some View"):scroll.index("private func pin(")]
        # Product owner (2026-11-19): "Cash flow" small on the left, then a
        # spacer, then Filters and + just left of the circle, all in one row,
        # so nothing overlaps (no ZStack laying the title over the buttons).
        self.assertNotIn("ZStack", bar)
        self.assertIn(".padding(.trailing, ProfileSlot.clearance + 4)", bar)
        self.assertIn(".padding(.leading, Pearl.gutter + 4)", bar)
        title = bar.index('Text("Cash flow").font(Nacre.headline)')
        spacer = bar.index("Spacer(minLength: 8)")
        filters = bar.index('symbol: "slider.horizontal.3"')
        plus = bar.index('symbol: "plus"')
        self.assertLess(title, spacer)
        self.assertLess(spacer, filters)
        self.assertLess(filters, plus)
        # 44 pt targets kept.
        self.assertIn(".frame(width: 44, height: 44)", scroll)
        # Fits a 375 pt iPhone: title + gaps + two 44 pt buttons + the circle.
        widest_title = 17 * 0.6 * len("Cash flow")  # Figtree 17 semibold, generous
        used = (16 + 4) + widest_title + 8 + 44 + 8 + 44 + (44 + 12 + 4)
        self.assertLess(used, 375)
        # The bar's centre line is the circle's: 6 + 44 / 2 == 56 / 2.
        self.assertIn("static let barHeight: CGFloat = 56", scroll)

    def test_pearl_tab(self):
        chat = code(read("Chat", "PearlChatView.swift"))
        top = chat[chat.index("private struct ChatTop"):chat.index("private struct ChatStarters")]
        self.assertEqual(top.count(".padding(.top, ProfileSlot.top)"), 2)  # large and inline
        # New chat on the left, clear of the circle on the right.
        self.assertLess(top.index('Button("New chat"'), top.index("Spacer()"))
        self.assertIn('.accessibilityIdentifier("chat-new")', top)
        # The unavailable state keeps the large title, so the circle too.
        self.assertIn("private var largeTitle: Bool { !available || isStart }", chat)


if __name__ == "__main__":
    unittest.main()
