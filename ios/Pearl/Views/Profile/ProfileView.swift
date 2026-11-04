import SwiftUI

/// P-01 Profile (THL-104, THL-209, THL-120): who's signed in, then Money,
/// You, Privacy and Help, each row led by its icon, and Sign out under them.
/// Everything opens in the app; nothing sends her to the web.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var tab: MainTabs.Tab
    @State private var summary: ProfileSummary?
    @State private var doc: PearlDoc?
    @State private var showYourData = false
    @State private var showConsent = false
    @State private var confirmSignOut = false
    @State private var confirmReset = false
    @State private var resetting = false
    @State private var error: String?

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
                        ProfileRow(symbol: "building.columns", title: "Accounts", sub: accountsLine,
                                   pill: summary?.needsYou.flatMap { $0 > 0 ? StatusPill(text: "\($0) needs you", tone: .needsALook) : nil })
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { IncomeBillsView() } label: {
                        ProfileRow(symbol: "dollarsign.square", title: "Income and bills",
                                   sub: "Your pay and regular bills")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { CategoriesRulesView() } label: {
                        ProfileRow(symbol: "square.on.circle", title: "Categories and rules", sub: rulesLine)
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("You")
                GlassCard {
                    NavigationLink { SignInSecurityView() } label: {
                        ProfileRow(symbol: "lock", title: "Sign-in and security", sub: securityLine)
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    NavigationLink { NotificationsView() } label: {
                        ProfileRow(symbol: "bell", title: "Notifications", sub: "Payday · weekly check-in")
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("Privacy")
                GlassCard {
                    Button { showConsent = true } label: {
                        ProfileRow(symbol: "eye", title: "Privacy and consent")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 62)
                    Button { showYourData = true } label: {
                        ProfileRow(symbol: "tray.and.arrow.down", title: "Your data",
                                   sub: "Download, start over or delete")
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
                }
                .padding(.top, 12)

                Button("Sign out") { confirmSignOut = true }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    .frame(maxWidth: .infinity)
                    .padding(.top, 8)

                resetCard.padding(.top, 8)

                ProfileNote("Pearl for iPhone · \(version)", centred: true)
                    .padding(.top, 12)
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .refreshable { await load() }
        .nacreScreen()
        .navigationBarHidden(true)
        .task(id: app.version) { await load() }
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
        .confirmationDialog("Reset Pearl?", isPresented: $confirmReset, titleVisibility: .visible) {
            Button("Reset", role: .destructive) { Task { await reset() } }
        } message: {
            Text("Your banks are unlinked and your transactions and setup are cleared. Your email, password and Face ID stay. This can't be undone.")
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

    /// Reset Pearl: back to the start of setup, keeping the sign-in.
    private var resetCard: some View {
        VStack(alignment: .leading, spacing: 6) {
            GlassCard {
                Button(role: .destructive) { confirmReset = true } label: {
                    ProfileRow(symbol: "arrow.counterclockwise", title: resetting ? "Resetting…" : "Reset Pearl",
                               tone: Pearl.moneyOut, chevron: false) {
                        if resetting { ProgressView() }
                    }
                }
                .buttonStyle(.plain)
                .disabled(resetting)
            }
            ProfileNote("Unlinks your banks and clears your transactions and setup, then starts setup again. You stay signed in.")
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
            }
        }
    }

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

    private var accountsLine: String {
        guard let n = summary?.accounts else { return " " }
        return n > 0 ? plural(n, "account") : "Link a bank or add a balance"
    }

    private var rulesLine: String {
        guard let n = summary?.rules else { return " " }
        return n > 0 ? plural(n, "rule") : "No saved rules yet"
    }

    /// "Face ID · passkey", or "Email codes" before she's added either.
    private var securityLine: String {
        let passkeys = app.user?.passkeys ?? 0
        let words = [app.faceIDOn ? "Face ID" : nil,
                     passkeys == 1 ? "passkey" : passkeys > 1 ? plural(passkeys, "passkey") : nil]
            .compactMap { $0 }
        return words.isEmpty ? "Email codes" : words.joined(separator: " · ")
    }

    private var version: String {
        Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0"
    }

    private func plural(_ n: Int, _ one: String) -> String { "\(n) \(one)\(n == 1 ? "" : "s")" }

    // MARK: Calls

    private func load() async {
        do {
            summary = try await app.api.get("api/profile")
        } catch {
            _ = app.handle(error)
        }
    }

    /// Back to the start of setup, as a new account (POST /api/account/reset).
    private func reset() async {
        resetting = true
        defer { resetting = false }
        do {
            struct Reply: Decodable { let user: PearlUser? }
            let reply: Reply = try await app.api.post("api/account/reset", ["confirm": "reset"])
            error = nil
            app.justCreated = false
            app.signedIn(reply.user)
        } catch {
            self.error = app.handle(error)
        }
    }
}
