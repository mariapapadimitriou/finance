"""Growth › Insights: the month in pictures (Pearl THL-186 GR-24 to GR-27,
THL-196 GR-28 to GR-32).

One payload per month holds everything the page and its detail views draw,
so a screen never works out a total itself:

* **Tiles** (GR-28): income that arrived, Essentials and Lifestyle so far,
  and what was set aside in the Anchor and chests.
* **Vs usual** (GR-24, GR-26): each group and category against her usual
  month (`usual_month`, unusual months left out, THL-59) and where she
  usually is by today.
* **Trend** (GR-29, THL-188): twelve months of Essentials and Lifestyle, and
  her usual month as a band from its quietest to its busiest month.
* **Where it went** (GR-30, THL-189): every category of a month, grouped,
  with the purchases Pearl isn't sure about counted (`is_unsure`).
* **Money in and out** (GR-31, THL-190): income, spending and set aside each
  month, and what she kept once a month has ended.
* **Savings** (GR-32, THL-193): the Anchor and each treasure chest at the end
  of every month, and the months a chest paid for something.
* **Review a month** (GR-25, THL-81): where the income went, as one bar.
* **Subscriptions** (GR-27, THL-63): each one by the year, with her Keep or
  Review (a reminder next month, nothing more).

Every gate is the one the rest of the app uses: `counts_as_spending` and
`spend_amount` for spending (so excluded accounts, joint shares, splits and
chest-paid charges all count the way they do on Home), `invested_in` for
what was saved. A one-off (THL-71) counts in its own month's bars and totals
but not in anything averaged: the usual band, or where she usually is by today. Money is integer cents throughout and rounded once, here.
"""

from __future__ import annotations

import calendar
from collections import defaultdict
from datetime import date

from . import piggy
from .analytics import counts_as_spending, invested_in, is_others, spend_amount
from .balances import balance_on
from .categorize import group_of, is_unsure
from .models import Transaction

GROUPS = ("essentials", "lifestyle")
GROUP_LABELS = {"essentials": "Essentials", "lifestyle": "Lifestyle"}
SPAN = 12                 # months of trend, money in/out and savings
HISTORY = 6               # months of bars per category (GR-26)
PACE_BAND = 0.10          # the snapshot's ±10% (THL-110 V-03)
SAME_BAND = 0.05          # "Same as usual" in GR-25's words column


def cents(x: float | None) -> int:
    return int(round((x or 0.0) * 100))


def _idx(month: str) -> int:
    return int(month[:4]) * 12 + int(month[5:7]) - 1


def add_months(month: str, n: int) -> str:
    total = _idx(month) + n
    return f"{total // 12:04d}-{total % 12 + 1:02d}"


def days_in(month: str) -> int:
    return calendar.monthrange(int(month[:4]), int(month[5:7]))[1]


def month_end(month: str) -> date:
    return date(int(month[:4]), int(month[5:7]), days_in(month))


def window(end: str, n: int) -> list[str]:
    """`n` months ending at `end`, oldest first."""
    return [add_months(end, i - n + 1) for i in range(n)]


def first_month(transactions: list[Transaction]) -> str | None:
    """The first month the ledger covers from its first day, or the month it
    starts in when that is all there is (a part month draws low otherwise)."""
    if not transactions:
        return None
    first = min(t.date for t in transactions)
    return first[:7] if first[8:10] == "01" else add_months(first[:7], 1)


def is_income(t: Transaction) -> bool:
    """Money that arrived as income: never a friend paying back, a row left
    out, or another member's money on a joint account."""
    return ((t.category or "") == "Income" and t.amount < 0 and not t.repays
            and not is_others(t))


# ── One pass over the ledger ──────────────────────────────────────────────

