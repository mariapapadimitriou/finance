import SwiftUI

/// One transaction: what it counts as, and changing its category.
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
                TransactionHeader(name: transaction.merchant, date: transaction.date,
                                  account: transaction.account, amount: transaction.amount,
                                  inflow: transaction.inflow)
                PearlCard {
                    row("Category", current)
                    if let toward = transaction.countsToward, !toward.isEmpty {
                        row("Counts toward", toward)
                    }
                    if let excluded = transaction.excluded, !excluded.isEmpty {
                        row("Left out", excluded)
                    }
                    if let note = transaction.note, !note.isEmpty {
                        Text(note).font(.subheadline).foregroundColor(Pearl.muted)
                    }
                    Button("Change category") { picking = true }
                        .buttonStyle(SecondaryButtonStyle())
                        .disabled(busy)
                }
                if let description = transaction.description, !description.isEmpty {
                    PearlCard {
                        Text("From your bank").font(.caption.weight(.semibold)).foregroundColor(Pearl.muted)
                        Text(description).font(.callout.monospaced()).foregroundColor(Pearl.ink)
                    }
                }
                if let message = message { Notice(text: message) }
                if let error = error { Notice(text: error, tone: .caution) }
            }
            .padding(Pearl.gutter)
        }
        .pearlPage()
        .navigationTitle(transaction.merchant)
        .navigationBarTitleDisplayMode(.inline)
        .sheet(isPresented: $picking) {
            CategoryPicker(categories: categories, current: current, merchant: transaction.merchant) { name, remember in
                picking = false
                Task { await change(to: name, remember: remember) }
            }
        }
    }

    private var current: String { category ?? transaction.category ?? "Other" }

    private func row(_ label: String, _ value: String) -> some View {
        HStack {
            Text(label).foregroundColor(Pearl.muted)
            Spacer()
            Text(value).foregroundColor(Pearl.ink).multilineTextAlignment(.trailing)
        }
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
