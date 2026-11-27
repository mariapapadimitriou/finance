"""The payback question, in Pearl's words (Figma Proposals › "Payback
question" 1418:88290, note 1419:89986; approved by the product owner
2026-11-16; THL-289, THL-291, THL-181, THL-231, THL-232, THL-301). It
replaces T-70 and the app's old list of three answers.

Worked out here so the app shows the server's words, never its own. Less
text (LT-03 1425:7351, dark 1425:7552; TEXT-01, approved 2026-11-16): the
Why card, the runner-up line and what Yes does are gone. The reason sits in
the tile.

- `tiles`: up to three likely purchases, best first (PQ-03, PQ-03b). Only
  the first is Pearl's guess, drawn dashed. Each carries its category, the
  short card name (account_names.py), its title ("Añejo · $61.57") and the
  reason in a few words, `compare`: "about a third · 2 days before", on a
  split "$20.00 of mPg’s $30.79 · $10.79 still to come", or from a message
  "“tacos”".
- `card`: the dashed question card on the deposit's own page (PQ-03p):
  "Pearl’s guess · about a third".

A tile answers through the payback path that already exists (POST
/api/transactions/<id>/mark {"case": "payback", "charge": …}); nothing here
writes.
"""

from __future__ import annotations

from datetime import date

from .models import Transaction

MAX_TILES = 3

_FRACTION = {2: "half", 3: "a third", 4: "a quarter", 5: "a fifth", 6: "a sixth"}


def _money(x: float) -> str:
    return f"${abs(x):,.2f}"


def _whose(name: str) -> str:
    """"mPg’s", "James’"."""
    return f"{name}’" if name.lower().endswith("s") else f"{name}’s"


def _gap(t: Transaction, day: str) -> int:
    return (date.fromisoformat(t.date[:10]) - date.fromisoformat(day[:10])).days


def _before(gap: int) -> str:
    """"2 days before": when the purchase was, from the money (LT-03)."""
    if gap <= 0:
        return "the same day"
    if gap == 1:
        return "the day before"
    return f"{gap} days before"


def share_of(got: float, amount: float) -> int | None:
    """How many ways the purchase was shared, when the money is one share
    of it: within $3 or 5% for tips and rounding, as review.py's
    charge_candidates reads it."""
    best = None
    for n in range(2, 7):
        share = amount / n
        if abs(share - got) <= max(3.0, share * 0.05):
            if best is None or abs(amount / n - got) < abs(amount / best - got):
                best = n
    return best


def card_names(st) -> dict[str, str]:
    """Each account's short name by id ("Amex Cobalt"), as Your accounts
    shows it (account_names.py, #367)."""
    from .profile_api import _all_rows
    try:
        return {a["id"]: a["short_name"] for a in _all_rows(st)}
    except Exception:  # noqa: BLE001 - a name is a nicety; the question stands without it
        return {}


def _card(c: Transaction, cards: dict[str, str]) -> str:
    if cards.get(c.account_id):
        return cards[c.account_id]
    from .account_names import short_name
    label = (c.account_nickname or c.account_name or "").split(" ••")[0]
    return short_name(label) if label.strip() else ""


def _shown(c: Transaction) -> str:
    """TEST-46: the tidy name ("Bar Isabel", not "Bar Isabel Toronto")."""
    from .tidy_names import of
    return of(c) or c.merchant


def _tile(c: Transaction, cards: dict[str, str], **extra) -> dict:
    return {"charge": c.fingerprint, "merchant": _shown(c), "amount": round(c.amount, 2),
            "date": c.date[:10], "category": c.category or "Other", "card": _card(c, cards), **extra}


def _hers(splits: dict, r: dict) -> bool:
    """She undid a small let go on this share: Pearl doesn't settle it."""
    people = (splits.get(r["charge_id"]) or {}).get("people") or []
    p = next((q for q in people if q["name"] == r["name"]), {})
    return bool((p.get("extra") or {}).get("hers") or p.get("let_go"))


