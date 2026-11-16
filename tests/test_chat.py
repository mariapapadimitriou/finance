"""Pearl chat (PC-01 to PC-13, note 1340:8893; product owner, 2026-11-15).

The server works out the evidence and the proposals; the iPhone's model only
ranks and explains. The rule these tests hold above all: **nothing changes
until she confirms**. Every /api/chat endpoint only reads, and a proposal
changes the ledger only when the card's tap calls the endpoint it already uses.
"""

from __future__ import annotations

import sqlite3
from datetime import date, timedelta

import pytest

from finance import chat
from finance import pattern_sort as ps
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
# The last whole weekend: always in the past, so "the weekend" means it.
SAT = TODAY - timedelta(days=(TODAY.weekday() - 5) % 7 or 7)
SUN = SAT + timedelta(days=1)


def tx(desc, amount, when, raw=None, account="visa", merchant=None):
    return Transaction(date=when.isoformat() if isinstance(when, date) else when, description=desc,
                       merchant=merchant or desc.title(), amount=amount, account_id=account,
                       account_name="TD Visa", raw={"account_type": "credit", **(raw or {})})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    db = tmp_path / "chat.db"
    app = create_app(str(db))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        c.db = db
        yield c


def add(c, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, rs in by.items():
        ingest(c.st, IngestResult(rs, acct))
    return {t.description: t for t in c.st.all_transactions()}


def weekend(c):
    """Saturday night out (three places Pearl can't name), a Sunday brunch,
    and a gas station the bank wasn't sure of: five open questions."""
    return add(c,
               tx("ZQX LOUNGE", 64.50, SAT), tx("MOLO HALL", 128.00, SAT),
               tx("VELLA HOUSE", 22.00, SAT),
               tx("BRUNCHY", 41.20, SUN),
               tx("PETRO STOP", 58.00, SAT, raw={"issuer_category": "TRANSPORTATION_GAS",
                                                  "category_confidence": "LOW"}))


def dump(c) -> list[str]:
    """Everything in the ledger, row for row."""
    con = sqlite3.connect(str(c.db))
    try:
        return list(con.iterdump())
    finally:
        con.close()


# ── Reading her words ──────────────────────────────────────────────────────

class TestWords:
    def test_categories_from_words_not_merchants(self):
        assert chat.category_from(None, "went out with friends Saturday") == "Dining"
        assert chat.category_from(None, "drinks after work") == "Alcohol & Bars"
        assert chat.category_from(None, "picked up groceries") == "Groceries"
        assert chat.category_from(None, "it was all Coffee") == "Coffee"
        assert chat.category_from(None, "nothing in particular") is None

    def test_a_category_the_model_names_is_made_one_of_pearls(self):
        assert chat.category_from("dining", None) == "Dining"
        assert chat.category_from("Alcohol and Bars", None) == "Alcohol & Bars"
        assert chat.category_from("eating out", None) == "Dining"
        assert chat.category_from("Spaceships", None) is None

    def test_days(self):
        w = chat.window("went out Saturday", SUN)
        assert w["days"] == [SAT.isoformat()] and w["label"] == "Saturday" and w["span"] == "Sat"
        w = chat.window("this weekend", SUN)
        assert w["days"] == [SAT.isoformat(), SUN.isoformat()]
        assert w["label"] == "the weekend" and w["span"] == "Sat–Sun"
        w = chat.window("yesterday", TODAY)
        assert w["days"] == [(TODAY - timedelta(days=1)).isoformat()]

    def test_the_last_seven_days_by_default(self):
        w = chat.window("went out with friends", TODAY)
        assert len(w["days"]) == 7 and w["end"] == TODAY.isoformat()
        assert w["label"] == "the last 7 days"

    def test_days_the_model_gives_win_and_never_the_future(self):
        later = (TODAY + timedelta(days=3)).isoformat()
        w = chat.window("whatever", TODAY, [SAT.isoformat(), later])
        assert w["days"] == [SAT.isoformat()]

    def test_people(self):
        assert chat.people_from("dinner with Jo and Sam", []) == ["Jo", "Sam"]
        assert chat.people_from("went out with friends", []) == []
        assert chat.people_from("drinks with sam", ["Sam Lee"]) == ["Sam Lee"]
        assert chat.people_from("x", ["Sam Lee"], hint=["sam"]) == ["Sam Lee"]

    def test_months(self):
        assert chat.month_from(None, "this month", TODAY) == TODAY.strftime("%Y-%m")
        last = TODAY.replace(day=1) - timedelta(days=1)
        assert chat.month_from(None, "last month", TODAY) == last.strftime("%Y-%m")
        assert chat.month_from("2026-03", None, TODAY) == "2026-03"


# ── Tell Pearl what you did (PC-05, PC-06, PC-10) ──────────────────────────

class TestTell:
    def test_one_proposal_per_transaction_that_fits(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "went out with friends this weekend"}).get_json()
        assert r["category"] == "Dining"
        assert r["open"] == 5
        # The gas station doesn't fit dinner; the other four do, one card each.
        names = [p["txn"]["merchant"] for p in r["proposals"]]
        assert "Petro Stop" not in names and len(names) == 4
        assert all(p["kind"] == "sort" and p["category"] == "Dining" for p in r["proposals"])
        assert len({p["id"] for p in r["proposals"]}) == 4
        assert r["line"] == "A guess for 4 of 5 from the weekend"
        # What was this? opens on the told category.
        assert all(p["item"]["guess"] == "Dining" and p["item"]["key"] == p["key"] for p in r["proposals"])

    def test_only_the_days_she_said(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "brunch on Sunday"}).get_json()
        assert [p["txn"]["merchant"] for p in r["proposals"]] == ["Brunchy"]

    def test_hints_from_the_model(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "you know", "category": "Alcohol & Bars",
                                                "days": [SAT.isoformat()]}).get_json()
        assert r["category"] == "Alcohol & Bars"
        assert {p["txn"]["merchant"] for p in r["proposals"]} == {"Zqx Lounge", "Molo Hall", "Vella House"}

    def test_maybe_split_with_who_she_named(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "dinner with Jo and Sam on Saturday"}).get_json()
        assert r["people"] == ["Jo", "Sam"]
        assert all(p["split_with"] == ["Jo", "Sam"] for p in r["proposals"])

    def test_no_split_suggestion_without_people(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "went out Saturday"}).get_json()
        assert all(p["split_with"] == [] for p in r["proposals"])

    def test_naming_the_place_fits_whatever_its_guess(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "filled up at Petro Stop Saturday",
                                                "category": "Gas & Fuel"}).get_json()
        assert [p["txn"]["merchant"] for p in r["proposals"]] == ["Petro Stop"]

    def test_nothing_matched(self, client):
        # PC-10: only the gas station is waiting, and the cottage isn't gas.
        add(client, tx("PETRO STOP", 58.00, SAT, raw={"issuer_category": "TRANSPORTATION_GAS",
                                                       "category_confidence": "LOW"}))
        r = client.post("/api/chat/tell", json={"text": "went to the cottage on the weekend",
                                                "category": "Lodging"}).get_json()
        assert r["nothing"] is True and r["proposals"] == []
        # TEXT-01: "Nothing from Sat–Sun fits."
        assert r["line"] == "Nothing from Sat\u2013Sun fits."

    def test_the_model_ranks_but_cant_add(self, client):
        rows = weekend(client)
        pick = [rows["ZQX LOUNGE"].fingerprint, rows["PETRO STOP"].fingerprint]
        r = client.post("/api/chat/tell", json={"text": "went out Saturday", "ids": pick}).get_json()
        # The gas station doesn't fit dinner, whatever the model picked.
        assert [p["txn"]["merchant"] for p in r["proposals"]] == ["Zqx Lounge"]

    def test_nothing_waiting(self, client):
        r = client.post("/api/chat/tell", json={"text": "dinner yesterday"}).get_json()
        assert r["nothing"] is True and r["open"] == 0
        assert r["line"].startswith("Nothing from ")

    def test_sorted_and_skipped_ones_are_not_asked(self, client):
        rows = weekend(client)
        client.post(f"/api/transactions/{rows['ZQX LOUNGE'].fingerprint}/mark",
                    json={"case": "spending", "category": "Dining"})
        client.post("/api/review/skip", json={"key": "cat:" + rows["MOLO HALL"].fingerprint})
        r = client.post("/api/chat/tell", json={"text": "went out this weekend"}).get_json()
        names = {p["txn"]["merchant"] for p in r["proposals"]}
        assert "Zqx Lounge" not in names and "Molo Hall" not in names
        assert r["open"] == 3

    def test_needs_words(self, client):
        assert client.post("/api/chat/tell", json={"text": "  "}).status_code == 400


