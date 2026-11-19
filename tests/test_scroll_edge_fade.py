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


def _block(src: str, opener: str) -> str:
    """The `{ … }` that follows `opener`, braces matched."""
    i = src.index("{", src.index(opener))
    depth = 0
    for j in range(i, len(src)):
        depth += {"{": 1, "}": -1}.get(src[j], 0)
        if depth == 0:
            return src[i:j + 1]
    raise AssertionError(opener)


FADE = PEARL / "Views/Components/ScrollEdgeFade.swift"


def test_the_inset_is_read_outside_the_ignored_area():
    """Round 5: a reader with .ignoresSafeArea() sees an inset of 0, so the
    fade never drew. The reader keeps to the safe area."""
    src = FADE.read_text()
    reader = _block(src, ".background(GeometryReader")
    assert "g.safeAreaInsets" in src[src.index("private func measure"):]
    assert "measure(g)" in reader and ".ignoresSafeArea" not in reader


def test_no_full_screen_layer_over_the_page():
    """TEST-49: a full-screen overlay, even with hit testing off, won the
    accessibility hit test, so nothing on the screen was hittable. The only
    layer on top is the band, as tall as the top inset, hidden from
    accessibility."""
    src = FADE.read_text()
    overlay = _block(src, ".overlay(alignment: .top)")
    assert "ScrollEdgeFadeBand(top: top, ground: ground)" in overlay
    for full in ("GeometryReader", "maxHeight: .infinity", "Spacer", "APGround()", "Color."):
        assert full not in overlay, full
    assert src.count(".overlay") == 1
    band = src[src.index("struct ScrollEdgeFadeBand"):]
    assert ".frame(height: top, alignment: .top)" in band and ".clipped()" in band
    assert ".allowsHitTesting(false)" in band and ".accessibilityHidden(true)" in band
    # The band's frame is set before anything that could make it bigger.
    assert band.index(".frame(height: top") < band.index(".mask(")


def test_the_band_lines_up_with_the_page_ground():
    band = FADE.read_text()[FADE.read_text().index("struct ScrollEdgeFadeBand"):]
    assert "if top > 0" in band and "APGround()" in band
    assert ".frame(width: ground.width, height: ground.height)" in band


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
