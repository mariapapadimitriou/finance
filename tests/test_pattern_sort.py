"""Pearl sorts for you, P1a (product owner, 2026-11-15; ios/bots/ai-plan.md).
Python-only pattern auto-sort: categories after 5 agreeing answers, joint
"theirs" deposits after 8, new transactions only, at most 20 a day, each
with Undo; Stop sorting like this; AI-07's captions."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import pattern_sort as ps
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def day(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def tx(desc, amount, when, account="visa", name="TD Visa", kind="credit", category=""):
    return Transaction(date=when, description=desc, merchant=desc.title(), amount=amount, category=category,
                       account_id=account, account_name=name, raw={"account_type": kind,
                                                                   "category_confidence": "LOW"})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "ps.db"))
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
    return c.st.all_transactions()


def ids(c, desc):
    return [t.fingerprint for t in c.st.all_transactions() if t.description == desc]


def answer(c, tid, category):
    r = c.post(f"/api/transactions/{tid}/mark",
               json={"case": "spending", "category": category, "remember": False})
    assert r.status_code == 200, r.get_json()


def farm_boy_history(c, n=5, category="Groceries"):
    add(c, *[tx("NORTHSIDE PANTRY", 40.0 + i, day(60 - i * 7)) for i in range(n)])
    for tid in ids(c, "NORTHSIDE PANTRY"):
        answer(c, tid, category)


def run(c):
    r = c.post("/api/pattern-sort/run")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


class TestCategories:
    def test_five_agreeing_answers_sort_a_new_one(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        new = [t for t in ids(client, "NORTHSIDE PANTRY") if t not in ps._json(client.st, ps.BASELINE_KEY, {})["known"]]
        body = run(client)
        assert body["sorted"] == 1
        row = body["rows"][0]
        assert row["txn"] == new[0] and row["line"] == "Groceries · like your last 5"
        t = client.st.get_transaction(new[0])
        assert t.category == "Groceries" and t.category_source == "pattern"
        # Out of Needs a look, and listed in Pearl sorted first, with its record.
        review = client.get("/api/review").get_json()
        assert not any(i["txn"]["id"] == new[0] for i in review["unsure_category"])
        listed = client.get("/api/review/sorted?view=pearl").get_json()
        assert listed["rows"][0]["record"] == row["id"]
        assert client.get("/api/pattern-sort").get_json()["week"] == 1

    def test_four_is_not_enough(self, client):
        farm_boy_history(client, n=4)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client)["sorted"] == 0

    def test_answers_that_disagree_are_no_pattern(self, client):
        farm_boy_history(client, n=6)
        answer(client, ids(client, "NORTHSIDE PANTRY")[0], "Dining")
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client)["sorted"] == 0

    def test_only_new_transactions(self, client):
        """Decision 3: what was there when the switch went on is left alone."""
        farm_boy_history(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(2)))          # before the switch
        ps.switched_on(client.st)
        assert run(client)["sorted"] == 0

    def test_off_sorts_nothing(self, client):
        farm_boy_history(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client) == {"sorted": 0, "on": False}

    def test_never_transfers_or_savings(self, client):
        add(client, *[tx("TD SAVINGS XFER", 100.0, day(60 - i * 7)) for i in range(6)])
        for tid in ids(client, "TD SAVINGS XFER"):
            client.post(f"/api/transactions/{tid}/mark", json={"case": "saved"})
        ps.switched_on(client.st)
        add(client, tx("TD SAVINGS XFER", 100.0, day(1)))
        assert run(client)["sorted"] == 0

    def test_twenty_a_day(self, client):
        """Decision 2: anything past 20 is left for Quick sort."""
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, *[tx("NORTHSIDE PANTRY", 10.0 + i, day(1)) for i in range(25)])
        assert run(client)["sorted"] == 20
        assert run(client)["sorted"] == 0

    def test_pearls_sorts_never_count_as_her_answers(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        run(client)
        assert ps.patterns(client.st)["category:" + __import__("finance.categorize").categorize.merchant_key("Northside Pantry")]["count"] == 5


class TestUndo:
    def test_undo_one_row(self, client):
        """Decision 4: just that row, back to Needs a look, never again."""
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        row = run(client)["rows"][0]
        detail = client.get(f"/api/pattern-sort/{row['id']}").get_json()
        assert detail["pattern_count"] == 5 and detail["sorted_by_pattern"] == [row["txn"]]
        r = client.post(f"/api/pattern-sort/{row['id']}/undo")
        assert r.status_code == 200, r.get_json()
        t = client.st.get_transaction(row["txn"])
        assert t.category_source != "pattern"
        review = client.get("/api/review").get_json()
        assert any(i["txn"]["id"] == row["txn"] for i in review["unsure_category"])
        assert run(client)["sorted"] == 0                     # never that row again
        assert client.get("/api/pattern-sort").get_json()["week"] == 0

    def test_stop_sorting_like_this(self, client):
        """AI-04: every row it sorted goes back; new ones go to Quick sort; Undo restarts."""
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, *[tx("NORTHSIDE PANTRY", 61.40 + i, day(1)) for i in range(3)])
        assert run(client)["sorted"] == 3
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        body = client.post(f"/api/pattern-sort/rules/{pid}/stop").get_json()
        assert body["undone"] == 3 and body["title"] == "Stopped · 3 back in Needs a look"
        assert client.get("/api/pattern-sort").get_json()["rows"] == []
        add(client, tx("NORTHSIDE PANTRY", 70.0, day(0)))
        assert run(client)["sorted"] == 0
        rule = client.get(f"/api/pattern-sort/rules/{pid}").get_json()["rule"]
        assert rule["on"] is False
        assert client.post(f"/api/pattern-sort/rules/{pid}/restart", json=body["undo"]).status_code == 200
        assert len(client.get("/api/pattern-sort").get_json()["rows"]) == 3

    def test_the_switch_on_a_learned_rule(self, client):
        """AI-06: off sends new ones to Quick sort; what it sorted stays."""
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        run(client)
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        r = client.put(f"/api/pattern-sort/rules/{pid}", json={"on": False}).get_json()
        assert r["rule"]["on"] is False and len(r["rows"]) == 1
        add(client, tx("NORTHSIDE PANTRY", 70.0, day(0)))
        assert run(client)["sorted"] == 0


class TestJoint:
    """Ana's deposits into the joint account: 8 agreeing answers (decision 2)."""

    def history(self, c, n):
        from finance.joint import THEM
        c.st.set_joint("joint", "Simplii Joint")
        c.st.set_joint_people("joint", ["Ana"])
        add(c, *[tx("E-TRANSFER FROM ANA RUIZ", -400.0, day(150 - i * 14), account="joint",
                    name="Simplii Joint", kind="depository") for i in range(n)])
        for t in c.st.all_transactions():
            if t.description.startswith("E-TRANSFER"):
                c.st.set_joint_deposit(t.fingerprint, THEM, "Ana")

    def test_seven_is_not_enough(self, client):
        self.history(client, 7)
        ps.switched_on(client.st)
        add(client, tx("E-TRANSFER FROM ANA RUIZ", -400.0, day(1), account="joint", name="Simplii Joint",
                       kind="depository"))
        assert run(client)["sorted"] == 0

    def test_eight_sorts_it_as_anas_share(self, client):
        self.history(client, 8)
        ps.switched_on(client.st)
        add(client, tx("E-TRANSFER FROM ANA RUIZ", -400.0, day(1), account="joint", name="Simplii Joint",
                       kind="depository"))
        body = run(client)
        assert body["sorted"] == 1 and body["rows"][0]["line"] == "Ana’s share · like the last 8"
        t = client.st.get_transaction(body["rows"][0]["txn"])
        assert (t.joint_from, t.joint_person) == ("them", "Ana")
        assert client.post(f"/api/pattern-sort/{body['rows'][0]['id']}/undo").status_code == 200
        assert client.st.get_transaction(t.fingerprint).joint_from is None


