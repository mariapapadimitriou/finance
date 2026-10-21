"""Searching any purchase an e-Transfer could pay back (2026-10-21)."""
from finance.models import Transaction
from finance.marks import search_charges


def _t(fp, date, merchant, amount, category="Dining", paid_back=None, description=None):
    # The fingerprint is derived, so each row gets a distinct description.
    return Transaction(date=date, merchant=merchant, amount=amount, category=category,
                       description=f"{description or merchant} {fp}", account_id="a",
                       paid_back=paid_back)


def test_search_finds_any_purchase_by_name_or_amount_with_what_is_left():
    inflow = _t("in", "2026-10-20", "e-Transfer from Denise", -18.0, category="Transfers")
    uber = _t("u", "2026-10-17", "Uber Eats", 54.0, paid_back=18.0)
    txns = [inflow, uber,
            _t("g", "2026-10-16", "Trader Joe's", 82.53, category="Groceries"),
            _t("old", "2026-03-01", "Uber Eats", 30.0),
            _t("tr", "2026-10-15", "Transfer", 200.0, category="Transfers")]
    ids = {x.fingerprint: fp for x, fp in zip(txns, ["in", "u", "g", "old", "tr"])}
    by_name = search_charges(inflow, txns, "uber")
    assert [ids[r["id"]] for r in by_name] == ["u"]
    assert by_name[0]["left"] == 36.0 and by_name[0]["paid_back"] == 18.0
    by_amount = search_charges(inflow, txns, "82.53")
    assert [ids[r["id"]] for r in by_amount] == ["g"]
    everything = search_charges(inflow, txns)
    assert [ids[r["id"]] for r in everything] == ["u", "g"]          # newest first, no transfers


def test_search_uses_her_name_for_a_merchant():
    inflow = _t("in", "2026-10-20", "e-Transfer from Ana", -20.0, category="Transfers")
    txns = [inflow, _t("d", "2026-10-18", "SQ *NOPA SF", 80.0)]
    assert search_charges(inflow, txns, "nopa", names={"sq *nopa sf": "Nopa"})[0]["merchant"] == "Nopa"
    assert search_charges(inflow, txns, "zzz") == []