# ── Nothing changes until she confirms ─────────────────────────────────────

class TestNothingChangesUntilSheConfirms:
    def test_every_chat_endpoint_only_reads(self, client):
        weekend(client)
        before = dump(client)
        client.get("/api/chat")
        client.post("/api/chat/tell", json={"text": "dinner with Jo and Sam this weekend"})
        client.post("/api/chat/tell", json={"text": "nothing"})
        client.post("/api/chat/spending", json={"text": "what did I spend eating out this month"})
        client.get("/api/chat/subscriptions")
        client.get("/api/chat/asks")
        client.post("/api/chat/plan", json={"text": "make me a plan for eating out"})
        assert dump(client) == before

    def test_a_proposal_changes_the_ledger_only_through_the_cards_yes(self, client):
        weekend(client)
        r = client.post("/api/chat/tell", json={"text": "went out with friends this weekend"}).get_json()
        first = r["proposals"][0]
        txn = first["txn"]["id"]
        assert client.st.get_transaction(txn).category_source != "user"
        # Skip is no request at all: still in Needs a look (PC-07 "The 2 are in Needs a look").
        again = client.post("/api/chat/tell", json={"text": "went out with friends this weekend"}).get_json()
        assert [p["id"] for p in again["proposals"]] == [p["id"] for p in r["proposals"]]
        # Yes: the existing endpoint the card calls.
        ok = client.post(f"/api/transactions/{txn}/mark",
                         json={"case": "spending", "category": first["category"], "remember": False})
        assert ok.status_code == 200
        t = client.st.get_transaction(txn)
        assert (t.category, t.category_source) == ("Dining", "user")
        after = client.post("/api/chat/tell", json={"text": "went out with friends this weekend"}).get_json()
        assert first["id"] not in {p["id"] for p in after["proposals"]}
        # No rule was saved for the merchant: a told guess is this one only.
        assert not any(first["txn"]["merchant"].lower() in str(k).lower() for k in client.st.overrides())

    def test_what_she_said_is_not_kept(self, client):
        weekend(client)
        client.post("/api/chat/tell", json={"text": "a very particular phrase about Saturday"})
        assert not any("particular phrase" in line for line in dump(client))

    def test_a_plan_changes_only_on_set_it(self, client):
        months(client)
        p = client.post("/api/chat/plan", json={"category": "Dining"}).get_json()
        assert client.get("/api/your-plan").get_json()["rows"] == []
        assert client.st.setting("your_plan") in (None, "")
        # Set it: Your plan's own endpoint, as the chat's executor calls it.
        r = client.put(f"/api/your-plan/rows/{p['category']}", json={"amount": p["amount"], "source": "chat"})
        row = next(x for x in r.get_json()["rows"] if x["category"] == "Dining")
        assert (row["amount"], row["source"]) == (p["amount"], "chat")


