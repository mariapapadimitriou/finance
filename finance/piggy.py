"""Piggy banks: the costs that aren't monthly, budgeted monthly anyway.

A monthly budget handles rent and groceries well and handles a holiday badly.
The holiday costs $3,000 once a year, so eleven months report a surplus that
isn't real and the twelfth reports a catastrophe that was entirely predictable.
The same is true of car maintenance, insurance paid annually, Christmas, a
dentist you see twice a year, and the flights for a wedding you agreed to
attend in April.

A piggy bank fixes both halves of that at once:

  * **Going in.** The target is divided by the months available and that
    share is subtracted from every month's budget, exactly like rent. A
    holiday you will take in June is a bill you are already paying.
  * **Coming out.** Spending allocated to a bank is drawn from the bank
    instead of counting against the month it fell in. June does not look like
    a disaster, because June was never asked to pay for the holiday.

Those two together are the whole idea. Everything below is arithmetic in
service of it, and all of it is derived rather than typed: the monthly figure
comes from the target and the horizon, and the balance comes from how many
months have passed and what has been charged to the bank. Nobody has to keep a
separate number up to date, which is the only way a number like this stays
true.

Two shapes of bank, because two shapes of cost:

  `annual`  A cost that recurs forever — car maintenance, insurance,
            Christmas. Contributions never stop, and spending draws the
            balance down and leaves it to refill. Monthly = target ÷ 12.
  `once`    A cost with a date — a trip in June, a wedding in April.
            Contributions run from when you started until the month of the
            date and then stop. Monthly = what is still needed ÷ months left.

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


def monthly(bank: Bank, today: str | None = None) -> float:
    """What this bank takes out of every month's budget.

    Money already in the bank reduces it: if the holiday costs $3,000 and
    $500 is already set aside, only $2,500 has to be collected. Saying
    otherwise would quietly ask for the $500 twice.
    """
    needed = max(bank.target - bank.opening, 0.0)
    return round(needed / funding_months(bank, today), 2)


def accrued(bank: Bank, today: str | None = None) -> float:
    """What should be in the bank by now, if every month paid in.

    Derived from the calendar rather than stored, so it cannot drift from the
    contributions the Plan has actually been subtracting. A dated bank stops
    collecting once its date passes; an annual one never does.
    """
    now = today or _today()
    start = bank.start_month or now[:7]
    if now[:7] < start:
        return round(bank.opening, 2)

    elapsed = months_between(start, now[:7])
    if bank.is_dated:
        elapsed = min(elapsed, funding_months(bank, today))
    return round(bank.opening + monthly(bank, today) * elapsed, 2)


def status(bank: Bank, charged: float, today: str | None = None) -> dict:
    """One bank's full picture: what went in, what came out, what is left.

    `charged` is everything taken out of it — spending allocated to the bank
    plus anything drawn to cover a month — because a pot does not care which
    gesture emptied it.
    """
    now = today or _today()
    per_month = monthly(bank, today)
    in_so_far = accrued(bank, today)
    balance = round(in_so_far - charged, 2)
    months = funding_months(bank, today)

    start = bank.start_month or now[:7]
    paid_months = max(months_between(start, now[:7]), 0) if now[:7] >= start else 0
    if bank.is_dated:
        remaining_months = max(months - paid_months, 0)
        funded_on = bank.target_date
    else:
        remaining_months = None
        funded_on = None

    return {
        "monthly": per_month,
        "accrued": in_so_far,
        "charged": round(charged, 2),
        "balance": balance,
        "funding_months": months,
        "months_paid": paid_months,
        "months_left": remaining_months,
        "funded_on": funded_on,
        "funded_share": round(min(in_so_far / bank.target, 1.0), 4) if bank.target > 0 else 0.0,
        "complete": bool(bank.is_dated and remaining_months == 0),
        # Spending ahead of the bank is not an error — you may have to fly
        # before you have finished saving for the flight — but it is the one
        # thing about a bank worth surfacing, because the overdraft comes out
        # of the month after all.
        "overdrawn": balance < 0,
        "overdrawn_by": round(-balance, 2) if balance < 0 else 0.0,
    }


def total_monthly(banks: list[Bank], today: str | None = None) -> float:
    """What every bank together takes out of a month, for the Plan's arithmetic."""
    return round(sum(monthly(b, today) for b in banks), 2)


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
