"""Wins (THL-246, THL-247, THL-249, THL-250, THL-251): the milestone path
and the pearls it earns, streaks, challenges and the monthly recap."""

import json
from datetime import date

import pytest

from finance import secrets_box, wins
from test_plaid_link import KEY
from test_safe_to_spend import TODAY, history, october, tx

MONTH = TODAY.strftime("%Y-%m")


@pytest.fixture
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)
    app = create_app(str(tmp_path / "wins.db"))
    app.config.update(TESTING=True)
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    st = app.config["STORE"]
    with app.test_client() as c:
        c.st = st
        yield c


def ledger(c, rows=None):
    c.st.add_transactions(rows if rows is not None else history() + october())


def saved_history():
    """The ledger with money moved to savings in August and September too."""
    return history() + october() + [tx("2026-08-15", "To savings", 300.00, "Saved"),
                                    tx("2026-09-15", "To savings", 340.00, "Saved")]


def savings(c, balance=3000):
    r = c.post("/api/accounts/manual", json={"name": "Savings", "kind": "savings", "balance": balance})
    assert r.status_code in (200, 201), r.get_json()
    return c.st.manual_accounts()[0]["account_id"]


# ── Runs ─────────────────────────────────────────────────────────────────

class TestRuns:
    def test_a_missed_period_starts_a_new_run_and_the_best_is_kept(self):
        periods = [{"period": m, "counted": v} for m, v in
                   zip(["2025-11", "2025-12", "2026-01", "2026-02", "2026-03", "2026-04", "2026-05",
                        "2026-06", "2026-07", "2026-08", "2026-09"],
                       [True, True, None, True, True, True, True, None, True, False, True])]
        r = wins.runs(periods)
        assert r == {"this": 1, "best": 7, "missed": "2026-08"}      # unknown months don't break a run

    def test_nothing_known_yet(self):
        assert wins.runs([{"period": "2026-09", "counted": None}]) == {"this": 0, "best": 0, "missed": None}


# ── Someone new (W-03) ───────────────────────────────────────────────────

class TestSomeoneNew:
    def test_the_first_milestone_is_a_month_away(self, client):
        ledger(client, october())
        w = client.get("/api/wins").get_json()
        assert w["heading"] == "Your first milestone is a month away" and w["first_month_away"]
        assert (w["done"], w["of"], w["earned"], w["total"]) == (0, 6, 0, 9)
        assert w["path"][0]["state"] == "next" and w["path"][0]["when"] == "After your first full month"
        assert all(p["state"] == "todo" and p["when"] == "Comes later" for p in w["path"][1:])
        assert w["next"]["label"] == "Sort your first transactions" and w["next"]["action"] == "review"
        assert [s["this_words"] for s in w["streaks"]] == [
            "Starts after your first full month", "Starts once your Anchor is set up", "Starts this week"]
        assert w["recap"] is None and w["next_recap"] == "November"
        assert w["challenges"]["suggested"] == [] and w["challenges"]["ready"] is False
        assert w["suggestion"] is None
        # Every unearned pearl says how to earn it; no phase names anywhere.
        hows = {p["key"]: p["how"] for p in w["pearls"]}
        assert hows["anchor_quarter"] == "Your Anchor reaches 3 weeks of Essentials"
        assert hows["anchor_half"] == "Your Anchor reaches 1½ months of Essentials"
        assert hows["saved_1000"] == "Put away $1,000 in total"
        assert hows["three_within"] == "Three months in a row within Allowance"
        assert not any(w2 in json.dumps(w) for w2 in ("Protect", "Build", "Unveil", "Shine"))


# ── The path (THL-247) ───────────────────────────────────────────────────

