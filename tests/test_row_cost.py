"""ROWCOST-01 (RC-01, RC-02, RC-03; product owner 2026-11-16): a split
purchase's row and its page header show what it costs her now, the number
Spent and the Allowance already count, so the month's rows add up to Spent.

Rule A stays: what others still owe is hers until it comes back. Each
payback (linked, cash, another app) and work paying her share lowers it at
once. The line under says the whole purchase, what's back and what's to come.
"""

from __future__ import annotations

import pytest

from tests.test_paid_back import MONTH, add, client, day, detail, parts, tx  # noqa: F401


def _split(c, charge, *people, mode="amount"):
    r = c.put(f"/api/transactions/{charge}/split", json={
        "mode": mode, "people": [{"name": n, "amount": a} if a is not None else {"name": n}
                                 for n, a in people]})
    assert r.status_code == 200, r.get_json()


def _ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def _month(c):
    return c.get("/api/transactions/list", query_string={"month": MONTH, "limit": "500"}).get_json()


def _row(c, tid):
    return next(r for r in _month(c)["transactions"] if r["id"] == tid)


@pytest.fixture()
def month(client):
    """One month with every kind of payback on a split."""
    i = add(client,
            tx("NORTHWIND LTD PAYROLL", -3000.0, "Income", when=day(20), merchant="Northwind Ltd"),
            tx("TST* GUSTO 504", 127.50, "Dining", when=day(15), merchant="Gusto"),
            tx("NOPA RESTAURANT", 59.33, "Dining", when=day(14), merchant="Nopa Restaurant"),
            tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(13), merchant="Pai Northern Thai"),
            tx("PIZZA NOVA", 79.95, "Dining", when=day(12), merchant="Pizza Nova"),
            tx("JOEY KING ST", 90.0, "Dining", when=day(11), merchant="Joey King St"),
            tx("SUSHI NAMI", 80.0, "Dining", when=day(10), merchant="Sushi Nami"),
            tx("LOBLAWS", 41.20, "Groceries", when=day(9), merchant="Loblaws"),
            tx("E-TRANSFER FROM PRIYA SHAH", -42.50, when=day(8), merchant="Priya Shah"),
            tx("E-TRANSFER FROM PRIYA S", -19.77, when=day(7), merchant="Priya Shah"),
            tx("E-TRANSFER FROM SAM L", -19.77, when=day(7), merchant="Sam Lee"),
            tx("NORTHWIND LTD EXPENSES", -60.0, when=day(6), merchant="Northwind Ltd"),
            tx("E-TRANSFER FROM SAM LEE", -56.65, when=day(5), merchant="Sam Lee"),
            tx("E-TRANSFER FROM JO", -30.0, when=day(4), merchant="Jo"))
    gusto, nopa, pai = i["TST* GUSTO 504"], i["NOPA RESTAURANT"], i["PAI NORTHERN THAI"]
    pizza, joey, sushi = i["PIZZA NOVA"], i["JOEY KING ST"], i["SUSHI NAMI"]
    _split(client, gusto, ("Priya", 42.50), ("Sam", 30.0), ("Jo", 15.0))
    _split(client, nopa, ("Priya", None), ("Sam", None), mode="even")
    _split(client, pai, ("Sam", None), mode="even")
    _split(client, pizza, ("Sam", 26.65), ("Jo", 26.65))
    _split(client, joey, ("Sam", 30.0), ("Jo", 30.0))
    _split(client, sushi, ("Priya", None), mode="unknown")
    # Gusto: Priya pays in full (linked), Sam pays part in cash.
    _ok(parts(client, i["E-TRANSFER FROM PRIYA SHAH"],
              {"kind": "payback", "amount": 42.50, "charge": gusto, "person": "Priya"}))
    _ok(client.post(f"/api/transactions/{gusto}/split/cash", json={"name": "Sam", "amount": 10.0}))
    # Nopa: everyone pays.
    _ok(parts(client, i["E-TRANSFER FROM PRIYA S"],
              {"kind": "payback", "amount": 19.77, "charge": nopa, "person": "Priya"}))
    _ok(parts(client, i["E-TRANSFER FROM SAM L"],
              {"kind": "payback", "amount": 19.77, "charge": nopa, "person": "Sam"}))
    # Pai: work pays her share; Sam's is still to come.
    _ok(client.post(f"/api/transactions/{i['NORTHWIND LTD EXPENSES']}/mark",
                    json={"case": "reimbursement", "charge": pai, "share": True}))
    # PB-30: one e-Transfer from Sam pays back Pizza Nova and Joey.
    _ok(parts(client, i["E-TRANSFER FROM SAM LEE"],
              {"kind": "payback", "amount": 26.65, "charge": pizza, "person": "Sam"},
              {"kind": "payback", "amount": 30.0, "charge": joey, "person": "Sam"}))
    # Not sure yet: Priya sends $30.00.
    _ok(parts(client, i["E-TRANSFER FROM JO"],
              {"kind": "payback", "amount": 30.0, "charge": sushi}))
    return i


