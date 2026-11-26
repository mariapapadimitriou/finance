import SwiftUI
import UIKit
import UserNotifications

/// Home, A+ (AP-Home H-00r v2, AP-HomeCalm, AP-PhotoHome; REDESIGN-04 to
/// -06): the date, "Good morning, Maya" and the profile circle, the
/// Allowance gauge (n-home-gauge; it opens How it adds up), then only cards with
/// something in them: a bank to reconnect (H-01, its own card), Set Pearl up
/// again, NEEDS A LOOK (8 to sort, the streak, Sort now; See the list on the
/// label), "2 people owe you" (opens Owed to you) and WORTH A LOOK. Nothing
/// there: the orb at full size and "You're all caught up." "November so
/// far" (MonthCard) and AI-01's "Pearl sorted this week" are gone; Pearl's
/// sorting shows in the streak line.
@MainActor
struct HomeView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab

    @State private var home: Home?
    @State private var setup: SetupAgain?
    /// Who owes her on splits, for "2 people owe you".
    @State private var owed: OwedOverview?
    @State private var worth: [WorthItem] = []
    @State private var error: String?
    /// G6-Offline: when Home last came back, and whether the last try failed.
    @State private var loadedAt: Date?
    @State private var offline = false
    /// N-01's quiet hours, while it's showing.
    @State private var askingToNotify: NotificationSettings.Quiet?
    @State private var checkedNotify = false
    /// H-01's Reconnect.
    @State private var reconnecting: Home.Connection?
    /// Where a tap goes: Accounts, the list, Owed to you, a Worth a look item.
    @State private var route: HomeRoute?
    /// H-00r's Sort now: Quick sort, straight from Home (TEST-04); a trip
    /// item opens just its trip question.
    @State private var quickSort: QuickSortDeck?
    @State private var opening = false
    /// The new-month item scrolls Home back to its Allowance.
    @State private var toOrb = 0

    var body: some View {
        ScrollViewReader { proxy in
        ScrollView {
            if let home = home {
                HomeFeed(home: home, setup: setup, owed: owed, worth: worth,
                         offlineSince: offline ? loadedAt : nil, sorting: opening,
                         actions: actions)
            } else {
                VStack(spacing: 0) {
                    HomeTopBar(today: nil)
                    LoadState(error: error) { Task { await load() } }
                }
                .padding(.horizontal, Pearl.gutter)
            }
        }
        .onChange(of: toOrb) { _ in withAnimation { proxy.scrollTo(HomeOrb.anchor, anchor: .top) } }
        }
        .nacreScreen()
        // Pinned, not in the feed: it stays put as Home scrolls.
        .profileCircleSlot()
        .navigationBarHidden(true)
        .refreshable { await load() }
        .reloads { await load() }
        .navigationDestination(isPresented: Binding(get: { route != nil }, set: { if !$0 { route = nil } })) {
            if let route = route { HomeDestination(route: route) }
        }
        .sheet(item: $reconnecting) { c in
            ReconnectSheet(bank: c.institution ?? "your bank", label: c.institution ?? "Your bank",
                           itemId: c.itemId, updatedAt: c.lastSynced) { ok in
                reconnecting = nil
                if ok { app.changed() }
            }
            .background(SheetBackground())
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .fullScreenCover(item: $askingToNotify) { quiet in
            TurnOnNotificationsView(quiet: quiet)
        }
        .fullScreenCover(item: $quickSort) { deck in
            QuickSortView(asks: deck.asks, categories: app.categories, names: deck.names,
                          patterns: deck.patterns, trips: deck.trips) {
                quickSort = nil
                Task { await load() }
            }
        }
    }

    private var actions: HomeActions {
        HomeActions(
            sortNow: { Task { await sortNow() } },
            seeList: { route = .review },
            seeOwed: { route = .owed },
            addsUp: { route = .addsUp },
            accounts: { route = .accounts },
            reconnect: { reconnecting = $0 },
            reload: { Task { await load() } },
            clear: { Task { await clearWorth() } },
            open: { item in Task { await open(item) } },
            yes: { item in Task { await answer(item, yes: true) } },
            notNow: { item in Task { await answer(item, yes: false) } },
            gotIt: { item in Task { await gotIt(item) } })
    }

    // MARK: Loading

    private func load() async {
        // Pearl sorts for you (P1a): what can be sorted from her own answers,
        // before Home counts what's left. Off, it does nothing.
        struct Ran: Decodable { let sorted: Int }
        _ = try? await app.api.post("api/pattern-sort/run", [:]) as Ran
        do {
            // All four at once (perf rehaul, 2026-11-19), each shown from
            // its kept answer the moment it's asked for and settled when the
            // server says it changed (ScreenStore); Home's failure still
            // ends the load.
            let screens = app.screens
            async let setupLoad: Bool? = try? screens.load("api/setup-again", as: SetupAgain.self) { setup = $0 }
            async let owedLoad: Bool? = try? screens.load("api/owed", as: OwedOverview.self) { owed = $0 }
            async let worthLoad: Bool? = try? screens.load("api/worth-a-look", as: WorthReply.self) { worth = $0.items }
            try await screens.load("api/home", as: Home.self, apply: { loaded in
                home = loaded
                // The Allowance Home shows is the app's: a kept answer seeds
                // it only when there is none yet (a write may have moved it
                // since), the server's own always does.
                if app.allowance == nil { app.seed(loaded) }
            }, fresh: { app.seed($0) })
            _ = await (setupLoad, owedLoad, worthLoad)
            error = nil
            offline = false
            loadedAt = Date()
            await offerNotifications()
        } catch {
            // G6-Offline: Home stays as it was, under the banner.
            if home != nil, (error as? APIError) == .offline {
                offline = true
            } else {
                self.error = app.handle(error)
            }
        }
    }

    /// N-01 (THL-139): once the Allowance has a number, if iOS hasn't asked
    /// yet (setup's O-08b may have) and N-01 hasn't been answered on any device.
    private func offerNotifications() async {
        guard !checkedNotify, home?.safeToSpend?.state == "ok" else { return }
        checkedNotify = true
        let status = await UNUserNotificationCenter.current().notificationSettings().authorizationStatus
        guard status == .notDetermined,
              let settings: NotificationSettings = try? await app.api.get("api/notifications"),
              settings.prefs.prompt?.answer == nil else { return }
        askingToNotify = settings.prefs.quiet
    }

    /// H-00r (REFRESH-00 decision 2): Sort now opens Quick sort with every
    /// open question, not only today's new ones.
    private func sortNow() async {
        guard !opening else { return }
        opening = true
        defer { opening = false }
        do {
            let prompt: QuickSortPrompt = try await app.api.get("api/quick-sort", query: ["all": "1"])
            quickSort = QuickSortDeck(asks: prompt.asks, names: prompt.review?.people ?? [],
                                      patterns: prompt.patterns, trips: prompt.trips)
        } catch {
            if let words = app.handle(error) { app.say(words) }
        }
    }

    // MARK: Worth a look

    /// Clear hides every item; Undo on the ink toast brings them back.
    private func clearWorth() async {
        let ids = worth.map(\.id)
        guard !ids.isEmpty else { return }
        do {
            let reply: WorthReply = try await app.api.post("api/worth-a-look", ["action": "clear", "ids": ids])
            withAnimation { worth = reply.items }
            // TEST-40: the server clears all that qualifies today; Undo brings all of it back.
            let cleared = reply.cleared ?? ids
            app.say("Cleared", undo: { [api = app.api] in
                let _: WorthReply = try await api.post("api/worth-a-look", ["action": "undo_clear", "ids": cleared])
            })
        } catch {
            if let words = app.handle(error) { app.say(words) }
        }
    }

    /// Yes (or Update the bill) does it, the row leaves and the next slides
    /// up; only the toast says what happened, with Undo. Not now: for good.
    private func answer(_ item: WorthItem, yes: Bool) async {
        do {
            let reply: WorthReply = try await app.api.post("api/worth-a-look",
                                                          ["action": yes ? "yes" : "not_now", "id": item.id])
            withAnimation { worth = reply.items }
            guard yes else { return }
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            app.say(reply.toast ?? "Done", undo: { [api = app.api] in
                let _: WorthReply = try await api.post("api/worth-a-look", ["action": "undo_yes", "id": item.id])
            })
            app.changed()
        } catch {
            if let words = app.handle(error) { app.say(words) }
        }
    }

    /// T-74's Got it (the old note's): it doesn't come back, here or anywhere.
    private func gotIt(_ item: WorthItem) async {
        do {
            let reply: WorthReply = try await app.api.post("api/worth-a-look", ["action": "got_it", "id": item.id])
            withAnimation { worth = reply.items }
        } catch {
            if let words = app.handle(error) { app.say(words) }
        }
    }

    /// A one-tap item: seen, then where it lives.
    private func open(_ item: WorthItem) async {
        let _: WorthReply? = try? await app.api.post("api/worth-a-look", ["action": "seen", "id": item.id])
        guard let target = item.target, let screen = target.screen else { return }
        switch screen {
        case "trip":
            // TR-01: just this trip's question, as Quick sort asks it.
            if let prompt: QuickSortPrompt = try? await app.api.get("api/quick-sort", query: ["all": "1"]) {
                let trips = prompt.trips.filter { $0.id == target.id || $0.key == target.id }
                if !trips.isEmpty {
                    quickSort = QuickSortDeck(asks: [], names: prompt.review?.people ?? [], patterns: [], trips: trips)
                }
            }
        case "category":
            // Cash flow filtered to that category (CashFlowFocus, TransactionsView.swift).
            if let name = target.name { CashFlowFocus.shared.show(category: name, month: target.month) }
            tab = .cashFlow
        case "income" where target.month != nil:
            // T-74 (AP-Paycheque): that month's income in Cash flow (CashFlowFocus).
            CashFlowFocus.shared.show(category: "Income", month: target.month)
            tab = .cashFlow
        case "allowance":
            // The new month: Home's own Allowance, the orb at the top.
            toOrb += 1
        default:
            if let r = HomeRoute(target) { route = r }
        }
        if let w: WorthReply = try? await app.api.get("api/worth-a-look") { worth = w.items }
    }
}

