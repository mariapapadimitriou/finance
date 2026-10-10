"""Leaving transactions out: one at a time, or every one a rule of yours matches.

An exclusion is your decision and wins over everything else — a category you
set, a transfer match, a payback. An excluded row stays in the ledger, visible
and reversible, but counts as nothing: not spending, not income, not savings,
and never the other end of a transfer.

A rule is an account, words in the description or merchant, the person the
money was with, and optionally a date range and an amount range. The rule is
written into `txn_exclusions` row by row as transactions arrive, rather than
evaluated on every read, so that the SQL that charges piggy banks sees the same
exclusions the Python does. A row a rule matched that you put back is kept in
that table as `kept`, so the rule never takes it again.
"""

from __future__ import annotations

from .models import Transaction

FIELDS = ("account_id", "keyword", "counterparty", "date_from", "date_to",
          "amount_min", "amount_max")


def clean(rule: dict) -> tuple[dict, str | None]:
    """A rule with only what it needs, or a problem in words."""
    out: dict = {}
    for key in ("account_id", "keyword", "counterparty", "date_from", "date_to"):
        value = " ".join(str(rule.get(key) or "").split())
        out[key] = value or None
    for key in ("amount_min", "amount_max"):
        value = rule.get(key)
        try:
            out[key] = None if value in (None, "") else round(abs(float(value)), 2)
        except (TypeError, ValueError):
            return out, "Amounts need to be numbers."
    out["reason"] = " ".join(str(rule.get("reason") or "").split())[:200]
    if not out["reason"]:
        return out, "Say why, so you can tell later what this rule is for."
    if not (out["account_id"] or out["keyword"] or out["counterparty"]):
        return out, "Name an account, some words, or a person to match."
    if out["keyword"] and len(out["keyword"]) < 3:
        return out, "Use at least three letters to match on."
    return out, None


def matches(rule: dict, t: Transaction) -> bool:
    if rule.get("account_id") and t.account_id != rule["account_id"]:
        return False
    if rule.get("keyword"):
        text = f"{t.description} {t.merchant}".lower()
        if rule["keyword"].lower() not in text:
            return False
    if rule.get("counterparty"):
        who = str((t.raw or {}).get("counterparty") or "").lower()
        text = f"{who} {t.description}".lower()
        if rule["counterparty"].lower() not in text:
            return False
    if rule.get("date_from") and t.date[:10] < rule["date_from"]:
        return False
    if rule.get("date_to") and t.date[:10] > rule["date_to"]:
        return False
    if rule.get("amount_min") is not None and abs(t.amount) < rule["amount_min"] - 0.005:
        return False
    if rule.get("amount_max") is not None and abs(t.amount) > rule["amount_max"] + 0.005:
        return False
    return True


def matching(rule: dict, transactions: list[Transaction]) -> list[Transaction]:
    return [t for t in transactions if matches(rule, t)]


def reapply(store, transactions: list[Transaction] | None = None) -> int:
    """Write every rule's matches that aren't recorded yet. Returns how many."""
    rules = store.exclusion_rules()
    if not rules:
        return 0
    txns = transactions if transactions is not None else store.all_transactions()
    taken = store.exclusion_ids()
    added = 0
    for rule in rules:
        for t in txns:
            if t.fingerprint in taken or not matches(rule, t):
                continue
            store.exclude(t.fingerprint, rule["reason"], rule_id=rule["id"])
            taken.add(t.fingerprint)
            added += 1
    return added


def by_month(transactions: list[Transaction]) -> dict[str, dict]:
    """How many rows were left out each month, and how much money they moved."""
    out: dict[str, dict] = {}
    for t in transactions:
        if t.excluded:
            m = out.setdefault(t.month, {"count": 0, "total": 0.0})
            m["count"] += 1
            m["total"] = round(m["total"] + abs(t.amount), 2)
    return out