# ── Ask about my spending (PC-04), subscriptions, a plan (PC-12) ───────────

def months(c):
    """Three whole months of dining, then this month's."""
    first = TODAY.replace(day=1)
    rows = []
    m = first
    for _ in range(3):
        m = (m.replace(day=1) - timedelta(days=1)).replace(day=10)
        rows += [tx("PAI NORTHERN THAI", 120.0, m, raw={"issuer_category": "FOOD_AND_DRINK"}),
                 tx("SUSHI NAMI", 94.0, m + timedelta(days=2), raw={"issuer_category": "FOOD_AND_DRINK"})]
    rows += [tx("PAI NORTHERN THAI", 120.0, first, raw={"issuer_category": "FOOD_AND_DRINK"}),
             tx("PAI NORTHERN THAI", 64.20, first, raw={"issuer_category": "FOOD_AND_DRINK"},
                account="visa2"),
             tx("SUSHI NAMI", 46.0, first, raw={"issuer_category": "FOOD_AND_DRINK"})]
    return add(c, *rows)


class TestSpending:
    def test_a_category_this_month_against_usual(self, client):
        months(client)
        r = client.post("/api/chat/spending", json={"text": "what did I spend on dining this month"}).get_json()
        assert r["category"] == "Dining" and r["count"] == 3
        assert r["total"] == pytest.approx(230.20)
        assert r["usual"] == pytest.approx(214.0)
        assert r["top"] == {"merchant": "Pai Northern Thai", "amount": 184.2, "count": 2}
        assert r["line"] == ("You spent $230 on Dining in " + r["month_name"]
                             + ", $16 more than usual. Pai Northern Thai was $184 of it, across 2 purchases.")
        assert [row["merchant"] for row in r["rows"]][0] in ("Pai Northern Thai", "Sushi Nami")

    def test_a_place(self, client):
        months(client)
        r = client.post("/api/chat/spending", json={"text": "how much at Sushi Nami this month"}).get_json()
        assert r["merchant"] == "Sushi Nami" and r["category"] is None and r["count"] == 1
        assert r["usual"] is None

    def test_nothing_understood(self, client):
        r = client.post("/api/chat/spending", json={"text": "hello"}).get_json()
        assert r["nothing"] is True


