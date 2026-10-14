"""The Plaid link and sync flow, against a stand-in for Plaid itself.

Nothing here talks to Plaid. What is worth testing is ours: that the access
token is encrypted before it is stored and never serialised back out, that the
cursor only advances over rows that landed, and that a pending charge which
posts doesn't end up in the ledger twice.
"""

import json

import pytest

from app import create_app
from finance import plaid_link, secrets_box
from finance.store import Store

KEY = "unit-test-key-that-is-definitely-long-enough"


@pytest.fixture(autouse=True)
def _encryption(monkeypatch):
    monkeypatch.setenv(secrets_box.KEY_ENV, KEY)


@pytest.fixture()
def store(tmp_path):
    return Store(str(tmp_path / "t.db"))


# ── A stand-in for Plaid ─────────────────────────────────────────────────────

def txn(tid, date, name, amount, account="acc1"):
    return {"transaction_id": tid, "date": date, "name": name, "amount": amount,
            "account_id": account, "iso_currency_code": "CAD",
            "personal_finance_category": {"primary": "FOOD_AND_DRINK"}}


ACCOUNTS = [{"account_id": "acc1", "name": "TD Cash Back Visa", "mask": "4321",
             "type": "credit", "subtype": "credit card"}]

# What linking a bank actually hands over: the card, plus everything else the
# institution holds.
MIXED_ACCOUNTS = ACCOUNTS + [
    {"account_id": "chq", "name": "TD Everyday Chequing", "mask": "1111",
     "type": "depository", "subtype": "checking"},
    {"account_id": "sav", "name": "TD Savings", "mask": "2222",
     "type": "depository", "subtype": "savings"},
    {"account_id": "inv", "name": "Wealthsimple TFSA", "mask": "3333",
     "type": "investment", "subtype": "tfsa"},
]


def _as_dict(request):
    """Plaid's generated models are not mappings; they do expose to_dict()."""
    return request.to_dict()


