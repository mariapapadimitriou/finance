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

import re
from datetime import date, timedelta

from .models import Transaction

UNSORTED = "Unsorted transfers"
NEUTRAL = "Transfers"

# How far apart the two ends of one transfer may post. Interac and bill
# payments land in a day or two; a card payment can take three business days
# to show on the card.
WINDOW_DAYS = 4

_DECIDED = {"user", "merchant_override"}
# Sorted by a destination rule: re-decided on every run, so a transfer whose
# other end turns up later becomes neutral after all.
RULED = "destination"


def others(t: Transaction) -> bool:
    """A row on a joint account that isn't yours: another member's money."""
    return bool(getattr(t, "joint", None)) and abs(t.my_share or 0.0) < 0.005


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


# Words that say "a transfer" without saying where to.
_GENERIC = {"send", "sent", "e", "tfr", "etfr", "e-tfr", "transfer", "e-transfer",
            "etransfer", "interac", "to", "fr", "from", "online", "banking",
            "payment", "pmt", "bill", "mobile", "internet", "debit", "withdrawal",
            "deposit", "the", "ref", "conf", "autodeposit", "request", "money"}
_ACCOUNT = re.compile(r"(?:\btfr|\btransfer)[\s-]*(?:to|fr|from)\b[^\d]{0,8}(\d[\d\s-]{3,})",
                      re.I)
_MASKED = re.compile(r"(?:••|\*{2,}|x{2,})\s*(\d{4})\b", re.I)
_REFERENCE = re.compile(r"\*+\s*\w+|#\s*\w+|\b\w*\d\w*\b")


def destination(t: Transaction) -> tuple[str, str] | None:
    """Where a transfer went, as (key, label), stable across transfers.

    E-transfer descriptions carry a new reference every time ("SEND E-TFR
    ***Q7k"), so the description can't be learned. In order: the payee Plaid
    names; the destination account's digits ("TFR-TO 1234567" → ••4567); what
    is left of the name once references are taken out. A transfer that says
    nothing but "SEND E-TFR" has no destination: nothing safe to learn.
    """
    who = str((t.raw or {}).get("counterparty") or "").strip()
    if who:
        return "to:" + " ".join(who.lower().split()), who
    text = t.description or ""
    m = _ACCOUNT.search(text)
    digits = re.sub(r"\D", "", m.group(1)) if m else ""
    if not digits:
        m = _MASKED.search(text)
        digits = m.group(1) if m else ""
    if len(digits) >= 4:
        return "acct:" + digits[-4:], "••" + digits[-4:]
    words = [w for w in re.split(r"[^a-z]+",
                                 _REFERENCE.sub(" ", (t.description or t.merchant or "").lower()))
             if w and w not in _GENERIC]
    if words and sum(len(w) for w in words) >= 3:
        return "name:" + " ".join(words), " ".join(words).title()
    merchant = " ".join((t.merchant or "").lower().split())
    if merchant and any(w not in _GENERIC for w in re.split(r"[^a-z0-9]+", merchant) if w):
        return "m:" + merchant, t.merchant
    return None


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


def match_transfers(transactions: list[Transaction], today: str | None = None,
                    destinations: dict[str, str] | None = None) -> dict[str, str]:
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

    Only what is still unmatched goes where you said its destination goes
    (`destinations`, key → category). Whatever is left is Unsorted when it's
    recent, and neutral when it's older than `ASK_DAYS`.
    """
    candidates = sorted(
        (t for t in transactions
         if t.amount > 0 and _is_bank(t) and not others(t)
         and (t.category in (NEUTRAL, UNSORTED) or t.category_source == RULED)
         and t.category_source not in _DECIDED),
        key=lambda t: (t.date, t.fingerprint))
    # A friend paying you back is not the other end of anything you sent, and
    # neither is your pay. Nor is a payment arriving on a loan: paying the
    # mortgage is a bill, not money moving between your own pockets, so it
    # must not vanish as neutral when the mortgage account is connected.
    inflows = [t for t in transactions
               if t.amount < 0 and not t.repays and t.category != "Income"
               and str((t.raw or {}).get("account_type", "")).lower() != "loan"]

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
    # Another member's transfers on a joint account aren't yours to sort; any
    # that were waiting before the account was marked joint go back to neutral.
    for t in transactions:
        if (t.amount > 0 and _is_bank(t) and others(t)
                and (t.category == UNSORTED or t.category_source == RULED)
                and t.category_source not in _DECIDED):
            out[t.fingerprint] = NEUTRAL

    rules = destinations or {}
    for t in candidates:
        if t.fingerprint not in out:
            where = destination(t)
            if where and where[0] in rules:
                out[t.fingerprint] = rules[where[0]]
                continue
            recent = date.fromisoformat(t.date[:10]) >= cutoff
            out[t.fingerprint] = UNSORTED if recent else NEUTRAL
    return out


def apply_transfer_matches(store, transactions: list[Transaction] | None = None) -> int:
    """Run the match over the ledger and write what changed."""
    txns = transactions if transactions is not None else store.all_transactions()
    current = {t.fingerprint: (t.category, t.category_source) for t in txns}
    changes = {}
    for tid, cat in match_transfers(txns, destinations=store.destinations()).items():
        source = "transfer_match" if cat in (NEUTRAL, UNSORTED) else RULED
        if current.get(tid) != (cat, source):
            changes[tid] = (cat, source)
    return store.set_categories(changes) if changes else 0


def migrate_overrides(store) -> int:
    """Turn "remember this name" choices made on transfers into destination
    rules, once.

    Those were merchant overrides, which apply before matching and so kept a
    transfer Saved or Spent even when its other end was in Spendie. A rule
    for the destination applies only to what stays unmatched. Overrides that
    cover anything other than bank transfers are left as they are.
    """
    if store.setting("destinations_migrated") == "1":
        return 0
    from .categorize import categorize
    txns = store.all_transactions()
    by_name: dict[str, list[Transaction]] = {}
    for t in txns:
        by_name.setdefault((t.merchant or "").strip().lower(), []).append(t)
    moved = 0
    for key, category in store.overrides().items():
        rows = by_name.get(key, [])
        if not rows or not all(
                t.amount > 0 and _is_bank(t)
                and categorize(t.merchant, t.description,
                               (t.raw or {}).get("issuer_category", ""))[0] == NEUTRAL
                for t in rows):
            continue
        for t in rows:
            where = destination(t)
            if where:
                store.set_destination(where[0], category, where[1])
        store.clear_override(key)
        store.write_categories({t.fingerprint: (NEUTRAL, "transfer_match") for t in rows})
        moved += 1
    store.set_setting("destinations_migrated", "1")
    return moved


def unsorted(transactions: list[Transaction]) -> list[Transaction]:
    """What is waiting for you to say where it went, newest first."""
    rows = [t for t in transactions if t.category == UNSORTED and t.amount > 0]
    return sorted(rows, key=lambda t: t.date, reverse=True)
