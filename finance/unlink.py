"""Unlink a payback from the purchase it paid back (SPLIT-25, THL-291:
"Unlinking any part from either side restores both sides").

The purchase's PAID BACK and REFUNDED BY rows open S-05o (View / Unlink…),
then S-34s or an S-34k sheet, then S-05t's toast with Undo. Each row
carries what the sheet says (`link`), worked out here so the line, the
button and the toast always match what Unlink does:

* An e-Transfer or bank payback for this purchase only: unlinked, back to
  Needs a look.
* One that also paid other purchases: only this purchase's part comes off;
  the others keep theirs as parts of the deposit, and this part is "$x left
  to sort" on it (as SPLIT-16).
* Cash or another app: this purchase's piece of the payment is forgotten.
  Cash a deposit holds comes out of the deposit's cash part, which leaves
  the deposit "$x left to sort".
* A part of a deposit (S-26): only that part goes; the deposit keeps its
  other parts and the amount is left to sort.
* Work paying me back: the purchase waits to be reimbursed again if it was.
* A refund: it stops coming off the purchase.
* A payback that made the split (THL-260): its person comes off this split
  only.

Every unlink returns `undo` marks (finance/marks.py `undo_marks`) that put
it back exactly as it was.
"""

from __future__ import annotations

from datetime import date

from . import parts as dp
from . import splits as sp
from .models import Transaction


def _money(x: float) -> str:
    return f"${abs(x):,.2f}"


def _day(iso: str | None) -> str:
    if not iso:
        return ""
    d = date.fromisoformat(iso[:10])
    return f"{d:%b} {d.day}"


def _stay(names: list[str]) -> str:
    """"Pizza Nova stays paid back", "Pizza Nova and Costco stay paid back"."""
    return f"{sp.and_list(names)} {'stays' if len(names) == 1 else 'stay'} paid back"


def _of(name: str) -> str:
    """"Loblaws’ $30.00", "Pizza Nova’s $30.00"."""
    return f"{name}’" if name.lower().endswith("s") else f"{name}’s"


def _look(out: dict, heading: str, card: str, card_amount: float, confirm: str | None = None,
          keep: str = "Keep linked", note: str | None = None, overline: str = "UNLINK") -> dict:
    """REFRESH-02 (S-34sr, S-34kr1–10): the custom Unlink? sheet's words on
    top of SPLIT-25's: its title, the payment card, the two buttons and the
    shared payment's footnote."""
    out["sheet"].update(heading=heading, card={"label": card, "amount": round(card_amount, 2)},
                        confirm=confirm or f"Unlink {_money(out['amount'])}", keep=keep, note=note,
                        overline=overline)
    return out


def _whose(name: str | None) -> str:
    """"Sam’s", or "this" when Pearl doesn't know who sent it."""
    return _of(name) if name and name != "They" else "this"


def _root(c: dict) -> int:
    return int(c.get("origin") or c["id"])


# ── What each row says (S-05o, S-34s, S-34k) ──────────────────────────────


def inflow_link(st, charge: Transaction, x: Transaction, who: str | None, by_id: dict,
                kinds: dict, stored_parts: dict) -> dict:
    """`_inflow_link`, with the initials the sheet shows (`face`): the
    person, else the name the bank put on it."""
    out = _inflow_link(st, charge, x, who, by_id, kinds, stored_parts)
    face = x.merchant if out["kind"] == "reimbursement" else (who or sp.sender_name(x) or x.merchant)
    out["sheet"]["face"] = face or "Payment"
    return out


