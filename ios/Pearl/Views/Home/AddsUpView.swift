import SwiftUI

/// How it adds up (n-home-gauge, n-cf-meter; drawn as PX-AddsUp and
/// PX-AddsUpCash): opened by Home's gauge and Cash flow's "How it adds up"
/// row. The month in Fraunces 34, then the server's own rows: Came in, less
/// the bills (paid and still to come) and what she moved to savings (and
/// Your plan, and what came from last month, when there is any) make the
/// Allowance; less Spent so far, Left. Then the daily amount. THL-125.
@MainActor
struct AddsUpView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let a = app.allowance, a.hasGauge {
                    OwedTitle(title: a.month.map { Format.monthName($0) } ?? "This month")
                    Text("How your Allowance adds up").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .padding(.leading, 4).padding(.top, 4)
                    AddsUpCards(allowance: a)
                } else {
                    OwedTitle(title: "How it adds up")
                    Text(Allowance.needsIncomeLine).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .padding(.leading, 4).padding(.top, 4)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .apPushedPage { dismiss() }
    }
}

private struct AddsUpCards: View {
    let allowance: Allowance

    private func row(_ key: String) -> Double? { allowance.rows.first { $0.key == key }?.amount }

    var body: some View {
        let bills = (row("bills") ?? 0) + (allowance.billsPaid ?? 0)
        let over = allowance.state == "over"
        VStack(alignment: .leading, spacing: 0) {
            APCard {
                line("Came in", "+" + Format.whole(row("income") ?? 0), tone: Pearl.moneyIn)
                line("Bills", "−" + Format.whole(bills))
                if let saved = row("saved"), saved >= 0.5 { line("Moved to savings", "−" + Format.whole(saved)) }
                if let plan = row("plan"), plan >= 0.5 { line("Your plan", "−" + Format.whole(plan)) }
                if let carried = row("from_last_month"), abs(carried) >= 0.5 {
                    line("From last month", (carried < 0 ? "−" : "+") + Format.whole(carried))
                }
                line("Allowance", Format.whole(allowance.total ?? 0), bold: true)
            }
            .padding(.top, 16)
            APCard {
                line("Spent so far", "−" + Format.whole(allowance.spent ?? 0))
                HStack {
                    Text(over ? "Over" : "Left").font(Nacre.headline)
                    Spacer(minLength: 8)
                    Text(allowance.leftText)
                        .font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title))
                        .foregroundColor(over ? AllowanceZone.overInk : Pearl.ink)
                }
                .foregroundColor(Pearl.ink)
                .padding(.horizontal, 16).frame(minHeight: 60)
                .accessibilityElement(children: .combine)
            }
            .padding(.top, 12)
            if !over, let perDay = allowance.perDayText, let days = allowance.daysLeft {
                (Text("About ") + Text(perDay).font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.ink)
                    + Text(" for the \(days == 1 ? "last day" : "\(days) days left")"))
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 4).padding(.top, 10)
            }
        }
    }

    /// fu.css `.story .kv`: 48 high, 16 pt, the figure in tabular digits.
    private func line(_ label: String, _ value: String, tone: Color = Pearl.ink, bold: Bool = false) -> some View {
        HStack {
            Text(label)
            Spacer(minLength: 8)
            Text(value).monospacedDigit().foregroundColor(tone)
        }
        .font(.custom(bold ? "Figtree-SemiBold" : "Figtree-Regular", size: 16, relativeTo: .body))
        .foregroundColor(Pearl.ink)
        .padding(.horizontal, 16).frame(minHeight: 48)
        .accessibilityElement(children: .combine)
    }
}

extension Allowance {
    static let needsIncomeLine = "Add your income to see your Allowance."
}
