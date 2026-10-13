"""The Goals page: the Anchor, when it is likely full, and treasure chests."""

from __future__ import annotations

from datetime import date

import pytest

from finance import anchor
from finance.models import Transaction

TODAY = "2026-10-12"


def t(when, amount, category, account="chq", description=None):
    return Transaction(date=when, description=description or category, amount=amount,
                       account_id=account, category=category)


def saved(month, amount):
    return t(f"{month}-02", amount, "Saved")


class TestTheSuggestedAmount:
    def test_one_month_of_essentials_from_the_last_three(self):
        rows = []
        for month, groceries in (("2026-07", 600), ("2026-08", 700), ("2026-09", 800)):
            rows += [t(f"{month}-03", 1500, "Rent & Housing"),
                     t(f"{month}-09", groceries, "Groceries"),
                     t(f"{month}-11", 300, "Dining Out")]     # chosen, not needed
        rows.append(t("2026-10-03", 5000, "Rent & Housing"))  # this month: not full
        s = anchor.essentials(rows, TODAY)
        assert [m["month"] for m in s["months"]] == ["2026-07", "2026-08", "2026-09"]
        assert s["average"] == 2200
        assert s["amount"] == 2200

    def test_fewer_months_when_that_is_all_there_is(self):
        rows = [t("2026-09-03", 1234, "Groceries")]
        s = anchor.essentials(rows, TODAY)
        assert len(s["months"]) == 1 and s["amount"] == 1250   # rounded to $50

    def test_nothing_to_suggest_without_history(self):
        assert anchor.essentials([], TODAY) is None


class TestThePace:
    MONTHS = [{"month": "2026-09", "saved": 180}, {"month": "2026-08", "saved": -90},
              {"month": "2026-07", "saved": 340}, {"month": "2026-06", "saved": 260}]

    def test_the_last_three_full_months(self):
        p = anchor.pace(self.MONTHS)
        assert [m["month"] for m in p["used"]] == ["2026-07", "2026-08", "2026-09"]
        assert p["best"]["month"] == "2026-07" and p["quietest"]["month"] == "2026-08"

    def test_an_unusual_month_is_left_out_and_the_next_older_comes_in(self):
        p = anchor.pace(self.MONTHS, {"2026-08"})
        assert [m["month"] for m in p["used"]] == ["2026-06", "2026-07", "2026-09"]
        assert [m["month"] for m in p["left_out"]] == ["2026-08"]
        assert p["usual"] == 260
        assert (p["best"]["saved"], p["quietest"]["saved"]) == (340, 180)


class TestTheRange:
    PACE = anchor.pace([{"month": "2026-09", "saved": 180}, {"month": "2026-07", "saved": 340},
                        {"month": "2026-06", "saved": 260}])

    def test_it_is_a_range_from_the_best_month_to_the_quietest(self):
        r = anchor.projection(1530, self.PACE, TODAY)
        assert r["state"] == "range"
        assert (r["from"], r["to"]) == ("2027-03", "2027-07")

    def test_putting_more_aside_brings_both_ends_in(self):
        r = anchor.projection(1530, self.PACE, TODAY, extra=50)
        assert (r["from"], r["to"]) == ("2027-02", "2027-05")

    def test_no_date_when_more_has_gone_out_than_come_in(self):
        p = anchor.pace([{"month": "2026-09", "saved": -100}, {"month": "2026-08", "saved": 20},
                         {"month": "2026-07", "saved": 0}])
        assert anchor.projection(1530, p, TODAY)["state"] == "none"

    def test_no_date_without_any_history(self):
        assert anchor.projection(1530, None, TODAY)["state"] == "none"

    def test_full_needs_no_date(self):
        assert anchor.projection(0, self.PACE, TODAY)["state"] == "full"


class TestWhereItStands:
    def test_the_first_stop_then_the_full_target(self):
        s = anchor.status(620, 2150, earned=False)
        assert s["first_stop_done"] and not s["full"] and s["to_go"] == 1530

    def test_full_is_earned_once_and_a_dip_keeps_it(self):
        s = anchor.status(1900, 2150, earned=True)
        assert s["earned"] and s["dipped"] and not s["full"]

    def test_a_target_below_the_first_stop_makes_it_the_first_stop(self):
        assert anchor.status(0, 300, earned=False)["first_stop"] == 300


