"""A deposit split into parts (THL-291).

Dad sends $600: $428 pays back his share of the flight, $172 is a gift.
One deposit holds several kinds of money, so each part becomes a row of its
own (`source = "part"`, `raw.part_of` the deposit) and the deposit itself
is left out (`SPLIT`), so nothing counts twice. Every part then counts the
way a whole deposit of its kind would — a payback comes off its purchase,
a gift is income of kind Gift, money from her own accounts moves — through
the same code as any other row.

Parts add up to the deposit. "Sort the rest later" keeps what's left as a
part of its own, left out (`REST`) and asked about in Needs a look as
"$172 left to sort", until she says what it is. Pearl never fills in a
leftover itself.

"They overpaid" is money she owes back: a Borrowed part with the person's
name, listed under You owe (`owed`).
"""

from __future__ import annotations

from datetime import date

from .models import Transaction

SPLIT = "Split into parts"
REST = "Left to sort"

KINDS = ("payback", "gift", "income", "moved", "savings", "cash", "refund",
         "category", "overpaid", "rest")
# The kinds income can be (finance/income.py).
INCOME_KINDS = ("salary", "bonus", "interest", "gifts", "government", "tax_refund", "other")
MAX_PARTS = 12
SEQ = 900   # parts' seq, so a part never shares a fingerprint with a bank row


class Problem(ValueError):
    pass


def _money(x: float) -> str:
    return f"${x:,.2f}"


def _cents(x) -> int:
    return int(round(float(x) * 100))


def is_part(t: Transaction) -> bool:
    return bool((t.raw or {}).get("part_of"))


def _clean(st, deposit: Transaction, parts: list, later: bool) -> list[dict]:
    """Check the parts she gave and say what's wrong, in her words."""
    from .categorize import CATEGORIES
    if not isinstance(parts, list) or not parts:
        raise Problem("Add a part.")
    if len(parts) > MAX_PARTS:
        raise Problem(f"Up to {MAX_PARTS} parts.")
    by_id = {t.fingerprint: t for t in st.all_transactions()}
    cash = {c["id"]: c for c in st.split_cash()}
    out = []
    for p in parts:
        if not isinstance(p, dict) or p.get("kind") not in KINDS or p.get("kind") == "rest":
            raise Problem("Say what each part is.")
        try:
            amount = round(float(p.get("amount")), 2)
        except (TypeError, ValueError):
            raise Problem("Give each part an amount.") from None
        if amount < 0.01:
            raise Problem("A part has to be more than nothing.")
        kind = p["kind"]
        detail: dict = {}
        if kind in ("payback", "refund"):
            charge = by_id.get(str(p.get("charge") or ""))
            if charge is None or charge.amount <= 0:
                raise Problem("Pick the purchase it pays back." if kind == "payback"
                              else "Pick the purchase it refunds.")
            detail["charge"] = charge.fingerprint
        if kind in ("payback", "overpaid"):
            person = " ".join(str(p.get("person") or "").split())[:40]
            if kind == "overpaid" and not person:
                raise Problem("Say who overpaid.")
            if person:
                detail["person"] = person
        if kind == "income":
            if p.get("income_kind") not in INCOME_KINDS:
                raise Problem("Choose what kind of income it is.")
            detail["income_kind"] = p["income_kind"]
        if kind == "category":
            if p.get("category") not in CATEGORIES:
                raise Problem("Choose a category.")
            detail["category"] = p["category"]
        if kind == "cash":
            ids = [int(i) for i in p.get("cash_ids") or [] if str(i).isdigit() and int(i) in cash]
            if not ids:
                raise Problem("Pick the cash you were paid.")
            if any(cash[i]["deposit_id"] for i in ids):
                raise Problem("That cash is already in another deposit.")
            detail["cash_ids"] = ids
        out.append({"kind": kind, "amount": amount, "detail": detail})
    whole = _cents(-deposit.amount)
    given = sum(_cents(p["amount"]) for p in out)
    if given > whole:
        raise Problem(f"The parts add up to {_money((given - whole) / 100)} more than came in.")
    if given < whole and not later:
        raise Problem(f"{_money((whole - given) / 100)} left to sort.")
    if given < whole:
        out.append({"kind": "rest", "amount": (whole - given) / 100, "detail": {}})
    return out


