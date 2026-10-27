"""Splits and repayments (Pearl S-01 to S-04, THL-124).

A split is a charge you paid for several people: evenly or by amount, with
up to eight others named by a first name you typed. Your part is written as
your share (`txn_shares`), so every total that counts spending — spent,
category totals, the usual month, safe to spend — already counts only it.

Each other person's part is a repayment you can watch for. When an
e-Transfer arrives from the same first name, for about what they owe
(within $1), within 60 days of the charge, Pearl suggests linking it (S-02).
Friends often pay before a card purchase posts, so "the charge" is the day
of the purchase, not the day it posted, and money from up to a week before
it counts too.
You can also link any money in to any open split by hand (S-03), and a
repayment can be partial: what is left stays open. A linked repayment is
never income: it was always theirs.
"""

from __future__ import annotations

import re
from datetime import date

from .models import Transaction

MAX_PEOPLE = 50   # paybacks on one split (2026-10-26: was 8)
MAX_NAME = 40
MATCH_WITHIN = 1.00        # dollars
MATCH_DAYS = 60
# Money that arrived this long before the purchase can still be paying it back.
EARLY_DAYS = 7

_WORD = re.compile(r"[a-zà-ÿ0-9']+")


def bought_on(t: Transaction) -> date:
    """The day of the purchase: the earlier of its two dates, since a bank
    feed's date is when it posted and a statement's is when it was made."""
    days = [d[:10] for d in (t.date, t.post_date) if d]
    return date.fromisoformat(min(days))


def first_name(name: str) -> str:
    words = _WORD.findall((name or "").lower())
    return words[0] if words else ""


def sender(t: Transaction) -> str:
    """Who money in came from, as the bank wrote it."""
    raw = t.raw or {}
    return " ".join(str(x) for x in (t.party, raw.get("counterparty"), t.merchant,
                                       t.description) if x)


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


def people_status(charge: Transaction, split: dict, transactions: list[Transaction],
                  payer: dict[str, str]) -> list[dict]:
    """Each person in a split: their part, what they've paid back and when,
    and what they still owe (S-04).

    A repayment counts for the person you linked it to; one linked before
    people had names counts for whoever it came from by name.
    """
    names = [p["name"] for p in split["people"]]
    part = {p["name"]: float(p["amount"]) for p in split["people"]}
    paid = {n: 0.0 for n in names}
    when: dict[str, str] = {}
    unnamed: list[Transaction] = []
    for t in sorted(_linked(charge.fingerprint, transactions), key=lambda x: x.date):
        who = payer.get(t.fingerprint)
        if who not in paid and who:
            # "Sam Lee" paying back the Sam in the split.
            who = next((n for n in names if first_name(n).lower() == first_name(who).lower()), None)
        if who not in paid:
            who = next((n for n in names if from_person(t, n)), None)
        if who is None:
            unnamed.append(t)
            continue
        paid[who] = round(paid[who] + -t.amount, 2)
        when[who] = t.date[:10]
    # A payback nobody's name is on (a bank that leaves the sender off, or
    # one linked from search) still counts (2026-10-24): to whoever owes
    # exactly that much, else the first who still owes anything.
    for t in unnamed:
        got = -t.amount
        owing = [n for n in names if part[n] - paid[n] >= 0.005]
        if not owing:
            continue
        who = next((n for n in owing if abs(part[n] - paid[n] - got) < 0.01), owing[0])
        paid[who] = round(paid[who] + got, 2)
        when[who] = t.date[:10]
    out = []
    for p in split["people"]:
        owes = round(max(p["amount"] - paid[p["name"]], 0.0), 2)
        out.append({"name": p["name"], "amount": p["amount"], "paid": paid[p["name"]],
                    "owes": owes, "paid_on": when.get(p["name"]) if owes < 0.005 else None})
    return out


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
    """The split this money most likely pays back (S-02): the same first
    name, within $1 of what they owe, from a week before the purchase to 60
    days after it."""
    if inflow.amount >= 0 or inflow.repays:
        return None
    got = -inflow.amount
    when = date.fromisoformat(inflow.date[:10])
    best = None
    for r in open_repayments(transactions, splits, payer):
        gap = (when - bought_on(r["charge"])).days
        if not -EARLY_DAYS <= gap <= MATCH_DAYS or not from_person(inflow, r["name"]):
            continue
        diff = abs(r["owes"] - got)
        if diff > MATCH_WITHIN + 0.005:
            continue
        key = (diff, abs(gap))
        if best is None or key < best[0]:
            best = (key, r)
    return None if best is None else brief(best[1], exact=best[0][0] < 0.005)


