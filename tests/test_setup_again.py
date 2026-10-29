"""Set up again, after Start over (2026-10-29, finance/setup_again.py):
what only she can say comes back as a short list — which accounts she
shares, her income and bills, how each account counts, debt details."""

from __future__ import annotations

import json

import pytest

from finance import setup_again, users


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, "unit-test-key-that-is-definitely-long-enough")
    app = create_app(str(tmp_path / "again.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        st = c.st = app.config["STORE"]
        st.add_plaid_item("item-1", "tok", "Wealthsimple")
        st.note_account("cash", name="Cash ••6922", item_id="item-1",
                        account_type="depository", subtype="checking")
        yield c


def status(c):
    return c.get("/api/setup-again").get_json()


def test_nothing_to_set_up_until_start_over(client):
    assert status(client) == {"active": False, "steps": [], "left": 0}


def test_start_over_leaves_the_list(client):
    client.st.set_joint_people("cash", ["Anastasia"])
    assert client.post("/api/data/start-over", json={"confirm": "start over"}).status_code == 200
    s = status(client)
    assert s["active"] is True
    assert [x["key"] for x in s["steps"]] == ["shared", "income", "accounts"]   # no card: no debts
    assert s["left"] == 3
    assert s["steps"][0]["title"] == "Which accounts do you share?"
    # The joint account it asks about again is gone with Start over.
    accounts = client.get("/api/accounts/overview").get_json()["linked"]
    assert not any(a["joint"] for a in accounts)


def test_debt_details_with_a_card_linked(client):
    client.st.note_account("visa", name="Visa ••4145", item_id="item-1",
                           account_type="credit", subtype="credit card")
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert [x["key"] for x in status(client)["steps"]][-1] == "debts"


def test_each_step_done_and_then_gone(client):
    client.post("/api/data/start-over", json={"confirm": "start over"})
    for step in ("shared", "accounts"):
        client.post("/api/setup-again", json={"step": step})
    s = status(client)
    assert [x["key"] for x in s["steps"] if not x["done"]] == ["income"]
    # Income and bills is done once both are confirmed there.
    client.st.set_setting("income_bills", json.dumps({"income_on": "2026-10-29", "bills_on": "2026-10-29"}))
    s = status(client)
    assert s["left"] == 0 and s["active"] is False


def test_hiding_it(client):
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert client.post("/api/setup-again", json={"hide": True}).get_json()["active"] is False
    assert client.post("/api/setup-again", json={"step": "nope"}).status_code == 400


def test_starting_over_again_starts_the_list_again(client):
    client.post("/api/data/start-over", json={"confirm": "start over"})
    client.post("/api/setup-again", json={"hide": True})
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert status(client)["active"] is True and status(client)["left"] == 3


def test_first_time_setup_asks_about_shared_accounts_after_linking():
    assert users.STEPS.index("linked") + 1 == users.STEPS.index("shared")
    assert setup_again.KEYS[0] == "shared"
