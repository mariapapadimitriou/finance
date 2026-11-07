import SwiftUI

/// Change category (THL-152, T-04, T-52): who and how much, Spending or Not
/// spending, the categories as tiles by group, and Save. The categories are
/// the server's own (GET /api/categories), the ones she hid left out.
struct CategorySheet: View {
    let name: String
    let amount: String
    let tone: Color
    let categories: [CategoryList.Category]
    let current: String
    /// "Do the same for every Loblaws": a rule for the merchant, when there is one.
    var merchant: String? = nil
    let onSave: (String, Bool) -> Void
    /// Only spending categories, with no Spending / Not spending switch
    /// (Sort these days, T-21).
    var spendingOnly = false
    /// What the disc shows instead of initials: "3" for three picked (T-51).
    var mark: String? = nil
    /// T-04's "Regular bill": told on Save, so it can go on to Add to your
    /// bills? (T-32). Nil hides the switch.
    var onRegularBill: ((Bool) -> Void)? = nil
    /// The title at the top ("Rule" when editing a saved rule).
    var title = "Category"
    /// "Delete this rule" under Save, when editing a saved rule.
    var onDelete: (() -> Void)? = nil
    /// T-79: what saving would do, before it's saved ("Also moves 6 other
    /// Loblaws transactions…"), for the category and the remember switch.
    var preview: ((String, Bool) async -> String?)? = nil
    @State private var previewLine: String?
    /// T-06 / T-04n: the Not spending side as answers, not categories
    /// (Saved, My own account, Card payment…), with Continue.
    var notSpending: [CaseTile]? = nil
    /// The answer, and whether to do the same for every one from now on.
    var onCase: ((String, Bool) -> Void)? = nil
    /// The Outcome table's rule for an answer ("Do this for every Rogers from
    /// now on"); nil when that answer can't make one.
    var caseRule: ((String) -> String?)? = nil
    /// Split with others, One-off…: under the categories, for a purchase.
    var extras: AnyView? = nil
    @State private var rememberCase = true
    /// T-52: Save on Pearl's guess, unchanged, confirms it.
    var confirmsCurrent = false
    @State private var chosenCase: String?
    /// One page (the redesign): every answer on one scroll, and a tile answers
    /// at once, with Undo after. No tabs, Save or Continue.
    var answersAtOnce = false
    /// The Always switch: whether new rows from the merchant sort the same way.
    @State private var newOnes = true

    @Environment(\.dismiss) private var dismiss
    @EnvironmentObject private var app: AppModel
    @State private var chosen: String
    @State private var spending: Bool
    /// T-79: saving would move her other transactions there too.
    @State private var remember = false
    @State private var bill = false

    init(name: String, amount: String, tone: Color, categories: [CategoryList.Category], current: String,
         merchant: String? = nil, spendingOnly: Bool = false, mark: String? = nil,
         onRegularBill: ((Bool) -> Void)? = nil, title: String = "Category",
         onDelete: (() -> Void)? = nil, preview: ((String, Bool) async -> String?)? = nil,
         notSpending: [CaseTile]? = nil, startNotSpending: Bool = false, onCase: ((String, Bool) -> Void)? = nil,
         confirmsCurrent: Bool = false, caseRule: ((String) -> String?)? = nil, extras: AnyView? = nil,
         answersAtOnce: Bool = false, newOnesOn: Bool = true,
         onSave: @escaping (String, Bool) -> Void) {
        self.answersAtOnce = answersAtOnce
        _newOnes = State(initialValue: newOnesOn)
        self.confirmsCurrent = confirmsCurrent
        self.caseRule = caseRule
        self.extras = extras
        self.title = title
        self.preview = preview
        self.notSpending = notSpending
        self.onCase = onCase
        self.onDelete = onDelete
        self.spendingOnly = spendingOnly
        self.mark = mark
        self.onRegularBill = onRegularBill
        self.name = name
        self.amount = amount
        self.tone = tone
        self.categories = categories
        self.current = current
        self.merchant = merchant
        self.onSave = onSave
        _chosen = State(initialValue: current)
        let group = categories.first { $0.name == current }?.group ?? "lifestyle"
        _spending = State(initialValue: !(startNotSpending && notSpending != nil)
                          && (spendingOnly || Self.spendingGroups.contains(group)))
    }

    private var answering: Bool { !spending && notSpending != nil }

    /// What the caller passed, or the app's own list if that came up empty: a
    /// sheet with no tiles is a dead end whatever caused it.
    private var available: [CategoryList.Category] { categories.isEmpty ? app.categories : categories }

