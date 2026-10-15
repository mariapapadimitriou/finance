"""Recommendation cards (THL-12 E08: THL-60 to THL-63; THL-133 RC-01 to RC-03).

Each rule's thresholds, its numbers, the two-card limit and the 30-day
"Not for me".
"""

from datetime import date

import pytest

from finance import recommendations as rec, secrets_box, usual_month
from test_category_budgets import october, usual_rows as budget_rows
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, tx


def usual_rows():
    """The budget tests' three months, with dinners out at a different place
    each time, as they are: the same restaurant on the same days for the same
    amount would look like a subscription."""
    rows = [t for t in budget_rows() if t.merchant != "Pai"]
    for m in ("07", "08", "09"):
        rows += [tx(f"2026-{m}-05", f"Bistro {m}", 100.00, "Dining"),
                 tx(f"2026-{m}-20", f"Cafe {m}", 100.00, "Dining")]
    return rows


def trend(rows, today=TODAY):
    return rec.trend(rows, today, usual_month.usual(rows, today))


class TestSpendingTrend:
    """Dining is usually $100 by the 9th (one $100 dinner on the 5th)."""

    def test_25_percent_above_usual_for_this_point_in_the_month(self):
        c = trend(usual_rows() + october(dining=130.00))
        assert c["title"] == "Dining is running about 30% above usual"
        assert c["body"] == "$130 so far, compared with a usual $100 by October 9."
        assert c["why"]["text"] == ("So far this month you’ve spent $130 on dining. By October 9 you "
                                    "usually spend about $100 (average of July to September).")
        assert c["action"] == {"label": "See dining", "to": "transactions",
                               "filters": {"month": "2026-10", "category": "Dining"}}
        assert c["impact"] == 360.00

    def test_under_25_percent_is_no_card(self):
        assert trend(usual_rows() + october(dining=124.00)) is None

    def test_a_small_gap_is_no_card(self):
        """+50% on a $10 habit is $5: not worth a card."""
        rows = usual_rows() + [tx(f"2026-{m}-02", "Tim Hortons", 10.00, "Coffee") for m in ("07", "08", "09")]
        rows += october(dining=100.00) + [tx("2026-10-02", "Tim Hortons", 15.00, "Coffee")]
        assert trend(rows) is None

    def test_essentials_never_trend(self):
        assert trend(usual_rows() + october(groceries=400.00, dining=100.00)) is None

    def test_needs_three_full_months(self):
        rows = [t for t in usual_rows() if t.month >= "2026-08"] + october(dining=200.00)
        assert trend(rows) is None


class TestSubscriptions:
    def test_a_yearly_total(self):
        """Netflix $16.49 and Spotify $11.99 every month."""
        c = rec.subscriptions(history(), TODAY)
        assert c["title"] == "You pay $28 a month for 2 subscriptions"
        assert c["body"] == "That’s $342 a year. Still using them all? Pearl won’t cancel anything."
        assert [line["label"] for line in c["why"]["lines"]] == ["Netflix", "Spotify"]
        assert c["why"]["lines"][0]["yearly"] == pytest.approx(197.88)
        assert c["action"]["filters"] == {"recurring": "1", "month": "2026-09"}

    def test_one_subscription_is_no_card(self):
        rows = [t for t in history() if t.merchant != "Spotify"]
        assert rec.subscriptions(rows, TODAY) is None

    def test_a_regular_dinner_is_not_a_subscription(self):
        rows = history() + [tx(f"2026-{m}-05", "Pai", 100.00, "Dining") for m in ("07", "08", "09")]
        assert rec.subscriptions(rows, TODAY)["numbers"]["count"] == 2

    def test_bills_are_not_subscriptions(self):
        lines = rec.subscriptions(history(), TODAY)["why"]["lines"]
        assert not {"Rogers", "Hydro One", "Belair Insurance", "Parkside Properties"} & {x["label"] for x in lines}


ANCHOR = {"started": True, "full": False, "to_go": 2000.0, "counted": 600.0, "target": 2600.0,
          "pace": {"usual": 260.0}}


