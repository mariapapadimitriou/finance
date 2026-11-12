"""T-01r (TEST-05, REFRESH-00 decision 1): Cash flow's month card leads with
Leftover, under a bar of Spent / Saved / Leftover. The list's month totals
carry what was put away (`saved`) so the app can say it."""

from __future__ import annotations

import sys

import pytest

sys.path.insert(0, "tests")
from test_splits import TODAY, charge, load  # noqa: E402

MONTH = TODAY.isoformat()[:7]


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "summary.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def test_month_totals_say_what_was_saved(client):
    ids = load(client.st, charge(40, "LOBLAWS", "Loblaws", category="Groceries"),
               charge(500, "TO TFSA", "To TFSA", category="Saved"))
    totals = client.get("/api/transactions/list", query_string={"month": MONTH}).get_json()["month_totals"]
    assert totals["saved"] == pytest.approx(500.0)
    assert totals["spent"] == pytest.approx(40.0)
    assert ids


def test_no_month_no_saved(client):
    load(client.st, charge(40, "LOBLAWS", "Loblaws", category="Groceries"))
    totals = client.get("/api/transactions/list").get_json()["month_totals"]
    assert "saved" not in totals
