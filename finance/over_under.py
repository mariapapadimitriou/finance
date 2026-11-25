"""Overpaid and underpaid shares of a split (REFRESH-18, approved by the
product owner 2026-11-25; THL-289, THL-291, THL-181, THL-301, THL-260).
Claude Design, canvas "Pearl redesign" › Cash flow › G2-OverCard to
G2-SmallLands, notes n-overunder and n-small.

One rule, whichever way a payment is linked: it covers the share, and
anything over is extra and stays a question until she says what it is.
Never under You owe, never money in, before that. `settle` runs after every
link that credits a share (tests/test_over_under.py fails a new caller that
skips it). For each share credited, judged on everything paid for it:

* a let go gives way first, by what was paid over what it had, and is
  cleared when the share is covered;
* a shortfall that's small (SMALL_MAX and SMALL_SHARE, both) is let go,
  unless she undid one on that share, and only on the last share a deposit
  over several pays;
* an overpayment is stored on the share: 'small' (a quiet line, counts for
  nothing), 'ask' (the chip, and Needs a look) or 'owe' (under You owe). No
  state is one linked before this, and reads as 'owe'.

Above the cutoff she always says. A refund or a changed share never settles
anything, and changing a share takes a small let go of Pearl's back first
(`edited`); unlinking a payment takes any let go back (`released`).

Amounts are compared in cents. Everything that changes a split records how
it was in Undo marks: `splits`, `let_go` and `extra` (finance/marks.py
`undo_marks`), so one Undo puts the link, the let go and the state back.
"""

from __future__ import annotations

import copy
import math

SMALL_MAX = 2.00       # dollars
SMALL_SHARE = 0.10     # of the share

ASK, OWE, SMALL = "ask", "owe", "small"


def _cents(x) -> int:
    return int(round(float(x) * 100))


def _money(x: float) -> str:
    return f"${abs(x):,.2f}"


def is_small(diff: float, share: float) -> bool:
    """Up to $2.00 and no more than 10% of the share."""
    d = _cents(diff)
    return 0 < d <= _cents(SMALL_MAX) and d <= math.floor(_cents(share) * SMALL_SHARE + 1e-6)


def factor_of(charge) -> float:
    """A refund shrinks every share the same way (decision 6)."""
    back = getattr(charge, "refunded", 0.0) or 0.0
    return max(1.0 - back / charge.amount, 0.0) if charge.amount > 0 and back else 1.0


def whole_share(person: dict, factor: float = 1.0) -> float:
    """Their share before any of it was let go."""
    gone = person.get("let_go")
    return round(float(gone["was"] if gone else person["amount"]) * factor, 2)


def let_go_left(person: dict, factor: float = 1.0) -> float:
    """What of their share is let go now."""
    if not person.get("let_go"):
        return 0.0
    return round(max(whole_share(person, factor) - round(float(person["amount"]) * factor, 2), 0.0), 2)


def extra_of(person: dict, factor: float, paid: float, over: float) -> dict | None:
    """What a person paid over, as the app shows it: `state`, `amount` (the
    part still a question, or the small one), `owe` (what she owes back) and
    `said`. None when there's nothing over and nothing was said."""
    row = person.get("extra") or {}
    said = [q for q in row.get("said") or [] if isinstance(q, dict)]
    moved = [q for q in said if q.get("kind") != OWE]
    if over < 0.005:
        if not moved or paid < 0.005:
            return None
        return _shown("said", 0.0, 0.0, moved)
    state = row.get("state") or OWE
    if state == SMALL and not is_small(over, whole_share(person, factor)):
        # A refund or a changed share since: it isn't small any more, and
        # nothing settles it but her.
        state = ASK
    owed = min(sum(_cents(q.get("amount") or 0) for q in said if q.get("kind") == OWE), _cents(over))
    if state == OWE:
        owed = _cents(over)
    elif state == SMALL:
        owed = 0
    shown = moved + ([{"kind": OWE, "amount": owed / 100}] if owed else [])
    return _shown(state, round((_cents(over) - owed) / 100, 2), owed / 100, shown)


