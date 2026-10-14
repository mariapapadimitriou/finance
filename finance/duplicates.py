"""Possible duplicate transactions (Pearl THL-165, D-01 to D-03).

Import de-duplication (`dedupe`) already drops what it is sure of: the same
row delivered twice — the same Plaid id, the same line of the same file — is
skipped on arrival with no question asked, and only counted in the import log
(imported vs duplicates). That stays silent on purpose.

What it cannot be sure of is the same purchase arriving from two places that
describe it differently:

* a statement file and the bank connection, for the same card;
* one card connected twice, so it sits under two account ids
  (`audit.same_card_pairs`, the old "Possible overlap" check);
* a pending charge whose posted version came back under a new id without
  naming it, so Plaid never said the pending row was gone;
* a purchase typed in by hand that the bank later sent too.

Those are *likely* duplicates: the same card, the same amount to the cent,
the same day or a few days apart, a similar merchant, and two different
sources. Merging them silently would sometimes lose a real purchase (two
identical coffees), so they are asked about instead. Until she answers, the
copy is counted once — it shows in the list as not counted — and the review
queue asks "Is this the same purchase?":

* Same purchase → the copy is soft-hidden: the row and its link to its twin
  stay, nothing is deleted, and Undo brings the question back.
* Two different purchases → both count.

The state lives beside the rows (`txn_duplicates`), keyed by the copy's
fingerprint, so a sync can't undo an answer.
"""

from __future__ import annotations

from datetime import date
from difflib import SequenceMatcher

from .models import Transaction

# How far apart the two copies may be. A statement prints the posted date and
# the bank feed the authorised one; a pending charge posts within a few days.
WINDOW_DAYS = 3
# How alike the cleaned-up merchant names have to be. Loose, because the
# amount and the card already have to match exactly.
MERCHANT_SIMILARITY = 0.6

PENDING, SAME, DIFFERENT = "pending", "same", "different"
# What the store says in `excluded` for a copy counted once (see `_CHARGE_COLUMNS`).
REASON = "Possible duplicate"
STATES = (PENDING, SAME, DIFFERENT)


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def _similar(a: str, b: str) -> float:
    a, b = (a or "").lower().strip(), (b or "").lower().strip()
    if not a or not b:
        return 0.0
    if a == b or a.startswith(b) or b.startswith(a):
        return 1.0
    return SequenceMatcher(None, a, b).ratio()


def _pending(t: Transaction) -> bool:
    return bool((t.raw or {}).get("pending"))


def _plaid_id(t: Transaction) -> str:
    raw = t.raw or {}
    return str(raw.get("transaction_id") or raw.get("plaid_id") or "")


def source_label(t: Transaction) -> str:
    """Where a copy came from, in her words: "from your bank connection"."""
    if t.source == "manual":
        return "added by hand"
    if t.source == "plaid":
        return "pending at your bank" if _pending(t) else "from your bank connection"
    return "from a statement file"


def source_verb(t: Transaction) -> str:
    """How the copy arrived, for the line under the bank's description."""
    if t.source == "manual":
        return "added by hand"
    return "synced" if t.source == "plaid" else "uploaded"


def _rank(t: Transaction) -> tuple:
    """Which of a pair to keep: the bank connection's posted row first, then
    its pending row, then a statement file, then a row typed by hand."""
    if t.source == "plaid":
        order = 1 if _pending(t) else 0
    elif t.source == "manual":
        order = 3
    else:
        order = 2
    return (order, t.date, t.fingerprint)


def _different_sources(a: Transaction, b: Transaction, same_card: set) -> bool:
    """Two records of one purchase, rather than one feed listing two."""
    if a.account_id != b.account_id:
        pair = (a.account_id, b.account_id) if a.account_id <= b.account_id \
            else (b.account_id, a.account_id)
        return pair in same_card
    if a.source != b.source:
        return True
    # One feed: only a pending row beside a posted one with its own id. Two
    # posted rows from one feed on one card are two purchases.
    if a.source == "plaid" and _pending(a) != _pending(b):
        return _plaid_id(a) != _plaid_id(b)
    return False


