"""Fewer taps, the transaction page and sorting (PR B; Pearl redesign canvas
v100: P2, P3, P4, P9, P10, P14, P15). The server half of P9 (I pay this every
month sends the fields she could change, and its key is the Undo), and
source checks for the words and the one-tap paths the boards draw."""

from __future__ import annotations

import re
import sys
from datetime import date, timedelta
from pathlib import Path

import pytest

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest

sys.path.insert(0, "tests")
IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl" / "Views"


def src(rel: str) -> str:
    return (IOS / rel).read_text()


@pytest.fixture()
def client(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "page.db"))
    app.config.update(TESTING=True)
    with app.test_client() as c:
        c.st = app.config["STORE"]
        yield c


def _equinox(client) -> str:
    when = (date.today() - timedelta(days=3)).isoformat()
    ingest(client.st, IngestResult(transactions=[Transaction(
        date=when, description="EQUINOX 0042", amount=215.0, account_id="card", account_name="card",
        merchant="Equinox", raw={"account_type": "credit"})], account_id="card"))
    return next(t.fingerprint for t in client.st.all_transactions() if t.description == "EQUINOX 0042")


# ── P9: I pay this every month ───────────────────────────────────────────

def test_i_pay_this_every_month_keeps_what_she_changed_and_undoes(client):
    tid = _equinox(client)
    got = client.get(f"/api/transactions/{tid}/bill").get_json()
    assert got["bill_key"] is None and got["name"] == "Equinox"
    r = client.post(f"/api/transactions/{tid}/bill", json={
        "cadence": "monthly", "next": got["next"], "share": 100, "category": got["category"],
        "name": "Gym", "amount": 199.5, "varies": True})
    assert r.status_code == 200, r.get_json()
    key = r.get_json()["key"]
    bills = client.get("/api/income-bills").get_json()
    rows = [b for b in bills["bills"] if b["key"] == key]
    assert rows and rows[0]["name"] == "Gym" and rows[0]["amount"] == pytest.approx(199.5) and rows[0]["varies"]
    # The page's pill: the merchant is on a bill now.
    assert client.get(f"/api/transactions/{tid}/bill").get_json()["bill_key"] == key
    # The toast's Undo.
    assert client.delete(f"/api/income-bills/bills/{key}").status_code == 200
    assert client.get(f"/api/transactions/{tid}/bill").get_json()["bill_key"] is None


def test_a_bill_with_a_bad_amount_is_refused(client):
    tid = _equinox(client)
    got = client.get(f"/api/transactions/{tid}/bill").get_json()
    r = client.post(f"/api/transactions/{tid}/bill", json={
        "cadence": "monthly", "next": got["next"], "share": 100, "category": got["category"], "amount": "lots"})
    assert r.status_code == 400


def test_without_the_new_fields_the_bill_is_the_purchase(client):
    tid = _equinox(client)
    got = client.get(f"/api/transactions/{tid}/bill").get_json()
    r = client.post(f"/api/transactions/{tid}/bill", json={
        "cadence": "monthly", "next": got["next"], "share": 100, "category": got["category"]})
    assert r.status_code == 200
    assert "Equinox" in r.get_json()["title"]


# ── The page (P2, P14, P10) ──────────────────────────────────────────────

def test_a_purchase_page_is_amount_category_split_and_more():
    tdv = src("Transactions/TransactionDetailView.swift")
    page = tdv[tdv.index("private var page: some View"):tdv.index("/// What was this? and the money-in questions.")]
    assert "OwnBody { splitRow }" in page and "OwnBody { moreRow }" in page
    assert "OwnBody { options }" not in page
    for words in ("Someone paid me back", "I pay this every month", "Moved between my accounts",
                  "Leave it out of your usual month", "Add a note"):
        assert words in tdv, words
    for gone in ('"Mark as paid back"', '"Link to another transfer"', '"Exclude from usual month"',
                 '"Always for this merchant"'):
        assert gone not in tdv, gone


def test_one_off_toasts_plainly_with_undo_and_shows_a_pill():
    tdv = src("Transactions/TransactionDetailView.swift")
    assert '"One-off. Your usual month stays the same."' in tdv
    assert 'CFPill(text: "One-off")' in tdv
    assert '"Every month · around the \\(ordinal(' in tdv


def test_a_category_change_has_undo_and_undo_has_none():
    tdv = src("Transactions/TransactionDetailView.swift")
    assert '"\\(merchant) is \\(name) now."' in tdv
    assert '"Undone. \\(merchant) is \\(was) again."' in tdv
    assert "say(said, undo: nil)" in tdv


# ── Sorting (P3, P4) ─────────────────────────────────────────────────────

def test_no_real_guess_shows_four_tiles_not_other():
    tdv = src("Transactions/TransactionDetailView.swift")
    assert 'guessName == "Other"' in tdv and "OwnBody { tilesCard }" in tdv
    cat = src("Transactions/CategorySheet.swift")
    assert 'guess.flatMap { $0 == "Other" ? nil : $0 }' in cat
    review = src("Review/ReviewView.swift")
    assert "opensPage(accounts) && !$0.guessesOther" in review


def test_quick_sort_tiles_answer_at_once_and_undo_is_a_toast():
    qs = src("Review/QuickSortView.swift")
    assert "if tilesOnCard(ask)" in qs and "OwnBody { cardTiles(ask) }" in qs
    assert "OwnBody { undoToast }" in qs
    assert "undoButton" not in qs
    assert '"\\(ask.t.name) is \\(name)."' in qs


# ── P15: one picker ──────────────────────────────────────────────────────

def test_the_category_picker_has_search_most_used_and_plain_groups():
    cat = src("Transactions/CategorySheet.swift")
    for words in ('"Search categories"', 'groupLabel("Most used")', '"All categories"', '"Everyday"',
                  '"Fun and treats"', '"Not really spending"', '"I lent it to someone"', '"Paying off a loan"',
                  '"Someone else’s purchase"', '"Paid off my card"', '"Someone pays you back for it"'):
        assert words in cat, words
    assert '"Essentials"' not in cat and '"Lifestyle"' not in cat
    assert re.search(r"prefix\(8\)", cat)
