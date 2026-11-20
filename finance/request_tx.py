"""One database transaction per request (2026-11-19).

Every `Store` method used to open its own transaction, and on a pooled
Postgres each one is `SET LOCAL search_path`, the statements and `COMMIT`:
a few network round trips, seventy-odd times for Home. Now the first store
call in a request opens the ledger's transaction, every later call joins it
(`finance/db.py`, `request_scope`), and it is committed here once the answer
is ready, or rolled back if the request failed. A failed write therefore
leaves nothing half-applied, where before each method's work stayed.

Requests that talk to Plaid, stream an export or drop an account are left as
they were: they can take long, and holding a pooled connection open through
a network call, or dropping a schema that this same request has a
transaction on, would be worse than the round trips.
"""

from __future__ import annotations

from flask import g, request

from . import db

NO_TRANSACTION_PREFIXES = ("/api/plaid/", "/api/data/", "/api/account/", "/api/setup-again")


def install(app) -> None:
    @app.before_request
    def _scope():
        db.abandon_request()            # nothing should be open; make sure
        g._tx_enabled = not request.path.startswith(NO_TRANSACTION_PREFIXES)
        g._dirty_seq = 0

    @app.after_request
    def _commit(response):
        if response.status_code < 500:
            bump_versions()
        db.finish_request(commit=response.status_code < 500)
        # The test client keeps the request context alive after the answer;
        # store calls made then (a test loading rows) are their own
        # transactions again, not an open one nobody will commit.
        g._tx_enabled = False
        return response

    @app.teardown_request
    def _rollback(exc):
        db.abandon_request()


def bump_versions() -> dict:
    """Every store this request wrote to gets a new version, once; the
    versions by store key. Called before the commit, and by anything that
    needs the new number for its answer (finance/changed.py)."""
    from .store import dirty_stores
    done = g.setdefault("_bumped", {})
    for st in dirty_stores():
        key = (st.path, st.url, st.schema)
        if key not in done:
            done[key] = st.bump_version()
    return done
