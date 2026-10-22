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


def test_plaid_payment_meta_names_the_sender_and_carries_the_message():
    """2026-10-22: payment_meta.payer is who sent money in, payee who was
    paid, and reason "the payer-supplied description" — the message."""
    from finance.ingest.plaid_source import map_plaid_transaction
    from finance.etransfers import memo, party
    item = {"date": "2026-10-19", "amount": -31.2, "account_id": "chq",
            "name": "E-TRANSFER ***Q7k", "merchant_name": None,
            "original_description": "E-TRANSFER ***Q7k",
            "payment_meta": {"payer": "DENISE RAO", "reason": "uber eats", "payee": None}}
    t = map_plaid_transaction(item, {"chq": {"name": "Chequing", "type": "depository"}})
    assert t.raw["payer"] == "DENISE RAO" and t.raw["reason"] == "uber eats"
    assert party(t) == {"direction": "from", "name": "Denise Rao", "named_by": "bank"}
    assert memo(t) == "uber eats"
    out = map_plaid_transaction({**item, "amount": 40.0,
                                 "payment_meta": {"payee": "Sam Lee"}},
                                {"chq": {"name": "Chequing", "type": "depository"}})
    assert party(out)["name"] == "Sam Lee" and party(out)["direction"] == "to"


def test_etransfer_names_are_clean_for_rules():
    """2026-10-22: "INTERAC E-TRF FROM DENISE RAO" is Denise Rao, as a
    merchant and as a remembered destination; a bare reference is nothing."""
    from finance.models import Transaction, normalize_merchant
    from finance.transfers import destination
    assert normalize_merchant("INTERAC E-TRF FROM DENISE RAO") == "Denise Rao"
    assert normalize_merchant("INTERAC E-TRANSFER RECEIVED PRIYA SHAH") == "Priya Shah"
    t = Transaction(date="2026-10-19", description="INTERAC E-TRF FROM DENISE RAO", amount=45, account_id="a")
    assert destination(t) == ("name:denise rao", "Denise Rao")
    bare = Transaction(date="2026-10-18", description="SEND E-TFR ***Ab9", amount=250, account_id="a")
    assert destination(bare) is None


def test_details_refresh_fills_in_sender_message_and_wording_only(tmp_path):
    """2026-10-22: rows stored before Pearl read payment_meta get the sender,
    message and bank's wording from Plaid once; nothing she decided moves."""
    from app import create_app
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    from finance.plaid_link import detail_fields
    from finance.etransfers import memo, party
    st = create_app(str(tmp_path / "d.db")).config["STORE"]
    t = Transaction(date="2026-10-19", description="E-TRANSFER ***Q7k", amount=-31.2,
                    account_id="chq", account_name="TD", source="plaid",
                    raw={"plaid_id": "p1", "account_type": "depository"})
    ingest(st, IngestResult(transactions=[t], account_id="chq"))
    fp = st.all_transactions()[0].fingerprint
    st.set_transaction_category(fp, "Lent")
    plaid_item = {"transaction_id": "p1", "name": "E-TRANSFER ***Q7k",
                  "original_description": "E-TRANSFER ***Q7k DENISE RAO uber eats",
                  "payment_meta": {"payer": "DENISE RAO", "reason": "uber eats"}}
    assert st.merge_plaid_details({"p1": detail_fields(plaid_item), "nope": {"payer": "X"}}) == 1
    row = st.all_transactions()[0]
    assert row.raw["payer"] == "DENISE RAO" and row.raw["reason"] == "uber eats"
    assert row.raw["plaid_id"] == "p1" and row.category == "Lent"     # hers, kept
    assert party(row)["name"] == "Denise Rao" and memo(row) == "uber eats"
    assert st.merge_plaid_details({"p1": detail_fields(plaid_item)}) == 0   # once is enough


def test_the_panel_shows_what_the_bank_sent(client=None):
    from finance.models import Transaction
    from finance.txlist import _bank_text
    t = Transaction(date="2026-10-19", description="E-TRANSFER ***Q7k", amount=-31.2, account_id="a",
                    raw={"original_description": "E-TRANSFER ***Q7k   DENISE RAO"})
    assert _bank_text(t) == "E-TRANSFER ***Q7k DENISE RAO"
    same = Transaction(date="2026-10-19", description="UBER EATS", amount=12, account_id="a",
                       raw={"original_description": "uber  eats"})
    assert _bank_text(same) == ""