/// What Quick sort opens with.
struct QuickSortDeck: Identifiable {
    let id = UUID()
    var asks: [Ask]
    var names: [String]
    var patterns: [PatternAsk]
    var trips: [TripAsk]
}

/// Where Home goes.
enum HomeRoute: Hashable {
    case review, owed, accounts, addsUp
    case owedPerson(String)
    case transaction(String)
    case bills, debts

    init?(_ t: WorthItem.Target) {
        switch t.screen {
        case "transaction": guard let id = t.id else { return nil }; self = .transaction(id)
        case "owed_person": guard let name = t.name else { return nil }; self = .owedPerson(name)
        case "owed": self = .owed
        case "bill": self = .bills
        case "debt": self = .debts
        case "income": self = .bills
        case "review": self = .review
        default: return nil
        }
    }
}

private struct HomeDestination: View {
    @EnvironmentObject private var app: AppModel
    let route: HomeRoute

    var body: some View {
        switch route {
        case .review: ReviewView()
        case .owed: OwedView()
        case .accounts: AccountsView()
        case .addsUp: AddsUpView()
        case .owedPerson(let name): OwedPersonView(name: name)
        case .transaction(let id): TransactionByID(id: id, categories: app.categories)
        case .bills: IncomeBillsView()
        case .debts: DebtsView()
        }
    }
}

