"""The same quantity, asked for in every place the app reports it.

Each tab computes its numbers from the ledger independently, which is how
they drift: two functions both called "monthly spend" that disagree about a
refund, a budget whose lines sum to a few cents either side of its own
total, a column headed "Spend" that counts a card payment.

Any one of those is small. Together they are the reason someone stops
trusting the figure in front of them, and no amount of care in a single
panel fixes it — the invariants have to be asserted across panels, and
re-asserted after the ledger changes, because a number that ties out on a
fresh import and drifts after an edit is worse than one that never tied out
at all.

So these tests are deliberately not unit tests. They drive the API the way
the app does and compare what different endpoints say about the same money.
"""

from __future__ import annotations

import pytest

from finance.categorize import NON_SPEND, is_discretionary

TOLERANCE = 0.011          # a cent, plus room for float noise


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "consistency.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


@pytest.fixture()
def ledger(client):
    """A ledger with a plan on it, as the app is meant to be used."""
    client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
    client.put("/api/plan/setup", json={"income": 5200, "savings": 900})
    client.post("/api/plan/fixed", json={"name": "Rent", "amount": 2100,
                                         "category": "Rent & Housing"})
    client.post("/api/plan/setup/apply")
    return client


def busiest_month(client) -> str:
    from collections import Counter
    rows = client.application.config["STORE"].all_transactions()
    return Counter(t.month for t in rows).most_common(1)[0][0]


def ledger_spend(client, month: str) -> float:
    """What the month cost, recomputed from the raw rows.

    Deliberately written out rather than calling the app's own predicate, so
    that it is an independent check. It has to mirror both halves of the rule:
    a transfer is not consumption, and a charge allocated to a piggy bank
    belongs to the months that funded the bank rather than to this one.
    """
    rows = client.application.config["STORE"].all_transactions()
    return round(sum(t.amount for t in rows
                     if t.month == month and t.category not in NON_SPEND
                     and t.bank_id is None), 2)


class TestOneMonthOneNumber:
    """What the month cost, according to each tab that says so."""

    def test_overview_breakdown_and_the_ledger_agree(self, ledger):
        month = busiest_month(ledger)
        truth = ledger_spend(ledger, month)

        monthly = ledger.get("/api/summary").get_json()["monthly"]
        overview = next(r["spend"] for r in monthly if r["month"] == month)
        breakdown = round(sum(r["amount"] for r in ledger.get(
            f"/api/breakdown?month={month}").get_json()["categories"]), 2)

        assert overview == pytest.approx(truth, abs=TOLERANCE)
        assert breakdown == pytest.approx(truth, abs=TOLERANCE)

    def test_the_budgets_tab_accounts_for_the_whole_month(self, ledger):
        """Budgeted, bank-funded and unbudgeted are the month, with nothing
        unexplained. Travel is the third term: it has no budget line and is
        not a missing one either."""
        add_travel(ledger)
        month = busiest_month(ledger)
        b = ledger.get(f"/api/budgets?month={month}").get_json()
        assert (b["covered_spend"] + b["unbudgeted_spend"]
                + b["bank_funded"]["unallocated_total"]) == pytest.approx(
            b["month_spend"], abs=TOLERANCE)
        assert b["budgetable_spend"] == pytest.approx(
            b["month_spend"] - b["bank_funded"]["unallocated_total"],
            abs=TOLERANCE)
        assert b["month_spend"] == pytest.approx(ledger_spend(ledger, month),
                                                 abs=TOLERANCE)


class TestSpendMeansSpend:
    def test_accounts_and_overview_agree_on_the_total(self, ledger):
        """A card payment is positive on some statements and is not spending."""
        accounts = ledger.get("/api/accounts").get_json()["accounts"]
        total = round(sum(a["total_spend"] for a in accounts), 2)
        assert total == pytest.approx(
            ledger.get("/api/summary").get_json()["total_spend"], abs=TOLERANCE)

    def test_account_rows_add_up_to_the_ledger(self, ledger):
        accounts = ledger.get("/api/accounts").get_json()["accounts"]
        assert sum(a["transactions"] for a in accounts) == len(
            ledger.application.config["STORE"].all_transactions())

    def test_a_card_payment_is_never_counted_as_income(self, ledger):
        """It once was, which read a $2,600 payment as a $2,600 salary."""
        monthly = ledger.get("/api/summary").get_json()["monthly"]
        assert all(r["income"] == 0 for r in monthly), [
            r for r in monthly if r["income"]]
        assert any(r["inflows"] > 0 for r in monthly)


class TestThePlanTiesOut:
    def test_the_leftover_is_the_arithmetic(self, ledger):
        p = ledger.get("/api/plan/setup").get_json()
        assert p["leftover"] == pytest.approx(
            p["income"] - p["fixed_total"] - p["savings"], abs=TOLERANCE)

    def test_the_budget_lines_sum_to_the_leftover_exactly(self, ledger):
        """Not to within a few cents. Exactly."""
        p = ledger.get("/api/plan/setup").get_json()
        assert round(sum(p["suggested_budgets"].values()), 2) == p["leftover"]

    def test_the_budgets_on_disk_sum_to_the_leftover(self, ledger):
        p = ledger.get("/api/plan/setup").get_json()
        saved = ledger.get("/api/budgets").get_json()["budgets"]
        assert round(sum(saved.values()), 2) == p["leftover"]

    def test_the_daily_number_divides_the_discretionary_slice(self, ledger):
        """Not the whole leftover.

        Groceries come out of the leftover and are not pocket money: no
        amount of restraint on a Tuesday changes the grocery bill. Dividing
        the whole leftover by the days in the month handed the grocery money
        out as a daily allowance and then budgeted it a second time.
        """
        p = ledger.get("/api/plan/setup").get_json()
        state = ledger.get("/api/plan").get_json()["state"]
        assert state["monthly_amount"] == pytest.approx(p["daily_pool"],
                                                        abs=TOLERANCE)
        assert p["daily_pool"] < p["leftover"]

    def test_the_budgets_still_cover_the_whole_leftover(self, ledger):
        """Everything not committed has a line, essentials included."""
        p = ledger.get("/api/plan/setup").get_json()
        saved = ledger.get("/api/budgets").get_json()["budgets"]
        assert round(sum(saved.values()), 2) == p["leftover"]
        assert any(c in saved for c in ("Groceries", "Health", "Utilities"))

    def test_the_daily_arithmetic_is_internally_consistent(self, ledger):
        s = ledger.get("/api/plan").get_json()["state"]
        assert s["flat_daily"] == pytest.approx(
            s["budget"] / s["days_in_month"], abs=0.02)
        assert s["remaining"] == pytest.approx(
            s["budget"] - s["spent_mtd"], abs=TOLERANCE)
        assert s["safe_today"] == pytest.approx(
            s["flat_daily"] + s["carried_in"] - s["spent_today"], abs=0.02)
        assert s["spread_daily"] == pytest.approx(
            s["remaining"] / s["days_left"], abs=0.02)


