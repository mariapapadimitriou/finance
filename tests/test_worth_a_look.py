"""Worth a look on Home (2026-11-18; finance/worth_a_look.py).

At most three items: every Yes question, then heads-ups, then one piece of
good news. Not now is for good for that event; Clear has an Undo; an item
drops off a week after it was first shown. Questions Quick sort also asks
come from the same open question, so answering either place clears both.
"""

from datetime import date, timedelta

import pytest

from finance import pattern_sort as ps, secrets_box
from finance.models import Transaction
from test_plaid_link import KEY

TODAY = date(2026, 11, 18)          # a Wednesday


def tx(day, merchant, amount, category, account="chq", description=None, **kw):
    return Transaction(date=day, description=description or merchant.upper(), merchant=merchant,
                       amount=amount, category=category, account_id=account, **kw)


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "wal.db"))
    app.config.update(TESTING=True)
    clock = {"today": TODAY}
    monkeypatch.setattr(api, "_today_iso", lambda: clock["today"].isoformat())
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.clock = clock
        yield c


def items(c):
    r = c.get("/api/worth-a-look")
    assert r.status_code == 200
    return r.get_json()["items"]


def post(c, action, ids=None, status=200, **kw):
    body = {"action": action, **kw}
    if ids is not None:
        body["ids"] = ids
    r = c.post("/api/worth-a-look", json=body)
    assert r.status_code == status, r.get_json()
    return r.get_json()


def kinds(c):
    return [i["kind"] for i in items(c)]


# ── Ledgers ────────────────────────────────────────────────────────────

