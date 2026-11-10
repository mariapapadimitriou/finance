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


def ratios(store) -> dict[tuple[str, str], float]:
    """{(account_id, "YYYY-MM"): the part of that month's joint spending on
    that account that is hers}, for joint accounts without a set share."""
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
    theirs: dict[tuple[str, str], float] = {}
    for r in rows:
        key = (r["account_id"], r["month"])
        if is_spend_category(r["category"] or "Other"):
            spent[key] = spent.get(key, 0.0) + float(r["spent"] or 0)
        theirs[key] = theirs.get(key, 0.0) + float(r["theirs"] or 0)
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
        store.set_split(t.fingerprint, mode, people, split["watch"], split.get("closed_at"))
        if mode == sp.UNSURE:
            store.set_share(t.fingerprint, None)
        else:
            store.set_share(t.fingerprint, round(part - sum(p["amount"] for p in people), 2))
