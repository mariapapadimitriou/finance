"""The savings engine.

Each rule reads the ledger and emits zero or more `Finding`s. A finding is only
worth showing if it names a number you could actually act on, so every one
carries an estimated annual saving and the transactions that justify it — the UI
shows the evidence, because a recommendation you can't audit is just a guess.

Estimates are deliberately conservative. Where a rule assumes a behaviour change
(cutting a habit in half, dropping one of three streaming services) the
assumption is stated in the finding text rather than buried in the maths.
"""

from __future__ import annotations

import hashlib
import statistics
from collections import defaultdict
from dataclasses import dataclass, field, asdict
from datetime import date

from ..analytics import by_category, category_baselines, last_complete_month, spend_only
from ..categorize import is_discretionary
from ..dedupe import find_duplicate_charges
from ..models import Transaction
from .recurring import detect_recurring

# Findings below this annual figure are noise relative to the effort of acting.
MIN_ANNUAL_SAVING = 40.0


@dataclass
class Finding:
    id: str
    kind: str
    title: str
    detail: str
    annual_saving: float
    monthly_saving: float
    confidence: float                 # 0-1: how sure we are the number holds
    effort: str                       # one-off | habit | negotiate
    category: str = ""
    merchants: list[str] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    assumption: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


def _fid(kind: str, *parts: str) -> str:
    key = "|".join([kind, *parts])
    return f"{kind}_{hashlib.sha1(key.encode()).hexdigest()[:10]}"


def _ev(t: Transaction) -> dict:
    return {
        "date": t.date, "merchant": t.merchant,
        "amount": round(t.amount, 2), "account": t.account_name or t.account_id,
    }


def generate_findings(transactions: list[Transaction],
                      dismissed: set[str] | None = None) -> list[dict]:
    """Run every rule and return findings, biggest opportunity first."""
    if not transactions:
        return []

    rows = spend_only(transactions)
    recurring = detect_recurring(transactions)
    months = _month_span(rows)

    findings: list[Finding] = []
    findings += fees_and_interest(rows)
    findings += duplicate_charges(rows)
    findings += subscription_price_creep(recurring)
    findings += zombie_subscriptions(recurring, rows)
    findings += overlapping_subscriptions(recurring)
    findings += small_frequent_habits(rows, months)
    findings += delivery_premium(rows, months)
    findings += category_above_baseline(transactions)
    findings += subscription_load(recurring, rows, months)

    dismissed = dismissed or set()
    out = [
        f.to_dict() for f in findings
        if f.annual_saving >= MIN_ANNUAL_SAVING and f.id not in dismissed
    ]
    out.sort(key=lambda f: f["annual_saving"] * max(f["confidence"], 0.3), reverse=True)
    return out


def _month_span(rows: list[Transaction]) -> float:
    """Months of history covered, for annualizing observed totals.

    Counts distinct calendar months rather than elapsed days between the first
    and last transaction. Elapsed days always lose part of the first and last
    month — twelve monthly charges from January to December span 341 days, not
    365 — which silently inflates every annualized figure by around 7%. Since
    these numbers are presented as savings you could bank, they should err low.
    """
    if not rows:
        return 0.0
    return float(max(len({t.month for t in rows}), 1))


# ── Rule 1: fees and interest ────────────────────────────────────────────────

