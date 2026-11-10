"""REFRESH-05 (THL-291 and the Home tickets, "Light mode colour: C‴ with the
darker grey"): by source, the iPhone app's light mode is the Iridescent/Light
gradient with the Pearl dust on every screen and sheet, its cards are glass
with the nacre edge, its muted grey is #514D67, the Allowance orb is one
shared view that Home draws, and nothing is left of the pearl-paper page.
Dark values are untouched."""

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

    def test_sheets_sit_on_the_iridescent_background(self):
        menus = code(src("ios/Pearl/Views/Transactions/SplitMenus.swift"))
        assert ".background(SheetBackground())" in menus
        assert "presentationBackground { SheetBackground() }" in menus
        tx = code(src("ios/Pearl/Views/Transactions/TransactionsView.swift"))
        sheet = tx[tx.index("struct SheetBackground"):]
        sheet = sheet[:sheet.index("\n}\n") + 3]
        assert "NacreBackground()" in sheet, "a light sheet is the page's own background"
        assert "0x1C2F73" in sheet and "0x12163F" in sheet, "the dark sheet gradient is unchanged"

    def test_card_tokens_are_glass(self):
        theme = code(src(self.THEME))
        assert "UIColor(white: 1, alpha: 0.72)" in theme, "color/surface/card light is white @72%"
        assert "UIColor(hex: 0x151B44)" in theme, "color/surface/card dark is unchanged"
        assert "UIColor(white: 1, alpha: 0.8)" in theme, "color/border/subtle light is white @80%"
        assert "UIColor(hex: 0x252C5E)" in theme, "color/border/subtle dark is unchanged"
        assert "static let cardShadow = Color(hex: 0x664D99)" in theme
        nacre = code(src(self.NACRE))
        surface = nacre[nacre.index("struct GlassSurface"):nacre.index("struct GlassCard")]
        assert ".background(.ultraThinMaterial, in: shape)" in surface, "one blur per card"
        assert "shape.strokeBorder(Nacre.horizontal, lineWidth: 1.2)" in surface, "Nacre/Horizontal 1.2 pt edge"
        assert "Pearl.cardShadow.opacity(scheme == .dark ? 0.12 : 0.10)" in surface
        assert "radius: scheme == .dark ? 12 : 20, y: 8" in surface
        assert "static let separator = Pearl.border" in nacre, "in-card dividers are color/border/subtle"

    def test_solid_cards_became_glass_in_light(self):
        """The split sheets' white cards (S-03*, S-04*, S-40*, S-06r*, S-07r*,
        S-34*) and the Home cards go through one modifier, which keeps the
        dark look and blurs once per card."""
        for path in ("ios/Pearl/Views/Components/Components.swift",
                     "ios/Pearl/Views/Transactions/SplitMenus.swift",
                     "ios/Pearl/Views/Transactions/SplitFlow.swift",
                     "ios/Pearl/Views/Transactions/JointSplitViews.swift",
                     "ios/Pearl/Views/Transactions/PaybackOptions.swift"):
            text = code(src(path))
            assert ".pearlCard(radius:" in text, path
            # A card-sized solid fill followed by the 1 pt border on the next
            # line: the old card. (A field or an answer, radiusChoice, is not a card.)
            by_hand = re.search(r"cornerRadius: Pearl\.radius(?:Tile|Row|Card), style: \.continuous\)\.fill\(Pearl\.card\)\)\n"
                                r"\s*\.overlay\(RoundedRectangle\([^\n]*\n?\s*\.stroke\(Pearl\.border, lineWidth: 1\)\)", text)
            assert not by_hand, f"{path} still draws a solid card with a 1 pt border by hand"
        nacre = code(src(self.NACRE))
        style = nacre[nacre.index("private struct PearlCardStyle"):]
        assert "if scheme == .dark" in style and ".background(shape.fill(Pearl.card))" in style
        assert "content.glassCard(radius: radius)" in style

    def test_pearl_dust_is_one_view_under_every_light_page(self):
        dust = src(self.DUST)
        assert "struct PearlDust: View" in dust
        bubbles = re.findall(r"Bubble\(x: (\d+), y: (\d+), size: (\d+)\)", dust)
        assert [tuple(map(int, b)) for b in bubbles] == [
            (338, 60, 9), (360, 76, 5), (324, 80, 4), (348, 89, 6), (367, 58, 4), (333, 96, 3),
            (4, 337, 4), (4, 551, 4), (2, 584, 6), (382, 624, 6)]
        assert "aura(size: 360, opacity: 0.5)" in dust and "aura(size: 280, opacity: 0.4)" in dust
        assert ".blur(radius: 90)" in dust
        assert ".accessibilityHidden(true)" in dust and ".allowsHitTesting(false)" in dust
        nacre = code(src(self.NACRE))
        background = nacre[nacre.index("struct NacreBackground"):nacre.index("extension View")]
        light = background[background.index("} else {"):]
        assert "PearlDust(width: w)" in light, "light draws the Pearl dust over the gradient"
        assert 'Image("Bubbles")' not in light, "the old bubble picture is dark mode's only"
        assert "Nacre.rose, Nacre.lilac, Nacre.seaglass" in light, "Iridescent/Light is unchanged"

    def test_allowance_orb_is_shared_and_home_uses_it(self):
        orb = src(self.ORB)
        assert "struct AllowanceOrb: View" in orb
        for layer in ("Circle().fill(Self.nacre)", ".blur(radius: 60)", ".opacity(0.45)",          # halo
                      "strokeBorder(.white.opacity(0.55), lineWidth: Self.ring)",                  # track
                      "Color(hex: 0xD999FF).opacity(0.45), radius: 18",                            # arc glow
                      "Circle().fill(Nacre.glass)", ".background(.ultraThinMaterial, in: Circle())",
                      "strokeBorder(Nacre.horizontal, lineWidth: 1)",                              # disc
                      "Color(hex: 0x734D99).opacity(0.15), radius: 30, y: 10",
                      "Color(hex: 0xFFD9F2).opacity(0.95), radius: 14",                            # thumb
                      'font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)'):
            assert layer in orb, layer
        assert "0xFF8FB1" in orb and "0xC9A8FF" in orb and "0x8FE0D4" in orb and "0xFFD6E0" in orb
        assert ".accessibilityElement(children: .ignore)" in orb
        assert "withAnimation" not in orb and ".animation(" not in orb, "no motion yet"
        home = code(src(self.HOME))
        assert "AllowanceOrb(progress:" in home
        assert 'label: "Allowance"' in home
        assert "Allowance.restCaption" in home, "the hidden caption stays as the VoiceOver hint"
        onboarding = code(src("ios/Pearl/Views/Onboarding/AllowanceView.swift"))
        assert "AllowanceOrb(progress: progress" in onboarding, "O-11b draws the same orb"
        assert '"left in \\(Format.monthName(month))"' in onboarding
        for path in swift_files():
            assert "AllowanceRing" not in code(path.read_text(encoding="utf-8")), path

    def test_house_rules(self):
        for path in swift_files():
            text = path.read_text(encoding="utf-8")
            assert "safe to spend" not in text.lower(), f"{path.relative_to(ROOT)} says safe to spend"
        for path in (self.ORB, self.DUST):
            assert "REFRESH-05" in src(path)
