"""The path: Protect → Build → Unveil, and the one next step (THL-129).

Steps, as THL-129 (2026-10-12) lists them:

* Protect: income confirmed; bills confirmed; last full month's income
  covered Essentials.
* Build: the Anchor's first stop ($500); the Anchor full (one month of
  Essentials). Also counts: saved more than spent in 2 of the last 3 months;
  no card balance growing.
* Unveil: first investment account opened — an investment account linked,
  or her own word for it (THL-195 GR-37: "Opened an investing account?"
  asks only the kind of account, never where, a login or a balance).

Income and bills are confirmed in the income and bills check (THL-45,
THL-127, `income_bills`). Income is confirmed once she has said yes to her
pay, edited it, or given the income she expects (I-03); bills once she has
confirmed them (I-04). Someone who hasn't run the check yet keeps the
earlier reading: income counts once Pearl can see regular pay or she has
told us what she earns (a cautious guess from irregular deposits is not a
confirmation), and bills once at least one is found or she has told us her
rent. Protect, once done, stays done (THL-53): a rough month doesn't undo it.

Also here: what each linked bank's connection needs (THL-120), from Plaid's
error code.
"""

from __future__ import annotations

from datetime import date

from .analytics import counts_as_spending, is_others, spend_amount
from .categorize import group_of
from .usual_month import covered_months

PHASES = ("protect", "build", "unveil")
PHASE_LABELS = {"protect": "Protect", "build": "Build", "unveil": "Unveil"}


def _month_income_and_spending(transactions, month: str) -> tuple[float, float, float]:
    """Income, all spending and Essentials in one month."""
    income = spent = essentials = 0.0
    for t in transactions:
        if t.month != month:
            continue
        if t.category == "Income" and t.amount < 0 and not t.repays and not is_others(t):
            income += -t.amount
        elif counts_as_spending(t):
            amount = spend_amount(t)
            spent += amount
            if group_of(t.category or "Other") == "essentials":
                essentials += amount
    return round(income, 2), round(spent, 2), round(essentials, 2)


def _cards_not_growing(transactions, month: str | None, card_accounts: set[str]) -> bool:
    """No card balance grew over the last full month: on each card, purchases
    were no more than what was paid back."""
    if not month or not card_accounts:
        return True
    net: dict[str, float] = {}
    for t in transactions:
        if t.month == month and t.account_id in card_accounts and not t.excluded:
            net[t.account_id] = net.get(t.account_id, 0.0) + t.amount
    return all(v <= 0.005 for v in net.values())


def cards_steady(transactions, months: list[str], card_accounts: set[str]) -> dict:
    """GR-16's "No card balance growing": no card balance grew in any of
    `months`. Says which month one did, if one did."""
    grew = [m for m in months if not _cards_not_growing(transactions, m, card_accounts)]
    return {"done": not grew, "months": len(months), "grew_in": grew[-1] if grew else None,
            "cards": len(card_accounts)}


def income_confirmed(sts: dict, confirm: dict | None, told_income: float = 0.0) -> bool:
    """Is her income confirmed (THL-127)? Her answers once she has given
    them; before that, regular pay Pearl can see or an amount she told us."""
    if confirm and confirm.get("income_on"):
        return bool(confirm.get("pays")) or told_income > 0
    return sts.get("income_source") in ("detected", "told", "entered", "confirmed")


def bills_confirmed(confirm: dict | None, bills_found: int = 0, told_rent: float = 0.0) -> bool:
    """Are her bills confirmed (THL-127)? Once she has confirmed I-04;
    before that, once a bill is found or she has told us her rent."""
    if confirm and confirm.get("bills_on"):
        return True
    return bills_found > 0 or told_rent > 0


