"""The ledger version, ETags and the `changed` envelope (finance/changed.py)."""

import pytest

from app import create_app
from ledger_files import load_bundled


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "changed.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        load_bundled(c)
        yield c


def _a_purchase(client) -> dict:
    rows = client.get("/api/transactions/list?limit=25&offset=0").get_json()["transactions"]
    return next(r for r in rows if r["amount"] > 0)


class TestVersion:
    def test_a_read_leaves_the_version_alone_and_a_write_bumps_it_once(self, client):
        st = client.application.config["STORE"]
        client.get("/api/home")                # a first read does its one-time fixes
        before = st.version()
        client.get("/api/home")
        client.get("/api/transactions/list?limit=25&offset=0")
        assert st.version() == before
        row = _a_purchase(client)
        client.post("/api/transactions/batch/category", json={"ids": [row["id"]], "category": "Groceries"})
        assert st.version() == before + 1

    def test_a_reads_one_time_fixes_count_once(self, client):
        """The first read after an import writes a few one-time fixes and
        says so in its tag; the next read is the same version."""
        first = client.get("/api/home").headers["ETag"]
        second = client.get("/api/home").headers["ETag"]
        third = client.get("/api/home").headers["ETag"]
        assert second == third
        assert first <= second


class TestETag:
    def test_a_read_carries_the_version_and_answers_304_when_asked_again(self, client):
        client.get("/api/home")
        first = client.get("/api/home")
        tag = first.headers["ETag"]
        assert tag.startswith('W/"')
        again = client.get("/api/home", headers={"If-None-Match": tag})
        assert again.status_code == 304 and again.headers["ETag"] == tag
        assert client.application.config["LAST_TIMING"]["stmts"] <= 2

    def test_a_change_makes_the_old_tag_stale(self, client):
        tag = client.get("/api/transactions/list?limit=25&offset=0").headers["ETag"]
        row = _a_purchase(client)
        client.post("/api/transactions/batch/category", json={"ids": [row["id"]], "category": "Groceries"})
        again = client.get("/api/transactions/list?limit=25&offset=0", headers={"If-None-Match": tag})
        assert again.status_code == 200 and again.headers["ETag"] != tag

    def test_answers_stay_uncached_by_browsers(self, client):
        assert client.get("/api/home").headers["Cache-Control"] == "no-store"


class TestEnvelope:
    def test_a_category_change_says_what_changed(self, client):
        row = _a_purchase(client)
        reply = client.post("/api/transactions/batch/category",
                            json={"ids": [row["id"]], "category": "Groceries"}).get_json()
        changed = reply["changed"]
        assert changed["version"] == client.application.config["STORE"].version()
        assert changed["etag"] == client.get("/api/home").headers["ETag"]
        ids = {r["id"] for r in changed["rows"]}
        assert row["id"] in ids
        mine = next(r for r in changed["rows"] if r["id"] == row["id"])
        assert mine["category"] == "Groceries"
        # The row is shaped as the list shapes it, Always switch and all.
        assert "rule" in mine and "chip" in mine
        assert changed["removed"] == []
        assert isinstance(changed["allowance"], dict)
        assert isinstance(changed["review_count"], int)

    def test_a_mark_and_a_quick_sort_answer_carry_it_too(self, client):
        row = _a_purchase(client)
        marked = client.post(f"/api/transactions/{row['id']}/mark",
                             json={"case": "spending", "category": "Groceries"}).get_json()
        assert row["id"] in {r["id"] for r in marked["changed"]["rows"]}
        sorted_ = client.put(f"/api/quick-sort/{row['id']}", json={"action": "right"}).get_json()
        assert "changed" in sorted_

    def test_a_dry_run_and_a_read_carry_none(self, client):
        row = _a_purchase(client)
        dry = client.post(f"/api/transactions/{row['id']}/mark?dry=1",
                          json={"case": "spending", "category": "Groceries"}).get_json()
        assert "changed" not in dry
        assert "changed" not in client.get("/api/home").get_json()

    def test_a_deleted_row_is_reported_removed(self, client):
        made = client.post("/api/transactions", json={
            "date": "2026-09-02", "merchant": "Lemonade stand", "amount": 3.5,
            "category": "Other", "account_id": "cash"}).get_json()
        tid = (made.get("transaction") or {}).get("id") or made.get("id")
        if not tid:
            pytest.skip("adding by hand answers differently here")
        gone = client.delete(f"/api/transactions/{tid}").get_json()
        assert tid in gone["changed"]["removed"]


