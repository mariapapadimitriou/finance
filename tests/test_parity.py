"""The parity pass against the Pearl Handoff File (2026-10-15; THL-231 to
THL-234): Sort a date range and Sorted together (DR-01, DR-02), the list by
merchant or by category with headers (VF-01), the last three months and
"owed to you" (VF-02, WW-01), the cases grouped as the sheet draws them
(WW-02, WW-04), Who sent this? in Needs a look (R-09), and what Pearl
decides per category (CR-01)."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def in_month(d=1):
    return f"{MONTH}-{d:02d}"


def months_ago(n, d=5):
    y, m = TODAY.year, TODAY.month - n
    while m <= 0:
        y, m = y - 1, m + 12
    return f"{y:04d}-{m:02d}-{d:02d}"


def row(amount, description, account="chq", when=None, kind="depository",
        category=None, who=None, merchant=None):
    raw = {"account_type": kind, "issuer_category": ""}
    if who:
        raw["counterparty"] = who
    t = Transaction(date=when or in_month(2), description=description, amount=amount,
                    account_id=account, account_name=account, raw=raw, merchant=merchant or "")
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "p.db"))
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


# ── Sort a date range ────────────────────────────────────────────────────

def trip_rows():
    return [
        row(420, "HOTEL BONAVENTURE", account="card", kind="credit", category="Lodging",
            merchant="Hotel Bonaventure", when=in_month(3)),
        row(62, "SCHWARTZ'S", account="card", kind="credit", category="Dining",
            merchant="Schwartz's", when=in_month(4)),
        row(18, "STM METRO", account="card", kind="credit", category="Transport",
            merchant="STM", when=in_month(4)),
        row(85, "ROGERS", account="card", kind="credit", category="Phone & Internet",
            merchant="Rogers", when=in_month(4)),              # a bill: stays
        *[row(85, "ROGERS", account="card", kind="credit", category="Phone & Internet",
              merchant="Rogers", when=months_ago(n, 4)) for n in (1, 2, 3)],
        row(-2000, "PAYROLL ACME", category="Income", when=in_month(3)),  # money in: stays
        row(300, "VISA PAYMENT", category="Transfers", when=in_month(5)),  # a transfer: stays
        row(40, "LOBLAWS", account="card", kind="credit", category="Groceries",
            merchant="Loblaws", when=in_month(9)),             # outside the range
    ]


def test_sort_a_date_range_moves_purchases_only(client):
    load(client.st, *trip_rows())                       # Rogers recurs: a bill
    body = {"name": "Montréal trip", "first": in_month(3), "last": in_month(5), "category": "Travel"}
    p = client.post("/api/ranges/preview", json=body).get_json()
    assert p["count"] == 3 and p["total"] == 500.0
    assert p["title"] == "3 purchases · $500.00 become Travel."
    assert p["mostly"] == "Mostly Lodging, Dining and Transport."
    assert p["staying"].startswith("Staying as they are: ")
    assert "1 deposit" in p["staying"] and "1 transfer" in p["staying"]
    assert "Money in, transfers, card payments, savings and lending never change." in p["staying"]

    r = client.post("/api/ranges", json=body)
    assert r.status_code == 201, r.get_json()
    out = r.get_json()
    assert out["title"] == "Sorted 3 purchases as Travel."
    assert out["range"]["count"] == 3 and out["range"]["total"] == 500.0
    rows = {t["description"]: t for t in listing(client)["transactions"]}
    assert {rows[k]["category"] for k in ("HOTEL BONAVENTURE", "SCHWARTZ'S", "STM METRO")} == {"Travel"}
    assert rows["PAYROLL ACME"]["category"] == "Income"
    assert rows["VISA PAYMENT"]["category"] == "Transfers"
    assert rows["LOBLAWS"]["category"] == "Groceries"
    # Sorted together lists it with its running total.
    listed = client.get("/api/ranges").get_json()["ranges"]
    assert listed[0]["name"] == "Montréal trip" and listed[0]["total"] == 500.0
    rid = listed[0]["id"]
    # Change: the last day moves earlier, so the metro ride goes back.
    r = client.put(f"/api/ranges/{rid}", json={**body, "last": in_month(3)}).get_json()
    assert r["range"]["count"] == 1
    rows = {t["description"]: t for t in listing(client)["transactions"]}
    assert rows["SCHWARTZ'S"]["category"] == "Dining" and rows["HOTEL BONAVENTURE"]["category"] == "Travel"
    # Remove: everything goes back.
    r = client.delete(f"/api/ranges/{rid}").get_json()
    assert r["restored"] == 1 and r["title"] == "Removed. 1 purchase went back."
    rows = {t["description"]: t for t in listing(client)["transactions"]}
    assert rows["HOTEL BONAVENTURE"]["category"] == "Lodging"
    assert client.get("/api/ranges").get_json()["ranges"] == []
    assert client.post("/api/ranges", json={**body, "category": "Income"}).status_code == 400
    assert client.post("/api/ranges", json={**body, "last": "2020-01-01"}).status_code == 400


def test_a_range_survives_resorting_and_a_hand_change_is_kept(client):
    from finance.categorize import apply_categories
    ids = load(client.st, *trip_rows()[:3])
    body = {"name": "Trip", "first": in_month(3), "last": in_month(5), "category": "Travel"}
    rid = client.post("/api/ranges", json=body).get_json()["range"]["id"]
    rows = client.st.all_transactions()
    apply_categories(rows, client.st.overrides())            # a re-sort leaves them alone
    assert all(t.category == "Travel" for t in rows)
    # She moves one by hand afterwards: Remove leaves her choice alone.
    client.patch(f"/api/transactions/{ids['STM METRO']}", json={"category": "Transport"})
    client.delete(f"/api/ranges/{rid}")
    rows = {t["description"]: t for t in listing(client)["transactions"]}
    assert rows["STM METRO"]["category"] == "Transport"
    assert rows["HOTEL BONAVENTURE"]["category"] == "Lodging"


# ── Views, months and owed ───────────────────────────────────────────────

def test_by_merchant_and_by_category_group_the_rows_under_headers(client):
    load(client.st, row(12, "COFFEE A", account="card", kind="credit", category="Coffee",
                        merchant="Pilot", when=in_month(1)),
         row(8, "COFFEE B", account="card", kind="credit", category="Coffee", merchant="Pilot",
             when=in_month(2)),
         row(60, "LOBLAWS", account="card", kind="credit", category="Groceries",
             merchant="Loblaws", when=in_month(3)))
    d = listing(client, by="merchant")
    assert d["transactions"] == []
    g = d["groups_of"]
    assert [(x["name"], x["count"], x["spent"]) for x in g] == [("Loblaws", 1, 60), ("Pilot", 2, 20)]
    assert [r["description"] for r in g[1]["rows"]] == ["COFFEE B", "COFFEE A"]
    c = listing(client, by="category")["groups_of"]
    assert [(x["name"], x["spent"]) for x in c] == [("Groceries", 60), ("Coffee", 20)]


def test_last_three_months_and_owed_to_you(client):
    ids = load(client.st,
               row(100, "OLD", account="card", kind="credit", category="Shopping", when=months_ago(4)),
               row(50, "RECENT", account="card", kind="credit", category="Shopping", when=months_ago(2)),
               row(85, "SUSHI NAMI", account="card", kind="credit", category="Dining",
                   merchant="Sushi Nami", when=in_month(2)))
    assert listing(client, month="last3")["total"] == 2
    assert listing(client, month="all")["total"] == 3
    assert listing(client)["owed"] is None
    client.put(f"/api/transactions/{ids['SUSHI NAMI']}/split",
               json={"mode": "even", "people": [{"name": "Priya", "amount": 42.5}], "watch": True})
    d = listing(client)
    assert d["owed"] == {"names": ["Priya"], "total": 42.5, "count": 1, "ids": [ids["SUSHI NAMI"]]}
    assert [r["description"] for r in listing(client, owed=1)["transactions"]] == ["SUSHI NAMI"]


# ── The sheet's groups ───────────────────────────────────────────────────

def test_cases_come_grouped_with_pearls_best_guess_on_top(client):
    ids = load(client.st, row(200, "TFR-TO 12343333"), row(-300, "E-TRANSFER FROM SAM", who="Sam"))
    d = client.get(f"/api/transactions/{ids['TFR-TO 12343333']}/cases").get_json()
    assert d["best"] == "saved"                      # an unsorted transfer to an account
    assert [g["key"] for g in d["groups"]] == ["spending", "not_spending", "not_mine"]
    by = {c["key"]: c for c in d["cases"]}
    assert by["saved"]["label"] == "Put into savings" and by["saved"]["group"] == "not_spending"
    assert by["bill"]["label"] == "A bill"
    assert by["work"]["label"] == "A work expense, to be reimbursed"
    assert "saved_part" not in by                    # kept off the sheet
    d = client.get(f"/api/transactions/{ids['E-TRANSFER FROM SAM']}/cases").get_json()
    assert d["best"] == "pay"
    assert [g["key"] for g in d["groups"]] == ["income", "not_income"]
    assert [c["key"] for c in d["cases"]] == [
        "pay", "regular_pay", "payback", "refund", "reimbursement", "own", "out_of_savings",
        "borrowed", "lent_back", "not_mine"]
    r = client.post(f"/api/transactions/{ids['E-TRANSFER FROM SAM']}/mark",
                    json={"case": "regular_pay"}).get_json()
    assert r["title"] == "Counted as your regular pay."
    assert listing(client)["totals"]["income"] == 300


def test_savings_accounts_say_which_are_part_of_the_anchor(client):
    client.st.note_account("sav1", name="TD Savings ••8820", item_id="it",
                           account_type="depository", subtype="savings")
    client.st.set_setting("anchor_accounts", '["sav1"]')
    r = client.post("/api/accounts/manual", json={"name": "TD TFSA", "kind": "investment",
                                                  "balance": 100, "last4": "5521"}).get_json()
    ids = load(client.st, row(200, "TFR-TO 5521"))
    d = client.get(f"/api/transactions/{ids['TFR-TO 5521']}/cases").get_json()
    assert [(a["label"], a["sub"]) for a in d["accounts"]] == [
        ("TD Savings ••8820", "Part of your Anchor"), ("TD TFSA", "Investment · added by hand")]


# ── Who sent this? ───────────────────────────────────────────────────────

def test_who_sent_this_is_asked_for_a_nameless_etransfer(client):
    ids = load(client.st, row(-42.5, "E-TRANSFER RECEIVED ***Q7K"),
               row(-60, "E-TRANSFER FROM SAM LEE", who="Sam Lee"))
    r = client.get("/api/review").get_json()
    assert [it["txn"]["id"] for it in r["who_sent"]] == [ids["E-TRANSFER RECEIVED ***Q7K"]]
    assert r["who_sent"][0]["key"] == "who:" + ids["E-TRANSFER RECEIVED ***Q7K"]
    client.put(f"/api/transactions/{ids['E-TRANSFER RECEIVED ***Q7K']}/party", json={"name": "Priya"})
    assert client.get("/api/review").get_json()["who_sent"] == []


# ── What Pearl decides per category ──────────────────────────────────────

def test_rules_carry_pearls_own_kind_per_category(client):
    load(client.st, *[row(85, "ROGERS", account="card", kind="credit", category="Phone & Internet",
                          merchant="Rogers", when=months_ago(n, 3)) for n in range(4)],
         row(40, "LOBLAWS", account="card", kind="credit", category="Groceries", merchant="Loblaws"))
    pk = client.get("/api/rules").get_json()["pearl_kinds"]
    assert pk["Phone & Internet"] == "fixed" and pk["Groceries"] == "variable"
    assert pk["Rent & Housing"] == "fixed" and "Income" not in pk