class FakePlaid:
    """Returns scripted /transactions/sync pages, and records what it was asked."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self.removed_items = []
        self.link_requests = []
        # What /accounts/get lists; None stands for Plaid not answering.
        self.item_accounts = None

    def transactions_sync(self, request):
        self.calls.append(_as_dict(request))
        page = self.pages.pop(0)
        return _Resp({"accounts": ACCOUNTS, "added": [], "modified": [],
                      "removed": [], "has_more": False, **page})

    def accounts_get(self, request):
        if self.item_accounts is None:
            raise RuntimeError("accounts/get unavailable")
        return _Resp({"accounts": self.item_accounts})

    def item_public_token_exchange(self, request):
        return _Resp({"item_id": "item-1", "access_token": "access-secret-xyz"})

    def item_remove(self, request):
        self.removed_items.append(_as_dict(request))
        return _Resp({"removed": True})

    def link_token_create(self, request):
        self.link_requests.append(_as_dict(request))
        return _Resp({"link_token": "link-sandbox-123", "expiration": "2026-01-01"})


class _Resp:
    def __init__(self, payload):
        self._payload = payload

    def to_dict(self):
        return self._payload


@pytest.fixture()
def fake(monkeypatch):
    def install(pages):
        client = FakePlaid(pages)
        monkeypatch.setattr(plaid_link, "_client", lambda: client)
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        return client
    return install


# ── Token handling ───────────────────────────────────────────────────────────

class TestTokenStorage:
    def test_the_token_is_encrypted_at_rest(self, store):
        store.add_plaid_item("item-1", "access-secret-xyz", "TD")
        with store.conn() as c:
            # By name, not by index: sqlite3.Row allows both, psycopg's dict
            # rows only the name, and this suite runs against both.
            raw = c.execute(
                "SELECT access_token FROM plaid_items").fetchone()["access_token"]
        assert "access-secret-xyz" not in raw
        assert store.plaid_token("item-1") == "access-secret-xyz"

    def test_listing_items_never_exposes_the_token(self, store):
        store.add_plaid_item("item-1", "access-secret-xyz", "TD")
        blob = json.dumps(store.plaid_items())
        assert "access_token" not in blob
        assert "access-secret-xyz" not in blob

    def test_a_tampered_ciphertext_is_rejected_not_decrypted(self, store):
        from cryptography.fernet import InvalidToken
        store.add_plaid_item("item-1", "access-secret-xyz", "TD")
        with store.conn() as c:
            c.execute("UPDATE plaid_items SET access_token = ? WHERE item_id = ?",
                      (secrets_box.encrypt("someone-elses-token")[:-4] + "AAAA",
                       "item-1"))
        with pytest.raises(InvalidToken):
            store.plaid_token("item-1")

    def test_without_a_key_nothing_is_stored_in_the_clear(self, store, monkeypatch):
        monkeypatch.delenv(secrets_box.KEY_ENV, raising=False)
        with pytest.raises(secrets_box.SecretsUnavailable):
            store.add_plaid_item("item-2", "access-secret-xyz", "TD")

    def test_a_short_key_is_refused_rather_than_stretched(self, monkeypatch):
        monkeypatch.setenv(secrets_box.KEY_ENV, "tooshort")
        assert secrets_box.available() is False


# ── Syncing ──────────────────────────────────────────────────────────────────

class TestSync:
    def test_a_first_sync_sends_no_cursor_and_imports(self, store, fake):
        client = fake([{"added": [txn("t1", "2026-01-05", "MOS MOS COFFEE", 6.40)],
                        "next_cursor": "cur-1"}])
        store.add_plaid_item("item-1", "tok", "TD")

        out = plaid_link.sync_all(store)
        assert "cursor" not in client.calls[0]
        assert out["imported"] == 1
        assert store.plaid_items()[0]["cursor"] == "cur-1"

    def test_the_next_sync_sends_the_stored_cursor(self, store, fake):
        client = fake([{"added": [txn("t1", "2026-01-05", "COFFEE", 6.40)],
                        "next_cursor": "cur-1"},
                       {"added": [], "next_cursor": "cur-2"}])
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        plaid_link.sync_all(store)
        assert client.calls[1]["cursor"] == "cur-1"

    def test_paging_follows_has_more(self, store, fake):
        client = fake([
            {"added": [txn("t1", "2026-01-05", "A", 1.0)], "has_more": True,
             "next_cursor": "c1"},
            {"added": [txn("t2", "2026-01-06", "B", 2.0)], "has_more": True,
             "next_cursor": "c2"},
            {"added": [txn("t3", "2026-01-07", "C", 3.0)], "has_more": False,
             "next_cursor": "c3"},
        ])
        store.add_plaid_item("item-1", "tok", "TD")
        out = plaid_link.sync_all(store)
        assert len(client.calls) == 3
        assert out["imported"] == 3
        assert store.plaid_items()[0]["cursor"] == "c3"

    def test_a_pending_charge_that_posts_is_not_counted_twice(self, store, fake):
        """Plaid removes the pending row and adds the posted one. An importer
        that only ever added would keep both."""
        fake([{"added": [txn("pending-1", "2026-01-05", "RESTAURANT", 42.00)],
               "next_cursor": "c1"},
              {"removed": [{"transaction_id": "pending-1"}],
               "added": [txn("posted-1", "2026-01-06", "RESTAURANT", 44.50)],
               "next_cursor": "c2"}])
        store.add_plaid_item("item-1", "tok", "TD")

        plaid_link.sync_all(store)
        assert len(store.all_transactions()) == 1

        second = plaid_link.sync_all(store)
        rows = store.all_transactions()
        assert len(rows) == 1, "the pending row should be gone, not kept alongside"
        assert rows[0].amount == 44.50
        assert second["items"][0]["deleted"] == 1

    def test_a_modified_row_replaces_rather_than_duplicates(self, store, fake):
        fake([{"added": [txn("t1", "2026-01-05", "SQ *UNKNOWN", 12.00)],
               "next_cursor": "c1"},
              {"modified": [txn("t1", "2026-01-05", "Blue Bottle Coffee", 12.00)],
               "next_cursor": "c2"}])
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        plaid_link.sync_all(store)
        rows = store.all_transactions()
        assert len(rows) == 1
        assert "Blue Bottle" in rows[0].description

    def test_a_failing_bank_does_not_stop_the_other_one(self, store, monkeypatch):
        """One institution being down must not silently skip the rest."""
        store.add_plaid_item("bad", "tok-a", "TD")
        store.add_plaid_item("good", "tok-b", "Wealthsimple")

        def one(st, item):
            if item["item_id"] == "bad":
                raise RuntimeError("ITEM_LOGIN_REQUIRED")
            return {"item_id": "good", "imported": 3}

        monkeypatch.setattr(plaid_link, "_sync_one", one)
        out = plaid_link.sync_all(store)
        assert out["imported"] == 3
        assert len(out["errors"]) == 1
        # Stored translated, not raw: this string is shown on the Banks tab.
        assert "sign in again" in store.plaid_items()[0]["last_error"].lower()

    def test_the_cursor_does_not_advance_when_a_sync_fails(self, store, fake):
        """A gap would be silent and permanent; a repeat is caught by the
        fingerprint."""
        class Boom(FakePlaid):
            def transactions_sync(self, request):
                raise RuntimeError("500 from Plaid")

        client = Boom([])
        import finance.plaid_link as pl
        original = pl._client
        pl._client = lambda: client
        try:
            store.add_plaid_item("item-1", "tok", "TD")
            store.set_plaid_cursor("item-1", "safe-cursor")
            plaid_link.sync_all(store)
        finally:
            pl._client = original
        assert store.plaid_items()[0]["cursor"] == "safe-cursor"

    def test_nothing_linked_says_so_rather_than_erroring(self, store):
        assert plaid_link.sync_all(store)["items"] == []


class TestUnlink:
    def test_it_revokes_at_plaid_and_forgets_locally(self, store, fake):
        client = fake([])
        store.add_plaid_item("item-1", "tok", "TD")
        assert plaid_link.unlink(store, "item-1") is True
        assert client.removed_items, "should have told Plaid to revoke it"
        assert store.plaid_items() == []

    def test_it_still_forgets_locally_when_plaid_is_unreachable(self, store,
                                                                monkeypatch):
        """Better to lose track of a revocation than to keep a bank token in
        our database because someone else's API was down."""
        class Down(FakePlaid):
            def item_remove(self, request):
                raise RuntimeError("connection refused")

        monkeypatch.setattr(plaid_link, "_client", lambda: Down([]))
        store.add_plaid_item("item-1", "tok", "TD")
        assert plaid_link.unlink(store, "item-1") is False
        assert store.plaid_items() == []


