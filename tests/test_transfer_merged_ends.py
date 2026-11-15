"""A transfer she marked stays findable under an account filter (2026-11-15).

The list merges a transfer between two of her accounts into one line, the
departure's row (collapse_transfers). The phone filters the month by account
itself, so filtered to the arrival's account the line was filtered out and
the arrival, merged into it, was nowhere. The list now sends each merged
arrival in `merged`, naming its line, for the phone to show where the line
isn't (ios/Pearl/Views/Transactions/TransferEnds.swift). Demo data only."""

from __future__ import annotations

from datetime import date

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

TODAY = date.today()
MONTH = TODAY.isoformat()[:7]


def on(d):
    return f"{MONTH}-{d:02d}"


def row(amount, description, account, when, category=None, kind="depository"):
    t = Transaction(date=when, description=description, amount=amount,
                    account_id=account, account_name=account,
                    raw={"account_type": kind, "issuer_category": ""})
    if category:
        t.category, t.category_source = category, "user"
    return t


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "ends.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def load(st, *rows):
    by: dict[str, list] = {}
    for r in rows:
        by.setdefault(r.account_id, []).append(r)
    for acct, txns in by.items():
        ingest(st, IngestResult(transactions=txns, account_id=acct))
    return {t.description: t.fingerprint for t in st.all_transactions()}


def listing(c, **params):
    params.setdefault("month", MONTH)
    res = c.get("/api/transactions/list", query_string=params)
    assert res.status_code == 200, res.get_json()
    return res.get_json()


@pytest.fixture()
def pair(client):
    """$500 out of chequing on the 1st, into savings on the 2nd; the arrival
    she marked a transfer herself."""
    ids = load(client.st,
               row(500, "TFR-TO 2210", "chq", on(1), category="Transfers"),
               row(-500, "TFR-FR 4417", "sav", on(2)),
               row(40, "GROCER", "chq", on(2), category="Groceries"))
    client.st.set_transaction_category(ids["TFR-FR 4417"], "Transfers")
    return ids


def test_the_merged_arrival_is_sent_with_its_line(client, pair):
    data = listing(client)
    shown = {r["id"]: r for r in data["transactions"]}
    # Today's single line, unchanged.
    assert pair["TFR-FR 4417"] not in shown
    line = shown[pair["TFR-TO 2210"]]
    assert line["transfer"]["from"] == "chq" and line["transfer"]["to"] == "sav"
    assert data["total"] == 2
    # The arrival, as its own row would be: its account, its date, money in.
    [end] = data["merged"]
    assert end["id"] == pair["TFR-FR 4417"] and end["merged_into"] == pair["TFR-TO 2210"]
    assert end["account_id"] == "sav" and end["date"] == on(2) and end["inflow"] is True
    assert end["counts"] == "none" and end["chip"]["label"] == "Transfer"
    assert "rule" in end    # described as the list's rows are


def test_tapping_the_arrival_shows_both_ends(client, pair):
    d = client.get(f"/api/transactions/{pair['TFR-FR 4417']}").get_json()
    assert d["transfer"]["from"] == "chq" and d["transfer"]["to"] == "sav"
    assert d["transfer"]["other_id"] == pair["TFR-TO 2210"]


def test_only_the_lines_on_the_page(client, pair):
    # Newest first: GROCER and the arrival are on the 2nd, the line on the 1st.
    first = listing(client, limit=1)
    assert [r["id"] for r in first["transactions"]] == [pair["GROCER"]]
    assert first["merged"] == []
    second = listing(client, limit=1, offset=1)
    assert [r["merged_into"] for r in second["merged"]] == [pair["TFR-TO 2210"]]


def test_nothing_merged_nothing_sent(client):
    load(client.st, row(300, "E-TRANSFER SENT", "chq", on(3)),
         row(40, "GROCER", "chq", on(3), category="Groceries"))
    assert listing(client)["merged"] == []


def test_a_server_filter_keeps_its_end_as_before(client, pair):
    # Filtered on the server (the web's account filter, a search, a day),
    # only one end is chosen: it stays as itself, and nothing is merged.
    sav = listing(client, account="sav")
    assert [r["id"] for r in sav["transactions"]] == [pair["TFR-FR 4417"]]
    assert sav["merged"] == []
    day = listing(client, day=on(2))
    assert pair["TFR-FR 4417"] in {r["id"] for r in day["transactions"]}


def test_by_merchant_sends_no_rows(client, pair):
    assert listing(client, by="merchant")["merged"] == []