# ── Through the API ──────────────────────────────────────────────────────────

THIS_MONTH = date.today().strftime("%Y-%m")


def months_back(n):
    return anchor.add_months(THIS_MONTH, -n)


@pytest.fixture()
def app(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "goals.db"))
    app.config.update(TESTING=True)
    return app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        yield c


@pytest.fixture()
def st(app):
    return app.config["STORE"]


def link_accounts(st):
    today = date.today().isoformat()
    st.note_account("sav", name="TD Savings ••2214", item_id="i", enabled=False,
                    account_type="depository", subtype="savings")
    st.note_account("tng", name="Tangerine Savings ••0932", item_id="i", enabled=False,
                    account_type="depository", subtype="savings")
    st.note_account("chq", name="TD Chequing ••8890", item_id="i", enabled=True,
                    account_type="depository", subtype="checking")
    st.note_account("brk", name="Wealthsimple TFSA", item_id="i", enabled=False,
                    account_type="investment", subtype="tfsa")
    for aid, held in (("sav", 480), ("tng", 140), ("chq", 1320), ("brk", 9000)):
        st.set_balance(aid, held, held, None, "CAD", today)


def ledger(st):
    rows = []
    for n, put in ((3, 260), (2, 340), (1, 180)):
        m = months_back(n)
        rows += [t(f"{m}-03", 1500, "Rent & Housing", description=f"Rent {m}"),
                 t(f"{m}-09", 650, "Groceries", description=f"Groceries {m}"),
                 t(f"{m}-15", put, "Saved", description=f"To savings {m}")]
    st.add_transactions(rows)


class TestTheAnchorEndpoints:
    def test_before_it_starts_it_offers_savings_ticked_and_chequing_not(self, client, st):
        link_accounts(st)
        ledger(st)
        a = client.get("/api/goals").get_json()["anchor"]
        assert a["started"] is False
        offered = {x["name"]: x["suggested"] for x in a["available_accounts"]}
        assert offered == {"TD Savings ••2214": True, "Tangerine Savings ••0932": True,
                           "TD Chequing ••8890": False}
        assert a["suggestion"]["amount"] == 2150

    def test_starting_it_counts_the_chosen_accounts(self, client, st):
        link_accounts(st)
        ledger(st)
        body = client.put("/api/goals/anchor", json={
            "target": 2150, "size": 1, "accounts": ["sav", "tng"]}).get_json()
        a = body["anchor"]
        assert a["started"] and a["counted"] == 620 and a["first_stop_done"]
        assert a["projection"]["state"] == "range"
        assert body["phase"] == "build"

    def test_it_says_what_was_saved_this_month(self, client, st):
        link_accounts(st)
        ledger(st)
        a = client.get("/api/goals").get_json()["anchor"]
        assert a["saved_this_month"] == 0
        client.put("/api/goals/anchor", json={"target": 2150, "accounts": ["sav", "tng"]})
        st.add_transactions([t(f"{THIS_MONTH}-01", 300, "Saved", description="To savings"),
                             t(f"{THIS_MONTH}-01", -120, "Saved", description="From savings")])
        a = client.get("/api/goals").get_json()["anchor"]
        assert a["saved_this_month"] == 180

    def test_an_account_it_cannot_count_is_refused(self, client, st):
        link_accounts(st)
        r = client.put("/api/goals/anchor", json={"target": 1000, "accounts": ["brk"]})
        assert r.status_code == 400

    def test_reaching_the_target_earns_unveil_for_good(self, client, st):
        link_accounts(st)
        client.put("/api/goals/anchor", json={"target": 600, "accounts": ["sav", "tng"]})
        assert client.get("/api/goals").get_json()["phase"] == "unveil"
        st.set_balance("sav", 100, 100, None, "CAD", date.today().isoformat())
        body = client.get("/api/goals").get_json()
        assert body["phase"] == "unveil" and body["anchor"]["dipped"]

    def test_leaving_out_a_month_changes_the_pace(self, client, st):
        link_accounts(st)
        ledger(st)
        client.put("/api/goals/anchor", json={"target": 2150, "accounts": ["sav", "tng"]})
        body = client.put("/api/goals/anchor/unusual",
                          json={"months": [months_back(1)]}).get_json()
        assert months_back(1) in body["anchor"]["unusual"]
        assert all(m["month"] != months_back(1) for m in body["anchor"]["pace"]["used"])

    def test_what_if_is_a_preview_and_saves_nothing(self, client, st):
        link_accounts(st)
        ledger(st)
        client.put("/api/goals/anchor", json={"target": 2150, "accounts": ["sav", "tng"]})
        w = client.get("/api/goals/anchor/whatif?monthly=400").get_json()
        assert w["extra"] == pytest.approx(400 - 260)
        assert w["sooner_months"] >= 1
        assert client.get("/api/goals").get_json()["anchor"]["target"] == 2150

    def test_someone_new_is_in_protect(self, client):
        body = client.get("/api/goals").get_json()
        assert body["phase"] == "protect" and body["chests"] == []


