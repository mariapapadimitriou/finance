"""Joint accounts: whose money is whose.

2026-10-23, as she uses them: an account either splits every purchase by
her share (her sister's, 50/50), or every purchase is hers until she marks
one as someone else's (her family's, where it isn't even). Either way each
deposit is asked about: hers, or theirs ("Joint added"). What the others
put in no longer lowers her share of the month by itself; the ratio below
is kept for reference but not applied.

A joint account's spending is hers by default — the account is in Pearl
because she uses it. Setting her share on the account (AM-04) splits every
row by that percent instead, and a charge she marks as the other person's
counts as nothing of hers.

Money that comes into a joint account from outside Pearl is asked about,
because two different things look the same: her own money from an account
Pearl can't see, and the other person's contribution. Until she answers it
counts as nothing.

* "me": hers. Pay stays her income ("Whose pay is this?", T-33); anything
  else is her own money moving between her pockets — not income.
* "both": pay that's both of theirs (T-33's "Both of us"): her share of it,
  the account's percent, or half when the account has none.
* "them": the other person's money, which pays for that much of the month's
  joint spending on that account. With $600 of joint spending in October
  and $200 put in by her sister, a third of each October charge was paid by
  her sister, so two thirds of each is hers. More put in than spent leaves
  her share at nothing, never below.

An answer can be for one deposit or for every deposit from that sender into
that account. The ratio is worked out here, per account and month, and each
row is given it as it loads (`Store._loaded`, `Transaction.from_row`).
"""

from __future__ import annotations

from .categorize import is_spend_category

ME, THEM, BOTH = "me", "them", "both"


# Paybacks 2 (approved 2026-11-16, decision 2): money the other owner took
# out of the joint account to pay her back didn't pay for joint spending, so
# it comes OFF their "them" deposits for that month. The sign is this one
# constant; +1 would count it toward them instead.
THEIR_PAYBACK_SIGN = -1


def payback_reduces_their_contribution(theirs: float, paid_back: float) -> float:
    """What the other owners put in that month once `paid_back` (money out
    of the joint account that paid her back, TP-03) is taken into account."""
    return theirs + THEIR_PAYBACK_SIGN * paid_back


def their_contributions(store) -> dict[tuple[str, str], float]:
    """{(account_id, "YYYY-MM"): what the other owners put in} on joint
    accounts without a set share: deposits answered "them", less what they
    took out to pay her back (`payback_reduces_their_contribution`)."""
    with store.conn() as c:
        rows = c.execute(
            """SELECT t.account_id AS account_id, SUBSTR(t.date, 1, 7) AS month,
                      SUM(CASE WHEN t.amount < 0 AND COALESCE(jdx.who, jrx.who) = 'them'
                               THEN -t.amount ELSE 0 END) AS theirs
                 FROM transactions t
                 JOIN joint_accounts jax ON jax.account_id = t.account_id
                                        AND jax.share IS NULL
                 LEFT JOIN joint_deposits jdx ON jdx.txn_id = t.id
                 LEFT JOIN joint_deposit_rules jrx ON jrx.account_id = t.account_id
                                                  AND jrx.sender_key = LOWER(t.merchant)
                WHERE NOT EXISTS (SELECT 1 FROM txn_exclusions e
                                   WHERE e.txn_id = t.id AND e.kept = 0)
                GROUP BY t.account_id, SUBSTR(t.date, 1, 7)""").fetchall()
        back = c.execute(
            """SELECT t.account_id AS account_id, SUBSTR(t.date, 1, 7) AS month,
                      SUM(t.amount) AS paid_back
                 FROM txn_joint_paybacks p
                 JOIN transactions t ON t.id = p.txn_id
                 JOIN joint_accounts jax ON jax.account_id = t.account_id
                                        AND jax.share IS NULL
                GROUP BY t.account_id, SUBSTR(t.date, 1, 7)""").fetchall()
    out = {(r["account_id"], r["month"]): float(r["theirs"] or 0) for r in rows}
    for r in back:
        key = (r["account_id"], r["month"])
        out[key] = round(payback_reduces_their_contribution(out.get(key, 0.0), float(r["paid_back"] or 0)), 2)
    return out


