"""Regular pay rules (2026-10-28): "This is my regular pay", remembered.

When she says a deposit is her regular pay and ticks Remember, every deposit
from the same payer — the ones already here and the ones still to come — is
sorted as income, of the salary kind, so Income and bills and the monthly
income count it without asking. The payer is the merchant the bank names
("ACME CORP PAYROLL"), or for pay sent by e-Transfer, the person or company
the transfer names. A name every transfer shares ("Interac e-Transfer")
never becomes a rule.

Into a joint account (2026-10-29): her pay is hers, so a deposit the rule
sorts there is answered "me" for "Who put this in?" too — asked about
otherwise, and counted as none of hers until answered. A deposit she said
someone else put in stays theirs.

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
        if not matches(t, rules):
            continue
        claim_joint(store, t)
        if t.category_source == "user":
            continue
        if (t.category, t.category_source) != ("Income", SOURCE):
            changes[t.fingerprint] = ("Income", SOURCE)
    if changes:
        store.write_categories(changes)
    return len(changes)


def unclaimed_joint(t: Transaction) -> bool:
    """A deposit into a joint account nobody has said is whose yet."""
    return bool(t.joint) and t.amount < 0 and not t.joint_from


def claim_joint(store, t: Transaction, marks: dict | None = None) -> bool:
    """Her pay into a joint account is hers (2026-10-29). `marks` notes the
    old answer for Undo."""
    if not unclaimed_joint(t):
        return False
    from .joint import ME
    if marks is not None:
        marks.setdefault("joint_from", {}).setdefault(
            t.fingerprint, {"who": t.joint_from, "person": t.joint_person})
    store.set_joint_deposit(t.fingerprint, ME, None)
    t.joint_from = ME
    return True


def claim_waiting(store, transactions: list[Transaction]) -> int:
    """Joint deposits a pay rule covers that still wait on "Who put this
    in?", answered as hers. No rules, nothing read or written."""
    rules = store.pay_rules()
    if not rules:
        return 0
    return sum(1 for t in transactions if unclaimed_joint(t) and matches(t, rules)
               and claim_joint(store, t))
