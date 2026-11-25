"""REFRESH-18 on the iPhone (approved 2026-11-25): the words on the boards
(Claude Design › Cash flow › G2-OverCard to G2-SmallLands) and what opens what."""

from __future__ import annotations

import pathlib
import re

ROOT = pathlib.Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def src(path):
    return (ROOT / path).read_text(encoding="utf-8")


OVER = "Views/Transactions/OverUnderViews.swift"
FLOW = "Views/Transactions/SplitFlow.swift"
MENUS = "Views/Transactions/SplitMenus.swift"
DETAIL = "Views/Transactions/TransactionDetailView.swift"
PARTS = "Views/Transactions/PartsFlow.swift"


def test_the_card_says_paid_left_let_go_and_extra():
    s = src(FLOW)
    for words in ('"Paid \\(Format.amount(p.paid)) of \\(Format.amount(p.amount))"', '"Paid back · \\(n) payments"',
                  '"left"', '"let go"', 'let go")', 'extra" : nil', "ExtraChip(amount: chip) { onChoose(p, .sayExtra) }"):
        assert words in s, words
    assert "· owes \\(Format.amount(p.owes))" not in s, "what's left is on the right (S-04l)"
    assert ".partLetGo(p.paid" in s and "case partLetGo(Double)" in src("Theme/APlus.swift")
    assert "PaidBackBar.track(s)" in src("Theme/APlus.swift")


def test_the_chip_is_a_button_of_its_own():
    """The row opens the options, as today; only the chip asks."""
    s = src(FLOW)
    card = s[s.index("private func person(_ p:"):s.index("private func personButton")]
    assert ".overlay(alignment: .bottomLeading)" in card and "Button { options = p }" not in card
    assert "What’s the extra \\(Format.amount(amount))?" in src(OVER)


def test_the_options():
    s = src(MENUS)
    for words in ("Add another payment", "Let the \\(Format.amount(p.owes)) go", "What’s the extra \\(Format.amount(extra.amount))?",
                  "Change what the extra is", "You owe it back",
                  "Paid \\(Format.amount(p.paid)) · \\(Format.amount(p.owes)) left",
                  "\\(Format.amount(letGoAmount)) let go \\(Format.short(gone.day))",
                  "Paid \\(Format.amount(paid)) · \\(Format.amount(extra.amount)) extra",
                  "Paid \\(Format.amount(paid)) · you owe \\(Format.amount(extra.owe)) back"):
        assert words in s, words
    assert "Mark the rest paid back" not in s
    # Bug 4: overpaid, they keep Change share and Remove.
    body = s[s.index("private var setBody"):s.index(".sheet(item: $payment")]
    assert all(c in body for c in ("paymentsCard", "extraCard", "stateCard", "changeSplitCard")) and "else" not in body


def test_what_the_extra_is():
    s = src(OVER)
    for words in ("What’s the extra \\(Format.amount(ask.amount))?", "How much of it?", "I owe it back",
                  "Pays back something else", "A gift", "I sent it back", "Something else…",
                  "share is \\(Format.amount($0)).", "Couldn’t save that. Nothing changed. Try again."):
        assert words in s, words
    # Nothing picked; a tile answers at once.
    assert "Binding(get: { nil }" in s
    assert "What did the \\(Format.amount(deposit.amount)) pay back?" in src(PARTS)
    for key in ('"kind": key', 'split/extra"', 'body["again"] = true'):
        assert key in s, key


def test_pays_back_something_else_is_pb30_with_nothing_ticked():
    s = src(PARTS)
    load = s[s.index("if let saying = saying {"):s.index("// S-11x: straight to the tiles; Paid")]
    assert "step = .whose" in load and "preTick" not in load
    assert "onPieces(parts.map(\\.body))" in s


def test_which_payment_was_it():
    s = src(FLOW)
    for words in ("Add another payment", "left on \\(t.merchant)", "You let \\(Format.amount(person.letGoLeft)) go on \\(t.merchant)",
                  '"\\(Format.amount(over)) extra"', '"\\(Format.amount(-over)) let go"',
                  'picked.isEmpty ? "Link" : "Link \\(Format.amount(paying))"', "picked = []"):
        assert words in s, words
    assert "deposits.first(where: { $0.likely == true" not in s, "nothing pre-ticked"
    # One after the other: each is judged on what's paid so far.
    primary = s[s.index("private func primary()"):]
    assert "withThrowingTaskGroup" not in primary


def test_the_cutoff_is_the_servers():
    s = src("API/Models.swift")
    assert "d <= 200 && d * 10 <= s" in s
    from finance import over_under as ou
    assert (ou.SMALL_MAX, ou.SMALL_SHARE) == (2.0, 0.10)


def test_needs_a_look_and_quick_sort():
    r = src("Views/Review/ReviewView.swift")
    for words in ("\\(Format.amount(over.amount)) extra", "you let \\(Format.amount(s.owes)) go",
                  "owes you \\(Format.amount(s.owes))", "Paid back for \\(s.merchant)?", "ReviewExtraSheet("):
        assert words in r, words
    assert "What’s the extra?" in src("API/Models.swift") and "ReviewExtraSheet(" in src("Views/Review/QuickSortView.swift")
    assert '"Yes, \\(tile.title)"' in src("Views/Review/PaybackQuestionViews.swift")


def test_the_deposit_and_owed_to_you():
    s = src(OVER)
    for words in ("\\(possessive(over.name)) share · \\(Format.short(date))", 'Text("Extra")'):
        assert words in s, words
    d = src(DETAIL)
    assert "OverExtraRow(amount: cents, line: nil, ask: nil)" in d, "PB-41s: no chip"
    owed = src("Views/Home/OwedViews.swift")
    assert "OweBackOptions(row: $oweBack)" in owed and "Button { openOwed(r) }" in owed


def test_sheets_take_an_item_and_never_ios_alerts():
    for path in (OVER, DETAIL):
        s = src(path)
        assert ".alert(" not in s and "confirmationDialog(" not in s
    assert "content.sheet(item: $ask)" in src(OVER)
    assert re.search(r"@State private var saying: ExtraAsk\?", src(DETAIL))


def test_say_allowance():
    for path in (OVER, FLOW, MENUS):
        assert "safe to spend" not in src(path).lower()


def test_unlink_from_the_deposit_says_the_share():
    """Bug 3: "owes you $40.00 again", from either side, in the server's words."""
    d = src(DETAIL)
    assert "charge: t.repaysCharge?.id ?? t.id" in d and "paybacks.map { $0.again ?? $0.amount }" in d
    assert "if let link = charge.link { unlinkingLink = link; return }" in d
