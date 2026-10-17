"""The expense calendar (THL-245, THL-255): shaded past days, what's due,
one day's story, and the Home strip."""

from datetime import date, timedelta

import pytest

from finance import calendar_view, secrets_box
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx

MONTH = TODAY.strftime("%Y-%m")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "cal.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    st = app.config["STORE"]
    with app.test_client() as c:
        c.st = st
        yield c


def cells(body):
    return {c["date"]: c for c in body["cells"]}


class TestMonth:
    def test_past_days_say_how_the_month_was_going(self, client):
        client.st.add_transactions(history() + october())
        body = client.get("/api/calendar").get_json()
        assert body["month"] == MONTH and body["label"] == "October 2026" and body["this_month"]
        by = cells(body)
        # Rent on the 1st is exactly the usual rent: on pace. The dinner on
        # the 3rd put October ahead of a usual month, and it stayed ahead.
        assert by["2026-10-01"]["state"] == "on" and by["2026-10-02"]["state"] == "on"
        assert by["2026-10-03"]["state"] == "ahead" and by["2026-10-08"]["state"] == "ahead"
        assert by["2026-10-09"]["state"] == "today" and by["2026-10-10"]["state"] == "future"
        # Sunday first, six rows: September's tail is outside the month.
        assert body["cells"][0]["date"] == "2026-09-27" and not body["cells"][0]["in_month"]
        assert body["cells"][0]["state"] == "outside" and len(body["cells"]) == 42
        assert body["has_usual"]
        assert [l["key"] for l in body["legend"]] == ["on", "ahead", "none", "today"]
        # No per-day amount anywhere in a cell.
        assert not any("spent" in c or "amount" in c for c in body["cells"])

    def test_upcoming_days_show_what_is_due_and_the_chests_on_the_first(self, client):
        client.st.add_transactions(history() + october())
        r = client.post("/api/piggy", json={"name": "Japan trip", "target": 3000,
                                            "target_date": "2027-10-01", "cadence": "once"})
        assert r.status_code in (200, 201), r.get_json()
        body = client.get("/api/calendar").get_json()
        by = cells(body)
        rogers = [d for d in by["2026-10-12"]["due"] if d["label"] == "Rogers"]
        assert rogers and rogers[0]["kind"] == "bill" and rogers[0]["amount"] == 85.0
        # November's rent and the chest's monthly amount sit on the 1st.
        first = by["2026-11-01"]["due"]
        assert any(d["kind"] == "bill" and d["label"] == "Parkside Properties" for d in first)
        chest = next(d for d in first if d["kind"] == "chest")
        assert chest["label"] == "Japan trip from Anchor" and chest["amount"] > 0
        # Past days carry nothing due; the coming-up list starts today.
        assert by["2026-10-05"]["due"] == []
        assert body["coming_up"] and all(i["date"] >= TODAY.isoformat() for i in body["coming_up"])
        assert body["totals"]["spent"] > 0 and body["totals"]["income"] == 2190.0   # pay, and the $40 sent back
        assert body["totals"]["moving"] == 650.0                  # the card payment and $150 to savings

    def test_a_month_with_no_history_is_not_shaded(self, client):
        client.st.add_transactions(october())
        body = client.get("/api/calendar").get_json()
        by = cells(body)
        assert all(by[f"2026-10-{d:02d}"]["state"] == "none" for d in range(1, 9))
        assert not body["has_usual"]

    def test_an_empty_ledger_is_a_calendar_with_nothing_in_it(self, client):
        body = client.get("/api/calendar").get_json()
        assert len(body["cells"]) == 42 and body["coming_up"] == []
        assert all(c["due"] == [] for c in body["cells"])

    def test_another_month_and_a_bad_one(self, client):
        client.st.add_transactions(history() + october())
        body = client.get("/api/calendar?month=2026-09").get_json()
        assert body["label"] == "September 2026" and not body["this_month"]
        assert body["prev"]["label"] == "August" and body["next"]["label"] == "October"
        by = cells(body)
        # September is compared with July and August; nothing is due in a past month.
        assert by["2026-09-01"]["state"] in ("on", "ahead") and by["2026-09-30"]["due"] == []
        assert client.get("/api/calendar?month=2026-13").status_code == 400

    def test_a_resorted_transaction_changes_the_shading(self, client):
        rows = history() + october()
        client.st.add_transactions(rows)
        by = cells(client.get("/api/calendar").get_json())
        assert by["2026-10-03"]["state"] == "ahead"
        # The dinner turns out to be a transfer: October is back on pace.
        dinner = next(t for t in rows if t.merchant == "Grey Gardens")
        client.st.set_transaction_category(dinner.fingerprint, "Transfers")
        by = cells(client.get("/api/calendar").get_json())
        assert by["2026-10-03"]["state"] == "on" and by["2026-10-04"]["state"] == "on"