# ── The HTTP surface ─────────────────────────────────────────────────────────

class TestPlaidApi:
    @pytest.fixture()
    def client(self, tmp_path, monkeypatch):
        monkeypatch.delenv("VERCEL", raising=False)
        app = create_app(str(tmp_path / "t.db"))
        app.config.update(TESTING=True)
        return app.test_client()

    def test_items_are_listed_without_tokens(self, client, monkeypatch):
        from finance.api import store as get_store
        r = client.get("/api/plaid/items")
        assert r.status_code == 200
        assert "access_token" not in r.get_data(as_text=True)

    def test_unconfigured_plaid_reports_rather_than_failing(self, client, monkeypatch):
        monkeypatch.setattr(plaid_link, "configured", lambda: False)
        assert client.post("/api/plaid/link-token").status_code == 501
        assert client.post("/api/plaid/sync").status_code == 501

    def test_linking_is_refused_without_an_encryption_key(self, client, monkeypatch):
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        monkeypatch.delenv(secrets_box.KEY_ENV, raising=False)
        r = client.post("/api/plaid/link-token")
        assert r.status_code == 503
        assert "SPENDIE_SECRET_KEY" in r.get_json()["error"]

    def test_exchange_needs_a_public_token(self, client, monkeypatch):
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        assert client.post("/api/plaid/exchange", json={}).status_code == 400

    def test_unlinking_something_that_is_not_linked_is_a_404(self, client):
        assert client.delete("/api/plaid/items/nope").status_code == 404


