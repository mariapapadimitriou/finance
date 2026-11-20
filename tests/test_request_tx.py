"""One transaction per request (finance/request_tx.py)."""

import pytest
from flask import jsonify

from app import create_app
from finance.request_tx import one_transaction
from ledger_files import load_bundled


@pytest.fixture()
def app(tmp_path):
    app = create_app(str(tmp_path / "tx.db"))
    # As in production: an unhandled error becomes a 500 answer, and the
    # request's transaction is rolled back on the way out.
    app.config.update(TESTING=True, PROPAGATE_EXCEPTIONS=False)

    @app.post("/api/test/write-then-fail")
    def write_then_fail():
        st = app.config["STORE"]
        st.set_setting("tx_probe", "written")
        raise RuntimeError("boom")

    @app.post("/api/test/write-then-refuse")
    def write_then_refuse():
        st = app.config["STORE"]
        st.set_setting("tx_probe", "refused")
        return jsonify({"error": "no"}), 500

    @app.post("/api/test/write-twice")
    def write_twice():
        st = app.config["STORE"]
        st.set_setting("tx_probe", "one")
        st.set_setting("tx_probe", "two")
        return jsonify({"ok": True})

    return app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        load_bundled(c)
        yield c


def test_a_request_that_fails_leaves_nothing_behind(app, client):
    r = client.post("/api/test/write-then-fail")
    assert r.status_code == 500
    client.get("/api/preferences")        # ends the kept test context
    assert app.config["STORE"].setting("tx_probe") is None


def test_a_request_that_answers_500_leaves_nothing_behind(app, client):
    r = client.post("/api/test/write-then-refuse")
    assert r.status_code == 500
    client.get("/api/preferences")
    assert app.config["STORE"].setting("tx_probe") is None


def test_a_request_that_succeeds_commits_once(app, client):
    r = client.post("/api/test/write-twice")
    assert r.status_code == 200
    assert app.config["STORE"].setting("tx_probe") == "two"
    assert app.config["LAST_TIMING"]["tx"] == 1


def test_which_requests_keep_their_own_transactions():
    assert one_transaction("/api/home", "GET")
    assert one_transaction("/api/transactions/abc/mark", "POST")
    assert one_transaction("/api/setup-again", "GET")          # Home reads it
    assert not one_transaction("/api/setup-again", "POST")     # resetting drops the ledger
    assert not one_transaction("/api/account/delete", "POST")
    assert not one_transaction("/api/plaid/sync", "POST")
    assert not one_transaction("/api/data/export.zip", "GET")


def test_store_work_between_requests_is_its_own_transaction(app, client):
    """The test client keeps the last request's context alive; a store call
    made then (a test loading rows) must still land."""
    client.get("/api/home")
    st = app.config["STORE"]
    st.set_setting("tx_probe", "between")
    assert client.get("/api/preferences").status_code == 200
    assert st.setting("tx_probe") == "between"
