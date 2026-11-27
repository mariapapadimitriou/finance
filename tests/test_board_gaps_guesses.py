"""Board gaps (Pearl redesign canvas v102), the server half.

P3 / P4: the four tiles on What was this? are the likeliest for this
purchase, from her own ledger: the same merchant, then names that share a
distinctive word, then the bank's own category, then her most used. Never a
fixed list of shops, never an auto-sort, no AI.

P5h: money with no clear name ("Interac e-Transfer") still gets Pearl's
guess at the purchase ("A third of Pai Northern Thai?"), with everyone on
the split who owes, and nobody credited until she says who."""

from __future__ import annotations

import inspect
import re
from datetime import date, timedelta

import pytest

from finance import likely
from finance.models import Transaction
from finance.payback_question import build

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def buy(merchant, amount, n, category="Other", source="issuer", code=""):
    return Transaction(date=ago(n), description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, category_source=source, account_id="amex",
                       account_name="Amex", raw={"issuer_category": code} if code else {})


def hers(merchant, category, n, amount=20.0):
    return buy(merchant, amount, n, category=category, source="user")


# ── P3 / P4: the likeliest four ──────────────────────────────────────────

def _base():
    # Her most used overall: Groceries, then Dining, then Shopping.
    rows = [hers(f"Grocer {i}", "Groceries", 30 + i) for i in range(6)]
    rows += [hers(f"Diner {i}", "Dining", 40 + i) for i in range(4)]
    rows += [hers(f"Shop {i}", "Shopping", 50 + i) for i in range(2)]
    return rows


def test_her_pick_for_the_same_merchant_leads():
    rows = _base() + [hers("Corner Store", "Coffee", 9), hers("Corner Store", "Coffee", 20)]
    t = buy("Corner Store", 18.40, 1)
    assert likely.likeliest(t, rows + [t])[0] == "Coffee"


def test_then_names_sharing_a_distinctive_word():
    rows = _base() + [hers("Lucky Noodle Bar", "Food Delivery", 12)]
    t = buy("TST* Lucky Noodle", 33.75, 1)
    four = likely.likeliest(t, rows + [t])
    assert four[0] == "Food Delivery"
    assert len(four) == 4


def test_a_word_many_of_her_merchants_share_is_not_a_hint():
    # "Market" is in many of her shops' names: it says nothing.
    rows = _base() + [hers(f"{n} Market", "Pets", 12 + i) for i, n in enumerate(
        ["Alpha", "Beta", "Gamma", "Delta", "Epsilon"])]
    t = buy("Zeta Market", 10.0, 1)
    assert likely.likeliest(t, rows + [t])[0] != "Pets"


def test_then_the_banks_category_and_its_group():
    t = buy("Some Cafe", 6.0, 1, code="FOOD_AND_DRINK_COFFEE")
    four = likely.likeliest(t, _base() + [t])
    assert four[0] == "Coffee"
    # Then the rest of Plaid's food group before her overall favourites.
    assert set(four[1:]) <= {"Dining", "Groceries", "Alcohol & Bars"}


def test_her_most_used_fill_up_to_four():
    t = buy("Brand New Place", 10.0, 1)
    assert likely.likeliest(t, _base() + [t]) == ["Groceries", "Dining", "Shopping", "Food Delivery"]


def test_only_categories_she_can_pick():
    rows = _base() + [hers("Odd Shop", "Groceries", 3)]
    t = buy("Odd Shop", 10.0, 1)
    four = likely.likeliest(t, rows + [t], hidden={"Groceries"})
    assert "Groceries" not in four
    assert not {"Other", "Unsorted transfers", "Income", "Transfers"} & set(four)


def test_pearls_own_guesses_are_not_her_picks():
    # Rows Pearl or the bank sorted don't count as what she picked.
    rows = _base() + [buy("Corner Store", 5.0, 9, category="Travel", source="issuer")]
    t = buy("Corner Store", 18.40, 1)
    assert likely.likeliest(t, rows + [t])[0] != "Travel"


