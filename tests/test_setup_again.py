"""Set up again, after Start over (2026-10-29, finance/setup_again.py):
what only she can say comes back as a short list — her accounts (how each
counts and who shares it, AS-04), her income and bills, debt details."""

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
    assert [x["key"] for x in s["steps"]] == ["accounts", "income"]   # no card: no debts
    assert s["left"] == 2
    # AS-04: one item for both account questions.
    assert s["steps"][0]["title"] == "Check your accounts"
    assert s["steps"][0]["sub"] == "How each counts and who shares it"
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
    client.post("/api/setup-again", json={"step": "accounts"})
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
    assert status(client)["active"] is True and status(client)["left"] == 2


def test_first_time_setup_asks_about_accounts_after_linking():
    assert users.STEPS.index("linked") + 1 == users.STEPS.index("shared")
    assert setup_again.KEYS[0] == "accounts"


# ── AS-01 / AS-04 Account setup (2026-11-15) ─────────────────────────────

def _accounts_done(c) -> bool:
    return next(x for x in status(c)["steps"] if x["key"] == "accounts")["done"]


def test_these_look_right_with_nothing_changed_is_done(client):
    """Decision 2: "These look right" counts even when she changed nothing."""
    client.post("/api/data/start-over", json={"confirm": "start over"})
    before = client.get("/api/accounts/overview").get_json()["linked"]
    assert not _accounts_done(client)
    s = client.post("/api/setup-again", json={"step": "accounts"}).get_json()
    assert next(x for x in s["steps"] if x["key"] == "accounts")["done"] is True
    assert s["left"] == 1
    # Nothing about the accounts changed.
    assert client.get("/api/accounts/overview").get_json()["linked"] == before


def test_saving_any_account_is_done(client):
    """AS-04: saving one account in AS-02 (or Accounts) answers the step."""
    client.post("/api/data/start-over", json={"confirm": "start over"})
    r = client.put("/api/accounts/cash/settings", json={"nickname": "Bills"})
    assert r.status_code == 200
    assert _accounts_done(client)


def test_a_change_that_asks_first_is_not_done_yet(client, monkeypatch):
    """A share change that needs her OK (AM-21j / AM-08n) hasn't saved, so
    the step waits."""
    from finance import profile_api
    client.post("/api/data/start-over", json={"confirm": "start over"})
    monkeypatch.setattr(profile_api, "_joint_split_plan",
                        lambda *a, **k: (None, None, {"ok": True, "needs_confirm": True, "changes": []}))
    r = client.put("/api/accounts/cash/settings", json={"joint_share": 50})
    assert r.get_json()["needs_confirm"] is True
    assert not _accounts_done(client)


def test_the_old_shared_key_still_marks_it(client):
    """A page that still sends "shared" answers the one account item."""
    client.post("/api/data/start-over", json={"confirm": "start over"})
    assert client.post("/api/setup-again", json={"step": "shared"}).status_code == 200
    assert _accounts_done(client)
    # A list saved before AS-04 with "shared" done reads as done too.
    client.st.set_setting("setup_again", json.dumps({"since": "2026-11-01", "done": ["shared"], "hidden": False}))
    assert _accounts_done(client)


def test_start_over_clears_every_account_setting(client):
    """Start over keeps only the banks: AS-02's settings and the done mark go."""
    client.st.note_account("save", name="Savings ••1111", item_id="item-1",
                           account_type="depository", subtype="savings")
    client.post("/api/data/start-over", json={"confirm": "start over"})
    client.put("/api/accounts/cash/settings",
               json={"joint_share": "auto", "joint_people": ["Sam"], "nickname": "Bills", "counted": False})
    assert _accounts_done(client)
    client.post("/api/data/start-over", json={"confirm": "start over"})
    cash = next(a for a in client.get("/api/accounts/overview").get_json()["linked"] if a["id"] == "cash")
    assert cash["joint"] is False and cash["joint_people"] == [] and cash["joint_share"] is None
    assert cash["nickname"] == "" and cash["counted"] is True
    assert not _accounts_done(client)
