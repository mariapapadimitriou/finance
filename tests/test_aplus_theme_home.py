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
        assert "minHeight: sortCard ? 48 : 50" in look and "Pearl.action.opacity(0.22)" in look

    def test_quiet_actions_are_link(self):
        nacre = code(read("Theme", "Nacre.swift"))
        quiet = nacre[nacre.index("struct NacreTextButtonStyle"):]
        assert "var tone: Color = Pearl.link" in quiet

    def test_close_back_and_more_are_glass_circles(self):
        menus = code(read("Views", "Transactions", "SplitMenus.swift"))
        assert menus.count(".background(APGlassCircle())") >= 2
        assert "APSheetHeader(face: face, symbol: symbol" in menus, "the old sheet header draws #385's"
        assert "APOptionRow(" in menus and "APIcon(symbol: symbol)" in menus
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

    def test_tab_bar_is_the_boards(self):
        # shared.css `.A.phone .tabs.lg`: white 80% / #151B44 @78% over a
        # blur, black / white words, #9C1F4B / #FFB8CE selected on a lens.
        app = code(read("App", "PearlApp.swift"))
        assert "tabs.configureWithTransparentBackground()" in app
        assert "UIColor(white: 1, alpha: 0.80)" in app and "alpha: 0.78" in app
        assert "0xFFB8CE : 0x9C1F4B" in app
        assert "tabs.selectionIndicatorTintColor" in app
        assert "badgeBackgroundColor = UIColor(Pearl.action)" in app, "the badge uses the tint"


class TestHome:
    home = code(read("Views", "Home", "HomeView.swift"))

    def test_attention_only(self):
        for gone in ("MonthCard", "PearlSortedCard", "so far\")", "patternWeek"):
            assert gone not in self.home, gone
        assert 'APSectionLabel(text: "Needs a look", action: "See the list"' in self.home
        # H-00r v2 (supersedes r7's "no streak dashes"): the 12 dashes are back.
        assert "SortStreak(sorted: sorted, toSort: count, sortCard: true)" in self.home
        assert '"Sort now"' in self.home
        assert "sorted: home.sorted ?? home.pearlSorted ?? 0" in self.home, "REDESIGN-18"
        assert "people owe you" in self.home and "OwedCard(" in self.home
        assert "BankAlertCard(" in self.home, "a bank to reconnect keeps its own card"
        assert ".profileCircleSlot()" in self.home

    def test_paycheque_is_a_worth_a_look_item(self):
        # T-74 (AP-Paycheque): Got it on the item; no separate card; nothing opens Your plan.
        assert "PaychequeNoteCard" not in self.home and '"got_it"' in self.home
        worth = code(read("Views", "Home", "WorthALook.swift"))
        assert "Button(ack, action: onGotIt)" in worth
        assert '"plan"' not in worth and "YourPlanView" not in self.home
        assert 'case "allowance":' in self.home

    def test_calm_state(self):
        assert "CalmState()" in self.home
        # AP-HomeCalm (H-00r v2): the same gauge as a busy Home, then the line.
        assert "HomeOrb(home: home, openAddsUp: actions.addsUp)" in self.home

    def test_greeting_and_faces(self):
        # H-00r v2 (home.css): the greeting by time of day, her first name;
        # "2 people owe you" shows who, and a chevron.
        assert "HomeTopBar.greeting(name: app.user?.firstName)" in self.home
        assert 'hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"' in self.home
        assert "OwedFaces(names: owed.owesYou.prefix(3).map(\\.name))" in self.home
        assert "case .addsUp: AddsUpView()" in self.home

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
        flow = code(read("Views", "Transactions", "SplitFlow.swift"))
        assert "See who else owes you" in flow and "See everyone who owes you" not in flow