def _inflow_link(st, charge: Transaction, x: Transaction, who: str | None, by_id: dict,
                 kinds: dict, stored_parts: dict) -> dict:
    """A bank payback, a part of a deposit or work paying her back, on this
    purchase: what S-05o and the Unlink? sheet say, and what unlinking does."""
    from .marks import REIMBURSEMENT, was_waiting
    cid = charge.fingerprint
    here = x.part_for(cid)
    whole = round(-x.amount, 2)
    word = sp.payment_word(x)
    kind = kinds.get(x.fingerprint)
    made = kind == sp.MADE_SPLIT
    others = [by_id[c].merchant if c in by_id else "another purchase" for c in x.repays_all if c != cid]
    parent = by_id.get((x.raw or {}).get("part_of") or "")
    sender = who or sp.sender_name(x)
    name = who or sender or "They"
    out: dict = {"id": x.fingerprint, "inflow": x.fingerprint, "cash_id": None, "amount": here,
                 "whole": whole, "date": x.date[:10], "person": who, "others": others,
                 "made_split": made, "was_waiting": False, "deposit": None}
    if kind == REIMBURSEMENT:
        entry = next((p for p in stored_parts.get(parent.fingerprint, []) if p["part_id"] == x.fingerprint),
                     None) if parent else None
        if entry is not None:
            waits = bool((entry.get("detail") or {}).get("was_excluded"))
        else:
            rest = [i for i in st.paybacks_for(cid) if i != x.fingerprint]
            waits = was_waiting(st, cid) and not rest
        payer = x.merchant or "work"
        out.update(kind="reimbursement", was_waiting=waits, goes="needs_a_look", noun="reimbursement",
                   message=f"{payer} · Work paying me back",
                   view={"id": parent.fingerprint if parent else x.fingerprint, "label": "View the deposit"},
                   dialog=f"{payer} paid back {_money(here)}",
                   sheet={"title": "Unlink?", "name": payer,
                          "sub": f"{_money(here)} · {_day(x.date)} · Work paying me back", "ask": None,
                          # REFRESH-03 (S-34kr7): "Loblaws waits to be reimbursed again.
                          # The $84.12 goes back to Needs a look."
                          "line": (f"{charge.merchant} waits to be reimbursed again. "
                                   if waits else f"{charge.merchant} counts as your spending again. ")
                          + f"The {_money(here)} goes back to Needs a look.",
                          "button": "Unlink"},
                   toast=(f"Unlinked · {charge.merchant} is waiting to be reimbursed" if waits
                          else f"Unlinked · {charge.merchant} counts as your spending again"))
        return _look(out, "Unlink the reimbursement?", f"{payer} · {_day(x.date)}", here)
    if parent is not None:
        # S-26: "Part of Dad’s $600.00".
        total = round(-parent.amount, 2)
        of = f"{_of(sender)} {_money(total)}" if sender else f"a {_money(total)} deposit"
        out.update(kind="part", goes="left_to_sort", noun="deposit part",
                   deposit={"id": parent.fingerprint, "amount": total, "date": parent.date[:10]},
                   message=f"Part of {_of(sender)} {_money(total)} deposit" if sender
                   else f"Part of a {_money(total)} deposit",
                   view={"id": parent.fingerprint, "label": "View the deposit"},
                   dialog=f"{name} paid back {_money(here)}")
        # REFRESH-03 (S-34kr9): "Dad will owe you $228.00 again. This $228.00
        # goes back to Needs a look."
        owe = f"{name} comes off the split too." if made else f"{name} will owe you {_money(here)} again."
        out["sheet"] = {"title": "Unlink?", "name": f"Part of {of}", "sub": f"{_money(here)} · {_day(x.date)}",
                        "ask": None,
                        "line": f"{owe} This {_money(here)} goes back to Needs a look.",
                        "button": "Unlink"}
        out["toast"] = f"Unlinked · {name} taken off the split" if made else None
        card = (f"Part of {_money(total)} from {sender} · {_day(x.date)}" if sender
                else f"Part of a {_money(total)} deposit · {_day(x.date)}")
        return _look(out, f"Unlink {_whose(name)} {_money(here)}?", card, here,
                     confirm="Unlink and remove" if made else None)
    # An e-Transfer or another bank payment.
    title = word if word == "e-Transfer" else word.capitalize()
    out.update(kind="bank", noun=word, view={"id": x.fingerprint, "label": f"View the {word}"},
               dialog=f"{name} paid back {_money(here)}")
    # REFRESH-03: each consequence once (who owes again; what goes back to
    # Needs a look), and "Priya comes off the split too." for THL-260's case.
    owe = f"{name} comes off the split too." if made else f"{name} will owe you {_money(here)} again."
    if others:
        # S-05o / S-05or: "Part of $60.00 · also paid back Pizza Nova".
        out.update(goes="left_to_sort",
                   message=f"Part of {_money(whole)} · also paid back {sp.and_list(others)}")
        # S-34s / S-34sr: "Unlink only Loblaws’ $30.00?" over "Jo will owe you
        # $30.00 again. The $30.00 goes back to Needs a look."
        out["sheet"] = {"title": "Unlink?", "name": f"{word} from {sender}" if sender else x.merchant,
                        "sub": f"{_money(whole)} · {_day(x.date)}",
                        "ask": f"Unlink only {_of(charge.merchant)} {_money(here)}?",
                        "line": f"{owe} The {_money(here)} goes back to Needs a look.",
                        "button": f"Unlink {_money(here)}"}
    else:
        out.update(goes="needs_a_look", message=f"{title} · {_day(x.date)}")
        out["sheet"] = {"title": "Unlink?", "name": f"{word} from {sender}" if sender else x.merchant,
                        "sub": f"{_money(here)} · {_day(x.date)}", "ask": None,
                        "line": f"{owe} The {word} goes back to Needs a look.", "button": "Unlink"}
    out["toast"] = f"Unlinked · {name} taken off the split" if made else None
    card = f"{word} from {sender} · {_day(x.date)}" if sender else f"{x.merchant} · {_day(x.date)}"
    confirm = "Unlink and remove" if made else None
    if others:
        # The footnote about the whole payment is gone (S-34sr); the app reads
        # it as a VoiceOver hint on the payment row.
        return _look(out, out["sheet"]["ask"], card, whole, confirm=confirm)
    return _look(out, f"Unlink {_whose(name)} {word}?", card, whole, confirm=confirm)


