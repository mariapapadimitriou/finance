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

from .ingest.plaid_source import group_plaid_transactions, is_credit_account
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
    from .ingest.plaid_source import plaid_environment
    try:
        return plaid_environment()
    except RuntimeError:
        # Reported rather than raised: the Banks tab shows this, and a bad
        # value should be visible there rather than blanking the page.
        return os.environ.get("PLAID_ENV", "").strip().lower() or "unset"


def explain(exc: Exception) -> str:
    """Turn a Plaid failure into something you can act on.

    plaid-python stringifies an ApiException as status line, every response
    header, then the JSON body — which buries the one sentence that matters
    under a wall of nginx trivia. The common failures each have a specific
    cause worth naming, and the environment is named too, because the most
    likely cause of bad keys is keys from the other one.
    """
    body = str(exc)
    env = environment()

    if "INVALID_API_KEYS" in body:
        return (
            f"Plaid rejected the credentials for the {env} environment. "
            f"The client ID is the same everywhere but the secret is not — "
            f"each environment has its own, so a sandbox secret fails against "
            f"production and vice versa. Check that PLAID_SECRET is the "
            f"{env} secret from the Plaid dashboard, and that neither value "
            f"picked up a stray space or newline when it was pasted."
        )
    if "INVALID_FIELD" in body or "INVALID_BODY" in body:
        return f"Plaid rejected the request as malformed ({env} environment): {_plaid_message(body)}"
    if "PRODUCTS_NOT_SUPPORTED" in body or "INVALID_PRODUCT" in body:
        return ("This Plaid account isn't enabled for Transactions yet. "
                "Enable the Transactions product in the Plaid dashboard.")
    if "ITEM_LOGIN_REQUIRED" in body:
        return "The bank needs you to sign in again. Reconnect it on this tab."
    if "RATE_LIMIT" in body:
        return "Plaid is rate-limiting this account. Wait a minute and retry."

    return _plaid_message(body) or f"Plaid returned an error ({env} environment)."


def _plaid_message(body: str) -> str:
    """Pull error_message out of a stringified ApiException, if it's in there."""
    import json
    import re
    match = re.search(r"\{.*\}", body, re.S)
    if match:
        try:
            payload = json.loads(match.group(0))
            return (payload.get("error_message")
                    or payload.get("display_message") or "").strip()
        except (ValueError, AttributeError):
            pass
    return body.strip()[:300]


# How much history to ask the bank for when a card is first connected.
#
# Plaid's default is 90 days, which is not enough to see a yearly subscription
# renew, to compare this December with the last one, or to average a category
# over anything but a quarter. 730 days is the maximum Plaid allows.
#
# This is fixed at the moment the Item is created and cannot be raised
# afterwards: Plaid's own guidance is that extending an existing Item's
# history means removing it and linking again. So asking for the maximum up
# front costs nothing and saves a relink later.
DAYS_REQUESTED = 730


