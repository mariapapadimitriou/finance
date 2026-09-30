"""Spendie — personal finance and budgeting across every card.

Aggregates transactions across every credit card you own, works out where the
money actually goes, and tells you specifically what to cut.

    python app.py            # API on http://localhost:5050
    python app.py --demo     # load sample data first, for a look around

Your data lives in a local SQLite file (`ledger.db`) and never leaves the
machine unless you explicitly run the optional Claude narrative.

This module also exposes a module-level `app` so a WSGI host (Vercel's Flask
runtime, gunicorn, uWSGI) can import it directly. See `_hosted_db_path` for the
one thing that changes when hosted.
"""

from __future__ import annotations

import argparse
import os
import sys

from flask import Flask, abort, jsonify, send_from_directory
from flask_cors import CORS

from finance.api import bp
from finance.db import database_url, storage_mode  # noqa: F401
from finance.store import DEFAULT_DB, Store

PORT = int(os.environ.get("PORT", 5050))

HERE = os.path.dirname(os.path.abspath(__file__))
# `npm run build` writes here. Vercel also serves this directory from its CDN,
# so in practice Flask only serves it when running as a plain WSGI app.
FRONTEND_DIR = os.path.join(HERE, "public")

# Local dev runs the UI on Vite's dev server against the API on another port.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000",
               "http://localhost:5173", "http://127.0.0.1:5173"]


def _is_hosted() -> bool:
    """True when running on a serverless host rather than a developer machine."""
    return bool(os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"))


def _hosted_db_path() -> str | None:
    """On a serverless host without a database, the only writable dir is /tmp.

    Returns None when running normally, so the local SQLite file is used.

    /tmp belongs to one function instance and is discarded when that instance
    is recycled, so anything added there — an upload, a budget, a category you
    corrected — lives only as long as that instance, and a second request
    served by a different instance never sees it at all. Set `DATABASE_URL` to
    a hosted Postgres and none of that applies: `finance/db.py` takes over, the
    path below is ignored, and edits persist and are shared across instances.
    """
    if database_url():
        return None  # Postgres is in charge; the path is unused
    if os.environ.get("LEDGER_DB"):
        return None  # explicit configuration wins
    if _is_hosted():
        return "/tmp/ledger.db"
    return None


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)

    # CORS exists only for local development, where the Vite dev server and the
    # API sit on different ports. A built deployment serves both from one
    # origin, so sending these headers there would be noise at best.
    if not _is_hosted():
        CORS(app, origins=DEV_ORIGINS)

    app.config["STORE"] = Store(db_path or _hosted_db_path() or DEFAULT_DB)
    app.register_blueprint(bp)

    # A hosted instance boots with an empty database, so the committed ledger is
    # loaded into it. On /tmp that happens on every cold start; on Postgres it
    # happens once, because `seed_ledger_if_empty` does nothing to a store that
    # already holds transactions — which is what lets an upload there survive.
    if _is_hosted() or os.environ.get("SEED_LEDGER") == "1":
        seed_ledger_if_empty(app.config["STORE"])
    elif os.environ.get("SEED_DEMO") == "1":
        seed_demo_if_empty(app.config["STORE"])

    @app.get("/", defaults={"path": ""})
    @app.get("/<path:path>")
    def frontend(path: str):
        """Serve the built UI, falling back to API info when there is no build.

        The blueprint's routes are static rules, so Flask matches them ahead of
        this catch-all; the guard below only covers unknown /api paths.
        """
        if path.startswith("api/"):
            abort(404)

        candidate = os.path.join(FRONTEND_DIR, path)
        if path and os.path.isfile(candidate):
            return send_from_directory(FRONTEND_DIR, path)

        if os.path.isfile(os.path.join(FRONTEND_DIR, "index.html")):
            return send_from_directory(FRONTEND_DIR, "index.html")

        return jsonify({
            "app": "Spendie",
            "note": "No frontend build found. Run `npm run build`, "
                    "or `npm run dev` for the dev server.",
            "endpoints": sorted(
                str(r.rule) for r in app.url_map.iter_rules()
                if str(r.rule).startswith("/api")
            ),
        })

    return app


def seed_demo_if_empty(store: Store) -> int:
    """Load generated sample data into an empty ledger. Never touches existing data."""
    if store.all_transactions():
        return 0
    from sample_data.generate import load_demo
    return load_demo(store)


def seed_ledger_if_empty(store: Store) -> int:
    """Load the committed ledger into an empty store.

    This is what makes a hosted deployment show real spending rather than an
    empty state. Everything in seed_data/transactions.json is public by design;
    see that package's docstring.
    """
    from seed_data.export import load
    return load(store)


# Imported by WSGI hosts. Safe at import time: it opens the ledger and,
# on a hosted instance, seeds an empty one.
app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description="Spendie — personal finance API")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--db", default=DEFAULT_DB, help="path to the SQLite ledger")
    parser.add_argument("--demo", action="store_true",
                        help="generate and import sample data before starting")
    parser.add_argument("--reset", action="store_true",
                        help="clear all transactions before starting")
    args = parser.parse_args()

    local = create_app(args.db)
    store: Store = local.config["STORE"]

    if args.reset:
        print(f"Cleared {store.clear_transactions()} transactions.")

    if args.demo:
        from sample_data.generate import load_demo
        print(f"Loaded {load_demo(store)} sample transactions across 3 cards.")

    print(f"Spendie API → http://localhost:{args.port}")
    print(f"Spendie DB  → {args.db}")
    local.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
