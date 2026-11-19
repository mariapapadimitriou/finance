"""A+ restyle, chat and trips (REDESIGN-14; Claude Design boards AP-Chat and
G7-Chat, -Tell, -TellMore, -Confirm, -Unavailable, -TripAsk, -Trip,
-TripCal). Read from the Swift source; the chat's logic itself runs on this
Mac in ios/tools/check_chat.py. Nothing here needs a simulator."""

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


CHAT_FILES = [("Chat", f) for f in ("ChatCards.swift", "ChatCore.swift", "ChatParts.swift", "PearlChatView.swift")]
TRIPS = ("Views", "Transactions", "TripViews.swift")


class TestNoStockDialogs(unittest.TestCase):
    def test_pearl_sheets_only(self):
        for parts in CHAT_FILES + [TRIPS]:
            src = code(read(*parts))
            for bad in [".alert(", ".confirmationDialog(", ".actionSheet(", "Menu {", "Menu("]:
                self.assertNotIn(bad, src, f"{parts[-1]} uses {bad}")

    def test_allowance_never_the_other_phrase(self):
        for parts in CHAT_FILES + [TRIPS]:
            self.assertNotIn("safe to spend", read(*parts).lower())


class TestChatLooksLikeG7(unittest.TestCase):
    def setUp(self):
        self.view = code(read("Chat", "PearlChatView.swift"))
        self.cards = code(read("Chat", "ChatCards.swift"))
        self.parts = code(read("Chat", "ChatParts.swift"))
        self.core = code(read("Chat", "ChatCore.swift"))

    def test_her_words_in_a_bubble_pearls_in_lines(self):
        self.assertIn("struct ChatYou", self.parts)
        self.assertIn("ChatBubbleShape().fill(Pearl.bubble)", self.parts)
        self.assertIn("struct ChatLine", self.parts)

    def test_old_nacre_card_styles_are_gone(self):
        for src in (self.view, self.cards):
            for old in ["GlassCard(", ".glassCard(", "pearlCard(", "NacreButtonStyle", "OutlineCapsuleStyle",
                        "RowSeparator(", "Pearl.radiusSort"]:
                self.assertNotIn(old, src)

    def test_one_card_at_a_time_skip_and_yes(self):
        self.assertIn('Button("Skip", action: skip)', self.cards)
        self.assertIn('Button("Yes", action: yes)', self.cards)
        self.assertIn("APPrimaryButtonStyle()", self.cards)
        self.assertNotIn("Yes to all", self.cards)
        self.assertIn("ChatQuestionCard(", self.cards)
        self.assertIn("APCardSurface(radius: 28)", self.parts)

    def test_trip_question_names_the_place(self):
        self.assertIn('"Were you in \\(place)?"', self.core)
        self.assertNotIn('Text("A trip?")', self.cards)
        self.assertIn("ChatWords.tripQuestion(t)", self.cards)

    def test_composer_well_with_send_arrow(self):
        self.assertIn('"arrow.up"', self.view)
        self.assertIn("capsule: true", self.view)
        self.assertNotIn("ignoresSafeArea(.keyboard", self.view)

    def test_working_dots_and_failed_try_again(self):
        self.assertIn("ChatWorking()", self.view)
        self.assertIn('Button("Try again", action: retry)', self.view)
        self.assertIn("await engine.retry()", self.view)

    def test_unavailable_is_a_primary_button(self):
        self.assertIn('"It runs on this iPhone only, and needs a newer one."', self.view)
        self.assertIn('Button("Search instead", action: onSearch)', self.view)


class TestUndoInChat(unittest.TestCase):
    def setUp(self):
        self.cards = code(read("Chat", "ChatCards.swift"))
        self.core = code(read("Chat", "ChatCore.swift"))

    def test_toast_after_set_it_and_a_trip(self):
        self.assertIn("app.say(u.toast) { try await engine.undo(u, tap: UserTap(\"undo\")) }", self.cards)
        self.assertEqual(self.cards.count("ChatToast.offer("), 2)
        self.assertIn('case .plan(let category, _): return "\\(category) plan set"', self.core)
        self.assertIn('case .trip(_, let name): return "\\(name) made"', self.core)

    def test_undo_only_through_the_executor(self):
        self.assertIn('query: ["undo": "1"]', self.core)
        executor = re.search(r"^struct ChatExecutor \{(.*?)^\}", self.core, re.S | re.M).group(1)
        self.assertIn("func undo(_ u: ChatUndo, tap: UserTap)", executor)


class TestTrips(unittest.TestCase):
    def setUp(self):
        self.src = code(read(*TRIPS))

    def test_options_leave_it_and_red_entry_row(self):
        self.assertIn('title: "Leave it as is"', self.src)
        self.assertIn('"It wasn\\u{2019}t a trip", danger: true', self.src)
        self.assertNotIn("piggy bank", self.src.lower())

    def test_not_a_trip_sheet(self):
        self.assertIn('APSheetTitle(title: "Not a trip?"', self.src)
        self.assertIn("Only the trip and its tag go.", self.src)
        self.assertIn('primary: failed ? "Try again" : "Not a trip"', self.src)
        self.assertIn('secondary: "Keep it"', self.src)

    def test_page_hero_and_switch(self):
        self.assertIn("struct TripHero", self.src)
        self.assertIn('side("Transactions"', self.src)
        self.assertIn('side("By category"', self.src)
        self.assertIn('APSectionLabel(text: "In the trip")', self.src)

    def test_trips_card_for_the_calendar(self):
        self.assertIn("struct TripsCard: View", self.src)
        self.assertIn('"No trips yet. Pearl asks when it spots one."', self.src)
        self.assertIn('Text("See all")', self.src)
        self.assertIn('Text("Trips").font(Nacre.largeTitle)', self.src)


if __name__ == "__main__":
    unittest.main()
