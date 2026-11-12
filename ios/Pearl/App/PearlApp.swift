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
        let tabs = UITabBarAppearance()
        tabs.configureWithDefaultBackground()
        let edge = UITabBarAppearance()
        edge.configureWithTransparentBackground()
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
                VStack(spacing: 16) {
                    Text("Pearl can't reach the server").font(Nacre.title).multilineTextAlignment(.center)
                    Text("Check your connection and try again.").font(Nacre.body)
                    Button("Try again") { Task { await app.start() } }
                        .buttonStyle(NacreButtonStyle())
                        .frame(maxWidth: 240)
                }
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .nacreScreen()
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

/// Home, Cash flow, Save, Wins and Profile in the system tab bar, Liquid
/// Glass on iOS 26 (THL-209: "use the system TabView, don't rebuild it").
/// Save and Wins have no design yet, so they're blank.
@MainActor
struct MainTabs: View {
    enum Tab: Hashable, CaseIterable {
        case home, cashFlow, save, wins, profile

        var label: String {
            switch self {
            case .home: return "Home"
            case .cashFlow: return "Cash flow"
            case .save: return "Save"
            case .wins: return "Wins"
            case .profile: return "Profile"
            }
        }

        /// The handoff file's line icons, as template images.
        var icon: String {
            switch self {
            case .home: return "TabHome"
            case .cashFlow: return "TabCashFlow"
            case .save: return "TabSave"
            case .wins: return "TabWins"
            case .profile: return "TabProfile"
            }
        }
    }

    @EnvironmentObject private var app: AppModel
    @State private var tab: Tab = .home
    @State private var reviewCount = 0
    /// Quick sort on return (THL-254): offered at most once a day, when
    /// something new needs a look; it walks every open question.
    @State private var quickSort: [Ask] = []
    @State private var quickSortNames: [String] = []
    @State private var offered = false
    /// SEC-10: another device asking to sign in as her, and the ones she's seen.
    @State private var approval: Approval?
    @State private var seenApprovals: Set<Int> = []
    @Environment(\.scenePhase) private var scenePhase

    var body: some View {
        TabView(selection: $tab) {
            page(.home) { HomeView(tab: $tab) }
            page(.cashFlow) { TransactionsView() }
                .badge(reviewCount)
            page(.save) { BlankTab() }
            page(.wins) { BlankTab() }
            page(.profile) { ProfileView(tab: $tab) }
        }
        .tint(Pearl.action)
        .task(id: app.version) { await loadCount() }
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
            if !quickSort.isEmpty {
                QuickSortView(asks: quickSort, categories: app.categories, names: quickSortNames) { quickSort = [] }
            }
        }
    }

    /// While Pearl is open, every 15 seconds: is another device waiting for
    /// this one to approve it? (The web looks as often.)
    private func lookForApprovals() async {
        struct Waiting: Decodable { let approvals: [Lenient<Approval>] }
        while scenePhase == .active && !Task.isCancelled {
            if approval == nil, let w: Waiting = try? await app.api.get("api/auth/approvals"),
               let next = w.approvals.compactMap(\.value).first(where: { !seenApprovals.contains($0.id) }) {
                seenApprovals.insert(next.id)
                approval = next
            }
            try? await Task.sleep(nanoseconds: 15_000_000_000)
        }
    }

    private func offerQuickSort() async {
        guard !offered else { return }
        offered = true
        guard let prompt: QuickSortPrompt = try? await app.api.get("api/quick-sort"),
              prompt.show, !prompt.asks.isEmpty else { return }
        quickSortNames = prompt.review?.people ?? []
        quickSort = prompt.asks
    }

    /// One tab: its own navigation, so each keeps its place. Select in Cash
    /// flow (T-19) puts its bar where the tab bar was.
    private func page<Content: View>(_ which: Tab, @ViewBuilder content: () -> Content) -> some View {
        NavigationStack {
            content().toolbar(app.hidesTabBar ? .hidden : .visible, for: .tabBar)
                .accessibilityHidden(!quickSort.isEmpty)
        }
        .tabItem {
            // TEST-14: VoiceOver hears the badge's count ("6 to sort").
            Label(which.label, image: which.icon)
                .accessibilityValue(which == .cashFlow && reviewCount > 0 ? "\(reviewCount) to sort" : "")
        }
        .tag(which)
    }

    private func loadCount() async {
        if let review: Review = try? await app.api.get("api/review") {
            reviewCount = review.open ?? review.count
        }
    }
}

/// A tab with no design yet: just the nacre.
private struct BlankTab: View {
    var body: some View {
        Color.clear
            .nacreScreen()
            .navigationBarHidden(true)
    }
}
