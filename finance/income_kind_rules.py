"""Always for a payer, on income (2026-11-08): the kind of income, remembered.

On an income transaction's page, "Always for Grandma" saves the kind she
gave it (a gift, a bonus, interest…) for that payer. Every deposit from the
same payer, here now and still to come, is then counted as income of that
kind without asking. The payer is named the way regular pay rules name it
(`pay_rules.key_of`): the merchant, or for an e-Transfer the person it names.
A name every transfer shares never becomes a rule.

Never touched: a deposit she sorted herself, or one a regular pay rule
already counts as her pay. Turning Always off keeps what it sorted; the next
deposit from that payer is asked about again.
"""

from __future__ import annotations

import json

from .models import Transaction

KEY = "income_kind_rules"


def rules(store) -> dict[str, dict]:
    """{payer key: {"name", "kind"}}."""
    try:
        out = json.loads(store.setting(KEY) or "{}")
    except (TypeError, ValueError):
        return {}
    return out if isinstance(out, dict) else {}


def rule_for(store, t: Transaction) -> dict | None:
    from .pay_rules import key_of
    found = key_of(t)
    return rules(store).get(found[0]) if found else None


def remember(store, t: Transaction, kind: str) -> bool:
    """Save the rule for this deposit's payer and sort the others. False when
    nothing names the payer well enough."""
    from .pay_rules import key_of
    found = key_of(t)
    if not found:
        return False
    out = rules(store)
    out[found[0]] = {"name": found[1], "kind": kind}
    store.set_setting(KEY, json.dumps(out))
    apply(store)
    return True


def forget(store, t: Transaction) -> bool:
    from .pay_rules import key_of
    found = key_of(t)
    out = rules(store)
    if not found or found[0] not in out:
        return False
    del out[found[0]]
    store.set_setting(KEY, json.dumps(out))
    return True


def apply(store, transactions: list[Transaction] | None = None) -> int:
    """Count every deposit from a remembered payer as income of its kind.
    Returns how many rows changed. No rules, nothing read."""
    from .pay_rules import SOURCE, key_of
    out = rules(store)
    if not out:
        return 0
    txns = transactions if transactions is not None else store.all_transactions()
    pay = store.pay_rules()
    cats: dict[str, tuple[str, str]] = {}
    n = 0
    for t in txns:
        if t.amount >= 0 or t.income_type_source == "user":
            continue
        found = key_of(t)
        rule = out.get(found[0]) if found else None
        if rule is None or (found and found[0] in pay):
            continue
        if t.category_source == "user" and t.category != "Income":
            continue
        if t.category != "Income":
            cats[t.fingerprint] = ("Income", SOURCE)
        # Hers, as if she'd said it: guesses never write over it.
        store.set_income_type(t.fingerprint, rule["kind"], "user")
        n += 1
    if cats:
        store.write_categories(cats)
    return n
