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

from datetime import date, timedelta

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


# Only recent transfers are asked about. Plaid backfills two years, and
# nobody remembers where an e-transfer from last spring went; an old one that
# still matches nothing is left neutral rather than counted as spending.
ASK_DAYS = 60

# Subsets are searched over at most this many outflows, so the search stays
# small (2**12) however busy the account.
SUBSET_LIMIT = 12


def _cents(x: float) -> int:
    return int(round(x * 100))


def _subset_summing(rows: list[Transaction], target: int) -> list[Transaction] | None:
    """Some of `rows` whose amounts add up to `target` cents, or None."""
    rows = sorted(rows, key=lambda t: -t.amount)[:SUBSET_LIMIT]
    amounts = [_cents(t.amount) for t in rows]
    best = None

    def walk(i: int, left: int, picked: list[int]) -> bool:
        nonlocal best
        if abs(left) <= 1 and picked:
            best = list(picked)
            return True
        if i == len(rows) or left < -1:
            return False
        picked.append(i)
        if walk(i + 1, left - amounts[i], picked):
            return True
        picked.pop()
        return walk(i + 1, left, picked)

    walk(0, target, [])
    return [rows[i] for i in best] if best else None


def match_transfers(transactions: list[Transaction],
                    today: str | None = None) -> dict[str, str]:
    """The category each sortable outflow should have: Transfers when its
    other end is here, Unsorted transfers when it isn't.

    Pure: returns {txn_id: category} for the rows it may decide, changed or
    not. Each arrival is used once. Passes, in order:

    1. One to one — the same amount arriving on another account within a few
       days, nearest first.
    2. Out and back — the same amount returning to the same account (a
       reversal or a bounce).
    3. Several out, one in — outflows from one account on the same day or the
       next that add up to one arrival elsewhere (300 + 200 → 500).
    4. The day nets out — everything that left on a day equals everything
       that arrived in your other accounts that day.

    Whatever is left is Unsorted when it's recent, and neutral when it's older
    than `ASK_DAYS`.
    """
    candidates = sorted(
        (t for t in transactions
         if t.amount > 0 and _is_bank(t)
         and t.category in (NEUTRAL, UNSORTED)
         and t.category_source not in _DECIDED),
        key=lambda t: (t.date, t.fingerprint))
    # A friend paying you back is not the other end of anything you sent, and
    # neither is your pay.
    inflows = [t for t in transactions
               if t.amount < 0 and not t.repays and t.category != "Income"]

    used: set[str] = set()          # inflows already the other end of something
    out: dict[str, str] = {}

    def near(t, other, days=WINDOW_DAYS):
        return _days(t.date, other.date) <= days

    # 1 and 2: the same amount, on another account first, then on the same one.
    by_amount: dict[int, list[Transaction]] = {}
    for t in inflows:
        by_amount.setdefault(_cents(-t.amount), []).append(t)
    for same_account in (False, True):
        for t in candidates:
            if t.fingerprint in out:
                continue
            best = None
            for other in by_amount.get(_cents(t.amount), []):
                if other.fingerprint in used or not near(t, other):
                    continue
                if (other.account_id == t.account_id) != same_account:
                    continue
                gap = _days(t.date, other.date)
                if best is None or gap < best[0]:
                    best = (gap, other)
            if best:
                used.add(best[1].fingerprint)
                out[t.fingerprint] = NEUTRAL

    # 3: several outflows from one account adding up to one arrival elsewhere.
    for other in sorted(inflows, key=lambda t: t.amount):
        if other.fingerprint in used:
            continue
        pool: dict[str, list[Transaction]] = {}
        for t in candidates:
            if (t.fingerprint not in out and t.account_id != other.account_id
                    and near(t, other, 1)):
                pool.setdefault(t.account_id, []).append(t)
        for rows in pool.values():
            if len(rows) < 2:
                continue
            hit = _subset_summing(rows, _cents(-other.amount))
            if hit:
                used.add(other.fingerprint)
                for t in hit:
                    out[t.fingerprint] = NEUTRAL
                break

    # 4: a day whose departures and arrivals cancel.
    days: dict[str, tuple[list[Transaction], list[Transaction]]] = {}
    for t in candidates:
        if t.fingerprint not in out:
            days.setdefault(t.date[:10], ([], []))[0].append(t)
    for other in inflows:
        if other.fingerprint not in used and other.date[:10] in days:
            days[other.date[:10]][1].append(other)
    for day, (gone, arrived) in days.items():
        if not arrived:
            continue
        if abs(sum(_cents(t.amount) for t in gone)
               - sum(_cents(-o.amount) for o in arrived)) <= 1:
            for t in gone:
                out[t.fingerprint] = NEUTRAL
            used.update(o.fingerprint for o in arrived)

    cutoff = (date.fromisoformat(today) if today else date.today()) \
        - timedelta(days=ASK_DAYS)
    for t in candidates:
        if t.fingerprint not in out:
            recent = date.fromisoformat(t.date[:10]) >= cutoff
            out[t.fingerprint] = UNSORTED if recent else NEUTRAL
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
