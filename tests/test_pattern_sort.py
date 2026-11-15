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


def on(c):
    """Switch "Pearl sorts for you" on and say Yes to every pattern it asks
    about, as she would (AI only detects; she confirms)."""
    ps.switched_on(c.st)
    for ask in c.get("/api/pattern-sort/asks").get_json()["asks"]:
        assert c.post(f"/api/pattern-sort/asks/{ask['id']}/yes").status_code == 200


def run(c):
    r = c.post("/api/pattern-sort/run")
    assert r.status_code == 200, r.get_json()
    return r.get_json()


class TestCategories:
    def test_five_agreeing_answers_sort_a_new_one(self, client):
        farm_boy_history(client)
        on(client)
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
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client)["sorted"] == 0

    def test_answers_that_disagree_are_no_pattern(self, client):
        farm_boy_history(client, n=6)
        answer(client, ids(client, "NORTHSIDE PANTRY")[0], "Dining")
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client)["sorted"] == 0

    def test_only_new_transactions(self, client):
        """Decision 3: what was there when the switch went on is left alone."""
        farm_boy_history(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(2)))          # before the switch
        on(client)
        assert run(client)["sorted"] == 0

    def test_off_sorts_nothing(self, client):
        farm_boy_history(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client) == {"sorted": 0, "on": False}

    def test_never_transfers_or_savings(self, client):
        add(client, *[tx("TD SAVINGS XFER", 100.0, day(60 - i * 7)) for i in range(6)])
        for tid in ids(client, "TD SAVINGS XFER"):
            client.post(f"/api/transactions/{tid}/mark", json={"case": "saved"})
        on(client)
        add(client, tx("TD SAVINGS XFER", 100.0, day(1)))
        assert run(client)["sorted"] == 0

    def test_twenty_a_day(self, client):
        """Decision 2: anything past 20 is left for Quick sort."""
        farm_boy_history(client)
        on(client)
        add(client, *[tx("NORTHSIDE PANTRY", 10.0 + i, day(1)) for i in range(25)])
        assert run(client)["sorted"] == 20
        assert run(client)["sorted"] == 0

    def test_pearls_sorts_never_count_as_her_answers(self, client):
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        run(client)
        assert ps.patterns(client.st)["category:" + __import__("finance.categorize").categorize.merchant_key("Northside Pantry")]["count"] == 5


class TestUndo:
    def test_undo_one_row(self, client):
        """Decision 4: just that row, back to Needs a look, never again."""
        farm_boy_history(client)
        on(client)
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
        on(client)
        add(client, *[tx("NORTHSIDE PANTRY", 61.40 + i, day(1)) for i in range(3)])
        assert run(client)["sorted"] == 3
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        body = client.post(f"/api/pattern-sort/rules/{pid}/stop").get_json()
        assert body["undone"] == 3 and body["title"] == "Stopped · 3 back in Needs a look"
        assert client.get("/api/pattern-sort").get_json()["rows"] == []
        add(client, tx("NORTHSIDE PANTRY", 70.0, day(0)))
        assert run(client)["sorted"] == 0
        # Stopped: gone from the rules, never learned again (until Undo).
        assert client.get(f"/api/pattern-sort/rules/{pid}").status_code == 404
        assert client.post(f"/api/pattern-sort/rules/{pid}/restart", json=body["undo"]).status_code == 200
        assert len(client.get("/api/pattern-sort").get_json()["rows"]) == 3

    def test_the_switch_on_a_learned_rule(self, client):
        """AI-06: off sends new ones to Quick sort; what it sorted stays."""
        farm_boy_history(client)
        on(client)
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
        on(client)
        add(client, tx("E-TRANSFER FROM ANA RUIZ", -400.0, day(1), account="joint", name="Simplii Joint",
                       kind="depository"))
        assert run(client)["sorted"] == 0

    def test_eight_sorts_it_as_anas_share(self, client):
        self.history(client, 8)
        on(client)
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
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        review = client.get("/api/review").get_json()
        it = next(i for i in review["unsure_category"] if i["txn"]["merchant"] == "Northside Pantry")
        assert it["unsure"]["case"] in ("few", "category")


class TestForget:
    def test_forget_keeps_the_rows_and_relearns_from_new_answers(self, client):
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        row = run(client)["rows"][0]
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        assert client.post(f"/api/pattern-sort/rules/{pid}/forget").status_code == 200
        assert client.get("/api/pattern-sort/rules").get_json()["rules"] == []
        assert client.get("/api/pattern-sort").get_json()["rows"][0]["id"] == row["id"]   # the row stays
        add(client, tx("NORTHSIDE PANTRY", 70.0, day(0)))
        assert run(client)["sorted"] == 0

    def test_stopped_is_never_learned_again(self, client):
        farm_boy_history(client)
        on(client)
        pid = next(iter(ps.patterns(client.st)))
        client.post(f"/api/pattern-sort/rules/{pid}/stop")
        add(client, *[tx("NORTHSIDE PANTRY", 30.0 + i, day(0)) for i in range(6)])
        for t in client.st.all_transactions():
            if t.date == day(0):
                answer(client, t.fingerprint, "Groceries")
        assert client.get("/api/pattern-sort/rules").get_json()["rules"] == []


