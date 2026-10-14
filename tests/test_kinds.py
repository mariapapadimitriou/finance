"""Fixed or Variable: the second lens (finance/kinds.py), and the filters on
Insights (2026-10-14)."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = "2026-10-14"


def tx(day, merchant, amount, category, account="chq", **kw):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, account_id=account, account_name=account,
                       source="plaid", raw={"account_type": "depository"}, **kw)


def rows():
    out = []
    # Groceries and dinners vary and happen more than once a month: not bills.
    groceries = {"06": (180.0, 95.0), "07": (240.0, 60.0), "08": (205.0, 110.0),
                 "09": (260.0, 70.0), "10": (220.0, 0.0)}
    dinners = {"06": 52.0, "07": 75.0, "08": 48.0, "09": 66.0, "10": 60.0}
    for m in ("06", "07", "08", "09", "10"):
        out += [tx(f"2026-{m}-01", "Northwind", -4300.0, "Income"),
                tx(f"2026-{m}-02", "Parkside", 1650.0, "Rent & Housing"),        # fixed: rent
                tx(f"2026-{m}-03", "Rogers", 85.0, "Phone & Internet"),          # fixed: recurring
                tx(f"2026-{m}-04", "Netflix", 16.49, "Streaming"),               # fixed: recurring
                tx(f"2026-{m}-05", "Loblaws", groceries[m][0], "Groceries"),     # variable, Essentials
                tx(f"2026-{m}-06", "Pai", dinners[m], "Dining", account="card"), # variable, Lifestyle
                tx(f"2026-{m}-07", "Planet Fitness", 45.0, "Fitness")]           # fixed: recurring
        if groceries[m][1]:
            out.append(tx(f"2026-{m}-19", "Loblaws", groceries[m][1], "Groceries"))
            out.append(tx(f"2026-{m}-21", "Pai", 31.0, "Dining", account="card"))
    out.append(tx("2026-10-08", "Flights", 900.0, "Travel", one_off_since="2026-10-09"))
    return out


@pytest.fixture()
def client(tmp_path, monkeypatch):
    from app import create_app
    import finance.api as api
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY)
    app = create_app(str(tmp_path / "k.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        st = c.st = app.config["STORE"]
        data = rows()
        wanted = {(t.date, t.merchant): (t.category, t.one_off_since) for t in data}
        ingest(st, IngestResult(data, "chq"))
        st.set_categories({t.fingerprint: (wanted[(t.date, t.merchant)][0], "plaid")
                           for t in st.all_transactions()})
        for t in st.all_transactions():
            if wanted[(t.date, t.merchant)][1]:
                st.set_one_off(t.fingerprint, True) if hasattr(st, "set_one_off") else None
        st.set_setting("home_income", "4300")
        yield c


def get(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.get_json())
    return r.get_json()


def test_bills_are_fixed_and_the_rest_variable(client):
    from datetime import date
    from finance import kinds
    km = kinds.kind_map(client.st, client.st.all_transactions(), date.fromisoformat(TODAY))
    by = {(t.merchant, t.date): km.get(t.fingerprint) for t in client.st.all_transactions()}
    assert by[("Parkside", "2026-10-02")] == "fixed"
    assert by[("Rogers", "2026-10-03")] == "fixed"
    assert by[("Netflix", "2026-10-04")] == "fixed"
    assert by[("Planet Fitness", "2026-10-07")] == "fixed"       # a bill, though Lifestyle
    assert by[("Loblaws", "2026-10-05")] == "variable"            # Essentials, but decided weekly
    assert by[("Pai", "2026-10-06")] == "variable"
    assert ("Northwind", "2026-10-01") not in {k for k, v in by.items() if v}   # income is neither


def test_her_word_on_a_category_wins(client):
    r = client.put("/api/rules/kinds", json={"category": "Groceries", "kind": "fixed"})
    assert r.status_code == 200 and r.get_json()["kinds"] == {"Groceries": "fixed"}
    assert get(client, "/api/rules")["kinds"] == {"Groceries": "fixed"}
    tiles = get(client, "/api/insights/month")["tiles"]
    assert tiles["fixed"] / 100 == 1650.0 + 85.0 + 16.49 + 45.0 + 220.0
    client.put("/api/rules/kinds", json={"category": "Fitness", "kind": "variable"})
    tiles = get(client, "/api/insights/month")["tiles"]
    assert tiles["variable"] / 100 == pytest.approx(60.0 + 45.0 + 900.0)
    assert client.put("/api/rules/kinds", json={"category": "Income", "kind": "fixed"}).status_code == 400
    client.put("/api/rules/kinds", json={"category": "Groceries", "kind": None})
    assert get(client, "/api/rules")["kinds"] == {"Fitness": "variable"}


def test_insights_shows_both_lenses_and_they_add_up(client):
    d = get(client, "/api/insights/month")
    t = d["tiles"]
    assert t["fixed"] + t["variable"] == t["essentials"] + t["lifestyle"]
    w = d["where"]
    assert [k["key"] for k in w["kinds"]] == ["fixed", "variable"]
    assert sum(k["total"] for k in w["kinds"]) == w["total"]
    fixed_cats = {c["category"] for c in w["kinds"][0]["categories"]}
    assert fixed_cats == {"Rent & Housing", "Phone & Internet", "Streaming", "Fitness"}
    row = next(m for m in d["trend"]["months"] if m["month"] == "2026-10")
    assert row["fixed"] + row["variable"] == row["total"]


def test_the_filters_narrow_what_the_page_draws(client):
    base = get(client, "/api/insights/month")
    assert base["filters"] == {"account": None, "span": 12, "one_offs": "in", "show": None}
    assert {a["id"] for a in base["accounts"]} == {"chq", "card"}
    # One account: the card only has Pai.
    card = get(client, "/api/insights/month?account=card")
    assert card["tiles"]["lifestyle"] / 100 == 60.0 and card["tiles"]["essentials"] == 0
    assert card["tiles"]["income"] == base["tiles"]["income"]      # income isn't narrowed
    # A span of 3 months.
    assert len(get(client, "/api/insights/month?span=3")["trend"]["months"]) == 3
    assert len(base["trend"]["months"]) == 5                          # all the ledger has
    # One-offs left out: the flights go.
    out = get(client, "/api/insights/month?one_offs=out")
    assert base["tiles"]["lifestyle"] - out["tiles"]["lifestyle"] == 90000
    # Only Fixed: Pai and Loblaws go, income stays.
    fixed = get(client, "/api/insights/month?show=fixed")
    assert fixed["tiles"]["variable"] == 0 and fixed["tiles"]["fixed"] == base["tiles"]["fixed"]
    assert fixed["where"]["total"] == base["tiles"]["fixed"]
    # Only Lifestyle.
    life = get(client, "/api/insights/month?show=lifestyle")
    assert life["tiles"]["essentials"] == 0 and life["tiles"]["lifestyle"] == base["tiles"]["lifestyle"]
    # Nonsense is ignored, not an error.
    assert get(client, "/api/insights/month?span=7&show=x")["filters"]["span"] == 12


def test_home_and_the_list_see_the_same_kinds(client):
    home = get(client, "/api/home")
    snap = {r["key"]: r for r in home["snapshot"]["rows"]}
    assert snap["fixed"]["lens"] == "kind" and snap["variable"]["lens"] == "kind"
    assert snap["fixed"]["spent"] + snap["variable"]["spent"] == \
        snap["essentials"]["spent"] + snap["lifestyle"]["spent"]
    assert snap["fixed"]["usual"] == pytest.approx(1650.0 + 85.0 + 16.49 + 45.0, abs=0.02)
    listed = get(client, "/api/transactions/list?month=2026-10&group=fixed&limit=100")
    assert {t["merchant"] for t in listed["transactions"]} == \
        {"Parkside", "Rogers", "Netflix", "Planet Fitness"}
    assert all(t["kind"] == "fixed" for t in listed["transactions"])
    assert listed["focus"]["label"] == "Fixed"
    assert listed["focus"]["total"] == snap["fixed"]["spent"]
    assert get(client, "/api/transactions/list?month=2026-10")["kinds"] == {"fixed": "Fixed", "variable": "Variable"}
