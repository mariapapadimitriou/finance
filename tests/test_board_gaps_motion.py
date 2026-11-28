"""Board gaps after the fewer-taps PRs (Pearl redesign canvas v102): P3b /
P4b motion (the tile fills, the card tilts 7° as it leaves, Reduce Motion
crossfades), P5f's success haptic, and P15b's "Also try", from her own
purchases, never a fixed list."""

from __future__ import annotations

import re
import sys
from pathlib import Path

sys.path.insert(0, "tests")
IOS = Path(__file__).resolve().parent.parent / "ios" / "Pearl"


def src(rel: str) -> str:
    return (IOS / rel).read_text()


QS = "Views/Review/QuickSortView.swift"
CAT = "Views/Transactions/CategorySheet.swift"
KIT = "Views/Transactions/CashFlowKit.swift"


def test_a_sorted_card_tilts_seven_degrees_as_it_leaves():
    s = src(QS)
    assert "static let tilt: Double = 7" in s
    assert "Animation.spring(response: 0.32, dampingFraction: 0.8)" in s
    # Never the old 33° (600 / 18) on the way out, and never past 7° while dragging.
    assert "offsetX / 18" not in s
    assert "max(-Self.tilt, min(Self.tilt" in s
    # Every way a card leaves goes through the one motion.
    assert "withAnimation(.easeIn(duration: 0.25)) { leaving" not in s
    assert s.count("fly(true)") + s.count("fly(false)") >= 8
    assert s.count(".modifier(away)") == 4      # + TR-30's pair card (THL-309)


def test_reduce_motion_crossfades_the_card():
    s = src(QS)
    assert "@Environment(\\.accessibilityReduceMotion) private var reduceMotion" in s
    assert "fade: reduceMotion && leaving != nil" in s
    assert "insertion: reduceMotion ? .opacity : .scale(scale: 0.96)" in s
    assert s.count(".transition(arrival)") == 4


def test_the_next_card_comes_up_and_the_tapped_tile_fills():
    s = src(QS)
    nxt = s[s.index("private func next()"):]
    nxt = nxt[:nxt.index("\n    }\n")]
    assert "withAnimation(.easeOut(duration: reduceMotion ? 0.2 : 0.3))" in nxt
    assert "pressed = nil" in nxt
    assert "mark: pressed == c.name ? .pressed : .rest" in s
    kit = src(KIT)
    assert "case rest, current, guess, pressed" in kit
    assert "mark == .pressed && !reduceMotion ? 0.96 : 1" in kit
    assert "mark == .pressed ? Pearl.action : APlus.card" in kit


def test_tile_haptic_is_light_and_payback_yes_is_success():
    s = src(QS)
    tile = s[s.index("private func tile(_ ask: Ask, _ name: String)"):]
    assert "UIImpactFeedbackGenerator(style: .light)" in tile[:400]
    yes = s[s.index("private func paybackYes"):]
    # P5h asks Who sent this? first, so the haptic sits after that branch.
    assert "notificationOccurred(.success)" in yes[:900]


def test_what_was_this_tile_fills_before_the_sheet_drops():
    s = src(CAT)
    assert "tapped == c.name ? .pressed" in s
    assert "asyncAfter(deadline: .now() + 0.12)" in s


def test_the_streak_fills_without_sliding():
    assert ".animation(.easeOut(duration: 0.2), value: on)" in src("Theme/APlus.swift")


def test_also_try_comes_from_her_purchases_not_a_list():
    s = src(CAT)
    assert '"api/transactions/list"' in s
    assert 'Text("Also try: ")' in s
    assert ".task(id: query) { await loadAlsoTry() }" in s
    fn = s[s.index("static func alsoTry"):]
    fn = fn[:fn.index("\n    }\n")]
    # No category or merchant names but the non-answer.
    assert not re.search(r'"(Gifts|Pets|Groceries|Dining|PetSmart)', fn)


def _also_try(filed, pool, showing):
    """The Swift rule, in Python, for the cases the board draws."""
    pickable = set(pool)
    counts, first = {}, {}
    for i, name in enumerate(filed):
        if name in pickable and name not in showing and name != "Other":
            counts[name] = counts.get(name, 0) + 1
            first.setdefault(name, i)
    ranked = sorted(counts, key=lambda n: (-counts[n], first[n]))
    return ranked[0] if ranked else None


def test_also_try_rule():
    pool = ["Pets", "Gifts & Charity", "Groceries", "Other"]
    # "pet": Pets is a result already; her PetSmart gifts say Gifts & Charity.
    assert _also_try(["Gifts & Charity", "Gifts & Charity", "Pets"], pool, {"Pets"}) == "Gifts & Charity"
    # Nothing she can pick, or only what's showing, or Other: no line.
    assert _also_try(["Income", "Other"], pool, set()) is None
    assert _also_try(["Pets"], pool, {"Pets"}) is None
    # Most first, then the newest.
    assert _also_try(["Groceries", "Gifts & Charity", "Gifts & Charity"], pool, set()) == "Gifts & Charity"
    assert _also_try(["Groceries", "Gifts & Charity"], pool, set()) == "Groceries"


def test_owed_at_the_largest_text_sizes():
    """P17 on the simulator at accessibility-extra-extra-extra-large: the
    face's initials were cut to "…", and Also's words broke mid-word."""
    face = src("Theme/APlus.swift")
    assert '.font(.custom("Figtree-Medium", fixedSize: size * 0.35))' in face
    owed = src("Views/Home/OwedViews.swift")
    row = owed[owed.index("private struct OwedAlsoRow"):]
    row = row[:row.index("@ViewBuilder private var icon")]
    assert "if typeSize.isAccessibilitySize {" in row
    assert "VStack(alignment: .leading, spacing: 2) {\n                    title\n                    value" in row
