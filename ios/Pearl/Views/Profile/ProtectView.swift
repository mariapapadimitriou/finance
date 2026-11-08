import SwiftUI

/// P-03 How we protect you (THL-115, THL-120): what Pearl can and can't do
/// with her bank, what it stores and who sees it, her live bank connections,
/// and a way to reach a person.
@MainActor
struct ProtectView: View {
    @EnvironmentObject private var app: AppModel
    @State private var privacy: Privacy?
    @State private var doc: PearlDoc?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            VStack(spacing: 12) {
                IconBubble(symbol: "checkmark.shield", size: 72)
                ProfileHeading(title: "How we protect you", intro: "What Pearl can and can’t do.",
                               centred: true)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 8).padding(.bottom, 4)

            GlassCard {
                ProfileRow(symbol: "eye", title: "Read-only", sub: "Sees balances and transactions", chevron: false)
                RowSeparator(inset: 62)
                ProfileRow(symbol: "nosign", title: "Can’t move money", sub: "No payments or transfers, ever",
                           chevron: false)
                RowSeparator(inset: 62)
                ProfileRow(symbol: "key", title: "Never sees your bank password", sub: "You sign in through Plaid",
                           chevron: false)
                RowSeparator()
                docRow("How Plaid sign-in works", .plaid)
            }

            ProfileSection("Your data")
            GlassCard {
                ProfileRow(symbol: "cpu", title: "Kept in Canada", sub: "Encrypted", chevron: false)
                RowSeparator(inset: 62)
                ProfileRow(symbol: "heart", title: "Never sold", chevron: false)
                RowSeparator()
                docRow("See what we store", .store)
                RowSeparator()
                docRow("See who we share with", .share)
            }

            ProfileSection("Connections")
            if let privacy = privacy {
                if privacy.connections.isEmpty {
                    ProfileNote("No banks are linked, so Pearl can’t see any.")
                } else {
                    GlassCard {
                        ForEach(Array(privacy.connections.enumerated()), id: \.element.id) { i, c in
                            if i > 0 { RowSeparator(inset: 62) }
                            NavigationLink { AccountsView() } label: {
                                ProfileRow(initials: c.institution, title: c.institution, sub: connectionLine(c),
                                           pill: StatusPill(text: pill(c).text, tone: pill(c).tone))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                if let contact = privacy.contact, !contact.isEmpty,
                   let mail = URL(string: "mailto:\(contact)") {
                    GlassCard {
                        Link(destination: mail) {
                            ProfileRow(symbol: "questionmark.circle", title: "Contact a person", tone: Pearl.action)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.top, 8)
                }
            } else if let error = error {
                Hint(text: error).padding(.horizontal, 16)
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 16)
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .docSheet($doc)
    }

    private func docRow(_ title: String, _ which: PearlDoc) -> some View {
        Button { doc = which } label: {
            ProfileRow(title: title, tone: Pearl.action)
        }
        .buttonStyle(.plain)
    }

    /// "3 accounts".
    private func connectionLine(_ c: Privacy.Connection) -> String {
        let n = c.accounts ?? 0
        return n > 0 ? "\(n) account\(n == 1 ? "" : "s")" : "Read-only"
    }

    private func pill(_ c: Privacy.Connection) -> (text: String, tone: StatusPill.Tone) {
        switch c.state {
        case "needs_sign_in": return ("Sign in again", .attention)
        case "bank_down": return ("Retrying", .info)
        case "disconnected": return ("Disconnected", .neutral)
        default: return ("Up to date", .positive)
        }
    }

    /// The server's "2026-11-03T14:05:00" (with or without a zone or fraction).
    nonisolated static func parse(_ text: String) -> Date? {
        let iso = ISO8601DateFormatter()
        iso.formatOptions = [.withInternetDateTime, .withFractionalSeconds]
        if let d = iso.date(from: text) { return d }
        iso.formatOptions = [.withInternetDateTime]
        if let d = iso.date(from: text) { return d }
        let plain = DateFormatter()
        plain.locale = Locale(identifier: "en_US_POSIX")
        plain.timeZone = TimeZone(identifier: "UTC")
        for format in ["yyyy-MM-dd'T'HH:mm:ss.SSSSSS", "yyyy-MM-dd'T'HH:mm:ss", "yyyy-MM-dd HH:mm:ss"] {
            plain.dateFormat = format
            if let d = plain.date(from: text) { return d }
        }
        return nil
    }

    private func load() async {
        do {
            privacy = try await app.api.get("api/privacy")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}
