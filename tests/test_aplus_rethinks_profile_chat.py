"""The approved rethinks in Profile, setup and the chat (round 3):
G5-Accounts-r (AM-01), G5b-Rule-r (CR-04), G6-PayBills-r (O-10) and
G7-Tell-r (PC-05). Source checks only; the chat's behaviour is in
ios/tools/chat_checks.swift (check_chat.py)."""
from pathlib import Path

IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def src(rel: str) -> str:
    return (IOS / rel).read_text()


def between(text: str, start: str, end: str) -> str:
    i = text.index(start)
    return text[i:text.index(end, i + len(start))]


# G5-Accounts-r: one list, the bank in each row's sub-line.

def test_accounts_one_list_bank_in_sub_line():
    s = src("Views/Profile/AccountsViews.swift")
    content = between(s, "@ViewBuilder private var content", "/// Each bank once")
    assert "ProfileSection(bank)" not in content, "no section per bank any more"
    assert 'ProfileSection("Added by you")' not in content
    assert "ForEach(Array(listed.enumerated())" in content
    assert "sub: AccountWords.listLine(a)" in s
    line = between(s, "static func listLine", "\n    }\n")
    assert "a.institution" in line and '" \\u{00B7} "' in line


def test_accounts_keeps_banner_add_loading_and_error():
    s = src("Views/Profile/AccountsViews.swift")
    content = between(s, "@ViewBuilder private var content", "/// Each bank once")
    assert "ConnectionBanner(account: first)" in content
    assert "APSkeletonRow()" in content
    assert "Couldn\\u{2019}t load your accounts" in content
    assert "No accounts yet" in content
    assert "AddAccountSheet" in s and 'label: "Add an account"' in s
    # Each row still opens the right page.
    for page in ("DisconnectedAccountView(account: a)", "ManualAccountView(account: a)",
                 "AccountDetailView(account: a)"):
        assert page in s


# G5b-Rule-r: the rule leads with its category; the picker opens on Change.

def test_rule_leads_with_category_and_change():
    s = src("Views/Profile/CategoriesRulesView.swift")
    page = between(s, "struct RuleEditView", "/// G5b-Rule-r: the rule's category")
    body = between(page, "var body: some View", ".safeAreaInset")
    assert "RuleCategoryRow(category: chosen" in body
    assert "RuleChips" not in body and "CRSegmented" not in body, "the picker is on its sheet only"
    assert ".sheet(isPresented: $choosing)" in page and "RuleCategorySheet(" in page
    row = between(s, "private struct RuleCategoryRow", "\n}\n")
    assert 'Text("Change")' in row and "CategorySheet.symbol(for: category)" in row
    sheet = between(s, "private struct RuleCategorySheet", "\n}\n")
    assert "PearlSheet {" in sheet and 'APSheetTitle(title: "Category"' in sheet
    assert ".confirmationDialog" not in s and ".alert(" not in s


def test_rule_keeps_earlier_save_and_toast():
    s = src("Views/Profile/CategoriesRulesView.swift")
    page = between(s, "struct RuleEditView", "/// G5b-Rule-r: the rule's category")
    assert '"Also moves the earlier one."' in page
    assert '"Also moves the \\(n) earlier ones."' in page
    assert 'APQuietButton(title: "Only new ones")' in page
    assert '"Now \\(category) · \\(n) moved"' in page
    assert "api/rules/earlier" in page
    assert "undo: undo.map(undoCall)" in s


# G6-PayBills-r: 3 rows, then See all with the count and the month's total.

def test_pay_bills_three_rows_and_see_all():
    s = src("Views/Onboarding/PayAndBillsView.swift")
    assert "static let shownRows = 3" in s
    assert 'billList("Bills", noun: ("bill", "bills")' in s
    words = between(s, "enum PayBillsWords", "\n}\n")
    assert '"See all \\(count) \\(count == 1 ? noun.one : noun.many) \\u{00B7} \\(Format.whole(monthly)) a month"' in words
    assert '"\\(title) \\u{00B7} \\(count)"' in words
    # The same months as the server's bills_each_month.
    for k, v in (("weekly", 52), ("biweekly", 26), ("monthly", 12), ("annual", 1)):
        assert f'"{k}": {v}' in words


def test_pay_bills_keeps_found_pay_yes_no():
    s = src("Views/Onboarding/PayAndBillsView.swift")
    money = between(s, "private func moneyIn", "/// Found pay, answered on the row")
    assert "FoundPayRow(" in money
    assert 'answer(c.payer, "yes")' in money and 'answer(c.payer, "no")' in money
    # Money in is never cut: every found pay asks her, and Looks good says Yes to the rest.
    assert "shownRows" not in money


# G7-Tell-r: after the first card, "Out with friends Saturday · 2 of 7".

def test_tell_progress_replaces_her_sentence_after_first_card():
    cards = src("Chat/ChatCards.swift")
    assert "if deck.showsProgress {" in cards
    assert "ChatDeckProgress(title: deck.progressTitle, done: deck.index, total: deck.progressTotal)" in cards
    core = src("Chat/ChatCore.swift")
    assert "showsProgress ? nil : counter" in core
    shows = between(core, "var showsProgress: Bool", "\n    }\n")
    assert "index > 0" in shows and "case .sort? = current" in shows
    parts = src("Chat/ChatParts.swift")
    prog = between(parts, "struct ChatDeckProgress", "\n}\n")
    assert '"\\(done + 1) of \\(total)"' in prog
    assert "APlus.streakFrom" in prog and "APlus.trackSoft" in prog