def detect(transactions: list[Transaction], known: set[str] | frozenset = frozenset(),
           same_card: set | None = None) -> list[tuple[Transaction, Transaction]]:
    """Likely duplicates not yet recorded, as (copy, twin) pairs.

    `known` is every fingerprint already in a pair, either side, answered or
    not: an answered pair is never asked again, and a row is paired at most
    once. Rows you left out, and money in, are not looked at.
    """
    if same_card is None:
        from .audit import same_card_pairs
        same_card = same_card_pairs(transactions)
    rows = [t for t in transactions
            if t.amount > 0 and not t.excluded and t.fingerprint not in known]
    by_amount: dict[str, list[Transaction]] = {}
    for t in rows:
        by_amount.setdefault(f"{t.amount:.2f}", []).append(t)

    taken: set[str] = set()
    pairs: list[tuple[Transaction, Transaction]] = []
    for group in by_amount.values():
        if len(group) < 2:
            continue
        group.sort(key=lambda t: (t.date, t.fingerprint))
        candidates = []
        for i, a in enumerate(group):
            for b in group[i + 1:]:
                gap = _days_apart(a.date, b.date)
                if gap > WINDOW_DAYS:
                    break
                if a.fingerprint == b.fingerprint:
                    continue
                if not _different_sources(a, b, same_card):
                    continue
                likeness = _similar(a.merchant, b.merchant)
                if likeness < MERCHANT_SIMILARITY:
                    continue
                candidates.append((gap, -likeness, a, b))
        # Closest first, so each row pairs with its best match once.
        candidates.sort(key=lambda c: (c[0], c[1], c[2].fingerprint, c[3].fingerprint))
        for _, _, a, b in candidates:
            if a.fingerprint in taken or b.fingerprint in taken:
                continue
            keep, copy = sorted((a, b), key=_rank)
            taken.update((a.fingerprint, b.fingerprint))
            pairs.append((copy, keep))
    return pairs


def scan(store, transactions: list[Transaction] | None = None) -> int:
    """Record every new likely duplicate as a question. Returns how many."""
    txns = transactions if transactions is not None else store.all_transactions()
    known = store.duplicate_ids()
    found = detect(txns, known)
    for copy, twin in found:
        store.add_duplicate(copy.fingerprint, twin.fingerprint)
    return len(found)


def is_copy(t: Transaction) -> bool:
    """A copy counted once until she answers, or one she said was the same."""
    return bool(t.duplicate_of) and t.duplicate_state in (PENDING, SAME)


def is_hidden(t: Transaction) -> bool:
    """A copy she said was the same purchase: kept, but not listed."""
    return bool(t.duplicate_of) and t.duplicate_state == SAME


def brief(t: Transaction) -> dict:
    """One side of D-02's comparison."""
    return {"id": t.fingerprint, "date": t.date[:10], "merchant": t.merchant,
            "description": t.description, "amount": t.amount,
            "account_id": t.account_id,
            "account": (t.account_label or "").replace("••", "··"),
            "source": t.source, "source_label": source_label(t),
            "source_verb": source_verb(t)}


def questions(transactions: list[Transaction], found_on: dict[str, str] | None = None
              ) -> list[dict]:
    """The pending pairs, for the needs-a-look queue (D-02)."""
    by_id = {t.fingerprint: t for t in transactions}
    found_on = found_on or {}
    out = []
    for t in transactions:
        if t.duplicate_state != PENDING or not t.duplicate_of:
            continue
        twin = by_id.get(t.duplicate_of)
        if twin is None:
            continue
        copy = brief(t)
        copy["found_on"] = (found_on.get(t.fingerprint) or "")[:10]
        out.append({"key": "dup:" + t.fingerprint, "txn": copy, "twin": brief(twin),
                    "reason": "The same amount came in from two places on the same day. "
                              "We’d rather check than count it twice."
                    if t.date[:10] == twin.date[:10] else
                    "The same amount came in from two places a few days apart. "
                    "We’d rather check than count it twice."})
    return out
