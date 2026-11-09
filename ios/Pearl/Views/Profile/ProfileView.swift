import SwiftUI

/// P-01 Profile (THL-104, THL-209, THL-120): who's signed in, then Money,
/// You, Privacy and Help, each row led by its icon, and Sign out under them.
/// Everything opens in the app; nothing sends her to the web.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab
    @State private var summary: ProfileSummary?
    /// P-01: "Every 2 weeks · 5 bills".
    @State private var doc: PearlDoc?
    @State private var showYourData = false
    @State private var showConsent = false
    @AppStorage(Appearance.key) private var appearance = Appearance.automatic.rawValue
    @State private var confirmSignOut = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                Text("Profile").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.top, 8).padding(.bottom, 8)

                NavigationLink { SignInSecurityView() } label: { identity }
                    .buttonStyle(.plain)

                ProfileSection("Money")
                GlassCard {
                    NavigationLink { AccountsView() } label: {
                        ProfileRow(symbol: "building.columns", title: "Accounts",
                                   pill: summary?.needsYou.flatMap { $0 > 0 ? StatusPill(text: "\($0) needs you", tone: .needsALook) : nil })
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { IncomeBillsView() } label: {
                        ProfileRow(symbol: "dollarsign.square", title: "Income and bills")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { RecurringTransfersView() } label: {
                        ProfileRow(symbol: "arrow.triangle.2.circlepath", title: "Recurring transfers")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    // THL-128: Debts has its own row, not only Set Pearl up again's step.
                    NavigationLink { DebtsView() } label: {
                        ProfileRow(symbol: "creditcard", title: "Debts")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { CategoriesRulesView() } label: {
                        ProfileRow(symbol: "square.on.circle", title: "Categories and rules")
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("You")
                GlassCard {
                    NavigationLink { SignInSecurityView() } label: {
                        ProfileRow(symbol: "lock", title: "Sign-in and security")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { NotificationsView() } label: {
                        ProfileRow(symbol: "bell", title: "Notifications")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    appearanceRow
                }

                ProfileSection("Privacy")
                GlassCard {
                    Button { showConsent = true } label: {
                        ProfileRow(symbol: "eye", title: "Privacy and consent")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    Button { showYourData = true } label: {
                        ProfileRow(symbol: "tray.and.arrow.down", title: "Your data")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { ProtectView() } label: {
                        ProfileRow(symbol: "checkmark.shield", title: "How we protect you")
                    }
                    .buttonStyle(.plain)
                }

                GlassCard {
                    Button { doc = .help } label: {
                        ProfileRow(symbol: "questionmark.circle", title: "Help and support")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    // THL-118: the Terms, after sign-up too.
                    Button { doc = .terms } label: {
                        ProfileRow(symbol: "doc.text", title: "Terms")
                    }
                    .buttonStyle(.plain)
                }
                .padding(.top, 12)

                Button("Sign out") { confirmSignOut = true }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)


                ProfileNote("Pearl for iPhone · \(version)", centred: true)
                    .padding(.top, 12)
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .refreshable { await load() }
        .nacreScreen()
        .navigationBarHidden(true)
        .reloads { await load() }
        .docSheet($doc)
        .navigationDestination(isPresented: $showConsent) {
            ConsentView(goHome: {
                showConsent = false
                tab = .home
            })
        }
        .navigationDestination(isPresented: $showYourData) {
            YourDataView(goHome: {
                showYourData = false
                tab = .home
            })
        }
        .confirmationDialog("Sign out of Pearl on this iPhone?", isPresented: $confirmSignOut,
                            titleVisibility: .visible) {
            Button("Sign out", role: .destructive) { Task { await app.signOut() } }
        }
    }

    // MARK: Parts

    /// The nacre avatar, her name and her email; opens Sign-in and security.
    private var identity: some View {
        GlassCard {
            HStack(spacing: 14) {
                RowAvatar(name: initials, size: 52, font: Nacre.headline)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(1)
                    if let email = app.user?.email, !email.isEmpty {
                        Text(email).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).padding(.vertical, 11)
            .contentShape(Rectangle())
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens Sign-in and security")
    }

    /// "Appearance   Automatic ›": Automatic, Light or Dark, on this iPhone.
    private var appearanceRow: some View {
        Menu {
            Picker("Appearance", selection: $appearance) {
                ForEach(Appearance.allCases) { Text($0.title).tag($0.rawValue) }
            }
        } label: {
            ProfileRow(symbol: "moon", title: "Appearance") {
                Text(Appearance(rawValue: appearance)?.title ?? Appearance.automatic.title)
                    .font(Nacre.body).foregroundColor(Pearl.muted)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Appearance")
        .accessibilityValue(Appearance(rawValue: appearance)?.title ?? Appearance.automatic.title)
    }

    /// Reset Pearl: back to the start of setup, keeping the sign-in.
    // MARK: Words

    private var name: String {
        if let first = app.user?.firstName, !first.isEmpty { return first }
        if let user = app.user?.username, !user.isEmpty { return user }
        return "Your account"
    }

    /// "AP" from her name, or the first letter of her email.
    private var initials: String {
        let source = app.user?.firstName?.isEmpty == false ? app.user!.firstName! : (app.user?.email ?? "")
        let words = source.split { !$0.isLetter }.prefix(2)
        let out = words.compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "P" : out
    }

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    // MARK: Calls

    /// Only the Accounts row's "needs you" needs the server now (2026-11-08):
    /// the rows have no second lines.
    private func load() async {
        do {
            summary = try await app.api.get("api/profile")
        } catch {
            _ = app.handle(error)
        }
    }

}

/// Light or dark, or whichever the iPhone is set to (P-01's Appearance).
enum Appearance: String, CaseIterable, Identifiable {
    case automatic, light, dark

    static let key = "pearl.appearance"

    var id: String { rawValue }

    var title: String {
        switch self {
        case .automatic: return "Automatic"
        case .light: return "Light"
        case .dark: return "Dark"
        }
    }

    var scheme: ColorScheme? {
        switch self {
        case .automatic: return nil
        case .light: return .light
        case .dark: return .dark
        }
    }
}