class Ledger:
    """Per-month aggregates, in cents, from one pass."""

    def __init__(self, transactions: list[Transaction], confirmed: dict[str, str] | None = None):
        self.transactions = transactions
        confirmed = confirmed or {}
        self.income: dict[str, int] = defaultdict(int)
        self.arrived: dict[str, list[str]] = defaultdict(list)
        self.group: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.category: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # Spending by category and day, for "by today" (GR-26).
        self.daily: dict[str, dict[str, list[int]]] = defaultdict(dict)
        self.unsure: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        # The same, one-offs left out (THL-71): what an average is made of.
        self.usual_group: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
        self.usual_daily: dict[str, dict[str, list[int]]] = defaultdict(dict)
        self.months: set[str] = set()
        for t in transactions:
            self.months.add(t.month)
            if is_income(t):
                self.income[t.month] += cents(-t.amount)
                self.arrived[t.month].append(t.date[:10])
                continue
            if not counts_as_spending(t):
                continue
            cat = t.category or "Other"
            c = cents(spend_amount(t))
            self.group[t.month][group_of(cat)] += c
            self.category[t.month][cat] += c
            days = self.daily[t.month].setdefault(cat, [0] * 32)
            days[int(t.date[8:10])] += c
            if not t.one_off:
                self.usual_group[t.month][group_of(cat)] += c
                days = self.usual_daily[t.month].setdefault(cat, [0] * 32)
                days[int(t.date[8:10])] += c
            if (t.amount > 0 and t.category_source != "user" and is_unsure(t)
                    and confirmed.get(t.fingerprint) != cat):
                self.unsure[t.month][cat] += 1

    def spent(self, month: str) -> int:
        return sum(self.group[month].get(g, 0) for g in GROUPS)

    def by_day(self, month: str, category: str, day: int) -> int:
        days = self.daily.get(month, {}).get(category)
        return sum(days[1:day + 1]) if days else 0

    def usual_spent(self, month: str) -> int:
        """What a month spent, one-offs left out: how it counts in an average."""
        return sum(self.usual_group[month].get(g, 0) for g in GROUPS)

    def usual_by_day(self, month: str, category: str, day: int) -> int:
        days = self.usual_daily.get(month, {}).get(category)
        return sum(days[1:day + 1]) if days else 0


# ── Set aside: the Anchor's saves and the chests' monthly amounts ─────────

def chest_monthly(banks: list[piggy.Bank], charges: dict[int, dict], month: str) -> int:
    """What the chests took out of a month: each one's monthly amount."""
    total = 0
    for b in banks:
        if b.start_month and month < b.start_month:
            continue
        upto = {m: v for m, v in charges.get(b.id, {}).items() if m <= month}
        total += cents(piggy.status(b, upto, today=f"{month}-01")["monthly"])
    return total


def set_aside(transactions, banks, charges, month: str) -> int:
    return cents(invested_in(transactions, month)) + chest_monthly(banks, charges, month)


def chest_held(bank: piggy.Bank, charges: dict, month: str) -> int:
    """What a chest held at the end of a month (never below nothing)."""
    if bank.start_month and month < bank.start_month:
        return 0
    upto = {m: v for m, v in charges.items() if m <= month}
    return max(cents(piggy.status(bank, upto, today=f"{month}-01")["held"]), 0)


# ── The pieces ────────────────────────────────────────────────────────────

def tiles(led: Ledger, sa: int, month: str) -> dict:
    return {
        "income": led.income.get(month, 0),
        "arrived": sorted(led.arrived.get(month, [])),
        "essentials": led.group[month].get("essentials", 0),
        "lifestyle": led.group[month].get("lifestyle", 0),
        "set_aside": sa,
    }


def usual_by_today(u: dict, group: str, day: int, days: int) -> int | None:
    grp = u["groups"].get(group)
    if not grp:
        return None
    if grp.get("by_day"):
        return cents(grp["by_day"][min(day, 31) - 1])
    return cents(grp["usual"] * day / days)


def vs_usual(led: Ledger, u: dict, month: str, day: int) -> list[dict]:
    """Essentials and Lifestyle against her usual month (GR-24)."""
    days = days_in(month)
    rows = []
    for g in GROUPS:
        grp = u["groups"].get(g)
        rows.append({"key": g, "label": GROUP_LABELS[g],
                     "spent": led.group[month].get(g, 0),
                     "usual": cents(grp["usual"]) if grp else None,
                     "by_today": usual_by_today(u, g, day, days)})
    return rows


def _over(spent: int, usual: int, by_today: int | None) -> bool:
    """Above usual, by the snapshot's rule: past a usual month, or more than
    10% past where she usually is by today."""
    if spent > usual:
        return True
    if by_today is None:
        return False
    return by_today > 0 and spent > by_today * (1 + PACE_BAND)


def compare_words(spent: int, usual: int | None) -> dict:
    """GR-25's words column: same, more or less than usual, in dollars."""
    if usual is None or usual <= 0:
        return {"kind": "new", "diff": None}
    diff = spent - usual
    if abs(diff) <= max(usual * SAME_BAND, 100):
        return {"kind": "same", "diff": 0}
    return {"kind": "more" if diff > 0 else "less", "diff": abs(diff)}


