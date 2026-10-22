"""One list of everything Pearl isn't sure about, each with its best guess.

Five kinds, all from the last 60 days (nobody remembers what an e-transfer
from last spring was for):

* unsorted         money that left for somewhere Pearl can't see
                   (grouped by where it went, as the Unsorted card was)
* unsure_category  a category Plaid itself wasn't confident in, or "Other"
* money_in         money that arrived from somewhere Pearl can't see and
                   paired with none of your own transfers: a friend paying
                   you back, a gift, a loan repaid, or your own money
* income_type      income whose type is only a guess (other, or bonus-sized)
* three_pay_month  a month that held a third paycheque
* duplicate        the same purchase from two places (THL-165): a statement
                   file and the bank connection, say. Counted once until
                   answered, so it is asked about however old it is.
* joint_in         money into a joint account from outside Pearl: hers,
                   or the other person's (finance/joint.py). Counted as
                   nothing until answered.

Skipped (THL-213): "Skip for now" puts an item in Skipped, kept between
visits. A skipped item is still listed, marked `skipped`; it leaves `count`
(the Home and navigation badge) and is counted in `skipped` instead. Each
item's key is what's skipped: "u:<id>" for a transfer, otherwise its `key`.

Nothing is decided here; each item says what Pearl would do and why. Acting
on one goes through the ordinary endpoints (category, payback, exclusion,
income type). An item you settle without changing anything is dismissed by
its key and does not come back.
"""

from __future__ import annotations

from datetime import date, timedelta

from .analytics import is_others
from .categorize import is_unsure
from .duplicates import questions as duplicate_questions
from .etransfers import is_etransfer, memo, party
from .income import KINDS, cadence, is_income, kind_of
from .models import Transaction
from .splits import suggest as split_suggest
from .transfers import ASK_DAYS, destination, matched_inflows, unsorted

# Where a friend's share most often comes from (doc: prefer these over $40).
SHARED = {"Dining", "Food Delivery", "Alcohol & Bars", "Coffee", "Entertainment",
          "Travel", "Lodging", "Groceries", "Transport"}
LOOKBACK_DAYS = 30


def _money(x: float) -> str:
    return f"${abs(x):,.2f}"


def _brief(t: Transaction) -> dict:
    who = party(t)
    return {"id": t.fingerprint, "date": t.date,
            "merchant": (who or {}).get("name") or t.merchant,
            "description": t.description, "amount": t.amount,
            "account_id": t.account_id, "account_name": t.account_label or "",
            "category": t.category, "logo": (t.raw or {}).get("logo_url") or "",
            # An e-Transfer's message, when the bank passed it on (2026-10-21).
            "memo": memo(t)}


def _is_bank(t: Transaction) -> bool:
    return str((t.raw or {}).get("account_type", "")).lower() == "depository"


def unsorted_groups(transactions: list[Transaction]) -> dict:
    rows = unsorted(transactions)
    groups: dict[str, dict] = {}
    for t in rows:
        where = destination(t)
        key = where[0] if where else "row:" + t.fingerprint
        g = groups.setdefault(key, {
            "key": key, "merchant": where[1] if where else t.merchant,
            "learnable": bool(where), "count": 0, "total": 0.0, "first": t.date,
            "last": t.date, "accounts": [], "ids": []})
        g["count"] += 1
        g["total"] = round(g["total"] + t.amount, 2)
        g["first"], g["last"] = min(g["first"], t.date), max(g["last"], t.date)
        if (t.account_label or "") not in g["accounts"]:
            g["accounts"].append(t.account_label or "")
        g["ids"].append(t.fingerprint)
    return {"count": len(rows),
            "total": round(sum(t.amount for t in rows), 2),
            # One row per transfer: each is its own decision.
            "transfers": [dict(_brief(t), to=(destination(t) or (None, t.merchant))[1])
                          for t in rows],
            "groups": sorted(groups.values(), key=lambda g: -g["total"])}