class TestPlan:
    def test_rounded_up_to_ten_and_kept_to_the_nearest_five(self, client):
        months(client)
        p = client.post("/api/chat/plan", json={"text": "Make me a plan for eating out"}).get_json()
        assert p["category"] == "Dining" and p["usual"] == pytest.approx(214.0)
        # $214 → $220, and plans keep the nearest $5, so $220 stays $220
        # (note 1353:11493): not the budgets' 5% steps ($224.70).
        assert p["amount"] == 220 and "pct" not in p
        assert p["current"] is None and p["in_use"] is False
        # The first month began on the 10th, so two whole months count.
        assert p["months"] == 2

    def test_needs_history(self, client):
        p = client.post("/api/chat/plan", json={"category": "Dining"}).get_json()
        assert p["nothing"] is True


class TestSubscriptions:
    def test_recurring_that_isnt_a_bill(self, client):
        first = TODAY.replace(day=1)
        add(client, *[tx("STREAMFLIX", 16.99, (first - timedelta(days=30 * i)).replace(day=3),
                         raw={"issuer_category": "ENTERTAINMENT_TV_AND_MOVIES"}) for i in range(1, 5)])
        r = client.get("/api/chat/subscriptions").get_json()
        assert r["count"] == 1 and r["rows"][0]["merchant"] == "Streamflix"
        assert r["line"].startswith("You have 1 subscription, about $17 a month")


# ── Trips and patterns stay one pending state with Quick sort (PC-08, PC-09) ─

class TestAsks:
    def test_off_until_pearl_sorts_for_you(self, client):
        r = client.get("/api/chat/asks").get_json()
        assert r == {"patterns": [], "trips": []}
        assert client.get("/api/chat").get_json()["suggest"] is False

    def test_same_cards_as_quick_sort_and_one_answer_clears_both(self, client):
        ps.switched_on(client.st)
        joint = [Transaction(date=(TODAY - timedelta(days=14 * i + 3)).isoformat(),
                             description="E-TRANSFER ANA RUIZ", merchant="Ana Ruiz", amount=-400.0,
                             account_id="joint", account_name="Joint", raw={"account_type": "depository"})
                 for i in range(9)]
        add(client, *joint)
        client.st.set_setting("joint_accounts", '["joint"]')
        asks = client.get("/api/chat/asks").get_json()
        review = client.get("/api/review").get_json()
        assert [p["id"] for p in asks["patterns"]] == [p["id"] for p in review["pattern_asks"]]
        assert [t["id"] for t in asks["trips"]] == [t["id"] for t in review["trip_asks"]]
        # 2026-11-15 (speed): GET /api/chat carries the same cards, so the
        # chat opens with one trip to the server.
        start = client.get("/api/chat").get_json()
        assert start["asks"] == asks and start["suggest"] is bool(asks["patterns"] or asks["trips"])
        for p in asks["patterns"]:
            client.post(f"/api/pattern-sort/asks/{p['id']}/skip")
        assert client.get("/api/chat/asks").get_json()["patterns"] == []
        assert client.get("/api/review").get_json()["pattern_asks"] == []

    def test_start(self, client):
        weekend(client)
        r = client.get("/api/chat").get_json()
        assert "Dining" in r["categories"] and "Income" not in r["categories"]
        assert r["today"] == TODAY.isoformat()


class TestSpeed:
    """2026-11-15: the chat was slow on her iPhone. Each chat read says how
    long it took on the server, for the phone's log and the server's."""

    def test_every_chat_read_is_timed(self, client):
        weekend(client)
        for r in (client.get("/api/chat"), client.get("/api/chat/asks"),
                  client.get("/api/chat/subscriptions"),
                  client.post("/api/chat/spending", json={"category": "Dining"}),
                  client.post("/api/chat/tell", json={"text": "out Saturday"})):
            assert r.status_code == 200
            assert r.headers["Server-Timing"].startswith("app;dur=")

    def test_other_reads_are_not(self, client):
        assert "Server-Timing" not in client.get("/api/transactions/list").headers
