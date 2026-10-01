"""What you can actually spend, worked out forwards from income.

The budget here used to be a median of past months: whatever you spent last
month, roughly, is what you may spend this month. That is a description
dressed up as a plan. It cannot tell you to spend less, because it is derived
from spending more, and a bad year quietly becomes the target.

So the total comes from arithmetic instead:

    income − fixed commitments − what you put away − what the piggy banks
    collect = what is left

Everything in that line is a decision rather than an observation. Rent is a
contract, savings is a choice, a piggy bank is a cost you have decided to meet
in twelve instalments instead of one, and the remainder is the only part a
daily number can influence.

History still has a job, but a different one. It is no use for deciding *how
much* is sensible to spend, and it is the best thing available for deciding
*how* that money gets divided: someone who has always spent four times as
much on groceries as on coffee will go on doing so, and a budget that
pretends otherwise gets ignored by the second week. So the pool is split
across categories in the proportions you already spend them — the shares are
yours, the total is the arithmetic's.
"""

from __future__ import annotations

from dataclasses import dataclass

from .analytics import counts_as_spending
from .categorize import CATEGORIES, is_discretionary

# A plan that leaves nothing over is not a plan anyone keeps, and one that
# leaves almost everything over is not telling you anything. Outside this
# band the app says so rather than quietly producing a strange daily number.
LOW_SHARE = 0.10
HIGH_SHARE = 0.75

# Below this a category's share is noise — a one-off in a category you do not
# really use, which would otherwise be handed a line in the budget forever.
MIN_CATEGORY_SHARE = 0.02


@dataclass
class FixedCost:
    id: int | None
    name: str
    amount: float
    category: str = "Other"

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name,
                "amount": round(self.amount, 2), "category": self.category}


def variable_shares(transactions, months_back: int = 12,
                    discretionary_only: bool = False) -> dict[str, float]:
    """How you divide the spending a budget can cover, as proportions of 1.0.

    Everything that is not a fixed commitment, which is what the leftover
    actually has to pay for. Groceries are essential and they are still bought
    with the money left after rent, so a budget that omitted them left a
    third of the month unaccounted for and read as if the plan had more room
    than it did.

    Proportions, never amounts. The amounts are what we are deliberately not
    taking from history; the shares are the part history genuinely knows.
    """
    totals: dict[str, float] = {}
    months = sorted({t.month for t in transactions})[-months_back:]
    recent = set(months)

    for t in transactions:
        if t.month not in recent or t.amount <= 0:
            continue
        category = t.category or "Other"
        if not counts_as_spending(t):
            continue
        if discretionary_only and not is_discretionary(category):
            continue
        totals[category] = totals.get(category, 0.0) + t.amount

    grand = sum(totals.values())
    if grand <= 0:
        return {}

    shares = {c: v / grand for c, v in totals.items()}
    # Drop the slivers, then renormalise so the kept shares still sum to one.
    kept = {c: s for c, s in shares.items() if s >= MIN_CATEGORY_SHARE}
    if not kept:
        return {}
    scale = sum(kept.values())
    return {c: round(s / scale, 4) for c, s in sorted(
        kept.items(), key=lambda kv: -kv[1])}


def discretionary_shares(transactions, months_back: int = 12) -> dict[str, float]:
    """Only the part a daily allowance can influence."""
    return variable_shares(transactions, months_back, discretionary_only=True)


def discretionary_pool(budgets: dict[str, float]) -> float:
    """The slice of the budget a daily number governs.

    Today's figure counts discretionary charges only — no amount of restraint
    on a Tuesday changes the grocery bill any more than it changes the hydro
    bill. So it has to divide the discretionary share of the leftover, not
    the whole of it, or it hands out the grocery money as pocket money.
    """
    return round(sum(amount for category, amount in budgets.items()
                     if is_discretionary(category)), 2)


def plan(income: float, fixed: list[FixedCost], savings: float,
         banks: float = 0.0) -> dict:
    """The arithmetic, with enough of its working shown to be argued with.

    `banks` is what the piggy banks collect this month — the annual costs
    turned into a monthly commitment. It is subtracted here, alongside rent
    and savings, because that is exactly what it is: money that has already
    been promised to a holiday or a set of tyres before the month starts.
    Leaving it out would hand the same money out twice, once as a daily
    allowance and again when the holiday is actually paid for.
    """
    income = round(max(float(income or 0), 0.0), 2)
    savings = round(max(float(savings or 0), 0.0), 2)
    banks = round(max(float(banks or 0), 0.0), 2)
    fixed_total = round(sum(max(f.amount, 0.0) for f in fixed), 2)
    leftover = round(income - fixed_total - savings - banks, 2)

    share = (leftover / income) if income > 0 else 0.0
    if income <= 0:
        verdict, note = "unset", "Add your monthly take-home pay to start."
    elif leftover < 0:
        committed = "fixed costs and savings"
        if banks > 0:
            committed = "fixed costs, savings and piggy banks"
        verdict, note = "negative", (
            f"Your {committed} come to more than you earn. "
            "Something here has to give before a daily number means anything.")
    elif share < LOW_SHARE:
        verdict, note = "tight", (
            f"That leaves {share:.0%} of your pay for everything else. "
            "Workable, but one unexpected bill will break it — consider "
            "lowering the savings figure rather than discovering it in week "
            "three.")
    elif share > HIGH_SHARE:
        verdict, note = "loose", (
            f"That leaves {share:.0%} of your pay unallocated. Nothing is "
            "wrong with it, but if some of that is really going into savings "
            "or a bill, putting it above makes the daily number mean more.")
    else:
        verdict, note = "ok", (
            f"{share:.0%} of your pay is left after commitments and savings, "
            "to cover everything else you buy.")

    return {
        "income": income,
        "fixed_total": fixed_total,
        "savings": savings,
        "banks": banks,
        "committed": round(fixed_total + savings + banks, 2),
        "leftover": leftover,
        "leftover_share": round(share, 4),
        "daily": round(leftover / 30.44, 2) if leftover > 0 else 0.0,
        "verdict": verdict,
        "note": note,
        "fixed": [f.to_dict() for f in fixed],
        "complete": income > 0,
    }


