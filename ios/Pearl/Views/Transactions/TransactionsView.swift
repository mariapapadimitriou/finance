import SwiftUI

/// Cash flow › Transactions: a month at a time, newest first, or a search
/// across everything.
@MainActor
struct TransactionsView: View {
    @EnvironmentObject private var app: AppModel

    @State private var months: [String] = []
    @State private var month: String?
    @State private var query = ""
    @State private var rows: [Transaction] = []
    @State private var total = 0
    @State private var totals: TransactionList.Totals?
    @State private var reviewCount = 0
    @State private var loading = false
    /// Once the first list has come back (or failed), never spin forever.
    @State private var loadedOnce = false
    @State private var error: String?
    @State private var categories: [CategoryList.Category] = []

    private let page = 100

    var body: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                header
                if query.isEmpty, let totals = totals {
                    MonthStats(spent: totals.spent ?? 0, income: totals.income ?? 0)
                        .padding(.top, 20)
                }
                toolbar.padding(.top, 16)
                if reviewCount > 0 {
                    NavigationLink {
                        ReviewView()
                    } label: {
                        NeedsALookBanner(count: reviewCount)
                    }
                    .buttonStyle(.plain)
                    .padding(.top, 16)
                }
                if rows.isEmpty {
                    Group {
                        if loading || !loadedOnce {
                            ProgressView().frame(maxWidth: .infinity)
                        } else if let error = error {
                            Text(error).foregroundColor(Pearl.muted)
                        } else {
                            Text(query.isEmpty ? "No transactions this month." : "Nothing matches “\(query)”.")
                                .foregroundColor(Pearl.muted)
                        }
                    }
                    .padding(.vertical, 32)
                }
                ForEach(days) { group in
                    DayHeading(iso: group.day)
                    ForEach(group.rows) { t in
                        NavigationLink(value: t) {
                            TransactionRow(t: t)
                        }
                        .buttonStyle(.plain)
                        .onAppear { if t.id == rows.last?.id { Task { await loadMore() } } }
                        if t.id != group.rows.last?.id { Divider().overlay(Pearl.border) }
                    }
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.top, 24)
            .padding(.bottom, 24)
        }
        .pearlPage()
        .navigationBarHidden(true)
        .navigationDestination(for: Transaction.self) { t in
            TransactionDetailView(transaction: t, categories: categories)
        }
        .refreshable { await reload() }
        .task(id: app.version) { await start() }
    }

    /// "OCTOBER 2026" over "Cash flow", as on the web.
    private var header: some View {
        VStack(alignment: .leading, spacing: 4) {
            Text((query.isEmpty ? (month.map { Format.month($0) } ?? "") : "Search").uppercased())
                .font(Pearl.text(.caption, .semibold)).tracking(1.44)
                .foregroundColor(Pearl.action)
            Text("Cash flow").font(Pearl.display()).foregroundColor(Pearl.ink)
        }
    }

    /// Search · Month, in one row.
    private var toolbar: some View {
        HStack(spacing: 8) {
            HStack(spacing: 10) {
                Image(systemName: "magnifyingglass").font(.system(size: 14)).foregroundColor(Pearl.muted)
                TextField("Search", text: $query)
                    .font(Pearl.text(.callout))
                    .foregroundColor(Pearl.ink)
                    .submitLabel(.search)
                    .onSubmit { Task { await reload() } }
                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundColor(Pearl.muted)
                    }
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.horizontal, 14)
            .frame(height: 40)
            .background(Pearl.card)
            .clipShape(RoundedRectangle(cornerRadius: 12, style: .continuous))
            .overlay(RoundedRectangle(cornerRadius: 12, style: .continuous).stroke(Pearl.border, lineWidth: 1))
            .onChange(of: query) { value in if value.isEmpty { Task { await reload() } } }

            Menu {
                ForEach(months.reversed(), id: \.self) { m in
                    Button(Format.month(m)) { month = m; query = ""; Task { await reload() } }
                }
            } label: {
                HStack(spacing: 6) {
                    Text(month.map { Format.monthName($0) } ?? "Month")
                    Image(systemName: "chevron.down").font(.system(size: 11, weight: .semibold))
                }
                .font(Pearl.text(.callout, .medium))
                .foregroundColor(Pearl.ink)
                .padding(.horizontal, 14)
                .frame(height: 40)
                .background(Pearl.card)
                .clipShape(Capsule())
                .overlay(Capsule().stroke(Pearl.borderStrong, lineWidth: 1))
            }
            .disabled(months.isEmpty)
            .accessibilityLabel("Month")
        }
    }

    private struct Day: Identifiable {
        let day: String
        var rows: [Transaction]
        var id: String { day }
    }

    private var days: [Day] {
        var out: [Day] = []
        for t in rows {
            if let last = out.last, last.day == t.date {
                out[out.count - 1].rows.append(t)
            } else {
                out.append(Day(day: t.date, rows: [t]))
            }
        }
        return out
    }

    private func start() async {
        if months.isEmpty, let summary: Summary = try? await app.api.get("api/summary") {
            months = summary.months ?? []
            if month == nil { month = summary.latestMonth ?? months.last }
        }
        if categories.isEmpty, let list: CategoryList = try? await app.api.get("api/categories") {
            categories = list.categories.filter { $0.hidden != true }
        }
        if let review: Review = try? await app.api.get("api/review") {
            reviewCount = review.open ?? review.count
        }
        await reload()
    }

    private func params(offset: Int) -> [String: String] {
        var p = ["limit": String(page), "offset": String(offset)]
        if !query.isEmpty {
            p["q"] = query
        } else if let month = month {
            p["month"] = month
        }
        return p
    }

    private func reload() async {
        loading = true
        defer {
            loading = false
            loadedOnce = true
        }
        do {
            let list: TransactionList = try await app.api.get("api/transactions/list", query: params(offset: 0))
            rows = list.transactions
            total = list.total
            totals = list.monthTotals
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func loadMore() async {
        guard !loading, rows.count < total else { return }
        loading = true
        defer { loading = false }
        if let list: TransactionList = try? await app.api.get("api/transactions/list",
                                                               query: params(offset: rows.count)) {
            rows += list.transactions
        }
    }
}

/// Spent · Came in · Left: the month as three numbers, as on a phone on the web.
struct MonthStats: View {
    let spent: Double
    let income: Double

    var body: some View {
        let left = max(income, 0) - max(spent, 0)
        HStack(spacing: 8) {
            tile("Spent", Format.amount(spent), Pearl.spent)
            tile("Came in", Format.amount(income), Pearl.cameIn)
            if left < -0.005 {
                tile("Over", Format.amount(left), Pearl.spent)
            } else {
                tile("Left", Format.amount(left), Pearl.ink)
            }
        }
    }

    private func tile(_ label: String, _ value: String, _ tone: Color) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Pearl.text(.caption, .medium)).foregroundColor(Pearl.muted)
            Text(value)
                .font(Pearl.text(.headline, .semibold)).monospacedDigit()
                .foregroundColor(tone)
                .lineLimit(1).minimumScaleFactor(0.7)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 12).padding(.vertical, 10)
        .background(Pearl.card)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
        .overlay(RoundedRectangle(cornerRadius: 20, style: .continuous).stroke(Pearl.border, lineWidth: 1))
        .accessibilityElement(children: .combine)
    }
}

