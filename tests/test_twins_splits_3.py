"""Twin build round 3, splits (2026-11-19): the source says what the boards
draw. S-03j v2's header line, G2b-JointIn2 TP-03, G2-PB30-r, S-45d and
G2-BMarkPaid. The server's G2-AUnlink words are tested in
test_split_menus.py and test_unlink_from_purchase.py."""

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
T = ROOT / "ios/Pearl/Views/Transactions"


def src(name: str) -> str:
    return (T / name).read_text()


def test_split_my_part_header_is_one_line():
    s = src("SplitFlow.swift")
    assert "JointStrip(t: t)" not in s
    assert "myPartHeader ? t.splitMyPartLine" in s or "return t.splitMyPartLine" in s
    # S-03j v2: no amount, so APQuestionWho drops the " · ".
    assert '(amount.isEmpty ? "" : " · ")' in src("SplitMenus.swift")


def test_settle_up_type_amounts():
    s = src("SplitFlow.swift")
    assert 'if settling { return "Settle up" }' in s
    assert "Settle up · type amounts" not in s
    assert 'Image(systemName: "lock.fill")' in s


def test_mark_paid_back_cancel_when_and_counts_line():
    s = src("SplitFlow.swift")
    assert 'Text("When")' in s and 'Text("Received")' not in s
    assert 'secondary: "Cancel"' in s
    assert 'counts as \\(Format.amount(after)) for you from now.' in s


def test_pb30_likely_first_then_search():
    s = src("PartsFlow.swift")
    assert '"Not here? Search other purchases"' in s
    assert 'label("Likely")' in s
    assert '" · with \\(Format.andList(hidden))"' in s
    # The joint (TP-03) and nothing-likely cases still search at once.
    assert "searching || likely.isEmpty || joint != nil" in s


def test_tp03_joint_label_and_line():
    s = src("PartsFlow.swift")
    assert 'APSectionLabel(text: "\\(first) · from your joint account", action: "Change")' in s
    assert "It stops being a transfer" not in s
    assert 'Text("The \\(Format.amount(deposit.amount)) out of \\(j.account) counts as' in s
