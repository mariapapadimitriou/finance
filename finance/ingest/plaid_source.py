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

# Plaid decommissioned Development in June 2024; these are the two that exist.
VALID_ENVIRONMENTS = ("sandbox", "production")


def plaid_environment() -> str:
    """Which Plaid environment to talk to.

    An unrecognised value used to fall through to Sandbox silently, which is
    the worst possible default: production credentials would be sent to the
    sandbox host and come back as INVALID_API_KEYS, pointing the blame at the
    keys rather than at the environment name. Now it says so.
    """
    env = os.environ.get("PLAID_ENV", "sandbox").strip().lower()
    if env not in VALID_ENVIRONMENTS:
        raise RuntimeError(
            f"PLAID_ENV is set to {env!r}, which is not a Plaid environment. "
            f"Use 'sandbox' or 'production'. (Plaid retired 'development' in "
            f"June 2024.)"
        )
    return env


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

        # Stripped, because these are pasted into a dashboard field and a
        # trailing newline is invisible there. Plaid rejects the whole request
        # as INVALID_API_KEYS, which reads as "wrong credentials" rather than
        # "your credentials have a space on the end".
        env = plaid_environment()
        host = {
            "sandbox": Environment.Sandbox,
            "production": Environment.Production,
        }[env]

        config = Configuration(host=host, api_key={
            "clientId": os.environ.get("PLAID_CLIENT_ID", "").strip(),
            "secret": os.environ.get("PLAID_SECRET", "").strip(),
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
                "Create a Plaid account — the Trial plan is free and covers "
                "10 connected banks",
                "Copy the client ID and secret from the Plaid dashboard",
                "Set PLAID_CLIENT_ID, PLAID_SECRET and PLAID_ENV in the "
                "deployment's environment",
                "Set SPENDIE_SECRET_KEY so access tokens can be encrypted "
                "before they are stored",
                "Then connect each card on the Banks tab",
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


def _counterparty(item: dict) -> str:
    for cp in item.get("counterparties") or []:
        name = (cp or {}).get("name")
        if name:
            return str(name).strip()
    return str(item.get("merchant_name") or "").strip()


def _logo(item: dict) -> str:
    if item.get("logo_url"):
        return str(item["logo_url"])
    for cp in item.get("counterparties") or []:
        if (cp or {}).get("logo_url"):
            return str(cp["logo_url"])
    return ""


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
        # Plaid reports the currency per transaction. `iso_currency_code` is
        # null for currencies it does not officially support, and the code
        # moves to `unofficial_currency_code` — reading only the first and
        # defaulting to USD labelled those rows as dollars.
        currency=(item.get("iso_currency_code")
                  or item.get("unofficial_currency_code")
                  or (accounts or {}).get(acct_id, {}).get("iso_currency_code")
                  or ""),
        source="plaid",
        # The account's type is kept on the row because it is the only place it
        # survives: Plaid reports it alongside the transactions, not with them,
        # and after the sync there is nothing left to ask.
        raw={"issuer_category": detail,
             "plaid_id": item.get("transaction_id", ""),
             "account_type": acct.get("type", ""),
             "account_subtype": acct.get("subtype", ""),
             # A pending row is replaced when it posts; the posted one names
             # the pending one it replaces, which is how the twin is found.
             "pending": bool(item.get("pending")),
             # Who the money went to or came from, when Plaid knows: the one
             # stable name an e-transfer has, since its description carries a
             # new reference every time.
             "counterparty": _counterparty(item),
             # Free with every transaction: the merchant's logo and a stable id
             # (one merchant however its name is spelled), and how sure Plaid
             # is of its own category.
             "logo_url": _logo(item),
             "merchant_entity_id": item.get("merchant_entity_id") or "",
             "category_confidence": str(plaid_cat.get("confidence_level") or ""),
             "pending_id": item.get("pending_transaction_id") or ""},
    )


# Linking a bank hands over every account it holds — chequing, savings, an
# investment account, a mortgage. This app is about card spending, and a
# chequing account's transfers would double-count what the card already
# records, so only credit accounts are kept by default.
CREDIT_TYPES = ("credit",)


def is_credit_account(account: dict) -> bool:
    return str(account.get("type", "")).lower() in CREDIT_TYPES


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
