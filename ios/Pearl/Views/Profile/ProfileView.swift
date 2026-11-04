import SwiftUI

/// P-01 Profile (THL-104, THL-209, THL-120): who's signed in, then Money,
/// You, Privacy and Help, each row led by its icon. Pages the iPhone doesn't
/// have yet open Pearl on the web, marked with an arrow out.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @State private var summary: ProfileSummary?
    @State private var doc: PearlDoc?
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
                        ProfileRow(symbol: "cylinder.split.1x2", title: "Accounts", sub: accountsLine) {
                            if let n = summary?.needsYou, n > 0 {
                                StatusPill(text: "\(n) needs you", tone: .attention)
                            }
                        }
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 64)
                    webRow(symbol: "chart.line.uptrend.xyaxis", title: "Income and bills",
                           sub: "Your pay, and the regular bills set aside")
                    RowSeparator(inset: 64)
                    webRow(symbol: "list.bullet", title: "Categories and rules", sub: rulesLine)
                }

                ProfileSection("You")
                GlassCard {
                    NavigationLink { SignInSecurityView() } label: {
                        ProfileRow(symbol: "key", title: "Sign-in and security", sub: securityLine)
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 64)
                    webRow(symbol: "bell", title: "Notifications", sub: "Payday, weekly check-in, progress")
                    RowSeparator(inset: 64)
                    Button { confirmSignOut = true } label: {
                        ProfileRow(symbol: "rectangle.portrait.and.arrow.right", title: "Sign out",
                                   sub: "On this iPhone", tone: Pearl.action, chevron: false)
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("Privacy")
                GlassCard {
                    webRow(symbol: "eye", title: "Privacy and consent", sub: "What you’ve agreed to")
                    RowSeparator(inset: 64)
                    webRow(symbol: "tray.and.arrow.down", title: "Your data",
                           sub: "Download a copy or delete your account")
                    RowSeparator(inset: 64)
                    NavigationLink { ProtectView() } label: {
                        ProfileRow(symbol: "shield", title: "How we protect you", sub: "What Pearl can and can’t do")
                    }
                    .buttonStyle(.plain)
                }

                ProfileSection("Help")
                GlassCard {
                    Button { doc = .help } label: {
                        ProfileRow(symbol: "questionmark.circle", title: "Help and support",
                                   sub: "Signing in, and new devices")
                    }
                    .buttonStyle(.plain)
                    RowSeparator(inset: 64)
                    Button { doc = .legal } label: {
                        ProfileRow(symbol: "doc.text", title: "Privacy policy and terms", sub: "Plain-language drafts")
                    }
                    .buttonStyle(.plain)
                }

                resetCard.padding(.top, 16)

                ProfileNote("Pearl for iPhone · Version \(version) · \(app.api.baseURL.host ?? app.api.baseURL.absoluteString)",
                            centred: true)
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
                Text(initials)
                    .font(Nacre.title2).foregroundColor(Nacre.onNacre)
                    .frame(width: 60, height: 60)
                    .background(Circle().fill(Pearl.nacre))
                    .overlay(Circle().strokeBorder(Color.white.opacity(0.8), lineWidth: 2))
                    .accessibilityHidden(true)
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
            .padding(16)
            .contentShape(Rectangle())
        }
        .accessibilityElement(children: .combine)
        .accessibilityHint("Opens Sign-in and security")
    }

    /// A page that's only on the web for now.
    private func webRow(symbol: String, title: String, sub: String) -> some View {
        Link(destination: app.api.baseURL) {
            ProfileRow(symbol: symbol, title: title, sub: sub, chevron: false) {
                Image(systemName: "arrow.up.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens Pearl on the web")
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
        return n > 0 ? plural(n, "saved rule") : "No saved rules yet"
    }

    /// "alex@example.com · email codes", as the web's hub says it.
    private var securityLine: String {
        let passkeys = app.user?.passkeys ?? 0
        return [app.user?.email, passkeys > 0 ? plural(passkeys, "passkey") : "email codes"]
            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
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
