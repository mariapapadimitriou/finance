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
from ledger_files import add_fixed, load_bundled, set_plan

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
    """A ledger with income, a saving goal and rent on it."""
    load_bundled(client)
    set_plan(client, income=5200, savings=900)
    add_fixed(client, "Rent", 2100, "Rent & Housing")
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


def insights_total(client, month: str) -> float:
    """What Growth › Insights says the month cost, across its categories."""
    where = client.get(f"/api/insights/month?month={month}").get_json()["where"]
    return sum(c["amount"] for g in where["groups"] for c in g["categories"]) / 100


class TestOneMonthOneNumber:
    """What the month cost, according to each tab that says so."""

    def test_overview_insights_and_the_ledger_agree(self, ledger):
        month = busiest_month(ledger)
        truth = ledger_spend(ledger, month)

        monthly = ledger.get("/api/summary").get_json()["monthly"]
        overview = next(r["spend"] for r in monthly if r["month"] == month)
        breakdown = insights_total(ledger, month)

        assert overview == pytest.approx(truth, abs=TOLERANCE)
        assert breakdown == pytest.approx(truth, abs=TOLERANCE)


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


class TestNumbersMoveTogetherWhenThingsChange:
    """The part that actually breaks: consistency after an edit."""

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
        breakdown = insights_total(ledger, month)
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
        breakdown = insights_total(ledger, month)
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
        breakdown = insights_total(ledger, month)
        assert breakdown == pytest.approx(after, abs=TOLERANCE)
        accounts = round(sum(a["total_spend"] for a in ledger.get(
            "/api/accounts").get_json()["accounts"]), 2)
        assert accounts == pytest.approx(
            ledger.get("/api/summary").get_json()["total_spend"], abs=TOLERANCE)



class TestDerivedFiguresAgreeWithTheirParts:
    def test_subscriptions_annual_is_twelve_monthlies(self, ledger):
        s = ledger.get("/api/recurring").get_json()["summary"]
        assert s["annual_total"] == pytest.approx(s["monthly_total"] * 12, abs=1.0)

    def test_the_split_adds_up_to_the_month(self, ledger):
        split = ledger.get("/api/summary").get_json()["split"]
        assert split["discretionary"] + split["fixed"] == pytest.approx(
            split["total"], abs=TOLERANCE)


class TestOneFigureOneName:
    """The same quantity quoted on two tabs has to be the same quantity."""

    def test_the_summary_keeps_both_names_pointing_at_one_number(self, ledger):
        summary = ledger.get("/api/summary").get_json()
        assert summary["average_monthly_spend"] == summary["typical_monthly_spend"]

    def test_the_month_against_typical_is_the_difference_shown(self, ledger):
        summary = ledger.get("/api/summary").get_json()
        assert summary["vs_average"] == pytest.approx(
            summary["latest_spend"] - summary["typical_monthly_spend"], abs=TOLERANCE)


class TestHeadlinesMatchTheirLists:

    def test_the_subscription_tiles_are_the_sum_of_the_rows(self, ledger):
        body = ledger.get("/api/recurring").get_json()
        active = [r for r in body["recurring"] if r["active"]]
        assert body["summary"]["monthly_total"] == pytest.approx(
            round(sum(r["monthly_cost"] for r in active), 2), abs=TOLERANCE)
        assert body["summary"]["annual_total"] == pytest.approx(
            round(sum(r["annual_cost"] for r in active), 2), abs=TOLERANCE)

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

    def test_a_budget_it_had_goes_when_a_bank_takes_it(self, ledger):
        ledger.application.config["STORE"].set_budget("Travel", 300)
        travel_bank(ledger)
        assert "Travel" not in ledger.application.config["STORE"].budgets()

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
            monthly = ledger.get("/api/summary").get_json()["monthly"]
            return next((m["spend"] for m in monthly if m["month"] == month), 0.0)
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


