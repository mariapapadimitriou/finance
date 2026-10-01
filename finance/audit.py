"""Finding rows that describe the same purchase twice.

Import de-duplication runs when data arrives and compares like with like: the
same card, the same descriptor, a date that moved by a day or two. It is
deliberately conservative, because merging two charges that are genuinely
distinct loses money that was really spent.

That conservatism leaves one gap this closes. The importer never merges across
*accounts*, and it is right not to — but a single card really can land in the
ledger under two account ids: imported from a PDF statement, and then
connected through Plaid, which backfills the same months. The descriptors
differ, because a printed statement and an API do not write them the same way,
so only the amount and the date line up.

What this deliberately does *not* do is treat two different cards as a source
of duplicates. Two cards belonging to one person share amounts constantly —
the same coffee, the same fare, the same lunch — and a $6.40 on the TD card
three days after a $6.40 on the Wealthsimple card is two coffees, not one
counted twice. Flagging those buries the real finding in noise.

So the account-level question is asked first: do these two ids look like the
same card? Only pairs that do are examined row by row. Everything here
reports rather than decides, because a tool that silently deleted half of
these would eventually delete something real.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

# A charge re-posted by a different source can sit a few days off: a statement
# shows the posted date, Plaid usually shows the authorised one.
WINDOW_DAYS = 5

# An account-level overlap claims something strong — "these two ids are the
# same card" — and a percentage computed over two or three amounts cannot
# support it. One shared amount out of one is 100% and means nothing.
MIN_AMOUNTS_FOR_OVERLAP = 6

# How much of the smaller account has to appear in the larger before the two
# are treated as one card.
#
# Two genuinely different cards held by one person overlap a little by
# coincidence: a handful of repeated fares and coffees out of hundreds of
# distinct amounts. One card imported twice overlaps almost entirely, and the
# smaller side is usually contained in the larger — a six-month statement
# inside a two-year backfill. There is a wide gap between those, and the
# threshold sits in it rather than near either edge.
SAME_CARD_OVERLAP = 0.6


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def cross_account_duplicates(transactions, same_card=None) -> list[dict]:
    """Same amount, near-same day, on two ids that look like the same card.

    Grouped by amount first because that is the one field neither source
    rewrites — a descriptor is reformatted, a date shifts, but $23.73 is
    $23.73 in a PDF and in an API response.

    `same_card` is the set of account-id pairs worth comparing at all. Without
    it, every coincidence between two real cards is reported as a duplicate,
    which is both wrong and loud enough to hide the real ones. Pass an empty
    set to compare nothing; omit it and it is worked out from the data.
    """
    if same_card is None:
        same_card = same_card_pairs(transactions)
    if not same_card:
        return []

    by_amount: dict[str, list] = defaultdict(list)
    for t in transactions:
        if t.amount <= 0:
            continue                      # refunds and payments handled below
        by_amount[f"{t.amount:.2f}"].append(t)

    findings = []
    for amount, rows in by_amount.items():
        if len(rows) < 2:
            continue
        rows.sort(key=lambda r: r.date)
        for i, a in enumerate(rows):
            for b in rows[i + 1:]:
                if _days_apart(a.date, b.date) > WINDOW_DAYS:
                    break               # sorted, so everything later is worse
                if a.account_id == b.account_id:
                    continue            # the importer's job, not this one
                if _pair(a.account_id, b.account_id) not in same_card:
                    continue            # two different cards, two purchases
                findings.append({
                    "amount": float(amount),
                    "days_apart": _days_apart(a.date, b.date),
                    "same_merchant": a.merchant == b.merchant,
                    "rows": [_row(a), _row(b)],
                })

    # Most likely first: same merchant and same day is about as sure as this
    # gets without asking the bank.
    findings.sort(key=lambda f: (not f["same_merchant"], f["days_apart"],
                                 -f["amount"]))
    return findings


def _pair(a: str, b: str) -> tuple[str, str]:
    """An unordered pair of account ids, so lookups don't depend on order."""
    return (a, b) if a <= b else (b, a)


def same_card_pairs(transactions) -> set[tuple[str, str]]:
    """Account pairs alike enough to be one card under two ids."""
    return {
        _pair(o["accounts"][0]["account_id"], o["accounts"][1]["account_id"])
        for o in overlapping_accounts(transactions)
    }


def _row(t) -> dict:
    return {
        "id": t.fingerprint,
        "date": t.date,
        "merchant": t.merchant,
        "description": t.description,
        "amount": t.amount,
        "account_id": t.account_id,
        "account": t.account_name or t.account_id,
        "source": t.source,
        "category": t.category,
    }


def overlapping_accounts(transactions) -> list[dict]:
    """Pairs of accounts whose date ranges overlap, with how much they share.

    A blunter instrument than the row-level check and a more useful first
    read: if a card was imported by PDF and later connected through Plaid, the
    two account ids will cover the same months and hold many matching amounts.
    One glance says whether that happened, before anyone reads a list of
    individual rows.
    """
    by_account: dict[str, list] = defaultdict(list)
    for t in transactions:
        by_account[t.account_id].append(t)

    summaries = {}
    for acct, rows in by_account.items():
        summaries[acct] = {
            "account_id": acct,
            "account": rows[0].account_name or acct,
            "source": rows[0].source,
            "first": min(r.date for r in rows),
            "last": max(r.date for r in rows),
            "amounts": {f"{r.amount:.2f}" for r in rows if r.amount > 0},
            "count": len(rows),
        }

    out = []
    names = sorted(summaries)
    for i, a in enumerate(names):
        for b in names[i + 1:]:
            x, y = summaries[a], summaries[b]
            if x["last"] < y["first"] or y["last"] < x["first"]:
                continue                       # no shared months at all
            smaller = min(len(x["amounts"]), len(y["amounts"]))
            if smaller < MIN_AMOUNTS_FOR_OVERLAP:
                continue          # too small a sample to mean anything
            shared = x["amounts"] & y["amounts"]
            if not shared:
                continue
            ratio = len(shared) / smaller
            if ratio < SAME_CARD_OVERLAP:
                # Two different cards sharing a few amounts by coincidence,
                # which is what two cards in one wallet do all the time.
                continue
            out.append({
                "accounts": [
                    {k: v for k, v in x.items() if k != "amounts"},
                    {k: v for k, v in y.items() if k != "amounts"},
                ],
                "shared_amounts": len(shared),
                # Of the smaller account's distinct amounts, how many also
                # appear in the larger. High means the same card twice.
                "overlap": round(ratio, 3),
                "same_source": x["source"] == y["source"],
            })
    out.sort(key=lambda o: -o["overlap"])
    return out


def report(transactions) -> dict:
    overlaps = overlapping_accounts(transactions)
    pairs = {_pair(o["accounts"][0]["account_id"], o["accounts"][1]["account_id"])
             for o in overlaps}
    rows = cross_account_duplicates(transactions, pairs)
    return {
        "checked": len(transactions),
        "account_overlaps": overlaps,
        "duplicates": rows[:100],
        "duplicate_count": len(rows),
        "note": ("Only accounts that look like one card under two ids are "
                 "compared. Two different cards sharing an amount within a "
                 "few days is two purchases, not one counted twice, so it is "
                 "not reported. What is found here is reported, not removed."),
    }