    private static let spendingGroups = ["essentials", "lifestyle"]
    private static let otherGroups = ["income", "savings", "transfer"]
    private static let groupNames = ["essentials": "Essentials", "lifestyle": "Lifestyle", "income": "Income",
                                     "savings": "Savings", "transfer": "Moving money"]
    /// A state Pearl puts a row in, not one she picks.
    private static let notPickable: Set<String> = ["Unsorted transfers"]

    /// Every answer on one scroll: the Always switch, the categories, then Not spending.
    private var onePage: some View {
        VStack(spacing: 0) {
            SheetTitle(title: title) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header
                    if let merchant = merchant {
                        Toggle(isOn: $newOnes) {
                            Text("Always for \(merchant)").font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .tint(Pearl.action).padding(.horizontal, 4)
                    }
                    if available.isEmpty {
                        LoadState(error: app.categoriesError) { Task { await app.loadCategories() } }
                    }
                    ForEach(Self.spendingGroups + ["lifestyleEnd"], id: \.self) { group in
                        if group == "lifestyleEnd" {
                            if let cases = notSpending {
                                Text("NOT SPENDING").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                    .padding(.horizontal, 16).padding(.top, 4)
                                    .accessibilityAddTraits(.isHeader)
                                CaseGrid(cases: cases, chosen: Binding(get: { nil }, set: { key in
                                    if let key = key { onCase?(key, newOnes && caseRule?(key) != nil && key != "not_mine") }
                                }))
                            }
                        } else {
                            let items = tiles(in: group)
                            if !items.isEmpty {
                                Text((Self.groupNames[group] ?? group).uppercased())
                                    .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                    .padding(.horizontal, 16).padding(.top, 4)
                                    .accessibilityAddTraits(.isHeader)
                                LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                                    ForEach(items) { c in tile(c) }
                                }
                            }
                        }
                    }
                    if onRegularBill != nil {
                        RowSeparator(inset: 0).padding(.top, 4)
                        Toggle(isOn: $bill) {
                            Text("Regular bill").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                        .tint(Pearl.action).padding(.horizontal, 4)
                    }
                    if let extras = extras { extras }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { if available.isEmpty { await app.loadCategories() } }
    }

    var body: some View {
        if answersAtOnce { onePage } else { steps }
    }

    private var steps: some View {
        VStack(spacing: 0) {
            SheetTitle(title: title) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    header
                    if !spendingOnly {
                        Picker("", selection: $spending) {
                            Text("Spending").tag(true)
                            Text("Not spending").tag(false)
                        }
                        .pickerStyle(.segmented)
                        .accessibilityLabel("Spending or not spending")
                    }
                    if answering, let cases = notSpending {
                        CaseGrid(cases: cases, chosen: $chosenCase)
                            // Leaving every one out is a bigger step: she turns that on herself.
                            .onChange(of: chosenCase) { key in rememberCase = key != "not_mine" }
                        if let key = chosenCase, let rule = caseRule?(key) {
                            Toggle(isOn: $rememberCase) {
                                Text(rule).font(Nacre.body).foregroundColor(Pearl.ink)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                            .tint(Pearl.action).padding(.horizontal, 4)
                        }
                    }
                    if !answering && available.isEmpty {
                        LoadState(error: app.categoriesError) { Task { await app.loadCategories() } }
                    }
                    ForEach(answering ? [] : (spending ? Self.spendingGroups : Self.otherGroups), id: \.self) { group in
                        let items = tiles(in: group)
                        if !items.isEmpty {
                            Text((Self.groupNames[group] ?? group).uppercased())
                                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16).padding(.top, 4)
                                .accessibilityAddTraits(.isHeader)
                            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
                                ForEach(items) { c in tile(c) }
                            }
                        }
                    }
                    if onRegularBill != nil, spending, !answering {
                        RowSeparator(inset: 0).padding(.top, 4)
                        Toggle(isOn: $bill) {
                            Text("Regular bill").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                        .tint(Pearl.action)
                        .padding(.horizontal, 4)
                    }
                    if spending, !answering, let extras = extras { extras }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
            }
            if let line = previewLine, !answering {
                GlassCard {
                    HStack(spacing: 12) {
                        IconBubble(symbol: "arrow.triangle.2.circlepath")
                        Text(line).font(Nacre.body).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                            .frame(maxWidth: .infinity, alignment: .leading)
                    }
                    .padding(14)
                }
                .padding(.horizontal, 16).padding(.top, 8)
                .accessibilityElement(children: .combine)
            }
            if answering {
                Button("Continue") {
                    if let c = chosenCase { onCase?(c, caseRule?(c) != nil && rememberCase) }
                }
                    .buttonStyle(NacreButtonStyle())
                    .disabled(chosenCase == nil)
                    .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
            } else {
            Button("Save") {
                onRegularBill?(bill && spending)
                onSave(chosen, remember)
            }
                .buttonStyle(NacreButtonStyle())
                .disabled((chosen == current && !bill && !confirmsCurrent) || available.isEmpty)
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, remember ? 0 : 8)
            if remember {
                Button("Just this one") {
                    onRegularBill?(bill && spending)
                    onSave(chosen, false)
                }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(chosen == current)
                .padding(.horizontal, 16).padding(.bottom, 8)
            }
            }
            if let onDelete = onDelete {
                Button("Delete this rule", action: onDelete)
                    .buttonStyle(NacreTextButtonStyle())
                    .padding(.horizontal, 16).padding(.bottom, 8)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { if available.isEmpty { await app.loadCategories() } }
        .task(id: chosen) {
            // T-79: what saving does, said before it's saved; when it would
            // move others, Save does and Just this one doesn't.
            guard let preview = preview, merchant != nil, chosen != current else {
                previewLine = nil
                remember = false
                return
            }
            previewLine = await preview(chosen, true)
            remember = previewLine?.hasPrefix("Also moves") == true
        }
    }

    /// "LO  Loblaws  −$84.12".
    private var header: some View {
        HStack(spacing: 12) {
            Initials(name: mark ?? name, size: 48)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(onDelete == nil ? 1 : 3)
                Text(amount).font(Nacre.subheadline).foregroundColor(tone)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }

    private func tiles(in group: String) -> [CategoryList.Category] {
        available.filter {
            ($0.group ?? "lifestyle") == group && !Self.notPickable.contains($0.name)
                && ($0.hidden != true || $0.name == current)
        }
    }

    private func tile(_ c: CategoryList.Category) -> some View {
        let on = chosen == c.name
        return Button {
            if answersAtOnce {
                onRegularBill?(bill)
                onSave(c.name, merchant != nil && newOnes)
            } else {
                chosen = c.name
            }
        } label: {
            VStack(spacing: 6) {
                Image(systemName: Self.symbol(for: c.name))
                    .font(.system(size: 16))
                    .foregroundColor(Pearl.action)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(Pearl.blush.opacity(on ? 1 : 0.7)))
                Text(c.name)
                    .font(.custom(on ? "Figtree-SemiBold" : "Figtree-Regular", size: 13, relativeTo: .footnote))
                    .foregroundColor(on ? Pearl.action : Pearl.ink)
                    .lineLimit(2).multilineTextAlignment(.center).minimumScaleFactor(0.85)
            }
            .frame(maxWidth: .infinity, minHeight: 76)
            .padding(.vertical, 6)
            .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                .fill(on ? Pearl.blush.opacity(0.75) : Nacre.glass))
            .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                .strokeBorder(on ? Pearl.action : Nacre.separator, lineWidth: on ? 1.5 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(c.name)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// The web's category icons (src/pearl/icons.jsx), in SF Symbols.
    static func symbol(for category: String) -> String {
        let icons: [String: String] = [
            "Groceries": "cart", "Dining": "fork.knife", "Food Delivery": "takeoutbag.and.cup.and.straw",
            "Coffee": "cup.and.saucer", "Alcohol & Bars": "wineglass", "Transport": "bus",
            "Gas & Fuel": "fuelpump", "Travel": "airplane", "Lodging": "bed.double", "Shopping": "bag",
            "Streaming": "tv", "News & Media": "newspaper", "Software": "laptopcomputer",
            "Utilities": "bolt", "Phone & Internet": "wifi", "Rent & Housing": "house",
            "Insurance": "checkmark.shield", "Health": "heart", "Fitness": "dumbbell",
            "Personal Care": "sparkles", "Entertainment": "ticket", "Education": "book", "Pets": "pawprint",
            "Home": "sofa", "Gifts & Charity": "gift", "Fees & Interest": "percent",
            "Taxes": "building.columns", "Cash & ATM": "banknote", "Saved": "lifepreserver",
            "Lent": "arrow.up.forward", "Borrowed": "arrow.down.backward",
            "Income": "chart.line.uptrend.xyaxis", "Transfers": "arrow.left.arrow.right",
            "Other": "ellipsis",
        ]
        return icons[category] ?? "ellipsis"
    }
}

// MARK: - Answers as tiles (T-06, T-08, T-12, T-78)

/// One answer on a What was this? grid.
struct CaseTile: Identifiable, Hashable {
    let key: String
    let label: String
    let symbol: String
    var id: String { key }

    /// T-06: money out that isn't spending.
    static let notSpending: [CaseTile] = [
        CaseTile(key: "saved", label: "Saved", symbol: "lifepreserver"),
        CaseTile(key: "own", label: "My own account", symbol: "arrow.left.arrow.right"),
        CaseTile(key: "card", label: "Card payment", symbol: "creditcard"),
        CaseTile(key: "lent", label: "Lending to someone", symbol: "arrow.up.forward"),
        CaseTile(key: "paying_back", label: "Paying back a loan", symbol: "arrow.uturn.left"),
        CaseTile(key: "work", label: "Work expense", symbol: "briefcase"),
        CaseTile(key: "not_mine", label: "Not mine", symbol: "person.crop.circle.badge.xmark"),
    ]

    /// T-12: money in that isn't income.
    static let notIncome: [CaseTile] = [
        CaseTile(key: "paid_back", label: "Paying me back", symbol: "person.2"),
        CaseTile(key: "refund", label: "Money back", symbol: "arrow.uturn.backward"),
        CaseTile(key: "reimbursement", label: "Work paying me back", symbol: "briefcase"),
        CaseTile(key: "own", label: "My own money", symbol: "arrow.left.arrow.right"),
        CaseTile(key: "loan", label: "Lent me this", symbol: "banknote"),
        CaseTile(key: "out_of_savings", label: "Out of savings", symbol: "lifepreserver"),
        CaseTile(key: "lent_back", label: "Money I lent, back", symbol: "arrow.down.backward"),
        CaseTile(key: "not_mine", label: "Not mine", symbol: "person.crop.circle.badge.xmark"),
    ]

    /// T-78 for deposits: the answers that need nothing per row.
    static let notIncomeTogether: [CaseTile] = notIncome.filter {
        ["own", "loan", "out_of_savings", "lent_back", "not_mine"].contains($0.key)
    }

    /// T-08: kinds of income, kept short. Interest, government credits and tax
    /// refunds Pearl recognises by name; anything else it missed is Other income.
    static let income: [CaseTile] = [
        CaseTile(key: "regular", label: "My pay", symbol: "briefcase"),
        CaseTile(key: "bonus", label: "Bonus", symbol: "sparkle"),
        CaseTile(key: "gifts", label: "A gift", symbol: "gift"),
        CaseTile(key: "other", label: "Other income", symbol: "ellipsis"),
    ]
}

/// Three across, the category sheet's tile look.
struct CaseGrid: View {
    let cases: [CaseTile]
    @Binding var chosen: String?

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
            ForEach(cases) { c in
                let on = chosen == c.key
                Button { chosen = c.key } label: {
                    VStack(spacing: 6) {
                        Image(systemName: c.symbol).font(.system(size: 16)).foregroundColor(Pearl.action)
                            .frame(width: 36, height: 36).background(Circle().fill(Pearl.blush.opacity(on ? 1 : 0.7)))
                        Text(c.label)
                            .font(.custom(on ? "Figtree-SemiBold" : "Figtree-Regular", size: 13, relativeTo: .footnote))
                            .foregroundColor(on ? Pearl.action : Pearl.ink)
                            .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
                            .padding(.horizontal, 4)
                    }
                    .frame(maxWidth: .infinity, minHeight: 76).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(on ? Pearl.blush.opacity(0.75) : Nacre.glass))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(on ? Pearl.action : Nacre.separator, lineWidth: on ? 1.5 : 1))
                    .contentShape(RoundedRectangle(cornerRadius: 16, style: .continuous))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(c.label)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
    }
}

extension CategorySheet {
    /// T-79's line for a transaction: "Also moves 6 other Loblaws
    /// transactions, and new ones from now on." and what it does to Allowance.
    static func preview(api: APIClient, id: String, merchant: String) -> (String, Bool) async -> String? {
        { name, remember in
            struct Preview: Decodable {
                let line: String?
                let merchantCount: Int?
                enum CodingKeys: String, CodingKey {
                    case line
                    case merchantCount = "merchant_count"
                }
            }
            guard let p: Preview = try? await api.post("api/transactions/\(id)/category/preview",
                                                     ["category": name, "apply_to_merchant": remember]) else { return nil }
            var words: [String] = []
            let others = max(0, (p.merchantCount ?? 1) - 1)
            if remember && others > 0 {
                words.append("Also moves \(others) other \(merchant) transaction\(others == 1 ? "" : "s"), and new ones from now on.")
            }
            if let line = p.line, !line.isEmpty { words.append(line) }
            return words.isEmpty ? nil : words.joined(separator: " ")
        }
    }
}
