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


def test_the_fade_covers_the_top_safe_area_only():
    src = (PEARL / "Views/Components/ScrollEdgeFade.swift").read_text()
    assert "g.safeAreaInsets.top" in src and ".frame(height: top)" in src
    assert ".allowsHitTesting(false)" in src and ".accessibilityHidden(true)" in src


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