def _shown(state: str, amount: float, owe: float, said: list[dict]) -> dict:
    """`line` is the card's, `note` S-11e2's, `moved` what of the extra has
    gone somewhere (so Change what the extra is asks about all of it)."""
    return {"state": state, "amount": amount, "owe": owe, "said": said, "line": line_of(said),
            "note": " ".join(f"{note_of(q)}." for q in said) or None,
            "moved": sum(_cents(q.get("amount") or 0) for q in said if q.get("kind") != OWE) / 100}


def note_of(piece: dict) -> str:
    """S-11e2: "$10.00 was a gift"."""
    amount, kind = _money(float(piece.get("amount") or 0)), piece.get("kind")
    if kind == "gift":
        return f"{amount} was a gift"
    if kind == "payback":
        return f"{amount} was for {piece.get('merchant') or 'another purchase'}"
    return words(piece)


def line_of(said: list[dict]) -> str | None:
    """S-04o2, S-04o3: what she said, under the person's line. The same kind
    (and purchase) said twice is one amount."""
    by: dict[tuple, dict] = {}
    for q in said:
        key = (q.get("kind"), q.get("charge"), q.get("label"))
        if key in by:
            by[key]["amount"] = (_cents(by[key]["amount"]) + _cents(q.get("amount") or 0)) / 100
        else:
            by[key] = dict(q)
    return " · ".join(words(q) for q in by.values()) or None


def words(piece: dict) -> str:
    """One piece as the card says it: "You owe $15.00 back", "$15.00 gift",
    "$5.00 for Pizza Nova", "You sent $15.00 back". S-11 v2's other tiles
    say their own name, as a deposit's parts do."""
    amount, kind = _money(float(piece.get("amount") or 0)), piece.get("kind")
    if kind == OWE:
        return f"You owe {amount} back"
    if kind == "gift":
        return f"{amount} gift"
    if kind == "payback":
        return f"{amount} for {piece.get('merchant') or 'another purchase'}"
    if kind == "returned":
        return f"You sent {amount} back"
    return f"{amount} · {piece.get('label') or 'Sorted'}"


# ── Undo marks ────────────────────────────────────────────────────────────


def merge(a: dict | None, b: dict | None) -> dict:
    """Two sets of Undo marks as one. `a` is the older, so its entry stays."""
    from .api import _merge_marks
    a, b = dict(a or {}), dict(b or {})
    out = _merge_marks(a, b)
    for k in ("let_go", "extra"):
        if a.get(k) or b.get(k):
            out[k] = {cid: {**((b.get(k) or {}).get(cid) or {}), **((a.get(k) or {}).get(cid) or {})}
                      for cid in {**(b.get(k) or {}), **(a.get(k) or {})}}
    return out


def _remember(st, t, split: dict, p: dict, marks: dict) -> None:
    cid = t.fingerprint
    was = {"split": copy.deepcopy(split), "share": t.my_share if t.share_set else None}
    if t.joint:
        was["joint_part"] = st.joint_parts().get(cid)
    marks.setdefault("splits", {}).setdefault(cid, was)
    marks.setdefault("let_go", {}).setdefault(cid, {}).setdefault(p["name"], copy.deepcopy(p.get("let_go")))


def _remember_extra(cid: str, p: dict, marks: dict) -> None:
    marks.setdefault("extra", {}).setdefault(cid, {}).setdefault(p["name"], copy.deepcopy(p.get("extra")))


# ── Writing ───────────────────────────────────────────────────────────────


def reshare(st, t, split: dict) -> None:
    """Write the split back and her share with it: of her part, when the
    purchase is joint."""
    from . import splits as sp
    people = [{"name": p["name"], "amount": p["amount"], "weight": p.get("weight")} for p in split["people"]]
    st.set_split(t.fingerprint, split["mode"], people, split["watch"], split.get("closed_at"))
    st.set_share(t.fingerprint, sp.your_part(t, people, sp.split_base(t) if t.joint else None))


def paid_amount(paid: float, factor: float) -> float:
    """The stored share that comes to `paid` after a refund's shrinking."""
    return round(paid / factor, 2) if factor > 0 else 0.0


def _status(st, t, split: dict, name: str, credited: dict | None = None) -> dict | None:
    from . import splits as sp
    rows = sp.people_status(t, split, st.all_transactions(), st.payback_people(), credited_to=credited)
    return next((s for s in rows if s["name"] == name), None)


