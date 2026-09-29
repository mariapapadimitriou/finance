"""Ledger — local-first personal finance and budgeting.

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
from finance.store import DEFAULT_DB, Store

PORT = int(os.environ.get("PORT", 5050))

HERE = os.path.dirname(os.path.abspath(__file__))
# `npm run build` writes here. Vercel also serves this directory from its CDN,
# so in practice Flask only serves it when running as a plain WSGI app.
FRONTEND_DIR = os.path.join(HERE, "public")

# Local dev runs the UI on Vite's dev server against the API on another port.
DEV_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000",
               "http://localhost:5173", "http://127.0.0.1:5173"]


def _hosted_db_path() -> str | None:
    """On a serverless host, the only writable directory is /tmp.

    Returns None when running normally, so the local SQLite file is used.

    Worth being blunt about what this implies: /tmp belongs to one function
    instance and is discarded when that instance is recycled. A hosted
    deployment is therefore a demo you can click through, not somewhere to keep
    real statements — imports and budget edits survive only as long as the
    instance that received them. Persisting properly means moving `store.py`
    onto a hosted database.
    """
    if os.environ.get("LEDGER_DB"):
        return None  # explicit configuration wins
    if os.environ.get("VERCEL") or os.environ.get("AWS_LAMBDA_FUNCTION_NAME"):
        return "/tmp/ledger.db"
    return None


def create_app(db_path: str | None = None) -> Flask:
    app = Flask(__name__)
    CORS(app, origins=DEV_ORIGINS)

    app.config["STORE"] = Store(db_path or _hosted_db_path() or DEFAULT_DB)
    app.register_blueprint(bp)

    # A hosted demo starts with an empty /tmp, so seed it with sample data —
    # otherwise every cold start would greet you with the empty state.
    if os.environ.get("SEED_DEMO") == "1":
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
            "app": "Ledger",
            "note": "No frontend build found. Run `npm run build`, "
                    "or `npm run dev` for the dev server.",
            "endpoints": sorted(
                str(r.rule) for r in app.url_map.iter_rules()
                if str(r.rule).startswith("/api")
            ),
        })

    return app


def seed_demo_if_empty(store: Store) -> int:
    """Load sample data into an empty ledger. Never touches existing data."""
    if store.all_transactions():
        return 0
    from sample_data.generate import load_demo
    return load_demo(store)


# Imported by WSGI hosts. Safe at import time: it only opens a SQLite file.
app = create_app()


def main() -> int:
    parser = argparse.ArgumentParser(description="Ledger — personal finance API")
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

    print(f"Ledger API → http://localhost:{args.port}")
    print(f"Ledger DB  → {args.db}")
    local.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