/// "12 need a look.  Review ›" on blush.
struct NeedsALookBanner: View {
    let count: Int

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: "info.circle").font(.system(size: 18))
            Text(count == 1 ? "1 needs a look." : "\(count) need a look.")
                .font(Pearl.text(.callout))
            Spacer(minLength: 8)
            HStack(spacing: 2) {
                Text("Review").underline()
                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
            }
            .font(Pearl.text(.footnote, .semibold))
        }
        .foregroundColor(Pearl.onBlush)
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(Pearl.blush)
        .clipShape(RoundedRectangle(cornerRadius: 20, style: .continuous))
    }
}

/// "TODAY · THU, OCT 29".
struct DayHeading: View {
    let iso: String

    var body: some View {
        let parts = Format.dayParts(iso)
        (Text(parts.name.uppercased()).foregroundColor(Pearl.ink)
            + Text(parts.date.isEmpty ? "" : " · " + parts.date.uppercased()).foregroundColor(Pearl.muted))
            .font(Pearl.text(.caption, .semibold)).tracking(1.44)
            .padding(.horizontal, 12)
            .padding(.top, 24).padding(.bottom, 6)
            .accessibilityAddTraits(.isHeader)
    }
}

/// One transaction: the category's icon, who and which account, the amount
/// and the category under it.
struct TransactionRow: View {
    let t: Transaction

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            CategoryAvatar(category: t.chip?.label ?? t.category, name: t.merchant)
            VStack(alignment: .leading, spacing: 0) {
                Text(t.merchant).font(Pearl.text(.callout)).foregroundColor(Pearl.ink).lineLimit(1)
                if let meta = meta {
                    Text(meta).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted).lineLimit(1)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            VStack(alignment: .trailing, spacing: 8) {
                Text(amount)
                    .font(Pearl.text(.body, muted ? .medium : .semibold)).monospacedDigit()
                    .foregroundColor(muted ? Pearl.muted : (t.inflow ? Pearl.moneyIn : Pearl.moneyOut))
                if let label = t.chip?.label ?? t.category {
                    CategoryChip(label: label, suggested: t.chip?.suggested == true)
                }
            }
        }
        .padding(.horizontal, 12)
        .padding(.vertical, 14)
        .contentShape(Rectangle())
    }

    private var muted: Bool { !(t.excluded ?? "").isEmpty || t.countsToward == "none" }

    private var amount: String {
        if muted { return Format.amount(t.amount) }
        return t.inflow ? "+" + Format.amount(t.amount) : "-" + Format.amount(t.amount)
    }

    private var meta: String? {
        let parts = [t.account, t.pending == true ? "Pending" : nil].compactMap { $0 }.filter { !$0.isEmpty }
        return parts.isEmpty ? nil : parts.joined(separator: " · ")
    }
}

