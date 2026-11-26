"""Also 8 older ones? on the iPhone (REFRESH-17, 2026-11-25): where it's
asked, its copy, and what stands where Always can't be."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts):
    return (ROOT / "ios" / "Pearl" / Path(*parts)).read_text()


def sheet():
    return read("Views", "Transactions", "RecurringSheets.swift").split("// MARK: - Also 8 older ones?")[1]


def test_the_copy():
    s = sheet()
    assert '"Also the older one?" : "Also \\(count) older ones?"' in s
    for words in ('"Yes, this one too"', '"Yes, both"', '"Yes, all \\(count)"', '"Leave it in Transfers"',
                  '"Leave them in Transfers"', '"Show all \\(count)"', '"That didn’t save. Try again."',
                  '"your half"'):
        assert words in s
    assert "most = 8" in s and "first = 5" in s


def test_only_leave_them_is_a_no():
    s = sheet()
    # ✕ closes and says nothing to the server; so does a swipe.
    assert "CFSheetTitle(title: ask.category, close: onClose)" in s
    assert s.count('older/no"') == 1
    assert 'older/no"' in s.split("private func leave()")[1]


def test_asked_after_her_answer_is_saved_in_all_three_places():
    review = read("Views", "Review", "ReviewView.swift")
    body = review.split("private func send(_ answer: ReviewAnswer)")[1].split("\n    }\n")[0]
    assert body.index("answer.send(app.api)") < body.index("OlderOnes.after(answer")
    quick = read("Views", "Review", "QuickSortView.swift")
    body = quick.split("private func answered(_ ask: Ask")[1].split("\n    }\n")[0]
    assert body.index("answer.send(app.api)") < body.index("OlderOnes.after(answer")
    page = read("Views", "Transactions", "TransactionDetailView.swift")
    assert page.count("askOlder(was:") == 3
    for source in (review, quick, page):
        assert ".sheet(item: $older" in source and ".sheet(isPresented: $older" not in source


def test_not_after_always_or_the_recurring_card():
    s = sheet().split("var sortsSpendingAlone: Bool")[1].split("\n    }\n")[0]
    assert 'body["remember"] as? Bool != true' in s and "return !remember" in s
    assert "recurring" not in s


def test_quick_sort_undoes_those_first_then_her_answer():
    quick = read("Views", "Review", "QuickSortView.swift")
    # P4c (fewer taps): the toast says how many; its Undo takes those back.
    assert 'case .older(_, let count, _): return "\\(count) more moved."' in quick
    body = quick.split("private func undoOlder(")[1].split("\n    }\n")[0]
    assert "lastAnswer = .sorted(answer)" in body


def test_always_starts_off_for_a_bank_transfer_out():
    models = read("API", "Models.swift")
    body = models.split("func savesRule(")[1].split("\n    }\n")[0]
    assert "if kind == .transfer && !t.inflow && savedTo(accounts) == nil { return false }" in body
    assert "!fromPage && ask.kind != .transfer && learnable == true" in read("Views", "Review", "AnswerSheet.swift")


def test_the_common_name_line_is_on_the_page_only():
    line = "This name is too common for a rule"
    page = read("Views", "Transactions", "TransactionDetailView.swift")
    # P2 (fewer taps): under More, the switch off with this line under it.
    assert page.count(line) == 1 and "sub: Self.noRule" in page
    others = [p for p in (ROOT / "ios" / "Pearl").rglob("*.swift") if line in p.read_text()]
    assert [p.name for p in others] == ["TransactionDetailView.swift"]


def test_the_leftover_category_step_is_gone():
    answer = read("Views", "Review", "AnswerSheet.swift")
    assert "enum Then" not in answer and "then = ." not in answer
    assert answer.count("go(.category)") == 1