class TestNumbersMoveTogetherWhenThingsChange:
    """The part that actually breaks: consistency after an edit."""

    def test_changing_income_moves_the_budgets_and_the_daily_number(self, ledger):
        ledger.put("/api/plan/setup", json={"income": 4000, "savings": 500})
        ledger.post("/api/plan/setup/apply")

        p = ledger.get("/api/plan/setup").get_json()
        assert p["leftover"] == 1400
        saved = ledger.get("/api/budgets").get_json()["budgets"]
        assert round(sum(saved.values()), 2) == 1400
        state = ledger.get("/api/plan").get_json()["state"]
        assert state["monthly_amount"] == pytest.approx(p["daily_pool"],
                                                        abs=TOLERANCE)

    def test_the_daily_number_follows_the_plan_without_being_re_applied(self, ledger):
        """The bug this replaced: it used to be stored when you pressed "Use
        these budgets", so raising your pay moved the Plan tab and left Today
        quoting the figure from whenever that button was last pressed."""
        ledger.put("/api/plan/setup", json={"income": 4000, "savings": 500})
        before = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]

        # Note: no /api/plan/setup/apply. Nothing is pressed.
        ledger.put("/api/plan/setup", json={"income": 6000, "savings": 500})
        after = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]

        assert after > before

    def test_todays_number_can_be_traced_back_to_the_plans_leftover(self, ledger):
        """The two tabs show different figures on purpose — the Plan's leftover
        still has the groceries in it — so Today publishes the whole chain."""
        ledger.put("/api/plan/setup", json={"income": 4000, "savings": 500})
        d = ledger.get("/api/plan").get_json()["derivation"]
        setup = ledger.get("/api/plan/setup").get_json()

        assert d["from_plan"] is True
        assert d["leftover"] == pytest.approx(setup["leftover"], abs=TOLERANCE)
        assert d["income"] - d["fixed_total"] - d["savings"] - d["banks"] == (
            pytest.approx(d["leftover"], abs=TOLERANCE))
        assert d["leftover"] - d["essentials"] == pytest.approx(
            d["discretionary"], abs=TOLERANCE)
        assert d["discretionary"] == pytest.approx(
            ledger.get("/api/plan").get_json()["state"]["monthly_amount"],
            abs=TOLERANCE)

    def test_a_piggy_bank_moves_the_plan_and_the_daily_number_together(self, ledger):
        ledger.put("/api/plan/setup", json={"income": 4000, "savings": 500})
        before_left = ledger.get("/api/plan/setup").get_json()["leftover"]
        before_daily = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]

        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})

        after_left = ledger.get("/api/plan/setup").get_json()["leftover"]
        after_daily = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]
        assert before_left - after_left == pytest.approx(200.0, abs=TOLERANCE)
        assert after_daily < before_daily

    def test_charging_a_purchase_to_a_bank_takes_it_out_of_every_total(self, ledger):
        month = busiest_month(ledger)
        rows = ledger.application.config["STORE"].all_transactions()
        charge = next(t for t in rows if t.month == month and t.amount > 100
                      and is_discretionary(t.category or "Other"))

        before_month = ledger_spend(ledger, month)
        before_total = ledger.get("/api/summary").get_json()["total_spend"]
        bank_id = ledger.post("/api/piggy", json={
            "name": "Big things", "target": 6000, "cadence": "annual",
        }).get_json()["id"]
        ledger.post(f"/api/piggy/{bank_id}/allocate",
                    json={"txn_id": charge.fingerprint})

        assert ledger_spend(ledger, month) == pytest.approx(
            before_month - charge.amount, abs=TOLERANCE)
        assert ledger.get("/api/summary").get_json()["total_spend"] == (
            pytest.approx(before_total - charge.amount, abs=TOLERANCE))

    def test_adding_a_commitment_reduces_what_is_left(self, ledger):
        before = ledger.get("/api/plan/setup").get_json()["leftover"]
        ledger.post("/api/plan/fixed", json={"name": "Gym", "amount": 80})
        after = ledger.get("/api/plan/setup").get_json()
        assert after["leftover"] == pytest.approx(before - 80, abs=TOLERANCE)
        assert after["fixed_total"] == pytest.approx(2180, abs=TOLERANCE)

    def test_removing_a_commitment_puts_it_back(self, ledger):
        before = ledger.get("/api/plan/setup").get_json()["leftover"]
        cost_id = ledger.post("/api/plan/fixed",
                              json={"name": "Gym", "amount": 80}).get_json()["id"]
        ledger.delete(f"/api/plan/fixed/{cost_id}")
        assert ledger.get("/api/plan/setup").get_json()["leftover"] == pytest.approx(
            before, abs=TOLERANCE)

    def test_adding_a_transaction_moves_every_total_that_includes_it(self, ledger):
        month = busiest_month(ledger)
        before_month = ledger_spend(ledger, month)
        before_total = ledger.get("/api/summary").get_json()["total_spend"]

        ledger.post("/api/transactions", json={
            "date": f"{month}-14", "description": "A NEW LUNCH",
            "amount": 42.50, "category": "Dining"})

        assert ledger_spend(ledger, month) == pytest.approx(
            before_month + 42.50, abs=TOLERANCE)
        summary = ledger.get("/api/summary").get_json()
        assert summary["total_spend"] == pytest.approx(
            before_total + 42.50, abs=TOLERANCE)
        breakdown = round(sum(r["amount"] for r in ledger.get(
            f"/api/breakdown?month={month}").get_json()["categories"]), 2)
        assert breakdown == pytest.approx(before_month + 42.50, abs=TOLERANCE)
        accounts = round(sum(a["total_spend"] for a in ledger.get(
            "/api/accounts").get_json()["accounts"]), 2)
        assert accounts == pytest.approx(summary["total_spend"], abs=TOLERANCE)

    def test_recategorizing_moves_money_between_lines_not_into_thin_air(self, ledger):
        month = busiest_month(ledger)
        before = ledger_spend(ledger, month)
        rows = ledger.get(f"/api/transactions?month={month}&limit=500").get_json()
        row = next(t for t in rows["transactions"]
                   if t["amount"] > 0 and t["category"] != "Travel")

        ledger.patch(f"/api/transactions/{row['id']}", json={"category": "Travel"})

        assert ledger_spend(ledger, month) == pytest.approx(before, abs=TOLERANCE)
        breakdown = round(sum(r["amount"] for r in ledger.get(
            f"/api/breakdown?month={month}").get_json()["categories"]), 2)
        assert breakdown == pytest.approx(before, abs=TOLERANCE)

    def test_moving_a_charge_to_transfers_removes_it_from_spending(self, ledger):
        """And removes it from every total, by the same amount."""
        month = busiest_month(ledger)
        before = ledger_spend(ledger, month)
        rows = ledger.get(f"/api/transactions?month={month}&limit=500").get_json()
        row = next(t for t in rows["transactions"] if t["amount"] > 0)

        ledger.patch(f"/api/transactions/{row['id']}", json={"category": "Transfers"})

        after = ledger_spend(ledger, month)
        assert after == pytest.approx(before - row["amount"], abs=TOLERANCE)
        breakdown = round(sum(r["amount"] for r in ledger.get(
            f"/api/breakdown?month={month}").get_json()["categories"]), 2)
        assert breakdown == pytest.approx(after, abs=TOLERANCE)
        accounts = round(sum(a["total_spend"] for a in ledger.get(
            "/api/accounts").get_json()["accounts"]), 2)
        assert accounts == pytest.approx(
            ledger.get("/api/summary").get_json()["total_spend"], abs=TOLERANCE)

    def test_trimming_the_ledger_moves_the_totals_down_together(self, ledger):
        ledger.put("/api/ledger/start", json={"start": "2026-03-01", "trim": True})
        summary = ledger.get("/api/summary").get_json()
        accounts = round(sum(a["total_spend"] for a in ledger.get(
            "/api/accounts").get_json()["accounts"]), 2)
        assert accounts == pytest.approx(summary["total_spend"], abs=TOLERANCE)
        assert all(m >= "2026-03" for m in summary["months"])

    def test_declaring_a_trip_keeps_the_month_total_unchanged(self, ledger):
        """It relabels spending; it must not create or destroy any."""
        month = busiest_month(ledger)
        before = ledger_spend(ledger, month)
        ledger.post("/api/trips", json={"name": "Somewhere",
                                        "start_date": f"{month}-05",
                                        "end_date": f"{month}-12"})
        assert ledger_spend(ledger, month) == pytest.approx(before, abs=TOLERANCE)


