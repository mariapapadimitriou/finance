"""The split sheet's button says "Split", not every name (product owner,
2026-11-27: "Split with anastasia …, Diana …, Ileena … and Christina …" was
cluttered; the names are already above it)."""
from pathlib import Path

SRC = (Path(__file__).resolve().parents[1] / "ios/Pearl/Views/Transactions/SplitFlow.swift").read_text()


def test_button_says_split():
    title = SRC[SRC.index("private var primaryTitle: String"):]
    title = title[:title.index("\n    }\n")]
    assert 'if light { return "Split" }' in title
    assert "andList(people)" not in title