def monthly_allowance(income: float, fixed: list[FixedCost], savings: float,
                      banks: float, shares: dict[str, float]) -> float:
    """The discretionary pool a daily number divides, derived from the plan.

    This is the one figure the Today tab needs, and it is computed here rather
    than stored anywhere. It used to be saved as a setting when you pressed
    "Use these budgets", which meant raising your income, adding a commitment
    or opening a piggy bank changed the Plan tab and left Today quoting the
    figure from whenever that button was last pressed. A derived number cannot
    go stale.
    """
    result = plan(income, fixed, savings, banks)
    if result["leftover"] <= 0:
        return 0.0
    return discretionary_pool(category_budgets(result["leftover"], shares))


# Above this, "Other" is not a category, it is a gap in the categorisation —
# and a budget whose biggest line is a bucket you cannot picture is a budget
# nobody can act on.
UNCATEGORISED_WARN = 0.25


def uncategorised_warning(shares: dict[str, float]) -> str | None:
    """Say when the budget's biggest line is really a missing one."""
    share = shares.get("Other", 0.0)
    if share < UNCATEGORISED_WARN:
        return None
    return (
        f"{share:.0%} of your discretionary spending is uncategorised, so "
        f"that share of the budget is a line called \u201cOther\u201d. The "
        "money is real, but you cannot act on it. Correcting a few merchants "
        "on the Transactions tab \u2014 ticking \u201capply to every charge "
        "from this merchant\u201d \u2014 moves a lot of it at once, and the "
        "budget gets sharper every time you do.")


def category_budgets(leftover: float, shares: dict[str, float]) -> dict[str, float]:
    """Split the leftover across categories in the proportions already used.

    The parts sum to the whole exactly. Rounding each share on its own left
    the budget lines adding up to a few cents either side of the pool, which
    is the kind of discrepancy that makes someone stop trusting every other
    number on the page. The remainder goes to the largest line, where a cent
    is least visible.
    """
    if leftover <= 0 or not shares:
        return {}

    raw = {c: leftover * s for c, s in shares.items()}
    # Slivers are dropped first, then the rest are rescaled, so what is
    # dropped is redistributed rather than quietly lost from the total.
    kept = {c: v for c, v in raw.items() if v >= 1}
    if not kept:
        return {}
    scale = leftover / sum(kept.values())
    out = {c: round(v * scale, 2) for c, v in kept.items()}

    drift = round(leftover - sum(out.values()), 2)
    if drift:
        biggest = max(out, key=lambda c: out[c])
        out[biggest] = round(out[biggest] + drift, 2)
    return out


def headroom(leftover: float, typical_total: float) -> dict | None:
    """When the plan leaves more than you actually spend.

    Good news, and easy to present badly. A budget line reading "$574 more
    than you usually spend" is an invitation, and this app is built so that
    nothing in it pays out for buying something. The same fact put the other
    way round — that much of your pay is drifting rather than being saved —
    is the one worth acting on.
    """
    if leftover <= 0 or typical_total <= 0:
        return None
    spare = round(leftover - typical_total, 2)
    if spare < max(typical_total * 0.15, 50):
        return None
    return {
        "spare": spare,
        "typical_total": round(typical_total, 2),
        "note": (
            f"You typically spend about {_money(typical_total)} a month of "
            f"this, leaving {_money(spare)} unallocated. That is not spare "
            "money to find a use for — it is the clearest saving available "
            "to you. Raising the savings figure above by some of it makes it "
            "happen on purpose rather than by accident."),
    }


def _money(value: float) -> str:
    return f"${value:,.0f}"


def explain(leftover: float, shares: dict[str, float],
            historical: dict[str, float] | None = None) -> list[dict]:
    """Each category's new budget beside what it used to cost.

    Shown together because the difference is the whole point: a category
    whose budget is well under what you spend is where the plan is asking
    something of you, and it is better to see that on the day you set it than
    to meet it as a failure three weeks later.
    """
    budgets = category_budgets(leftover, shares)
    rows = []
    for category, amount in budgets.items():
        was = round((historical or {}).get(category, 0.0), 2)
        rows.append({
            "category": category,
            "budget": amount,
            "share": shares.get(category, 0.0),
            "typical": was,
            "change": round(amount - was, 2) if was else None,
            "essential": not CATEGORIES.get(category, {}).get("discretionary", True),
        })
    rows.sort(key=lambda r: -r["budget"])
    return rows