def crave(c, since="2026-08-20"):
    """A new streaming charge, every month since `since`."""
    start = date.fromisoformat(since)
    rows = []
    d = start
    while d <= TODAY - timedelta(days=5):
        rows.append(tx(d.isoformat(), "Crave", 19.99, "Streaming", account="visa"))
        d = date(d.year + (d.month // 12), d.month % 12 + 1, d.day)
    c.st.add_transactions(rows)


def netflix(c, confirm=True):
    """Netflix at $15 since June, $17 from October; counted as a bill."""
    rows = [tx(f"2026-{m:02d}-15", "Netflix", 15.00, "Streaming", account="visa") for m in (6, 7, 8, 9)]
    rows += [tx(f"2026-{m:02d}-15", "Netflix", 17.00, "Streaming", account="visa") for m in (10, 11)]
    c.st.add_transactions(rows)
    if confirm:
        r = c.put("/api/income-bills/bills", json={"ticked": {"Netflix": True}})
        assert r.status_code == 200


def bill(c, name, days, amount=80.0, category=None):
    body = {"name": name, "amount": amount, "cadence": "monthly",
            "next": (TODAY + timedelta(days=days)).isoformat()}
    if category:
        body["category"] = category
    r = c.post("/api/income-bills/bills", json=body)
    assert r.status_code == 200, r.get_json()
    return next(b["key"] for b in r.get_json()["bills"] if b["name"] == name)


def piggy(c, name="Japan fund", target=3000, opening=1600):
    r = c.post("/api/piggy", json={"name": name, "target": target, "cadence": "once",
                                   "target_date": "2027-06-01", "opening": opening})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def takeout(c, last=200.0, now=80.0):
    """Takeout by the 18th: `last` in October, `now` in November."""
    c.st.add_transactions([
        tx("2026-09-30", "Corner Store", 5.0, "Groceries"),
        tx("2026-10-10", "DoorDash", last, "Food Delivery", account="visa"),
        tx("2026-11-10", "DoorDash", now, "Food Delivery", account="visa"),
    ])


def duplicate(c):
    a = tx("2026-11-12", "Uber Eats", 32.40, "Food Delivery", account="visa")
    b = tx("2026-11-12", "Uber Eats", 32.40, "Food Delivery", account="chq", description="UBER EATS*X")
    c.st.add_transactions([a, b])
    rows = {t.account_id: t.fingerprint for t in c.st.all_transactions() if t.merchant == "Uber Eats"}
    c.st.add_duplicate(rows["chq"], rows["visa"])
    return rows["chq"]


# ── Empty ──────────────────────────────────────────────────────────────

class TestEmpty:
    def test_nothing_qualifies(self, client):
        assert client.get("/api/worth-a-look").get_json() == {"items": []}

    def test_post_on_nothing_is_still_ok(self, client):
        assert post(client, "seen", ["subscription:Nope"]) == {"ok": True, "items": []}


# ── Each kind ──────────────────────────────────────────────────────────

class TestSubscription:
    def test_a_new_one_asks(self, client):
        crave(client)
        [it] = items(client)
        assert it == {"id": "subscription:Crave", "kind": "subscription", "tier": "yes",
                      "title": "New subscription: Crave", "amount": "$19.99/mo",
                      "icon": "subscription", "tone": "rose", "yes": "Yes", "ack": None, "target": None,
                      "since": TODAY.isoformat()}

    def test_an_old_one_is_not_new(self, client):
        crave(client, since="2026-03-20")
        assert items(client) == []

    def test_answered_in_income_and_bills_it_goes(self, client):
        crave(client)
        client.put("/api/income-bills/bills", json={"ticked": {"Crave": False}})
        assert items(client) == []

    def test_yes_adds_it_to_bills_and_undo_takes_it_back(self, client):
        crave(client)
        r = post(client, "yes", ["subscription:Crave"])
        assert r["ok"] and r["toast"] == "Crave added to subscriptions"
        # Now a bill she counts: it comes out on the 20th.
        assert [i["kind"] for i in r["items"]] == ["bill_due"]
        row = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Crave")
        assert row["counts"] is True
        r = post(client, "undo_yes", ["subscription:Crave"])
        assert r["undone"] == ["subscription:Crave"]
        assert [i["id"] for i in r["items"]] == ["subscription:Crave"]
        assert r["items"][0]["since"] == TODAY.isoformat()
        row = next(b for b in client.get("/api/income-bills").get_json()["bills"] if b["key"] == "Crave")
        assert row["counts"] is None
        assert client.get("/api/income-bills").get_json()["checked"]["bills"] is None


class TestPriceRise:
    def test_a_counted_bill_that_went_up(self, client):
        netflix(client)
        [it] = items(client)
        assert it["id"] == "price_rise:Netflix:1700" and it["kind"] == "price_rise"
        assert (it["tier"], it["tone"], it["icon"]) == ("yes", "rose", "price")
        assert it["title"] == "Netflix went up $2" and it["yes"] == "Update the bill"
        assert it["amount"] is None and it["target"] is None

    def test_not_a_bill_she_counts(self, client):
        netflix(client, confirm=False)
        assert items(client) == []

    def test_yes_updates_the_bill_and_undo_puts_it_back(self, client):
        netflix(client)

        def amount():
            return next(b for b in client.get("/api/income-bills").get_json()["bills"]
                        if b["key"] == "Netflix")["amount"]
        assert amount() == 15.0
        r = post(client, "yes", ["price_rise:Netflix:1700"])
        assert r["toast"] == "Netflix bill updated" and r["items"] == []
        assert amount() == 17.0
        r = post(client, "undo_yes", ["price_rise:Netflix:1700"])
        assert amount() == 15.0 and [i["kind"] for i in r["items"]] == ["price_rise"]

    def test_a_bill_she_added_with_her_own_amount(self, client):
        rows = [tx(f"2026-{m:02d}-03", "Gym Co", 40.00, "Fitness") for m in (8, 9, 10)]
        rows.append(tx("2026-11-03", "Gym Co", 45.00, "Fitness"))
        client.st.add_transactions(rows)
        key = bill(client, "Gym Co", 15, amount=40.0)
        [it] = [i for i in items(client) if i["kind"] == "price_rise"]
        assert it["title"] == "Gym Co went up $5"
        post(client, "yes", [it["id"]])
        assert next(b for b in client.get("/api/income-bills").get_json()["bills"]
                    if b["key"] == key)["amount"] == 45.0


class TestDuplicate:
    def test_an_open_question(self, client):
        copy = duplicate(client)
        [it] = items(client)
        assert it["id"] == f"duplicate:{copy}" and it["title"] == "Double charge at Uber Eats?"
        assert it["target"] == {"screen": "transaction", "id": copy, "name": None, "month": None}
        assert it["yes"] is None and it["tier"] == "yes"

    def test_answered_in_quick_sort_it_goes(self, client):
        copy = duplicate(client)
        assert f"dup:{copy}" in client.get("/api/quick-sort?all=1").get_json()["keys"]
        client.post(f"/api/review/duplicates/{copy}", json={"answer": "same"})
        assert items(client) == []

    def test_not_now_leaves_the_question_in_quick_sort(self, client):
        copy = duplicate(client)
        post(client, "not_now", [f"duplicate:{copy}"])
        assert items(client) == []
        assert f"dup:{copy}" in client.get("/api/quick-sort?all=1").get_json()["keys"]

    def test_yes_is_not_for_this_kind(self, client):
        copy = duplicate(client)
        post(client, "yes", [f"duplicate:{copy}"], status=400)


class TestTrip:
    @pytest.fixture
    def trip_client(self, client):
        """test_trips' person, today."""
        from test_trips import away, home
        client.clock["today"] = date.today()
        home(client)
        away(client, flight=False)
        ps.switched_on(client.st)
        return client

    @staticmethod
    def trips(c):
        return [i for i in items(c) if i["kind"] == "trip"]

    def test_an_open_trip_question(self, trip_client):
        [ask] = trip_client.get("/api/trips/asks").get_json()["asks"]
        assert f"trip:{ask['id']}" in trip_client.get("/api/quick-sort?all=1").get_json()["keys"]
        [it] = self.trips(trip_client)
        assert it["id"] == f"trip:{ask['id']}" and it["tier"] == "yes" and it["yes"] is None
        assert it["title"].startswith("Were you in Montréal ") and it["title"].endswith("?")
        assert it["target"]["screen"] == "trip" and it["target"]["id"] == ask["id"]

    def test_answered_in_quick_sort_it_goes(self, trip_client):
        [ask] = trip_client.get("/api/trips/asks").get_json()["asks"]
        trip_client.post(f"/api/trips/asks/{ask['id']}/skip")
        assert self.trips(trip_client) == []

    def test_off_with_pearl_sorts_for_you(self, client):
        from test_trips import away, home
        client.clock["today"] = date.today()
        home(client)
        away(client, flight=False)
        assert self.trips(client) == []

    def test_the_dates(self):
        from finance.worth_a_look import _span
        assert _span("2026-11-07", "2026-11-10") == "Nov 7–10"
        assert _span("2026-10-30", "2026-11-02") == "Oct 30–Nov 2"


class TestBillDue:
    def test_rent_and_a_bill(self, client):
        bill(client, "Hydro", 1)
        rent = bill(client, "Rent", 2, amount=1800.0, category="Rent & Housing")
        got = items(client)
        assert [i["title"] for i in got] == ["Hydro comes out tomorrow", "Rent comes out Friday"]
        assert got[1]["amount"] == "$1,800.00" and got[1]["icon"] == "home" and got[0]["icon"] == "bill"
        assert (got[1]["tier"], got[1]["tone"]) == ("heads_up", "warn")
        assert got[1]["target"] == {"screen": "bill", "id": rent, "name": "Rent", "month": None}
        assert got[1]["id"] == f"bill_due:{rent}:2026-11-20"

    def test_today(self, client):
        bill(client, "Hydro", 0)
        assert [i["title"] for i in items(client)] == ["Hydro comes out today"]

    def test_not_for_days_yet(self, client):
        bill(client, "Hydro", 4)
        assert items(client) == []


class TestCardDue:
    @pytest.fixture
    def loan(self, client):
        client.st.note_account("loan", name="Student loan", account_type="loan", subtype="student")
        client.st.set_balance("loan", 3000.00, None, None, "CAD", TODAY.isoformat())
        client.st.add_transactions([tx("2026-11-01", "Shop", 10.0, "Shopping")])
        return client

    def test_due_in_a_few_days(self, loan):
        r = loan.put("/api/debts/loan", json={"minimum": 120, "due_day": 22})
        assert r.status_code == 200, r.get_json()
        [it] = items(loan)
        assert it["title"] == "Student loan is due in 4 days" and it["amount"] == "$120.00"
        assert it["target"] == {"screen": "debt", "id": "loan", "name": "Student loan", "month": None}
        assert (it["kind"], it["icon"], it["tone"]) == ("card_due", "card", "warn")

    def test_not_yet(self, loan):
        loan.put("/api/debts/loan", json={"minimum": 120, "due_day": 28})
        assert items(loan) == []

    def test_early_next_month(self, loan):
        loan.put("/api/debts/loan", json={"minimum": 120, "due_day": 2})
        loan.clock["today"] = date(2026, 11, 29)
        [it] = items(loan)
        assert it["title"] == "Student loan is due in 3 days" and it["id"] == "card_due:loan:2026-12-02"


class TestPlanPace:
    def plan(self, c, spent):
        import json
        c.st.add_transactions([tx("2026-11-05", "Pai", spent, "Dining", account="visa")])
        c.st.set_setting("your_plan", json.dumps({
            "rows": [{"category": "Dining", "amount": 100, "source": "you"}],
            "in_use": True, "since": "2026-11-01", "stopped_since": None}))

    def test_parked_with_your_plan(self, client):
        # Your plan is parked with Save: no item opens it, so plan pace waits.
        self.plan(client, 85.0)
        assert items(client) == []

    def test_under_the_line(self, client):
        self.plan(client, 60.0)
        assert items(client) == []


class TestSplits:
    def charge(self, c, day, merchant, amount=100.0):
        c.st.add_transactions([tx(day, merchant, amount, "Dining", account="visa")])
        return next(t.fingerprint for t in c.st.all_transactions() if t.merchant == merchant)

    def split(self, c, tid, body):
        r = c.put(f"/api/transactions/{tid}/split", json=body)
        assert r.status_code == 200, r.get_json()

    def test_not_sure_yet_after_a_week(self, client):
        tid = self.charge(client, "2026-11-08", "Corner Bistro")
        self.split(client, tid, {"mode": "unknown", "people": [{"name": "Sam"}]})
        [it] = items(client)
        assert it["title"] == "Corner Bistro isn’t settled yet" and it["kind"] == "unsettled_split"
        assert it["target"]["screen"] == "transaction" and it["target"]["id"] == tid

    def test_not_sure_yet_this_week(self, client):
        tid = self.charge(client, "2026-11-15", "Corner Bistro")
        self.split(client, tid, {"mode": "unknown", "people": [{"name": "Sam"}]})
        assert items(client) == []

    def test_unpaid_for_three_weeks(self, client):
        tid = self.charge(client, "2026-10-26", "Pizza Nova")
        self.split(client, tid, {"mode": "even", "people": [{"name": "Sam"}]})
        [it] = items(client)
        assert it["title"] == "Sam hasn’t paid back in 3 weeks" and it["kind"] == "unpaid"
        assert it["target"] == {"screen": "owed_person", "id": None, "name": "Sam", "month": None}
        owed = client.get("/api/owed").get_json()
        assert owed["owes_you"][0]["name"] == "Sam"

    def test_unpaid_for_two_weeks_is_not_yet(self, client):
        tid = self.charge(client, "2026-11-04", "Pizza Nova")
        self.split(client, tid, {"mode": "even", "people": [{"name": "Sam"}]})
        assert items(client) == []


class TestNewMonth:
    def setup(self, c):
        c.st.set_setting("home_income", 6800)
        c.st.add_transactions([tx("2026-10-01", "Shop", 10.0, "Shopping")])

    def test_first_days_with_an_allowance(self, client):
        self.setup(client)
        client.clock["today"] = date(2026, 12, 2)
        [it] = items(client)
        assert it["id"] == "new_month:2026-12" and it["title"].startswith("New month · Allowance is $")
        assert it["target"]["screen"] == "allowance", "Home's Allowance, not Your plan (parked)"

    def test_not_after_the_third(self, client):
        self.setup(client)
        client.clock["today"] = date(2026, 12, 4)
        assert items(client) == []


class TestGoodNews:
    def test_piggy_halfway(self, client):
        bank = piggy(client)
        [it] = items(client)
        assert it == {"id": f"piggy_halfway:{bank}", "kind": "piggy_halfway", "tier": "good",
                      "title": "Japan fund is halfway there", "amount": None, "icon": "piggy",
                      "tone": "good", "yes": None, "ack": None,
                      "target": {"screen": "piggy", "id": bank, "name": "Japan fund", "month": None},
                      "since": TODAY.isoformat()}

    def test_piggy_not_halfway(self, client):
        piggy(client, opening=1000)
        assert items(client) == []

    def test_less_on_takeout(self, client):
        takeout(client)
        [it] = items(client)
        assert it["title"] == "$120 less on takeout than October"
        assert it["target"] == {"screen": "category", "id": None, "name": "Food Delivery", "month": "2026-11"}
        assert (it["icon"], it["tone"]) == ("trend_down", "good")

    def test_more_is_not_good_news(self, client):
        takeout(client, last=80.0, now=200.0)
        assert items(client) == []

    def test_a_few_dollars_is_not_news(self, client):
        takeout(client, last=95.0, now=80.0)
        assert items(client) == []


# ── Ranking ────────────────────────────────────────────────────────────

class TestRanking:
    def test_yes_then_heads_up_then_one_good(self, client):
        piggy(client)
        takeout(client)
        bill(client, "Hydro", 1)
        crave(client)
        got = items(client)
        assert [i["kind"] for i in got] == ["subscription", "bill_due", "piggy_halfway"]

    def test_only_one_good_item(self, client):
        piggy(client)
        takeout(client)
        assert [i["kind"] for i in items(client)] == ["piggy_halfway"]

    def test_three_at_most_and_good_news_gives_way(self, client):
        piggy(client)
        crave(client)
        bill(client, "Hydro", 1)
        bill(client, "Phone", 2)
        got = items(client)
        assert [i["kind"] for i in got] == ["subscription", "bill_due", "bill_due"]

    def test_hiding_one_makes_room(self, client):
        piggy(client)
        crave(client)
        bill(client, "Hydro", 1)
        bill(client, "Phone", 2)
        r = post(client, "seen", ["subscription:Crave"])
        assert [i["kind"] for i in r["items"]] == ["bill_due", "bill_due", "piggy_halfway"]


# ── Her answers ────────────────────────────────────────────────────────

class TestAnswers:
    def test_seen(self, client):
        crave(client)
        r = post(client, "seen", id="subscription:Crave")
        assert r == {"ok": True, "items": []}
        assert items(client) == []

    def test_not_now_is_for_good_but_a_new_event_shows(self, client):
        key = bill(client, "Hydro", 1)
        [it] = items(client)
        post(client, "not_now", [it["id"]])
        assert items(client) == []
        client.clock["today"] = TODAY + timedelta(days=1)
        assert items(client) == []
        # Next month's is a new event.
        client.clock["today"] = date(2026, 12, 18)
        [again] = items(client)
        assert again["id"] == f"bill_due:{key}:2026-12-19" != it["id"]

    def test_not_now_on_a_price_rise_until_it_rises_again(self, client):
        netflix(client)
        post(client, "not_now", ["price_rise:Netflix:1700"])
        assert items(client) == []
        client.clock["today"] = date(2026, 12, 17)
        client.st.add_transactions([tx("2026-12-15", "Netflix", 19.00, "Streaming", account="visa")])
        assert [i["id"] for i in items(client)] == ["price_rise:Netflix:1900"]

    def test_clear_and_undo(self, client):
        crave(client)
        bill(client, "Hydro", 1)
        ids = [i["id"] for i in items(client)]
        r = post(client, "clear", ids + ["nothing:here"])
        assert r["ok"] and r["cleared"] == ids and r["items"] == []
        r = post(client, "undo_clear", ids)
        assert [i["id"] for i in r["items"]] == ids

    def test_drops_off_after_seven_days(self, client):
        crave(client)
        assert items(client)[0]["since"] == TODAY.isoformat()
        client.clock["today"] = TODAY + timedelta(days=6)
        [it] = items(client)
        assert it["since"] == TODAY.isoformat()
        client.clock["today"] = TODAY + timedelta(days=7)
        assert items(client) == []

    def test_undo_yes_on_nothing_does_nothing(self, client):
        crave(client)
        r = post(client, "undo_yes", ["subscription:Crave"])
        assert r["undone"] == [] and len(r["items"]) == 1

    def test_unknown_ids_are_ignored(self, client):
        crave(client)
        r = post(client, "yes", ["subscription:Nobody"])
        assert r["ok"] and r["toast"] is None and len(r["items"]) == 1

    @pytest.mark.parametrize("body", [{"action": "delete", "ids": ["x"]}, {"ids": ["x"]},
                                      {"action": "seen", "ids": "x"}, {"action": "seen", "ids": [1]}])
    def test_bad_requests(self, client, body):
        assert client.post("/api/worth-a-look", json=body).status_code == 400


class TestAuth:
    def test_signed_out_is_refused(self, tmp_path, monkeypatch):
        from test_auth import client_for
        from finance import auth
        monkeypatch.delenv(auth.PASSWORD_ENV, raising=False)
        c = client_for(tmp_path, monkeypatch, hosted=True, password="hunter2")
        assert c.get("/api/worth-a-look").status_code == 401
        assert c.post("/api/worth-a-look", json={"action": "seen", "ids": []}).status_code == 401


class TestPaycheque:
    """T-74 (AP-Paycheque): a month with a third paycheque, good news with Got it."""

    def pay(self, c):
        start = date(2026, 7, 10)
        c.st.add_transactions([tx((start + timedelta(days=14 * i)).isoformat(), "Northwind Ltd", -2150.0,
                                  "Income", description="NORTHWIND LTD PAYROLL") for i in range(10)])

    def test_third_paycheque_is_good_news_opening_that_months_income(self, client):
        self.pay(client)
        found = [it for it in items(client) if it["kind"] == "paycheque"]
        assert found, items(client)
        it = found[0]
        assert it["id"] == "paycheque:2026-10" and it["title"] == "3 paycheques in October"
        assert (it["tier"], it["tone"], it["ack"], it["yes"]) == ("good", "good", "Got it", None)
        assert it["target"] == {"screen": "income", "id": None, "name": None, "month": "2026-10"}

    def test_got_it_is_homes_got_it(self, client):
        self.pay(client)
        out = post(client, "got_it", ["paycheque:2026-10"])
        assert not [it for it in out["items"] if it["kind"] == "paycheque"]
        home = client.get("/api/home").get_json()
        assert home["paycheque_note"] is None, "the note doesn't come back anywhere"

    def test_got_it_only_for_a_paycheque(self, client):
        post(client, "got_it", ["subscription:x"], status=400)

    def test_ranks_before_other_good_news(self, client):
        self.pay(client)
        piggy(client)
        goods = [it for it in items(client) if it["tier"] == "good"]
        assert [it["kind"] for it in goods] == ["paycheque"]


def test_no_item_opens_your_plan_or_save(client):
    """Your plan and Save are parked."""
    import finance.worth_a_look as w
    src = open(w.__file__, encoding="utf-8").read()
    assert '"screen": "plan"' not in src