def categories(led: Ledger, u: dict, month: str, day: int, running: bool) -> list[dict]:
    """Every category with spending in the six months to `month`, against
    its usual (GR-25, GR-26), largest this month first."""
    months = window(month, HISTORY)
    usual_months = u.get("months") or []
    names = {c for m in months for c, v in led.category[m].items() if v > 0}
    rows = []
    for cat in names:
        usual = u["categories"].get(cat, {}).get("usual")
        usual_c = cents(usual) if usual else (0 if usual_months else None)
        by_today = None
        if running and usual_months:
            by_today = round(sum(led.usual_by_day(m, cat, day) for m in usual_months)
                             / len(usual_months))
        spent = max(led.category[month].get(cat, 0), 0)
        history = []
        for m in months:
            amount = max(led.category[m].get(cat, 0), 0)
            live = running and m == month
            history.append({"month": m, "amount": amount, "running": live,
                            "above": _over(amount, usual_c, by_today if live else None)
                            if usual_c else False})
        rows.append({"category": cat, "group": group_of(cat), "spent": spent,
                     "usual": usual_c or None, "by_today": by_today,
                     "words": compare_words(spent, usual_c or None),
                     "unsure": led.unsure[month].get(cat, 0),
                     "history": history})
    rows.sort(key=lambda r: (-r["spent"], -(r["usual"] or 0), r["category"]))
    return rows


def where(led: Ledger, month: str) -> dict:
    """GR-30: the month's spending by group and category."""
    groups = []
    for g in GROUPS:
        cats = sorted(((c, v) for c, v in led.category[month].items()
                       if v > 0 and group_of(c) == g), key=lambda kv: (-kv[1], kv[0]))
        groups.append({"key": g, "label": GROUP_LABELS[g], "total": sum(v for _, v in cats),
                       "categories": [{"category": c, "amount": v,
                                       "unsure": led.unsure[month].get(c, 0)}
                                      for c, v in cats]})
    total = sum(g["total"] for g in groups)
    for g in groups:
        for c in g["categories"]:
            c["share"] = round(c["amount"] * 100 / total) if total else 0
    return {"month": month, "total": total, "groups": groups,
            "unsure": sum(c["unsure"] for g in groups for c in g["categories"])}


def months_shown(led: Ledger, end: str, n: int = SPAN) -> list[str]:
    """Up to `n` months to `end`, from the first the ledger covers."""
    first = first_month(led.transactions)
    if not first:
        return [end]
    if first > end:
        first = end
    return [m for m in window(end, n) if m >= first]


def trend(led: Ledger, u: dict, months: list[str], today: date) -> dict:
    """GR-29: Essentials and Lifestyle each month, and the usual band."""
    now = today.strftime("%Y-%m")
    # The band is made of usual months, so a one-off doesn't widen it.
    totals = {m: led.usual_spent(m) for m in u.get("months") or []}
    band = None
    if totals:
        band = {"low": min(totals.values()), "high": max(totals.values()),
                "usual": round(sum(totals.values()) / len(totals))}
    rows = []
    for m in months:
        e, life = led.group[m].get("essentials", 0), led.group[m].get("lifestyle", 0)
        rows.append({"month": m, "essentials": max(e, 0), "lifestyle": max(life, 0),
                     "total": max(e + life, 0), "running": m == now,
                     "above": bool(band) and m != now and e + life > band["high"]})
    above = {g: [r["month"] for r in rows if not r["running"] and _group_above(led, u, g, r["month"])]
             for g in GROUPS}
    return {"months": rows, "band": band, "above": above}


def _group_above(led: Ledger, u: dict, g: str, month: str) -> bool:
    grp = u["groups"].get(g)
    if not grp or grp["usual"] <= 0:
        return False
    return led.group[month].get(g, 0) > cents(grp["usual"]) * (1 + PACE_BAND)


def money(led: Ledger, set_asides: dict[str, int], months: list[str], today: date) -> list[dict]:
    """GR-31: in, out and set aside, and what she kept once a month ends."""
    now = today.strftime("%Y-%m")
    out = []
    for m in months:
        income, spent, sa = led.income.get(m, 0), led.spent(m), set_asides[m]
        out.append({"month": m, "income": income, "spent": max(spent, 0), "set_aside": sa,
                    "kept": None if m >= now else income - spent - sa})
    return out


def income_went(led: Ledger, sa: int, month: str) -> dict:
    """GR-25: where a month's income went, as one bar."""
    e = max(led.group[month].get("essentials", 0), 0)
    life = max(led.group[month].get("lifestyle", 0), 0)
    income = led.income.get(month, 0)
    left = income - e - life - max(sa, 0)
    return {"income": income, "essentials": e, "lifestyle": life, "set_aside": max(sa, 0),
            "left_over": max(left, 0), "short": max(-left, 0)}


def anchor_held(accounts: list[dict], transactions: list[Transaction], day: str) -> int:
    """What the Anchor's accounts held at the end of `day`, wound back from
    today's balances through each account's own transactions."""
    total = 0.0
    for a in accounts:
        rows = [t for t in transactions if t.account_id == a["account_id"]]
        as_of = a.get("as_of") or day
        total += a["balance"] if day >= as_of else balance_on(
            a["balance"], "depository", day, as_of, rows)
    return cents(max(total, 0.0))


