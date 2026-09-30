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


ACCOUNTS = [{"account_id": "acc1", "name": "TD Cash Back Visa", "mask": "4321"}]


def _as_dict(request):
    """Plaid's generated models are not mappings; they do expose to_dict()."""
    return request.to_dict()


class FakePlaid:
    """Returns scripted /transactions/sync pages, and records what it was asked."""

    def __init__(self, pages):
        self.pages = list(pages)
        self.calls = []
        self.removed_items = []

    def transactions_sync(self, request):
        self.calls.append(_as_dict(request))
        page = self.pages.pop(0)
        return _Resp({"accounts": ACCOUNTS, "added": [], "modified": [],
                      "removed": [], "has_more": False, **page})

    def item_public_token_exchange(self, request):
        return _Resp({"item_id": "item-1", "access_token": "access-secret-xyz"})

    def item_remove(self, request):
        self.removed_items.append(_as_dict(request))
        return _Resp({"removed": True})

    def link_token_create(self, request):
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
        """The Banks tab renders this; a bad value must not blank the page."""
        monkeypatch.setenv("PLAID_ENV", "nonsense")
        assert plaid_link.environment() == "nonsense"