def for_inflow(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
               payer: dict[str, str]) -> tuple[list[dict], bool]:
    """Splits this money could be for (S-03): the sender's, if Pearl can
    tell who sent it, otherwise every open one. The second value says which."""
    when = date.fromisoformat(inflow.date[:10])
    open_ = [r for r in open_repayments(transactions, splits, payer)
             if (when - bought_on(r["charge"])).days >= -EARLY_DAYS]
    theirs = [r for r in open_ if from_person(inflow, r["name"])]
    rows = theirs or open_
    rows.sort(key=lambda r: r["charge"].date, reverse=True)
    return [brief(r) for r in rows[:12]], bool(theirs)


def brief(r: dict, exact: bool = False) -> dict:
    c = r["charge"]
    return {"charge_id": c.fingerprint, "merchant": c.merchant, "date": c.date[:10],
            "amount": round(c.amount, 2), "name": r["name"], "owes": r["owes"],
            "share": r["amount"], "exact": exact}


# ── A payback that makes the split (THL-260, 2026-10-24) ─────────────────
# Linking money in to a purchase that was never split ("Paid back" → any
# charge) turns the purchase into a split with whoever sent it, so the split
# card shows them, paid back. The payback is marked as having made its
# person's place in the split, so unlinking it takes them out again.
MADE_SPLIT = "made_split"


def add_payer(store, charge: Transaction, inflow: Transaction, person: str | None):
    """Put the sender into the charge's split for what they sent, if they
    aren't in it already. Returns what to put back for an Undo
    ({"split", "share"}), or None when nothing changed: no name, a joint
    charge, a share she typed without a split, someone already in the split,
    or more than her part is left."""
    person = " ".join((person or "").split())[:MAX_NAME]
    if not person or charge.joint or charge.amount <= 0 or inflow.amount >= 0:
        return None
    current = store.splits().get(charge.fingerprint)
    if current is None and charge.share_set:
        return None
    people = list(current["people"]) if current else []
    if any(first_name(p["name"]) == first_name(person) for p in people):
        return None
    got = round(-inflow.amount, 2)
    if current is None and (charge.paid_back or 0.0) - got > 0.005:
        # Others already paid some of it back with no split to say who;
        # a split now would have to guess their names, so it nets as before.
        return None
    yours = round(charge.my_share if current and charge.my_share is not None else charge.amount, 2)
    if got > yours + 0.005:
        return None
    was = {"split": current, "share": charge.my_share if charge.share_set else None}
    people.append({"name": person, "amount": got})
    store.set_split(charge.fingerprint, "amount", people, current["watch"] if current else True)
    store.set_share(charge.fingerprint, round(yours - got, 2))
    store.set_payback_kind(inflow.fingerprint, MADE_SPLIT)
    return was


def drop_payer(store, inflow: Transaction):
    """Undo `add_payer` when the payback is unlinked or moved: its person
    leaves the split and their part is hers again; a split left with nobody
    goes. Returns what to put back for an Undo, or None."""
    if not inflow.repays or store.payback_kinds().get(inflow.fingerprint) != MADE_SPLIT:
        return None
    charge = store.get_transaction(inflow.repays)
    current = store.splits().get(inflow.repays)
    store.set_payback_kind(inflow.fingerprint, None)
    if charge is None or current is None:
        return None
    person = store.payback_people().get(inflow.fingerprint)
    got = round(-inflow.amount, 2)
    idx = next((i for i, p in enumerate(current["people"])
                if p["name"] == person and abs(p["amount"] - got) < 0.01), None)
    if idx is None:
        return None
    was = {"split": current, "share": charge.my_share if charge.share_set else None}
    people = [p for i, p in enumerate(current["people"]) if i != idx]
    if people:
        store.set_split(charge.fingerprint, current["mode"], people, current["watch"])
        store.set_share(charge.fingerprint, round((charge.my_share or 0.0) + got, 2))
    else:
        store.clear_split(charge.fingerprint)
        store.set_share(charge.fingerprint, None)
    return was
