"""Whose was it?'s Save (WhoseAnswer.swift), checked with swiftc where it's
installed: Part of it starts at her share, so Save is on (2026-11-15)."""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
SOURCE = ROOT / "ios/Pearl/Views/Transactions/WhoseAnswer.swift"
CHECK = ROOT / "tests/swift/whose_answer_check.swift"


@pytest.mark.skipif(shutil.which("swiftc") is None, reason="needs swiftc")
def test_whose_answer(tmp_path):
    main = tmp_path / "main.swift"
    main.write_text(CHECK.read_text())
    out = tmp_path / "whose"
    subprocess.run(["swiftc", "-o", str(out), str(SOURCE), str(main)], check=True,
                   capture_output=True, timeout=300)
    run = subprocess.run([str(out)], capture_output=True, text=True, timeout=60)
    assert run.returncode == 0, run.stdout + run.stderr