class TestThePath:
    def test_placed_from_what_is_already_true(self, client):
        """THL-50: a full ledger starts past "your money, assessed"."""
        ledger(client)
        w = client.get("/api/wins").get_json()
        assessed = next(p for p in w["pearls"] if p["key"] == "assessed")
        assert assessed["earned"] and assessed["on"] == TODAY.isoformat()
        assert w["heading"] == "1 of 6 milestones on your path"
        assert w["next"]["key"] == "anchor_setup" and w["next"]["label"] == "Set up your Anchor"
        assert [e["key"] for e in w["events"] if e["kind"] == "milestone_earned"] == ["assessed"]

    def test_setting_up_the_anchor_earns_pearls_measured_toward_three_months(self, client):
        ledger(client)
        aid = savings(client, 3000)
        client.put("/api/goals/anchor", json={"accounts": [aid]})
        w = client.get("/api/wins").get_json()
        earned = {p["key"] for p in w["pearls"] if p["earned"]}
        # Essentials run about $2,360 a month: 3 months is ~$7,080, so $3,000 is past a quarter, under half.
        assert {"assessed", "anchor_setup", "anchor_quarter"} <= earned and "anchor_half" not in earned
        assert w["done"] == 3 and w["next"]["key"] == "anchor_half"
        assert w["next"]["title"] == "Next: grow your Anchor to 3 months"
        assert "$3,000 of" in w["next"]["line"] and "to go" in w["next"]["line"]
        half = next(p for p in w["path"] if p["key"] == "anchor_half")
        assert half["state"] == "next" and half["when"].startswith("Next · ")
        assert w["suggestion"]["to"] == "learn"

    def test_a_pearl_is_never_taken_away(self, client):
        """THL-53: a dip below a quarter keeps the quarter pearl."""
        ledger(client)
        aid = savings(client, 3000)
        client.put("/api/goals/anchor", json={"accounts": [aid]})
        client.get("/api/wins")
        with client.st.conn() as c:
            c.execute("UPDATE manual_accounts SET balance = 100")
        w = client.get("/api/wins").get_json()
        quarter = next(p for p in w["pearls"] if p["key"] == "anchor_quarter")
        assert quarter["earned"] and quarter["on"] == TODAY.isoformat()
        assert w["done"] == 3

    def test_thresholds_change_without_a_release(self, client):
        """THL-54: a setting (or PEARL_WINS_THRESHOLDS) moves the bars."""
        ledger(client)
        client.st.set_setting("wins_thresholds", json.dumps({"saved": 100, "half": 0.4}))
        w = client.get("/api/wins").get_json()
        hows = {p["key"]: (p["label"], p["how"]) for p in w["pearls"]}
        assert hows["saved_1000"] == ("First $100 saved", "Put away $100 in total")
        assert hows["anchor_half"][1] == "Your Anchor reaches 1.2 months of Essentials"
        # October's $150 Saved transfer passes the lowered bar.
        assert next(p for p in w["pearls"] if p["key"] == "saved_1000")["earned"]

    def test_the_extra_pearls(self, client):
        rows = history() + october() + [tx("2026-08-02", "To savings", 900.00, "Saved")]
        ledger(client, rows)
        w = client.get("/api/wins").get_json()
        saved = next(p for p in w["pearls"] if p["key"] == "saved_1000")
        # $900 in August, $150 on Oct 8: passed before she started, so it's
        # dated the day Pearl could see it (today), never before she joined.
        assert saved["earned"] and saved["on"] == TODAY.isoformat()
        assert next(p for p in w["pearls"] if p["key"] == "three_within")["earned"] is False
        # Earned pearls come first in the collection, the rest in their order.
        keys = [p["key"] for p in w["pearls"]]
        assert keys[:2] == ["assessed", "saved_1000"] and keys[-1] == "invest"

    def test_a_pearl_from_history_keeps_its_own_date_once_she_has_started(self, client):
        rows = history() + october() + [tx("2026-08-02", "To savings", 900.00, "Saved")]
        ledger(client, rows)
        client.st.set_setting("protect_done_on", "2026-09-01")
        w = client.get("/api/wins").get_json()
        saved = next(p for p in w["pearls"] if p["key"] == "saved_1000")
        assert saved["on"] == "2026-10-08"

    def test_investing_by_her_word(self, client):
        ledger(client)
        client.put("/api/unveil", json={"type": "tfsa"})
        w = client.get("/api/wins").get_json()
        assert next(p for p in w["pearls"] if p["key"] == "invest")["earned"]

    def test_home_carries_the_next_step(self, client):
        ledger(client)
        h = client.get("/api/home").get_json()["wins"]
        assert h["done"] == 1 and h["of"] == 6 and h["next"]["label"] == "Set up your Anchor"