def fees_and_interest(rows: list[Transaction]) -> list[Finding]:
    """Money paid for nothing. The highest-conviction saving in the whole engine."""
    fees = [t for t in rows if t.category == "Fees & Interest" and t.amount > 0]
    if not fees:
        return []

    span = _month_span(rows)
    total = sum(t.amount for t in fees)
    annual = round(total / span * 12, 2)

    interest = [t for t in fees if "interest" in t.description.lower()]
    by_account = defaultdict(float)
    for t in fees:
        by_account[t.account_name or t.account_id] += t.amount

    worst = max(by_account.items(), key=lambda kv: kv[1])
    detail_parts = [
        f"You paid ${total:,.2f} in fees and interest across "
        f"{len(fees)} charges over {span:.0f} months."
    ]
    if interest:
        int_total = sum(t.amount for t in interest)
        detail_parts.append(
            f"${int_total:,.2f} of that is interest, which means a balance is "
            f"being carried — paying the statement balance in full is the single "
            f"highest-return change available to you here."
        )
    detail_parts.append(f"Most of it sits on {worst[0]} (${worst[1]:,.2f}).")

    return [Finding(
        id=_fid("fees"),
        kind="fees",
        title=f"${annual:,.0f}/yr in fees and interest",
        detail=" ".join(detail_parts),
        annual_saving=annual,
        monthly_saving=round(annual / 12, 2),
        confidence=0.95,
        effort="one-off",
        category="Fees & Interest",
        merchants=sorted({t.merchant for t in fees})[:5],
        evidence=[_ev(t) for t in sorted(fees, key=lambda t: -t.amount)[:8]],
        assumption="Assumes fees and interest are avoidable in full by paying "
                   "statement balances on time and dropping fee-bearing cards.",
    )]


# ── Rule 2: duplicate charges ────────────────────────────────────────────────

def duplicate_charges(rows: list[Transaction]) -> list[Finding]:
    """Same merchant, same amount, same day or next — usually a double-bill."""
    dupes = find_duplicate_charges(rows)
    if not dupes:
        return []

    total = sum(d["amount"] for d in dupes)
    return [Finding(
        id=_fid("duplicates", *[f"{d['merchant']}{d['dates'][0]}" for d in dupes[:5]]),
        kind="duplicate",
        title=f"{len(dupes)} possible double charge{'s' if len(dupes) > 1 else ''} — "
              f"${total:,.0f} to check",
        detail="These merchants billed the same amount twice within a day. Some "
               "will be legitimate (two identical purchases), but each is worth "
               "30 seconds to confirm against your receipts, and a real "
               "double-bill is refundable.",
        annual_saving=round(total, 2),
        monthly_saving=round(total / 12, 2),
        confidence=0.45,
        effort="one-off",
        merchants=[d["merchant"] for d in dupes[:5]],
        evidence=[
            {"date": d["dates"][1], "merchant": d["merchant"],
             "amount": d["amount"], "account": d["account"]}
            for d in dupes[:8]
        ],
        assumption="Recoverable only if the duplicate is genuinely an error.",
    )]


# ── Rule 3: subscription price creep ─────────────────────────────────────────

def subscription_price_creep(recurring: list[dict]) -> list[Finding]:
    """Subscriptions that quietly raised their price on you."""
    out = []
    for r in recurring:
        pc = r.get("price_change")
        if not pc or pc["direction"] != "increase" or not r["active"]:
            continue

        annual_delta = round(pc["delta"] * r["charges_per_year"], 2)
        if annual_delta < MIN_ANNUAL_SAVING:
            continue

        out.append(Finding(
            id=_fid("creep", r["merchant"]),
            kind="price_creep",
            title=f"{r['merchant']} raised its price "
                  f"{pc['pct'] * 100:.0f}% — ${annual_delta:,.0f}/yr more",
            detail=f"This {r['cadence']} charge went from ${pc['from']:,.2f} to "
                   f"${pc['to']:,.2f}. You're now paying ${r['annual_cost']:,.0f} a "
                   f"year for it. Worth deciding deliberately whether it's still "
                   f"worth the new price — many services reverse an increase or "
                   f"offer a retention discount if you start to cancel.",
            annual_saving=annual_delta,
            monthly_saving=round(annual_delta / 12, 2),
            confidence=round(min(r["confidence"], 0.85), 2),
            effort="negotiate",
            category=r["category"],
            merchants=[r["merchant"]],
            evidence=[{"date": d, "merchant": r["merchant"], "amount": r["amount"],
                       "account": r["account_name"]} for d in r["dates"][-4:]],
            assumption="Saving equals reverting to the old price, not cancelling.",
        ))
    return out


