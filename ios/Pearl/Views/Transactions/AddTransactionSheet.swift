import SwiftUI

/// Add a transaction (T-23, T-61, T-62): money out or money in, its name,
/// date and category, and what paid for it or where it went: cash, or an
/// account added by hand. Add waits for a name, an amount and a category.
/// Something already like it asks first.
@MainActor
struct AddTransactionSheet: View {
    let api: APIClient
    let categories: [CategoryList.Category]
    let onAdded: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var moneyIn = false
    @State private var amount = ""
    @State private var name = ""
    @State private var day = Date()
    @State private var pickingDay = false
    @State private var category: String?
    @State private var incomeKind: String?
    @State private var pickingCategory = false
    @State private var account = "cash"
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var similar: [ServerProblem.Match]?
    @State private var busy = false
    @State private var error: String?
    @FocusState private var typingAmount: Bool

    private static let incomeKinds = ["salary", "bonus", "interest", "gifts", "government", "tax_refund", "other"]

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Add a transaction") { dismiss() }
            ScrollView {
                VStack(spacing: 14) {
                    Picker("", selection: $moneyIn) {
                        Text("Money out").tag(false)
                        Text("Money in").tag(true)
                    }
                    .pickerStyle(.segmented)
                    .accessibilityLabel("Money out or money in")
                    .onChange(of: moneyIn) { _ in
                        category = nil
                        incomeKind = nil
                        similar = nil
                    }
                    amountField
                    GlassCard {
                        HStack {
                            Text("Name").font(Nacre.body).foregroundColor(Pearl.ink)
                            TextField("", text: $name, prompt: Text("e.g. Farmers’ market").foregroundColor(Pearl.muted))
                                .font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.trailing)
                                .textInputAutocapitalization(.words)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                        RowSeparator()
                        row("Date", value: dayLabel) { pickingDay.toggle() }
                        if pickingDay {
                            DatePicker("", selection: $day, in: ...Date(), displayedComponents: .date)
                                .datePickerStyle(.graphical).tint(Pearl.action)
                                .padding(.horizontal, 8)
                                .onChange(of: day) { _ in pickingDay = false }
                        }
                        RowSeparator()
                        row("Category", value: categoryLabel, placeholder: categoryLabel == nil) {
                            pickingCategory = true
                        }
                        RowSeparator()
                        Menu {
                            Picker("", selection: $account) {
                                Text("Cash").tag("cash")
                                ForEach(accounts) { a in Text(a.name).tag(a.id) }
                            }
                        } label: {
                            rowLabel(moneyIn ? "Goes into" : "Paid with", value: accountName, placeholder: false)
                        }
                        .buttonStyle(.plain)
                    }
                    if let similar = similar {
                        similarCard(similar)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            Button(similar == nil ? "Add" : "It’s a different one · add it") {
                Task { await add(confirm: similar != nil) }
            }
            .buttonStyle(NacreButtonStyle(busy: busy))
            .disabled(!ready || busy)
            .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await loadAccounts() }
        .sheet(isPresented: $pickingCategory) {
            if moneyIn {
                kindSheet
            } else {
                CategorySheet(name: name.isEmpty ? "New transaction" : name, amount: amountText,
                              tone: Pearl.ink, categories: categories, current: category ?? "",
                              spendingOnly: true) { chosen, _ in
                    category = chosen
                    similar = nil
                    pickingCategory = false
                }
            }
        }
    }

    // MARK: The amount

    /// "$0.00" in large type; "+$150.00" in green for money in.
    private var amountField: some View {
        ZStack {
            Text(amountText)
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(value == nil ? Pearl.muted : (moneyIn ? Pearl.moneyIn : Pearl.ink))
                .lineLimit(1).minimumScaleFactor(0.5)
                .accessibilityHidden(true)
            TextField("", text: $amount)
                .keyboardType(.decimalPad)
                .focused($typingAmount)
                .foregroundColor(.clear).tint(.clear)
                .frame(maxWidth: .infinity, minHeight: 60)
                .accessibilityLabel("Amount")
                .onChange(of: amount) { typed in
                    let kept = String(typed.filter { $0.isNumber || $0 == "." }.prefix(10))
                    if kept != typed { amount = kept }
                    similar = nil
                }
        }
        .frame(maxWidth: .infinity, minHeight: 60)
    }

    private var value: Double? {
        guard let v = Double(amount), v > 0 else { return nil }
        return (v * 100).rounded() / 100
    }

    private var amountText: String {
        guard let v = value else { return "$0.00" }
        return (moneyIn ? "+" : "") + Format.amount(v)
    }

    // MARK: The rows

    private var dayLabel: String {
        let iso = Format.isoDay(day)
        return Format.relativeDay(iso) == "Today" ? "Today" : Format.weekdayDay(iso)
    }

    private var categoryLabel: String? {
        if moneyIn { return incomeKind.map { TransactionDetailView.kindName($0) } }
        return category
    }

    private var accountName: String {
        accounts.first { $0.id == account }?.name ?? "Cash"
    }

    private var ready: Bool {
        value != nil && !name.trimmingCharacters(in: .whitespaces).isEmpty && categoryLabel != nil
    }

    private func row(_ title: String, value: String?, placeholder: Bool = false,
                     _ run: @escaping () -> Void) -> some View {
        Button(action: run) { rowLabel(title, value: value ?? "Choose", placeholder: placeholder) }
            .buttonStyle(.plain)
    }

    private func rowLabel(_ title: String, value: String, placeholder: Bool) -> some View {
        HStack(spacing: 8) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer()
            Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// What kind of income money in is (the kinds T-71 offers).
    private var kindSheet: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "What kind of income?") { pickingCategory = false }
            ScrollView {
                GlassCard {
                    ForEach(Array(Self.incomeKinds.enumerated()), id: \.element) { i, k in
                        if i > 0 { RowSeparator() }
                        Button {
                            incomeKind = k
                            similar = nil
                            pickingCategory = false
                        } label: {
                            HStack {
                                Text(TransactionDetailView.kindName(k)).font(Nacre.body).foregroundColor(Pearl.ink)
                                Spacer()
                                if incomeKind == k {
                                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold))
                                        .foregroundColor(Pearl.action)
                                }
                            }
                            .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(incomeKind == k ? .isSelected : [])
                    }
                }
                .padding(16)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.medium, .large])
    }

    /// "This looks like something already in your transactions:" and what.
    private func similarCard(_ matches: [ServerProblem.Match]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("This looks like something already in your transactions:")
                .font(Nacre.footnote).foregroundColor(Pearl.ink).padding(.horizontal, 16)
            GlassCard {
                ForEach(Array(matches.prefix(3).enumerated()), id: \.element.id) { i, m in
                    if i > 0 { RowSeparator() }
                    HStack {
                        VStack(alignment: .leading, spacing: 2) {
                            Text(m.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Text(Format.weekdayDay(m.date)).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        Spacer()
                        Text((m.amount < 0 ? "+" : "\u{2212}") + Format.amount(m.amount))
                            .font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
        }
    }

    // MARK: Server

    private func loadAccounts() async {
        if let overview: AccountsOverview = try? await api.get("api/accounts/overview") {
            accounts = overview.added ?? []
        }
    }

    private func add(confirm: Bool) async {
        guard let v = value else { return }
        busy = true
        defer { busy = false }
        var body: [String: Any] = [
            "date": Format.isoDay(day), "description": name.trimmingCharacters(in: .whitespaces),
            "amount": moneyIn ? -v : v, "account": account,
        ]
        if moneyIn {
            body["category"] = "Income"
            if let kind = incomeKind { body["income_kind"] = kind }
        } else if let category = category {
            body["category"] = category
        }
        if confirm { body["confirm"] = true }
        do {
            let _: OK = try await api.post("api/transactions", body)
            onAdded("Added \(name.trimmingCharacters(in: .whitespaces)).")
        } catch {
            if let problem = error.serverProblem, problem.needsConfirmation == true {
                similar = problem.matches ?? []
                self.error = nil
            } else {
                self.error = error.localizedDescription
            }
        }
    }
}