def build(t: Transaction, transactions: list[Transaction], splits: dict | None = None,
          payer: dict | None = None, people: list[str] | None = None,
          cards: dict[str, str] | None = None, sender: str | None = None,
          candidates: list[dict] | None = None) -> dict | None:
    """The question for one deposit, or None when no purchase is likely. A
    nameless e-Transfer isn't "Interac" paying her back: Pearl guesses the
    purchase and asks who (P5h, `_nameless`). `sender` is the name the review already
    settled on; `candidates` are review.charge_candidates', when computed."""
    from .categorize import is_generic_transfer_name
    from .etransfers import memo, party
    from .marks import memo_match
    from .review import charge_candidates
    from .splits import for_inflow

    if t.amount >= 0 or t.repays:
        return None
    cards = cards or {}
    sent = party(t, people) or {}
    who = sender or (sent.get("name") if sent.get("direction") == "from" else None)
    # "Name them" only where the bank's name is all Pearl has: once she
    # names them, or for a payer that isn't an e-Transfer, it's a name.
    named = sent.get("named_by") == "you" or not sent
    if not who:
        if not (t.merchant or "").strip():
            return None
        if is_generic_transfer_name(t.merchant):
            # P5h: no clear name. Pearl guesses the purchase, never who.
            return _nameless(t, transactions, splits, payer, cards, candidates)
        who = t.merchant
    got = round(-t.amount, 2)
    by_id = {x.fingerprint: x for x in transactions}
    tiles: list[dict] = []
    seen: set[str] = set()

    # 1. Splits the sender is on and still owes on (PQ-03b): the closest to
    # what they owe first, then the latest. One they'd overpay says the extra
    # (PQ-03o, REFRESH-18), and one a small difference settles says so first
    # (PQ-03s); then a share she let go of.
    if splits:
        from .over_under import is_small
        from .splits import brief, let_go_rows
        rows, theirs = for_inflow(t, transactions, splits, payer or {})
        owed = [r for r in rows if theirs and not r.get("unknown") and r["owes"] >= 0.005]
        if any(got <= r["owes"] + 0.005 for r in owed):
            # Never one they'd overpay, when another takes all of it.
            owed = [r for r in owed if got <= r["owes"] + 0.005]
        else:
            owed.sort(key=lambda r: abs(r["owes"] - got))
        for r in let_go_rows(t, transactions, splits, payer or {}):
            c = r["charge"]
            if any(c.fingerprint == o["charge_id"] for o in owed) or got < 0.005:
                continue
            owed.append(brief(r))
        # for_inflow lists the latest first; a stable sort keeps that.
        owed.sort(key=lambda r: abs(r["owes"] - got) >= 0.005)
        for r in owed:
            c = by_id.get(r["charge_id"])
            if c is None or c.fingerprint in seen:
                continue
            seen.add(c.fingerprint)
            rest = round(r["owes"] - got, 2)
            name = r["name"]
            compare = f"{_money(got)} of {_whose(name)} {_money(r['owes'])}"
            toast = f"{who} paid back {_money(got)} for {_shown(c)}"
            # S-44s, S-44s2, S-04g2: the toast says what it settled.
            if r.get("let_go"):
                compare = f"You let {_money(r['owes'])} go"
                if rest < 0.005:
                    toast = f"{name} paid back the {_money(r['owes'])} you let go"
            elif rest <= -0.005:
                compare = f"{_money(r['owes'])} of {_money(got)} · {_money(rest)} extra"
                toast = f"{name} paid back {_money(r['owes'])} · {_money(rest)} extra"
            elif is_small(rest, r["share"]) and not _hers(splits, r):
                compare = f"{_money(got)} of {_money(r['owes'])} · {_money(rest)} let go"
                toast = f"{name} paid back {_money(got)} · {_money(rest)} let go"
            after = None
            if not r.get("let_go") and rest >= 0.005 and not (is_small(rest, r["share"]) and not _hers(splits, r)):
                # TP-Words (fewer taps, P5): "Priya still owes $2.50", never
                # "$2.50 still to come"; the card says it with "after this".
                compare += f" · {name} still owes {_money(rest)}"
                after = f"{name} still owes {_money(rest)} after this"
            tiles.append(_tile(c, cards, kind="split", person=name, owes=r["owes"],
                               title=f"{_shown(c)} · {_whose(name)} share",
                               compare=compare, toast=toast, **({"after": after} if after else {})))

    # 2. The purchase the sender's message names.
    said = memo_match(t, transactions)
    if said and said["id"] not in seen and said["id"] in by_id:
        c = by_id[said["id"]]
        seen.add(c.fingerprint)
        n = share_of(got, c.amount)
        said_words = memo(t)
        tiles.append(_tile(c, cards, kind="memo", ways=n, memo=said_words,
                           title=f"{_shown(c)} · {_money(c.amount)}",
                           compare=f"“{said_words}”" if said_words else (f"about {_FRACTION[n]}" if n else ""),
                           toast=f"{who} paid back {_money(got)} for {_shown(c)}"))

    # 3. An even share of a purchase, best first (review.charge_candidates).
    for cand in candidates if candidates is not None else charge_candidates(t, transactions):
        c = by_id.get(cand["id"])
        if c is None or c.fingerprint in seen:
            continue
        seen.add(c.fingerprint)
        n = cand.get("split") or share_of(got, c.amount)
        reason = [f"about {_FRACTION[n]}"] if n in _FRACTION else []
        reason.append(_before(_gap(t, c.date)))
        tiles.append(_tile(c, cards, kind="share", ways=n,
                           title=f"{_shown(c)} · {_money(c.amount)}",
                           compare=" · ".join(reason),
                           toast=f"{who} paid back {_money(got)} for {_shown(c)}"))

    tiles = tiles[:MAX_TILES]
    if not tiles:
        return None
    best = tiles[0]
    best["guess"] = True

    # PQ-03p: the dashed card on the deposit's page, "Pearl’s guess · about
    # a third" (TEXT-01).
    m = best["merchant"]
    if best["kind"] == "split":
        guess = best["compare"]
    elif best.get("ways") in _FRACTION:
        guess = f"about {_FRACTION[best['ways']]}"
    else:
        guess = best["compare"]
    return {
        "who": who, "named": named, "tiles": tiles,
        # PQ-03b: a part payment stays on the split.
        "part": best["kind"] == "split" and best["owes"] - got >= 0.005,
        "card": {"title": f"Paying you back for {m}?",
                 "line": f"Pearl’s guess · {guess}" if guess else "Pearl’s guess"},
    }