def ratios(store) -> dict[tuple[str, str], float]:
    """{(account_id, "YYYY-MM"): the part of that month's joint spending on
    that account that is hers}, for joint accounts without a set share.
    What the others put in is `their_contributions` (Paybacks 2)."""
    with store.conn() as c:
        rows = c.execute(
            """SELECT t.account_id AS account_id, SUBSTR(t.date, 1, 7) AS month,
                      t.category AS category,
                      SUM(CASE WHEN t.amount > 0 AND sh.txn_id IS NULL
                               AND jmx.merchant_key IS NULL THEN t.amount ELSE 0 END)
                          AS spent,
                      SUM(CASE WHEN t.amount < 0 AND COALESCE(jdx.who, jrx.who) = 'them'
                               THEN -t.amount ELSE 0 END) AS theirs
                 FROM transactions t
                 JOIN joint_accounts jax ON jax.account_id = t.account_id
                                        AND jax.share IS NULL
                 LEFT JOIN txn_shares sh ON sh.txn_id = t.id
                 LEFT JOIN joint_mine jmx ON jmx.merchant_key = LOWER(t.merchant)
                 LEFT JOIN joint_deposits jdx ON jdx.txn_id = t.id
                 LEFT JOIN joint_deposit_rules jrx ON jrx.account_id = t.account_id
                                                  AND jrx.sender_key = LOWER(t.merchant)
                WHERE NOT EXISTS (SELECT 1 FROM txn_exclusions e
                                   WHERE e.txn_id = t.id AND e.kept = 0)
                GROUP BY t.account_id, SUBSTR(t.date, 1, 7), t.category""").fetchall()
    spent: dict[tuple[str, str], float] = {}
    for r in rows:
        key = (r["account_id"], r["month"])
        if is_spend_category(r["category"] or "Other"):
            spent[key] = spent.get(key, 0.0) + float(r["spent"] or 0)
    theirs = their_contributions(store)
    out = {}
    for key in set(spent) | set(theirs):
        s, p = spent.get(key, 0.0), theirs.get(key, 0.0)
        out[key] = 1.0 if s <= 0 or p <= 0 else max(0.0, 1.0 - p / s)
    return out


def my_share(amount: float, *, category: str | None, mine: bool, share: float | None,
             who: str | None, ratio: float | None) -> float:
    """Her part of one row on a joint account she hasn't set a share for by
    hand. `mine` is a name she said is always hers; `share` the account's
    percent (AM-04); `who` who put money in; `ratio` the month's (above)."""
    if mine:
        return amount
    # Money in is hers only once she says so (2026-10-23), split or not:
    # with her sister every purchase is 50/50 but they each put money in
    # separately, so a deposit is never half hers.
    if amount < 0:
        if who == BOTH:
            return round(amount * float(share if share is not None else 50) / 100.0, 2)
        return amount if who == ME else 0.0
    # "Split every purchase": her share of each one.
    if share is not None:
        return round(amount * float(share) / 100.0, 2)
    # Otherwise every purchase is hers until she marks it someone else's
    # (2026-10-23). What others put in no longer shrinks her share by itself.
    return amount


def claim_deposit(store, t, marks: dict) -> bool:
    """A deposit into a joint account that she sorted herself (2026-10-25):
    Pay, her own money, a refund, a category, a kind of income. Saying what
    it was says it was hers, so "Who put this in?" is answered as her, and it
    counts. Notes the old answer in `marks` for Undo."""
    if not t.joint or t.amount >= 0 or t.joint_from:
        return False
    marks.setdefault("joint_from", {})[t.fingerprint] = {"who": t.joint_from, "person": t.joint_person}
    store.set_joint_deposit(t.fingerprint, ME, None)
    return True


# ── JOINT-A / JOINT-B (2026-11-09): splits of her part, and Undo ──────────

def account_state(store, account_id: str) -> dict | None:
    """A joint account as it is (label, share, people), for an Undo; None
    when it isn't joint."""
    with store.conn() as c:
        row = c.execute("SELECT label, share, people FROM joint_accounts WHERE account_id = ?",
                        (account_id,)).fetchone()
    if row is None:
        return None
    from .store import _people
    return {"label": row["label"], "share": None if row["share"] is None else float(row["share"]),
            "people": _people(row["people"])}


def restore_account(store, account_id: str, was: dict | None) -> None:
    """Put a joint account back as `account_state` saw it (AM-08x1,
    AM-08n1, AM-21j1). None: not joint."""
    import json
    with store.conn() as c:
        c.execute("DELETE FROM joint_accounts WHERE account_id = ?", (account_id,))
        if was is not None:
            c.execute("INSERT INTO joint_accounts (account_id, label, share, people) VALUES (?, ?, ?, ?)",
                      (account_id, was.get("label") or "Joint",
                       None if was.get("share") is None else float(was["share"]),
                       json.dumps(list(was.get("people") or []))))


