"""Forward projections: where this lands if nothing changes, and if it does.

Two lines, and the difference between them is the point:

  *current pace*  — your own recent monthly surplus, carried forward
  *with cuts*     — the same, plus the savings the engine has already found

Projections are arithmetic on a trend, not a forecast. The honest part is
saying how thin the trend is: with three observed months the band around any
projection is wider than the projection itself, so the months of data behind it
travel with the numbers and the UI states them.
"""

from __future__ import annotations

import statistics

from .spend_plan import counts_toward_plan


def _monthly_totals(transactions) -> dict[str, dict]:
    """Discretionary spend and income per month, observed months only."""
    out: dict[str, dict] = {}
    for t in transactions:
        m = out.setdefault(t.month, {"spend": 0.0, "income": 0.0, "all_spend": 0.0})
        if counts_toward_plan(t):
            m["spend"] += t.amount
        if t.amount > 0 and t.category not in ("Income", "Transfers"):
            m["all_spend"] += t.amount
        # Only real income counts. A card payment is a Transfer — money moving
        # onto the card to clear it, not money arriving. Treating it as income
        # would read a $1,000 payment as a $1,000 salary and project savings
        # from your own debt repayment.
        if t.category == "Income" and t.amount < 0:
            m["income"] += abs(t.amount)
    return {k: {kk: round(vv, 2) for kk, vv in v.items()} for k, v in out.items()}


def project(transactions, monthly_income: float | None = None,
            found_savings_annual: float = 0.0, months_ahead: int = 12,
            plan: dict | None = None) -> dict:
    """Project cumulative savings forward under two scenarios.

    `plan` is the result of `money_plan.plan` when one has been set up. It
    matters a great deal. Without it the only surplus available is take-home
    less the spending visible on the imported cards — which silently treats
    rent as money you could be saving, because rent is usually paid by transfer
    and never appears. On a real ledger that produced a surplus of $3,552 a
    month against a plan that had $1,910 left in it, and a twelve-month
    projection five times larger than anything achievable.

    With a plan the app already knows the commitments, so the projection is
    built from what the plan says accumulates:

        what you put away  +  what the plan leaves unspent

    Piggy banks are deliberately not in that sum. They collect, but they
    collect in order to be spent on the thing they are named after, so counting
    them as savings would be the same mistake in a smaller coat.
    """
    totals = _monthly_totals(transactions)
    observed = sorted(totals)

    if not observed:
        return {"available": False,
                "reason": "No transactions yet — import statements to project."}

    # The same definition the Overview quotes, so the two tabs cannot
    # disagree about what a normal month costs.
    from .analytics import typical_month_spend
    typical_spend = typical_month_spend(transactions)

    # Income is only visible when payroll lands on an imported card. Credit card
    # statements usually show none, so it is an input rather than a deduction.
    observed_income = [totals[m]["income"] for m in observed if totals[m]["income"] > 0]
    income = monthly_income if monthly_income else (
        round(statistics.median(observed_income), 2) if observed_income else None
    )

    if not income:
        return {
            "available": False,
            "reason": "Add your monthly take-home pay to project savings — "
                      "credit card statements don't show income.",
            "typical_monthly_spend": typical_spend,
            "months_observed": len(observed),
        }

    surplus, basis = _surplus(income, typical_spend, plan)
    monthly_cuts = round(found_savings_annual / 12, 2)

    rows = []
    base, improved = 0.0, 0.0
    for i in range(1, months_ahead + 1):
        base = round(base + surplus, 2)
        improved = round(improved + surplus + monthly_cuts, 2)
        rows.append({"month": i, "current": base, "with_cuts": improved})

    return {
        "available": True,
        "months_observed": len(observed),
        "monthly_income": round(income, 2),
        "typical_monthly_spend": typical_spend,
        "monthly_surplus": surplus,
        "monthly_cuts": monthly_cuts,
        "series": rows,
        "at_12": rows[-1] if rows else None,
        # The terms behind the surplus, so the figure can be argued with rather
        # than taken on trust — the same treatment the daily number gets.
        "basis": basis,
        "from_plan": basis["from_plan"],
        "caveat": (
            # With a plan, commitments are known and subtracted, so the old
            # "ceiling" warning would now be false modesty about a figure that
            # is actually derived. What remains uncertain is the spending, not
            # the income.
            "Your commitments come out of this, so it is what the plan expects "
            "to accumulate rather than an upper bound. The spending side is "
            "still only the cards you have imported."
            if basis["from_plan"] else
            "Based only on the cards you've imported. Spending that never "
            "touches them — rent, other cards, cash — isn't counted, so "
            "treat the surplus as a ceiling."
        ),
        # A projection off three months is a guess with a wide band; off twelve
        # it is a trend. The caller shows this rather than implying precision.
        "confidence": ("thin" if len(observed) < 4
                       else "fair" if len(observed) < 8 else "reasonable"),
    }


def goal_eta(projection: dict, target: float) -> dict | None:
    """How long a savings target takes under each scenario."""
    if not projection.get("available") or target <= 0:
        return None

    def months_for(rate: float) -> int | None:
        if rate <= 0:
            return None
        return max(1, int(-(-target // rate)))

    return {
        "target": round(target, 2),
        "current_months": months_for(projection["monthly_surplus"]),
        "with_cuts_months": months_for(
            projection["monthly_surplus"] + projection["monthly_cuts"]),
    }


def _surplus(income: float, typical_spend: float,
             plan: dict | None) -> tuple[float, dict]:
    """What accumulates each month, and the terms it came from.

    Two cases, and the difference between them is whether the app knows what
    is already committed.
    """
    if plan and plan.get("income", 0) > 0:
        leftover = plan["leftover"]
        unspent = round(leftover - typical_spend, 2)
        saving = plan["savings"]
        return round(saving + unspent, 2), {
            "from_plan": True,
            "income": plan["income"],
            "fixed_total": plan["fixed_total"],
            # Named so the tab can say why it is excluded rather than appearing
            # to have forgotten it.
            "banks": plan["banks"],
            "saving": saving,
            "leftover": leftover,
            "typical_spend": typical_spend,
            "unspent": unspent,
        }

    return round(income - typical_spend, 2), {
        "from_plan": False,
        "income": round(income, 2),
        "typical_spend": typical_spend,
    }
