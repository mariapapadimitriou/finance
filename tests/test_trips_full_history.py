"""Trips across her whole history (product owner, 2026-11-19): after Start
over with about two years of transactions, Pearl finds every trip, not only
the last four months, one Yes/Skip question each, newest first. Two signals
must still agree: a staycation at home and a month's work stint aren't
trips. Start over and Reset clear trips, skipped dates and Undo's record,
so every past trip can be asked about again."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import pattern_sort as ps
from finance import trips
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
HISTORY = 730                               # about two years
HOME = "Toronto"


def day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def tx(desc, amount, when, category="", city="", account="visa"):
    t = Transaction(date=when, description=desc, merchant=desc.title(), amount=amount, category=category,
                    account_id=account, account_name="TD Visa",
                    raw={"account_type": "credit", "city": city})
    t.currency = "CAD"
    return t


def stay(city, start, merchants):
    """A row a day at each merchant from `start` days ago, one day apart."""
    return [tx(m, 12.0 + 7 * i, day(start - i), city=city) for i, m in enumerate(merchants)]


# Each trip: (start days ago, end days ago). Home spending stops while she's away.
EARLY = (HISTORY - 10, HISTORY - 14)        # her first three weeks of history
LISBON = (548, 544)                         # 18 months ago
MONTREAL_1 = (400, 396)
MONTREAL_2 = (35, 31)                       # a year later, the same places
STAYCATION = (200, 197)                     # at home: not a trip
STINT = (300, 268)                          # a month's work in another city: not a trip
ROAD_1 = (250, 247)                         # a road trip: no flight, hotel or fees
ROAD_2 = (160, 157)                         # the same drive again, the same places
ROAD_PLACES = ["COUNTY CIDER", "BOARDWALK CAFE", "SANDBANKS PARK", "HARVEST KITCHEN"]
MONTREAL_PLACES = ["CAFE OLIMPICO", "SCHWARTZS DELI", "SIMONS", "ST VIATEUR BAGEL", "LA BANQUISE"]


def away_days():
    out = set()
    for a, b in (EARLY, LISBON, MONTREAL_1, MONTREAL_2, STINT, ROAD_1, ROAD_2):
        out.update(range(b, a + 1))
    return out


def history() -> list[Transaction]:
    rows: list[Transaction] = []
    gone = away_days()
    everyday = ["CORNER GROCER", "BALZACS COFFEE", "TTC PRESTO"]
    for n in range(HISTORY, 0, -1):
        if n not in gone:
            rows.append(tx(everyday[n % 3], 9.0 + (n % 17), day(n), city=HOME))
        if n % 30 == 0:
            rows.append(tx("NETFLIX", 18.99, day(n)))     # online: no city, all the time
    # In her first three weeks: everything is new then, so the city and the
    # hotel carry it.
    rows += stay("Vancouver", EARLY[0], ["GRANVILLE MARKET", "JAPADOG", "MEC VANCOUVER", "CACTUS CLUB", "BLUE WATER"])
    rows.append(tx("MARRIOTT VANCOUVER", 612.0, day(EARLY[0]), category="Lodging", city="Vancouver"))
    # 18 months ago, abroad: a flight booked ahead, foreign fees.
    rows += stay("Lisbon", LISBON[0], ["PASTEIS DE BELEM", "TIME OUT MARKET", "A VIDA PORTUGUESA", "CARRIS", "TASCA"])
    rows.append(tx("LUFTHANSA", 1180.0, day(LISBON[0] + 12), category="Travel"))
    rows += [tx("FOREIGN TRANSACTION FEE", 2.10, day(LISBON[0] - 1)),
             tx("FOREIGN TRANSACTION FEE", 1.40, day(LISBON[0] - 3))]
    # Montréal twice, a year apart, the same hotel and places both times.
    for a, _ in (MONTREAL_1, MONTREAL_2):
        rows += stay("Montréal", a, MONTREAL_PLACES)
        rows.append(tx("AIR CANADA", 318.2 + a / 100, day(a + 6), category="Travel"))
        rows.append(tx("HILTON MONTREAL", 420.0 + a / 100, day(a), category="Lodging", city="Montréal"))
    # A road trip twice, by car, staying with friends: nothing booked. The
    # first time the places are new; the second, she's simply gone from home.
    for a, _ in (ROAD_1, ROAD_2):
        rows += [tx(m, 14.0 + 5 * i + a / 1000, day(a - i), city="Picton") for i, m in enumerate(ROAD_PLACES)]
    # A staycation at home: new places and a hotel, all in her own city.
    rows += stay(HOME, STAYCATION[0], ["ALO RESTAURANT", "STEAM WHISTLE", "ROM GIFT SHOP", "CANOE"])
    rows.append(tx("HYATT REGENCY TORONTO", 389.0, day(STAYCATION[0]), category="Lodging", city=HOME))
    # A month's work in Calgary, weekdays, weekends off: a stint, not a trip.
    rows.append(tx("WESTJET", 402.0, day(STINT[0] + 2), category="Travel"))
    rows.append(tx("WESTIN CALGARY", 2400.0, day(STINT[0]), category="Lodging", city="Calgary"))
    for n in range(STINT[0], STINT[1] - 1, -1):
        if date.fromisoformat(day(n)).weekday() < 5:
            rows.append(tx(f"CALGARY LUNCH {n % 9}", 15.0 + n % 5, day(n), city="Calgary"))
            rows.append(tx("CALGARY TRANSIT", 3.6 + n / 1000, day(n), city="Calgary"))
    return rows


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "history.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(c):
    ingest(c.st, IngestResult(history(), "visa"))


def asks(c):
    return trips.candidates(c.st, c.st.all_transactions(), TODAY.isoformat())


def span(trip):
    return (day(trip[0]), day(trip[1]))


EXPECTED = [MONTREAL_2, ROAD_2, ROAD_1, MONTREAL_1, LISBON, EARLY]      # newest first


class TestWholeHistory:
    def test_every_trip_once_newest_first(self, client):
        load(client)
        found = asks(client)
        assert [(a["start"], a["end"]) for a in found] == [span(t) for t in EXPECTED]
        assert [a["place"] for a in found] == ["Montréal", "Picton", "Picton", "Montréal", "Lisbon", "Vancouver"]

    def test_eighteen_months_ago(self, client):
        load(client)
        lisbon = next(a for a in asks(client) if a["place"] == "Lisbon")
        assert lisbon["flight"] and lisbon["fees"]
        assert lisbon["count"] == 8          # five places, the flight, two fees

    def test_first_three_weeks_carried_by_city_and_hotel(self, client):
        load(client)
        early = next(a for a in asks(client) if a["place"] == "Vancouver")
        assert early["hotel"] and not early["flight"]

    def test_second_visit_same_places_is_still_a_trip(self, client):
        load(client)
        first, second = [a for a in asks(client) if a["place"] == "Montréal"][::-1]
        assert first["start"] == day(MONTREAL_1[0]) and second["start"] == day(MONTREAL_2[0])
        assert second["count"] == first["count"] == 7      # five places, flight, hotel

    def test_a_road_trip_again_is_found_by_her_absence(self, client):
        """The second drive: the same places, nothing booked. Away, and
        nothing spent at home those days, where she spends every day."""
        load(client)
        second = next(a for a in asks(client) if a["start"] == day(ROAD_2[0]))
        assert second["place"] == "Picton" and not (second["flight"] or second["hotel"] or second["fees"])

    def test_staycation_and_work_stint_are_not_trips(self, client):
        load(client)
        for a in asks(client):
            assert not trips._overlaps((a["start"], a["end"]), span(STAYCATION))
            assert not trips._overlaps((a["start"], a["end"]), span(STINT))

    def test_one_signal_is_still_not_enough(self, client):
        """Away for days with nothing else (no flight, hotel, fees or new
        places) isn't asked about."""
        load(client)
        rows = stay("Ottawa", 120, ["CORNER GROCER", "BALZACS COFFEE", "TTC PRESTO", "CORNER GROCER"])
        for i, t in enumerate(rows):
            t.amount += 0.31 * (i + 1)
        ingest(client.st, IngestResult(rows, "visa"))
        assert all(a["place"] != "Ottawa" for a in asks(client))


