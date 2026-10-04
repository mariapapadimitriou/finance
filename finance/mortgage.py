"""A mortgage: what it costs a month, when it ends, and how much is interest.

Everything here is arithmetic on what you typed — balance owing, rate, years
left, how often you pay — and nothing is read from the ledger. A mortgage is
usually paid from a chequing account this app never sees, so the figures have
to be declared, like rent.

Two conventions, because the lenders differ:

* **Canadian.** A fixed-rate mortgage is quoted with semi-annual compounding,
  by law (the Interest Act). A quoted 5% is an effective 5.0625% a year, a
  little less than the 5.116% monthly compounding would give, so a Canadian
  payment is slightly smaller than an American calculator says.
* **Monthly.** The US convention: the quoted rate divided by twelve.

The rate per payment is taken from the effective annual rate, so a weekly
payment and a monthly one cost the same over a year at the same rate — which
is the honest comparison when the only thing that changes is how often.

The rate is assumed to hold for the whole amortization. It will not: the term
ends, the mortgage renews, and the rate moves. The page says so, and shows the
balance at renewal, which is the figure the next rate will apply to.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

# How often you pay → (payments a year, accelerated?).
#
# "Accelerated" is a Canadian product with a misleading name: it is the
# monthly payment divided by two (or four), paid 26 (or 52) times a year. That
# comes to thirteen monthly payments a year instead of twelve, and the
# thirteenth goes entirely to principal — which is why it pays off years
# sooner. An ordinary bi-weekly payment is simply the same mortgage spread
# thinner and saves almost nothing.
FREQUENCIES = {
    "monthly": (12, False),
    "biweekly": (26, False),
    "accelerated_biweekly": (26, True),
    "weekly": (52, False),
    "accelerated_weekly": (52, True),
}
COMPOUNDING = ("canadian", "monthly")

# The amortizations offered side by side, so "how long could I pay it off in"
# has an answer for each length a lender would actually write.
ALTERNATIVES = (15, 20, 25, 30)

MAX_YEARS = 40
MAX_RATE = 25.0


@dataclass
class Terms:
    balance: float                  # owing as of `as_of`
    rate: float                     # annual, in percent: 5 means 5%
    years: float                    # left to pay, as of `as_of`
    as_of: str                      # YYYY-MM the balance was true in
    frequency: str = "monthly"
    compounding: str = "canadian"
    extra_monthly: float = 0.0      # paid on top, every month
    term_end: str | None = None     # YYYY-MM the term ends and it renews

    def to_dict(self) -> dict:
        return {"balance": round(self.balance, 2), "rate": self.rate,
                "years": self.years, "as_of": self.as_of,
                "frequency": self.frequency, "compounding": self.compounding,
                "extra_monthly": round(self.extra_monthly, 2),
                "term_end": self.term_end}

    @classmethod
    def from_dict(cls, d: dict) -> "Terms":
        return cls(balance=float(d["balance"]), rate=float(d["rate"]),
                   years=float(d["years"]), as_of=str(d["as_of"])[:7],
                   frequency=d.get("frequency") or "monthly",
                   compounding=d.get("compounding") or "canadian",
                   extra_monthly=float(d.get("extra_monthly") or 0.0),
                   term_end=(str(d["term_end"])[:7] if d.get("term_end") else None))


# ── Months ───────────────────────────────────────────────────────────────────

def _index(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def _month(index: int) -> str:
    return f"{index // 12:04d}-{index % 12 + 1:02d}"


def add_months(month: str, n: int) -> str:
    return _month(_index(month) + n)


# ── The arithmetic ───────────────────────────────────────────────────────────

def effective_annual(rate: float, compounding: str) -> float:
    """The rate actually charged over a year, as a fraction."""
    r = rate / 100
    if compounding == "canadian":
        return (1 + r / 2) ** 2 - 1
    return (1 + r / 12) ** 12 - 1


def periodic_rate(rate: float, compounding: str, per_year: int) -> float:
    return (1 + effective_annual(rate, compounding)) ** (1 / per_year) - 1


def annuity(balance: float, rate_per: float, payments: int) -> float:
    """The level payment that clears `balance` in `payments` payments."""
    if payments <= 0:
        return round(balance, 2)
    if rate_per == 0:
        return balance / payments
    return balance * rate_per / (1 - (1 + rate_per) ** -payments)


def payment(balance: float, rate: float, years: float, frequency: str,
            compounding: str) -> float:
    """The regular payment, rounded up to the cent.

    Up, not to the nearest: rounded down, the last payment leaves a few
    dollars owing and the mortgage runs a month past its amortization.
    """
    per_year, accelerated = FREQUENCIES[frequency]
    if accelerated:
        # The monthly payment split into halves (26 a year) or quarters (52):
        # thirteen monthly payments' worth a year.
        monthly = annuity(balance, periodic_rate(rate, compounding, 12),
                          max(round(years * 12), 1))
        return _cents_up(monthly / (per_year / 13))
    return _cents_up(annuity(balance, periodic_rate(rate, compounding, per_year),
                             max(round(years * per_year), 1)))


def _cents_up(x: float) -> float:
    # The small allowance keeps float noise from adding a cent to a payment
    # that is already exact.
    return math.ceil(round(x * 100, 6)) / 100


def _offset(k: int, per_year: int) -> int:
    """Months after `as_of` that payment k (from 1) falls in."""
    return math.ceil(k * 12 / per_year - 1e-9)


def schedule(t: Terms) -> list[dict]:
    """Every payment until the balance is gone.

    The extra is a monthly figure spread across the payments in a month, so
    "$200 extra a month" means the same thing however often you pay.
    """
    per_year, _ = FREQUENCIES[t.frequency]
    i = periodic_rate(t.rate, t.compounding, per_year)
    regular = payment(t.balance, t.rate, t.years, t.frequency, t.compounding)
    extra = max(t.extra_monthly, 0.0) * 12 / per_year
    balance = t.balance
    rows = []
    k = 0
    # A ceiling that no real mortgage reaches, in case a payment could ever
    # fail to cover its interest.
    while balance > 0.005 and k < 100 * per_year:
        k += 1
        interest = balance * i
        principal = min(regular + extra - interest, balance)
        if principal <= 0:
            break
        balance -= principal
        rows.append({"k": k, "offset": _offset(k, per_year),
                     "interest": interest, "principal": principal,
                     "balance": max(balance, 0.0)})
    return rows


def _months_between(start: str, end: str) -> int:
    return _index(end) - _index(start)


def _sum(rows, key) -> float:
    return round(sum(r[key] for r in rows), 2)


def _ahead(t: Terms, today: str) -> tuple[list[dict], float]:
    """The payments still to come, and the balance owing now."""
    rows = schedule(t)
    now = max(_months_between(t.as_of, today), 0)
    past = [r for r in rows if r["offset"] <= now]
    balance_now = past[-1]["balance"] if past else t.balance
    return [r for r in rows if r["offset"] > now], round(balance_now, 2)


def _payoff(t: Terms, ahead: list[dict], today: str) -> dict:
    per_year, _ = FREQUENCIES[t.frequency]
    if not ahead:
        return {"payoff_month": today, "months_left": 0, "years_left": 0.0}
    last = ahead[-1]
    return {"payoff_month": add_months(t.as_of, last["offset"]),
            "months_left": max(last["offset"]
                               - max(_months_between(t.as_of, today), 0), 0),
            "years_left": round(len(ahead) / per_year, 2)}


def compute(t: Terms, today: str) -> dict:
    """The whole picture, from this month on.

    Totals are what is still to be paid — the balance owing now and the
    interest on it — because the payments already made are spent and no
    choice on this page changes them.
    """
    today = today[:7]
    per_year, accelerated = FREQUENCIES[t.frequency]
    regular = payment(t.balance, t.rate, t.years, t.frequency, t.compounding)
    monthly_equivalent = round(regular * per_year / 12, 2)
    ahead, balance_now = _ahead(t, today)
    now = max(_months_between(t.as_of, today), 0)

    interest = _sum(ahead, "interest")
    principal = round(balance_now, 2)
    paid = round(interest + principal, 2)

    by_year = []
    for y in range(0, math.ceil(len(ahead) / per_year) if ahead else 0):
        rows = ahead[y * per_year:(y + 1) * per_year]
        by_year.append({
            "year": y + 1,
            "ending": add_months(t.as_of, rows[-1]["offset"]),
            "interest": _sum(rows, "interest"),
            "principal": _sum(rows, "principal"),
            "balance": round(rows[-1]["balance"], 2),
        })

    # The next month with a payment in it, split the way the lender splits it.
    upcoming = ahead[0]["offset"] if ahead else None
    first = [r for r in ahead if r["offset"] == upcoming]

    renewal = None
    if t.term_end and _index(t.term_end) > _index(today):
        end = _months_between(t.as_of, t.term_end)
        until = [r for r in ahead if r["offset"] <= end]
        renewal = {
            "month": t.term_end,
            "balance": round(until[-1]["balance"], 2) if until else balance_now,
            "interest": _sum(until, "interest"),
            "principal": _sum(until, "principal"),
        }

    result = {
        "payment": regular,
        "frequency": t.frequency,
        "payments_per_year": per_year,
        "accelerated": accelerated,
        "compounding": t.compounding,
        "effective_annual_rate": round(effective_annual(t.rate, t.compounding) * 100, 4),
        "monthly_equivalent": monthly_equivalent,
        "extra_monthly": round(max(t.extra_monthly, 0.0), 2),
        # The one figure the plan subtracts, like rent.
        "committed_monthly": round(monthly_equivalent + max(t.extra_monthly, 0.0), 2),
        "balance_now": balance_now,
        "as_of": t.as_of,
        **_payoff(t, ahead, today),
        "total_paid": paid,
        "total_interest": interest,
        "total_principal": principal,
        "interest_share": round(interest / paid, 4) if paid > 0 else 0.0,
        "next_month": {
            "month": add_months(t.as_of, upcoming) if first else None,
            "interest": _sum(first, "interest"),
            "principal": _sum(first, "principal"),
        },
        "by_year": by_year,
        "renewal": renewal,
    }

    # The same mortgage without the extra, which is what the extra is worth.
    if t.extra_monthly > 0:
        plain = Terms(**{**t.__dict__, "extra_monthly": 0.0})
        plain_ahead, _ = _ahead(plain, today)
        base = _payoff(plain, plain_ahead, today)
        result["without_extra"] = {**base,
                                   "total_interest": _sum(plain_ahead, "interest")}
        result["saves"] = {
            "months": max(base["months_left"] - result["months_left"], 0),
            "interest": round(result["without_extra"]["total_interest"] - interest, 2),
        }
    else:
        result["without_extra"] = None
        result["saves"] = None

    # The balance owing now over each common amortization, at this rate and
    # frequency, without the extra: the payment each needs and what it costs.
    alternatives = []
    for years in sorted(set(ALTERNATIVES)):
        if balance_now <= 0:
            break
        alt = Terms(balance=balance_now, rate=t.rate, years=years, as_of=today,
                    frequency=t.frequency, compounding=t.compounding)
        alt_rows = schedule(alt)
        pay = payment(balance_now, t.rate, years, t.frequency, t.compounding)
        alternatives.append({
            "years": years,
            "payment": pay,
            "monthly_equivalent": round(pay * per_year / 12, 2),
            "total_interest": _sum(alt_rows, "interest"),
        })
    result["alternatives"] = alternatives
    return result


def validate(d: dict, today: str) -> tuple[Terms | None, str | None]:
    """Clean a submitted mortgage, or say what is wrong with it."""
    try:
        balance = float(d.get("balance"))
        rate = float(d.get("rate"))
        years = float(d.get("years"))
        extra = float(d.get("extra_monthly") or 0)
    except (TypeError, ValueError):
        return None, "Balance, rate, years and extra must be numbers."
    if not math.isfinite(balance) or balance <= 0:
        return None, "Enter the balance you still owe."
    if not math.isfinite(rate) or rate < 0 or rate > MAX_RATE:
        return None, f"The rate has to be between 0% and {MAX_RATE:g}%."
    if not math.isfinite(years) or years < 1 or years > MAX_YEARS:
        return None, f"Years left to pay has to be between 1 and {MAX_YEARS}."
    if not math.isfinite(extra) or extra < 0:
        return None, "The extra each month can't be negative."
    frequency = d.get("frequency") or "monthly"
    if frequency not in FREQUENCIES:
        return None, "Choose how often you pay."
    compounding = d.get("compounding") or "canadian"
    if compounding not in COMPOUNDING:
        return None, "Choose Canadian or monthly compounding."
    term_end = d.get("term_end") or None
    if term_end:
        term_end = str(term_end)[:7]
        if len(term_end) != 7 or term_end[4] != "-":
            return None, "The term end has to be a month, like 2029-06."
        if term_end <= today[:7]:
            return None, "The term end has to be in the future."
    return Terms(balance=round(balance, 2), rate=rate, years=years,
                 as_of=today[:7], frequency=frequency, compounding=compounding,
                 extra_monthly=round(extra, 2), term_end=term_end), None
