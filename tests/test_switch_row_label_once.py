"""TEST-39 (G5-Notifications, N-02): each switch row says its label once.
The A+ switch style draws whatever label the Toggle has, .labelsHidden() or
not, so SwitchRow's Toggle has an empty label on screen and the title as
its VoiceOver label (2026-11-19)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEARL = ROOT / "ios/Pearl"


def _switch_row() -> str:
    src = (PEARL / "Views/Profile/PrivacyViews.swift").read_text()
    start = src.index("struct SwitchRow: View")
    return src[start:src.index("struct RowChevron", start)]


def test_switch_row_draws_the_title_once():
    row = _switch_row()
    assert "Toggle(isOn: Binding(get: { isOn }, set: changed)) { EmptyView() }" in row
    assert "Toggle(title" not in row
    assert ".accessibilityLabel(title)" in row and ".accessibilityHint(hint ?? sub ?? \"\")" in row


def test_no_toggle_relies_on_labels_hidden():
    # APToggleStyle (set by nacreScreen) ignores .labelsHidden(); a Toggle
    # that uses it would show its label twice.
    offenders = []
    for p in PEARL.rglob("*.swift"):
        for m in re.finditer(r"Toggle\([^\n]*\n(\s*\.[^\n]*\n){0,3}", p.read_text()):
            if ".labelsHidden()" in m.group(0):
                offenders.append(str(p.relative_to(PEARL)))
    assert offenders == []
