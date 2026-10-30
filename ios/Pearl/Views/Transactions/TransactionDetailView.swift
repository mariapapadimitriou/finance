import SwiftUI

/// One transaction (AB-22): what it counts as, and changing its category.
@MainActor
struct TransactionDetailView: View {
    @EnvironmentObject private var app: AppModel
    let transaction: Transaction
    let categories: [CategoryList.Category]

    @State private var category: String?
    @State private var picking = false
    @State private var busy = false
    @State private var message: String?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 16) {
                Overline("Transaction", tone: Pearl.action)
                header
                if !facts.isEmpty {
                    PearlCard(padding: 0, spacing: 0, radius: Pearl.radiusTile) {
                        ForEach(Array(facts.enumerated()), id: \.offset) { index, fact in
                            if index > 0 { Rectangle().fill(Pearl.border).frame(height: 1) }
                            HStack(alignment: .firstTextBaseline, spacing: 16) {
                                Text(fact.label).foregroundColor(Pearl.muted)
                                Spacer(minLength: 8)
                                Text(fact.value).foregroundColor(Pearl.ink).multilineTextAlignment(.trailing)
                            }
                            .font(Pearl.text(.body))
                            .padding(.horizontal, 20).padding(.vertical, 14)
                        }
                    }
                }
                PearlCard(spacing: 10, radius: Pearl.radiusTile) {
                    Overline("Category")
                    CategoryChip(label: current)
                }
                if let note = transaction.note, !note.isEmpty {
                    Text(note).font(Pearl.text(.subheadline, .medium)).foregroundColor(Pearl.muted)
                }
                if let description = transaction.description, !description.isEmpty {
                    PearlCard(spacing: 10, radius: Pearl.radiusTile) {
                        Overline("From your bank")
                        Text(description).font(.callout.monospaced()).foregroundColor(Pearl.ink)
                    }
                }
                if let message = message { Notice(text: message) }
                if let error = error { Notice(text: error, tone: .caution) }
                Button("Change category") { picking = true }
                    .buttonStyle(PrimaryButtonStyle())
                    .disabled(busy)
                    .padding(.top, 4)
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 24)
        }
        .pearlPage()
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $picking) {
            CategoryPicker(categories: categories, current: current, merchant: transaction.merchant) { name, remember in
                picking = false
                Task { await change(to: name, remember: remember) }
            }
        }
    }

    /// Initials, who and when, and the amount.
    private var header: some View {
        HStack(alignment: .top, spacing: 12) {
            Text(initials)
                .font(Pearl.text(.body, .medium)).foregroundColor(Pearl.ink)
                .frame(width: 48, height: 48)
                .background(Circle().fill(Pearl.track))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 4) {
                Text(transaction.merchant)
                    .font(Pearl.display(.title3)).tracking(-0.44).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(Format.day(transaction.date))
                    .font(Pearl.text(.footnote, .medium)).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text(amount)
                .font(Pearl.display(.title3)).tracking(-0.44)
                .foregroundColor(left ? Pearl.muted : (transaction.inflow ? Pearl.moneyIn : Pearl.moneyOut))
                .lineLimit(1)
        }
    }

    private var current: String { category ?? transaction.category ?? "Other" }

    private var left: Bool { !(transaction.excluded ?? "").isEmpty || transaction.countsToward == "none" }

    private var amount: String {
        if left { return Format.amount(transaction.amount) }
        return (transaction.inflow ? "+" : "-") + Format.amount(transaction.amount)
    }

    private var initials: String {
        transaction.merchant.split(separator: " ").prefix(2)
            .compactMap { $0.first.map(String.init) }.joined().uppercased()
    }

    /// Account, what it counts toward, and why it's left out.
    private var facts: [(label: String, value: String)] {
        var out: [(label: String, value: String)] = []
        if let account = transaction.account, !account.isEmpty { out.append(("Account", account)) }
        if let toward = transaction.countsToward, !toward.isEmpty {
            out.append(("Counts toward", toward == "none" ? "Not counted" : toward))
        }
        if let excluded = transaction.excluded, !excluded.isEmpty { out.append(("Left out", excluded)) }
        if transaction.pending == true { out.append(("Status", "Pending")) }
        return out
    }

    private func change(to name: String, remember: Bool) async {
        busy = true
        defer { busy = false }
        do {
            let _: CategoryChange = try await app.api.patch("api/transactions/\(transaction.id)",
                                                            ["category": name, "apply_to_merchant": remember])
            category = name
            message = remember ? "\(name), and every \(transaction.merchant) from now on." : "Moved to \(name)."
            error = nil
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// Every category, grouped as Pearl groups them, with "Remember".
struct CategoryPicker: View {
    let categories: [CategoryList.Category]
    let current: String
    let merchant: String
    let onPick: (String, Bool) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var query = ""
    @State private var remember = false

    private let groupOrder = ["essentials", "lifestyle", "savings", "income", "transfer"]
    private let groupNames = ["essentials": "Essentials", "lifestyle": "Lifestyle", "savings": "Savings",
                              "income": "Income", "transfer": "Transfers"]

    var body: some View {
        NavigationStack {
            List {
                Section {
                    Toggle("Do the same for every \(merchant)", isOn: $remember).tint(Pearl.action)
                }
                ForEach(groups) { group in
                    Section(groupNames[group.key] ?? group.key.capitalized) {
                        ForEach(group.items) { c in
                            Button {
                                onPick(c.name, remember)
                            } label: {
                                HStack {
                                    Text(c.name).foregroundColor(Pearl.ink)
                                    Spacer()
                                    if c.name == current {
                                        Image(systemName: "checkmark").foregroundColor(Pearl.action)
                                    }
                                }
                            }
                        }
                    }
                }
            }
            .searchable(text: $query, prompt: "Find a category")
            .navigationTitle("Category")
            .navigationBarTitleDisplayMode(.inline)
            .toolbar {
                ToolbarItem(placement: .cancellationAction) { Button("Cancel") { dismiss() } }
            }
        }
    }

    private struct CategoryGroup: Identifiable {
        let key: String
        let items: [CategoryList.Category]
        var id: String { key }
    }

    private var groups: [CategoryGroup] {
        let shown = categories.filter { query.isEmpty || $0.name.localizedCaseInsensitiveContains(query) }
        var by: [String: [CategoryList.Category]] = [:]
        for c in shown { by[c.group ?? "other", default: []].append(c) }
        let keys = by.keys.sorted { (groupOrder.firstIndex(of: $0) ?? 99) < (groupOrder.firstIndex(of: $1) ?? 99) }
        return keys.map { CategoryGroup(key: $0, items: by[$0] ?? []) }
    }
}
