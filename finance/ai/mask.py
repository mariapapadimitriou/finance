"""Pseudonymisation: what the model sees instead of her values (AI Phase 2b,
product owner 2026-11-27).

Before every call the gateway swaps her values for placeholders, numbered
within one ask and stable for it (the same shop is always the same one):

    amounts  [AMT1]     "$1,234", "$40.50", "12 dollars"
    dates    [DATE1]    "2026-11-27", "2026-11", "Nov 3", "October", "2025"
    people   [PERSON1]  split names, e-Transfer senders, people she named
    cards    [CARD1]    card and account nicknames
    shops    [SHOP1]    merchants
    numbers  [NUM1]     any other figure: a count, a share, a day

Relative words ("last month", "this year", "Saturday") stay as written, and
so do categories. Comparisons Python works out reach the model as words
("more than usual"), never as numbers: the caller writes them that way.

Known people, cards and shops come from the caller (`known`); amounts,
dates and numbers are found in any text. A tool result's keys also say what
a value is (`merchant` is a shop, a `name` in `cards` is a card), so a shop
the caller didn't list is still masked.

The model's tool calls are filled back in on the server before a tool runs,
and its reply before it leaves the server. A reply that names a placeholder
the server never issued, or writes a figure of its own (any digit outside a
placeholder), isn't used: `problem` says why, and the caller answers with
Python instead.

A route's allowlist (`config.ROUTES[route]["mask"]["raw"]`) names the kinds
it may send as they are: Ask Pearl sends none; Smart sorting's reasons
(`sort_reason`, Phase 4) may send the shop name and nothing else. No route
may send account or card numbers, Plaid tokens or logins: `safety.check`
still refuses those, before and after masking.
"""

from __future__ import annotations

import json
import re

KINDS = {"amount": "AMT", "date": "DATE", "person": "PERSON", "card": "CARD",
         "shop": "SHOP", "number": "NUM"}
NAMED = ("person", "card", "shop")              # known by name, from the caller
_TAG_KIND = {v: k for k, v in KINDS.items()}

# A placeholder, or something written like one ("[SHOP]", "[SHOP12]", "[Amt1]").
PLACEHOLDER = re.compile(r"\[(AMT|DATE|PERSON|CARD|SHOP|NUM)(\d+)\]")
_LOOKS_LIKE = re.compile(r"\[\s*[A-Za-z]{2,8}\s*\d*\s*\]")

_MONTHS = ("january", "february", "march", "april", "may", "june", "july", "august",
           "september", "october", "november", "december")
_ABBR = r"(?:Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)"
_DAY = r"(?:\s+\d{1,2}(?:st|nd|rd|th)?)"
_YEAR = r"(?:,?\s+(?:19|20)\d{2})"
_FULL = "|".join(m for m in _MONTHS if m != "may")

DATES = [
    re.compile(r"(?<![\w])\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2}(?:\.\d+)?)?Z?)?(?![\w])"),
    re.compile(r"(?<![\w-])\d{4}-\d{2}(?![\w-])"),
    re.compile(r"(?<![\w/])\d{1,2}/\d{1,2}(?:/\d{2,4})?(?![\w/])"),
    re.compile(rf"(?<![\w])(?:{_FULL}){_DAY}?{_YEAR}?(?![\w])", re.IGNORECASE),
    re.compile(rf"(?<![\w])May(?:{_DAY}{_YEAR}?|{_YEAR})?(?![\w])"),
    re.compile(rf"(?<![\w]){_ABBR}\.?(?:{_DAY}{_YEAR}?|{_YEAR})?(?![\w])"),
    re.compile(r"(?<![\w$.,])(?:19|20)\d{2}(?![\w.,%])"),
]
AMOUNTS = [
    re.compile(r"[-−]?\s?\$\s?\d[\d,]*(?:\.\d+)?"),
    re.compile(r"(?<![\w.])\d[\d,]*(?:\.\d+)?\s?(?:dollars?|bucks|CAD|USD)(?![\w])", re.IGNORECASE),
]
NUMBERS = [re.compile(r"(?<![A-Za-z\d])\d+(?:[.,]\d+)*(?:\s?%)?")]
_DIGIT = re.compile(r"\d")

# What a key in a tool result says its value is.
_SHOP_KEYS = {"merchant", "shop", "merchant_name", "store"}
_PERSON_KEYS = {"person", "people", "sender", "payer", "payee", "who", "with", "from", "to",
                "party"}
_CARD_KEYS = {"card", "cards_name", "account", "account_label", "nickname"}
_ROW_PARENTS = {"latest", "rows", "top_shops"}
_CARD_PARENTS = {"cards"}


class UnknownPlaceholder(ValueError):
    """The model named a placeholder this ask never issued."""


def _casefold(s: str) -> str:
    return " ".join(s.split()).casefold()


