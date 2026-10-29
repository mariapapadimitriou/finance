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
    @State private var error: String?
    @State private var categories: [CategoryList.Category] = []

    private let page = 100

    var body: some View {
        List {
            if reviewCount > 0 {
                Section {
                    NavigationLink {
                        ReviewView()
                    } label: {
                        Label(reviewCount == 1 ? "1 transaction needs a look" : "\(reviewCount) transactions need a look",
                              systemImage: "sparkles")
                            .foregroundColor(Pearl.action)
                    }
                }
            }
            if query.isEmpty, let totals = totals {
                Section {
                    HStack {
                        stat("Spent", Format.whole(totals.spent ?? 0))
                        Spacer()
                        stat("Income", Format.whole(totals.income ?? 0))
                    }
                }
            }
            if rows.isEmpty {
                Section {
                    if loading || (error == nil && month == nil) {
                        HStack { Spacer(); ProgressView(); Spacer() }
                    } else if let error = error {
                        Text(error).foregroundColor(Pearl.muted)
                    } else {
                        Text(query.isEmpty ? "No transactions this month." : "Nothing matches “\(query)”.")
                            .foregroundColor(Pearl.muted)
                    }
                }
            }
            ForEach(days) { group in
                Section(Format.day(group.day)) {
                    ForEach(group.rows) { t in
                        NavigationLink(value: t) {
                            TransactionRow(t: t)
                        }
                        .onAppear { if t.id == rows.last?.id { Task { await loadMore() } } }
                    }
                }
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .background(Pearl.page.ignoresSafeArea())
        .navigationTitle(query.isEmpty ? Format.month(month ?? "") : "Search")
        .navigationBarTitleDisplayMode(.inline)
        .searchable(text: $query, prompt: "Search all transactions")
        .onSubmit(of: .search) { Task { await reload() } }
        .onChange(of: query) { value in if value.isEmpty { Task { await reload() } } }
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                Menu {
                    ForEach(months.reversed(), id: \.self) { m in
                        Button(Format.month(m)) { month = m; Task { await reload() } }
                    }
                } label: {
                    Image(systemName: "calendar")
                }
                .disabled(months.isEmpty)
            }
        }
        .navigationDestination(for: Transaction.self) { t in
            TransactionDetailView(transaction: t, categories: categories)
        }
        .refreshable { await reload() }
        .task(id: app.version) { await start() }
    }

    private func stat(_ label: String, _ value: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(.caption).foregroundColor(Pearl.muted)
            Text(value).font(Pearl.display(.title2)).foregroundColor(Pearl.ink)
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
        defer { loading = false }
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

struct TransactionRow: View {
    let t: Transaction

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            VStack(alignment: .leading, spacing: 3) {
                Text(t.merchant).foregroundColor(Pearl.ink).lineLimit(1)
                HStack(spacing: 6) {
                    if let label = t.chip?.label ?? t.category {
                        Text(label)
                            .font(.caption.weight(.medium))
                            .padding(.horizontal, 8).padding(.vertical, 2)
                            .background(t.chip?.suggested == true ? Color.clear : Pearl.answered)
                            .overlay(Capsule().strokeBorder(Pearl.border,
                                                            style: StrokeStyle(lineWidth: 1, dash: t.chip?.suggested == true ? [3] : [])))
                            .clipShape(Capsule())
                            .foregroundColor(Pearl.muted)
                    }
                    if t.pending == true {
                        Text("Pending").font(.caption).foregroundColor(Pearl.muted)
                    }
                }
            }
            Spacer(minLength: 8)
            Text(Format.signed(t.amount, inflow: t.inflow))
                .font(.body.weight(.semibold))
                .foregroundColor(t.inflow ? Pearl.moneyIn : Pearl.ink)
                .strikethrough(!(t.excluded ?? "").isEmpty, color: Pearl.muted)
        }
        .padding(.vertical, 2)
    }
}