class TestQuestions:
    def test_each_trip_is_its_own_question_in_quick_sort(self, client):
        load(client)
        ps.switched_on(client.st)
        review = client.get("/api/review").get_json()
        assert len(review["trip_asks"]) == len(EXPECTED)
        keys = client.get("/api/quick-sort?all=1").get_json()["keys"]
        trip_keys = [k for k in keys if k.startswith("trip:")]
        assert trip_keys == [a["key"] for a in review["trip_asks"]]
        # Home's count leaves them out (TEST-35); chat has the same four.
        listed = review["count"] - len(review["trip_asks"]) - len(review["pattern_asks"])
        assert client.get("/api/home").get_json()["review_count"] == listed
        assert [t["id"] for t in client.get("/api/chat/asks").get_json()["trips"]] == \
               [a["id"] for a in review["trip_asks"]]

    def test_worth_a_look_only_has_the_recent_one(self, client):
        load(client)
        ps.switched_on(client.st)
        items = client.get("/api/worth-a-look").get_json()["items"]
        trip_items = [i for i in items if i["kind"] == "trip"]
        assert [i["target"]["id"] for i in trip_items] == [f"{day(MONTREAL_2[0])}:{day(MONTREAL_2[1])}"]

    def test_nothing_groups_without_her_yes(self, client):
        load(client)
        ps.switched_on(client.st)
        client.get("/api/review")
        client.get("/api/chat/asks")
        assert trips.all_trips(client.st) == {}


