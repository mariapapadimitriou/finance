"""One-offs (THL-71 U-01 to U-03), possible duplicates (THL-165 D-01 to D-03)
and keyboard review's batch changes and shortcut preference (THL-83 K-01 to
K-04).

The ledger is the safe-to-spend fixture's: pay twice a month from mid-July,
rent, phone, insurance and hydro as Essentials, Netflix and Spotify as
Lifestyle, July to September, then October to the 9th.
"""

from __future__ import annotations

import pytest

from finance import category_budgets as cb
from finance import duplicates as dup
from finance import growth_insights as gi
from finance import look_ahead as la
from finance import recommendations as rec
from finance import safe_to_spend as sts
from finance import usual_month as um
from finance.analytics import counts_as_spending
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest
from test_category_budgets import october as budget_october, usual_rows as budget_rows
from test_recommendations import usual_rows as trend_rows
from test_safe_to_spend import TODAY, history, october, tx

ESSENTIALS = round(2000 + 85 + 190 + (60 + 64 + 57) / 3, 2)
LIFESTYLE = round(16.49 + 11.99, 2)
GARAGE = ("2026-08-15", "Garage", 1900.00, "Home")


def flagged(t: Transaction, on: str = "2026-10-09") -> Transaction:
    t.one_off_since = on
    return t