class TestAnchorPace:
    def test_a_little_more_each_paycheque(self):
        """$40 more a month on $260: 2,000 ÷ 260 = 7.7 months, ÷ 300 = 6.7."""
        c = rec.pace(ANCHOR, 2)
        assert c["title"] == "Putting away $20 more each paycheque gets your Anchor to 3 months about 4 weeks sooner"
        assert c["body"] == "Based on your usual pace of $260 a month."
        assert c["action"]["goals"] == {"view": "whatif", "monthly": 300.0}
        assert c["impact"] == 480.0

    def test_paid_monthly(self):
        assert "each month" in rec.pace(ANCHOR, 1)["title"]

    @pytest.mark.parametrize("anchor", [
        {**ANCHOR, "started": False},                       # R2: only once started
        {**ANCHOR, "full": True},
        {**ANCHOR, "pace": {"usual": 0}},
        {**ANCHOR, "to_go": 150.0},                         # less than 2 weeks sooner
    ])
    def test_no_card(self, anchor):
        assert rec.pace(anchor, 2) is None


class TestIdleCash:
    def test_start_the_anchor_without_one(self):
        """R2: idle cash shows without an Anchor."""
        c = rec.idle({"started": False, "full": False, "target": 6900.0}, 3850.00, 2300.00)
        assert c["title"] == "Your chequing has stayed above $3,800 for 3 months"
        assert c["body"] == "Moving $1,550 to savings would start your Anchor at $1,550 and still leave a month of Essentials in chequing."
        assert c["action"]["goals"] == {"view": "start", "amount": 1550}

    def test_from_here_to_there_but_never_below_a_month_of_essentials(self):
        c = rec.idle(ANCHOR, 3850.00, 2300.00)
        assert c["numbers"]["amount"] == 1550                     # 3,850 − 2,300, in $50s
        assert "take your Anchor from $600 to $2,150" in c["body"]

    @pytest.mark.parametrize("low,essentials,anchor", [
        (2350.00, 2300.00, ANCHOR),                               # under $100 to spare
        (None, 2300.00, ANCHOR),                                  # not 3 months of history
        (3850.00, None, ANCHOR),
        (9000.00, 2300.00, {**ANCHOR, "full": True}),
    ])
    def test_no_card(self, low, essentials, anchor):
        assert rec.idle(anchor, low, essentials) is None

    def test_the_lowest_balance_over_90_days(self):
        rows = [tx("2026-06-01", "Opening", -100.00, "Income"),
                tx("2026-08-15", "Landlord", 2000.00, "Rent & Housing"),
                tx("2026-08-16", "Northwind Ltd", -2150.00, "Income", income_type="salary")]
        # $5,000 today; on Aug 15, after rent and before pay, $2,850.
        assert rec.lowest_balance({"chq": 5000.00}, rows, TODAY) == 2850.00
        assert rec.lowest_balance({"chq": 5000.00}, rows[1:], TODAY) is None


def card(kind, impact):
    return {"type": kind, "impact": impact}


class TestChoosing:
    def test_at_most_two_biggest_yearly_impact_first(self):
        """R4."""
        cards = [card("trend", 360), card("subscriptions", 768), card("pace", 480), card("idle", 500)]
        assert [c["type"] for c in rec.choose(cards, {}, TODAY)] == ["subscriptions", "idle"]

    def test_not_for_me_hides_the_type_for_30_days(self):
        cards = [card("trend", 360), card("subscriptions", 768)]
        assert [c["type"] for c in rec.choose(cards, {"subscriptions": "2026-09-10"}, TODAY)] == ["trend"]
        # 30 days on, it's back.
        assert len(rec.choose(cards, {"subscriptions": "2026-09-09"}, TODAY)) == 2

    def test_no_card_without_its_data(self):
        assert rec.choose([None, None, card("idle", 500), None], {}, TODAY) == [card("idle", 500)]


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "rec.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    app.config["STORE"].add_transactions(usual_rows() + october(dining=130.00))
    with app.test_client() as c:
        yield c


class TestTheApi:
    def test_home_has_at_most_two(self, client):
        cards = client.get("/api/home").get_json()["recommendations"]
        assert [c["type"] for c in cards] == ["trend", "subscriptions"]

    def test_not_for_me_and_undo(self, client):
        r = client.put("/api/recommendations/trend/dismiss").get_json()
        assert r == {"type": "trend", "hidden_until": "2026-11-08"}
        assert [c["type"] for c in client.get("/api/home").get_json()["recommendations"]] == ["subscriptions"]
        client.delete("/api/recommendations/trend/dismiss")
        assert len(client.get("/api/home").get_json()["recommendations"]) == 2
        assert client.put("/api/recommendations/lottery/dismiss").status_code == 404

    def test_review_subscriptions_lists_their_charges(self, client):
        rows = client.get("/api/transactions/list?recurring=1&month=2026-09").get_json()["transactions"]
        merchants = {r["merchant"] for r in rows}
        assert merchants == {"Netflix", "Spotify"}
        assert not any(m.startswith(("Bistro", "Cafe")) for m in merchants)
