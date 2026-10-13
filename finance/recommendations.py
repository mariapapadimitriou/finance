"""Recommendation cards (Pearl E08, THL-12: THL-60 to THL-63; designed in
THL-133 RC-01 to RC-03).

Four rule types, each with her own numbers, a "Why you're seeing this" and
one action. Nothing is written by a model, no product is named, and no card
appears without the data behind it.

1. Spending trend: a Lifestyle category is running TREND_ABOVE (25%) or more
   above her usual for this point in the month: the average of the last
   three full months by today's day. Needs those three months, and a gap of
   at least MIN_GAP so small categories don't make noise. The largest gap
   wins. Yearly impact: the gap, twelve times. One-offs (THL-71) are left
   out on both sides.
2. Subscriptions (THL-63): her recurring charges in a subscription category
   (streaming, news, software, fitness, entertainment), billed monthly or
   less often, and what they cost a year. Shown with at least
   MIN_SUBSCRIPTIONS of them. "Still using
   them all? Pearl won't cancel anything." Yearly impact: the yearly total.
3. Anchor pace (R2: only once the Anchor is started and not full): a little
   more each paycheque, and how much sooner it fills. The extra is about
   PACE_EXTRA (15%) of her usual pace, in $10s, at least MIN_EXTRA a
   paycheque; shown only when it's at least MIN_WEEKS_SOONER sooner. Yearly
   impact: the extra over a year.
4. Idle cash: her chequing has stayed above a month of Essentials for the
   last IDLE_DAYS while the Anchor isn't full. Suggests moving what would
   reach the Anchor's next stop (its first $500, or what's left) and still
   leave a month of Essentials, in $50s, at least MIN_MOVE. Shows without a
   started Anchor too ("start your Anchor with $500", R2). Impact: the amount.

Decisions this follows (THL-9 comment, 2026-10-12):

* At most MAX_CARDS (2). With more qualifying, the biggest yearly dollar
  impact wins (R4).
* "Not for me" hides that type for DISMISS_DAYS (30), with Undo.
* R1: every card action is secondary; Home's one primary stays the path.
* R3: "Move to savings" opens Goals › Anchor; "Review subscriptions" opens
  Transactions filtered to recurring charges.
"""

from __future__ import annotations

from collections import defaultdict
from datetime import date, timedelta

from .analytics import counts_as_spending, spend_amount
from .balances import balance_on
from .categorize import group_of
from .insights.recurring import detect_recurring
from .models import Transaction

TYPES = ("trend", "subscriptions", "pace", "idle")
LABELS = {"trend": "Spending trend", "subscriptions": "Subscriptions",
          "pace": "Anchor pace", "idle": "Idle cash"}
MAX_CARDS = 2
DISMISS_DAYS = 30

TREND_ABOVE = 0.25
MIN_GAP = 20.0
MIN_SUBSCRIPTIONS = 2
SUBSCRIPTION_CATEGORIES = {"Streaming", "News & Media", "Software", "Fitness", "Entertainment"}
SUBSCRIPTION_CADENCES = {"monthly", "quarterly", "semiannual", "annual"}
PACE_EXTRA = 0.15
MIN_EXTRA = 20
MIN_WEEKS_SOONER = 2
IDLE_DAYS = 90
MIN_MOVE = 100

MONTHS = ["January", "February", "March", "April", "May", "June", "July", "August",
          "September", "October", "November", "December"]


def _money(x: float) -> str:
    return f"${round(x):,}"


def _month(m: str) -> str:
    return MONTHS[int(m[5:7]) - 1]


def _day(d: date) -> str:
    return f"{MONTHS[d.month - 1]} {d.day}"


# ── 1. Spending trend ────────────────────────────────────────────────────