# ── Rule 4: zombie subscriptions ─────────────────────────────────────────────

# Categories where a recurring charge without any related activity is
# suspicious. A gym you never visit still bills; electricity does not work that way.
_ZOMBIE_CATEGORIES = {"Streaming", "Software", "Fitness", "Entertainment", "News & Media"}


# Only subscriptions worth a real audit. Below this, a standalone "consider
# cancelling" card is noise -- the aggregate subscription-load finding covers
# the long tail of small charges far better than fifteen separate cards would.
ZOMBIE_MIN_ANNUAL = 150.0
ZOMBIE_MAX_FINDINGS = 3


def zombie_subscriptions(recurring: list[dict], rows: list[Transaction]) -> list[Finding]:
    """The costliest long-running subscriptions, surfaced for a deliberate decision.

    Every flat monthly charge technically fits this shape, so the rule is
    ranked and capped rather than exhaustive: the three most expensive are the
    ones where an hour spent deciding actually pays.
    """
    out = []
    candidates = sorted(
        (r for r in recurring if r["annual_cost"] >= ZOMBIE_MIN_ANNUAL),
        key=lambda r: r["annual_cost"], reverse=True,
    )

    for r in candidates:
        if len(out) >= ZOMBIE_MAX_FINDINGS:
            break
        if not r["active"] or r["category"] not in _ZOMBIE_CATEGORIES:
            continue

        # A gym membership with no other fitness spend, or a software seat
        # billed monthly for a year with the amount never varying, is a
        # candidate — but the honest signal we have is "flat and old", not usage.
        age_months = _months_between(r["first_seen"], r["last_seen"])
        if age_months < 6:
            continue

        flat = not r.get("price_change")
        if not flat:
            continue

        out.append(Finding(
            id=_fid("zombie", r["merchant"]),
            kind="zombie",
            title=f"{r['merchant']} — ${r['annual_cost']:,.0f}/yr, unchanged for "
                  f"{age_months:.0f} months",
            detail=f"A {r['cadence']} charge of ${r['amount']:,.2f} that has run "
                   f"quietly since {r['first_seen']}, totalling "
                   f"${r['total_paid']:,.2f} so far. Long-running flat charges are "
                   f"where forgotten subscriptions hide — if you can't remember the "
                   f"last time you used it, that's the answer.",
            annual_saving=r["annual_cost"],
            monthly_saving=r["monthly_cost"],
            confidence=round(min(r["confidence"] * 0.7, 0.6), 2),
            effort="one-off",
            category=r["category"],
            merchants=[r["merchant"]],
            evidence=[{"date": d, "merchant": r["merchant"], "amount": r["amount"],
                       "account": r["account_name"]} for d in r["dates"][-4:]],
            assumption="Full saving only if you cancel; we can see the charge but "
                       "not whether you use the service.",
        ))
    return out


def _months_between(a: str, b: str) -> float:
    return max((date.fromisoformat(b) - date.fromisoformat(a)).days / 30.44, 0.0)


# ── Rule 5: overlapping subscriptions ────────────────────────────────────────

