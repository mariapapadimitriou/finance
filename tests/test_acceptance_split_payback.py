"""The product owner's acceptance bar (2026-11-17): "For every transaction,
I can split multiple ways. For every payback, I can also assign the payback
to multiple items. As long as this functionality works, I will be happy."

Demo data only, through the endpoints the iPhone app calls.

1. Split N ways. Every kind of money out, split 2, 3 and 5 ways, evenly,
   by amount and by shares (PUT …/split, as SplitSheet sends it): it saves,
   her share and what it costs her are right, and Undo puts it back exactly.

2. Payback to many items. Every kind of money in, by every path the app
   has that makes sense for it, linked to 2 and to 3 purchases with the
   last one part-paid, in the one save the app makes (POST …/parts): each
   person's share is credited, nobody is added to a split, Spent and the
   Allowance move by exactly the deposit, and one Undo puts it all back.

Kind × path combinations that don't make sense are left out, each with why
(`NOT_A_PATH`). PQ-03's single tap links one purchase by design; several
go through PB-30, which the tile opens when the money is more than its share.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import spend_amount
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.strftime("%Y-%m")


def day(n: int) -> str:
    """n days ago, kept in this month so Spent and the Allowance see it."""
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(desc, amount, account="chq", when=None, merchant=None, category="", raw=None, kind="depository"):
    names = {"chq": "Chequing ••4417", "amex": "Amex Cobalt ••1001", "fam": "Joint ••1123",
             "jnt": "Joint ••1123"}
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name=names.get(account, account),
                       raw={"account_type": kind, **(raw or {})})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "acceptance.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.st.set_setting("home_income", "4300")
        yield c


def add(c, account, *rows):
    ingest(c.st, IngestResult(list(rows), account))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def detail(c, tid):
    return ok(c.get(f"/api/transactions/{tid}"))


def numbers(c):
    """The month's Spent (the list's totals) and the Allowance on Home."""
    lst = ok(c.get("/api/transactions/list", query_string={"month": MONTH, "limit": 500}))
    return {"spent": lst["month_totals"]["spent"], "allowance": ok(c.get("/api/home"))["safe_to_spend"]["amount"]}


def world(c):
    """Everything Undo must put back exactly."""
    rows = {t.fingerprint: (t.category, t.category_source, t.my_share, t.share_set, t.excluded, t.repays,
                            tuple(t.repays_all or ()))
            for t in c.st.all_transactions()}
    return {"rows": rows, "splits": c.st.splits(), "joint_parts": c.st.joint_parts(),
            "parts": c.st.parts(), "payer": c.st.payback_people(), "joint_paybacks": c.st.joint_paybacks(),
            "numbers": numbers(c)}


def undo(c, reply):
    ok(c.post("/api/transactions/undo", json=reply["undo"]))


def cents(x) -> int:
    return int(round(float(x) * 100))


# ── 1. Split N ways ─────────────────────────────────────────────────────

NAMES = ["Priya", "Jo", "Dana", "Kai"]
PRICE = 90.0


def _card(c):
    return add(c, "amex", row("LOBLAWS", PRICE, "amex", category="Groceries", kind="credit"))["LOBLAWS"]


def _bill(c):
    # #355: a bill paid from chequing sorts as spending by its payee.
    return add(c, "chq", row("BILL PAYMENT ROGERS", PRICE, raw={"issuer_category": "TRANSFER_OUT_ACCOUNT_TRANSFER"}))[
        "BILL PAYMENT ROGERS"]


def _joint(c, share):
    i = add(c, "fam", row("PIZZA NOVA", PRICE, "fam", category="Dining"))
    ok(c.put("/api/accounts/fam/joint", json={"label": "Joint"}))
    ok(c.put("/api/accounts/fam/settings", json={"joint_people": ["Sam Lee"]}))
    ok(c.put("/api/accounts/fam/settings", json={"joint_share": share}))
    return i["PIZZA NOVA"]


def _etransfer_out(c):
    return add(c, "chq", row("INTERAC E-TRANSFER TO PRIYA SHAH", PRICE, merchant="Priya Shah",
                             category="Dining"))["INTERAC E-TRANSFER TO PRIYA SHAH"]


def _pending(c):
    return add(c, "amex", row("BAR RAVAL", PRICE, "amex", category="Dining", kind="credit",
                              raw={"pending": True}))["BAR RAVAL"]


def _trip(c):
    i = add(c, "amex", row("HOTEL LE GERMAIN", PRICE, "amex", category="Travel", kind="credit"))
    ok(c.post("/api/trips", json={"ids": [i["HOTEL LE GERMAIN"]], "name": "Trip to Montréal"}))
    return i["HOTEL LE GERMAIN"]


def _refunded(c):
    i = add(c, "amex", row("WINNERS", PRICE + 30.0, "amex", when=day(5), category="Shopping", kind="credit"))
    i = add(c, "chq", row("WINNERS REFUND", -30.0, when=day(2), merchant="Winners"))
    ok(c.post(f"/api/transactions/{i['WINNERS REFUND']}/mark", json={"case": "refund", "charge": i["WINNERS"]}))
    return i["WINNERS"]


KINDS = {
    "card purchase": _card,
    "bill payment": _bill,
    "joint 50/50": lambda c: _joint(c, 50),
    "joint mine unless I say": lambda c: _joint(c, "auto"),
    "e-Transfer out": _etransfer_out,
    "pending purchase": _pending,
    "trip transaction": _trip,
    "purchase with a refund": _refunded,
}


def split_body(mode: str, n: int, base: float) -> tuple[dict, list[float]]:
    """What SplitSheet sends for N ways (her and N-1 people), and what each
    of them should owe."""
    people = NAMES[:n - 1]
    if mode == "even":
        each = cents(base) // n
        return {"mode": "even", "people": [{"name": p} for p in people]}, [each / 100] * len(people)
    if mode == "amount":
        amounts = [5.0 + i for i in range(len(people))]
        return {"mode": "amount", "people": [{"name": p, "amount": a} for p, a in zip(people, amounts)]}, amounts
    # Shares: one each for them, two for her.
    total = len(people) + 2
    each = cents(base) // total
    return ({"mode": "shares", "you": 2, "people": [{"name": p, "shares": 1} for p in people]},
            [each / 100] * len(people))


@pytest.mark.parametrize("mode", ["even", "amount", "shares"])
@pytest.mark.parametrize("n", [2, 3, 5])
@pytest.mark.parametrize("kind", list(KINDS))
def test_split_n_ways(client, kind, n, mode):
    tid = KINDS[kind](client)
    before = world(client)
    t = client.st.get_transaction(tid)
    cost = round(spend_amount(t), 2)
    base = detail(client, tid).get("splitting", {}).get("base") or (t.amount if not t.joint else None)
    if base is None:
        from finance.splits import split_base
        base = split_base(t)
    body, theirs = split_body(mode, n, base)
    reply = ok(client.put(f"/api/transactions/{tid}/split", json=body))
    s = reply["splitting"]
    # What's saved is what she typed, of the whole.
    stored = {p["name"]: p["amount"] for p in client.st.splits()[tid]["people"]}
    assert stored == dict(zip(NAMES[:n - 1], theirs))
    her = round(base - sum(theirs), 2)
    t = client.st.get_transaction(tid)
    assert round(t.my_share, 2) == her and s["base"] == base
    # Decision 6: a refund on it is shared the way the purchase is, so each
    # row, hers too, shows its part of what the purchase cost after it.
    factor = 1 - (t.refunded or 0.0) / t.amount
    shown = {p["name"]: p["amount"] for p in s["people"]}
    assert shown == {nm: round(a * factor, 2) for nm, a in zip(NAMES[:n - 1], theirs)}
    assert s["you"] == round(her * factor, 2)
    # Rule A: what they owe stays hers until it's paid, so the cost holds.
    assert round(spend_amount(t), 2) == cost
    assert numbers(client) == before["numbers"]
    undo(client, reply)
    assert world(client) == before


# ── 2. Payback to many items ────────────────────────────────────────────

# Anastasia owes on three purchases she split with her and Jo, oldest first.
SHARES = (("COSTCO", 90.0, 30.0, 12), ("PIZZA NOVA", 60.0, 20.0, 9), ("PAI", 75.0, 25.0, 6))
# Two purchases: Costco in full, Pizza Nova $10.00 of $20.00. Three: Costco
# and Pizza Nova in full, Pai $15.00 of $25.00 (PB-30o, the newest part-paid).
LINKS = {2: (40.0, [30.0, 10.0]), 3: (65.0, [30.0, 20.0, 15.0])}

SENDERS = {
    "e-Transfer from a person on the splits": ("INTERAC E-TRANSFER FROM ANASTASIA PAPAS", "Anastasia Papas"),
    "e-Transfer from a sender who doesn't match": ("INTERAC E-TRANSFER FROM A PAPAS", "A Papas"),
    "a deposit": ("MOBILE CHEQUE DEPOSIT", "Mobile Cheque Deposit"),
}


def friends(c, sender: str, amount: float):
    """Her three splits with Anastasia and Jo, and the money in."""
    i = add(c, "amex", *(row(m, a, "amex", when=day(n), category="Dining", kind="credit") for m, a, _, n in SHARES))
    for m, _, share, _ in SHARES:
        ok(c.put(f"/api/transactions/{i[m]}/split", json={
            "mode": "amount", "people": [{"name": "Anastasia", "amount": share}, {"name": "Jo", "amount": share}]}))
    desc, merchant = SENDERS[sender]
    i = add(c, "chq", row(desc, -amount, when=day(1), merchant=merchant))
    return {m: i[m] for m, *_ in SHARES}, i[desc]


def owes(c, charge):
    return {p["name"]: p["owes"] for p in detail(c, charge)["splitting"]["people"]}


def split_names(c):
    return {cid: sorted(p["name"] for p in s["people"]) for cid, s in c.st.splits().items()}


def owing(c, dep, person=None):
    return ok(c.get(f"/api/transactions/{dep}/owing", query_string={"person": person} if person else {}))


def theirs(reply):
    """PB-30's rows (`theirShares`), oldest first: the order the money pays."""
    rows = [o for o in reply["items"] if o.get("theirs") and not o.get("unknown") and o["owes"] >= 0.005]
    return sorted(rows, key=lambda o: o["date"])


