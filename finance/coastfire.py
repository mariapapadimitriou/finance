"""CoastFIRE: when saving for retirement could stop.

The question: how much do you need invested *now* so that, without adding
another dollar, it grows into enough to retire on by your retirement age?
Once you have that, you are "coasting": work only has to pay for today, and
anything more you save makes retirement earlier rather than possible.

Three figures carry it:

* **The FIRE number** — what the portfolio must hold to pay for a year of
  retirement indefinitely: the spending it has to cover (after any pension)
  divided by a safe withdrawal rate. At 4%, $60,000 a year needs $1.5M.
* **The coast number** — the FIRE number discounted back to today at the
  expected return: what grows into it by your retirement age untouched.
* **The coast age** — when your investments, with the contributions you are
  making, first reach the coast number as it stands at that age.

Everything is in today's dollars, so the return is the real one — after
inflation. That is what keeps "$60,000 a year" meaning what it means now,
thirty years before it is spent, and it is why the default return is lower
than the figures quoted for markets.

Nothing here reads the ledger or changes the plan. It is arithmetic on what
you typed, with defaults taken from the plan where it has an opinion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# The returns offered side by side, after inflation.
RATES = (0.04, 0.05, 0.06, 0.07)

# The horizon for "what would it take to coast", in years.
COAST_IN_YEARS = 10

# How far past the retirement age to look for the full-FIRE date before
# saying it never arrives.
MAX_AGE = 100


def _index(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _month(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def add_months(month: str, n: int) -> str:
    return _month(_index(month) + n)


@dataclass
class Inputs:
    born: str                       # YYYY-MM, so the age moves on by itself
    retire_age: float
    invested: float                 # for retirement, as of `as_of`
    as_of: str                      # YYYY-MM the invested figure was true
    spending: float                 # a year in retirement, today's dollars
    pension: float = 0.0            # CPP, OAS, a work pension: a year
    withdrawal: float = 4.0         # percent of the portfolio a year
    real_return: float = 5.0        # percent a year, after inflation
    monthly: float = 0.0            # contributed every month until you stop

    def to_dict(self) -> dict:
        return {"born": self.born, "retire_age": self.retire_age,
                "invested": round(self.invested, 2), "as_of": self.as_of,
                "spending": round(self.spending, 2),
                "pension": round(self.pension, 2),
                "withdrawal": self.withdrawal, "real_return": self.real_return,
                "monthly": round(self.monthly, 2)}

    @classmethod
    def from_dict(cls, d: dict) -> "Inputs":
        return cls(born=str(d["born"])[:7], retire_age=float(d["retire_age"]),
                   invested=float(d["invested"]), as_of=str(d["as_of"])[:7],
                   spending=float(d["spending"]),
                   pension=float(d.get("pension") or 0),
                   withdrawal=float(d.get("withdrawal") or 4),
                   real_return=float(d.get("real_return", 5)),
                   monthly=float(d.get("monthly") or 0))


def age_at(born: str, month: str) -> float:
    return (_index(month) - _index(born)) / 12


def fire_number(spending: float, pension: float, withdrawal: float) -> float:
    """What the portfolio must hold to pay for retirement indefinitely."""
    return max(spending - pension, 0.0) / (withdrawal / 100)


def _monthly_rate(annual: float) -> float:
    # Effective: twelve of these compound to exactly `annual` over a year.
    return (1 + annual) ** (1 / 12) - 1


def _first_month(invested: float, monthly: float, m: float, horizon: int,
                 target) -> int | None:
    """The first month from now (0 = now) the portfolio meets `target(t)`."""
    value = invested
    for t in range(0, horizon + 1):
        if t:
            value = value * (1 + m) + monthly
        if value >= target(t) - 0.005:
            return t
    return None


def _at(inp: Inputs, annual: float, today: str) -> dict:
    """The coast and FIRE dates at one return."""
    m = _monthly_rate(annual)
    age_now = age_at(inp.born, today)
    n = max(round((inp.retire_age - age_now) * 12), 0)
    fire = fire_number(inp.spending, inp.pension, inp.withdrawal)
    growth = lambda months: (1 + m) ** months            # noqa: E731

    coast_now = fire / growth(n)
    coast_t = _first_month(inp.invested, inp.monthly, m, n,
                           lambda t: fire / growth(n - t))
    fire_t = _first_month(inp.invested, inp.monthly, m,
                          max(round((MAX_AGE - age_now) * 12), n),
                          lambda t: fire)
    return {
        "rate": annual,
        "coast_number": round(coast_now, 2),
        "coast_month": coast_t,
        "coast_age": round(age_now + coast_t / 12, 2) if coast_t is not None else None,
        "fire_month": fire_t,
        "fire_age": round(age_now + fire_t / 12, 2) if fire_t is not None else None,
    }


def compute(inp: Inputs, today: str) -> dict:
    today = today[:7]
    r = inp.real_return / 100
    m = _monthly_rate(r)
    age_now = age_at(inp.born, today)
    n = max(round((inp.retire_age - age_now) * 12), 0)
    fire = fire_number(inp.spending, inp.pension, inp.withdrawal)
    main = _at(inp, r, today)
    coast = main["coast_number"]
    coasting = inp.invested >= coast - 0.005

    # The year-by-year picture: what is needed to coast at each point, which
    # rises to the FIRE number at retirement, against the investments with
    # the contributions continuing. Where they cross is the coast age.
    series = []
    value = inp.invested
    for t in range(0, n + 1):
        if t:
            value = value * (1 + m) + inp.monthly
        if t % 12 == 0 or t == n:
            series.append({"age": round(age_now + t / 12, 2),
                           "month": add_months(today, t),
                           "needed": round(fire / (1 + m) ** (n - t), 2),
                           "invested": round(value, 2)})
    at_retirement = value

    # Already coasting: what the portfolio does left alone, and the earliest
    # age it reaches the FIRE number by itself.
    untouched = inp.invested * (1 + m) ** n
    early = None
    if coasting and inp.invested > 0:
        if inp.invested >= fire:
            early = age_now
        elif m > 0:
            early = age_now + math.log(fire / inp.invested) / math.log(1 + m) / 12

    # What it would take: the monthly contribution that reaches the coast
    # number in ten years, and the one that reaches the FIRE number by the
    # retirement age. The future value of a level monthly contribution is
    # c·(g^T − 1)/m, so each is one line of algebra.
    def needed(months: int, target: float) -> float | None:
        if months <= 0:
            return None
        g = (1 + m) ** months
        short = target - inp.invested * g
        if short <= 0:
            return 0.0
        # Up to the cent, so paying exactly this does arrive on time.
        return math.ceil(round((short * m / (g - 1) if m > 0 else short / months)
                               * 100, 6)) / 100

    soon = min(COAST_IN_YEARS * 12, n)
    return {
        "age_now": round(age_now, 2),
        "age": int(math.floor(age_now + 1e-9)),
        "retire_age": inp.retire_age,
        "months_to_retire": n,
        "retire_month": add_months(today, n),
        "spending": round(inp.spending, 2),
        "pension": round(inp.pension, 2),
        "from_portfolio": round(max(inp.spending - inp.pension, 0.0), 2),
        "withdrawal": inp.withdrawal,
        "real_return": inp.real_return,
        "monthly": round(inp.monthly, 2),
        "fire_number": round(fire, 2),
        "coast_number": coast,
        "invested": round(inp.invested, 2),
        "as_of": inp.as_of,
        "progress": round(min(inp.invested / coast, 1.0), 4) if coast > 0 else 1.0,
        "coasting": coasting,
        "gap": round(max(coast - inp.invested, 0.0), 2),
        "coast_month": (add_months(today, main["coast_month"])
                        if main["coast_month"] is not None else None),
        "coast_age": main["coast_age"],
        "contributed_to_coast": (round(inp.monthly * main["coast_month"], 2)
                                 if main["coast_month"] is not None else None),
        "fire_month": (add_months(today, main["fire_month"])
                       if main["fire_month"] is not None else None),
        "fire_age": main["fire_age"],
        "at_retirement": round(at_retirement, 2),
        "untouched_at_retirement": round(untouched, 2),
        "early_retire_age": round(early, 2) if early is not None else None,
        "series": series,
        "rates": [_at(inp, rate, today) for rate in RATES],
        "needed_monthly": {
            "coast_years": round(soon / 12, 2),
            "to_coast": needed(soon, fire / (1 + m) ** (n - soon)),
            "to_fire_by_retirement": needed(n, fire),
        },
    }


def validate(d: dict, today: str) -> tuple[Inputs | None, str | None]:
    """Clean what was submitted, or say what is wrong with it."""
    today = today[:7]
    try:
        age = float(d.get("age"))
        retire_age = float(d.get("retire_age", 65))
        invested = float(d.get("invested") or 0)
        spending = float(d.get("spending"))
        pension = float(d.get("pension") or 0)
        withdrawal = float(d.get("withdrawal") or 4)
        real_return = float(d.get("real_return", 5))
        monthly = float(d.get("monthly") or 0)
    except (TypeError, ValueError):
        return None, "Every field has to be a number."
    values = (age, retire_age, invested, spending, pension, withdrawal,
              real_return, monthly)
    if not all(math.isfinite(v) for v in values):
        return None, "Every field has to be a number."
    if age < 16 or age > 90:
        return None, "Your age has to be between 16 and 90."
    if retire_age <= age or retire_age > MAX_AGE:
        return None, f"Retirement age has to be after your age, and at most {MAX_AGE}."
    if invested < 0 or monthly < 0:
        return None, "Amounts can't be negative."
    if spending <= 0:
        return None, "Enter what a year of retirement would cost."
    if pension < 0 or pension >= spending:
        return None, ("A pension covering all of it needs no portfolio — enter "
                      "less than the spending, or 0.")
    if withdrawal < 2 or withdrawal > 10:
        return None, "The withdrawal rate has to be between 2% and 10%."
    if real_return < 0 or real_return > 15:
        return None, "The return has to be between 0% and 15%."
    born = add_months(today, -round(age * 12))
    return Inputs(born=born, retire_age=retire_age, invested=round(invested, 2),
                  as_of=today, spending=round(spending, 2),
                  pension=round(pension, 2), withdrawal=withdrawal,
                  real_return=real_return, monthly=round(monthly, 2)), None
