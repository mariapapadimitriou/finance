import SwiftUI

@main
struct PearlApp: App {
    @StateObject private var app = AppModel()
    /// P-01's Appearance: Automatic follows the iPhone.
    @AppStorage(Appearance.key) private var appearance = Appearance.automatic.rawValue

    init() {
        // Pushed screens' titles in Pearl's faces too.
        let bar = UINavigationBarAppearance()
        bar.configureWithTransparentBackground()
        bar.titleTextAttributes = [.font: Pearl.uiText(17), .foregroundColor: UIColor(Pearl.ink)]
        bar.largeTitleTextAttributes = [.font: Pearl.uiText(30, "Fraunces-SemiBold"),
                                        .foregroundColor: UIColor(Pearl.ink)]
        UINavigationBar.appearance().standardAppearance = bar
        UINavigationBar.appearance().scrollEdgeAppearance = bar
        // Cash flow's count in the tab bar's own colour, not system red.
        // SwiftUI's TabView reads the bar's appearance, not each item's, so
        // the badge is set on every layout of both the usual bar and the
        // see-through one at the bottom of a list.
        func badged(_ tabs: UITabBarAppearance) -> UITabBarAppearance {
            for layout in [tabs.stackedLayoutAppearance, tabs.inlineLayoutAppearance, tabs.compactInlineLayoutAppearance] {
                for state in [layout.normal, layout.selected] {
                    state.badgeBackgroundColor = UIColor(Pearl.action)
                    state.badgeTextAttributes = [.foregroundColor: UIColor(Pearl.onAction)]
                }
            }
            return tabs
        }
        // A+ (REDESIGN-08, AP-TabCompare): on iOS 26 the bar is see-through
        // Liquid Glass everywhere, so the page shows through it, with a
        // lilac-tinted lozenge under the selected tab (`tab-lozenge`).
        // Before iOS 26 the bar keeps its usual frosted background.
        let tabs = UITabBarAppearance()
        if #available(iOS 26, *) {
            tabs.configureWithTransparentBackground()
            tabs.selectionIndicatorTintColor = UIColor(APlus.tabLozenge)
        } else {
            tabs.configureWithDefaultBackground()
        }
        let edge = UITabBarAppearance()
        edge.configureWithTransparentBackground()
        if #available(iOS 26, *) { edge.selectionIndicatorTintColor = UIColor(APlus.tabLozenge) }
        UITabBar.appearance().standardAppearance = badged(tabs)
        UITabBar.appearance().scrollEdgeAppearance = badged(edge)
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .tint(Pearl.action)
                .font(Pearl.text())
                .preferredColorScheme(Appearance(rawValue: appearance)?.scheme)
        }
    }
}

/// Signed in or not, and the app's tabs once you are.
@MainActor
struct RootView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        Group {
            switch app.phase {
            case .starting:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity).nacreScreen()
            case .offline:
                // G6-Offline (REDESIGN-14, new function): Can't reach Pearl at launch.
                CantReachPearlView { await app.start() }
            case .signedOut:
                AuthFlow()
            case .deleted(let sentTo):
                AccountDeletedView(sentTo: sentTo)
            case .signedIn(let user):
                if user?.onboarding?.done == false || Self.debugSetup {
                    SetupFlow()
                } else {
                    MainTabs()
                }
            }
        }
        .overlay {
            if app.locked {
                AppLockView().transition(.opacity)
            }
        }
        .animation(.easeInOut(duration: 0.2), value: app.locked)
        .task { await app.start() }
        .onOpenURL { app.open($0) }
        .onChange(of: scenePhase) { phase in
            switch phase {
            case .background: app.wentToBackground()
            case .active: app.cameBack()
            default: break
            }
        }
    }

    /// DEBUG: `-pearl-setup <screen>` opens setup even on an account that
    /// finished it (see SetupFlow).
    private static var debugSetup: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("-pearl-setup")
        #else
        return false
        #endif
    }
}

/// A+ (REDESIGN-02, -03, -07; TabBar): Home · Cash flow · Save · Wins ·
/// Pearl in the system tab bar, Liquid Glass on iOS 26 (THL-209: "use the
/// system TabView, don't rebuild it"), tinted Pearl.action; unselected items
/// as the system draws them. Profile left the bar for the profile circle at
/// the top right of all five (`profileCircleSlot`); the floating Pearl button is gone
/// and Pearl chat is the fifth tab. Save and Wins are parked, so blank.
@MainActor
struct MainTabs: View {
    enum Tab: Hashable, CaseIterable {
        case home, cashFlow, save, wins, pearl

