"""Insights written in advance, shown when they apply to you.

The savings engine next door looks at transactions and finds things to cut.
This looks at the shape of the whole plan — what comes in, what is committed,
what is left, what that leaves per day — and says the handful of things worth
saying about it. A bot used to do this job by reading the same figures and
writing a paragraph. It cost money per answer, and it could be wrong, and it
could be wrong differently each time you asked.

So the observations are written here instead, once, by hand, each with the
condition under which it is true. There are a few dozen things worth telling
someone about a budget, and they are all knowable in advance:

    if your commitments are more than 55% of your pay, that is worth saying
    if you are putting away nothing while the plan leaves a surplus, that is
    worth saying
    if the weekly number is under seventy dollars, the plan will not survive
    contact with a Tuesday

What varies between people is which ones apply and what the numbers are, and
both of those are arithmetic. The result costs nothing to run, says the same
thing twice when asked twice, and cannot invent a figure that the Overview tab
disagrees with — the numbers come from the same functions every other tab
uses.

Three severities, which are a claim about what to do and not about how alarming
something sounds:

    act    something is wrong and there is a specific thing to change
    watch  true and worth knowing, but nothing is broken
    good   worth saying out loud, because a budget that only ever reports
           failure is one people stop opening

Each observation names the tab that can act on it, because an insight you
cannot do anything with is just a mood.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field

# Thresholds, gathered here rather than buried in the rules so they can be
# argued with in one place. None of them is a law of nature; they are the
# commonly cited rules of thumb, and the prose says so where it matters.
HIGH_COMMITMENT_SHARE = 0.55      # fixed costs + savings as a share of pay
LOW_SAVINGS_SHARE = 0.10          # what you are putting away
GOOD_SAVINGS_SHARE = 0.20
THIN_WEEKLY = 70.0                # a weekly allowance nobody can keep to
DOMINANT_CATEGORY_SHARE = 0.40    # one category, this much of discretionary
HEAVY_SUBSCRIPTION_SHARE = 0.15   # renewals as a share of discretionary
OVERSPEND_TOLERANCE = 0.10        # over the plan by more than this is a story
THIN_HISTORY_MONTHS = 3
EMERGENCY_MONTHS = 3              # months of commitments worth having aside


@dataclass
class Observation:
    id: str
    title: str
    detail: str
    severity: str                      # act | watch | good
    metric: str = ""                   # the figure it turns on, formatted
    tab: str = ""                      # where to go to do something about it
    action: str = ""                   # the label for that link
    figures: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Profile:
    """Everything the observations below are allowed to look at.

    Assembled by the caller from the same functions the tabs use, so an
    observation cannot quote a number the rest of the app disagrees with.
    """

    income: float = 0.0
    fixed_total: float = 0.0
    savings: float = 0.0
    bank_monthly: float = 0.0
    leftover: float = 0.0
    daily: float = 0.0
    months_of_history: int = 0
    # Last complete month, for comparisons that need a month that finished.
    last_month: str = ""
    last_month_discretionary: float = 0.0
    discretionary_budget: float = 0.0
    shares: dict = field(default_factory=dict)
    uncategorised_share: float = 0.0
    subscriptions_monthly: float = 0.0
    budgets_set: int = 0
    banks: list = field(default_factory=list)
    travel_last_year: float = 0.0
    findings_weighted_annual: float = 0.0

    @property
    def committed(self) -> float:
        return round(self.fixed_total + self.savings + self.bank_monthly, 2)

    @property
    def has_plan(self) -> bool:
        return self.income > 0


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _pct(v: float) -> str:
    return f"{v:.0%}"


# ── The library ──────────────────────────────────────────────────────────────
# Each rule takes the profile and returns an Observation or None. Order here is
# the order they are considered; the final list is sorted by severity.

def no_plan_yet(p: Profile) -> Observation | None:
    if p.has_plan:
        return None
    return Observation(
        id="no_plan",
        title="The plan has no income in it yet",
        detail=("Everything else on this page can be worked out from your "
                "transactions, but what you can afford cannot — that needs to "
                "start from what you earn. Until it does, the weekly number is "
                "your own median spending, which describes your habits rather "
                "than deciding anything."),
        severity="act", tab="plan", action="Set up your plan",
    )


def commitments_are_heavy(p: Profile) -> Observation | None:
    if not p.has_plan or p.income <= 0:
        return None
    share = p.committed / p.income
    if share < HIGH_COMMITMENT_SHARE:
        return None
    return Observation(
        id="heavy_commitments",
        title=f"{_pct(share)} of your pay is committed before the month starts",
        detail=(f"Rent, bills, savings and piggy banks come to "
                f"{_money(p.committed)} of {_money(p.income)}. The usual "
                "advice is to keep that under about half, and the reason is "
                "not neatness: commitments are the hardest spending to change "
                "quickly, so the more of your pay they take, the less room you "
                "have when something unexpected arrives. Worth checking "
                "whether anything on the commitments list has stopped being "
                "one."),
        severity="watch" if share < 0.7 else "act",
        metric=_pct(share), tab="plan", action="Review commitments",
        figures={"share": round(share, 4), "committed": p.committed,
                 "income": p.income},
    )


def saving_nothing(p: Profile) -> Observation | None:
    if not p.has_plan or p.savings > 0 or p.leftover <= 0:
        return None
    return Observation(
        id="saving_nothing",
        title="Nothing is being put away",
        detail=(f"The plan leaves {_money(p.leftover)} a month after your "
                "commitments, and none of it is marked as savings — so "
                "whatever is left at the end of the month is left by accident "
                "rather than on purpose. Deciding a figure, even a small one, "
                "is what makes the difference: it comes out before the daily "
                "allowance is worked out, so it stops being optional."),
        severity="act", tab="plan", action="Set a savings figure",
        figures={"leftover": p.leftover},
    )


def saving_little(p: Profile) -> Observation | None:
    if not p.has_plan or p.savings <= 0 or p.income <= 0:
        return None
    share = p.savings / p.income
    if share >= LOW_SAVINGS_SHARE:
        return None
    return Observation(
        id="saving_little",
        title=f"You are putting away {_pct(share)} of your pay",
        detail=(f"That is {_money(p.savings)} a month. The figure usually "
                "suggested is around 15–20%, which would be "
                f"{_money(p.income * 0.15)}–{_money(p.income * 0.2)} — but the "
                "number that matters is the one you can hold to every month, "
                "not the one on a chart. If the plan is comfortable, raising "
                "this is the cheapest change available to you, because it "
                "happens before you see the money."),
        severity="watch", metric=_pct(share), tab="plan",
        action="Raise the savings figure",
        figures={"share": round(share, 4), "savings": p.savings},
    )


def saving_well(p: Profile) -> Observation | None:
    if not p.has_plan or p.income <= 0:
        return None
    share = p.savings / p.income
    if share < GOOD_SAVINGS_SHARE or p.leftover <= 0:
        return None
    return Observation(
        id="saving_well",
        title=f"{_pct(share)} of your pay is going into savings",
        detail=(f"{_money(p.savings)} a month, and the plan still leaves "
                f"{_money(p.leftover)} to live on. That is comfortably above "
                "what is usually recommended. Nothing to do — it is here "
                "because a page that only ever lists problems is one you stop "
                "reading, and this is the number most worth not breaking."),
        severity="good", metric=_pct(share),
        figures={"share": round(share, 4), "savings": p.savings},
    )


def plan_is_too_tight(p: Profile) -> Observation | None:
    if not p.has_plan or p.leftover <= 0 or p.daily <= 0:
        return None
    # Today's number is a week now; `daily` is still what the profile
    # carries, since the arithmetic underneath is a daily share.
    weekly = round(p.daily * 7, 2)
    if weekly >= THIN_WEEKLY:
        return None
    return Observation(
        id="too_tight",
        title=f"The plan leaves {_money(weekly)} a week",
        detail=("That is thin enough that a couple of coffees and a bus fare "
                "breaks it, and a budget you break by Wednesday is a budget "
                "you stop using by the weekend. This is usually a sign that "
                "the savings figure or a piggy bank is set higher than the "
                "month can actually bear. Lowering it on purpose is better "
                "than discovering it in week three."),
        severity="act", metric=_money(weekly), tab="plan",
        action="Loosen the plan", figures={"daily": p.daily, "weekly": weekly},
    )


def spending_over_the_plan(p: Profile) -> Observation | None:
    if p.discretionary_budget <= 0 or not p.last_month:
        return None
    over = p.last_month_discretionary - p.discretionary_budget
    if over <= p.discretionary_budget * OVERSPEND_TOLERANCE:
        return None
    return Observation(
        id="over_the_plan",
        title=f"Last month ran {_money(over)} over the plan",
        detail=(f"The plan allows {_money(p.discretionary_budget)} a month of "
                f"day-to-day spending and {_month_name(p.last_month)} used "
                f"{_money(p.last_month_discretionary)}. One month proves "
                "nothing, but if it keeps happening the plan is being ignored "
                "rather than followed, and a plan nobody follows is worse than "
                "none — it makes every other number on the page a guess. "
                "Either the spending or the plan has to move."),
        severity="act", metric=_money(over), tab="budgets",
        action="See which categories",
        figures={"over": round(over, 2),
                 "spent": p.last_month_discretionary,
                 "budget": p.discretionary_budget},
    )


def living_under_the_plan(p: Profile) -> Observation | None:
    if p.discretionary_budget <= 0 or not p.last_month:
        return None
    under = p.discretionary_budget - p.last_month_discretionary
    if under < max(p.discretionary_budget * 0.15, 50):
        return None
    return Observation(
        id="under_the_plan",
        title=f"Last month came in {_money(under)} under the plan",
        detail=(f"{_money(p.last_month_discretionary)} spent against "
                f"{_money(p.discretionary_budget)} allowed. That surplus is "
                "real money, and right now it is drifting rather than going "
                "anywhere: unless it is named, it quietly becomes next month's "
                "spending. Moving some of it into savings or a piggy bank is "
                "how a good month turns into something you keep."),
        severity="good", metric=_money(under), tab="plan",
        action="Put it somewhere",
        figures={"under": round(under, 2)},
    )


def one_category_dominates(p: Profile) -> Observation | None:
    if not p.shares:
        return None
    category, share = max(p.shares.items(), key=lambda kv: kv[1])
    if share < DOMINANT_CATEGORY_SHARE or category == "Other":
        return None
    return Observation(
        id=f"dominant_{category.lower().replace(' ', '_')}",
        title=f"{category} is {_pct(share)} of your day-to-day spending",
        detail=(f"Not a problem in itself — it may be exactly where you want "
                f"your money to go. It is worth knowing because it is the only "
                "line where a change makes a visible difference: trimming a "
                f"tenth off {category} does more than halving anything else on "
                "the list, and the reverse is also true, so it is where the "
                "month usually goes wrong."),
        severity="watch", metric=_pct(share), tab="budgets",
        action=f"See {category}",
        figures={"category": category, "share": round(share, 4)},
    )


def subscriptions_are_heavy(p: Profile) -> Observation | None:
    if p.subscriptions_monthly <= 0 or p.discretionary_budget <= 0:
        return None
    share = p.subscriptions_monthly / p.discretionary_budget
    if share < HEAVY_SUBSCRIPTION_SHARE:
        return None
    return Observation(
        id="heavy_subscriptions",
        title=f"{_pct(share)} of your spending money renews without a decision",
        detail=(f"{_money(p.subscriptions_monthly)} a month of the "
                f"{_money(p.discretionary_budget)} you have to spend goes to "
                "things that bill themselves. That is the easiest money in the "
                "budget to free up, because cancelling takes one decision "
                "rather than sustained restraint — and the hardest to notice, "
                "for the same reason."),
        severity="watch", metric=_pct(share), tab="subscriptions",
        action="Review what renews",
        figures={"share": round(share, 4),
                 "monthly": p.subscriptions_monthly},
    )


def budgets_not_adopted(p: Profile) -> Observation | None:
    if not p.has_plan or p.budgets_set > 0 or p.leftover <= 0:
        return None
    return Observation(
        id="budgets_not_adopted",
        title="The plan has worked out your budgets, but none are set",
        detail=("The arithmetic is done — what you earn, less commitments, "
                "divided across categories in the proportions you already "
                "spend them. Budgets shows that split as a proposal; until "
                "you adopt it, nothing is tracked against it and the month "
                "has no per-category shape."),
        # Budgets, not the plan: the button that adopts the split is on the
        # page the split is shown on now.
        severity="act", tab="budgets", action="Use these budgets",
    )


def uncategorised_is_large(p: Profile) -> Observation | None:
    if p.uncategorised_share < 0.25:
        return None
    return Observation(
        id="uncategorised",
        title=f"{_pct(p.uncategorised_share)} of your spending is uncategorised",
        detail=("That share of the budget is a line called “Other”, "
                "which is money you cannot act on: no rule can tell you to "
                "spend less on a category you cannot picture. Correcting a few "
                "merchants fixes a lot at once — ticking “apply to every "
                "charge from this merchant” moves every past and future "
                "charge from it in one go."),
        severity="act", metric=_pct(p.uncategorised_share),
        tab="transactions", action="Fix some merchants",
        figures={"share": round(p.uncategorised_share, 4)},
    )


def travel_has_no_bank(p: Profile) -> Observation | None:
    """The case piggy banks exist for, pointed out from the data."""
    if p.travel_last_year <= 240:
        return None
    if any("Travel" in (b.get("categories") or []) for b in p.banks):
        return None
    monthly = round(p.travel_last_year / 12, 2)
    return Observation(
        id="travel_no_bank",
        title=f"{_money(p.travel_last_year)} of travel, paid from the week",
        detail=(f"That is what the last year of travel cost. Until a piggy "
                "bank pays for it, every trip lands on the week it was "
                "booked in and makes that week look like a disaster. A bank "
                f"of {_money(p.travel_last_year)} a year takes "
                f"{_money(monthly)} out of every month instead, has the whole "
                "amount ready from the day it opens, and pays for every "
                "travel charge by itself — the weekly allowance is left for "
                "the everyday."),
        severity="act", metric=_money(monthly), tab="piggy",
        action="Open a travel bank",
        figures={"annual": p.travel_last_year, "monthly": monthly},
    )


def a_bank_is_catching_up(p: Profile) -> list[Observation]:
    """A bank over this year's budget, or repaying last year's overspend.

    Both are allowed — sometimes the trip costs what it costs — and both are
    worth knowing about, because they are why a month can feel tighter.
    """
    out = []
    for bank in p.banks:
        base = round(bank.get("target", 0) / 12, 2)
        if bank.get("over"):
            out.append(Observation(
                id=f"bank_behind_{bank['id']}",
                title=f"{bank['name']} is {_money(bank['behind_by'])} over this year",
                detail=(f"It paid {_money(bank.get('spent_this_year', 0))} "
                        f"against a budget of {_money(bank['target'])} a year. "
                        "That is allowed, and it changes nothing this year. "
                        "Next year the bank repays what it actually spent, so "
                        "its monthly contribution rises by the overspend "
                        "spread over twelve months."),
                severity="watch", metric=_money(bank["behind_by"]),
                tab="piggy", action=f"Look at {bank['name']}",
                figures={"bank": bank["name"], "behind": bank["behind_by"],
                         "monthly": bank["monthly"]},
            ))
        elif (bank.get("basis") == "repaying" and bank.get("cadence") != "once"
              and bank.get("monthly", 0) > base + 0.005):
            out.append(Observation(
                id=f"bank_repaying_{bank['id']}",
                title=f"{bank['name']} is repaying last year's overspend",
                detail=(f"Last year it paid "
                        f"{_money(bank.get('spent_last_year') or 0)}, more than "
                        f"its {_money(bank['target'])}. So this year it takes "
                        f"{_money(bank['monthly'])} a month instead of "
                        f"{_money(base)}, and that extra is coming out of your "
                        "everyday money. Nothing to fix; worth knowing why "
                        "the week feels tighter."),
                severity="watch", metric=_money(bank["monthly"]),
                tab="piggy", action=f"Look at {bank['name']}",
                figures={"bank": bank["name"], "monthly": bank["monthly"],
                         "base_monthly": base},
            ))
    return out


def a_bank_is_ready(p: Profile) -> list[Observation]:
    """A bank whose money is really in it, not just promised.

    Every bank can pay its whole target from the day it opens, so "can pay"
    says nothing. What is worth a good word is the real money — paid in, less
    paid out — reaching the target.
    """
    out = []
    for bank in p.banks:
        held = bank.get("held", 0)
        if bank.get("over") or held <= 0 or held < bank.get("target", 0):
            continue
        out.append(Observation(
            id=f"bank_ready_{bank['id']}",
            title=f"{bank['name']} is fully funded",
            detail=(f"{_money(held)} is really in it, against a target of "
                    f"{_money(bank['target'])}. The thing it is for is paid "
                    "for before you have bought it, which is the whole point "
                    "of having done it monthly."),
            severity="good", metric=_money(held),
            tab="piggy", action=f"Look at {bank['name']}",
            figures={"bank": bank["name"], "balance": held},
        ))
    return out


def no_emergency_fund(p: Profile) -> Observation | None:
    if not p.has_plan or p.fixed_total <= 0:
        return None
    target = round(p.fixed_total * EMERGENCY_MONTHS, 2)
    # Real money, not what a bank could advance: that is what an empty
    # month can actually be paid from.
    held = round(sum(max(b.get("held", 0), 0) for b in p.banks), 2)
    if held >= target:
        return None
    return Observation(
        id="no_emergency_fund",
        title=f"{_money(target)} would cover three months of commitments",
        detail=(f"Your fixed costs are {_money(p.fixed_total)} a month, so "
                f"that is what three months without income would need. The "
                f"piggy banks hold {_money(held)} between them. This is the "
                "one saving that is not about any particular purchase — it is "
                "what stops an unexpected month becoming debt — and it works "
                "the same way as the others: a monthly figure, taken out "
                "before the weekly number is worked out."),
        severity="watch", metric=_money(target), tab="piggy",
        action="Open a piggy bank",
        figures={"target": target, "held": held,
                 "fixed_monthly": p.fixed_total},
    )


def history_is_thin(p: Profile) -> Observation | None:
    if p.months_of_history >= THIN_HISTORY_MONTHS:
        return None
    return Observation(
        id="thin_history",
        title=f"{p.months_of_history or 'No'} month"
              f"{'' if p.months_of_history == 1 else 's'} of history so far",
        detail=("Most of what this app can tell you needs three months or "
                "more, because that is the point at which a habit can be told "
                "apart from a one-off. Until then the budget split is working "
                "from very little, and anything described as a trend should be "
                "read as a coincidence. Importing a longer date range is the "
                "fastest fix."),
        severity="watch", metric=str(p.months_of_history), tab="banks",
        action="Import more history",
        figures={"months": p.months_of_history},
    )


def savings_are_available(p: Profile) -> Observation | None:
    if p.findings_weighted_annual < 240:
        return None
    return Observation(
        id="findings_available",
        title=f"{_money(p.findings_weighted_annual)} a year of identified savings",
        detail=("Below this, each one names the charges it is based on and "
                "what it assumes. They are listed with the one-off actions "
                "first, because those take a single decision rather than "
                "sustained restraint and so are the ones that actually "
                "happen."),
        severity="watch", metric=_money(p.findings_weighted_annual),
        figures={"annual": p.findings_weighted_annual},
    )


RULES = (
    no_plan_yet,
    plan_is_too_tight,
    spending_over_the_plan,
    saving_nothing,
    budgets_not_adopted,
    uncategorised_is_large,
    commitments_are_heavy,
    saving_little,
    subscriptions_are_heavy,
    one_category_dominates,
    travel_has_no_bank,
    no_emergency_fund,
    history_is_thin,
    savings_are_available,
    a_bank_is_catching_up,
    a_bank_is_ready,
    living_under_the_plan,
    saving_well,
)

SEVERITY_ORDER = {"act": 0, "watch": 1, "good": 2}


def observe(profile: Profile, dismissed: set[str] | None = None) -> list[dict]:
    """Every observation that applies, the ones needing action first."""
    dismissed = dismissed or set()
    out: list[Observation] = []
    for rule in RULES:
        result = rule(profile)
        if result is None:
            continue
        out.extend(result if isinstance(result, list) else [result])

    return [o.to_dict() for o in
            sorted(out, key=lambda o: SEVERITY_ORDER.get(o.severity, 9))
            if o.id not in dismissed]


def _month_name(month: str) -> str:
    from datetime import date
    if not month:
        return ""
    return date(int(month[:4]), int(month[5:7]), 1).strftime("%B")
