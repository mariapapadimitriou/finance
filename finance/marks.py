"""What was this? (2026-10-14): one question, one list of answers, used from
the transactions list, the detail panel and Needs a look.

Every transaction answers "what was this?" with one of a short list of cases
that mean the same thing everywhere. Money out: a purchase (a category), a
bill, moved between her accounts, put into savings (and which account), lent,
shared with others, paying back something borrowed, a work expense to be
reimbursed, or not hers. Money in: pay, from her own account, out of savings,
someone paying her back, a refund, a reimbursement, money borrowed, a loan
repaid, or not hers.

`cases()` says which apply to a row, with what each needs (a category, an
account, a candidate purchase) and what it would do. `apply()` does one,
through the same tables everything else reads — a category, a share, a
payback, an exclusion — so the list and the month can never disagree. Each
answer can carry "Do this for every <merchant> from now on", which writes a
rule she can see and undo in Categories and rules.

Nothing here is a new kind of number: a refund nets in the category it is
linked to, a reimbursement is a repayment in full (both sides vanish from
totals), savings go to Saved, and Borrowed is Lent's mirror.
"""

from __future__ import annotations

from dataclasses import replace
from datetime import date, timedelta

from .categorize import CATEGORIES, NON_SPEND, group_of
from .income import KINDS as INCOME_KINDS
from .models import Transaction

WORK_REASON = "Work expense · waiting to be reimbursed"
NOT_MINE = "Not mine"
REIMBURSEMENT = "reimbursement"
# How far back a refund or a reimbursement looks for the purchase it is of.
REFUND_DAYS = 120

# The cases, in the order the sheet shows them. `needs` is what the sheet
# asks for before Save; `remember` is the rule the answer can write.
OUT_CASES = (
    {"key": "spending", "label": "A purchase", "needs": "category",
     "effect": "Counts as spending, in the category you pick.", "remember": "merchant"},
    {"key": "bill", "label": "A bill or subscription", "needs": "category",
     "effect": "Counts as spending, and as one of your bills.", "remember": "merchant"},
    {"key": "moved", "label": "Moved between my accounts", "needs": None,
     "effect": "Nothing changes in your numbers.", "remember": "destination"},
    {"key": "saved", "label": "Put into savings or investments", "needs": "account",
     "effect": "Adds to what you put away. Not spending.", "remember": "destination"},
    {"key": "saved_part", "label": "Part of it was put away", "needs": "amount",
     "effect": "The part you name is saved; the rest counts as spending.", "remember": None},
    {"key": "lent", "label": "Lent to someone", "needs": None,
     "effect": "Not spending: it comes back later.", "remember": "merchant"},
    {"key": "shared", "label": "Paid for a group", "needs": "split",
     "effect": "Only your share counts. Pearl watches for the others paying you back.",
     "remember": None},
    {"key": "paying_back", "label": "Paying back money I borrowed", "needs": "borrowed",
     "effect": "Not spending if what you bought is already in Pearl.", "remember": None},
    {"key": "work", "label": "A work expense I’ll be reimbursed for", "needs": None,
     "effect": "Left out until the reimbursement arrives; then both disappear.",
     "remember": None},
    {"key": "not_mine", "label": "Not mine", "needs": "reason",
     "effect": "Left out of everything.", "remember": "exclusion"},
)
IN_CASES = (
    {"key": "pay", "label": "My pay or other income", "needs": "income_kind",
     "effect": "Counts as income.", "remember": None},
    {"key": "own", "label": "From my own account", "needs": None,
     "effect": "Nothing changes in your numbers.", "remember": "destination"},
    {"key": "out_of_savings", "label": "Taken out of savings or investments", "needs": "account",
     "effect": "Comes off what you put away. Not income.", "remember": "destination"},
    {"key": "payback", "label": "Someone paying me back", "needs": "candidates",
     "effect": "Comes off the charge it was for. Not income.", "remember": None},
    {"key": "refund", "label": "A refund or return", "needs": "refund",
     "effect": "Comes off what you spent in that category. Not income.", "remember": None},
    {"key": "reimbursement", "label": "A reimbursement (work, insurance)", "needs": "candidates",
     "effect": "Cancels the expense it reimburses. Not income.", "remember": None},
    {"key": "borrowed", "label": "Money I borrowed", "needs": None,
     "effect": "Not income: you’ll pay it back.", "remember": None},
    {"key": "lent_back", "label": "Someone paying back money I lent", "needs": None,
     "effect": "Not income: it was yours before.", "remember": None},
    {"key": "joint_them", "label": "Someone else put this in", "needs": "person",
     "effect": "Pays for that much of this month’s joint spending.", "remember": "sender"},
    {"key": "not_mine", "label": "Not mine", "needs": "reason",
     "effect": "Left out of everything.", "remember": "exclusion"},
)