class TestWhichAccountsSync:
    """Linking a bank hands over chequing, savings and investment accounts too.

    Safe to spend (Pearl E05) needs the cards and the everyday accounts: pay
    and rent move through chequing, and savings is where money set aside goes.
    Card payments and moves between her own accounts are matched as
    transfers, so keeping both ends counts nothing twice. An investment
    account's activity is not spending, so it is skipped by default.
    """

    def _pages(self, fake):
        return fake([{
            "accounts": MIXED_ACCOUNTS,
            "added": [
                txn("t1", "2026-01-05", "MOS MOS COFFEE", 6.40, account="acc1"),
                txn("t2", "2026-01-06", "PAYMENT - THANK YOU", 500.00, account="chq"),
                txn("t3", "2026-01-07", "INTERAC E-TRANSFER", 80.00, account="sav"),
                txn("t4", "2026-01-08", "DIVIDEND", 12.00, account="inv"),
            ],
            "next_cursor": "c1",
        }])

    def test_cards_chequing_and_savings_are_imported(self, store, fake):
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        out = plaid_link.sync_all(store)
        assert out["imported"] == 3
        assert {t.account_id for t in store.all_transactions()} == {"acc1", "chq", "sav"}

    def test_the_skipped_accounts_are_named(self, store, fake):
        """Silently dropping an account would look like a bug."""
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        skipped = plaid_link.sync_all(store)["items"][0]["skipped_accounts"]
        assert "Wealthsimple TFSA ••3333" in skipped
        assert not any("Chequing" in name or "Cash Back Visa" in name for name in skipped)

    def test_cards_only_keeps_just_the_card(self, store, fake):
        self._pages(fake)
        store.set_setting("plaid_cards_only", "1")
        store.add_plaid_item("item-1", "tok", "TD")
        assert plaid_link.sync_all(store)["imported"] == 1

    def test_turning_the_filter_off_imports_everything(self, store, fake):
        self._pages(fake)
        store.set_setting("plaid_cards_only", "0")
        store.add_plaid_item("item-1", "tok", "TD")
        assert plaid_link.sync_all(store)["imported"] == 4

    def test_the_account_type_is_recorded_on_the_row(self, store, fake):
        """Plaid reports the type beside the transactions, not on them; after
        the sync there is nothing left to ask."""
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        row = next(t for t in store.all_transactions() if t.account_id == "acc1")
        assert row.raw["account_type"] == "credit"
        assert row.raw["account_subtype"] == "credit card"


    def test_accounts_quiet_in_the_first_pull_are_still_listed(self, store, fake):
        """The feed names only accounts with transactions in it; a card or
        savings account with none yet comes from /accounts/get, listed and
        synced like any other, so its rows come in as they arrive."""
        client = fake([{"accounts": [MIXED_ACCOUNTS[1]],
                        "added": [txn("t2", "2026-01-06", "COFFEE", 5.0, account="chq")],
                        "next_cursor": "c1"}])
        client.item_accounts = MIXED_ACCOUNTS
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        rules = store.account_sync_rules()
        assert set(rules) == {"acc1", "chq", "sav", "inv"}
        assert rules["acc1"]["enabled"] and rules["sav"]["enabled"]
        assert not rules["inv"]["enabled"]
        assert rules["sav"]["account_name"] == "TD Savings ••2222"

    def test_they_show_on_the_accounts_page(self, store, fake, monkeypatch):
        client = fake([{"accounts": [MIXED_ACCOUNTS[1]], "added": [], "next_cursor": "c1"}])
        client.item_accounts = MIXED_ACCOUNTS
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        from finance import profile_api
        rows = {r["id"]: r for r in profile_api._linked_rows(store)}
        assert set(rows) == {"acc1", "chq", "sav", "inv"}
        assert rows["acc1"]["kind"] == "card"
        assert rows["inv"]["status"] == "investment"

    def test_a_sync_carries_on_when_accounts_get_fails(self, store, fake):
        fake([{"accounts": [MIXED_ACCOUNTS[1]], "added": [], "next_cursor": "c1"}])
        store.add_plaid_item("item-1", "tok", "TD")
        out = plaid_link.sync_all(store)
        assert "error" not in out["items"][0]
        assert set(store.account_sync_rules()) == {"chq"}

class TestCashAccountsSwitchedOnOnce:
    """Chequing and savings used to be skipped by default. Accounts that only
    that default switched off come on once, with their history; one the
    person switched off stays off."""

    def _pages(self, fake):
        return fake([{
            "accounts": MIXED_ACCOUNTS,
            "added": [
                txn("t1", "2026-01-05", "MOS MOS COFFEE", 6.40, account="acc1"),
                txn("t2", "2026-01-06", "PAYROLL", -2150.00, account="chq"),
            ],
            "next_cursor": "c1",
        }])

    def _old_defaults(self, store):
        for aid, kind in (("acc1", "credit"), ("chq", "depository"),
                          ("sav", "depository"), ("inv", "investment")):
            store.note_account(aid, name=aid, item_id="item-1",
                               enabled=kind == "credit", account_type=kind)

    def test_auto_skipped_chequing_comes_on_with_its_history(self, store, fake):
        store.add_plaid_item("item-1", "tok", "TD")
        self._old_defaults(store)
        store.set_plaid_cursor("item-1", "old-cursor")
        client = self._pages(fake)
        plaid_link.sync_all(store)
        assert "cursor" not in client.calls[0]           # the feed started over
        rules = store.account_sync_rules()
        assert rules["chq"]["enabled"] is True and rules["sav"]["enabled"] is True
        assert rules["inv"]["enabled"] is False
        assert "chq" in {t.account_id for t in store.all_transactions()}

    def test_a_choice_to_skip_chequing_is_kept(self, store, fake):
        store.add_plaid_item("item-1", "tok", "TD")
        self._old_defaults(store)
        store.set_account_sync("chq", False)
        self._pages(fake)
        plaid_link.sync_all(store)
        assert store.account_sync_rules()["chq"]["enabled"] is False

    def test_it_happens_once(self, store, fake):
        store.add_plaid_item("item-1", "tok", "TD")
        self._pages(fake)
        plaid_link.sync_all(store)
        store.note_account("new-chq", name="x", item_id="item-1", enabled=False,
                           account_type="depository")
        self._pages(fake)
        plaid_link.sync_all(store)
        assert store.account_sync_rules()["new-chq"]["enabled"] is False

    @pytest.mark.parametrize("acct,expected", [
        ({"type": "credit"}, True),
        ({"type": "Credit"}, True),
        ({"type": "depository"}, False),
        ({"type": "investment"}, False),
        ({"type": "loan"}, False),
        ({}, False),
    ])
    def test_what_counts_as_a_card(self, acct, expected):
        from finance.ingest.plaid_source import is_credit_account
        assert is_credit_account(acct) is expected


