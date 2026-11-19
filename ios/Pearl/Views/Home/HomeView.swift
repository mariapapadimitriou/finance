import SwiftUI
import UIKit
import UserNotifications

/// Home, A+ (AP-Home, AP-HomeCalm, AP-PhotoHome; REDESIGN-04 to -06): the
/// date and the profile circle, the Allowance orb, then only cards with
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

    var body: some View {
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
        .nacreScreen()
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
            accounts: { route = .accounts },
            reconnect: { reconnecting = $0 },
            reload: { Task { await load() } },
            dismissNote: { note in Task { await dismissNote(note) } },
            clear: { Task { await clearWorth() } },
            open: { item in Task { await open(item) } },
            yes: { item in Task { await answer(item, yes: true) } },
            notNow: { item in Task { await answer(item, yes: false) } })
    }

    // MARK: Loading

    private func load() async {
        // Pearl sorts for you (P1a): what can be sorted from her own answers,
        // before Home counts what's left. Off, it does nothing.
        struct Ran: Decodable { let sorted: Int }
        _ = try? await app.api.post("api/pattern-sort/run", [:]) as Ran
        do {
            home = try await app.api.get("api/home")
            async let setupReply: SetupAgain? = try? app.api.get("api/setup-again")
            async let owedReply: OwedOverview? = try? app.api.get("api/owed")
            async let worthReply: WorthReply? = try? app.api.get("api/worth-a-look")
            let (s, o, w) = await (setupReply, owedReply, worthReply)
            setup = s
            owed = o
            worth = w?.items ?? []
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

    /// Got it: the note doesn't come back.
    private func dismissNote(_ note: Review.PayMonth) async {
        let _: OK? = try? await app.api.post("api/review/dismiss", ["key": note.key])
        await load()
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
            app.say("Cleared", undo: { [api = app.api] in
                let _: WorthReply = try await api.post("api/worth-a-look", ["action": "undo_clear", "ids": ids])
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
            // Cash flow, where categories live (filtering it from here waits for Cash flow).
            tab = .cashFlow
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
    case review, owed, accounts
    case owedPerson(String)
    case transaction(String)
    case bills, debts, plan

    init?(_ t: WorthItem.Target) {
        switch t.screen {
        case "transaction": guard let id = t.id else { return nil }; self = .transaction(id)
        case "owed_person": guard let name = t.name else { return nil }; self = .owedPerson(name)
        case "owed": self = .owed
        case "bill": self = .bills
        case "debt": self = .debts
        case "plan": self = .plan
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
        case .owedPerson(let name): OwedPersonView(name: name)
        case .transaction(let id): TransactionByID(id: id, categories: app.categories)
        case .bills: IncomeBillsView()
        case .debts: DebtsView()
        case .plan: YourPlanView()
        }
    }
}

/// Everything Home's cards can ask for.
struct HomeActions {
    let sortNow: () -> Void
    let seeList: () -> Void
    let seeOwed: () -> Void
    let accounts: () -> Void
    let reconnect: (Home.Connection) -> Void
    let reload: () -> Void
    let dismissNote: (Review.PayMonth) -> Void
    let clear: () -> Void
    let open: (WorthItem) -> Void
    let yes: (WorthItem) -> Void
    let notNow: (WorthItem) -> Void
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
            && home.paychequeNote == nil && worth.isEmpty
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let since = offlineSince {
                OfflineBanner(since: since).padding(.top, 8).padding(.bottom, 8)
            }
            HomeTopBar(today: home.today)
            HomeOrb(home: home, calm: calm)
            if calm {
                CalmState().padding(.top, 12)
            } else {
                HomeCards(home: home, setup: setup, owed: owes ? owed : nil, troubled: troubled,
                          sorting: sorting, actions: actions)
                if !worth.isEmpty {
                    WorthALookSection(items: worth, onClear: actions.clear, onOpen: actions.open,
                                      onYes: actions.yes, onNotNow: actions.notNow)
                        .padding(.top, 20)
                }
            }
        }
        .padding(.horizontal, Pearl.gutter)
        .padding(.bottom, 32)
    }
}

/// The date (12/500, tracked 1.4, `muted`), centred, and the profile circle
/// on the right, 44 high.
struct HomeTopBar: View {
    let today: String?

    var body: some View {
        HStack {
            Color.clear.frame(width: 44, height: 44)
            Spacer(minLength: 0)
            Text((today.map { Format.day($0) } ?? "").uppercased())
                .font(.custom("Figtree-Medium", size: 12, relativeTo: .caption)).tracking(1.4)
                .foregroundColor(Pearl.muted)
                .lineLimit(1).minimumScaleFactor(0.8)
            Spacer(minLength: 0)
            // A+ (AP-Home, AP-PhotoHome): it pushes Profile in this tab.
            ProfileCircle()
        }
        .frame(height: 44)
        .padding(.top, 2)
        .padding(.trailing, -4)
    }
}

/// The orb: 188 with cards under it, 232 and 48 lower when calm. The
/// estimate, over and no-income states keep their line under it.
private struct HomeOrb: View {
    let home: Home
    let calm: Bool

    var body: some View {
        VStack(spacing: 10) {
            AllowanceOrb(progress: home.safeToSpend?.ringProgress ?? 0,
                         label: "Allowance",
                         amount: home.safeToSpend?.ringAmount ?? "—",
                         sub: home.safeToSpend?.orbSub(month: home.month) ?? Allowance.orbSub(forMonth: home.month),
                         size: calm ? AllowanceOrb.full : AllowanceOrb.small)
                .accessibilityAddTraits(.isHeader)
                .accessibilityHint(home.safeToSpend?.ringCaption == Allowance.restCaption ? Allowance.restCaption : "")
            if let caption = home.safeToSpend?.ringCaption, !caption.isEmpty, caption != Allowance.restCaption {
                Text(caption).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, calm ? 48 : 0)
        .padding(.bottom, calm ? 24 : 0)
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
            // H-02 (THL-120): every bank in trouble, worst first, each its own card.
            ForEach(troubled) { c in
                BankAlertCard(connection: c, today: home.today, openAccounts: actions.accounts) {
                    actions.reconnect(c)
                }
                .padding(.top, 18)
            }
            if let setup = setup, setup.active {
                SetupAgainCard(setup: setup, onChanged: actions.reload).padding(.top, 18)
            }
            if home.reviewCount > 0 {
                APSectionLabel(text: "Needs a look", action: "See the list", act: actions.seeList)
                    .padding(.top, 18).padding(.bottom, 8)
                NeedsALookCard(count: home.reviewCount, pearlSorted: home.pearlSorted ?? 0,
                               busy: sorting, onSort: actions.sortNow)
            }
            if let owed = owed {
                OwedCard(owed: owed, open: actions.seeOwed).padding(.top, 12)
            }
            if let note = home.paychequeNote {
                PaychequeNoteCard(month: note) { actions.dismissNote(note) }.padding(.top, 12)
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
                Image(systemName: "square.on.square").font(.system(size: 18)).foregroundColor(Pearl.action)
                    .frame(width: 44, height: 44)
                    .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(Pearl.bubble))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(count) to sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                    Text(howLong + (pearlSorted > 0 ? " \u{00B7} Pearl sorted \(pearlSorted)" : ""))
                        .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .accessibilityElement(children: .combine)
            if pearlSorted > 0 {
                SortStreak(sorted: pearlSorted, toSort: count)
            }
            Button("Sort now", action: onSort)
                .buttonStyle(PearlPrimaryButtonStyle(busy: busy, busyLabel: "Opening…"))
                .disabled(busy)
        }
        .padding(18)
        .apCard()
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
                APIcon(symbol: "person.2")
                Text(OwedCard.words(owed)).font(Nacre.body).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                Text(Format.amount(owed.total)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.ink).pearlAmountFit().fixedSize()
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

/// A month with a third paycheque: why it looks bigger, and nothing to do.
struct PaychequeNoteCard: View {
    let month: Review.PayMonth
    let onDismiss: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            APIcon(symbol: "dollarsign.circle", tone: .good)
            // REFRESH-03 (H-00n), PC-01 (TEXT-01): "3 paycheques in October".
            Text("3 paycheques in \(Format.monthName(month.month))")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
            Button("Got it", action: onDismiss)
                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(Pearl.link)
                .buttonStyle(.plain)
                .tapTarget(vertical: 12, horizontal: 6)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .apCard()
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

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            APSectionLabel(text: "Set Pearl up again")
            Text(setup.left == 1 ? "Start over cleared what only you can tell Pearl. 1 thing left to set again."
                 : "Start over cleared what only you can tell Pearl. \(setup.left) things left to set again.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4)
                .fixedSize(horizontal: false, vertical: true)
            APCard {
                ForEach(Array(setup.steps.enumerated()), id: \.element.id) { index, step in
                    if index > 0 { APSeparator(afterFace: false) }
                    NavigationLink { destination(step) } label: {
                        ProfileRow(symbol: symbol(step.key), title: step.title,
                                   sub: step.done ? "Done" : step.sub)
                    }
                    .buttonStyle(.plain)
                    .accessibilityValue(step.done ? "Done" : "")
                }
            }
            if hideable {
                Button("Hide this list") {
                    Task {
                        let _: SetupAgain? = try? await app.api.post("api/setup-again", ["hide": true])
                        onChanged()
                    }
                }
                .buttonStyle(NacreTextButtonStyle())
            }
        }
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

/// H-01 (THL-120, THL-123): a bank that needs her, at the top of Home, on
/// its own A+ card: the same words as Accounts' C-01. Disconnected opens
/// Accounts; a bank that isn't responding needs nothing from her.
struct BankAlertCard: View {
    let connection: Home.Connection
    let today: String?
    let openAccounts: () -> Void
    let reconnect: () -> Void

    var body: some View {
        VStack(spacing: 14) {
            HStack(spacing: 12) {
                APIcon(symbol: connection.state == "bank_down" ? "clock" : "arrow.triangle.2.circlepath", tone: .warn)
                Text(text).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
            }
            switch connection.state {
            case "needs_sign_in":
                Button("Reconnect", action: reconnect).buttonStyle(NacreButtonStyle())
            case "disconnected":
                Button("See accounts", action: openAccounts).buttonStyle(NacreButtonStyle())
            default:
                EmptyView()
            }
        }
        .padding(18)
        .apCard()
    }

    private var text: String {
        let bank = connection.institution ?? "Your bank"
        switch connection.state {
        case "needs_sign_in":
            let what = connection.cardsOnly == true ? "Its purchases" : "Its transactions"
            let since = connection.lastSynced.map { " since \(Format.short($0))" } ?? ""
            return "\(bank) needs you to sign in again. \(what)\(since) aren’t counted yet."
        case "disconnected":
            return "\(bank) is no longer connected, so its transactions aren’t coming in."
        default:
            return "\(bank) isn’t responding right now. Pearl keeps trying; there’s nothing you need to do."
        }
    }
}