SAVINGS_SUBTYPES = {"savings", "money market", "hsa", "cash management", "hisa", "tfsa savings",
                    "tfsa", "rrsp", "fhsa", "resp", "brokerage", "rrif", "lira"}


def _key(merchant: str) -> str:
    return " ".join((merchant or "").lower().split())


def _brief(t: Transaction, names: dict[str, str] | None = None) -> dict:
    return {"id": t.fingerprint, "date": t.date[:10],
            "merchant": (names or {}).get(_key(t.merchant)) or t.merchant,
            "amount": round(abs(t.amount), 2), "category": t.category or "Other",
            "excluded": t.excluded or ""}


# ── Her accounts, as the sheet names them ────────────────────────────────

def account_labels(store) -> dict[str, str]:
    """{account id: what to call it}: her nickname, else the bank's name;
    hand-added accounts by the name she gave them."""
    out = {aid: r["label"] for aid, r in store.account_sync_rules().items()}
    for m in store.manual_accounts():
        out[m["account_id"]] = m["name"]
    for a in store.accounts():
        out.setdefault(a["account_id"], a.get("account_name") or a["account_id"])
    for aid, nick in store.account_nicknames().items():
        out[aid] = nick
    return out


def savings_accounts(store) -> list[dict]:
    """Where money can be put away: every savings or investment account Plaid
    pulled in, and every one she added by hand. If none were pulled in, she
    makes them on the Accounts page (that's the only way in)."""
    removed = {aid for aid, s in store.account_settings().items() if s["removed"]}
    labels = account_labels(store)
    out = []
    for aid, r in store.account_sync_rules().items():
        if aid in removed:
            continue
        kind = (r["account_type"] or "").lower()
        sub = (r["account_subtype"] or "").lower()
        if kind in ("investment", "brokerage") or sub in SAVINGS_SUBTYPES:
            out.append({"id": aid, "label": labels.get(aid, aid),
                        "kind": "investment" if kind in ("investment", "brokerage") else "savings",
                        "source": "linked"})
    for m in store.manual_accounts():
        if m["kind"] in ("savings", "investment"):
            out.append({"id": m["account_id"], "label": m["name"], "kind": m["kind"],
                        "source": "hand"})
    out.sort(key=lambda a: (a["source"] != "linked", a["label"].lower()))
    return out


# ── Candidates ───────────────────────────────────────────────────────────

def _days(a: str, b: str) -> int:
    return (date.fromisoformat(a[:10]) - date.fromisoformat(b[:10])).days


def refund_candidates(inflow: Transaction, txns: list[Transaction],
                      names: dict[str, str] | None = None) -> list[dict]:
    """Purchases this money might be a refund of: the same merchant first,
    then the same amount, within the last few months."""
    got = round(-inflow.amount, 2)
    key = _key(inflow.merchant)
    out = []
    for c in txns:
        if c.amount <= 0 or c.repays or c.fingerprint == inflow.fingerprint:
            continue
        if (c.category or "Other") in NON_SPEND or c.category == "Unsorted transfers":
            continue
        gap = _days(inflow.date, c.date)
        if gap < -3 or gap > REFUND_DAYS:
            continue
        same_name = _key(c.merchant) == key
        same_amount = abs(round(c.amount, 2) - got) < 0.01
        if not (same_name or same_amount):
            continue
        out.append(((0 if same_name and same_amount else 1 if same_name else 2, gap),
                    dict(_brief(c, names), exact=same_amount)))
    out.sort(key=lambda r: r[0])
    return [r for _, r in out[:6]]


