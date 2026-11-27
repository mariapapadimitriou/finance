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
        assert ".profileCircleSlot(labelled: true)" in self.home, "P12a: Home's Profile has its word"

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
        # P1a (TP-Words): For you · Dismiss.
        assert 'APSectionLabel(text: "For you", action: "Dismiss"' in worth
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

    def test_everyone_who_owes_you_is_a_secondary_button(self):
        """P16a/b (TP-P16-OwedButton): the rose link became the Secondary
        button, 12 under the split card, in both places it's drawn."""
        for path in (("Views", "Transactions", "SplitFlow.swift"), ("Views", "Transactions", "CashFlowKit.swift")):
            flow = code(read(*path))
            assert "who else owes you" not in flow and "See everyone who owes you" not in flow
            at = flow.index('Button("Everyone who owes you", action: onOwed)')
            button = flow[at:at + 260]
            assert "SecondaryButtonStyle()" in button and ".padding(.top, 12)" in button, path
            assert "Pearl.link" not in button

    def test_one_list_biggest_first_ties_a_to_z(self):
        """P17a: one list, each person's total, biggest first, ties A–Z."""
        assert "OwedList(people: people" in self.owed and "OwedView.sorted(owed.owesYou)" in self.owed
        assert "if abs(a.total - b.total) >= 0.005 { return a.total > b.total }" in self.owed
        assert "a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending" in self.owed
        # P17a / P17c: the header line.
        assert '"\\(one.name) owes you"' in self.owed and '"\\(people.count) people owe you"' in self.owed
        # The old sections are gone from the main page.
        assert "struct OwedSections" not in self.owed
        assert 'APSectionLabel(text: "Owes you")' in self.owed

    def test_also_rows_only_when_they_have_something(self):
        """P17b: You owe (its amount), Not settled ("1 split"), Paid back
        this month (+ in green), each opening its own page (P17f–h)."""
        rows = self.owed[self.owed.index("static func rows(_ owed: OwedOverview)"):]
        rows = rows[:rows.index("\n    }\n")]
        assert "if !owed.youOwe.isEmpty" in rows and 'title: "You owe", value: Format.amount(owe)' in rows
        assert 'n == 1 ? "1 split" : "\\(n) splits"' in rows and "if n > 0" in rows
        assert "if !owed.paidBack.isEmpty" in rows and '"Paid back this month", value: "+" + Format.amount(back)' in rows
        assert "if !rows.isEmpty" in self.owed and 'APSectionLabel(text: "Also")' in self.owed
        for page in ('return "You owe"', 'return "Not settled"', 'return "Paid back"'):
            assert page in self.owed, page
        # P17f: the one explaining line moved to Not settled's page.
        assert self.owed.count('"Not in the total until settled."') == 1
        assert 'line: n == 1 ? "to 1 person" : "to \\(n) people"' in self.owed
        assert 'line: "this month",\n                           sign: "+", tone: Pearl.moneyIn' in self.owed
        # S-14o: You owe's rows still open the person's options there.
        assert "Button { oweBack = r }" in self.owed and ".modifier(OweBackOptions(row: $oweBack))" in self.owed

    def test_nobody_owes_you(self):
        """P17d: the pearl and one calm line; Also still shows below."""
        assert "PearlOrb(size: 96)" in self.owed and '"Nobody owes you anything."' in self.owed
        body = self.owed[self.owed.index("struct OwedView: View"):self.owed.index("static func sorted")]
        assert body.index("OwedNobody(arrived: allPaid)") < body.index("OwedAlsoRows(owed: owed")

    def test_long_names_and_amounts(self):
        """P17e: a long name is one line with "…"; the amount never shrinks
        and moves under the name at the larger text sizes."""
        row = self.owed[self.owed.index("struct OwedRow: View"):]
        assert ".lineLimit(1).truncationMode(.tail)" in row
        assert "typeSize.isAccessibilitySize" in row
        figure = row[row.index("private var figure"):]
        figure = figure[:figure.index("\n    }\n")]
        assert ".fixedSize()" in figure and "minimumScaleFactor" not in figure and "pearlAmountFit" not in figure

    def test_motion_has_reduce_motion_fallbacks(self):
        """P17a/c/d motion, each with its Reduce Motion fallback."""
        for words in ("withAnimation(.easeOut(duration: 0.35)) { shown = total }",
                      ".delay(Double(min(index, 12)) * 0.03)", "withAnimation(.easeInOut(duration: 0.15)) { shown = true }",
                      "UIImpactFeedbackGenerator(style: .light).impactOccurred()",
                      "UINotificationFeedbackGenerator().notificationOccurred(.success)",
                      "withAnimation(.easeOut(duration: reduceMotion ? 0.15 : 0.4))"):
            assert words in self.owed, words
        assert self.owed.count("accessibilityReduceMotion") >= 4

    def test_initials_skip_emoji(self):
        """P17e: "Mia 💋 Rossi" → MR, "🎉 Party fund" → PF."""
        kit = code(read("Theme", "APlus.swift"))
        assert "name.split { !$0.isLetter && !$0.isNumber }.prefix(2)" in kit
