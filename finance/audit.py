"""Finding rows that describe the same purchase twice.

Import de-duplication runs when data arrives and compares like with like: the
same card, the same descriptor, a date that moved by a day or two. It is
deliberately conservative, because merging two charges that are genuinely
distinct loses money that was really spent.

That conservatism leaves a gap this closes. The importer never merges across
*accounts*, and it is right not to — but a charge really can land in the ledger
twice under two account ids:

  *the same card, twice over*  — a statement imported by PDF, and then the same
                                 card connected through Plaid, which backfills
                                 two years. The descriptors differ (a printed
                                 statement and an API are not the same source),
                                 so nothing matches on merchant.
  *a card and its chequing*    — the purchase on the card, and the payment that
                                 settles it in the account behind it. Not the
                                 same amount usually, but a full-balance
                                 payment of a single purchase is.

So this reports rather than decides. Anything it finds is shown with both
sides and their sources, and removing one is a choice made in the open. A tool
that silently deleted half of these would eventually delete something real.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date

# A charge re-posted by a different source can sit a few days off: a statement
# shows the posted date, Plaid usually shows the authorised one.
WINDOW_DAYS = 5

# An account-level overlap claims something strong — "these two ids are the
# same card" — and a percentage computed over two or three amounts cannot
# support it. One shared amount out of one is 100% and means nothing. Below
# this, the row-level list is the right tool and this stays quiet.
MIN_AMOUNTS_FOR_OVERLAP = 6


def _days_apart(a: str, b: str) -> int:
    return abs((date.fromisoformat(a) - date.fromisoformat(b)).days)


def cross_account_duplicates(transactions) -> list[dict]:
    """Same amount, near-same day, different accounts.

    Grouped by amount first because that is the one field neither source
    rewrites — a descriptor is reformatted, a date shifts, but $23.73 is
    $23.73 in a PDF and in an API response.
    """
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
            out.append({
                "accounts": [
                    {k: v for k, v in x.items() if k != "amounts"},
                    {k: v for k, v in y.items() if k != "amounts"},
                ],
                "shared_amounts": len(shared),
                # Of the smaller account's distinct amounts, how many also
                # appear in the larger. High means the same card twice.
                "overlap": round(len(shared) / smaller, 3),
                "same_source": x["source"] == y["source"],
            })
    out.sort(key=lambda o: -o["overlap"])
    return out


def report(transactions) -> dict:
    rows = cross_account_duplicates(transactions)
    return {
        "checked": len(transactions),
        "account_overlaps": overlapping_accounts(transactions),
        "duplicates": rows[:100],
        "duplicate_count": len(rows),
        "note": ("Same amount within five days on two different accounts. "
                 "The importer never merges across accounts, deliberately — "
                 "so these are reported, not removed."),
    }