def reimbursement_candidates(inflow: Transaction, txns: list[Transaction],
                             names: dict[str, str] | None = None) -> list[dict]:
    """Expenses this money might reimburse: ones left out as work expenses
    first, then any charge of the same amount in the last few months."""
    got = round(-inflow.amount, 2)
    out = []
    for c in txns:
        if c.amount <= 0 or c.repays or c.fingerprint == inflow.fingerprint:
            continue
        if (c.category or "Other") in NON_SPEND or c.category == "Unsorted transfers":
            continue
        gap = _days(inflow.date, c.date)
        if gap < -3 or gap > REFUND_DAYS:
            continue
        work = (c.excluded or "").lower().startswith("work expense")
        left = round(c.amount - (c.paid_back or 0.0), 2)
        same_amount = abs(left - got) < 0.01
        if not (work or same_amount):
            continue
        if got > left + 0.005:
            continue
        out.append(((0 if work and same_amount else 1 if work else 2, gap),
                    dict(_brief(c, names), exact=same_amount, work=work)))
    out.sort(key=lambda r: r[0])
    return [r for _, r in out[:6]]


def payback_candidates(inflow: Transaction, txns: list[Transaction], splits: dict,
                       payer: dict, names: dict[str, str] | None = None) -> list[dict]:
    """Charges a friend might be paying back: open splits first (with who
    owes what), then charges of which this is an even share."""
    from . import splits as sp
    from .review import charge_candidates
    out = []
    seen = set()
    options, _ = sp.for_inflow(inflow, txns, splits, payer)
    for o in options:
        seen.add((o["charge_id"], o["name"]))
        out.append({"id": o["charge_id"], "date": o["date"][:10], "merchant": o["merchant"],
                    "amount": round(float(o["owes"]), 2), "person": o["name"],
                    "split": True, "exact": abs(float(o["owes"]) + inflow.amount) < 0.01})
    for c in charge_candidates(inflow, txns):
        if (c["id"], None) in seen or any(o["id"] == c["id"] for o in out):
            continue
        out.append({"id": c["id"], "date": c["date"][:10],
                    "merchant": (names or {}).get(_key(c["merchant"])) or c["merchant"],
                    "amount": round(float(c["amount"]), 2), "person": None,
                    "split": False, "share": c["split"], "exact": False})
    return out[:8]


# ── Which cases apply ────────────────────────────────────────────────────

def current_case(t: Transaction, store_refunds: dict[str, str],
                 payback_kinds: dict[str, str]) -> str | None:
    """The case a row answers now, from what's recorded on it."""
    cat = t.category or "Other"
    if t.excluded:
        if (t.excluded or "").lower().startswith("work expense"):
            return "work"
        return "not_mine" if t.excluded != "Possible duplicate" else None
    if t.amount > 0:
        if t.joint and t.share_set and abs(t.my_share or 0.0) < 0.005:
            return "not_mine"
        if cat == "Transfers":
            return "moved"
        if cat == "Saved":
            return "saved"
        if t.invested:
            return "saved_part"
        if cat == "Lent":
            return "lent"
        if cat == "Borrowed":
            return "paying_back"
        if t.my_share is not None or t.paid_back:
            return "shared"
        if cat == "Unsorted transfers":
            return None
        return "spending"
    if t.repays:
        return "reimbursement" if payback_kinds.get(t.fingerprint) == REIMBURSEMENT else "payback"
    if cat == "Income":
        return "pay"
    if cat == "Transfers":
        if t.joint and t.joint_from == "them":
            return "joint_them"
        # A deposit Pearl paired with nothing is a question, not an answer.
        return "own" if t.category_source in ("user", "merchant_override") else None
    if cat == "Saved":
        return "out_of_savings"
    if cat == "Borrowed":
        return "borrowed"
    if cat == "Lent":
        return "lent_back"
    if t.fingerprint in store_refunds or cat not in NON_SPEND:
        return "refund"
    return None