def _category(kind: str, detail: dict, deposit: Transaction, by_id: dict) -> str:
    if kind in ("gift", "income"):
        return "Income"
    if kind in ("moved", "cash"):
        return "Transfers"
    if kind == "savings":
        return "Saved"
    if kind == "overpaid":
        return "Borrowed"
    if kind == "refund":
        return by_id[detail["charge"]].category or "Other"
    if kind == "category":
        return detail["category"]
    if kind == "payback":
        return by_id[detail["charge"]].category or "Other"
    return deposit.category or "Other"


def apply(st, deposit: Transaction, parts: list, later: bool = False) -> dict:
    """Split `deposit` into `parts`. Returns {parts, rest, title}."""
    if deposit.amount >= 0:
        raise Problem("Only money coming in can be split into parts.")
    if deposit.excluded and deposit.excluded != REST:
        raise Problem("This deposit is left out. Put it back first.")
    if st.parts().get(deposit.fingerprint):
        raise Problem("This deposit is already in parts. Unlink them first.")
    clean = _clean(st, deposit, parts, later)
    by_id = {t.fingerprint: t for t in st.all_transactions()}
    raw = deposit.raw or {}
    rows, stored = [], []
    for pos, p in enumerate(clean):
        child = Transaction(
            date=deposit.date, post_date=deposit.post_date, description=deposit.description,
            merchant=deposit.merchant, amount=-p["amount"], currency=deposit.currency,
            account_id=deposit.account_id, account_name=deposit.account_name,
            category=_category(p["kind"], p["detail"], deposit, by_id), category_source="user",
            source="part", seq=SEQ + pos + (deposit.seq or 0) * MAX_PARTS,
            raw={"part_of": deposit.fingerprint, "part_kind": p["kind"],
                 "account_type": raw.get("account_type"), "counterparty": raw.get("counterparty"),
                 **({"part_rest": True} if p["kind"] == "rest" else {})})
        rows.append(child)
        stored.append({"part_id": child.fingerprint, "kind": p["kind"], "amount": p["amount"],
                       "detail": p["detail"]})
    # A deposit linked as a payback before its parts: the parts say it now.
    st.unlink_payback(deposit.fingerprint)
    st.link_refund(deposit.fingerprint, None)
    st.add_transactions(rows)
    for child, p in zip(rows, stored):
        cid, d = child.fingerprint, p["detail"]
        if deposit.party:
            st.set_party(cid, deposit.party)
        if p["kind"] == "payback":
            st.link_payback(d["charge"], cid, d.get("person"))
        elif p["kind"] == "refund":
            st.link_refund(cid, d["charge"])
        elif p["kind"] == "gift":
            st.set_income_type(cid, "gifts", "user")
        elif p["kind"] == "income":
            st.set_income_type(cid, d["income_kind"], "user")
        elif p["kind"] == "cash":
            st.set_cash_deposit(d["cash_ids"], cid)
        elif p["kind"] == "overpaid":
            st.set_party(cid, d["person"])
        elif p["kind"] == "rest":
            st.exclude(cid, REST)
    st.exclude(deposit.fingerprint, SPLIT)
    st.set_parts(deposit.fingerprint, stored)
    rest = next((p["amount"] for p in stored if p["kind"] == "rest"), 0.0)
    n = len(stored) - (1 if rest else 0)
    title = (f"Sorted {n} part{'' if n == 1 else 's'}. {_money(rest)} left to sort."
             if rest else f"Sorted into {n} part{'' if n == 1 else 's'}.")
    return {"parts": listed(st, deposit.fingerprint), "rest": rest, "title": title}


def undo(st, deposit_id: str) -> int:
    """Unlink every part: each part's links go with it, the cash it held is
    free again, and the deposit counts as it did. Returns how many."""
    parts = st.parts().get(deposit_id) or []
    for p in parts:
        # A part that was itself split goes back too.
        if st.parts().get(p["part_id"]):
            undo(st, p["part_id"])
        st.clear_cash_deposit(p["part_id"])
        st.link_refund(p["part_id"], None)
        st.delete_transaction(p["part_id"])
    st.clear_parts(deposit_id)
    t = st.get_transaction(deposit_id)
    if t is not None and t.excluded == SPLIT:
        st.include(deposit_id)
        if (t.raw or {}).get("part_rest"):
            st.exclude(deposit_id, REST)
    return len(parts)