def _share(st, cid: str, name: str | None):
    """(purchase, split, person) for a share with an amount, or None."""
    from . import splits as sp
    t, split = st.get_transaction(cid), st.splits().get(cid)
    if t is None or not split or split.get("mode") == sp.UNSURE or not name:
        return None
    p = next((q for q in split["people"] if q["name"] == name), None)
    return (t, split, p) if p is not None else None


def let_go(st, cid: str, name: str, day: str, marks: dict, auto: bool = False) -> float:
    """What they still owe becomes hers: their part shrinks to what they've
    paid, and her share grows by the rest. Returns how much."""
    found = _share(st, cid, name)
    if not found:
        return 0.0
    t, split, p = found
    s = _status(st, t, split, name)
    if s is None or s["owes"] < 0.005:
        return 0.0
    _remember(st, t, split, p, marks)
    st.set_let_go(cid, name, p["let_go"]["was"] if p.get("let_go") else p["amount"], day, auto=auto)
    p["amount"] = paid_amount(s["paid"], factor_of(t))
    reshare(st, t, split)
    return s["owes"]


def take_back(st, cid: str, name: str, marks: dict) -> float:
    """The whole let go on a share comes back: they owe it again, less what
    they've paid. Returns how much was let go."""
    found = _share(st, cid, name)
    if not found or not found[2].get("let_go"):
        return 0.0
    t, split, p = found
    gone = let_go_left(p, factor_of(t))
    _remember(st, t, split, p, marks)
    p["amount"] = p["let_go"]["was"]
    st.clear_let_go(cid, name)
    reshare(st, t, split)
    return gone


def set_extra(st, cid: str, p: dict, marks: dict, **change) -> None:
    """Change what's stored about a share's extra, remembering how it was."""
    _remember_extra(cid, p, marks)
    row = {"state": None, "said": [], "hers": False, **(p.get("extra") or {}), **change}
    st.set_split_extra(cid, p["name"], row)
    p["extra"] = row


def say(st, cid: str, name: str, pieces: list[dict], marks: dict, again: bool = False) -> None:
    """Record what she said each piece of an extra was, once the money has
    moved. What's left over is still asked, however small: only a link
    settles anything."""
    found = _share(st, cid, name)
    if not found:
        return
    t, split, p = found
    said = [] if again else list((p.get("extra") or {}).get("said") or [])
    if not (p.get("extra") or {}).get("state") and not again:
        said = [q for q in said if q.get("kind") != OWE]
    names = st.merchant_names()
    from .tidy_names import display
    for q in pieces:
        q = {**q, "kind": OWE if q["kind"] == "overpaid" else q["kind"]}
        if q["kind"] == "payback":
            c = st.get_transaction(str(q.get("charge") or ""))
            if c is not None:
                q["merchant"] = display(c, names)
        said.append(q)
    s = _status(st, t, split, name)
    owed = sum(_cents(q.get("amount") or 0) for q in said if q.get("kind") == OWE)
    state = None if s["over"] < 0.005 else OWE if _cents(s["over"]) <= owed else ASK
    set_extra(st, cid, p, marks, state=state, said=said)


# ── The rule ──────────────────────────────────────────────────────────────


def links_of(st, deposit_id: str, charge_id: str | None = None) -> list[tuple[str, str]]:
    """(money in, purchase) for each payback a deposit makes: its payback
    parts in order, or the deposit itself."""
    stored = st.parts().get(deposit_id)
    if stored:
        out = [(p["part_id"], (p.get("detail") or {}).get("charge")) for p in stored if p["kind"] == "payback"]
    else:
        t = st.get_transaction(deposit_id)
        out = [(deposit_id, c) for c in (t.repays_all if t is not None else [])]
    return [(i, c) for i, c in out if c and (charge_id is None or c == charge_id)]


def credited_name(st, inflow_id: str, cid: str) -> str | None:
    """Whose share on this purchase a payment counts for, or None. Her own
    share, work paying all of it and a shop's refund aren't anyone's."""
    from . import splits as sp
    t, split = st.get_transaction(cid), st.splits().get(cid)
    if t is None or not split:
        return None
    credited: dict[str, str] = {}
    sp.people_status(t, split, st.all_transactions(), st.payback_people(), credited_to=credited)
    who = credited.get(inflow_id)
    return None if who in sp.SELF else who