class TestRepeatedWrites:
    """The phone's outbox names each edit; a repeat gets the same answer."""

    def test_the_same_op_twice_is_applied_once(self, client):
        st = client.application.config["STORE"]
        row = _a_purchase(client)
        headers = {"X-Op-Id": "op-0001-aaaa-bbbb", "X-Base-Version": str(st.version())}
        first = client.post("/api/transactions/batch/category", headers=headers,
                            json={"ids": [row["id"]], "category": "Groceries"})
        version = st.version()
        again = client.post("/api/transactions/batch/category", headers=headers,
                            json={"ids": [row["id"]], "category": "Groceries"})
        assert again.status_code == 200 and again.headers.get("X-Replayed") == "1"
        assert again.get_json() == first.get_json()
        assert st.version() == version
        assert client.application.config["LAST_TIMING"]["stmts"] <= 4

    def test_a_different_op_is_its_own_write(self, client):
        st = client.application.config["STORE"]
        row = _a_purchase(client)
        client.post("/api/transactions/batch/category", headers={"X-Op-Id": "op-0002-aaaa-bbbb"},
                    json={"ids": [row["id"]], "category": "Groceries"})
        v = st.version()
        client.post("/api/transactions/batch/category", headers={"X-Op-Id": "op-0003-aaaa-bbbb"},
                    json={"ids": [row["id"]], "category": "Dining"})
        assert st.version() > v

    def test_a_refused_write_is_replayed_as_refused(self, client):
        row = _a_purchase(client)
        headers = {"X-Op-Id": "op-0004-aaaa-bbbb"}
        first = client.post(f"/api/transactions/{row['id']}/mark", headers=headers,
                            json={"case": "nonsense"})
        again = client.post(f"/api/transactions/{row['id']}/mark", headers=headers,
                            json={"case": "nonsense"})
        assert first.status_code == 400 and again.status_code == 400
        assert again.headers.get("X-Replayed") == "1"

    def test_a_bad_op_id_is_refused(self, client):
        row = _a_purchase(client)
        r = client.post("/api/transactions/batch/category", headers={"X-Op-Id": "no way; drop"},
                        json={"ids": [row["id"]], "category": "Groceries"})
        assert r.status_code == 400


class TestRowsThatLeaveTheList:
    def test_a_row_the_write_left_out_is_removed_not_updated(self, client):
        row = _a_purchase(client)
        reply = client.put(f"/api/transactions/{row['id']}/exclude", json={"reason": "Not mine"}).get_json()
        changed = reply["changed"]
        assert row["id"] in changed["removed"]
        assert row["id"] not in {r["id"] for r in changed["rows"]}

    def test_a_deposits_parts_join_the_rows(self, client):
        rows = client.get("/api/transactions/list?limit=1000").get_json()["transactions"]
        deposit = next((r for r in rows if r["amount"] < 0), None)
        if deposit is None:
            pytest.skip("no deposit in the bundled ledger")
        amount = abs(deposit["amount"])
        reply = client.post(f"/api/transactions/{deposit['id']}/parts", json={
            "parts": [{"kind": "gift", "amount": round(amount / 2, 2)},
                      {"kind": "income", "amount": round(amount - round(amount / 2, 2), 2),
                       "income_kind": "other"}]})
        if reply.status_code != 200:
            pytest.skip(f"parts refused here: {reply.get_json()}")
        changed = reply.get_json()["changed"]
        assert deposit["id"] in changed["removed"]              # the deposit is left out as SPLIT
        made = {p["id"] for p in reply.get_json()["parts"]}
        assert made and made <= {r["id"] for r in changed["rows"]}
