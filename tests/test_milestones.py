"""The path on Home (THL-129 GR-05, GR-01) and connection health (THL-120)."""

from datetime import date

import pytest

from finance import milestones, plaid_link, safe_to_spend as sts, secrets_box
from finance.store import Store
from test_plaid_link import KEY, FakePlaid
from test_safe_to_spend import TODAY, history, october, tx

ANCHOR_NONE = {"started": False, "earned": False, "target": 0, "counted": 0, "months": None}


def path(rows=None, anchor=ANCHOR_NONE, **kw):
    rows = history() + october() if rows is None else rows
    s = kw.pop("sts", None) or sts.compute(rows, TODAY)
    kw.setdefault("bills_found", 5)
    return milestones.path(rows, TODAY, s, anchor=anchor, **kw)


class TestThePath:
    def test_h01_build_with_the_anchor_next(self):
        """H-01: income and bills in, September's pay covered Essentials, so
        Build, nothing done yet, and the next step is to start the Anchor."""
        p = path()
        assert p["phase"] == "build" and p["protect_done"] is True
        assert [ph["state"] for ph in p["phases"]] == ["done", "now", "ahead"]
        assert (p["step"], p["of"]) == (1, 2)
        assert p["next"] == {"text": "Next: set up your Anchor, so a big surprise doesn’t land on your credit card.",
                             "label": "Set up your Anchor", "action": "goals"}
        assert [ph["label"] for ph in p["phases"]] == ["The basics", "Your Anchor", "Grow your money"]
        assert [s["key"] for s in p["steps"]] == ["setup", "full"]

    def test_essentials_not_covered_last_month(self):
        """September: $1,500 in, $2,000 rent. Protect waits on that step, and
        it carries the numbers that explain it."""
        rows = [tx("2026-09-01", "Landlord", 2000.00, "Rent & Housing"),
                tx("2026-09-15", "Client A", -1500.00, "Income"),
                tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        s = sts.compute(rows, TODAY, told_income=3000.0)
        p = path(rows, sts=s, bills_found=1)
        assert p["phase"] == "protect" and p["step"] == 3
        step = p["steps"][2]
        assert (step["month"], step["income"], step["essentials"]) == ("2026-09", 1500.00, 2000.00)
        assert p["next"]["action"] == "path"

    def test_set_up_then_grow_it_to_three_months(self):
        anchor = {**ANCHOR_NONE, "started": True, "started_on": "2026-09-14", "target": 8700,
                  "counted": 5470, "months": 1.9}
        p = path(anchor=anchor)
        assert (p["step"], p["of"]) == (2, 2)                     # GR-05: "step 2 of 2"
        assert p["steps"][0]["started_on"] == "2026-09-14"
        assert p["steps"][1] == {"key": "full", "label": "Grow your Anchor to 3 months", "done": False,
                                 "target": 8700, "counted": 5470, "months": 1.9, "usual": None}
        assert p["next"]["label"] == "See your Anchor"

    def test_also_counts_toward_build(self):
        p = path(account_types={"chq": "depository", "visa": "credit"})
        also = {a["key"]: a for a in p["also"]}
        # July: $2,150 in, $2,363 out. August and September: $4,300 in.
        assert also["saved_more"]["done"] is True and also["saved_more"]["count"] == 2
        # Rogers, Netflix and Spotify go on the Visa and nothing pays it off.
        assert also["cards"]["done"] is False

    def test_a_full_anchor_is_unveil(self):
        p = path(anchor={**ANCHOR_NONE, "started": True, "earned": True})
        assert p["phase"] == "unveil" and p["next"]["action"] == "path"
        p2 = path(anchor={**ANCHOR_NONE, "started": True, "earned": True},
                  account_types={"tfsa": "investment"})
        assert p2["step"] is None and p2["next"]["text"] == "Every step on your path is done."

    def test_no_income_is_protect_with_income_next(self):
        rows = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        p = path(rows, bills_found=0)
        assert p["phase"] == "protect" and (p["step"], p["of"]) == (1, 3)
        assert p["next"]["action"] == "income" and p["next"]["label"] == "Add your income"

    def test_bills_next_once_income_is_in(self):
        rows = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        s = sts.compute(rows, TODAY, told_income=3200.0)
        p = path(rows, sts=s, bills_found=0)
        assert p["step"] == 2 and p["next"]["action"] == "bills"
        assert path(rows, sts=s, bills_found=0, told_rent=1400.0)["step"] == 3

    def test_protect_stays_done(self):
        """A rough month doesn't undo Protect (THL-53)."""
        rows = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        p = path(rows, bills_found=0, protect_done_before=True)
        assert p["phase"] == "build" and p["protect_done"] is True


class TestConnections:
    @pytest.mark.parametrize("code,text,state", [
        ("ITEM_LOGIN_REQUIRED", "x", "needs_sign_in"),
        ("PENDING_EXPIRATION", "x", "needs_sign_in"),
        ("INSTITUTION_DOWN", "x", "bank_down"),
        ("INSTITUTION_NOT_RESPONDING", "x", "bank_down"),
        ("USER_PERMISSION_REVOKED", "x", "disconnected"),
        ("", "The bank needs you to sign in again. Reconnect it on this tab.", "needs_sign_in"),
        ("RATE_LIMIT_EXCEEDED", "x", None),
        (None, None, None),
    ])
    def test_state_from_plaids_code(self, code, text, state):
        assert milestones.connection_state({"last_error": text, "error_code": code}) == state

    def test_worst_first_and_whether_it_is_only_cards(self):
        items = [{"item_id": "eq", "institution": "EQ Bank", "last_error": "x",
                  "error_code": "INSTITUTION_DOWN", "last_synced": "2026-10-09T03:00:00"},
                 {"item_id": "td", "institution": "TD", "last_error": "x",
                  "error_code": "ITEM_LOGIN_REQUIRED", "last_synced": "2026-10-06T08:00:00"},
                 {"item_id": "ok", "institution": "Tangerine", "last_error": None}]
        rules = {"visa": {"item_id": "td", "enabled": True, "account_type": "credit"},
                 "sav": {"item_id": "eq", "enabled": True, "account_type": "depository"}}
        out = milestones.connections(items, rules)
        assert [(c["institution"], c["state"], c["cards_only"]) for c in out] == [
            ("TD", "needs_sign_in", True), ("EQ Bank", "bank_down", False)]


class _PlaidError(Exception):
    def __init__(self, code):
        self.body = '{"error_type": "ITEM_ERROR", "error_code": "%s", "error_message": "x"}' % code
        super().__init__(self.body)


class TestPlaidErrorsAreKept:
    def test_a_failed_sync_records_the_code(self, tmp_path, monkeypatch):
        monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
        st = Store(str(tmp_path / "t.db"))
        st.add_plaid_item("item-1", "tok", "TD")

        class Failing(FakePlaid):
            def transactions_sync(self, request):
                raise _PlaidError("ITEM_LOGIN_REQUIRED")

        monkeypatch.setattr(plaid_link, "_client", lambda: Failing([]))
        plaid_link.sync_all(st)
        item = st.plaid_items()[0]
        assert item["error_code"] == "ITEM_LOGIN_REQUIRED"
        assert milestones.connection_state(item) == "needs_sign_in"

    def test_a_good_sync_clears_it(self, tmp_path, monkeypatch):
        monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
        st = Store(str(tmp_path / "t.db"))
        st.add_plaid_item("item-1", "tok", "TD")
        st.set_plaid_error("item-1", "x", "ITEM_LOGIN_REQUIRED")
        monkeypatch.setattr(plaid_link, "_client", lambda: FakePlaid([{"next_cursor": "c"}]))
        plaid_link.sync_all(st)
        assert st.plaid_items()[0]["error_code"] is None

    def test_reconnect_opens_link_in_update_mode(self, tmp_path, monkeypatch):
        """C-04: the same connection, signed in again; no products asked for."""
        from app import create_app
        monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
        monkeypatch.delenv("VERCEL", raising=False)
        fake = FakePlaid([])
        monkeypatch.setattr(plaid_link, "_client", lambda: fake)
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        app.config["STORE"].add_plaid_item("item-1", "access-secret-xyz", "TD")
        with app.test_client() as c:
            assert c.post("/api/plaid/link-token", json={"item_id": "item-1"}).status_code == 200
            assert c.post("/api/plaid/link-token", json={"item_id": "nope"}).status_code == 404
        sent = fake.link_requests[0]
        assert sent["access_token"] == "access-secret-xyz"
        assert "products" not in sent


def test_the_home_payload_carries_path_review_and_connections(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "home.db"))
    app.config.update(TESTING=True)
    st = app.config["STORE"]
    st.add_transactions(history() + [t for t in october() if t.my_share is None and not t.repays])
    st.add_plaid_item("item-1", "tok", "TD")
    st.set_plaid_error("item-1", "x", "ITEM_LOGIN_REQUIRED")
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    with app.test_client() as c:
        body = c.get("/api/home").get_json()
        assert body["path"]["phase"] == "build"
        assert isinstance(body["review_count"], int)
        assert body["connections"][0]["state"] == "needs_sign_in"
        assert c.get("/api/path").get_json()["phase"] == "build"
    assert st.setting("protect_done_on") == TODAY.isoformat()
