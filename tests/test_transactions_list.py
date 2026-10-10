"""The transactions list (THL-122): what counts, what shows, what's suggested."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def day(n):
    return (TODAY - timedelta(days=n)).isoformat()


def in_month(d=1):
    return f"{MONTH}-{d:02d}"


def row(amount, description, account="chq", when=None, kind="depository",
        category=None, who=None, issuer="", pending=False, merchant=None):
    raw = {"account_type": kind, "issuer_category": issuer}
    if who:
        raw["counterparty"] = who
    if pending:
        raw["pending"] = True
    t = Transaction(date=when or in_month(), description=description, amount=amount,
                    account_id=account, account_name=account, raw=raw,
                    merchant=merchant or "")
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "list.db"))
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
    return {t.description: t.fingerprint for t in st.all_transactions()}


def listing(c, **params):
    params.setdefault("month", MONTH)
    res = c.get("/api/transactions/list", query_string=params)
    assert res.status_code == 200, res.get_json()
    return res.get_json()


def by_desc(data):
    return {r["description"]: r for r in data["transactions"]}


def test_counts_no_rows_are_out_of_spent_and_income_and_summed(client):
    load(client.st,
         row(50, "GROCER", account="card", kind="credit", category="Groceries"),
         row(-2000, "PAYROLL ACME", category="Income"),
         row(612, "VISA PREAUTH PYMT"),
         row(-612, "PAYMENT THANK YOU", account="card", kind="credit"))
    data = listing(client)
    rows = by_desc(data)
    assert data["totals"]["spent"] == 50
    assert data["totals"]["income"] == 2000
    assert data["totals"]["not_counted"] == 1224
    pay = rows["VISA PREAUTH PYMT"]
    assert pay["counts"] == "none" and pay["chip"] == {"label": "Transfer", "suggested": False}
    assert pay["note"] == "Card payment · not counted as spending"
    assert rows["PAYROLL ACME"]["counts"] == "income" and rows["PAYROLL ACME"]["inflow"]


def test_pending_counts_toward_spending(client):
    load(client.st, row(24.80, "UBER EATS", account="card", kind="credit",
                        category="Food Delivery", pending=True))
    data = listing(client)
    r = data["transactions"][0]
    assert r["pending"] is True and r["counts"] == "spending"
    assert data["totals"]["spent"] == 24.80


def test_a_split_shows_and_counts_only_her_share(client):
    ids = load(client.st,
               row(85, "SUSHI NAMI", account="card", kind="credit", category="Dining",
                   merchant="Sushi Nami", when=in_month(1)),
               row(-42.5, "E-TRANSFER RECEIVED PRIYA", who="Priya",
                   issuer="TRANSFER_IN_ACCOUNT_TRANSFER", when=in_month(1)))
    client.post(f"/api/transactions/{ids['SUSHI NAMI']}/paybacks/"
                f"{ids['E-TRANSFER RECEIVED PRIYA']}")
    data = listing(client)
    rows = by_desc(data)
    sushi = rows["SUSHI NAMI"]
    assert sushi["amount"] == 42.5 and sushi["full_amount"] == 85
    assert sushi["note"] == "Your share of $85.00 · split with Priya"
    back = rows["E-TRANSFER RECEIVED PRIYA"]
    assert back["chip"]["label"] == "Repayment" and back["counts"] == "none"
    assert back["note"] == "Paid you back for Sushi Nami · not income"
    assert data["totals"] == {"spent": 42.5, "income": 0, "not_counted": 42.5, "count": 2}


def test_a_typed_share_is_what_counts(client):
    ids = load(client.st, row(100, "DINNER", account="card", kind="credit", category="Dining"))
    client.put(f"/api/transactions/{ids['DINNER']}/share", json={"my_share": 25})
    data = listing(client)
    assert data["transactions"][0]["amount"] == 25
    assert data["totals"]["spent"] == 25


def test_suggested_until_confirmed_or_edited(client):
    ids = load(client.st,
               row(24.8, "UBER EATS", account="card", kind="credit", merchant="Uber Eats"),
               row(40, "LOBLAWS", account="card", kind="credit", merchant="Loblaws"))
    rows = by_desc(listing(client))
    assert rows["UBER EATS"]["suggested"] and rows["LOBLAWS"]["suggested"]
    assert client.put(f"/api/transactions/{ids['UBER EATS']}/confirm").status_code == 200
    client.patch(f"/api/transactions/{ids['LOBLAWS']}", json={"category": "Groceries"})
    rows = by_desc(listing(client))
    assert not rows["UBER EATS"]["suggested"] and not rows["LOBLAWS"]["suggested"]
    # Confirming takes it out of the review queue too.
    assert "cat:" + ids["UBER EATS"] in client.st.dismissed_reviews()
    # A later re-filing makes the new category a suggestion again.
    client.st.confirm_category(ids["UBER EATS"], "Something else")
    assert by_desc(listing(client))["UBER EATS"]["suggested"]


def test_unsorted_transfer_is_suggested_and_counts(client):
    load(client.st, row(200, "SEND E-TFR ***X", who="M. Papas"))
    r = listing(client)["transactions"][0]
    assert r["chip"] == {"label": "Not sorted yet", "suggested": True}
    assert r["counts"] == "spending" and r["note_link"]


def test_search_by_merchant_note_and_amount(client):
    ids = load(client.st,
               row(24.8, "UBER EATS", account="card", kind="credit", category="Food Delivery"),
               row(240, "IKEA", account="card", kind="credit", category="Home"))
    client.put(f"/api/transactions/{ids['IKEA']}/note", json={"note": "Bookshelf for the study"})
    found = lambda q: [r["description"] for r in listing(client, q=q)["transactions"]]
    assert found("24.80") == ["UBER EATS"]
    assert found("$24.8") == ["UBER EATS"]
    assert found("240") == ["IKEA"]
    assert found("bookshelf") == ["IKEA"]
    assert found("uber") == ["UBER EATS"]
    assert found("sushi place") == []


def test_notes_are_private_and_short(client):
    ids = load(client.st, row(10, "COFFEE", account="card", kind="credit", category="Coffee"))
    url = f"/api/transactions/{ids['COFFEE']}/note"
    assert client.put(url, json={"note": "x" * 141}).status_code == 400
    assert client.put(url, json={"note": "  with  Sam "}).get_json()["note"] == "with Sam"
    assert listing(client)["transactions"][0]["my_note"] == "with Sam"
    client.put(url, json={"note": ""})
    assert listing(client)["transactions"][0]["my_note"] == ""


def test_group_filter_and_usual_month(client):
    first = date.fromisoformat(in_month(1))
    def months_ago(n):
        y, m = first.year, first.month - n
        while m <= 0:
            y, m = y - 1, m + 12
        return f"{y:04d}-{m:02d}-05"
    load(client.st,
         row(100, "BAR A", account="card", kind="credit", category="Alcohol & Bars",
             when=months_ago(1)),
         row(200, "BAR B", account="card", kind="credit", category="Alcohol & Bars",
             when=months_ago(2)),
         row(300, "BAR C", account="card", kind="credit", category="Alcohol & Bars",
             when=months_ago(3)),
         row(90, "BAR NOW", account="card", kind="credit", category="Alcohol & Bars"),
         row(500, "RENT", category="Rent & Housing"))
    data = listing(client, group="lifestyle")
    assert [r["description"] for r in data["transactions"]] == ["BAR NOW"]
    assert data["focus"] == {"label": "Lifestyle", "kind": "spending", "total": 90,
                             "usual": 200}
    assert listing(client, group="essentials")["totals"]["spent"] == 500
    assert client.get("/api/transactions/list?group=nope").status_code == 400


def test_amounts_are_never_negative_and_excluded_rows_hidden(client):
    ids = load(client.st,
               row(-30, "REFUND SHOP", account="card", kind="credit", category="Shopping"),
               row(80, "WORK LUNCH", account="card", kind="credit", category="Dining"))
    client.put(f"/api/transactions/{ids['WORK LUNCH']}/exclude", json={"reason": "Work"})
    data = listing(client)
    assert [r["description"] for r in data["transactions"]] == ["REFUND SHOP"]
    r = data["transactions"][0]
    assert r["amount"] == 30 and r["inflow"] and r["note"] == "Refund"
    assert data["totals"]["spent"] == -30


def test_pages_of_25(client):
    load(client.st, *[row(1 + i, f"SHOP {i:02d}", account="card", kind="credit",
                          category="Shopping", when=in_month(1)) for i in range(30)])
    first = listing(client)
    assert len(first["transactions"]) == 25 and first["total"] == 30
    assert len(listing(client, offset=25)["transactions"]) == 5


def test_detail_endpoint(client):
    ids = load(client.st, row(24.8, "UBER* EATS TORONTO ON", account="card", kind="credit",
                              merchant="Uber Eats"))
    r = client.get(f"/api/transactions/{ids['UBER* EATS TORONTO ON']}").get_json()
    assert r["merchant"] == "Uber Eats" and r["description"] == "UBER* EATS TORONTO ON"
    assert r["counts_toward"].endswith("safe to spend")
    assert client.get("/api/transactions/nope").status_code == 404


def test_left_out_rows_are_listed_on_their_own(client):
    ids = load(client.st, row(80, "WORK LUNCH", account="card", kind="credit", category="Dining"))
    client.put(f"/api/transactions/{ids['WORK LUNCH']}/exclude", json={"reason": "Work"})
    assert listing(client)["transactions"] == []
    out = listing(client, excluded=1)
    r = out["transactions"][0]
    assert r["chip"] == {"label": "Left out", "suggested": False}
    assert r["note"] == "Left out · Work" and r["counts"] == "none"
    assert client.get(f"/api/transactions/{ids['WORK LUNCH']}").get_json()["excluded"] == "Work"
