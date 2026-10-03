"""Budget lines: categories folded together for budgeting.

There are thirty-odd categories because a transaction deserves an accurate
label, and that is too many lines for a budget anyone keeps. Lodging is part of
a trip; Health and Personal Care are one decision about looking after
yourself; Coffee may well deserve a line of its own. Which of those are true is
a matter of how a person thinks about their money, so it is theirs to choose.

A grouping maps a category to the line it is budgeted under. A category with no
entry is its own line. The line is named either after a category (Lodging
folded into Travel) or freshly ("Health & care"). Only budgeting sees lines:
the plan's split, the Budgets table and what can be saved there. Transactions,
the Overview and the weekly number keep the categories they always had — the
weekly number in particular is worked out per category, so how you group your
budget cannot change what you may spend today.

Two rules, both to keep the arithmetic honest:

  *No nesting.* A line cannot itself be folded into another. One level is
  what a budget needs, and two would let a cycle in.
  *Bank-funded stays with bank-funded.* Travel and Lodging are paid for by a
  piggy bank and have no budget line. Folding one into a budgeted line would
  pull its spending into a budget that was never given money for it.
"""

from __future__ import annotations

from .categorize import CATEGORIES, NON_SPEND, is_bank_funded, is_discretionary

MAX_NAME = 40


def spend_categories() -> list[str]:
    """Every category a budget could cover — not income, not transfers."""
    return [c for c in CATEGORIES if c not in NON_SPEND]


def line_of(category: str, groups: dict[str, str] | None) -> str:
    return (groups or {}).get(category, category)


def lines(groups: dict[str, str] | None) -> dict[str, list[str]]:
    """Each budget line and the categories in it, in the table's order."""
    out: dict[str, list[str]] = {}
    for category in spend_categories():
        out.setdefault(line_of(category, groups), []).append(category)
    return out


def line_bank_funded(members: list[str]) -> bool:
    return bool(members) and all(is_bank_funded(m) for m in members)


def line_daily(members: list[str]) -> str:
    """Which side of the weekly number a line falls on: all, none, or part.

    A line is a budgeting convenience; the weekly number is still decided per
    category, so a line holding Health (budgeted monthly) and Personal Care
    (in the weekly number) is honestly "part", and says so.
    """
    flags = {is_discretionary(m) for m in members}
    if flags == {True}:
        return "all"
    if flags == {False}:
        return "none"
    return "part"


def validate(mapping: dict) -> tuple[dict[str, str] | None, str | None]:
    """Clean a proposed grouping, or say what is wrong with it.

    Returns the mapping as it will be stored — trimmed, with "its own line"
    entries removed — or an error a person can act on.
    """
    if not isinstance(mapping, dict):
        return None, "Expected a mapping of category to the line it joins."

    allowed = set(spend_categories())
    clean: dict[str, str] = {}
    for category, parent in mapping.items():
        if category not in allowed:
            return None, f"'{category}' is not a category a budget can cover."
        if parent is None:
            continue
        if not isinstance(parent, str):
            return None, f"The line for {category} has to be a name."
        parent = " ".join(parent.split())
        if not parent or parent == category:
            continue                      # its own line
        if len(parent) > MAX_NAME:
            return None, f"Line names are at most {MAX_NAME} characters."
        if parent in NON_SPEND or (parent in CATEGORIES and parent not in allowed):
            return None, f"'{parent}' is not a line spending can be budgeted under."
        clean[category] = parent

    # No nesting: whatever is a line cannot also be folded into another.
    for category, parent in clean.items():
        if parent in clean:
            return None, (f"{parent} is folded into {clean[parent]}, so it "
                          f"cannot also hold {category}. Put both under "
                          f"{clean[parent]} instead.")

    # Bank-funded categories only share a line with each other.
    for line, members in lines(clean).items():
        funded = {is_bank_funded(m) for m in members}
        if len(funded) > 1:
            banked = ", ".join(m for m in members if is_bank_funded(m))
            budgeted = ", ".join(m for m in members if not is_bank_funded(m))
            return None, (
                f"{banked} {'is' if ',' not in banked else 'are'} paid for by a "
                f"piggy bank and can't share the {line} line with {budgeted}, "
                "which has a budget — its spending would land on a budget "
                "that was never given money for it.")

    return clean, None


def carry_budgets(saved: dict[str, float], old: dict[str, str],
                  new: dict[str, str]) -> dict[str, float]:
    """Saved budgets re-expressed under a new grouping.

    Folding lines together adds their budgets, so a hand-tuned total survives
    regrouping exactly: Health at $85 and Personal Care at $40 become one line
    at $125, not a fresh split from the plan. A line that is broken up has no
    honest way to divide its figure, so it is dropped, and the drift notice on
    Budgets says the saved total no longer matches — with a button to re-split.
    """
    old_lines = lines(old)
    new_lines = lines(new)
    out: dict[str, float] = {}
    for key, amount in saved.items():
        if key in CATEGORIES:
            target = line_of(key, new)
        elif key in new_lines and sorted(new_lines[key]) == sorted(
                old_lines.get(key, [])):
            target = key                  # a named line that came through intact
        else:
            continue                      # a line that no longer exists as it was
        if line_bank_funded(new_lines.get(target, [])):
            continue
        out[target] = round(out.get(target, 0.0) + amount, 2)
    return out