# ── Streaks (THL-249) ────────────────────────────────────────────────────

class TestStreaks:
    def test_within_safe_to_spend_counts_full_months_only(self, client):
        ledger(client)
        s = client.get("/api/wins/streaks/within").get_json()
        # July went over ($2,150 in, $2,363 out); August and September were within.
        assert [p["counted"] for p in s["periods"]] == [False, True, True]
        assert (s["this"], s["best"]) == (2, 2) and s["new_best"]
        assert s["note"] == "July went over. A new run started in August, and your best run of 2 months is kept."
        assert "rose" not in json.dumps(s).lower() and "broke" not in json.dumps(s).lower()

    def test_the_best_run_is_never_lowered(self, client):
        ledger(client)
        client.st.set_setting(wins.BEST_KEY, json.dumps({"within": 4}))
        s = client.get("/api/wins/streaks/within").get_json()
        assert (s["this"], s["best"], s["new_best"]) == (2, 4, False)
        assert s["best_words"] == "Best 4"

    def test_anchor_months_start_when_it_is_set_up(self, client):
        ledger(client, saved_history())
        aid = savings(client)
        client.st.set_setting("anchor_started", "2026-08-01")
        client.st.set_setting("anchor_accounts", json.dumps([aid]))
        s = client.get("/api/wins/streaks/anchor").get_json()
        assert [p["period"] for p in s["periods"]] == ["2026-08", "2026-09"]
        assert [p["counted"] for p in s["periods"]] == [True, True]       # $300 and $340 to savings

    def test_anchor_set_up_this_month_counts_from_next_month(self, client):
        ledger(client)
        aid = savings(client)
        client.st.set_setting("anchor_started", TODAY.isoformat())
        client.st.set_setting("anchor_accounts", json.dumps([aid]))
        s = client.get("/api/wins/streaks/anchor").get_json()
        assert s["this"] == 0 and s["this_words"] == "Counts from November"

    def test_weeks_cleared_count_once_the_week_ends(self, client):
        ledger(client)
        s = client.get("/api/wins/streaks/review").get_json()
        weeks = json.loads(client.st.setting(wins.WEEKS_KEY))
        assert list(weeks) == [wins.week_start(TODAY).isoformat()]        # this week, recorded
        assert s["this"] == 0 and s["this_words"] == "Starts this week"
        client.st.set_setting(wins.WEEKS_KEY, json.dumps({"2026-09-14": True, "2026-09-21": False,
                                                         "2026-09-28": True}))
        s = client.get("/api/wins/streaks/review").get_json()
        assert (s["this"], s["best"]) == (1, 1)                        # this week isn't over yet
        assert s["note"] == ("The week of Sep 21 was missed. A new run started in the week of Sep 28, "
                             "and your best run of 1 week is kept.")

    def test_an_unknown_streak_is_a_404(self, client):
        assert client.get("/api/wins/streaks/daily").status_code == 404


# ── Challenges (THL-250) ─────────────────────────────────────────────────

COFFEE = [tx(f"2026-09-{d:02d}", "Café Alta", a, "Coffee") for d, a in
          ((2, 5.40), (5, 6.10), (9, 4.80), (12, 5.40), (16, 6.10), (19, 4.80), (23, 5.40),
           (26, 6.10), (30, 4.80))]                                     # $48.90 in September


