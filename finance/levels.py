"""Levels: what you have saved and invested, as a ladder to climb.

Each rung is a round number people actually picture — the first $1k, the
first $10k, six figures. The next one gets a month: when you reach it on the
plan, and when at the pace you are running now. The milestones past the
rungs are the two that change how money feels: the month your money's growth
puts in more than you do, and Coast FIRE, when it is set up.

Growth is the middle assumption the "If invested" chart uses, never the
flattering one.
"""

from __future__ import annotations

from .coastfire import add_months
from .projections import CHART_RATE

LEVELS = (
    (1_000, "$1k club"),
    (5_000, "$5k club"),
    (10_000, "$10k club"),
    (25_000, "$25k club"),
    (50_000, "$50k club"),
    (100_000, "Six figures"),
    (250_000, "Quarter million"),
    (500_000, "Half a million"),
    (1_000_000, "Millionaire"),
)

# Fifty years. Past that, "never" is the honest answer.
HORIZON = 600


def month_reaching(balance: float, monthly: float, target: float,
                   rate: float = CHART_RATE) -> int | None:
    """Months until the balance reaches the target, growing and topped up."""
    if balance >= target:
        return 0
    r = rate / 12
    value = balance
    for n in range(1, HORIZON + 1):
        value = value * (1 + r) + monthly
        if value >= target:
            return n
    return None


def growth_month(balance: float, monthly: float,
                 rate: float = CHART_RATE) -> int | None:
    """The first month the growth alone is more than what you put in."""
    r = rate / 12
    value = balance
    for n in range(0, HORIZON + 1):
        if value > 0 and value * r >= monthly:
            return n
        value = value * (1 + r) + monthly
    return None


def compute(balance: float, monthly_plan: float, monthly_pace: float,
            today: str, coast: dict | None = None) -> dict:
    month = today[:7]
    balance = max(balance, 0.0)
    earned = sum(1 for amount, _ in LEVELS if balance >= amount)
    current = LEVELS[earned - 1] if earned else None

    def eta(n: int | None) -> str | None:
        return add_months(month, n) if n is not None else None

    upcoming = None
    if earned < len(LEVELS):
        amount, name = LEVELS[earned]
        plan_n = month_reaching(balance, max(monthly_plan, 0.0), amount)
        pace_n = month_reaching(balance, max(monthly_pace, 0.0), amount)
        upcoming = {
            "amount": amount, "name": name,
            "left": round(amount - balance, 2),
            "progress": round(balance / amount, 4),
            "plan_months": plan_n, "plan_eta": eta(plan_n),
            "pace_months": pace_n, "pace_eta": eta(pace_n),
        }

    milestones = []
    for amount, name in LEVELS:
        n = month_reaching(balance, max(monthly_plan, 0.0), amount)
        milestones.append({"id": f"level-{amount}", "label": name,
                           "done": balance >= amount,
                           "eta": None if balance >= amount else eta(n)})
    growth = growth_month(balance, max(monthly_plan, 0.0))
    milestones.append({"id": "growth", "label": "Growth beats deposits",
                       "done": growth == 0, "eta": eta(growth) if growth else None})
    if coast:
        milestones.append({"id": "coast", "label": "Coast FIRE",
                           "done": bool(coast.get("coasting")),
                           "eta": None if coast.get("coasting")
                           else coast.get("coast_month")})

    # Unlocked first, then the rest in the order they arrive; never-on-this-
    # plan last.
    milestones.sort(key=lambda m: (not m["done"], m["eta"] is None, m["eta"] or ""))

    return {
        "balance": round(balance, 2),
        "level": ({"amount": current[0], "name": current[1]}
                  if current else None),
        "stars": {"earned": earned, "total": len(LEVELS)},
        "next": upcoming,
        "milestones": milestones,
        "rate": CHART_RATE,
        "monthly_plan": round(monthly_plan, 2),
        "monthly_pace": round(monthly_pace, 2),
    }
