"""Piggy banks: the arithmetic, the exclusion, and the plan it comes out of."""

from __future__ import annotations

import pytest

from finance import piggy
from finance.models import Transaction
from finance.piggy import Bank
from finance.store import Store


def txn(date="2026-09-10", merchant="AIR CANADA", amount=600.0,
        category="Travel", account="card"):
    return Transaction(date=date, description=merchant, amount=amount,
                       account_id=account, account_name=account,
                       merchant=merchant, category=category, source="csv")


# ── The arithmetic ───────────────────────────────────────────────────────────

class TestTheMonthlyContribution:
    def test_an_annual_bank_spreads_its_target_over_twelve_months(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.monthly(bank) == 100.0

    def test_money_already_set_aside_is_not_collected_twice(self):
        """$3,000 needed and $600 in hand is $2,400 to find, not $3,000."""
        bank = Bank(id=1, name="Trip", target=3000.0, opening=600.0,
                    start_month="2026-01")
        assert piggy.monthly(bank) == 200.0

    def test_a_dated_bank_divides_by_the_months_it_actually_has(self):
        bank = Bank(id=1, name="June trip", target=3000.0, cadence="once",
                    target_date="2026-06-15", start_month="2026-01")
        # January through June inclusive is six months.
        assert piggy.funding_months(bank) == 6
        assert piggy.monthly(bank) == 500.0

    def test_a_bank_opened_the_month_it_is_needed_still_divides_by_one(self):
        bank = Bank(id=1, name="Tomorrow", target=400.0, cadence="once",
                    target_date="2026-01-28", start_month="2026-01")
        assert piggy.monthly(bank) == 400.0

    def test_a_fully_funded_bank_asks_for_nothing(self):
        bank = Bank(id=1, name="Done", target=500.0, opening=500.0,
                    start_month="2026-01")
        assert piggy.monthly(bank) == 0.0


class TestWhatIsInIt:
    def test_it_accrues_a_contribution_for_every_month_including_the_first(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.accrued(bank, today="2026-01-15") == 100.0
        assert piggy.accrued(bank, today="2026-03-15") == 300.0

    def test_what_was_already_set_aside_counts_from_the_start(self):
        bank = Bank(id=1, name="Trip", target=1200.0, opening=600.0,
                    start_month="2026-01")
        # $600 in hand, plus one month of (1200-600)/12.
        assert piggy.accrued(bank, today="2026-01-15") == 650.0

    def test_a_dated_bank_stops_collecting_once_its_date_passes(self):
        bank = Bank(id=1, name="June", target=600.0, cadence="once",
                    target_date="2026-06-10", start_month="2026-01")
        assert piggy.accrued(bank, today="2026-06-30") == 600.0
        assert piggy.accrued(bank, today="2027-01-01") == 600.0

    def test_an_annual_bank_keeps_collecting_forever(self):
        """A sinking fund refills after it is spent; that is the point."""
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.accrued(bank, today="2027-06-15") == 1800.0

    def test_a_bank_whose_start_month_has_not_arrived_holds_only_its_opening(self):
        bank = Bank(id=1, name="Later", target=1200.0, opening=50.0,
                    start_month="2026-06")
        assert piggy.accrued(bank, today="2026-01-15") == 50.0


class TestStatus:
    def test_spending_more_than_has_gone_in_reads_as_overdrawn(self):
        bank = Bank(id=1, name="Trip", target=1200.0, start_month="2026-01")
        s = piggy.status(bank, charged=500.0, today="2026-02-15")
        assert s["accrued"] == 200.0
        assert s["balance"] == -300.0
        assert s["overdrawn"] is True
        assert s["overdrawn_by"] == 300.0

    def test_a_bank_within_its_means_is_not_overdrawn(self):
        bank = Bank(id=1, name="Trip", target=1200.0, start_month="2026-01")
        s = piggy.status(bank, charged=150.0, today="2026-03-15")
        assert s["balance"] == 150.0
        assert s["overdrawn"] is False

    def test_the_total_is_what_every_bank_takes_out_of_a_month(self):
        banks = [
            Bank(id=1, name="Car", target=1200.0, start_month="2026-01"),
            Bank(id=2, name="Xmas", target=600.0, start_month="2026-01"),
        ]
        assert piggy.total_monthly(banks) == 150.0


class TestValidation:
    def test_a_bank_needs_a_name_and_a_target(self):
        assert piggy.validate("", 100, "annual", None)
        assert piggy.validate("Trip", 0, "annual", None)
        assert piggy.validate("Trip", -5, "annual", None)

    def test_a_dated_bank_needs_a_date_that_has_not_passed(self):
        assert piggy.validate("Trip", 100, "once", None) is not None
        assert piggy.validate("Trip", 100, "once", "not-a-date") is not None
        assert piggy.validate("Trip", 100, "once", "2020-01-01",
                              today="2026-09-01") is not None

    def test_a_date_inside_the_current_month_is_still_usable(self):
        """A trip starting in three days is exactly when you need this."""
        assert piggy.validate("Trip", 100, "once", "2026-09-03",
                              today="2026-09-28") is None

    def test_a_good_bank_passes(self):
        assert piggy.validate("Car", 1200, "annual", None) is None


# ── The exclusion: spending charged to a bank leaves its month ────────────────

class TestAllocatedSpendingLeavesTheMonth:
    @pytest.fixture()
    def store(self, tmp_path):
        st = Store(str(tmp_path / "t.db"))
        st.add_transactions([
            txn("2026-09-10", "AIR CANADA", 600.0),
            txn("2026-09-12", "GROCER", 80.0, category="Groceries"),
        ])
        return st

    def test_an_unallocated_charge_counts_as_spending(self, store):
        from finance.analytics import counts_as_spending
        rows = store.all_transactions()
        assert all(counts_as_spending(t) for t in rows)

    def test_an_allocated_charge_does_not(self, store):
        from finance.analytics import counts_as_spending

        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank)

        rows = store.all_transactions()
        allocated = next(t for t in rows if t.amount == 600.0)
        assert allocated.bank_id == bank
        assert counts_as_spending(allocated) is False
        # The grocery shop is untouched.
        assert counts_as_spending(next(t for t in rows if t.amount == 80.0))

    def test_it_comes_back_when_the_allocation_is_removed(self, store):
        from finance.analytics import counts_as_spending

        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank)
        store.unallocate(flight.fingerprint)

        rows = store.all_transactions()
        assert all(counts_as_spending(t) for t in rows)

    def test_what_a_bank_has_been_charged_is_summed_from_the_ledger(self, store):
        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank)
        assert store.charged_to_banks()[bank] == 600.0

    def test_deleting_the_transaction_stops_it_counting_against_the_bank(self, store):
        """The total is a join, not a stored balance, so nothing has to
        remember to adjust it."""
        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank)
        store.delete_transaction(flight.fingerprint)
        assert store.charged_to_banks().get(bank, 0.0) == 0.0

    def test_allocating_a_charge_twice_moves_it_rather_than_doubling_it(self, store):
        a = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        b = store.add_piggy_bank("Car", 1200.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, a)
        store.allocate(flight.fingerprint, b)

        charged = store.charged_to_banks()
        assert charged.get(a, 0.0) == 0.0
        assert charged[b] == 600.0


