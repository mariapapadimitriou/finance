"""Money in's What was this? opens on every answer, Income then Not income,
with no Something else… step (product owner, 2026-11-26: "almost every time
I've had to click Something else, so just make the entire sheet what pops up
after you click Something else")."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1] / "ios/Pearl/Views"


def test_every_answer_at_once():
    src = (ROOT / "Review/AnswerSheet.swift").read_text()
    sheet = src[src.index("private var intoSheet: some View"):src.index("private func answer(income: Bool")]
    assert "CaseGrid(cases: CaseTile.income, chosen: answer(income: true))" in sheet
    assert "CaseGrid(cases: CaseTile.notIncome" in sheet
    assert "title: \"Something else" not in sheet and "intoEverything" not in src
    assert sheet.index('Text("INCOME")') < sheet.index('Text("NOT INCOME")')


def test_the_four_likely_tiles_are_gone():
    assert "likelyIn" not in (ROOT / "Transactions/CategorySheet.swift").read_text()


def test_a_card_payment_has_its_arrows():
    """Product owner, 2026-11-26: her sister's TD chequing → Aeroplan Visa
    payment said "Between your accounts" on its page and had no ⇄ in the list."""
    src = (Path(__file__).resolve().parents[1] / "ios/Pearl/API/Models.swift").read_text()
    rule = src[src.index("var movedBetweenAccounts: Bool {"):]
    rule = rule[:rule.index("}") + 1]
    assert "cardPayment" not in rule and '["Transfer", "Saved"]' in rule
