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

Masking (Phase 2b, mask.py): her messages and every tool result go to the
model with placeholders for her values ([SHOP1], [AMT1], ...), as the
route's allowlist says. The model's tool calls are filled back in before
`execute` runs (an unknown placeholder goes back to it as an error), and its
words are filled back in as they stream, so no placeholder reaches her. A
reply that names a placeholder never issued, or writes a figure of its own,
ends with ok False and reason "mask_unknown" or "mask_number" (recorded on
that call's usage row): the caller answers with Python.

Escalation to Sonnet happens only before any tool has run (a server error,
a timeout, a lost connection, or a call to a tool that wasn't offered): a
question half answered isn't asked again at 20x the price.
"""

from __future__ import annotations

import time
import uuid

from . import budget, config, mask, prompts, safety, usage
from . import client as client_mod
from .router import ESCALATE_ON, _judge, models_for

_USE_ENV = object()


class ToolInputError(ValueError):
    """The model called a tool with input it can't take. Sent back to the
    model as an error result, so it can try again within the turn limit."""


def run(route: str, messages: list, tools: list, execute, *, base, user_id,
        client=_USE_ENV, now: float | None = None, known: dict | None = None):
    """Yield the events above. `execute(name, input) -> (content, payload)`:
    `input` has her values filled back in; `content` is the text the model
    gets back (already safe to send; masked here), `payload` whatever the
    caller wants handed back in the "tool" event. `known` is the people,
    cards and shops to mask by name (mask.py)."""
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
        masker = mask.for_route(cfg, known)
        messages = masker.messages(messages)
        safety.check(messages)
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
            gate = mask.ReplyGate(masker)
            try:
                for kind, value in ai.stream(model=model, system=system, messages=convo,
                                             tools=tools, max_tokens=cfg["max_tokens"],
                                             effort=cfg["effort"]):
                    if kind == "text":
                        out = gate.feed(value) if value else ""
                        if out:
                            wrote = True
                            yield {"kind": "text", "text": out}
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
            if outcome == "ok" and not reply.tool_calls:
                outcome = masker.problem(reply.text) or "ok"
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
            if outcome != "ok":                 # a refusal, cut off, or a mask rule broken
                if wrote:
                    yield {"kind": "reset"}
                yield end(False, outcome, used=used)
                return
            if not reply.tool_calls:
                tail = gate.finish()
                if tail:
                    yield {"kind": "text", "text": tail}
                yield end(True, "ok", text=masker.fill(reply.text), used=used)
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
                try:
                    inp = masker.fill_value(call["input"] or {})
                except mask.UnknownPlaceholder as e:
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": f"There is no {e}. Use only the placeholders "
                                               "you were given, exactly as written.",
                                    "is_error": True})
                    continue
                yield {"kind": "step", "name": call["name"], "input": inp}
                try:
                    content, payload = execute(call["name"], inp)
                except ToolInputError as e:
                    results.append({"type": "tool_result", "tool_use_id": call["id"],
                                    "content": masker.text(str(e)), "is_error": True})
                    continue
                used += 1
                content = masker.content(content)
                results.append({"type": "tool_result", "tool_use_id": call["id"],
                                "content": content})
                yield {"kind": "tool", "name": call["name"], "input": inp,
                       "payload": payload}
            convo = convo + [{"role": "assistant", "content": reply.content},
                             {"role": "user", "content": results}]
    yield end(False, "error:server", used=used)
