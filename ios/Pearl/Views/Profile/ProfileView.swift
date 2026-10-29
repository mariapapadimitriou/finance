import SwiftUI

/// Profile: who's signed in, where the rest of Pearl lives, and signing out.
@MainActor
struct ProfileView: View {
    @EnvironmentObject private var app: AppModel
    @State private var confirmSignOut = false

    var body: some View {
        List {
            Section {
                VStack(alignment: .leading, spacing: 4) {
                    Text(app.user?.name.isEmpty == false ? app.user!.name : "Your account")
                        .font(Pearl.title).foregroundColor(Pearl.ink)
                    if let email = app.user?.email, !email.isEmpty {
                        Text(email).foregroundColor(Pearl.muted)
                    }
                }
                .padding(.vertical, 4)
            }
            Section {
                Link(destination: app.api.baseURL) {
                    Label("Open Pearl on the web", systemImage: "safari")
                }
            } footer: {
                Text("Accounts, rules, income and bills, and privacy are on the web for now.")
            }
            Section {
                LabeledContent("Server", value: app.api.baseURL.host ?? app.api.baseURL.absoluteString)
                LabeledContent("Version", value: Bundle.main.infoDictionary?["CFBundleShortVersionString"] as? String ?? "1.0")
            }
            Section {
                Button("Sign out", role: .destructive) { confirmSignOut = true }
            }
        }
        .scrollContentBackground(.hidden)
        .background(Pearl.page.ignoresSafeArea())
        .navigationTitle("Profile")
        .confirmationDialog("Sign out of Pearl on this iPhone?", isPresented: $confirmSignOut,
                            titleVisibility: .visible) {
            Button("Sign out", role: .destructive) { Task { await app.signOut() } }
        }
    }
}
