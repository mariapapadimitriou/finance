"""Ledger — local-first personal finance and budgeting.

Aggregates transactions across every credit card you own, works out where the
money actually goes, and tells you specifically what to cut.

    python app.py            # API on http://localhost:5050
    python app.py --demo     # load sample data first, for a look around

Your data lives in a local SQLite file (`ledger.db`) and never leaves the
machine unless you explicitly run the optional Claude narrative.
"""

from __future__ import annotations

import argparse
import os
import sys

from flask import Flask, jsonify
from flask_cors import CORS

from finance.api import bp
from finance.store import DEFAULT_DB, Store

PORT = int(os.environ.get("PORT", 5050))


def create_app(db_path: str = DEFAULT_DB) -> Flask:
    app = Flask(__name__)
    # The frontend runs on the Vite dev server, so cross-origin is expected.
    # Bound to localhost only -- this API is not meant to face a network.
    CORS(app, origins=["http://localhost:3000", "http://127.0.0.1:3000",
                       "http://localhost:5173", "http://127.0.0.1:5173"])
    app.config["STORE"] = Store(db_path)
    app.register_blueprint(bp)

    @app.get("/")
    def root():
        return jsonify({
            "app": "Ledger",
            "docs": "See README.md",
            "endpoints": sorted(
                str(r.rule) for r in app.url_map.iter_rules()
                if str(r.rule).startswith("/api")
            ),
        })

    return app


def main() -> int:
    parser = argparse.ArgumentParser(description="Ledger — personal finance API")
    parser.add_argument("--port", type=int, default=PORT)
    parser.add_argument("--db", default=DEFAULT_DB, help="path to the SQLite ledger")
    parser.add_argument("--demo", action="store_true",
                        help="generate and import sample data before starting")
    parser.add_argument("--reset", action="store_true",
                        help="clear all transactions before starting")
    args = parser.parse_args()

    app = create_app(args.db)
    store: Store = app.config["STORE"]

    if args.reset:
        deleted = store.clear_transactions()
        print(f"Cleared {deleted} transactions.")

    if args.demo:
        from sample_data.generate import load_demo
        count = load_demo(store)
        print(f"Loaded {count} sample transactions across 3 cards.")

    print(f"Ledger API → http://localhost:{args.port}")
    print(f"Ledger DB  → {args.db}")
    app.run(host="127.0.0.1", port=args.port, debug=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
