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


def test_the_preview_ticks_only_what_she_spent_while_away(client):
    p = preview(client)
    ticked = {r["merchant"] for r in p["rows"] if r["ticked"]}
    assert ticked == {"Soda La Casita", "Cafe Monteverde", "Hotel Belmar", "Uber"}
    why = {r["merchant"]: r["why_not"] for r in p["rows"] if not r["ticked"]}
    assert why["Parkside Properties"] == "A regular bill or subscription"
    assert why["Netflix"] == "A regular bill or subscription"
    assert why["Northwind Ltd"] == "Money in"
    assert why["TD Visa Payment"] in ("Money in", "Not spending")
    assert p["total"] == round(18.40 + 4.80 + 410.0 + 23.10, 2)


def test_saving_moves_the_ticked_rows_to_travel_and_names_the_trip(client):
    ids = [r["id"] for r in preview(client)["rows"] if r["ticked"]]
    r = client.post("/api/trips", json={"name": "Costa Rica", "start": "2026-10-01",
                                        "end": "2026-10-05", "ids": ids})
    assert r.status_code == 200
    trip = r.get_json()["trip"]
    assert trip["name"] == "Costa Rica" and trip["count"] == 4 and trip["total"] == 456.3
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Travel"
    assert rows["Soda La Casita"].category_source == "trip"
    assert rows["Parkside Properties"].category == "Rent & Housing"
    listed = client.get("/api/transactions/list", query_string={"month": "2026-10"}).get_json()
    soda = next(t for t in listed["transactions"] if t["merchant"] == "Soda La Casita")
    assert soda["note"] == "Costa Rica trip" and soda["trip"] == "Costa Rica"


def test_unticking_and_removing_put_rows_back(client):
    ids = [r["id"] for r in preview(client)["rows"] if r["ticked"]]
    trip = client.post("/api/trips", json={"name": "CR", "start": "2026-10-01",
                                           "end": "2026-10-05", "ids": ids}).get_json()["trip"]
    uber = by_merchant(client)["Uber"].fingerprint
    client.put(f"/api/trips/{trip['id']}", json={"name": "CR", "start": "2026-10-01",
                                                 "end": "2026-10-05",
                                                 "ids": [i for i in ids if i != uber]})
    assert by_merchant(client)["Uber"].category == "Transport"
    assert client.delete(f"/api/trips/{trip['id']}").get_json()["put_back"] == 3
    rows = by_merchant(client)
    assert rows["Soda La Casita"].category == "Dining" and rows["Hotel Belmar"].category == "Lodging"
    assert client.get("/api/trips").get_json()["trips"] == []


def test_her_own_category_is_never_overwritten(client):
    soda = by_merchant(client)["Soda La Casita"].fingerprint
    client.st.set_transaction_category(soda, "Gifts")
    p = preview(client)
    row = next(r for r in p["rows"] if r["id"] == soda)
    assert row["ticked"] is False and row["why_not"] == "You sorted it yourself"
    client.post("/api/trips", json={"name": "CR", "start": "2026-10-01", "end": "2026-10-05",
                                    "ids": [soda]})
    assert by_merchant(client)["Soda La Casita"].category == "Gifts"


def test_a_charge_that_posts_later_joins_the_trip(client):
    ids = [r["id"] for r in preview(client)["rows"] if r["ticked"]]
    client.post("/api/trips", json={"name": "CR", "start": "2026-10-01", "end": "2026-10-05",
                                    "ids": ids})
    ingest(client.st, IngestResult([tx("2026-10-04", "Selvatura Park", 65.0, "Entertainment")],
                                   "card"))
    assert by_merchant(client)["Selvatura Park"].category == "Travel"
    trip = client.get("/api/trips").get_json()["trips"][0]
    assert trip["count"] == 5


def test_trips_survive_reopening_the_ledger(client):
    """The cleanup for the old Trips tab mustn't undo a trip she marked."""
    from finance.store import Store
    ids = [r["id"] for r in preview(client)["rows"] if r["ticked"]]
    client.post("/api/trips", json={"name": "CR", "start": "2026-10-01", "end": "2026-10-05",
                                    "ids": ids})
    again = Store(client.st.path)
    soda = next(t for t in again.all_transactions() if t.merchant == "Soda La Casita")
    assert soda.category == "Travel"


@pytest.mark.parametrize("body, words", [
    ({"name": "", "start": "2026-10-01", "end": "2026-10-05", "ids": []}, "name"),
    ({"name": "CR", "start": "2026-10-05", "end": "2026-10-01", "ids": []}, "ends before"),
    ({"name": "CR", "start": "2026-01-01", "end": "2026-10-01", "ids": []}, "three months"),
])
def test_bad_trips_are_refused(client, body, words):
    r = client.post("/api/trips", json=body)
    assert r.status_code == 400 and words in r.get_json()["error"]
