"""Your plan (YP-01 to YP-06, note 1353:11493; product owner, 2026-11-15).

The rules these hold: a plan only proposes, and the Allowance changes only
after "Use this plan" (YP-02); while it's in use a change counts at once, the
chat's Set it included; every amount rounds to the nearest $5, so the chat's
$220 stays $220; Remove and Stop give her usual back.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance import your_plan as yp
from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
FIRST = TODAY.replace(day=1)
INCOME = 4000.0


def tx(desc, amount, when, issuer, account="visa"):
    return Transaction(date=when.isoformat(), description=desc, merchant=desc.title(), amount=amount,
                       account_id=account, account_name="TD Visa",
                       raw={"account_type": "credit", "issuer_category": issuer})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "plan.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


# Each month somewhere different, for different amounts, so nothing here
# looks like a bill: Dining $214 a month, Groceries $412.
MONTHS = (
    (("PAI NORTHERN THAI", 100.0), ("SUSHI NAMI", 114.0), ("FRESHCO", 200.0), ("METRO", 212.0)),
    (("BURGER BARN", 130.0), ("TACO TIME", 84.0), ("NOFRILLS", 150.0), ("LOBLAWS", 262.0)),
    (("RAMEN HOUSE", 95.0), ("PHO 88", 119.0), ("FARM BOY", 300.0), ("SOBEYS", 112.0)),
    (("CAFE LUNA", 60.0), ("GRILL 21", 154.0), ("FOODLAND", 180.0), ("SAFEWAY", 232.0)),
)


def history(c):
    """Whole months of Dining ($214 a month) and Groceries ($412 a month),
    and this month's $46 of Dining so far; her income is $4,000."""
    rows = []
    m = FIRST
    for i, month in enumerate(MONTHS):
        m = (m.replace(day=1) - timedelta(days=1)).replace(day=1)
        for j, (name, amount) in enumerate(month):
            rows.append(tx(name, amount, m + timedelta(days=3 + 5 * j + i),
                           "FOOD_AND_DRINK" if j < 2 else "GROCERIES"))
    rows.append(tx("NOODLE BAR", 46.0, FIRST, "FOOD_AND_DRINK"))
    ingest(c.st, IngestResult(rows, "visa"))
    c.st.set_setting("home_income", INCOME)


def allowance(c) -> float:
    return c.get("/api/home").get_json()["safe_to_spend"]["amount"]


def plan(c) -> dict:
    return c.get("/api/your-plan").get_json()


def category(c, name) -> str:
    """The category Pearl filed a merchant under, as the plan names it."""
    return next(t.category for t in c.st.all_transactions() if t.description == name)


class TestRounding:
    @pytest.mark.parametrize("given, kept", [(214, 220), (210, 210), (210.01, 220), (209.999, 210),
                                             (412, 420), (0.5, 10)])
    def test_suggestions_round_up_to_ten(self, given, kept):
        assert yp.round_up_10(given) == kept

    @pytest.mark.parametrize("given, kept", [(220, 220), (214, 215), (212.5, 215), (212.49, 210),
                                             (2.5, 5), (1180, 1180)])
    def test_nearest_five(self, given, kept):
        assert yp.round_5(given) == kept

    def test_a_row_keeps_the_nearest_five(self, client):
        history(client)
        dining = category(client, "NOODLE BAR")
        for given, kept in ((220, 220), (214, 215), (223, 225), (212.49, 210)):
            r = client.put(f"/api/your-plan/rows/{dining}", json={"amount": given}).get_json()
            assert r["rows"][0]["amount"] == kept

    def test_the_chats_220_stays_220(self, client):
        history(client)
        p = client.post("/api/chat/plan", json={"text": "make me a plan for eating out"}).get_json()
        assert p["amount"] == 220
        r = client.put(f"/api/your-plan/rows/{p['category']}", json={"amount": p["amount"], "source": "chat"})
        assert r.get_json()["rows"] == [{"category": p["category"], "amount": 220, "source": "chat",
                                         "usual": pytest.approx(214.0)}]

    def test_nothing_below_five_and_no_words_for_amounts(self, client):
        history(client)
        dining = category(client, "NOODLE BAR")
        for bad in (2, 0, -5, "a lot", None, True, 10**9):
            assert client.put(f"/api/your-plan/rows/{dining}", json={"amount": bad}).status_code == 400
        assert client.put("/api/your-plan/rows/Income", json={"amount": 100}).status_code == 400
        assert plan(client)["rows"] == []


