"""PQ-01 Whose pay is this? and PQ-02 How often is this pay? (POLISH-01):
GET /api/transactions/<id>/paydays, the deposits from the same payer into
the same account, and Pearl's guess at how often they come."""

from __future__ import annotations

import sys
from datetime import date, timedelta

sys.path.insert(0, __file__.rsplit("/", 1)[0])
from test_what_was_this import client, load, row  # noqa: E402,F401


def _every(days: int, n: int, amount=-2150.0, desc="NORTHWIND LTD PAYROLL", account="chq"):
    start = date.today() - timedelta(days=days * (n - 1) + 1)
    return [row(amount, desc, account=account, merchant="Northwind Ltd",
                when=(start + timedelta(days=days * k)).isoformat()) for k in range(n)]


def test_paydays_and_a_guess(client):
    ids = load(client.st, *_every(14, 5), row(-40, "REFUND SHOP", merchant="Shop"),
               *_every(14, 2, account="other"))
    last = max((t for t in client.st.all_transactions() if t.merchant == "Northwind Ltd"
                and t.account_id == "chq"), key=lambda t: t.date)
    r = client.get(f"/api/transactions/{last.fingerprint}/paydays").get_json()
    assert r["count"] == 5 and len(r["dates"]) == 5 and r["dates"] == sorted(r["dates"])
    assert r["first"] == r["dates"][0] and r["dates"][-1] == last.date[:10]
    assert last.fingerprint in r["ids"]
    assert r["cadence"] == "biweekly"
    assert r["next"] > date.today().isoformat()
    assert ids  # loaded


def test_too_few_to_guess(client):
    load(client.st, *_every(14, 2))
    t = next(t for t in client.st.all_transactions() if t.merchant == "Northwind Ltd")
    r = client.get(f"/api/transactions/{t.fingerprint}/paydays").get_json()
    assert r["count"] == 2 and r["cadence"] is None and r["next"] is None


def test_only_money_in(client):
    load(client.st, row(25, "COFFEE", merchant="Coffee"))
    t = client.st.all_transactions()[0]
    assert client.get(f"/api/transactions/{t.fingerprint}/paydays").status_code == 400
    assert client.get("/api/transactions/nope/paydays").status_code == 404


def test_no_route_shadows_another(client):
    """The first try at this endpoint took /deposits, which S-12's search
    already had: Flask kept one and the other's callers got the wrong reply."""
    seen: dict[tuple, str] = {}
    for r in client.application.url_map.iter_rules():
        for m in r.methods - {"HEAD", "OPTIONS"}:
            key = (r.rule, m)
            assert key not in seen, (key, seen.get(key), r.endpoint)
            seen[key] = r.endpoint