class TestDay:
    def test_a_past_day(self, client):
        client.st.add_transactions(history() + october())
        body = client.get("/api/calendar/day/2026-10-03").get_json()
        assert body["label"] == "Saturday, October 3" and body["state"] == "ahead" and body["past"]
        assert body["reason"] == ("Spending moved ahead of your usual pace after this day, "
                                  "mostly from one Grey Gardens purchase.")
        assert [r["merchant"] for r in body["spent"]] == ["Grey Gardens"]
        assert body["spent"][0]["amount"] == 120.0 and body["spent"][0]["category"] == "Dining"
        assert body["due"] == []
        later = client.get("/api/calendar/day/2026-10-06").get_json()
        assert later["reason"] == "Spending was still ahead of your usual pace at the end of this day."
        on = client.get("/api/calendar/day/2026-10-02").get_json()
        assert on["reason"] == "On or under your usual pace by the end of this day."

    def test_today_and_an_upcoming_day(self, client):
        client.st.add_transactions(history() + october())
        today = client.get(f"/api/calendar/day/{TODAY.isoformat()}").get_json()
        assert today["today"] and today["state"] == "today"
        assert today["reason"] == "Today isn’t finished. It’s shaded once the day ends."
        soon = client.get("/api/calendar/day/2026-10-12").get_json()
        assert soon["state"] == "future" and soon["spent"] == []
        assert soon["reason"] == "Upcoming days only show what’s due. Allowance already counts these."
        assert [d["label"] for d in soon["due"]] == ["Rogers"]
        assert client.get("/api/calendar/day/2026-10-40").status_code == 400

    def test_never_the_word_bad(self, client):
        client.st.add_transactions(history() + october())
        for d in range(1, 12):
            body = client.get(f"/api/calendar/day/2026-10-{d:02d}").get_json()
            assert "bad" not in body["reason"].lower()


class TestStrip:
    def test_home_carries_the_strip(self, client):
        client.st.add_transactions(history() + october())
        home = client.get("/api/home").get_json()
        s = home["calendar"]
        assert s["month"] == MONTH and s["label"] == "October" and len(s["cells"]) == 31
        assert [c["state"] for c in s["cells"][:3]] == ["on", "on", "ahead"]
        assert s["cells"][8]["state"] == "today" and s["cells"][11]["due"]
        assert s["line"].startswith("Next: ") and "Rogers on Oct 12" in s["line"]
        assert s["line"].endswith("Spending moved ahead of your usual pace on Oct 3.")

    def test_a_quiet_strip(self, client):
        client.st.add_transactions(october())
        s = client.get("/api/home").get_json()["calendar"]
        assert all(c["state"] in ("none", "today", "future") for c in s["cells"])
        assert "usual pace" not in s["line"]


class TestWords:
    def test_flips_and_pace(self):
        assert calendar_view.flips({1: "on", 2: "ahead", 3: "ahead", 4: "on", 5: "ahead"}) == [2, 5]
        assert calendar_view.flips({1: "none", 2: "ahead"}) == [2]
        usual = {"groups": {"essentials": {"usual": 3000.0, "by_day": None},
                            "lifestyle": {"usual": 600.0, "by_day": None}}}
        assert calendar_view.usual_by_day(usual, 15, 30) == 1800.0
        assert calendar_view.usual_by_day({"groups": {}}, 3, 31) is None


class TestSelectDays:
    """Select days (CAL-06 to CAL-09): a range of days summed by category,
    the sorted ranges as bands on the calendar and the list under it, and
    the transactions list filtered to those days."""

    def test_a_range_is_summed_by_category_with_what_is_not_counted(self, client):
        client.st.add_transactions(history() + october())
        body = client.get("/api/calendar/range?first=2026-10-01&last=2026-10-05").get_json()
        assert body["first"] == "2026-10-01" and body["last"] == "2026-10-05" and body["days"] == 5
        assert body["label"] == "October 1–5" and body["words"] == "Thursday to Monday"
        assert body["count"] >= 1 and body["title"].endswith(f"${body['total']:,.2f}")
        assert sum(c["count"] for c in body["by_category"]) == body["count"]
        assert abs(sum(c["total"] for c in body["by_category"]) - body["total"]) < 0.01
        # Rent on the 1st is a bill: listed as staying, not in the purchases.
        assert any(r["why"] == "Bill" for r in body["not_counted"])
        assert "Money in, transfers, card payments, savings and lending never change." in body["staying"]
        assert body["ranges"] == []
        # Backwards is forgiven; a year and a day is not; a non-day is not.
        flipped = client.get("/api/calendar/range?first=2026-10-05&last=2026-10-01").get_json()
        assert flipped["first"] == "2026-10-01"
        assert client.get("/api/calendar/range?first=2025-01-01&last=2026-10-05").status_code == 400
        assert client.get("/api/calendar/range?first=nope&last=2026-10-05").status_code == 400

    def test_a_sorted_range_shows_on_the_calendar_and_filters_the_list(self, client):
        client.st.add_transactions(history() + october())
        r = client.post("/api/ranges", json={"name": "Long weekend", "first": "2026-10-02",
                                             "last": "2026-10-04", "category": "Travel"})
        assert r.status_code == 201, r.get_json()
        month = client.get("/api/calendar").get_json()
        assert [b["name"] for b in month["bands"]] == ["Long weekend"]
        assert month["bands"][0]["days"] == 3 and month["bands"][0]["bank"] is None
        assert [x["name"] for x in month["ranges"]] == ["Long weekend"]
        # Another month's grid doesn't carry the band, but still lists the range.
        august = client.get("/api/calendar?month=2026-08").get_json()
        assert august["bands"] == [] and len(august["ranges"]) == 1
        # The transactions list keeps only those days.
        rows = client.get("/api/transactions/list", query_string={
            "month": MONTH, "first": "2026-10-02", "last": "2026-10-04"}).get_json()["transactions"]
        assert rows and all("2026-10-02" <= t["date"][:10] <= "2026-10-04" for t in rows)
        summary = client.get("/api/calendar/range?first=2026-10-02&last=2026-10-04").get_json()
        assert summary["ranges"][0]["name"] == "Long weekend"