# ── The buckets piggy banks replaced ─────────────────────────────────────────

class TestTheBucketMigration:
    def test_an_old_bucket_becomes_a_bank_that_is_already_full(self, tmp_path):
        """Its balance is preserved and it asks nothing of next month."""
        path = str(tmp_path / "t.db")
        st = Store(path)
        with st.conn() as c:
            c.execute("INSERT INTO buckets (name, balance) VALUES (?, ?)",
                      ("Fun", 400.0))

        again = Store(path)
        banks = again.piggy_banks()
        assert [b.name for b in banks] == ["Fun"]
        assert banks[0].opening == 400.0
        assert piggy.monthly(banks[0]) == 0.0
        assert piggy.status(banks[0], 0.0)["balance"] == 400.0

    def test_it_runs_once_and_then_does_nothing(self, tmp_path):
        path = str(tmp_path / "t.db")
        st = Store(path)
        with st.conn() as c:
            c.execute("INSERT INTO buckets (name, balance) VALUES (?, ?)",
                      ("Fun", 400.0))
        Store(path)
        Store(path)
        assert len(Store(path).piggy_banks()) == 1


# ── The plan: contributions come out before the daily number ──────────────────

class TestThePlanSubtractsContributions:
    def test_a_bank_reduces_what_is_left_to_spend(self):
        from finance.money_plan import plan

        without = plan(4000.0, [], 500.0)
        with_bank = plan(4000.0, [], 500.0, banks=250.0)
        assert without["leftover"] - with_bank["leftover"] == 250.0
        assert with_bank["banks"] == 250.0
        assert with_bank["committed"] == 750.0

    def test_banks_can_make_a_plan_negative_and_it_says_so(self):
        from finance.money_plan import plan

        result = plan(1000.0, [], 500.0, banks=800.0)
        assert result["verdict"] == "negative"
        assert "piggy banks" in result["note"]


# ── Through the API ──────────────────────────────────────────────────────────