# ── Configuration mistakes ───────────────────────────────────────────────────

class TestEnvironmentAndCredentials:
    """The failures that look like bad keys but aren't.

    A value pasted into a dashboard field can carry a trailing newline that is
    invisible there, and an unrecognised PLAID_ENV used to fall through to
    Sandbox silently — sending production credentials to the sandbox host and
    getting back INVALID_API_KEYS, which blames the keys.
    """

    def test_a_trailing_newline_in_the_environment_is_tolerated(self, monkeypatch):
        from finance.ingest.plaid_source import plaid_environment
        monkeypatch.setenv("PLAID_ENV", "production\n")
        assert plaid_environment() == "production"

    def test_surrounding_whitespace_and_case_are_tolerated(self, monkeypatch):
        from finance.ingest.plaid_source import plaid_environment
        monkeypatch.setenv("PLAID_ENV", "  Sandbox  ")
        assert plaid_environment() == "sandbox"

    def test_an_unknown_environment_raises_rather_than_defaulting(self, monkeypatch):
        """Silently becoming sandbox is how production keys get rejected."""
        from finance.ingest.plaid_source import plaid_environment
        monkeypatch.setenv("PLAID_ENV", "development")
        with pytest.raises(RuntimeError, match="not a Plaid environment"):
            plaid_environment()

    def test_the_default_is_sandbox(self, monkeypatch):
        from finance.ingest.plaid_source import plaid_environment
        monkeypatch.delenv("PLAID_ENV", raising=False)
        assert plaid_environment() == "sandbox"

    def test_credentials_are_stripped_before_they_are_sent(self, monkeypatch):
        """A newline on the end of a secret reads to Plaid as a wrong secret."""
        from finance.ingest.plaid_source import PlaidSource
        monkeypatch.setenv("PLAID_ENV", "sandbox")
        monkeypatch.setenv("PLAID_CLIENT_ID", "  client-123\n")
        monkeypatch.setenv("PLAID_SECRET", "secret-456\n")
        client = PlaidSource()._client()
        api_key = client.api_client.configuration.api_key
        assert api_key["clientId"] == "client-123"
        assert api_key["secret"] == "secret-456"


class TestErrorMessages:
    """plaid-python stringifies a failure as status line, every response
    header, then the body — the useful sentence is buried."""

    RAW_INVALID_KEYS = (
        "(400)\nReason: Bad Request\nHTTP response headers: HTTPHeaderDict("
        "{'Server': 'nginx'})\nHTTP response body: {\"display_message\": null, "
        "\"error_code\": \"INVALID_API_KEYS\", \"error_message\": "
        "\"invalid client_id or secret provided\", \"error_type\": "
        "\"INVALID_INPUT\", \"request_id\": \"abc\"}"
    )

    def test_invalid_keys_names_the_environment_and_the_likely_cause(
            self, monkeypatch):
        monkeypatch.setenv("PLAID_ENV", "production")
        msg = plaid_link.explain(Exception(self.RAW_INVALID_KEYS))
        assert "production" in msg
        assert "secret" in msg.lower()
        assert "nginx" not in msg and "HTTPHeaderDict" not in msg

    def test_it_says_the_secret_differs_per_environment(self, monkeypatch):
        """The actual fix, most of the time."""
        monkeypatch.setenv("PLAID_ENV", "sandbox")
        msg = plaid_link.explain(Exception(self.RAW_INVALID_KEYS))
        assert "each environment has its own" in msg

    def test_an_unrecognised_error_still_yields_the_plaid_message(self):
        raw = ('(400)\nHTTP response body: {"error_code": "SOMETHING_NEW", '
               '"error_message": "the useful sentence"}')
        assert plaid_link.explain(Exception(raw)) == "the useful sentence"

    def test_a_login_required_error_says_what_to_do(self):
        msg = plaid_link.explain(Exception('{"error_code": "ITEM_LOGIN_REQUIRED"}'))
        assert "sign in again" in msg.lower()

    def test_a_bad_environment_is_reported_not_raised(self, monkeypatch):
        """Accounts renders this; a bad value must not blank the page."""
        monkeypatch.setenv("PLAID_ENV", "nonsense")
        assert plaid_link.environment() == "nonsense"


