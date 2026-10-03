"""Invariants between the shell, the groups, and the panels they render.

These read the source rather than run it. There is no JavaScript test runner
here, and the alternative to a static check was no check at all — for a class
of bug that is invisible in review and looks, in the browser, like a button that
does nothing.

The navigation has two levels now: six groups in the sidebar, each holding one
or more panels behind a section switcher. Panels still link to each other by
panel key, which only works because `resolve` maps a panel key back to the group
that owns it — so the checks below are mostly about that mapping staying whole.

Each test fails loudly if it cannot find what it expects to parse, so a
restructured file reports that it needs updating rather than passing silently.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

SRC = Path(__file__).resolve().parent.parent / "src"
APP = SRC / "App.jsx"
# The map of panels, groups and aliases. It lives apart from the shell so that
# components naming a destination in a sentence can ask what it is called.
NAV = SRC / "nav.js"


@pytest.fixture(scope="module")
def source() -> str:
    text = APP.read_text(encoding="utf-8")
    assert text.strip(), "src/App.jsx is empty"
    return text


@pytest.fixture(scope="module")
def nav() -> str:
    text = NAV.read_text(encoding="utf-8")
    assert text.strip(), "src/nav.js is empty"
    return text


@pytest.fixture(scope="module")
def panels(nav) -> set[str]:
    """The keys of the PANELS map."""
    m = re.search(r"const PANELS = \{(.*?)\n\};", nav, re.S)
    assert m, "could not find `const PANELS = {...}` in nav.js — update this test"
    keys = set(re.findall(r"^\s{2}(\w+):\s*\{", m.group(1), re.M))
    assert len(keys) > 5, f"only parsed {keys} out of PANELS — update this test"
    return keys


@pytest.fixture(scope="module")
def groups(nav) -> dict[str, list[str]]:
    """Group key -> the panel keys it holds, in order."""
    m = re.search(r"const GROUPS = \[(.*?)\n\];", nav, re.S)
    assert m, "could not find `const GROUPS = [...]` in nav.js — update this test"
    # `short:` is the optional phone-width label, and may push `panels` onto
    # the next line.
    found = re.findall(r"key: '([^']+)', label: '[^']*',"
                       r"(?:\s*short: '[^']*',)?\s*panels: \[([^\]]+)\]",
                       m.group(1))
    assert found, "could not parse any group out of GROUPS — update this test"
    return {key: re.findall(r"'([^']+)'", panels) for key, panels in found}


@pytest.fixture(scope="module")
def aliases(nav) -> dict[str, str]:
    """Old panel keys that now point at the panel which absorbed them."""
    m = re.search(r"const ALIASES = \{(.*?)\};", nav, re.S)
    assert m, "could not find `const ALIASES = {...}` in nav.js — update this test"
    return dict(re.findall(r"(\w+):\s*'([^']+)'", m.group(1)))


@pytest.fixture(scope="module")
def rendered(source) -> set[str]:
    """Panel keys that actually have a branch rendering them."""
    keys = set(re.findall(r"panel === '([^']+)'", source))
    assert keys, "no `panel === '...'` branches found — update this test"
    return keys


def _string_list(source: str, name: str) -> list[str]:
    m = re.search(rf"const {name} = \[(.*?)\];", source, re.S)
    assert m, f"could not find `const {name} = [...]` in App.jsx — update this test"
    return re.findall(r"'([^']+)'", m.group(1))


class TestEveryPanelIsReachableAndRendered:
    def test_every_panel_belongs_to_exactly_one_group(self, panels, groups):
        """A panel in no group cannot be reached; one in two is ambiguous —
        `resolve` would send you to whichever appeared first."""
        owners: dict[str, list[str]] = {key: [] for key in panels}
        for group, members in groups.items():
            for key in members:
                assert key in panels, (
                    f"group '{group}' lists panel '{key}', which is not in PANELS")
                owners[key].append(group)

        orphans = sorted(k for k, g in owners.items() if not g)
        assert not orphans, f"panels in no group, so unreachable: {orphans}"
        shared = sorted(k for k, g in owners.items() if len(g) > 1)
        assert not shared, f"panels claimed by more than one group: {shared}"

    def test_every_panel_is_rendered(self, panels, rendered):
        missing = sorted(panels - rendered)
        assert not missing, (
            f"{missing} appear in PANELS and the section switcher, but nothing "
            "renders them — the section would open onto an empty page")

    def test_nothing_is_rendered_that_is_not_a_panel(self, panels, rendered):
        stray = sorted(rendered - panels)
        assert not stray, (
            f"{stray} have a render branch but are in no group, so no "
            "navigation can reach them")

    def test_the_import_panel_is_reachable_again(self, groups):
        """It used to be hidden from the strip entirely, which left the import
        history unreachable in normal use once Plaid was working."""
        owners = [g for g, members in groups.items() if "import" in members]
        assert owners, "'import' is in no group, so nothing can reach it"


class TestLinksBetweenPanels:
    def test_every_alias_points_somewhere_real(self, panels, groups, aliases):
        """An alias is how a panel that was folded into another one keeps its
        old links working. One pointing at nothing is worse than no alias at
        all: `resolve` falls through to Today, so the button appears to work."""
        assert aliases, "ALIASES is empty — remove the fixture if it is gone"
        for key, target in aliases.items():
            assert key not in panels, (
                f"'{key}' is aliased but is also a panel — the alias wins in "
                "`resolve`, so the panel is unreachable")
            assert target in panels or target in groups, (
                f"alias '{key}' points at '{target}', which is neither")

    def test_every_link_target_resolves(self, panels, groups, aliases):
        """Panels navigate by panel key — `onTab('piggy')` — and a key that is
        neither a panel, a group nor an alias silently lands you on Today."""
        targets: dict[str, list[str]] = {}
        for path in sorted(SRC.rglob("*.jsx")):
            text = path.read_text(encoding="utf-8")
            for key in re.findall(r"onTab\('([^']+)'\)", text):
                targets.setdefault(key, []).append(path.name)
            for key in re.findall(r"\bgo\('([^']+)'\)", text):
                targets.setdefault(key, []).append(path.name)

        assert targets, "no onTab('...') calls found anywhere — update this test"
        valid = panels | set(groups) | set(aliases)
        bad = {k: v for k, v in targets.items() if k not in valid}
        assert not bad, f"link targets that resolve to nothing: {bad}"


class TestTheEmptyLedger:
    def test_the_empty_state_only_offers_panels_it_will_render(self, source):
        """The bug this exists to prevent.

        When the ledger is empty most panels are hidden behind an empty state. A
        button there that points at a hidden panel sets the destination, the
        empty state renders over it again, and nothing appears to happen — which
        is exactly how it was reported.
        """
        allowed = _string_list(source, "WORKS_WHEN_EMPTY")
        assert allowed, "WORKS_WHEN_EMPTY is empty"

        guard = re.search(r"if \(summary\.empty && (.+?)\) \{", source)
        assert guard, "could not find the empty-ledger guard — update this test"
        assert "WORKS_WHEN_EMPTY" in guard.group(1), (
            "the empty-ledger guard no longer consults WORKS_WHEN_EMPTY")
        # It has to test the panel, not the group: a group whose first panel
        # works when empty would otherwise let through every panel beside it.
        assert "includes(panel)" in guard.group(1), (
            "the guard checks something other than the active panel")

        block = re.search(r"<Empty title=.*?</Empty>", source, re.S)
        assert block, "could not find the <Empty> block — update this test"

        targets = set(re.findall(r"go\('([^']+)'\)", block.group(0)))
        assert targets, "the empty state offers no way out of itself"

        unreachable = sorted(t for t in targets if t not in allowed)
        assert not unreachable, (
            f"the empty state links to {unreachable}, which it will not render; "
            f"add them to WORKS_WHEN_EMPTY or point the button elsewhere")

    def test_the_guarded_panels_are_real(self, panels, source):
        for key in _string_list(source, "WORKS_WHEN_EMPTY"):
            assert key in panels, (
                f"WORKS_WHEN_EMPTY names '{key}', which is not a panel")


class TestTheMonthSelector:
    def test_it_is_offered_on_the_panels_that_read_a_month(self, panels, source):
        """It is shown per panel now, not per group: Overview and Budgets live
        in different groups and both need it, and their neighbours do not."""
        m = re.search(r"showMonth=\{(.+?)\}", source)
        assert m, "could not find the showMonth prop — update this test"
        assert "includes(panel)" in m.group(1), (
            "showMonth no longer keys off the active panel")
        for key in re.findall(r"'([^']+)'", m.group(1)):
            assert key in panels, f"showMonth names '{key}', which is not a panel"


class TestNumberInputsAcceptTheAmountsPeopleType:
    """The `step` attribute is a validity rule, not a convenience.

    `min="1" step="50"` on the piggy bank target meant the browser considered
    1300, 2400 and every other round figure invalid — the two nearest valid
    values being 1251 and 1301. Chrome then refuses to submit the form and
    reports it on a tooltip nobody sees, so the button does nothing. This is
    exactly the class of bug this file exists for: invisible in review, and
    indistinguishable in use from a dead button.

    Cents are the only step a money field may impose.
    """

    def test_no_money_field_rejects_an_ordinary_amount(self):
        pattern = re.compile(r'type="number"[^>]*?step="([^"]+)"'
                             r'|step="([^"]+)"[^>]*?type="number"', re.S)
        offenders = []
        for path in sorted(SRC.rglob("*.jsx")):
            for m in pattern.finditer(path.read_text(encoding="utf-8")):
                step = m.group(1) or m.group(2)
                if step not in ("any", "0.01"):
                    offenders.append(f"{path.name}: step=\"{step}\"")
        assert not offenders, (
            "number inputs whose step makes ordinary amounts invalid, so the "
            f"form silently refuses to submit: {offenders}")