/// The category as a chip: blush once settled, a dashed outline while it's
/// Pearl's guess.
struct CategoryChip: View {
    let label: String
    var suggested = false

    var body: some View {
        Text(label)
            .font(Pearl.text(.footnote, .medium))
            .lineLimit(1)
            .foregroundColor(suggested ? Pearl.ink : Pearl.onBlush)
            .padding(.horizontal, 10).padding(.vertical, 3)
            .background(suggested ? Pearl.card : Pearl.blush)
            .clipShape(Capsule())
            .overlay(Capsule().strokeBorder(Color(hex: 0xFF8FB1),
                                            style: StrokeStyle(lineWidth: 1, dash: [3]))
                .opacity(suggested ? 1 : 0))
    }
}

/// The category's icon in rose on blush; the name's initials when there's
/// no category to show.
struct CategoryAvatar: View {
    let category: String?
    let name: String

    var body: some View {
        ZStack {
            if let symbol = symbol {
                Circle().fill(Pearl.blush)
                Image(systemName: symbol).font(.system(size: 16)).foregroundColor(Pearl.rose)
            } else {
                Circle().fill(Pearl.track)
                Text(initials).font(Pearl.text(.footnote, .semibold)).foregroundColor(Pearl.ink)
            }
        }
        .frame(width: 40, height: 40)
        .accessibilityHidden(true)
    }

    private var initials: String {
        name.split(separator: " ").prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    /// The web's CATEGORY_ICONS (src/pearl/icons.jsx), in SF Symbols.
    private var symbol: String? {
        guard let category = category, !["Possible duplicate", "Whose?"].contains(category) else { return nil }
        let icons: [String: String] = [
            "Groceries": "cart", "Dining": "fork.knife", "Food Delivery": "box.truck", "Coffee": "cup.and.saucer",
            "Alcohol & Bars": "wineglass", "Transport": "bus", "Gas & Fuel": "fuelpump", "Travel": "airplane",
            "Lodging": "bed.double", "Shopping": "bag", "Streaming": "play.rectangle", "News & Media": "newspaper",
            "Software": "laptopcomputer", "Utilities": "bolt", "Phone & Internet": "wifi",
            "Rent & Housing": "house", "Insurance": "checkmark.shield", "Health": "heart", "Fitness": "dumbbell",
            "Personal Care": "sparkles", "Entertainment": "ticket", "Education": "book", "Pets": "pawprint",
            "Home": "sofa", "Gifts & Charity": "gift", "Fees & Interest": "percent", "Taxes": "building.columns",
            "Cash & ATM": "banknote", "Saved": "lifepreserver", "Lent": "arrow.up.forward",
            "Borrowed": "arrow.down.backward", "Income": "chart.line.uptrend.xyaxis",
            "Transfers": "arrow.left.arrow.right", "Transfer": "arrow.left.arrow.right",
        ]
        return icons[category] ?? "ellipsis"
    }
}