def pb30(c, dep, rows, amount):
    """PB-30's one tap (`takeTicked`): oldest in full, the newest part-paid."""
    room, parts = cents(amount), []
    for o in rows:
        take = min(cents(o["owes"]), room)
        room -= take
        parts.append({"kind": "payback", "amount": take / 100, "charge": o["id"], "person": o["person"]})
    return c.post(f"/api/transactions/{dep}/parts", json={"parts": parts, "later": False})


# How each path finds the person, as the app does it, before PB-30.

def via_pq03(c, dep, n):
    """PQ-03: Something else (or a tile with more money than its share)
    opens PB-30 for the person the split tiles name."""
    item = next(i for i in ok(c.get("/api/review"))["money_in"] if i["txn"]["id"] == dep)
    q = item.get("payback")
    assert q, "PQ-03 should ask"
    named = {t["person"] for t in q["tiles"] if t.get("person")}
    person = named.pop() if len(named) == 1 else owing(c, dep)["from"]
    assert person == "Anastasia"
    return owing(c, dep, person)


def via_a_person(c, dep, n):
    """Paid back › A person: PB-30 for the sender; when Pearl can't match
    them, PP-01 lists only who owes her, and her pick reloads their shares."""
    r = owing(c, dep)
    if r["from"] is None:
        asked = {o["person"] for o in r["items"] if o.get("person") and o["owes"] >= 0.005}
        assert asked == {"Anastasia", "Jo"}     # PP-01: no Someone new
        r = owing(c, dep, "Anastasia")
    assert r["from"] == "Anastasia"
    return r