class TestChallenges:
    def test_suggested_from_her_own_spending(self, client):
        ledger(client, history() + october() + COFFEE)
        s = client.get("/api/wins/challenges").get_json()["suggested"]
        coffee = next(c for c in s if c["kind"] == "coffee")
        assert coffee["baseline"] == 48.9 and coffee["target"] == 35.0
        assert coffee["line"] == "You spent $48.90 on coffee in September. Try $35."
        assert coffee["start"] == TODAY.isoformat() and coffee["end"] == "2026-10-31"
        kinds = {c["kind"] for c in s}
        assert "subscription_sweep" in kinds
        assert "anchor_boost" not in kinds                              # no Anchor yet

    def test_start_progress_and_stop_in_neutral_words(self, client):
        ledger(client, history() + october() + COFFEE)
        r = client.post("/api/wins/challenges", json={"kind": "coffee", "target": 30}).get_json()
        cid = r["id"]
        assert r["challenge"]["target"] == 30 and r["challenge"]["status"] == "active"
        client.st.add_transactions([tx("2026-10-09", "Café Alta", 5.40, "Coffee"),
                                    tx("2026-10-09", "Tim Hortons", 3.15, "Coffee")])
        d = client.get(f"/api/wins/challenges/{cid}").get_json()
        assert d["progress"]["done"] == 8.55 and d["progress"]["days_left"] == 22
        assert d["words"]["line"] == "$8.55 of $30."                  # day 1 of 23: not on pace yet
        client.st.set_setting("x", "")
        from finance import wins as w
        from datetime import date as _d
        p = w.progress(client.st.all_transactions(), client.st.challenge(cid), _d(2026, 10, 30))
        assert p["on_pace"] and w.challenge_words(client.st.challenge(cid), p, _d(2026, 10, 30))["line"] \
            == "$8.55 of $30. You’re on pace to spend less than September’s $48.90."
        assert {x["merchant"] for x in d["recent"]} == {"Tim Hortons", "Café Alta"}
        s = client.post(f"/api/wins/challenges/{cid}/stop").get_json()
        assert s["challenge"]["status"] == "stopped"
        assert s["words"]["title"] == "Challenge stopped"
        assert s["words"]["line"] == "You spent $8.55 on coffee in 1 day. Try again any time, or pick another challenge."
        assert client.get("/api/wins").get_json()["challenges"]["active"] == []

    def test_over_the_target_is_said_plainly(self, client):
        ledger(client, history() + october() + COFFEE)
        cid = client.post("/api/wins/challenges", json={"kind": "coffee", "target": 5}).get_json()["id"]
        client.st.add_transactions([tx("2026-10-09", "Café Alta", 9.00, "Coffee")])
        d = client.get(f"/api/wins/challenges/{cid}").get_json()
        assert d["progress"]["over"] and d["words"]["tone"] == "champagne"
        assert "Over the target" in d["words"]["line"]

    def test_finishing_offers_a_chest_and_moves_what_she_saved(self, client):
        ledger(client, history() + october() + COFFEE)
        cid = client.st.add_challenge("coffee", "Coffee for a month", 35.0, "2026-09-10", "2026-09-30",
                                      category="Coffee", baseline=60.0)
        bank = client.post("/api/piggy", json={"name": "Japan trip", "target": 3000, "cadence": "annual"}).get_json()["id"]
        w = client.get("/api/wins").get_json()                       # the window has passed: finished
        past = next(c for c in w["challenges"]["past"] if c["id"] == cid)
        assert past["status"] == "finished"
        # $60 last time, $32.60 spent from Sep 10 to Sep 30: $27.40 less.
        assert past["result"] == {"spent": 32.6, "saved": 27.4, "over": False}
        assert past["words"]["title"] == "You spent $32.60 on coffee"
        assert past["words"]["line"] == "That’s $27.40 less than August. Nicely done."
        assert any(e["kind"] == "challenge_finished" for e in json.loads(client.st.setting(wins.EVENTS_KEY)))
        r = client.post(f"/api/wins/challenges/{cid}/chest", json={"bank_id": bank}).get_json()
        assert r["added"] == 27.4 and r["chest"] == "Japan trip"
        assert [d["amount"] for d in client.st.draws()] == [-27.4]
        assert client.post(f"/api/wins/challenges/{cid}/chest", json={"bank_id": bank}).status_code == 409

    def test_the_catalogue_changes_without_a_release(self, client):
        ledger(client, history() + october() + COFFEE)
        client.st.set_setting("wins_challenges", json.dumps([
            {"kind": "coffee", "title": "Less coffee", "category": "Coffee", "span": "month", "cut": 0.5}]))
        s = client.get("/api/wins/challenges").get_json()
        assert [c["title"] for c in s["suggested"]] == ["Less coffee"]
        assert s["suggested"][0]["target"] == 25.0

    def test_a_challenge_pearl_cannot_price_is_refused(self, client):
        ledger(client, october())
        assert client.post("/api/wins/challenges", json={"kind": "coffee"}).status_code == 400


