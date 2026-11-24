"""Profile changes and PB-30 "Change" (product owner, 2026-11-19; Claude
Design G5-Profile, G5-Security, G5-Email, G5-Devices, G5-Data, and G2-PB30 in
approved-r7). Read from the Swift source; nothing here needs a simulator."""

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


def between(text, start, end):
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


STOCK = [".alert(", ".confirmationDialog(", ".actionSheet(", "Menu {"]


class TestProfileName(unittest.TestCase):
    def setUp(self):
        self.profile = code(read("Views", "Profile", "ProfileView.swift"))
        self.forms = code(read("Views", "Profile", "ProfileForms.swift"))

    def test_name_is_a_button_with_a_pencil_opening_your_name(self):
        p = self.profile
        button = between(p, "private var nameButton", "private func runChoice")
        self.assertIn("editingName = true", button)
        self.assertIn('Image(systemName: "pencil")', button)
        self.assertIn('accessibilityIdentifier("profile-name")', button)
        self.assertIn("YourNameSheet { editingName = false }", p)

    def test_email_stays_read_only_and_sign_out_is_gone(self):
        p = self.profile
        self.assertIn("Text(email)", p)
        self.assertNotIn("ChangeEmailView", p)
        self.assertNotIn('"Sign out"', p)
        self.assertNotIn("app.signOut()", p)
        for bad in STOCK:
            self.assertNotIn(bad, p)

    def test_your_name_sheet(self):
        f = between(self.forms, "struct YourNameSheet", "struct ChangePasswordChecks")
        self.assertIn('ProfileFormSheet(title: "Your name"', f)
        # The live initials circle, one Name well, Save off while empty.
        self.assertIn("ProfileName.initials(name: name, email: app.user?.email)", f)
        self.assertIn('PearlField(label: "Name", placeholder: "Your name"', f)
        self.assertIn('Button("Save")', f)
        self.assertIn(".disabled(trimmed.isEmpty || busy)", f)
        # The server's endpoint, the toast with Undo, the circle updating.
        self.assertIn('"api/account/name", ["first_name": trimmed]', f)
        self.assertIn('app.say("Name changed to \\(', f)
        self.assertIn("undo:", f)
        self.assertIn("app.phase = .signedIn(user)", f)

    def test_initials_two_letters_or_the_emails_first(self):
        c = code(read("Views", "Components", "ProfileCircle.swift"))
        f = between(c, "static func initials(name: String?, email: String?)", "private struct GoHomeKey")
        self.assertIn(".prefix(typed.isEmpty ? 1 : 2)", f)

    def test_form_sheet_keeps_the_button_above_the_keyboard(self):
        f = between(self.forms, "struct ProfileFormSheet", "private struct FormSheetCorners")
        self.assertIn("APSheetTitle(title: title, close: close)", f)
        self.assertIn("ScrollView", f)
        self.assertIn("VStack(spacing: 12, content: bottom)", f)
        self.assertIn(".presentationDetents([.large])", f)


class TestSignInAndSecurity(unittest.TestCase):
    def setUp(self):
        self.s = code(read("Views", "Profile", "SettingsViews.swift"))
        self.view = between(self.s, "struct SignInSecurityView", "struct ChangePasswordView")

    def test_sign_out_is_a_row_here_with_its_pearl_sheet(self):
        v = self.view
        card = between(v, "private var signOutCard", "private var dangerCard")
        self.assertIn('symbol: "rectangle.portrait.and.arrow.right", title: "Sign out"', card)
        self.assertIn("confirmSignOut = true", card)
        self.assertIn('PearlConfirmSheet(overline: "Sign out", title: "Sign out on this iPhone?"', v)
        self.assertIn('secondary: "Stay signed in"', v)
        self.assertIn("await app.signOut()", v)
        for bad in STOCK:
            self.assertNotIn(bad, v)

    def test_sign_out_other_devices_is_the_devices_cards_last_row_not_red(self):
        card = between(self.view, "private var devicesCard", "private func deviceRow")
        row = card[card.index('"Sign out other devices"') - 200:card.index('"Sign out other devices"') + 200]
        self.assertIn('symbol: "macbook.and.iphone"', row)
        self.assertNotIn("danger", row)
        self.assertNotIn("APQuietButton(title: \"Sign out other devices\"", self.view)

    def test_reset_and_delete_together_in_danger_red(self):
        v = self.view
        card = between(v, "private var dangerCard", "private var version")
        self.assertIn("ResetPearlRow()", card)
        self.assertIn('SecurityDangerRow(symbol: "trash", title: "Delete your account")', card)
        self.assertIn("showDelete = true", card)
        row = between(self.s, "struct SecurityDangerRow", "struct SecureWell")
        self.assertIn(".fill(Pearl.danger)", row)
        self.assertIn(".foregroundColor(Pearl.danger)", row)
        self.assertIn("Figtree-SemiBold", row)
        reset = between(self.s, "struct ResetPearlRow", "struct SecurityDangerRow")
        self.assertIn('SecurityDangerRow(symbol: "arrow.counterclockwise"', reset)
        # D-03 unchanged, reached from here; Download a copy first goes to Your data.
        self.assertIn("DeleteAccountView(downloadFirst:", v)
        self.assertIn("prepareOnOpen: true", v)

    def test_delete_flow_unchanged(self):
        d = code(read("Views", "Profile", "YourDataView.swift"))
        delete = between(d, "struct DeleteAccountView", "struct DeleteOptions")
        self.assertIn('Button("Continue")', delete)
        self.assertIn('Button("Delete my account")', d)
        # Gone from Your data (G5-Data).
        page = between(d, "struct YourDataView", "private struct ShareSheet")
        self.assertNotIn("Delete your account", page)
        self.assertNotIn("DeleteAccountView(", page)

    def test_email_and_password_open_as_sheets(self):
        v = self.view
        self.assertIn(".sheet(isPresented: $changingEmail) { ChangeEmailView() }", v)
        self.assertIn(".sheet(isPresented: $changingPassword) { ChangePasswordView() }", v)
        self.assertNotIn("NavigationLink { ChangeEmailView() }", v)