def listed(st, deposit_id: str) -> list[dict]:
    """A deposit's parts as the detail shows them: kind, amount, and what it
    pays back or who it's for."""
    by_id = {t.fingerprint: t for t in st.all_transactions()}
    out = []
    for p in st.parts().get(deposit_id) or []:
        d = p["detail"]
        charge = by_id.get(d.get("charge") or "")
        row = by_id.get(p["part_id"])
        out.append({"id": p["part_id"], "kind": p["kind"], "amount": p["amount"],
                    "person": d.get("person"), "income_kind": d.get("income_kind"),
                    "category": (row.category if row else d.get("category")),
                    "charge": ({"id": charge.fingerprint, "merchant": charge.merchant,
                                "date": charge.date[:10], "amount": charge.amount,
                                "category": charge.category} if charge else None),
                    "sorted": not (row is not None and row.excluded == REST)})
    return out


def rest_questions(st, transactions: list[Transaction]) -> list[dict]:
    """Every "$x left to sort", for Needs a look."""
    by_id = {t.fingerprint: t for t in transactions}
    out = []
    for t in transactions:
        if not (t.raw or {}).get("part_rest") or t.excluded != REST:
            continue
        parent = by_id.get((t.raw or {}).get("part_of") or "")
        whole = -parent.amount if parent else -t.amount
        out.append({"t": t, "whole": round(whole, 2),
                    "sorted": round(whole - (-t.amount), 2)})
    return out


def owed(st, transactions: list[Transaction], today: date) -> dict:
    """Owed to you (S-14): per person, what they still owe on your splits,
    what you owe them (they overpaid), and what they paid back this month."""
    from .splits import people_status, same_person
    splits, payer = st.splits(), st.payback_people()
    by_id = {t.fingerprint: t for t in transactions}

    def person_key(name: str, names: list[str]) -> str:
        return next((n for n in names if same_person(n, name)), name)

    owes: dict[str, dict] = {}
    for cid, split in splits.items():
        charge = by_id.get(cid)
        if charge is None or charge.excluded:
            continue
        for p in people_status(charge, split, transactions, payer):
            if p["owes"] < 0.005:
                continue
            key = person_key(p["name"], list(owes))
            row = owes.setdefault(key, {"name": key, "total": 0.0, "items": []})
            row["total"] = round(row["total"] + p["owes"], 2)
            row["items"].append({"charge_id": cid, "merchant": charge.merchant,
                                 "date": charge.date[:10], "owes": p["owes"],
                                 "amount": p["amount"], "paid": p["paid"]})
    you_owe: dict[str, dict] = {}
    for t in transactions:
        if (t.raw or {}).get("part_kind") != "overpaid" or t.excluded:
            continue
        name = t.party or "Someone"
        key = person_key(name, list(you_owe))
        row = you_owe.setdefault(key, {"name": key, "total": 0.0, "items": []})
        row["total"] = round(row["total"] + -t.amount, 2)
        row["items"].append({"id": t.fingerprint, "date": t.date[:10], "amount": round(-t.amount, 2),
                             "merchant": t.merchant})
    month = today.strftime("%Y-%m")
    back = []
    for t in transactions:
        if not t.repays or t.amount >= 0 or not t.date.startswith(month):
            continue
        charge = by_id.get(t.repays)
        back.append({"name": payer.get(t.fingerprint) or t.party or t.merchant,
                     "merchant": charge.merchant if charge else "",
                     "date": t.date[:10], "amount": round(t.paid_part, 2)})
    for cid, split in splits.items():
        charge = by_id.get(cid)
        for p in split["people"]:
            for c in p.get("cash") or []:
                if c["day"].startswith(month):
                    back.append({"name": p["name"], "merchant": charge.merchant if charge else "",
                                 "date": c["day"], "amount": c["amount"], "cash": True})
    back.sort(key=lambda r: r["date"], reverse=True)
    people = sorted(owes.values(), key=lambda r: -r["total"])
    return {"total": round(sum(r["total"] for r in people), 2), "people": len(people),
            "owes_you": people, "you_owe": sorted(you_owe.values(), key=lambda r: -r["total"]),
            "paid_back": back}