class TestRemovingAnAccountSticks:
    """Some banks grant the whole login or nothing, so the choosing is here.

    Deleting an account's rows is not a removal while the bank still holds it:
    the next sync fetches the lot again, and the account reappears with every
    transaction it had. The decision has to outlive the rows.
    """

    def _pages(self, fake):
        return fake([{
            "accounts": MIXED_ACCOUNTS,
            "added": [
                txn("t1", "2026-01-05", "MOS MOS COFFEE", 6.40, account="acc1"),
                txn("t2", "2026-01-06", "PAYMENT - THANK YOU", 500.00, account="chq"),
            ],
            "next_cursor": "c1",
        }])

    def test_an_account_turned_off_is_not_imported_again(self, store, fake):
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        assert {t.account_id for t in store.all_transactions()} == {"acc1", "chq"}

        # Remove the card, the way the app does it, and sync from scratch.
        store.clear_transactions("acc1")
        store.set_account_sync("acc1", False)
        store.set_plaid_cursor("item-1", "")
        self._pages(fake)
        plaid_link.sync_all(store)

        assert "acc1" not in {t.account_id for t in store.all_transactions()}

    def test_without_the_decision_it_comes_straight_back(self, store, fake):
        """The bug this exists to prevent: deleting rows alone achieves nothing."""
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        store.clear_transactions("acc1")
        store.set_plaid_cursor("item-1", "")
        self._pages(fake)
        plaid_link.sync_all(store)
        assert "acc1" in {t.account_id for t in store.all_transactions()}

    def test_a_non_card_turned_on_stays_on(self, store, fake):
        """A choice outranks the default, in both directions."""
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)          # records the defaults
        store.set_account_sync("chq", True)
        store.set_plaid_cursor("item-1", "")
        self._pages(fake)
        plaid_link.sync_all(store)
        assert "chq" in {t.account_id for t in store.all_transactions()}

    def test_switching_chequing_on_brings_its_history_in(self, store, fake, tmp_path):
        """The bug: rows dropped while it was off never came back, because the
        cursor had already moved past them. Switching it on rewinds it."""
        app = create_app(str(tmp_path / "t.db"))
        app.config["STORE"] = store
        client = app.test_client()
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        store.set_account_sync("chq", False)        # she had switched it off
        plaid_link.sync_all(store)
        assert "chq" not in {t.account_id for t in store.all_transactions()}
        assert store.plaid_items()[0]["synced_before"]
        cards = len(store.all_transactions())

        r = client.put("/api/accounts/chq/sync", json={"enabled": True})
        assert r.get_json()["resync"] is True
        assert not store.plaid_items()[0]["synced_before"]     # rewound

        self._pages(fake)                           # Plaid sends it all again
        plaid_link.sync_all(store)
        rows = store.all_transactions()
        assert "chq" in {t.account_id for t in rows}
        assert len([t for t in rows if t.account_id == "acc1"]) == cards   # no doubles

    def test_switching_a_card_off_does_not_rewind(self, store, fake, tmp_path):
        app = create_app(str(tmp_path / "t.db"))
        app.config["STORE"] = store
        client = app.test_client()
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        r = client.put("/api/accounts/acc1/sync", json={"enabled": False})
        assert r.get_json()["resync"] is False
        assert store.plaid_items()[0]["synced_before"]

    def test_every_account_the_bank_sent_is_recorded(self, store, fake):
        """Including the ones skipped — they cannot be chosen if unlisted."""
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        rules = store.account_sync_rules()
        assert set(rules) == {"acc1", "chq", "sav", "inv"}
        assert rules["acc1"]["enabled"] is True
        assert rules["chq"]["enabled"] is True
        assert rules["inv"]["enabled"] is False
        assert all(r["decided_by"] == "auto" for r in rules.values())
        assert rules["chq"]["item_id"] == "item-1"

    def test_a_default_never_overwrites_a_choice(self, store, fake):
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        store.set_account_sync("acc1", False)
        store.set_plaid_cursor("item-1", "")
        self._pages(fake)
        plaid_link.sync_all(store)
        rule = store.account_sync_rules()["acc1"]
        assert rule["decided_by"] == "user"
        assert rule["enabled"] is False

    def test_unlinking_the_bank_forgets_its_accounts(self, store, fake):
        self._pages(fake)
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        plaid_link.unlink(store, "item-1")
        assert store.account_sync_rules() == {}