def cases(store, t: Transaction, txns: list[Transaction]) -> dict:
    """Everything the sheet needs for one row."""
    from .transfers import destination
    names = store.merchant_names()
    refunds = store.refunds()
    kinds = store.payback_kinds()
    out_ = t.amount > 0
    where = destination(t)
    items = []
    for c in (OUT_CASES if out_ else IN_CASES):
        item = dict(c)
        if c["key"] == "joint_them" and not t.joint:
            continue
        if c["key"] == "shared" and t.joint:
            continue
        if c["key"] == "not_mine" and t.joint:
            item["label"] = f"{t.joint}’s, not mine"
            item["effect"] = "Counts as theirs, not yours."
            item["needs"] = None
            item["remember"] = None
        if c["remember"] == "destination":
            item["remember"] = "destination" if where else None
            item["remember_label"] = (f"Do this for every transfer to {where[1]} from now on"
                                      if where and out_ else
                                      f"Do this for every transfer from {where[1]} from now on"
                                      if where else "")
        elif c["remember"] == "merchant":
            item["remember_label"] = f"Do this for every {t.merchant} from now on"
        elif c["remember"] == "exclusion":
            item["remember_label"] = f"Leave out every {t.merchant} from now on"
        elif c["remember"] == "sender":
            item["remember_label"] = f"The same for every deposit from {t.merchant}"
        if c["needs"] == "candidates" and c["key"] == "payback":
            item["candidates"] = payback_candidates(t, txns, store.splits(),
                                                    store.payback_people(), names)
        elif c["needs"] == "candidates" and c["key"] == "reimbursement":
            item["candidates"] = reimbursement_candidates(t, txns, names)
        elif c["needs"] == "refund":
            item["candidates"] = refund_candidates(t, txns, names)
        items.append(item)
    return {
        "id": t.fingerprint,
        "direction": "out" if out_ else "in",
        "current": current_case(t, refunds, kinds),
        "cases": items,
        "accounts": savings_accounts(store),
        "saved_to": store.saved_to().get(t.fingerprint),
        "income_kinds": INCOME_KINDS,
        "income_kind": t.income_type,
        "joint": t.joint or "",
        "joint_people": list(t.joint_people or []),
        "tags": store.tags().get(t.fingerprint, []),
        "categories": [c for c in CATEGORIES if c not in NON_SPEND and c != "Unsorted transfers"],
    }


# ── Applying one ─────────────────────────────────────────────────────────

class Problem(Exception):
    """Something the person needs to fix before the answer can be saved."""


def _category(body: dict) -> str:
    cat = body.get("category")
    if cat not in CATEGORIES or cat in NON_SPEND or cat == "Unsorted transfers":
        raise Problem("Choose a category.")
    return cat


def _remember_destination(store, t: Transaction, category: str, body: dict) -> bool:
    from .transfers import destination
    where = destination(t) if body.get("remember") else None
    if where:
        store.set_destination(where[0], category, where[1])
        return True
    return False


def _tick_bill(store, t: Transaction, category: str, today: date) -> None:
    """Make this merchant one of her bills in Income and bills: ticked when
    Pearl already sees it recurring, added as a monthly bill when it doesn't."""
    from . import income_bills as ib
    state = ib.load(store)
    known = {r["key"]: r for r in ib.bills(store.all_transactions(), today, state)}
    key = t.merchant
    if key in known and known[key]["source"] != "added":
        state["bills"].setdefault(key, {})["state"] = "yes"
    elif not any(ib.clean_name(b.get("name")) == ib.clean_name(t.merchant)
                 for b in state.get("added") or []):
        nxt = date.fromisoformat(t.date[:10])
        nxt = (nxt.replace(day=1) + timedelta(days=32)).replace(day=min(nxt.day, 28))
        while nxt < today:
            nxt = (nxt.replace(day=1) + timedelta(days=32)).replace(day=min(nxt.day, 28))
        bill, error = ib.bill_from({"name": t.merchant, "amount": abs(t.amount),
                                    "cadence": "monthly", "next": nxt.isoformat()})
        if bill:
            bill["category"] = category
            state["added"].append({"id": ib.next_id(state, "b"), **bill})
    state["bills_on"] = state["bills_on"] or today.isoformat()
    ib.save(store, state)