class TestStartOver:
    def answer_all(self, c):
        for i, a in enumerate(c.get("/api/trips/asks").get_json()["asks"]):
            verb = "yes" if i % 2 == 0 else "skip"
            assert c.post(f"/api/trips/asks/{a['id']}/{verb}").status_code == 200
        made = list(trips.all_trips(c.st))
        assert made
        c.delete(f"/api/trips/{made[0]}")              # "Not a trip": kept for Undo
        assert asks(c) == []

    @pytest.mark.parametrize("how", ["start_over", "reset"])
    def test_every_trip_is_found_again(self, client, how):
        load(client)
        self.answer_all(client)
        if how == "start_over":
            client.st.start_over()
        else:
            client.st.reset()
        for key in (trips.TRIPS_KEY, trips.SKIPPED_KEY, trips.ENDED_KEY):
            assert client.st.setting(key) in (None, "")
        load(client)                                  # the sync brings the same history back
        assert [(a["start"], a["end"]) for a in asks(client)] == [span(t) for t in EXPECTED]


class TestGoneFromHomeNeedsASteadyHome:
    def test_quiet_at_home_is_not_gone(self, client):
        """She rarely spends at home (every fifth day): a few days without a
        home row says nothing, so away alone isn't asked about."""
        rows = [tx("CORNER GROCER", 30.0 + n % 7, day(n), city=HOME) for n in range(300, 0, -5)]
        for a in (250, 160):
            rows += [tx(m, 14.0 + 5 * i + a / 1000, day(a - i), city="Picton") for i, m in enumerate(ROAD_PLACES)]
        ingest(client.st, IngestResult(rows, "visa"))
        assert [a["start"] for a in asks(client)] == [day(250)]     # only the first, by its new places


class TestHistoryStillComingIn:
    """After Start over (or a new link), Plaid can send a recent slice first;
    trips and new subscriptions wait until every bank's history is in."""

    def sync(self, c, monkeypatch, status, more=False):
        from finance import plaid_link

        class Plaid:
            calls = []

            def transactions_sync(self, req):
                Plaid.calls.append(req.to_dict())
                return type("R", (), {"to_dict": lambda s: {
                    "accounts": [], "added": [], "modified": [], "removed": [], "has_more": more,
                    "next_cursor": "c1", "transactions_update_status": status}})()

            def accounts_get(self, req):
                return type("R", (), {"to_dict": lambda s: {"accounts": []}})()

        monkeypatch.setattr(plaid_link, "_client", lambda: Plaid())
        monkeypatch.setattr(plaid_link, "_bank_logo", lambda *a: "")
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        out = plaid_link.sync_all(c.st)
        assert not out["errors"], out
        return Plaid.calls

    def test_trips_wait_for_the_whole_history(self, client, monkeypatch):
        from finance import secrets_box
        monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
        client.st.add_plaid_item("item-1", "tok", "TD")
        load(client)
        assert asks(client)
        client.st.start_over()
        assert client.st.plaid_history_pending() == ["item-1"]
        load(client)                                        # rows arrive...
        calls = self.sync(client, monkeypatch, "INITIAL_UPDATE_COMPLETE")
        assert calls[0]["count"] == 500
        assert asks(client) == []                           # ...but only a slice, Plaid says
        self.sync(client, monkeypatch, "HISTORICAL_UPDATE_COMPLETE", more=True)
        assert asks(client) == []                           # more pages to come
        self.sync(client, monkeypatch, "HISTORICAL_UPDATE_COMPLETE")
        assert client.st.plaid_history_ready()
        assert [(a["start"], a["end"]) for a in asks(client)] == [span(t) for t in EXPECTED]

    def test_a_new_link_waits_too(self, client, monkeypatch):
        from finance import plaid_link, secrets_box
        monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")

        class Plaid:
            def item_public_token_exchange(self, req):
                return type("R", (), {"to_dict": lambda s: {"item_id": "item-2", "access_token": "tok"}})()

        monkeypatch.setattr(plaid_link, "_client", lambda: Plaid())
        plaid_link.exchange_public_token(client.st, "public-x", "RBC")
        assert not client.st.plaid_history_ready()
        load(client)
        assert asks(client) == []


class TestPatternSortAfterStartOver:
    def test_its_answers_go_and_the_baseline_waits_for_the_history(self, client, monkeypatch):
        from finance import secrets_box
        monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
        st = client.st
        st.add_plaid_item("item-1", "tok", "TD")
        load(client)
        ps.switched_on(st)
        for key in ("pattern_sort_log", "pattern_sort_state", "pattern_sort_never", "reimbursement_waited"):
            st.set_setting(key, '["x"]' if key == "pattern_sort_never" else '{"x": 1}')
        st.start_over()
        for key in ("pattern_sort_log", "pattern_sort_state", "pattern_sort_never", "reimbursement_waited"):
            assert st.setting(key) in (None, ""), key
        assert ps.is_on(st)                                   # the switch is hers: it stays
        load(client)
        assert ps.run(st, TODAY.isoformat()) == []
        assert ps._json(st, ps.BASELINE_KEY, {}).get("resync")    # history not in yet
        st.set_plaid_history_pending("item-1", False)
        ps.run(st, TODAY.isoformat())
        base = ps._json(st, ps.BASELINE_KEY, {})
        assert not base.get("resync")
        assert set(base["known"]) == {t.fingerprint for t in st.all_transactions()}
