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
    /// T-62 (G1-PaidWith): Paid with / Goes into on a Pearl sheet.
    @State private var pickingAccount = false
    @State private var similar: [ServerProblem.Match]?
    @State private var busy = false
    @State private var error: String?
    @FocusState private var typingAmount: Bool

    private static let incomeKinds = ["salary", "bonus", "interest", "gifts", "government", "tax_refund", "other"]

    var body: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: "Add a transaction") { dismiss() }
            ScrollView {
                VStack(spacing: 14) {
                    // G1-Change (Add a transaction): kit `.seg`, not the stock picker.
                    CFSegmented(options: [(false, "Money out"), (true, "Money in")], selection: $moneyIn)
                    .accessibilityLabel("Money out or money in")
                    .onChange(of: moneyIn) { _ in
                        category = nil
                        incomeKind = nil
                        similar = nil
                    }
                    amountField
                    // REDESIGN-09: Name is a well, its label above it.
                    PearlField(label: "Name", placeholder: "Where was it?", text: $name)
                        .textInputAutocapitalization(.words)
                    APCard {
                        // G0-DateSheet DP-01: the Pearl date sheet, not the stock picker.
                        row("Date", value: dayLabel) { pickingDay = true }
                        APSeparator(afterFace: false)
                        row("Category", value: categoryLabel, placeholder: categoryLabel == nil) {
                            pickingCategory = true
                        }
                        APSeparator(afterFace: false)
                        // T-62 (G1-PaidWith, REDESIGN-18): a Pearl sheet, not a stock Menu.
                        row(moneyIn ? "Goes into" : "Paid with", value: accountName) { pickingAccount = true }
                    }
                    if let similar = similar {
                        similarCard(similar)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger)
                            .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 12) {
                Button(similar == nil ? "Add" : "It’s a different one · add it") {
                    Task { await add(confirm: similar != nil) }
                }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(!ready || busy)
                // T-62d: Cancel keeps the one already there and adds nothing.
                if similar != nil {
                    Button("Cancel") { dismiss() }
                        .buttonStyle(APSecondaryButtonStyle())
                        .disabled(busy)
                }
            }
            .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .cfSheet()
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await loadAccounts() }
        .pearlDateSheet(isPresented: $pickingDay, title: "When was it?", selection: $day,
                        range: .pastOnly, quickPicks: true)
        .sheet(isPresented: $pickingAccount) {
            PaidWithSheet(title: moneyIn ? "Goes into" : "Paid with", accounts: accounts, chosen: account) { id in
                account = id
                similar = nil
                pickingAccount = false
            }
        }
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

    /// A+ (G1-Change, kit `.fld.big`): the amount in a 72 pt well, Fraunces
    /// 36, the `$` muted; the 2 pt rose line while she types.
    private var amountField: some View {
        ZStack {
            // G1-Add: "+$ 150.00" / "−$ 32.00", the sign and $ muted; "$ 0.00" empty.
            HStack(spacing: 6) {
                Text(value == nil ? "$" : (moneyIn ? "+$" : "\u{2212}$")).foregroundColor(Pearl.muted)
                Text(value.map { Format.amount($0).replacingOccurrences(of: "$", with: "") } ?? "0.00")
                    .foregroundColor(value == nil ? Pearl.muted : Pearl.ink)
            }
            .font(.custom("Fraunces-SemiBold", size: 36, relativeTo: .largeTitle))
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
        .frame(maxWidth: .infinity, minHeight: 72)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(APlus.well))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
            .strokeBorder(typingAmount ? Pearl.action : APlus.wellLine, lineWidth: typingAmount ? 2 : 1))
        .contentShape(Rectangle())
        .onTapGesture { typingAmount = true }
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

    /// G1-Add: an unanswered row says Choose in `link`.
    private func rowLabel(_ title: String, value: String, placeholder: Bool) -> some View {
        HStack(spacing: 8) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer()
            Text(value).font(Nacre.body).foregroundColor(placeholder ? Pearl.link : Pearl.muted).lineLimit(1)
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// What kind of income money in is (the kinds T-71 offers).
    private var kindSheet: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: "What kind of income?") { pickingCategory = false }
            ScrollView {
                APCard {
                    ForEach(Array(Self.incomeKinds.enumerated()), id: \.element) { i, k in
                        if i > 0 { APSeparator(afterFace: false) }
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
        .cfSheet()
        .presentationDetents([.medium, .large])
    }

    /// T-62d (G1-Add): the champagne banner "Looks like one already there:"
    /// holding the match as a payment row.
    private func similarCard(_ matches: [ServerProblem.Match]) -> some View {
        SimilarBanner(matches: matches)
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

/// T-62d (G1-Add, kit `.banner` stacked): "Looks like one already there:"
/// over a card of the matches as payment rows.
private struct SimilarBanner: View {
    let matches: [ServerProblem.Match]
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text("Looks like one already there:").font(Nacre.subheadline).foregroundColor(Pearl.ink)
            APCard {
                ForEach(Array(matches.prefix(3).enumerated()), id: \.element.id) { i, m in
                    if i > 0 { APSeparator() }
                    APPaymentRow(name: m.merchant, line: Format.weekdayDay(m.date),
                                 money: m.amount < 0 ? .into(abs(m.amount)) : .out(m.amount))
                }
            }
        }
        .padding(12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
            .fill(Pearl.champagne.opacity(scheme == .dark ? 0.10 : 0.22)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
    }
}

/// T-62 (G1-PaidWith, REDESIGN-18): Paid with (or Goes into) on a Pearl
/// sheet. Cash first, then each account she can add to by hand: a radio,
/// the face, the name over "••4417 · joint". A row picks at once; no Done.
struct PaidWithSheet: View {
    let title: String
    let accounts: [AccountsOverview.Account]
    let chosen: String
    let pick: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        APSheet {
            APSheetHeader(heading: title) { dismiss() }
            APOptionCard {
                option(id: "cash", face: "$", name: "Cash", line: "Not in a bank")
                ForEach(accounts) { a in
                    APSeparator()
                    // TEST-43: an empty institution falls back to the name, never "·".
                    option(id: a.id, face: APFace.initials(AccountWords.bank(a)), name: a.name,
                           line: Self.line(a))
                }
            }
        }
    }

    /// "••4417", "••0931 · joint".
    static func line(_ a: AccountsOverview.Account) -> String? {
        // TEST-43: no digits, no stray "••".
        let digits = (a.mask ?? "").trimmingCharacters(in: .whitespaces)
        let parts = [digits.isEmpty ? nil : "\u{2022}\u{2022}" + digits, a.joint == true ? "joint" : nil].compactMap { $0 }
        return parts.isEmpty ? nil : parts.joined(separator: " \u{00B7} ")
    }

    private func option(id: String, face: String, name: String, line: String?) -> some View {
        Button { pick(id) } label: {
            HStack(spacing: 12) {
                APRadio(on: chosen == id)
                Text(face)
                    .font(.custom("Figtree-Medium", size: 14, relativeTo: .footnote))
                    .lineLimit(1).minimumScaleFactor(0.6)
                    .foregroundColor(Pearl.ink)
                    .frame(width: 40, height: 40)
                    .background(Circle().fill(APlus.face))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    if let line = line {
                        Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([name, line].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(chosen == id ? [.isButton, .isSelected] : .isButton)
    }
}