def apply(store, t: Transaction, body: dict, today: date) -> dict:
    """Do one case. Returns what to say and how to undo the parts a change
    of category doesn't cover (`marks`, for `undo_extras`)."""
    case = str(body.get("case") or "")
    out_ = t.amount > 0
    keys = {c["key"] for c in (OUT_CASES if out_ else IN_CASES)}
    if case not in keys:
        raise Problem("Say what this was.")
    old_cat = t.category or "Other"
    marks: dict = {}
    remember = False
    title = ""
    cat_to = old_cat

    def recat(category: str, always: bool = False) -> None:
        nonlocal cat_to, remember
        cat_to = category
        if always:
            store.set_override(t.merchant, category)
            remember = True
        else:
            store.set_transaction_category(t.fingerprint, category)

    def un_exclude() -> None:
        if t.excluded and t.excluded != "Possible duplicate":
            marks.setdefault("exclusions", {})[t.fingerprint] = t.excluded
            store.include(t.fingerprint)

    def set_saved_to() -> None:
        aid = str(body.get("account") or "") or None
        if aid and aid not in {a["id"] for a in savings_accounts(store)}:
            raise Problem("Choose one of your savings or investment accounts.")
        marks.setdefault("saved_to", {})[t.fingerprint] = store.saved_to().get(t.fingerprint)
        store.set_saved_to(t.fingerprint, aid)

    if case == "spending":
        cat = _category(body)
        un_exclude()
        recat(cat, bool(body.get("remember")))
        title = f"Moved to {cat}."
    elif case == "bill":
        cat = _category(body)
        un_exclude()
        recat(cat, bool(body.get("remember")))
        _tick_bill(store, t, cat, today)
        title = f"Counted as a bill, in {cat}."
    elif case in ("moved", "own"):
        un_exclude()
        if not _remember_destination(store, t, "Transfers", body):
            recat("Transfers")
        else:
            cat_to, remember = "Transfers", True
        title = "Sorted as moved between your accounts."
    elif case in ("saved", "out_of_savings"):
        un_exclude()
        set_saved_to()
        if not _remember_destination(store, t, "Saved", body):
            recat("Saved")
        else:
            cat_to, remember = "Saved", True
        label = account_labels(store).get(str(body.get("account") or ""), "")
        title = (f"Put away to {label}." if label and out_ else "Put away."
                 if out_ else f"Taken out of {label}." if label else "Taken out of savings.")
    elif case == "saved_part":
        try:
            amount = round(float(body.get("amount")), 2)
        except (TypeError, ValueError):
            raise Problem("Say how much was put away.") from None
        if not 0 < amount < t.amount - 0.004:
            raise Problem("The saved part has to be less than the whole transaction.")
        marks.setdefault("invested", {})[t.fingerprint] = t.invested
        store.set_invested(t.fingerprint, amount)
        if old_cat in NON_SPEND or old_cat == "Unsorted transfers":
            recat(_category(body))
        set_saved_to()
        title = f"${amount:,.2f} of it put away."
    elif case == "lent":
        un_exclude()
        recat("Lent", bool(body.get("remember")))
        title = "Sorted as money you lent."
    elif case == "lent_back":
        un_exclude()
        recat("Lent")
        title = "Sorted as a loan paid back to you."
    elif case == "borrowed":
        un_exclude()
        recat("Borrowed")
        title = "Sorted as money you borrowed."
    elif case == "paying_back":
        un_exclude()
        if body.get("counted") is False:
            recat(_category(body))
            title = f"Moved to {cat_to}."
        else:
            recat("Borrowed")
            title = "Sorted as paying back what you borrowed."
    elif case == "work":
        marks.setdefault("exclusions", {})[t.fingerprint] = t.excluded
        store.exclude(t.fingerprint, WORK_REASON)
        title = "Left out until it’s reimbursed."
    elif case == "not_mine":
        if t.joint:
            marks.setdefault("shares", {})[t.fingerprint] = t.my_share if t.share_set else None
            store.set_share(t.fingerprint, 0.0)
            title = f"Counted as {t.joint}’s."
        else:
            reason = " ".join(str(body.get("reason") or "").split())[:200] or NOT_MINE
            marks.setdefault("exclusions", {})[t.fingerprint] = t.excluded
            store.exclude(t.fingerprint, reason)
            if body.get("remember"):
                store.add_exclusion_rule({"keyword": t.merchant, "reason": reason,
                                          "account_id": None, "counterparty": None,
                                          "date_from": None, "date_to": None,
                                          "amount_min": None, "amount_max": None})
                remember = True
            title = "Left out."
    elif case == "pay":
        kind = body.get("income_kind") or "other"
        if kind not in INCOME_KINDS:
            raise Problem("Choose a kind of income.")
        un_exclude()
        marks.setdefault("income_type", {})[t.fingerprint] = (
            t.income_type if t.income_type_source == "user" else None)
        if old_cat != "Income":
            recat("Income")
        store.set_income_type(t.fingerprint, kind, "user")
        title = f"Counted as income: {INCOME_KINDS[kind]}."
    elif case == "payback":
        charge_id = str(body.get("charge") or "")
        charge = next((x for x in store.all_transactions() if x.fingerprint == charge_id), None)
        if charge is None or charge.amount <= 0:
            raise Problem("Pick the charge it pays back.")
        un_exclude()
        marks.setdefault("paybacks", {})[t.fingerprint] = {
            "charge": t.repays, "kind": store.payback_kinds().get(t.fingerprint)}
        person = " ".join(str(body.get("person") or "").split()) or None
        store.link_payback(charge_id, t.fingerprint, person)
        store.set_payback_kind(t.fingerprint, None)
        title = f"Linked to {charge.merchant}. Not income."
    elif case == "reimbursement":
        charge_id = str(body.get("charge") or "")
        charge = next((x for x in store.all_transactions() if x.fingerprint == charge_id), None)
        if charge is None or charge.amount <= 0:
            raise Problem("Pick the expense it reimburses.")
        un_exclude()
        if charge.excluded and charge.excluded != "Possible duplicate":
            marks.setdefault("exclusions", {})[charge.fingerprint] = charge.excluded
            store.include(charge.fingerprint)
        marks.setdefault("paybacks", {})[t.fingerprint] = {
            "charge": t.repays, "kind": store.payback_kinds().get(t.fingerprint)}
        store.link_payback(charge_id, t.fingerprint, None)
        store.set_payback_kind(t.fingerprint, REIMBURSEMENT)
        title = f"Reimbursement for {charge.merchant}. Both are out of your numbers."
    elif case == "refund":
        charge_id = str(body.get("charge") or "")
        charge = next((x for x in store.all_transactions() if x.fingerprint == charge_id),
                      None) if charge_id else None
        if charge_id and charge is None:
            raise Problem("Pick the purchase it refunds.")
        un_exclude()
        cat = charge.category if charge else _category(body)
        marks.setdefault("refunds", {})[t.fingerprint] = store.refunds().get(t.fingerprint)
        store.link_refund(t.fingerprint, charge.fingerprint if charge else None)
        recat(cat)
        title = (f"Refund of {charge.merchant}. Comes off {cat}." if charge
                 else f"Refund. Comes off {cat}.")
    elif case == "joint_them":
        from .joint import THEM
        person = " ".join(str(body.get("person") or "").split()) or None
        if person and person not in (t.joint_people or []):
            raise Problem("Choose one of the people you share this account with.")
        marks.setdefault("joint_from", {})[t.fingerprint] = {
            "who": t.joint_from, "person": t.joint_person}
        store.set_joint_deposit(t.fingerprint, THEM, person)
        if body.get("remember"):
            store.set_joint_deposit_rule(t.account_id, t.merchant, THEM, person)
            remember = True
        if old_cat == "Income":
            recat("Transfers")
        title = f"{person or t.joint} put this in."
    if body.get("tags") is not None:
        tags = clean_tags(body.get("tags"))
        marks.setdefault("tags", {})[t.fingerprint] = store.tags().get(t.fingerprint, [])
        store.set_tags(t.fingerprint, tags)
    return {"title": title, "from": old_cat, "to": cat_to, "remember": remember,
            "marks": marks}