def trend(transactions: list[Transaction], today: date, usual: dict) -> dict | None:
    months = usual.get("months") or []
    if usual.get("curve") != "daily":
        return None
    covered, month = set(months), today.strftime("%Y-%m")
    by_today: dict[str, float] = defaultdict(float)
    spent: dict[str, float] = defaultdict(float)
    for t in transactions:
        # A one-off (THL-71) is neither part of usual nor a trend: one big
        # purchase this month is not "running above usual".
        if not counts_as_spending(t) or t.one_off:
            continue
        cat = t.category or "Other"
        if group_of(cat) != "lifestyle":
            continue
        if t.month in covered and int(t.date[8:10]) <= today.day:
            by_today[cat] += spend_amount(t) / len(months)
        elif t.month == month and t.date <= today.isoformat():
            spent[cat] += spend_amount(t)
    best = None
    for cat, usual_by in by_today.items():
        now = spent.get(cat, 0.0)
        gap = now - usual_by
        if usual_by <= 0 or gap < MIN_GAP or now < usual_by * (1 + TREND_ABOVE):
            continue
        if not best or gap > best[3]:
            best = (cat, now, usual_by, gap)
    if not best:
        return None
    cat, now, usual_by, gap = best
    pct = int(round((now / usual_by - 1) * 100 / 5) * 5)
    name = cat.lower() if cat[:1].isupper() and not cat.isupper() else cat
    span = f"{_month(months[0])} to {_month(months[-1])}"
    return {
        "type": "trend", "label": LABELS["trend"], "impact": round(gap * 12, 2),
        "title": f"{cat} is running about {pct}% above usual",
        "body": f"{_money(now)} so far, compared with a usual {_money(usual_by)} by {_day(today)}.",
        "numbers": {"category": cat, "spent": round(now, 2), "usual_by_today": round(usual_by, 2),
                    "pct": pct},
        "why": {"title": f"{cat} is above usual",
                "text": (f"So far this month you’ve spent {_money(now)} on {name}. By {_day(today)} "
                         f"you usually spend about {_money(usual_by)} (average of {span})."),
                "rule": "We show this when a Lifestyle category is 25% or more above usual "
                        "for this point in the month.",
                "lines": []},
        "action": {"label": f"See {name}", "to": "transactions",
                   "filters": {"month": month, "category": cat}},
    }


# ── 2. Subscriptions ─────────────────────────────────────────────────────

def subscription_records(transactions: list[Transaction], today: date) -> list[dict]:
    """Live recurring charges in a subscription category, billed monthly or
    less often. A weekly coffee or a monthly dinner at the same place recurs
    too, but it isn't a subscription."""
    return [r for r in detect_recurring(transactions, as_of=today.isoformat())
            if r.get("active") and r.get("category") in SUBSCRIPTION_CATEGORIES
            and r.get("cadence") in SUBSCRIPTION_CADENCES]


def subscriptions(transactions: list[Transaction], today: date) -> dict | None:
    subs = subscription_records(transactions, today)
    if len(subs) < MIN_SUBSCRIPTIONS:
        return None
    monthly = sum(r["monthly_cost"] for r in subs)
    yearly = sum(r["annual_cost"] for r in subs)
    if monthly < 1:
        return None
    lines = sorted(({"label": r["merchant"], "monthly": round(r["monthly_cost"], 2),
                     "yearly": round(r["annual_cost"], 2)} for r in subs),
                   key=lambda x: -x["yearly"])
    return {
        "type": "subscriptions", "label": LABELS["subscriptions"], "impact": round(yearly, 2),
        "title": f"You pay {_money(monthly)} a month for {len(subs)} subscriptions",
        "body": f"That’s {_money(yearly)} a year. Still using them all? Pearl won’t cancel anything.",
        "numbers": {"count": len(subs), "monthly": round(monthly, 2), "yearly": round(yearly, 2)},
        "why": {"title": "Your subscriptions, by the year",
                "text": "These charge you again and again. Here’s what each one costs over a year.",
                "rule": "We show this when you have 2 or more subscriptions. Pearl only reads "
                        "your accounts, so it can’t cancel anything.",
                "lines": lines},
        "action": {"label": "Review subscriptions", "to": "transactions",
                   # The latest month they charged in, so the list isn't
                   # empty early in a month.
                   "filters": {"recurring": "1",
                               "month": max(r["last_seen"] for r in subs)[:7]}},
    }


# ── 3. Anchor pace ───────────────────────────────────────────────────────