class TestEmailAndPasswordLook(unittest.TestCase):
    def test_change_email(self):
        e = code(read("Views", "Profile", "ChangeEmailView.swift"))
        self.assertIn('ProfileFormSheet(title: sentTo == nil ? "Change your email" : "Check your email"', e)
        self.assertIn('NacreRingIcon(symbol: "envelope")', e)
        self.assertIn("ProfileFormCard", e)
        self.assertIn('EmailField(label: "New email"', e)
        self.assertIn('Text("Current")', e)
        self.assertIn(".disabled(!looksLikeEmail || busy)", e)
        self.assertIn(".disabled(code.count < 6 || busy)", e)
        for words in ['"Send code"', '"Confirm"', '"Send a new code"', '"Use a different email"',
                      "That code didn\\u{2019}t work. Check it and try again."]:
            self.assertIn(words, e)

    def test_change_password(self):
        s = code(read("Views", "Profile", "SettingsViews.swift"))
        p = between(s, "struct ChangePasswordView", "struct RecoveryCodes")
        self.assertIn('ProfileFormSheet(title: "Change password"', p)
        self.assertIn('NacreRingIcon(symbol: "key", size: 36)', p)
        for label in ['"Current password"', '"New password"', '"Confirm new password"']:
            self.assertIn("SecureWell(label: " + label, p)
        self.assertIn("ChangePasswordChecks(rules: rules, new: new, confirm: confirm)", p)
        self.assertIn(".disabled(current.isEmpty || !rules.ok || !matches || busy)", p)
        f = code(read("Views", "Profile", "ProfileForms.swift"))
        checks = between(f, "struct ChangePasswordChecks", "private func line")
        self.assertIn("The new passwords don\\u{2019}t match", checks)
        self.assertIn("Both new passwords match", checks)
        line = f[f.index("private func line(_ text: String, state: State)"):]
        self.assertIn("Nacre.teal", line)
        self.assertIn("Pearl.danger", line)


class TestPB30Change(unittest.TestCase):
    def setUp(self):
        self.p = code(read("Views", "Transactions", "PartsFlow.swift"))

    def test_ticking_other_purchases_covers_the_whole_purchase(self):
        toggle = between(self.p, "private func toggleUnsplit", "static func wholeCovered")
        self.assertNotIn("askUnsplit", toggle)
        self.assertIn("Self.wholeCovered(amount: cents(u.amount)", toggle)
        whole = between(self.p, "static func wholeCovered", "private func unsplitRoom")
        self.assertIn("min(amount, room)", whole)

    def test_change_after_the_price_on_every_ticked_row(self):
        slot = between(self.p, "private func changeSlot", "private func toggleTick")
        self.assertIn("if on {", slot)
        self.assertIn(".frame(width: 64, alignment: .trailing)", slot)
        for row, call in [("private func tickRow", "changePart(o)"), ("private func unsplitRow", "askUnsplit(u)")]:
            body = between(self.p, row, "\n    }\n")
            price = body.index("Text(Format.amount(")
            change = body.index("changeSlot(on: on")
            self.assertLess(price, change)
            self.assertIn(call, body[change:])

    def test_nothing_preticked_and_the_whole_row_ticks(self):
        # Product owner, 2026-11-24: "don't have anything pre-selected"; only
        # the purchase she came from is ticked when PB-30 / MP-01 opens.
        pre = between(self.p, "private func preTick()", "\n    }\n")
        self.assertNotIn("bestSum", pre)
        self.assertNotIn("likely", pre)
        self.assertIn("ticks = Set(must.map { [$0.id] } ?? [])", pre)
        # "if I tap anywhere on the entire row, it should select": the price
        # and the Change slot are inside the row's button; Change lies over it.
        for row in ["private func tickRow", "private func unsplitRow", "private func mineRow"]:
            body = between(self.p, row, "\n    }\n")
            self.assertIn("ZStack(alignment: .trailing)", body)
            self.assertLess(body.index("Text(Format.amount("), body.index(".buttonStyle(.plain)"))
            self.assertIn("changeGap", body)
            self.assertIn("changeSlot(on:", body)

    def test_row_lines(self):
        row = between(self.p, "private func unsplitRow", "\n    }\n")
        self.assertIn('"\\(day) · all of it"', row)
        self.assertIn('of it · \\(day)', row)

    def test_change_sheet_pb30c(self):
        p = self.p
        self.assertIn('"How much of \\(possessive(o.merchant)) \\(Format.amount(o.owes))?"', p)
        self.assertIn("stays your spending", p)
        self.assertIn("more than \\(firstName(sender ?? who)) sent", p)
        # ✕ on a Change goes back to PB-30 with nothing added.
        self.assertIn("parts = before", p)
        self.assertIn("unsplitPaid = unsplitBeforeChange", p)
        change = between(p, "private func changePart", "private func takeTicked")
        self.assertIn("addUnsplit()", change)
        self.assertIn("changing: true", change)


if __name__ == "__main__":
    unittest.main()
