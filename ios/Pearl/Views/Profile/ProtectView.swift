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
                IconOrb(symbol: "shield", size: 72)
                ProfileHeading(eyebrow: "Profile", title: "How we protect you",
                               intro: "What Pearl can and can’t do with your bank, and what happens to your data.",
                               centred: true)
            }
            .frame(maxWidth: .infinity)
            .padding(.top, 8).padding(.bottom, 4)

            GlassCard {
                ProfileRow(symbol: "eye", title: "Read-only access",
                           sub: "Pearl can see your balances and transactions. That’s all.", chevron: false)
                RowSeparator(inset: 64)
                ProfileRow(symbol: "nosign", title: "Pearl can’t move money",
                           sub: "No payments, transfers or withdrawals, ever.", chevron: false)
                RowSeparator(inset: 64)
                ProfileRow(symbol: "key", title: "We never see your bank password",
                           sub: "You sign in to your bank through Plaid. Your login goes to your bank, not to us.",
                           chevron: false)
                RowSeparator()
                docRow("How signing in through Plaid works", .plaid)
            }

            ProfileSection("Your data")
            GlassCard {
                ProfileRow(symbol: "lock", title: "Encrypted when stored and when it moves",
                           sub: "Account names, balances and transactions.", chevron: false)
                RowSeparator(inset: 64)
                ProfileRow(symbol: "person.2", title: "We don’t sell your data",
                           sub: "We share only what’s needed to run Pearl.", chevron: false)
                RowSeparator()
                docRow("See everything we store", .store)
                RowSeparator()
                docRow("See who we share with", .share)
            }

            ProfileSection("Your connections")
            if let privacy = privacy {
                if privacy.connections.isEmpty {
                    ProfileNote("No banks are linked, so Pearl can’t see any.")
                } else {
                    GlassCard {
                        ForEach(Array(privacy.connections.enumerated()), id: \.element.id) { i, c in
                            if i > 0 { RowSeparator(inset: 64) }
                            ProfileRow(initials: c.institution, title: connectionName(c),
                                       sub: connectionLine(c), chevron: false) {
                                StatusPill(text: pill(c).text, tone: pill(c).tone)
                            }
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
        .task(id: app.version) { await load() }
        .docSheet($doc)
    }

    private func docRow(_ title: String, _ which: PearlDoc) -> some View {
        Button { doc = which } label: {
            ProfileRow(title: title, tone: Pearl.action)
        }
        .buttonStyle(.plain)
    }

    /// "TD · 3 accounts".
    private func connectionName(_ c: Privacy.Connection) -> String {
        let n = c.accounts ?? 0
        guard n > 0 else { return c.institution }
        return "\(c.institution) · \(n) account\(n == 1 ? "" : "s")"
    }

    /// "Read-only through Plaid · synced 5 min ago".
    private func connectionLine(_ c: Privacy.Connection) -> String {
        guard let synced = c.lastSynced.flatMap(Self.parse) else { return "Read-only through Plaid" }
        let words = RelativeDateTimeFormatter().localizedString(for: synced, relativeTo: Date())
        return "Read-only through Plaid · synced \(words)"
    }

    private func pill(_ c: Privacy.Connection) -> (text: String, tone: StatusPill.Tone) {
        switch c.state {
        case "needs_sign_in": return ("Sign in again", .attention)
        case "bank_down": return ("Retrying", .info)
        case "disconnected": return ("Disconnected", .neutral)
        default: return ("Healthy", .positive)
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
