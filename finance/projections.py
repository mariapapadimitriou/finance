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
            plan: dict | None = None, today: str | None = None) -> dict:
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

    # What the plan's leftover actually has to cover, which is not the same
    # thing. `leftover` already has the commitments taken out of it, and a
    # commitment paid by card — a phone bill, insurance — is *also* in the
    # spending above. Subtracting both charged it twice and made the surplus
    # look worse than the ledger does.
    #
    # Each commitment names a category, so those categories come out of the
    # comparison. It is not perfect — a commitment could share a category with
    # ordinary spending — but it is far closer than counting them twice, and it
    # errs toward the plan looking worse rather than better.
    committed = {f["category"] for f in (plan or {}).get("fixed", [])
                 if isinstance(f, dict) and f.get("category")}
    plan_spend = (typical_month_spend(transactions, exclude=committed)
                  if committed else typical_spend)

    # Income is only visible when payroll lands on an imported card. Credit card
    # statements usually show none, so it is an input rather than a deduction.
    observed_income = [totals[m]["income"] for m in observed if totals[m]["income"] > 0]
    income = monthly_income if monthly_income else (
        round(statistics.median(observed_income), 2) if observed_income else None
    )

    if not income:
        return {
            "available": False,
            "reason": "Add your monthly take-home pay on the Plan to see "
                      "projections.",
            "typical_monthly_spend": typical_spend,
            "months_observed": len(observed),
        }

    surplus, basis = _surplus(income, plan_spend, plan)
    on_plan = basis.get("on_plan")
    monthly_cuts = round(found_savings_annual / 12, 2)

    # What is actually being set aside on purpose: the savings figure when
    # there is a plan, and otherwise whatever the month happens to leave.
    saving = on_plan if on_plan is not None else surplus
    if today is None:
        from datetime import date as _date
        today = _date.today().isoformat()

    rows = []
    pace, planned = 0.0, 0.0
    for i in range(1, months_ahead + 1):
        pace = round(pace + surplus, 2)
        planned = round(planned + (on_plan if on_plan is not None
                                   else surplus + monthly_cuts), 2)
        rows.append({"month": i, "pace": pace, "on_plan": planned})

    return {
        "available": True,
        "months_observed": len(observed),
        "monthly_income": round(income, 2),
        "typical_monthly_spend": typical_spend,
        # What the leftover is measured against: the same months with the
        # commitment categories removed, so nothing is subtracted twice.
        "plan_spend": plan_spend,
        "monthly_surplus": surplus,
        "monthly_cuts": monthly_cuts,
        "series": rows,
        "at_12": rows[-1] if rows else None,
        # The rest of this calendar year, which is the horizon anyone
        # actually pictures. Not a balance — the app has never seen one.
        "year_end": {
            "months": months_left_in_year(today),
            "pace": by_year_end(surplus, today)["total"],
            "on_plan": by_year_end(saving, today)["total"],
        },
        # The same contribution left to compound instead of sitting still.
        "invested": invested(saving),
        # The terms behind the surplus, so the figure can be argued with rather
        # than taken on trust — the same treatment the daily number gets.
        "basis": basis,
        "from_plan": basis["from_plan"],
        # What following the plan accumulates each month, against what the
        # recent pace does. The chart draws both.
        "monthly_on_plan": basis.get("on_plan"),
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
    """How long a savings target takes at the recent pace, and on the plan."""
    if not projection.get("available") or target <= 0:
        return None

    def months_for(rate: float) -> int | None:
        if rate is None or rate <= 0:
            return None
        return max(1, int(-(-target // rate)))

    on_plan = projection.get("monthly_on_plan")
    return {
        "target": round(target, 2),
        "pace_months": months_for(projection["monthly_surplus"]),
        "plan_months": months_for(
            on_plan if on_plan is not None
            else projection["monthly_surplus"] + projection["monthly_cuts"]),
    }


def _surplus(income: float, typical_spend: float,
             plan: dict | None) -> tuple[float, dict]:
    """What accumulates each month at the recent pace, and on the plan.

    Two figures, because the honest answer to "where does this land" depends
    entirely on which question is being asked, and the tab used to answer only
    the discouraging one:

      *recent pace*  what you put away, plus whatever the plan's leftover has
                     actually been going unspent. Spend above budget and this
                     is negative, which is the truth about the last few months
                     and says nothing about the plan.
      *on plan*      what you put away, full stop. Following the plan means
                     spending the budget, so the budget is not a surplus — the
                     savings figure is, and it arrives every month.

    Reporting only the first made the plan look unachievable because it was
    never being projected: a ledger that overspends its budget projected a flat
    or falling line for ever, however good the plan was.
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
            "on_plan": saving,
        }

    return round(income - typical_spend, 2), {
        "from_plan": False,
        "income": round(income, 2),
        "typical_spend": typical_spend,
        "on_plan": None,
    }


# ── What it becomes if it is invested rather than held ───────────────────────
#
# Rates, not a rate. A single number would be a forecast dressed as arithmetic,
# and the honest shape of this question is a range: the same contribution is a
# very different sum after thirty years depending on where it sits. These are
# long-run nominal averages of the obvious places to put it, and the UI labels
# them as assumptions rather than expectations, because a real thirty years
# delivers them in a jagged order that includes falling years.
RATES = (
    (0.02, "A savings account"),
    (0.05, "A balanced portfolio"),
    (0.08, "A stock index"),
)

# The one drawn as a chart: the middle assumption, never the flattering one.
CHART_RATE = 0.05

HORIZONS = (5, 10, 20, 30)


def future_value(monthly: float, annual_rate: float, months: int,
                 opening: float = 0.0) -> float:
    """An ordinary annuity: a contribution at the end of each month, compounded.

    Monthly compounding of an annual rate divided by twelve, which is the
    convention every retirement calculator uses and is close enough to the
    truth that the difference is invisible beside the uncertainty in the rate
    itself.
    """
    if months <= 0:
        return round(opening, 2)
    r = annual_rate / 12
    if r == 0:
        return round(opening + monthly * months, 2)
    growth = (1 + r) ** months
    return round(opening * growth + monthly * (growth - 1) / r, 2)


def invested(monthly: float, opening: float = 0.0) -> dict | None:
    """What a monthly contribution comes to, under each assumption.

    Contributions are reported beside every value, because the gap between
    them is the only part of this that is interesting — and the only part that
    is not simply the contribution restated.
    """
    if monthly <= 0:
        return None

    def at(rate: float, years: int) -> dict:
        months = years * 12
        value = future_value(monthly, rate, months, opening)
        paid_in = round(opening + monthly * months, 2)
        return {"years": years, "value": value, "contributed": paid_in,
                "growth": round(value - paid_in, 2)}

    return {
        "monthly": round(monthly, 2),
        "opening": round(opening, 2),
        "horizons": list(HORIZONS),
        "rates": [
            {"rate": rate, "label": label,
             "at": {str(y): at(rate, y) for y in HORIZONS}}
            for rate, label in RATES
        ],
        # One line of value against one of contributions, year by year, for
        # the middle assumption. The area between them is the growth.
        "chart_rate": CHART_RATE,
        "series": [
            {"year": y,
             "contributed": round(opening + monthly * y * 12, 2),
             "value": future_value(monthly, CHART_RATE, y * 12, opening)}
            for y in range(0, max(HORIZONS) + 1)
        ],
    }


def months_left_in_year(today: str) -> int:
    """Including the month we are in, which is the month still being saved."""
    return 13 - int(today[5:7])


def by_year_end(monthly: float, today: str) -> dict:
    """What the rest of the calendar year accumulates at this rate.

    Deliberately not "your savings", which the app has no way to know — it has
    never seen a savings balance, only what the plan sets aside. So this is
    what these remaining months add, and the UI says so.
    """
    months = months_left_in_year(today)
    return {"months": months, "total": round(max(monthly, 0.0) * months, 2)}
