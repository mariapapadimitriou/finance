"""Linking a bank through Plaid, and keeping it in step afterwards.

`ingest/plaid_source.py` already knows how to turn a Plaid transaction into one
of ours. This is the part around it: getting an access token in the first
place, storing it safely, and pulling changes since the last time.

**Linking.** Plaid Link runs in the browser and never hands the page anything
durable. The server mints a short-lived *link token*, Link exchanges the user's
credentials for a one-shot *public token*, and the server swaps that for the
*access token* that actually reads the account. The access token never reaches
the browser, which is the whole point of the dance — so it is created here,
encrypted here, and never serialised back out.

**Syncing.** `/transactions/sync` rather than `/transactions/get`: Plaid
recommends it for new integrations, and it fits this ledger better. Instead of
re-downloading a date range and relying on de-duplication to sort it out, each
call returns exactly what changed since a stored cursor — added, modified and
removed. That last one matters: when a pending charge posts, Plaid removes the
pending row and adds the posted one, and an importer that only ever adds would
keep both and count the purchase twice.

The cursor is only advanced once the rows it covers are safely stored. If a
sync fails halfway the cursor stays where it was, and the next run re-fetches
the same window rather than skipping it — the same rows arriving twice are
caught by the fingerprint, where a gap would be silent and permanent.
"""

from __future__ import annotations

import os

from .ingest.plaid_source import group_plaid_transactions
from .pipeline import ingest

# Canada only. Both cards here are Canadian, and a narrower country list gives
# Link a shorter, correct institution picker instead of a mostly-US one.
COUNTRY_CODES = [c.strip().upper() for c in
                 os.environ.get("PLAID_COUNTRY_CODES", "CA").split(",") if c.strip()]


def _client():
    from .ingest.plaid_source import PlaidSource
    return PlaidSource()._client()


def configured() -> bool:
    from .ingest.plaid_source import PlaidSource
    return PlaidSource().status().available


def environment() -> str:
    return os.environ.get("PLAID_ENV", "sandbox").lower()


def create_link_token(user_id: str = "spendie-user") -> dict:
    """A short-lived token that authorises one run of Plaid Link."""
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.products import Products

    resp = _client().link_token_create(LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        client_name="Spendie",
        products=[Products("transactions")],
        country_codes=[CountryCode(c) for c in COUNTRY_CODES],
        language="en",
    )).to_dict()
    return {"link_token": resp["link_token"], "expiration": str(resp.get("expiration", ""))}


def exchange_public_token(store, public_token: str, institution: str = "") -> dict:
    """Swap Link's one-shot token for a lasting one, and store it encrypted."""
    from plaid.model.item_public_token_exchange_request import (
        ItemPublicTokenExchangeRequest,
    )

    resp = _client().item_public_token_exchange(
        ItemPublicTokenExchangeRequest(public_token=public_token)
    ).to_dict()

    item_id = resp["item_id"]
    store.add_plaid_item(item_id, resp["access_token"], institution)
    # The access token is deliberately absent from what we hand back.
    return {"item_id": item_id, "institution": institution}


def _sync_one(store, item: dict) -> dict:
    """Pull one item's changes and apply them. Returns what happened."""
    from plaid.model.transactions_sync_request import TransactionsSyncRequest

    item_id = item["item_id"]
    access_token = store.plaid_token(item_id)
    if not access_token:
        return {"item_id": item_id, "error": "No stored token for this item."}

    client = _client()
    cursor = item.get("cursor") or None
    added, modified, removed = [], [], []
    accounts: dict = {}

    # Plaid pages the change feed; keep asking until it says there is no more.
    # The bound is a safety net against a feed that never reports has_more
    # false, which would otherwise spin until the function times out.
    for _ in range(50):
        kwargs = {"access_token": access_token}
        if cursor:
            kwargs["cursor"] = cursor
        resp = client.transactions_sync(TransactionsSyncRequest(**kwargs)).to_dict()

        added.extend(resp.get("added", []))
        modified.extend(resp.get("modified", []))
        removed.extend(resp.get("removed", []))
        # Accumulated across pages rather than taken from the last one: the
        # account a transaction belongs to supplies its card name, and a later
        # page need not repeat an account an earlier page introduced.
        accounts.update(_accounts_from(resp))
        cursor = resp.get("next_cursor") or cursor
        if not resp.get("has_more"):
            break

    # A removal is Plaid saying that row no longer exists — usually a pending
    # charge that has now posted under a new id. Applied before the additions
    # so the posted version doesn't briefly sit alongside its own pending twin.
    removed_ids = [r.get("transaction_id") for r in removed if r.get("transaction_id")]
    deleted = store.delete_transactions_from(removed_ids)

    # A modified row is the same purchase with better information — a merchant
    # name resolved, an amount finalised. Replacing it means deleting the old
    # one and letting the new one import normally.
    modified_ids = [m.get("transaction_id") for m in modified if m.get("transaction_id")]
    store.delete_transactions_from(modified_ids)

    imported = 0
    results = group_plaid_transactions(added + modified, accounts)
    for result in results:
        imported += ingest(store, result, filename=f"Plaid · {item.get('institution') or item_id}")["imported"]

    store.set_plaid_cursor(item_id, cursor or "")
    return {
        "item_id": item_id,
        "institution": item.get("institution") or "",
        "added": len(added),
        "modified": len(modified),
        "removed": len(removed),
        "deleted": deleted,
        "imported": imported,
    }


def _accounts_from(resp: dict) -> dict:
    return {a["account_id"]: a for a in (resp or {}).get("accounts", [])}


def sync_all(store) -> dict:
    """Sync every linked item, reporting each one's outcome separately.

    One bank being down must not stop the other from syncing, so a failure is
    recorded against its own item and the loop continues.
    """
    items = store.plaid_items()
    if not items:
        return {"items": [], "imported": 0,
                "message": "No banks linked yet."}

    out = []
    for item in items:
        try:
            out.append(_sync_one(store, item))
        except Exception as exc:                     # noqa: BLE001
            store.set_plaid_error(item["item_id"], str(exc))
            out.append({"item_id": item["item_id"],
                        "institution": item.get("institution") or "",
                        "error": str(exc)})
    return {
        "items": out,
        "imported": sum(o.get("imported", 0) for o in out),
        "errors": [o for o in out if o.get("error")],
    }


def unlink(store, item_id: str) -> bool:
    """Forget an item here, and tell Plaid to revoke it.

    Revoking at Plaid matters for more than tidiness: an item left live keeps
    counting against the plan's limit, and leaves a credential valid that
    nothing is using any more. A failure there still removes it locally —
    better to lose track of a revocation than to leave a token in our database
    because someone else's API was down.
    """
    from plaid.model.item_remove_request import ItemRemoveRequest

    token = store.plaid_token(item_id)
    revoked = False
    if token:
        try:
            _client().item_remove(ItemRemoveRequest(access_token=token))
            revoked = True
        except Exception:                            # noqa: BLE001
            revoked = False
    store.delete_plaid_item(item_id)
    return revoked