def settle(st, marks: dict, links=(), cash=(), day: str | None = None, skip=()) -> list[dict]:
    """After a link. `links` are (money in, purchase) in order, one deposit's;
    `cash` are (purchase, name, amount) pieces of a cash or app payment.
    `skip` are shares said about in the same save. Records Undo in `marks`.
    Returns one row for each share credited: {charge, name, paid, extra,
    extra_state, let_go, back, back_hers, left}."""
    from .marks import REFUND_SHARE, REIMBURSEMENT
    if day is None:
        from .api import _today_iso
        day = _today_iso()
    kinds = st.payback_kinds()
    shares: list[list] = []                        # [purchase, name, paid by this payment]

    def add(cid, name, amount):
        row = next((r for r in shares if r[0] == cid and r[1] == name), None)
        if row is None:
            shares.append([cid, name, round(amount, 2)])
        else:
            row[2] = round(row[2] + amount, 2)
    for inflow_id, cid in links:
        # Work, or a shop's refund, isn't anyone paying their share back.
        if kinds.get(inflow_id) in (REFUND_SHARE, REIMBURSEMENT):
            continue
        name = credited_name(st, inflow_id, cid)
        x = st.get_transaction(inflow_id)
        if name and x is not None:
            add(cid, name, x.part_for(cid))
    for cid, name, amount in cash:
        add(cid, name, amount)
    out = []
    last = [(c, n) for c, n, _ in shares][-1:]
    for cid, name, here in shares:
        row = _settle_one(st, cid, name, here, day, marks,
                          short=[(cid, name)] == last, say=(cid, name) not in skip)
        if row:
            out.append(row)
    return out


def _settle_one(st, cid: str, name: str, here: float, day: str, marks: dict, short: bool, say: bool) -> dict | None:
    found = _share(st, cid, name)
    if not found:
        return None
    t, split, p = found
    if split.get("closed_at"):
        return None
    f = factor_of(t)
    s = _status(st, t, split, name)
    row = {"charge": cid, "name": name, "paid": here, "let_go": 0.0, "back": 0.0, "back_hers": False,
           "extra": 0.0, "extra_state": None, "left": s["owes"]}
    # (a) a let go gives way, by what was paid over what it had.
    if p.get("let_go") and s["over"] >= 0.005:
        _remember(st, t, split, p, marks)
        had = let_go_left(p, f)
        row["back_hers"] = not p["let_go"].get("auto")
        if _cents(s["paid"]) >= _cents(whole_share(p, f)):
            p["amount"] = p["let_go"]["was"]
            st.clear_let_go(cid, name)
            p["let_go"] = None
        else:
            p["amount"] = paid_amount(s["paid"], f)
        row["back"] = round(had - let_go_left(p, f), 2)
        row["back_all"] = p.get("let_go") is None
        reshare(st, t, split)
        t, split, p = _share(st, cid, name)
        s = _status(st, t, split, name)
    share = whole_share(p, f)
    # (b) a small shortfall is let go, never one she undid, never on top of
    # a let go that's still there.
    if (short and s["paid"] >= 0.005 and not p.get("let_go") and not (p.get("extra") or {}).get("hers")
            and is_small(s["owes"], share)):
        row["let_go"] = let_go(st, cid, name, day, marks, auto=True)
        t, split, p = _share(st, cid, name)
        s = _status(st, t, split, name)
    row["left"] = s["owes"]
    # (c) an overpayment is hers to say, unless it's small.
    was = p.get("extra") or {}
    said = list(was.get("said") or [])
    over = s["over"]
    if over < 0.005:
        if was.get("state") and say:
            set_extra(st, cid, p, marks, state=None, said=[q for q in said if q.get("kind") != OWE])
        return row
    row["extra"] = round(min(over, here), 2)
    if not say:
        return row
    if not was.get("state"):
        # Linked before this shipped: what was over already is owed back.
        before = round(min(over - here, over), 2)
        if before >= 0.005:
            said = [q for q in said if q.get("kind") != OWE] + [{"kind": OWE, "amount": before}]
    owed = sum(_cents(q.get("amount") or 0) for q in said if q.get("kind") == OWE)
    if _cents(over) <= owed:
        state = OWE
    else:
        state = SMALL if not owed and is_small(over, share) else ASK
    row["extra_state"] = state
    if state != was.get("state") or said != list(was.get("said") or []):
        set_extra(st, cid, p, marks, state=state, said=said)
    return row


