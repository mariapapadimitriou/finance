"""Which model answers, and what happens when it can't (AI plan v2).

`ask` sends one question on a route to the default model (Haiku) and, only
when that attempt fails in a way a stronger model can fix, once more to the
escalation model (Sonnet):

- escalate: a server error, timeout or lost connection (after the SDK's own
  retries); a tool call the caller's check rejects or that names no offered
  tool; an answer the caller's `accept` calls low confidence.
- fall back, no escalation: AI off or killed, over a cap, a payload that
  carries something it mustn't, a refusal (a safety decision, not a skill
  one), an answer cut off at max_tokens (the bigger model would be cut off
  too, at 20x the price), a rate limit, or a request the API calls wrong.

Every attempt, and every question that never reached a model, is one row in
`app_ai_usage`. Nothing here raises to her: an `Answer` with `fall_back`
set means "answer with Python".
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass

from . import budget, config, mask, prompts, safety, usage
from . import client as client_mod

ESCALATE_ON = ("server", "timeout", "connection")


@dataclass
class Answer:
    ask_id: str
    route: str
    ok: bool
    reason: str                        # "ok", or why she gets the fallback
    reply: client_mod.Reply | None = None
    model: str | None = None
    attempts: int = 0
    cost_usd: float = 0.0
    filled_text: str = ""              # the reply with her values put back
    filled_calls: list | None = None   # its tool calls, likewise

    @property
    def fall_back(self) -> bool:
        return not self.ok

    @property
    def text(self) -> str:
        """The answer as she reads it: placeholders filled back in."""
        return self.filled_text if self.reply and self.ok else ""

    @property
    def tool_calls(self) -> list:
        return list(self.filled_calls or []) if self.reply and self.ok else []


_USE_ENV = object()


def models_for(route_cfg: dict) -> list[str]:
    chain = [config.DEFAULT_MODEL]
    if route_cfg.get("escalate") and config.ESCALATION_MODEL != config.DEFAULT_MODEL:
        chain.append(config.ESCALATION_MODEL)
    return chain


def _judge(reply, tools, valid_tool, accept) -> str:
    """How this reply ended: ok, refusal, max_tokens, bad_tool, low_confidence."""
    if reply.stop_reason == "refusal":
        return "refusal"
    if reply.stop_reason == "max_tokens":
        return "max_tokens"
    offered = {t["name"] for t in tools or []}
    for call in reply.tool_calls:
        if call["name"] not in offered:
            return "bad_tool"
        if valid_tool is not None and not valid_tool(call):
            return "bad_tool"
    if accept is not None and not accept(reply):
        return "low_confidence"
    return "ok"


ESCALATE_OUTCOMES = ("bad_tool", "low_confidence")
# The reply named a placeholder never issued, or wrote a figure of its own
# (mask.py): her answer comes from Python, on no bigger model.
MASK_OUTCOMES = ("mask_unknown", "mask_number")


def filled(masker, reply) -> tuple[str, str, list]:
    """(outcome, words, tool calls) with her values put back: "ok", or a
    MASK_OUTCOMES reason when the reply can't be used."""
    why = masker.problem(reply.text)
    if why:
        return why, "", []
    try:
        calls = [{**call, "input": masker.fill_value(call.get("input") or {})}
                 for call in reply.tool_calls]
        return "ok", masker.fill(reply.text), calls
    except mask.UnknownPlaceholder:
        return "mask_unknown", "", []


