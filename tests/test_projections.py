"""Growth › Projections and Unveil (Pearl THL-197 GR-33 to GR-37, THL-135
GR-16): the month-end forecast, the next 30 days, savings in a year, and
"Opened an investing account?" making the path's Unveil step done.

Every projection is a range, never one figure, and everything is in cents.
"""

from __future__ import annotations

from datetime import date

import pytest

from finance import look_ahead as la
from finance import milestones, safe_to_spend as sts
from finance.models import Transaction
from test_safe_to_spend import TODAY, history, october, tx

BILLS = set()


def spend(day, amount, category="Dining", merchant="Pai"):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant,
                       amount=amount, category=category, account_id="visa")


# ── This month (GR-34) ────────────────────────────────────────────────────

class TestTheRestOfTheMonth:
    MONTHS = ["2026-07", "2026-08", "2026-09"]

    def rows(self):
        # After the 9th: $300 in July, $400 in August, $500 in September;
        # what came before the 9th never counts toward the rest.
        return [spend("2026-07-03", 999), spend("2026-07-20", 300),
                spend("2026-08-15", 150), spend("2026-08-28", 250),
                spend("2026-09-30", 500), spend("2026-09-09", 77)]

    def test_quietest_to_busiest_of_her_usual_months(self):
        rest = la.rest_of_month(self.rows(), TODAY, self.MONTHS, BILLS)
        assert (rest["low"], rest["high"], rest["basis"]) == (30000, 50000, "usual")

    def test_bills_are_left_out_because_they_are_counted_by_name(self):
        rows = self.rows() + [spend("2026-09-21", 60, "Utilities", "Hydro One")]
        rest = la.rest_of_month(rows, TODAY, self.MONTHS, {("Hydro One", "2026-09-21")})
        assert rest["high"] == 50000

    def test_with_no_full_month_this_months_pace_is_carried_on(self):
        # $90 over nine days is $10 a day; 22 days left is $220, ±15%.
        rows = [spend("2026-10-02", 90)]
        rest = la.rest_of_month(rows, TODAY, [], BILLS)
        assert rest["basis"] == "this_month"
        assert (rest["low"], rest["high"]) == (18700, 25300)

    def test_one_month_is_still_a_range(self):
        rest = la.rest_of_month(self.rows(), TODAY, ["2026-08"], BILLS)
        assert rest["low"] < 40000 < rest["high"]


def sts_for(income=4000.0, spent=1760.0, set_aside=0.0, bills=()):
    rows = [{"key": "income", "amount": income, "lines": []},
            {"key": "bills", "amount": sum(b["amount"] for b in bills), "lines": list(bills)},
            {"key": "spent", "amount": spent, "lines": []}]
    if set_aside:
        rows.append({"key": "set_aside", "amount": set_aside, "lines": []})
    return {"rows": rows}


class TestMonthEnd:
    MONTHS = ["2026-07", "2026-08", "2026-09"]

    def rows(self):
        return TestTheRestOfTheMonth().rows() + [spend("2026-10-02", 1760)]

    def test_spent_plus_bills_plus_the_rest_rounded_outwards(self):
        bills = [{"label": "Phone", "date": "2026-10-18", "amount": 65.0, "confirmed": True}]
        f = la.month_end(self.rows(), TODAY, sts_for(bills=bills), self.MONTHS, BILLS)
        # 1,760 + 65 + 300 = 2,125 → $2,120; 1,760 + 65 + 500 = 2,325 → $2,330.
        assert f["spend"] == {"low": 212000, "high": 233000}
        assert f["can_spend"] == 400000
        assert f["left"] == {"low": 400000 - 233000, "high": 400000 - 212000}
        assert f["state"] == "ok"
        assert f["bills_ahead"] == [{"date": "2026-10-18", "label": "Phone", "amount": 6500,
                                     "confirmed": True}]

    def test_what_you_can_spend_is_income_less_what_she_sets_aside(self):
        f = la.month_end(self.rows(), TODAY, sts_for(set_aside=300.0), self.MONTHS, BILLS)
        assert f["can_spend"] == 370000

    def test_running_over_is_a_state_not_a_negative_figure_to_show(self):
        f = la.month_end(self.rows(), TODAY, sts_for(income=2000.0), self.MONTHS, BILLS)
        assert f["state"] == "over" and f["left"]["high"] < 0
        tight = la.month_end(self.rows(), TODAY, sts_for(income=2200.0), self.MONTHS, BILLS)
        assert tight["state"] == "tight"

    def test_without_income_there_is_a_spend_range_and_nothing_left_to_quote(self):
        f = la.month_end(self.rows(), TODAY, {"rows": []}, self.MONTHS, BILLS, spent_c=176000)
        assert f["state"] == "no_income" and f["left"] is None
        assert f["spend"]["low"] < f["spend"]["high"]

    def test_the_line_runs_from_the_first_to_today(self):
        f = la.month_end(self.rows(), TODAY, sts_for(), self.MONTHS, BILLS)
        assert [p["day"] for p in f["line"]] == list(range(1, 10))
        assert f["line"][-1]["spent"] == 176000

    def test_an_empty_ledger_says_so(self):
        f = la.month_end([], TODAY, sts_for(spent=0.0), [], BILLS, spent_c=0)
        assert f["state"] == "none"