def test_rhythm():
    assert ps.rhythm(["2026-09-01", "2026-09-15", "2026-09-29", "2026-10-13"]) == "about every 2 weeks"
    assert ps.rhythm(["2026-09-01", "2026-09-03", "2026-10-20", "2026-10-21"]) is None


class TestAskFirst:
    """AI only detects; she confirms (product owner, 2026-11-15; AI-18)."""

    def asks(self, c):
        return c.get("/api/pattern-sort/asks").get_json()["asks"]

    def test_a_found_pattern_is_pending_and_sorts_nothing(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        [ask] = self.asks(client)
        assert ask["kind"] == "category" and ask["answer"] == "Groceries" and ask["count"] == 5
        assert ask["label"] == "Groceries" and ask["need"] == 5 and ask["skips"] == 0
        assert ask["amount"] == 42.0 and ask["same_amount"] is False      # 40..44, the middle one
        assert run(client)["sorted"] == 0
        # Not a learned rule until she says Yes.
        assert client.get("/api/pattern-sort/rules").get_json()["rules"] == []

    def test_the_ask_is_a_quick_sort_question(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        review = client.get("/api/review").get_json()
        [ask] = review["pattern_asks"]
        prompt = client.get("/api/quick-sort?all=1").get_json()
        assert ask["key"] in prompt["keys"] and prompt["count"] == review["count"]

    def test_no_asks_while_the_switch_is_off(self, client):
        farm_boy_history(client)
        assert self.asks(client) == []
        assert client.get("/api/review").get_json()["pattern_asks"] == []
        pid = next(iter(ps.patterns(client.st)))
        assert client.post(f"/api/pattern-sort/asks/{pid}/yes").status_code == 409

    def test_too_few_answers_is_not_asked(self, client):
        farm_boy_history(client, n=4)
        ps.switched_on(client.st)
        assert self.asks(client) == []

    def test_yes_records_when_how_and_count_and_sorts_only_new_matches(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))      # waiting in Needs a look
        waiting = [t for t in ids(client, "NORTHSIDE PANTRY")
                   if client.st.get_transaction(t).category_source != "user"
                   and t not in client.st.confirmed_categories()]
        [ask] = self.asks(client)
        r = client.post(f"/api/pattern-sort/asks/{ask['id']}/yes", json={"how": "ai18"}).get_json()
        assert r["confirmed"]["how"] == "ai18" and r["confirmed"]["day"] == TODAY.isoformat()
        assert r["confirmed"]["count"] == 5 and r["confirmed"]["at"]
        assert r["rule"]["confirmed"] == r["confirmed"]
        assert self.asks(client) == []
        assert run(client)["sorted"] == 0                        # the Yes sorts nothing already waiting
        assert client.st.get_transaction(waiting[0]).category_source != "pattern"
        add(client, tx("NORTHSIDE PANTRY", 70.00, day(0)))
        body = run(client)
        assert body["sorted"] == 1 and body["rows"][0]["txn"] not in waiting
        detail = client.get(f"/api/pattern-sort/{body['rows'][0]['id']}").get_json()
        assert detail["learned"] is True and detail["confirmed"]["count"] == 5

    def test_a_strange_how_is_kept_as_ask(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        [ask] = self.asks(client)
        r = client.post(f"/api/pattern-sort/asks/{ask['id']}/yes", json={"how": "<script>"}).get_json()
        assert r["confirmed"]["how"] == "ask"

    def test_yes_or_skip_to_nothing(self, client):
        ps.switched_on(client.st)
        assert client.post("/api/pattern-sort/asks/category:nope/yes").status_code == 404
        assert client.post("/api/pattern-sort/asks/category:nope/skip").status_code == 404

    def more(self, c, n, start):
        rows = [tx("NORTHSIDE PANTRY", 30.0 + start + i, day(20 - start - i)) for i in range(n)]
        add(c, *rows)
        for t in c.st.all_transactions():
            if t.description == "NORTHSIDE PANTRY" and t.category_source != "user":
                answer(c, t.fingerprint, "Groceries")

    def test_skip_asks_again_after_n_more_then_never(self, client):
        farm_boy_history(client)
        ps.switched_on(client.st)
        [ask] = self.asks(client)
        r = client.post(f"/api/pattern-sort/asks/{ask['id']}/skip").get_json()
        assert r == {"ok": True, "skips": 1, "never": False, "again_after": 5}
        assert self.asks(client) == []
        self.more(client, 4, 0)
        assert self.asks(client) == []                           # 4 more isn't 5
        self.more(client, 1, 4)
        [again] = self.asks(client)
        assert again["id"] == ask["id"] and again["count"] == 10 and again["skips"] == 1
        r = client.post(f"/api/pattern-sort/asks/{ask['id']}/skip").get_json()
        assert r == {"ok": True, "skips": 2, "never": True, "again_after": None}
        self.more(client, 6, 5)
        assert self.asks(client) == []                           # never again
        assert client.post(f"/api/pattern-sort/asks/{ask['id']}/skip").status_code == 404

    def test_forget_makes_it_askable_again(self, client):
        """Forget clears her Yes and any Skips: relearned from new answers, asked again."""
        farm_boy_history(client)
        on(client)
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        client.post(f"/api/pattern-sort/rules/{pid}/forget")
        assert ps.confirmed(client.st, pid) is None and self.asks(client) == []
        s = ps._state(client.st)
        s[pid]["forgot"] = day(30)                              # forgotten a while ago
        ps._save(client.st, ps.STATE_KEY, s)
        self.more(client, 5, 0)
        [ask] = self.asks(client)
        assert ask["id"] == pid and ask["count"] == 5

    def test_joint_asks_after_eight(self, client):
        TestJoint().history(client, 8)
        ps.switched_on(client.st)
        [ask] = self.asks(client)
        assert ask["kind"] == "joint" and ask["label"] == "Ana’s share" and ask["count"] == 8
        assert ask["need"] == 8 and ask["amount"] == 400.0 and ask["same_amount"] is True
        assert ask["rhythm"] == "about every 2 weeks"

    def test_stops_undo_keeps_her_yes(self, client):
        farm_boy_history(client)
        on(client)
        add(client, tx("NORTHSIDE PANTRY", 61.40, day(1)))
        assert run(client)["sorted"] == 1
        pid = client.get("/api/pattern-sort/rules").get_json()["rules"][0]["id"]
        body = client.post(f"/api/pattern-sort/rules/{pid}/stop").get_json()
        assert self.asks(client) == []                        # stopped is never asked about
        client.post(f"/api/pattern-sort/rules/{pid}/restart", json=body["undo"])
        assert ps.confirmed(client.st, pid) is not None
        add(client, tx("NORTHSIDE PANTRY", 72.00, day(0)))
        assert run(client)["sorted"] == 1


class TestMigration:
    """Rows P1a sorted before it asked go back to Needs a look (product owner, 2026-11-15)."""

    def sorted_before_the_rule(self, c):
        farm_boy_history(c)
        ps.switched_on(c.st)
        add(c, *[tx("NORTHSIDE PANTRY", 61.40 + i, day(1)) for i in range(2)])
        # What #341 did: no Yes in the state, rows sorted by the pattern.
        c.st.set_setting(ps.MIGRATED_KEY, "")
        pid = next(iter(ps.patterns(c.st)))
        p = ps.patterns(c.st)[pid]
        log = []
        for t in c.st.all_transactions():
            if t.description == "NORTHSIDE PANTRY" and t.date == day(1):
                log.append(ps._apply(c.st, t, p, TODAY.isoformat()))
        ps._save(c.st, ps.LOG_KEY, log)
        return pid, log

    def test_rows_go_back_to_needs_a_look_once(self, client):
        pid, log = self.sorted_before_the_rule(client)
        review = client.get("/api/review").get_json()
        back = {r["txn"] for r in log}
        assert back <= {i["txn"]["id"] for i in review["unsure_category"]}
        assert all(client.st.get_transaction(t).category_source != "pattern" for t in back)
        assert client.get("/api/pattern-sort").get_json()["rows"] == []
        assert [a["id"] for a in review["pattern_asks"]] == [pid]
        assert ps.migrate(client.st) == []                     # once

    def test_a_confirmed_patterns_rows_stay(self, client):
        pid, log = self.sorted_before_the_rule(client)
        s = ps._state(client.st)
        s[pid] = {"on": True, "confirmed": {"at": "x", "day": TODAY.isoformat(), "how": "ask", "count": 5}}
        ps._save(client.st, ps.STATE_KEY, s)
        assert ps.migrate(client.st) == []
        assert len(client.get("/api/pattern-sort").get_json()["rows"]) == 2

    def test_a_yes_after_migration_sorts_only_new_ones(self, client):
        pid, log = self.sorted_before_the_rule(client)
        run(client)                                            # migrates
        client.post(f"/api/pattern-sort/asks/{pid}/yes")
        assert run(client)["sorted"] == 0                      # the ones that went back stay hers
        add(client, tx("NORTHSIDE PANTRY", 81.0, day(0)))
        body = run(client)
        assert body["sorted"] == 1 and client.st.get_transaction(body["rows"][0]["txn"]).amount == 81.0
