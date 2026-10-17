"""One number everywhere (2026-10-14): the screens that name this month's
spending, income, saving or Allowance all agree with Home.

Two ledgers: one with a chequing account and deposits Pearl can see, and a
card-only one where income is what she told Pearl."""

from __future__ import annotations

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = "2026-10-14"
MONTH = "2026-10"


def tx(day, merchant, amount, category, account="chq", kind="depository", **kw):
    return Transaction(date=day, description=merchant.upper(), merchant=merchant, amount=amount,
                       category=category, account_id=account, account_name=account,
                       source="plaid", raw={"account_type": kind}, **kw)


def rows():
    out = []
    for m in ("07", "08", "09", "10"):
        out += [tx(f"2026-{m}-01", "Northwind", -4300.0, "Income"),
                tx(f"2026-{m}-02", "Parkside", 1650.0, "Rent & Housing"),
                tx(f"2026-{m}-03", "Loblaws", 220.0, "Groceries", account="card", kind="credit"),
                tx(f"2026-{m}-05", "Pai", 60.0, "Dining", account="card", kind="credit"),
                tx(f"2026-{m}-06", "TFR-TO 3333", 500.0, "Saved")]
    out += [tx("2026-10-09", "TFR-FR 3333", -150.0, "Saved"),          # taken back out
            tx("2026-10-10", "TD Visa Payment", 300.0, "Transfers"),
            tx("2026-10-11", "Sister", -40.0, "Transfers"),             # money in, not income
            tx("2026-10-12", "Work lunch", 35.0, "Dining", account="card", kind="credit")]
    return out


def make(tmp_path, monkeypatch, *, card_only: bool):
    from app import create_app
    import finance.api as api
    monkeypatch.setattr(api, "_today_iso", lambda: TODAY)
    app = create_app(str(tmp_path / ("card.db" if card_only else "full.db")))
    app.config.update(TESTING=True)
    c = app.test_client()
    st = c.st = app.config["STORE"]
    data = rows()
    if card_only:
        data = [t for t in data if t.account_id == "card"]
    wanted = {(t.date, t.merchant): t.category for t in data}
    ingest(st, IngestResult(data, "chq"))
    st.set_categories({t.fingerprint: (wanted[(t.date, t.merchant)], "plaid")
                       for t in st.all_transactions()})
    st.note_account("card", name="Visa ••4321", item_id="i", account_type="credit")
    if not card_only:
        st.note_account("chq", name="Chequing ••1111", item_id="i", account_type="depository",
                        subtype="checking")
    # Excluded: counts nowhere.
    lunch = next(t for t in st.all_transactions() if t.merchant == "Work lunch")
    st.exclude(lunch.fingerprint, "work")
    st.set_setting("home_income", "4300")
    st.set_setting("home_rent", "1650")
    st.set_setting("savings_target", "600")
    chest = st.add_piggy_bank("Holidays", 1200, "annual", None, "2026-07")
    st.add_draw(chest, MONTH, -200.0, "Added")
    return c


@pytest.fixture()
def full(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch, card_only=False)


@pytest.fixture()
def cards(tmp_path, monkeypatch):
    return make(tmp_path, monkeypatch, card_only=True)


def get(c, url):
    r = c.get(url)
    assert r.status_code == 200, (url, r.get_json())
    return r.get_json()


def sts_row(home, key):
    return next((r for r in home["safe_to_spend"]["rows"] if r["key"] == key), None)


def test_spending_this_month_is_the_same_number_everywhere(full):
    home = get(full, "/api/home")
    spent = sts_row(home, "spent")["amount"]
    assert spent == get(full, f"/api/transactions/list?month={MONTH}&limit=500")["totals"]["spent"]
    summary = next(m for m in get(full, "/api/summary")["monthly"] if m["month"] == MONTH)
    assert spent == summary["spend"]
    insights = get(full, f"/api/insights/month?month={MONTH}")
    assert spent == pytest.approx(sum(r["spent"] for r in insights["categories"]) / 100)
    # Budgets cover what isn't a bill (rent is), so they add up to the rest.
    budgets = get(full, "/api/category-budgets")
    rent = sum(t["amount"] for t in get(full, f"/api/transactions/list?month={MONTH}&limit=500")
               ["transactions"] if t["category"] == "Rent & Housing")
    assert spent == pytest.approx(sum(r["spent"] for r in budgets["rows"]) + rent)
    assert spent == 1650.0 + 220.0 + 60.0                     # the excluded lunch counts nowhere


