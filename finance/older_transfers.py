"""Also 8 older ones? (REFRESH-17, product owner, 2026-11-25).

A bank transfer nothing placed is asked about for `ASK_DAYS`; an older one
is left a plain transfer, unasked. So when she sorts one payment as spending
and makes no rule, its older ones stay out of her spending and out of her
bills. This finds them, so Pearl can ask, once, after her answer is saved.

Older ones are the same name out of the same account, dated before it, that
are a transfer only because of their age: `match_transfers` reached its last
line for them (`aged_out`). "Transfers, set by the match" alone isn't enough:
real transfers between her accounts are stored the same way. Nothing she
answered, matched, linked or left out is ever among them, and one still
waiting in Needs a look keeps its own card.

Yes sorts them as her own answers, with no rule. Leave them in Transfers is
a no for good, for that name and account; closing the sheet isn't."""

from __future__ import annotations

from .categorize import is_generic_transfer_name, is_spend_category, merchant_key
from .models import Transaction
from .transfers import (NEUTRAL, UNSORTED, _is_bank, known_destinations, linked_accounts,
                        match_transfers, others)


def key_for(t: Transaction) -> str:
    return f"older:{t.account_id}:{merchant_key(t.merchant)}"


def asks(t: Transaction) -> bool:
    """Whether her answer on this row is one to ask after: money out of a
    bank account she sorted as spending herself, under a name a rule could use."""
    return (t.amount > 0 and _is_bank(t) and not others(t) and t.category_source == "user"
            and t.category != UNSORTED and is_spend_category(t.category or "Other")
            and (t.category or "Other") != "Other"
            and bool((t.merchant or "").strip()) and not is_generic_transfer_name(t.merchant))


def find(store, t: Transaction, transactions: list[Transaction] | None = None) -> list[Transaction]:
    """The older ones, newest first; none once she has said no."""
    if not asks(t) or key_for(t) in store.dismissed_reviews():
        return []
    txns = transactions if transactions is not None else store.all_transactions()
    name = merchant_key(t.merchant)
    rows = [x for x in txns
            if x.amount > 0 and x.account_id == t.account_id and x.date[:10] < t.date[:10]
            and merchant_key(x.merchant) == name and x.category == NEUTRAL
            and x.category_source == "transfer_match" and not others(x)
            and not x.transfer_link and not x.unpaired]
    if not rows:
        return []
    aged: set[str] = set()
    match_transfers(txns, destinations=known_destinations(store), accounts=linked_accounts(store),
                    recurring=store.recurring_transfers(), aged_out=aged)
    return sorted((x for x in rows if x.fingerprint in aged),
                  key=lambda x: (x.date, x.fingerprint), reverse=True)