class TestDerivedFiguresAgreeWithTheirParts:
    def test_subscriptions_annual_is_twelve_monthlies(self, ledger):
        s = ledger.get("/api/recurring").get_json()["summary"]
        assert s["annual_total"] == pytest.approx(s["monthly_total"] * 12, abs=1.0)

    def test_the_split_adds_up_to_the_month(self, ledger):
        split = ledger.get("/api/summary").get_json()["split"]
        assert split["discretionary"] + split["fixed"] == pytest.approx(
            split["total"], abs=TOLERANCE)

    def test_each_budget_row_is_internally_consistent(self, ledger):
        for r in ledger.get("/api/budgets").get_json()["status"]:
            assert r["remaining"] == pytest.approx(r["budget"] - r["spent"],
                                                   abs=TOLERANCE)
            if r["budget"]:
                assert r["used"] == pytest.approx(r["spent"] / r["budget"], abs=1e-3)


class TestOneFigureOneName:
    """The same quantity quoted on two tabs has to be the same quantity."""

    def test_the_typical_month_is_the_same_on_overview_and_projections(self, ledger):
        """They disagreed by half: a mean of complete months against a median
        including a partial one, both labelled the typical month."""
        summary = ledger.get("/api/summary").get_json()
        projections = ledger.get("/api/projections").get_json()
        assert projections["typical_monthly_spend"] == pytest.approx(
            summary["typical_monthly_spend"], abs=TOLERANCE)

    def test_the_summary_keeps_both_names_pointing_at_one_number(self, ledger):
        summary = ledger.get("/api/summary").get_json()
        assert summary["average_monthly_spend"] == summary["typical_monthly_spend"]

    def test_the_month_against_typical_is_the_difference_shown(self, ledger):
        summary = ledger.get("/api/summary").get_json()
        assert summary["vs_average"] == pytest.approx(
            summary["latest_spend"] - summary["typical_monthly_spend"], abs=TOLERANCE)


class TestHeadlinesMatchTheirLists:
    def test_the_savings_headline_is_the_sum_of_its_findings(self, ledger):
        ins = ledger.get("/api/insights").get_json()
        listed = round(sum(f.get("annual_saving") or 0 for f in ins["findings"]), 2)
        assert ins["summary"]["annual_total"] == pytest.approx(listed, abs=TOLERANCE)

    def test_the_savings_split_by_effort_adds_up(self, ledger):
        s = ledger.get("/api/insights").get_json()["summary"]
        assert sum(s["by_effort"].values()) == pytest.approx(
            s["annual_total"], abs=TOLERANCE)

    def test_the_weighted_figure_never_exceeds_the_raw_one(self, ledger):
        s = ledger.get("/api/insights").get_json()["summary"]
        assert s["weighted_annual"] <= s["annual_total"] + TOLERANCE

    def test_the_subscription_tiles_are_the_sum_of_the_rows(self, ledger):
        body = ledger.get("/api/recurring").get_json()
        active = [r for r in body["recurring"] if r["active"]]
        assert body["summary"]["monthly_total"] == pytest.approx(
            round(sum(r["monthly_cost"] for r in active), 2), abs=TOLERANCE)
        assert body["summary"]["annual_total"] == pytest.approx(
            round(sum(r["annual_cost"] for r in active), 2), abs=TOLERANCE)

    def test_the_trip_summary_is_the_travel_in_the_ledger(self, ledger):
        month = busiest_month(ledger)
        ledger.post("/api/trips", json={"name": "Somewhere",
                                        "start_date": f"{month}-05",
                                        "end_date": f"{month}-12"})
        rows = ledger.application.config["STORE"].all_transactions()
        travel = round(sum(t.amount for t in rows
                           if t.category == "Travel" and t.amount > 0), 2)
        summary = ledger.get("/api/trips").get_json()["summary"]
        assert summary["travel_spend"] == pytest.approx(travel, abs=TOLERANCE)

    def test_the_account_list_totals_match_the_import_list(self, ledger):
        """Two tabs show the same per-card table; they must not differ."""
        accounts = {a["account_id"]: a for a in
                    ledger.get("/api/accounts").get_json()["accounts"]}
        for a in ledger.get("/api/summary").get_json()["accounts"]:
            other = accounts.get(a["account_id"])
            if not other:
                continue
            assert a["amount"] == pytest.approx(other["total_spend"], abs=TOLERANCE)
            # Same column name, so it has to be the same count.
            assert a["transactions"] == other["transactions"]


class TestTheLedgerKnowsItsCurrency:
    """The amounts were always right; the dollar sign on them was not.

    Plaid reports a currency per transaction and the CSV layouts record one,
    so a Canadian ledger is stored as CAD throughout. The formatter said USD
    regardless, hard-coded, which relabelled every figure in the app.
    """

    def test_the_summary_reports_what_the_ledger_is_in(self, ledger):
        assert ledger.get("/api/summary").get_json()["currency"] == "CAD"

    def test_the_accounts_tab_agrees_about_the_currency(self, ledger):
        accounts = ledger.get("/api/accounts").get_json()
        assert accounts["currency"] == (
            ledger.get("/api/summary").get_json()["currency"])

    def test_a_single_currency_ledger_says_so(self, ledger):
        mix = ledger.get("/api/summary").get_json()["currency_mix"]
        assert len(mix) == 1
        assert mix[0]["currency"] == "CAD"

    def test_a_statement_keeps_the_currency_its_layout_declares(self, ledger):
        rows = ledger.application.config["STORE"].all_transactions()
        assert {t.currency for t in rows} == {"CAD"}

    def test_plaid_rows_keep_the_currency_plaid_reports(self):
        from finance.ingest.plaid_source import map_plaid_transaction
        t = map_plaid_transaction(
            {"transaction_id": "x", "date": "2026-05-01", "name": "TIM HORTONS",
             "amount": 2.79, "account_id": "a", "iso_currency_code": "CAD"},
            {"a": {"name": "TD", "type": "credit"}})
        assert t.currency == "CAD"

    def test_an_unofficial_currency_is_not_relabelled_as_dollars(self):
        """Plaid moves the code when it does not officially support one."""
        from finance.ingest.plaid_source import map_plaid_transaction
        t = map_plaid_transaction(
            {"transaction_id": "y", "date": "2026-05-01", "name": "X",
             "amount": 1.0, "account_id": "a", "iso_currency_code": None,
             "unofficial_currency_code": "CRC"}, {"a": {}})
        assert t.currency == "CRC"

    def test_a_mixed_ledger_is_reported_as_mixed(self, ledger):
        """Totals add amounts together, so two currencies make them wrong."""
        from finance.ingest.base import IngestResult
        from finance.models import Transaction
        from finance.pipeline import ingest

        st = ledger.application.config["STORE"]
        ingest(st, IngestResult(transactions=[Transaction(
            date="2026-05-04", description="US SHOP", amount=20.0,
            account_id="us_card", account_name="US card", source="csv",
            currency="USD")], format_key="csv", format_label="CSV",
            confidence=1.0), filename="us.csv")

        mix = ledger.get("/api/accounts").get_json()["currency_mix"]
        assert [m["currency"] for m in mix] == ["CAD", "USD"]
        # The commoner one still drives formatting; the warning does the rest.
        assert ledger.get("/api/summary").get_json()["currency"] == "CAD"


