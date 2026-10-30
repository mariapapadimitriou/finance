import SwiftUI

/// Profile: who's signed in, where the rest of Pearl lives, and signing out.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @State private var confirmSignOut = false

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
