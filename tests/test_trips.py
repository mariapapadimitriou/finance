"""Trips (product owner, 2026-11-15; note 1329:69536): Pearl asks only when
two signals agree; Yes or Make a trip groups rows with a tag of the same
name; rename and remove keep trip and tag in step; totals per currency."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import pattern_sort as ps
from finance import trips
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def tx(desc, amount, when, category="", city="", currency="CAD", account="visa"):
    t = Transaction(date=when, description=desc, merchant=desc.title(), amount=amount, category=category,
                    account_id=account, account_name="TD Visa",
                    raw={"account_type": "credit", "city": city})
    t.currency = currency
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "trips.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def add(c, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, rs in by.items():
        ingest(c.st, IngestResult(rs, acct))
    return {t.description: t for t in c.st.all_transactions()}


def home(c):
    """Months of everyday spending at home, so new places stand out."""
    add(c, *[tx("CORNER GROCER", 40.0 + i, day(200 - i * 5), city="Toronto") for i in range(30)])


def away(c, flight=True, fees=False, city="Montréal", start=40):
    rows = [tx("CAFE OLIMPICO", 6.5, day(start), city=city), tx("SCHWARTZS DELI", 46.8, day(start - 1), city=city),
            tx("SIMONS", 142.0, day(start - 2), city=city), tx("STM METRO", 17.5, day(start - 2), city=city),
            tx("ST VIATEUR BAGEL", 9.0, day(start - 3), city=city)]
    if flight:
        rows.append(tx("AIR CANADA", 318.2, day(start + 1), category="Travel"))
    if fees:
        rows.append(tx("FOREIGN TRANSACTION FEE", 14.62, day(start - 3)))
    return add(c, *rows)


class TestAsking:
    def test_new_places_and_a_flight_are_asked_about(self, client):
        home(client)
        away(client, city="")
        [ask] = trips.candidates(client.st, client.st.all_transactions(), TODAY.isoformat())
        assert ask["flight"] and not ask["fees"] and ask["place"] is None and ask["name"] == ""
        assert ask["count"] == 6 and ask["days"] == 4
        assert ask["totals"] == [{"currency": "CAD", "amount": 540.0}]

    def test_one_signal_is_not_enough(self, client):
        home(client)
        away(client, flight=False, city="")
        assert trips.candidates(client.st, client.st.all_transactions(), TODAY.isoformat()) == []

    def test_fees_or_a_city_count_as_the_second_signal(self, client):
        home(client)
        away(client, flight=False, fees=True, city="")
        [ask] = trips.candidates(client.st, client.st.all_transactions(), TODAY.isoformat())
        assert ask["fees"]

    def test_the_city_names_it(self, client):
        home(client)
        away(client, flight=False)
        [ask] = trips.candidates(client.st, client.st.all_transactions(), TODAY.isoformat())
        assert ask["place"] == "Montréal" and ask["name"] == "Trip to Montréal"

    def test_the_start_of_her_history_is_not_a_trip(self, client):
        away(client)                        # everything is new on day one
        assert trips.candidates(client.st, client.st.all_transactions(), TODAY.isoformat()) == []

    def test_asked_in_quick_sort_only_with_the_switch_on(self, client):
        home(client)
        away(client)
        assert client.get("/api/review").get_json()["trip_asks"] == []
        ps.switched_on(client.st)
        review = client.get("/api/review").get_json()
        [ask] = review["trip_asks"]
        assert ask["key"] in client.get("/api/quick-sort?all=1").get_json()["keys"]

    def test_yes_makes_the_trip_and_its_tag(self, client):
        home(client)
        rows = away(client)
        [ask] = client.get("/api/trips/asks").get_json()["asks"]
        r = client.post(f"/api/trips/asks/{ask['id']}/yes").get_json()
        trip = r["trip"]
        assert trip["name"] == "Trip to Montréal" and trip["by"] == "pearl" and trip["count"] == 6
        tags = client.st.tags()
        assert all("Trip to Montréal" in tags.get(i, []) for i in trip["ids"])
        assert client.get("/api/trips/asks").get_json()["asks"] == []
        page = client.get(f"/api/trips/{trip['id']}").get_json()
        assert len(page["rows"]) == 6 and page["rows"][0]["trip"]["name"] == "Trip to Montréal"
        detail = client.get(f"/api/transactions/{rows['SIMONS'].fingerprint}").get_json()
        assert detail["trip"]["id"] == trip["id"]

    def test_skip_never_asks_about_those_dates_again(self, client):
        home(client)
        away(client)
        [ask] = client.get("/api/trips/asks").get_json()["asks"]
        assert client.post(f"/api/trips/asks/{ask['id']}/skip").status_code == 200
        assert client.get("/api/trips/asks").get_json()["asks"] == []
        assert client.post(f"/api/trips/asks/{ask['id']}/skip").status_code == 404


class TestMakingAndChanging:
    def make(self, c, name="Cottage weekend"):
        home(c)
        rows = away(c, flight=False, city="")
        ids = [rows["SIMONS"].fingerprint, rows["STM METRO"].fingerprint]
        r = c.post("/api/trips", json={"ids": ids, "name": name})
        assert r.status_code == 200, r.get_json()
        return r.get_json()["trip"], rows

    def test_make_a_trip_yourself(self, client):
        trip, _ = self.make(client)
        assert trip["by"] == "you" and trip["count"] == 2 and trip["month_names"]
        assert client.post("/api/trips", json={"ids": trip["ids"], "name": "Again"}).status_code == 400
        assert client.post("/api/trips", json={"ids": [], "name": "x"}).status_code == 400

    def test_rename_renames_its_tag(self, client):
        trip, _ = self.make(client)
        r = client.put(f"/api/trips/{trip['id']}", json={"name": "Weekend away"}).get_json()
        assert r["trip"]["name"] == "Weekend away"
        tags = {t for ts in client.st.tags().values() for t in ts}
        assert "Weekend away" in tags and "Cottage weekend" not in tags

    def test_renaming_the_tag_renames_the_trip(self, client):
        trip, _ = self.make(client)
        client.put("/api/tags/Cottage weekend", json={"name": "Lake trip"})
        assert trips.all_trips(client.st)[trip["id"]]["name"] == "Lake trip"

    def test_removing_the_tag_ends_the_trip_and_keeps_the_rows(self, client):
        trip, rows = self.make(client)
        listed = client.get("/api/tags").get_json()["tags"]
        assert next(g for g in listed if g["tag"] == "Cottage weekend")["trip"] == trip["id"]
        assert client.put("/api/tags/Cottage weekend", json={"name": None}).status_code == 200
        assert trips.all_trips(client.st) == {}
        assert client.st.get_transaction(rows["SIMONS"].fingerprint).amount == 142.0
        assert not any("Cottage weekend" in ts for ts in client.st.tags().values())

    def test_it_wasnt_a_trip(self, client):
        trip, _ = self.make(client)
        assert client.delete(f"/api/trips/{trip['id']}").get_json() == {"ok": True, "count": 2}
        assert client.get(f"/api/trips/{trip['id']}").status_code == 404

    def test_add_and_remove(self, client):
        trip, rows = self.make(client)
        r = client.put(f"/api/trips/{trip['id']}", json={"add": [rows["CAFE OLIMPICO"].fingerprint],
                                                          "remove": [rows["SIMONS"].fingerprint]}).get_json()
        assert r["trip"]["count"] == 2
        assert "Cottage weekend" not in client.st.tags().get(rows["SIMONS"].fingerprint, [])
        r = client.put(f"/api/trips/{trip['id']}", json={"remove": r["trip"]["ids"]}).get_json()
        assert r == {"ok": True, "ended": True}


def test_two_currencies_are_totalled_apart(client):
    """No conversion anywhere: "$1,240 CAD + $310 USD"."""
    home(client)
    rows = add(client, tx("HOTEL A", 300.0, day(30)), tx("DINER B", 40.0, day(29), currency="USD"),
               tx("MUSEUM C", 25.0, day(29), currency="USD"))
    ids = [rows[k].fingerprint for k in ("HOTEL A", "DINER B", "MUSEUM C")]
    trip = client.post("/api/trips", json={"ids": ids, "name": "Boston"}).get_json()["trip"]
    assert trip["totals"] == [{"currency": "CAD", "amount": 300.0}, {"currency": "USD", "amount": 65.0}]
    page = client.get(f"/api/trips/{trip['id']}").get_json()
    assert {r["merchant"]: r["currency"] for r in page["rows"]}["Diner B"] == "USD"


def test_the_calendar_gives_each_trips_days_per_month(client):
    """TR-10: the month view marks a trip's days and spans months honestly."""
    home(client)
    rows = add(client, tx("HOTEL A", 300.0, "2026-03-30"), tx("DINER B", 40.0, "2026-04-02"))
    trip = client.post("/api/trips", json={"ids": [rows["HOTEL A"].fingerprint, rows["DINER B"].fingerprint],
                                           "name": "Easter"}).get_json()["trip"]
    march = client.get("/api/calendar?month=2026-03").get_json()["trips"]
    april = client.get("/api/calendar?month=2026-04").get_json()["trips"]
    assert [t["id"] for t in march] == [trip["id"]] and march[0]["days"] == [30, 31]
    assert april[0]["days"] == [1, 2] and april[0]["start"] == "2026-03-30"
    assert client.get("/api/calendar?month=2026-06").get_json()["trips"] == []
    assert march[0]["totals"] == [{"currency": "CAD", "amount": 340.0}]      # the whole trip
    day = client.get("/api/calendar/day/2026-03-31").get_json()["trips"]
    assert [t["name"] for t in day] == ["Easter"]
    assert client.get("/api/calendar/day/2026-03-28").get_json()["trips"] == []