def savings(transactions, months: list[str], today: date, *, anchor: dict,
            accounts: list[dict], banks: list[piggy.Bank], charges: dict) -> dict:
    """GR-32: the Anchor and each chest at the end of every month."""
    now = today.strftime("%Y-%m")
    started = bool(anchor.get("started"))
    paid: dict[int, set[str]] = defaultdict(set)
    for t in transactions:
        if t.bank_id is not None and t.amount > 0:
            paid[t.bank_id].add(t.month)
    series = []
    for m in months:
        day = today.isoformat() if m == now else month_end(m).isoformat()
        point = {"month": m, "anchor": anchor_held(accounts, transactions, day) if started else 0,
                 "chests": {str(b.id): chest_held(b, charges.get(b.id, {}), m) for b in banks}}
        point["total"] = point["anchor"] + sum(point["chests"].values())
        series.append(point)
    events = [{"month": m, "chest": str(b.id), "label": f"{b.name} opened"}
              for b in banks for m in sorted(paid.get(b.id, ())) if m in months]
    last = series[-1] if series else {"total": 0, "anchor": 0, "chests": {}}
    before = series[-2]["total"] if len(series) > 1 else None
    parts = ([{"key": "anchor", "label": "Anchor", "amount": last["anchor"]}] if started else [])
    parts += [{"key": str(b.id), "label": b.name, "amount": last["chests"].get(str(b.id), 0)}
              for b in banks]
    return {"total": last["total"], "change": None if before is None else last["total"] - before,
            "since": months[-2] if len(months) > 1 else None, "first": months[0] if months else None,
            "anchor_started": started, "parts": parts, "series": series, "events": events}


def subscriptions(records: list[dict], choices: dict, today: date) -> dict:
    """GR-27: each subscription by the year, with Keep or Review."""
    now = today.strftime("%Y-%m")
    rows = []
    for r in sorted(records, key=lambda r: (-r["annual_cost"], r["merchant"])):
        choice = choices.get(r["merchant"]) or {}
        rows.append({"merchant": r["merchant"], "category": r.get("category"),
                     "monthly": cents(r["monthly_cost"]), "yearly": cents(r["annual_cost"]),
                     "cadence": r.get("cadence"), "choice": choice.get("choice"),
                     "remind": choice.get("remind")})
    reminders = [r["merchant"] for r in rows
                 if r["choice"] == "review" and r["remind"] and r["remind"] <= now]
    return {"count": len(rows), "monthly": sum(r["monthly"] for r in rows),
            "yearly": sum(r["yearly"] for r in rows), "rows": rows, "reminders": reminders}


def build(transactions: list[Transaction], today: date, month: str, *, u_today: dict,
          u_month: dict, unusual: set[str], banks: list[piggy.Bank], charges: dict,
          confirmed: dict, anchor: dict, anchor_accounts: list[dict],
          subscription_records: list[dict], subscription_choices: dict) -> dict:
    """Everything Growth › Insights draws for `month`.

    `u_today` is her usual month as of today (the page and the trend);
    `u_month` the usual month as of `month` (GR-25 compares September with
    the months before September).
    """
    now = today.strftime("%Y-%m")
    running = month == now
    day = today.day if running else days_in(month)
    led = Ledger(transactions, confirmed)
    span = months_shown(led, now)
    set_asides = {m: set_aside(transactions, banks, charges, m) for m in sorted(set(span) | {month})}
    # The months the switcher steps through: from the ledger's first to now.
    first = min((t.month for t in transactions), default=now)
    all_months = window(now, _idx(now) - _idx(first) + 1) if first <= now else [now]
    prev = add_months(now, -1)
    used = u_month.get("months") or []
    # The unusual months the usual month stepped over to find three others.
    left_out = sorted(m for m in unusual if used and used[0] <= m < month)
    return {
        "today": today.isoformat(),
        "month": month,
        "running": running,
        "day": day,
        "days_in_month": days_in(month),
        "months": all_months,
        "empty": not transactions,
        "tiles": tiles(led, set_asides[month], month),
        "usual": {"months": u_month.get("months") or [], "curve": u_month.get("curve"),
                  "left_out": left_out,
                  "unusual": sorted(unusual), "month_unusual": month in unusual},
        "vs_usual": vs_usual(led, u_month, month, day),
        "categories": categories(led, u_month, month, day, running),
        "trend": trend(led, u_today, span, today),
        "where": where(led, month),
        "where_last": where(led, prev) if running and prev in led.months else None,
        "money": money(led, set_asides, span, today),
        "income_went": income_went(led, set_asides[month], month),
        "savings": savings(transactions, span, today, anchor=anchor, accounts=anchor_accounts,
                           banks=banks, charges=charges),
        "subscriptions": subscriptions(subscription_records, subscription_choices, today),
    }
