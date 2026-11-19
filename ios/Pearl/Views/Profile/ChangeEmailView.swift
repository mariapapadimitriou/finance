import SwiftUI

/// P-02 Change your sign-in email (THL-104, THL-114): the new address, then
/// the 6-digit code sent to it (POST /api/auth/email/start, then /verify).
/// The server lets the old address know once it's changed.
@MainActor
struct ChangeEmailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var current = ""
    @State private var email = ""
    @State private var code = ""
    @State private var sentTo: String?
    @State private var busy = false
    @State private var failed = false
    @State private var error: String?

    private struct Started: Decodable {
        let sentTo: String?
        enum CodingKeys: String, CodingKey { case sentTo = "sent_to" }
    }

    private struct Verified: Decodable { let user: PearlUser? }

    /// Good enough to ask the server: something@something.something.
    private var looksLikeEmail: Bool {
        let parts = email.trimmingCharacters(in: .whitespaces).split(separator: "@")
        return parts.count == 2 && parts[1].contains(".") && !parts[0].isEmpty
    }

    /// G5-Email: Current as a key-value card, then the New email well, Send
    /// code riding above the keyboard; then the six code wells, Confirm
    /// greyed until all six are in, and the two quiet ways out.
    var body: some View {
        ProfilePage {
            if let sentTo = sentTo {
                ProfileHeading(title: "Check your email", intro: "We sent a 6-digit code to \(sentTo).")
                ProfileCodeWells(code: $code, failed: failed) { Task { await verify() } }
                    .padding(.top, 10)
                if failed {
                    Text("That code didn\u{2019}t work. Check it and try again.")
                        .font(Nacre.footnote).foregroundColor(Pearl.danger)
                        .frame(maxWidth: .infinity)
                } else if let error = error {
                    APErrorLine(text: error).padding(.top, 4)
                }
            } else {
                ProfileHeading(title: "Change your email")
                APCard {
                    APKeyValueRow(key: "Current", value: current)
                }
                .padding(.top, 8)
                EmailField(label: "New email", text: $email) {
                    if looksLikeEmail { Task { await start() } }
                }
                .padding(.top, 8)
                if let error = error { APErrorLine(text: error).padding(.top, 4) }
            }
        } bottom: {
            if sentTo == nil {
                Button("Send code") { Task { await start() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(!looksLikeEmail || busy)
            } else {
                Button("Confirm") { Task { await verify() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(code.count < 6 || busy)
                VStack(spacing: 0) {
                    Button("Send a new code") { Task { await start() } }
                        .buttonStyle(APQuietTextStyle())
                        .disabled(busy)
                    Button("Use a different email") {
                        sentTo = nil
                        code = ""
                        error = nil
                        failed = false
                    }
                    .buttonStyle(APQuietTextStyle())
                }
            }
        }
        .onAppear { current = app.user?.email ?? "" }
        .onChange(of: email) { _ in error = nil }
        .onChange(of: code) { c in if !c.isEmpty { failed = false } }
    }

    private func start() async {
        busy = true
        defer { busy = false }
        do {
            let reply: Started = try await app.api.post("api/auth/email/start",
                                                        ["email": email.trimmingCharacters(in: .whitespaces)])
            sentTo = reply.sentTo ?? email
            code = ""
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func verify() async {
        guard code.count == 6, !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: Verified = try await app.api.post("api/auth/email/verify", ["code": code])
            if let user = reply.user { app.signedIn(user) }
            dismiss()
        } catch {
            failed = true
            code = ""
            self.error = app.handle(error)
        }
    }
}