def pace(anchor: dict, paycheques: int) -> dict | None:
    if not anchor.get("started") or anchor.get("full"):
        return None
    usual = (anchor.get("pace") or {}).get("usual") or 0
    to_go = anchor.get("to_go") or 0
    if usual <= 0 or to_go <= 0:
        return None
    pays = max(int(paycheques or 0), 1)
    each = max(MIN_EXTRA, int(round(usual * PACE_EXTRA / pays / 10)) * 10)
    extra = each * pays
    now_months, new_months = to_go / usual, to_go / (usual + extra)
    weeks = int(round((now_months - new_months) * 52 / 12))
    if weeks < MIN_WEEKS_SOONER:
        return None
    every = "each paycheque" if pays > 1 else "each month"
    return {
        "type": "pace", "label": LABELS["pace"], "impact": float(extra * 12),
        "title": f"Moving {_money(each)} more {every} gets your Anchor full about {weeks} weeks sooner",
        "body": f"Based on your usual pace of {_money(usual)} a month.",
        "numbers": {"each": each, "monthly_extra": extra, "usual": round(usual, 2),
                    "weeks_sooner": weeks, "to_go": round(to_go, 2)},
        "why": {"title": "Your Anchor could fill sooner",
                "text": (f"You have {_money(to_go)} to go. At your usual {_money(usual)} a month "
                         f"that’s about {_months_words(now_months)}; with {_money(extra)} more a "
                         f"month, about {_months_words(new_months)}."),
                "rule": "We show this once your Anchor is started, when a little more would "
                        "make it full at least 2 weeks sooner.",
                "lines": []},
        "action": {"label": "Try it", "to": "goals",
                   "goals": {"view": "whatif", "monthly": round(usual + extra, 2)}},
    }


def _months_words(m: float) -> str:
    n = max(int(round(m)), 1)
    return f"{n} month" if n == 1 else f"{n} months"


# ── 4. Idle cash ─────────────────────────────────────────────────────────

def lowest_balance(accounts: dict[str, float], transactions: list[Transaction], today: date,
                   days: int = IDLE_DAYS) -> float | None:
    """The lowest the chequing accounts held together at the end of any day
    over the last `days`, from today's balances and the transactions since.
    None without that much history."""
    if not accounts:
        return None
    rows = [t for t in transactions if t.account_id in accounts]
    first = min((t.date for t in rows), default=None)
    start = today - timedelta(days=days)
    if not first or first > start.isoformat():
        return None
    low = None
    for i in range(days + 1):
        d = (start + timedelta(days=i)).isoformat()
        held = sum(balance_on(cur, "depository", d, today.isoformat(),
                              [t for t in rows if t.account_id == aid])
                   for aid, cur in accounts.items())
        low = held if low is None else min(low, held)
    return round(low, 2)


def idle(anchor: dict, low: float | None, essentials: float | None) -> dict | None:
    if low is None or not essentials or anchor.get("full"):
        return None
    started = bool(anchor.get("started"))
    counted = anchor.get("counted") or 0
    first_stop = anchor.get("first_stop") or 500
    if not started:
        need, outcome = first_stop, "start your Anchor"
    elif not anchor.get("first_stop_done"):
        need, outcome = first_stop - counted, "cover your Anchor’s first stop"
    else:
        need, outcome = anchor.get("to_go") or 0, None
    room = low - essentials
    amount = int(min(need, room) // 50 * 50)
    if amount < MIN_MOVE:
        return None
    if outcome is None:
        outcome = "fill your Anchor" if amount >= need else f"bring your Anchor {_money(amount)} closer"
    floor = int(low // 100 * 100)
    return {
        "type": "idle", "label": LABELS["idle"], "impact": float(amount),
        "title": f"Your chequing has stayed above {_money(floor)} for 3 months",
        "body": f"Moving {_money(amount)} to savings would {outcome} and still leave a month of Essentials.",
        "numbers": {"lowest": low, "essentials": round(essentials, 2), "amount": amount},
        "why": {"title": "Money sitting in chequing",
                "text": (f"Over the last 3 months your chequing never went below {_money(low)}. "
                         f"A month of Essentials is about {_money(essentials)}, so {_money(amount)} "
                         "can move and still leave that."),
                "rule": "We show this when chequing stays above a month of Essentials for 3 "
                        "months while your Anchor isn’t full. We don’t suggest any product.",
                "lines": []},
        "action": {"label": "Move to savings", "to": "goals",
                   "goals": {"view": "anchor" if started else "start", "amount": amount}},
    }


# ── Choosing ─────────────────────────────────────────────────────────────

def hidden(dismissed: dict[str, str], today: date) -> set[str]:
    """Types she said "Not for me" to in the last 30 days."""
    cutoff = (today - timedelta(days=DISMISS_DAYS)).isoformat()
    return {t for t, on in dismissed.items() if on and on > cutoff}


def choose(cards: list[dict | None], dismissed: dict[str, str], today: date) -> list[dict]:
    """At most two, the biggest yearly dollar impact first (R4)."""
    off = hidden(dismissed, today)
    live = [c for c in cards if c and c["type"] not in off]
    live.sort(key=lambda c: (-c["impact"], TYPES.index(c["type"])))
    return live[:MAX_CARDS]
