import SwiftUI

@main
struct PearlApp: App {
    @StateObject private var app = AppModel()

    var body: some Scene {
        WindowGroup {
            RootView()
                .environmentObject(app)
                .tint(Pearl.action)
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

/// Home, Cash flow and Profile, as on the web.
@MainActor
struct MainTabs: View {
    enum Tab: Hashable { case home, cashFlow, profile }

    @EnvironmentObject private var app: AppModel
    @State private var tab: Tab = .home
    @State private var reviewCount = 0

    var body: some View {
        TabView(selection: $tab) {
            NavigationStack { HomeView(tab: $tab) }
                .tabItem { Label("Home", systemImage: "house") }
                .tag(Tab.home)
            NavigationStack { TransactionsView() }
                .tabItem { Label("Cash flow", systemImage: "chart.line.uptrend.xyaxis") }
                .badge(reviewCount)
                .tag(Tab.cashFlow)
            NavigationStack { ProfileView() }
                .tabItem { Label("Profile", systemImage: "person.crop.circle") }
                .tag(Tab.profile)
        }
        .task(id: app.version) { await loadCount() }
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
