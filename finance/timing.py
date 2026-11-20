"""How long each request spent, and on what (2026-11-19).

Every answer carries a `Server-Timing` header: total milliseconds on the
server, milliseconds inside the database, how many database transactions and
statements the request opened, and whether a computed result was reused. The
iPhone prints it in DEBUG next to the wall time, so a slow screen can be split
into the server, the network and the phone. `tests/test_request_budget.py`
holds the transaction counts to a ceiling per endpoint so the costs this was
added to measure can't creep back.

Counting lives here rather than in `db.py` or `store.py` so neither needs to
know about Flask: outside a request the counters are simply not there.
"""

from __future__ import annotations

import time

from flask import g, has_request_context, request

HEADER = "Server-Timing"


def _slot() -> dict | None:
    if not has_request_context():
        return None
    return g.get("_timing")


def transaction() -> None:
    """One database transaction opened (the outermost `with store.conn()`)."""
    t = _slot()
    if t is not None:
        t["tx"] += 1


def statement(seconds: float) -> None:
    """One statement ran, taking `seconds` inside the driver."""
    t = _slot()
    if t is not None:
        t["stmts"] += 1
        t["db_s"] += seconds


def note(key: str, value) -> None:
    """Anything else worth seeing in the header (a cache hit, a recompute)."""
    t = _slot()
    if t is not None:
        t["notes"][key] = value


def install(app) -> None:
    @app.before_request
    def _start():
        g._timing = {"began": time.perf_counter(), "tx": 0, "stmts": 0, "db_s": 0.0,
                     "notes": {}}

    @app.after_request
    def _report(response):
        t = g.get("_timing")
        if t is None:
            return response
        total_ms = (time.perf_counter() - t["began"]) * 1000
        parts = [f"total;dur={total_ms:.0f}",
                 f"db;dur={t['db_s'] * 1000:.0f};desc=\"tx={t['tx']} stmts={t['stmts']}\""]
        for key, value in t["notes"].items():
            parts.append(f"{key};desc=\"{value}\"")
        response.headers[HEADER] = ", ".join(parts)
        if app.config.get("TESTING"):
            # The budget test reads what the last request cost.
            app.config["LAST_TIMING"] = {"path": request.path, "method": request.method,
                                         "total_ms": total_ms, **t}
        return response
