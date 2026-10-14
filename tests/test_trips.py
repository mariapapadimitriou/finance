"""Trips (THL-174): mark a date range and its spending becomes Travel."""

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
    # Rent and Netflix recur, so they're bills, not trip spending.
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
    app = create_app(str(tmp_path / "trips.db"))
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


def preview(c, start="2026-10-01", end="2026-10-05", **kw):
    return c.post("/api/trips/preview", json={"start": start, "end": end, **kw}).get_json()


def save(c, name="Costa Rica", start="2026-10-01", end="2026-10-05", trip_id=None):
    body = {"name": name, "start": start, "end": end}
    if trip_id:
        return c.put(f"/api/trips/{trip_id}", json=body)
    return c.post("/api/trips", json=body)


def test_the_preview_says_what_moves_and_what_stays(client):
    p = preview(client)
    # Every purchase in the dates, rent and Netflix included (2026-10-14).
    assert p["count"] == 6
    assert p["total"] == round(2000 + 16.49 + 18.40 + 4.80 + 410.0 + 23.10, 2)
    assert [c["category"] for c in p["categories"]] == [
        "Rent & Housing", "Lodging", "Transport", "Dining", "Subscriptions", "Coffee"]
    assert p["staying"] == {"money_in": 2}                # pay, and the card payment
    assert p["staying_count"] == 2
    assert "rows" not in p                                   # nothing to tick


def test_saving_moves_every_purchase_and_leaves_money_in(client):
    r = save(client)
    assert r.status_code == 200
    trip = r.get_json()["trip"]
    assert trip["name"] == "Costa Rica" and trip["count"] == 6 and trip["total"] == 2472.79
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Travel"
    assert rows["Soda La Casita"].category_source == "trip"
    assert rows["Parkside Properties"].category == "Travel"
    assert rows["Netflix"].category == "Travel"
    assert rows["TD Visa Payment"].category == "Transfers"
    assert rows["Northwind Ltd"].category == "Income"
    assert rows["Loblaws"].category == "Groceries"            # after the trip
    listed = client.get("/api/transactions/list", query_string={"month": "2026-10"}).get_json()
    soda = next(t for t in listed["transactions"] if t["merchant"] == "Soda La Casita")
    assert soda["note"] == "Costa Rica trip" and soda["trip"] == "Costa Rica"


def test_the_preview_of_a_saved_trip_still_names_the_categories(client):
    trip = save(client).get_json()["trip"]
    p = preview(client, trip_id=trip["id"])
    assert p["count"] == 6
    assert "Travel" not in [c["category"] for c in p["categories"]]


def test_changing_the_dates_and_removing_put_rows_back(client):
    trip = save(client).get_json()["trip"]
    save(client, end="2026-10-04", trip_id=trip["id"])        # Uber was on the 5th
    assert by_merchant(client)["Uber"].category == "Transport"
    assert by_merchant(client)["Hotel Belmar"].category == "Travel"
    assert client.delete(f"/api/trips/{trip['id']}").get_json()["put_back"] == 5
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Dining" and rows["Hotel Belmar"].category == "Lodging"
    assert client.get("/api/trips").get_json()["trips"] == []


def test_bills_in_the_dates_are_travel_too(client):
    ingest(client.st, IngestResult([tx("2026-10-03", "Rogers", 85.0, "Phone & Internet")], "card"))
    save(client)
    assert by_merchant(client)["Rogers"].category == "Travel"


def test_what_the_bank_already_called_travel_joins_the_trip(client):
    ingest(client.st, IngestResult([tx("2026-10-02", "Aegean Airlines", 240.0, "Travel")], "card"))
    flight = by_merchant(client)["Aegean Airlines"].fingerprint
    client.st.set_categories({flight: ("Travel", "plaid")})
    p = preview(client)
    assert p["count"] == 7 and "transfer" not in p["staying"]
    trip = save(client).get_json()["trip"]
    assert trip["count"] == 7
    client.delete(f"/api/trips/{trip['id']}")
    assert by_merchant(client)["Aegean Airlines"].category == "Travel"


def test_the_preview_says_when_there_is_nothing_in_the_dates(client):
    p = preview(client, start="2026-06-01", end="2026-06-10")
    assert p["count"] == 0 and p["in_dates"] == 0
    assert preview(client)["in_dates"] == 8


