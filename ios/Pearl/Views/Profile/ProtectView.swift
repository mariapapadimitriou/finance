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

    /// G5-Protect P-03: what Pearl can't do, the data pills and the two
    /// docs, the live connections with their pills, and Contact a person.
    var body: some View {
        ProfilePage {
            ProfileHeading(title: "How we protect you")
            APCard {
                ProfileRow(symbol: "eye", title: "Read-only", sub: "Sees balances and transactions", chevron: false)
                APSeparator()
                ProfileRow(symbol: "nosign", title: "Can\u{2019}t move money", sub: "No payments or transfers, ever",
                           chevron: false)
                APSeparator()
                ProfileRow(symbol: "key", title: "Never sees your bank password", sub: "You sign in through Plaid",
                           chevron: false)
                APSeparator()
                docRow("doc.text", "How Plaid sign-in works", .plaid)
            }
            .padding(.top, 10)

            ProfileSection("Your data")
            HStack(spacing: 8) {
                StatusPill(text: "Kept in Canada", tone: .neutral)
                StatusPill(text: "Encrypted", tone: .neutral)
                StatusPill(text: "Never sold", tone: .neutral)
            }
            APCard {
                docRow("doc.text", "See what we store", .store)
                APSeparator()
                docRow("person.2", "See who we share with", .share)
            }
            .padding(.top, 4)

            ProfileSection("Connections")
            if let privacy = privacy {
                APCard {
                    if privacy.connections.isEmpty {
                        Text("No banks linked, so Pearl can\u{2019}t see any.")
                            .font(Nacre.body).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 16).padding(.vertical, 12)
                            .frame(maxWidth: .infinity, minHeight: 64, alignment: .leading)
                    }
                    ForEach(Array(privacy.connections.enumerated()), id: \.element.id) { i, c in
                        if i > 0 { APSeparator() }
                        NavigationLink { AccountsView() } label: {
                            ProfileRow(initials: c.institution, title: c.institution, sub: connectionLine(c),
                                       pill: StatusPill(text: pill(c).text, tone: pill(c).tone),
                                       chevron: false, pillTrailing: true)
                        }
                        .buttonStyle(.plain)
                    }
                }
                if let contact = privacy.contact, !contact.isEmpty,
                   let mail = URL(string: "mailto:\(contact)") {
                    Link("Contact a person", destination: mail)
                        .buttonStyle(APSecondaryButtonStyle())
                        .padding(.top, 10)
                }
            } else if let error = error {
                APErrorLine(text: error)
            } else {
                APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }
            }
            Color.clear.frame(height: 24)
        }
        .refreshable { await load() }
        .reloads { await load() }
        .docSheet($doc)
    }

    private func docRow(_ symbol: String, _ title: String, _ which: PearlDoc) -> some View {
        Button { doc = which } label: {
            ProfileRow(symbol: symbol, title: title)
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
