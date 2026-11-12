import SwiftUI

/// T-46 Category: Groceries — what went to one category this month, against
/// her usual month for it, and the rows behind it.
@MainActor
struct CategoryPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let name: String
    let month: String?
    /// "spending", "income" or "none": which part of By category it's from.
    let counts: String
    let rows: [Transaction]
    let total: Double

    @State private var usual: Double?

    private struct Budgets: Decodable {
        let rows: [Lenient<Line>]?
        struct Line: Decodable {
            let category: String
            let usual: Double?
        }
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                GlassCard {
                    HStack(alignment: .top, spacing: 0) {
                        stat(headline, Format.whole(total), tone)
                        if let usual = usual, counts == "spending" {
                            stat("Usual month", Format.whole(usual), Pearl.ink)
                        }
                    }
                    .padding(16)
                }
                GlassCard {
                    ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                        if i > 0 { RowSeparator(inset: 72) }
                        NavigationLink(value: t) { TransactionRow(t: t, showsCategory: false) }
                            .buttonStyle(.plain)
                    }
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.top, 8).padding(.bottom, 32)
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold)).foregroundColor(Pearl.ink)
                }
                .accessibilityLabel("Back")
            }
            ToolbarItem(placement: .principal) {
                Text(name).font(Nacre.headline).foregroundColor(Pearl.ink)
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationBarTitleDisplayMode(.inline)
        .task { await loadUsual() }
    }

    /// "Spent in November", or "Came in, November" for money in.
    private var headline: String {
        let when = month.map { Format.monthName($0) } ?? "this month"
        switch counts {
        case "spending": return "Spent in \(when)"
        case "income": return "Came in, \(when)"
        default: return "Not counted, \(when)"
        }
    }

    private var tone: Color {
        counts == "spending" ? Pearl.ink : counts == "income" ? Pearl.moneyIn : Pearl.ink
    }

    private func stat(_ label: String, _ value: String, _ tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted)
            Text(value).font(Pearl.display(.title3)).foregroundColor(tone)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
    }

    /// Her usual month for the category, once Pearl has months to go on.
    private func loadUsual() async {
        guard counts == "spending",
              let b: Budgets = try? await app.api.get("api/category-budgets") else { return }
        usual = b.rows?.compactMap(\.value).first { $0.category == name }?.usual
    }
}