def preview(t: Transaction, txns: list[Transaction], body: dict) -> list[Transaction] | None:
    """The ledger as it would be after `body`, for the impact line — or None
    when the case doesn't move a category or an exclusion."""
    case = str(body.get("case") or "")
    new = None
    if case in ("spending", "bill"):
        cat = body.get("category")
        new = replace(t, category=cat, category_source="user", excluded=None) if cat in CATEGORIES \
            else None
    elif case in ("moved", "own"):
        new = replace(t, category="Transfers", category_source="user", excluded=None)
    elif case in ("saved", "out_of_savings"):
        new = replace(t, category="Saved", category_source="user", excluded=None)
    elif case in ("lent", "lent_back"):
        new = replace(t, category="Lent", category_source="user", excluded=None)
    elif case in ("borrowed",) or (case == "paying_back" and body.get("counted") is not False):
        new = replace(t, category="Borrowed", category_source="user", excluded=None)
    elif case == "paying_back":
        cat = body.get("category")
        new = replace(t, category=cat, category_source="user", excluded=None) if cat in CATEGORIES \
            else None
    elif case == "pay":
        new = replace(t, category="Income", category_source="user", excluded=None)
    elif case in ("work", "not_mine") and not t.joint:
        new = replace(t, excluded=WORK_REASON if case == "work" else NOT_MINE)
    elif case == "refund":
        cat = body.get("category")
        charge = next((x for x in txns if x.fingerprint == str(body.get("charge") or "")), None)
        cat = charge.category if charge else cat
        new = replace(t, category=cat, category_source="user", excluded=None) if cat in CATEGORIES \
            else None
    if new is None:
        return None
    return [new if x.fingerprint == t.fingerprint else x for x in txns]