class TestTreasureChests:
    def _open(self, client, **kw):
        body = {"name": "Holiday gifts", "target": 600, "cadence": "annual"}
        body.update(kw)
        return client.post("/api/piggy", json=body).get_json()["id"]

    def test_a_chest_is_a_piggy_bank_with_what_it_holds(self, client):
        self._open(client)
        chest = client.get("/api/goals").get_json()["chests"][0]
        assert chest["monthly"] == 50 and chest["held"] == 50
        assert chest["ready"] is False and chest["share"] == pytest.approx(50 / 600, abs=1e-3)

    def test_open_your_treasure_pays_purchases_and_a_category(self, client, st):
        bank = self._open(client)
        today = date.today().isoformat()
        st.add_transactions([t(today, 64.20, "Gifts & Charity", description="INDIGO"),
                             t(today, 96.32, "Groceries", description="LOBLAWS")])
        detail = client.get(f"/api/goals/chests/{bank}").get_json()
        assert detail["suggested_category"] == "Gifts & Charity"
        picks = {c["merchant"]: c["suggested"] for c in detail["candidates"]}
        assert picks["Indigo"] is True and picks["Loblaws"] is False
        gift = next(c["id"] for c in detail["candidates"] if c["merchant"] == "Indigo")
        r = client.post(f"/api/goals/chests/{bank}/open",
                        json={"txn_ids": [gift], "categories": ["Gifts & Charity"]}).get_json()
        assert r["paid"] == 64.20
        after = client.get(f"/api/goals/chests/{bank}").get_json()
        assert after["chest"]["categories"] == ["Gifts & Charity"]
        assert after["recent"][0]["kind"] == "paid"

    def test_add_money_comes_out_of_this_month_and_into_the_chest(self, client, st):
        bank = self._open(client)
        assert client.post(f"/api/goals/chests/{bank}/add", json={"amount": 100}).status_code == 200
        chest = client.get("/api/goals").get_json()["chests"][0]
        assert chest["held"] == 150
        # It is not shown as money a chest lent the month.
        assert [d for d in st.draws() if d["amount"] > 0] == []

    def test_got_it_quiets_the_catching_up_note_until_the_amount_changes(self, client, st):
        bank = self._open(client, name="Car insurance", target=1200)
        st.add_transactions([t(date.today().isoformat(), 1500, "Insurance",
                               description="INSURER")])
        tx = st.all_transactions()[0]
        client.post(f"/api/piggy/{bank}/allocate", json={"txn_id": tx.fingerprint})
        detail = client.get(f"/api/goals/chests/{bank}").get_json()
        assert detail["catch_up_seen"] is False
        monthly = detail["chest"]["monthly"]
        client.put(f"/api/goals/chests/{bank}/seen", json={"monthly": monthly})
        again = client.get(f"/api/goals/chests/{bank}").get_json()
        assert again["catch_up_seen"] is (again["chest"]["catching_up"])
