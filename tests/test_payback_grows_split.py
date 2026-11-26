"""A second payback on a purchase the first one split (product owner,
2026-11-25).

"I spent $120 on Uber Eats and split it with Denise and Anastasia. Denise
owed me $58 and Anastasia $19. I didn't mark the split on Uber Eats; I
selected Denise's e-Transfer and said it paid back Uber Eats. When I went
to select Anastasia's to also pay back Uber Eats, it didn't show up."

Denise's payback split Uber Eats with Denise alone (THL-260, a split made
by paybacks). Such a split grows with each payback (`sp.add_payer`), so
Anastasia's payback lists it under OTHER PURCHASES, as far as her own
share goes, and linking it puts Anastasia on it. A split she set up
herself still isn't offered, and never gains someone from a payback.

Demo data only, through the endpoints the app calls.
"""

from __future__ import annotations

from datetime import date, timedelta

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()


def day(n: int) -> str:
    return max(TODAY - timedelta(days=n), TODAY.replace(day=1)).isoformat()


def row(desc, amount, account="chq", when=None, merchant=None, category="", kind="depository"):
    return Transaction(date=when or day(3), description=desc, merchant=merchant or desc, amount=amount,
                       category=category, account_id=account, account_name=account, raw={"account_type": kind})


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "grows.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def ok(r):
    assert r.status_code in (200, 201), r.get_json()
    return r.get_json()


def add(c, account, *rows):
    ingest(c.st, IngestResult(list(rows), account))
    return {t.description: t.fingerprint for t in c.st.all_transactions()}


def setup(c):
    i = add(c, "amex", row("UBER EATS", 120.0, "amex", when=day(5), merchant="Uber Eats", category="Dining",
                           kind="credit"))
    j = add(c, "chq",
            row("INTERAC E-TRANSFER FROM DENISE MORAN", -58.0, when=day(2), merchant="Denise Moran"),
            row("INTERAC E-TRANSFER FROM ANASTASIA PAPAS", -19.0, when=day(1), merchant="Anastasia Papas"))
    return (i["UBER EATS"], j["INTERAC E-TRANSFER FROM DENISE MORAN"],
            j["INTERAC E-TRANSFER FROM ANASTASIA PAPAS"])


def owing(c, dep, person):
    return ok(c.get(f"/api/transactions/{dep}/owing", query_string={"person": person}))


def pay(c, dep, charge, person, amount):
    return c.post(f"/api/transactions/{dep}/parts", json={"parts": [
        {"kind": "payback", "charge": charge, "amount": amount, "person": person, "new_split": True}]})


def people(c, cid):
    s = ok(c.get(f"/api/transactions/{cid}"))["splitting"]
    return {p["name"]: (p["amount"], p["paid"], p["owes"]) for p in s["people"]}, s["you"]


def test_the_second_payback_finds_the_purchase(client):
    uber, denise, ana = setup(client)
    ok(pay(client, denise, uber, "Denise Moran", 58.0))
    listed = {r["id"]: r for r in owing(client, ana, "Anastasia Papas")["unsplit"]}
    assert uber in listed
    # As far as her own share goes: $120.00 less Denise's $58.00.
    assert listed[uber]["max"] == 62.0


def test_and_links_to_it(client):
    uber, denise, ana = setup(client)
    ok(pay(client, denise, uber, "Denise Moran", 58.0))
    ok(pay(client, ana, uber, "Anastasia Papas", 19.0))
    who, you = people(client, uber)
    assert who == {"Denise Moran": (58.0, 58.0, 0.0), "Anastasia Papas": (19.0, 19.0, 0.0)}
    assert you == 43.0
    assert [(p["kind"], p["detail"]["charge"]) for p in client.st.parts()[ana]] == [("payback", uber)]


def test_undo_takes_only_the_second_off(client):
    uber, denise, ana = setup(client)
    ok(pay(client, denise, uber, "Denise Moran", 58.0))
    undo = ok(pay(client, ana, uber, "Anastasia Papas", 19.0))["undo"]
    ok(client.post("/api/transactions/undo", json=undo))
    who, you = people(client, uber)
    assert who == {"Denise Moran": (58.0, 58.0, 0.0)} and you == 62.0
    assert not client.st.parts().get(ana)


def test_no_more_than_her_share_is_left(client):
    uber, denise, ana = setup(client)
    ok(pay(client, denise, uber, "Denise Moran", 58.0))
    before = people(client, uber)
    r = pay(client, ana, uber, "Anastasia Papas", 62.01)
    assert r.status_code == 400
    assert r.get_json()["error"] == "Your share of Uber Eats is $62.00. Make it $62.00 or less."
    assert people(client, uber) == before


def test_a_split_she_set_up_is_still_not_offered(client):
    uber, denise, ana = setup(client)
    ok(client.put(f"/api/transactions/{uber}/split", json={
        "mode": "amount", "people": [{"name": "Denise Moran", "amount": 58.0}]}))
    assert uber not in {r["id"] for r in owing(client, ana, "Anastasia Papas")["unsplit"]}
    r = pay(client, ana, uber, "Anastasia Papas", 19.0)
    assert r.status_code == 400
    assert r.get_json()["error"] == "Uber Eats is already split. Pick a share on it instead."


def test_nothing_of_hers_left_is_not_offered(client):
    uber, denise, ana = setup(client)
    i = add(client, "chq", row("INTERAC E-TRANSFER FROM DENISE MORAN #2", -120.0, when=day(2),
                               merchant="Denise Moran"))
    ok(pay(client, i["INTERAC E-TRANSFER FROM DENISE MORAN #2"], uber, "Denise Moran", 120.0))
    assert uber not in {r["id"] for r in owing(client, ana, "Anastasia Papas")["unsplit"]}


def test_the_app_caps_it_at_her_share():
    from pathlib import Path
    src = (Path(__file__).resolve().parents[1] / "ios/Pearl/Views/Transactions/PartsFlow.swift").read_text()
    row = src[src.index("struct UnsplitRow"):src.index("struct MineRow")]
    assert "var max: Double? = nil" in row and "var room: Double { Swift.min(max ?? amount, amount) }" in row
    # Only the "split" line compares with the whole; every cap is her share.
    assert src.count("cents(u.amount)") == 1 and "let shared = cents(u.room) < cents(u.amount)" in src
    assert '" · \\(Format.amount(u.amount)) split"' in src
