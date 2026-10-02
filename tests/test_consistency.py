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
        """Budgeted plus unbudgeted is the month, with nothing unexplained."""
        month = busiest_month(ledger)
        b = ledger.get(f"/api/budgets?month={month}").get_json()
        assert b["covered_spend"] + b["unbudgeted_spend"] == pytest.approx(
            b["month_spend"], abs=TOLERANCE)
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