def test_spending_she_sorted_herself_moves_and_comes_back(client):
    """Dining she confirmed is still the trip; removing it gives her Dining back."""
    soda = by_merchant(client)["Soda La Casita"].fingerprint
    client.st.set_transaction_category(soda, "Gifts")
    assert preview(client)["count"] == 6
    trip = save(client).get_json()["trip"]
    assert by_merchant(client)["Soda La Casita"].category == "Travel"
    client.delete(f"/api/trips/{trip['id']}")
    row = by_merchant(client)["Soda La Casita"]
    assert (row.category, row.category_source) == ("Gifts", "user")


def test_a_trip_row_she_resorts_afterwards_keeps_her_choice(client):
    trip = save(client).get_json()["trip"]
    soda = by_merchant(client)["Soda La Casita"].fingerprint
    client.st.set_transaction_category(soda, "Gifts")
    assert preview(client, trip_id=trip["id"])["staying"].get("yours") == 1
    save(client, trip_id=trip["id"])
    assert by_merchant(client)["Soda La Casita"].category == "Gifts"


def test_rows_that_are_not_hers_are_not_looked_at(client):
    """Left out, or another joint member's: not in the trip, not in the counts."""
    uber = by_merchant(client)["Uber"].fingerprint
    client.st.exclude(uber, "manual")
    p = preview(client)
    assert p["count"] == 5 and p["in_dates"] == 7 and "excluded" not in p["staying"]
    save(client)
    assert by_merchant(client)["Uber"].category == "Transport"


def test_a_charge_that_posts_later_joins_the_trip(client):
    save(client)
    ingest(client.st, IngestResult([tx("2026-10-04", "Selvatura Park", 65.0, "Entertainment")],
                                   "card"))
    assert by_merchant(client)["Selvatura Park"].category == "Travel"
    trip = client.get("/api/trips").get_json()["trips"][0]
    assert trip["count"] == 7


def test_trips_survive_reopening_the_ledger(client):
    """The cleanup for the old Trips tab mustn't undo a trip she marked."""
    from finance.store import Store
    save(client)
    again = Store(client.st.path)
    soda = next(t for t in again.all_transactions() if t.merchant == "Soda La Casita")
    assert soda.category == "Travel"


@pytest.mark.parametrize("body, words", [
    ({"name": "", "start": "2026-10-01", "end": "2026-10-05"}, "name"),
    ({"name": "CR", "start": "2026-10-05", "end": "2026-10-01"}, "ends before"),
    ({"name": "CR", "start": "2026-01-01", "end": "2026-10-01"}, "three months"),
])
def test_bad_trips_are_refused(client, body, words):
    r = client.post("/api/trips", json=body)
    assert r.status_code == 400 and words in r.get_json()["error"]


def test_places_she_goes_often_are_still_trip_spending(client):
    """Regulars, fees, bills: anything bought in the dates is Travel."""
    regulars = []
    for m in ("07", "08", "09"):
        for d in ("04", "11", "18", "25"):
            regulars.append(tx(f"2026-{m}-{d}", "Uber", 21.0, "Transport"))
    regulars.append(tx("2026-10-04", "Uber", 21.0, "Transport"))
    regulars.append(tx("2026-10-03", "Foreign transaction fee", 4.10, "Fees & Interest"))
    regulars.append(tx("2026-10-03", "Interest charge", 12.00, "Fees & Interest"))
    ingest(client.st, IngestResult(regulars, "card"))
    client.st.set_categories({t.fingerprint: (t.category or "Transport", "plaid")
                              for t in client.st.all_transactions()
                              if t.merchant in ("Uber", "Foreign transaction fee", "Interest charge")})
    save(client)
    october = [t for t in client.st.all_transactions() if t.date.startswith("2026-10")]
    by = {(t.merchant, t.date): t.category for t in october}
    assert by[("Uber", "2026-10-04")] == "Travel"
    assert by[("Foreign transaction fee", "2026-10-03")] == "Travel"
    assert by[("Interest charge", "2026-10-03")] == "Travel"
    assert by[("Netflix", "2026-10-03")] == "Travel"
    assert by[("Northwind Ltd", "2026-10-01")] == "Income"