def path(transactions, today: date, sts: dict, *, anchor: dict, bills_found: int = 0,
         told_rent: float = 0.0, account_types: dict[str, str] | None = None,
         protect_done_before: bool = False, confirm: dict | None = None,
         told_income: float = 0.0, invest_reported: bool = False,
         every_step: bool = False) -> dict:
    """Where she is on the path, every step's state, and the next step.
    `confirm` is her income and bills check (`income_bills.load`);
    `invest_reported` is her saying she opened an investing account (GR-37).

    `lapse` is GR-04's "Keep it going": Protect is done and stays done, but
    the last full month's Essentials came to more than its income. With
    `every_step`, `all` holds every phase's steps, for a step's own screen
    (GR-02, GR-03), whichever phase she's in."""
    types = account_types or {}
    months = covered_months(transactions, today)
    last = months[-1] if months else None
    income, spent, essentials = _month_income_and_spending(transactions, last) if last else (0, 0, 0)

    protect = [
        {"key": "income", "label": "Confirm your income",
         "done": income_confirmed(sts, confirm, told_income)},
        {"key": "bills", "label": "Confirm your bills",
         "done": bills_confirmed(confirm, bills_found, told_rent)},
        {"key": "essentials", "label": "Cover your Essentials",
         "done": bool(last) and essentials > 0 and income >= essentials,
         "month": last, "income": income, "essentials": essentials},
    ]
    protect_done = protect_done_before or all(s["done"] for s in protect)
    lapse = None
    if protect_done and last and essentials > 0 and income < essentials:
        lapse = {"step": "essentials", "month": last, "income": income, "essentials": essentials}
        protect[2]["lapsed"] = True
    if protect_done:
        for s in protect:
            s["done"] = True

    started = bool(anchor.get("started"))
    build = [
        {"key": "first_stop", "label": "Reach your Anchor’s first stop",
         "done": started and bool(anchor.get("first_stop_done")),
         "first_stop": anchor.get("first_stop")},
        {"key": "full", "label": "Fill your Anchor",
         "done": bool(anchor.get("earned")), "target": anchor.get("target") or None},
    ]
    saving_months = sum(1 for m in months
                        if _month_income_and_spending(transactions, m)[0]
                        > _month_income_and_spending(transactions, m)[1])
    cards = {a for a, t in types.items() if (t or "").lower() == "credit"}
    also = [
        {"key": "saved_more", "label": "Save more than you spend in 2 of the last 3 months",
         "done": len(months) >= 3 and saving_months >= 2, "count": saving_months,
         "of": len(months)},
        {"key": "cards", "label": "Keep card balances from growing",
         "done": _cards_not_growing(transactions, last, cards)},
    ]
    unveil = [
        {"key": "invest", "label": "Open your first investment account",
         "done": invest_reported
         or any((t or "").lower() == "investment" for t in types.values())},
    ]

    if not protect_done:
        phase, steps = "protect", protect
    elif not build[1]["done"]:
        phase, steps = "build", build
    else:
        phase, steps = "unveil", unveil
    current = next((i for i, s in enumerate(steps) if not s["done"]), None)
    order = PHASES.index(phase)
    extra = {"all": {"protect": protect, "build": build, "also": also, "unveil": unveil}} \
        if every_step else {}
    return {
        **extra,
        "phase": phase,
        "phases": [{"key": p, "label": PHASE_LABELS[p],
                    "state": "done" if i < order else "now" if i == order else "ahead"}
                   for i, p in enumerate(PHASES)],
        "steps": steps,
        "also": also if phase == "build" else [],
        "step": (current + 1) if current is not None else None,
        "of": len(steps),
        "protect_done": protect_done,
        "lapse": lapse,
        "next": _next(phase, steps[current]["key"] if current is not None else None, started),
    }


def _next(phase: str, step: str | None, started: bool) -> dict:
    """The one next step and the action that takes it (GR-05)."""
    if phase == "protect":
        return {
            "income": {"text": "Next: add your income, so we can work out what’s safe to spend.",
                       "label": "Add your income", "action": "income"},
            "bills": {"text": "Next: check the bills we found, so none of them is a surprise.",
                      "label": "Check your bills", "action": "bills"},
            "essentials": {"text": "Next: a month where what comes in covers your Essentials.",
                           "label": "See your path", "action": "path"},
        }[step]
    if phase == "build":
        if not started:
            return {"text": "Next: start your Anchor, so a surprise bill doesn’t become a problem.",
                    "label": "Start your Anchor", "action": "goals"}
        return {"text": "Next: add to your Anchor.", "label": "Add to your Anchor",
                "action": "goals"}
    if step:
        return {"text": "Next: see whether you’re ready to invest.", "label": "See your path",
                "action": "path"}
    return {"text": "Every step on your path is done.", "label": "See your path",
            "action": "path"}


# ── Connection health (THL-120) ──────────────────────────────────────────

SIGN_IN = {"ITEM_LOGIN_REQUIRED", "PENDING_EXPIRATION", "PENDING_DISCONNECT",
           "INVALID_CREDENTIALS", "INVALID_MFA", "USER_SETUP_REQUIRED",
           "ITEM_LOCKED", "INSUFFICIENT_CREDENTIALS"}
BANK_DOWN = {"INSTITUTION_DOWN", "INSTITUTION_NOT_RESPONDING", "INSTITUTION_NOT_AVAILABLE",
             "INSTITUTION_NO_LONGER_SUPPORTED", "PRODUCT_NOT_READY"}
GONE = {"ITEM_NOT_FOUND", "USER_PERMISSION_REVOKED", "ACCESS_NOT_GRANTED"}


def connection_state(item: dict) -> str | None:
    """needs_sign_in (C-02), bank_down (C-03), disconnected (C-06), or None
    when it's fine, or when the error isn't one she can see or act on."""
    if not item.get("last_error"):
        return None
    code = (item.get("error_code") or "").upper()
    if code in SIGN_IN or (not code and "sign in again" in item["last_error"].lower()):
        return "needs_sign_in"
    if code in BANK_DOWN:
        return "bank_down"
    if code in GONE:
        return "disconnected"
    return None


def connections(items: list[dict], account_rules: dict[str, dict]) -> list[dict]:
    """Every linked bank whose connection needs something, worst first."""
    out = []
    for item in items:
        state = connection_state(item)
        if not state:
            continue
        kinds = {(r.get("account_type") or "").lower() for r in account_rules.values()
                 if r.get("item_id") == item["item_id"] and r.get("enabled")}
        out.append({"item_id": item["item_id"],
                    "institution": item.get("institution") or "Your bank",
                    "state": state, "last_synced": item.get("last_synced"),
                    "cards_only": kinds == {"credit"}})
    rank = {"needs_sign_in": 0, "disconnected": 1, "bank_down": 2}
    return sorted(out, key=lambda c: rank[c["state"]])