def via_who_paid(c, dep, n, charges):
    """PQ-03's tile 409s `who_paid`; her pick opens PB-30 for that person."""
    r = c.post(f"/api/transactions/{dep}/mark", json={"case": "payback", "charge": charges["COSTCO"]})
    assert r.status_code == 409, r.get_json()
    ask = r.get_json()["who_paid"]
    assert ask["deposit"] == dep and ask["date"] == day(1)
    assert "Anastasia" in [p["name"] for p in ask["people"]]
    return owing(c, ask["deposit"], "Anastasia")


def via_purchase(c, dep, n, charges):
    """PB-20 › PB-22 from Costco: the money picked, A person (the candidate's
    person, or PP-01's pick), then PB-30 with Costco ticked."""
    find = ok(c.get(f"/api/transactions/{charges['COSTCO']}/paid-back-find"))
    cand = next((x for x in find["candidates"] if x["id"] == dep), None)
    if cand is None:
        # Not LIKELY (no one on the split by that name): PB-22's search, by amount.
        amount = -c.st.get_transaction(dep).amount
        find = ok(c.get(f"/api/transactions/{charges['COSTCO']}/paid-back-find", query_string={"q": f"{amount:.2f}"}))
        cand = next((x for x in find["candidates"] if x["id"] == dep), None)
    assert cand, "the money should be offered"
    person = cand.get("person") if cand.get("kind") == "person" else None
    r = owing(c, dep, person)
    if r["from"] is None:
        r = owing(c, dep, "Anastasia")
    assert r["from"] == "Anastasia"
    assert charges["COSTCO"] in [o["id"] for o in theirs(r)]
    return r


