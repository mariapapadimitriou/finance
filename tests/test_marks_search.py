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


def _et(desc, original, amount=-18.2, date="2026-10-16"):
    return Transaction(date=date, merchant=desc, amount=amount, category="Transfers",
                       description=desc, account_id="chq",
                       raw={"original_description": original, "account_type": "depository"})


def test_the_message_on_an_e_transfer_is_read_out_of_the_banks_wording():
    from finance.etransfers import memo
    assert memo(_et("E-transfer From Denise Rao", "INTERAC E-TRANSFER FROM DENISE RAO UBER EATS")) == "uber eats"
    assert memo(_et("E-transfer From Denise Rao", "E-TRANSFER RECEIVED DENISE RAO MEMO: sushi thursday")) == "sushi thursday"
    assert memo(_et("E-transfer From Denise Rao", "INTERAC E-TRANSFER ***Q7K1 DENISE RAO")) is None
    assert memo(_et("E-transfer From Denise Rao", "")) is None              # the bank passed nothing on


def test_the_message_names_the_purchase_it_pays_back():
    from finance.marks import memo_match
    inflow = _et("E-transfer From Denise Rao", "INTERAC E-TRANSFER FROM DENISE RAO UBER EATS")
    uber = _t("u", "2026-10-14", "Uber Eats", 54.6, category="Food Delivery")
    older = _t("o", "2026-09-01", "Uber Eats", 30.0, category="Food Delivery")
    ride = _t("r", "2026-10-15", "Uber Trip", 19.1, category="Transport")
    hit = memo_match(inflow, [inflow, uber, older, ride])
    assert hit["id"] == uber.fingerprint and hit["memo"] is True      # closest before, both words
    paid = _t("u", "2026-10-14", "Uber Eats", 54.6, category="Food Delivery", paid_back=54.6)
    assert memo_match(inflow, [inflow, paid]) is None                  # nothing left to pay back
    assert memo_match(_et("E-transfer From Denise Rao", "INTERAC E-TRANSFER DENISE RAO"), [uber]) is None


def test_needs_a_look_asks_about_the_purchase_the_message_names():
    from finance.review import build
    inflow = _et("E-transfer From Denise Rao", "INTERAC E-TRANSFER FROM DENISE RAO UBER EATS")
    uber = _t("u", "2026-10-14", "Uber Eats", 54.6, category="Food Delivery")
    body = build([inflow, uber], today="2026-10-21")
    item = next(i for i in body["money_in"] if i["txn"]["id"] == inflow.fingerprint)
    assert item["guess"]["action"] == "memo" and item["guess"]["charge"]["id"] == uber.fingerprint
    assert item["txn"]["memo"] == "uber eats"
    assert "uber eats" in item["reason"]
