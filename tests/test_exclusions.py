"""Leaving transactions out: your exclusion wins over every rule, stays
visible, can be undone, and is counted so nothing disappears silently."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.analytics import counts_as_spending, monthly_totals
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, description, account="chq", when=None, kind="depository",
        category=None, who=None):
    raw = {"account_type": kind}
    if who:
        raw["counterparty"] = who
    t = Transaction(date=when or day(1), description=description, amount=amount,
                    account_id=account, account_name=account, raw=raw)
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "ex.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t for t in st.all_transactions()}


def spending(st):
    return round(sum(t.amount for t in st.all_transactions() if counts_as_spending(t)), 2)


def test_one_row_out_and_back(client):
    rows = load(client.st, row(120, "WORK DINNER", kind="credit", category="Dining"),
                row(30, "LUNCH SPOT", kind="credit", category="Dining"))
    assert spending(client.st) == 150
    tid = rows["WORK DINNER"].fingerprint
    assert client.put(f"/api/transactions/{tid}/exclude", json={}).status_code == 400
    r = client.put(f"/api/transactions/{tid}/exclude",
                   json={"reason": "Work expense, reimbursed"})
    assert r.status_code == 200 and r.get_json()["transaction"]["excluded"]
    # A category you set doesn't save it: the exclusion wins.
    assert spending(client.st) == 30
    # Still listed, under its own filter.
    listed = client.get("/api/transactions?category=__excluded__").get_json()
    assert [t["id"] for t in listed["transactions"]] == [tid]
    assert client.delete(f"/api/transactions/{tid}/exclude").status_code == 200
    assert spending(client.st) == 150


def test_excluded_income_is_not_income(client):
    rows = load(client.st, row(-2000, "PAYROLL ACME"), row(-300, "PAYROLL ACME ADJ"))
    client.put(f"/api/transactions/{rows['PAYROLL ACME ADJ'].fingerprint}/exclude",
               json={"reason": "Passed on to my sister"})
    month = day(1)[:7]
    m = next(r for r in monthly_totals(client.st.all_transactions()) if r["month"] == month)
    assert m["income"] == 2000
    assert m["excluded"] == {"count": 1, "total": 300}


def test_a_rule_catches_now_and_later_and_can_be_removed(client):
    load(client.st, row(80, "FAMILY ACCT PURCHASE", account="fam", kind="credit",
                        category="Groceries"))
    preview = client.post("/api/exclusions?dry=1",
                          json={"account_id": "fam", "reason": "Family money"}).get_json()
    assert preview["matches"] == 1
    assert client.get("/api/exclusions").get_json()["rules"] == []       # dry: not saved
    r = client.post("/api/exclusions", json={"account_id": "fam", "reason": "Family money"})
    assert r.status_code == 201
    assert spending(client.st) == 0
    # A row that arrives later is caught too.
    load(client.st, row(45, "FAMILY ACCT LATER", account="fam", kind="credit",
                        category="Groceries"))
    assert spending(client.st) == 0
    rules = client.get("/api/exclusions").get_json()["rules"]
    assert rules[0]["matched"] == 2
    assert client.delete(f"/api/exclusions/{rules[0]['id']}").status_code == 200
    assert spending(client.st) == 125


def test_putting_back_one_row_a_rule_matched_keeps_it_back(client):
    rows = load(client.st,
                row(50, "SEND E-TFR ***A1", who="Alex Holding", category="Shopping"),
                row(60, "SEND E-TFR ***A2", who="Alex Holding", category="Shopping"))
    client.post("/api/exclusions", json={"counterparty": "alex holding",
                                         "reason": "Holding money for Alex"})
    assert spending(client.st) == 0
    tid = rows["SEND E-TFR ***A1"].fingerprint
    client.delete(f"/api/transactions/{tid}/exclude")
    # Another sync re-applies the rule; the row you put back stays back.
    load(client.st, row(5, "COFFEE", kind="credit", category="Coffee"))
    assert spending(client.st) == 55


def test_rules_need_a_reason_and_something_to_match(client):
    assert client.post("/api/exclusions", json={"account_id": "x"}).status_code == 400
    assert client.post("/api/exclusions", json={"reason": "why"}).status_code == 400
    assert client.post("/api/exclusions", json={"keyword": "ab", "reason": "r"}).status_code == 400


def test_an_excluded_row_never_pairs_as_a_transfer(client):
    rows = load(client.st,
                row(500, "TFR-TO 1234567", account="chq"),
                row(-500, "TFR-FR 7654321", account="sav", when=day(1)))
    out = client.st.get_transaction(rows["TFR-TO 1234567"].fingerprint)
    assert out.category == "Transfers"                  # paired: neutral
    client.put(f"/api/transactions/{rows['TFR-FR 7654321'].fingerprint}/exclude",
               json={"reason": "Not mine"})
    out = client.st.get_transaction(rows["TFR-TO 1234567"].fingerprint)
    assert out.category == "Unsorted transfers"         # its other end is gone


def test_an_excluded_charge_is_no_piggy_banks(client):
    rows = load(client.st, row(900, "FLIGHT", kind="credit", category="Travel"))
    tid = rows["FLIGHT"].fingerprint
    client.put(f"/api/transactions/{tid}/exclude", json={"reason": "Work trip"})
    t = client.st.get_transaction(tid)
    assert t.bank_id is None and not counts_as_spending(t)