/// Everything Home's cards can ask for.
struct HomeActions {
    let sortNow: () -> Void
    let seeList: () -> Void
    let seeOwed: () -> Void
    /// The gauge: How it adds up (n-home-gauge).
    let addsUp: () -> Void
    let accounts: () -> Void
    let reconnect: (Home.Connection) -> Void
    let reload: () -> Void
    let clear: () -> Void
    let open: (WorthItem) -> Void
    let yes: (WorthItem) -> Void
    let notNow: (WorthItem) -> Void
    let gotIt: (WorthItem) -> Void
}

// MARK: - The feed

/// The page under the orb: only what has something in it.
private struct HomeFeed: View {
    let home: Home
    let setup: SetupAgain?
    let owed: OwedOverview?
    let worth: [WorthItem]
    let offlineSince: Date?
    let sorting: Bool
    let actions: HomeActions

    private var troubled: [Home.Connection] {
        (home.connections ?? []).filter { ["needs_sign_in", "disconnected"].contains($0.state ?? "") }
    }

    private var owes: Bool { (owed?.people ?? 0) > 0 && (owed?.total ?? 0) >= 0.005 }

    /// AP-HomeCalm: nothing needs her.
    private var calm: Bool {
        troubled.isEmpty && !(setup?.active ?? false) && home.reviewCount == 0 && !owes
            && worth.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HomeTopBar(today: home.today)
            // Under the date, so the pinned profile circle never covers it.
            if let since = offlineSince {
                OfflineBanner(since: since).padding(.top, 4).padding(.bottom, 8)
            }
            HomeOrb(home: home, openAddsUp: actions.addsUp)
            if calm {
                CalmState().padding(.top, 12)
            } else {
                HomeCards(home: home, setup: setup, owed: owes ? owed : nil, troubled: troubled,
                          sorting: sorting, actions: actions)
                if !worth.isEmpty {
                    WorthALookSection(items: worth, onClear: actions.clear, onOpen: actions.open,
                                      onYes: actions.yes, onNotNow: actions.notNow, onGotIt: actions.gotIt)
                        .padding(.top, 20)
                }
            }
        }
        .padding(.horizontal, Pearl.gutter)
        .padding(.bottom, 32)
    }
}

