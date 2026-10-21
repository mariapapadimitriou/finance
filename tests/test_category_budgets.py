"""Category budgets (THL-168, THL-185 B-01 to B-03).

Three usual months (July to September) with $400 of Groceries on the 3rd,
10th, 17th and 24th and $200 of Dining on the 5th and 20th, on top of the
X-01 person's pay and bills.
"""

from datetime import date

import pytest

from finance import category_budgets as cb, safe_to_spend as sts, secrets_box, usual_month
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, tx


def usual_rows():
    rows = history()
    for m in ("07", "08", "09"):
        # Shops and amounts vary, or they'd look like a weekly bill: $400 a
        # month all the same.
        i = int(m) - 7
        rows += [tx(f"2026-{m}-{d:02d}", shop, a, "Groceries")
                 for d, shop, a in ((3, "Loblaws", 100.00 + 20 * i), (10, "No Frills", 62.40 - 12 * i),
                                    (17, "Farm Boy", 141.85 - 25 * i), (24, "Metro", 95.75 + 17 * i))]
        rows += [tx(f"2026-{m}-{d:02d}", "Pai", a, "Dining") for d, a in ((5, 100.00), (20, 100.00))]
    return rows


def october(groceries=100.00, dining=100.00, extra=()):
    rows = [tx("2026-10-01", "Northwind Ltd", -2150.00, "Income", income_type="salary"),
            tx("2026-10-01", "Parkside Properties", 2000.00, "Rent & Housing")]
    if groceries:
        rows.append(tx("2026-10-03", "Loblaws", groceries, "Groceries"))
    if dining:
        rows.append(tx("2026-10-06", "Pai", dining, "Dining"))
    return rows + list(extra)


def build(rows, today=TODAY, pcts=None):
    s = sts.compute(rows, today)
    bills = next((r["lines"] for r in s["rows"] if r["key"] == "bills"), [])
    return cb.build(rows, today, usual_month.usual(rows, today), pcts or {}, bills)


def by_cat(result):
    return {r["category"]: r for r in result["rows"]}


class TestPreSet:
    def test_every_category_starts_at_its_usual_month(self):
        r = build(usual_rows() + october())
        rows = by_cat(r)
        assert rows["Groceries"]["budget"] == 400.00 and rows["Groceries"]["pct"] == 100
        assert rows["Dining"]["budget"] == 200.00
        assert "Rent & Housing" not in rows                            # B2
        assert [x["category"] for x in r["rows"]][:2] == ["Groceries", "Dining"]   # largest first

    def test_a_percent_of_usual_with_the_dollars(self):
        """B-02: Dining at 80% of a usual $200 is $160."""
        rows = by_cat(build(usual_rows() + october(), pcts={"Dining": 80}))
        assert (rows["Dining"]["pct"], rows["Dining"]["budget"]) == (80, 160.00)

    def test_no_full_month_no_budgets_yet(self):
        """E2: there's no usual month to start from."""
        r = cb.build(october(), TODAY, usual_month.usual(october(), TODAY), {}, [], "2026-11-01")
        assert r == {"ready": False, "starts": "2026-11-01", "month": "2026-10", "rows": [],
                     "needs_look": 0}

    @pytest.mark.parametrize("pct,ok", [(50, True), (150, True), (85, True), (100, True),
                                        (45, False), (155, False), (82, False), ("80", False)])
    def test_custom_is_50_to_150_in_5s(self, pct, ok):
        assert cb.valid_pct(pct) is ok


class TestPace:
    """By the 9th she has usually done one grocery shop ($120 of $400) and one
    of two dinners."""

    def test_on_track(self):
        g = by_cat(build(usual_rows() + october(groceries=120.00)))["Groceries"]
        assert g["by_today"] == 120.00 and g["status"] == "on"

    def test_on_pace_to_go_over(self):
        g = by_cat(build(usual_rows() + october(groceries=140.00)))["Groceries"]
        assert g["status"] == "over" and g["over_by"] is None

    def test_a_little_under_is_still_on_track(self):
        assert by_cat(build(usual_rows() + october(groceries=100.00)))["Groceries"]["status"] == "under"

    def test_over_the_month(self):
        d = by_cat(build(usual_rows() + october(dining=238.00), pcts={"Dining": 80}))["Dining"]
        assert d["status"] == "over-month" and d["over_by"] == 78.00

    def test_needs_a_look_counts_over_and_on_pace_to_go_over(self):
        """B4."""
        assert build(usual_rows() + october(groceries=120.00))["needs_look"] == 0
        assert build(usual_rows() + october(groceries=140.00, dining=238.00))["needs_look"] == 2

    def test_with_under_three_months_the_pace_is_the_day_of_the_month(self):
        rows = [t for t in usual_rows() if t.month == "2026-09"] + october()
        g = by_cat(build(rows))["Groceries"]
        assert g["by_today"] == 116.12                    # $400 × 9/31, to the cent below


class TestBills:
    def test_a_category_of_bills_has_no_pace(self):
        rows = by_cat(build(usual_rows() + october()))
        assert rows["Insurance"]["bill"] is True and rows["Insurance"]["by_today"] is None
        assert rows["Insurance"]["status"] == "to_come" and rows["Insurance"]["to_come"] == 190.00
        assert rows["Groceries"]["bill"] is False

    def test_all_paid(self):
        today = date(2026, 10, 28)
        paid = [tx("2026-10-12", "Rogers", 85.00, "Phone & Internet", account="visa"),
                tx("2026-10-20", "Belair Insurance", 190.00, "Insurance"),
                tx("2026-10-21", "Hydro One", 61.00, "Utilities"),
                tx("2026-10-22", "Netflix", 16.49, "Streaming", account="visa"),
                tx("2026-10-25", "Spotify", 11.99, "Streaming", account="visa")]
        rows = by_cat(build(usual_rows() + october(extra=paid), today))
        assert {rows[c]["status"] for c in ("Phone & Internet", "Insurance", "Utilities", "Streaming")} == {"paid"}


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "budgets.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    app.config["STORE"].add_transactions(usual_rows() + october(groceries=140.00))
    with app.test_client() as c:
        yield c


class TestTheApi:
    def test_the_page_and_the_home_card(self, client):
        page = client.get("/api/category-budgets").get_json()
        assert page["ready"] and by_cat(page)["Groceries"]["status"] == "over"
        assert page["needs_look"] == 1

    def test_changing_one_and_back(self, client):
        r = client.put("/api/category-budgets", json={"category": "Groceries", "pct": 90}).get_json()
        assert by_cat(r)["Groceries"]["budget"] == 360.00
        r = client.put("/api/category-budgets", json={"category": "Groceries", "pct": 100}).get_json()
        assert by_cat(r)["Groceries"]["pct"] == 100

    @pytest.mark.parametrize("body", [{"category": "Groceries", "pct": 47},
                                      {"category": "Groceries", "pct": True},
                                      {"category": "", "pct": 80}, {"pct": 80}])
    def test_it_checks_what_it_is_given(self, client, body):
        assert client.put("/api/category-budgets", json=body).status_code == 400

    def test_before_a_full_month(self, tmp_path, monkeypatch):
        from app import create_app
        from finance import api
        monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
        app = create_app(str(tmp_path / "new.db"))
        app.config.update(TESTING=True)
        monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
        app.config["STORE"].add_transactions(october())
        with app.test_client() as c:
            page = c.get("/api/category-budgets").get_json()
            assert page["ready"] is False and page["starts"] == "2026-11-01"
            assert c.get("/api/category-budgets").get_json()["needs_look"] == 0
