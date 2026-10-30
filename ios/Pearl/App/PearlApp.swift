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

    var body: some View {
        Group {
            switch app.phase {
            case .starting:
                ProgressView().frame(maxWidth: .infinity, maxHeight: .infinity).pearlPage()
            case .offline:
                VStack(spacing: 16) {
                    Text("Pearl can't reach the server").font(Pearl.title).foregroundColor(Pearl.ink)
                    Text("Check your connection and try again.").foregroundColor(Pearl.muted)
                    Button("Try again") { Task { await app.start() } }
                        .buttonStyle(PrimaryButtonStyle())
                        .frame(maxWidth: 240)
                }
                .padding(24)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .pearlPage()
            case .signedOut:
                SignInView()
            case .signedIn(let user):
                if user?.onboarding?.done == false {
                    FinishOnWebView()
                } else {
                    MainTabs()
                }
            }
        }
        .task { await app.start() }
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

/// An account that hasn't finished setting up does that on the web first:
/// linking a bank happens there.
@MainActor
struct FinishOnWebView: View {
    @EnvironmentObject private var app: AppModel

    var body: some View {
        VStack(alignment: .leading, spacing: 16) {
            Text("Finish setting up Pearl").font(Pearl.display()).foregroundColor(Pearl.ink)
            Text("Linking your bank and the rest of setup happen on the web. Once that's done, everything is here too.")
                .foregroundColor(Pearl.muted)
            Link("Open Pearl on the web", destination: app.api.baseURL)
                .buttonStyle(PrimaryButtonStyle())
            Button("I've finished, check again") { Task { await app.start() } }
                .buttonStyle(SecondaryButtonStyle())
            Button("Sign out") { Task { await app.signOut() } }.foregroundColor(Pearl.action)
            Spacer()
        }
        .padding(24)
        .pearlPage()
    }
}