class TestNothingChangesUntilUse:
    def test_suggest_and_changes_leave_the_allowance_alone(self, client):
        history(client)
        before = allowance(client)
        empty = plan(client)
        assert empty["rows"] == [] and empty["in_use"] is False   # YP-06
        r = client.post("/api/your-plan/suggest").get_json()
        dining, groceries = category(client, "NOODLE BAR"), category(client, "METRO")
        # One rule for suggestions (note 1353:11493): up to the next $10,
        # as the chat's, so $214 is $220 here and in the chat.
        assert {x["category"]: x["amount"] for x in r["rows"]} == {groceries: 420, dining: 220}
        chat = client.post("/api/chat/plan", json={"category": dining}).get_json()
        assert chat["amount"] == 220
        assert all(x["source"] == "pearl" for x in r["rows"])
        assert r["in_use"] is False and r["since"] is None
        client.put(f"/api/your-plan/rows/{dining}", json={"amount": 180})
        client.delete(f"/api/your-plan/rows/{groceries}")
        assert allowance(client) == before

    def test_use_sets_the_plan_aside_from_today(self, client):
        history(client)
        before = allowance(client)
        dining, groceries = category(client, "NOODLE BAR"), category(client, "METRO")
        client.put(f"/api/your-plan/rows/{dining}", json={"amount": 220})
        client.put(f"/api/your-plan/rows/{groceries}", json={"amount": 400})
        page = plan(client)
        # YP-01's WHAT IT MEANS: income less bills less the plan.
        assert page["total"] == 620
        assert page["allowance"] == pytest.approx(page["income"] - page["bills"] - 620)
        r = client.post("/api/your-plan/use").get_json()
        assert r["in_use"] is True and r["since"] == TODAY.isoformat()
        # $46 of Dining is already spent (and already off the Allowance), so
        # $174 of it is held back, and all $400 of Groceries.
        assert allowance(client) == pytest.approx(before - 174 - 400)
        sts = client.get("/api/home").get_json()["safe_to_spend"]
        held = next(row for row in sts["rows"] if row["key"] == "plan")
        assert held["amount"] == pytest.approx(574)

    def test_undo_puts_it_back(self, client):
        history(client)
        before = allowance(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.post("/api/your-plan/use")
        assert allowance(client) < before
        r = client.post("/api/your-plan/undo").get_json()
        assert r["in_use"] is False and r["since"] is None and len(r["rows"]) == 1
        assert allowance(client) == before

    def test_no_plan_to_use(self, client):
        history(client)
        assert client.post("/api/your-plan/use").status_code == 409

    def test_no_suggestion_while_in_use(self, client):
        history(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.post("/api/your-plan/use")
        assert client.post("/api/your-plan/suggest").status_code == 409

    def test_no_history_no_suggestion(self, client):
        assert client.post("/api/your-plan/suggest").status_code == 409


class TestChatSetIt:
    def test_not_in_use_it_is_only_a_row(self, client):
        history(client)
        before = allowance(client)
        p = client.post("/api/chat/plan", json={"category": "Dining"}).get_json()
        client.put(f"/api/your-plan/rows/{p['category']}", json={"amount": p["amount"], "source": "chat"})
        assert allowance(client) == before
        assert plan(client)["rows"][0]["source"] == "chat"

    def test_in_use_set_it_changes_the_allowance_at_once(self, client):
        history(client)
        dining, groceries = category(client, "NOODLE BAR"), category(client, "METRO")
        client.put(f"/api/your-plan/rows/{groceries}", json={"amount": 400})
        client.post("/api/your-plan/use")
        before = allowance(client)
        p = client.post("/api/chat/plan", json={"category": "Dining"}).get_json()
        assert p["in_use"] is True
        client.put(f"/api/your-plan/rows/{p['category']}", json={"amount": p["amount"], "source": "chat"})
        # The chat's confirm is the confirm: $220 less the $46 spent.
        assert allowance(client) == pytest.approx(before - 174)
        assert plan(client)["in_use"] is True
        assert dining == p["category"]


class TestRemoveAndStop:
    def test_remove_gives_the_usual_back(self, client):
        history(client)
        before = allowance(client)
        dining, groceries = category(client, "NOODLE BAR"), category(client, "METRO")
        client.put(f"/api/your-plan/rows/{dining}", json={"amount": 220})
        client.put(f"/api/your-plan/rows/{groceries}", json={"amount": 400})
        client.post("/api/your-plan/use")
        r = client.delete(f"/api/your-plan/rows/{dining}").get_json()
        assert [x["category"] for x in r["rows"]] == [groceries] and r["in_use"] is True
        assert allowance(client) == pytest.approx(before - 400)
        # The last one out stops the plan.
        r = client.delete(f"/api/your-plan/rows/{groceries}").get_json()
        assert r["rows"] == [] and r["in_use"] is False
        assert allowance(client) == before
        assert client.delete(f"/api/your-plan/rows/{groceries}").status_code == 404

    def test_stop_keeps_the_rows_as_a_proposal(self, client):
        history(client)
        before = allowance(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.post("/api/your-plan/use")
        r = client.post("/api/your-plan/stop").get_json()
        assert r["in_use"] is False and r["since"] is None and r["rows"][0]["amount"] == 220
        assert allowance(client) == before

    def test_yp07_says_the_allowance_without_the_plan(self, client):
        history(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        page = plan(client)
        assert page["allowance_without"] == pytest.approx(page["income"] - page["bills"])
        assert page["allowance"] == pytest.approx(page["allowance_without"] - 220)

    def test_undo_on_stop_uses_it_again_since_the_same_day(self, client):
        history(client)
        before = allowance(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.post("/api/your-plan/use")
        held = allowance(client)
        # As if she'd started it a while ago.
        state = yp.load(client.st)
        state["since"] = (TODAY - timedelta(days=9)).isoformat()
        yp.save(client.st, state)
        client.post("/api/your-plan/stop")
        assert allowance(client) == before
        r = client.post("/api/your-plan/resume").get_json()
        assert r["in_use"] is True and r["since"] == (TODAY - timedelta(days=9)).isoformat()
        assert allowance(client) == held
        # Once in use again, there's nothing left to resume from.
        assert yp.load(client.st)["stopped_since"] is None

    def test_undo_on_use_forgets_any_earlier_day(self, client):
        history(client)
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.post("/api/your-plan/use")
        client.post("/api/your-plan/stop")
        client.post("/api/your-plan/use")
        client.post("/api/your-plan/undo")
        assert yp.load(client.st)["stopped_since"] is None

    def test_nothing_to_resume_without_rows(self, client):
        assert client.post("/api/your-plan/resume").status_code == 409

    def test_start_over_clears_it(self, client):
        assert "your_plan" in client.st.START_OVER_SETTINGS


class TestSetAside:
    def test_never_below_zero_and_bills_are_not_counted_twice(self):
        d = FIRST.isoformat()
        t1 = Transaction(date=d, description="SUSHI", merchant="Sushi", amount=300.0, account_id="a",
                         category="Dining")
        t2 = Transaction(date=d, description="PHONECO", merchant="Phoneco", amount=60.0, account_id="a",
                         category="Phone")
        held = yp.set_aside([t1, t2], TODAY, {"Dining": 220.0, "Phone": 80.0}, {("Phoneco", d)})
        by = {line["label"]: line["amount"] for line in held["lines"]}
        assert by == {"Dining": 0.0, "Phone": 80.0}
        assert held["amount_c"] == 8000
        assert yp.set_aside([t1], TODAY, {}) is None


class TestAddACategory:
    def test_yp08_lists_what_isnt_in_the_plan_largest_first_zero_last(self, client):
        history(client)
        dining, groceries = category(client, "NOODLE BAR"), category(client, "METRO")
        cats = client.get("/api/your-plan/categories").get_json()["categories"]
        names = [c["category"] for c in cats]
        assert names[:2] == [groceries, dining]
        assert cats[0]["usual"] == pytest.approx(412.0) and cats[0]["amount"] == 410   # nearest $5
        assert cats[1]["amount"] == 215
        # No spending in her usual month: listed last, at $0, by name.
        zeros = [c for c in cats if c["usual"] == 0]
        assert zeros and cats[-len(zeros):] == zeros
        assert [c["category"] for c in zeros] == sorted(c["category"] for c in zeros)
        assert all(c["amount"] == 0 for c in zeros)
        # Never a category a plan can't have.
        assert "Income" not in names and "Rent & Housing" not in names
        assert "Unsorted transfers" not in names

    def test_one_in_the_plan_leaves_the_list(self, client):
        history(client)
        dining = category(client, "NOODLE BAR")
        client.put(f"/api/your-plan/rows/{dining}", json={"amount": 215})
        names = [c["category"] for c in client.get("/api/your-plan/categories").get_json()["categories"]]
        assert dining not in names


class TestIncomeAndBillsCard:
    def test_yp09_none_yet_not_in_use_and_in_use(self, client):
        history(client)
        card = lambda: client.get("/api/income-bills").get_json()["your_plan"]   # noqa: E731
        assert card() == {"rows": 0, "in_use": False, "total": 0}
        client.put(f"/api/your-plan/rows/{category(client, 'NOODLE BAR')}", json={"amount": 220})
        client.put(f"/api/your-plan/rows/{category(client, 'METRO')}", json={"amount": 400})
        assert card() == {"rows": 2, "in_use": False, "total": 620}
        client.post("/api/your-plan/use")
        assert card() == {"rows": 2, "in_use": True, "total": 620}