def test_no_merchant_names_or_store_lists_in_the_code():
    src = inspect.getsource(likely)
    assert not re.search(r"\b(loblaws|starbucks|uber|amazon|costco|petsmart|walmart)\b", src, re.I)
    assert "anthropic" not in src.lower() and "openai" not in src.lower()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "g.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def test_review_and_the_page_carry_the_four_and_sort_nothing(client):
    from finance.ingest.base import IngestResult
    from finance.pipeline import ingest
    rows = [Transaction(date=ago(20 + i), description="QUIMBY HALL", amount=25.0 + i,
                        account_id="amex", account_name="Amex", raw={"account_type": "credit"})
            for i in range(2)]
    rows.append(Transaction(date=ago(1), description="SQ *QUIMBY 22", amount=33.75, account_id="amex",
                            account_name="Amex", raw={"account_type": "credit", "category_confidence": "LOW"}))
    ingest(client.st, IngestResult(transactions=rows, account_id="amex"))
    for t in client.st.all_transactions():
        if t.description == "QUIMBY HALL":
            client.st.set_transaction_category(t.fingerprint, "Food Delivery")
    new = next(t for t in client.st.all_transactions() if t.description == "SQ *QUIMBY 22")
    before = new.category
    review = client.get("/api/review").get_json()
    item = next(i for i in review["unsure_category"] if i["txn"]["id"] == new.fingerprint)
    assert item["likely"][0] == "Food Delivery"
    assert len(item["likely"]) == 4
    page = client.get(f"/api/transactions/{new.fingerprint}").get_json()
    assert page["likely"][0] == "Food Delivery"
    # A suggestion, never an answer.
    assert client.st.get_transaction(new.fingerprint).category == before


# ── P5h: no clear name ───────────────────────────────────────────────────

def nameless(amount, n):
    return Transaction(date=ago(n), description="Interac e-Transfer", merchant="Interac e-Transfer",
                       amount=-amount, category="Transfers", category_source="issuer",
                       account_id="chq", account_name="TD Chequing", raw={"account_type": "depository"})


def test_nameless_money_onto_a_split_lists_everyone_who_owes(client):
    pai = buy("Pai Northern Thai", 120.0, 3, category="Dining")
    money = nameless(40.0, 1)
    client.st.add_transactions([pai, money])
    pid = next(t.fingerprint for t in client.st.all_transactions() if t.amount > 0)
    client.st.set_split(pid, "even", [{"name": "Priya", "amount": 40.0}, {"name": "Sam", "amount": 40.0}], True)
    client.st.set_share(pid, 40.0)
    items = client.get("/api/review").get_json()["money_in"]
    q = next(i for i in items if i["txn"]["amount"] < 0)["payback"]
    assert q["unknown"] is True and q["named"] is False
    assert q["card"]["title"] == "A third of Pai Northern Thai?"
    tile = q["tiles"][0]
    assert tile["after"] == "Exactly a third of $120.00"
    assert sorted(p["name"] for p in tile["people"]) == ["Priya", "Sam"]
    # Nobody is guessed: no tile carries a person.
    assert all(not x.get("person") for x in q["tiles"])


def test_nameless_answer_credits_who_she_picked_and_is_not_remembered(client):
    pai = buy("Pai Northern Thai", 120.0, 5, category="Dining")
    first, second = nameless(40.0, 2), nameless(40.0, 1)
    client.st.add_transactions([pai, first, second])
    txns = client.st.all_transactions()
    pid = next(t.fingerprint for t in txns if t.amount > 0)
    a, b = sorted((t for t in txns if t.amount < 0), key=lambda t: t.date)
    client.st.set_split(pid, "even", [{"name": "Priya", "amount": 40.0}, {"name": "Sam", "amount": 40.0}], True)
    client.st.set_share(pid, 40.0)
    r = client.post(f"/api/transactions/{a.fingerprint}/mark",
                    json={"case": "payback", "charge": pid, "person": "Priya"})
    assert r.status_code == 200, r.get_json()
    people = client.get(f"/api/transactions/{pid}").get_json()["splitting"]["people"]
    assert [p["name"] for p in people] == ["Priya", "Sam"] or sorted(p["name"] for p in people) == ["Priya", "Sam"]
    priya = next(p for p in people if p["name"] == "Priya")
    assert priya["owes"] < 0.005
    # The next nameless one is asked again: nothing remembered her pick.
    items = client.get("/api/review").get_json()["money_in"]
    nxt = next(i for i in items if i["txn"]["id"] == b.fingerprint)
    q = nxt.get("payback")
    assert q is None or (q["unknown"] is True and all(not x.get("person") for x in q["tiles"]))
    assert nxt.get("from") in (None, "")