def create_link_token(user_id: str = "spendie-user") -> dict:
    """A short-lived token that authorises one run of Plaid Link."""
    from plaid.model.country_code import CountryCode
    from plaid.model.link_token_create_request import LinkTokenCreateRequest
    from plaid.model.link_token_create_request_user import LinkTokenCreateRequestUser
    from plaid.model.link_token_transactions import LinkTokenTransactions
    from plaid.model.products import Products

    resp = _client().link_token_create(LinkTokenCreateRequest(
        user=LinkTokenCreateRequestUser(client_user_id=user_id),
        client_name="Pearl",
        products=[Products("transactions")],
        country_codes=[CountryCode(c) for c in COUNTRY_CODES],
        language="en",
        transactions=LinkTokenTransactions(days_requested=DAYS_REQUESTED),
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
    # From no cursor, the feed is the bank's whole current state rather than
    # changes, and anything stored that it leaves out no longer exists.
    full = cursor is None
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
    # A posted row names the pending row it replaces. Plaid normally reports
    # that pending row as removed too, but not on a sync started over, so the
    # posted row is the reliable signal.
    removed_ids += [a.get("pending_transaction_id") for a in added
                    if a.get("pending_transaction_id")]
    deleted = store.delete_transactions_from(removed_ids)

    # A modified row is the same purchase with better information — a merchant
    # name resolved, an amount finalised. Replacing it means deleting the old
    # one and letting the new one import normally.
    modified_ids = [m.get("transaction_id") for m in modified if m.get("transaction_id")]
    store.delete_transactions_from(modified_ids)

    # Which of this bank's accounts to keep.
    #
    # Some banks' consent screens are all-or-nothing: you grant the whole
    # login, and the chequing, savings and investment accounts arrive beside
    # the card you wanted. So every account the bank hands over is recorded
    # the first time it is seen, with a default — keep the cards, skip the
    # rest — and from then on the stored decision governs. Removing an account
    # in the app writes a decision here, which is what stops the next sync
    # fetching it all over again.
    if full and accounts:
        _replace_superseded(store, item_id, accounts)

    cards_only = store.setting("plaid_cards_only", "1") != "0"
    for aid, a in accounts.items():
        store.note_account(
            aid,
            name=_account_label(a, aid),
            item_id=item_id,
            enabled=(is_credit_account(a) or not cards_only),
            account_type=str(a.get("type") or ""),
            subtype=str(a.get("subtype") or ""),
        )

    # What each account holds, as the bank reports it with every sync — for
    # accounts switched off too: a savings account's balance is worth knowing
    # even when its transactions aren't tracked.
    from datetime import date as _date
    today = _date.today().isoformat()
    for aid, a in accounts.items():
        b = a.get("balances") or {}
        if b.get("current") is not None or b.get("available") is not None:
            store.set_balance(aid, b.get("current"), b.get("available"), b.get("limit"),
                              str(b.get("iso_currency_code") or ""), today)

    rules = store.account_sync_rules()
    blocked = {aid for aid in accounts if not rules.get(aid, {}).get("enabled", True)}
    skipped_accounts = sorted(_account_label(accounts[aid], aid) for aid in blocked)
    if blocked:
        added = [t for t in added if t.get("account_id") not in blocked]
        modified = [t for t in modified if t.get("account_id") not in blocked]

    if full:
        returned: dict[str, tuple[set[str], str]] = {}
        for t in added + modified:
            aid, tid, day = t.get("account_id"), t.get("transaction_id"), str(t.get("date") or "")
            if not (aid and tid and day):
                continue
            ids, earliest = returned.get(aid, (set(), day))
            ids.add(tid)
            returned[aid] = (ids, min(earliest, day))
        deleted += store.reconcile_plaid(returned)

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
        "skipped_accounts": skipped_accounts,
    }


def _mask_of(name: str) -> str:
    import re
    m = re.search(r"••\s*(\d{2,4})\s*$", name or "")
    return m.group(1) if m else ""


def _replace_superseded(store, item_id: str, accounts: dict) -> list[str]:
    """Reconnecting a bank replaces the connection it duplicates.

    Each Plaid reconnect is a new Item with new account ids, so the same
    purchases arrive again under ids nothing de-duplicates against, and the
    old connection goes on syncing beside it. An earlier connection whose
    every account reappears here — same last four digits, same kind — is that
    duplicate: its rows go (this connection brings them back), it is revoked
    at Plaid, and what you decided about its accounts (switched on, joint)
    carries over to their new ids. Two different logins at one bank share no
    accounts, so neither replaces the other.
    """
    new = {(str(a.get("mask") or ""), str(a.get("type") or "").lower()): aid
           for aid, a in accounts.items() if a.get("mask")}
    if not new:
        return []
    rules = store.account_sync_rules()
    joint = store.joint_accounts()
    replaced = []
    for other in store.plaid_items():
        old_id = other["item_id"]
        if old_id == item_id:
            continue
        olds = [r for r in rules.values() if r["item_id"] == old_id]
        keys = [(_mask_of(r["account_name"]), (r["account_type"] or "").lower())
                for r in olds]
        if not olds or not all(k in new and k[0] for k in keys):
            continue
        for r, k in zip(olds, keys):
            if r["decided_by"] == "user":
                store.set_account_sync(new[k], r["enabled"], name=r["account_name"],
                                       item_id=item_id)
            if r["account_id"] in joint:
                store.set_joint(new[k], joint[r["account_id"]])
                store.set_joint(r["account_id"], None)
        store.forget_rows(store.row_ids_for_accounts([r["account_id"] for r in olds]))
        unlink(store, old_id)
        replaced.append(old_id)
    return replaced


def _account_label(account: dict, fallback: str = "") -> str:
    """What to call an account in a list the person reads.

    The mask is part of the name because two cards at one bank are otherwise
    told apart only by an opaque id, and deciding which to drop needs more
    than "Credit Card" twice.
    """
    name = (account.get("official_name") or account.get("name")
            or fallback or "Account")
    mask = account.get("mask")
    return f"{name} ••{mask}" if mask else name


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

    # Once: start every bank's feed over so the reconcile in `_sync_one`
    # clears pending rows left behind by earlier restarted syncs.
    if store.setting("plaid_reconciled") != "1" and store.has_plaid_rows():
        for item in items:
            store.rewind_plaid_cursor(item["item_id"])
            item["cursor"] = None
    store.set_setting("plaid_reconciled", "1")

    out = []
    for item in items:
        try:
            out.append(_sync_one(store, item))
        except Exception as exc:                     # noqa: BLE001
            message = explain(exc)
            store.set_plaid_error(item["item_id"], message)
            out.append({"item_id": item["item_id"],
                        "institution": item.get("institution") or "",
                        "error": message})
    # When the categorising rules have changed since the ledger was last
    # sorted, sort what is already there once — your own choices are kept.
    from .categorize import RULES_VERSION
    from .pipeline import recategorize_all
    if store.setting("categories_version") != str(RULES_VERSION):
        recategorize_all(store)
        store.set_setting("categories_version", RULES_VERSION)
    elif any(o.get("deleted") for o in out):
        # A transfer whose other end was withdrawn is no longer matched.
        from .transfers import apply_transfer_matches
        apply_transfer_matches(store)

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
    # The per-account decisions describe accounts this app can no longer see.
    # Keeping them would mean a relink silently inherits choices made about
    # ids nobody can now inspect.
    store.forget_account_rules(item_id)
    return revoked

def credential_shape() -> dict:
    """What the credentials look like, without saying what they are.

    "Check your secret" is unhelpful when you cannot see the value you set.
    Length and character class give away nothing usable — a 24-character
    lowercase-hex string is every Plaid credential ever issued — but they
    immediately catch a value that is the wrong thing entirely: a truncated
    paste, a swapped pair, or an API key from somewhere else.
    """
    import re

    def shape(name: str) -> dict:
        raw = os.environ.get(name, "")
        value = raw.strip()
        return {
            "set": bool(value),
            "length": len(value),
            # Reported separately so a value that only *looks* fine but was
            # pasted with whitespace is visible even now it is stripped out.
            "had_surrounding_whitespace": raw != value,
            "hex_only": bool(value) and bool(re.fullmatch(r"[0-9a-f]+", value)),
        }

    return {"client_id": shape("PLAID_CLIENT_ID"), "secret": shape("PLAID_SECRET")}


def check_credentials() -> dict:
    """Ask Plaid whether these keys work, without creating anything.

    /institutions/get is authenticated, cheap, and has no side effects — no
    Item, no quota, nothing to clean up — so it can be run as often as it
    takes to get the configuration right.
    """
    if not configured():
        return {"ok": False, "error": "Plaid isn't configured on this deployment."}

    from plaid.model.country_code import CountryCode
    from plaid.model.institutions_get_request import InstitutionsGetRequest

    try:
        resp = _client().institutions_get(InstitutionsGetRequest(
            count=1, offset=0,
            country_codes=[CountryCode(c) for c in COUNTRY_CODES],
        )).to_dict()
    except Exception as exc:                          # noqa: BLE001
        return {"ok": False, "environment": environment(),
                "error": explain(exc), "shape": credential_shape()}

    return {
        "ok": True,
        "environment": environment(),
        "message": (f"These credentials work against Plaid's {environment()} "
                    f"environment."),
        "institutions_visible": resp.get("total", 0),
    }
