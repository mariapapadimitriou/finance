"""A+ G5b (REDESIGN-12, 2026-11-18): the iPhone's Recurring transfers,
Debts, and Categories and rules read as the Claude Design boards: short
toasts with Undo, the rule edit's "Also moves the N earlier ones." with
Only new ones, and no stock iOS dialogs."""

from pathlib import Path

PROFILE = Path(__file__).resolve().parents[1] / "ios" / "Pearl" / "Views" / "Profile"
RULES = (PROFILE / "CategoriesRulesView.swift").read_text()
RECURRING = (PROFILE / "RecurringTransfersView.swift").read_text()
DEBTS = (PROFILE / "DebtsView.swift").read_text()


def test_short_toasts():
    assert '"No longer recurring"' in RECURRING
    assert '"Now \\(label)"' in RECURRING          # "Now Into savings"
    assert '"Rule deleted"' in RULES
    assert '"\\(category) hidden"' in RULES        # "Fitness hidden"
    assert '"Details saved"' in DEBTS


def test_undo_goes_through_the_server():
    for src in (RULES, RECURRING):
        assert "api/transactions/undo" in src
    assert "undo: reply.undo.map(undoCall)" in RULES


def test_the_rule_edit_moves_earlier_ones_or_only_new_ones():
    assert "api/rules/earlier" in RULES
    assert "Also moves the" in RULES and "earlier ones" in RULES
    assert '"Only new ones"' in RULES
    assert '"earlier": move' in RULES
    assert 'Now \\(category) · \\(n) moved' in RULES


def test_red_only_on_the_entry_row():
    assert 'title: "Delete this rule", tone: Pearl.danger' in RULES
    assert 'title: "Remove this rule", tone: Pearl.danger' in RULES
    assert 'title: "Stop treating it as recurring"' in RECURRING
    assert 'primary: "Remove the rule"' in RULES


def test_no_stock_dialogs_and_a_plus_parts():
    for src in (RULES, RECURRING, DEBTS):
        for stock in (".alert(", ".confirmationDialog(", "Menu {", "GlassCard", "NacreButtonStyle"):
            assert stock not in src
    assert "APCard" in RECURRING and "APCard" in DEBTS
    assert "ProfileHeading(title: \"Categories and rules\")" in RULES
    assert "safe to spend" not in (RULES + RECURRING + DEBTS).lower()
