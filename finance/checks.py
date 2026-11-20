"""Questions Pearl asks about her plan, not about one transaction's category
(the logic review, 2026-11-07). Each one is a Yes or No card in Needs a look
and Quick sort, tied to the transaction that raised it.

* Is this where you save? (decision 2; the only way to Saved since
  2026-11-20): once per savings or investment account she moves money into,
  linked or added by hand. Until she says Yes, money moved there is a
  transfer, whatever the bank calls the account. Yes counts money moved
  there as put away, and money moved back out as taken out of savings. An
  account picked for her Anchor counts without asking.
* Still paid by Acme? (decision 8): her confirmed pay hasn't arrived for two
  of its cycles. Pearl keeps expecting it until she answers; No stops it.
"""

from __future__ import annotations

import json
from datetime import date, timedelta

# Your plan is parked with Save (product owner, 2026-11-18): while it is,
# Needs a look and Quick sort don't ask its question (Still paid by…?), so
# nothing counts it. The iPhone app's switch is YourPlanGate.shown. "Is X
# where you save?" is asked regardless (2026-11-20): it decides Saved.
PARKED = True
SAVERS_KEY = "saver_accounts"
NOT_SAVERS_KEY = "saver_no"
# Two missed cycles, and a few days' grace, before Pearl asks.
STALE_DAYS = {"weekly": 16, "biweekly": 33, "semimonthly": 36, "monthly": 66}
SAVINGS_SUBTYPES = {"savings", "money market", "hisa", "cash management", "tfsa savings",
                    "tfsa", "rrsp", "fhsa"}
INVESTMENT_TYPES = {"investment", "brokerage"}


def _list(st, key: str) -> list[str]:
    try:
        out = json.loads(st.setting(key) or "[]")
    except (TypeError, ValueError):
        return []
    return out if isinstance(out, list) else []


def savers(st) -> set[str]:
    """Accounts money is put away in: the ones she said yes to, and the ones
    she picked for her Anchor."""
    return set(_list(st, SAVERS_KEY)) | set(_list(st, "anchor_accounts"))


def _money(x: float) -> str:
    return f"${abs(x):,.0f}" if abs(x) == round(abs(x)) else f"${abs(x):,.2f}"


def saving_accounts(st) -> dict[str, str]:
    """{account id: name} of every account money could be put away in: a
    linked savings or investment account, or one she added by hand as
    savings or an investment (named in transfers by its digits)."""
    out: dict[str, str] = {}
    removed = {aid for aid, s in st.account_settings().items() if s.get("removed")}
    for aid, rule in st.account_sync_rules().items():
        if aid in removed:
            continue
        kind = (rule.get("account_type") or "").lower()
        sub = (rule.get("account_subtype") or "").lower()
        if sub in SAVINGS_SUBTYPES or kind in INVESTMENT_TYPES:
            out[aid] = rule.get("nickname") or rule.get("label") or rule.get("account_name") or "This account"
    for m in st.manual_accounts():
        if m.get("kind") in ("savings", "investment"):
            out[m["account_id"]] = m.get("name") or "This account"
    return out


def _moved_in(txns, aid: str, since: str, accounts: dict) -> list:
    """Money moved into `aid` since `since`: arrivals in the account itself,
    and outflows elsewhere that name it (an investment account's own
    activity isn't in Plaid's Transactions, so the naming side is all
    there is), oldest first."""
    from .transfers import own_account
    moved = []
    for t in txns:
        if t.date[:10] < since or t.category not in ("Transfers", "Saved", "Unsorted transfers"):
            continue
        if t.account_id == aid and t.amount < 0:
            moved.append(t)
        elif t.amount > 0 and t.account_id != aid and (own_account(t, accounts) or (None,))[0] == aid:
            moved.append(t)
    return sorted(moved, key=lambda t: t.date)


