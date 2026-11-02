import SwiftUI

/// Profile: who's signed in, where the rest of Pearl lives, and signing out.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @State private var confirmSignOut = false
    @State private var confirmReset = false
    @State private var resetting = false
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                PageHeader(title: "Profile")

                PearlCard(spacing: 4) {
                    Text(app.user?.name.isEmpty == false ? app.user!.name : "Your account")
                        .font(Pearl.cardTitle).foregroundColor(Pearl.ink)
                    if let email = app.user?.email, !email.isEmpty {
                        Text(email).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                    }
                }

                PearlCard(padding: 0, spacing: 0) {
                    Link(destination: app.api.baseURL) {
                        row("Open Pearl on the web",
                            sub: "Accounts, rules, income and bills, and privacy are on the web for now.",
                            chevron: true)
                    }
                    .buttonStyle(.plain)
                    Rectangle().fill(Pearl.rule).frame(height: 1)
                    row("Server", value: app.api.baseURL.host ?? app.api.baseURL.absoluteString)
                    Rectangle().fill(Pearl.rule).frame(height: 1)
                    row("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
                }

                Button("Sign out") { confirmSignOut = true }
                    .buttonStyle(SecondaryButtonStyle())
                    .padding(.top, 4)

                VStack(alignment: .leading, spacing: 6) {
                    Button(role: .destructive) { confirmReset = true } label: {
                        HStack {
                            Text(resetting ? "Resetting…" : "Reset Pearl")
                            Spacer()
                            if resetting { ProgressView() }
                        }
                        .font(Pearl.text(.body))
                        .foregroundColor(Pearl.moneyOut)
                        .padding(.horizontal, 20).padding(.vertical, 14)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(resetting)
                    .sheetCard()
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .stroke(Pearl.border, lineWidth: 1))
                    Text("Unlinks your banks and clears your transactions and setup, then starts setup again. You stay signed in.")
                        .font(Pearl.text(.footnote, .medium)).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 4)
                    if let error = error {
                        Text(error).font(Pearl.text(.footnote, .medium)).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.top, 12)
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.vertical, 24)
        }
        .pearlPage()
        .navigationBarHidden(true)
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

    private func row(_ title: String, sub: String? = nil, value: String? = nil, chevron: Bool = false) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.body)).foregroundColor(Pearl.ink)
                if let sub = sub {
                    Text(sub).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                        .multilineTextAlignment(.leading)
                }
            }
            Spacer(minLength: 8)
            if let value = value {
                Text(value).font(Pearl.text(.body)).foregroundColor(Pearl.muted).lineLimit(1)
            }
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 20).padding(.vertical, 14)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}
