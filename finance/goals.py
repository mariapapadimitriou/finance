"""Savings goals: how far along each one is, and when it lands.

A goal is a target, what you have put towards it so far, and what goes in
each month. The month it lands is plain arithmetic on those. The game is the
other figure: when your spending is running under the plan, that extra could
go to a goal, and the month it would land instead is worth seeing.
"""

from __future__ import annotations

import math

from .coastfire import add_months


def _months(left: float, monthly: float) -> int | None:
    if left <= 0:
        return 0
    if monthly <= 0:
        return None
    return max(1, math.ceil(round(left / monthly, 6)))


def status(goal: dict, today: str, extra: float = 0.0) -> dict:
    """One goal's progress, its landing month, and what the extra would do."""
    target, saved, monthly = goal["target"], goal["saved"], goal["monthly"]
    left = round(max(target - saved, 0.0), 2)
    reached = left <= 0
    months = _months(left, monthly)
    month = today[:7]

    faster = sooner = None
    if not reached and extra > 0:
        faster = _months(left, monthly + extra)
        if months is not None and faster is not None:
            sooner = months - faster

    return {
        **goal,
        "progress": round(min(saved / target, 1.0), 4) if target > 0 else 1.0,
        "left": left,
        "reached": reached,
        "months": None if reached else months,
        "eta": None if reached or months is None else add_months(month, months),
        # With this month's extra added each month, if there is any.
        "eta_with_extra": (add_months(month, faster)
                           if faster is not None else None),
        "sooner": sooner,
    }


def funding(goals: list[dict], saving: float) -> dict:
    """How the plan's saving divides: goals first, investing gets the rest.

    A reached goal takes nothing more. Investing never goes below zero; when
    the goals ask for more than you save, `over` says by how much.
    """
    active = [g for g in goals if g["saved"] < g["target"]]
    to_goals = round(sum(g["monthly"] for g in active), 2)
    return {
        "saving": round(saving, 2),
        "to_goals": to_goals,
        "to_investing": round(max(saving - to_goals, 0.0), 2),
        "over": round(max(to_goals - saving, 0.0), 2),
    }
