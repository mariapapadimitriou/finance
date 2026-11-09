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

from .analytics import is_others, share_amount, spend_amount
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


def _mine(t: Transaction) -> float:
    """What a charge shows as hers: what the month pays for, or her share when a
    piggy bank paid it all. The whole charge if neither says anything."""
    if t.amount <= 0:
        return abs(t.amount)
    return round(abs(spend_amount(t)) or abs(share_amount(t)) or t.amount, 2)


def _brief(t: Transaction, people=None) -> dict:
    from .categorize import is_generic_transfer_name
    who = party(t, people)
    return {"id": t.fingerprint, "date": t.date,
            "merchant": (who or {}).get("name") or t.merchant,
            "description": t.description, "amount": t.amount, "my_amount": _mine(t),
            "account_id": t.account_id, "account_name": t.account_label or "",
            "category": t.category, "logo": (t.raw or {}).get("logo_url") or "",
            # Whether a rule for this name could match the right rows: Always
            # (T-90) isn't offered for "Interac e-Transfer".
            "learnable": bool((t.merchant or "").strip()) and not is_generic_transfer_name(t.merchant),
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
          skipped: set[str] | None = None, recurring: list[dict] | None = None,
          me: str | None = None) -> dict:
    today_d = date.fromisoformat(today) if today else date.today()
    from .etransfers import known_people
    from .splits import same_person
    people = known_people(transactions, splits, payer)
    since = (today_d - timedelta(days=ASK_DAYS)).isoformat()
    dismissed = dismissed or set()
    live = [t for t in transactions if not t.excluded]

    # 1. Unsorted transfers.
    groups = unsorted_groups(live)

    # 1b. Recurring transfers (2026-10-27): the same amount out of one account
    # on a schedule is asked once, "Is this a recurring transfer?", instead of
    # once for each.
    from .recurring_transfers import series
    from .transfers import transfer_pairs
    by_id = {t.fingerprint: t for t in live}
    waiting = {t["id"] for t in groups["transfers"]}
    repeating = []
    for s in series(live, recurring or [], set(transfer_pairs(transactions, today=today_d.isoformat()))):
        key = s["key"]
        if key in dismissed:
            continue
        rows = [by_id[i] for i in s["ids"] if i in by_id]
        last = rows[-1]
        to = f" to {s['to']}" if s["to"] else ""
        repeating.append({
            "key": key, "txn": _brief(last), "series": s,
            "rows": [_brief(t) for t in reversed(rows)],
            # The ones still counted as spending until she answers.
            "asked": [i for i in s["ids"] if i in waiting],
            "reason": (f"${s['amount']:,.2f}{to}, {s['when']}: {s['count']} times "
                       f"since {date.fromisoformat(s['first']).strftime('%B %-d')}.")})
    asked = {i for it in repeating for i in it["asked"]}
    if asked:
        kept = [t for t in groups["transfers"] if t["id"] not in asked]
        groups = {**groups, "transfers": kept, "count": len(kept),
                  "total": round(sum(t["amount"] for t in kept), 2),
                  "groups": [g for g in groups["groups"] if not set(g["ids"]) <= asked]}

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
                or t.category not in ("Transfers",)
                # Answered: by her, or by a rule of hers (2026-10-22).
                or t.category_source in ("user", "merchant_override")
                # Who put a joint deposit in is answered (2026-10-23): asking
                # about it again as money in read as not sorted.
                or t.joint_from
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
            who = (party(t, people) or {}).get("name") or "They"
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
        # From someone else (2026-10-28): an e-Transfer or Wealthsimple Pay
        # with another person's name is asked "Is Anastasia paying you
        # back?" first, never guessed to be her own money moving.
        sent = party(t, people) or {}
        person = sent.get("name") if sent.get("direction") == "from" else None
        if person and me and same_person(person, me):
            person = None
        if person and guess["action"] == "own":
            guess = {"action": "person"}
            reason = f"From {person}. It didn’t pair with any of your accounts."
        money_in.append({"key": key, "txn": _brief(t, people), "guess": guess,
                         "candidates": candidates, "reason": reason,
                         **({"from": person} if person else {})})

    # 3a. Money back from a store she bought from, not yet called a refund:
    # it nets against the category meanwhile, so the question is which purchase.
    asked_money = {it["txn"]["id"] for it in money_in}
    store_names: dict[str, list] = {}
    for c in live:
        if c.amount > 0 and (c.merchant or "").strip():
            store_names.setdefault(" ".join(c.merchant.lower().split()), []).append(c)
    for t in live:
        if (t.amount >= 0 or t.date[:10] < since or t.fingerprint in asked_money or t.repays
                or getattr(t, "refund_of", None)
                or t.category in ("Transfers", "Saved", "Lent", "Borrowed", "Unsorted transfers")
                or (t.category == "Income" and "refund" not in (t.merchant or "").lower())
                or t.category_source in ("user", "merchant_override") or t.joint):
            continue
        # "Canada Computers Refund" is Canada Computers, whatever Pearl's patterns said.
        words = (t.merchant or "").lower().split()
        name = " ".join(w for w in words if w not in ("refund", "return", "credit"))
        bought = [c for c in store_names.get(name, []) if c.date[:10] <= t.date[:10]]
        # Nothing to refund: money that Pearl was quietly taking off spending.
        # On a card a refund can outlive the purchase in Pearl, so only money
        # into a bank account, or that nothing recognised, is asked about.
        if not bought and not (_is_bank(t) or (t.category or "Other") == "Other"):
            continue
        key = "in:" + t.fingerprint
        if key in dismissed:
            continue
        money_in.append({"key": key, "txn": _brief(t, people),
                         "guess": {"action": "refund" if bought else "unknown"}, "candidates": [],
                         "reason": ("Money back from a store you bought from." if bought
                                    else "Pearl had this as a refund, with nothing to refund.")})

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
                         "share": t.joint_split if t.joint_split is not None else t.joint_share,
                         "reason": f"It came into your account with {t.joint} from "
                                   "outside Pearl, so it could be yours or theirs."})

    # 3c. Who sent this? (R-09): an e-Transfer in with no name from the bank.
    # One transaction, one question (2026-10-22): an e-Transfer already asked
    # about as money in isn't listed again here; its card asks who sent it.
    asked_in = {it["txn"]["id"]: it for it in money_in}
    who_sent = []
    for t in live:
        if (t.amount >= 0 or t.date[:10] < since or not is_etransfer(t) or t.party
                or t.repays or is_others(t)
                # Already answered (2026-10-23): sorted by her or a rule of
                # hers, or matched to her own account. Asking who sent it
                # then reads as asking her to sort it again.
                or t.category_source in ("user", "merchant_override", "transfer_match", "destination")
                or t.fingerprint in paired):
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

    # 3d. Who sent this? on a payback already linked (SPLIT-22b, THL-181;
    # S-21u): linked from search, the web or the API, and credited to no one
    # because two shares, or none, are its amount. One row per payback, with
    # the chip above; it opens S-35c. Asked until answered, however old.
    if splits:
        from .splits import ASK_FROM, credit_question
        for t in live:
            # Only a payback dated from ASK_FROM can be credited to no one.
            if (t.amount >= 0 or not t.repays or t.date[:10] < ASK_FROM
                    or not any(c in splits for c in t.repays_all)):
                continue
            q = credit_question(t, transactions, splits, payer or {})
            key = "credit:" + t.fingerprint
            if q is None or key in dismissed:
                continue
            who_sent.append({"key": key, "txn": _brief(t),
                             "credit": {"paid_back": [x["merchant"] for x in q["purchases"]]},
                             "reason": "Pearl can’t tell who sent it, so it isn’t "
                                       "credited to anyone yet."})

    # 4. Income whose type is a guess.
    income = []
    from .categorize import merchant_key
    from .income import guess as income_guess
    paid_by: dict[str, int] = {}
    for t in live:
        if is_income(t):
            k = merchant_key(t.merchant or "")
            paid_by[k] = paid_by.get(k, 0) + 1
    refunds_asked = {it["txn"]["id"] for it in money_in if (it.get("guess") or {}).get("action") == "refund"}
    # A joint deposit's card asks what kind of income it is too, so one
    # deposit is one question, and counted once (2026-10-26).
    joint_asked = {it["txn"]["id"] for it in joint_in}
    for t in live:
        if not is_income(t) or t.date[:10] < since or t.income_type_source == "user" \
                or t.fingerprint in joint_asked or t.fingerprint in refunds_asked:
            continue
        kind = kind_of(t)
        # One payment from someone reads as pay but isn't a salary yet: asked
        # about, with the safer guess, however much it looks like a paycheque.
        once = (kind == "salary" and paid_by.get(merchant_key(t.merchant or ""), 0) == 1
                and t.category_source not in ("merchant_override", "user", "pay_rule"))
        if kind not in ("other", "bonus") and not once:
            continue
        key = "inc:" + t.fingerprint
        if key in dismissed:
            continue
        reason = ("Bigger than your usual paycheque." if kind == "bonus"
                  else "The first money from them, so Pearl can’t call it a salary." if once
                  else "Pearl couldn’t tell what kind of income this is.")
        if once:
            kind = "other"
        income.append({"key": key, "txn": _brief(t), "guess": kind,
                       "guess_label": KINDS[kind], "reason": reason})

    # 4b. What's left of a deposit split into parts (THL-291): "$172 left to
    # sort", asked as money in until she says what it is.
    from .parts import rest_questions
    for q in rest_questions(None, transactions):
        rt = q["t"]
        key = "in:" + rt.fingerprint
        if key in dismissed:
            continue
        money_in.append({"key": key, "txn": _brief(rt), "guess": {"action": "rest"},
                         "rest": {"whole": q["whole"], "sorted": q["sorted"]},
                         "reason": f"${-rt.amount:,.2f} left to sort from a ${q['whole']:,.2f} deposit."})

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
                                "third paycheque. Your plan counts two paycheques "
                                "a month, so the third isn’t a raise."})

    # 6. Likely duplicates: is this the same purchase? (THL-165 D-02). Asked
    # until answered, however old: until then the copy is counted once.
    dupes = duplicate_questions(transactions, found_on)

    # Skipped items stay listed, marked, and leave the badge (THL-213).
    keys = ({"u:" + t["id"] for t in groups["transfers"]}
            | {it["key"] for part in (repeating, unsure, money_in, joint_in, who_sent, income, three, dupes)
               for it in part})
    held = keys & (skipped or set())
    for t in groups["transfers"]:
        t["skipped"] = "u:" + t["id"] in held
    for part in (repeating, unsure, money_in, joint_in, who_sent, income, three, dupes):
        for it in part:
            it["skipped"] = it["key"] in held
    # One number for the whole app (2026-10-22): everything that needs a
    # look, skipped or not — the badge, Home, the Transactions banner, To
    # review and the Needs a look filter all show this. `open` is the part
    # not skipped, for To review's tabs.
    # A third paycheque is a note, not a question: nothing to sort, so it is
    # on Home and in no count (the redesign, decision 8).
    held -= {it["key"] for it in three}
    total = (groups["count"] + len(repeating) + len(unsure) + len(money_in) + len(joint_in)
             + len(who_sent) + len(income) + len(dupes))
    return {"count": total, "open": total - len(held), "skipped": len(held), "unsorted": groups,
            "recurring_transfer": repeating, "unsure_category": unsure,
            "money_in": money_in, "joint_in": joint_in, "who_sent": who_sent,
            "income_type": income, "three_pay_month": three,
            "duplicate": dupes, "kinds": KINDS}