# ── The next 30 days (GR-35) ──────────────────────────────────────────────

class TestTheNext30Days:
    PER_DAY = {"low": 1500, "high": 2500, "usual": 2000}

    def run(self, balance=150000, **kw):
        paydays = kw.pop("paydays", [{"date": "2026-11-01", "label": "Northwind", "amount": 420000}])
        bills = kw.pop("bills", [
            {"date": "2026-10-18", "label": "Phone", "amount": 6500, "confirmed": True},
            {"date": "2026-11-01", "label": "Rent", "amount": 145000, "confirmed": True},
            {"date": "2026-11-05", "label": "Car insurance", "amount": 14200, "confirmed": False},
            {"date": "2026-12-01", "label": "Too far", "amount": 100, "confirmed": True},
        ])
        return la.next_30_days(TODAY, balance_c=balance, paydays=paydays, bills=bills,
                               per_day=self.PER_DAY, **kw)

    def test_the_lowest_point_is_the_day_before_payday(self):
        n = self.run()
        # 22 days at $20, less the $65 phone bill: 1,500 − 440 − 65 = $995.
        assert n["lowest"]["date"] == "2026-10-31"
        assert n["lowest"]["amount"] == 100000          # "about $1,000"
        assert n["lowest"]["before_payday"] is True
        assert n["lowest"]["low"] < n["lowest"]["amount"] < n["lowest"]["high"]
        assert n["state"] == "covered"

    def test_payday_and_rent_land_together(self):
        n = self.run()
        nov1 = next(s for s in n["series"] if s["date"] == "2026-11-01")
        oct31 = next(s for s in n["series"] if s["date"] == "2026-10-31")
        assert nov1["balance"] - oct31["balance"] == 420000 - 145000 - 2000

    def test_the_timeline_holds_the_window_and_marks_unconfirmed_bills(self):
        n = self.run()
        labels = [e["label"] for e in n["events"]]
        assert "Too far" not in labels
        assert labels.index("Northwind") < labels.index("Rent")      # paydays first on a day
        car = next(e for e in n["events"] if e["label"] == "Car insurance")
        assert car["confirmed"] is False and car["kind"] == "bill"
        assert len(n["series"]) == 31 and n["series"][0]["balance"] == 150000

    def test_running_short_is_said_as_a_state(self):
        n = self.run(balance=20000)
        assert n["state"] == "short"

    def test_no_chequing_balance_still_shows_whats_coming(self):
        n = self.run(balance=None)
        assert n["state"] == "no_balance" and n["series"] == [] and n["lowest"] is None
        assert n["events"]

    def test_everyday_spending_a_day_leaves_bills_out(self):
        rows = [spend("2026-09-10", 300), spend("2026-09-01", 2000, "Rent & Housing", "Landlord")]
        per = la.everyday_per_day(rows, TODAY, ["2026-09"], {("Landlord", "2026-09-01")})
        assert per["usual"] == 1000                     # $300 over September's 30 days
        assert per["low"] < per["usual"] < per["high"]


# ── Savings in a year (GR-36) ─────────────────────────────────────────────

PACE = {"used": [{"month": "2026-07", "saved": 100.0}, {"month": "2026-08", "saved": 150.0},
                 {"month": "2026-09", "saved": 200.0}],
        "best": {"month": "2026-09", "saved": 200.0},
        "quietest": {"month": "2026-07", "saved": 100.0}, "usual": 150.0, "left_out": []}


