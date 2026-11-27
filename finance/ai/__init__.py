"""Pearl's AI gateway (AI plan v2, 2026-11-27; Phase 1: no UI, no endpoints).

Python decides: totals, detections and what answers are allowed. The model
only understands her words, phrases answers and ranks among options Python
allows. Every iPhone gets the same AI, through the server.

- `config`  models, prices, routes, default caps (the only place model IDs live)
- `client`  the Anthropic SDK; off with no ANTHROPIC_API_KEY
- `router`  `ask(...)`: Haiku first, Sonnet only on failure or low confidence
- `prompts` frozen, versioned system prompts (ask@1 → prompts/ask_v1.md)
- `budget`  kill switch, monthly $ cap, daily request cap; never raises
- `usage`   app_ai_usage rows and the read-only cost summary
- `safety`  what never goes to the model (account numbers, Plaid tokens)
"""

from .router import Answer, ask  # noqa: F401