def released(st, cid: str, name: str | None, marks: dict) -> None:
    """A payment unlinked or removed: a let go on that share comes back (it
    was the rest of a share that payment paid part of), and what was said of
    an extra that's gone goes with it."""
    found = _share(st, cid, name)
    if not found:
        return
    take_back(st, cid, name, marks)
    t, split, p = _share(st, cid, name)
    row = p.get("extra")
    if not row:
        return
    s = _status(st, t, split, name)
    if s["over"] < 0.005 and (row.get("state") or row.get("said")):
        keep = [q for q in row.get("said") or [] if q.get("kind") != OWE] if s["paid"] >= 0.005 and s["owes"] < 0.005 \
            else []
        set_extra(st, cid, p, marks, state=None, said=keep)


def refunded(st, charge_id: str | None, marks: dict) -> None:
    """A refund linked to a split purchase shrinks every share, so a small
    let go of Pearl's comes back (a refund never settles anything)."""
    split = st.splits().get(charge_id or "")
    for p in (split or {}).get("people") or []:
        if (p.get("let_go") or {}).get("auto"):
            take_back(st, charge_id, p["name"], marks)


def edited(before: dict, typed: float, paid: float, factor: float = 1.0) -> tuple[float, dict | None]:
    """Change share for someone let go: (the amount to store, the let go to
    keep as {was, day, auto} or None). A small let go of Pearl's comes back
    first; one she said never grows, so what's typed above it they owe."""
    gone = before["let_go"]
    if _cents(typed) == _cents(gone["was"]):
        return before["amount"], gone
    if gone.get("auto"):
        return typed, None
    floor = paid_amount(paid, factor)
    left = round(float(gone["was"]) - float(before["amount"]), 2)
    if _cents(typed) <= _cents(floor):
        return typed, None
    return round(max(typed - left, floor), 2), {**gone, "was": typed}


def paid_now(st, deposit_id: str) -> dict[tuple[str, str], float]:
    """What each share a payment pays has been paid in all, before the
    payment is linked again or taken off (`unpaid`)."""
    out: dict[tuple[str, str], float] = {}
    for inflow_id, cid in links_of(st, deposit_id):
        name = credited_name(st, inflow_id, cid)
        found = _share(st, cid, name)
        if found:
            out[(cid, name)] = _status(st, found[0], found[1], name)["paid"]
    return out


def unpaid(st, before: dict[tuple[str, str], float], marks: dict) -> None:
    """Each share that payment pays less of now: a let go on it comes back."""
    for (cid, name), paid in before.items():
        found = _share(st, cid, name)
        s = _status(st, found[0], found[1], name) if found else None
        if s is not None and _cents(s["paid"]) < _cents(paid):
            released(st, cid, name, marks)


# ── What the toast says ───────────────────────────────────────────────────


def line(rows: list[dict]) -> str | None:
    """"Priya paid back $19.00 · $1.00 let go"; "Georgia Klev paid back
    $19.77 · $0.23 extra"; "Georgia Klev paid back the $15.00 you let go".
    None when nothing here needs saying, or the rows are several people's."""
    if not rows or len({r["name"] for r in rows}) != 1:
        return None
    name = rows[0]["name"]
    gone = round(sum(r["let_go"] for r in rows), 2)
    extra = round(sum(r["extra"] for r in rows if r["extra_state"] in (SMALL, ASK)), 2)
    if len(rows) == 1 and rows[0]["back_hers"] and rows[0].get("back_all"):
        return f"{name} paid back the {_money(rows[0]['back'])} you let go"
    if gone < 0.005 and extra < 0.005 and not any(r["back"] >= 0.005 for r in rows):
        return None
    paid = round(sum(r["paid"] for r in rows) - extra, 2)
    what = f"{len(rows)} purchases · " if len(rows) > 1 else ""
    tail = f" · {_money(gone)} let go" if gone >= 0.005 else f" · {_money(extra)} extra" if extra >= 0.005 else ""
    return f"{name} paid back {what}{_money(paid)}{tail}"


