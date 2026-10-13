"""This week's share of the month (THL-166) and "Can I afford it?" (THL-167)."""

from datetime import date, timedelta

import pytest

from finance import safe_to_spend as sts, secrets_box, weekly
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx


def cents(x):
    return round(x * 100)


def alex(today=TODAY, rows=None):
    rows = history() + october() if rows is None else rows
    s = sts.compute(rows, today, savings_target=300.0)
    return rows, s, weekly.week(rows, today, s)


def plain(today, spends=()):
    """$3,100 a month (a round $100 a day in October), no bills, no goal."""
    rows = [tx(d, "Shop", amount, "Shopping") for d, amount in spends]
    s = sts.compute(rows, today, told_income=3100.0)
    return s, weekly.week(rows, today, s)


class TestTheWeek:
    @pytest.mark.parametrize("today,start,end", [
        (date(2026, 10, 9), "2026-10-05", "2026-10-11"),     # Friday
        (date(2026, 10, 1), "2026-10-01", "2026-10-04"),     # Thursday: the month starts mid-week
        (date(2026, 10, 30), "2026-10-26", "2026-10-31"),    # the month ends mid-week
        (date(2026, 11, 2), "2026-11-02", "2026-11-08"),     # Monday
    ])
    def test_monday_to_sunday_cut_at_the_month(self, today, start, end):
        a, b = weekly.week_bounds(today)
        assert (a.isoformat(), b.isoformat()) == (start, end)

    def test_the_handoff_files_friday(self):
        """Oct 9: $642.18 safe to spend now and $1,104.34 spent since Monday
        (rent left out, W3), so $1,746.52 on Monday morning. 7 of its 27
        days: $452.80. The week is $651.54 past its share."""
        _, s, w = alex()
        assert w["at_start"] == 1746.52 and w["spent"] == 1104.34
        assert w["share"] == 452.80
        assert w["state"] == "over" and w["over_by"] == 651.54 and w["per_day"] is None
        # Oct 1-4 spent $40 against an even $230-odd, so some rolled over.
        assert w["rolled_over"] == 49.40

    def test_per_day_counts_today(self):
        _, w = plain(date(2026, 10, 9))                       # Fri, Sat, Sun
        assert w["days_left"] == 3
        assert w["per_day"] == cents(w["left"]) // 3 / 100

    @pytest.mark.parametrize("day", range(1, 32))
    def test_the_week_and_the_rest_add_up_to_the_month(self, day):
        today = date(2026, 10, day)
        rows = history() + [t for t in october() if t.date <= today.isoformat()]
        _, s, w = alex(today, rows)
        assert cents(w["left"]) + cents(w["rest_of_month"]) == cents(s["amount"])
        if w["end"] == "2026-10-31":
            assert w["rest_of_month"] == 0 and w["rest_days"] == 0

    @pytest.mark.parametrize("day", range(1, 32))
    def test_a_plain_month_adds_up_too(self, day):
        today = date(2026, 10, day)
        spends = [((date(2026, 10, 1) + timedelta(days=i)).isoformat(), 37.13 * (i % 3))
                  for i in range(day)]
        s, w = plain(today, spends)
        assert cents(w["left"]) + cents(w["rest_of_month"]) == cents(s["amount"])


class TestRollover:
    def test_spending_at_pace_rolls_nothing_over(self):
        spends = [(f"2026-10-{d:02d}", 100.00) for d in range(1, 12)]
        _, w = plain(date(2026, 10, 12), spends)
        assert w["share"] == 700.00 and w["rolled_over"] == 0

    def test_unspent_rolls_into_the_weeks_after(self):
        """Nothing spent Oct 1-11: $1,100 left over, re-split across the 20
        days left, so this week gets $55 a day more: $385."""
        _, w = plain(date(2026, 10, 12))
        assert w["share"] == 1085.00 and w["rolled_over"] == 385.00

    def test_overspend_stays_in_the_month(self):
        """$200 over pace last week comes out of every week left, by days
        (W4): this week carries $70 of it, not all $200."""
        spends = [(f"2026-10-{d:02d}", 100.00) for d in range(1, 12)] + [("2026-10-08", 200.00)]
        _, w = plain(date(2026, 10, 12), spends)
        assert w["share"] == 630.00 and w["rolled_over"] == -70.00

    def test_a_bill_paid_this_week_does_not_touch_it(self):
        """Rogers is due Oct 12. Charged or not, the week is the same (W3)."""
        today = date(2026, 10, 13)
        without = alex(today)[2]
        rows = history() + october() + [
            tx("2026-10-12", "Rogers", 85.00, "Phone & Internet", account="visa")]
        assert alex(today, rows)[2] == without