# ── The recap (THL-251) ──────────────────────────────────────────────────

class TestRecap:
    def test_made_once_the_month_closes_and_leads_with_what_went_well(self, client):
        ledger(client, saved_history())
        w = client.get("/api/wins").get_json()
        r = w["recap"]
        assert r["month"] == "2026-09" and r["made_on"] == TODAY.isoformat()
        assert r["title"] == "A good month for your Anchor"               # within, and $340 put away
        assert [x["text"] for x in r["went_well"]] == [
            "You stayed within Allowance.", "You put away $340."]
        assert [x["share"] for x in r["went_well"]] == ["Stayed within my plan", "Put money away"]
        assert r["pearls"] == [] and r["within"] is True and r["put_away"] == 340.0
        assert r["streaks"] == "Within Allowance: 2 months in a row."
        assert w["recaps"] == ["2026-09"]
        assert client.get("/api/wins/recaps/2026-09").get_json()["title"] == r["title"]
        assert client.get("/api/wins/recaps/2026-08").status_code == 404
        assert "rose" not in json.dumps(r).lower()

    def test_a_kept_recap_and_the_opportunity(self, client):
        rows = history() + october() + [tx("2026-09-20", "Pai", 400.00, "Dining", account="visa")]
        ledger(client, rows)
        r = client.get("/api/wins").get_json()["recap"]
        assert r["opportunity"]["category"] == "Dining"
        assert r["opportunity"]["text"].startswith("Dining out ran")
        assert r["opportunity"]["challenge"] == "cook_at_home"
        # Kept as it was, even as the ledger changes.
        client.st.add_transactions([tx("2026-09-25", "Pai", 900.00, "Dining", account="visa")])
        assert client.get("/api/wins").get_json()["recap"] == r


# ── "You earned a pearl" (THL-256) ───────────────────────────────────────

class TestPearlMoment:
    def test_nothing_earned_shows_nothing(self, client):
        ledger(client, october())
        m = client.get("/api/wins/moment").get_json()
        assert m == {"show": False, "pearls": [], "title": "", "line": "", "overline": ""}

    def test_one_pearl_then_never_again(self, client):
        ledger(client)
        m = client.get("/api/wins/moment").get_json()
        assert m["show"] and [p["key"] for p in m["pearls"]] == ["assessed"]
        assert m["overline"] == "Pearl earned" and m["title"] == "Your money, assessed"
        assert m["line"] == "Your income, bills and first month are sorted. It’s in your collection on Wins."
        assert m["announce"] == "Pearl earned. Your money, assessed."
        assert client.post("/api/wins/moment/seen", json={"keys": ["assessed"]}).get_json()["ok"]
        assert not client.get("/api/wins/moment").get_json()["show"]
        assert client.post("/api/wins/moment/seen", json={"keys": ["nope"]}).status_code == 400

    def test_two_at_once_make_one_sheet(self, client):
        ledger(client)
        client.post("/api/wins/moment/seen", json={"keys": ["assessed"]})
        aid = savings(client)
        client.st.set_setting("anchor_started", TODAY.isoformat())
        client.st.set_setting("anchor_accounts", json.dumps([aid]))
        m = client.get("/api/wins/moment").get_json()
        assert m["show"] and m["overline"] == "Pearls earned"
        assert m["title"] == "You earned 2 pearls"
        assert [p["key"] for p in m["pearls"]] == ["anchor_setup", "anchor_quarter"]
        assert m["line"] == "Anchor set up and Anchor a quarter there. They’re in your collection on Wins."
        assert m["pearls"][1]["line"].startswith("$3,000 toward 3 months of Essentials.")

    def test_the_full_anchor_line_is_her_target(self, client):
        ledger(client)
        aid = savings(client, balance=20000)
        client.st.set_setting("anchor_started", TODAY.isoformat())
        client.st.set_setting("anchor_accounts", json.dumps([aid]))
        m = client.get("/api/wins/moment").get_json()
        full = next(p for p in m["pearls"] if p["key"] == "anchor_full")
        assert full["line"].endswith("ready for a big surprise.") and full["line"].startswith("$")