@pytest.fixture()
def app(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    app = create_app(str(tmp_path / "extras.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    return app


@pytest.fixture()
def client(app):
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def plain_october():
    return [t for t in october() if t.my_share is None and not t.repays]


def ids(st) -> dict[str, str]:
    return {t.merchant: t.fingerprint for t in st.all_transactions()}


# ── THL-71: a one-off ────────────────────────────────────────────────────

class TestOneOffMaths:
    """Left out of usual averages, projections and trend suggestions; still
    counted in its month and in safe to spend."""

    def test_left_out_of_the_usual_month(self):
        rows = history() + [tx(*GARAGE)]
        assert um.usual(rows, TODAY)["groups"]["essentials"]["usual"] > ESSENTIALS
        flagged(rows[-1])
        u = um.usual(rows, TODAY)
        assert u["groups"]["essentials"]["usual"] == ESSENTIALS
        assert "Home" not in u["categories"]

    def test_still_counts_in_its_month_and_in_safe_to_spend(self):
        ikea = tx("2026-10-03", "IKEA Etobicoke", 1480.00, "Shopping", account="visa")
        rows = history() + october() + [ikea]
        before = sts.compute(rows, TODAY, savings_target=300.0)
        flagged(ikea)
        after = sts.compute(rows, TODAY, savings_target=300.0)
        assert counts_as_spending(ikea)
        assert after["amount"] == before["amount"]
        spent = lambda s: next(r for r in s["rows"] if r["key"] == "spent")["amount"]  # noqa: E731
        assert spent(after) == spent(before)

    def test_left_out_of_budgets_pace_but_counted_as_spent(self):
        extra = tx("2026-08-08", "Restaurant Week", 600.00, "Dining")
        rows = budget_rows() + budget_october(dining=300.00) + [extra]

        def dining(rs):
            r = cb.build(rs, TODAY, um.usual(rs, TODAY), {}, [])
            return next(x for x in r["rows"] if x["category"] == "Dining")
        assert dining(rows)["usual"] == 400.00
        flagged(extra)
        d = dining(rows)
        assert d["usual"] == 200.00 and d["spent"] == 300.00
        # A one-off this month still counts as spent.
        now = flagged(tx("2026-10-07", "Le Select", 250.00, "Dining"))
        assert dining(rows + [now])["spent"] == 550.00

    def test_left_out_of_insights_averages_but_drawn_in_its_month(self):
        rows = history() + [flagged(tx("2026-08-18", "Leon's", 900.00, "Shopping"))]
        led = gi.Ledger(rows)
        assert led.spent("2026-08") - led.usual_spent("2026-08") == 90000
        u = um.usual(rows, TODAY)
        t = gi.trend(led, u, ["2026-07", "2026-08", "2026-09"], TODAY)
        assert t["band"]["high"] < 300000           # the $900 sofa isn't usual
        assert next(m for m in t["months"] if m["month"] == "2026-08")["lifestyle"] == 90000 + 2848
        cats = {r["category"]: r for r in gi.categories(led, u, "2026-10", 9, True)
                if r["category"] == "Shopping"}
        assert cats == {} or cats["Shopping"]["by_today"] == 0

    def test_left_out_of_projections(self):
        months = ["2026-07", "2026-08", "2026-09"]
        rows = [Transaction(date=d, description="PAI", merchant="Pai", amount=a,
                            category="Dining", account_id="visa")
                for d, a in (("2026-07-20", 300), ("2026-08-28", 400), ("2026-09-30", 500))]
        big = Transaction(date="2026-09-25", description="TRAVEL", merchant="Air Canada",
                          amount=1200, category="Shopping", account_id="visa")
        assert la.rest_of_month(rows + [big], TODAY, months, set())["high"] == 170000
        flagged(big)
        assert la.rest_of_month(rows + [big], TODAY, months, set())["high"] == 50000
        per_day = la.everyday_per_day(rows + [big], TODAY, months, set())
        assert per_day == la.everyday_per_day(rows, TODAY, months, set())

    def test_left_out_of_the_trend_suggestion(self):
        rows = trend_rows() + budget_october(dining=100.00)
        party = tx("2026-10-07", "Birthday dinner", 300.00, "Dining")
        u = um.usual(rows + [party], TODAY)
        assert rec.trend(rows + [party], TODAY, u) is not None
        flagged(party)
        assert rec.trend(rows + [party], TODAY, um.usual(rows + [party], TODAY)) is None


class TestOneOffApi:
    def load(self, client, extra=()):
        client.st.add_transactions(history() + plain_october() + list(extra))
        return ids(client.st)

    def test_marking_says_which_average_changed_and_undo_unticks(self, client, app):
        from finance import api
        i = self.load(client, [tx("2026-10-03", "IKEA Etobicoke", 1480.00, "Shopping",
                                  account="visa")])
        with app.app_context():
            before = api._safe_left(client.st, client.st.all_transactions())
        r = client.put(f"/api/transactions/{i['IKEA Etobicoke']}/one-off", json={"on": True})
        assert r.status_code == 200, r.get_json()
        body = r.get_json()
        assert body["title"] == "Left out of your usual month."
        assert body["detail"] == ("A usual month of Lifestyle stays $28 instead of rising to "
                                  "$522. It still counts in October.")
        with app.app_context():
            assert api._safe_left(client.st, client.st.all_transactions()) == before

        # U-02: the row says so; U-03: the detail says since when.
        row = next(t for t in client.get("/api/transactions/list?month=2026-10")
                   .get_json()["transactions"] if t["merchant"] == "IKEA Etobicoke")
        assert row["one_off"] and row["note"] == "Unusual · left out of your usual month"
        assert row["counts"] == "spending"
        detail = client.get(f"/api/transactions/{i['IKEA Etobicoke']}").get_json()
        assert detail["one_off_line"]["line"] == ("Left out since October 9. "
                                                  "A usual month of Lifestyle: $28.")

        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        assert not client.st.get_transaction(i["IKEA Etobicoke"]).one_off

    def test_a_past_month_moves_the_usual_month_now(self, client):
        i = self.load(client, [tx(*GARAGE)])
        body = client.put(f"/api/transactions/{i['Garage']}/one-off",
                          json={"on": True}).get_json()
        assert body["detail"] == ("A usual month of Essentials is now $2,335 instead of "
                                  "$2,969. It still counts in August.")
        off = client.put(f"/api/transactions/{i['Garage']}/one-off", json={"on": False}).get_json()
        assert off["title"] == "Back in your usual month."
        assert off["detail"] == "A usual month of Essentials is now $2,969 instead of $2,335."

    @pytest.mark.parametrize("merchant", ["TD Visa payment", "To savings"])
    def test_only_on_a_transaction_that_counts(self, client, merchant):
        i = self.load(client)
        r = client.put(f"/api/transactions/{i[merchant]}/one-off", json={"on": True})
        assert r.status_code == 400
        assert not client.st.get_transaction(i[merchant]).one_off

    def test_not_on_a_linked_repayment(self, client):
        i = self.load(client, [tx("2026-10-05", "Sushi Nami", 85.00, "Dining", account="visa"),
                               tx("2026-10-08", "Priya", -42.50, "Transfers")])
        client.st.link_payback(i["Sushi Nami"], i["Priya"])
        r = client.put(f"/api/transactions/{i['Priya']}/one-off", json={"on": True})
        assert r.status_code == 400


# ── THL-165: possible duplicates ─────────────────────────────────────────

def card_row(day, description, amount, source, **raw):
    return Transaction(date=day, description=description, amount=amount, account_id="visa",
                       account_name="Visa ··4421", source=source, category="Groceries",
                       raw={"account_type": "credit", **raw})


def feed(st, *rows):
    out = {}
    for r in rows:
        out = ingest(st, IngestResult(transactions=[r], account_id=r.account_id))
    return out


def month_list(client):
    res = client.get("/api/transactions/list?month=2026-10")
    assert res.status_code == 200
    return res.get_json()


class TestDetection:
    def test_a_statement_file_beside_the_bank_connection(self):
        bank = card_row("2026-10-07", "LOBLAWS #1032 TORONTO ON", 96.32, "plaid", plaid_id="p1")
        file = card_row("2026-10-07", "LOBLAWS 1032 TORONTO", 96.32, "csv")
        [(copy, twin)] = dup.detect([bank, file], same_card=set())
        assert (copy.source, twin.source) == ("csv", "plaid")
        assert dup.source_label(copy) == "from a statement file"
        assert dup.source_label(twin) == "from your bank connection"

    def test_a_pending_row_whose_posted_twin_never_named_it(self):
        pending = card_row("2026-10-05", "UBER EATS", 24.80, "plaid", plaid_id="p1", pending=True)
        posted = card_row("2026-10-06", "UBER EATS TORONTO", 24.80, "plaid", plaid_id="q1")
        [(copy, twin)] = dup.detect([pending, posted], same_card=set())
        assert copy is pending and twin is posted

    def test_a_card_linked_twice(self):
        a = card_row("2026-10-07", "LOBLAWS", 96.32, "plaid", plaid_id="p1")
        b = card_row("2026-10-07", "LOBLAWS", 96.32, "plaid", plaid_id="x9")
        b.account_id = "visa-again"
        assert dup.detect([a, b], same_card=set()) == []
        assert len(dup.detect([a, b], same_card={("visa", "visa-again")})) == 1

    def test_two_coffees_from_one_feed_are_two_coffees(self):
        a = card_row("2026-10-07", "BALZACS", 6.40, "plaid", plaid_id="p1")
        b = card_row("2026-10-07", "BALZACS", 6.40, "plaid", plaid_id="p2")
        b.seq = 1
        assert dup.detect([a, b], same_card=set()) == []

    def test_different_merchants_or_far_apart_are_not_asked_about(self):
        bank = card_row("2026-10-07", "LOBLAWS", 96.32, "plaid")
        assert dup.detect([bank, card_row("2026-10-07", "SHOPPERS DRUG MART", 96.32, "csv")],
                          same_card=set()) == []
        assert dup.detect([bank, card_row("2026-10-20", "LOBLAWS", 96.32, "csv")],
                          same_card=set()) == []


class TestTheQuestion:
    def setup(self, client):
        feed(client.st,
             card_row("2026-10-07", "LOBLAWS #1032 TORONTO ON", 96.32, "plaid", plaid_id="p1"),
             card_row("2026-10-05", "PRESTO", 40.00, "plaid", plaid_id="p2"))
        result = feed(client.st, card_row("2026-10-07", "LOBLAWS 1032 TORONTO", 96.32, "csv"))
        assert result["possible_duplicates"] == 1
        copy = next(t for t in client.st.all_transactions() if t.source == "csv")
        return copy.fingerprint

    def test_counted_once_until_she_answers(self, client):
        copy = self.setup(client)
        data = month_list(client)
        assert data["totals"]["spent"] == round(96.32 + 40.00, 2)
        row = next(r for r in data["transactions"] if r["id"] == copy)
        assert row["counts"] == "none"
        assert row["chip"] == {"label": "Possible duplicate", "suggested": True}
        assert row["note"] == "Possible duplicate · counted once until you check"
        assert row["source_label"] == "from a statement file"
        twin = next(r for r in data["transactions"] if r["description"].startswith("LOBLAWS #"))
        assert twin["source_label"] == "from your bank connection"
        assert twin["counts"] == "spending"

        review = client.get("/api/review").get_json()
        assert review["count"] == 1
        [q] = review["duplicate"]
        assert q["key"] == f"dup:{copy}"
        assert (q["txn"]["source_label"], q["twin"]["source_label"]) == (
            "from a statement file", "from your bank connection")
        assert q["reason"].startswith("The same amount came in from two places on the same day.")

    def test_same_purchase_soft_hides_the_copy_and_undo_asks_again(self, client):
        copy = self.setup(client)
        r = client.post(f"/api/review/duplicates/{copy}", json={"answer": "same"})
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["title"] == "Kept one. Your numbers didn’t change."
        assert body["detail"] == "We were already counting it once."
        data = month_list(client)
        assert copy not in {r["id"] for r in data["transactions"]}
        assert data["totals"]["spent"] == round(96.32 + 40.00, 2)
        # Nothing was deleted.
        assert client.st.get_transaction(copy) is not None
        assert client.get("/api/review").get_json()["count"] == 0
        # Not among the rows she left out either.
        left = client.get("/api/transactions/list?month=2026-10&excluded=1").get_json()
        assert left["total"] == 0

        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        assert client.get("/api/review").get_json()["count"] == 1
        assert copy in {r["id"] for r in month_list(client)["transactions"]}

    def test_two_different_purchases_both_count(self, client):
        copy = self.setup(client)
        body = client.post(f"/api/review/duplicates/{copy}",
                           json={"answer": "different"}).get_json()
        assert body["title"].startswith("Kept both.")
        data = month_list(client)
        assert data["totals"]["spent"] == round(2 * 96.32 + 40.00, 2)
        assert client.get("/api/review").get_json()["count"] == 0
        # Answered once, never asked again — even after another sync.
        feed(client.st, card_row("2026-10-08", "METRO", 12.00, "plaid", plaid_id="p3"))
        assert client.get("/api/review").get_json()["count"] == 0
        client.post("/api/transactions/undo", json=body["undo"])
        assert month_list(client)["totals"]["spent"] == round(96.32 + 40.00 + 12.00, 2)

    def test_a_bad_answer_is_refused(self, client):
        copy = self.setup(client)
        assert client.post(f"/api/review/duplicates/{copy}", json={"answer": "x"}).status_code == 400
        assert client.post("/api/review/duplicates/nope", json={"answer": "same"}).status_code == 404

    def test_exact_repeats_are_skipped_silently_and_only_logged(self, client):
        rows = [card_row("2026-10-07", "LOBLAWS #1032", 96.32, "plaid", plaid_id="p1"),
                card_row("2026-10-05", "PRESTO", 40.00, "plaid", plaid_id="p2")]
        first = ingest(client.st, IngestResult(transactions=rows, account_id="visa"))
        again = ingest(client.st, IngestResult(transactions=[
            card_row("2026-10-07", "LOBLAWS #1032", 96.32, "plaid", plaid_id="p1"),
            card_row("2026-10-05", "PRESTO", 40.00, "plaid", plaid_id="p2")], account_id="visa"))
        assert (first["imported"], again["imported"], again["duplicates"]) == (2, 0, 2)
        assert again["possible_duplicates"] == 0
        assert len(client.st.all_transactions()) == 2
        assert client.get("/api/review").get_json()["count"] == 0
        with client.st.conn() as c:
            logged = [r["duplicates"] for r in c.execute(
                "SELECT duplicates FROM imports ORDER BY id").fetchall()]
        assert logged == [0, 2]

    def test_added_anyway_by_hand_is_not_asked_about(self, client):
        feed(client.st, card_row("2026-10-07", "LOBLAWS", 96.32, "plaid", plaid_id="p1"))
        r = client.post("/api/transactions", json={"date": "2026-10-07", "description": "Loblaws",
                                                   "amount": 96.32, "confirm": True})
        assert r.status_code == 200, r.get_json()
        feed(client.st, card_row("2026-10-08", "METRO", 12.00, "plaid", plaid_id="p3"))
        assert client.get("/api/review").get_json()["count"] == 0


# ── THL-83: keyboard review ──────────────────────────────────────────────

class TestBatchCategory:
    def load(self, client):
        rows = [tx("2026-10-09", "Uber Eats", 24.80, "Food Delivery", account="visa"),
                tx("2026-10-08", "DoorDash", 31.60, "Food Delivery", account="visa"),
                tx("2026-10-07", "SkipTheDishes", 27.15, "Food Delivery", account="visa"),
                tx("2026-10-07", "Uber Eats", 19.90, "Food Delivery", account="visa"),
                tx("2026-10-01", "Uber Eats", 22.00, "Food Delivery", account="visa")]
        client.st.add_transactions(history() + rows)
        txns = client.st.all_transactions()
        picked = [t.fingerprint for t in txns if t.date[:7] == "2026-10" and t.date >= "2026-10-07"]
        other = next(t.fingerprint for t in txns if t.date == "2026-10-01")
        return picked, other

    def test_preview_says_what_it_will_do(self, client):
        picked, _ = self.load(client)
        r = client.post("/api/transactions/batch/category/preview",
                        json={"ids": picked, "category": "Dining"})
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["line"] == "All 4 are Lifestyle now, so your safe to spend stays the same."
        assert all(t.category == "Food Delivery" for t in client.st.all_transactions()
                   if t.fingerprint in picked)

    def test_changes_them_all_with_one_undo_and_no_merchant_rule(self, client):
        picked, other = self.load(client)
        r = client.post("/api/transactions/batch/category",
                        json={"ids": picked, "category": "Dining"})
        body = r.get_json()
        assert r.status_code == 200, body
        assert body["title"] == "Changed 4 to Dining. Your safe to spend stays the same."
        assert body["detail"] == "All 4 were already Lifestyle."
        by_id = {t.fingerprint: t for t in client.st.all_transactions()}
        assert all(by_id[i].category == "Dining" for i in picked)
        # Bulk changes never write a rule: the other Uber Eats row is untouched.
        assert client.st.overrides() == {}
        assert by_id[other].category == "Food Delivery"

        assert client.post("/api/transactions/undo", json=body["undo"]).status_code == 200
        by_id = {t.fingerprint: t for t in client.st.all_transactions()}
        assert all(by_id[i].category == "Food Delivery" for i in picked)

    def test_refuses_nothing_or_an_unknown_category(self, client):
        picked, _ = self.load(client)
        assert client.post("/api/transactions/batch/category",
                           json={"ids": [], "category": "Dining"}).status_code == 400
        assert client.post("/api/transactions/batch/category",
                           json={"ids": picked, "category": "Nope"}).status_code == 400
        assert client.post("/api/transactions/batch/category",
                           json={"ids": ["nope"], "category": "Dining"}).status_code == 404

    def test_confirm_suggestions_with_one_undo(self, client):
        picked, _ = self.load(client)
        # Only a guess Pearl isn't sure of is a suggestion (2026-10-14): these
        # four are Plaid's label at low confidence.
        client.st.set_categories({i: ("Food Delivery", "issuer") for i in picked})
        with client.st.conn() as c:
            for i in picked:
                c.execute("UPDATE transactions SET raw = ? WHERE id = ?",
                          ('{"category_confidence": "LOW"}', i))
        body = client.post("/api/transactions/batch/confirm", json={"ids": picked}).get_json()
        assert body["title"] == "Confirmed 4 suggestions."
        assert set(client.st.confirmed_categories()) == set(picked)
        client.post("/api/transactions/undo", json=body["undo"])
        assert client.st.confirmed_categories() == {}


class TestShortcutPreference:
    def test_on_by_default_off_when_she_says_and_kept(self, client):
        assert client.get("/api/preferences").get_json() == {"single_key_shortcuts": True}
        r = client.put("/api/preferences", json={"single_key_shortcuts": False})
        assert r.get_json() == {"single_key_shortcuts": False}
        assert client.st.setting("single_key_shortcuts") == "0"
        assert client.get("/api/preferences").get_json() == {"single_key_shortcuts": False}

    def test_only_true_or_false(self, client):
        assert client.put("/api/preferences",
                          json={"single_key_shortcuts": "no"}).status_code == 400
