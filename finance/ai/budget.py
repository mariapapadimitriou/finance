"""Whether an account may ask the model now: the kill switch, a monthly $
cap and a daily request cap (AI plan v2).

Never raises to her. Over a cap, or with AI off, the answer is a `Verdict`
that says fall back, and the caller answers with Python and templates.
"""

from __future__ import annotations

import os
from dataclasses import dataclass

from . import config, usage


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    reason: str = "ok"        # ok | off | killed | over_budget | over_daily

    @property
    def fall_back(self) -> bool:
        return not self.allowed


def killed(base) -> bool:
    """The global kill switch: PEARL_AI_OFF=1 in the environment, or the
    app_secrets row `ai_off` set to 1 (flipped without a redeploy)."""
    if os.environ.get(config.KILL_ENV, "").strip() in ("1", "true", "yes", "on"):
        return True
    try:
        with base.conn(standalone=True) as c:
            row = c.execute("SELECT value FROM app_secrets WHERE name = ?",
                            (config.KILL_SECRET,)).fetchone()
    except Exception:                                    # noqa: BLE001
        return False                 # no app_secrets yet: nobody turned it off
    return bool(row) and str(row["value"]).strip() == "1"


def set_killed(base, off: bool) -> None:
    with base.conn(standalone=True) as c:
        c.execute_quietly("INSERT INTO app_secrets (name, value) VALUES (?, ?) "
                          "ON CONFLICT(name) DO UPDATE SET value = excluded.value",
                          (config.KILL_SECRET, "1" if off else "0"))


def check(base, user_id, now: float | None = None, escalation: bool = False) -> Verdict:
    """May this account make one more model call? An escalation is the same
    question asked again, so only the kill switch and the $ cap apply."""
    try:
        if killed(base):
            return Verdict(False, "killed")
        month, day = usage.periods(now)
        if usage.month_cost(base, user_id, month) >= config.monthly_cap_usd():
            return Verdict(False, "over_budget")
        if not escalation and usage.day_requests(base, user_id, day) >= config.daily_requests():
            return Verdict(False, "over_daily")
    except Exception:                                    # noqa: BLE001
        # Can't tell what she has spent: fail closed, never charge blind.
        return Verdict(False, "over_budget")
    return Verdict(True)
