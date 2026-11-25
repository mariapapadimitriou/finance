"""The toast draws the Undo it is given now (2026-11-25): "Undone." on Needs
a look kept the toast before's Undo, which did nothing."""

from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "ios" / "Pearl" / "Views" / "Profile" / "AccountsViews.swift").read_text()


def test_the_toast_is_never_rebuilt_in_on_change():
    body = SRC.split("struct UndoToast: View")[1].split("\n}\n")[0]
    assert "PearlToast.Model(id: id, text: text" in body and "run: undo)" in body
    assert "@State private var model" not in body
    for handler in body.split(".onChange(")[1:]:
        assert "Model(" not in handler