class TestStates:
    def test_no_income_no_week(self):
        rows = [tx("2026-10-02", "Loblaws", 80.00, "Groceries")]
        assert weekly.week(rows, TODAY, sts.compute(rows, TODAY)) is None

    def test_a_month_past_its_plan_is_a_week_past_it_too(self):
        rows = history() + october() + [tx("2026-10-08", "Air Canada", 900.00, "Travel")]
        _, s, w = alex(rows=rows)
        assert s["state"] == "over" and w["state"] == "over"

    def test_a_rough_month_shows_the_week_rounded_down(self):
        s, w = plain(date(2026, 10, 12), [("2026-10-12", 12.34)])
        assert s["estimate"] == "rough"
        assert w["left"] == 1072.66 and w["shown"] == 1070


class TestCanIAffordIt:
    def test_it_fits(self):
        """AF-02: $642.18 goes to $462.18, about $20 a day for 23 days."""
        rows, s, w = alex()
        r = weekly.afford(rows, TODAY, s, w, 180.00)
        assert r["fits"] and (r["before"], r["after"]) == (642.18, 462.18)
        assert r["per_day_after"] == 20.09 and r["days_left"] == 23
        assert r["short_by"] is None and r["next_month"] is None

    def test_not_this_month_but_november(self):
        """AF-03 as decided (A1): $258 more than what's left, and a usual
        November ($4,300 in, $2,363.48 of bills, $300 set aside) covers it."""
        rows, s, w = alex()
        r = weekly.afford(rows, TODAY, s, w, 900.00)
        assert not r["fits"] and r["short_by"] == 257.82 and r["after"] is None
        assert r["next_month"] == {"month": "2026-11", "fits": True, "per_day_after": 24.55}

    def test_more_than_a_usual_month_leaves(self):
        rows, s, w = alex()
        r = weekly.afford(rows, TODAY, s, w, 5000.00)
        assert r["next_month"]["fits"] is False and r["next_month"]["per_day_after"] is None

    def test_one_line_on_the_week(self):
        s, w = plain(date(2026, 10, 12))
        r = weekly.afford([], date(2026, 10, 12), s, w, 85.00)
        assert r["week"] == {"left": 1085.00, "within": True, "left_after": 1000.00}
        r = weekly.afford([], date(2026, 10, 12), s, w, 1500.00)
        assert r["week"]["within"] is False and r["week"]["left_after"] is None

    def test_a_month_already_past_its_plan(self):
        rows = history() + october() + [tx("2026-10-08", "Air Canada", 900.00, "Travel")]
        rows, s, w = alex(rows=rows)
        r = weekly.afford(rows, TODAY, s, w, 50.00)
        assert r["already_over"] and not r["fits"]
        assert r["short_by"] == round(s["over_by"] + 50, 2)

    def test_a_rough_month_is_checked_against_what_she_sees(self):
        s, w = plain(date(2026, 10, 12), [("2026-10-12", 12.34)])
        r = weekly.afford([], date(2026, 10, 12), s, w, 3085.00)
        assert s["shown"] == 3080 and not r["fits"] and r["short_by"] == 5.00


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "home.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    st = app.config["STORE"]
    with app.test_client() as c:
        yield c, st


class TestTheApi:
    def test_home_carries_the_week_and_the_view(self, client):
        c, st = client
        st.add_transactions(history() + [t for t in october() if t.my_share is None and not t.repays])
        body = c.get("/api/home").get_json()
        assert body["week"]["start"] == "2026-10-05" and body["view"] == "month"
        assert c.put("/api/home/view", json={"view": "week"}).status_code == 200
        assert c.get("/api/home").get_json()["view"] == "week"
        assert c.put("/api/home/view", json={"view": "day"}).status_code == 400

    def test_afford_records_nothing(self, client):
        c, st = client
        st.add_transactions(history() + [t for t in october() if t.my_share is None and not t.repays])
        before = len(st.all_transactions())
        settings = c.get("/api/home").get_json()["safe_to_spend"]["amount"]
        r = c.post("/api/home/afford", json={"amount": 180}).get_json()
        assert r["fits"] and r["before"] == settings
        assert len(st.all_transactions()) == before
        assert c.get("/api/home").get_json()["safe_to_spend"]["amount"] == settings

    @pytest.mark.parametrize("amount", [0, -5, "abc", None, 2_000_000])
    def test_afford_wants_an_amount(self, client, amount):
        c, _ = client
        assert c.post("/api/home/afford", json={"amount": amount}).status_code == 400

    def test_afford_waits_for_an_income(self, client):
        c, st = client
        st.add_transactions([tx("2026-10-02", "Loblaws", 80.00, "Groceries")])
        assert c.post("/api/home/afford", json={"amount": 50}).status_code == 409
        assert c.get("/api/home").get_json()["week"] is None
