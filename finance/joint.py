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

* "me": her own money moving between her pockets — not income.
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

ME, THEM = "me", "them"


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
        return amount if who == ME else 0.0
    # "Split every purchase": her share of each one.
    if share is not None:
        return round(amount * float(share) / 100.0, 2)
    # Otherwise every purchase is hers until she marks it someone else's
    # (2026-10-23). What others put in no longer shrinks her share by itself.
    return amount