def covers(st, charge, inflow, person: str | None, amount: float | None) -> str | None:
    """The person whose share of `charge` this whole payment goes to, so one
    of $55.00 on a $40.00 share is linked whole from every path, its extra
    asked about: they're on a split with amounts, and `amount` (what was
    asked to go there, None for all of it) covers what they owe. None keeps
    what was asked."""
    from . import splits as sp
    split = st.splits().get(charge.fingerprint)
    if not split or split.get("mode") == sp.UNSURE or split.get("closed_at") or not person:
        return None
    name = sp.pick([p["name"] for p in split["people"]], person)
    # A place a payback made (THL-260) grows with each payback; it has no
    # share to go over.
    if name is None or sp._made_by_paybacks(st, charge, name, inflow):
        return None
    if amount is None:
        return name
    # What this payment already pays here doesn't count against it.
    s = _status(st, charge, split, name)
    p = next(q for q in split["people"] if q["name"] == name)
    owes = _cents(s["owes"]) + _cents(let_go_left(p, factor_of(charge)))
    credited = credited_name(st, inflow.fingerprint, charge.fingerprint) if charge.fingerprint in inflow.repays_all else None
    if credited == name:
        owes += max(_cents(inflow.part_for(charge.fingerprint)) - _cents(s["over"]), 0)
    return name if owes > 0 and _cents(amount) >= owes else None


def owed_on(st, charge, person: str | None) -> float | None:
    """What `person` still owes on their share of this purchase; None when
    they haven't one."""
    from . import splits as sp
    split = st.splits().get(charge.fingerprint)
    if not split or split.get("mode") == sp.UNSURE or split.get("closed_at") or not person:
        return None
    name = sp.pick([p["name"] for p in split["people"]], person)
    s = _status(st, charge, split, name) if name else None
    return s["owes"] if s else None


def asked(transactions, splits: dict, payer: dict) -> list[dict]:
    """Every extra still a question, for Needs a look (S-21o): the newest
    payment that paid the share (the whole deposit, when it's in parts), or
    the purchase when only cash did."""
    from . import splits as sp
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for cid, split in splits.items():
        charge = by_id.get(cid)
        if charge is None or not any((p.get("extra") or {}).get("state") for p in split["people"]):
            continue
        credited: dict[str, str] = {}
        for s in sp.people_status(charge, split, transactions, payer, credited_to=credited):
            extra = s.get("extra") or {}
            if extra.get("state") != ASK or extra["amount"] < 0.005:
                continue
            paid = sorted((by_id[i] for i, who in credited.items() if who == s["name"] and i in by_id),
                          key=lambda t: (t.date, t.fingerprint))
            t = paid[-1] if paid else charge
            whole = by_id.get((t.raw or {}).get("part_of") or "") or t
            out.append({"key": f"over:{cid}:{s['name']}", "txn": whole,
                        "over": {"charge": cid, "merchant": charge.merchant, "name": s["name"],
                                 "amount": extra["amount"], "share": s["amount"], "note": extra["note"],
                                 "word": sp.payment_word(whole) if paid else None}})
    return out


def over_of(charge, split: dict | None, inflow, transactions, payer: dict) -> dict | None:
    """PB-41o: what of a payment is over the share it paid, for its own page
    and "Paid back this month": the extra is the newest payment's first.
    {charge, name, share, back, extra, state, line} or None when it's not over."""
    from . import splits as sp
    if not split or split.get("mode") == sp.UNSURE:
        return None
    credited: dict[str, str] = {}
    rows = sp.people_status(charge, split, transactions, payer, credited_to=credited)
    name = credited.get(inflow.fingerprint)
    s = next((q for q in rows if q["name"] == name), None)
    if s is None or s["over"] < 0.005 or not s.get("extra"):
        return None
    left = _cents(s["over"])
    theirs = sorted((t for t in transactions if credited.get(t.fingerprint) == name),
                    key=lambda t: (t.date, t.fingerprint), reverse=True)
    for t in theirs:
        here = _cents(t.part_for(charge.fingerprint))
        take = min(left, here)
        left -= take
        if t.fingerprint == inflow.fingerprint:
            if take < 1:
                return None
            return {"charge": charge.fingerprint, "name": name, "share": s["amount"], "back": (here - take) / 100,
                    "extra": take / 100, "state": s["extra"]["state"], "line": s["extra"]["line"],
                    "asked": s["extra"]["amount"], "note": s["extra"]["note"],
                    "word": sp.payment_word(next((x for x in transactions if x.fingerprint
                                                  == (inflow.raw or {}).get("part_of")), inflow))}
    return None