def charge_candidates(inflow: Transaction, transactions: list[Transaction]) -> list[dict]:
    """The charges this money most likely paid you back for, best first.

    A friend's share is the charge split evenly: $20 back on an $80 dinner is
    one of four. Within $3 or 5% for tips and rounding, in the 30 days before
    the money arrived. Shared kinds of spending over $40 rank first, and a
    charge that other arrivals in the window would finish paying off ranks
    above one they wouldn't.
    """
    got = -inflow.amount
    when = date.fromisoformat(inflow.date[:10])
    arrivals = [t for t in transactions
                if t.amount < 0 and not t.repays and t.fingerprint != inflow.fingerprint
                and abs((date.fromisoformat(t.date[:10]) - when).days) <= LOOKBACK_DAYS]
    out = []
    for c in transactions:
        if c.amount <= 0 or c.excluded or c.repays:
            continue
        if c.category in ("Transfers", "Income", "Saved", "Lent", "Borrowed",
                          "Unsorted transfers"):
            continue
        gap = (when - date.fromisoformat(c.date[:10])).days
        if gap < 0 or gap > LOOKBACK_DAYS:
            continue
        left = round(c.amount - (c.paid_back or 0.0), 2)
        if got > left + 0.005:
            continue
        best = None
        for n in range(2, 7):
            share = c.amount / n
            if abs(share - got) <= max(3.0, share * 0.05):
                best = n if best is None or abs(c.amount / n - got) < abs(
                    c.amount / best - got) else best
        if best is None:
            continue
        # Others in the window sending about the same share: the rest of the split.
        peers = sum(1 for a in arrivals if abs(-a.amount - got) <= max(3.0, got * 0.05))
        shared = c.category in SHARED and c.amount >= 40
        score = (0 if shared else 1, 0 if peers >= 1 else 1, gap)
        out.append((score, best, c))
    out.sort(key=lambda r: r[0])
    return [dict(_brief(c), split=n, likely=(s[0] == 0)) for s, n, c in out[:5]]