PATHS = {
    "PQ-03": lambda c, dep, n, ch: via_pq03(c, dep, n),
    "Paid back › A person / PB-30": lambda c, dep, n, ch: via_a_person(c, dep, n),
    "who_paid, then PB-30": via_who_paid,
    "PB-20 › PB-22 from the purchase": via_purchase,
}

# Kind × path left out, and why.
NOT_A_PATH = {
    ("e-Transfer from a person on the splits", "who_paid, then PB-30"):
        "Pearl matches the sender to Anastasia, so it never asks who paid.",
    ("e-Transfer from a sender who doesn't match", "PQ-03"):
        "No split tile names a person for an unmatched sender; its tile asks who_paid (that row).",
    ("a deposit", "PQ-03"):
        "A deposit with no sender's name gets no payback question (payback_question.build).",
    ("a deposit", "who_paid, then PB-30"):
        "No sender's name, so the server links without asking; the deposit goes A person › PP-01.",
    ("e-Transfer from a person on the splits", "PQ-03", 3):
        "PQ-03 asks only when a share or an even part of a purchase fits the money; $65.00 fits "
        "none, so What was this? › Paid back opens PB-30 straight away (the A person row).",
}


@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("path", list(PATHS))
@pytest.mark.parametrize("kind", list(SENDERS))
def test_payback_to_many(client, kind, path, n):
    if (kind, path) in NOT_A_PATH:
        pytest.skip(NOT_A_PATH[(kind, path)])
    if (kind, path, n) in NOT_A_PATH:
        pytest.skip(NOT_A_PATH[(kind, path, n)])
    amount, paid = LINKS[n]
    charges, dep = friends(client, kind, amount)
    before = world(client)
    names = split_names(client)
    jo = {m: owes(client, cid)["Jo"] for m, cid in charges.items()}
    r = PATHS[path](client, dep, n, charges)
    rows = theirs(r)[:n]
    assert [o["person"] for o in rows] == ["Anastasia"] * n
    reply = ok(pb30(client, dep, rows, amount))
    assert reply["title"] == f"Anastasia paid back {n} purchases · ${amount:,.2f}"
    for (m, _, share, _), got in zip(SHARES, paid):
        assert owes(client, charges[m])["Anastasia"] == round(share - got, 2)
    assert {m: owes(client, cid)["Jo"] for m, cid in charges.items()} == jo
    assert split_names(client) == names
    after = numbers(client)
    assert round(before["numbers"]["spent"] - after["spent"], 2) == amount
    assert round(after["allowance"] - before["numbers"]["allowance"], 2) == amount
    undo(client, reply)
    assert world(client) == before


# TP-03: a joint transfer from the account's other owner.

JSHARES = (("COSTCO", 240.0, 60.0, 8), ("SHOPPERS", 129.0, 40.0, 7), ("AIR CANADA", 111.0, 50.0, 6))
JLINKS = {2: (80.0, [60.0, 20.0]), 3: (135.0, [60.0, 40.0, 35.0])}