def overlapping_subscriptions(recurring: list[dict]) -> list[Finding]:
    """Several active subscriptions competing for the same slot in your life."""
    groups = defaultdict(list)
    for r in recurring:
        if r["active"] and r["category"] in {"Streaming", "Software", "Fitness", "News & Media"}:
            groups[r["category"]].append(r)

    out = []
    for category, subs in groups.items():
        if len(subs) < 3:
            continue

        subs.sort(key=lambda r: r["annual_cost"], reverse=True)
        total = sum(r["annual_cost"] for r in subs)
        # Conservative: assume you drop only the cheapest one of the stack.
        droppable = subs[-1]["annual_cost"]

        out.append(Finding(
            id=_fid("overlap", category, *[r["merchant"] for r in subs]),
            kind="overlap",
            title=f"{len(subs)} active {category.lower()} subscriptions — "
                  f"${total:,.0f}/yr combined",
            detail=f"You're paying for {', '.join(r['merchant'] for r in subs)}. "
                   f"Rotating rather than stacking — keeping one or two at a time "
                   f"and resubscribing when there's something you want — typically "
                   f"cuts this bill by a third without cutting what you actually "
                   f"watch or use.",
            annual_saving=round(droppable, 2),
            monthly_saving=round(droppable / 12, 2),
            confidence=0.7,
            effort="one-off",
            category=category,
            merchants=[r["merchant"] for r in subs],
            evidence=[{"date": r["last_seen"], "merchant": r["merchant"],
                       "amount": r["amount"], "account": r["account_name"]}
                      for r in subs],
            assumption="Counts dropping only the least expensive of the stack.",
        ))
    return out


# ── Rule 6: small frequent habits ────────────────────────────────────────────

_HABIT_CATEGORIES = {"Coffee", "Dining", "Food Delivery", "Alcohol & Bars",
                     "Shopping", "Entertainment"}


def small_frequent_habits(rows: list[Transaction], months: float) -> list[Finding]:
    """The death-by-a-thousand-cuts pattern: small purchases, high frequency.

    This is where discretionary money actually goes, and it never shows up as a
    single alarming line on a statement.
    """
    if months < 1.5:
        return []

    groups: dict[tuple[str, str], list[Transaction]] = defaultdict(list)
    for t in rows:
        if t.amount > 0 and t.category in _HABIT_CATEGORIES:
            groups[(t.merchant, t.category)].append(t)

    out = []
    for (merchant, category), txns in groups.items():
        per_month = len(txns) / months
        total = sum(t.amount for t in txns)
        avg = total / len(txns)

        # The pattern of interest: frequent and individually small. A monthly
        # big-ticket purchase is a different conversation.
        if per_month < 4 or avg > 40:
            continue

        annual = total / months * 12
        # Assume halving the frequency, not eliminating it — nobody quits coffee.
        saving = round(annual * 0.5, 2)
        if saving < MIN_ANNUAL_SAVING:
            continue

        out.append(Finding(
            id=_fid("habit", merchant),
            kind="habit",
            title=f"{merchant}: {per_month:.0f}×/month at ${avg:,.2f} — "
                  f"${annual:,.0f}/yr",
            detail=f"{len(txns)} visits over {months:.0f} months, averaging "
                   f"${avg:,.2f} each. Individually invisible; annually this is "
                   f"${annual:,.0f}. Halving the frequency — not stopping — frees "
                   f"about ${saving:,.0f} a year.",
            annual_saving=saving,
            monthly_saving=round(saving / 12, 2),
            confidence=0.8,
            effort="habit",
            category=category,
            merchants=[merchant],
            evidence=[_ev(t) for t in sorted(txns, key=lambda t: t.date, reverse=True)[:6]],
            assumption="Assumes cutting visit frequency by half.",
        ))

    out.sort(key=lambda f: f.annual_saving, reverse=True)
    return out[:5]


# ── Rule 7: the delivery premium ─────────────────────────────────────────────