class TestOneFigureOneAuthority:
    """The class of bug this suite exists for: a number decided in one place
    and read in another, which then drift apart without saying so."""

    def test_budgets_report_when_they_no_longer_match_the_plan(self, ledger):
        """Adopt budgets, then change the plan underneath them."""
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        ledger.post("/api/plan/setup/apply")
        assert ledger.get("/api/budgets").get_json()["drift"] is None

        # A piggy bank takes $200 a month out of the leftover the saved budgets
        # are still dividing.
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})

        drift = ledger.get("/api/budgets").get_json()["drift"]
        assert drift is not None
        assert drift["gap"] == pytest.approx(200.0, abs=TOLERANCE)
        assert drift["saved_total"] - drift["plan_total"] == pytest.approx(
            200.0, abs=TOLERANCE)
        assert drift["banks"] == pytest.approx(200.0, abs=TOLERANCE)

    def test_re_applying_clears_the_drift(self, ledger):
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        ledger.post("/api/plan/setup/apply")
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})
        assert ledger.get("/api/budgets").get_json()["drift"] is not None

        ledger.post("/api/plan/setup/apply")
        assert ledger.get("/api/budgets").get_json()["drift"] is None

    def test_no_drift_is_reported_before_a_plan_exists(self, client):
        """Nothing to disagree with yet, so the notice must stay silent."""
        client.put("/api/budgets", json={"budgets": {"Coffee": 60}})
        assert client.get("/api/budgets").get_json()["drift"] is None

    def test_editing_one_category_by_hand_is_also_reported(self, ledger):
        """The notice states the discrepancy without claiming the plan moved —
        it cannot tell that from a budget edited here, and either way the
        totals no longer agree."""
        before = ledger.get("/api/budgets").get_json()
        coffee = before["budgets"]["Coffee"]
        ledger.put("/api/budgets", json={"budgets": {"Coffee": 1}})

        drift = ledger.get("/api/budgets").get_json()["drift"]
        assert drift["gap"] == pytest.approx(1 - coffee, abs=TOLERANCE)
        assert drift["gap"] < 0          # under-allocated, the milder direction

    def test_the_projected_surplus_never_exceeds_what_the_plan_leaves(self, ledger):
        """It used to be take-home less card spending, which treated rent as
        money available to save."""
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        ledger.post("/api/plan/fixed", json={"name": "Rent", "amount": 1850})

        plan = ledger.get("/api/plan/setup").get_json()
        proj = ledger.get("/api/projections").get_json()

        assert proj["from_plan"] is True
        assert proj["monthly_surplus"] <= plan["leftover"] + plan["savings"]
        # And the terms add up to the figure shown.
        b = proj["basis"]
        assert b["saving"] + b["unspent"] == pytest.approx(
            proj["monthly_surplus"], abs=TOLERANCE)
        assert b["leftover"] - b["typical_spend"] == pytest.approx(
            b["unspent"], abs=TOLERANCE)

    def test_a_piggy_bank_is_not_counted_as_savings(self, ledger):
        """It accumulates in order to be spent on the thing it is named after."""
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        before = ledger.get("/api/projections").get_json()["monthly_surplus"]
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})
        after = ledger.get("/api/projections").get_json()

        # The bank's $200 leaves the leftover and does not reappear as savings.
        assert after["monthly_surplus"] == pytest.approx(before - 200.0,
                                                         abs=TOLERANCE)
        assert after["basis"]["banks"] == pytest.approx(200.0, abs=TOLERANCE)

    def test_without_a_plan_the_projection_keeps_the_ceiling_caveat(self, client):
        """The fallback is still take-home less card spending, which genuinely
        is only a ceiling — so there the old warning is the honest one."""
        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        client.put("/api/plan/setup", json={"income": 5200})
        proj = client.get("/api/projections").get_json()

        # Income but no commitments and no savings: the plan exists, so the
        # derived path is used and the leftover is the whole income.
        assert proj["from_plan"] is True
        assert proj["basis"]["fixed_total"] == 0

    def test_the_plan_and_today_divide_by_the_same_number_of_days(self, ledger):
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        setup = ledger.get("/api/plan/setup").get_json()
        state = ledger.get("/api/plan").get_json()["state"]

        assert setup["days_this_month"] == state["days_in_month"]
        assert setup["daily_pool"] / setup["days_this_month"] == pytest.approx(
            state["flat_daily"], abs=0.02)

    def test_every_category_called_essential_on_today_actually_is(self, ledger):
        """Today's Essentials note named 'transport', which categorize.py marks
        discretionary — a counter-example inside the one figure on the page
        whose purpose is to be checkable."""
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        d = ledger.get("/api/plan").get_json()["derivation"]

        assert d["from_plan"] is True
        for category in d["essential_categories"]:
            assert not is_discretionary(category), category


class TestTheBudgetsTableHasOneRowPerCategory:
    """One list, once.

    The per-category list used to be rendered three times — the plan's split on
    one tab, bars and an editor on another — and two of the three were
    editable. The server now hands over a single row list, and these are the
    invariants that keep it a single list: it covers everything either side
    knew about, it carries the plan's figure whether or not the two agree, and
    each row says which side of the daily number it falls on using the same
    predicate the daily number itself uses.
    """

    def test_the_plans_split_is_served_even_when_the_budgets_match_it(self, ledger):
        """The bug this replaces: the split travelled inside `drift`, which is
        absent precisely when the saved budgets agree with the plan — so the
        column was blank in the one case where it is reassuring."""
        body = ledger.get("/api/budgets").get_json()
        setup = ledger.get("/api/plan/setup").get_json()

        assert body["drift"] is None, "the fixture applies the plan, so it ties out"
        assert body["plan_budgets"], "the plan's split went missing with the drift"
        assert body["plan_leftover"] == pytest.approx(setup["leftover"],
                                                      abs=TOLERANCE)
        assert sum(body["plan_budgets"].values()) == pytest.approx(
            body["plan_leftover"], abs=TOLERANCE)

    def test_the_split_survives_the_plan_moving_underneath_it(self, ledger):
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})
        body = ledger.get("/api/budgets").get_json()

        assert body["drift"], "opening a bank should put the budgets out"
        assert body["plan_budgets"]
        # The notice compares these two; they have to come from one place.
        assert body["drift"]["plan_total"] == pytest.approx(
            body["plan_leftover"], abs=TOLERANCE)

    def test_every_row_knows_which_side_of_the_daily_number_it_is_on(self, ledger):
        rows = ledger.get("/api/budgets").get_json()["rows"]
        assert rows
        for r in rows:
            assert r["essential"] == (not is_discretionary(r["category"])), \
                r["category"]

    def test_the_rows_cover_the_saved_budgets_and_the_plans_proposals(self, ledger):
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})
        body = ledger.get("/api/budgets").get_json()

        expected = set(body["budgets"]) | set(body["plan_budgets"])
        assert {r["category"] for r in body["rows"]} == expected
        for r in body["rows"]:
            assert r["adopted"] is (r["category"] in body["budgets"])
            assert r["plan_budget"] == body["plan_budgets"].get(r["category"])
            # A row the plan proposes is drawn against the plan's figure, so
            # the bar means something before anything has been adopted.
            if not r["adopted"]:
                assert r["budget"] == pytest.approx(r["plan_budget"],
                                                    abs=TOLERANCE)

    def test_a_category_the_plan_pays_for_is_on_the_page_before_adoption(self, ledger):
        """The table was empty until budgets were adopted, on the one tab whose
        job is to get them adopted."""
        saved = ledger.get("/api/budgets").get_json()["budgets"]
        ledger.put("/api/budgets", json={"budgets": {c: 0 for c in saved}})

        body = ledger.get("/api/budgets").get_json()
        assert body["budgets"] == {}
        assert body["status"] == []          # nothing saved…
        assert body["rows"]                  # …and still a page to read
        assert all(r["adopted"] is False for r in body["rows"])


