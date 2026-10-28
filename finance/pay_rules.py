"""Regular pay rules (2026-10-28): "This is my regular pay", remembered.

When she says a deposit is her regular pay and ticks Remember, every deposit
from the same payer — the ones already here and the ones still to come — is
sorted as income, of the salary kind, so Income and bills and the monthly
income count it without asking. The payer is the merchant the bank names
("ACME CORP PAYROLL"), or for pay sent by e-Transfer, the person or company
the transfer names. A name every transfer shares ("Interac e-Transfer")
never becomes a rule.

Never touched: a row she sorted herself. Removing a rule keeps what it
sorted as it is; the next deposit from that payer is asked about again.
"""

from __future__ import annotations

from .models import Transaction

SOURCE = "pay_rule"


def key_of(t: Transaction) -> tuple[str, str] | None:
    """(key, name) of who paid this deposit, or None when nothing names
    them well enough to remember."""
    from .categorize import is_generic_transfer_name
    from .etransfers import is_etransfer, party
    if is_etransfer(t):
        who = (party(t) or {}).get("name")
        if who:
            return "person:" + " ".join(who.lower().split()), who
    name = " ".join((t.merchant or t.description or "").split())
    if not name or is_generic_transfer_name(name):
        return None
    return "payer:" + name.lower(), name


def matches(t: Transaction, rules: dict[str, str]) -> bool:
    if t.amount >= 0 or not rules:
        return False
    found = key_of(t)
    return bool(found) and found[0] in rules


def salary_ids(transactions: list[Transaction], rules: dict[str, str]) -> set[str]:
    """The deposits a rule makes regular pay: salary, whatever they look like."""
    return {t.fingerprint for t in transactions
            if matches(t, rules) and t.category == "Income"}


def apply(store, transactions: list[Transaction] | None = None) -> int:
    """Sort every deposit from a payer she named as income. Returns how many
    rows changed."""
    rules = store.pay_rules()
    if not rules:
        return 0                # no rules, no reading the ledger (metered on a hosted one)
    txns = transactions if transactions is not None else store.all_transactions()
    changes = {}
    for t in txns:
        if t.category_source == "user" or not matches(t, rules):
            continue
        if (t.category, t.category_source) != ("Income", SOURCE):
            changes[t.fingerprint] = ("Income", SOURCE)
    if changes:
        store.write_categories(changes)
    return len(changes)