def delivery_premium(rows: list[Transaction], months: float) -> list[Finding]:
    """Food delivery costs roughly 40% more than the same food collected.

    Fees, service charges, marked-up menu prices and tip stack up; the widely
    cited figure is 35-45%. We use 35% to stay on the conservative side.
    """
    delivery = [t for t in rows if t.category == "Food Delivery" and t.amount > 0]
    if len(delivery) < 4 or months < 1.5:
        return []

    total = sum(t.amount for t in delivery)
    annual = total / months * 12
    per_month = len(delivery) / months
    saving = round(annual * 0.35, 2)
    if saving < MIN_ANNUAL_SAVING:
        return []

    services = sorted({t.merchant for t in delivery})
    return [Finding(
        id=_fid("delivery"),
        kind="delivery",
        title=f"Food delivery is costing ${annual:,.0f}/yr — "
              f"${saving:,.0f} of it is markup",
        detail=f"{len(delivery)} delivery orders ({per_month:.1f}/month) across "
               f"{', '.join(services[:3])}, averaging "
               f"${total / len(delivery):,.2f} per order. Delivery adds roughly 35% "
               f"over collecting the same order yourself once service fees, "
               f"marked-up menu prices and tip are counted. Switching even half "
               f"your orders to pickup keeps the meals and drops the premium.",
        annual_saving=saving,
        monthly_saving=round(saving / 12, 2),
        confidence=0.75,
        effort="habit",
        category="Food Delivery",
        merchants=services[:5],
        evidence=[_ev(t) for t in sorted(delivery, key=lambda t: -t.amount)[:6]],
        assumption="Uses a 35% delivery markup, the conservative end of published "
                   "estimates.",
    )]


# ── Rule 8: categories running above your own baseline ───────────────────────

# A category needs to be elevated across this many recent months before we call
# it a trend. One month is variance -- restaurants cluster around birthdays and
# visitors -- and annualizing a single noisy month produces alarming numbers
# that evaporate the following month.
TREND_WINDOW = 2
TREND_THRESHOLD = 0.30


def category_above_baseline(transactions: list[Transaction]) -> list[Finding]:
    """A category running above its own trailing median across recent months.

    Compared against you, not against national averages, because "the average
    household spends X" tells you nothing about your own life.
    """
    rows = spend_only(transactions)

    # Only months the data covers end to end are comparable. A partial current
    # month always looks like an improvement, which would be a lie.
    complete = [m for m in sorted({t.month for t in rows})
                if _is_complete(rows, m)]
    if len(complete) < TREND_WINDOW + 3:
        return []

    recent, prior = complete[-TREND_WINDOW:], complete[:-TREND_WINDOW]

    per_month: dict[str, dict[str, float]] = defaultdict(lambda: defaultdict(float))
    for t in rows:
        per_month[t.month][t.category or "Other"] += t.amount

    out = []
    for category in {c for m in recent for c in per_month[m]}:
        # "Other" is the uncategorized bucket, not a spending habit -- a spike
        # there means the categorizer needs teaching, not that you overspent.
        # Fees are real but the fees rule reports them far better.
        if category in {"Other", "Fees & Interest"} or not is_discretionary(category):
            continue

        recent_avg = statistics.fmean([per_month[m].get(category, 0.0) for m in recent])
        baseline = statistics.median([per_month[m].get(category, 0.0) for m in prior])
        if baseline <= 0 or recent_avg <= 0:
            continue

        delta = recent_avg - baseline
        if delta <= 0 or delta / baseline < TREND_THRESHOLD:
            continue

        # Every month in the window must be up, or it isn't a trend — one
        # blowout month averaged with a normal one would otherwise qualify.
        if not all(per_month[m].get(category, 0.0) > baseline for m in recent):
            continue

        annual = round(delta * 12, 2)
        if annual < MIN_ANNUAL_SAVING:
            continue

        out.append(Finding(
            id=_fid("baseline", category, recent[-1]),
            kind="trend",
            title=f"{category} is {delta / baseline * 100:.0f}% above your normal — "
                  f"${delta:,.0f}/month extra",
            detail=f"Across {' and '.join(_month_name(m) for m in recent)} you averaged "
                   f"${recent_avg:,.2f}/month on {category}, against a typical "
                   f"${baseline:,.2f} over the prior {len(prior)} months — and both "
                   f"months were up, so this is drift rather than a one-off. "
                   f"Returning to your own baseline is worth ${annual:,.0f} a year.",
            annual_saving=annual,
            monthly_saving=round(delta, 2),
            confidence=0.6,
            effort="habit",
            category=category,
            evidence=[_ev(t) for t in sorted(
                [t for t in rows if t.month in recent and t.category == category],
                key=lambda t: -t.amount)[:6]],
            assumption="Annualizes the recent monthly excess; it assumes the new "
                       "level persists, which is the thing worth catching early.",
        ))

    out.sort(key=lambda f: f.annual_saving, reverse=True)
    return out[:3]