        var label: String {
            switch self {
            case .home: return "Home"
            case .cashFlow: return "Cash flow"
            case .save: return "Save"
            case .wins: return "Wins"
            case .pearl: return "Pearl"
            }
        }

        /// The app's own line icons, as template images (Pearl draws its own).
        var icon: String {
            switch self {
            case .home: return "TabHome"
            case .cashFlow: return "TabCashFlow"
            case .save: return "TabSave"
            case .wins: return "TabWins"
            case .pearl: return "LogoMark"
            }
        }
    }

    @EnvironmentObject private var app: AppModel
    @State private var tab: Tab = .home
    @State private var reviewCount = 0
    /// The server's own open count the last time api/review was read, so a
    /// write's `changed.review_count` moves the badge by the difference:
    /// the badge counts rows only (TEST-35), the server's count has the
    /// trip and pattern cards too.
    @State private var serverOpen: Int?
    /// Quick sort on return (THL-254): offered at most once a day, when
    /// something new needs a look; it walks only the new questions.
    @State private var quickSort: [Ask] = []
    @State private var quickSortNames: [String] = []
    /// AI-18: patterns Pearl asks about once, first in Quick sort.
    @State private var quickSortPatterns: [PatternAsk] = []
    /// TR-01: likely trips, after the patterns.
    @State private var quickSortTrips: [TripAsk] = []
    @State private var offered = false
    /// SEC-10: another device asking to sign in as her, and the ones she's seen.
    @State private var approval: Approval?
    @State private var seenApprovals: Set<Int> = []
    /// A trip or pattern card is waiting (GET /api/chat `suggest`): the
    /// Pearl tab's nacre dot, where the old button showed its ring. Never a number.
    @State private var chatSuggests = false
    @Environment(\.scenePhase) private var scenePhase
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        TabView(selection: $tab) {
            page(.home) { HomeView(tab: $tab) }
            page(.cashFlow) { TransactionsView() }
                .badge(reviewCount)
            page(.save) { BlankTab() }
            page(.wins) { BlankTab() }
            // The conversation stays across tab switches (the tab's view, and
            // its ChatEngine, live as long as the bar). Where Apple
            // Intelligence can't run it shows PC-11; the bar keeps five.
            PearlChatView(api: app.api, describe: { app.handle($0) ?? "Something went wrong. Try again." },
                          onSearch: { tab = .cashFlow })   // PC-11's Search instead: Cash flow, where Search is.
                .toolbar(app.hidesTabBar ? .hidden : .visible, for: .tabBar)
                .tabItem {
                    Label {
                        Text(Tab.pearl.label)
                    } icon: {
                        Image(uiImage: PearlTabIcon.image(suggest: chatSuggests, dark: scheme == .dark))
                            .renderingMode(.original)
                    }
                    .accessibilityLabel(chatSuggests ? "Pearl, has a suggestion" : "Pearl")
                }
                .tag(Tab.pearl)
        }
        .tint(Pearl.action)
        .environment(\.goHome, { tab = .home })
        .task(id: app.version) {
            await loadCount()
            await lookForSuggestions()
            await lookAtProfile()
        }
        .onReceive(app.$reviewCount) { count in
            // A write said how many are left: the badge moves at once.
            guard let count = count, let was = serverOpen, count != was else { return }
            serverOpen = count
            reviewCount = max(0, reviewCount + (count - was))
        }
        .task(id: app.user?.id) {
            // Her photo is on this iPhone only, one per account.
            ProfilePhotoStore.shared.use(account: app.user?.id.map(String.init))
        }
        .onChange(of: tab) { [tab] _ in
            // Leaving the Pearl tab: what chat changed shows everywhere
            // (what closing the chat's sheet did before A+).
            if tab == .pearl { app.changed() }
        }
        .task { await offerQuickSort() }
        .task(id: scenePhase) { await lookForApprovals() }
        .sheet(item: $approval) { a in
            ApprovalPrompt(approval: a) { yes in
                approval = nil
                Task {
                    let _: OK? = try? await app.api.post("api/auth/approvals/\(a.id)", ["approve": yes])
                }
            }
            .presentationDetents([.medium])
        }
        // Part of this screen, not presented over it: nothing dismissed inside can close it.
        .overlay {
            if !quickSort.isEmpty || !quickSortPatterns.isEmpty || !quickSortTrips.isEmpty {
                QuickSortView(asks: quickSort, categories: app.categories, names: quickSortNames,
                              patterns: quickSortPatterns, trips: quickSortTrips) {
                    quickSort = []; quickSortPatterns = []; quickSortTrips = []
                }
            }
        }
        // Trips (TR-02c, TR-11–TR-13): its toast stays while the trip's page
        // opens or closes under it. UN-01: at the bottom, above the tab bar.
        .overlay(alignment: .bottom) {
            if let toast = app.toast {
                UndoToast(text: toast.text, undo: toast.undo.map { run in {
                    // Gone at once, so a second tap can't undo twice.
                    withAnimation { app.toast = nil }
                    Task {
                        do {
                            try await run()
                            app.changed()
                            app.say("Undone.")
                        } catch {
                            if let words = app.handle(error) { app.say(words) }
                        }
                    }
                } }) {
                    if app.toast == toast { withAnimation { app.toast = nil } }
                }
                // UN-01: 12 above the tab bar (49 pt, over the home indicator's safe area).
                .padding(.bottom, 49 + 12)
                .id(toast.id)
            }
        }
    }

    /// Once as Pearl comes to the front, then every 60 seconds while it's
    /// active, never in the background (`.task(id: scenePhase)` ends the
    /// loop as the phase changes): is another device waiting for this one to
    /// approve it? Was every 15 seconds, a paid call each (perf rehaul,
    /// 2026-11-19).
    private func lookForApprovals() async {
        struct Waiting: Decodable { let approvals: [Lenient<Approval>] }
        while scenePhase == .active && !Task.isCancelled {
            if approval == nil, let w: Waiting = try? await app.api.get("api/auth/approvals"),
               let next = w.approvals.compactMap(\.value).first(where: { !seenApprovals.contains($0.id) }) {
                seenApprovals.insert(next.id)
                approval = next
            }
            try? await Task.sleep(nanoseconds: 60_000_000_000)
        }
    }

    private func offerQuickSort() async {
        guard !offered else { return }
        offered = true
        // THL-254: once a day at most, only when something is new since her
        // last visit (the server's `show`), and then only the new ones.
        guard let prompt: QuickSortPrompt = try? await app.api.get("api/quick-sort"),
              prompt.show, !(prompt.newAsks.isEmpty && prompt.newPatterns.isEmpty && prompt.newTrips.isEmpty) else { return }
        quickSortNames = prompt.review?.people ?? []
        quickSortPatterns = prompt.newPatterns
        quickSortTrips = prompt.newTrips
        quickSort = prompt.newAsks
    }

    /// One tab: its own navigation, so each keeps its place. Select in Cash
    /// flow (T-19) puts its bar where the tab bar was.
    private func page<Content: View>(_ which: Tab, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content().toolbar(app.hidesTabBar ? .hidden : .visible, for: .tabBar)
                .accessibilityHidden(!quickSort.isEmpty || !quickSortPatterns.isEmpty || !quickSortTrips.isEmpty)
        }
        .tabItem {
            // TEST-14: VoiceOver hears the badge's count ("6 to sort").
            Label(which.label, image: which.icon)
                .accessibilityValue(which == .cashFlow && reviewCount > 0 ? "\(reviewCount) to sort" : "")
        }
        .tag(which)
    }

    /// The Pearl tab's dot: a trip or pattern card waiting, the same ones
    /// Quick sort has. Only where Apple Intelligence can run the chat.
    private func lookForSuggestions() async {
        guard PearlIntelligence.available else {
            chatSuggests = false
            return
        }
        if let start: ChatStart = try? await app.api.get("api/chat") {
            chatSuggests = start.suggest
        }
    }

    /// The profile circle's dot (REDESIGN-03): what Profile already flags,
    /// Accounts' "needs you" (a bank to sign in to again or cut off, THL-120).
    private func lookAtProfile() async {
        if let summary: ProfileSummary = try? await app.api.get("api/profile") {
            app.profileNeedsYou = (summary.needsYou ?? 0) > 0
        }
    }

    private func loadCount() async {
        // The last write already said how many are left (changed.review_count,
        // applied above): no fetch for this bump.
        if app.reviewCount != nil, app.reviewCountAt == app.version, serverOpen != nil { return }
        // Else the kept answer at once, and the server's with its ETag.
        try? await app.screens.load("api/review", as: Review.self) { review in
            // TEST-35: the rows Needs a look lists, as its "All" chip.
            reviewCount = review.listedOpen
            serverOpen = review.open ?? review.count
        }
    }
}

/// Save and Wins, parked (REDESIGN-11): just the nacre, and the profile
/// circle at the top right as on every main tab.
private struct BlankTab: View {
    var body: some View {
        Color.clear
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .nacreScreen()
            .profileCircleSlot()
            .navigationBarHidden(true)
    }
}
