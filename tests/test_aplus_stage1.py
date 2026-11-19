"""A+ redesign, stage 1 (REDESIGN-02 to 16, product owner 2026-11-18): the
A+ tokens and components, the five tabs with Pearl as a tab, the profile
circle, and the profile photo kept on this iPhone. Read from the Swift
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


class TestTokensAndComponents(unittest.TestCase):
    def setUp(self):
        self.aplus = read("Theme", "APlus.swift")

    def test_tokens_light_and_dark(self):
        a = self.aplus
        for line in [
            "card = rgba(light: (255, 255, 255, 0.80), dark: (21, 27, 68, 0.72))",
            "cardLine = rgba(light: (255, 255, 255, 0.95), dark: (255, 255, 255, 0.08))",
            "separator = rgba(light: (46, 37, 71, 0.09), dark: (255, 255, 255, 0.08))",
            "chip = rgba(light: (46, 37, 71, 0.06), dark: (255, 255, 255, 0.08))",
            "trackSoft = rgba(light: (46, 37, 71, 0.08), dark: (255, 255, 255, 0.10))",
            "face = Pearl.dynamic(light: 0xF3E8EE, dark: 0x262E63)",
            "tabLozenge = rgba(light: (160, 140, 235, 0.26), dark: (255, 255, 255, 0.12))",
            "streakFrom = Color(hex: 0xFF8FB1)",
            "streakTo = Color(hex: 0xC9A8FF)",
            "well = rgba(light: (46, 37, 71, 0.05), dark: (0, 0, 0, 0.24))",
            "wellLine = rgba(light: (46, 37, 71, 0.18), dark: (255, 255, 255, 0.18))",
        ]:
            self.assertIn(line, a)

    def test_components_exist(self):
        for name in ["struct APCard<", "struct APSectionLabel", "struct APPaymentRow", "struct SortStreak",
                     "struct PaidBackBar", "struct PearlField", "struct CalmState", "typealias APToast",
                     "typealias APPrimaryButtonStyle", "struct APConfirmSheet"]:
            self.assertIn(name, self.aplus)

    def test_payment_row_colours(self):
        a = code(self.aplus)
        # Spending plum, money in green, ⇄ and uncounted muted with no sign; never red.
        self.assertIn("case .out: return Pearl.moneyOut", a)
        self.assertIn("case .into: return Pearl.moneyIn", a)
        self.assertIn("case .moved, .uncounted: return Pearl.muted", a)
        self.assertIn('case .moved(let v): return "\\u{21C4} " + Format.amount(v)', a)
        row = a[a.index("struct APPaymentRow"):a.index("struct APFace")]
        self.assertNotIn("Pearl.danger", row)

    def test_fields_are_wells(self):
        a = code(self.aplus)
        self.assertIn("frame(minHeight: 44)", a)
        self.assertIn("lineWidth: error || focused ? 2 : 1", a)
        self.assertIn("error ? Pearl.danger : (focused ? Pearl.action : APlus.wellLine)", a)
        self.assertIn('Text("$")', a)
        self.assertIn('"magnifyingglass"', a)
        self.assertIn("isEnabled ? 1 : 0.45", a)

    def test_streak_twelve_dashes_and_spoken(self):
        a = self.aplus
        self.assertIn("static let dashes = 12", a)
        self.assertIn("frame(width: mini ? 108 : nil)", a)
        self.assertIn('"\\(max(0, sorted)) of \\(max(0, sorted) + max(0, toSort)) sorted"', a)


class TestTabs(unittest.TestCase):
    def setUp(self):
        self.app = code(read("App", "PearlApp.swift"))

    def test_five_tabs_pearl_last_no_profile(self):
        self.assertIn("case home, cashFlow, save, wins, pearl", self.app)
        self.assertNotIn("TabProfile", self.app)
        self.assertNotIn("ProfileView(", self.app)

    def test_pearl_tab_is_the_logo_in_its_own_colours(self):
        self.assertIn("PearlTabIcon.image(suggest: chatSuggests", self.app)
        self.assertIn(".renderingMode(.original)", self.app)
        circle = read("Views", "Components", "ProfileCircle.swift")
        self.assertIn('UIImage(named: "LogoMark")', circle)
        self.assertIn("withRenderingMode(.alwaysOriginal)", circle)
        self.assertIn('"Pearl, has a suggestion"', self.app)

    def test_tint_and_badge_never_red(self):
        self.assertIn(".tint(Pearl.action)", self.app)
        self.assertIn("state.badgeBackgroundColor = UIColor(Pearl.action)", self.app)
        self.assertNotIn("systemRed", self.app)

    def test_floating_button_is_gone(self):
        self.assertFalse(os.path.exists(os.path.join(APP, "Chat", "PearlButton.swift")))
        for root, _, files in os.walk(APP):
            for f in files:
                if f.endswith(".swift"):
                    with open(os.path.join(root, f), encoding="utf-8") as fh:
                        self.assertNotIn(".pearlButton(", fh.read(), f)
        self.assertNotIn("fullScreenCover(isPresented: $chatOpen", self.app)


class TestPearlTab(unittest.TestCase):
    def setUp(self):
        self.chat = code(read("Chat", "PearlChatView.swift"))

    def test_no_close_and_new_chat_asks_first(self):
        # A tab has no Close: the view takes no onClose and draws no chat-close.
        self.assertNotIn("let onClose", self.chat)
        self.assertNotIn('"chat-close"', self.chat)
        self.assertIn('"Start a new chat?"', self.chat)
        self.assertIn('primary: "New chat", secondary: "Keep this one"', self.chat)
        self.assertIn("await engine.newChat()", self.chat)
        core = read("Chat", "ChatCore.swift")
        self.assertIn("func newChat() async", core)

    def test_conversation_kept_across_tabs(self):
        # Opened once; a tab switch doesn't open it again.
        self.assertIn("guard available, !opened else { return }", self.chat)

    def test_composer_is_a_well_with_send(self):
        self.assertIn(".wellStyle(focused: composing.wrappedValue, capsule: true)", self.chat)
        self.assertIn('"arrow.up"', self.chat)
        self.assertIn(".disabled(!canSend)", self.chat)

    def test_unavailable_screen_kept(self):
        self.assertIn('"Pearl chat needs Apple Intelligence"', self.chat)
        # G7-Unavailable: Search instead is the Primary button.
        self.assertIn('Button("Search instead", action: onSearch)', self.chat)

    def test_no_stock_dialogs(self):
        for bad in [".alert(", ".confirmationDialog(", ".actionSheet("]:
            self.assertNotIn(bad, self.chat)


class TestProfileCircleAndPhoto(unittest.TestCase):
    def test_circle_on_the_four_main_tabs(self):
        self.assertIn("ProfileCircle()", code(read("Views", "Home", "HomeView.swift")))
        self.assertIn("ProfileCircle()", code(read("Views", "Transactions", "TransactionsView.swift")))
        self.assertIn("ProfileCircle()", code(read("App", "PearlApp.swift")))  # Save and Wins

    def test_circle_size_dot_and_push(self):
        c = code(read("Views", "Components", "ProfileCircle.swift"))
        self.assertIn("var size: CGFloat = 36", c)
        self.assertIn(".frame(width: 44, height: 44)", c)
        self.assertIn("if app.profileNeedsYou { NacreDot()", c)
        self.assertIn('"Profile, needs you"', c)
        self.assertIn(".navigationDestination(isPresented: $open)", c)

    def test_photo_on_this_iphone_only(self):
        c = code(read("Views", "Components", "ProfileCircle.swift"))
        store = c[c.index("final class ProfilePhotoStore"):c.index("struct ProfileAvatar")]
        self.assertIn("isExcludedFromBackup = true", store)
        self.assertIn(".applicationSupportDirectory", store)
        for upload in ["api.", "URLSession", "post(", "put("]:
            self.assertNotIn(upload, store)

    def test_photo_flow(self):
        p = code(read("Views", "Profile", "ProfileView.swift"))
        v = code(read("Views", "Profile", "ProfilePhotoViews.swift"))
        self.assertIn('"Add photo" : "Change photo"', p)
        self.assertIn('"Saving\\u{2026}"', p)
        self.assertIn('"Couldn\\u{2019}t save your photo."', p)
        self.assertIn('"Camera is off for Pearl"', p)
        self.assertIn(".photosPicker(", p)  # PHPicker: no Photos permission needed
        for words in ['"Choose photo"', '"Take photo"', '"Remove photo"', '"Cancel"',
                      '"Move and scale"', '"Use photo"']:
            self.assertIn(words, v)
        self.assertIn("if photo != nil", v)  # Remove only when one is set
        self.assertIn("isSourceTypeAvailable(.camera)", v)  # Take photo only with a camera
        for bad in [".alert(", ".confirmationDialog(", ".actionSheet("]:
            self.assertNotIn(bad, p)
            self.assertNotIn(bad, v)
        with open(os.path.join(APP, "Info.plist"), encoding="utf-8") as f:
            self.assertIn("NSCameraUsageDescription", f.read())

    def test_profile_pushed_with_back_and_home(self):
        p = code(read("Views", "Profile", "ProfileView.swift"))
        self.assertIn("let goHome: () -> Void", p)
        self.assertNotIn("MainTabs.Tab", p)
        self.assertIn('accessibilityLabel("Back")', p)


class TestWords(unittest.TestCase):
    def test_allowance_never_the_other_phrase(self):
        for parts in [("Theme", "APlus.swift"), ("Views", "Components", "ProfileCircle.swift"),
                      ("Views", "Profile", "ProfilePhotoViews.swift"), ("Chat", "PearlChatView.swift")]:
            self.assertNotIn("safe to spend", read(*parts).lower())


if __name__ == "__main__":
    unittest.main()