def test_the_rows_add_up_to_spent(client, month):
    lst = _month(client)
    rows = [r for r in lst["transactions"] if r["counts"] == "spending"]
    total = round(sum(-r["amount"] if r["inflow"] else r["amount"] for r in rows), 2)
    assert total == lst["month_totals"]["spent"]
    # Every split row's amount is the server's cost now.
    for r in rows:
        if r.get("cost"):
            assert r["cost"]["now"] == r["amount"], r["merchant"]


def test_each_row_costs_what_it_costs_now(client, month):
    i = month
    want = {
        # Rule A: Sam's $20.00 and Jo's $15.00 are still hers.
        "TST* GUSTO 504": (75.0, "$127.50 split · $52.50 back · $35.00 to come"),
        "NOPA RESTAURANT": (19.79, "$59.33 split · $39.54 back"),
        "PAI NORTHERN THAI": (60.0, "$120.00 split · work paid your $60.00 · $60.00 to come"),
        "PIZZA NOVA": (53.30, "$79.95 split · $26.65 back · $26.65 to come"),
        "JOEY KING ST": (60.0, "$90.00 split · $30.00 back · $30.00 to come"),
        "SUSHI NAMI": (50.0, "$80.00 split 2 ways · not sure yet"),
    }
    for desc, (amount, note) in want.items():
        r = _row(client, i[desc])
        assert (r["amount"], r["note"]) == (amount, note), desc


def test_nobody_paid_yet_is_the_whole_purchase(client):
    """Rule A stays (RC-01): Gusto with nothing back reads −$127.50."""
    i = add(client, tx("TST* GUSTO 504", 127.50, "Dining", when=day(3), merchant="Gusto"))
    gusto = i["TST* GUSTO 504"]
    _split(client, gusto, ("Priya", 42.50), ("Sam", 30.0), ("Jo", 15.0))
    r = _row(client, gusto)
    assert (r["amount"], r["note"]) == (127.50, "$127.50 split · $87.50 to come")
    assert r["cost"]["back"] == 0.0 and r["cost"]["to_come"] == 87.50


def test_the_page_header_names_the_ways(client):
    """RC-02: "$150.00 split 5 ways · $40.00 back · $50.00 to come", and
    Alex's share let go stays hers: −$110.00 now."""
    i = add(client, tx("LOBLAWS", 150.0, "Groceries", when=day(3), merchant="Loblaws"))
    lob = i["LOBLAWS"]
    _split(client, lob, ("Jo", 30.0), ("Sam", 30.0), ("Priya", 30.0), ("Alex", 30.0))
    _ok(client.post(f"/api/transactions/{lob}/split/cash", json={"name": "Jo", "amount": 30.0}))
    _ok(client.post(f"/api/transactions/{lob}/split/cash", json={"name": "Sam", "amount": 10.0}))
    _ok(client.post(f"/api/transactions/{lob}/split/let-go", json={"name": "Alex"}))
    t = detail(client, lob)
    t = t.get("transaction", t)
    assert t["amount"] == 110.0
    assert t["cost"]["header"] == "$150.00 split 5 ways · $40.00 back · $50.00 to come"
    assert t["cost"]["line"] == "$150.00 split · $40.00 back · $50.00 to come"
    assert (t["cost"]["ways"], t["cost"]["whole"], t["cost"]["share"]) == (5, 150.0, 60.0), "with Alex's $30.00 (S-04g)"


def test_a_payback_counts_the_header_down(client):
    """RC-03: Sam pays $15.00 and the header goes from $120.00 to $105.00."""
    i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(3), merchant="Pai Northern Thai"))
    pai = i["PAI NORTHERN THAI"]
    _split(client, pai, ("Sam", None), mode="even")
    assert detail(client, pai)["amount"] == 120.0
    _ok(client.post(f"/api/transactions/{pai}/split/cash", json={"name": "Sam", "amount": 15.0}))
    t = detail(client, pai)
    assert t["amount"] == 105.0
    assert t["cost"]["header"] == "$120.00 split · $15.00 back · $45.00 to come"


def test_settled_at_nothing_reads_as_today(client):
    """Settled at $0.00 reads as today: work paid her share and Sam paid
    his, so "Reimbursed · not your spending" (friends alone: "Paid back in
    full · not your spending"), with no cost line."""
    i = add(client, tx("PAI NORTHERN THAI", 120.0, "Dining", when=day(3), merchant="Pai Northern Thai"),
            tx("NORTHWIND LTD EXPENSES", -60.0, when=day(2), merchant="Northwind Ltd"))
    pai = i["PAI NORTHERN THAI"]
    _split(client, pai, ("Sam", None), mode="even")
    _ok(client.post(f"/api/transactions/{i['NORTHWIND LTD EXPENSES']}/mark",
                    json={"case": "reimbursement", "charge": pai, "share": True}))
    _ok(client.post(f"/api/transactions/{pai}/split/cash", json={"name": "Sam", "amount": 60.0}))
    r = _row(client, pai)
    assert r["amount"] == 0.0
    assert r["note"] == "Reimbursed · not your spending"
    assert r["cost"] is None
