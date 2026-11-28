import SwiftUI

// AU-01 (THL-308 / THL-309; Pearl redesign canvas, Profile page,
// "AI-Usage"): Profile › AI usage, for the owner only. The server answers
// 404 to anyone else (PEARL_OWNER_EMAILS), and Profile shows the row only
// when /api/profile says `ai_usage`.

/// GET /api/ai-usage.
struct AIUsage: Decodable {
    let monthName: String
    let costUSD: Double
    let questions: Int
    let escalated: Int
    let escalationRate: Double
    let atCap: Int
    let people: Int
    let capUSD: Double
    let highestUSD: Double
    let youUSD: Double

    enum CodingKeys: String, CodingKey {
        case questions, escalated, people
        case monthName = "month_name"
        case costUSD = "cost_usd"
        case escalationRate = "escalation_rate"
        case atCap = "at_cap"
        case capUSD = "cap_usd"
        case highestUSD = "highest_usd"
        case youUSD = "you_usd"
    }
}

/// "November so far. Only you see this." Everyone: Cost, Questions, Needed
/// the bigger model ("25 · 6%"), People at the cap ("0 of 4"). Per person:
/// Cap ("$0.50 a month"), Highest this month, You.
@MainActor
struct AIUsageView: View {
    @EnvironmentObject private var app: AppModel
    @State private var usage: AIUsage?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                PageTitle(title: "AI usage",
                          line: usage.map { "\($0.monthName) so far. Only you see this." } ?? "Only you see this.")
                if let u = usage {
                    CardCaption("Everyone")
                    APCard {
                        row("Cost", Self.dollars(u.costUSD))
                        APSeparator(afterFace: false)
                        row("Questions", "\(u.questions)")
                        APSeparator(afterFace: false)
                        row("Needed the bigger model", "\(u.escalated) \u{00B7} \(Int((u.escalationRate * 100).rounded()))%")
                        APSeparator(afterFace: false)
                        row("People at the cap", "\(u.atCap) of \(u.people)")
                    }
                    CardCaption("Per person")
                    APCard {
                        row("Cap", "\(Self.dollars(u.capUSD)) a month")
                        APSeparator(afterFace: false)
                        row("Highest this month", Self.dollars(u.highestUSD))
                        APSeparator(afterFace: false)
                        row("You", Self.dollars(u.youUSD))
                    }
                } else if let error = error {
                    APErrorLine(text: error)
                } else {
                    APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }.padding(.top, 12)
                }
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
    }

    private func row(_ key: String, _ value: String) -> some View {
        APKeyValueRow(key: key) {
            Text(value).foregroundColor(Pearl.ink).monospacedDigit()
        }
    }

    /// "$1.86": cents, always two places.
    static func dollars(_ v: Double) -> String { String(format: "$%.2f", v) }

    private func load() async {
        do {
            usage = try await app.api.get("api/ai-usage")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}