class Masker:
    """One ask's placeholders. `known` is {"person": [...], "card": [...],
    "shop": [...]}; `raw` the kinds this route may send as they are."""

    def __init__(self, known: dict | None = None, raw=()):
        self.raw = set(raw or ())
        self._forward: dict[tuple[str, str], str] = {}
        self.back: dict[str, str] = {}
        self._count: dict[str, int] = {}
        self._terms: dict[str, tuple[str, str]] = {}     # casefold → (kind, spelling)
        self._term_re = None
        # People first: an e-Transfer whose merchant is a person stays a person.
        for kind in ("person", "card", "shop"):
            for term in (known or {}).get(kind) or []:
                self.learn(kind, term)

    # ── Placeholders ──
    def learn(self, kind: str, term) -> None:
        """Know `term` as a `kind` from now on, wherever it appears."""
        term = " ".join(str(term or "").split())
        if len(term) < 3 or not re.search(r"[A-Za-zÀ-ÿ]", term) or PLACEHOLDER.fullmatch(term):
            return
        key = _casefold(term)
        if key not in self._terms:
            self._terms[key] = (kind, term)
            self._term_re = None
        # "Georgia Klev" is also "Georgia" when she types it.
        first = term.split()[0]
        if kind == "person" and first != term:
            self.learn(kind, first)

    def placeholder(self, kind: str, real: str) -> str:
        key = (kind, _casefold(real) if kind in NAMED else real.strip())
        ph = self._forward.get(key)
        if ph is None:
            tag = KINDS[kind]
            self._count[tag] = self._count.get(tag, 0) + 1
            ph = f"[{tag}{self._count[tag]}]"
            self._forward[key] = ph
            self.back[ph] = real.strip()
        return ph

    def issued(self) -> dict[str, str]:
        return dict(self.back)

    # ── Masking ──
    def _terms_regex(self):
        if self._term_re is None:
            terms = sorted((t for k, t in self._terms.values() if k not in self.raw),
                           key=len, reverse=True)
            self._term_re = (re.compile(r"(?<![\w])(?:" + "|".join(re.escape(t) for t in terms)
                                        + r")(?![\w])", re.IGNORECASE) if terms else False)
        return self._term_re

    def _split(self, pieces, regex, to_ph):
        out = []
        for piece, done in pieces:
            if done:
                out.append((piece, True))
                continue
            at = 0
            for m in regex.finditer(piece):
                if m.start() > at:
                    out.append((piece[at:m.start()], False))
                out.append((to_ph(m.group(0)), True))
                at = m.end()
            if at < len(piece):
                out.append((piece[at:], False))
        return out

    def text(self, s: str) -> str:
        """`s` with every value this route may not send swapped out."""
        if not s:
            return s
        pieces = [(s, False)]
        # What's already a placeholder (the model's own words) stays.
        pieces = self._split(pieces, PLACEHOLDER, lambda g: g)
        terms = self._terms_regex()
        if terms:
            def named(g):
                kind, spelling = self._terms[_casefold(g)]
                return self.placeholder(kind, spelling)
            pieces = self._split(pieces, terms, named)
        for kind, regexes in (("amount", AMOUNTS), ("date", DATES), ("number", NUMBERS)):
            if kind in self.raw:
                continue
            for regex in regexes:
                pieces = self._split(pieces, regex, lambda g, k=kind: self._lead(g, k))
        return "".join(p for p, _ in pieces)

    def _lead(self, g: str, kind: str) -> str:
        # "  $40" keeps its leading space outside the placeholder.
        stripped = g.lstrip()
        return g[:len(g) - len(stripped)] + self.placeholder(kind, stripped)

    def _hint(self, key, parent) -> str | None:
        k = str(key or "").lower()
        p = str(parent or "").lower()
        if k in _SHOP_KEYS or (k == "name" and p in _ROW_PARENTS):
            return "shop"
        if k in _PERSON_KEYS:
            return "person"
        if k in _CARD_KEYS or (k == "name" and p in _CARD_PARENTS):
            return "card"
        return None

    def _collect(self, value, key=None, parent=None):
        """Learn what the keys say before masking, so a shop named under
        `merchant` is masked in the `line` that comes before it too."""
        if isinstance(value, dict):
            for k, v in value.items():
                self._collect(v, k, key)
        elif isinstance(value, (list, tuple)):
            for v in value:
                self._collect(v, key, parent)
        elif isinstance(value, str):
            kind = self._hint(key, parent)
            if kind and value.strip() and not PLACEHOLDER.fullmatch(value.strip()):
                self.learn(kind, value)

    def _key(self, k):
        """A key that is itself one of her values ("2026-11": ...) is masked;
        a plain field name ("merchant") stays."""
        if isinstance(k, str) and (_DIGIT.search(k) or self._terms_regex() and
                                   self._terms_regex().search(k)):
            return self.text(k)
        return k

    def _walk(self, value, key=None, parent=None):
        if isinstance(value, dict):
            return {self._key(k): self._walk(v, k, key) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return [self._walk(v, key, parent) for v in value]
        if isinstance(value, bool) or value is None:
            return value
        if isinstance(value, (int, float)):
            kind = "date" if str(key).lower() == "year" else "number"
            if kind in self.raw:
                return value
            return self.placeholder(kind, f"{value:g}" if isinstance(value, float) else str(value))
        if isinstance(value, str):
            kind = self._hint(key, parent)
            v = value.strip()
            if kind and kind not in self.raw and v and len(v) < 3 and not _DIGIT.search(v):
                return self.placeholder(kind, v)     # too short to learn, still hers
            return self.text(value)
        return self.text(str(value))

    def value(self, value):
        """A tool result or any JSON-like value, masked."""
        self._collect(value)
        return self._walk(value)

    def content(self, content):
        """A tool result's content: JSON text stays JSON, other text is
        masked as text, blocks are masked inside."""
        if isinstance(content, str):
            try:
                parsed = json.loads(content)
            except ValueError:
                return self.text(content)
            if isinstance(parsed, (dict, list)):
                return json.dumps(self.value(parsed), sort_keys=True, ensure_ascii=False)
            return self.text(content)
        if isinstance(content, list):
            return [self._block(b) for b in content]
        return self.value(content)

    def _block(self, block):
        if isinstance(block, dict):
            b = dict(block)
            if b.get("type") == "text" and isinstance(b.get("text"), str):
                b["text"] = self.text(b["text"])
            elif b.get("type") == "tool_result" and "content" in b:
                b["content"] = self.content(b["content"])
            return b
        return block

    def messages(self, messages: list) -> list:
        """The caller's messages, masked: her words and anything Python put
        in them."""
        out = []
        for m in messages or []:
            if not isinstance(m, dict):
                out.append(m)
                continue
            m = dict(m)
            c = m.get("content")
            if isinstance(c, str):
                m["content"] = self.content(c)      # JSON stays JSON, keys say what
            elif isinstance(c, list):
                m["content"] = [self._block(b) for b in c]
            out.append(m)
        return out

    # ── Filling back in ──
    def fill(self, s: str) -> str:
        """`s` with each placeholder this ask issued put back. Raises
        UnknownPlaceholder for one it didn't."""
        def back(m):
            ph = m.group(2)
            if ph not in self.back:
                raise UnknownPlaceholder(ph)
            real = self.back[ph]
            # "$[AMT1]" when [AMT1] is "$40": one dollar sign.
            return real if m.group(1) and real.lstrip("-−").startswith("$") else m.group(1) + real
        return re.sub(r"(\$?)(\[(?:AMT|DATE|PERSON|CARD|SHOP|NUM)\d+\])", back, s or "")

    def fill_value(self, value):
        """A tool call's input, filled back in (strings anywhere inside)."""
        if isinstance(value, dict):
            return {k: self.fill_value(v) for k, v in value.items()}
        if isinstance(value, list):
            return [self.fill_value(v) for v in value]
        if isinstance(value, str):
            filled = self.fill(value)
            for m in _LOOKS_LIKE.finditer(value):
                if m.group(0) not in self.back:
                    raise UnknownPlaceholder(m.group(0))
            return filled
        return value

    def problem(self, reply: str) -> str | None:
        """Why the model's words can't be used, or None:
        "mask_unknown" a placeholder this ask never issued (or one made up);
        "mask_number"  a figure of its own, outside a placeholder."""
        reply = reply or ""
        for m in _LOOKS_LIKE.finditer(reply):
            if m.group(0) not in self.back:
                return "mask_unknown"
        if _DIGIT.search(PLACEHOLDER.sub("", reply)):
            return "mask_number"
        return None


class ReplyGate:
    """The model's words as they stream: filled back in piece by piece, a
    placeholder never split across pieces, and nothing more let out once a
    piece breaks the rules (the caller then answers with Python)."""

    def __init__(self, masker: Masker):
        self.masker = masker
        self.pending = ""
        self.bad: str | None = None

    def feed(self, chunk: str) -> str:
        if self.bad:
            return ""
        pending = self.pending + (chunk or "")
        cut = len(pending)
        i = pending.rfind("[")
        if i != -1 and "]" not in pending[i:] and len(pending) - i <= 12:
            cut = i
        while cut > 0 and pending[cut - 1] == "$":
            cut -= 1
        ready, self.pending = pending[:cut], pending[cut:]
        return self._let_out(ready)

    def _let_out(self, ready: str) -> str:
        if not ready:
            return ""
        why = self.masker.problem(ready)
        if why:
            self.bad = why
            return ""
        return self.masker.fill(ready)

    def finish(self) -> str:
        """What was held back, filled in ("" once the reply broke a rule)."""
        if self.bad:
            return ""
        tail, self.pending = self.pending, ""
        return self._let_out(tail)


def policy(route_cfg: dict | None) -> tuple:
    """The kinds a route may send as they are (its allowlist)."""
    raw = tuple((route_cfg or {}).get("mask", {}).get("raw") or ())
    unknown = set(raw) - set(KINDS)
    if unknown:
        raise ValueError(f"not a kind of value: {sorted(unknown)}")
    return raw


def for_route(route_cfg: dict | None, known: dict | None = None) -> Masker:
    return Masker(known, raw=policy(route_cfg))