/// H-00r v2 (home.css `.hhead`): the date (12/500, tracked 1.4, `muted`)
/// over "Good morning, Maya" (Fraunces 28/600), on the left; the profile
/// circle is pinned over Home by `profileCircleSlot`, so the row keeps its
/// 44 pt place on the right empty.
struct HomeTopBar: View {
    @EnvironmentObject private var app: AppModel
    let today: String?

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            VStack(alignment: .leading, spacing: 4) {
                Text((today.map { Format.day($0) } ?? "").uppercased())
                    .font(.custom("Figtree-Medium", size: 12, relativeTo: .caption)).tracking(1.4)
                    .foregroundColor(Pearl.muted)
                    .lineLimit(1).minimumScaleFactor(0.8)
                Text(HomeTopBar.greeting(name: app.user?.firstName))
                    .font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title)).tracking(-0.3)
                    .foregroundColor(Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.7)
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Color.clear.frame(width: ProfileSlot.size, height: ProfileSlot.size)
        }
        .frame(minHeight: ProfileSlot.size)
        .padding(.top, ProfileSlot.top)
    }

    /// home.css: morning before 12, afternoon 12 to 5, evening after 5;
    /// her first name when Pearl knows it.
    static func greeting(name: String?, at date: Date = Date()) -> String {
        let hour = Calendar.current.component(.hour, from: date)
        let part = hour < 12 ? "morning" : hour < 17 ? "afternoon" : "evening"
        let first = name?.split(separator: " ").first.map(String.init) ?? ""
        return first.isEmpty ? "Good \(part)" : "Good \(part), \(first)"
    }
}

