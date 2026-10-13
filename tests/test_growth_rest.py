"""The rest of Growth (Pearl THL-129, THL-130, THL-134, THL-136).

* A step's own screen with her numbers (GR-02 not done, GR-03 done, GR-04
  "Keep it going" after a rough month, with Protect staying done).
* Where she starts at the end of onboarding (GR-06 Protect, GR-07 further
  along, savings credited as the Anchor), and each phase's moment playing
  once (GR-08 Protect done, GR-09 Build done, GR-10 Unveil done).
* Learn's modules: her place and quick-check answers kept on her account,
  and GR-16's "Read the basics · N of 5" ticking at five.
* The partner handoff (post-MVP), configured rather than built in: off with
  no partner (GR-22), gated on Protect (GR-23), and GR-21 recording the same
  self-report as GR-37.
"""

from __future__ import annotations

import json
from datetime import date
from urllib.parse import parse_qs, urlsplit

import pytest

from finance import milestones, safe_to_spend as sts
from finance.models import Transaction
from test_milestones import ANCHOR_NONE, path as path_of
from test_safe_to_spend import TODAY, history, october


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    from finance import api
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY.isoformat())
    monkeypatch.delenv("PEARL_PARTNER_NAME", raising=False)
    monkeypatch.delenv("PEARL_PARTNER_URL", raising=False)
    app = create_app(str(tmp_path / "growth.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        yield c


def store(c):
    return c.application.config["STORE"]


def full_ledger(c):
    """July to October: Protect done, Build next (H-01)."""
    store(c).add_transactions(history() + october())


def new_ledger(c):
    """This month only: no full month yet, so Protect can't be done."""
    store(c).add_transactions(october())


def fill_anchor(c, target=2000):
    """An Anchor started on a savings account that already holds its target."""
    r = c.post("/api/accounts/manual", json={"name": "Savings", "kind": "savings", "balance": 3000})
    assert r.status_code in (200, 201), r.get_json()
    st = store(c)
    aid = st.manual_accounts()[0]["account_id"]
    st.set_setting("anchor_started", "2026-08-01")
    st.set_setting("anchor_accounts", json.dumps([aid]))
    st.set_setting("anchor_target", target)
    st.set_setting("anchor_size", 1)


def partner(monkeypatch, name="Example Invest", url="https://example.com/open?campaign=pearl"):
    monkeypatch.setenv("PEARL_PARTNER_NAME", name)
    monkeypatch.setenv("PEARL_PARTNER_URL", url)


# ── A step's own screen (GR-02, GR-03) ────────────────────────────────────

class TestStepDetail:
    def test_every_step_answers_with_where_it_sits(self, client):
        full_ledger(client)
        for key, phase, index, of, also in [
                ("income", "protect", 1, 3, False), ("bills", "protect", 2, 3, False),
                ("essentials", "protect", 3, 3, False), ("first_stop", "build", 1, 2, False),
                ("full", "build", 2, 2, False), ("saved_more", "build", 1, 2, True),
                ("cards", "build", 2, 2, True), ("invest", "unveil", 1, 1, False)]:
            d = client.get(f"/api/path/step/{key}").get_json()
            assert (d["key"], d["phase"], d["index"], d["of"], d["also"]) == (key, phase, index, of, also)
            assert d["checked_on"] == "2026-10-01" and d["next_check"] == "2026-11-01"
            assert d["current_phase"] == "build"

    def test_gr03_a_done_step_carries_its_numbers(self, client):
        full_ledger(client)
        d = client.get("/api/path/step/essentials").get_json()
        assert d["state"] == "done" and d["label"] == "Cover your Essentials"
        f = d["facts"]
        assert f["month"] == "2026-09" and f["income"] == 4300.0
        assert f["left"] == round(f["income"] - f["essentials"], 2) and f["left"] > 0

    def test_gr02_the_anchor_step_not_done_yet(self, client):
        full_ledger(client)
        d = client.get("/api/path/step/full").get_json()
        # Not started: the step after the current one, with her usual month
        # of Essentials as the target it would have.
        assert d["state"] == "todo"
        assert d["facts"]["started"] is False and d["facts"]["target"] > 0
        assert d["facts"]["to_go"] == d["facts"]["target"]
        assert client.get("/api/path/step/first_stop").get_json()["state"] == "now"

    def test_build_also_counts_carry_each_month(self, client):
        full_ledger(client)
        f = client.get("/api/path/step/saved_more").get_json()["facts"]
        assert [m["month"] for m in f["months"]] == ["2026-07", "2026-08", "2026-09"]
        assert [m["saved"] for m in f["months"]] == [False, True, True]
        assert f["known_by"] is None

    def test_a_new_ledger_says_when_it_will_know(self, client):
        new_ledger(client)
        d = client.get("/api/path/step/essentials").get_json()
        current = client.get("/api/path").get_json()["step"]
        assert d["state"] == ("now" if current == 3 else "todo") and d["facts"]["month"] is None
        f = client.get("/api/path/step/saved_more").get_json()
        assert f["state"] == "ahead" and f["facts"]["known_by"] == "2027-01"

    def test_invest_reads_her_self_report(self, client):
        client.put("/api/unveil", json={"type": "tfsa"})
        f = client.get("/api/path/step/invest").get_json()["facts"]
        assert f["report"]["label"] == "TFSA" and f["linked"] is False

    def test_an_unknown_step_is_a_404(self, client):
        assert client.get("/api/path/step/lottery").status_code == 404


# ── Keep it going (GR-04) ─────────────────────────────────────────────────

def repair(amount=2600.0):
    return Transaction(date="2026-09-18", description="MIDAS AUTO 0412", merchant="Midas",
                       amount=amount, category="Transport", account_id="chq")


class TestKeepItGoing:
    def test_protect_stays_done_and_the_lapse_is_named(self):
        rows = history() + october() + [repair()]
        p = path_of(rows, protect_done_before=True)
        assert p["protect_done"] is True and p["phase"] == "build"
        assert p["lapse"]["month"] == "2026-09"
        assert p["lapse"]["essentials"] > p["lapse"]["income"]

    def test_no_lapse_in_an_ordinary_month_or_before_protect(self):
        assert path_of()["lapse"] is None
        rows = history() + october() + [repair()]
        s = sts.compute(rows, TODAY, savings_target=300.0)
        p = milestones.path(rows, TODAY, s, anchor=ANCHOR_NONE, bills_found=5)
        assert p["protect_done"] is False and p["lapse"] is None

    def test_the_step_screen_explains_it_with_the_biggest_charge(self, client):
        full_ledger(client)
        client.get("/api/path")                         # Protect is remembered…
        store(client).add_transactions([repair()])      # …then a rough September.
        d = client.get("/api/path/step/essentials").get_json()
        assert d["state"] == "lapsed"
        assert d["facts"]["biggest"] == {"merchant": "Midas", "category": "Transport", "amount": 2600.0}
        assert d["facts"]["unusual"] is False
        assert client.get("/api/path").get_json()["lapse"]["month"] == "2026-09"
        client.put("/api/insights/unusual", json={"month": "2026-09", "unusual": True})
        assert client.get("/api/path/step/essentials").get_json()["facts"]["unusual"] is True


# ── Where you start (GR-06, GR-07) ────────────────────────────────────────

class TestPlacement:
    def test_gr06_a_new_account_starts_in_protect(self, client):
        new_ledger(client)
        p = client.get("/api/path/placement").get_json()
        assert p["phase"] == "protect" and p["invested"] is False and p["credit"] is None
        assert [r["key"] for r in p["rows"]] == ["income", "bills", "essentials"]
        ess = p["rows"][2]
        assert ess["done"] is False and ess["month"] is None and ess["known_by"] == "2026-11"
        assert p["done"] == sum(r["done"] for r in p["rows"]) and p["of"] == 3

    def test_gr07_further_along_starts_in_build(self, client):
        full_ledger(client)
        p = client.get("/api/path/placement").get_json()
        assert p["phase"] == "build" and p["credit"] is None
        assert [r["key"] for r in p["rows"]] == ["protect", "anchor", "saved_more"]
        assert p["rows"][0]["done"] is True and p["rows"][1]["target"] > 0

    def test_savings_above_a_month_of_essentials_are_credited_as_the_anchor(self, client):
        full_ledger(client)
        r = client.post("/api/accounts/manual", json={"name": "Savings", "kind": "savings",
                                                      "balance": 9000})
        assert r.status_code in (200, 201), r.get_json()
        p = client.get("/api/path/placement").get_json()
        assert p["phase"] == "unveil"
        assert p["credit"]["amount"] == 9000.0 and p["credit"]["target"] < 9000
        assert [r["key"] for r in p["rows"]] == ["protect", "build", "invest"]
        # Looking credits nothing; "See my path" does.
        assert store(client).setting("anchor_started") in (None, "")
        path = client.post("/api/path/placement").get_json()
        assert path["phase"] == "unveil"
        st = store(client)
        assert st.setting("anchor_started") == TODAY.isoformat()
        assert st.setting("anchor_earned_on") == TODAY.isoformat()
        # The reveal said it, so no moment replays it.
        assert client.get("/api/moments").get_json()["phase"] is None

    def test_an_investment_account_already_linked_goes_straight_to_unveil_done(self, client):
        full_ledger(client)
        fill_anchor(client)
        st = store(client)
        with st.conn() as cc:
            cc.execute("INSERT INTO account_sync (account_id, account_name, account_type, enabled)"
                       " VALUES ('inv', 'TFSA ••7', 'investment', 1)")
        p = client.get("/api/path/placement").get_json()
        assert p["phase"] == "unveil" and p["invested"] is True


# ── Each phase's moment, once (GR-08, GR-09, GR-10) ───────────────────────

class TestMomentsPlayOnce:
    def test_protect_done_plays_once(self, client):
        full_ledger(client)
        m = client.get("/api/moments").get_json()
        assert m["phase"] == "protect" and m["anchor"]["started"] is False
        assert client.get("/api/moments").get_json()["phase"] == "protect"   # until she's seen it
        assert client.post("/api/moments/protect").get_json()["seen"] == ["protect"]
        assert client.get("/api/moments").get_json()["phase"] is None

    def test_nothing_before_a_phase_is_done(self, client):
        new_ledger(client)
        assert client.get("/api/moments").get_json()["phase"] is None

    def test_build_done_plays_once_and_covers_protect(self, client):
        full_ledger(client)
        fill_anchor(client)
        st = store(client)
        m = client.get("/api/moments").get_json()
        assert m["phase"] == "build" and m["anchor"]["target"] == 2000
        client.post("/api/moments/build")
        assert json.loads(st.setting("moments_seen")) == ["build", "protect"]
        assert client.get("/api/moments").get_json()["phase"] is None

    def test_unveil_done_is_seen_when_she_reports_it(self, client):
        full_ledger(client)
        client.put("/api/unveil", json={"type": "rrsp"})
        assert client.get("/api/moments").get_json()["phase"] is None
        assert set(json.loads(store(client).setting("moments_seen"))) == {"protect", "build", "unveil"}

    def test_an_unknown_phase_is_refused(self, client):
        assert client.post("/api/moments/shine").status_code == 404


# ── Learn (GR-11 to GR-14) and GR-16's count ──────────────────────────────

def basics(c):
    return next(x for x in c.get("/api/unveil").get_json()["checklist"] if x["key"] == "basics")


class TestLearn:
    def test_five_modules_nothing_read(self, client):
        d = client.get("/api/learn").get_json()
        assert [m["id"] for m in d["modules"]] == ["tfsa-rrsp-fhsa", "index-funds-etfs",
                                                  "risk-time-horizon", "fees", "robo-or-self-directed"]
        assert (d["read"], d["of"], d["next"]) == (0, 5, "tfsa-rrsp-fhsa")
        assert all(m["screen"] == 0 and not m["done"] for m in d["modules"])

    def test_her_place_is_kept_per_screen_and_never_goes_back(self, client):
        client.put("/api/learn/fees", json={"screen": 3})
        d = client.put("/api/learn/fees", json={"screen": 2}).get_json()
        fees = next(m for m in d["modules"] if m["id"] == "fees")
        assert fees["screen"] == 3 and fees["done"] is False

    def test_the_quick_check_is_kept_and_finishing_needs_an_answer(self, client):
        r = client.put("/api/learn/tfsa-rrsp-fhsa", json={"done": True})
        assert r.status_code == 400 and "answer" in r.get_json()["error"]
        d = client.put("/api/learn/tfsa-rrsp-fhsa", json={"answer": "rrsp"}).get_json()
        m = d["modules"][0]
        assert (m["answer"], m["correct"], m["screen"], m["done"]) == ("rrsp", False, 4, False)
        client.put("/api/learn/tfsa-rrsp-fhsa", json={"answer": "fhsa"})
        d = client.put("/api/learn/tfsa-rrsp-fhsa", json={"done": True}).get_json()
        m = d["modules"][0]
        assert (m["answer"], m["correct"], m["done"], m["done_on"]) == ("fhsa", True, True, "2026-10-09")
        assert (d["read"], d["next"]) == (1, "index-funds-etfs")
        # It's kept on her account, so a fresh read sees it.
        assert client.get("/api/learn").get_json()["modules"][0]["done"] is True

    def test_gr16_counts_modules_read_and_ticks_at_five(self, client):
        full_ledger(client)
        assert basics(client) == {"key": "basics", "done": False, "available": True, "read": 0,
                                  "of": 5, "next": "tfsa-rrsp-fhsa"}
        answers = {"tfsa-rrsp-fhsa": "fhsa", "index-funds-etfs": "false",
                   "risk-time-horizon": "steady", "fees": "one_time", "robo-or-self-directed": "robo"}
        for i, (mid, answer) in enumerate(answers.items(), start=1):
            client.put(f"/api/learn/{mid}", json={"answer": answer})
            client.put(f"/api/learn/{mid}", json={"done": True})
            b = basics(client)
            assert b["read"] == i
            assert b["done"] is (i == 5)
        # A "Close!" answer counts the same: there's no score.
        assert basics(client)["next"] is None

    @pytest.mark.parametrize("body", [{"screen": 0}, {"screen": 9}, {"screen": "two"},
                                      {"answer": "maybe"}])
    def test_nonsense_is_refused(self, client, body):
        assert client.put("/api/learn/fees", json=body).status_code == 400

    def test_an_unknown_module_is_a_404(self, client):
        assert client.put("/api/learn/crypto", json={"screen": 1}).status_code == 404


# ── The partner handoff (GR-19 to GR-23, post-MVP) ────────────────────────

class TestPartnerConfiguration:
    def test_off_with_no_partner_configured(self, client):
        full_ledger(client)
        p = client.get("/api/unveil").get_json()["partner"]
        assert p == {"configured": False, "name": None, "welcome": False, "clicked_on": None,
                     "notify": False}
        assert client.post("/api/unveil/partner").status_code == 404

    @pytest.mark.parametrize("name, url", [("Example Invest", ""), ("", "https://example.com"),
                                           ("Example Invest", "http://example.com"),
                                           ("Example Invest", "javascript:alert(1)")])
    def test_half_a_configuration_or_an_unsafe_link_is_no_partner(self, client, monkeypatch, name, url):
        partner(monkeypatch, name, url)
        assert client.get("/api/unveil").get_json()["partner"]["configured"] is False

    def test_on_with_a_name_and_an_https_link(self, client, monkeypatch):
        partner(monkeypatch)
        full_ledger(client)
        p = client.get("/api/unveil").get_json()["partner"]
        assert p["configured"] is True and p["name"] == "Example Invest" and p["welcome"] is False
        assert "url" not in p

    def test_gr19_the_link_carries_a_tracking_id_only(self, client, monkeypatch):
        partner(monkeypatch)
        full_ledger(client)
        r = client.post("/api/unveil/partner")
        assert r.status_code == 200
        url = urlsplit(r.get_json()["url"])
        assert (url.scheme, url.netloc, url.path) == ("https", "example.com", "/open")
        query = parse_qs(url.query)
        assert set(query) == {"campaign", "pearl_ref"}
        ref = query["pearl_ref"][0]
        assert len(ref) >= 12 and "@" not in ref
        # The same ID next time; no amount, name or account in it.
        again = parse_qs(urlsplit(client.post("/api/unveil/partner").get_json()["url"]).query)
        assert again["pearl_ref"] == [ref]

    def test_gr23_the_handoff_waits_for_protect(self, client, monkeypatch):
        partner(monkeypatch)
        new_ledger(client)
        r = client.post("/api/unveil/partner")
        assert r.status_code == 409 and "Protect" in r.get_json()["error"]
        protect = client.get("/api/unveil").get_json()["checklist"][0]
        assert protect["done"] is False and protect["left"] >= 1 and protect["next"]
        assert store(client).setting("partner_click") in (None, "")


class TestWelcomeBack:
    def test_gr20_asks_after_a_click_until_answered(self, client, monkeypatch):
        partner(monkeypatch)
        full_ledger(client)
        client.post("/api/moments/protect")
        client.post("/api/unveil/partner")
        assert client.get("/api/unveil").get_json()["partner"]["welcome"] is True
        assert client.get("/api/moments").get_json()["partner_welcome"] is True
        d = client.put("/api/unveil/partner/welcome", json={"answer": "not_yet"}).get_json()
        assert d["partner"]["welcome"] is False and d["report"] is None
        assert client.put("/api/unveil/partner/welcome", json={"answer": "yes"}).status_code == 400

    def test_stops_asking_after_14_days(self, client, monkeypatch):
        from finance import api
        partner(monkeypatch)
        full_ledger(client)
        client.post("/api/unveil/partner")
        monkeypatch.setattr(api, "_today_iso", lambda: date(2026, 10, 23).isoformat())
        assert client.get("/api/unveil").get_json()["partner"]["welcome"] is True
        monkeypatch.setattr(api, "_today_iso", lambda: date(2026, 10, 24).isoformat())
        assert client.get("/api/unveil").get_json()["partner"]["welcome"] is False

    def test_gr21_is_the_same_self_report_as_gr37(self, client, monkeypatch):
        partner(monkeypatch)
        full_ledger(client)
        client.post("/api/unveil/partner")
        d = client.put("/api/unveil", json={"type": "not_sure", "via": "partner"}).get_json()
        assert d["report"] == {"type": "not_sure", "label": "Not sure", "on": "2026-10-09",
                               "via": "partner"}
        assert d["partner"]["welcome"] is False
        # One record: the path's Unveil step, Profile and GR-37 all read it.
        from finance import api
        assert api._json_setting(store(client), "unveil_reported", None)["via"] == "partner"
        assert client.get("/api/path/step/invest").get_json()["state"] == "done"
        assert client.get("/api/moments").get_json()["phase"] is None
        # GR-37 can change the kind of account; undoing it undoes both.
        assert client.put("/api/unveil", json={"type": "tfsa"}).get_json()["report"].get("via") is None
        assert client.delete("/api/unveil").get_json()["report"] is None

    def test_how_she_opened_it_is_one_of_two(self, client):
        assert client.put("/api/unveil", json={"type": "tfsa", "via": "a friend"}).status_code == 400


class TestNoPartnerYet:
    def test_gr22_tell_me_when(self, client):
        full_ledger(client)
        d = client.put("/api/unveil/partner/notify").get_json()
        assert d["partner"]["notify"] is True and d["partner"]["configured"] is False
        assert store(client).setting("partner_notify_on") == "2026-10-09"
        assert client.delete("/api/unveil/partner/notify").get_json()["partner"]["notify"] is False