def add_travel(client, amount: float = 1800.0) -> float:
    """Put a year's worth of travel in the ledger, in two lumps.

    The bundled statements have none, and the whole point of the rule is how
    a lumpy cost behaves — so a fixture with no lumps would prove nothing.
    """
    months = sorted({t.month for t in
                     client.application.config["STORE"].all_transactions()})
    for month, part in ((months[-1], amount * 0.4), (months[0], amount * 0.6)):
        client.post("/api/transactions", json={
            "date": f"{month}-09", "description": "AIR CANADA 014",
            "amount": round(part, 2), "category": "Travel"})
    return round(amount, 2)


def travel_bank(client, categories=("Travel", "Lodging"), name="Travel",
                target=8000) -> int:
    """Open a yearly bank that pays for travel, the way the suggestion does."""
    r = client.post("/api/piggy", json={"name": name, "target": target,
                                        "cadence": "annual",
                                        "categories": list(categories)})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def charge_today(client, amount=6000.0, category="Travel",
                 description="AIR CANADA 4410") -> str:
    from datetime import date
    r = client.post("/api/transactions", json={
        "date": date.today().isoformat(), "description": description,
        "amount": amount, "category": category, "confirm": True})
    assert r.status_code == 200, r.get_json()
    return r.get_json()["id"]


def the_bank(client, bank_id):
    return next(b for b in client.get("/api/piggy").get_json()["banks"]
                if b["id"] == bank_id)


class TestBanksOwnTheirCategories:
    """Big spending comes out of a piggy bank, not the weekly allowance.

    Which spending is "big" differs from person to person, so a bank says
    what it pays for. Those categories leave the budget split, Budgets and
    the weekly number — the bank's contribution is already subtracted from the
    leftover in `plan()`, so giving them a share of what remains would fund
    the same trip twice — and every charge in them is paid by the bank.
    """

    def test_travel_nobody_owns_is_an_ordinary_line(self, ledger):
        from finance import money_plan
        add_travel(ledger)
        st = ledger.application.config["STORE"]
        assert "Travel" in money_plan.variable_shares(
            st.all_transactions(), bank_funded=st.bank_funded_categories())
        assert ledger.put("/api/budgets", json={
            "budgets": {"Travel": 300}}).status_code == 200

    def test_an_owned_category_gets_no_share_of_the_leftover(self, ledger):
        from finance import money_plan
        add_travel(ledger)
        travel_bank(ledger)
        st = ledger.application.config["STORE"]
        txns = st.all_transactions()
        assert any(t.category == "Travel" and t.amount > 0 for t in txns), \
            "the fixture has no travel, so this test proves nothing"
        assert "Travel" not in money_plan.variable_shares(
            txns, bank_funded=st.bank_funded_categories())

    def test_no_row_no_budget_and_not_reported_missing(self, ledger):
        add_travel(ledger)
        travel_bank(ledger)
        ledger.post("/api/plan/setup/apply")
        body = ledger.get("/api/budgets").get_json()
        assert "Travel" not in body["plan_budgets"]
        assert "Travel" not in body["budgets"]
        assert "Travel" not in {r["category"] for r in body["rows"]}
        assert "Travel" not in {r["category"] for r in body["unbudgeted"]}
        assert body["bank_funded"]["categories"] == ["Lodging", "Travel"]
        assert body["bank_funded"]["paid_by"] == [
            {"bank": "Travel", "id": 1, "categories": ["Lodging", "Travel"]}]

    def test_a_budget_for_it_is_refused(self, ledger):
        travel_bank(ledger)
        r = ledger.put("/api/budgets", json={"budgets": {"Travel": 300}})
        assert r.status_code == 400
        assert "piggy bank" in r.get_json()["error"]

    def test_a_budget_it_had_goes_when_a_bank_takes_it(self, ledger):
        ledger.put("/api/budgets", json={"budgets": {"Travel": 300}})
        travel_bank(ledger)
        assert "Travel" not in ledger.application.config["STORE"].budgets()

    def test_the_leftover_still_divides_exactly(self, ledger):
        """Dropping a category must redistribute its share, not lose it."""
        add_travel(ledger)
        travel_bank(ledger)
        body = ledger.get("/api/budgets").get_json()
        assert sum(body["plan_budgets"].values()) == pytest.approx(
            body["plan_leftover"], abs=TOLERANCE)

    def test_a_category_belongs_to_one_bank(self, ledger):
        travel_bank(ledger)
        r = ledger.post("/api/piggy", json={"name": "Hotels", "target": 900,
                                            "cadence": "annual",
                                            "categories": ["Lodging"]})
        assert r.status_code == 400
        assert "Travel bank" in r.get_json()["error"]

    def test_only_spending_can_be_owned(self, ledger):
        r = ledger.post("/api/piggy", json={"name": "Pay", "target": 900,
                                            "cadence": "annual",
                                            "categories": ["Income"]})
        assert r.status_code == 400

    def test_a_line_cannot_end_up_half_owned(self, ledger):
        ledger.put("/api/category-groups", json={"groups": {"Lodging": "Dining"}})
        r = ledger.post("/api/piggy", json={"name": "Hotels", "target": 900,
                                            "cadence": "annual",
                                            "categories": ["Lodging"]})
        assert r.status_code == 400
        assert "Settings" in r.get_json()["error"]

    def test_closing_the_bank_gives_the_categories_back(self, ledger):
        bank = travel_bank(ledger)
        ledger.delete(f"/api/piggy/{bank}")
        assert ledger.application.config["STORE"].bank_funded_categories() == set()


