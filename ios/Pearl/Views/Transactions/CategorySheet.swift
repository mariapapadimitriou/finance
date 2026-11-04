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

    @Environment(\.dismiss) private var dismiss
    @State private var chosen: String
    @State private var spending: Bool
    @State private var remember = false
    @State private var bill = false

    init(name: String, amount: String, tone: Color, categories: [CategoryList.Category], current: String,
         merchant: String? = nil, spendingOnly: Bool = false, mark: String? = nil,
         onRegularBill: ((Bool) -> Void)? = nil, title: String = "Category",
         onDelete: (() -> Void)? = nil, onSave: @escaping (String, Bool) -> Void) {
        self.title = title
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
        _spending = State(initialValue: spendingOnly || Self.spendingGroups.contains(group))
    }

    private static let spendingGroups = ["essentials", "lifestyle"]
    private static let otherGroups = ["income", "savings", "transfer"]
    private static let groupNames = ["essentials": "Essentials", "lifestyle": "Lifestyle", "income": "Income",
                                     "savings": "Savings", "transfer": "Moving money"]
    /// A state Pearl puts a row in, not one she picks.
    private static let notPickable: Set<String> = ["Unsorted transfers"]

    var body: some View {
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
                    ForEach(spending ? Self.spendingGroups : Self.otherGroups, id: \.self) { group in
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
                    if let merchant = merchant {
                        RowSeparator(inset: 0).padding(.top, 4)
                        Toggle(isOn: $remember) {
                            Text("Do the same for every \(merchant)").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                        .tint(Pearl.action)
                        .padding(.horizontal, 4)
                    }
                    if onRegularBill != nil, spending {
                        if merchant == nil { RowSeparator(inset: 0).padding(.top, 4) }
                        Toggle(isOn: $bill) {
                            Text("Regular bill").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                        .tint(Pearl.action)
                        .padding(.horizontal, 4)
                    }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
            }
            Button("Save") {
                onRegularBill?(bill && spending)
                onSave(chosen, remember)
            }
                .buttonStyle(NacreButtonStyle())
                .disabled(chosen == current && !remember && !bill)
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
            if let onDelete = onDelete {
                Button("Delete this rule", action: onDelete)
                    .buttonStyle(NacreTextButtonStyle())
                    .padding(.horizontal, 16).padding(.bottom, 8)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
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
        categories.filter {
            ($0.group ?? "lifestyle") == group && !Self.notPickable.contains($0.name)
                && ($0.hidden != true || $0.name == current)
        }
    }

    private func tile(_ c: CategoryList.Category) -> some View {
        let on = chosen == c.name
        return Button { chosen = c.name } label: {
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
