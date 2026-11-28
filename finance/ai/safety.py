"""What may never go to the model (AI plan v2, data minimisation).

Sent: her words and what Python already worked out, with her amounts,
dates, people, cards and shops as placeholders (`mask.py`, Phase 2b; a
route's allowlist may send some kinds as they are). Never sent, on any
route: account or card numbers, Plaid tokens or ids,
passwords, keys. `check` refuses a payload that carries one, so a caller's
mistake turns into a fallback, not a leak; `redact` masks long digit runs for
callers that want to pass text through anyway.
"""

from __future__ import annotations

import re

# Plaid access/public/link tokens, and Anthropic or other secret-looking keys.
_TOKEN = re.compile(r"\b(?:access|public|link)-(?:sandbox|development|production)-[0-9a-f-]{8,}",
                    re.IGNORECASE)
_SECRET = re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")
# Eight or more digits in a row (account, transit, card numbers), or a card
# number written in fours. Dates (2026-11-27) and amounts ($1,234.56) pass.
_LONG_DIGITS = re.compile(r"(?<![\d.])\d{8,}(?![\d])")
_CARD = re.compile(r"\b\d{4}([ -])\d{4}\1\d{4}\1\d{1,7}\b")

# Keys that never belong in anything sent, whatever their value.
_KEY = re.compile(r"(access_token|public_token|link_token|item_id|account_number|"
                  r"routing|transit|iban|card_number|password|secret|api_key|plaid)",
                  re.IGNORECASE)


class UnsafePayload(ValueError):
    """A payload carried something that must not leave the server."""


def _strings(value, path="$"):
    if isinstance(value, str):
        yield path, value
    elif isinstance(value, dict):
        for k, v in value.items():
            if isinstance(k, str) and _KEY.search(k):
                raise UnsafePayload(f"{path}.{k}: key not allowed")
            yield from _strings(v, f"{path}.{k}")
    elif isinstance(value, (list, tuple)):
        for i, v in enumerate(value):
            yield from _strings(v, f"{path}[{i}]")
    elif hasattr(value, "model_dump"):          # an SDK block replayed in a tool loop
        yield from _strings(value.model_dump(), path)
    elif value is not None and not isinstance(value, (int, float, bool)):
        yield path, str(value)


def problem(text: str) -> str | None:
    """Why this text may not be sent, or None."""
    if _TOKEN.search(text):
        return "a Plaid token"
    if _SECRET.search(text):
        return "a secret key"
    if _CARD.search(text):
        return "a card number"
    if _LONG_DIGITS.search(text):
        return "an account number"
    return None


def check(*payloads) -> None:
    """Raise UnsafePayload if anything in these (strings, dicts, lists:
    messages, tools, a system prompt) must not be sent."""
    for payload in payloads:
        for path, text in _strings(payload):
            why = problem(text)
            if why:
                raise UnsafePayload(f"{path}: looks like {why}")


def redact(text: str) -> str:
    """Mask what `check` would refuse, keeping a card or account's last four."""
    text = _TOKEN.sub("[token]", text)
    text = _SECRET.sub("[key]", text)
    text = _CARD.sub(lambda m: "••••" + re.sub(r"\D", "", m.group(0))[-4:], text)
    return _LONG_DIGITS.sub(lambda m: "••••" + m.group(0)[-4:], text)