# ── Categories she never uses ────────────────────────────────────────────

HIDDEN_SETTING = "hidden_categories"


def hidden_categories(store) -> set[str]:
    """Categories kept out of the pickers (Profile › Categories and rules).
    A row already in one keeps it; only new choices leave it out."""
    import json
    try:
        data = json.loads(store.setting(HIDDEN_SETTING) or "[]")
    except (TypeError, ValueError):
        return set()
    return {c for c in data if c in CATEGORIES} if isinstance(data, list) else set()


def set_hidden(store, category: str, hidden: bool) -> set[str]:
    import json
    if category not in CATEGORIES or category in NON_SPEND \
            or category in ("Unsorted transfers", "Other"):
        raise Problem("Only a spending category can be hidden.")
    out = hidden_categories(store)
    out = (out | {category}) if hidden else (out - {category})
    store.set_setting(HIDDEN_SETTING, json.dumps(sorted(out)))
    return out


# ── Tags ─────────────────────────────────────────────────────────────────

TAG_MAX = 30
TAGS_MAX = 8


def clean_tags(raw) -> list[str]:
    """Tags as typed, trimmed, no repeats, a few at most."""
    if not isinstance(raw, list):
        raise Problem("Tags are a list of words.")
    out: list[str] = []
    for item in raw:
        tag = " ".join(str(item or "").split())[:TAG_MAX]
        if tag and tag.lower() not in {x.lower() for x in out}:
            out.append(tag)
    return out[:TAGS_MAX]


# ── Undo, for what a change of category doesn't cover ────────────────────

def undo_marks(store, marks: dict) -> int:
    """Put back what `apply` recorded in `marks`. Returns how many."""
    if not isinstance(marks, dict):
        raise Problem("Nothing to undo.")
    known = {t.fingerprint: t for t in store.all_transactions()}
    n = 0
    for tid, reason in (marks.get("exclusions") or {}).items():
        if tid not in known:
            continue
        if reason:
            store.exclude(tid, str(reason)[:200])
        else:
            store.include(tid)
        n += 1
    for tid, aid in (marks.get("saved_to") or {}).items():
        if tid in known:
            store.set_saved_to(tid, aid or None)
            n += 1
    for tid, cid in (marks.get("refunds") or {}).items():
        if tid in known:
            store.link_refund(tid, cid or None)
            n += 1
    for tid, was in (marks.get("paybacks") or {}).items():
        if tid not in known or not isinstance(was, dict):
            continue
        if was.get("charge"):
            store.link_payback(was["charge"], tid)
            store.set_payback_kind(tid, was.get("kind"))
        else:
            store.unlink_payback(tid)
        n += 1
    for tid, share in (marks.get("shares") or {}).items():
        if tid in known:
            store.set_share(tid, None if share is None else float(share))
            n += 1
    for tid, amount in (marks.get("invested") or {}).items():
        if tid in known:
            store.set_invested(tid, None if amount is None else float(amount))
            n += 1
    for tid, kind in (marks.get("income_type") or {}).items():
        if tid in known:
            store.set_income_type(tid, kind if kind in INCOME_KINDS else None,
                                  "user" if kind else "rule")
            n += 1
    for tid, was in (marks.get("joint_from") or {}).items():
        if tid in known and isinstance(was, dict):
            store.set_joint_deposit(tid, was.get("who"), was.get("person"))
            n += 1
    for tid, tags in (marks.get("tags") or {}).items():
        if tid in known and isinstance(tags, list):
            store.set_tags(tid, clean_tags(tags))
            n += 1
    return n
