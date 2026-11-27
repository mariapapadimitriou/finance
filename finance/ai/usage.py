"""What every AI call cost: one row per attempt, in `app_ai_usage`.

It lives with the account list in the original database (`base`, as in
`finance/users.py`), not in each ledger: one table covers every account, so
cost per user per month and the escalation rate are one query, and emptying
or deleting a ledger (Start over, THL-116) never loses the bill. A row holds
no words, only an account id, which route, model and prompt, token counts,
$, time taken and how it ended.

Rows are written in their own short transaction and quietly (they are
bookkeeping, not a change to anyone's ledger), so a failed request doesn't
lose them and they don't move the ledger's version.
"""

from __future__ import annotations

import time
from datetime import datetime, timezone

_TABLE = """
CREATE TABLE IF NOT EXISTS app_ai_usage (
    id                 INTEGER PRIMARY KEY AUTOINCREMENT,
    at                 REAL NOT NULL,
    month              TEXT NOT NULL,
    day                TEXT NOT NULL,
    user_id            INTEGER,
    ask_id             TEXT NOT NULL,
    attempt            INTEGER NOT NULL DEFAULT 1,
    route              TEXT NOT NULL,
    model              TEXT,
    prompt             TEXT,
    input_tokens       INTEGER NOT NULL DEFAULT 0,
    cache_read_tokens  INTEGER NOT NULL DEFAULT 0,
    cache_write_tokens INTEGER NOT NULL DEFAULT 0,
    output_tokens      INTEGER NOT NULL DEFAULT 0,
    cost_usd           REAL NOT NULL DEFAULT 0,
    latency_ms         INTEGER NOT NULL DEFAULT 0,
    outcome            TEXT NOT NULL,
    stop_reason        TEXT,
    request_id         TEXT
);
CREATE INDEX IF NOT EXISTS idx_app_ai_usage_user_month ON app_ai_usage (user_id, month);
CREATE INDEX IF NOT EXISTS idx_app_ai_usage_user_day ON app_ai_usage (user_id, day);
"""

# Outcomes that never reached the model: they cost nothing and don't count
# towards the daily cap.
SKIPPED = ("off", "killed", "over_budget", "over_daily", "blocked", "no_prompt")

_ready: set = set()


def ensure_table(base) -> None:
    key = (base.path, base.url, base.schema)
    if key in _ready:
        return
    # One quiet statement at a time: making the table isn't a change to
    # anyone's ledger, so it mustn't move the ledger's version.
    with base.conn(standalone=True) as c:
        for statement in filter(str.strip, _TABLE.split(";")):
            c.execute_quietly(statement)
    _ready.add(key)


def periods(now: float | None = None) -> tuple[str, str]:
    """(month, day) in UTC: "2026-11", "2026-11-27"."""
    d = datetime.fromtimestamp(time.time() if now is None else now, tz=timezone.utc)
    return d.strftime("%Y-%m"), d.strftime("%Y-%m-%d")


def record(base, *, user_id, ask_id: str, route: str, outcome: str, attempt: int = 1,
           model: str | None = None, prompt: str | None = None,
           input_tokens: int = 0, cache_read_tokens: int = 0, cache_write_tokens: int = 0,
           output_tokens: int = 0, cost_usd: float = 0.0, latency_ms: int = 0,
           stop_reason: str | None = None, request_id: str | None = None,
           now: float | None = None) -> None:
    ensure_table(base)
    at = time.time() if now is None else now
    month, day = periods(at)
    with base.conn(standalone=True) as c:
        c.execute_quietly(
            "INSERT INTO app_ai_usage (at, month, day, user_id, ask_id, attempt, route, model, "
            "prompt, input_tokens, cache_read_tokens, cache_write_tokens, output_tokens, "
            "cost_usd, latency_ms, outcome, stop_reason, request_id) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (at, month, day, None if user_id is None else int(user_id), ask_id, int(attempt),
             route, model, prompt, int(input_tokens), int(cache_read_tokens),
             int(cache_write_tokens), int(output_tokens), float(cost_usd), int(latency_ms),
             outcome, stop_reason, request_id))


