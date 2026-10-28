"""Recurring transfers (2026-10-27): the same amount out of one account on a
schedule is asked about once, and once confirmed, every transfer matching
its amount and schedule is sorted the same way."""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

sys.path.insert(0, "tests")
from test_what_was_this import load, row  # noqa: E402

from finance import recurring_transfers as rt  # noqa: E402
from finance.review import for_store, ids_in  # noqa: E402

TODAY = date.today()


def month_day(back: int, day: int = 1) -> str:
    m = TODAY.month - back
    y = TODAY.year + (m - 1) // 12
    m = (m - 1) % 12 + 1
    return rt._on(y, m, day).isoformat()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "rt.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def rent(c, months=3, extra=()):
    rows = [row(1500, f"SEND E-TFR ***R{i}k", when=month_day(i)) for i in range(months)]
    return load(c.st, row(-3000, "PAYROLL ACME", category="Income", when=month_day(0, 2)),
                *rows, *extra)


def asked(c):
    return for_store(c.st)["recurring_transfer"]


class TestSpotting:
    def test_same_amount_on_a_schedule_is_asked_once(self, client):
        rent(client, extra=[row(1500, "SEND E-TFR ***X1k", when=month_day(0, 14)),
                            row(42, "SEND E-TFR ***Q1k", when=month_day(0, 5))])
        r = for_store(client.st)
        [it] = r["recurring_transfer"]
        assert it["series"]["cadence"] == "monthly" and it["series"]["count"] == 3
        assert it["reason"].startswith("$1,500.00, every month, around the 1st: 3 times since")
        # The off-schedule $1,500 and the $42 are still asked on their own.
        assert sorted(t["amount"] for t in r["unsorted"]["transfers"]) == [42, 1500]
        assert set(it["asked"]) <= ids_in(r)

    @pytest.mark.parametrize("dates,cadence", [
        (["2026-09-04", "2026-09-18", "2026-10-02"], "biweekly"),
        (["2026-10-02", "2026-10-09", "2026-10-16"], "weekly"),
        (["2026-08-31", "2026-09-30", "2026-10-31"], "monthly"),     # short months
        (["2026-08-30", "2026-10-02"], "monthly"),                   # a weekend either side
    ])
    def test_cadences(self, dates, cadence):
        assert rt.cadence_of([date.fromisoformat(d) for d in dates]) == cadence

    @pytest.mark.parametrize("dates", [
        ["2025-10-01", "2026-10-01"],                 # a year apart
        ["2026-10-01", "2026-10-01"],                 # the same day
        ["2026-09-01", "2026-09-20", "2026-10-25"],   # no schedule
        ["2026-10-09", "2026-10-16"],                 # two a week apart: not yet
    ])
    def test_not_a_schedule(self, dates):
        assert rt.cadence_of([date.fromisoformat(d) for d in dates]) is None

    def test_a_different_amount_is_not_the_same_series(self, client):
        load(client.st, row(1500, "SEND E-TFR ***A1k", when=month_day(1)),
             row(1495, "SEND E-TFR ***A2k", when=month_day(0)))
        assert asked(client) == []


