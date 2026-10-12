"""Splits and repayments (Pearl S-01 to S-04, THL-124).

A split is a charge you paid for several people: evenly or by amount, with
up to eight others named by a first name you typed. Your part is written as
your share (`txn_shares`), so every total that counts spending — spent,
category totals, the usual month, safe to spend — already counts only it.

Each other person's part is a repayment you can watch for. When an
e-Transfer arrives from the same first name, for about what they owe
(within $1), within 60 days of the charge, Pearl suggests linking it (S-02).
You can also link any money in to any open split by hand (S-03), and a
repayment can be partial: what is left stays open. A linked repayment is
never income: it was always theirs.
"""

from __future__ import annotations

import re
from datetime import date

from .models import Transaction

MAX_PEOPLE = 8
MAX_NAME = 40
MATCH_WITHIN = 1.00        # dollars
MATCH_DAYS = 60
# An e-Transfer that names nobody can still be offered for a split when its
# amount is what one person owes (THL-181), but only closely and only when
# exactly one person fits — otherwise any $20 would match any $20 share.
AMOUNT_ONLY_WITHIN = 0.01

_WORD = re.compile(r"[a-zà-ÿ0-9']+")


def first_name(name: str) -> str:
    words = _WORD.findall((name or "").lower())
    return words[0] if words else ""


def sender(t: Transaction) -> str:
    """Who money in came from, as the bank wrote it."""
    raw = t.raw or {}
    return " ".join(str(x) for x in (raw.get("counterparty"), t.merchant, t.description) if x)


def from_person(inflow: Transaction, name: str) -> bool:
    """Did this money come from someone with this first name?"""
    first = first_name(name)
    return bool(first) and first in _WORD.findall(sender(inflow).lower())


def even_amounts(total: float, n_people: int) -> tuple[float, list[float]]:
    """Split `total` evenly among you and n others, in cents. Any odd cent
    stays with you, so what the others owe is never rounded up on them."""
    each = int(round(total * 100)) // (n_people + 1)
    theirs = [each / 100] * n_people
    return round(total - sum(theirs), 2), theirs


def validate(charge: Transaction, mode: str, people: list) -> tuple[list[dict], str | None]:
    """Clean the people of a split, or say what is wrong with them."""
    if mode not in ("even", "amount"):
        return [], "Split evenly or by amount."
    if not isinstance(people, list) or not people:
        return [], "Add someone to split it with."
    if len(people) > MAX_PEOPLE:
        return [], f"Up to {MAX_PEOPLE} people."
    clean = []
    for p in people:
        if not isinstance(p, dict):
            return [], "Add someone to split it with."
        name = " ".join(str(p.get("name") or "").split())[:MAX_NAME]
        if not name:
            return [], "Give everyone a name."
        clean.append({"name": name, "amount": p.get("amount")})
    if mode == "even":
        _, theirs = even_amounts(charge.amount, len(clean))
        for p, a in zip(clean, theirs):
            p["amount"] = a
    else:
        for p in clean:
            try:
                p["amount"] = round(float(p["amount"]), 2)
            except (TypeError, ValueError):
                return [], f"How much was {p['name']}’s part?"
            if p["amount"] < 0:
                return [], f"{p['name']}’s part can’t be less than nothing."
        if sum(p["amount"] for p in clean) > charge.amount + 0.005:
            return [], "Their parts add up to more than the whole charge."
    return clean, None


def your_part(charge: Transaction, people: list[dict]) -> float:
    return round(charge.amount - sum(p["amount"] for p in people), 2)


def _linked(charge_id: str, transactions: list[Transaction]) -> list[Transaction]:
    return sorted((t for t in transactions if t.repays == charge_id), key=lambda t: t.date)


