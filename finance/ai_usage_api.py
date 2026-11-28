"""Profile › AI usage, owner only (AU-01, THL-308 / THL-309; Pearl redesign
canvas, Profile page, "AI-Usage").

This month's cost, how many questions reached the model, how often the
bigger model was needed, who is at the $ cap, the highest cost per person
and her own, from `finance/ai/usage.summary()`.

Only the owner sees it. The owner is whoever signs in with an email listed
in the server's `PEARL_OWNER_EMAILS` (comma-separated, set in Vercel; no
email lives in the code). Anyone else gets 404, as if it weren't there, and
Profile hides the row; ordinary users never see dollars. A local ledger
with no accounts (never hosted: the sign-in gate answers first there) is
the owner's own machine, so it counts as the owner.
"""

from __future__ import annotations

import os

from flask import current_app, g, jsonify

from .api import bp

OWNER_ENV = "PEARL_OWNER_EMAILS"


def owner_emails() -> set[str]:
    raw = os.environ.get(OWNER_ENV, "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def is_owner(user) -> bool:
    if user is None:
        return not current_app.config.get("HOSTED")
    email = (getattr(user, "email", None) or "").strip().lower()
    return bool(email) and email in owner_emails()


def _people(base) -> int | None:
    try:
        with base.conn(standalone=True) as c:
            row = c.execute("SELECT COUNT(*) AS n FROM app_users").fetchone()
        return int(row["n"] or 0)
    except Exception:                                    # noqa: BLE001
        return None                                      # no accounts here


def page(base, user, now: float | None = None) -> dict:
    from datetime import datetime, timezone

    from .ai import config, usage
    month, _ = usage.periods(now)
    s = usage.summary(base, month)
    cap = config.monthly_cap_usd()
    per = s["per_user"]
    mine = next((u for u in per if u["user_id"] == (user.id if user is not None else None)), None)
    people = _people(base)
    first = datetime.strptime(month + "-01", "%Y-%m-%d").replace(tzinfo=timezone.utc)
    return {"month": month, "month_name": first.strftime("%B"),
            "cost_usd": s["total_cost_usd"], "questions": s["asked"],
            "escalated": s["escalated"], "escalation_rate": s["escalation_rate"],
            "at_cap": sum(1 for u in per if cap > 0 and u["cost_usd"] >= cap),
            "people": people if people else len(per),
            "cap_usd": cap,
            "highest_usd": max((u["cost_usd"] for u in per), default=0.0),
            "you_usd": mine["cost_usd"] if mine else 0.0}


@bp.get("/ai-usage")
def ai_usage():
    user = g.get("user")
    if not is_owner(user):
        return jsonify({"error": "Not found."}), 404
    return jsonify(page(current_app.config["STORE"], user))