def cash_link(st, charge: Transaction, name: str, pay: dict, by_id: dict) -> dict:
    """A cash or app payment on this purchase (one of `splits.payments`)."""
    here = pay["amount"]
    app = pay.get("via") == "app"
    app_name = pay.get("app") or ("Another app" if app else None)
    whole = round(pay.get("whole") or here, 2)
    # SPLIT-19: every purchase the payment paid back, its own first.
    others = [m for m in pay.get("paid_back") or [] if m != charge.merchant]
    held = [c for c in st.split_cash() if _root(c) == pay["id"] and c["txn_id"] == charge.fingerprint
            and c.get("kind") is None and c["deposit_id"]]
    deposit = None
    held_amount = round(sum(c["amount"] for c in held), 2)
    if held:
        part = by_id.get(held[0]["deposit_id"])
        parent = by_id.get(((part.raw or {}).get("part_of") if part else None) or "")
        if parent is not None:
            deposit = {"id": parent.fingerprint, "amount": round(-parent.amount, 2), "date": parent.date[:10]}
    what = f"{app_name} payment" if app else "cash"
    head = f"{app_name} from {name}" if app else f"Cash from {name}"
    out: dict = {"id": f"cash:{pay['id']}", "inflow": None, "cash_id": pay["id"], "amount": here,
                 "whole": whole, "date": pay["day"], "person": name, "others": others,
                 "made_split": False, "was_waiting": False, "deposit": deposit,
                 "kind": "app" if app else "cash", "noun": what,
                 "dialog": f"{name} paid back {_money(here)}",
                 "view": {"id": deposit["id"], "label": "View the deposit"} if deposit else None,
                 "toast": None}
    sub = f"{_money(whole if others else here)} · {_day(pay['day'])}"
    if deposit:
        sub += f" · deposited {_day(deposit['date'])}"
    # REFRESH-03 (S-34kr3–6): each consequence once.
    if others:
        out.update(goes="forgotten",
                   message=f"Part of {_money(whole)} · also paid back {sp.and_list(others)}")
        out["sheet"] = {"title": "Unlink?", "name": head, "sub": sub,
                        "ask": f"Unlink only {_of(charge.merchant)} {_money(here)}?",
                        "line": f"{name} will owe you {_money(here)} again. {_stay(others)}.",
                        "button": f"Unlink {_money(here)}"}
    elif deposit:
        out.update(goes="left_to_sort",
                   message=f"Cash · {_day(pay['day'])} · deposited {_day(deposit['date'])}")
        out["sheet"] = {"title": "Unlink?", "name": head, "sub": sub, "ask": None,
                        "line": f"{name} will owe you {_money(here)} again. This {_money(held_amount)} "
                                f"goes back to Needs a look.",
                        "button": "Unlink"}
    else:
        out.update(goes="forgotten", message=f"{app_name if app else 'Cash'} · {_day(pay['day'])}")
        gone = (f"The {app_name if app_name != 'Another app' else 'app'} payment is forgotten"
                if app else "The cash is forgotten")
        out["sheet"] = {"title": "Unlink?", "name": head, "sub": sub, "ask": None,
                        "line": f"{name} will owe you {_money(here)} again. {gone}.",
                        "button": "Unlink"}
    out["sheet"]["face"] = name
    label = app_name if app else "Cash"
    if others:
        return _look(out, out["sheet"]["ask"], f"{label} · {_day(pay['day'])}", whole)
    if deposit:
        return _look(out, f"Unlink {_of(name)} cash?", f"Cash, deposited {_day(deposit['date'])}", here)
    what_here = ("app payment" if app_name == "Another app" else f"{app_name} payment") if app else "cash"
    return _look(out, f"Unlink {_of(name)} {what_here}?", f"{label} · {_day(pay['day'])}", here)


