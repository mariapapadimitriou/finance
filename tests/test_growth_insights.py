"""Growth › Insights (Pearl THL-186 GR-24 to GR-27, THL-196 GR-28 to GR-32):
the one payload behind the page and its detail views, and the usual month
with unusual months left out (THL-59).

The ledger is the safe-to-spend fixture's: pay of $2,150 twice a month from
mid-July, rent, phone, insurance and hydro as Essentials, Netflix and
Spotify as Lifestyle, July to September, then October to the 9th.
"""

from datetime import date

import pytest

from finance import growth_insights as gi
from finance import piggy, usual_month as um
from test_safe_to_spend import TODAY, history, october, tx

ESSENTIALS = {"2026-07": 2335.00, "2026-08": 2339.00, "2026-09": 2332.00}
LIFESTYLE = 28.48


def c(dollars: float) -> int:
    return int(round(dollars * 100))


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    app = create_app(str(tmp_path / "insights.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    return app


def load(app, rows=None):
    plain = [t for t in october() if t.my_share is None and not t.repays]
    app.config["STORE"].add_transactions(rows if rows is not None else history() + plain)


def month(client, m=None):
    r = client.get("/api/insights/month" + (f"?month={m}" if m else ""))
    assert r.status_code == 200, r.get_json()
    return r.get_json()


# ── The usual month leaves unusual months out ────────────────────────────

class TestUsualWithUnusualMonths:
    def rows(self):
        """June to September, each with $1,000 of groceries, and a $3,000
        August (a move)."""
        rows = []
        for m in ("06", "07", "08", "09"):
            rows.append(tx(f"2026-{m}-01", "Loblaws", 1000.00, "Groceries"))
        rows.append(tx("2026-08-15", "Movers", 2000.00, "Groceries"))
        return rows

    def test_an_unusual_month_is_left_out_and_an_older_one_pulled_in(self):
        u = um.usual(self.rows(), TODAY, unusual={"2026-08"})
        assert u["months"] == ["2026-06", "2026-07", "2026-09"]
        assert u["groups"]["essentials"]["usual"] == 1000.00
        assert u["curve"] == "daily"

    def test_without_it_the_move_is_in_the_usual(self):
        u = um.usual(self.rows(), TODAY)
        assert u["months"] == ["2026-07", "2026-08", "2026-09"]
        assert u["groups"]["essentials"]["usual"] == pytest.approx(5000 / 3, abs=0.01)

    def test_with_nothing_older_it_rests_on_fewer(self):
        rows = [r for r in self.rows() if r.month >= "2026-07"]
        u = um.usual(rows, TODAY, unusual={"2026-08"})
        assert u["months"] == ["2026-07", "2026-09"]
        assert u["curve"] == "day_fraction"

    def test_home_budgets_and_insights_read_the_same_list(self, app):
        load(app, self.rows())
        with app.test_client() as client:
            r = client.put("/api/insights/unusual", json={"month": "2026-08", "unusual": True})
            assert r.get_json()["month"] == "2026-08"
            assert r.get_json()["usual"]["month_unusual"] is True
            body = month(client)
            assert body["usual"]["months"] == ["2026-06", "2026-07", "2026-09"]
            assert body["usual"]["left_out"] == ["2026-08"]
            assert body["vs_usual"][0]["usual"] == c(1000)
            home = client.get("/api/home").get_json()
            assert home["usual_month"]["months"] == ["2026-06", "2026-07", "2026-09"]
            budgets = client.get("/api/category-budgets").get_json()
            assert next(r for r in budgets["rows"] if r["category"] == "Groceries")["usual"] == 1000
            # The Anchor's pace reads the same setting.
            assert client.get("/api/goals").get_json()["anchor"]["unusual"] == ["2026-08"]
            client.put("/api/insights/unusual", json={"month": "2026-08", "unusual": False})
            assert month(client)["usual"]["months"] == ["2026-07", "2026-08", "2026-09"]
            assert client.get("/api/home").get_json()["usual_month"]["months"] == [
                "2026-07", "2026-08", "2026-09"]

    def test_only_a_month_that_has_ended(self, app):
        load(app)
        with app.test_client() as client:
            assert client.put("/api/insights/unusual", json={"month": "2026-10"}).status_code == 400
            assert client.put("/api/insights/unusual", json={"month": "Sept"}).status_code == 400


# ── The page ─────────────────────────────────────────────────────────────

class TestTiles:
    def test_income_essentials_lifestyle_and_set_aside(self, app):
        load(app)
        with app.test_client() as client:
            t = month(client)["tiles"]
        assert t["income"] == c(2150)                       # a friend paying back isn't income
        assert t["arrived"] == ["2026-10-01"]
        assert t["essentials"] == c(2000 + 732)
        assert t["lifestyle"] == c(332.34 + 40)
        assert t["set_aside"] == c(150)                     # the Saved transfer
        assert all(isinstance(v, int) for k, v in t.items() if k != "arrived")

    def test_left_out_and_joint_rows_count_for_nothing(self):
        rows = history() + [
            tx("2026-10-02", "Big TV", 900.00, "Shopping", excluded="row"),
            # On a joint account a row is another member's until she says
            # otherwise: the store loads it with no share of hers.
            tx("2026-10-02", "Family groceries", 300.00, "Groceries", joint="Family", my_share=0.0),
            tx("2026-10-03", "Partner's pay", -3000.00, "Income", joint="Family", my_share=0.0),
            tx("2026-10-04", "Our dinner", 100.00, "Dining", joint="Family", my_share=50.0,
               share_set=True),
        ]
        led = gi.Ledger(rows)
        assert led.income.get("2026-10", 0) == 0
        assert led.group["2026-10"].get("essentials", 0) == 0
        assert led.group["2026-10"]["lifestyle"] == c(50)

    def test_a_past_month(self, app):
        load(app)
        with app.test_client() as client:
            body = month(client, "2026-09")
        assert body["running"] is False and body["day"] == 30
        assert body["tiles"]["income"] == c(4300)
        assert body["tiles"]["essentials"] == c(ESSENTIALS["2026-09"])


class TestVsUsual:
    def test_groups_against_usual_and_by_today(self, app):
        load(app)
        with app.test_client() as client:
            rows = {r["key"]: r for r in month(client)["vs_usual"]}
        ess = rows["essentials"]
        assert ess["spent"] == c(2732)
        assert ess["usual"] == c(sum(ESSENTIALS.values()) / 3)
        assert ess["by_today"] == c(2000)                   # rent on the 1st, nothing else by the 9th
        assert rows["lifestyle"]["usual"] == c(LIFESTYLE)

    def test_a_past_month_against_the_months_before_it(self, app):
        """September is compared with July and August, not with itself."""
        load(app)
        with app.test_client() as client:
            body = month(client, "2026-09")
        assert body["usual"]["months"] == ["2026-07", "2026-08"]
        hydro = next(r for r in body["categories"] if r["category"] == "Utilities")
        assert (hydro["spent"], hydro["usual"]) == (c(57), c(62))
        assert hydro["words"] == {"kind": "less", "diff": c(5)}
        rent = next(r for r in body["categories"] if r["category"] == "Rent & Housing")
        assert rent["words"] == {"kind": "same", "diff": 0}

    def test_category_history_marks_months_above_usual(self, app):
        rows = history() + [tx("2026-10-02", "Pai", 90.00, "Dining"),
                            tx("2026-07-05", "Pai", 30.00, "Dining"),
                            tx("2026-08-05", "Pai", 30.00, "Dining"),
                            tx("2026-09-05", "Pai", 30.00, "Dining")]
        load(app, rows)
        with app.test_client() as client:
            dining = next(r for r in month(client)["categories"] if r["category"] == "Dining")
        assert dining["usual"] == c(30) and dining["by_today"] == c(30)
        assert [h["month"] for h in dining["history"]] == [
            "2026-05", "2026-06", "2026-07", "2026-08", "2026-09", "2026-10"]
        assert [h["above"] for h in dining["history"]] == [False] * 5 + [True]
        assert dining["history"][-1]["running"] is True


class TestTrend:
    def test_months_stacked_and_the_usual_band(self, app):
        load(app)
        with app.test_client() as client:
            t = month(client)["trend"]
        assert [m["month"] for m in t["months"]] == ["2026-07", "2026-08", "2026-09", "2026-10"]
        sep = t["months"][2]
        assert (sep["essentials"], sep["lifestyle"]) == (c(ESSENTIALS["2026-09"]), c(LIFESTYLE))
        totals = [c(v + LIFESTYLE) for v in ESSENTIALS.values()]
        assert t["band"] == {"low": min(totals), "high": max(totals),
                             "usual": round(sum(totals) / 3)}
        assert t["months"][-1]["running"] is True and t["months"][-1]["above"] is False

    def test_twelve_months_at_most(self):
        rows = [tx(f"{y}-{m:02d}-03", "Loblaws", 100.0, "Groceries")
                for y in (2025, 2026) for m in range(1, 13)
                if f"{y}-{m:02d}" <= "2026-10"]
        led = gi.Ledger(rows)
        shown = gi.months_shown(led, "2026-10")
        assert len(shown) == 12 and shown[0] == "2025-11" and shown[-1] == "2026-10"

    def test_a_partial_first_month_is_not_drawn_as_a_quiet_one(self):
        rows = [tx("2026-08-20", "Loblaws", 50.0, "Groceries"),
                tx("2026-09-03", "Loblaws", 500.0, "Groceries")]
        assert gi.months_shown(gi.Ledger(rows), "2026-10") == ["2026-09", "2026-10"]


class TestWhereItWent:
    def test_groups_categories_shares_and_unsure(self, app):
        unsure = tx("2026-10-07", "Mystery Shop", 60.00, "Shopping",
                    category_source="issuer", raw={"category_confidence": "LOW"})
        load(app, history() + [t for t in october() if t.my_share is None and not t.repays]
             + [unsure])
        with app.test_client() as client:
            w = month(client)["where"]
            ess, life = w["groups"]
            assert (ess["label"], life["label"]) == ("Essentials", "Lifestyle")
            assert [x["category"] for x in ess["categories"]] == ["Rent & Housing", "Groceries"]
            assert w["total"] == c(2000 + 732 + 332.34 + 40 + 60)
            shop = next(x for x in life["categories"] if x["category"] == "Shopping")
            assert shop["unsure"] == 1 and w["unsure"] == 1
            assert sum(x["share"] for g in w["groups"] for x in g["categories"]) in (99, 100, 101)
            # Confirming it takes the marker away.
            app.config["STORE"].confirm_category(unsure.fingerprint, "Shopping")
            assert month(client)["where"]["unsure"] == 0

    def test_this_month_also_carries_last_month(self, app):
        load(app)
        with app.test_client() as client:
            body = month(client)
            assert body["where_last"]["month"] == "2026-09"
            assert month(client, "2026-09")["where_last"] is None


class TestMoneyInAndOut:
    def test_kept_once_a_month_ends(self, app):
        load(app)
        with app.test_client() as client:
            rows = {r["month"]: r for r in month(client)["money"]}
        sep = rows["2026-09"]
        assert sep["income"] == c(4300)
        assert sep["spent"] == c(ESSENTIALS["2026-09"] + LIFESTYLE)
        assert sep["kept"] == sep["income"] - sep["spent"] - sep["set_aside"]
        assert rows["2026-10"]["kept"] is None              # still going
        assert rows["2026-10"]["set_aside"] == c(150)

    def test_where_the_income_went(self, app):
        load(app)
        with app.test_client() as client:
            went = month(client, "2026-09")["income_went"]
        assert went == {"income": c(4300), "essentials": c(ESSENTIALS["2026-09"]),
                        "lifestyle": c(LIFESTYLE), "set_aside": 0,
                        "left_over": c(4300 - ESSENTIALS["2026-09"] - LIFESTYLE), "short": 0}


class TestSavings:
    def bank(self):
        return piggy.Bank(id=1, name="Trip", target=1200.0, cadence="annual",
                          start_month="2026-07")

    def test_chests_at_each_month_end_and_openings_labelled(self):
        flight = tx("2026-08-20", "Air Canada", 150.00, "Travel", bank_id=1, bank_amount=150.00)
        charges = {1: {"2026-08": 150.0}}
        out = gi.savings([flight], ["2026-07", "2026-08", "2026-09", "2026-10"], TODAY,
                         anchor={"started": False}, accounts=[], banks=[self.bank()],
                         charges=charges)
        held = [p["chests"]["1"] for p in out["series"]]
        assert held == [c(100), c(50), c(150), c(250)]      # $100 a month in, $150 out in August
        assert out["events"] == [{"month": "2026-08", "chest": "1", "label": "Trip opened"}]
        assert out["total"] == c(250) and out["change"] == c(100)
        assert out["parts"] == [{"key": "1", "label": "Trip", "amount": c(250)}]

    def test_the_anchor_is_wound_back_through_its_account(self):
        rows = [tx("2026-09-10", "From chequing", -400.00, "Saved", account="sav"),
                tx("2026-10-05", "From chequing", -200.00, "Saved", account="sav")]
        accounts = [{"account_id": "sav", "balance": 1000.00, "as_of": "2026-10-09"}]
        out = gi.savings(rows, ["2026-08", "2026-09", "2026-10"], TODAY,
                         anchor={"started": True}, accounts=accounts, banks=[], charges={})
        assert [p["anchor"] for p in out["series"]] == [c(400), c(800), c(1000)]
        assert out["parts"][0] == {"key": "anchor", "label": "Anchor", "amount": c(1000)}

    def test_chest_monthly_is_set_aside(self):
        assert gi.chest_monthly([self.bank()], {}, "2026-09") == c(100)
        assert gi.chest_monthly([self.bank()], {}, "2026-06") == 0


class TestSubscriptionsPerYear:
    def test_each_by_the_year_and_the_total(self, app):
        load(app)
        with app.test_client() as client:
            subs = month(client)["subscriptions"]
            assert [r["merchant"] for r in subs["rows"]] == ["Netflix", "Spotify"]
            assert subs["count"] == 2
            assert subs["yearly"] == sum(r["yearly"] for r in subs["rows"])
            assert subs["rows"][0]["yearly"] == c(16.49 * 12)

            r = client.put("/api/insights/subscriptions",
                           json={"merchant": "Netflix", "choice": "review"})
            row = r.get_json()["subscriptions"]["rows"][0]
            assert row["choice"] == "review" and row["remind"] == "2026-11"
            # A reminder, next month, and nothing more.
            assert r.get_json()["subscriptions"]["reminders"] == []
            assert client.put("/api/insights/subscriptions",
                              json={"merchant": "Netflix", "choice": "cancel"}).status_code == 400

    def test_the_reminder_shows_next_month(self):
        recs = [{"merchant": "Audible", "monthly_cost": 14.95, "annual_cost": 179.40}]
        out = gi.subscriptions(recs, {"Audible": {"choice": "review", "remind": "2026-10"}}, TODAY)
        assert out["reminders"] == ["Audible"]


class TestThinAndEmpty:
    def test_an_empty_ledger(self, app):
        with app.test_client() as client:
            body = month(client)
        assert body["empty"] is True and body["months"] == ["2026-10"]
        assert body["tiles"]["income"] == 0 and body["where"]["total"] == 0
        assert body["trend"]["band"] is None
        assert [r["usual"] for r in body["vs_usual"]] == [None, None]
        assert body["savings"]["total"] == 0 and body["savings"]["change"] is None
        assert body["subscriptions"]["count"] == 0

    def test_one_month_of_data(self, app):
        load(app, [tx("2026-10-02", "Loblaws", 80.00, "Groceries")])
        with app.test_client() as client:
            body = month(client)
        assert body["usual"]["months"] == []
        assert [m["month"] for m in body["trend"]["months"]] == ["2026-10"]
        assert body["money"][0]["kept"] is None

    def test_a_future_or_malformed_month_is_refused(self, app):
        with app.test_client() as client:
            assert client.get("/api/insights/month?month=2026-11").status_code == 400
            assert client.get("/api/insights/month?month=2026-13").status_code == 400
