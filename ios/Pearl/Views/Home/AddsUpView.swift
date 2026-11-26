import SwiftUI

/// How it adds up (n-home-gauge, n-cf-meter; drawn as PX-AddsUp and
/// PX-AddsUpCash): opened by Home's gauge and Cash flow's "How it adds up"
/// row. The month in Fraunces 34, then the server's own rows: Came in, less
/// the bills (paid and still to come) and what she moved to savings (and
/// Your plan, and what came from last month, when there is any) make the
/// Allowance; the Allowance less Spent so far, Allowance left (P1b). Then the
/// daily amount. THL-125.
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
            // fu.css `.story`: rows 48 high, 16 pt, 0.5 pt `sep` between
            // them (kit `.kv+.kv`), the figures muted, Came in green.
            APCard {
                line("Came in", "+" + Format.whole(row("income") ?? 0), tone: Pearl.moneyIn, first: true)
                line("Bills", "−" + Format.whole(bills))
                // Between Bills and the Allowance: the savings share set aside
                // each pay ("Saving", fix/savings-rate-and-pg, product owner
                // 2026-11-26). Shown only when the server sends its row.
                if let saving = row("saving"), saving >= 0.5 { line("Saving", "−" + Format.whole(saving)) }
                if let saved = row("saved"), saved >= 0.5 { line("Moved to savings", "−" + Format.whole(saved)) }
                if let plan = row("plan"), plan >= 0.5 { line("Your plan", "−" + Format.whole(plan)) }
                if let carried = row("from_last_month"), abs(carried) >= 0.5 {
                    line("From last month", (carried < 0 ? "−" : "+") + Format.whole(carried))
                }
                line("Allowance", Format.whole(allowance.total ?? 0), bold: true)
            }
            .padding(.top, 16)
            // P1b (TP-P1-Home): the Allowance, less Spent so far, is
            // Allowance left, the same words as the ring.
            APCard {
                line("Allowance", Format.whole(allowance.total ?? 0), first: true)
                line("Spent so far", "−" + Format.whole(allowance.spent ?? 0))
                Rectangle().fill(APlus.separator).frame(height: 0.5).accessibilityHidden(true)
                // `.kv.big`: 60 high, the label 16/600, the figure Fraunces 28/600.
                HStack {
                    Text(over ? "Over" : "Allowance left")
                        .font(.custom("Figtree-SemiBold", size: 16, relativeTo: .body)).foregroundColor(Pearl.ink)
                    Spacer(minLength: 8)
                    Text(allowance.leftText)
                        .font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title))
                        .foregroundColor(over ? AllowanceZone.overInk : Pearl.muted)
                        .lineLimit(1).minimumScaleFactor(0.7)
                }
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

    /// fu.css `.story .kv`: 48 high, 16 pt, the figure muted in tabular
    /// digits; a 0.5 pt `sep` above every row but the first.
    private func line(_ label: String, _ value: String, tone: Color = Pearl.muted, bold: Bool = false,
                      first: Bool = false) -> some View {
        VStack(spacing: 0) {
            if !first { Rectangle().fill(APlus.separator).frame(height: 0.5).accessibilityHidden(true) }
            HStack {
                Text(label).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                Text(value).monospacedDigit().foregroundColor(tone)
            }
            .font(.custom(bold ? "Figtree-SemiBold" : "Figtree-Regular", size: 16, relativeTo: .body))
            .padding(.horizontal, 16).frame(minHeight: 48)
            .accessibilityElement(children: .combine)
        }
    }
}

extension Allowance {
    static let needsIncomeLine = "Add your income to see your Allowance."
}
