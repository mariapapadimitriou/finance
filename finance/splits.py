"""Splits and repayments (Pearl S-01 to S-04, THL-124).

A split is a charge you paid for several people: evenly or by amount, with
up to eight others named by a first name you typed. Your part is written as
your share (`txn_shares`), so every total that counts spending — spent,
category totals, the usual month, safe to spend — already counts only it.

Each other person's part is a repayment you can watch for. When an
e-Transfer arrives from the same first name, for about what they owe
(within $1), within 60 days of the charge, Pearl suggests linking it (S-02).
Friends often pay before a card purchase posts, so "the charge" is the day
of the purchase, not the day it posted, and money from up to a week before
it counts too.
You can also link any money in to any open split by hand (S-03), and a
repayment can be partial: what is left stays open. A linked repayment is
never income: it was always theirs.
"""

from __future__ import annotations

import re
from datetime import date

from .models import Transaction

MAX_PEOPLE = 50   # paybacks on one split (2026-10-26: was 8)
MAX_NAME = 40
MATCH_WITHIN = 1.00        # dollars
MATCH_DAYS = 60
# Money that arrived this long before the purchase can still be paying it back.
EARLY_DAYS = 7
# THL-181 (SPLIT-21, S-35a/S-35b): a payback that names nobody on the split,
# dated from this day on, counts for someone only when exactly one share
# still owed is its amount; otherwise she's asked who it was. One dated
# before keeps the old guess, so nothing she has already seen changes.
ASK_FROM = "2026-11-10"

_WORD = re.compile(r"[a-zà-ÿ0-9']+")


def bought_on(t: Transaction) -> date:
    """The day of the purchase: the earlier of its two dates, since a bank
    feed's date is when it posted and a statement's is when it was made."""
    days = [d[:10] for d in (t.date, t.post_date) if d]
    return date.fromisoformat(min(days))


def first_name(name: str) -> str:
    words = _WORD.findall((name or "").lower())
    return words[0] if words else ""


def same_person(a: str, b: str) -> bool:
    """Two names for one person: the same first name, or a Wealthsimple Pay
    handle that starts with the other's first name ("Anastasiapapas" and
    "Anastasia", 2026-10-28)."""
    fa, fb = first_name(a), first_name(b)
    if not fa or not fb:
        return False
    if fa == fb:
        return True
    one_word = lambda n: len(_WORD.findall((n or "").lower())) == 1
    return ((one_word(a) and len(fb) >= 3 and fa.startswith(fb))
            or (one_word(b) and len(fa) >= 3 and fb.startswith(fa)))


def sender(t: Transaction) -> str:
    """Who money in came from, as the bank wrote it."""
    raw = t.raw or {}
    return " ".join(str(x) for x in (t.party, raw.get("counterparty"), t.merchant,
                                       t.description) if x)


def from_person(inflow: Transaction, name: str) -> bool:
    """Did this money come from someone with this first name?"""
    first = first_name(name)
    if not first:
        return False
    if first in _WORD.findall(sender(inflow).lower()):
        return True
    # A Wealthsimple Pay handle runs the names together (2026-10-28):
    # "anastasiapapas" is Anastasia.
    from .etransfers import handle_matches
    return handle_matches(inflow, first)


def even_amounts(total: float, n_people: int) -> tuple[float, list[float]]:
    """Split `total` evenly among you and n others, in cents. Any odd cent
    stays with you, so what the others owe is never rounded up on them."""
    each = int(round(total * 100)) // (n_people + 1)
    theirs = [each / 100] * n_people
    return round(total - sum(theirs), 2), theirs


MODES = ("even", "amount", "percent", "shares", "unknown")
# SPLIT-C (2026-11-09): "Not sure yet", the fifth method: who it was with,
# no amounts. Each payback linked to it comes off what it costs her.
UNSURE = "unknown"

# TEST-31 (product owner, 2026-11-13): who a payback linked to a split counts
# for, when it isn't one of the people. ME: her own share, reimbursed (work
# paying her back for her part, T-09w); it never counts for anyone else.
# EVERYONE: a whole-purchase reimbursement ("all of it"), which pays her share
# first and then whoever still owes, as any whole-purchase payback would.
ME = "me"
EVERYONE = "everyone"
SELF = (ME, EVERYONE)


def _cents(x) -> int:
    return int(round(float(x) * 100))


