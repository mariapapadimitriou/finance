"""Regular pay, remembered (2026-10-28): "This is my regular pay" with
Remember sorts every deposit from the same payer as income, of the salary
kind — the ones here and the ones still to come."""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, "tests")
from test_what_was_this import client, load, mark, row, undo  # noqa: E402,F401

from finance.ingest.base import IngestResult  # noqa: E402
from finance.pipeline import ingest  # noqa: E402

TODAY = date.today()


def ago(n):
    return (TODAY - timedelta(days=n)).isoformat()


def deposit(when, amount=-2150.0, desc="ACME CORP PAY", merchant="Acme Corp"):
    t = row(amount, desc, when=when, merchant=merchant)
    t.raw["issuer_category"] = "TRANSFER_IN_DEPOSIT"
    return t


def pay(c, n=3):
    rows = load(c.st, *[deposit(ago(14 * i + 1), desc=f"ACME CORP PAY {i}") for i in range(n)])
    return [rows[f"ACME CORP PAY {i}"] for i in range(n)]


def by_id(c):
    return {t.fingerprint: t for t in c.st.all_transactions()}


def cases(c, tid):
    return {x["key"]: x for x in c.get(f"/api/transactions/{tid}/cases").get_json()["cases"]}


def test_regular_pay_offers_a_rule_for_the_payer(client):
    first, *_ = pay(client)
    item = cases(client, first)["regular_pay"]
    assert item["remember"] == "payer"
    assert item["remember_label"] == "Always count deposits from Acme Corp as my regular pay"


def test_without_remember_only_this_one_is_pay(client):
    first, second, third = pay(client)
    mark(client, first, case="regular_pay")
    rows = by_id(client)
    assert rows[first].category == "Income" and rows[first].income_type == "salary"
    assert rows[second].category != "Income"
    assert client.st.pay_rules() == {}


def test_remembered_every_deposit_from_them_is_pay(client):
    first, second, third = pay(client)
    res = mark(client, first, case="regular_pay", remember=True)
    assert res["remember"] is True
    assert res["title"] == "Counted as your regular pay, and the 2 other deposits from Acme Corp."
    rows = by_id(client)
    for tid in (second, third):
        assert rows[tid].category == "Income" and rows[tid].category_source == "pay_rule"
        assert rows[tid].income_type == "salary"
    # None of them is asked about any more.
    review = client.get("/api/review").get_json()
    asked = {it["txn"]["id"] for part in ("money_in", "income_type") for it in review[part]}
    assert not asked & {first, second, third}
    # The next one is sorted as it arrives.
    ingest(client.st, IngestResult([deposit(ago(0), amount=-2163.12, desc="ACME CORP PAY NEW")], "chq"))
    new = next(t for t in client.st.all_transactions() if t.description == "ACME CORP PAY NEW")
    assert new.category == "Income" and new.income_type == "salary"
    # Only deposits: money paid to them isn't income.
    ingest(client.st, IngestResult([row(40.0, "ACME CORP STORE", when=ago(0), merchant="Acme Corp")], "chq"))
    out = next(t for t in client.st.all_transactions() if t.description == "ACME CORP STORE")
    assert out.category != "Income"


def test_her_own_answer_wins_over_the_rule(client):
    first, second, third = pay(client)
    client.st.set_transaction_category(third, "Gifts")
    mark(client, first, case="regular_pay", remember=True)
    assert by_id(client)[third].category == "Gifts"


def test_undo_takes_the_rule_back(client):
    first, second, _ = pay(client)
    res = mark(client, first, case="regular_pay", remember=True)
    undo(client, res)
    assert client.st.pay_rules() == {}
    assert by_id(client)[second].category != "Income"


def test_the_rule_is_on_the_rules_page_and_can_be_removed(client):
    first, second, _ = pay(client)
    mark(client, first, case="regular_pay", remember=True)
    rules = client.get("/api/rules").get_json()["rules"]
    [rule] = [r for r in rules if r["kind"] == "pay"]
    assert rule == {"id": "pay:payer:acme corp", "kind": "pay", "name": "Acme Corp", "category": "Income"}
    assert client.put(f"/api/rules/{rule['id']}", json={"category": "Gifts"}).status_code == 400
    assert client.delete(f"/api/rules/{rule['id']}").status_code == 200
    assert client.st.pay_rules() == {}
    # What it sorted stays her pay; the next one is asked about again.
    kept = by_id(client)[second]
    assert kept.category == "Income" and kept.category_source == "user" and kept.income_type == "salary"
    ingest(client.st, IngestResult([deposit(ago(0), amount=-2163.12, desc="ACME CORP PAY NEW")], "chq"))
    new = next(t for t in client.st.all_transactions() if t.description == "ACME CORP PAY NEW")
    assert new.category != "Income" or new.category_source != "pay_rule"


