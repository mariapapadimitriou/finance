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

    /// G5-Email (P-02), a Pearl sheet: the envelope in its nacre ring and one
    /// line; Current and the New email well in the glass card; Send code
    /// above the keyboard. Then the six code wells in the card, Confirm greyed
    /// until all six are in, and the two quiet ways out under the card.
    var body: some View {
        ProfileFormSheet(title: sentTo == nil ? "Change your email" : "Check your email",
                         close: { dismiss() }) {
            NacreRingIcon(symbol: "envelope")
            Text(sentTo.map { "We sent a 6-digit code to \($0)." } ?? "We\u{2019}ll send a code to the new address.")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
                .fixedSize(horizontal: false, vertical: true)
            if sentTo != nil { codeStep } else { addressStep }
        } bottom: {
            if sentTo == nil {
                Button("Send code") { Task { await start() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(!looksLikeEmail || busy)
                    .accessibilityIdentifier("send-code")
            } else {
                Button("Confirm") { Task { await verify() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(code.count < 6 || busy)
                    .accessibilityIdentifier("confirm-code")
            }
        }
        .onAppear { current = app.user?.email ?? "" }
        .onChange(of: email) { _ in error = nil }
        .onChange(of: code) { c in if !c.isEmpty { failed = false } }
    }

    /// Current (read-only) over the New email well.
    @ViewBuilder private var addressStep: some View {
        ProfileFormCard {
            VStack(alignment: .leading, spacing: 4) {
                Text("Current").font(Nacre.footnote).foregroundColor(Pearl.muted)
                Text(current).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            }
            .padding(.horizontal, 4)
            .accessibilityElement(children: .combine)
            EmailField(label: "New email", text: $email) {
                if looksLikeEmail { Task { await start() } }
            }
        }
        if let error = error { APErrorLine(text: error) }
    }

    /// The six wells; a wrong code rings them red with the reason under them.
    @ViewBuilder private var codeStep: some View {
        ProfileFormCard {
            ProfileCodeWells(code: $code, failed: failed) { Task { await verify() } }
            if failed {
                Text("That code didn\u{2019}t work. Check it and try again.")
                    .font(Nacre.footnote).foregroundColor(Pearl.danger)
                    .frame(maxWidth: .infinity)
            }
        }
        if !failed, let error = error { APErrorLine(text: error) }
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
        .frame(maxWidth: .infinity)
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