def account_part(t, share: float | None) -> float:
    """Her part of a joint charge by the account alone (no answer of hers):
    a name always hers, the name's rule, the account's share, or all of it
    ("All mine unless I mark it")."""
    if t.joint_mine:
        return round(t.amount, 2)
    if t.joint_split is not None:
        return round(t.amount * float(t.joint_split) / 100.0, 2)
    if share is not None:
        return round(t.amount * float(share) / 100.0, 2)
    return round(t.amount, 2)


def holder(t, name: str) -> str | None:
    """The joint account holder this name is ("Sam" is Sam Lee), if any."""
    from .splits import same_person
    return next((p for p in (t.joint_people or []) if same_person(p, name)), None)


def rescale(t, split: dict, old_base: float, new_base: float) -> tuple[list[dict] | None, str | None, str]:
    """A split of her part when her part changes (JOINT-B, PO 2026-11-09):
    evenly, % and shares are worked out again on the new part; amounts she
    typed stay, and her share takes the rest. Someone she let go keeps what
    they paid. Returns (people, problem, mode)."""
    from . import splits as sp
    mode = split["mode"]
    people = [dict(p) for p in split["people"]]
    if mode == sp.UNSURE:
        return people, None, mode
    if mode != "amount":
        # REFRESH-18: a share that changes takes a small let go of Pearl's
        # back first (save_plan clears it); one she said stays.
        for p in people:
            if (p.get("let_go") or {}).get("auto"):
                p["amount"] = p.pop("let_go")["was"]
    theirs = sum(sp._cents(p["amount"]) for p in people)
    had_me = sp._cents(old_base) - theirs >= 1
    if mode == "amount":
        out = people
    elif mode == "even" and not any(p.get("let_go") for p in people):
        proxy = _with_amount(t, new_base)
        out, problem = sp.validate(proxy, "even", [{"name": p["name"]} for p in people], None, had_me)
        if problem:
            return None, problem, mode
        out = [dict(q, **{k: v for k, v in p.items() if k not in ("amount",)}) for p, q in zip(people, out)]
    else:
        # % and shares (and an even split with someone let go): each part
        # in proportion, rounded down; the odd cents are hers, or the first
        # person's when she isn't in it.
        new = sp._cents(new_base)
        old = sp._cents(old_base) or 1
        out = []
        for p in people:
            if p.get("let_go"):
                out.append(p)
                continue
            out.append(dict(p, amount=(sp._cents(p["amount"]) * new // old) / 100))
        if not had_me:
            gap = new - sum(sp._cents(p["amount"]) for p in out)
            for i in range(max(gap, 0)):
                q = out[i % len(out)]
                q["amount"] = round(q["amount"] + 0.01, 2)
    total = sum(sp._cents(p["amount"]) for p in out)
    if total > sp._cents(new_base):
        return None, "That’s more than your part now. Change the split first.", mode
    return out, None, mode


def _with_amount(t, amount: float):
    import copy
    proxy = copy.copy(t)
    proxy.amount = round(amount, 2)
    return proxy


def preview(store, charges: list, new_part, keep: bool = False) -> tuple[list[dict], str | None, list[tuple]]:
    """What a change of her part does to the split joint purchases in
    `charges` (AM-21j, AM-08n): each one's part before and after, and each
    person's share before and after with what they've paid. `new_part`
    maps a charge to its new part. Returns (changes, problem, plan) where
    plan is [(charge, split, people, mode, part)] to save."""
    from . import splits as sp
    splits = store.splits()
    txns = store.all_transactions()
    payer = store.payback_people()
    changes, plan = [], []
    for t in charges:
        split = splits.get(t.fingerprint)
        if not split:
            continue
        old = sp.split_base(t)
        new = round(new_part(t), 2)
        if abs(new - old) < 0.005:
            continue
        if keep:
            # Not joint any more (decision 1): people owe the same.
            people, mode = [dict(p) for p in split["people"]], split["mode"]
            problem = (None if sum(sp._cents(p["amount"]) for p in people) <= sp._cents(new)
                       else "That’s more than your part now. Change the split first.")
        else:
            people, problem, mode = rescale(t, split, old, new)
        if problem:
            return [], f"{t.merchant} on {t.date[:10]}: {problem}" if len(charges) > 1 else problem, []
        status = {p["name"]: p for p in sp.people_status(t, split, txns, payer)}
        rows = []
        for p, q in zip(split["people"], people):
            st = status.get(p["name"]) or {}
            rows.append({"name": p["name"], "paid": st.get("paid", 0.0),
                         "share_was": round(p["amount"], 2), "share_now": round(q["amount"], 2)})
        theirs = sum(q["amount"] for q in people)
        changes.append({"charge_id": t.fingerprint, "merchant": t.merchant, "date": t.date[:10],
                        "mode": mode, "part_was": old, "part_now": new,
                        "yours_was": round(t.my_share if t.my_share is not None else old, 2),
                        "yours_now": round(new - theirs, 2) if mode != sp.UNSURE
                        else round(max(new - (t.unsure_paid or 0.0), 0.0), 2),
                        "people": rows, "paid": any(r["paid"] >= 0.005 for r in rows)})
        plan.append((t, split, people, mode, new))
    return changes, None, plan


def save_plan(store, plan: list[tuple], marks: dict, joint: bool = True) -> None:
    """Save what `preview` worked out, noting each split for Undo. With
    `joint` off the account isn't joint any more: the split is of the whole
    purchase, people keep their amounts and her share takes the rest
    (decision 1), as Amounts."""
    from . import splits as sp
    parts = store.joint_parts()
    for t, split, people, mode, part in plan:
        marks.setdefault("splits", {}).setdefault(t.fingerprint, {
            "split": split, "share": t.my_share if t.share_set else None,
            "joint_part": parts.get(t.fingerprint)})
        if not joint:
            store.set_joint_part(t.fingerprint, None)
            if mode != sp.UNSURE:
                mode = "amount"
        for p, q in zip(split["people"], people):
            if p.get("let_go") and not q.get("let_go"):
                store.clear_let_go(t.fingerprint, p["name"])
        store.set_split(t.fingerprint, mode, people, split["watch"], split.get("closed_at"))
        if mode == sp.UNSURE:
            store.set_share(t.fingerprint, None)
        else:
            store.set_share(t.fingerprint, round(part - sum(p["amount"] for p in people), 2))


# ── Paybacks 2 (approved 2026-11-16): a transfer that was really someone
# paying her back (TP-01 to TP-05). Money out of a joint account into one
# only hers can be the other owner paying her back: the money in links to
# their shares as any payback does (Rule A), and the money out becomes
# theirs, marked the way a joint charge she says is theirs is (her share 0,
# one "I say" on an account that's hers unless she says), all of it even on
# a 50/50 account (decision 1). Undo and Unlink all put both back, and with
# them the transfer pairing (finance/transfers.py pairs only what's hers).

def payback_offer(t, other) -> dict | None:
    """TP-01: for money in `t` whose other end is `other`, the joint
    account's other owners who could have paid her back ({people,
    account, out}); None when it's not money out of a joint account into
    one only hers (TP-05, or money she moved into the joint account)."""
    if t is None or other is None or t.amount >= 0 or other.amount <= 0:
        return None
    if t.joint or not other.joint or other.account_id == t.account_id:
        return None
    people = [p for p in (other.joint_people or []) if p]
    if not people:
        return None
    return {"people": people, "account": (other.account_label or other.joint or "Joint").replace("••", "··"),
            "out": other.fingerprint}


def mark_payback(store, out, inflow_id: str, person: str) -> dict:
    """TP-03: joint money out `out` was `person` paying her back with money
    in `inflow_id`. It becomes theirs (her share 0). Returns Undo's marks."""
    was = out.my_share if out.share_set else None
    store.set_share(out.fingerprint, 0.0)
    store.set_joint_payback(out.fingerprint, {"inflow": inflow_id, "person": person, "was": was})
    return {"shares": {out.fingerprint: was}, "joint_paybacks": {out.fingerprint: None}}


def release_payback(store, inflow_id: str) -> dict:
    """Unlink all on the money in (TP-04): the joint money out is as it was
    before, so the two pair as a transfer again. Returns Undo's marks."""
    marks: dict = {}
    for out_id, rec in store.joint_paybacks().items():
        if rec["inflow"] != inflow_id:
            continue
        marks.setdefault("shares", {})[out_id] = 0.0
        marks.setdefault("joint_paybacks", {})[out_id] = rec
        store.set_share(out_id, rec["was"])
        store.set_joint_payback(out_id, None)
    return marks


def payback_of(store, inflow_id: str) -> tuple[str, dict] | None:
    """(joint money out id, {inflow, person, was}) for money in that a
    joint account's other owner paid her back with; None otherwise."""
    return next(((o, r) for o, r in store.joint_paybacks().items() if r["inflow"] == inflow_id), None)
