"""The one place Pearl talks to Anthropic (AI plan v2, 2026-11-27).

The key is the server's own, `ANTHROPIC_API_KEY`, read from the environment
here and nowhere else; no phone ever holds it. With no key (or no SDK) there
is no client: `from_env()` is None, AI is simply off, and callers fall back
to Python answers. The key is passed to the SDK explicitly so it never picks
up some other credential lying around on the machine.

Every payload is checked by `safety.check` before it leaves: no account or
card numbers, no Plaid tokens. A failed call comes back as a `ClientError`
with a plain `kind`; a refusal or a cut-off answer comes back as a `Reply`
whose `stop_reason` says so. Deciding what to do about either is the
router's job.

Only `finance/ai/` imports `anthropic` (a test checks).
"""

from __future__ import annotations

import contextlib
import os
from dataclasses import dataclass, field

from . import config, safety


class ClientError(Exception):
    """A call that failed. `kind` is one of: bad_request, auth, permission,
    not_found, rate_limited, server, timeout, connection, other."""

    def __init__(self, kind: str, message: str = "", request_id: str | None = None):
        super().__init__(f"{kind}: {message}" if message else kind)
        self.kind = kind
        self.request_id = request_id


@dataclass
class Reply:
    model: str
    stop_reason: str | None
    text: str = ""
    tool_calls: list = field(default_factory=list)     # [{id, name, input}]
    content: list = field(default_factory=list)        # the raw blocks, for a tool loop
    input_tokens: int = 0                              # uncached part of the prompt
    cache_read_tokens: int = 0
    cache_write_tokens: int = 0
    output_tokens: int = 0
    request_id: str | None = None
    refusal_category: str | None = None


def build_request(model: str, system: str, messages: list, tools: list | None,
                  max_tokens: int, effort: str) -> dict:
    """The Messages API parameters, laid out to cache well: tools in a fixed
    order (by name), then the frozen system prompt with the cache breakpoint
    on it, so tools + system are one cached prefix; only messages vary."""
    params = {
        "model": model,
        "max_tokens": int(max_tokens),
        "system": [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        "messages": messages,
        "output_config": {"effort": effort},
    }
    if tools:
        params["tools"] = sorted(tools, key=lambda t: t["name"])
    return params


def _n(value) -> int:
    return int(value or 0)


def to_reply(message) -> Reply:
    """A Reply from the SDK's Message."""
    text, calls = [], []
    for block in message.content or []:
        if block.type == "text":
            text.append(block.text)
        elif block.type == "tool_use":
            calls.append({"id": block.id, "name": block.name, "input": block.input})
    used = message.usage
    details = getattr(message, "stop_details", None)
    return Reply(
        model=message.model,
        stop_reason=message.stop_reason,
        text="".join(text),
        tool_calls=calls,
        content=list(message.content or []),
        input_tokens=_n(getattr(used, "input_tokens", 0)),
        cache_read_tokens=_n(getattr(used, "cache_read_input_tokens", 0)),
        cache_write_tokens=_n(getattr(used, "cache_creation_input_tokens", 0)),
        output_tokens=_n(getattr(used, "output_tokens", 0)),
        request_id=getattr(message, "_request_id", None),
        refusal_category=getattr(details, "category", None) if details else None,
    )


class Client:
    """Anthropic, through the official SDK."""

    def __init__(self, api_key: str):
        import anthropic
        self._sdk = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=config.TIMEOUT_SECONDS,
                                           max_retries=config.MAX_RETRIES)

    @contextlib.contextmanager
    def _mapped(self):
        """The SDK's errors as a ClientError with a plain kind."""
        a = self._sdk
        try:
            yield
        except a.BadRequestError as e:
            raise ClientError("bad_request", e.message, getattr(e, "request_id", None)) from e
        except a.AuthenticationError as e:
            raise ClientError("auth", e.message, getattr(e, "request_id", None)) from e
        except a.PermissionDeniedError as e:
            raise ClientError("permission", e.message, getattr(e, "request_id", None)) from e
        except a.NotFoundError as e:
            raise ClientError("not_found", e.message, getattr(e, "request_id", None)) from e
        except a.RateLimitError as e:
            raise ClientError("rate_limited", e.message, getattr(e, "request_id", None)) from e
        except a.APIStatusError as e:
            kind = "server" if e.status_code >= 500 else "other"
            raise ClientError(kind, e.message, getattr(e, "request_id", None)) from e
        except a.APITimeoutError as e:            # before APIConnectionError, its parent
            raise ClientError("timeout", str(e)) from e
        except a.APIConnectionError as e:
            raise ClientError("connection", str(e)) from e

    def send(self, *, model: str, system: str, messages: list, tools: list | None = None,
             max_tokens: int = 1024, effort: str = "low") -> Reply:
        safety.check(system, messages, tools or [])
        params = build_request(model, system, messages, tools, max_tokens, effort)
        with self._mapped():
            message = self._client.messages.create(**params)
        return to_reply(message)

    def stream(self, *, model: str, system: str, messages: list, tools: list | None = None,
               max_tokens: int = 1024, effort: str = "low"):
        """The same request, streamed (AI Phase 2, /api/ask): yields
        ("text", words) as the answer is written, then ("reply", Reply) once
        the message is whole. Tool inputs are small and never shown, so they
        aren't streamed: the API validates them whole."""
        safety.check(system, messages, tools or [])
        params = build_request(model, system, messages, tools, max_tokens, effort)
        with self._mapped():
            with self._client.messages.stream(**params) as s:
                for event in s:
                    if event.type == "text":
                        yield ("text", event.text)
                message = s.get_final_message()
        yield ("reply", to_reply(message))


def from_env():
    """The server's client, or None when AI is off: no key, or no SDK."""
    key = os.environ.get(config.KEY_ENV, "").strip()
    if not key:
        return None
    try:
        return Client(key)
    except ImportError:
        return None