@pytest.mark.parametrize("n", [2, 3])
def test_joint_transfer_tp03(client, n):
    amount, paid = JLINKS[n]
    add(client, "chq", *(row(m, a, when=day(d), category="Shopping") for m, a, _, d in JSHARES),
        row("TFR-FR 1123", -amount, when=day(1)))
    i = add(client, "jnt", row("TFR-TO 4417", amount, "jnt", when=day(1)))
    ok(client.put("/api/accounts/jnt/joint", json={"label": "Joint"}))
    ok(client.put("/api/accounts/jnt/settings", json={"joint_people": ["Mom"]}))
    for m, _, share, _ in JSHARES:
        ok(client.put(f"/api/transactions/{i[m]}/split", json={
            "mode": "amount", "people": [{"name": "Mom", "amount": share}, {"name": "Jo", "amount": share}]}))
    dep = i["TFR-FR 1123"]
    before = world(client)
    names = split_names(client)
    # TP-03: PB-30 with Mom picked (…/owing?person=Mom), one save with the joint side.
    rows = theirs(owing(client, dep, "Mom"))[:n]
    assert [o["person"] for o in rows] == ["Mom"] * n
    room, parts = cents(amount), []
    for o in rows:
        take = min(cents(o["owes"]), room)
        room -= take
        parts.append({"kind": "payback", "amount": take / 100, "charge": o["id"], "person": "Mom"})
    reply = ok(client.post(f"/api/transactions/{dep}/parts", json={
        "parts": parts, "later": False, "joint_payback": {"out": i["TFR-TO 4417"], "person": "Mom"}}))
    assert reply["title"] == f"Mom paid back {n} purchases · ${amount:,.2f}"
    for (m, _, share, _), got in zip(JSHARES, paid):
        assert owes(client, i[m])["Mom"] == round(share - got, 2)
        assert owes(client, i[m])["Jo"] == share
    assert split_names(client) == names
    after = numbers(client)
    assert round(before["numbers"]["spent"] - after["spent"], 2) == amount
    assert round(after["allowance"] - before["numbers"]["allowance"], 2) == amount
    undo(client, reply)
    assert world(client) == before


# The shop and Work: no person, her own purchases (T-09rs, T-09w).

OWN = (("AMAZON", 40.0, 10), ("AMAZON MKTPL", 30.0, 8), ("AMAZON.CA", 25.0, 6))
OWN_LINKS = {2: (55.0, [40.0, 15.0]), 3: (80.0, [40.0, 30.0, 10.0])}


NO_UI = ("no UI: Paid back › The shop / Work (T-09rs, T-09w) picks one purchase and saves it; "
         "what's left is S-11m / S-11w's question, a second save with its own Undo. The server takes "
         "several in one save (test_refund_or_work_to_many_server); the app has no screen that sends it.")


@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("kind", ["a refund", "a work reimbursement"])
def test_refund_or_work_to_many_in_the_app(n, kind):
    pytest.skip(NO_UI)


@pytest.mark.parametrize("n", [2, 3])
@pytest.mark.parametrize("kind", ["a refund", "a work reimbursement"])
def test_refund_or_work_to_many_server(client, kind, n):
    """The shop or Work paying back several of her own purchases, in the one
    request PartsSheet would send (POST …/parts)."""
    amount, paid = OWN_LINKS[n]
    i = add(client, "amex", *(row(m, a, "amex", when=day(d), category="Shopping", kind="credit") for m, a, d in OWN))
    # Before the money comes in: a refund from the shop already counts as one
    # when it lands (Pearl's guess), so the move is measured from here.
    was = numbers(client)
    desc = "AMAZON REFUND" if kind == "a refund" else "NORTHWIND LTD EXPENSE REIMB"
    i = add(client, "chq", row(desc, -amount, when=day(1), merchant="Amazon" if kind == "a refund" else "Northwind Ltd"))
    dep = i[desc]
    before = world(client)
    part = "refund" if kind == "a refund" else "reimbursement"
    parts = [{"kind": part, "amount": got, "charge": i[m]} for (m, _, _), got in zip(OWN, paid)]
    reply = ok(client.post(f"/api/transactions/{dep}/parts", json={"parts": parts, "later": False}))
    assert client.st.splits() == {}
    linked = {p["charge"]["id"]: p["amount"] for p in detail(client, dep).get("parts") or [] if p.get("charge")}
    assert linked == {i[m]: got for (m, _, _), got in zip(OWN, paid)}
    after = numbers(client)
    assert round(was["spent"] - after["spent"], 2) == amount
    assert round(after["allowance"] - was["allowance"], 2) == amount
    undo(client, reply)
    assert world(client) == before
