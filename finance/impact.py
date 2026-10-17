"""What sorting or re-filing a transaction did, and how to take it back (THL-123).

Every change of category says what it did to Allowance, the weekly
number on Allowance: "Allowance is now $842.18 — $200 more, because it
went to savings." The figure is never estimated. The caller works the week
out before and after (on the real ledger, or on a copy for a preview), so
what the sentence says is what Allowance will show.

A change can reach further than the row you touched: "Apply to all from
Uber Eats" re-files every Uber Eats row and writes a rule, and "Remember where
these go" writes a rule for a transfer's destination. Undo has to take all of
it back, so a change is described as the difference between two snapshots of
the ledger — every row's category and source, every merchant rule, every
destination rule — and undoing it writes the old side of that difference.
"""

from __future__ import annotations

import re

from .categorize import CATEGORY_GROUPS, group_of

# How each group's money is described when it stops counting as spending.
_BECAUSE = {
    "savings": "it went to savings, not spending",
    "transfer": "it moved between your accounts, not spending",
    "income": "it’s income, not spending",
}

# What a restored row's source may look like ("rule", "merchant_override"…).
SOURCE = re.compile(r"[a-z_]{1,32}")


def money(x: float) -> str:
    return f"${abs(x):,.2f}"


def snapshot(store, transactions=None) -> dict:
    """The parts of the ledger a change of category can touch."""
    txns = store.all_transactions() if transactions is None else transactions
    labels = store.destination_labels()
    return {
        "rows": {t.fingerprint: (t.category, t.category_source) for t in txns},
        "overrides": dict(store.overrides()),
        "destinations": {k: (v, labels.get(k, ""))
                         for k, v in store.destinations().items()},
    }


def undo_payload(before: dict, after: dict) -> dict:
    """What to write to put `before` back: only what changed."""
    rows = [{"id": i, "category": c, "source": s}
            for i, (c, s) in before["rows"].items()
            if after["rows"].get(i) != (c, s)]
    overrides = {k: before["overrides"].get(k)
                 for k in set(before["overrides"]) | set(after["overrides"])
                 if before["overrides"].get(k) != after["overrides"].get(k)}
    dests = {}
    for k in set(before["destinations"]) | set(after["destinations"]):
        old, new = before["destinations"].get(k), after["destinations"].get(k)
        if old != new:
            dests[k] = None if old is None else {"category": old[0], "label": old[1]}
    return {"rows": rows, "overrides": overrides, "destinations": dests}


def group_label(category: str) -> str:
    return CATEGORY_GROUPS[group_of(category)]


def describe(before: float, after: float, cat_from: str, cat_to: str,
             spent_before: float | None = None, spent_after: float | None = None,
             month: str = "") -> dict:
    """The impact line (before saving) and the toast (after), from safe to
    spend — the week — before and after the change, and the month's spending.

    Same group and no change → "Both are Lifestyle, so your Allowance
    stays the same." A change that moves the number says by how much and why.
    Some moves change what was spent this month without touching the week —
    an unsorted transfer never came out of it — and then the month is what
    the sentence is about.
    """
    delta = round(after - before, 2)
    spent_delta = (round(spent_after - spent_before, 2)
                   if spent_before is not None and spent_after is not None else 0.0)
    g_from, g_to = group_of(cat_from), group_of(cat_to)
    out = {"before": round(before, 2), "after": round(after, 2), "delta": delta,
           "spent_delta": spent_delta, "group_from": g_from, "group_to": g_to,
           "line": "", "title": "", "detail": ""}
    if cat_from == cat_to:
        return out
    because_up = _BECAUSE.get(g_to, f"{cat_to} doesn’t come out of your Allowance")
    if abs(delta) >= 0.005:
        if delta > 0:
            out.update(line=f"Your Allowance goes up by {money(delta)}, because {because_up}.",
                       detail=f"{money(delta)} more, because {because_up}.")
        else:
            because = f"{cat_to} comes out of your Allowance"
            out.update(line=f"Your Allowance goes down by {money(delta)}, because {because}.",
                       detail=f"{money(delta)} less, because {because}.")
        out["title"] = (f"Allowance is now {money(after)}." if after >= 0
                        else f"You’re {money(after)} over for this week.")
        return out
    if abs(spent_delta) >= 0.005 and month:
        if spent_delta < 0:
            because = _BECAUSE.get(g_to, f"{cat_to} isn’t spending")
            out.update(line=f"{money(spent_delta)} less counted as spending in {month}, "
                            f"because {because}. Your Allowance stays the same.",
                       detail=f"{money(spent_delta)} less, because {because}.")
        else:
            out.update(line=f"{money(spent_delta)} more counted as spending in {month}. "
                            "Your Allowance stays the same.",
                       detail=f"{money(spent_delta)} more, because {cat_to} is spending.")
        out["title"] = f"Spent in {month} is now {money(spent_after)}."
        return out
    out.update(line=(f"Both are {CATEGORY_GROUPS[g_to]}, so your Allowance stays the same."
                     if g_from == g_to else "Your Allowance stays the same."),
               title="Your Allowance stays the same.")
    return out