def ask(route: str, prompt: str | None, messages: list, tools: list | None = None, *,
        base, user_id, client=_USE_ENV, accept=None, valid_tool=None,
        now: float | None = None, known: dict | None = None) -> Answer:
    """Ask on `route` with system prompt `prompt` (id@version; None for the
    route's own). `accept(reply) -> bool` and `valid_tool(call) -> bool` are
    the caller's checks (on the reply as the model wrote it, placeholders
    and all): False escalates once, then falls back. `known` is the people,
    cards and shops to mask by name (mask.py); amounts, dates and numbers
    are masked wherever they are."""
    ask_id = uuid.uuid4().hex
    cfg = config.ROUTES.get(route)

    def skip(reason: str, attempt: int = 1, prompt_ref=None, spent: float = 0.0,
             last=None) -> Answer:
        usage.record(base, user_id=user_id, ask_id=ask_id, route=route, outcome=reason,
                     attempt=attempt, prompt=prompt_ref, now=now)
        return Answer(ask_id, route, False, reason, reply=last, attempts=attempt - 1,
                      cost_usd=spent)

    if cfg is None:
        return skip("no_route")
    prompt_ref = prompt or cfg["prompt"]
    ai = client_mod.from_env() if client is _USE_ENV else client
    if ai is None:
        return skip("off", prompt_ref=prompt_ref)
    try:
        system = prompts.load(prompt_ref)
    except prompts.PromptError:
        return skip("no_prompt", prompt_ref=prompt_ref)
    try:
        safety.check(messages, tools or [])
        masker = mask.for_route(cfg, known)
        messages = masker.messages(messages)
        safety.check(messages)
    except safety.UnsafePayload:
        return skip("blocked", prompt_ref=prompt_ref)

    spent = 0.0
    last_reason = "off"
    last_reply = None
    chain = models_for(cfg)
    for attempt, model in enumerate(chain, start=1):
        verdict = budget.check(base, user_id, now=now, escalation=attempt > 1)
        if verdict.fall_back:
            return skip(verdict.reason, attempt, prompt_ref, spent, last_reply)
        began = time.perf_counter()
        try:
            reply = ai.send(model=model, system=system, messages=messages, tools=tools,
                            max_tokens=cfg["max_tokens"], effort=cfg["effort"])
        except safety.UnsafePayload:
            return skip("blocked", attempt, prompt_ref, spent, last_reply)
        except client_mod.ClientError as e:
            latency = int((time.perf_counter() - began) * 1000)
            last_reason = f"error:{e.kind}"
            usage.record(base, user_id=user_id, ask_id=ask_id, route=route, attempt=attempt,
                         model=model, prompt=prompt_ref, latency_ms=latency,
                         outcome=last_reason, request_id=e.request_id, now=now)
            if e.kind in ESCALATE_ON and attempt < len(chain):
                continue
            return Answer(ask_id, route, False, last_reason, reply=last_reply, model=model,
                          attempts=attempt, cost_usd=spent)
        latency = int((time.perf_counter() - began) * 1000)
        cost = config.cost_usd(model, reply.input_tokens, reply.cache_read_tokens,
                               reply.cache_write_tokens, reply.output_tokens)
        spent += cost
        outcome = _judge(reply, tools, valid_tool, accept)
        words, calls = "", []
        if outcome == "ok":
            outcome, words, calls = filled(masker, reply)
        usage.record(base, user_id=user_id, ask_id=ask_id, route=route, attempt=attempt,
                     model=model, prompt=prompt_ref, input_tokens=reply.input_tokens,
                     cache_read_tokens=reply.cache_read_tokens,
                     cache_write_tokens=reply.cache_write_tokens,
                     output_tokens=reply.output_tokens, cost_usd=cost, latency_ms=latency,
                     outcome=outcome, stop_reason=reply.stop_reason,
                     request_id=reply.request_id, now=now)
        if outcome == "ok":
            return Answer(ask_id, route, True, "ok", reply=reply, model=model,
                          attempts=attempt, cost_usd=spent, filled_text=words,
                          filled_calls=calls)
        last_reason, last_reply = outcome, reply
        if outcome in ESCALATE_OUTCOMES and attempt < len(chain):
            continue
        return Answer(ask_id, route, False, outcome, reply=reply, model=model,
                      attempts=attempt, cost_usd=spent)
    return Answer(ask_id, route, False, last_reason, reply=last_reply, attempts=len(chain),
                  cost_usd=spent)