def mixed_merchants(transactions: list[Transaction], confirmed: dict[str, str]) -> set[str]:
    """Merchants that don't sort one way, by merchant key: she has sorted them
    into more than one category, or the bank's own labels disagree, or her
    answers disagree with the guess still open. Yes on one of their guesses
    answers that row alone and saves no rule (T-97). Worked out from the
    ledger for any merchant: there is no list of stores."""
    from .categorize import is_guess, merchant_key
    said: dict[str, set[str]] = {}
    labels: dict[str, set[str]] = {}
    for t in transactions:
        key = merchant_key(t.merchant or "")
        if not key:
            continue
        category = confirmed.get(t.fingerprint) or (t.category if t.category_source == "user" else None)
        if category:
            said.setdefault(key, set()).add(category)
        elif t.amount > 0 and t.category_source == "issuer" and t.category and t.category != "Other":
            labels.setdefault(key, set()).add(t.category)
    out = {k for k, cats in said.items() if len(cats) > 1}
    out |= {k for k, cats in labels.items() if len(cats) > 1}
    for t in transactions:
        key = merchant_key(t.merchant or "")
        if key in said and t.amount > 0 and t.category_source != "user" \
                and t.fingerprint not in confirmed and is_guess(t) and t.category not in said[key]:
            out.add(key)
    return out