def refund_link(charge: Transaction, x: Transaction) -> dict:
    """A refund of this purchase (S-34k "Unlink refund?")."""
    amount = round(-x.amount, 2)
    out = {"id": x.fingerprint, "inflow": x.fingerprint, "cash_id": None, "amount": amount, "whole": amount,
            "date": x.date[:10], "person": None, "others": [], "made_split": False, "was_waiting": False,
            "deposit": None, "kind": "refund", "goes": "needs_a_look", "noun": "refund",
            "message": f"Refund · {_day(x.date)}", "view": {"id": x.fingerprint, "label": "View the refund"},
            "dialog": f"{x.merchant} refunded {_money(amount)}",
            "sheet": {"title": "Unlink refund?", "name": f"Refund from {x.merchant}", "face": x.merchant,
                      "sub": f"{_money(amount)} · {_day(x.date)}", "ask": None,
                      # REFRESH-03 (S-34kr8).
                      "line": f"The {_money(amount)} stops coming off {charge.merchant} and goes back to "
                              f"Needs a look.",
                      "button": "Unlink"},
            "toast": "Refund unlinked"}
    return _look(out, "Unlink refund?", f"{x.merchant} refund · {_day(x.date)}", out["amount"],
                 confirm="Unlink refund", keep="Keep it", overline="REFUND")


def add_links(st, charge: Transaction, splitting: dict, txns: list[Transaction], payer: dict) -> None:
    """S-05v: each person on the split card with every payment that paid
    them back here (`links`), so every PAID BACK row opens S-05o."""
    split = st.splits().get(charge.fingerprint)
    if not split:
        return
    credited: dict[str, str] = {}
    sp.people_status(charge, split, txns, payer, credited_to=credited)
    by_id = {t.fingerprint: t for t in txns}
    kinds, stored = st.payback_kinds(), st.parts()
    linked = [t for t in txns if charge.fingerprint in t.repays_all]
    for p in splitting.get("people") or []:
        links = [inflow_link(st, charge, x, p["name"], by_id, kinds, stored) for x in linked
                 if credited.get(x.fingerprint) == p["name"]]
        links += [cash_link(st, charge, p["name"], pay, by_id) for pay in p.get("payments") or []]
        p["links"] = sorted(links, key=lambda link: (link["date"], str(link["id"])))


# ── Unlinking ─────────────────────────────────────────────────────────────


def _take_down(st, deposit_id: str, change) -> dict:
    """Take a deposit's parts down so they can be saved again without one
    of them (`change` edits the parts as asked). Returns what Undo needs."""
    stored = st.parts().get(deposit_id) or []
    asked, later = dp.as_asked(stored)
    ids = {p["part_id"] for p in stored}
    every = st.split_cash()
    roots = sorted({_root(c) for c in every if c["deposit_id"] in ids})
    kinds = st.payback_kinds()
    made = [[(p.get("detail") or {}).get("charge"), (p.get("detail") or {}).get("person")]
            for p in stored if kinds.get(p["part_id"]) == sp.MADE_SPLIT]
    info = {"deposit": deposit_id, "parts": [dict(a) for a in asked], "later": later,
            "roots": roots, "part_ids": sorted(ids), "cash": [dict(c) for c in every if _root(c) in roots], "made": made}
    info["new"] = change([dict(a) for a in asked])
    dp.undo(st, deposit_id)
    return info


