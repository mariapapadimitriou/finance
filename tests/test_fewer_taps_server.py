"""Server groundwork for the tap audit (2026-11-26, "fewer taps"):

* numbers that looked wrong on demo data: a card payment offered (and, on
  Continue, confirmed) as pay; the month picker's Leftover beside the tab's
  Left;
* P6/P8: card payments are never pay or income, and a shop's refund on a
  card isn't a card payment;
* P5: from a purchase, a person's money for part of it is listed;
* P14: a one-off is left out of every past-spending figure, and still
  counts in its own month;
* P10: a category change, its "always" rule and a new split can be undone.
"""

from __future__ import annotations

import sys
from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

sys.path.insert(0, "tests")

TODAY = date.today()


def ago(n: int) -> str:
    return (TODAY - timedelta(days=n)).isoformat()


def row(amount, desc, when, account="card", kind="credit", merchant=""):
    return Transaction(date=when, description=desc, amount=amount, account_id=account,
                       account_name=account, merchant=merchant, raw={"account_type": kind})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "taps.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def ids(st) -> dict[str, str]:
    return {t.description: t.fingerprint for t in st.all_transactions()}


# ── Card payments are never pay (P6, P8; the $13,477 Allowance) ──────────

@pytest.fixture()
def demo(client):
    from sample_data.generate import load_demo
    load_demo(client.st)
    return client


def test_a_card_payment_is_never_a_pay_candidate(demo):
    d = demo.get("/api/income-bills").get_json()
    payers = [c["payer"] for c in d["candidates"]]
    assert payers == ["Direct Deposit Payroll Acme"]
    assert not any("thank you" in p.lower() for p in payers)


def test_continue_on_set_up_leaves_the_allowance_on_her_pay(demo):
    """Set-up's Continue says Yes to every candidate: with the card payment
    among them, income was pay plus ~$2,650 of card payments."""
    for c in demo.get("/api/income-bills").get_json()["candidates"]:
        demo.post("/api/income-bills/pay/answer", json={"payer": c["payer"], "answer": "yes"})
    home = demo.get("/api/home").get_json()["safe_to_spend"]
    income = next(r for r in home["rows"] if r["key"] == "income")
    assert {line["label"] for line in income["lines"]} <= {"Direct Deposit Payroll Acme", "Acme"}
    # The income screens and the Allowance agree on what comes in.
    assert demo.get("/api/income-bills").get_json()["totals"]["income"] == pytest.approx(11700.0)
    assert income["amount"] <= 11700.0 + 0.01
    # And no rule turned card payments into pay.
    assert not any(k.startswith("payer:online payment") for k in demo.st.pay_rules())


def test_never_pay_covers_card_rows_and_card_payment_names():
    from finance.txlist import never_pay
    assert never_pay(row(-900, "ONLINE PAYMENT - THANK YOU", ago(1), kind=""))
    assert never_pay(row(-45, "JOEY KING ST REFUND", ago(1)))
    assert not never_pay(row(-5850, "DIRECT DEPOSIT PAYROLL ACME", ago(1), account="chq", kind="depository"))
    payroll = row(-5850, "VISA DIRECT PAYROLL", ago(1), account="chq", kind="depository")
    payroll.raw["issuer_category"] = "INCOME_WAGES"
    assert not never_pay(payroll)
    assert not never_pay(row(40, "ONLINE PAYMENT - THANK YOU", ago(1)))


def test_a_pay_rule_never_sorts_a_card_payment_and_puts_old_ones_back(client):
    from finance import pay_rules
    load = [row(-1200, "ONLINE PAYMENT - THANK YOU", ago(n), kind="") for n in (3, 33, 63)]
    ingest(client.st, IngestResult(transactions=load, account_id="card"))
    client.st.set_pay_rule("payer:online payment - thank you", "Online Payment - Thank You")
    t = client.st.all_transactions()[0]
    assert not pay_rules.matches(t, client.st.pay_rules())
    # One a rule sorted as pay before this fix goes back to a transfer.
    client.st.write_categories({t.fingerprint: ("Income", pay_rules.SOURCE)})
    pay_rules.apply(client.st)
    assert client.st.get_transaction(t.fingerprint).category == "Transfers"