def test_income_this_month_is_the_same_number_everywhere(full):
    home = get(full, "/api/home")
    income = sts_row(home, "income")["amount"]
    tiles = get(full, f"/api/insights/month?month={MONTH}")["tiles"]
    assert tiles["income"] / 100 == income == 4300.0 and tiles["estimate"] is False
    assert get(full, f"/api/transactions/list?month={MONTH}&limit=500")["totals"]["income"] == income
    facts = get(full, "/api/path/step/essentials")["facts"]
    assert facts["month"] == "2026-09" and facts["income"] == 4300.0 and facts["estimate"] is False
    assert get(full, "/api/income-bills")["totals"]["income"] == income


def test_card_only_uses_the_income_she_told_pearl_everywhere(cards):
    home = get(cards, "/api/home")
    assert sts_row(home, "income")["amount"] == 4300.0
    tiles = get(cards, f"/api/insights/month?month={MONTH}")["tiles"]
    assert tiles["income"] == 430000 and tiles["estimate"] is True
    facts = get(cards, "/api/path/step/essentials")["facts"]
    assert facts["income"] == 4300.0 and facts["estimate"] is True
    assert facts["income"] >= facts["essentials"] > 0                 # covered, on told income
    assert home["savings"]["left_over"]["estimate"] is True


def test_saving_this_month_is_the_same_number_everywhere(full):
    home = get(full, "/api/home")
    saved = sts_row(home, "saved")["amount"]
    # Saved in (500) less taken out (150). The chest's monthly amount and the
    # $200 added to it by hand come from her Anchor, not the month (THL-230).
    assert saved == 500.0 - 150.0
    snapshot = next(r for r in home["snapshot"]["rows"] if r["key"] == "savings")
    assert snapshot["saved"] == saved
    insights = get(full, f"/api/insights/month?month={MONTH}")
    assert insights["tiles"]["set_aside"] / 100 == saved
    assert next(m for m in insights["money"] if m["month"] == MONTH)["set_aside"] / 100 == saved
    from finance import carryover, savings
    assert carryover.result(full.st.all_transactions(), "2026-09",
                            saved=savings.put_away_month(full.st, full.st.all_transactions(),
                                                         "2026-09"))["saved"] == 500.0


def test_homes_savings_this_month_is_the_same_saving_figure(full):
    home = get(full, "/api/home")
    s = home["savings"]
    assert s["month"] == MONTH
    assert s["put_away"]["contributions"] == 500.0 and s["put_away"]["withdrawals"] == 150.0
    assert "chests" not in s["put_away"]
    assert s["put_away"]["net"] == sts_row(home, "saved")["amount"]
    assert s["left_over"]["income"] == sts_row(home, "income")["amount"]
    assert s["left_over"]["spent"] == sts_row(home, "spent")["amount"]


def test_goals_quotes_homes_safe_to_spend(full):
    home = get(full, "/api/home")
    goals = get(full, "/api/goals")
    assert goals["safe_to_spend"] == home["safe_to_spend"]["shown"]
    chest = full.st.piggy_banks()[0]
    assert get(full, f"/api/goals/chests/{chest.id}")["safe_to_spend"] == home["safe_to_spend"]["shown"]


def test_profile_bills_count_the_rent_home_counts(full):
    from finance.income_bills import bills_each_month
    # Rent among the bills: counted once, told or not.
    ib = get(full, "/api/income-bills")
    rent_rows = [r for r in ib["bills"] if r["category"] == "Rent & Housing" and r["ticked"]]
    assert rent_rows and ib["totals"]["bills"] == bills_each_month(ib["bills"], 1650.0)
    assert bills_each_month(ib["bills"], 1650.0) == bills_each_month(ib["bills"], 0.0)
    # No rent bill yet: the rent she told Home about counts, as Home counts it.
    others = [r for r in ib["bills"] if r["category"] != "Rent & Housing"]
    assert bills_each_month(others, 1650.0) == bills_each_month(others, 0.0) + 1650.0