_SHARE_WORDS = {2: "Half", 3: "A third", 4: "A quarter", 5: "A fifth", 6: "A sixth"}


def _nameless(t: Transaction, transactions: list[Transaction], splits: dict | None, payer: dict | None,
              cards: dict[str, str], candidates: list[dict] | None) -> dict | None:
    """P5h (TP-P5-NeedsALook): money with no clear name on it ("Interac
    e-Transfer"). Pearl still guesses the purchase, "A third of Pai Northern
    Thai?", but never who: each tile carries everyone on the split who still
    owes (`people`), and the app asks Who sent this? before anything is
    credited. Nobody is guessed, added to a split, or remembered."""
    from .review import charge_candidates
    from .splits import for_inflow

    got = round(-t.amount, 2)
    by_id = {x.fingerprint: x for x in transactions}
    who = _shown(t) or "Money in"
    tiles: list[dict] = []
    seen: set[str] = set()

    # 1. A split someone on it still owes about this much on, the closest first.
    if splits:
        rows, _ = for_inflow(t, transactions, splits, payer or {})
        by_charge: dict[str, list[dict]] = {}
        for r in rows:
            if r.get("unknown") or r["owes"] < 0.005:
                continue
            by_charge.setdefault(r["charge_id"], []).append(r)
        fits = []
        for cid, people in by_charge.items():
            near = min(abs(p["owes"] - got) for p in people)
            if near <= max(3.0, got * 0.05):
                fits.append((near, cid, people))
        fits.sort(key=lambda f: f[0])
        for _, cid, people in fits:
            c = by_id.get(cid)
            if c is None or cid in seen:
                continue
            seen.add(cid)
            n = share_of(got, c.amount)
            tiles.append(_tile(c, cards, kind="split", ways=n,
                               people=[{"name": p["name"], "owes": round(p["owes"], 2)} for p in people],
                               title=f"{_shown(c)} · {_money(c.amount)}",
                               compare=_fraction_line(got, c.amount, n),
                               toast=f"Paid back {_money(got)} for {_shown(c)}"))

    # 2. An even share of a purchase nobody split.
    for cand in candidates if candidates is not None else charge_candidates(t, transactions):
        c = by_id.get(cand["id"])
        if c is None or c.fingerprint in seen or (splits or {}).get(c.fingerprint):
            continue
        seen.add(c.fingerprint)
        n = cand.get("split") or share_of(got, c.amount)
        tiles.append(_tile(c, cards, kind="share", ways=n, people=[],
                           title=f"{_shown(c)} · {_money(c.amount)}",
                           compare=_fraction_line(got, c.amount, n),
                           toast=f"Paid back {_money(got)} for {_shown(c)}"))

    tiles = tiles[:MAX_TILES]
    if not tiles:
        return None
    best = tiles[0]
    best["guess"] = True
    best["after"] = best["compare"]
    m, n = best["merchant"], best.get("ways")
    title = f"{_SHARE_WORDS[n]} of {m}?" if n in _SHARE_WORDS else f"Paying you back for {m}?"
    return {"who": who, "named": False, "unknown": True, "tiles": tiles, "part": False,
            "card": {"title": title, "line": f"Pearl’s guess · {best['compare']}"}}