class TestHistoryRequested:
    """Ninety days is not enough to see a year-on-year anything."""

    def test_two_years_are_asked_for_at_link_time(self, store, fake):
        client = fake([])
        plaid_link.create_link_token()
        sent = client.link_requests[0]
        assert sent["transactions"]["days_requested"] == 730

    def test_it_is_the_most_plaid_allows(self):
        """Higher is rejected outright, and the window cannot be raised later."""
        assert plaid_link.DAYS_REQUESTED == 730


class TestQuietTwinsAndInvestments:
    """The same bank linked more than once hands over every account each time;
    listed once. Investment accounts are balance only, and a transfer into one
    is Saved."""

    TFSA = {"account_id": "inv-new", "name": "Wealthsimple TFSA", "mask": None,
            "type": "investment", "subtype": "tfsa"}

    def _two_logins(self, store, fake):
        store.add_plaid_item("item-old", "tok-old", "Wealthsimple")
        store.add_plaid_item("item-new", "tok-new", "Wealthsimple")
        for aid, item in (("inv-old", "item-old"), ("inv-new", "item-new")):
            store.note_account(aid, name="Wealthsimple TFSA", item_id=item, enabled=False,
                               account_type="investment", subtype="tfsa")

    def test_a_copy_with_nothing_in_it_comes_off_the_list(self, store, fake):
        self._two_logins(store, fake)
        assert plaid_link.hide_quiet_twins(store) == ["inv-old"]       # the newer one stays
        from finance import profile_api
        assert [r["id"] for r in profile_api._linked_rows(store)] == ["inv-new"]
        assert plaid_link.hide_quiet_twins(store) == []

    def test_the_copy_with_transactions_stays(self, store, fake):
        store.add_plaid_item("item-old", "tok-old", "TD")
        store.add_plaid_item("item-new", "tok-new", "TD")
        store.note_account("chq-old", name="TD Chequing ••1111", item_id="item-old",
                           account_type="depository", subtype="checking")
        store.note_account("chq-new", name="TD Chequing ••1111", item_id="item-new",
                           account_type="depository", subtype="checking")
        from finance.models import Transaction
        store.add_transactions([Transaction(date="2026-01-05", description="COFFEE",
                                            merchant="Coffee", amount=5.0, category="Coffee",
                                            account_id="chq-old", account_name="TD Chequing")])
        assert plaid_link.hide_quiet_twins(store) == ["chq-new"]

    def test_different_banks_are_never_twins(self, store, fake):
        store.add_plaid_item("item-a", "tok-a", "TD")
        store.add_plaid_item("item-b", "tok-b", "RBC")
        store.note_account("a", name="Chequing ••1111", item_id="item-a", account_type="depository")
        store.note_account("b", name="Chequing ••1111", item_id="item-b", account_type="depository")
        assert plaid_link.hide_quiet_twins(store) == []

    def test_an_investment_account_is_balance_only_and_never_counted(self, tmp_path):
        from finance import profile_api
        app = create_app(str(tmp_path / "inv.db"))
        app.config.update(TESTING=True)
        st = app.config["STORE"]
        st.add_plaid_item("item-1", "tok", "Wealthsimple")
        st.note_account("inv", name="Wealthsimple TFSA ••3333", item_id="item-1",
                        enabled=False, account_type="investment", subtype="tfsa")
        row = profile_api._linked_rows(st)[0]
        assert row["kind"] == "investment" and row["status"] == "investment"
        with app.test_client() as c:
            r = c.put("/api/accounts/inv/settings", json={"counted": True})
        assert r.status_code == 400 and "investment" in r.get_json()["error"]
        assert st.account_sync_rules()["inv"]["enabled"] is False

    def test_a_transfer_into_a_linked_investment_account_is_saved(self, store):
        from finance.models import Transaction
        from finance.transfers import apply_transfer_matches, known_destinations
        store.add_plaid_item("item-1", "tok", "Wealthsimple")
        store.note_account("inv", name="Wealthsimple TFSA ••3333", item_id="item-1",
                           enabled=False, account_type="investment", subtype="tfsa")
        assert known_destinations(store) == {"acct:3333": "Saved"}
        from datetime import date
        day = date.today().isoformat()
        store.add_transactions([Transaction(
            date=day, description="TFR-TO 12343333", merchant="Transfer", amount=500.0,
            category="Transfers", account_id="chq", account_name="Chequing",
            raw={"account_type": "depository"})])
        apply_transfer_matches(store)
        assert store.all_transactions()[0].category == "Saved"
        store.set_destination("acct:3333", "Transfers")
        assert known_destinations(store)["acct:3333"] == "Transfers"     # her rule wins

    def test_the_bank_logo_is_looked_up_once(self, store, fake):
        client = fake([{"next_cursor": "c1"}, {"next_cursor": "c2"}])
        calls = []
        client.item_get = lambda req: (calls.append("item"),
                                       _Resp({"item": {"institution_id": "ins_1"}}))[1]
        client.institutions_get_by_id = lambda req: (calls.append("inst"),
                                                     _Resp({"institution": {"logo": "QUJD"}}))[1]
        store.add_plaid_item("item-1", "tok", "TD")
        plaid_link.sync_all(store)
        assert store.plaid_items()[0]["logo"] == "data:image/png;base64,QUJD"
        plaid_link.sync_all(store)
        assert calls == ["item", "inst"]