def validate(charge: Transaction, mode: str, people: list, you=None,
             include_me: bool = True, base: float | None = None) -> tuple[list[dict], str | None]:
    """Clean the people of a split, or say what is wrong with them.

    THL-291: evenly (any odd cent to you), by amount, by percent or by
    shares. `you` is your own amount, percent or shares; with it, the parts
    can't add up to more than the whole charge. Less is fine only when
    you're in it (SPLIT-01 (b′), S-03b v2, 2026-11-09): what nobody has been
    given yet stays yours. With `include_me` off ("I had some too" off)
    there's no "you" to keep it, so a short split is "$x left to assign".

    JOINT-B: `base` is her part of a joint-account purchase, and the split
    is of that, not the whole charge. SPLIT-C: Not sure yet takes names
    only; whatever isn't paid back is hers, so "I had some too" is moot."""
    if mode not in MODES:
        return [], "Split evenly, by amount, by percent or by shares."
    whole = round(float(base if base is not None else charge.amount), 2)
    if not isinstance(people, list) or not people:
        return [], "Add someone to split it with."
    if len(people) > MAX_PEOPLE:
        return [], f"Up to {MAX_PEOPLE} people."
    clean = []
    for p in people:
        if not isinstance(p, dict):
            return [], "Add someone to split it with."
        name = " ".join(str(p.get("name") or "").split())[:MAX_NAME]
        if not name:
            return [], "Give everyone a name."
        clean.append({"name": name, "amount": p.get("amount")})
    if mode == UNSURE:
        for p in clean:
            p["amount"] = 0.0
        return clean, None
    total = _cents(whole)
    if mode == "even":
        if include_me:
            _, theirs = even_amounts(whole, len(clean))
        else:
            # All theirs: split among them, the odd cents to the first.
            each, odd = divmod(total, len(clean))
            theirs = [(each + (1 if i < odd else 0)) / 100 for i in range(len(clean))]
        for p, a in zip(clean, theirs):
            p["amount"] = a
    elif mode in ("percent", "shares"):
        key = mode
        try:
            weights = [float(p.get(key) if isinstance(p.get(key), (int, float, str)) else "x")
                       for p in people]
            mine = 0.0 if not include_me else float(you if you is not None else
                                                  (100 - sum(weights) if mode == "percent" else 1))
        except (TypeError, ValueError):
            return [], "Give everyone a number."
        if any(w < 0 for w in weights) or mine < 0:
            return [], "A part can’t be less than nothing."
        whole = sum(weights) + mine
        if whole <= 0:
            return [], "Give someone a part."
        short = mode == "percent" and whole < 100 - 0.001
        if short:
            # SPLIT-10 (2026-11-09): % works in cents. A shortfall smaller
            # than one cent per row (33.33% three ways) is rounding, not a
            # gap: it adds up, and the odd cent goes by the usual rule.
            rows = len(clean) + (1 if include_me else 0)
            if total * (100 - whole) / 100 < rows:
                short = False
        if mode == "percent" and whole > 100 + 0.001:
            return [], f"That’s {whole - 100:g}% too much."
        if short and not include_me:
            # SPLIT-01 (b′): with "I had some too" off, nobody keeps the rest.
            return [], f"{round(100 - whole, 2):g}% left to assign."
        # Theirs rounded down to the cent; what's left over is yours. Short
        # of 100%, each part is its percent of the whole and the rest is yours.
        over = 100 if short else whole
        for p, w in zip(clean, weights):
            p["amount"] = (total * w // over) / 100 if over else 0.0
            p[key] = w
        if not include_me and not short:
            gap = total - sum(_cents(p["amount"]) for p in clean)
            for i in range(gap):
                clean[i % len(clean)]["amount"] = round(clean[i % len(clean)]["amount"] + 0.01, 2)
    else:
        for p in clean:
            try:
                p["amount"] = round(float(p["amount"]), 2)
            except (TypeError, ValueError):
                return [], f"How much was {p['name']}’s part?"
            if p["amount"] < 0:
                return [], f"{p['name']}’s part can’t be less than nothing."
        theirs = sum(_cents(p["amount"]) for p in clean)
        mine = None if you is None else _cents(you) if include_me else 0
        if mine is None and not include_me:
            mine = 0
        if mine is not None and theirs + mine > total:
            return [], f"That’s ${(theirs + mine - total) / 100:,.2f} more than the charge."
        if theirs > total:
            return [], "Their parts add up to more than the whole charge."
        if not include_me and theirs < total:
            # SPLIT-01 (b′), S-03b: blocked in the app and here alike.
            return [], f"${(total - theirs) / 100:,.2f} left to assign."
    for p in clean:
        p["amount"] = round(p["amount"], 2)
    return clean, None


def same_name(a: str, b: str) -> bool:
    """The same name typed twice ("Sam" and "sam")."""
    return " ".join(a.lower().split()) == " ".join(b.lower().split())


def your_part(charge: Transaction, people: list[dict], base: float | None = None) -> float:
    whole = base if base is not None else charge.amount
    return round(whole - sum(p["amount"] for p in people), 2)


def split_base(charge: Transaction) -> float:
    """What a split of this charge splits (JOINT-B): her part of a joint
    purchase, or the whole charge."""
    if charge.joint and charge.joint_part is not None:
        return round(charge.joint_part, 2)
    return round(charge.amount, 2)


def still_yours(charge: Transaction) -> float:
    """SPLIT-C: what a Not sure yet split still costs her (S-04u's "$80.00
    still counts as yours"): her part less every payback so far. It's
    also the most one more payback can take (decision 2)."""
    if charge.split_mode == UNSURE and charge.my_share is not None:
        return round(max(charge.my_share, 0.0), 2)
    return round(max(split_base(charge) - (charge.paid_back or 0.0), 0.0), 2)


def is_open(split: dict | None) -> bool:
    """A split still watching for paybacks: not one she said That's
    everything on (SPLIT-C, S-46)."""
    return bool(split) and not split.get("closed_at")


def _linked(charge_id: str, transactions: list[Transaction]) -> list[Transaction]:
    # A payback can cover several purchases (2026-10-28).
    return sorted((t for t in transactions if charge_id in t.repays_all), key=lambda t: t.date)


def and_list(names: list[str]) -> str:
    """"Loblaws", "Loblaws and Pizza Nova", "Loblaws, Costco and Pizza Nova"."""
    return names[0] if len(names) == 1 else ", ".join(names[:-1]) + " and " + names[-1]


def payments(records: list[dict], dates: dict[str, str] | None = None,
             merchants: dict[str, str] | None = None) -> list[dict]:
    """SPLIT-15: cash or app records as the payments she recorded. A payment
    only partly deposited is cut into pieces (`origin`), but she always
    sees one: "$250.00 cash · Nov 3", and under it "$200.00 deposited
    Nov 12 · $50.00 still cash". `dates` maps a deposit part to its day.

    SPLIT-19: a payment whose extra paid back other shares names every
    purchase it paid (`paid_back`, its own first), from `merchants`
    (charge id → merchant)."""
    dates = dates or {}
    merchants = merchants or {}
    groups: dict[int, list[dict]] = {}
    for c in records:
        groups.setdefault(c.get("origin") or c["id"], []).append(c)
    out = []
    for root, pieces in groups.items():
        first = min(pieces, key=lambda c: c["id"])
        total = round(sum(c["amount"] for c in pieces), 2)
        held = [c for c in pieces if c.get("deposit_id")]
        deposited = round(sum(c["amount"] for c in held), 2)
        days = sorted(dates.get(c["deposit_id"], "") for c in held if dates.get(c["deposit_id"]))
        # SPLIT-19: the whole payment, when its extra went elsewhere too.
        extra = {}
        if (first.get("whole") or total) > total + 0.005:
            extra["whole"] = first["whole"]
        if (first.get("given_back") or 0.0) >= 0.005:
            extra["given_back"] = first["given_back"]
        if len(first.get("charges") or []) > 1:
            extra["paid_back"] = [merchants.get(c) or "another purchase" for c in first["charges"]]
        out.append({**extra, "id": root, "ids": sorted(c["id"] for c in pieces), "amount": total,
                    "day": first["day"], "via": first.get("via") or "cash", "app": first.get("app"),
                    "deposited": deposited, "deposited_on": days[-1] if days else None,
                    "still": round(total - deposited, 2)})
    out.sort(key=lambda p: (p["day"], p["id"]))
    return out


def people_status(charge: Transaction, split: dict, transactions: list[Transaction],
                  payer: dict[str, str], left_out: list[Transaction] | None = None,
                  extra_out: list[Transaction] | None = None,
                  credited_to: dict[str, str] | None = None,
                  mine: dict | None = None) -> list[dict]:
    """Each person in a split: their part, what they've paid back and when,
    what they still owe (S-04), and what they paid over their part (`over`,
    SPLIT-02: a share lowered below what they'd paid, which she owes back).

    A repayment counts for the person you linked it to; one linked before
    people had names counts for whoever it came from by name. A payback that
    names someone no longer in the split counts for nobody (SPLIT-02,
    2026-11-09): it is theirs, never "the first who still owes".

    `left_out`, when given, gets each payback the ask rule credited to no
    one while somebody still owes (SPLIT-22b, S-05u): the ones Pearl asks
    "Who sent this?" about.

    `extra_out`, when given, gets each payback dated from ASK_FROM, with no
    name, that came when nobody on the split still owed anything (SPLIT-23
    (1), S-21x): it isn't anyone's payback, so Pearl asks what it was.
    THL-301 (SPLIT-24, S-21xm): so does one over two or more purchases that
    she said was from someone who isn't on this one (S-35c credited Jo on
    Pizza Nova), when nobody here still owes: one payment has one sender,
    so its part here is extra too.

    `credited_to`, when given, maps each payback counted here to who it
    counted for (S-11xm's "Jo paid back $30.00 of this for Pizza Nova").

    `mine`, when given, gets her own share and what reimbursed it (TEST-31,
    S-04w): `amount` her share, `paid` what work paid of it, `on` the day it
    was last paid and `ids` the deposits. A payback linked for ME counts
    only for her; one for EVERYONE fills her share, then whoever owes.
    """
    names = [p["name"] for p in split["people"]]
    unsure = split.get("mode") == UNSURE
    # A refund on the purchase is shared the way the purchase was: each
    # person's part shrinks by the same fraction (decision 6).
    back = getattr(charge, "refunded", 0.0) or 0.0
    factor = max(1.0 - back / charge.amount, 0.0) if charge.amount > 0 and back else 1.0
    part = {p["name"]: round(float(p["amount"]) * factor, 2) for p in split["people"]}
    paid = {n: 0.0 for n in names}
    when: dict[str, str] = {}
    # Cash in hand (THL-291) counts as paid the day she marked it.
    # Another app (SPLIT-11) counts as paid like cash, but isn't cash.
    cash = {p["name"]: round(sum(c["amount"] for c in p.get("cash") or [] if c.get("via", "cash") != "app"), 2)
            for p in split["people"]}
    app = {p["name"]: round(sum(c["amount"] for c in p.get("cash") or [] if c.get("via") == "app"), 2)
           for p in split["people"]}
    for p in split["people"]:
        for c in p.get("cash") or []:
            paid[p["name"]] = round(paid[p["name"]] + c["amount"], 2)
            when[p["name"]] = max(when.get(p["name"], ""), c["day"])
    # Deposits holding cash are parts; their day is the deposit's (SPLIT-15).
    dates = {t.fingerprint: t.date[:10] for t in transactions if (t.raw or {}).get("part_of")}
    named = {c for p in split["people"] for x in p.get("cash") or [] for c in x.get("charges") or []}
    merchants = {t.fingerprint: t.merchant for t in transactions if t.fingerprint in named}
    unnamed: list[Transaction] = []
    everyone: list[Transaction] = []
    # TEST-31: her own share, as split (a refund shrinks it the same way).
    yours = round(float(charge.my_share or 0.0) * factor, 2) \
        if split.get("me", True) and charge.my_share is not None and not unsure else 0.0
    mine_paid, mine_on, mine_ids = 0.0, None, []
    extras_named: list[Transaction] = []
    shared: dict[str, list[dict]] = {}
    names_of: dict[str, str] = {}
    for t in sorted(_linked(charge.fingerprint, transactions), key=lambda x: x.date):
        who = payer.get(t.fingerprint)
        if who in SELF:
            # TEST-31: never anyone's payback, so never asked about. Not sure
            # yet has no shares: what came back already lowers what it costs.
            if unsure:
                continue
            if who == EVERYONE:
                everyone.append(t)
                continue
            mine_paid = round(mine_paid + t.part_for(charge.fingerprint), 2)
            mine_on = t.date[:10]
            mine_ids.append(t.fingerprint)
            if credited_to is not None:
                credited_to[t.fingerprint] = ME
            continue
        if who not in paid and who:
            # "Sam Lee" paying back the Sam in the split.
            who = next((n for n in names if same_person(n, who)), None)
            if who is None:
                # Someone taken out of the split: their payback is still
                # theirs, so it counts for nobody here.
                if (extra_out is not None and len(t.repays_all) > 1 and t.date[:10] >= ASK_FROM
                        and t.fingerprint in payer):
                    # THL-301: unless it's a payment over several purchases
                    # whose sender she named for another of them. Asked
                    # about below, once nobody here owes.
                    extras_named.append(t)
                continue
        if who not in paid:
            who = next((n for n in names if from_person(t, n)), None)
        if who is None:
            unnamed.append(t)
            continue
        paid[who] = round(paid[who] + t.part_for(charge.fingerprint), 2)
        when[who] = t.date[:10]
        if credited_to is not None:
            credited_to[t.fingerprint] = who
        if len(t.repays_all) > 1:
            # SPLIT-16 (S-03f): a payback that also paid back other
            # purchases; removing them here unlinks only this purchase's part.
            names_of = names_of or {x.fingerprint: x.merchant for x in transactions}
            text = f"{t.description or ''} {t.merchant or ''}".lower().replace("-", "")
            shared.setdefault(who, []).append({
                "whole": round(t.paid_part, 2), "here": t.part_for(charge.fingerprint),
                "others": [names_of.get(c) or "another purchase" for c in t.repays_all
                           if c != charge.fingerprint],
                "word": "e-Transfer" if "etransfer" in text or "interac" in text else "payment"})
    # TEST-31 (decision 2): "all of it" pays her share first, then each
    # person who still owes, in the split's order; anything over is no one's.
    for t in everyone:
        got = t.part_for(charge.fingerprint)
        take = round(min(got, max(yours - mine_paid, 0.0)), 2)
        if take >= 0.005:
            mine_paid = round(mine_paid + take, 2)
            mine_on = t.date[:10]
            mine_ids.append(t.fingerprint)
            got = round(got - take, 2)
        for n in names:
            take = round(min(got, max(part[n] - paid[n], 0.0)), 2)
            if take >= 0.005:
                paid[n] = round(paid[n] + take, 2)
                when[n] = t.date[:10]
                got = round(got - take, 2)
        if credited_to is not None:
            credited_to[t.fingerprint] = EVERYONE
    if mine is not None:
        mine.update({"amount": yours, "paid": mine_paid, "on": mine_on, "ids": mine_ids})
    # A payback nobody's name is on (a bank that leaves the sender off, or
    # one linked from search). Only these: one with a name is never moved to
    # someone else (2026-11-09).
    for t in unnamed:
        got = t.part_for(charge.fingerprint)
        if unsure:
            # SPLIT-C (S-35u): no amounts, so no amount can say who sent it.
            # Pearl never guesses; it asks, whatever the payback's date.
            if left_out is not None:
                left_out.append(t)
            continue
        owing = [n for n in names if part[n] - paid[n] >= 0.005]
        if not owing:
            if extra_out is not None and t.date[:10] >= ASK_FROM:
                extra_out.append(t)
            continue
        fits = [n for n in owing if abs(part[n] - paid[n] - got) < 0.01]
        if t.date[:10] >= ASK_FROM:
            # THL-181 "If Pearl can't tell who, it asks" (SPLIT-21): the one
            # share that is its amount, or nobody until she says (S-35a, S-35b).
            if len(fits) != 1:
                if left_out is not None:
                    left_out.append(t)
                continue
            who = fits[0]
        else:
            # Before ASK_FROM (2026-10-24 rule, kept so old paybacks read as
            # they did): whoever owes exactly that much, else the first who
            # still owes anything.
            who = fits[0] if fits else owing[0]
        paid[who] = round(paid[who] + got, 2)
        when[who] = t.date[:10]
        if credited_to is not None:
            credited_to[t.fingerprint] = who
    if extras_named and all(part[n] - paid[n] < 0.005 for n in names):
        extra_out.extend(extras_named)
    if unsure or split.get("closed_at"):
        # SPLIT-C: Not sure yet has no shares, so nobody owes and nobody
        # paid over; each person's part so far is what they've paid. A
        # closed split (That's everything) has nobody owing either.
        for n in names:
            part[n] = paid[n] if unsure else min(part[n], paid[n])
    out = []
    for p in split["people"]:
        owes = round(max(part[p["name"]] - paid[p["name"]], 0.0), 2)
        out.append({"name": p["name"], "amount": part[p["name"]], "paid": paid[p["name"]],
                    "owes": owes, "paid_on": when.get(p["name"]) if owes < 0.005 else None,
                    "over": round(max(paid[p["name"]] - part[p["name"]], 0.0), 2),
                    "weight": p.get("weight"),
                    "cash": cash.get(p["name"], 0.0),
                    "app": app.get(p["name"], 0.0),
                    "cash_ids": [c["id"] for c in p.get("cash") or []],
                    # SPLIT-15: each cash or app payment once, as recorded.
                    "payments": payments(p.get("cash") or [], dates, merchants),
                    # SPLIT-14: "Paid back · PayPal · Nov 13"; the newest named app.
                    "app_name": next((c["app"] for c in sorted(p.get("cash") or [], key=lambda c: (c["day"], c["id"]),
                                                               reverse=True)
                                      if c.get("via") == "app" and c.get("app")), None),
                    "shared": shared.get(p["name"], []),
                    "let_go": p.get("let_go")})
    return out


def your_share_left(charge: Transaction, split: dict | None, transactions: list[Transaction],
                    payer: dict[str, str], inflow: Transaction | None = None) -> float | None:
    """TEST-31 (T-09w): what's still hers of a split with shares, for work to
    reimburse: her share less what already reimbursed it. None when she
    isn't in it, it's Not sure yet, or it isn't split. `inflow`, already
    linked for her, doesn't count against itself."""
    if (not split or split.get("mode") == UNSURE or not split.get("me", True)
            or charge.my_share is None or charge.amount <= 0):
        return None
    mine: dict = {}
    people_status(charge, split, transactions, payer, mine=mine)
    back = mine.get("paid", 0.0)
    if inflow is not None and inflow.fingerprint in (mine.get("ids") or []):
        back -= inflow.part_for(charge.fingerprint)
    return round(max(mine.get("amount", 0.0) - back, 0.0), 2)


def unsure_rows(transactions: list[Transaction], splits: dict[str, dict],
                payer: dict[str, str]) -> list[dict]:
    """SPLIT-C: every open Not sure yet split, one row a person, with what
    the purchase still costs her (`still`). S-09u lists a sender's first,
    S-35u everyone's under COULD BE EITHER; S-14u lists them NOT SETTLED."""
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for cid, split in splits.items():
        charge = by_id.get(cid)
        if (charge is None or charge.excluded or split.get("mode") != UNSURE
                or not is_open(split) or not split.get("watch", True)):
            continue
        status = people_status(charge, split, transactions, payer)
        for p in status:
            out.append({"charge": charge, "name": p["name"], "paid": p["paid"],
                        "still": still_yours(charge), "people": [q["name"] for q in status],
                        "paid_total": round(sum(q["paid"] for q in status), 2)})
    return out


def uncredited(charge: Transaction, split: dict, transactions: list[Transaction],
                payer: dict[str, str]) -> list[Transaction]:
    """SPLIT-22b (THL-181, S-05u): paybacks linked to this split purchase
    that the ask rule credited to no one, newest first. Only ones dated from
    ASK_FROM can be here; an older one keeps its old credit."""
    out: list[Transaction] = []
    people_status(charge, split, transactions, payer, left_out=out)
    return sorted(out, key=lambda t: (t.date, t.fingerprint), reverse=True)


def payment_word(t: Transaction) -> str:
    """"e-Transfer" for an Interac e-Transfer, else "payment" (S-03f, S-05u)."""
    text = f"{t.description or ''} {t.merchant or ''}".lower().replace("-", "")
    return "e-Transfer" if "etransfer" in text or "interac" in text else "payment"


def sender_name(t: Transaction) -> str | None:
    """The name the bank put on money in, if any (S-05u's "no name" if not)."""
    raw = t.raw or {}
    return t.party or raw.get("counterparty") or None


def uncredited_rows(charge: Transaction, split: dict, transactions: list[Transaction],
                    payer: dict[str, str]) -> list[dict]:
    """S-05u: each uncredited payback on the split card, as "$30.00 from an
    e-Transfer" over "Nov 16 · no name · paid back Loblaws". Shown only
    while someone on one of its purchases still owes, since S-35c can only
    credit someone who does (SPLIT-23 asks about the rest)."""
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for t in uncredited(charge, split, transactions, payer):
        out.append({"id": t.fingerprint, "amount": t.part_for(charge.fingerprint),
                    "whole": round(-t.amount, 2), "date": t.date[:10],
                    "sender": sender_name(t), "word": payment_word(t),
                    "name": t.merchant or t.description or "",
                    "paid_back": [(by_id.get(c).merchant if by_id.get(c) else "another purchase")
                                  for c in t.repays_all]})
    return out


def credit_question(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
                    payer: dict[str, str]) -> dict | None:
    """S-35c "Who sent this?" (SPLIT-22b, THL-181): for a payback already
    linked that the ask rule credited to no one, the open shares on the
    purchases it pays back, to tick who sent it. None when Pearl already
    knows who it was, or nobody on those purchases still owes anything."""
    if inflow.amount >= 0 or not inflow.repays:
        return None
    by_id = {t.fingerprint: t for t in transactions}
    asking = False
    purchases, shares = [], []
    for cid in inflow.repays_all:
        charge, split = by_id.get(cid), splits.get(cid)
        if charge is None:
            continue
        here = inflow.part_for(cid)
        purchases.append({"id": cid, "merchant": charge.merchant, "date": charge.date[:10], "here": here})
        if split is None:
            continue
        left: list[Transaction] = []
        status = people_status(charge, split, transactions, payer, left_out=left)
        if any(t.fingerprint == inflow.fingerprint for t in left):
            asking = True
        for p in status:
            if split.get("mode") == UNSURE:
                # S-35u: everyone on a Not sure yet split could have sent it.
                shares.append({"charge": cid, "merchant": charge.merchant, "date": charge.date[:10],
                               "person": p["name"], "owes": still_yours(charge), "share": None,
                               "here": here, "people": len(status), "unknown": True})
            elif p["owes"] >= 0.005:
                shares.append({"charge": cid, "merchant": charge.merchant, "date": charge.date[:10],
                               "person": p["name"], "owes": p["owes"], "share": p["amount"],
                               "here": here, "people": len(status)})
    if not asking or not shares:
        return None
    return {"id": inflow.fingerprint, "amount": round(-inflow.amount, 2),
            "linked": round(sum(p["here"] for p in purchases), 2), "date": inflow.date[:10],
            "sender": sender_name(inflow), "word": payment_word(inflow),
            "merchant": inflow.merchant or inflow.description or "",
            "purchases": purchases, "shares": shares}


def extra_question(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
                   payer: dict[str, str]) -> dict | None:
    """S-21x / S-11x (SPLIT-23 (1), THL-181): a payback linked to split
    purchases, dated from ASK_FROM, with no name, that came when nobody on
    any of them still owed anything. There's no one to tick, so it isn't a
    payback at all: Needs a look asks "What was this?" about the whole
    amount. None for anything else, including a payback that pays back a
    purchase that isn't split (that one counts for the purchase).

    THL-301 (SPLIT-24, S-21xm / S-11xm): also when it's extra on only some
    of its purchases and counted for someone on the rest. `amount` is then
    the extra part (the deposit less what was credited), `whole` the
    deposit, and `credited` each purchase it still pays back, with who and
    how much ("Jo paid back $30.00 of this for Pizza Nova"). While a part is
    still uncredited (S-35c, `credit:<id>`), this is None: who comes first,
    so one deposit is one question at a time."""
    if inflow.amount >= 0 or not inflow.repays or inflow.date[:10] < ASK_FROM:
        return None
    by_id = {t.fingerprint: t for t in transactions}
    purchases: list[dict] = []
    credited: list[dict] = []
    people: list[str] = []
    for cid in inflow.repays_all:
        charge, split = by_id.get(cid), splits.get(cid)
        if charge is None or split is None:
            return None
        extra: list[Transaction] = []
        left: list[Transaction] = []
        got: dict[str, str] = {}
        status = people_status(charge, split, transactions, payer, left_out=left, extra_out=extra,
                               credited_to=got)
        if any(t.fingerprint == inflow.fingerprint for t in left):
            return None
        if inflow.fingerprint in got:
            credited.append({"id": cid, "merchant": charge.merchant, "person": got[inflow.fingerprint],
                             "amount": inflow.part_for(cid)})
            continue
        if not any(t.fingerprint == inflow.fingerprint for t in extra):
            return None
        purchases.append({"id": cid, "merchant": charge.merchant, "date": charge.date[:10]})
        for p in status:
            if p["paid"] >= 0.005 and p["owes"] < 0.005 and not any(same_person(p["name"], n) for n in people):
                people.append(p["name"])
    if not purchases:
        return None
    whole = round(-inflow.amount, 2)
    out = {"id": inflow.fingerprint, "amount": whole, "date": inflow.date[:10],
           "purchases": purchases, "paid_back": [p["merchant"] for p in purchases], "people": people}
    if credited:
        out["whole"] = whole
        out["amount"] = round((_cents(whole) - sum(_cents(c["amount"]) for c in credited)) / 100, 2)
        out["credited"] = credited
    return out


def open_repayments(transactions: list[Transaction], splits: dict[str, dict],
                    payer: dict[str, str]) -> list[dict]:
    """Everyone who still owes something on a split you're watching."""
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for cid, split in splits.items():
        charge = by_id.get(cid)
        if charge is None or charge.excluded or not split.get("watch", True) or not is_open(split):
            continue
        for p in people_status(charge, split, transactions, payer):
            if p["owes"] >= 0.005:
                out.append({"charge": charge, "name": p["name"], "owes": p["owes"],
                            "amount": p["amount"]})
    return out


def suggest(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
            payer: dict[str, str]) -> dict | None:
    """The split this money most likely pays back (S-02): the same first
    name, within $1 of what they owe, from a week before the purchase to 60
    days after it."""
    if inflow.amount >= 0 or inflow.repays:
        return None
    got = -inflow.amount
    when = date.fromisoformat(inflow.date[:10])
    best = None
    for r in open_repayments(transactions, splits, payer):
        gap = (when - bought_on(r["charge"])).days
        if not -EARLY_DAYS <= gap <= MATCH_DAYS or not from_person(inflow, r["name"]):
            continue
        diff = abs(r["owes"] - got)
        if diff > MATCH_WITHIN + 0.005:
            continue
        key = (diff, abs(gap))
        if best is None or key < best[0]:
            best = (key, r)
    if best is not None and best[0][0] < 0.005:
        return brief(best[1], exact=True)
    # SPLIT-C (S-09u): a Not sure yet split the sender is on comes next,
    # since it takes any amount; it's never matched by amount.
    for r in sorted(unsure_rows(transactions, splits, payer), key=lambda r: r["charge"].date, reverse=True):
        gap = (when - bought_on(r["charge"])).days
        if -EARLY_DAYS <= gap <= MATCH_DAYS and r["still"] >= 0.005 and from_person(inflow, r["name"]):
            return unsure_brief(r)
    return None if best is None else brief(best[1], exact=False)


def for_inflow(inflow: Transaction, transactions: list[Transaction], splits: dict[str, dict],
               payer: dict[str, str]) -> tuple[list[dict], bool]:
    """Splits this money could be for (S-03): the sender's, if Pearl can
    tell who sent it, otherwise every open one. The second value says which."""
    when = date.fromisoformat(inflow.date[:10])
    open_ = [r for r in open_repayments(transactions, splits, payer)
             if (when - bought_on(r["charge"])).days >= -EARLY_DAYS]
    theirs = [r for r in open_ if from_person(inflow, r["name"])]
    rows = theirs or open_
    rows.sort(key=lambda r: r["charge"].date, reverse=True)
    # SPLIT-C (S-09u): Not sure yet splits, theirs first, "takes any amount".
    unsure = [r for r in unsure_rows(transactions, splits, payer)
              if r["still"] >= 0.005 and (when - bought_on(r["charge"])).days >= -EARLY_DAYS]
    mine = [r for r in unsure if from_person(inflow, r["name"])]
    if not mine:
        # One row a purchase when nobody on it is the sender.
        seen: set[str] = set()
        unsure = [r for r in unsure if not (r["charge"].fingerprint in seen or seen.add(r["charge"].fingerprint))]
    listed = [unsure_brief(r) for r in (mine or ([] if theirs else unsure))]
    return (listed + [brief(r) for r in rows[:12]])[:12], bool(theirs or mine)


def unsure_brief(r: dict) -> dict:
    """A Not sure yet split as a choice for money in: no share, and it can
    take up to what the purchase still costs her (S-09u)."""
    c = r["charge"]
    return {"charge_id": c.fingerprint, "merchant": c.merchant, "date": c.date[:10],
            "amount": round(c.amount, 2), "name": r["name"], "owes": r["still"],
            "share": None, "exact": False, "unknown": True, "still": r["still"]}


def brief(r: dict, exact: bool = False) -> dict:
    c = r["charge"]
    return {"charge_id": c.fingerprint, "merchant": c.merchant, "date": c.date[:10],
            "amount": round(c.amount, 2), "name": r["name"], "owes": r["owes"],
            "share": r["amount"], "exact": exact}


# ── A payback that makes the split (THL-260, 2026-10-24) ─────────────────
# Linking money in to a purchase that was never split ("Paid back" → any
# charge) turns the purchase into a split with whoever sent it, so the split
# card shows them, paid back. The payback is marked as having made its
# person's place in the split, so unlinking it takes them out again.
MADE_SPLIT = "made_split"


def add_payer(store, charge: Transaction, inflow: Transaction, person: str | None,
              got: float | None = None):
    """Put the sender into the charge's split for what they sent, if they
    aren't in it already. Returns what to put back for an Undo
    ({"split", "share"}), or None when nothing changed: no name, a joint
    charge, a share she typed without a split, someone already in the split,
    or more than her part is left."""
    person = " ".join((person or "").split())[:MAX_NAME]
    if not person or charge.joint or charge.amount <= 0 or inflow.amount >= 0:
        return None
    current = store.splits().get(charge.fingerprint)
    if current is None and charge.share_set:
        return None
    if current is not None and current.get("mode") == UNSURE:
        # SPLIT-C: a Not sure yet split takes any amount from anyone on it;
        # someone new joins it with no amount, and their payback is theirs.
        if any(same_person(p["name"], person) for p in current["people"]):
            return None
        was = {"split": current, "share": None}
        store.set_split(charge.fingerprint, UNSURE, list(current["people"]) + [{"name": person, "amount": 0.0}],
                        current["watch"], current.get("closed_at"))
        store.set_payback_kind(inflow.fingerprint, MADE_SPLIT)
        return was
    people = list(current["people"]) if current else []
    # What this payback put toward this purchase: all of it, or its part of
    # a payback that covered several (2026-10-28).
    got = inflow.part_for(charge.fingerprint) if got is None else got
    at = next((i for i, p in enumerate(people) if same_person(p["name"], person)), None)
    if at is not None:
        # Someone paying back in more than one e-Transfer (2026-10-26): if
        # their place was made by their earlier payback, it grows by this
        # one; a part she set in the split herself stays what she said.
        if not _made_by_paybacks(store, charge, people[at]["name"], inflow):
            return None
        yours = round(charge.my_share if charge.my_share is not None else charge.amount, 2)
        if got > yours + 0.005:
            return None
        was = {"split": current, "share": charge.my_share if charge.share_set else None}
        people[at] = {**people[at], "amount": round(float(people[at]["amount"]) + got, 2)}
        store.set_split(charge.fingerprint, current["mode"], people, current["watch"])
        store.set_share(charge.fingerprint, round(yours - got, 2))
        store.set_payback_kind(inflow.fingerprint, MADE_SPLIT)
        return was
    if current is None and (charge.paid_back or 0.0) - got > 0.005:
        # Others already paid some of it back with no split to say who;
        # a split now would have to guess their names, so it nets as before.
        return None
    yours = round(charge.my_share if current and charge.my_share is not None else charge.amount, 2)
    if got > yours + 0.005:
        return None
    was = {"split": current, "share": charge.my_share if charge.share_set else None}
    people.append({"name": person, "amount": got})
    store.set_split(charge.fingerprint, "amount", people, current["watch"] if current else True)
    store.set_share(charge.fingerprint, round(yours - got, 2))
    store.set_payback_kind(inflow.fingerprint, MADE_SPLIT)
    return was


def _made_by_paybacks(store, charge: Transaction, name: str, inflow: Transaction) -> bool:
    """Whether `name`'s place in the charge's split was made by paybacks of
    theirs (add_payer), not set by her."""
    kinds = store.payback_kinds()
    payer = store.payback_people()
    return any(charge.fingerprint in t.repays_all and t.fingerprint != inflow.fingerprint
               and kinds.get(t.fingerprint) == MADE_SPLIT
               and same_person(payer.get(t.fingerprint) or "", name)
               for t in store.all_transactions())


def drop_payer(store, inflow: Transaction, charge_id: str | None = None,
               checked: bool = False):
    """Undo `add_payer` when the payback is unlinked or moved: its person
    leaves the split and their part is hers again; a split left with nobody
    goes. Returns what to put back for an Undo, or None. `charge_id` is one
    of the purchases it covers (the first, unless said); `checked` is for
    `drop_payer_all`, which has already looked."""
    cid = charge_id or inflow.repays
    if not cid:
        return None
    if not checked:
        if store.payback_kinds().get(inflow.fingerprint) != MADE_SPLIT:
            return None
        store.set_payback_kind(inflow.fingerprint, None)
    charge = store.get_transaction(cid)
    current = store.splits().get(cid)
    if charge is None or current is None:
        return None
    person = store.payback_people().get(inflow.fingerprint)
    got = inflow.part_for(cid)
    if current.get("mode") == UNSURE:
        # SPLIT-C: the person this payback put on a Not sure yet split leaves
        # it with it, unless another payback of theirs is still here.
        idx = next((i for i, p in enumerate(current["people"]) if same_person(p["name"], person or "")), None)
        if idx is None or _made_by_paybacks(store, charge, current["people"][idx]["name"], inflow):
            return None
        was = {"split": current, "share": None}
        people = [p for i, p in enumerate(current["people"]) if i != idx]
        if people:
            store.set_split(charge.fingerprint, UNSURE, people, current["watch"], current.get("closed_at"))
        else:
            store.clear_split(charge.fingerprint)
        return was
    idx = next((i for i, p in enumerate(current["people"])
                if p["name"] == person and p["amount"] - got > -0.01), None)
    if idx is None:
        return None
    was = {"split": current, "share": charge.my_share if charge.share_set else None}
    left = round(float(current["people"][idx]["amount"]) - got, 2)
    if left > 0.005:
        # One of their e-Transfers goes; their place shrinks by it.
        people = [dict(p, amount=left) if i == idx else p for i, p in enumerate(current["people"])]
    else:
        people = [p for i, p in enumerate(current["people"]) if i != idx]
    if people:
        store.set_split(charge.fingerprint, current["mode"], people, current["watch"])
        store.set_share(charge.fingerprint, round((charge.my_share or 0.0) + got, 2))
    else:
        store.clear_split(charge.fingerprint)
        store.set_share(charge.fingerprint, None)
    return was


def drop_payer_all(store, inflow: Transaction) -> dict[str, dict]:
    """`drop_payer` for every purchase a payback covers (2026-10-28).
    Returns {charge id: what to put back}."""
    if not inflow.repays or store.payback_kinds().get(inflow.fingerprint) != MADE_SPLIT:
        return {}
    store.set_payback_kind(inflow.fingerprint, None)
    out = {}
    for cid in inflow.repays_all:
        was = drop_payer(store, inflow, cid, checked=True)
        if was is not None:
            out[cid] = was
    return out


# ── SPLIT-C decisions 2 and 4 (2026-11-09): linking to Not sure yet ──────

def cap_problem(store, charge_id: str, amount: float, inflow_id: str | None = None) -> str | None:
    """Decision 2 (S-09u2): a payback can take at most what a Not sure yet
    purchase still costs her; the rest is sorted next ("What's the other
    $40.00?", left to sort). The problem in her words, or None. What
    `inflow_id` already puts toward it is counted back first."""
    charge = store.get_transaction(charge_id)
    split = store.splits().get(charge_id)
    if charge is None or not split or split.get("mode") != UNSURE:
        return None
    room = still_yours(charge)
    if inflow_id:
        inflow = store.get_transaction(inflow_id)
        if inflow is not None and charge_id in inflow.repays_all:
            room = round(room + inflow.part_for(charge_id), 2)
    if _cents(amount) > _cents(room):
        return (f"Only ${room:,.2f} of {charge.merchant} still counts as yours, so that’s the most it "
                f"can take. Say what the other ${amount - room:,.2f} was.")
    return None


def reopen_closed(store, charge_id: str, marks: dict | None = None) -> bool:
    """Decision 4: a payback linked to a closed split (from search; closed
    ones aren't suggested) opens it again. The day it was closed goes in
    `marks` so Undo closes it again."""
    split = store.splits().get(charge_id)
    if not split or not split.get("closed_at"):
        return False
    if marks is not None:
        marks.setdefault("split_closed", {}).setdefault(charge_id, split["closed_at"])
    store.set_split_closed(charge_id, None)
    return True
