"""Pearl's AI gateway settings: models, prices, routes and the default caps.

The one place model IDs live (AI plan v2, 2026-11-27). Nothing else in the
code names a model; `router.py` reads them from here.

Python decides (totals, detections, what is allowed). The model only
understands words, phrases answers and ranks among options Python allows, so
a small cheap model is the default and the bigger one is only for failures.
"""

from __future__ import annotations

import os

# ── Models ───────────────────────────────────────────────────────────────
DEFAULT_MODEL = "claude-haiku-5-5"
ESCALATION_MODEL = "claude-sonnet-5-5"

# ── Prices, US $ per 1M tokens (Anthropic list prices, cached 2026-11-03) ──
# Cache reads are 0.1x input; 5-minute cache writes 1.25x input. Haiku 5.5
# has a second rate card for prompts over 100K tokens. Batch is 50% off.
CACHE_READ_FACTOR = 0.10
CACHE_WRITE_FACTOR = 1.25
BATCH_FACTOR = 0.50
LONG_PROMPT_TOKENS = 100_000

PRICES = {
    # model: (input, output, long-prompt input, long-prompt output)
    "claude-haiku-5-5": (0.10, 0.50, 0.50, 2.50),
    "claude-sonnet-5-5": (2.00, 10.00, 2.00, 10.00),
}

# ── Routes ───────────────────────────────────────────────────────────────
# One per kind of question. `prompt` is a frozen system prompt (id@version,
# see prompts/). `effort` is low: Python has done the thinking already.
# `escalate` says whether a failure on the default model may be retried on
# the escalation model (about 20x the price).
ROUTES = {
    "ask": {"prompt": "ask@1", "max_tokens": 1024, "effort": "low", "escalate": True},
}

# ── Caps ─────────────────────────────────────────────────────────────────
# Per account, per calendar month (UTC), in US $: $0.50, set by the product
# owner on 2026-11-27. An account that has spent $0.50 this month falls back
# to Python answers until the month turns. Requests per day is a guard
# against loops, not a price; the product owner may change it.
MONTHLY_CAP_USD_DEFAULT = 0.50
DAILY_REQUESTS_DEFAULT = 60

KEY_ENV = "ANTHROPIC_API_KEY"
KILL_ENV = "PEARL_AI_OFF"                 # "1" turns AI off everywhere
MONTHLY_CAP_ENV = "PEARL_AI_MONTHLY_CAP_USD"
DAILY_REQUESTS_ENV = "PEARL_AI_DAILY_REQUESTS"
KILL_SECRET = "ai_off"                    # app_secrets row; "1" turns AI off

# Seconds to wait for one answer, and the SDK's own retries (429, 5xx).
TIMEOUT_SECONDS = 20.0
MAX_RETRIES = 1


def _number(env: str, default, kind):
    raw = os.environ.get(env)
    if raw is None or not raw.strip():
        return default
    try:
        value = kind(raw)
    except ValueError:
        return default
    return value if value >= 0 else default


def monthly_cap_usd() -> float:
    return _number(MONTHLY_CAP_ENV, MONTHLY_CAP_USD_DEFAULT, float)


def daily_requests() -> int:
    return _number(DAILY_REQUESTS_ENV, DAILY_REQUESTS_DEFAULT, int)


def cost_usd(model: str, input_tokens: int, cache_read: int, cache_write: int,
             output_tokens: int, batch: bool = False) -> float:
    """What one answer cost, from the usage the API reported. `input_tokens`
    is the uncached part only, as the API reports it."""
    if model not in PRICES:
        return 0.0
    price_in, price_out, long_in, long_out = PRICES[model]
    prompt = input_tokens + cache_read + cache_write
    if prompt > LONG_PROMPT_TOKENS:
        price_in, price_out = long_in, long_out
    dollars = (input_tokens * price_in
               + cache_read * price_in * CACHE_READ_FACTOR
               + cache_write * price_in * CACHE_WRITE_FACTOR
               + output_tokens * price_out) / 1_000_000
    if batch:
        dollars *= BATCH_FACTOR
    return round(dollars, 8)
