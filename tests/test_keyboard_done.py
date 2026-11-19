"""TEST-37: the keyboard's Done pill never sits on the primary button. One
footer modifier (KeyboardDone.swift) puts Done above the keyboard and lifts
Next/Save above both; the stock keyboard toolbar, whose floating pill landed
on the button, isn't used anywhere (2026-11-19)."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEARL = ROOT / "ios/Pearl"


def test_no_stock_keyboard_toolbar():
    offenders = [str(p.relative_to(PEARL)) for p in PEARL.rglob("*.swift")
                 if "placement: .keyboard" in p.read_text()]
    assert offenders == []


def test_sheets_with_done_use_the_shared_footer():
    split = (PEARL / "Views/Transactions/SplitFlow.swift").read_text()
    share = (PEARL / "Views/Transactions/YourShareViews.swift").read_text()
    assert ".keyboardDoneFooter { focused = nil; searching = false }" in split
    assert ".keyboardDoneFooter { typing = nil }" in share


def test_the_footer_lifts_clear_of_the_keyboard():
    src = (PEARL / "Views/Components/KeyboardDone.swift").read_text()
    assert "keyboardWillChangeFrameNotification" in src and "keyboardWillHideNotification" in src
    assert ".padding(.bottom, lift)" in src
    assert 'Text("Done")' in src and "minHeight: 44" in src
