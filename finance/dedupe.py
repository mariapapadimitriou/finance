"""Deduplication across overlapping exports.

The problem this solves: you download "last 90 days" from a card in March and
again in April. The overlap re-delivers ~60 days of rows you already have. Some
of them come back with a different posted date, and a few descriptors get
rewritten once the charge settles.

Two passes:

`exact`   — fingerprint equality (account + date + amount + descriptor + seq).
            Catches the common case, and is safe because the sequence number
            keeps genuinely repeated charges distinct.

`near`    — same account, same amount, similar merchant, within a few days.
            Catches the settle-shift case where the transaction date itself
            moved. Deliberately conservative: it requires the merchant key to
            match, so two $12 lunches at different places never merge.
"""

from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher

from .models import Transaction

# How far a re-posted charge is allowed to drift before we stop calling it the
# same charge. Card networks settle within a few business days.
NEAR_WINDOW_DAYS = 4
MERCHANT_SIMILARITY = 0.86


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def _similar(a: str, b: str) -> float:
    if a == b:
        return 1.0
    return SequenceMatcher(None, a.lower(), b.lower()).ratio()


def dedupe_batch(transactions: list[Transaction]) -> tuple[list[Transaction], int]:
    """Drop exact repeats inside a single import batch."""
    seen: set[str] = set()
    kept: list[Transaction] = []
    dropped = 0
    for t in transactions:
        fp = t.fingerprint
        if fp in seen:
            dropped += 1
            continue
        seen.add(fp)
        kept.append(t)
    return kept, dropped


def split_new(incoming: list[Transaction], existing: list[Transaction]
              ) -> tuple[list[Transaction], list[Transaction]]:
    """Partition incoming rows into (new, duplicates) against what we already store."""
    existing_fps = {t.fingerprint for t in existing}

    # Index existing rows by (account, amount) so the near-match scan stays cheap.
    index: dict[tuple[str, str], list[Transaction]] = {}
    for t in existing:
        index.setdefault((t.account_id, f"{t.amount:.2f}"), []).append(t)

    new: list[Transaction] = []
    dupes: list[Transaction] = []
    # Rows accepted in this batch also become candidates, so a file containing
    # its own near-duplicate does not sneak both copies in.
    accepted_index = dict(index)

    for t in incoming:
        if t.fingerprint in existing_fps:
            dupes.append(t)
            continue

        if _has_near_match(t, accepted_index.get((t.account_id, f"{t.amount:.2f}"), [])):
            dupes.append(t)
            continue

        new.append(t)
        existing_fps.add(t.fingerprint)
        accepted_index.setdefault((t.account_id, f"{t.amount:.2f}"), []).append(t)

    return new, dupes


def _has_near_match(t: Transaction, candidates: list[Transaction]) -> bool:
    for c in candidates:
        if _days_apart(t.date, c.date) > NEAR_WINDOW_DAYS:
            continue
        # Same day + same amount + same merchant is a legitimate repeat purchase
        # (two identical coffees), and the sequence number already separates
        # those. Only a date shift indicates a re-posted duplicate.
        if t.date == c.date:
            continue
        if _similar(t.merchant, c.merchant) >= MERCHANT_SIMILARITY:
            return True
    return False


def find_duplicate_charges(transactions: list[Transaction]) -> list[dict]:
    """Find likely double-billings worth disputing.

    Distinct from import dedupe: these are rows we believe are *really* on the
    statement twice — same merchant, same amount, same or adjacent day — which
    usually means the merchant charged you twice.
    """
    groups: dict[tuple, list[Transaction]] = {}
    for t in transactions:
        if t.amount <= 0:
            continue
        groups.setdefault((t.merchant, f"{t.amount:.2f}"), []).append(t)

    findings = []
    for (merchant, amount), rows in groups.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r.date)
        for i in range(len(rows) - 1):
            a, b = rows[i], rows[i + 1]
            if _days_apart(a.date, b.date) <= 1:
                findings.append({
                    "merchant": merchant,
                    "amount": float(amount),
                    "dates": [a.date, b.date],
                    "account": a.account_name or a.account_id,
                })
    return findings