/// H-00r v2 (n-home-gauge): the Allowance gauge, the same on a busy Home
/// and a calm one. Tapping it opens How it adds up. Without income, an
/// estimate or a month started part-way keep their line under it.
private struct HomeOrb: View {
    static let anchor = "home-orb"
    @EnvironmentObject private var app: AppModel
    let home: Home
    let openAddsUp: () -> Void

    /// The app's Allowance (moved by every write's `changed`), else Home's own.
    private var sts: Allowance? { app.allowance ?? home.safeToSpend }

    var body: some View {
        VStack(spacing: 10) {
            if let sts = sts {
                AllowanceGauge(allowance: sts, open: openAddsUp)
            }
            if let caption = sts?.ringCaption ?? Optional(Allowance.needsIncomeLine),
               sts?.state != "over", caption != Allowance.restCaption {
                Text(caption).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity)
        .id(HomeOrb.anchor)
        .padding(.top, 14)
    }
}

/// The bank cards, Set Pearl up again, Needs a look, who owes her, a note.
private struct HomeCards: View {
    let home: Home
    let setup: SetupAgain?
    let owed: OwedOverview?
    let troubled: [Home.Connection]
    let sorting: Bool
    let actions: HomeActions

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            // H-02 (THL-120, rethought): only the worst bank (the server sends
            // them worst first); the others wait in Accounts.
            if let c = troubled.first {
                BankAlertCard(connection: c, today: home.today, more: troubled.count - 1,
                              openAccounts: actions.accounts) {
                    actions.reconnect(c)
                }
                .padding(.top, 10)
            }
            if let setup = setup, setup.active {
                SetupAgainCard(setup: setup, onChanged: actions.reload).padding(.top, 18)
            }
            if home.reviewCount > 0 {
                APSectionLabel(text: "Needs a look", action: "See the list", act: actions.seeList)
                    .padding(.top, 18).padding(.bottom, 8)
                NeedsALookCard(count: home.reviewCount, pearlSorted: home.pearlSorted ?? 0,
                               sorted: home.sorted ?? home.pearlSorted ?? 0,
                               busy: sorting, onSort: actions.sortNow)
            }
            if let owed = owed {
                OwedCard(owed: owed, open: actions.seeOwed).padding(.top, 12)
            }
        }
    }
}

/// H-00r (TEST-04; AP-Home): "8 to sort", "About a minute · Pearl sorted 40",
/// the 12-dash streak (B's, REDESIGN-02) and Sort now. See the list sits on
/// the label above.
struct NeedsALookCard: View {
    let count: Int
    var pearlSorted = 0
    /// REDESIGN-18: her answers plus Pearl's, over the same window as `count`.
    var sorted = 0
    var busy = false
    let onSort: () -> Void

    /// About ten seconds a card.
    private var howLong: String {
        let minutes = Int((Double(count) * 10 / 60).rounded())
        return minutes <= 1 ? "About a minute" : "About \(minutes) minutes"
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                SortIcon()
                VStack(alignment: .leading, spacing: 2) {
                    // H-00r v2 (home.css `.sortcard .n`): Fraunces 22/600.
                    Text("\(count) to sort")
                        .font(.custom("Fraunces-SemiBold", size: 22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    Text(howLong + (pearlSorted > 0 ? " \u{00B7} Pearl sorted \(pearlSorted)" : ""))
                        .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .accessibilityElement(children: .combine)
            // AP-Home (approved r7): no streak dashes on this card; the
            // words still say Pearl sorted N.
            Button("Sort now", action: onSort)
                .buttonStyle(PearlPrimaryButtonStyle(busy: busy, busyLabel: "Opening…"))
                .disabled(busy)
                .modifier(SortGlow())
        }
        .padding(18)
        .apCard()
    }
}

/// `.sortcard .sorticon`: 46 pt, 14 round, the nacre wash (rose, lilac,
/// seaglass at 140°) with a white inner line; softer in dark.
private struct SortIcon: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let dark = scheme == .dark
        let wash = dark ? [Color(hex: 0xFF8FB1).opacity(0.22), Color(hex: 0xC9A8FF).opacity(0.18), Color(hex: 0x8FE0D4).opacity(0.14)]
                        : [Color(hex: 0xFFE1EA), Color(hex: 0xF0E6FF), Color(hex: 0xDDF5EF)]
        return Image(systemName: "square.on.square").font(.system(size: 18)).foregroundColor(Pearl.action)
            .frame(width: 46, height: 46)
            .background(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .fill(LinearGradient(stops: [.init(color: wash[0], location: 0), .init(color: wash[1], location: 0.6),
                                             .init(color: wash[2], location: 1)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing)))
            .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                .strokeBorder(Color.white.opacity(dark ? 0.10 : 0.8), lineWidth: 1))
            .accessibilityHidden(true)
    }
}

