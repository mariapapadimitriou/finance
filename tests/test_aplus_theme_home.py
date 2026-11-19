"""A+ theme and Home (REDESIGN-04 to -08, -13, -14; the chosen redesign,
2026-11-18), by source: the shared styles render A+, Home matches AP-Home,
AP-HomeCalm and AP-PhotoHome, Worth a look is wired to /api/worth-a-look,
Owed to you has its person page, and G6-Offline is built."""

from __future__ import annotations

from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
IOS = ROOT / "ios" / "Pearl"


def read(*parts: str) -> str:
    return (IOS.joinpath(*parts)).read_text(encoding="utf-8")


def code(text: str) -> str:
    return "\n".join(l for l in text.splitlines() if not l.strip().startswith("//"))


class TestSharedStyles:
    def test_buttons_are_the_a_plus_capsules(self):
        nacre = code(read("Theme", "Nacre.swift"))
        comps = code(read("Views", "Components", "Components.swift"))
        menus = code(read("Views", "Transactions", "SplitMenus.swift"))
        for text in (nacre, comps, menus):
            assert "APPrimaryLook(" in text
        assert "APSecondaryLook(" in comps and "APSecondaryLook(" in menus
        assert "Nacre.horizontal" not in nacre[nacre.index("struct NacreButtonStyle"):nacre.index("struct NacreTextButtonStyle")], \
            "dark primary is the action pink, not the nacre gradient"
        aplus = code(read("Theme", "APlus.swift"))
        look = aplus[aplus.index("struct APPrimaryLook"):aplus.index("struct APSecondaryLook")]
        assert "minHeight: 50" in look and "Pearl.action.opacity(0.22)" in look

    def test_quiet_actions_are_link(self):
        nacre = code(read("Theme", "Nacre.swift"))
        quiet = nacre[nacre.index("struct NacreTextButtonStyle"):]
        assert "var tone: Color = Pearl.link" in quiet

    def test_close_back_and_more_are_glass_circles(self):
        menus = code(read("Views", "Transactions", "SplitMenus.swift"))
        assert menus.count(".background(APGlassCircle())") >= 3
        tx = code(read("Views", "Transactions", "TransactionsView.swift"))
        title = tx[tx.index("struct SheetTitle"):tx.index("struct SheetBackground")]
        assert "APGlassCircle()" in title

    def test_fields_radios_and_switches(self):
        nacre = code(read("Theme", "Nacre.swift"))
        field = nacre[nacre.index("struct FieldRow"):nacre.index("struct Hint")]
        assert ".wellStyle(focused: focused)" in field, "every place she can type is a well"
        assert "APlus.well" in nacre[nacre.index("struct CodeBoxes"):]
        assert ".toggleStyle(APToggleStyle())" in nacre
        comps = code(read("Views", "Components", "Components.swift"))
        assert "lineWidth: on ? 7 : 1.5" in comps and "width: 24, height: 24" in comps

    def test_light_tab_bar_is_see_through_with_the_lilac_lozenge(self):
        app = code(read("App", "PearlApp.swift"))
        assert "tabs.configureWithTransparentBackground()" in app
        assert "selectionIndicatorTintColor = UIColor(APlus.tabLozenge)" in app
        assert "badgeBackgroundColor = UIColor(Pearl.action)" in app, "the badge uses the tint"


class TestHome:
    home = code(read("Views", "Home", "HomeView.swift"))

    def test_attention_only(self):
        for gone in ("MonthCard", "PearlSortedCard", "so far\")", "patternWeek"):
            assert gone not in self.home, gone
        assert 'APSectionLabel(text: "Needs a look", action: "See the list"' in self.home
        assert "SortStreak(sorted: pearlSorted, toSort: count)" in self.home
        assert '"Sort now"' in self.home
        assert "people owe you" in self.home and "OwedCard(" in self.home
        assert "BankAlertCard(" in self.home, "a bank to reconnect keeps its own card"
        assert "ProfileCircle()" in self.home

    def test_calm_state(self):
        assert "CalmState()" in self.home
        assert "size: calm ? AllowanceOrb.full : AllowanceOrb.small" in self.home

    def test_worth_a_look_is_wired(self):
        assert '"api/worth-a-look"' in self.home
        for action in ('"clear"', '"undo_clear"', '"yes"', '"not_now"', '"undo_yes"', '"seen"'):
            assert action in self.home, action
        worth = code(read("Views", "Home", "WorthALook.swift"))
        assert 'APSectionLabel(text: "Worth a look", action: "Clear"' in worth
        assert "items.prefix(3)" in worth
        assert 'Button("Not now"' in worth

    def test_offline(self):
        app = code(read("App", "PearlApp.swift"))
        assert "CantReachPearlView {" in app
        offline = read("Views", "Home", "CantReachPearl.swift")
        assert "Can\\u{2019}t reach Pearl" in offline
        assert "Check your connection. Your money is safe; Pearl only reads it." in offline
        assert "showing Pearl from" in offline
        assert "OfflineBanner(since:" in self.home

    def test_house_rules(self):
        for path in (IOS / "Views" / "Home").glob("*.swift"):
            text = path.read_text(encoding="utf-8")
            assert "safe to spend" not in text.lower()
            for stock in (".alert(", ".confirmationDialog(", "actionSheet("):
                assert stock not in text, (path.name, stock)


class TestOwed:
    owed = code(read("Views", "Home", "OwedViews.swift"))

    def test_owed_to_you_and_the_person_page(self):
        assert "struct OwedView: View" in self.owed and "struct OwedPersonView: View" in self.owed
        assert 'OwedTitle(title: "Owed to you")' in self.owed
        assert '"Owes you for"' in self.owed
        assert "PersonOptionsSheet(t: o.t, split: o.split, p: o.p" in self.owed
        assert "onOpen:" in self.owed
        menus = code(read("Views", "Transactions", "SplitMenus.swift"))
        assert 'Button("Open \\(t.merchant)", action: onOpen)' in menus
        detail = code(read("Views", "Transactions", "TransactionDetailView.swift"))
        assert "runStartChoice()" in detail
        assert "struct OwedView" not in read("Views", "Transactions", "PartsFlow.swift")

    def test_see_who_else_owes_you(self):
        flow = read("Views", "Transactions", "SplitFlow.swift")
        assert "See who else owes you" in flow and "See everyone who owes you" not in flow