def put_back(st, deposit_id: str, asked: list[dict], later: bool, made: list, cash_rows: list[dict]) -> None:
    """Save a deposit's parts again. A cash part holds the records of the
    same payments that are still there (pieces cut and joined again keep
    their payment's id as `origin`)."""
    if not asked:
        return
    root_of = {int(c["id"]): _root(c) for c in cash_rows}
    live = st.split_cash()
    out = []
    for a in asked:
        if a["kind"] == "cash":
            old = [int(i) for i in a.get("cash_ids") or []]
            roots = {root_of.get(i, i) for i in old}
            free = [c for c in live if not c["deposit_id"] and c.get("kind") is None and c.get("via") != "app"]
            ids = [c["id"] for c in free if c["id"] in old]
            ids += [c["id"] for c in free if _root(c) in roots and c["id"] not in ids]
            if not ids:
                continue
            a = dict(a, cash_ids=ids)
        out.append(a)
    deposit = st.get_transaction(deposit_id)
    if deposit is None or not out:
        return
    dp.apply(st, deposit, out, later or sum(round(a["amount"], 2) for a in out) < -deposit.amount - 0.005)
    kinds_for = {(c, p) for c, p in made}
    for p in st.parts().get(deposit_id) or []:
        d = p.get("detail") or {}
        if p["kind"] == "payback" and (d.get("charge"), d.get("person")) in kinds_for:
            st.set_payback_kind(p["part_id"], sp.MADE_SPLIT)


def unlink_payback(st, charge_id: str, x: Transaction, whole: bool = False) -> dict:
    """Unlink payback `x` from one purchase (or, with `whole`, from every
    purchase it paid: the deposit's own Unlink, S-34). Returns undo marks."""
    from .marks import REIMBURSEMENT, WORK_REASON, _remember_waiting, was_waiting
    kinds, payer = st.payback_kinds(), st.payback_people()
    kind = kinds.get(x.fingerprint)
    targets = list(x.repays_all) if whole else [charge_id]
    marks: dict = {}
    if kind == sp.MADE_SPLIT:
        # THL-260: its person comes off these splits only.
        for cid in targets:
            was = sp.drop_payer(st, x, cid, checked=True)
            if was is not None:
                marks.setdefault("splits", {})[cid] = was
    who = payer.get(x.fingerprint)
    others = [(c, x.part_for(c)) for c in x.repays_all if c not in targets]
    parent_id = (x.raw or {}).get("part_of")
    stored = st.parts().get(parent_id or "") or []
    entry = next((p for p in stored if p["part_id"] == x.fingerprint), None)
    if entry is not None:
        # S-26: only this part goes; the deposit keeps the others, and what
        # it was is left to sort.
        rest = [p for p in stored if p["kind"] != "rest"]
        at = rest.index(entry)

        def without(asked):
            keep = [{"kind": "payback", "charge": c, "amount": a, **({"person": who} if who else {})}
                    for c, a in others]
            return asked[:at] + keep + asked[at + 1:]
        info = _take_down(st, parent_id, without)
        put_back(st, parent_id, info["new"], True, info["made"], info["cash"])
        info.pop("new")
        marks["reparts"] = [info]
    else:
        marks.setdefault("paybacks", {})[x.fingerprint] = {
            "charge": x.repays, "kind": kind, "person": who, "amount": x.repays_amount}
        marks.setdefault("payback_more", {})[x.fingerprint] = st.payback_more(x.fingerprint)
        st.unlink_payback(x.fingerprint)
        if others:
            # SPLIT-16: the other purchases keep their part, as parts of the
            # deposit, and this purchase's part is "$x left to sort".
            fresh = st.get_transaction(x.fingerprint) or x
            dp.apply(st, fresh, [{"kind": "payback", "charge": c, "amount": a, **({"person": who} if who else {})}
                                 for c, a in others], later=True)
            marks.setdefault("unparts", []).append(x.fingerprint)
            if kind == sp.MADE_SPLIT:
                for p in st.parts().get(x.fingerprint) or []:
                    if p["kind"] == "payback":
                        st.set_payback_kind(p["part_id"], sp.MADE_SPLIT)
    # A work expense that was waiting to be reimbursed waits again (gap 29).
    charge = st.get_transaction(charge_id)
    if (kind == REIMBURSEMENT and entry is None and charge is not None and not charge.excluded
            and not st.paybacks_for(charge_id) and was_waiting(st, charge_id)):
        st.exclude(charge_id, WORK_REASON)
        _remember_waiting(st, charge_id, False)
        marks.setdefault("exclusions", {})[charge_id] = None
        marks.setdefault("waiting", {})[charge_id] = True
    return marks