/// `.sortcard .btn`: its rose glow, 0 8 20 (action @22% light, #FF8FB1 @20% dark).
private struct SortGlow: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content.shadow(color: scheme == .dark ? Color(hex: 0xFF8FB1).opacity(0.20) : Pearl.action.opacity(0.22),
                       radius: 10, y: 8)
    }
}

/// AP-Home (REDESIGN-04): "2 people owe you" with the total on the right
/// edge, one row on its own card; it opens Owed to you.
struct OwedCard: View {
    let owed: OwedOverview
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 12) {
                // H-00r v2 (home.css `.faces`): who, as faces, then a chevron.
                if owed.owesYou.isEmpty {
                    APIcon(symbol: "person.2")
                } else {
                    OwedFaces(names: owed.owesYou.prefix(3).map(\.name))
                }
                Text(OwedCard.words(owed)).font(Nacre.body).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(Format.amount(owed.total)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.ink).pearlAmountFit().fixedSize()
                APChevron()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .apCard()
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens Owed to you")
    }

    /// "2 people owe you", "1 person owes you".
    static func words(_ owed: OwedOverview) -> String {
        owed.people == 1 ? "1 person owes you" : "\(owed.people) people owe you"
    }
}

/// `.faces`: 36 pt initials, 6 over each other, each ringed 2 pt in the
/// card's colour (white / #1D2558).
private struct OwedFaces: View {
    let names: [String]

    var body: some View {
        // 40 apart with their rings, so −10 overlaps the faces by 6.
        HStack(spacing: -10) {
            ForEach(Array(names.enumerated()), id: \.offset) { _, name in
                Initials(name: name, size: 36)
                    .overlay(Circle().strokeBorder(Pearl.dynamic(light: 0xFFFFFF, dark: 0x1D2558), lineWidth: 2)
                        .padding(-2))
                    .padding(2)
            }
        }
        .accessibilityHidden(true)
    }
}

/// SU-01 Set Pearl up again (THL-300, THL-294): after Start over, what
/// only she can tell Pearl, each step opening its page in the app: Check
/// your accounts (AS-04, opening AS-01), Income and bills (IB-01) and Debts
/// (DB-01). Accounts is done when she taps "These look right" or saves an
/// account (the server marks that); Debts when she opens it; income when
/// she confirms her income and bills.
@MainActor
struct SetupAgainCard: View {
    @EnvironmentObject private var app: AppModel
    let setup: SetupAgain
    /// SO-04b leaves Hide this list to Home.
    var hideable = true
    let onChanged: () -> Void

