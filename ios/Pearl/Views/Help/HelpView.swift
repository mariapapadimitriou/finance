import SwiftUI

/// Help and support: How we protect you (T-04), as on the web — what Pearl
/// can and can't do, the banks it reads, and a way to reach a person.
@MainActor
struct HelpView: View {
    @EnvironmentObject private var app: AppModel
    @State private var privacy: Privacy?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                PageHeader(overline: "Help and support", title: "How we protect you",
                           sub: "What Pearl can and can't do with your bank, and what happens to your data.")

                PearlCard(padding: 0, spacing: 0) {
                    ForEach(Array(Self.points.enumerated()), id: \.offset) { index, point in
                        if index > 0 { Rectangle().fill(Pearl.rule).frame(height: 1) }
                        TrustPoint(symbol: point.symbol, title: point.title, text: point.text)
                    }
                }

                if let privacy = privacy {
                    Text("Your connections").font(Pearl.cardTitle).foregroundColor(Pearl.ink)
                        .padding(.top, 8)
                        .accessibilityAddTraits(.isHeader)
                    if privacy.connections.isEmpty {
                        Text("No banks are linked, so Pearl can't see any.")
                            .font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                    } else {
                        PearlCard(padding: 0, spacing: 0) {
                            ForEach(Array(privacy.connections.enumerated()), id: \.element.id) { index, c in
                                if index > 0 { Rectangle().fill(Pearl.rule).frame(height: 1) }
                                ConnectionRow(connection: c)
                            }
                        }
                    }
                    if let contact = privacy.contact, !contact.isEmpty,
                       let mail = URL(string: "mailto:\(contact)") {
                        Link("Contact a person", destination: mail)
                            .buttonStyle(SecondaryButtonStyle())
                            .padding(.top, 4)
                    }
                } else if let error = error {
                    Notice(text: error, tone: .caution)
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.vertical, 24)
        }
        .pearlPage()
        .navigationBarHidden(true)
        .refreshable { await load() }
        .task(id: app.version) { await load() }
    }

    private func load() async {
        do {
            privacy = try await app.api.get("api/privacy")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// The web's ProtectPoints (src/pearl/privacy.jsx).
    private static let points: [(symbol: String, title: String, text: String)] = [
        ("eye", "Read-only access", "Pearl can see your balances and transactions. That's all."),
        ("nosign", "Pearl can't move money", "No payments, transfers or withdrawals, ever."),
        ("key", "We never see your bank password",
         "You sign in to your bank through Plaid, our connection partner. Your login goes to your bank, not to us."),
        ("cylinder.split.1x2", "What we store",
         "Account names, balances and transactions. Encrypted when stored and when they move."),
        ("person.2", "Who we share with", "We don't sell your data. We share only what's needed to run Pearl."),
    ]
}

/// One promise: an icon on blush, a title and a line under it.
struct TrustPoint: View {
    let symbol: String
    let title: String
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            Image(systemName: symbol)
                .font(.system(size: 16))
                .foregroundColor(Pearl.action)
                .frame(width: 40, height: 40)
                .background(Circle().fill(Pearl.blush))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.body, .medium)).foregroundColor(Pearl.ink)
                Text(text).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20).padding(.vertical, 16)
        .accessibilityElement(children: .combine)
    }
}

/// "TD · 3 accounts", "Read-only through Plaid", and how it is.
struct ConnectionRow: View {
    let connection: Privacy.Connection

    var body: some View {
        HStack(spacing: 14) {
            Text(initials)
                .font(Pearl.text(.footnote, .semibold)).foregroundColor(Pearl.ink)
                .frame(width: 40, height: 40)
                .background(Circle().fill(Pearl.track))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.ink)
                Text("Read-only through Plaid").font(Pearl.text(.footnote, .medium)).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text(status.label)
                .font(Pearl.text(.footnote, .medium))
                .foregroundColor(status.tone)
                .padding(.horizontal, 10).padding(.vertical, 3)
                .background(Capsule().fill(status.tone.opacity(0.12)))
        }
        .padding(.horizontal, 20).padding(.vertical, 14)
        .accessibilityElement(children: .combine)
    }

    private var name: String {
        let n = connection.accounts ?? 0
        guard n > 0 else { return connection.institution }
        return "\(connection.institution) · \(n) account\(n == 1 ? "" : "s")"
    }

    private var initials: String {
        connection.institution.split(separator: " ").prefix(2)
            .compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    private var status: (label: String, tone: Color) {
        switch connection.state {
        case "needs_sign_in": return ("Sign in again", Pearl.caution)
        case "bank_down": return ("We're retrying", Pearl.muted)
        case "disconnected": return ("Disconnected", Pearl.muted)
        default: return ("Healthy", Pearl.moneyIn)
        }
    }
}
