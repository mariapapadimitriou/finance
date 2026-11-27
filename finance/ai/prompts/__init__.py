"""Versioned system prompts, loaded by id@version ("ask@1" is ask_v1.md).

A published prompt is frozen: the text never changes once it is in use, so
its cached prefix stays valid and every usage row says exactly which words
the model saw. To change a prompt, add the next version (ask_v2.md), pin its
hash below and point the route at it. Prompts hold no dates, names or
anything else that changes per request; that goes after the cached prefix.
"""

from __future__ import annotations

import functools
import hashlib
import os
import re

_DIR = os.path.dirname(os.path.abspath(__file__))
_REF = re.compile(r"^([a-z][a-z0-9_]*)@([1-9][0-9]*)$")

# sha256 of each published prompt. A test fails if a file drifts from it.
FROZEN = {
    "ask@1": "e06470208ef47093156b557a02fad63eac47bc2dbf393c30c04060241c405672",
}


class PromptError(LookupError):
    """No such prompt, or its text no longer matches what was published."""


def path(ref: str) -> str:
    m = _REF.match(ref or "")
    if not m:
        raise PromptError(f"not an id@version: {ref!r}")
    return os.path.join(_DIR, f"{m.group(1)}_v{m.group(2)}.md")


@functools.lru_cache(maxsize=None)
def load(ref: str) -> str:
    """The text of prompt `ref` ("ask@1"), checked against its frozen hash."""
    if ref not in FROZEN:
        raise PromptError(f"prompt {ref} is not published")
    try:
        with open(path(ref), "rb") as f:
            raw = f.read()
    except OSError as e:
        raise PromptError(f"prompt {ref} is missing") from e
    if hashlib.sha256(raw).hexdigest() != FROZEN[ref]:
        raise PromptError(f"prompt {ref} changed after it was published")
    return raw.decode("utf-8")


def published() -> list[str]:
    return sorted(FROZEN)
