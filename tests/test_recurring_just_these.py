"""Recurring transfers, 2026-11-24 (product owner): "Sometimes savings are
not recurring… when I assign something as a saving, it finds a pattern."
The app's side of the three changes; the server's are in
test_recurring_transfers.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def read(*parts: str) -> str:
    return (ROOT / "ios" / "Pearl" / Path(*parts)).read_text()


def test_the_tiles_ask_from_now_on_before_saving():
    answer = read("Views", "Review", "AnswerSheet.swift")
    # Every tile, and a category after Something I pay for, goes through the ask.
    body = answer.split("private func recurring(_ kind: String?, _ label: String, category: String? = nil)")[1]
    body = body.split("\n    }\n")[0]
    assert "repeatAsk = RepeatAsk(kind: kind, category: category, label: label)" in body
    assert "onAnswer(.recurring(" not in body
    # After Something I pay for › a category, the sheet goes back to the
    # tiles' page where "from now on?" is drawn; left on the category page,
    # Save was a dead button (product owner, 2026-11-24).
    after = answer.split("the only way here (REFRESH-17)")[1][:700]
    assert "recurring(nil, name, category: name)\n                    go(.recurring)" in after
    # G1-RecurringFrom: in the tiles' place, under the rhythm card; ✕ goes back.
    assert "if let r = repeatAsk {\n            fromNowOn(r)\n        } else {\n            recurringChoices\n        }" in answer
    assert '" from now on?")' in answer
    assert 'Text("Pearl can sort the ones to come as \\(r.label), too.")' in answer
    assert 'PearlSheetButtons(primary: "Yes, \\(every)", secondary: "Just \\(these)"' in answer
    assert 'let these = n == 2 ? "both" : "these \\(n)"' in answer
    assert 'toast: "\\(r.label) · \\(seriesAll) sorted, and the ones to come")' in answer
    assert 'toast: "\\(r.label) · \\(seriesAll) sorted", once: true)' in answer
    assert "if repeatAsk != nil { repeatAsk = nil } else { dismiss() }" in answer
    assert 'case .recurring: return repeatAsk?.label ?? "Is this a recurring transfer?"' in answer
    assert ".sheet(item: $repeatAsk" not in answer


def test_just_these_reaches_the_server():
    review = read("Views", "Review", "ReviewView.swift")
    assert "case recurring(key: String, kind: String?, category: String?, toast: String? = nil, once: Bool = false)" in review
    assert 'if once { body["once"] = true }' in review


def test_the_rs01_sheet_copy():
    sheets = read("Views", "Transactions", "RecurringSheets.swift")
    assert "struct RecurringRowSheet" in sheets
    assert "APSheetHeader(heading: rule.when, line: line, close: onClose)" in sheets
    assert '"\\(what) · \\(rule.count) so far\\(since)"' in sheets
    assert '"Not this one"' in sheets and "as your own answer. The rule skips it." in sheets
    assert '"Stop the rule"' in sheets and "category. Pearl stops sorting new ones." in sheets
    assert "tone: Pearl.danger" in sheets


def test_the_page_shows_the_rule_under_the_category():
    page = read("Views", "Transactions", "TransactionDetailView.swift")
    card = page.split("private var categoryCard: some View")[1].split("private func categoryRow")[0]
    assert 'row(title: "Recurring", sub: rule.when, chevron: true, icon: "repeat")' in card
    assert '.sheet(isPresented: $recurringMenu) { recurringSheet }' in page
    assert 'write("POST", "api/transactions/\\(t.id)/not-recurring")' in page
    assert 'app.say("Left out of the rule"' in page and 'app.say("Rule stopped"' in page
    assert 'write("DELETE", "api/recurring-transfers/\\(rule)")' in page
    models = read("API", "Models.swift")
    assert 'case recurringRule = "recurring_rule"' in models
