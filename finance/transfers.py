"""Where money leaving a bank account went: somewhere you can see, or not.

Every dollar that leaves is either spent or saved. A transfer is only neutral
when Spendie can see both ends of it — a chequing account paying a card that
is also here, or moving money into a savings account that is also here. Then
it really is the same money changing pockets, and counting it would count it
twice.

Anything else that leaves a bank account went somewhere Spendie can't see: a
brokerage that isn't connected, a landlord paid by e-transfer, a friend. Until
you say which, it is "Unsorted transfers" and counts as spending — an
undecided dollar is assumed gone, never assumed saved.

Only bank accounts are sorted this way (Plaid's `depository`: chequing and
savings). A card's own outflows that read as transfers — a balance transfer —
are left alone, and so are imported statements, whose account type is
unknown.

Never touched: a category you set yourself, and one a merchant override
chose ("always Saved for QUESTRADE"). Those are decisions, not guesses.
"""

from __future__ import annotations

from datetime import date

from .models import Transaction

UNSORTED = "Unsorted transfers"
NEUTRAL = "Transfers"

# How far apart the two ends of one transfer may post. Interac and bill
# payments land in a day or two; a card payment can take three business days
# to show on the card.
WINDOW_DAYS = 4

_DECIDED = {"user", "merchant_override"}


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


def match_transfers(transactions: list[Transaction]) -> dict[str, str]:
    """The category each sortable outflow should have: Transfers when its
    other end is here, Unsorted transfers when it isn't.

    Pure: returns {txn_id: category} for the rows it may decide, changed or
    not. Each inflow pairs with one outflow at most, nearest date first, so
    two $500 payments can't both lean on one $500 arrival.
    """
    candidates = sorted(
        (t for t in transactions
         if t.amount > 0 and _is_bank(t)
         and t.category in (NEUTRAL, UNSORTED)
         and t.category_source not in _DECIDED),
        key=lambda t: (t.date, t.fingerprint))
    # A friend paying you back is not the other end of anything you sent.
    inflows = [t for t in transactions if t.amount < 0 and not t.repays]

    by_amount: dict[float, list[Transaction]] = {}
    for t in inflows:
        by_amount.setdefault(round(-t.amount, 2), []).append(t)

    used: set[str] = set()
    out: dict[str, str] = {}
    for t in candidates:
        best = None
        for other in by_amount.get(round(t.amount, 2), []):
            if other.account_id == t.account_id or other.fingerprint in used:
                continue
            gap = _days(t.date, other.date)
            if gap > WINDOW_DAYS:
                continue
            if best is None or gap < best[0]:
                best = (gap, other)
        if best:
            used.add(best[1].fingerprint)
            out[t.fingerprint] = NEUTRAL
        else:
            out[t.fingerprint] = UNSORTED
    return out


def apply_transfer_matches(store, transactions: list[Transaction] | None = None) -> int:
    """Run the match over the ledger and write what changed."""
    txns = transactions if transactions is not None else store.all_transactions()
    current = {t.fingerprint: t.category for t in txns}
    changes = {tid: (cat, "transfer_match")
               for tid, cat in match_transfers(txns).items()
               if current.get(tid) != cat}
    return store.set_categories(changes) if changes else 0


def unsorted(transactions: list[Transaction]) -> list[Transaction]:
    """What is waiting for you to say where it went, newest first."""
    rows = [t for t in transactions if t.category == UNSORTED and t.amount > 0]
    return sorted(rows, key=lambda t: t.date, reverse=True)
