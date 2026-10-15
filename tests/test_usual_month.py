"""Usual month per group and category, with the daily curve (THL-184), and
the Home snapshot built from it (THL-48)."""

from datetime import date

import pytest

from finance import safe_to_spend as sts
from finance import usual_month as um
from test_safe_to_spend import TODAY, history, october, tx

# Rent $2,000 on the 1st; Rogers $85, Belair $190, Hydro One ($60, $64, $57)
# in Essentials; Netflix and Spotify in Lifestyle; July to September.
ESSENTIALS = round(2000 + 85 + 190 + (60 + 64 + 57) / 3, 2)
LIFESTYLE = round(16.49 + 11.99, 2)


class TestUsualMonth:
    def test_three_full_months_give_a_daily_curve(self):
        u = um.usual(history(), TODAY)
        assert u["months"] == ["2026-07", "2026-08", "2026-09"]
        assert u["curve"] == "daily"
        assert u["groups"]["essentials"]["usual"] == ESSENTIALS
        assert u["groups"]["lifestyle"]["usual"] == LIFESTYLE

    def test_the_curve_is_how_much_by_each_day(self):
        by_day = um.usual(history(), TODAY)["groups"]["essentials"]["by_day"]
        assert len(by_day) == 31
        assert by_day[0] == 2000.00                     # rent on the 1st
        assert by_day[10] == 2000.00                    # nothing more by the 11th
        assert by_day[11] == 2085.00                    # Rogers on the 12th
        assert by_day[30] == ESSENTIALS                 # the whole month by the 31st
        assert by_day == sorted(by_day)                 # it only ever builds up

    def test_per_category(self):
        cats = um.usual(history(), TODAY)["categories"]
        assert cats["Rent & Housing"] == {"usual": 2000.00, "group": "essentials"}
        assert cats["Streaming"] == {"usual": LIFESTYLE, "group": "lifestyle"}

    def test_transfers_and_card_payments_never_count(self):
        rows = history() + [tx("2026-08-10", "TD Visa payment", 900.00, "Transfers"),
                            tx("2026-08-11", "To savings", 300.00, "Saved")]
        u = um.usual(rows, TODAY)
        assert u["groups"]["essentials"]["usual"] == ESSENTIALS
        assert "Transfers" not in u["categories"] and "Saved" not in u["categories"]

    def test_a_partial_first_month_is_left_out(self):
        rows = [r for r in history() if r.date >= "2026-07-10"]
        u = um.usual(rows, TODAY)
        assert u["months"] == ["2026-08", "2026-09"]
        assert u["curve"] == "day_fraction"             # under 3 months: no curve
        assert u["groups"]["essentials"]["by_day"] is None
        assert u["groups"]["essentials"]["usual"] == round(2000 + 85 + 190 + (64 + 57) / 2, 2)

    def test_no_full_month_no_usual(self):
        u = um.usual([tx("2026-09-20", "Loblaws", 80.00, "Groceries")], TODAY)
        assert u == {"months": [], "curve": None, "groups": {}, "kinds": {}, "categories": {}}

    def test_a_big_purchase_counts_until_she_marks_it_a_one_off(self):
        rows = history() + [tx("2026-08-15", "Garage", 1900.00, "Home")]
        u = um.usual(rows, TODAY)
        # Rounded once, at the end: (3 × $2,275 + $181 of Hydro + $1,900) ÷ 3.
        assert u["groups"]["essentials"]["usual"] == round((3 * 2275 + 181 + 1900) / 3, 2)
        # THL-71: marked as a one-off, it's left out.
        rows[-1].one_off_since = "2026-10-09"
        assert um.usual(rows, TODAY)["groups"]["essentials"]["usual"] == ESSENTIALS


class TestSnapshot:
    def build(self, rows=None, **kw):
        rows = rows or history() + october()
        s = sts.compute(rows, TODAY)
        return um.snapshot(rows, TODAY, s, um.usual(rows, TODAY))

    def row(self, snap, key):
        return next(r for r in snap["rows"] if r["key"] == key)

    def test_four_rows_in_order(self):
        snap = self.build()
        assert [r["label"] for r in snap["rows"]] == ["Income", "Essentials", "Lifestyle", "Put away"]
        assert (snap["day"], snap["days_in_month"], snap["months_of_history"]) == (9, 31, 3)

    def test_income_arrived_against_expected(self):
        income = self.row(self.build(), "income")
        assert (income["received"], income["expected"], income["next_pay"]) == (
            2150.00, 4300.00, "2026-10-16")

    def test_groups_against_usual_and_usual_by_today(self):
        snap = self.build()
        ess, life = self.row(snap, "essentials"), self.row(snap, "lifestyle")
        assert (ess["spent"], ess["usual"], ess["usual_by_today"]) == (2732.00, ESSENTIALS, 2000.00)
        assert (life["spent"], life["usual"], life["usual_by_today"]) == (412.34, LIFESTYLE, 0.00)

    def test_put_away_is_what_she_moved_with_no_plan_behind_it(self):
        """THL-230: Put away is what she moved to savings; nothing is planned
        against it, and chests fill from her Anchor."""
        assert self.row(self.build(), "savings") == {
            "key": "savings", "label": "Put away", "saved": 150.00, "planned": None, "goal": None}

    def test_where_the_extra_went(self):
        assert self.build()["extra_went_to"] == "Essentials"   # $732 past its usual by the 9th

    def test_without_a_usual_month_there_is_nothing_to_compare(self):
        rows = [tx("2026-09-20", "Loblaws", 80.00, "Groceries"),
                tx("2026-10-02", "Pai", 45.00, "Dining")]
        snap = um.snapshot(rows, TODAY, sts.compute(rows, TODAY), um.usual(rows, TODAY))
        life = self.row(snap, "lifestyle")
        assert life["usual"] is None and life["spent"] == 45.00
        assert snap["extra_went_to"] is None


def test_the_home_payload_carries_both(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    app = create_app(str(tmp_path / "home.db"))
    app.config.update(TESTING=True)
    plain = [t for t in october() if t.my_share is None and not t.repays]
    app.config["STORE"].add_transactions(history() + plain)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    with app.test_client() as c:
        body = c.get("/api/home").get_json()
    assert body["usual_month"]["curve"] == "daily"
    assert [r["key"] for r in body["snapshot"]["rows"]] == ["income", "essentials", "lifestyle", "savings", "fixed", "variable"]
