"""Manually entered transactions, and keeping them out of the way of imports.

Typing a purchase in before the statement arrives is useful — the safe-to-spend
number is wrong all week otherwise. It also creates the obvious hazard: the
statement shows up later carrying the same purchase, and now it is in twice.

Both directions are handled by the same fingerprint machinery the importers
use, so a manual row and an imported row that describe the same purchase
collapse into one:

  *entering*  — a new manual row is checked against everything already stored,
                exactly as an import would be, and near-matches are reported
                rather than silently merged. You decide.
  *importing* — a statement row that matches a manual row *supersedes* it: the
                manual row is dropped and the imported one kept. The statement
                is the authority on the date, the descriptor and which card it
                landed on; the row you typed was a placeholder for exactly this.

That direction cannot be left to the importer's own dedupe. It keys on the
account, and a row typed by hand has no account yet; the hand-typed date is
often a day off, and the descriptor almost never matches the card's. Anything
loose enough to catch that would be far too loose to apply between two real
statements, so it applies only where one side is a placeholder.

A category you set by hand on the manual row is the one thing worth keeping, so
it travels onto the imported row rather than dying with the placeholder.
"""

from __future__ import annotations

import re

from .dedupe import NEAR_WINDOW_DAYS, _days_apart, _similar
from .models import Transaction, normalize_merchant, parse_amount, parse_date


def build(date_str: str, description: str, amount, account_id: str = "manual",
          account_name: str = "Added by hand", category: str = "",
          currency: str = "CAD") -> Transaction | None:
    """Turn form input into a Transaction, or None when it is unusable."""
    iso = parse_date(str(date_str))
    value = parse_amount(amount)
    if iso is None or value is None or not str(description).strip():
        return None

    t = Transaction(
        date=iso,
        description=re.sub(r"\s+", " ", str(description).strip()),
        amount=value,
        account_id=account_id or "manual",
        account_name=account_name or "Added by hand",
        currency=currency,
        source="manual",
    )
    if category:
        t.category, t.category_source = category, "user"
    return t


def find_possible_duplicates(candidate: Transaction, existing: list[Transaction]
                             ) -> list[dict]:
    """Rows that might already be this purchase.

    Deliberately looser than the importer's rule: a hand-typed date is often a
    day or two off from the posted one, and the description rarely matches the
    card descriptor. Amount is the anchor, and it reports rather than decides.
    """
    hits = []
    for e in existing:
        if abs(e.amount - candidate.amount) > 0.01:
            continue
        gap = _days_apart(candidate.date, e.date)
        if gap > NEAR_WINDOW_DAYS + 3:
            continue
        similarity = _similar(candidate.merchant, e.merchant)
        # Same amount within a few days is worth showing even when the
        # descriptions look nothing alike, which is the usual case.
        hits.append({
            "id": e.fingerprint,
            "date": e.date,
            "merchant": e.merchant,
            "description": e.description,
            "amount": e.amount,
            "account": e.account_name or e.account_id,
            "source": e.source,
            "days_apart": gap,
            "merchant_similarity": round(similarity, 2),
            "confidence": "high" if (gap <= 1 and similarity >= 0.7)
                          else "possible",
        })
    hits.sort(key=lambda h: (h["days_apart"], -h["merchant_similarity"]))
    return hits


def supersedes(incoming: list[Transaction], existing: list[Transaction]
               ) -> list[tuple[Transaction, Transaction]]:
    """Pair imported rows with the manual placeholders they replace.

    Amount is the anchor and the window is loose, because that looseness is
    safe here in a way it would never be between two statements: the only rows
    eligible to be replaced are ones somebody typed in themselves, expecting
    the real charge to arrive. Each placeholder is claimed at most once, by the
    closest-dated import, so two typed coffees are replaced by two real ones.
    """
    placeholders = [e for e in existing if e.source == "manual"]
    if not placeholders:
        return []

    claimed: set[str] = set()
    pairs: list[tuple[Transaction, Transaction]] = []
    for t in incoming:
        if t.source == "manual":
            continue
        candidates = [
            p for p in placeholders
            if p.fingerprint not in claimed
            and abs(p.amount - t.amount) <= 0.01
            and _days_apart(p.date, t.date) <= NEAR_WINDOW_DAYS + 3
        ]
        if not candidates:
            continue
        best = min(candidates, key=lambda p: (_days_apart(p.date, t.date),
                                              -_similar(p.merchant, t.merchant)))
        claimed.add(best.fingerprint)
        pairs.append((t, best))
    return pairs


def normalized_preview(description: str) -> str:
    """What the merchant will be called once it is cleaned up."""
    return normalize_merchant(description)