def _is_complete(rows: list[Transaction], month: str) -> bool:
    from ..analytics import is_month_complete
    return is_month_complete(rows, month)


_MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"]


def _month_name(month: str) -> str:
    """"2026-07" -> "July 2026". These strings are read by a person."""
    try:
        return f"{_MONTH_NAMES[int(month[5:7]) - 1]} {month[:4]}"
    except (ValueError, IndexError):
        return month


# ── Rule 9: total subscription load ──────────────────────────────────────────

def subscription_load(recurring: list[dict], rows: list[Transaction],
                      months: float) -> list[Finding]:
    """The aggregate view: what share of your spending renews without a decision."""
    active = [r for r in recurring if r["active"]]
    discretionary_subs = [
        r for r in active
        if r["category"] in _ZOMBIE_CATEGORIES
    ]
    if len(discretionary_subs) < 4:
        return []

    annual = sum(r["annual_cost"] for r in discretionary_subs)
    total_annual = sum(t.amount for t in rows if t.amount > 0) / months * 12
    share = annual / total_annual if total_annual else 0

    # A standard audit outcome is that a quarter of a subscription stack is
    # genuinely unwanted once you look at it line by line.
    saving = round(annual * 0.25, 2)
    if saving < MIN_ANNUAL_SAVING:
        return []

    cheapest = sorted(discretionary_subs, key=lambda r: r["annual_cost"])

    return [Finding(
        id=_fid("subload", str(len(discretionary_subs))),
        kind="subscription_load",
        title=f"{len(discretionary_subs)} recurring subscriptions — "
              f"${annual:,.0f}/yr on autopilot",
        detail=f"That's {share * 100:.0f}% of your total spending renewing without "
               f"a decision each month (${annual / 12:,.0f}/month). The smallest "
               f"ones are the easiest to forget: "
               f"{', '.join(r['merchant'] for r in cheapest[:3])}. Cancel what you "
               f"can't justify out loud and the typical result is about a quarter "
               f"of the stack.",
        annual_saving=saving,
        monthly_saving=round(saving / 12, 2),
        confidence=0.55,
        effort="one-off",
        merchants=[r["merchant"] for r in discretionary_subs],
        evidence=[{"date": r["last_seen"], "merchant": r["merchant"],
                   "amount": r["amount"], "account": r["account_name"]}
                  for r in sorted(discretionary_subs,
                                  key=lambda r: -r["annual_cost"])[:8]],
        assumption="Assumes cancelling a quarter of the subscription stack by value.",
    )]


def findings_summary(findings: list[dict]) -> dict:
    """Headline totals, split by how much work each finding actually takes."""
    by_effort = defaultdict(float)
    for f in findings:
        by_effort[f["effort"]] += f["annual_saving"]

    # A confidence-weighted figure is the honest headline: the raw sum
    # double-counts speculative findings alongside certain ones.
    weighted = sum(f["annual_saving"] * f["confidence"] for f in findings)

    return {
        "count": len(findings),
        "annual_total": round(sum(f["annual_saving"] for f in findings), 2),
        "monthly_total": round(sum(f["monthly_saving"] for f in findings), 2),
        "weighted_annual": round(weighted, 2),
        "by_effort": {k: round(v, 2) for k, v in by_effort.items()},
        "quick_wins": round(by_effort.get("one-off", 0.0), 2),
    }
