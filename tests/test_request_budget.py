"""How much database work a request may do (2026-11-19).

The iPhone felt slow because one tap meant a write that opened fifty-odd
transactions and then three to five reads that each opened as many again, on
a hosted Postgres where every transaction is a few network round trips. These
ceilings hold the main screens and the common edits to what they cost when
this was written; each performance phase lowers them. A number here going up
is the regression the phone would feel.

Every answer carries the same counts in its `Server-Timing` header
(finance/timing.py); in TESTING the app also keeps the last request's counts
in `app.config["LAST_TIMING"]`, which is what this reads.
"""

import pytest

from app import create_app
from ledger_files import load_bundled


@pytest.fixture()
def client(tmp_path):
    app = create_app(str(tmp_path / "budget.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        load_bundled(c)
        yield c


def _cost(client, method: str, path: str, **kw) -> dict:
    resp = getattr(client, method)(path, **kw)
    assert resp.status_code == 200, resp.get_json()
    timing = client.application.config["LAST_TIMING"]
    assert timing["path"] == path.split("?")[0]
    assert resp.headers["Server-Timing"].startswith("total;dur=")
    return timing


def _a_purchase(client) -> str:
    rows = client.get("/api/transactions/list?limit=25&offset=0").get_json()["transactions"]
    return next(r["id"] for r in rows if r["amount"] > 0)


# Ceilings: (transactions, statements). Measured on the bundled ledger; a
# request is allowed to cost this much and no more. One transaction per
# request since finance/request_tx.py (2026-11-19); the statements come down
# as computed results are kept (finance/derived.py).
READS = {
    "/api/home": (1, 47),
    "/api/transactions/list?limit=25&offset=0": (1, 30),
    "/api/review": (1, 19),
    "/api/quick-sort": (1, 19),
    "/api/calendar?month=2026-09": (1, 14),
    "/api/accounts/overview": (1, 24),
}


@pytest.mark.parametrize("path", sorted(READS))
def test_read_stays_within_budget(client, path):
    client.get(path)                       # the first call pays one-time setup
    t = _cost(client, "get", path)
    tx, stmts = READS[path]
    assert t["tx"] <= tx, f"{path}: {t['tx']} transactions, budget {tx}"
    assert t["stmts"] <= stmts, f"{path}: {t['stmts']} statements, budget {stmts}"


def test_category_change_stays_within_budget(client):
    tid = _a_purchase(client)
    t = _cost(client, "post", "/api/transactions/batch/category",
              json={"ids": [tid], "category": "Groceries"})
    assert t["tx"] <= 1 and t["stmts"] <= 62, (t["tx"], t["stmts"])


def test_mark_stays_within_budget(client):
    """A write's answer carries what changed (finance/changed.py): the rows
    it touched, the Allowance and the review's count. That is most of a
    write's statements now, and what spares the phone three screen loads."""
    tid = _a_purchase(client)
    t = _cost(client, "post", f"/api/transactions/{tid}/mark",
              json={"case": "spending", "category": "Groceries"})
    assert t["tx"] <= 1 and t["stmts"] <= 65, (t["tx"], t["stmts"])


def test_header_says_what_the_request_spent(client):
    resp = client.get("/api/categories")
    header = resp.headers["Server-Timing"]
    assert "db;dur=" in header and "tx=" in header and "stmts=" in header