def test_a_card_payments_page_offers_no_pay(client):
    ingest(client.st, IngestResult(transactions=[row(-1709.21, "ONLINE PAYMENT - THANK YOU", ago(1), kind="")],
                                   account_id="card"))
    tid = ids(client.st)["ONLINE PAYMENT - THANK YOU"]
    keys = {c["key"] for c in client.get(f"/api/transactions/{tid}/cases").get_json()["cases"]}
    assert "regular_pay" not in keys and "pay" not in keys
    r = client.post(f"/api/transactions/{tid}/mark", json={"case": "regular_pay"})
    assert r.status_code == 400
    assert client.st.get_transaction(tid).category != "Income"
    detail = client.get(f"/api/transactions/{tid}").get_json()
    assert detail["never_pay"] is True and detail["card_payment"] is True


# ── A shop's refund on a card is not a card payment (P8) ─────────────────

def test_a_refund_from_a_shop_she_bought_from_is_not_a_transfer(client):
    ingest(client.st, IngestResult(transactions=[row(90, "JOEY KING ST", ago(3))], account_id="card"))
    # The refund arrives in a later sync than the purchase.
    ingest(client.st, IngestResult(transactions=[row(-45, "JOEY KING ST REFUND", ago(1))], account_id="card"))
    i = ids(client.st)
    refund = client.st.get_transaction(i["JOEY KING ST REFUND"])
    assert refund.category != "Transfers" and refund.category_source != "card_inflow"
    page = client.get(f"/api/transactions/{refund.fingerprint}").get_json()
    assert page["card_payment"] is False and (page["chip"] or {}).get("label") != "Transfer"


def test_money_back_takes_the_purchases_category():
    from finance.categorize import apply_categories, bought_from
    purchase = row(60, "BLUE DOOR BISTRO", ago(5))
    purchase.category = "Dining"
    back = row(-20, "BLUE DOOR BISTRO", ago(1))
    apply_categories([back], shops=bought_from([purchase]))
    assert back.category == "Dining"


def test_a_credit_that_says_refund_is_not_a_payment_and_an_unknown_one_still_is():
    from finance.categorize import apply_categories
    named = row(-30, "ZZQ STORE RETURN 4412", ago(1))
    unknown = row(-412, "ZZQ BILL PAY REF 88812", ago(1))
    apply_categories([named, unknown])
    assert named.category != "Transfers"
    assert (unknown.category, unknown.category_source) == ("Transfers", "card_inflow")


# ── The month picker says the tab's Left ─────────────────────────────────

def test_this_months_left_in_the_picker_is_homes_left(demo):
    home = demo.get("/api/home").get_json()["safe_to_spend"]
    assert home["state"] in ("ok", "over")
    months = demo.get("/api/transactions/months").get_json()["months"]
    [now] = [m for m in months if m["month"] == home["month"]]
    want = -home["over_by"] if home["state"] == "over" else home["shown"]
    assert now["allowance"] is True and now["left"] == pytest.approx(want)
    past = [m for m in months if m["month"] != home["month"]]
    assert past and all(m["allowance"] is False for m in past)
    assert all(m["left"] == pytest.approx(m["income"] - m["spent"] - m["saved"]) for m in past)


# ── P5: a person's money for part of a purchase ──────────────────────────