class TestCaptions:
    """AI-07: the first case that applies."""

    def test_another_category(self, client):
        farm_boy_history(client, n=5)
        a, b = ids(client, "NORTHSIDE PANTRY")[:2]
        answer(client, a, "Dining")
        answer(client, b, "Dining")
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        t = next(x for x in client.st.all_transactions() if x.description == "NORTHSIDE PANTRY" and x.date == day(1))
        client.st.write_categories({t.fingerprint: ("Groceries", "issuer")})   # Pearl's guess
        t = client.st.get_transaction(t.fingerprint)
        why = ps.caption(client.st, t)
        assert why["case"] == "category" and why["n"] == 5 and why["k"] == 2

    def test_only_a_few(self, client):
        farm_boy_history(client, n=2)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        t = next(x for x in client.st.all_transactions() if x.date == day(1))
        client.st.write_categories({t.fingerprint: ("Groceries", "issuer")})
        assert ps.caption(client.st, client.st.get_transaction(t.fingerprint)) == {"case": "few", "n": 2}

    def test_split(self, client):
        farm_boy_history(client, n=5)
        tid = ids(client, "NORTHSIDE PANTRY")[-1]
        r = client.put(f"/api/transactions/{tid}/split", json={"mode": "even", "people": [{"name": "Sam"}]})
        assert r.status_code == 200, r.get_json()
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        t = next(x for x in client.st.all_transactions() if x.date == day(1))
        client.st.write_categories({t.fingerprint: ("Groceries", "issuer")})
        assert ps.caption(client.st, client.st.get_transaction(t.fingerprint)) == {"case": "split", "k": 1, "n": 5}

    def test_in_the_review_when_on(self, client):
        farm_boy_history(client, n=2)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        review = client.get("/api/review").get_json()
        it = next(i for i in review["unsure_category"] if i["txn"]["merchant"] == "Northside Pantry")
        assert it["unsure"]["case"] in ("few", "category")
