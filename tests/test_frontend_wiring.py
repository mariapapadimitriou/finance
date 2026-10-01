"""Invariants between the shell and the panels it can refuse to render.

These read the source rather than run it. There is no JavaScript test runner
here, and the alternative to a static check was no check at all — for a class
of bug that is invisible in review and looks, in the browser, like a button
that does nothing.

Each test fails loudly if it cannot find what it expects to parse, so a
restructured file reports that it needs updating rather than passing silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

APP = Path(__file__).resolve().parent.parent / "src" / "App.jsx"


@pytest.fixture(scope="module")
def source() -> str:
    text = APP.read_text(encoding="utf-8")
    assert text.strip(), "src/App.jsx is empty"
    return text


def _string_list(source: str, name: str) -> list[str]:
    m = re.search(rf"const {name} = \[(.*?)\];", source, re.S)
    assert m, f"could not find `const {name} = [...]` in App.jsx — update this test"
    return re.findall(r"'([^']+)'", m.group(1))


def test_the_empty_state_only_offers_tabs_it_will_render(source):
    """The bug this exists to prevent.

    When the ledger is empty most panels are hidden behind an empty state. A
    button there that points at a hidden panel sets the tab, the empty state
    renders over it again, and nothing appears to happen — which is exactly
    how it was reported.
    """
    allowed = _string_list(source, "WORKS_WHEN_EMPTY")
    assert allowed, "WORKS_WHEN_EMPTY is empty"

    guard = re.search(r"if \(summary\.empty && (.+?)\) \{", source)
    assert guard, "could not find the empty-ledger guard — update this test"
    assert "WORKS_WHEN_EMPTY" in guard.group(1), (
        "the empty-ledger guard no longer consults WORKS_WHEN_EMPTY")

    block = re.search(r"<Empty title=.*?</Empty>", source, re.S)
    assert block, "could not find the <Empty> block — update this test"

    targets = set(re.findall(r"setTab\('([^']+)'\)", block.group(0)))
    assert targets, "the empty state offers no way out of itself"

    unreachable = sorted(t for t in targets if t not in allowed)
    assert not unreachable, (
        f"the empty state links to {unreachable}, which it will not render; "
        f"add them to WORKS_WHEN_EMPTY or point the button elsewhere")


def test_every_offered_tab_exists(source):
    """A button pointing at a tab key nothing renders is the same dead end."""
    keys = set(re.findall(r"\{ key: '([^']+)'", source))
    assert "banks" in keys and "import" in keys, (
        "could not parse the tab definitions — update this test")

    rendered = set(re.findall(r"tab === '([^']+)'", source))
    for target in set(re.findall(r"setTab\('([^']+)'\)", source)):
        assert target in rendered, f"setTab('{target}') has no panel rendering it"


def test_the_hidden_panel_is_still_rendered(source):
    """Import is absent from the strip on purpose; it must remain reachable."""
    m = re.search(r"const HIDDEN_TABS = \[(.*?)\];", source, re.S)
    assert m, "could not find HIDDEN_TABS — update this test"
    # Objects, not bare strings: take the `key:` of each, not every literal.
    hidden = re.findall(r"key: '([^']+)'", m.group(1))
    assert hidden, "HIDDEN_TABS is empty"
    rendered = set(re.findall(r"tab === '([^']+)'", source))
    for key in hidden:
        assert key in rendered, f"'{key}' is hidden and never rendered"
