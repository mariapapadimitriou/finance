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

class TestTheBaseContribution:
    """What the target and the horizon imply, before any catching up."""

    def test_an_annual_bank_spreads_its_target_over_twelve_months(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.base_monthly(bank) == 100.0

    def test_money_already_set_aside_is_not_collected_twice(self):
        """$3,000 needed and $600 in hand is $2,400 to find, not $3,000."""
        bank = Bank(id=1, name="Trip", target=3000.0, opening=600.0,
                    start_month="2026-01")
        assert piggy.base_monthly(bank) == 200.0

    def test_a_dated_bank_divides_by_the_months_it_actually_has(self):
        bank = Bank(id=1, name="June trip", target=3000.0, cadence="once",
                    target_date="2026-06-15", start_month="2026-01")
        # January through June inclusive is six months.
        assert piggy.funding_months(bank) == 6
        assert piggy.base_monthly(bank) == 500.0

    def test_a_bank_opened_the_month_it_is_needed_still_divides_by_one(self):
        bank = Bank(id=1, name="Tomorrow", target=400.0, cadence="once",
                    target_date="2026-01-28", start_month="2026-01")
        assert piggy.base_monthly(bank) == 400.0

    def test_a_fully_funded_bank_asks_for_nothing(self):
        bank = Bank(id=1, name="Done", target=500.0, opening=500.0,
                    start_month="2026-01")
        assert piggy.base_monthly(bank) == 0.0


class TestWhatIsInIt:
    """The balance, replayed month by month from what was charged when."""

    def test_it_collects_a_contribution_for_every_month_including_the_first(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.run(bank, {}, today="2026-01-15")["balance"] == 100.0
        assert piggy.run(bank, {}, today="2026-03-15")["balance"] == 300.0

    def test_what_was_already_set_aside_counts_from_the_start(self):
        bank = Bank(id=1, name="Trip", target=1200.0, opening=600.0,
                    start_month="2026-01")
        # $600 in hand, plus one month of (1200-600)/12.
        assert piggy.run(bank, {}, today="2026-01-15")["balance"] == 650.0

    def test_a_dated_bank_stops_collecting_once_its_date_passes(self):
        bank = Bank(id=1, name="June", target=600.0, cadence="once",
                    target_date="2026-06-10", start_month="2026-01")
        assert piggy.run(bank, {}, today="2026-06-30")["balance"] == 600.0
        assert piggy.run(bank, {}, today="2027-01-01")["balance"] == 600.0

    def test_an_annual_bank_keeps_collecting_forever(self):
        """A sinking fund refills after it is spent; that is the point."""
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        assert piggy.run(bank, {}, today="2027-06-15")["balance"] == 1800.0

    def test_a_bank_whose_start_month_has_not_arrived_holds_only_its_opening(self):
        bank = Bank(id=1, name="Later", target=1200.0, opening=50.0,
                    start_month="2026-06")
        assert piggy.run(bank, {}, today="2026-01-15")["balance"] == 50.0

    def test_what_it_was_charged_comes_out_in_the_month_it_was_charged(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        played = piggy.run(bank, {"2026-02": 150.0}, today="2026-03-15")
        # Three months at $100, less the $150 spent in February.
        assert played["balance"] == 150.0
        assert played["charged"] == 150.0


class TestCatchingUp:
    """The mechanism that lets a bank pay for something it has not saved for."""

    def test_a_bank_spent_ahead_of_itself_goes_behind_rather_than_refusing(self):
        """The case the feature exists for: a $2,000 trip in the first month of
        a $2,400-a-year travel fund. The month must not absorb it."""
        bank = Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")
        played = piggy.run(bank, {"2026-10": 2000.0}, today="2026-10-15")

        assert played["balance"] == -1800.0
        assert played["behind"] is True
        assert played["behind_by"] == 1800.0

    def test_the_contribution_rises_to_repay_it(self):
        bank = Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")
        played = piggy.run(bank, {"2026-10": 2000.0}, today="2026-10-15")

        assert played["base_monthly"] == 200.0
        # The shortfall spread over the catch-up window, on top of the base.
        assert played["monthly"] == round(200 + 1800 / piggy.CATCH_UP_MONTHS, 2)
        assert played["catch_up"] == round(1800 / piggy.CATCH_UP_MONTHS, 2)

    def test_the_catch_up_shrinks_as_it_is_repaid_and_then_stops(self):
        bank = Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")
        charges = {"2026-10": 2000.0}

        rates = [piggy.run(bank, charges, today=f"{m}-15")["monthly"]
                 for m in ("2026-10", "2026-11", "2026-12", "2027-03")]
        assert rates == sorted(rates, reverse=True), rates
        assert all(r > 200.0 for r in rates)

        # And a year on it is whole again, back at the base rate.
        later = piggy.run(bank, charges, today="2027-10-15")
        assert later["behind"] is False
        assert later["monthly"] == 200.0
        assert later["balance"] > 0

    def test_it_names_the_month_it_expects_to_be_whole(self):
        bank = Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")
        played = piggy.run(bank, {"2026-10": 2000.0}, today="2026-10-15")
        assert played["caught_up_by"] == "2027-10"

    def test_a_charge_made_before_the_bank_existed_still_counts(self):
        """Opening a fund *after* the trip it is for is a normal thing to do —
        "that holiday hurt, let me spread the next one" — and the replay used
        to begin at the start month, so those charges were skipped entirely and
        the bank reported itself fully funded while owing $2,000."""
        bank = Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")
        played = piggy.run(bank, {"2026-08": 2000.0}, today="2026-10-15")

        assert played["charged"] == 2000.0
        assert played["behind"] is True
        assert played["balance"] < 0

    def test_nothing_is_collected_for_months_before_the_bank_existed(self):
        """It sees the charge, but it must not pretend to have been saving."""
        bank = Bank(id=1, name="Travel", target=1200.0, start_month="2026-10")
        played = piggy.run(bank, {"2026-01": 100.0}, today="2026-10-15")
        # October alone: $100 of base plus a first catch-up instalment on the
        # $100 charged in January. Nothing at all for the nine months before it
        # opened — neither base nor catch-up.
        assert played["months_paid"] == 1
        assert played["paid_in"] == round(100 + 100 / piggy.CATCH_UP_MONTHS, 2)

    def test_a_bank_in_credit_names_no_catch_up_date(self):
        bank = Bank(id=1, name="Car", target=1200.0, start_month="2026-01")
        played = piggy.run(bank, {}, today="2026-06-15")
        assert played["caught_up_by"] is None
        assert played["catch_up"] == 0.0


class TestStatus:
    def test_it_reports_the_shortfall_and_the_raised_contribution(self):
        bank = Bank(id=1, name="Trip", target=1200.0, start_month="2026-01")
        s = piggy.status(bank, {"2026-01": 500.0}, today="2026-02-15")

        assert s["behind"] is True
        assert s["behind_by"] > 0
        assert s["monthly"] > s["base_monthly"]

    def test_a_bank_within_its_means_is_not_behind(self):
        bank = Bank(id=1, name="Trip", target=1200.0, start_month="2026-01")
        s = piggy.status(bank, {"2026-01": 50.0}, today="2026-03-15")
        assert s["behind"] is False
        assert s["monthly"] == s["base_monthly"]

    def test_a_bare_total_is_read_as_spent_this_month(self):
        """For callers asking what a charge made right now would do."""
        bank = Bank(id=1, name="Trip", target=1200.0, start_month="2026-01")
        assert (piggy.status(bank, 50.0, today="2026-03-15")["balance"]
                == piggy.status(bank, {"2026-03": 50.0}, today="2026-03-15")["balance"])

    def test_the_total_is_what_every_bank_takes_out_of_a_month(self):
        banks = [
            Bank(id=1, name="Car", target=1200.0, start_month="2026-01"),
            Bank(id=2, name="Xmas", target=600.0, start_month="2026-01"),
        ]
        assert piggy.total_monthly(banks) == 150.0

    def test_the_total_includes_a_banks_catch_up(self):
        banks = [Bank(id=1, name="Travel", target=2400.0, start_month="2026-10")]
        charged = {1: {"2026-10": 2000.0}}
        assert piggy.total_monthly(banks, charged, today="2026-10-15") > 200.0


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
        store.allocate(flight.fingerprint, bank, 600.0)

        rows = store.all_transactions()
        allocated = next(t for t in rows if t.amount == 600.0)
        assert allocated.bank_id == bank
        assert counts_as_spending(allocated) is False
        # The grocery shop is untouched.
        assert counts_as_spending(next(t for t in rows if t.amount == 80.0))

    def test_a_partly_covered_charge_still_counts_for_the_rest(self, store):
        """The bank paid $200 of a $600 flight, so $400 is the month's."""
        from finance.analytics import counts_as_spending, spend_amount, spend_only

        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank, 200.0)

        allocated = next(t for t in store.all_transactions() if t.amount == 600.0)
        assert allocated.bank_amount == 200.0
        assert counts_as_spending(allocated) is True
        assert spend_amount(allocated) == 400.0

        # And what spend_only hands downstream carries the reduced figure, so
        # every total nets it off without knowing piggy banks exist.
        netted = next(t for t in spend_only(store.all_transactions())
                      if t.merchant == "AIR CANADA")
        assert netted.amount == 400.0

    def test_the_statement_amount_is_never_rewritten(self, store):
        """spend_only hands out adjusted copies; the ledger keeps the truth."""
        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank, 200.0)

        again = next(t for t in store.all_transactions() if t.merchant == "AIR CANADA")
        assert again.amount == 600.0

    def test_it_comes_back_when_the_allocation_is_removed(self, store):
        from finance.analytics import counts_as_spending

        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank, 600.0)
        store.unallocate(flight.fingerprint)

        rows = store.all_transactions()
        assert all(counts_as_spending(t) for t in rows)

    def test_what_a_bank_has_been_charged_is_summed_from_the_ledger(self, store):
        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank, 600.0)
        assert store.charged_to_banks()[bank] == 600.0

    def test_deleting_the_transaction_stops_it_counting_against_the_bank(self, store):
        """The total is a join, not a stored balance, so nothing has to
        remember to adjust it."""
        bank = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, bank, 600.0)
        store.delete_transaction(flight.fingerprint)
        assert store.charged_to_banks().get(bank, 0.0) == 0.0

    def test_allocating_a_charge_twice_moves_it_rather_than_doubling_it(self, store):
        a = store.add_piggy_bank("Trip", 3600.0, "annual", None, "2026-01")
        b = store.add_piggy_bank("Car", 1200.0, "annual", None, "2026-01")
        flight = next(t for t in store.all_transactions() if t.amount == 600.0)
        store.allocate(flight.fingerprint, a, 600.0)
        store.allocate(flight.fingerprint, b, 600.0)

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
        assert piggy.base_monthly(banks[0]) == 0.0
        assert piggy.status(banks[0], {})["balance"] == 400.0

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

    def test_the_whole_charge_leaves_the_month_even_unfunded(self, client):
        """Your $2,000 trip: the month keeps its room, the bank goes behind."""
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=3600).get_json()["id"]   # $300/mo

        body = client.post(f"/api/piggy/{bank_id}/allocate",
                           json={"txn_id": txn_id}).get_json()
        assert body["covered"] == 600.0          # all of it, funded or not
        assert body["behind"] is True
        assert body["monthly"] > body["base_monthly"]
        assert body["caught_up_by"]

        # Deliberately not an exact shortfall: how far behind it lands depends
        # on how many months sit between the charge and today, and on how much
        # catch-up has already been paid in them. The exact arithmetic is
        # pinned in TestCatchingUp, where `today` is fixed.
        bank = client.get("/api/piggy").get_json()["banks"][0]
        assert bank["charged"] == 600.0
        assert -600.0 < bank["balance"] < 0

        assert client.delete(f"/api/piggy/allocations/{txn_id}").status_code == 200
        after = client.get("/api/piggy").get_json()["banks"][0]
        assert after["charged"] == 0.0
        assert after["behind"] is False

    def test_a_funded_bank_takes_the_charge_without_going_behind(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=3600, opening=600).get_json()["id"]

        body = client.post(f"/api/piggy/{bank_id}/allocate",
                           json={"txn_id": txn_id}).get_json()
        assert body["behind"] is False
        assert body["monthly"] == body["base_monthly"]

    def test_the_catch_up_comes_out_of_the_plan(self, client):
        """The cost does come off each month's target, which is the point."""
        client.put("/api/plan/setup", json={"income": 5200, "savings": 500})
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 2000.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=2400).get_json()["id"]

        before = client.get("/api/plan/setup").get_json()["banks"]
        client.post(f"/api/piggy/{bank_id}/allocate", json={"txn_id": txn_id})
        after = client.get("/api/plan/setup").get_json()["banks"]

        assert after > before, (before, after)

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
        bank_id = self._open(client, target=3600, opening=600).get_json()["id"]
        client.post(f"/api/piggy/{bank_id}/allocate",
                    json={"txn_id": flight.fingerprint})

        after = client.get("/api/summary").get_json()
        month_after = next(m for m in after["monthly"] if m["month"] == "2026-09")
        assert month_before["spend"] - month_after["spend"] == pytest.approx(600.0)

    def test_an_unfunded_charge_still_leaves_the_month_entirely(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        before = client.get("/api/summary").get_json()
        month_before = next(m for m in before["monthly"] if m["month"] == "2026-09")

        flight = st.all_transactions()[0]
        bank_id = self._open(client, target=3600).get_json()["id"]   # holds 300
        client.post(f"/api/piggy/{bank_id}/allocate",
                    json={"txn_id": flight.fingerprint})

        after = client.get("/api/summary").get_json()
        month_after = next(m for m in after["monthly"] if m["month"] == "2026-09")
        # All $600, not the $300 the bank had collected.
        assert month_before["spend"] - month_after["spend"] == pytest.approx(600.0)

    def test_closing_a_bank_reports_what_it_released(self, client):
        st = client.application.config["STORE"]
        st.add_transactions([txn("2026-09-10", "AIR CANADA", 600.0)])
        txn_id = st.all_transactions()[0].fingerprint
        bank_id = self._open(client, target=3600, opening=600).get_json()["id"]
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
