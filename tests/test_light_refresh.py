"""REFRESH-05, then A+ (REDESIGN-08, the chosen redesign, 2026-11-18): by
source, the iPhone app's page is the A+ ground (the nacre under a white veil
in light, the night in dark), its cards are the one A+ card, its muted grey
is #514D67, the Allowance orb is one shared view that Home draws, and
nothing is left of the pearl-paper page."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios" / "Pearl"


def src(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def swift_files():
    return sorted(IOS.rglob("*.swift"))


def code(text: str) -> str:
    """The source without its comment lines (they may name what went)."""
    return "\n".join(line for line in text.splitlines() if not line.strip().startswith("//"))


class TestLightIridescent:
    THEME = "ios/Pearl/Theme/Theme.swift"
    NACRE = "ios/Pearl/Theme/Nacre.swift"
    DUST = "ios/Pearl/Theme/PearlDust.swift"
    ORB = "ios/Pearl/Views/Components/AllowanceOrb.swift"
    HOME = "ios/Pearl/Views/Home/HomeView.swift"
    GAUGE = "ios/Pearl/Views/Components/AllowanceGauge.swift"

    def test_muted_light_is_the_darker_grey_and_dark_is_unchanged(self):
        theme = src(self.THEME)
        m = re.search(r"static let muted = dynamic\(light: 0x([0-9A-F]{6}), dark: 0x([0-9A-F]{6})\)", theme)
        assert m, "Pearl.muted should still be a light/dark pair"
        assert m.group(1) == "514D67", "color/text/muted light is mist/600 #514D67"
        assert m.group(2) == "B4B1CC", "color/text/muted dark stays mist/300"
        # Ink and the action colour do not change.
        assert "static let ink = dynamic(light: 0x2E2547, dark: 0xFBF8F6)" in theme
        assert "static let action = dynamic(light: 0xB22757, dark: 0xFF8FB1)" in theme

    def test_no_pearl_paper_light_background_remains(self):
        theme = code(src(self.THEME))
        assert "static let page" not in theme, "the flat light page colour is gone"
        for path in swift_files():
            text = code(path.read_text(encoding="utf-8"))
            rel = path.relative_to(ROOT)
            assert "Pearl.page" not in text, f"{rel} still paints Pearl.page"
            assert "pearlPage()" not in text, f"{rel} still uses pearlPage()"
            # The sheets' old pale wash.
            assert "0xFFF1F5" not in text and "0xFBF8FB" not in text, f"{rel} still draws the pale sheet wash"
        # #FBF8F6 survives only as dark ink and the toast's words on ink.
        for line in theme.splitlines():
            if "0xFBF8F6" in line:
                assert "static let ink" in line or "static let onInk" in line, line

    def test_sheets_sit_on_the_a_plus_sheet_surface(self):
        menus = code(src("ios/Pearl/Views/Transactions/SplitMenus.swift"))
        assert ".background(SheetBackground())" in menus
        assert "presentationBackground { SheetBackground() }" in menus
        tx = code(src("ios/Pearl/Views/Transactions/TransactionsView.swift"))
        sheet = tx[tx.index("struct SheetBackground"):]
        sheet = sheet[:sheet.index("\n}\n") + 3]
        assert "APSheetGround()" in sheet, "a sheet is the A+ `.sheet` surface"
        aplus = code(src("ios/Pearl/Theme/APlus.swift"))
        ground = aplus[aplus.index("struct APSheetGround"):aplus.index("struct APGlassCircle")]
        assert "0x1C2F73" in ground and "0x12163F" in ground, "the dark sheet gradient"
        assert ".white.opacity(0.66), .white.opacity(0.44)" in ground, "light: the nacre under a white veil"

    def test_card_tokens_are_a_plus(self):
        theme = code(src(self.THEME))
        assert "static let card = APlus.card" in theme
        assert "static let border = APlus.cardLine" in theme
        assert "static let cardShadow = Color(hex: 0x664D99)" in theme
        aplus = code(src("ios/Pearl/Theme/APlus.swift"))
        assert "static let card = rgba(light: (255, 255, 255, 0.80), dark: (21, 27, 68, 0.72))" in aplus
        assert "static let cardLine = rgba(light: (255, 255, 255, 0.95), dark: (255, 255, 255, 0.08))" in aplus
        nacre = code(src(self.NACRE))
        surface = nacre[nacre.index("struct GlassSurface"):nacre.index("struct GlassCard")]
        assert "APCardSurface(radius: radius)" in surface, "GlassCard draws the one A+ card"
        assert "static let separator = APlus.separator" in nacre, "in-card dividers are the A+ separator"
        assert "Nacre.horizontal, lineWidth: 1.2" not in nacre, "no nacre edge on cards in A+"

    def test_every_card_modifier_draws_the_a_plus_card(self):
        """The split sheets' cards and the Home cards go through one modifier."""
        for path in ("ios/Pearl/Views/Components/Components.swift",
                     "ios/Pearl/Views/Transactions/SplitMenus.swift",
                     "ios/Pearl/Views/Transactions/SplitFlow.swift",
                     "ios/Pearl/Views/Transactions/JointSplitViews.swift",
                     "ios/Pearl/Views/Transactions/PaybackOptions.swift"):
            text = code(src(path))
            assert ".pearlCard(radius:" in text or ".apCard(" in text, path
        nacre = code(src(self.NACRE))
        mods = nacre[nacre.index("func glassCard("):nacre.index("struct RowSeparator")]
        assert mods.count("apCard(radius: radius)") == 2, "glassCard and pearlCard are the A+ card"

    def test_the_page_is_the_a_plus_ground(self):
        dust = src(self.DUST)
        assert "struct PearlDust: View" in dust, "kept, but no page draws it in A+"
        nacre = code(src(self.NACRE))
        background = nacre[nacre.index("struct NacreBackground"):nacre.index("extension View")]
        assert "APGround()" in background and "PearlDust" not in background
        assert 'Image("Bubbles")' not in background
        aplus = code(src("ios/Pearl/Theme/APlus.swift"))
        ground = aplus[aplus.index("struct APGround"):aplus.index("struct APSheetGround")]
        assert "0xFFB6CC" in ground and "0xCDB9FF" in ground and "0xA8E9DF" in ground
        assert ".white.opacity(0.50)" in ground and ".white.opacity(0.22)" in ground and ".white.opacity(0.34)" in ground
        assert "0x12163F" in ground and "0x172566" in ground and "0x1D4A7D" in ground
        assert ".accessibilityHidden(true)" in ground

    def test_allowance_gauge_replaces_the_orb_and_home_uses_it(self):
        # H-00r v2 (n-home-gauge, 2026-11-21): the gauge replaces the orb.
        assert not (ROOT / self.ORB).exists()
        gauge = src(self.GAUGE)
        assert "struct AllowanceGauge: View" in gauge
        for layer in ("0xCDEFEA", "0xEBDDFB", "0xFAD3DF", "0x1D4A57", "0x3A3375", "0x552A5C",   # zones
                      "0x8FE0D4", "0xC9A8FF", "0xFF8FB1", "0xE0457B",                           # fills
                      "lineWidth: 14", "radius: CGFloat = 132", "235 + 250 * share",            # the arc
                      '.custom("Fraunces-SemiBold", size: 48, relativeTo: .largeTitle)'):
            assert layer in gauge, layer
        assert ".accessibilityElement(children: .ignore)" in gauge
        assert "withAnimation" not in gauge and ".animation(" not in gauge, "no motion yet"
        home = code(src(self.HOME))
        assert "AllowanceGauge(allowance: sts, open: openAddsUp)" in home
        assert "Allowance.restCaption" in home and "Allowance.restCaption" in gauge, \
            "the hidden caption stays as the VoiceOver hint"
        onboarding = code(src("ios/Pearl/Views/Onboarding/AllowanceView.swift"))
        # A+ G6-Allowance (REDESIGN-13): set-up shows the Allowance on its card, not the orb.
        assert "AllowanceCard(month:" in onboarding and "AllowanceOrb(" not in onboarding
        assert '"left in \\(Format.monthName(month))"' in onboarding
        for path in swift_files():
            assert "AllowanceRing" not in code(path.read_text(encoding="utf-8")), path

    def test_house_rules(self):
        for path in swift_files():
            text = path.read_text(encoding="utf-8")
            assert "safe to spend" not in text.lower(), f"{path.relative_to(ROOT)} says safe to spend"
        assert "REFRESH-05" in src(self.DUST)
        assert "H-00r v2" in src(self.GAUGE)
