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
    assert res["title"] == "Counted as your regular pay, and every deposit from Acme Corp."
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
