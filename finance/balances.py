"""What your accounts hold, and what they held on any day.

Plaid reports each account's balance with every sync. That is today's figure
only, but the transactions say how it got there, so the balance on an earlier
day is today's with everything since undone:

* a bank account: today's balance + money out since − money in since;
* a credit card, which reports what is owed: owed today − charges since +
  payments since.

That only works for an account whose transactions are tracked; for one that
isn't, the daily readings kept from each sync are used where they exist.

Growth › Insights winds the Anchor's accounts back this way to draw savings
over time (GR-32).
"""

from __future__ import annotations

def balance_on(current: float, account_type: str, day: str, as_of: str,
               transactions) -> float:
    """What the account held at the end of `day`, from today's `current`."""
    delta = sum(t.amount for t in transactions if day < t.date[:10] <= as_of)
    if (account_type or "").lower() == "credit":
        return round(current - delta, 2)
    return round(current + delta, 2)

