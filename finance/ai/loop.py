"""One question, streamed, with a read-only tool loop (AI Phase 2, /api/ask).

`run` asks the route's model (Haiku first) and, while it calls tools, runs
them with the caller's `execute` and sends their results back, until it
answers in words. It yields what happened, in order, for the caller to turn
into what the phone shows:

    {"kind": "text", "text": words}        part of the answer, as it is written
    {"kind": "reset"}                      the words so far came before a tool
                                           call or an escalation: drop them
    {"kind": "step", "name", "input"}      a tool is about to run
    {"kind": "tool", "name", "input", "payload"}   it ran; `payload` is the
                                           caller's own, unchanged
    {"kind": "end", "ok", "reason", "text", "tools"}   always last

Python decides: the tools are the caller's and only read; the model only
picks them and words the answer. Everything `router.ask` guarantees holds
here too: the kill switch and both caps are checked before every call (an
escalation, and each later turn of the same question, only against the $
cap), every call is one `app_ai_usage` row under the question's ask_id,
nothing unsafe is sent (`safety.check`, again in the client), and nothing
raises to her: `end` with ok False means "answer with Python".

Escalation to Sonnet happens only before any tool has run (a server error,
a timeout, a lost connection, or a call to a tool that wasn't offered): a
question half answered isn't asked again at 20x the price.
"""

from __future__ import annotations

import time
import uuid

from . import budget, config, prompts, safety, usage
from . import client as client_mod
from .router import ESCALATE_ON, _judge, models_for

_USE_ENV = object()


class ToolInputError(ValueError):
    """The model called a tool with input it can't take. Sent back to the
    model as an error result, so it can try again within the turn limit."""


def run(route: str, messages: list, tools: list, execute, *, base, user_id,
        client=_USE_ENV, now: float | None = None):
    """Yield the events above. `execute(name, input) -> (content, payload)`:
    `content` is the text the model gets back (already safe to send),
    `payload` whatever the caller wants handed back in the "tool" event."""
    ask_id = uuid.uuid4().hex
    cfg = config.ROUTES.get(route)

    def skip(reason: str, attempt: int = 1, prompt_ref=None):
        usage.record(base, user_id=user_id, ask_id=ask_id, route=route, outcome=reason,
                     attempt=attempt, prompt=prompt_ref, now=now)

    def end(ok: bool, reason: str, text: str = "", used: int = 0):
        return {"kind": "end", "ok": ok, "reason": reason, "text": text, "tools": used,
                "ask_id": ask_id}

    if cfg is None:
        skip("no_route")
        yield end(False, "no_route")
        return
    prompt_ref = cfg["prompt"]
    ai = client_mod.from_env() if client is _USE_ENV else client
    if ai is None:
        skip("off", prompt_ref=prompt_ref)
        yield end(False, "off")
        return
    try:
        system = prompts.load(prompt_ref)
    except prompts.PromptError:
        skip("no_prompt", prompt_ref=prompt_ref)
        yield end(False, "no_prompt")
        return
    try:
        safety.check(messages, tools)
    except safety.UnsafePayload:
        skip("blocked", prompt_ref=prompt_ref)
        yield end(False, "blocked")
        return

    chain = models_for(cfg)
    used = 0
    for attempt, model in enumerate(chain, start=1):
        convo = list(messages)
        turns = 0
        while True:
            verdict = budget.check(base, user_id, now=now, escalation=attempt > 1 or turns > 0)
            if verdict.fall_back:
                skip(verdict.reason, attempt, prompt_ref)
                yield end(False, verdict.reason, used=used)
                return
            began = time.perf_counter()
            reply = None
            wrote = False
            try:
                for kind, value in ai.stream(model=model, system=system, messages=convo,
                                             tools=tools, max_tokens=cfg["max_tokens"],
                                             effort=cfg["effort"]):
                    if kind == "text":
                        if value:
                            wrote = True
                            yield {"kind": "text", "text": value}
                    else:
                        reply = value
            except safety.UnsafePayload:
                if wrote:
                    yield {"kind": "reset"}
                skip("blocked", attempt, prompt_ref)
                yield end(False, "blocked", used=used)
                return
            except client_mod.ClientError as e:
                latency = int((time.perf_counter() - began) * 1000)
                usage.record(base, user_id=user_id, ask_id=ask_id, route=route, attempt=attempt,
                             model=model, prompt=prompt_ref, latency_ms=latency,
                             outcome=f"error:{e.kind}", request_id=e.request_id, now=now)
                if wrote:
                    yield {"kind": "reset"}
                if e.kind in ESCALATE_ON and used == 0 and attempt < len(chain):
                    break                                   # once more, on Sonnet
                yield end(False, f"error:{e.kind}", used=used)
                return
            latency = int((time.perf_counter() - began) * 1000)
            cost = config.cost_usd(model, reply.input_tokens, reply.cache_read_tokens,
                                   reply.cache_write_tokens, reply.output_tokens)
            outcome = _judge(reply, tools, None, None)
            usage.record(base, user_id=user_id, ask_id=ask_id, route=route, attempt=attempt,
                         model=model, prompt=prompt_ref, input_tokens=reply.input_tokens,
                         cache_read_tokens=reply.cache_read_tokens,
                         cache_write_tokens=reply.cache_write_tokens,
                         output_tokens=reply.output_tokens, cost_usd=cost, latency_ms=latency,
                         outcome=outcome, stop_reason=reply.stop_reason,
                         request_id=reply.request_id, now=now)
            if outcome == "bad_tool":
                if wrote:
                    yield {"kind": "reset"}
                if used == 0 and attempt < len(chain):
                    break                                   # once more, on Sonnet
                yield end(False, outcome, used=used)
                return
            if outcome != "ok":                             # a refusal, or cut off
                if wrote:
                    yield {"kind": "reset"}
                yield end(False, outcome, used=used)
                return
            if not reply.tool_calls:
                yield end(True, "ok", text=reply.text, used=used)
                return
            # Words before a tool call are a preamble, not the answer.
            if wrote:
                yield {"kind": "reset"}
            turns += 1
            if turns > config.MAX_TOOL_TURNS:
                yield end(False, "too_many_tools", used=used)
                return
            results = []
            for call in reply.tool_calls:
                yield {"kind": "step", "name": call["name"], "input": call["input"]}
                try:
                    content, payload = execute(call["name"], call["input"] or {})
                except ToolInputError as e:
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": str(e), "is_error": True})
                    continue
                used += 1
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": content})
                yield {"kind": "tool", "name": call["name"], "input": call["input"],
                       "payload": payload}
            convo = convo + [{"role": "assistant", "content": reply.content},
                             {"role": "user", "content": results}]
    yield end(False, "error:server", used=used)