def for_store(st, today: str | None = None) -> dict:
    """The review as every screen sees it: one call, so one number."""
    found_on = {k: v["found_on"] for k, v in st.duplicates().items()}
    txns = st.all_transactions()
    # Her pay into a joint account is hers (2026-10-29): deposits a pay rule
    # made before that rule claimed them aren't asked "Who put this in?".
    from .pay_rules import claim_waiting
    claim_waiting(st, txns)
    # Bonuses measured per payer (2026-10-29): kinds saved before then are
    # worked out again, once, so paycheques guessed as bonuses stop being
    # asked about without waiting for new transactions.
    if st.setting("income_kinds_by_payer") != "1":
        from .income import apply_income_types
        if apply_income_types(st, txns):
            txns = st.all_transactions()
        st.set_setting("income_kinds_by_payer", "1")
    review = build(txns, today=today, dismissed=st.dismissed_reviews(),
                   splits=st.splits(), payer=st.payback_people(), found_on=found_on,
                   skipped=st.skipped_reviews(), recurring=st.recurring_transfers(), me=_me())
    from .categorize import merchant_key
    mixed = mixed_merchants(txns, st.confirmed_categories())
    names = {t.fingerprint: merchant_key(t.merchant or "") for t in txns}
    open_guesses = [it for it in review.get("unsure_category") or [] if not it.get("skipped")]
    by_merchant: dict[str, list[dict]] = {}
    for it in open_guesses:
        key = names.get(it["txn"]["id"])
        if key:
            by_merchant.setdefault(key, []).append(it)
    for it in review.get("unsure_category") or []:
        key = names.get(it["txn"]["id"])
        it["txn"]["mixed"] = key in mixed
        # What Yes moves is printed on the card: the merchant's other open
        # guesses, except where the merchant doesn't sort one way.
        it["siblings"] = ([] if key in mixed or not it["txn"].get("learnable") else
                          [o["txn"] for o in by_merchant.get(key, []) if o is not it])
    from .etransfers import canonical_names
    canon = canonical_names(txns)
    for part in ("money_in", "who_sent", "joint_in", "income_type"):
        for it in review.get(part) or []:
            full = canon.get(it["txn"].get("merchant") or "")
            if full:
                it["txn"]["merchant"] = full
                if it.get("from"):
                    it["from"] = full
    for row in (review.get("unsorted") or {}).get("transfers", []):
        full = canon.get(row.get("merchant") or "")
        if full:
            row["merchant"] = full
    from .pairs import annotate
    annotate(st, review, txns, today)
    # Questions about her plan (finance/checks.py): Yes or No cards.
    from . import checks
    from . import api as core_api
    review["checks"] = checks.build(st, txns, today or core_api._today_iso())
    open_checks = sum(1 for c in review["checks"] if not c["skipped"])
    review["count"] += len(review["checks"])
    review["open"] += open_checks
    review["skipped"] += len(review["checks"]) - open_checks
    from . import sorted_log
    from . import api as core
    day = today or core._today_iso()
    review["sorted_today"] = sorted_log.count_today(st, day)
    review["pearl_sorted"] = len(sorted_log.pearl_rows(st, review, day, ids_in))
    return review


def sorted_view(st, view: str, today: str) -> list[dict]:
    """Sorted today or Pearl sorted, as rows."""
    from . import sorted_log
    if view == "today":
        return sorted_log.today_rows(st, today)
    return sorted_log.pearl_rows(st, for_store(st, today), today, ids_in)


def _me() -> str | None:
    """Her own first name, so money she sent herself isn't asked about as
    someone paying her back."""
    try:
        from flask import g
        user = g.get("user")
    except RuntimeError:            # outside a request
        return None
    return getattr(user, "first_name", None) if user else None


def ids_in(review: dict) -> set[str]:
    """Every transaction the review asks about, for the list's Needs a look."""
    out = {t["id"] for t in (review.get("unsorted") or {}).get("transfers", [])}
    for it in review.get("recurring_transfer") or []:
        out.update(it.get("asked") or [])
    for part in ("unsure_category", "money_in", "joint_in", "who_sent", "income_type", "duplicate", "checks"):
        for it in review.get(part) or []:
            if it.get("txn"):
                out.add(it["txn"]["id"])
    return out