def test_a_persons_money_for_part_of_a_purchase_is_listed_first(client):
    from test_splits import etransfer_in
    ingest(client.st, IngestResult(transactions=[row(127.5, "TST* GUSTO 504", ago(4))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[
        etransfer_in(42.5, "Priya Shah", ago(1)),
        row(-127.5, "STORE CREDIT", ago(2), account="chq", kind="depository"),
        row(-900, "PAYROLL", ago(1), account="chq", kind="depository")], account_id="chq"))
    i = ids(client.st)
    body = client.get(f"/api/transactions/{i['TST* GUSTO 504']}/paid-back-find").get_json()
    found = [c["id"] for c in body["candidates"]]
    priya = i["E-TRANSFER RECEIVED PRIYA SHAH"]
    assert found[0] == priya
    first = body["candidates"][0]
    assert first["sender"] == "Priya Shah" and first["likely"] is True and first["amount"] == 42.5
    # A person is only suggested: nothing is linked by listing it.
    assert first["kind"] is None
    assert i["PAYROLL"] not in found


def test_a_part_payback_never_forgives_the_rest(client):
    from test_splits import etransfer_in
    ingest(client.st, IngestResult(transactions=[row(127.5, "TST* GUSTO 504", ago(4))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[etransfer_in(42.5, "Priya Shah", ago(1))], account_id="chq"))
    i = ids(client.st)
    purchase, money = i["TST* GUSTO 504"], i["E-TRANSFER RECEIVED PRIYA SHAH"]
    r = client.post(f"/api/transactions/{money}/parts",
                    json={"parts": [{"kind": "payback", "charge": purchase, "amount": 42.5, "person": "Priya"}]})
    assert r.status_code == 200, r.get_json()
    after = client.get(f"/api/transactions/{purchase}/paid-back-find").get_json()
    assert after["left"] == pytest.approx(85.0)


def test_split_people_still_come_before_anyone_else(client):
    from test_splits import etransfer_in
    ingest(client.st, IngestResult(transactions=[row(90, "JOEY KING ST", ago(3))], account_id="card"))
    ingest(client.st, IngestResult(transactions=[etransfer_in(40, "Priya Shah", ago(2)),
                                                 etransfer_in(30, "Sam Lee", ago(1))], account_id="chq"))
    i = ids(client.st)
    tid = i["JOEY KING ST"]
    assert client.put(f"/api/transactions/{tid}/split",
                      json={"mode": "even", "people": [{"name": "Priya"}]}).status_code == 200
    rows = client.get(f"/api/transactions/{tid}/paid-back-find").get_json()["candidates"]
    assert rows and rows[0]["kind"] == "person" and rows[0]["person"] == "Priya"
    assert rows[0]["amount"] == 40.0


# ── P14: a one-off is never history ──────────────────────────────────────

def _months_of(amounts: dict[int, float], big_back: int | None = None) -> list[Transaction]:
    """One grocery charge in each of the last few full months, and (if
    asked) a $3,000 one-off in the month `big_back` months ago."""
    out = []
    first = TODAY.replace(day=1)
    for back, amount in amounts.items():
        m = first
        for _ in range(back):
            m = (m - timedelta(days=1)).replace(day=1)
        t = row(amount, f"GROCER {back}", m.replace(day=10).isoformat(), merchant="Grocer")
        t.category, t.category_source = "Groceries", "user"
        out.append(t)
        if back == big_back:
            big = row(3000, "SOFA WORLD", m.replace(day=12).isoformat(), merchant="Sofa World")
            big.category, big.category_source, big.one_off_since = "Groceries", "user", TODAY.isoformat()
            out.append(big)
    return out


def test_one_offs_shape_no_average():
    from finance import analytics, anchor, money_plan, spend_plan
    from finance.usual_month import usual
    txns = _months_of({0: 50, 1: 400, 2: 400, 3: 400, 4: 400}, big_back=1)
    plain = [t for t in txns if not t.one_off]
    assert analytics.typical_month_spend(txns) == analytics.typical_month_spend(plain)
    base = analytics.category_baselines(txns)["Groceries"]
    assert base["max"] == pytest.approx(400.0)
    assert analytics.summary(txns)["average_transaction"] == analytics.summary(plain)["average_transaction"]
    assert analytics.weekday_profile(txns) == analytics.weekday_profile(plain)
    assert spend_plan.suggest_monthly_amount(txns) == spend_plan.suggest_monthly_amount(plain)
    assert money_plan.typical_monthly(txns) == money_plan.typical_monthly(plain)
    assert anchor.essentials(txns, TODAY.isoformat())["average"] == pytest.approx(400.0)
    assert usual(txns, TODAY)["categories"]["Groceries"]["usual"] == pytest.approx(400.0)


def test_a_one_off_still_counts_in_its_own_month():
    from finance import analytics
    txns = _months_of({0: 50, 1: 400, 2: 400, 3: 400}, big_back=1)
    last = (TODAY.replace(day=1) - timedelta(days=1)).strftime("%Y-%m")
    month = next(m for m in analytics.monthly_totals(txns) if m["month"] == last)
    assert month["spend"] == pytest.approx(3400.0)
    # Against the month it's in, the comparison still sees it.
    change = next(r for r in analytics.month_over_month(txns, last) if r["category"] == "Groceries")
    assert change["amount"] == pytest.approx(3400.0) and change["baseline"] == pytest.approx(400.0)


def test_a_one_off_in_its_own_month_still_comes_off_the_allowance():
    from finance import safe_to_spend
    t = row(300, "SOFA WORLD", TODAY.isoformat(), merchant="Sofa World")
    t.category, t.category_source, t.one_off_since = "Shopping", "user", TODAY.isoformat()
    spent = safe_to_spend.already_spent([t], TODAY, {})
    assert spent["amount_c"] == 30000


def test_a_one_off_payment_is_left_out_of_cautious_income():
    from finance import safe_to_spend
    txns = []
    first = TODAY.replace(day=1)
    m = first
    for back in range(1, 5):
        m = (m - timedelta(days=1)).replace(day=1)
        pay = row(-3000, "PAYROLL ACME", m.replace(day=15).isoformat(), account="chq", kind="depository")
        pay.category = "Income"
        txns.append(pay)
        if back == 2:
            bonus = row(-9000, "PAYROLL ACME BONUS", m.replace(day=20).isoformat(), account="chq",
                        kind="depository")
            bonus.category, bonus.one_off_since = "Income", TODAY.isoformat()
            txns.append(bonus)
    careful = safe_to_spend.cautious_income(txns, TODAY)
    assert careful["highest"] == pytest.approx(3000.0)


# ── P10: Undo for a category change, its rule and a split ────────────────

def _card(client, *rows_):
    ingest(client.st, IngestResult(transactions=list(rows_), account_id="card"))
    return ids(client.st)


def test_a_category_change_undoes(client):
    i = _card(client, row(12, "CORNER CAFE", ago(2), merchant="Corner Cafe"))
    tid = i["CORNER CAFE"]
    was = client.st.get_transaction(tid)
    r = client.patch(f"/api/transactions/{tid}", json={"category": "Coffee"}).get_json()
    assert client.st.get_transaction(tid).category == "Coffee"
    assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
    now = client.st.get_transaction(tid)
    assert (now.category, now.category_source) == (was.category, was.category_source)


def test_always_for_this_merchant_undoes_rows_and_rule(client):
    i = _card(client, row(12, "CORNER CAFE", ago(2), merchant="Corner Cafe"),
              row(9, "CORNER CAFE 2", ago(9), merchant="Corner Cafe"))
    before = {t.fingerprint: t.category for t in client.st.all_transactions()}
    r = client.patch(f"/api/transactions/{i['CORNER CAFE']}",
                     json={"category": "Coffee", "apply_to_merchant": True}).get_json()
    assert r["scope"] == "merchant" and client.st.overrides()
    assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
    assert not client.st.overrides()
    assert {t.fingerprint: t.category for t in client.st.all_transactions()} == before


def test_the_always_switch_undoes(client):
    i = _card(client, row(12, "CORNER CAFE", ago(2), merchant="Corner Cafe"))
    tid = i["CORNER CAFE"]
    client.patch(f"/api/transactions/{tid}", json={"category": "Coffee"})
    on = client.put(f"/api/transactions/{tid}/always", json={"on": True}).get_json()
    assert client.st.overrides()
    assert client.post("/api/transactions/undo", json=on["undo"]).status_code == 200
    assert not client.st.overrides()


def test_a_new_split_undoes(client):
    i = _card(client, row(90, "NOODLE BAR", ago(2), merchant="Noodle Bar"))
    tid = i["NOODLE BAR"]
    r = client.put(f"/api/transactions/{tid}/split",
                   json={"mode": "even", "people": [{"name": "Priya"}, {"name": "Sam"}]}).get_json()
    assert tid in client.st.splits()
    assert client.post("/api/transactions/undo", json=r["undo"]).status_code == 200
    assert tid not in client.st.splits()
    assert client.st.get_transaction(tid).my_share is None
