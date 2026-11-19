"""TEST-38: nothing scrolls under the status bar bare. One shared modifier,
scrollEdgeFade (ScrollEdgeFade.swift), fades the A+ ground over the top
safe area, and nacreScreen() adds it, so every A+ screen has it: Cash flow
and Calendar, a transaction's page, Profile, Sign-in and security
(2026-11-19)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PEARL = ROOT / "ios/Pearl"


def test_nacre_screen_adds_the_fade():
    nacre = (PEARL / "Theme/Nacre.swift").read_text()
    body = nacre[nacre.index("func nacreScreen()"):]
    body = body[:body.index("\n    }\n")]
    assert "scrollEdgeFade()" in body and "NacreBackground()" in body


def _reader(src: str) -> tuple[str, str]:
    """The GeometryReader that reads the inset: its closure, and the
    modifiers chained on the reader itself (up to the end of `body`)."""
    start = src.index("GeometryReader {")
    i = src.index("{", start)
    depth = 0
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            break
    closure = src[i:j + 1]
    after = src[j + 1:]
    chain = after[:after.index("\n    }\n")]    # the rest of ScrollEdgeFade.body
    return closure, chain


def test_the_inset_is_read_outside_the_ignored_area():
    """Round 5 re-test: a reader with .ignoresSafeArea() sees an inset of 0,
    so the fade never drew. The reader keeps to the safe area; only the band
    it draws ignores it."""
    src = (PEARL / "Views/Components/ScrollEdgeFade.swift").read_text()
    body = src[src.index("struct ScrollEdgeFade: View"):src.index("struct ScrollEdgeFadeBand")]
    closure, chain = _reader(body)
    assert "g.safeAreaInsets.top" in closure
    assert ".ignoresSafeArea()" not in chain, "the reader itself must not ignore the safe area"
    assert ".ignoresSafeArea()" in closure, "the band it draws reaches up under the clock"
    assert ".allowsHitTesting(false)" in chain and ".accessibilityHidden(true)" in chain


def test_the_band_covers_the_top_inset_only():
    src = (PEARL / "Views/Components/ScrollEdgeFade.swift").read_text()
    band = src[src.index("struct ScrollEdgeFadeBand"):]
    assert "if top > 0" in band and ".frame(height: top)" in band and "APGround()" in band


def test_every_screen_named_in_test_38_is_on_the_a_plus_ground():
    for path in ["Views/Transactions/TransactionsView.swift",          # Cash flow, Calendar
                 "Views/Transactions/TransactionDetailView.swift",     # a transaction's page
                 "Views/Profile/ProfileView.swift",                    # Profile
                 "Views/Profile/ProfileParts.swift"]:                  # ProfilePage: Sign-in and security
        assert ".nacreScreen()" in (PEARL / path).read_text(), path
    assert "SettingsPage(title: \"Sign-in and security\")" in (PEARL / "Views/Profile/SettingsViews.swift").read_text()


def test_no_screen_draws_the_ground_without_the_fade():
    offenders = [str(p.relative_to(PEARL)) for p in PEARL.rglob("*.swift")
                 if p.name not in ("Nacre.swift", "ScrollEdgeFade.swift", "APlus.swift")
                 and re.search(r"\.background\((NacreBackground|APGround)\(\)\)", p.read_text())]
    assert offenders == []
