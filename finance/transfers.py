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

# How far apart the two ends of one transfer may post: two days (her call,
# 2026-10-22). Interac and transfers between her accounts land in a day or
# two. A payment arriving on a credit card can take three business days to
# show there, so that one case keeps CARD_DAYS — otherwise a late card
# payment would count as spending and be asked about.
WINDOW_DAYS = 2
CARD_DAYS = 4


def _window(arrival: Transaction) -> int:
    kind = str((arrival.raw or {}).get("account_type", "")).lower()
    return CARD_DAYS if kind == "credit" else WINDOW_DAYS

_DECIDED = {"user", "merchant_override", "pay_rule"}
# Sorted by a destination rule: re-decided on every run, so a transfer whose
# other end turns up later becomes neutral after all.
RULED = "destination"


def _guessed_income(t: Transaction) -> bool:
    """Money in that Pearl (or the bank's label) only guessed was income —
    not hers to call, and not a paycheque: it can still be the other end of
    one of her transfers (2026-10-22)."""
    if t.category != "Income" or t.category_source in _DECIDED or t.income_type_source == "user":
        return False
    from .income import guess
    return guess(t) != "salary"


def _guessed_arrival(t: Transaction) -> bool:
    """Money in whose category is only Pearl's guess — income she didn't
    set, or "Other" / an unsure guess nobody chose (2026-10-24). It can be
    the other end of one of her transfers between her accounts."""
    if _guessed_income(t):
        return True
    if t.amount >= 0 or t.category_source in _DECIDED or t.category_source in ("range",):
        return False
    from .categorize import is_guess
    return is_guess(t)


def others(t: Transaction) -> bool:
    """A row that is nothing of yours: one you excluded, or another member's
    money on a joint account."""
    if getattr(t, "excluded", None):
        return True
    return bool(getattr(t, "joint", None)) and abs(t.my_share or 0.0) < 0.005