def test_pay_by_e_transfer_is_remembered_by_who_sent_it(client):
    rows = load(client.st, *[row(-900, f"E-TRANSFER RECEIVED STUDIO NINE {i}", when=ago(14 * i + 1),
                                 who="Studio Nine") for i in range(2)])
    ids = list(rows.values())
    mark(client, ids[0], case="regular_pay", remember=True)
    assert list(client.st.pay_rules()) == ["person:studio nine"]
    assert by_id(client)[ids[1]].category == "Income"


def test_a_name_every_transfer_shares_is_never_a_rule(client):
    rows = load(client.st, row(-500, "Interac e-Transfer", when=ago(1), merchant="Interac e-Transfer"))
    [tid] = rows.values()
    assert cases(client, tid)["regular_pay"]["remember"] is None
    mark(client, tid, case="regular_pay", remember=True)
    assert client.st.pay_rules() == {}


def test_start_over_clears_pay_rules(client):
    first, *_ = pay(client)
    mark(client, first, case="regular_pay", remember=True)
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert client.st.pay_rules() == {}


def test_the_rest_leave_needs_a_look_with_the_first(client):
    """2026-10-29: deposits Needs a look asks "Is this income?" about. One
    marked as regular pay, remembered, takes the rest with it."""
    rows = load(client.st, *[deposit(ago(14 * i + 1), amount=-2150.0 - i * 6.5,
                                     desc=f"WEALTHSIMPLE TECHNOLOGIES {i}",
                                     merchant="Wealthsimple Technologies") for i in range(4)])
    ids = list(rows.values())
    review = client.get("/api/review").get_json()
    assert {it["txn"]["id"] for it in review["money_in"]} == set(ids)
    res = mark(client, ids[0], case="regular_pay", remember=True)
    assert res["title"] == ("Counted as your regular pay, and the 3 other deposits from "
                            "Wealthsimple Technologies.")
    review = client.get("/api/review").get_json()
    assert review["count"] == 0


def joint_pay(c, n=4):
    rows = load(c.st, *[deposit(ago(14 * i + 1), amount=-3419.22, desc="Wealthsimple-os - Direct Deposit",
                                merchant="Wealthsimple-os - Direct Deposit") for i in range(n)])
    ids = sorted((t.fingerprint for t in c.st.all_transactions()), key=str)
    acct = c.st.all_transactions()[0].account_id
    assert c.put(f"/api/accounts/{acct}/joint", json={"label": "Anastasia"}).status_code == 200
    return ids


def test_pay_into_a_joint_account_is_hers_and_not_asked_again(client):
    """2026-10-29: pay landing in an account she shares. Needs a look asks
    "Who put this in?" about money in from outside; her regular pay is hers,
    so the rule answers that too, and counts it."""
    ids = joint_pay(client)
    review = client.get("/api/review").get_json()
    asked = [it["txn"]["id"] for it in review["joint_in"]]
    assert sorted(asked) == sorted(ids)
    res = mark(client, asked[0], case="regular_pay", remember=True)
    assert "3 other deposits" in res["title"]
    assert client.get("/api/review").get_json()["joint_in"] == []
    assert all(t.joint_from == "me" for t in client.st.all_transactions())
    # Undo gives the question back.
    undo(client, res)
    assert len(client.get("/api/review").get_json()["joint_in"]) == 4


def test_a_rule_made_before_claims_its_waiting_joint_pay(client):
    """A pay rule saved before 2026-10-29 left joint deposits asked about;
    the next look at Needs a look answers them."""
    joint_pay(client)
    client.st.set_pay_rule("payer:wealthsimple-os - direct deposit", "Wealthsimple-os - Direct Deposit")
    assert len(client.get("/api/review").get_json()["joint_in"]) == 0
    assert all(t.joint_from == "me" for t in client.st.all_transactions())


def test_a_deposit_she_said_was_theirs_stays_theirs(client):
    ids = joint_pay(client, n=2)
    client.put(f"/api/transactions/{ids[0]}/joint-from", json={"who": "them"})
    client.st.set_pay_rule("payer:wealthsimple-os - direct deposit", "Wealthsimple-os - Direct Deposit")
    client.get("/api/review")
    by = {t.fingerprint: t.joint_from for t in client.st.all_transactions()}
    assert by[ids[0]] == "them" and by[ids[1]] == "me"