def build(transactions: list[Transaction], today: str | None = None,
          dismissed: set[str] | None = None, splits: dict | None = None,
          payer: dict | None = None, found_on: dict[str, str] | None = None,
          skipped: set[str] | None = None) -> dict:
    today_d = date.fromisoformat(today) if today else date.today()
    since = (today_d - timedelta(days=ASK_DAYS)).isoformat()
    dismissed = dismissed or set()
    live = [t for t in transactions if not t.excluded]

    # 1. Unsorted transfers.
    groups = unsorted_groups(live)

    # 2. Categories Pearl isn't sure of.
    unsure = []
    for t in live:
        if t.date[:10] < since or t.amount <= 0 or t.category_source == "user":
            continue
        key = "cat:" + t.fingerprint
        if key in dismissed:
            continue
        if is_unsure(t) or (t.category or "Other") == "Other":
            reason = ("Plaid wasn’t confident about this category." if is_unsure(t)
                      else "Pearl couldn’t tell what this was.")
            unsure.append({"key": key, "txn": _brief(t), "guess": t.category or "Other",
                           "reason": reason})

    # 3. Money in from somewhere Pearl can't see.
    paired = matched_inflows(transactions, today=today_d.isoformat())
    money_in = []
    for t in live:
        if (t.amount >= 0 or t.date[:10] < since or not _is_bank(t) or t.repays
                or t.category not in ("Transfers",) or t.category_source == "user"
                or t.fingerprint in paired or is_others(t)):
            continue
        key = "in:" + t.fingerprint
        if key in dismissed:
            continue
        candidates = charge_candidates(t, transactions)
        # A split waiting for this person's share beats any guess (S-02).
        match = split_suggest(t, transactions, splits or {}, payer or {}) if splits else None
        # Then a purchase her friend's message names ("uber eats"), 2026-10-21.
        from .marks import memo_match
        said = None if match else memo_match(t, transactions)
        if said:
            who = (party(t) or {}).get("name") or "They"
            guess = {"action": "memo", "charge": said, "memo": memo(t)}
            on = date.fromisoformat(said["date"]).strftime("%b %-d")
            reason = (f"{who}’s message says “{memo(t)}”: {said['merchant']} on "
                      f"{on}, ${said['amount']:,.2f}.")
        elif match:
            guess = {"action": "split", "split": match}
            reason = (f"{match['name']} owes you {_money(match['owes'])} for "
                      f"{match['merchant']}.")
        elif candidates and candidates[0]["likely"]:
            top = candidates[0]
            guess = {"action": "payback", "charge": top}
            reason = (f"About a 1/{top['split']} share of {top['merchant']} "
                      f"(${top['amount']:,.2f}) a few days before.")
        elif candidates:
            guess = {"action": "payback", "charge": candidates[0]}
            reason = "Could be someone paying you back; more than one charge fits."
        else:
            guess = {"action": "own"}
            reason = "It didn’t pair with any of your accounts or charges."
        money_in.append({"key": key, "txn": _brief(t), "guess": guess,
                         "candidates": candidates, "reason": reason})

    # 3b. Money into a joint account from outside: whose was it?
    joint_in = []
    for t in live:
        if (not t.joint or t.amount >= 0 or t.date[:10] < since or t.repays
                or t.joint_from or t.share_set or t.fingerprint in paired):
            continue
        key = "joint:" + t.fingerprint
        if key in dismissed:
            continue
        joint_in.append({"key": key, "txn": _brief(t), "label": t.joint,
                         "people": list(t.joint_people or []),
                         "reason": f"It came into your account with {t.joint} from "
                                   "outside Pearl, so it could be yours or theirs."})

    # 3c. Who sent this? (R-09): an e-Transfer in with no name from the bank.
    # One transaction, one question (2026-10-22): an e-Transfer already asked
    # about as money in isn't listed again here; its card asks who sent it.
    asked_in = {it["txn"]["id"]: it for it in money_in}
    who_sent = []
    for t in live:
        if (t.amount >= 0 or t.date[:10] < since or not is_etransfer(t) or t.party
                or t.repays or is_others(t)):
            continue
        who = party(t)
        if who and who.get("name"):
            continue
        if t.fingerprint in asked_in:
            asked_in[t.fingerprint]["nameless"] = True
            continue
        key = "who:" + t.fingerprint
        if key in dismissed:
            continue
        who_sent.append({"key": key, "txn": _brief(t),
                         "reason": "Your bank didn’t say who sent it. A name helps Pearl match "
                                   "paybacks and makes it easy to find."})

    # 4. Income whose type is a guess.
    income = []
    for t in live:
        if not is_income(t) or t.date[:10] < since or t.income_type_source == "user":
            continue
        kind = kind_of(t)
        if kind not in ("other", "bonus"):
            continue
        key = "inc:" + t.fingerprint
        if key in dismissed:
            continue
        reason = ("Bigger than your usual paycheque." if kind == "bonus"
                  else "Pearl couldn’t tell what kind of income this is.")
        income.append({"key": key, "txn": _brief(t), "guess": kind,
                       "guess_label": KINDS[kind], "reason": reason})

    # 5. Months with a third paycheque.
    pay = cadence(transactions, today_d.isoformat())
    three = []
    for m in (pay or {}).get("three_pay_months", []):
        key = "pay3:" + m
        if key in dismissed:
            continue
        three.append({"key": key, "month": m, "paycheque": pay["paycheque"],
                      "monthly": pay["monthly"],
                      "reason": "Paid every two weeks, so two months a year hold a "
                                "third paycheque. Your plan uses a typical month: "
                                "one paycheque × 26 ÷ 12."})

    # 6. Likely duplicates: is this the same purchase? (THL-165 D-02). Asked
    # until answered, however old: until then the copy is counted once.
    dupes = duplicate_questions(transactions, found_on)

    # Skipped items stay listed, marked, and leave the badge (THL-213).
    keys = ({"u:" + t["id"] for t in groups["transfers"]}
            | {it["key"] for part in (unsure, money_in, joint_in, who_sent, income, three, dupes)
               for it in part})
    held = keys & (skipped or set())
    for t in groups["transfers"]:
        t["skipped"] = "u:" + t["id"] in held
    for part in (unsure, money_in, joint_in, who_sent, income, three, dupes):
        for it in part:
            it["skipped"] = it["key"] in held
    count = (groups["count"] + len(unsure) + len(money_in) + len(joint_in) + len(who_sent)
             + len(income) + len(three) + len(dupes)) - len(held)
    return {"count": count, "skipped": len(held), "unsorted": groups, "unsure_category": unsure,
            "money_in": money_in, "joint_in": joint_in, "who_sent": who_sent,
            "income_type": income, "three_pay_month": three,
            "duplicate": dupes, "kinds": KINDS}