def test_refresh_runs_once_per_bank_and_pages_through(tmp_path, monkeypatch):
    from app import create_app
    from finance import plaid_link
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    st = create_app(str(tmp_path / "r.db")).config["STORE"]
    rows = [Transaction(date="2026-10-1%d" % i, description=f"E-TRANSFER ***{i}", amount=-10 - i,
                        account_id="chq", account_name="TD", source="plaid",
                        raw={"plaid_id": f"p{i}", "account_type": "depository"}) for i in range(3)]
    ingest(st, IngestResult(transactions=rows, account_id="chq"))
    calls = []

    class Resp:
        def __init__(self, d): self.d = d
        def to_dict(self): return self.d

    class Client:
        def transactions_get(self, req):
            off = req.options.offset
            calls.append(off)
            page = [{"transaction_id": f"p{i}", "payment_meta": {"payer": f"Friend {i}"}}
                    for i in range(3)][off:off + 2]
            return Resp({"transactions": page, "total_transactions": 3})

    monkeypatch.setattr(plaid_link, "_client", lambda: Client())
    monkeypatch.setattr(st, "plaid_token", lambda item_id: "tok")
    items = [{"item_id": "item-td"}]
    assert plaid_link.refresh_details_once(st, items) == 3
    assert calls == [0, 2]                                        # paged
    assert {t.raw.get("payer") for t in st.all_transactions()} == {"Friend 0", "Friend 1", "Friend 2"}
    assert plaid_link.refresh_details_once(st, items) == 0 and calls == [0, 2]   # once per bank

    def boom(*a, **k): raise RuntimeError("down")
    monkeypatch.setattr(plaid_link, "refresh_details", boom)
    assert plaid_link.refresh_details_once(st, [{"item_id": "item-rbc"}]) == 0
    assert "item-rbc" not in st.setting(plaid_link.DETAILS_KEY)     # tried again next sync


def test_row_says_when_the_bank_sent_no_name(tmp_path):
    from app import create_app
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    app = create_app(str(tmp_path / "n.db")); st = app.config["STORE"]
    ingest(st, IngestResult(transactions=[Transaction(
        date="2026-10-21", description="E-TRANSFER ***Q7k", amount=-31.2, account_id="td",
        account_name="TD", source="plaid", raw={"plaid_id": "a1", "account_type": "depository"})],
        account_id="td"))
    with app.test_client() as c:
        tid = st.all_transactions()[0].fingerprint
        r = c.get(f"/api/transactions/{tid}").get_json()
        assert r["bank_sender_missing"] is True and r["bank_sender"] == ""
        st.merge_plaid_details({"a1": {"payer": "DENISE RAO"}})
        r = c.get(f"/api/transactions/{tid}").get_json()
        assert r["bank_sender"] == "DENISE RAO" and r["bank_sender_missing"] is False


def test_what_your_bank_sent_lists_every_field(tmp_path):
    from app import create_app
    from finance.ingest.base import IngestResult
    from finance.models import Transaction
    from finance.pipeline import ingest
    app = create_app(str(tmp_path / "w.db")); st = app.config["STORE"]
    ingest(st, IngestResult(transactions=[
        Transaction(date="2026-10-21", description="E-TRANSFER ***Q7k", amount=-31.2, account_id="td",
                    account_name="TD", source="plaid", raw={"plaid_id": "a1", "account_type": "depository",
                                                            "issuer_category": "TRANSFER_IN_ACCOUNT_TRANSFER"}),
        Transaction(date="2026-10-20", description="CORNER BAKERY", amount=12, account_id="manual",
                    account_name="Added by hand", source="manual")], account_id="td"))
    with app.test_client() as c:
        by = {t.description: t.fingerprint for t in st.all_transactions()}
        fields = c.get(f"/api/transactions/{by['E-TRANSFER ***Q7k']}").get_json()["bank_fields"]
        got = {f["label"]: f["value"] for f in fields}
        assert got["Sender"] == "Not sent" and got["Message"] == "Not sent"
        assert got["Plaid’s name"] == "E-TRANSFER ***Q7k"
        assert got["Plaid’s category"] == "TRANSFER_IN_ACCOUNT_TRANSFER"
        assert c.get(f"/api/transactions/{by['CORNER BAKERY']}").get_json()["bank_fields"] == []


def test_a_recent_sync_still_runs_the_one_time_refresh(tmp_path, monkeypatch):
    from app import create_app
    from finance import plaid_link
    app = create_app(str(tmp_path / "s.db")); st = app.config["STORE"]
    ran = []
    monkeypatch.setattr(plaid_link, "configured", lambda: True)
    monkeypatch.setattr(plaid_link, "synced_recently", lambda store: True)
    monkeypatch.setattr(plaid_link, "refresh_details_once", lambda store, items: ran.append(1) or 7)
    with app.test_client() as c:
        r = c.post("/api/plaid/sync", json={}).get_json()
    assert r["recent"] is True and r["details_refreshed"] == 7 and ran == [1]