class TestSavingsInAYear:
    def test_twelve_months_of_her_quietest_to_her_best(self):
        s = la.savings_in_a_year(TODAY, now_c=205000, pace=PACE)
        # 2,050 + 12 × 100 = 3,250 → $3,200; 2,050 + 12 × 200 = 4,450 → $4,500.
        assert s["current"] == {"low": 320000, "high": 450000}
        assert s["by"] == "2027-10" and s["what_if"] is None and s["state"] == "ok"

    def test_the_what_if_moves_both_ends(self):
        s = la.savings_in_a_year(TODAY, now_c=205000, pace=PACE, extra_c=5000)
        assert s["what_if"] == {"low": 380000, "high": 510000}

    def test_a_month_that_took_money_out_counts_as_nothing_saved(self):
        pace = {**PACE, "quietest": {"month": "2026-07", "saved": -80.0}}
        s = la.savings_in_a_year(TODAY, now_c=100000, pace=pace)
        assert s["current"]["low"] == 100000

    def test_no_pace_yet(self):
        s = la.savings_in_a_year(TODAY, now_c=0, pace=None)
        assert s["state"] == "no_history" and s["current"] == {"low": 0, "high": 0}

    def test_chests_that_open_within_the_year_are_marked(self):
        chests = [{"name": "New laptop", "ready_by": "2027-03", "target": 1500},
                  {"name": "Trip chest", "ready_by": "2027-06", "target": 900},
                  {"name": "Later", "ready_by": "2028-01", "target": 100}]
        s = la.savings_in_a_year(TODAY, now_c=0, pace=PACE, chests=chests)
        assert [o["label"] for o in s["opens"]] == ["New laptop chest opens", "Trip chest opens"]
        both = la.savings_in_a_year(TODAY, now_c=0, pace=PACE, chests=[
            {"name": "New laptop", "ready_by": "2027-04", "target": 1500},
            {"name": "Trip chest", "ready_by": "2027-04", "target": 900}])
        assert both["opens"] == [{"month": "2027-04", "label": "New laptop chest and Trip chest open"}]


# ── Unveil: the self-report and the checklist (GR-37, GR-16) ──────────────

ANCHOR_FULL = {"started": True, "first_stop_done": True, "earned": True,
               "first_stop": 500, "target": 2335}


class TestUnveilOnThePath:
    def path(self, **kw):
        rows = history() + october()
        s = sts.compute(rows, TODAY, savings_target=300.0)
        return milestones.path(rows, TODAY, s, anchor=ANCHOR_FULL, bills_found=5, **kw)

    def test_her_word_makes_the_step_done(self):
        before = self.path()
        assert before["phase"] == "unveil" and before["steps"][0]["done"] is False
        after = self.path(invest_reported=True)
        assert after["steps"][0]["done"] is True
        assert after["next"]["text"] == "Every step on your path is done."

    def test_a_linked_investment_account_still_does(self):
        p = self.path(account_types={"rrsp": "investment"})
        assert p["steps"][0]["done"] is True

    def test_card_balances_checked_over_three_months(self):
        rows = [spend("2026-08-12", 85), spend("2026-08-20", -85, "Transfers", "Payment"),
                spend("2026-09-12", 85)]
        steady = milestones.cards_steady(rows, ["2026-07", "2026-08", "2026-09"], {"visa"})
        assert steady["done"] is False and steady["grew_in"] == "2026-09"
        assert milestones.cards_steady(rows, ["2026-07", "2026-08"], {"visa"})["done"] is True


# ── The endpoints ─────────────────────────────────────────────────────────

