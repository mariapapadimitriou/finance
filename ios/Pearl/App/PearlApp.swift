import SwiftUI

@main
struct PearlApp: App {
    @StateObject private var app = AppModel()

    init() {
        // Pushed screens' titles in Pearl's faces too.
        let bar = UINavigationBarAppearance()
        bar.configureWithTransparentBackground()
        bar.titleTextAttributes = [.font: Pearl.uiText(17), .foregroundColor: UIColor(Pearl.ink)]
        bar.largeTitleTextAttributes = [.font: Pearl.uiText(30, "Fraunces-SemiBold"),
                                        .foregroundColor: UIColor(Pearl.ink)]
        UINavigationBar.appearance().standardAppearance = bar
        UINavigationBar.appearance().scrollEdgeAppearance = bar
    }

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .tint(Pearl.action)
                .font(Pearl.text())
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

/// Home, Cash flow, Help and support, and Profile, with the web's bar along
/// the bottom.
@MainActor
struct MainTabs: View {
    enum Tab: Hashable, CaseIterable {
        case home, cashFlow, help, profile

        var label: String {
            switch self {
            case .home: return "Home"
            case .cashFlow: return "Cash flow"
            case .help: return "Help and support"
            case .profile: return "Profile"
            }
        }
    }

    @EnvironmentObject private var app: AppModel
    @State private var tab: Tab = .home
    @State private var reviewCount = 0
    /// Quick sort on return (THL-254): offered at most once a day, when
    /// Pearl has new guesses to check.
    @State private var quickSort: [QuickSortPrompt.Card] = []
    @State private var categories: [CategoryList.Category] = []
    @State private var offered = false

    var body: some View {
        VStack(spacing: 0) {
            // All four stay alive, so each keeps its place, as tabs do.
            ZStack {
                page(.home) { HomeView(tab: $tab) }
                page(.cashFlow) { TransactionsView() }
                page(.help) { HelpView() }
                page(.profile) { ProfileView() }
            }
            PearlTabBar(selection: $tab, badges: [.cashFlow: reviewCount])
        }
        .background(Pearl.page.ignoresSafeArea())
        .task(id: app.version) { await loadCount() }
        .task { await offerQuickSort() }
        .fullScreenCover(isPresented: Binding(get: { !quickSort.isEmpty }, set: { if !$0 { quickSort = [] } })) {
            QuickSortView(cards: quickSort, categories: categories) { quickSort = [] }
        }
    }

    private func offerQuickSort() async {
        guard !offered else { return }
        offered = true
        guard let prompt: QuickSortPrompt = try? await app.api.get("api/quick-sort"),
              prompt.show, !prompt.items.isEmpty else { return }
        if let list: CategoryList = try? await app.api.get("api/categories") {
            categories = list.categories.filter { $0.hidden != true }
        }
        quickSort = prompt.items
    }

    private func page<Content: View>(_ which: Tab, @ViewBuilder content: () -> Content) -> some View {
        let open = tab == which
        return NavigationStack(root: content)
            .opacity(open ? 1 : 0)
            .allowsHitTesting(open)
            .accessibilityHidden(!open)
    }

    private func loadCount() async {
        if let review: Review = try? await app.api.get("api/review") {
            reviewCount = review.open ?? review.count
        }
    }
}