def test_someone_not_on_the_split_is_never_added_to_it(client):
    pai = buy("Pai Northern Thai", 120.0, 3, category="Dining")
    money = nameless(40.0, 1)
    client.st.add_transactions([pai, money])
    txns = client.st.all_transactions()
    pid = next(t.fingerprint for t in txns if t.amount > 0)
    mid = next(t.fingerprint for t in txns if t.amount < 0)
    client.st.set_split(pid, "even", [{"name": "Priya", "amount": 40.0}, {"name": "Sam", "amount": 40.0}], True)
    client.st.set_share(pid, 40.0)
    r = client.post(f"/api/transactions/{mid}/mark", json={"case": "payback", "charge": pid, "person": "Jo"})
    assert r.status_code == 409 and r.get_json().get("who_paid")
    people = client.get(f"/api/transactions/{pid}").get_json()["splitting"]["people"]
    assert sorted(p["name"] for p in people) == ["Priya", "Sam"]


def test_a_named_sender_is_unchanged():
    t = Transaction(date=ago(1), description="e-Transfer from Sam", merchant="e-Transfer from Sam",
                    amount=-30.0, category="Transfers", category_source="issuer", account_id="chq",
                    account_name="TD", raw={"account_type": "depository"})
    q = build(t, [t, buy("Pizza Nova", 60.0, 3, category="Dining")])
    assert not q.get("unknown")
    assert q["card"]["title"] == "Paying you back for Pizza Nova?"


# ── The app's half ───────────────────────────────────────────────────────

from pathlib import Path  # noqa: E402

IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def swift(rel: str) -> str:
    return (IOS / rel).read_text()


def test_every_tile_place_uses_the_servers_four():
    cat = swift("Views/Transactions/CategorySheet.swift")
    assert "prefer: likelyFirst" in cat
    assert "likelyFirst: ask.item.likely" in swift("Views/Review/AnswerSheet.swift")
    assert "prefer: ask.item.likely" in swift("Views/Review/QuickSortView.swift")
    assert "prefer: t.likely ?? guessing?.ask.item.likely" in swift("Views/Transactions/TransactionDetailView.swift")
    models = swift("API/Models.swift")
    assert "@Boxed var likely: [String]?" in models


def test_yes_on_a_nameless_guess_asks_who_first():
    qs = swift("Views/Review/QuickSortView.swift")
    yes = qs[qs.index("private func paybackYes"):]
    yes = yes[:yes.index("\n    }\n")]
    assert "q.unknown == true, tile.person == nil" in yes
    assert "notThis = .who(QuickWhoSent(" in yes
    sheet = qs[qs.index("private func whoSentSheet"):]
    sheet = sheet[:sheet.index("\n    }\n")]
    # Someone on the split: their payback. Anyone else: What did … pay back?, never added.
    assert "samePerson($0.name, name)" in sheet
    assert "notThis = .not(QuickNotThis(ask: w.ask, person: name))" in sheet
    answer = swift("Views/Review/AnswerSheet.swift")
    assert "ask.item.payback?.unknown == true, tile.person == nil" in answer
    assert "whoSentTile = tile" in answer


def test_who_sent_this_offers_contacts_and_a_typed_name():
    s = swift("Views/Transactions/PaidBackFindViews.swift")
    sheet = s[s.index("struct PaybackSenderSheet"):]
    sheet = sheet[:sheet.index("\n}\n")]
    assert "@StateObject private var contacts = ContactNames()" in sheet
    assert 'APSheetLabel(text: "From your contacts")' in sheet
    assert 'prompt: Text("Type a name")' in sheet
    assert "ContactsOffLine()" in sheet