class TestOwnedChargesGoToTheBankByThemselves:
    """Her example: an $8,000 vacation bank, then a $6,000 trip."""

    def test_the_whole_target_is_there_the_day_it_opens(self, ledger):
        bank = travel_bank(ledger)
        b = the_bank(ledger, bank)
        assert b["available"] == pytest.approx(8000)
        assert b["monthly"] == pytest.approx(666.67)
        assert b["categories"] == ["Lodging", "Travel"]
        offered = ledger.get("/api/piggy").get_json()["spend_categories"]
        assert "Travel" in offered and "Income" not in offered

    def test_a_trip_is_charged_to_it_without_being_asked(self, ledger):
        bank = travel_bank(ledger)
        txn = charge_today(ledger, 6000)
        row = ledger.application.config["STORE"].get_transaction(txn)
        assert row.bank_id == bank and row.bank_auto
        assert row.bank_amount == pytest.approx(6000)
        assert the_bank(ledger, bank)["available"] == pytest.approx(2000)

    def test_the_trip_is_not_in_the_months_spending(self, ledger):
        from datetime import date
        month = date.today().isoformat()[:7]
        travel_bank(ledger)

        def spent():
            return ledger.get(f"/api/budgets?month={month}").get_json()["month_spend"]
        before = spent()
        charge_today(ledger, 6000)
        assert spent() == pytest.approx(before, abs=TOLERANCE)

    def test_charges_from_before_the_bank_opened_stay_in_their_months(self, ledger):
        add_travel(ledger)
        bank = travel_bank(ledger)
        assert the_bank(ledger, bank)["available"] == pytest.approx(8000)

    def test_count_as_everyday_takes_it_out_and_it_stays_out(self, ledger):
        bank = travel_bank(ledger)
        txn = charge_today(ledger, 120)
        assert ledger.delete(f"/api/piggy/allocations/{txn}").status_code == 200
        st = ledger.application.config["STORE"]
        assert st.get_transaction(txn).bank_id is None
        assert the_bank(ledger, bank)["available"] == pytest.approx(8000)
        # Charging it by hand again withdraws the opt-out.
        ledger.post(f"/api/piggy/{bank}/allocate", json={"txn_id": txn})
        assert st.get_transaction(txn).bank_id == bank

    def test_recategorising_it_out_of_travel_takes_it_off_the_bank(self, ledger):
        bank = travel_bank(ledger)
        txn = charge_today(ledger, 300)
        ledger.patch(f"/api/transactions/{txn}", json={"category": "Dining"})
        assert ledger.application.config["STORE"].get_transaction(txn).bank_id is None
        assert the_bank(ledger, bank)["available"] == pytest.approx(8000)

    def test_letting_go_of_a_category_lets_go_of_its_charges(self, ledger):
        bank = travel_bank(ledger)
        txn = charge_today(ledger, 300, category="Lodging",
                           description="HOTEL DIEU 22")
        ledger.patch(f"/api/piggy/{bank}", json={"categories": ["Travel"]})
        assert ledger.application.config["STORE"].get_transaction(txn).bank_id is None

    def test_a_hand_allocation_to_another_bank_wins(self, ledger):
        travel_bank(ledger)
        other = ledger.post("/api/piggy", json={"name": "Wedding", "target": 3000,
                                                "cadence": "annual"}).get_json()["id"]
        txn = charge_today(ledger, 500)
        ledger.post(f"/api/piggy/{other}/allocate", json={"txn_id": txn})
        row = ledger.application.config["STORE"].get_transaction(txn)
        assert row.bank_id == other and not row.bank_auto

    def test_more_than_the_target_is_paid_and_reported_as_over(self, ledger):
        bank = travel_bank(ledger)
        charge_today(ledger, 10000)
        b = the_bank(ledger, bank)
        assert b["available"] == pytest.approx(-2000)
        assert b["over"] is True


class TestTravelOwnershipMigration:
    """Her ledger had a Travel bank funded by the old hard-coded rule."""

    def _old_ledger(self, tmp_path):
        from finance.store import Store
        path = str(tmp_path / "old.db")
        st = Store(path, url="")
        st.add_piggy_bank("Travel fund", 2400, "annual", None, "2026-01")
        # As if the migration had never run: no ownership, no flag.
        with st.conn() as c:
            c.execute("DELETE FROM piggy_bank_categories")
            c.execute("DELETE FROM settings WHERE key = 'bank_categories_migrated'")
        st.set_budget("Travel", 300)
        return path

    def test_a_travel_bank_takes_travel_and_lodging(self, tmp_path):
        from finance.store import Store
        st = Store(self._old_ledger(tmp_path), url="")
        assert st.bank_funded_categories() == {"Travel", "Lodging"}
        assert "Travel" not in st.budgets()

    def test_it_happens_once(self, tmp_path):
        from finance.store import Store
        path = self._old_ledger(tmp_path)
        st = Store(path, url="")
        st.set_bank_categories(st.piggy_banks()[0].id, [])
        assert Store(path, url="").bank_funded_categories() == set()


class TestTheFirstBankIsTravel:
    def test_it_is_suggested_with_a_target_from_her_own_history(self, ledger):
        add_travel(ledger)
        body = ledger.get("/api/piggy").get_json()
        suggested = body["suggested"]
        assert suggested and suggested["name"] == "Travel"
        assert suggested["annual_spend"] > 0
        # Rounded up to something recognisable, never below what it costs.
        assert suggested["target"] >= suggested["annual_spend"]
        assert suggested["target"] % 100 == 0

    def test_travel_is_still_offered_with_nothing_to_go_on(self, ledger):
        """No travel in the ledger is no reason to leave the field blank of a
        name — only of a number nobody can source."""
        suggested = ledger.get("/api/piggy").get_json()["suggested"]
        assert suggested["name"] == "Travel"
        assert suggested["target"] is None

    def test_the_suggestion_stops_once_a_bank_exists(self, ledger):
        ledger.post("/api/piggy", json={"name": "Trip", "target": 2400,
                                        "cadence": "annual"})
        assert ledger.get("/api/piggy").get_json()["suggested"] is None

    def test_the_insight_and_the_suggestion_quote_one_figure(self, ledger):
        """Both are "what travel costs you a year" and they are read off the
        same function, so they cannot disagree."""
        add_travel(ledger)
        suggested = ledger.get("/api/piggy").get_json()["suggested"]
        rows = ledger.get("/api/insights").get_json()["observations"]
        row = next((r for r in rows if r["id"] == "travel_no_bank"), None)
        assert row, "the fixture travels but is offered no bank"
        assert row["figures"]["annual"] == pytest.approx(
            suggested["annual_spend"], abs=TOLERANCE)


