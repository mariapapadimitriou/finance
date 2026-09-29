"""Plaid live-sync adapter.

This implements the same `TransactionSource` contract as the CSV importer, so
turning on live sync is a configuration change rather than a rewrite: the
mapping from Plaid's payload to our normalized `Transaction` is already written
below and exercised by tests against a recorded fixture.

What is missing is only the account and credentials:

    pip install plaid-python
    export PLAID_CLIENT_ID=...  PLAID_SECRET=...  PLAID_ENV=sandbox|production

and a stored access token per linked institution (see `link_token` /
`exchange_public_token` in Plaid's Link flow). Until those exist, `status()`
reports unavailable and the API surfaces the setup steps instead of failing.
"""

from __future__ import annotations

import os

from ..models import Transaction, parse_date
from .base import IngestResult, SourceStatus, TransactionSource, register

_ENV_KEYS = ("PLAID_CLIENT_ID", "PLAID_SECRET")


class PlaidSource(TransactionSource):
    key = "plaid"
    label = "Plaid live sync"

    # ── Configuration ────────────────────────────────────────────────────────
    def _missing_config(self) -> list[str]:
        return [k for k in _ENV_KEYS if not os.environ.get(k)]

    def _client(self):
        try:
            import plaid  # noqa: F401
        except ImportError as exc:
            raise RuntimeError(
                "plaid-python is not installed. Run: pip install plaid-python"
            ) from exc

        from plaid.api import plaid_api
        from plaid.configuration import Configuration, Environment
        from plaid.api_client import ApiClient

        env = os.environ.get("PLAID_ENV", "sandbox").lower()
        host = {
            "sandbox": Environment.Sandbox,
            "production": Environment.Production,
        }.get(env, Environment.Sandbox)

        config = Configuration(host=host, api_key={
            "clientId": os.environ["PLAID_CLIENT_ID"],
            "secret": os.environ["PLAID_SECRET"],
        })
        return plaid_api.PlaidApi(ApiClient(config))

    def status(self) -> SourceStatus:
        missing = self._missing_config()
        try:
            import plaid  # noqa: F401
            lib = True
        except ImportError:
            lib = False

        if lib and not missing:
            return SourceStatus(
                key=self.key, label=self.label, available=True,
                detail="Credentials found. Link an institution to start syncing.",
            )

        problems = []
        if not lib:
            problems.append("plaid-python is not installed")
        if missing:
            problems.append("missing " + ", ".join(missing))

        return SourceStatus(
            key=self.key,
            label=self.label,
            available=False,
            detail="Not configured — " + "; ".join(problems) + ".",
            setup_url="https://dashboard.plaid.com/signup",
            setup_steps=[
                "Create a Plaid developer account (sandbox is free)",
                "pip install plaid-python",
                "export PLAID_CLIENT_ID and PLAID_SECRET",
                "Run Plaid Link to connect each card and store its access token",
                "Production access requires Plaid's approval and is billed per item",
            ],
        )

    # ── Fetch ────────────────────────────────────────────────────────────────
    def fetch(self, access_token: str | None = None, start_date: str | None = None,
              end_date: str | None = None, **kwargs) -> list[IngestResult]:
        st = self.status()
        if not st.available:
            raise RuntimeError(st.detail)
        if not access_token:
            raise RuntimeError("No access_token supplied — link an institution first.")

        from plaid.model.transactions_get_request import TransactionsGetRequest
        from datetime import date, timedelta

        end = date.fromisoformat(end_date) if end_date else date.today()
        start = date.fromisoformat(start_date) if start_date else end - timedelta(days=365)

        client = self._client()
        resp = client.transactions_get(TransactionsGetRequest(
            access_token=access_token, start_date=start, end_date=end,
        )).to_dict()

        accounts = {a["account_id"]: a for a in resp.get("accounts", [])}
        return group_plaid_transactions(resp.get("transactions", []), accounts)


def map_plaid_transaction(item: dict, accounts: dict | None = None) -> Transaction | None:
    """Translate one Plaid transaction into our normalized model.

    Plaid reports outflows as positive, which already matches our convention,
    so the amount passes through unflipped.
    """
    iso = parse_date(str(item.get("date", "")))
    if iso is None:
        return None

    amount = item.get("amount")
    if amount is None:
        return None

    acct_id = item.get("account_id", "plaid")
    acct = (accounts or {}).get(acct_id, {})
    name = acct.get("official_name") or acct.get("name") or "Plaid account"
    mask = acct.get("mask")
    if mask:
        name = f"{name} ••{mask}"

    description = (item.get("merchant_name") or item.get("name") or "").strip()

    plaid_cat = item.get("personal_finance_category") or {}
    detail = plaid_cat.get("detailed") or plaid_cat.get("primary") or ""
    if not detail and item.get("category"):
        detail = " / ".join(item["category"])

    return Transaction(
        date=iso,
        post_date=parse_date(str(item.get("authorized_date") or "")) or None,
        description=description or "(no description)",
        amount=float(amount),
        account_id=acct_id,
        account_name=name,
        currency=item.get("iso_currency_code") or "USD",
        source="plaid",
        raw={"issuer_category": detail, "plaid_id": item.get("transaction_id", "")},
    )


def group_plaid_transactions(items: list[dict], accounts: dict) -> list[IngestResult]:
    """Bucket Plaid rows into one IngestResult per account."""
    by_account: dict[str, list[Transaction]] = {}
    skipped = 0

    for item in items:
        t = map_plaid_transaction(item, accounts)
        if t is None:
            skipped += 1
            continue
        by_account.setdefault(t.account_id, []).append(t)

    results = []
    for acct_id, txns in by_account.items():
        # Plaid gives every row a stable id, so sequence numbering is only a
        # safety net for the identical-row case the fingerprint would collapse.
        seen: dict[tuple, int] = {}
        for t in txns:
            key = (t.account_id, t.date, f"{t.amount:.2f}", t.description.upper())
            t.seq = seen.get(key, 0)
            seen[key] = t.seq + 1

        results.append(IngestResult(
            transactions=txns,
            account_id=acct_id,
            account_name=txns[0].account_name,
            format_key="plaid",
            format_label="Plaid",
            confidence=1.0,
            skipped_rows=skipped,
        ))
    return results


register(PlaidSource())