class TestReadingLessOfTheLedger:
    """Every ledger load reads every row from the database, which on a hosted
    one is metered (Neon's network transfer ran out, 2026-10-14)."""

    def test_a_sync_loads_the_ledger_once_and_settles_once_for_all_accounts(
            self, store, fake, monkeypatch):
        from finance.store import Store
        fake([{"accounts": MIXED_ACCOUNTS,
               "added": [txn("t1", "2026-01-05", "COFFEE", 6.40, account="acc1"),
                         txn("t2", "2026-01-06", "GROCER", 50.00, account="chq"),
                         txn("t3", "2026-01-07", "BAKERY", 8.00, account="sav")],
               "next_cursor": "c1"}])
        store.add_plaid_item("item-1", "tok", "TD")
        from finance.categorize import RULES_VERSION
        store.set_setting("categories_version", RULES_VERSION)   # no one-time re-sort
        store.set_setting("destinations_migrated", "1")          # nor migration
        loads = []
        orig = Store.all_transactions
        monkeypatch.setattr(Store, "all_transactions",
                            lambda self: (loads.append(1), orig(self))[1])
        out = plaid_link.sync_all(store)
        assert out["imported"] == 3
        # One load to check for repeats, then transfers, income types and
        # duplicates once — not all of it once per account.
        assert len(loads) == 4

    def test_opening_the_app_syncs_at_most_hourly(self, tmp_path, monkeypatch):
        app = create_app(str(tmp_path / "s.db"))
        app.config.update(TESTING=True)
        st = app.config["STORE"]
        client = FakePlaid([{"next_cursor": "c1"}, {"next_cursor": "c2"}])
        monkeypatch.setattr(plaid_link, "_client", lambda: client)
        monkeypatch.setattr(plaid_link, "configured", lambda: True)
        st.add_plaid_item("item-1", "tok", "TD")
        with app.test_client() as c:
            assert "recent" not in c.post("/api/plaid/sync", json={}).get_json()
            assert c.post("/api/plaid/sync", json={}).get_json()["recent"] is True
            assert len(client.calls) == 1
            assert "recent" not in c.post("/api/plaid/sync", json={"force": True}).get_json()
            assert len(client.calls) == 2

    def test_an_old_or_failed_sync_is_not_recent(self, store):
        from datetime import datetime, timedelta, timezone
        store.add_plaid_item("item-1", "tok", "TD")
        assert not plaid_link.synced_recently(store)              # never synced
        store.set_plaid_cursor("item-1", "c1")
        assert plaid_link.synced_recently(store)
        later = datetime.now(timezone.utc) + timedelta(minutes=61)
        assert not plaid_link.synced_recently(store, now=later)
        store.set_plaid_error("item-1", "Sign in again", "ITEM_LOGIN_REQUIRED")
        assert not plaid_link.synced_recently(store)

    def test_a_doubled_connection_starts_over_at_most_once_a_day(self, store, fake, monkeypatch):
        store.add_plaid_item("item-1", "tok", "TD")
        monkeypatch.setattr(plaid_link, "doubled_items", lambda st: ["item-1"])
        rewinds = []
        orig = store.rewind_plaid_cursor
        monkeypatch.setattr(store, "rewind_plaid_cursor",
                            lambda i: (rewinds.append(i), orig(i))[1])
        fake([{"next_cursor": "c1"}, {"next_cursor": "c2"}])
        plaid_link.sync_all(store)
        plaid_link.sync_all(store)
        assert rewinds.count("item-1") == 1