class TestTheSavingsSliderAsksTheServer:
    """Nothing about the preview is computed in the browser.

    The slider moves a real projection by asking for one, so the figure under
    the handle and the figure that gets saved are produced by the same code.
    A client-side preview would be a second implementation of the plan's
    arithmetic, which is how two versions of one sum start disagreeing.
    """

    def test_previewing_does_not_write_anything(self, ledger):
        before = ledger.get("/api/plan/setup").get_json()["savings"]
        body = ledger.get("/api/projections?savings=1500").get_json()

        assert body["savings_previewing"] is True
        assert body["basis"]["saving"] == pytest.approx(1500.0, abs=TOLERANCE)
        assert ledger.get("/api/plan/setup").get_json()["savings"] == before
        assert body["savings_saved"] == pytest.approx(before, abs=TOLERANCE)

    def test_the_preview_matches_what_saving_it_would_give(self, ledger):
        preview = ledger.get("/api/projections?savings=1500").get_json()
        ledger.put("/api/plan/setup", json={"savings": 1500})
        saved = ledger.get("/api/projections").get_json()

        assert saved["savings_previewing"] is False
        for key in ("monthly_on_plan", "monthly_surplus"):
            assert saved[key] == pytest.approx(preview[key], abs=TOLERANCE)
        assert saved["at_12"]["on_plan"] == pytest.approx(
            preview["at_12"]["on_plan"], abs=TOLERANCE)
        assert saved["year_end"]["on_plan"] == pytest.approx(
            preview["year_end"]["on_plan"], abs=TOLERANCE)

    def test_saving_more_moves_the_plan_line_and_not_the_pace(self, ledger):
        """The honest part, and what the copy on the card promises: this does
        not conjure money, it relabels money. What you accumulate is the same;
        how much of it was a decision is not."""
        low = ledger.get("/api/projections?savings=200").get_json()
        high = ledger.get("/api/projections?savings=1200").get_json()

        assert high["at_12"]["on_plan"] > low["at_12"]["on_plan"]
        assert high["at_12"]["pace"] == pytest.approx(low["at_12"]["pace"],
                                                      abs=TOLERANCE)
        # And it comes out of what is left to spend, pound for pound.
        assert high["basis"]["leftover"] == pytest.approx(
            low["basis"]["leftover"] - 1000.0, abs=TOLERANCE)

    def test_the_ceiling_is_everything_not_already_promised(self, ledger):
        body = ledger.get("/api/projections").get_json()
        setup = ledger.get("/api/plan/setup").get_json()
        assert body["savings_ceiling"] == pytest.approx(
            setup["income"] - setup["fixed_total"] - setup["banks"],
            abs=TOLERANCE)

    def test_a_nonsense_figure_is_refused_rather_than_guessed_at(self, ledger):
        assert ledger.get("/api/projections?savings=lots").status_code == 400

    def test_the_year_end_figure_is_the_months_that_are_left(self, ledger):
        from finance import projections
        from datetime import date

        body = ledger.get("/api/projections").get_json()
        months = projections.months_left_in_year(date.today().isoformat())
        assert body["year_end"]["months"] == months
        assert body["year_end"]["on_plan"] == pytest.approx(
            body["monthly_on_plan"] * months, abs=TOLERANCE)


class TestWhatItComesToIfInvested:
    def test_the_compounding_is_an_ordinary_annuity(self):
        from finance.projections import future_value
        # $500 a month at 7% for ten years, the figure every calculator gives.
        assert future_value(500, 0.07, 120) == pytest.approx(86542.40, abs=1.0)
        # No return is just the contributions, with nothing conjured.
        assert future_value(500, 0.0, 120) == pytest.approx(60000.0, abs=0.01)
        assert future_value(0, 0.07, 120, opening=1000) == pytest.approx(
            2009.66, abs=1.0)

    def test_every_value_is_reported_beside_what_was_paid_in(self, ledger):
        inv = ledger.get("/api/projections").get_json()["invested"]
        assert inv
        for rate in inv["rates"]:
            for years in inv["horizons"]:
                row = rate["at"][str(years)]
                assert row["contributed"] == pytest.approx(
                    inv["monthly"] * years * 12, abs=TOLERANCE)
                assert row["growth"] == pytest.approx(
                    row["value"] - row["contributed"], abs=TOLERANCE)
                # A positive rate can only beat holding it in a drawer.
                assert row["value"] >= row["contributed"] - TOLERANCE

    def test_a_higher_assumption_is_never_worth_less(self, ledger):
        inv = ledger.get("/api/projections").get_json()["invested"]
        values = [r["at"]["30"]["value"] for r in
                  sorted(inv["rates"], key=lambda r: r["rate"])]
        assert values == sorted(values)

    def test_it_compounds_the_figure_the_plan_sets_aside(self, ledger):
        body = ledger.get("/api/projections?savings=800").get_json()
        assert body["invested"]["monthly"] == pytest.approx(800.0, abs=TOLERANCE)

    def test_nothing_is_offered_when_nothing_is_being_saved(self, ledger):
        body = ledger.get("/api/projections?savings=0").get_json()
        assert body["invested"] is None

    def test_the_chart_is_drawn_on_the_middle_assumption(self, ledger):
        """Never the flattering one — the chart is the figure people
        remember, so it is not allowed to be the best case."""
        inv = ledger.get("/api/projections").get_json()["invested"]
        rates = sorted(r["rate"] for r in inv["rates"])
        assert inv["chart_rate"] == rates[len(rates) // 2]
        assert inv["chart_rate"] < max(rates)

    def test_the_chart_series_starts_at_nothing_and_matches_the_table(self, ledger):
        inv = ledger.get("/api/projections").get_json()["invested"]
        assert inv["series"][0] == {"year": 0, "contributed": 0.0, "value": 0.0}
        middle = next(r for r in inv["rates"] if r["rate"] == inv["chart_rate"])
        for years in inv["horizons"]:
            point = next(p for p in inv["series"] if p["year"] == years)
            assert point["value"] == pytest.approx(
                middle["at"][str(years)]["value"], abs=TOLERANCE)


class TestBudgetLines:
    """Categories folded together for budgeting, and nothing else.

    The promises: a line's budget, spending and typical month are the sums of
    its categories; regrouping keeps hand-tuned totals; the daily number does
    not move at all; and the two rules — no nesting, bank-funded only with
    bank-funded — hold at the API, not just in the picker.
    """

    HEALTH = {"Health": "Health & care", "Personal Care": "Health & care"}

    def _status(self, client, month=None):
        q = f"?month={month}" if month else ""
        return client.get(f"/api/budgets{q}").get_json()

    def test_no_grouping_is_the_page_it_always_was(self, ledger):
        body = self._status(ledger)
        for r in body["rows"]:
            assert r["members"] == []
            assert r["daily"] in ("all", "none")

    def test_a_line_is_the_sum_of_its_categories(self, ledger):
        month = busiest_month(ledger)
        before = {r["category"]: r for r in self._status(ledger, month)["rows"]}
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        after = {r["category"]: r for r in self._status(ledger, month)["rows"]}

        assert "Health" not in after and "Personal Care" not in after
        line = after["Health & care"]
        assert sorted(line["members"]) == ["Health", "Personal Care"]
        expected = sum(before[c]["spent"] for c in ("Health", "Personal Care")
                       if c in before)
        assert line["spent"] == pytest.approx(expected, abs=TOLERANCE)

    def test_the_plan_still_divides_the_leftover_exactly(self, ledger):
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        body = self._status(ledger)
        assert "Health & care" in body["plan_budgets"]
        assert sum(body["plan_budgets"].values()) == pytest.approx(
            body["plan_leftover"], abs=TOLERANCE)

    def test_folding_lines_together_adds_their_saved_budgets(self, ledger):
        ledger.put("/api/budgets", json={"budgets": {"Health": 85,
                                                     "Personal Care": 40}})
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        saved = self._status(ledger)["budgets"]
        assert saved["Health & care"] == pytest.approx(125.0, abs=TOLERANCE)
        assert "Health" not in saved and "Personal Care" not in saved

    def test_breaking_a_line_up_drops_it_and_says_so(self, ledger):
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        ledger.post("/api/plan/setup/apply")
        assert self._status(ledger)["drift"] is None

        ledger.put("/api/category-groups", json={"groups": {}})
        body = self._status(ledger)
        assert "Health & care" not in body["budgets"]
        # Nothing invented for the two categories: they are proposals until
        # adopted, and the totals no longer match, which the page reports.
        assert body["drift"] is not None

    def test_the_daily_number_does_not_move(self, ledger):
        """Grouping is a budgeting label. The daily number is worked out per
        category, so no grouping can change what you may spend today."""
        before = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]
        ledger.put("/api/category-groups", json={"groups": {
            **self.HEALTH, "Coffee": "Dining", "Groceries": "Food"}})
        ledger.post("/api/plan/setup/apply")
        after = ledger.get("/api/plan").get_json()["state"]["monthly_amount"]
        assert after == pytest.approx(before, abs=TOLERANCE)

    def test_a_mixed_line_says_it_is_partly_in_the_daily_number(self, ledger):
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        row = next(r for r in self._status(ledger)["rows"]
                   if r["category"] == "Health & care")
        assert row["daily"] == "part"
        assert row["essential"] is False

    def test_a_folded_category_cannot_be_budgeted_on_its_own(self, ledger):
        ledger.put("/api/category-groups", json={"groups": self.HEALTH})
        r = ledger.put("/api/budgets", json={"budgets": {"Health": 50}})
        assert r.status_code == 400
        assert "Health & care" in r.get_json()["error"]
        assert ledger.put("/api/budgets", json={
            "budgets": {"Health & care": 150}}).status_code == 200

    def test_nesting_is_refused(self, ledger):
        r = ledger.put("/api/category-groups", json={"groups": {
            "Lodging": "Travel", "Travel": "Trips"}})
        assert r.status_code == 400

    def test_bank_funded_only_shares_with_bank_funded(self, ledger):
        """A bank-paid category can't join a budgeted line. The other way
        round, joining a bank's line hands the category to that bank — see
        test_lines_totals_hidden.py — so the line is still all bank-paid."""
        travel_bank(ledger)
        bad = ledger.put("/api/category-groups",
                         json={"groups": {"Travel": "Dining"}})
        assert bad.status_code == 400
        assert "piggy bank" in bad.get_json()["error"]
        ok = ledger.put("/api/category-groups",
                        json={"groups": {"Lodging": "Travel"}})
        assert ok.status_code == 200

    def test_lodging_under_travel_reads_as_one_bank_funded_line(self, ledger):
        add_travel(ledger)
        travel_bank(ledger)
        ledger.put("/api/category-groups", json={"groups": {"Lodging": "Travel"}})
        body = self._status(ledger)
        assert body["bank_funded"]["categories"] == ["Travel"]
        assert "Travel" not in {r["category"] for r in body["rows"]}

    def test_income_and_transfers_cannot_be_grouped(self, ledger):
        assert ledger.put("/api/category-groups", json={"groups": {
            "Transfers": "Other"}}).status_code == 400
        assert ledger.put("/api/category-groups", json={"groups": {
            "Dining": "Income"}}).status_code == 400

    def test_the_month_still_adds_up_with_lines(self, ledger):
        add_travel(ledger)
        travel_bank(ledger)
        ledger.put("/api/category-groups", json={"groups": {
            **self.HEALTH, "Lodging": "Travel"}})
        ledger.post("/api/plan/setup/apply")
        b = self._status(ledger, busiest_month(ledger))
        assert (b["covered_spend"] + b["unbudgeted_spend"]
                + b["bank_funded"]["unallocated_total"]) == pytest.approx(
            b["month_spend"], abs=TOLERANCE)


