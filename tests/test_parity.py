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
    assert by["work"]["label"] == "To be reimbursed"
    assert "saved_part" not in by                    # kept off the sheet
    d = client.get(f"/api/transactions/{ids['E-TRANSFER FROM SAM']}/cases").get_json()
    assert d["best"] == "pay"
    assert [g["key"] for g in d["groups"]] == ["income", "not_income"]
    assert [c["key"] for c in d["cases"]] == [
        "pay", "regular_pay", "payback", "refund", "reimbursement", "own", "cash", "out_of_savings",
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
    q7k = ids["E-TRANSFER RECEIVED ***Q7K"]
    # One transaction, one question (2026-10-22): when it is already asked
    # about as money in, that card asks who sent it, and it isn't listed twice.
    asked = [it for it in r["money_in"] if it["txn"]["id"] == q7k]
    listed = [it for it in r["who_sent"] if it["txn"]["id"] == q7k]
    assert len(asked) + len(listed) == 1
    if asked:
        assert asked[0]["nameless"] is True
    else:
        assert listed[0]["key"] == "who:" + q7k
    client.put(f"/api/transactions/{q7k}/party", json={"name": "Priya"})
    r = client.get("/api/review").get_json()
    assert r["who_sent"] == []
    assert not any(it.get("nameless") for it in r["money_in"])


@pytest.mark.parametrize("case", ["pay", "regular_pay", "own", "cash", "out_of_savings", "borrowed",
                                  "lent_back", "refund", "payback", "not_mine"])
def test_a_nameless_etransfer_sorted_elsewhere_is_not_asked_again(client, case):
    """2026-10-23: sorted on the transactions tab, a nameless e-Transfer in
    used to come back in Needs a look as "Who sent this?", so it read as not
    sorted. Once she has said what it was, it leaves Needs a look."""
    ids = load(client.st, row(-80, "E-TRANSFER RECEIVED ***R8M"),
               row(80, "SUSHI NAMI", account="card", kind="credit", merchant="Sushi Nami",
                   category="Dining"))
    tid = ids["E-TRANSFER RECEIVED ***R8M"]
    from finance.review import for_store, ids_in
    assert tid in ids_in(for_store(client.st))
    res = client.post(f"/api/transactions/{tid}/mark", json={
        "case": case, "income_kind": "salary", "account": "", "reason": "", "category": "Dining",
        "charge": ids["SUSHI NAMI"]})
    assert res.status_code == 200, res.get_json()
    assert tid not in ids_in(for_store(client.st))


# ── What Pearl decides per category ──────────────────────────────────────

def test_rules_carry_pearls_own_kind_per_category(client):
    load(client.st, *[row(85, "ROGERS", account="card", kind="credit", category="Phone & Internet",
                          merchant="Rogers", when=months_ago(n, 3)) for n in range(4)],
         row(40, "LOBLAWS", account="card", kind="credit", category="Groceries", merchant="Loblaws"))
    pk = client.get("/api/rules").get_json()["pearl_kinds"]
    assert pk["Phone & Internet"] == "fixed" and pk["Groceries"] == "variable"
    assert pk["Rent & Housing"] == "fixed" and "Income" not in pk


def test_a_range_can_be_paid_from_a_treasure_chest(client):
    """CAL-07/CAL-08: the chest is optional; with one, every purchase the
    range sorts is paid from it, and Remove or a change puts them back."""
    ids = load(client.st, *trip_rows())
    bank = client.post("/api/piggy", json={"name": "Japan trip", "target": 3000, "cadence": "once",
                                           "target_date": "2027-10-01"}).get_json()
    bank_id = bank.get("id") or bank.get("bank", {}).get("id")
    body = {"name": "Montréal trip", "first": in_month(3), "last": in_month(5), "category": "Travel",
            "bank_id": bank_id}
    p = client.post("/api/ranges/preview", json=body).get_json()
    assert p["title"] == "3 purchases · $500.00 become Travel, paid from Japan trip."
    assert p["bank"] == "Japan trip"
    assert p["effect"].startswith("Japan trip pays $500.00 and ")
    assert "Allowance goes up by $500.00" in p["effect"]
    assert p["staying"].startswith("The purchases keep Travel and show “Paid from Japan trip”. ")
    # Without a chest, nothing about one.
    plain = client.post("/api/ranges/preview", json={**body, "bank_id": None}).get_json()
    assert plain["bank"] is None and plain["effect"] == "" and "chest" not in plain["title"]

    out = client.post("/api/ranges", json=body)
    assert out.status_code == 201, out.get_json()
    assert out.get_json()["title"] == "Sorted 3 purchases as Travel, paid from Japan trip."
    assert out.get_json()["range"]["bank"] == "Japan trip"
    for key in ("HOTEL BONAVENTURE", "SCHWARTZ'S", "STM METRO"):
        assert client.st.get_transaction(ids[key]).bank_id == bank_id
    assert client.st.get_transaction(ids["ROGERS"]).bank_id is None      # the bill stays
    rid = out.get_json()["range"]["id"]
    # Paid for or not, the trip is still 3 purchases · $500: the list says
    # so, and a change's preview still counts them (not as transfers).
    assert client.get("/api/ranges").get_json()["ranges"][0]["total"] == 500.0
    again = client.post("/api/ranges/preview", json={**body, "id": rid}).get_json()
    assert again["count"] == 3 and again["total"] == 500.0 and "1 transfer" in again["staying"]
    assert "has $" in again["effect"] or "behind" in again["effect"]
    # Change: no chest any more, so the chest stops paying.
    client.put(f"/api/ranges/{rid}", json={**body, "bank_id": None})
    assert all(client.st.get_transaction(ids[k]).bank_id is None
               for k in ("HOTEL BONAVENTURE", "SCHWARTZ'S", "STM METRO"))
    client.put(f"/api/ranges/{rid}", json=body)
    assert client.st.get_transaction(ids["HOTEL BONAVENTURE"]).bank_id == bank_id
    # Remove: back to the month, and the categories they were.
    client.delete(f"/api/ranges/{rid}")
    assert client.st.get_transaction(ids["HOTEL BONAVENTURE"]).bank_id is None
    rows = {t["description"]: t for t in listing(client)["transactions"]}
    assert rows["HOTEL BONAVENTURE"]["category"] == "Lodging"
    # A chest that doesn't exist, or nonsense, is refused.
    assert client.post("/api/ranges", json={**body, "bank_id": 999}).status_code == 400
    assert client.post("/api/ranges", json={**body, "bank_id": "x"}).status_code == 400
