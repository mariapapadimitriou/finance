"""Optional Claude layer.

The rule engine produces every number on its own; this turns those numbers into
a short written read. It is strictly additive — if no API key is present the app
renders the rule output directly and nothing here runs.

Privacy note, because it matters here: calling this sends aggregates to
Anthropic's API. We deliberately send category totals, merchant names and the
finding summaries — never individual transaction rows, account numbers, or
anything identifying you. `build_payload` is the whole of what leaves the
machine, and it is returned to the UI for inspection before any call is made.
"""

from __future__ import annotations

import json
import os

MODEL = os.environ.get("CLAUDE_MODEL", "claude-sonnet-5")
MAX_TOKENS = 1200

SYSTEM_PROMPT = """You are a plain-spoken personal finance analyst. You are \
given pre-computed aggregates from someone's own credit card history, plus \
findings from a deterministic savings engine.

Write a short read of their spending: what stands out, what is driving it, and \
which of the findings actually deserve attention first. Rules:

- Every number you cite must come from the data given. Never invent a figure.
- Rank by what saves the most for the least disruption, and say so explicitly.
- Be concrete: name merchants and amounts.
- No moralising about coffee or avocado toast. Treat the person as an adult \
making deliberate trade-offs.
- If the data is thin (under three months), say so and keep conclusions tentative.
- 250 words maximum, in short paragraphs. No headings, no bullet lists."""


def is_available() -> bool:
    if not os.environ.get("ANTHROPIC_API_KEY"):
        return False
    try:
        import anthropic  # noqa: F401
        return True
    except ImportError:
        return False


def status() -> dict:
    key = bool(os.environ.get("ANTHROPIC_API_KEY"))
    try:
        import anthropic  # noqa: F401
        lib = True
    except ImportError:
        lib = False

    if key and lib:
        return {"available": True, "model": MODEL,
                "detail": "Claude narrative enabled."}

    missing = []
    if not lib:
        missing.append("pip install anthropic")
    if not key:
        missing.append("export ANTHROPIC_API_KEY=...")

    return {
        "available": False,
        "model": MODEL,
        "detail": "Optional — the rule engine works without it. To enable: "
                  + "; ".join(missing) + ".",
    }


def build_payload(summary: dict, findings: list[dict], recurring: list[dict]) -> dict:
    """Exactly what would be sent to the API. Aggregates only — no raw rows."""
    return {
        "months_of_history": len(summary.get("months", [])),
        "latest_month": summary.get("latest_month"),
        "latest_month_spend": summary.get("latest_spend"),
        "average_monthly_spend": summary.get("average_monthly_spend"),
        "fixed_vs_discretionary": summary.get("split", {}),
        "monthly_trend": [
            {"month": m["month"], "spend": m["spend"]}
            for m in summary.get("monthly", [])[-12:]
        ],
        "categories_this_month": [
            {"category": c["category"], "amount": c["amount"], "share": c["share"]}
            for c in summary.get("categories", [])[:12]
        ],
        "biggest_changes": [
            {"category": c["category"], "amount": c["amount"],
             "baseline": c["baseline"], "delta": c["delta"]}
            for c in summary.get("changes", [])[:6]
        ],
        "top_merchants": [
            {"merchant": m["merchant"], "amount": m["amount"],
             "transactions": m["transactions"]}
            for m in summary.get("merchants", [])[:10]
        ],
        "active_subscriptions": [
            {"merchant": r["merchant"], "cadence": r["cadence"],
             "amount": r["amount"], "annual_cost": r["annual_cost"]}
            for r in recurring if r.get("active")
        ][:20],
        "findings": [
            {"title": f["title"], "detail": f["detail"], "kind": f["kind"],
             "annual_saving": f["annual_saving"], "confidence": f["confidence"],
             "effort": f["effort"], "assumption": f.get("assumption", "")}
            for f in findings[:10]
        ],
    }


def analyze(summary: dict, findings: list[dict], recurring: list[dict]) -> dict:
    """Ask Claude for a written read. Returns {available, text, payload}."""
    payload = build_payload(summary, findings, recurring)

    if not is_available():
        return {"available": False, "text": "", "payload": payload,
                **status()}

    import anthropic

    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    message = client.messages.create(
        model=MODEL,
        max_tokens=MAX_TOKENS,
        system=SYSTEM_PROMPT,
        messages=[{
            "role": "user",
            "content": "Here are my spending aggregates and the savings findings "
                       "from my own analysis. Give me your read.\n\n"
                       + json.dumps(payload, indent=2),
        }],
    )

    text = "".join(block.text for block in message.content if block.type == "text")
    return {"available": True, "text": text.strip(), "payload": payload,
            "model": MODEL}
