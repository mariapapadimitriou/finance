"""Sort a date range: one category for every purchase in it, kept as an
edit with running totals that can be put back (finance/bulk_edits.py)."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def tx(day, merchant, amount, category, **kw):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, account_id="card", account_name="card", **kw)


def away():
    """Five days in Costa Rica, with rent, a subscription and pay landing too."""
    rows = []
    for m in ("07", "08", "09", "10"):
        rows.append(tx(f"2026-{m}-01", "Parkside Properties", 2000.0, "Rent & Housing"))
        rows.append(tx(f"2026-{m}-03", "Netflix", 16.49, "Subscriptions"))
    rows += [
        tx("2026-10-01", "Northwind Ltd", -2150.0, "Income"),
        tx("2026-10-02", "Soda La Casita", 18.40, "Dining"),
        tx("2026-10-02", "Cafe Monteverde", 4.80, "Coffee"),
        tx("2026-10-04", "Hotel Belmar", 410.0, "Lodging"),
        tx("2026-10-05", "Uber", 23.10, "Transport"),
        tx("2026-10-05", "TD Visa Payment", -500.0, "Transfers"),
        tx("2026-10-09", "Loblaws", 80.0, "Groceries"),          # home again
    ]
    return rows


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    import finance.api as api
    monkeypatch.setattr(api, "_today_iso", lambda: "2026-10-12")
    app = create_app(str(tmp_path / "edits.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        ingest(c.st, IngestResult(away(), "card"))
        # The categories a bank feed would have sent, which the rules keep.
        wanted = {r.merchant: r.category for r in away()}
        c.st.set_categories({t.fingerprint: (wanted[t.merchant], "plaid")
                             for t in c.st.all_transactions()})
        yield c


def by_merchant(c):
    return {t.merchant: t for t in c.st.all_transactions() if t.date.startswith("2026-10")}


def preview(c, start="2026-10-01", end="2026-10-05", category="Travel", **kw):
    return c.post("/api/bulk-edits/preview",
                  json={"start": start, "end": end, "category": category, **kw}).get_json()


def save(c, name="Costa Rica", category="Travel", start="2026-10-01", end="2026-10-05",
         edit_id=None):
    body = {"name": name, "category": category, "start": start, "end": end}
    if edit_id:
        return c.put(f"/api/bulk-edits/{edit_id}", json=body)
    return c.post("/api/bulk-edits", json=body)


def test_the_preview_says_what_changes_and_what_stays(client):
    p = preview(client)
    # Every purchase in the range, rent and Netflix included.
    assert p["count"] == 6 and p["category"] == "Travel"
    assert p["total"] == round(2000 + 16.49 + 18.40 + 4.80 + 410.0 + 23.10, 2)
    assert [c["category"] for c in p["categories"]] == [
        "Rent & Housing", "Lodging", "Transport", "Dining", "Subscriptions", "Coffee"]
    assert p["staying"] == {"money_in": 2}                # pay, and the card payment
    assert p["in_dates"] == 8 and "rows" not in p


def test_saving_gives_every_purchase_the_category_and_leaves_money_in(client):
    r = save(client)
    assert r.status_code == 200
    edit = r.get_json()["edit"]
    assert edit["name"] == "Costa Rica" and edit["category"] == "Travel"
    assert edit["count"] == 6 and edit["total"] == 2472.79
    rows = by_merchant(client)
    for m in ("Soda La Casita", "Parkside Properties", "Netflix", "Hotel Belmar"):
        assert rows[m].category == "Travel" and rows[m].category_source == "bulk"
    assert rows["TD Visa Payment"].category == "Transfers"
    assert rows["Northwind Ltd"].category == "Income"
    assert rows["Loblaws"].category == "Groceries"            # after the range
    listed = client.get("/api/transactions/list", query_string={"month": "2026-10"}).get_json()
    soda = next(t for t in listed["transactions"] if t["merchant"] == "Soda La Casita")
    assert soda["note"] == "Costa Rica · sorted together" and soda["bulk_edit"] == "Costa Rica"


def test_any_spending_category_works_and_income_is_refused(client):
    r = save(client, name="Groceries week", category="Groceries")
    assert r.status_code == 200
    assert by_merchant(client)["Soda La Casita"].category == "Groceries"
    for bad in ("Income", "Transfers", "Saved", "Nonsense"):
        assert save(client, name="x", category=bad).status_code == 400


def test_the_list_keeps_running_totals(client):
    save(client)
    [edit] = client.get("/api/bulk-edits").get_json()["edits"]
    assert (edit["count"], edit["total"]) == (6, 2472.79)
    ingest(client.st, IngestResult([tx("2026-10-04", "Selvatura Park", 65.0, "Entertainment")],
                                   "card"))
    park = by_merchant(client)["Selvatura Park"].fingerprint
    client.st.set_categories({park: ("Entertainment", "plaid")})
    # A charge that posts later isn't sorted on its own…
    assert by_merchant(client)["Selvatura Park"].category == "Entertainment"
    # …saving the edit again picks it up, and the total moves.
    save(client, edit_id=edit["id"])
    [edit] = client.get("/api/bulk-edits").get_json()["edits"]
    assert (edit["count"], edit["total"]) == (7, 2537.79)


def test_changing_the_range_or_category_and_removing_put_rows_back(client):
    edit = save(client).get_json()["edit"]
    save(client, end="2026-10-04", edit_id=edit["id"])        # Uber was on the 5th
    rows = by_merchant(client)
    assert rows["Uber"].category == "Transport" and rows["Hotel Belmar"].category == "Travel"
    save(client, category="Entertainment", end="2026-10-04", edit_id=edit["id"])
    assert by_merchant(client)["Hotel Belmar"].category == "Entertainment"
    assert client.delete(f"/api/bulk-edits/{edit['id']}").get_json()["put_back"] == 5
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Dining" and rows["Hotel Belmar"].category == "Lodging"
    assert rows["Netflix"].category == "Subscriptions"
    assert client.get("/api/bulk-edits").get_json()["edits"] == []


def test_a_purchase_she_sorted_herself_moves_and_comes_back_as_hers(client):
    soda = by_merchant(client)["Soda La Casita"].fingerprint
    client.st.set_transaction_category(soda, "Gifts")
    edit = save(client).get_json()["edit"]
    assert by_merchant(client)["Soda La Casita"].category == "Travel"
    client.delete(f"/api/bulk-edits/{edit['id']}")
    row = by_merchant(client)["Soda La Casita"]
    assert (row.category, row.category_source) == ("Gifts", "user")


def test_a_row_she_resorts_afterwards_keeps_her_choice(client):
    edit = save(client).get_json()["edit"]
    soda = by_merchant(client)["Soda La Casita"].fingerprint
    client.st.set_transaction_category(soda, "Gifts")
    assert preview(client, edit_id=edit["id"])["staying"].get("yours") == 1
    save(client, edit_id=edit["id"])
    assert by_merchant(client)["Soda La Casita"].category == "Gifts"


def test_rows_that_are_not_hers_and_other_edits_rows_are_left_alone(client):
    uber = by_merchant(client)["Uber"].fingerprint
    client.st.exclude(uber, "manual")
    first = save(client, name="First", start="2026-10-01", end="2026-10-02").get_json()["edit"]
    p = preview(client)
    assert p["staying"].get("other_edit") == 3 and "excluded" not in p["staying"]
    save(client, name="Second", category="Entertainment")
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Travel"        # still the first edit's
    assert rows["Hotel Belmar"].category == "Entertainment"
    assert rows["Uber"].category == "Transport"
    assert first["count"] == 3                                 # rent, Soda, Cafe


def test_the_preview_says_when_there_is_nothing_in_the_dates(client):
    p = preview(client, start="2026-06-01", end="2026-06-10")
    assert p["count"] == 0 and p["in_dates"] == 0


def test_it_survives_reopening_the_ledger(client):
    from finance.store import Store
    save(client)
    again = Store(client.st.path)
    soda = next(t for t in again.all_transactions() if t.merchant == "Soda La Casita")
    assert soda.category == "Travel"


def test_a_row_an_old_trip_moved_keeps_its_category_as_hers(tmp_path):
    """Trips are gone: their tables are dropped and their rows become her own
    choice, so nothing changes on screen."""
    import sqlite3
    from finance.store import Store
    db = str(tmp_path / "old.db")
    con = sqlite3.connect(db)
    con.execute("CREATE TABLE marked_trips (id INTEGER PRIMARY KEY, name TEXT)")
    con.execute("CREATE TABLE trip_rows (txn_id TEXT PRIMARY KEY, trip_id INTEGER NOT NULL)")
    con.commit(); con.close()
    st = Store(db)
    ingest(st, IngestResult([tx("2026-10-02", "Soda La Casita", 18.40, "Dining")], "card"))
    [row] = st.all_transactions()
    st.write_categories({row.fingerprint: ("Travel", "trip")})
    again = Store(db)
    [row] = again.all_transactions()
    assert (row.category, row.category_source) == ("Travel", "user")
    with again.conn() as c:
        names = {r[0] if not isinstance(r, dict) else r["name"] for r in c.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'").fetchall()}
    assert not names & {"trips", "marked_trips", "trip_rows"}


@pytest.mark.parametrize("body, words", [
    ({"name": "", "category": "Travel", "start": "2026-10-01", "end": "2026-10-05"}, "name"),
    ({"name": "CR", "category": "Travel", "start": "2026-10-05", "end": "2026-10-01"}, "ends before"),
    ({"name": "CR", "category": "Travel", "start": "2026-01-01", "end": "2026-10-01"}, "three months"),
    ({"name": "CR", "category": "", "start": "2026-10-01", "end": "2026-10-05"}, "spending category"),
])
def test_bad_edits_are_refused(client, body, words):
    r = client.post("/api/bulk-edits", json=body)
    assert r.status_code == 400 and words in r.get_json()["error"]