def _days(a: str, b: str) -> int:
    return abs((date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days)


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


# Words that say "a transfer" without saying where to.
_GENERIC = {"send", "sent", "e", "tfr", "etfr", "e-tfr", "trf", "e-trf", "received", "recv",
            "rcvd", "transfer", "e-transfer",
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
    raw = t.raw or {}
    # Plaid's payment_meta payee (money out) or payer (money in), when the
    # bank names them (2026-10-22), before the counterparty.
    who = str(raw.get("payee" if t.amount > 0 else "payer") or raw.get("counterparty") or "").strip()
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
    # A reference code ("ab9") isn't a name: it changes every time.
    if merchant and any(w not in _GENERIC and not any(ch.isdigit() for ch in w)
                        for w in re.split(r"[^a-z0-9]+", merchant) if w):
        return "m:" + merchant, t.merchant
    return None


# Her own accounts, found in a transfer's description by their last four
# digits however the bank words it ("TFR-TO 12343333", "deposit account-3333",
# "TFSA 3333", "***3333"), or by the bank's own name for the account. Never by
# her nickname: the bank writes its own names.
_FOUR = re.compile(r"(?<!\d)\d{4}(?!\d)")
_LONG = re.compile(r"\d[\d\s-]{3,}\d")
_GENERIC_NAMES = {"chequing", "checking", "savings", "credit card", "account", "visa",
                  "mastercard", "card", "cash", "everyday"}


def linked_accounts(store) -> dict:
    """Her accounts as a transfer's description might name them:
    {"masks": {last four: (account_id, type)}, "names": {name: (account_id, type)}}.
    From the bank's names (account_sync), not her nicknames; without the
    copies she hid, and without loans (paying one stays a bill)."""
    from .plaid_link import _mask_of
    removed = {aid for aid, s in store.account_settings().items() if s["removed"]}
    masks: dict[str, tuple[str, str]] = {}
    names: dict[str, list[tuple[str, str]]] = {}
    for aid, r in store.account_sync_rules().items():
        kind = (r["account_type"] or "").lower()
        if aid in removed or kind == "loan":
            continue
        mask = _mask_of(r["account_name"])
        if mask:
            masks[mask] = (aid, kind)
        name = re.sub(r"\s*(?:••|\*{2,}|x{2,})\s*\d{2,4}\s*$", "", r["account_name"] or "",
                      flags=re.I).strip().lower()
        if len(name) >= 6 and name not in _GENERIC_NAMES:
            names.setdefault(name, []).append((aid, kind))
    # A savings or investment account she added by hand, with its last four
    # digits (2026-10-14): a transfer naming them is Saved, the same as one
    # Plaid pulled in. Either kind is money put away.
    for m in store.manual_accounts():
        if m.get("last4") and m["kind"] in ("savings", "investment"):
            masks.setdefault(m["last4"], (m["account_id"], "investment"))
    return {"masks": masks,
            "names": {n: ids[0] for n, ids in names.items() if len({i for i, _ in ids}) == 1}}


def own_account(t: Transaction, accounts: dict | None) -> tuple[str, str] | None:
    """(account_id, type) of one of her accounts that a transfer names, or None."""
    if not accounts:
        return None
    text = f"{t.description or ''} {t.merchant or ''}"
    found = [m.group(0) for m in _FOUR.finditer(text)]
    found += [re.sub(r"\D", "", m.group(0))[-4:] for m in _LONG.finditer(text)]
    found += [m.group(1) for m in _MASKED.finditer(text)]
    for digits in found:
        hit = accounts.get("masks", {}).get(digits)
        if hit and hit[0] != t.account_id:
            return hit
    low = text.lower()
    for name, hit in accounts.get("names", {}).items():
        if hit[0] != t.account_id and re.search(r"(?<!\w)" + re.escape(name) + r"(?!\w)", low):
            return hit
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
                    destinations: dict[str, str] | None = None,
                    used_out: set[str] | None = None,
                    accounts: dict | None = None,
                    pairs_out: dict[str, str] | None = None,
                    recurring: list[dict] | None = None) -> dict[str, str]:
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
    (`destinations`, key → category); then, when it names one of her own
    accounts (`accounts`, see `own_account`), an investment account makes it
    Saved and any other of hers makes it a transfer. Whatever is left is
    Unsorted when it's recent, and neutral when it's older than `ASK_DAYS`.
    """
    candidates = sorted(
        (t for t in transactions
         if t.amount > 0 and _is_bank(t) and not others(t)
         and (t.category in (NEUTRAL, UNSORTED) or t.category_source == RULED
              # Nothing placed it, but it names one of her accounts.
              or (t.category == "Other" and own_account(t, accounts)))
         and t.category_source not in _DECIDED),
        key=lambda t: (t.date, t.fingerprint))
    # A friend paying you back is not the other end of anything you sent, and
    # neither is your pay. Nor is a payment arriving on a loan: paying the
    # mortgage is a bill, not money moving between your own pockets, so it
    # must not vanish as neutral when the mortgage account is connected.
    inflows = [t for t in transactions
               if t.amount < 0 and not t.repays
               and (t.category != "Income" or _guessed_income(t))
               and not getattr(t, "excluded", None)
               and str((t.raw or {}).get("account_type", "")).lower() != "loan"]
    # Guessed income is only ever a one-to-one end (pass 1), never part of a
    # sum or a day that nets out: the loose passes need the surer arrivals.
    sure_in = [t for t in inflows if t.category != "Income"]

    used: set[str] = set()          # inflows already the other end of something
    out: dict[str, str] = {}

    def near(t, other, days=None):
        return _days(t.date, other.date) <= (days if days is not None else _window(other))

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
                if same_account and other.category == "Income":
                    continue
                gap = _days(t.date, other.date)
                if best is None or gap < best[0]:
                    best = (gap, other)
            if best:
                used.add(best[1].fingerprint)
                out[t.fingerprint] = NEUTRAL
                # Its arrival was guessed as income: it was this transfer.
                if best[1].category == "Income":
                    out[best[1].fingerprint] = NEUTRAL
                # Or guessed as "Other" on another of her accounts: the
                # same (2026-10-24). Not on the same account, where the same
                # amount back is more likely a refund.
                elif not same_account and _guessed_arrival(best[1]):
                    out[best[1].fingerprint] = NEUTRAL
                # One departure, one arrival on another of her accounts: the
                # list shows them as one line (2026-10-22).
                if pairs_out is not None and not same_account:
                    pairs_out[t.fingerprint] = best[1].fingerprint

    # 3: several outflows from one account adding up to one arrival elsewhere.
    for other in sorted(sure_in, key=lambda t: t.amount):
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
    for other in sure_in:
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
    from .recurring_transfers import paydays, rule_for
    # Every payday (2026-10-28) needs her paydays; only read when a rule asks.
    pays = paydays(transactions) if any(r["cadence"] == "payday" for r in recurring or []) else []
    for t in candidates:
        if t.fingerprint not in out:
            # A recurring transfer she confirmed (2026-10-27): amount and
            # schedule, more particular than where it goes.
            rec = rule_for(t, recurring, pays) if recurring else None
            if rec:
                out[t.fingerprint] = rec["category"]
                continue
            where = destination(t)
            if where and where[0] in rules:
                out[t.fingerprint] = rules[where[0]]
                continue
            mine = own_account(t, accounts)
            if mine:
                out[t.fingerprint] = "Saved" if mine[1] == "investment" else NEUTRAL
                continue
            recent = date.fromisoformat(t.date[:10]) >= cutoff
            out[t.fingerprint] = UNSORTED if recent else NEUTRAL
    if used_out is not None:
        # Which arrivals were the other end of something: the rest is money
        # that came from somewhere you can't see, and worth asking about.
        used_out.update(used)
    return out


def matched_inflows(transactions: list[Transaction], today: str | None = None) -> set[str]:
    """The arrivals that are the other end of one of your own transfers."""
    used: set[str] = set()
    match_transfers(transactions, today=today, used_out=used)
    return used


# What a transfer between her own accounts can be sorted as, at either end
# (2026-10-22): moved between accounts, put into or taken out of savings,
# and still waiting to be sorted.
_MOVED = {NEUTRAL, "Saved", UNSORTED}


def transfer_pairs(transactions: list[Transaction], today: str | None = None) -> dict[str, str]:
    """{departure id: arrival id} for money that left one of her accounts and
    arrived, the same amount, in another of hers within WINDOW_DAYS (two days) — for the
    list to show as one line.

    Its own pairing, not `match_transfers`: that one decides categories and
    so leaves out a transfer she sorted herself, one into savings, and any
    departure that isn't from a bank account. Here only the facts matter:
    the amount, the two accounts, the days between, and that neither end was
    sorted as spending or income. Each arrival pairs once, nearest first.
    """
    outs = sorted((t for t in transactions
                   if t.amount > 0 and not others(t) and (t.category or "") in _MOVED),
                  key=lambda t: (t.date, t.fingerprint))
    arrivals: dict[int, list[Transaction]] = {}
    for t in transactions:
        if (t.amount < 0 and not others(t) and not t.repays
                and ((t.category or "") in _MOVED - {UNSORTED} or _guessed_arrival(t))):
            arrivals.setdefault(_cents(-t.amount), []).append(t)
    used: set[str] = set()
    pairs: dict[str, str] = {}
    for t in outs:
        best = None
        for other in arrivals.get(_cents(t.amount), []):
            if other.fingerprint in used or other.account_id == t.account_id:
                continue
            gap = _days(t.date, other.date)
            if gap > _window(other):
                continue
            if best is None or gap < best[0]:
                best = (gap, other)
        if best:
            used.add(best[1].fingerprint)
            pairs[t.fingerprint] = best[1].fingerprint
    return pairs


def known_destinations(store) -> dict[str, str]:
    """Where her rules say transfers go. Her own accounts are found by
    `own_account` (an investment account's activity isn't in Plaid's
    Transactions product, so a transfer into one has no other end to match;
    its digits or its name in the description do)."""
    return dict(store.destinations())


def apply_transfer_matches(store, transactions: list[Transaction] | None = None) -> int:
    """Run the match over the ledger and write what changed."""
    txns = transactions if transactions is not None else store.all_transactions()
    current = {t.fingerprint: (t.category, t.category_source) for t in txns}
    changes = {}
    for tid, cat in match_transfers(txns, destinations=known_destinations(store),
                                    accounts=linked_accounts(store),
                                    recurring=store.recurring_transfers()).items():
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