    /// AP-SetupAgain (rethought, approved 2026-11-18): SET PEARL UP AGAIN ·
    /// Hide, then one card: a bar per step (done in green), "1 of 3 done",
    /// and only the next step as one row.
    var body: some View {
        let done = setup.steps.filter(\.done).count
        VStack(alignment: .leading, spacing: 8) {
            if hideable {
                APSectionLabel(text: "Set Pearl up again", action: "Hide") {
                    Task {
                        let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                        onChanged()
                    }
                }
            } else {
                APSectionLabel(text: "Set Pearl up again")
            }
            VStack(alignment: .leading, spacing: 0) {
                HStack(spacing: 6) {
                    ForEach(setup.steps) { step in
                        RoundedRectangle(cornerRadius: 3, style: .continuous)
                            .fill(step.done ? Pearl.moneyIn : APlus.trackSoft)
                            .frame(height: 6)
                    }
                }
                .accessibilityHidden(true)
                Text("\(done) of \(setup.steps.count) done")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .padding(.top, 8)
                if let next = setup.steps.first(where: { !$0.done }) {
                    NavigationLink { destination(next) } label: { nextRow(next) }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("setup-next-\(next.key)")
                }
            }
            .padding(.horizontal, 16).padding(.top, 16).padding(.bottom, 6)
            .apCard()
        }
    }

    /// "Next" over the step's title, its icon on the left, a chevron.
    private func nextRow(_ step: SetupAgain.Step) -> some View {
        HStack(spacing: 12) {
            APIcon(symbol: symbol(step.key))
            VStack(alignment: .leading, spacing: 2) {
                Text("Next").font(Nacre.footnote).foregroundColor(Pearl.muted)
                Text(step.title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            APChevron()
        }
        .padding(.vertical, 10)
        .frame(minHeight: 56)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    @ViewBuilder
    private func destination(_ step: SetupAgain.Step) -> some View {
        switch step.key {
        case "accounts":
            // AS-04 → AS-01: the same page as part 3, ending back here.
            AccountSetupView(path: .constant([])) { await mark("accounts") }
        case "income":
            IncomeBillsView()
        case "debts":
            DebtsView().task { await mark("debts") }
        default:
            AccountsView()
        }
    }

    private func symbol(_ key: String) -> String {
        ["income": "dollarsign.square", "accounts": "building.columns",
         "debts": "creditcard"][key] ?? "checkmark.circle"
    }

    private func mark(_ key: String) async {
        let _: SetupAgain? = try? await app.api.post("api/setup-again", ["step": key])
        onChanged()
    }
}

/// H-01 / H-02 (AP-BankAlert; THL-120, THL-123): a bank that needs her, as
/// the A+ champagne banner under the Allowance: the warning icon, one line,
/// and a quiet action (Reconnect, or See accounts when it's disconnected).
/// H-02 (rethought, approved 2026-11-18): with several banks only the worst
/// shows; "1 more bank · See accounts" sends her to the rest in Accounts.
struct BankAlertCard: View {
    let connection: Home.Connection
    let today: String?
    /// The other banks that need her (H-02); they wait in Accounts.
    var more: Int = 0
    let openAccounts: () -> Void
    let reconnect: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 4) {
            HStack(spacing: 12) {
                APIcon.warn("exclamationmark.triangle")
                Text(text).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                if connection.state == "needs_sign_in" {
                    APQuietButton(title: "Reconnect", identifier: "bank-reconnect", action: reconnect).fixedSize()
                } else {
                    APQuietButton(title: "See accounts", identifier: "bank-see-accounts", action: openAccounts).fixedSize()
                }
            }
            if more > 0 {
                Button(action: openAccounts) {
                    Text("\(more) more bank\(more == 1 ? "" : "s") \u{00B7} See accounts")
                        .font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote))
                        .foregroundColor(Pearl.link)
                        .frame(minHeight: 28)
                }
                .buttonStyle(.plain)
                .padding(.leading, 48)
                .accessibilityIdentifier("bank-more")
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(ProfileTone.bannerFill))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
    }

    /// "TD needs you to sign in again. Nothing since Nov 9 counts yet."
    private var text: String {
        let bank = connection.institution ?? "Your bank"
        if connection.state == "needs_sign_in" {
            let since = connection.lastSynced.map { "Nothing since \(Format.short($0)) counts yet." }
                ?? "Nothing new counts yet."
            return "\(bank) needs you to sign in again. \(since)"
        }
        return "\(bank) is no longer connected. Nothing new comes in."
    }
}
