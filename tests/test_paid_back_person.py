"""PaidBackPerson.swift, checked with swiftc where it's installed: Paid back ›
A person never opens an empty Who paid you back? (PP-01), and a name that is
clearly one person who owes her goes to PB-30 without asking (2026-11-17)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ios/Pearl/Views/Transactions/PaidBackPerson.swift"
CHECK = ROOT / "tests/swift/paid_back_person_check.swift"
PARTS = ROOT / "ios/Pearl/Views/Transactions/PartsFlow.swift"


@pytest.mark.skipif(shutil.which("swiftc") is None, reason="needs swiftc")
def test_paid_back_person(tmp_path):
    main = tmp_path / "main.swift"
    main.write_text(CHECK.read_text())
    out = tmp_path / "paid_back_person"
    subprocess.run(["swiftc", "-o", str(out), str(SOURCE), str(main)], check=True,
                   capture_output=True, timeout=300)
    run = subprocess.run([str(out)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr


def test_pp01_is_not_a_sheet_on_a_spinner():
    """PP-01 is the parts sheet's own content, its rows taken when it opens;
    a load that fails or never answers shows Try again."""
    src = PARTS.read_text()
    assert ".sheet(isPresented: $askWho" not in src
    assert "if let ask = askWho { askWhoView(ask) }" in src
    assert "PaidBackPerson.route(" in src
    assert "LoadState(error: e)" in src
    assert "withDeadline(" in src
