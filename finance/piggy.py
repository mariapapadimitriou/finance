"""Piggy banks: the costs that aren't monthly, budgeted monthly anyway.

A monthly budget handles rent and groceries well and handles a holiday badly.
The holiday costs $3,000 once a year, so eleven months report a surplus that
isn't real and the twelfth reports a catastrophe that was entirely predictable.
The same is true of car maintenance, insurance paid annually, Christmas, a
dentist you see twice a year, and the flights for a wedding you agreed to
attend in April.

A piggy bank is the pot for that kind of spending — the big, planned, lumpy
kind that is not habit — kept apart from the weekly allowance, which is for the
habits. Each person's big spending is different, so each bank owns the
categories it pays for: travel for one person, concerts or a bike for another.
Spending in those categories goes to the bank automatically and never touches
the week.

  * **The money is there from day one.** A bank for $8,000 a year of travel
    holds $8,000 the day it opens, so the trip can be booked in March without
    waiting to save for it.
  * **Going in.** The first year, the target is paid in a twelfth at a time —
    $667 a month off the allowance. Every year after that, what goes in is
    what the bank actually paid out the year before: spend $6,000 and next
    year costs $500 a month; spend nothing and next year costs nothing,
    because the bank is still full. A bank only ever collects what it has
    spent, so it cannot hoard, and the deduction is fixed for the whole year,
    so a trip mid-year does not jolt this week's number.
  * **Coming out.** Spending charged to a bank leaves the month it fell in.
    June does not look like a disaster, because June was never asked to pay
    for the holiday.

Over time what goes into a bank is exactly what comes out of it, which is the
property every figure here is tested against. Nothing is stored: the figures
are worked out from the target and the charges on every request.

Two shapes of bank, because two shapes of cost:

  `annual`  A cost that recurs — travel, car maintenance, Christmas. Works in
            bank-years, twelve months from the month it opened, as above.
  `once`    A cost with a date — a wedding in April. The target is available
            from day one and paid in evenly until the date; anything spent
            beyond it is repaid over the twelve months after.

The distinction matters for the arithmetic and nowhere else; the UI calls them
"every year" and "by a date".
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date

ANNUAL = "annual"
ONCE = "once"
CADENCES = (ANNUAL, ONCE)

# A bank funded over more than ten years is not a plan, it is a rounding error
# with a name, and dividing by it produces a monthly figure of pennies.
MAX_MONTHS = 120

# How long a dated bank takes to repay spending beyond its target, after its
# date. A year, because the alternative is a single month absorbing the whole
# overspend — the problem piggy banks exist to solve. (An annual bank needs no
# such rule: next year's contributions are this year's spending.)
CATCH_UP_MONTHS = 12


@dataclass
class Bank:
    """A named pot with a target, a horizon, and money already in it."""

    id: int | None
    name: str
    target: float
    cadence: str = ANNUAL
    target_date: str | None = None
    start_month: str = ""
    opening: float = 0.0
    note: str = ""

    @property
    def is_dated(self) -> bool:
        return self.cadence == ONCE and bool(self.target_date)

    def to_dict(self, stats: dict | None = None) -> dict:
        d = {
            "id": self.id,
            "name": self.name,
            "target": round(self.target, 2),
            "cadence": self.cadence,
            "target_date": self.target_date,
            "start_month": self.start_month,
            "opening": round(self.opening, 2),
            "note": self.note,
        }
        if stats:
            d.update(stats)
        return d


# ── The arithmetic ───────────────────────────────────────────────────────────

def _month_index(month: str) -> int:
    """Months since year zero, so two months can be subtracted."""
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def months_between(start: str, end: str) -> int:
    """Whole calendar months from one to the other, both ends counted.

    January to January is one month, not zero: a bank started and spent in the
    same month still had that month to collect a contribution.
    """
    return _month_index(end) - _month_index(start) + 1


def funding_months(bank: Bank, today: str | None = None) -> int:
    """How many months the target is spread across.

    For an annual bank that is simply twelve, every year, forever. For a dated
    one it is the months from when you started to the month of the date — and
    never fewer than one, because a trip booked for next week still has to be
    paid for out of something.
    """
    if bank.cadence == ANNUAL or not bank.target_date:
        return 12
    start = bank.start_month or (today or _today())[:7]
    span = months_between(start, bank.target_date[:7])
    return max(min(span, MAX_MONTHS), 1)


def base_monthly(bank: Bank, today: str | None = None) -> float:
    """The first-year rate: the target spread over its months.

    After the first year an annual bank collects what it paid out the year
    before instead — see `status`.

    Money already in the bank reduces it: if the holiday costs $3,000 and
    $500 is already set aside, only $2,500 has to be collected. Saying
    otherwise would quietly ask for the $500 twice.
    """
    needed = max(bank.target - bank.opening, 0.0)
    return round(needed / funding_months(bank, today), 2)


def _add_months(month: str, n: int) -> str:
    total = _month_index(month) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def _year_of(bank: Bank, month: str) -> int:
    """Which bank-year a month falls in. Charges dated before the bank opened
    — "that holiday hurt, let me spread the next one" — count to its first."""
    start = bank.start_month or month
    return max((_month_index(month) - _month_index(start)) // 12, 0)


def _annual(bank: Bank, charges: dict[str, float], now: str) -> dict:
    start = bank.start_month or now
    year = _year_of(bank, now) if now >= start else 0
    spent = {}
    for month, amount in charges.items():
        k = _year_of(bank, month)
        spent[k] = round(spent.get(k, 0.0) + amount, 2)

    first_year = round(max(bank.target - bank.opening, 0.0) / 12, 2)

    def rate(k: int) -> float:
        # A year that took in more refunds than charges owes nothing back.
        return first_year if k == 0 else round(max(spent.get(k - 1, 0.0), 0.0) / 12, 2)

    # What has gone in so far: every finished year in full, and this year's
    # months up to and including this one. Nothing before the bank opened.
    paid_in = round(bank.opening, 2)
    if now >= start:
        for k in range(year):
            paid_in += (max(bank.target - bank.opening, 0.0) if k == 0
                        else max(spent.get(k - 1, 0.0), 0.0))
        paid_in += rate(year) * ((_month_index(now) - _month_index(start)) % 12 + 1)

    ceiling = max(bank.target, bank.opening) if year == 0 else bank.target
    year_start = _add_months(start, 12 * year)
    monthly = rate(year) if now >= start else 0.0
    return {
        "monthly": monthly,
        "base_monthly": first_year if year == 0 else round(bank.target / 12, 2),
        "available": round(ceiling - spent.get(year, 0.0), 2),
        "spent_this_year": spent.get(year, 0.0),
        "spent_last_year": spent.get(year - 1, 0.0) if year else None,
        "year": year,
        "year_start": year_start,
        "year_end": _add_months(year_start, 11),
        "paid_in": round(paid_in, 2),
        "basis": ("first_year" if year == 0
                  else "repaying" if spent.get(year - 1, 0.0) > 0
                  else "full"),
    }


def _dated(bank: Bank, charges: dict[str, float], now: str) -> dict:
    start = bank.start_month or now
    end = bank.target_date[:7]
    months = max(min(months_between(start, end), MAX_MONTHS), 1)
    rate = round(max(bank.target - bank.opening, 0.0) / months, 2)
    spent = round(sum(charges.values()), 2)
    ceiling = max(bank.target, bank.opening)

    # Anything spent beyond the target is repaid over the months after the
    # later of the date and the last charge.
    over = round(max(spent - ceiling, 0.0), 2)
    last = max([end, *charges]) if charges else end
    repay_from = _add_months(last, 1)

    def month_rate(month: str) -> float:
        if start <= month <= end:
            return rate
        if over and repay_from <= month < _add_months(repay_from, CATCH_UP_MONTHS):
            return round(over / CATCH_UP_MONTHS, 2)
        return 0.0

    paid_in = round(bank.opening, 2)
    if now >= start:
        for i in range(months_between(start, now)):
            paid_in += month_rate(_add_months(start, i))

    # Until the date the bank advances the whole target. After it there is no
    # more advance: what it can pay is what is really in it — a leftover, or
    # an overspend still being repaid.
    paid_in = round(paid_in, 2)
    available = (round(ceiling - spent, 2) if now <= end
                 else round(paid_in - spent, 2))
    return {
        "monthly": month_rate(now) if now >= start else 0.0,
        "base_monthly": rate,
        "available": available,
        "spent_this_year": spent,
        "spent_last_year": None,
        "year": 0,
        "year_start": start,
        "year_end": end,
        "paid_in": round(paid_in, 2),
        "basis": ("dated" if now <= end
                  else "repaying" if month_rate(now) > 0 else "done"),
    }


def status(bank: Bank, charges, today: str | None = None) -> dict:
    """One bank's full picture: what it can pay now, and what it costs a month.

    `charges` is either the per-month breakdown of everything taken out of the
    bank, or a single total for callers that do not have the breakdown — a
    total is treated as having been spent in the current month, which is right
    for the common case of asking what a charge made just now would do.
    """
    now = (today or _today())[:7]
    if not isinstance(charges, dict):
        charges = {now: float(charges or 0.0)}
    charges = {m[:7]: float(v) for m, v in charges.items() if v}

    played = (_dated(bank, charges, now) if bank.is_dated
              else _annual(bank, charges, now))
    available = played["available"]
    charged = round(sum(charges.values()), 2)
    over = available < 0

    return {
        **played,
        # The extra above the first-year rate this month — repaying a year
        # that spent more than its target.
        "catch_up": round(max(played["monthly"] - played["base_monthly"], 0.0), 2),
        "charged": charged,
        "accrued": played["paid_in"],
        # Real money in the bank: paid in, less paid out. Negative is the bank
        # having advanced the money, which is what lets the trip happen first.
        "held": round(played["paid_in"] - charged, 2),
        # What the bank can pay now. Kept under its old name too, since every
        # caller that offers "cover it from a bank" wants exactly this.
        "balance": available,
        "funding_months": funding_months(bank, today),
        "funded_share": (round(min(max(available, 0.0) / bank.target, 1.0), 4)
                         if bank.target > 0 else 0.0),
        "funded_on": bank.target_date if bank.is_dated else None,
        "complete": bool(bank.is_dated and now > bank.target_date[:7]),
        # Over this year's budget: allowed — sometimes the trip costs what it
        # costs — and repaid by next year's contributions.
        "over": over,
        "behind": over,
        "behind_by": round(-available, 2) if over else 0.0,
        "caught_up_by": (played["year_end"] if played["monthly"] > played["base_monthly"]
                         else _add_months(played["year_end"], 12) if over
                         and not bank.is_dated else None),
    }


def total_monthly(banks: list[Bank], charges: dict[int, dict] | None = None,
                  today: str | None = None) -> float:
    """What every bank together takes out of this month, for the Plan."""
    charges = charges or {}
    return round(sum(status(b, charges.get(b.id, {}), today)["monthly"]
                     for b in banks), 2)


def _today() -> str:
    return date.today().isoformat()


# ── Validation ───────────────────────────────────────────────────────────────

def validate(name: str, target: float, cadence: str,
             target_date: str | None, today: str | None = None) -> str | None:
    """Return an error message, or None when the bank is usable."""
    if not (name or "").strip():
        return "Give the piggy bank a name."
    try:
        amount = float(target)
    except (TypeError, ValueError):
        return "The target must be a number."
    if amount <= 0:
        return "A piggy bank needs a target above zero."
    if amount > 10_000_000:
        return "That target is implausibly large."
    if cadence not in CADENCES:
        return "Choose either a yearly amount or a target date."

    if cadence == ONCE:
        if not target_date:
            return "Give the date you need the money by."
        try:
            when = date.fromisoformat(target_date)
        except (ValueError, TypeError):
            return "The date must be YYYY-MM-DD."
        now = date.fromisoformat(today or _today())
        if when < now.replace(day=1):
            return ("That date has already passed. Use a yearly amount for "
                    "something that recurs, or pick the next one.")
        if months_between(now.isoformat()[:7], target_date[:7]) > MAX_MONTHS:
            return "That is more than ten years out — pick something nearer."
    return None