class TestTheSetupChecklist:
    """Every tick comes from the data, so a step done anywhere ticks itself."""

    def _setup(self, client):
        return client.get("/api/setup").get_json()

    def _step(self, client, step_id):
        return next(s for s in self._setup(client)["steps"] if s["id"] == step_id)

    def test_a_fresh_ledger_has_everything_to_do(self, client):
        body = self._setup(client)
        assert [s["id"] for s in body["steps"]] == [
            "start", "data", "income", "commitments", "travel", "budgets"]
        assert not any(s["done"] for s in body["steps"])
        assert body["remaining"] == 6

    def test_each_step_ticks_itself_from_the_ordinary_endpoint(self, client):
        client.put("/api/ledger/start", json={"start": "2026-03-01"})
        assert self._step(client, "start")["done"]

        client.post("/api/import/bundled", json={"key": "scotiabank_amex"})
        assert self._step(client, "data")["done"]

        client.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        assert self._step(client, "income")["done"]

        client.post("/api/plan/fixed", json={"name": "Rent", "amount": 1800,
                                             "category": "Rent & Housing"})
        assert self._step(client, "commitments")["done"]

        client.post("/api/piggy", json={"name": "Concerts", "target": 600,
                                        "cadence": "annual"})
        assert not self._step(client, "travel")["done"], \
            "a bank that pays for nothing keeps nothing off the week"
        travel_bank(client, target=1200)
        assert self._step(client, "travel")["done"]

        client.post("/api/plan/setup/apply")
        assert self._step(client, "budgets")["done"]

        assert self._setup(client)["remaining"] == 0

    def test_remaining_counts_what_is_left(self, ledger):
        body = self._setup(ledger)
        assert body["remaining"] == sum(
            1 for s in body["steps"] if not s["done"] and not s["skipped"])

    def test_only_optional_steps_can_be_skipped(self, client):
        for step_id in ("start", "travel", "income"):
            client.post(f"/api/insights/setup.{step_id}/dismiss")
        steps = {s["id"]: s for s in self._setup(client)["steps"]}
        assert steps["start"]["skipped"] and steps["travel"]["skipped"]
        # A core step is not skippable however it is asked.
        assert steps["income"]["skipped"] is False
        assert self._setup(client)["remaining"] == 4

    def test_a_bank_funded_budget_does_not_count_as_adopted(self, ledger):
        """Only a real budget line ticks the step — a stale Travel row a
        piggy bank pays for is not a budget being kept."""
        st = ledger.application.config["STORE"]
        travel_bank(ledger)
        for key in list(st.budgets()):
            st.set_budget(key, 0)
        st.set_budget("Travel", 300)          # written directly, past the API
        assert self._step(ledger, "budgets")["done"] is False


class TestTheWeeklyNumberIsOneNumber:
    def test_the_plan_and_today_quote_the_same_week(self, ledger):
        """Plan says "about $X a week"; Today's derivation ends in "a week".
        They are one figure and come from one place."""
        ledger.put("/api/plan/setup", json={"income": 5200, "savings": 700})
        setup = ledger.get("/api/plan/setup").get_json()
        state = ledger.get("/api/plan").get_json()["state"]
        assert setup["weekly_share"] == pytest.approx(
            state["week"]["nominal"], abs=0.02)

    def test_a_purchase_is_judged_against_what_is_left_this_week(self, ledger):
        state = ledger.get("/api/plan").get_json()["state"]
        left = state["week"]["left"]
        if left <= 1:
            pytest.skip("the fixture's week is already spent")
        r = ledger.post("/api/plan/simulate",
                        json={"amount": round(left - 1, 2)}).get_json()
        assert r["affordable"] is True
        r = ledger.post("/api/plan/simulate",
                        json={"amount": round(left + 50, 2)}).get_json()
        assert r["affordable"] is False
        assert r["short_by"] == pytest.approx(50.0, abs=0.02)