def unlink_cash(st, charge_id: str, root: int) -> tuple[dict | None, str | None]:
    """Forget this purchase's piece of a cash or app payment (S-34k). Cash a
    deposit holds comes out of the deposit, which is left with "$x left to
    sort". The whole payment goes, with its gift, only when it paid nothing
    else. Returns (undo marks, problem)."""
    from .parts_api import GIFT_SOURCE
    every = st.split_cash()
    rows = [c for c in every if _root(c) == root]
    mine = [c for c in rows if c["txn_id"] == charge_id and c.get("kind") is None]
    if not mine:
        return None, "No such cash."
    elsewhere = [c for c in rows if c["txn_id"] != charge_id and c.get("kind") is None]
    going = mine + ([c for c in rows if c.get("kind") is not None] if not elsewhere else [])
    held: dict[str, float] = {}
    for c in going:
        if c["deposit_id"]:
            held[c["deposit_id"]] = round(held.get(c["deposit_id"], 0.0) + c["amount"], 2)
    deposits: dict[str, dict[str, float]] = {}
    for part_id, amount in held.items():
        part = st.get_transaction(part_id)
        parent = (part.raw or {}).get("part_of") if part else None
        if parent:
            deposits.setdefault(parent, {})[part_id] = amount
    infos = []
    for parent, by_part in deposits.items():
        stored = st.parts().get(parent) or []
        rest = [p for p in stored if p["kind"] != "rest"]

        def smaller(asked, rest=rest, by_part=by_part):
            out = []
            for a, p in zip(asked, rest):
                take = by_part.get(p["part_id"], 0.0)
                if take and a["kind"] == "cash":
                    left = round(a["amount"] - take, 2)
                    if left < 0.005:
                        continue
                    a = dict(a, amount=left)
                out.append(a)
            return out
        infos.append(_take_down(st, parent, smaller))
    roots = sorted({root} | {r for i in infos for r in i["roots"]})
    snapshot = {int(c["id"]): dict(c) for c in every if _root(c) in roots}
    # The records go: this purchase's pieces (joined again if a deposit cut
    # them), and the gift or what was given back when nothing else is left.
    for c in st.split_cash():
        if _root(c) == root and (c["txn_id"] == charge_id and c.get("kind") is None
                                 or (not elsewhere and c.get("kind") is not None)):
            st.remove_split_cash(c["id"])
    gifts = []
    if not elsewhere:
        ids = {c["id"] for c in rows}
        for t in st.all_transactions():
            if t.source == GIFT_SOURCE and (t.raw or {}).get("split_gift") in ids:
                gifts.append((t.raw or {}).get("split_gift"))
                st.delete_transaction(t.fingerprint)
    for info in infos:
        put_back(st, info["deposit"], info.pop("new"), True, info["made"], info["cash"])
    marks: dict = {"cash_rows": {"roots": roots, "rows": list(snapshot.values()), "gifts": gifts}}
    if infos:
        marks["reparts"] = infos
    return marks, None


def undo(st, marks: dict) -> int:
    """Put back what `unlink_payback` / `unlink_cash` took apart: a
    deposit's parts as they were, and the cash records they held."""
    reparts = [i for i in marks.get("reparts") or [] if isinstance(i, dict) and i.get("deposit")]
    cash = marks.get("cash_rows") if isinstance(marks.get("cash_rows"), dict) else None
    for info in reparts:
        dp.undo(st, str(info["deposit"]))
    # The cash records as they were before; a deposit put back below holds
    # its own again, every other one keeps its deposit.
    again = {i for info in reparts for i in info.get("part_ids") or []}
    rows: dict[int, dict] = {}
    roots: set[int] = set()
    for src in [info for info in reparts] + ([cash] if cash else []):
        roots |= {int(r) for r in src.get("roots") or []}
        for r in (src.get("rows") if src is cash else src.get("cash")) or []:
            if isinstance(r, dict) and "id" in r:
                rows[int(r["id"])] = dict(r, deposit_id=None if r.get("deposit_id") in again else r.get("deposit_id"))
    if roots:
        st.restore_split_cash(sorted(roots), list(rows.values()))
    if cash:
        from .parts_api import GIFT_SOURCE, _gift_row
        have = {(t.raw or {}).get("split_gift") for t in st.all_transactions() if t.source == GIFT_SOURCE}
        for r in rows.values():
            if r.get("kind") == "gift" and r["id"] in (cash.get("gifts") or []) and r["id"] not in have:
                _gift_row(st, int(r["id"]), _root(r), r["name"], float(r["amount"]), r["day"],
                          r.get("via"), r.get("app"))
    for info in reparts:
        put_back(st, str(info["deposit"]), [dict(a) for a in info.get("parts") or []],
                 bool(info.get("later")), info.get("made") or [], list(rows.values()))
    if reparts:
        from .pipeline import classify_ledger
        classify_ledger(st)
    return len(reparts) + (1 if cash else 0)