class TestTheEndpoints:
    @pytest.fixture()
    def client(self, tmp_path):
        from app import create_app
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        with app.test_client() as c:
            yield c

    def _open(self, client, **kw):
        body = {"name": "Trip", "target": 1200, "cadence": "annual"}
        body.update(kw)
        return client.post("/api/piggy", json=body)

    def test_a_bank_round_trips_with_its_derived_figures(self, client):
        assert self._open(client).status_code == 200
        body = client.get("/api/piggy").get_json()
        bank = body["banks"][0]
        assert bank["name"] == "Trip"
        assert bank["monthly"] == 100.0
        assert body["monthly_total"] == 100.0

    def test_two_banks_cannot_share_a_name(self, client):
        self._open(client)
        r = self._open(client)
        assert r.status_code == 400
        assert "already have" in r.get_json()["error"]

    def test_a_dated_bank_needs_a_date(self, client):
        r = self._open(client, cadence="once", target_date=None)
        assert r.status_code == 400

    def test_more_set_aside_than_the_target_is_refused(self, client):
        r = self._open(client, target=100, opening=500)
        assert r.status_code == 400

    def test_editing_keeps_the_month_it_started(self, client):
        bank_id = self._open(client).get_json()["id"]
        started = client.get("/api/piggy").get_json()["banks"][0]["start_month"]
        client.patch(f"/api/piggy/{bank_id}", json={"target": 2400})
        after = client.get("/api/piggy").get_json()["banks"][0]
        assert after["start_month"] == started
        assert after["monthly"] == 200.0

    def test_renaming_a_bank_whose_date_has_passed_is_allowed(self, client):
        """Re-validating the old date would reject coming back from a trip."""
        bank_id = self._open(client, cadence="once",
                             target_date="2030-01-10").get_json()["id"]
        with client.application.config["STORE"].conn() as c:
            c.execute("UPDATE piggy_banks SET target_date = '2020-01-10', "
                      "start_month = '2019-06' WHERE id = ?", (bank_id,))
        r = client.patch(f"/api/piggy/{bank_id}", json={"name": "Old trip"})
        assert r.status_code == 200

    def test_a_charge_can_be_allocated_and_released(self, client):
        from finance.models import Transaction
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=3600).get_json()["id"]

        assert client.post(f"/api/piggy/{bank_id}/allocate",
                          json={"txn_id": txn_id}).status_code == 200
        assert client.get("/api/piggy").get_json()["banks"][0]["charged"] == 600.0

        assert client.delete(f"/api/piggy/allocations/{txn_id}").status_code == 200
        assert client.get("/api/piggy").get_json()["banks"][0]["charged"] == 0.0

    def test_an_inflow_cannot_be_charged_to_a_bank(self, client):
        """There is nothing to take out of a bank for money coming back."""
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "REFUND", -40.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client).get_json()["id"]

        r = client.post(f"/api/piggy/{bank_id}/allocate", json={"txn_id": txn_id})
        assert r.status_code == 400

    def test_allocating_removes_the_charge_from_the_month(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([
            txn("2026-09-10", "AIR CANADA", 600.0),
            txn("2026-09-12", "DINER", 50.0, category="Dining"),
        ])
        before = client.get("/api/summary").get_json()
        month_before = next(m for m in before["monthly"] if m["month"] == "2026-09")

        flight = next(t for t in st.all_transactions() if t.amount == 600.0)
        bank_id = self._open(client, target=3600).get_json()["id"]
        client.post(f"/api/piggy/{bank_id}/allocate",
                    json={"txn_id": flight.fingerprint})

        after = client.get("/api/summary").get_json()
        month_after = next(m for m in after["monthly"] if m["month"] == "2026-09")
        assert month_before["spend"] - month_after["spend"] == pytest.approx(600.0)

    def test_closing_a_bank_reports_what_it_released(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=3600).get_json()["id"]
        client.post(f"/api/piggy/{bank_id}/allocate", json={"txn_id": txn_id})

        r = client.delete(f"/api/piggy/{bank_id}")
        assert r.get_json()["released"] == 600.0
        # And the charge is back in its month.
        assert st.all_transactions()[0].bank_id is None

    def test_a_bank_lowers_the_daily_number(self, client):
        client.put("/api/plan/setup", json={"income": 4000, "savings": 500})
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-12", "DINER", 50.0, category="Dining")])

        before = client.get("/api/plan/setup").get_json()["leftover"]
        self._open(client, target=1200)
        after = client.get("/api/plan/setup").get_json()
        assert before - after["leftover"] == pytest.approx(100.0)
        assert after["banks"] == 100.0