def build(st, txns, today: str, parked: bool = False) -> list[dict]:
    """The questions to ask. `parked`: Your plan's own (Still paid by…?)
    stays unasked while Your plan is."""
    from .review import _brief
    from .transfers import linked_accounts
    out = []
    since = (date.fromisoformat(today) - timedelta(days=60)).isoformat()
    decided = savers(st) | set(_list(st, NOT_SAVERS_KEY))
    dismissed = st.dismissed_reviews()
    skipped = st.skipped_reviews()
    accounts = linked_accounts(st)
    for aid, name in saving_accounts(st).items():
        if aid in decided:
            continue
        key = f"chk:saver:{aid}"
        if key in dismissed:
            continue
        moved = _moved_in(txns, aid, since, accounts)
        if not moved:
            continue
        last = moved[-1]
        out.append({"key": key, "txn": _brief(last), "skipped": key in skipped,
                    "pair": {"question": f"Is {name} where you save?",
                             "evidence": f"You moved {_money(last.amount)} into it on "
                                         f"{date.fromisoformat(last.date[:10]).strftime('%b %-d')}.",
                             "line": "Yes counts money moved there as put away.", "other": ""}})
    # Money sent to an investment firm by name, or anywhere a rule could
    # learn (`destination`), with no rule yet: asked once per destination.
    from .categorize import looks_like_saving
    from .transfers import destination
    rules = st.destinations()
    asked_dest: set[str] = set()
    for t in sorted((t for t in txns if t.amount > 0 and t.date[:10] >= since
                     and t.category in ("Transfers", "Saved", "Unsorted transfers")
                     and looks_like_saving(t.merchant, t.description)),
                    key=lambda t: t.date, reverse=True):
        where = destination(t)
        if not where or where[0] in rules or where[0] in asked_dest:
            continue
        asked_dest.add(where[0])
        key = f"chk:dest:{where[0]}"
        if key in dismissed:
            continue
        name = where[1] or t.merchant or "there"
        out.append({"key": key, "txn": _brief(t), "skipped": key in skipped,
                    "pair": {"question": f"Is {name} where you save?",
                             "evidence": f"You sent {_money(t.amount)} there on "
                                         f"{date.fromisoformat(t.date[:10]).strftime('%b %-d')}.",
                             "line": "Yes counts money sent there as put away.", "other": ""}})
    if parked:
        return out
    from . import income_bills as ib
    state = ib.load(st)
    day = date.fromisoformat(today)
    for p in state.get("pays") or []:
        limit = STALE_DAYS.get(p.get("cadence"))
        if not limit or not p.get("payer"):
            continue
        theirs = sorted((t for t in txns if t.amount < 0 and (t.merchant or t.description) == p["payer"]),
                        key=lambda t: t.date)
        if not theirs:
            continue
        last = theirs[-1]
        quiet = (day - date.fromisoformat(last.date[:10])).days
        checked = p.get("checked_on")
        if quiet <= limit or (checked and (day - date.fromisoformat(checked)).days <= limit):
            continue
        key = f"chk:pay:{p['id']}"
        if key in dismissed:
            continue
        out.append({"key": key, "txn": _brief(last), "skipped": key in skipped,
                    "pair": {"question": f"Still paid by {p.get('name') or p['payer']}?",
                             "evidence": f"Nothing from {p['payer']} since "
                                         f"{date.fromisoformat(last.date[:10]).strftime('%b %-d')}.",
                             "line": "Yes keeps it in your Allowance. No stops expecting it.", "other": ""}})
    return out


def answer(st, key: str, yes: bool, today: str) -> str | None:
    """What she said. Returns the line to show, or None for an unknown key."""
    kind, _, ref = key.partition(":")[2].partition(":")
    if kind == "saver":
        target = SAVERS_KEY if yes else NOT_SAVERS_KEY
        st.set_setting(target, json.dumps(sorted(set(_list(st, target)) | {ref})))
        from .transfers import apply_transfer_matches
        apply_transfer_matches(st)
        return "Money moved there counts as put away." if yes else "Pearl won’t count it as saving."
    if kind == "dest":
        # Her answer is the destination rule ("always Saved for Questrade"),
        # so it holds for every transfer there and she isn't asked again.
        from .transfers import apply_transfer_matches, destination
        label = next((w[1] for t in st.all_transactions() if t.amount > 0
                      for w in [destination(t)] if w and w[0] == ref), "")
        st.set_destination(ref, "Saved" if yes else "Transfers", label)
        apply_transfer_matches(st)
        return "Money sent there counts as put away." if yes else "Pearl won’t count it as saving."
    if kind == "pay":
        from . import income_bills as ib
        state = ib.load(st)
        pay = next((p for p in state["pays"] if p["id"] == ref), None)
        if pay is None:
            return None
        if yes:
            pay["checked_on"] = today
            line = f"Still expecting {pay.get('name') or pay['payer']}."
        else:
            state["pays"] = [p for p in state["pays"] if p["id"] != ref]
            line = f"{pay.get('name') or pay['payer']} isn’t expected any more."
        ib.save(st, state)
        return line
    return None