def split_status(charge: Transaction, split: dict, transactions: list[Transaction],
                 payer: dict[str, str]) -> dict:
    """Each person in a split, and any repayment Pearl can't put a name to.

    Every repayment linked to the charge is credited to someone (THL-181): the
    person you linked it to; otherwise whoever it names; otherwise the one
    person whose part it pays exactly. Anything still unplaced comes back as
    `unassigned`, so the split card can ask who sent it rather than drop it.
    """
    names = [p["name"] for p in split["people"]]
    share = {p["name"]: p["amount"] for p in split["people"]}
    paid = {n: 0.0 for n in names}
    when: dict[str, str] = {}
    unplaced = []
    for t in _linked(charge.fingerprint, transactions):
        who = payer.get(t.fingerprint)
        if who not in paid:
            who = next((n for n in names if from_person(t, n)), None)
        if who is None:
            unplaced.append(t)
            continue
        paid[who] = round(paid[who] + -t.amount, 2)
        when[who] = t.date[:10]
    unassigned = []
    for t in unplaced:
        got = -t.amount
        fits = [n for n in names
                if abs((share[n] - paid[n]) - got) <= MATCH_WITHIN + 0.005]
        if len(fits) == 1:
            paid[fits[0]] = round(paid[fits[0]] + got, 2)
            when[fits[0]] = t.date[:10]
        else:
            unassigned.append({"id": t.fingerprint, "date": t.date[:10],
                               "amount": round(got, 2)})
    people = []
    for p in split["people"]:
        owes = round(max(p["amount"] - paid[p["name"]], 0.0), 2)
        people.append({"name": p["name"], "amount": p["amount"], "paid": paid[p["name"]],
                       "owes": owes,
                       "paid_on": when.get(p["name"]) if owes < 0.005 else None})
    return {"people": people, "unassigned": unassigned}


def people_status(charge: Transaction, split: dict, transactions: list[Transaction],
                  payer: dict[str, str]) -> list[dict]:
    """Each person in a split: their part, what they've paid back and when,
    and what they still owe (S-04)."""
    return split_status(charge, split, transactions, payer)["people"]


def open_repayments(transactions: list[Transaction], splits: dict[str, dict],
                    payer: dict[str, str]) -> list[dict]:
    """Everyone who still owes something on a split you're watching."""
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for cid, split in splits.items():
        charge = by_id.get(cid)
        if charge is None or charge.excluded or not split.get("watch", True):
            continue
        for p in people_status(charge, split, transactions, payer):
            if p["owes"] >= 0.005:
                out.append({"charge": charge, "name": p["name"], "owes": p["owes"],
                            "amount": p["amount"]})
    return out


def suggest(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
            payer: dict[str, str]) -> dict | None:
    """The split this money most likely pays back (S-02).

    The same first name, within $1 of what they owe, within 60 days after the
    charge. Failing that, an e-Transfer that names nobody is offered for the
    one person who owes exactly that amount (THL-181) — marked as an amount
    match, since Pearl is going on the amount alone.
    """
    if inflow.amount >= 0 or inflow.repays:
        return None
    from .transfers import etransfer_person
    got = -inflow.amount
    when = date.fromisoformat(inflow.date[:10])
    nameless = not etransfer_person(inflow)
    best = None
    by_amount = []
    for r in open_repayments(transactions, splits, payer):
        gap = (when - date.fromisoformat(r["charge"].date[:10])).days
        if not 0 <= gap <= MATCH_DAYS:
            continue
        diff = abs(r["owes"] - got)
        if not from_person(inflow, r["name"]):
            if nameless and diff <= AMOUNT_ONLY_WITHIN + 0.0001:
                by_amount.append(r)
            continue
        if diff > MATCH_WITHIN + 0.005:
            continue
        key = (diff, gap)
        if best is None or key < best[0]:
            best = (key, r)
    if best is not None:
        return brief(best[1], exact=best[0][0] < 0.005)
    if len(by_amount) == 1:
        return brief(by_amount[0], exact=True, by_name=False)
    return None


def for_inflow(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
               payer: dict[str, str]) -> tuple[list[dict], bool]:
    """Splits this money could be for (S-03): the sender's, if Pearl can
    tell who sent it, otherwise every open one. The second value says which."""
    # Any open split, whichever was recorded first: a friend can pay you
    # back before the charge posts (THL-181). Nearest in time first.
    when = date.fromisoformat(inflow.date[:10])
    open_ = open_repayments(transactions, splits, payer)
    theirs = [r for r in open_ if from_person(inflow, r["name"])]
    rows = theirs or open_
    rows.sort(key=lambda r: (abs((when - date.fromisoformat(r["charge"].date[:10])).days),
                             r["charge"].date))
    return [brief(r) for r in rows[:12]], bool(theirs)


def brief(r: dict, exact: bool = False, by_name: bool = True) -> dict:
    c = r["charge"]
    return {"charge_id": c.fingerprint, "merchant": c.merchant, "date": c.date[:10],
            "amount": round(c.amount, 2), "name": r["name"], "owes": r["owes"],
            "share": r["amount"], "exact": exact, "by_name": by_name}
