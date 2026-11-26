"""The money out of her account into a joint one opens, before Pearl has
sorted the joint end (an account marked joint after the money came in) (2026-11-25): its other end was described lazily, and
copying it for "Transfer between your accounts" raised a TypeError."""

from datetime import date, timedelta

from finance.ingest.base import IngestResult
from finance.models import Transaction
from finance.pipeline import ingest


def test_both_ends_open_before_the_ledger_is_sorted(tmp_path):
    from app import create_app
    app = create_app(str(tmp_path / "j.db"))
    app.config.update(TESTING=True)
    st = app.config["STORE"]
    day = lambda n: (date.today() - timedelta(days=n)).isoformat()
    for acct, amount, n, kind in (("chq", 250.0, 3, "TRANSFER_OUT_ACCOUNT_TRANSFER"),
                                  ("joint", -250.0, 2, "TRANSFER_IN_ACCOUNT_TRANSFER")):
        ingest(st, IngestResult([Transaction(date=day(n), description="INTERNET TRANSFER", amount=amount,
                                             account_id=acct, account_name=acct,
                                             raw={"account_type": "depository", "issuer_category": kind})], acct))
    # Marked joint after the money came in, as when she sets an account up.
    st.set_joint("joint", "Sister")
    with st.conn() as c:
        c.execute("UPDATE joint_accounts SET share = 50, people = ? WHERE account_id = 'joint'", ('["Sister"]',))
    ids = {t.account_id: t.fingerprint for t in st.all_transactions()}
    with app.test_client() as c:
        for acct in ("chq", "joint"):
            r = c.get(f"/api/transactions/{ids[acct]}")
            assert r.status_code == 200, (acct, r.status_code)
            assert r.get_json()["transfer"], acct
