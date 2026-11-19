"""TEST-36: Edit split › a new method starts from the split as it stands
(SplitCarry.swift), checked with swiftc where it's installed; and How to
split goes through it whenever the method changes (2026-11-19)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ios/Pearl/Views/Transactions/SplitCarry.swift"
FLOW = ROOT / "ios/Pearl/Views/Transactions/SplitFlow.swift"
CHECK = ROOT / "tests/swift/split_carry_check.swift"


@pytest.mark.skipif(shutil.which("swiftc") is None, reason="needs swiftc")
def test_split_carry(tmp_path):
    main = tmp_path / "main.swift"
    main.write_text(CHECK.read_text())
    out = tmp_path / "carry"
    subprocess.run(["swiftc", "-o", str(out), str(SOURCE), str(main)], check=True,
                   capture_output=True, timeout=300)
    run = subprocess.run([str(out)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr


def test_every_method_change_carries_the_split():
    src = FLOW.read_text()
    assert "selection: Binding(get: { mode }, set: { switchMode(to: $0) })" in src
    assert "onPick: { m in switchMode(to: m)" in src
    assert "SplitCarry.values(" in src
    # The old reset wiped the split on every change.
    assert ".onChange(of: mode)" not in src