def month_cost(base, user_id, month: str) -> float:
    ensure_table(base)
    with base.conn(standalone=True) as c:
        row = c.execute("SELECT COALESCE(SUM(cost_usd), 0) AS d FROM app_ai_usage "
                        "WHERE user_id = ? AND month = ?", (int(user_id), month)).fetchone()
    return float(row["d"] or 0)


def day_requests(base, user_id, day: str) -> int:
    """Questions that reached the model today (an escalation is the same one)."""
    ensure_table(base)
    marks = ", ".join("?" for _ in SKIPPED)
    with base.conn(standalone=True) as c:
        row = c.execute(f"SELECT COUNT(*) AS n FROM app_ai_usage WHERE user_id = ? AND day = ? "
                        f"AND attempt = 1 AND outcome NOT IN ({marks})",
                        (int(user_id), day, *SKIPPED)).fetchone()
    return int(row["n"] or 0)


def rows(base, user_id=None) -> list[dict]:
    ensure_table(base)
    with base.conn(standalone=True) as c:
        if user_id is None:
            got = c.execute("SELECT * FROM app_ai_usage ORDER BY id").fetchall()
        else:
            got = c.execute("SELECT * FROM app_ai_usage WHERE user_id = ? ORDER BY id",
                            (int(user_id),)).fetchall()
    return [dict(r) for r in got]


def summary(base, month: str | None = None) -> dict:
    """Read-only figures for the cost page (a later phase): per account and
    month, what was spent, how many questions reached the model, how many
    escalated and how many fell back; and the same in total."""
    ensure_table(base)
    marks = ", ".join("?" for _ in SKIPPED)
    where, args = ("WHERE month = ?", (month,)) if month else ("", ())
    with base.conn(standalone=True) as c:
        got = c.execute(
            f"SELECT user_id, month, "
            f"  SUM(cost_usd) AS cost_usd, "
            f"  COUNT(DISTINCT CASE WHEN attempt = 1 AND outcome NOT IN ({marks}) "
            f"        THEN ask_id END) AS asked, "
            f"  COUNT(DISTINCT CASE WHEN attempt > 1 THEN ask_id END) AS escalated, "
            f"  COUNT(DISTINCT CASE WHEN outcome IN ({marks}) THEN ask_id END) AS skipped, "
            f"  SUM(input_tokens) AS input_tokens, SUM(cache_read_tokens) AS cache_read_tokens, "
            f"  SUM(cache_write_tokens) AS cache_write_tokens, SUM(output_tokens) AS output_tokens "
            f"FROM app_ai_usage {where} GROUP BY user_id, month ORDER BY month, user_id",
            (*SKIPPED, *SKIPPED, *args)).fetchall()
    per_user = []
    for r in got:
        asked = int(r["asked"] or 0)
        escalated = int(r["escalated"] or 0)
        per_user.append({
            "user_id": r["user_id"], "month": r["month"],
            "cost_usd": round(float(r["cost_usd"] or 0), 6),
            "asked": asked, "escalated": escalated, "skipped": int(r["skipped"] or 0),
            "escalation_rate": round(escalated / asked, 4) if asked else 0.0,
            "input_tokens": int(r["input_tokens"] or 0),
            "cache_read_tokens": int(r["cache_read_tokens"] or 0),
            "cache_write_tokens": int(r["cache_write_tokens"] or 0),
            "output_tokens": int(r["output_tokens"] or 0),
        })
    asked = sum(u["asked"] for u in per_user)
    escalated = sum(u["escalated"] for u in per_user)
    return {
        "per_user": per_user,
        "total_cost_usd": round(sum(u["cost_usd"] for u in per_user), 6),
        "asked": asked,
        "escalated": escalated,
        "escalation_rate": round(escalated / asked, 4) if asked else 0.0,
    }