class TestConfirming:
    def test_yes_sorts_them_all_and_new_ones(self, client):
        rent(client)
        [it] = asked(client)
        r = client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["title"] == "Recurring: $1,500.00, every month, around the 1st."
        assert "the 3 here and every one like it" in body["detail"]
        rows = [t for t in client.st.all_transactions() if t.amount == 1500]
        assert {t.category for t in rows} == {"Rent & Housing"}
        assert asked(client) == [] and for_store(client.st)["unsorted"]["count"] == 0
        # Next month's arrives sorted; one for another amount, or off schedule, doesn't.
        load(client.st, row(1500, "SEND E-TFR ***N1k", when=month_day(-1, 2)),
             row(1500, "SEND E-TFR ***N2k", when=month_day(-1, 16)),
             row(1600, "SEND E-TFR ***N3k", when=month_day(-1, 1)))
        by = {t.description: t.category for t in client.st.all_transactions()}
        assert by["SEND E-TFR ***N1k"] == "Rent & Housing"
        assert by["SEND E-TFR ***N2k"] != "Rent & Housing"
        assert by["SEND E-TFR ***N3k"] != "Rent & Housing"

    def test_undo(self, client):
        rent(client)
        [it] = asked(client)
        body = client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "saved"}).get_json()
        assert {t.category for t in client.st.all_transactions() if t.amount == 1500} == {"Saved"}
        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        assert client.st.recurring_transfers() == []
        assert [x["key"] for x in asked(client)] == [it["key"]]

    def test_no_asks_each_one_again(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/review/dismiss", json={"key": it["key"]})
        r = for_store(client.st)
        assert r["recurring_transfer"] == [] and r["unsorted"]["count"] >= 1

    def test_a_category_and_bad_answers(self, client):
        rent(client)
        [it] = asked(client)
        assert client.post("/api/recurring-transfers", json={"key": it["key"]}).status_code == 400
        assert client.post("/api/recurring-transfers",
                           json={"key": it["key"], "category": "Income"}).status_code == 400
        assert client.post("/api/recurring-transfers",
                           json={"key": "rt:nope", "kind": "rent"}).status_code == 404
        assert client.post("/api/recurring-transfers",
                           json={"key": it["key"], "category": "Utilities"}).status_code == 200

    def test_her_own_answer_on_one_stays(self, client):
        ids = rent(client, months=4)
        one = ids["SEND E-TFR ***R1k"]
        client.patch(f"/api/transactions/{one}", json={"category": "Gifts & Charity"})
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        assert client.st.get_transaction(one).category == "Gifts & Charity"


class TestTheRule:
    def test_listed_and_deleted(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        rules = client.get("/api/rules").get_json()["rules"]
        [r] = [x for x in rules if x["kind"] == "recurring"]
        assert r["name"].startswith("$1,500.00 every month, around the 1st")
        assert r["category"] == "Rent & Housing"
        # Editing what it's filed as moves its transfers.
        client.put(f"/api/rules/{r['id']}", json={"category": "Saved"})
        assert {t.category for t in client.st.all_transactions() if t.amount == 1500} == {"Saved"}
        assert client.delete(f"/api/rules/{r['id']}").status_code == 200
        assert client.st.recurring_transfers() == []
        # What it sorted keeps its category.
        assert {t.category for t in client.st.all_transactions() if t.amount == 1500} == {"Saved"}

    def test_matching(self):
        rule = {"account_id": "chq", "amount": 200.0, "cadence": "biweekly",
                "anchor": "2026-10-02", "dest_key": "acct:2345"}
        from finance.models import Transaction

        def t(amount, when, desc="TFR-TO 7712345", account="chq"):
            return Transaction(date=when, description=desc, amount=amount, account_id=account,
                               account_name=account, raw={"account_type": "depository"})
        assert rt.matches(t(200, "2026-10-16"), rule)
        assert rt.matches(t(200, "2026-10-31"), rule)            # a day late
        assert not rt.matches(t(200, "2026-10-09"), rule)        # the week between
        assert not rt.matches(t(200.01, "2026-10-16"), rule)     # another amount
        assert not rt.matches(t(200, "2026-10-16", account="sav"), rule)
        assert not rt.matches(t(200, "2026-10-16", desc="TFR-TO 9999999"), rule)


def test_the_list_says_recurring(client):
    rent(client)
    [it] = asked(client)
    client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
    rows = [r for r in client.get("/api/transactions/list", query_string={"month": month_day(0)[:7]})
            .get_json()["transactions"] if r["amount"] == 1500]
    assert rows and rows[0]["note"] == "Recurring · every month, around the 1st"
    assert rows[0]["recurring"] == it["key"]


class TestSummaryPage:
    """Profile › Recurring transfers (2026-10-28)."""

    def test_empty(self, client):
        body = client.get("/api/recurring-transfers").get_json()
        assert body == {"transfers": [], "count": 0, "asking": 0, "monthly": 0}

    def test_waiting_ones_are_counted(self, client):
        rent(client)
        assert client.get("/api/recurring-transfers").get_json()["asking"] == 1

    def test_a_confirmed_one_is_summarized(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        body = client.get("/api/recurring-transfers").get_json()
        assert body["count"] == 1 and body["asking"] == 0
        [r] = body["transfers"]
        assert r["amount"] == 1500 and r["cadence"] == "monthly"
        assert r["when"] == "every month, around the 1st"
        assert r["category"] == "Rent & Housing" and r["what"] == "Rent"
        assert r["count"] == 3 and r["last"] == month_day(0)
        assert [t["date"] for t in r["transactions"]] == [month_day(0), month_day(1), month_day(2)]
        assert r["next"] > TODAY.isoformat() and r["next"].endswith("-01")
        assert body["monthly"] == 1500 and r["rule_id"] == f"recurring:{r['id']}"

    def test_a_month_of_a_weekly_one(self, client):
        load(client.st, *[row(50, f"SEND E-TFR ***W{i}k", when=(TODAY - timedelta(days=7 * i)).isoformat())
                          for i in range(4)])
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "saved"})
        [r] = client.get("/api/recurring-transfers").get_json()["transfers"]
        assert r["cadence"] == "weekly" and r["what"] == "Into savings"
        assert r["monthly"] == round(50 * 52 / 12, 2)

    def test_changing_and_stopping_one(self, client):
        rent(client)
        [it] = asked(client)
        client.post("/api/recurring-transfers", json={"key": it["key"], "kind": "rent"})
        [r] = client.get("/api/recurring-transfers").get_json()["transfers"]
        assert client.put(f"/api/rules/{r['rule_id']}", json={"category": "Saved"}).status_code == 200
        [r] = client.get("/api/recurring-transfers").get_json()["transfers"]
        assert r["what"] == "Into savings"
        assert client.delete(f"/api/rules/{r['rule_id']}").status_code == 200
        assert client.get("/api/recurring-transfers").get_json()["count"] == 0