def _fraction_line(got: float, amount: float, n: int | None) -> str:
    """"Exactly a third of $120.00", "About half of $80.00", "$40.00 of $95.00"."""
    if n in _FRACTION:
        exact = abs(round(amount / n, 2) - got) < 0.015
        return f"{'Exactly' if exact else 'About'} {_FRACTION[n]} of {_money(amount)}"
    return f"{_money(got)} of {_money(amount)}"


def annotate(st, review: dict, txns: list[Transaction]) -> None:
    """Add `payback` to each money-in question it answers: the deposits
    that could be someone paying her back. Not a refund from a store, the
    rest of a deposit, the extra on a paid-back purchase, or money the
    evidence already calls a loan."""
    from .etransfers import known_people
    items = [it for it in review.get("money_in") or []
             if not it.get("rest") and not it.get("extra")
             and (it.get("guess") or {}).get("action") not in ("refund", "unknown")
             and (it.get("pair") or {}).get("kind") not in ("lent", "borrowed", "refund", "reimbursement")]
    if not items:
        return
    splits, payer = st.splits(), st.payback_people()
    people = known_people(txns, splits, payer)
    cards = card_names(st)
    by_id = {t.fingerprint: t for t in txns}
    for it in items:
        t = by_id.get(it["txn"]["id"])
        if t is None:
            continue
        q = build(t, txns, splits, payer, people, cards, sender=it.get("from"),
                  candidates=it.get("candidates"))
        if q:
            it["payback"] = q


def for_deposit(st, t: Transaction) -> dict | None:
    """PQ-03p: the question for one deposit's own page."""
    from .etransfers import known_people
    txns = st.all_transactions()
    splits, payer = st.splits(), st.payback_people()
    return build(t, txns, splits, payer, known_people(txns, splits, payer), card_names(st))