@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    app = create_app(str(tmp_path / "projections.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def ledger(c):
    c.application.config["STORE"].add_transactions(history() + october())
    r = c.post("/api/accounts/manual", json={"name": "Everyday", "kind": "chequing",
                                             "balance": 1500})
    assert r.status_code in (200, 201), r.get_json()


def ranges(node):
    """Every {low, high} in a payload."""
    if isinstance(node, dict):
        if set(node) >= {"low", "high"}:
            yield node
        for v in node.values():
            yield from ranges(v)
    elif isinstance(node, list):
        for v in node:
            yield from ranges(v)


class TestTheEndpoint:
    def test_an_empty_ledger_answers_with_states_not_zeros(self, client):
        d = client.get("/api/projections").get_json()
        assert d["empty"] is True
        assert d["anchor"]["state"] == "not_started"
        assert d["forecast"]["state"] in ("none", "no_income")
        assert d["next30"]["state"] == "no_balance"
        assert d["savings"]["state"] == "no_history"

    def test_a_ledger_gets_ranges_in_whole_cents(self, client):
        ledger(client)
        d = client.get("/api/projections?extra=50").get_json()
        assert d["forecast"]["state"] in ("ok", "tight", "over")
        assert d["next30"]["balance"] == 150000 and d["next30"]["lowest"]
        assert d["savings"]["extra"] == 5000
        for r in ranges(d):
            assert isinstance(r["low"], int) and isinstance(r["high"], int)
            assert r["low"] <= r["high"]

    def test_the_next_30_days_reads_paydays_and_bills(self, client):
        ledger(client)
        n = client.get("/api/projections").get_json()["next30"]
        kinds = {e["kind"] for e in n["events"]}
        assert kinds == {"payday", "bill"}
        assert any(e["label"] == "Parkside Properties" for e in n["events"])

    def test_a_joint_chequing_account_counts_her_share(self, client):
        ledger(client)
        st = client.application.config["STORE"]
        aid = st.manual_accounts()[0]["account_id"]
        st.set_joint_share(aid, 50)
        assert client.get("/api/projections").get_json()["next30"]["balance"] == 75000

    @pytest.mark.parametrize("extra", ["lots", "-5", "20000"])
    def test_a_nonsense_what_if_is_refused(self, client, extra):
        assert client.get(f"/api/projections?extra={extra}").status_code == 400

    def test_use_this_pace_sets_what_is_set_aside(self, client):
        ledger(client)
        r = client.put("/api/projections/pace", json={"monthly": 250})
        assert r.status_code == 200 and r.get_json()["saving_goal"] == 25000
        rows = client.get("/api/home").get_json()["safe_to_spend"]["rows"]
        assert next(x for x in rows if x["key"] == "set_aside")["target"] == 250
        assert client.put("/api/projections/pace", json={"monthly": 0}).status_code == 400


class TestUnveilEndpoints:
    def test_the_checklist(self, client):
        ledger(client)
        d = client.get("/api/unveil").get_json()
        assert [c["key"] for c in d["checklist"]] == ["protect", "anchor", "cards", "basics"]
        assert d["report"] is None
        assert d["checklist"][3]["available"] is False       # Learn isn't built yet
        assert [t["label"] for t in d["types"]] == ["TFSA", "RRSP", "FHSA", "Non-registered",
                                                    "Not sure"]

    def test_marking_unveil_done_and_undoing_it(self, client):
        r = client.put("/api/unveil", json={"type": "tfsa"})
        assert r.status_code == 200
        assert r.get_json()["report"] == {"type": "tfsa", "label": "TFSA", "on": "2026-10-09"}
        assert client.delete("/api/unveil").get_json()["report"] is None

    def test_the_report_reaches_the_path(self, client):
        st = client.application.config["STORE"]
        client.put("/api/unveil", json={"type": "rrsp"})
        from finance import api
        assert api._json_setting(st, "unveil_reported", None)["type"] == "rrsp"

    def test_only_a_kind_of_account_is_accepted(self, client):
        assert client.put("/api/unveil", json={"type": "my bank login"}).status_code == 400
        assert client.put("/api/unveil", json={}).status_code == 400


class TestThePrototypePageIsGone:
    @pytest.mark.parametrize("method, path", [
        ("get", "/api/plan"), ("get", "/api/plan/week?on=2026-10-01"),
        ("post", "/api/plan/simulate"), ("get", "/api/plan/setup"), ("put", "/api/plan/setup"),
        ("post", "/api/plan/setup/apply"), ("get", "/api/budgets"), ("put", "/api/budgets"),
        ("put", "/api/budgets/allocation"), ("get", "/api/setup"), ("get", "/api/nudge"),
        ("get", "/api/insights"), ("post", "/api/insights/x/dismiss"),
    ])
    def test_its_endpoints_answer_404_or_405(self, client, method, path):
        assert getattr(client, method)(path).status_code in (404, 405)

    def test_its_modules_are_gone(self):
        import importlib.util
        for name in ("projections", "nudge", "insights.rules", "insights.profile"):
            assert importlib.util.find_spec(f"finance.{name}") is None, name
