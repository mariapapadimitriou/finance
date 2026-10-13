"""Profile › Accounts (Pearl AM-01 to AM-07, C-01, C-06): how each account
counts, joint shares, balances added by hand, and removing an account."""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = f"{TODAY:%Y-%m}"


def day(n=1):
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


NAMES = {"visa": "TD Visa ••1203", "amex": "Amex Business ••3008"}


def row(amount, description, account, kind="credit", n=1):
    return Transaction(date=day(n), description=description, amount=amount,
                       account_id=account, account_name=NAMES[account],
                       raw={"account_type": kind}, source="plaid")


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from cryptography.fernet import Fernet
    from app import create_app
    from finance import secrets_box
    monkeypatch.setenv(secrets_box.KEY_ENV, Fernet.generate_key().decode())
    app = create_app(str(tmp_path / "profile.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.put("/api/plan/setup", json={"income": 5200, "savings": 0})
        st = c.application.config["STORE"]
        st.add_plaid_item("item-td", "token", "TD")
        st.note_account("visa", name="TD Visa ••1203", item_id="item-td",
                        account_type="credit", subtype="credit card")
        st.note_account("sav", name="Tangerine Savings ••0932", item_id="item-td",
                        account_type="depository", subtype="savings")
        st.note_account("amex", name="Amex Business ••3008", item_id="item-td",
                        account_type="credit", subtype="credit card")
        ingest(st, IngestResult([row(120, "LOBLAWS", "visa"),
                                 row(60, "LOBLAWS", "visa", n=2)], "visa"))
        ingest(st, IngestResult([row(300, "BEST BUY", "amex")], "amex"))
        st.set_balance("visa", 412.55, None, 5000, "CAD", TODAY.isoformat())
        st.set_balance("sav", 6100, 6100, None, "CAD", TODAY.isoformat())
        yield c


def spend(c):
    return next(m for m in c.get("/api/summary").get_json()["monthly"]
                if m["month"] == MONTH)["spend"]


def overview(c):
    return c.get("/api/accounts/overview").get_json()


def find(c, aid):
    data = overview(c)
    return next(a for a in data["linked"] + data["added"] if a["id"] == aid)


def test_the_overview_lists_linked_accounts_with_their_state(client):
    data = overview(client)
    ids = [a["id"] for a in data["linked"]]
    assert set(ids) == {"visa", "sav", "amex"}
    visa = find(client, "visa")
    assert visa["name"] == "TD Visa" and visa["mask"] == "1203"
    assert visa["kind"] == "card" and visa["owing"] and visa["balance"] == 412.55
    assert visa["status"] == "up_to_date" and visa["counted"]
    assert find(client, "sav")["kind"] == "savings"
    assert data["added"] == [] and data["needs_you"] == 0


def test_a_bank_that_wants_a_sign_in_needs_her(client):
    st = client.application.config["STORE"]
    st.set_plaid_error("item-td", "Sign in again", "ITEM_LOGIN_REQUIRED")
    data = overview(client)
    assert data["needs_you"] == 3
    assert find(client, "visa")["status"] == "sign_in"
    assert client.get("/api/profile").get_json()["needs_you"] == 3


def test_not_counting_an_account_takes_it_out_of_spending(client):
    assert spend(client) == 480
    r = client.put("/api/accounts/amex/settings", json={"counted": False})
    body = r.get_json()
    assert r.status_code == 200
    assert body["account"]["status"] == "not_counted" and not body["account"]["counted"]
    assert spend(client) == 180
    # Its transactions stay in Pearl, listed as left out.
    rows = client.get("/api/transactions").get_json()["transactions"]
    assert any(t["description"] == "BEST BUY" for t in rows)


def test_not_counting_changes_safe_to_spend_and_says_so(client):
    before = client.get("/api/home").get_json()["safe_to_spend"]["amount"]
    body = client.put("/api/accounts/amex/settings", json={"counted": False}).get_json()
    after = client.get("/api/home").get_json()["safe_to_spend"]["amount"]
    assert after == pytest.approx(before + 300)
    assert body["safe_to_spend"] == pytest.approx(after)
    # Counting it again undoes it.
    client.put("/api/accounts/amex/settings", json={"counted": True})
    assert client.get("/api/home").get_json()["safe_to_spend"]["amount"] == pytest.approx(before)


def test_an_account_not_counted_cannot_be_put_back_one_row_at_a_time(client):
    client.put("/api/accounts/amex/settings", json={"counted": False})
    tid = next(t["id"] for t in client.get("/api/transactions").get_json()["transactions"]
               if t["description"] == "BEST BUY")
    r = client.delete(f"/api/transactions/{tid}/exclude")
    assert r.status_code == 409 and "budget" in r.get_json()["error"]


def test_an_uncounted_card_is_not_a_debt(client):
    debts = client.get("/api/debts").get_json()
    before = {d["account_id"] for d in debts["debts"]}
    client.put("/api/accounts/visa/settings", json={"counted": False})
    after = {d["account_id"] for d in client.get("/api/debts").get_json()["debts"]}
    assert "visa" not in after and after <= before


def test_counting_an_account_never_synced_switches_syncing_on(client):
    st = client.application.config["STORE"]
    st.set_account_sync("sav", False)
    assert find(client, "sav")["status"] == "not_counted"
    body = client.put("/api/accounts/sav/settings", json={"counted": True}).get_json()
    assert body["resync"] is True
    assert st.account_sync_rules()["sav"]["enabled"] is True
    assert find(client, "sav")["status"] == "up_to_date"


def test_a_joint_share_counts_that_share_of_each_row(client):
    r = client.put("/api/accounts/visa/settings", json={"joint_share": 50})
    assert r.status_code == 200
    visa = r.get_json()["account"]
    assert visa["joint"] and visa["joint_share"] == 50 and visa["status"] == "joint"
    assert spend(client) == 300 + 90           # half of 180, and the Amex
    client.put("/api/accounts/visa/settings", json={"joint_share": 25})
    assert spend(client) == 300 + 45
    client.put("/api/accounts/visa/settings", json={"joint_share": None})
    assert spend(client) == 480 and not find(client, "visa")["joint"]


@pytest.mark.parametrize("share", [0, 100, 150, "half", -5])
def test_a_joint_share_is_between_1_and_99(client, share):
    r = client.put("/api/accounts/visa/settings", json={"joint_share": share})
    assert r.status_code == 400 and "1%" in r.get_json()["error"]


def test_an_older_joint_account_keeps_its_rule(client):
    """Marked joint before there was a share: another member's unless she says."""
    client.put("/api/accounts/visa/joint", json={"label": "Family"})
    assert spend(client) == 300
    assert find(client, "visa")["joint_share"] is None


def test_nickname(client):
    client.put("/api/accounts/visa/settings", json={"nickname": "  Everyday   card "})
    visa = find(client, "visa")
    assert visa["name"] == "Everyday card" and visa["bank_name"] == "TD Visa"
    client.put("/api/accounts/visa/settings", json={"nickname": ""})
    assert find(client, "visa")["name"] == "TD Visa"


def test_a_savings_account_can_count_toward_the_anchor(client):
    r = client.put("/api/accounts/sav/settings", json={"anchor": True})
    assert r.status_code == 200 and r.get_json()["account"]["anchor"]
    assert client.put("/api/accounts/visa/settings", json={"anchor": True}).status_code == 400
    client.put("/api/accounts/sav/settings", json={"anchor": False})
    assert not find(client, "sav")["anchor"]


def test_unknown_account(client):
    assert client.put("/api/accounts/nope/settings", json={"counted": False}).status_code == 404
    assert client.post("/api/accounts/nope/remove", json={}).status_code == 404


# ── Added by hand (AM-05, AM-06) ─────────────────────────────────────────

def add(c, name="Meridian Savings", kind="savings", balance="$3,000.00"):
    return c.post("/api/accounts/manual", json={"name": name, "kind": kind, "balance": balance})


def test_a_balance_added_by_hand(client):
    r = add(client)
    assert r.status_code == 201
    acct = r.get_json()["account"]
    assert acct["source"] == "hand" and acct["status"] == "manual"
    assert acct["balance"] == 3000 and acct["kind"] == "savings" and acct["can_anchor"]
    assert acct["updated_at"] == TODAY.isoformat()
    assert overview(client)["added"][0]["id"] == acct["id"]
    # It brings no transactions, so spending doesn't change.
    assert spend(client) == 480


@pytest.mark.parametrize("body, field", [
    ({"name": "", "kind": "savings", "balance": 10}, "name"),
    ({"name": "X", "kind": "boat", "balance": 10}, "kind"),
    ({"name": "X", "kind": "savings", "balance": "lots"}, "balance"),
])
def test_adding_by_hand_needs_name_type_and_balance(client, body, field):
    r = client.post("/api/accounts/manual", json=body)
    assert r.status_code == 400 and r.get_json()["field"] == field


def test_hand_balances_count_in_the_position_and_the_anchor(client):
    aid = add(client).get_json()["account"]["id"]
    add(client, "Line card", "credit", 250)
    plan = client.get("/api/plan").get_json()["position"]
    assert plan["cash"] == pytest.approx(6100 + 3000)
    assert plan["owed"] == pytest.approx(412.55 + 250)

    client.put(f"/api/accounts/{aid}/settings", json={"anchor": True})
    anchor = client.get("/api/goals").get_json()["anchor"]
    assert aid in anchor["accounts"]
    assert any(a["account_id"] == aid for a in anchor["available_accounts"])

    # Not counted: out of the position.
    client.put(f"/api/accounts/{aid}/settings", json={"counted": False})
    assert client.get("/api/plan").get_json()["position"]["cash"] == pytest.approx(6100)


def test_a_hand_added_card_is_money_owed(client):
    add(client, "Store card", "credit", 250)
    debts = client.get("/api/debts").get_json()["debts"]
    assert any(d["name"] == "Store card" and d["balance"] == 250 for d in debts)


def test_updating_a_hand_balance(client):
    aid = add(client).get_json()["account"]["id"]
    r = client.put(f"/api/accounts/{aid}/balance", json={"balance": "3,250.50"})
    assert r.status_code == 200 and r.get_json()["account"]["balance"] == 3250.5
    assert client.put(f"/api/accounts/{aid}/balance", json={"balance": "x"}).status_code == 400
    assert client.put("/api/accounts/visa/balance", json={"balance": 1}).status_code == 404


# ── Removing (AM-07) and keeping as manual (C-06) ────────────────────────

def test_remove_and_keep_its_transactions(client):
    r = client.post("/api/accounts/amex/remove", json={"transactions": "keep"})
    assert r.status_code == 200 and r.get_json()["removed"] == 0
    st = client.application.config["STORE"]
    assert st.account_sync_rules()["amex"]["enabled"] is False
    assert "amex" not in {a["id"] for a in overview(client)["linked"]}
    # Past months stay accurate.
    assert spend(client) == 480


def test_remove_and_delete_its_transactions(client):
    r = client.post("/api/accounts/amex/remove", json={"transactions": "delete"})
    assert r.get_json()["removed"] == 1
    assert spend(client) == 180


def test_removing_the_last_account_on_a_login_disconnects_it(client, monkeypatch):
    from finance import plaid_link
    gone = []
    monkeypatch.setattr(plaid_link, "unlink", lambda st, item: (gone.append(item),
                                                                st.delete_plaid_item(item)))
    for aid in ("amex", "sav"):
        assert not client.post(f"/api/accounts/{aid}/remove", json={}).get_json()["disconnected"]
    assert client.post("/api/accounts/visa/remove", json={}).get_json()["disconnected"]
    assert gone == ["item-td"]


def test_remove_needs_keep_or_delete(client):
    r = client.post("/api/accounts/amex/remove", json={"transactions": "maybe"})
    assert r.status_code == 400


def test_removing_a_hand_account(client):
    aid = add(client).get_json()["account"]["id"]
    client.put(f"/api/accounts/{aid}/settings", json={"anchor": True})
    assert client.post(f"/api/accounts/{aid}/remove", json={}).status_code == 200
    assert overview(client)["added"] == []
    st = client.application.config["STORE"]
    assert aid not in (st.setting("anchor_accounts") or "")


def test_a_disconnected_account_kept_as_manual(client):
    st = client.application.config["STORE"]
    st.set_plaid_error("item-td", "Gone", "ITEM_NOT_FOUND")
    assert find(client, "visa")["status"] == "disconnected"
    assert find(client, "visa")["disconnected_on"] is not None
    r = client.post("/api/accounts/visa/keep-as-manual")
    assert r.status_code == 200
    kept = r.get_json()["account"]
    assert kept["source"] == "hand" and kept["kind"] == "card" and kept["balance"] == 412.55
    assert "visa" not in {a["id"] for a in overview(client)["linked"]}
    assert spend(client) == 480               # its history stays


def test_reset_forgets_hand_accounts(client):
    add(client)
    client.post("/api/reset", json={"confirm": "erase", "keep_banks": True})
    assert overview(client)["added"] == []
