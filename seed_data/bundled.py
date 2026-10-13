"""Statements shipped with the app: the owner's closed card.

The button that loaded them (Profile › From a file) was removed with file
import (C1). What stays is the list and `read`, for two reasons: `app.py`
uses them to find and remove a copy that was once loaded into another
account's ledger, and the tests use the file as a real-world ledger.

What follows is why they were committed in the first place.

This is not the seeder. The seeder ran on a cold start and filled an empty
ledger by itself, which is why a reset has to leave a marker telling it not to;
a file that loads itself is a file that undoes someone's decision to clear the
ledger.

What is here loads when asked and never otherwise. It exists for a card that
cannot be connected: a closed account has no live feed, Plaid has nothing to
sync, and the statements are the only record there will ever be. Committing
them is the only way they survive a database that can be emptied.

Clicking twice is harmless. The rows go through the ordinary import pipeline,
so the fingerprint check that stops a re-uploaded file from counting twice
stops this too.

Anything committed here is readable by anyone who can reach the repository.
Account numbers are masked before a file lands in this directory, even where
the bank already masked them, because the app reads the descriptor and never
the digits.
"""

from __future__ import annotations

from pathlib import Path

HERE = Path(__file__).parent

# One entry per statement set. `account_id` is fixed rather than derived from
# the filename: these rows have to land in the same account every time, and the
# filename is not a promise.
BUNDLED: list[dict] = [
    {
        "key": "scotiabank_amex",
        "file": "scotiabank_amex_2025_2026.csv",
        "account_id": "scotiabank_amex",
        "account_name": "Scotiabank Amex (closed)",
        "label": "Scotiabank Amex",
        "period": "March 2025 – August 2026",
        "note": (
            "A closed card. Plaid cannot sync it, so these statements are the "
            "whole of its history and will not change."
        ),
    },
]


def _entry(key: str) -> dict | None:
    return next((b for b in BUNDLED if b["key"] == key), None)


def read(key: str) -> tuple[str, dict]:
    """The file's text and its entry. Raises KeyError / FileNotFoundError."""
    entry = _entry(key)
    if entry is None:
        raise KeyError(key)
    path = HERE / entry["file"]
    return path.read_text(encoding="utf-8"), entry
