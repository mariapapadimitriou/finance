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
    /// Off when the page behind this sheet already has the switch.
    var showsAlways = true
    /// The Always switch: whether new rows from the merchant sort the same way.
    @State private var newOnes = true
    /// G1-WhatWasThis-r (T-04n, approved): Pearl's guess leads with one
    /// button, then her four likeliest, and every other answer opens in place
    /// under "Something else…". What was this? only; nil guess leads with the four.
    var leadsWithLikely = false
    var guess: String? = nil
    /// P3 / P4: the server's likeliest for this purchase (finance/likely.py).
    var likelyFirst: [String]? = nil
    /// P3 / P15: What was this? › Something else opens the picker in place.
    @State private var pickerOpen = false
    /// P15c: All categories, one level down.
    @State private var allOpen = false
    @State private var query = ""

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
         answersAtOnce: Bool = false, newOnesOn: Bool = true, showsAlways: Bool = true,
         leadsWithLikely: Bool = false, guess: String? = nil, likelyFirst: [String]? = nil,
         onSave: @escaping (String, Bool) -> Void) {
        self.leadsWithLikely = leadsWithLikely
        self.likelyFirst = likelyFirst
        self.guess = guess
        self.answersAtOnce = answersAtOnce
        self.showsAlways = showsAlways
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
    // TP-Words (P15): plain group names.
    private static let groupNames = ["essentials": "Everyday", "lifestyle": "Fun and treats", "income": "Income",
                                     "savings": "Savings", "transfer": "Moving money"]
    /// A state Pearl puts a row in, not one she picks.
    private static let notPickable: Set<String> = ["Unsorted transfers"]

    /// P15 (TP-P15-Category, fewer taps): the one picker, for Change on a
    /// page and Something else on What was this?: the who, a search field
    /// that looks typeable, her 8 most used (the current one ringed) and All
    /// categories one level down. A tap picks and closes.
    private var onePage: some View {
        VStack(spacing: 0) {
            pickerTitle.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    if allOpen {
                        allCategories
                    } else {
                        header
                        PearlField(placeholder: "Search categories", text: $query, kind: .search,
                                   identifier: "Search categories")
                            .padding(.top, 14)
                        if available.isEmpty {
                            LoadState(error: app.categoriesError) { Task { await app.loadCategories() } }
                        } else if searching {
                            searchResults
                        } else {
                            groupLabel("Most used")
                            CFTileGrid { ForEach(mostUsed) { c in pickTile(c) } }
                            APCard {
                                Button { withAnimation(.easeOut(duration: 0.2)) { allOpen = true } } label: {
                                    CFRowLabel(symbol: "ellipsis", title: "All categories", trailing: .chevron)
                                }
                                .buttonStyle(.plain)
                                .accessibilityIdentifier("All categories")
                            }
                            .padding(.top, 12)
                        }
                        if !searching {
                            if let merchant = merchant, showsAlways {
                                APCard { CFToggleRow(symbol: "repeat", title: Self.everyTime,
                                                     sub: "For every \(merchant) purchase", isOn: $newOnes) }
                                    .padding(.top, 12)
                            }
                            if onRegularBill != nil {
                                APCard { CFToggleRow(symbol: "calendar", title: "Regular bill", isOn: $bill) }.padding(.top, 12)
                            }
                            if let extras = extras { extras.padding(.top, 16) }
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
                .sheetPart()
            }
        }
        .cfSheet()
        // POLISH-01 audit 1: sized to what it shows.
        .fitsContent()
        .presentationDragIndicator(.visible)
        .task { if available.isEmpty { await app.loadCategories() } }
    }

    /// P15c: "All categories" with Back; the picker itself, with Back to
    /// What was this? when Something else opened it; or the plain title.
    @ViewBuilder private var pickerTitle: some View {
        if allOpen {
            BackSheetTitle(title: "All categories", back: { withAnimation(.easeOut(duration: 0.2)) { allOpen = false } }) { dismiss() }
        } else if pickerOpen {
            BackSheetTitle(title: "Category", back: { withAnimation(.easeOut(duration: 0.2)) { pickerOpen = false; query = "" } }) { dismiss() }
        } else {
            CFSheetTitle(title: title) { dismiss() }
        }
    }

    /// The words on the switch everywhere (TP-Words: was "Always for this merchant").
    static let everyTime = "Do this every time"

    private var searching: Bool { !query.trimmingCharacters(in: .whitespaces).isEmpty }

    /// Her 8 most used spending categories (GET /api/categories `uses`), the
    /// current one first and ringed. Hers, never a fixed list.
    private var mostUsed: [CategoryList.Category] {
        let pool = Self.spendingGroups.flatMap { tiles(in: $0) }
        var out = pool.enumerated().sorted { a, b in
            let ua = a.element.uses ?? 0, ub = b.element.uses ?? 0
            return ua != ub ? ua > ub : a.offset < b.offset
        }.map(\.element)
        if let now = out.firstIndex(where: { $0.name == current }) { out.insert(out.remove(at: now), at: 0) }
        return Array(out.prefix(8))
    }

    /// A tile on the picker: the current one has the 2 pt rose line; a tap picks.
    private func pickTile(_ c: CategoryList.Category) -> some View {
        CFTile(symbol: Self.symbol(for: c.name), title: c.name, mark: c.name == current ? .current : .rest) {
            pick(c.name)
        }
        .accessibilityLabel(c.name)
    }

    private func pick(_ name: String) {
        onRegularBill?(bill)
        onSave(name, merchant != nil && newOnes)
    }

    private func pickCase(_ key: String) {
        onCase?(key, newOnes && caseRule?(key) != nil && key != "not_mine")
    }

    /// P15b: results as rows, the group as a plain line under each.
    @ViewBuilder private var searchResults: some View {
        let q = query.trimmingCharacters(in: .whitespaces).lowercased()
        let cats = Self.spendingGroups.flatMap { g in tiles(in: g).map { (g, $0) } }
            .filter { $0.1.name.lowercased().contains(q) }
        let cases = (notSpending ?? []).filter { $0.label.lowercased().contains(q) }
        if cats.isEmpty && cases.isEmpty {
            Text("Nothing called “\(query)”").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4).padding(.top, 14)
        } else {
            APCard {
                ForEach(Array(cats.enumerated()), id: \.element.1.id) { i, pair in
                    if i > 0 { APSeparator(afterFace: false) }
                    pickRow(symbol: Self.symbol(for: pair.1.name), title: pair.1.name,
                            sub: Self.groupNames[pair.0]) { pick(pair.1.name) }
                }
                ForEach(Array(cases.enumerated()), id: \.element.id) { i, c in
                    if i > 0 || !cats.isEmpty { APSeparator(afterFace: false) }
                    pickRow(symbol: c.symbol, title: c.label, sub: Self.notReally) { pickCase(c.key) }
                }
            }
            .padding(.top, 14)
        }
    }

    /// P15c: Everyday, Fun and treats, Not really spending, as rows.
    @ViewBuilder private var allCategories: some View {
        ForEach(Self.spendingGroups, id: \.self) { group in
            let items = tiles(in: group)
            if !items.isEmpty {
                groupLabel(Self.groupNames[group] ?? group)
                APCard {
                    ForEach(Array(items.enumerated()), id: \.element.id) { i, c in
                        if i > 0 { APSeparator(afterFace: false) }
                        pickRow(symbol: Self.symbol(for: c.name), title: c.name, sub: nil,
                                on: c.name == current) { pick(c.name) }
                    }
                }
            }
        }
        if let cases = notSpending {
            groupLabel(Self.notReally)
            APCard {
                ForEach(Array(cases.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { APSeparator(afterFace: false) }
                    pickRow(symbol: c.symbol, title: c.label, sub: c.key == "work" ? "Someone pays you back for it" : nil) {
                        pickCase(c.key)
                    }
                }
            }
        }
    }

    static let notReally = "Not really spending"

    private func pickRow(symbol: String, title: String, sub: String?, on: Bool = false,
                         action: @escaping () -> Void) -> some View {
        Button(action: action) {
            CFRowLabel(symbol: symbol, title: title, sub: sub, bold: on, trailing: .none)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(title)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    var body: some View {
        if answersAtOnce && leadsWithLikely && !pickerOpen { likelyPage } else if answersAtOnce { onePage } else { steps }
    }

    // MARK: G1-WhatWasThis-r (T-04n)

    /// T-04n (G1-WhatWasThis-r, approved): the who; PEARL'S GUESS, "Dining
    /// out?" (Fraunces 24) and "Yes, Dining out" on one card; OR and her four
    /// likeliest as slim tiles; "Something else…", which opens every other
    /// answer here, on this page; and Always for the merchant last.
    private var likelyPage: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: title) { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header
                    if let guess = realGuess, available.contains(where: { $0.name == guess }) {
                        guessCard(guess).padding(.top, 14)
                    }
                    if available.isEmpty {
                        LoadState(error: app.categoriesError) { Task { await app.loadCategories() } }
                    } else {
                        // P3a (TP-P3-NoGuess): with no real guess, no "Other?":
                        // the four likeliest, straight under the who.
                        if realGuess != nil { groupLabel("Or") } else { Color.clear.frame(height: 18) }
                        CFTileGrid { ForEach(likely) { c in tile(c) } }
                    }
                    APCard {
                        // P3 / P15: Something else opens the one picker, in place.
                        Button { withAnimation(.easeOut(duration: 0.2)) { pickerOpen = true } } label: {
                            CFRowLabel(symbol: "ellipsis", title: "Something else", trailing: .chevron)
                        }
                        .buttonStyle(.plain)
                        .accessibilityIdentifier("Something else")
                        .accessibilityHint("Search, or every category")
                    }
                    .padding(.top, 12)
                    if let merchant = merchant, showsAlways {
                        APCard { CFToggleRow(symbol: "repeat", title: Self.everyTime,
                                             sub: "For every \(merchant) purchase", isOn: $newOnes) }
                            .padding(.top, 12)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
                .sheetPart()
            }
        }
        .cfSheet()
        .fitsContent()
        .presentationDragIndicator(.visible)
        .task { if available.isEmpty { await app.loadCategories() } }
    }

    /// P3: Pearl's guess only when it is one; "Other" is no guess.
    private var realGuess: String? { guess.flatMap { $0 == "Other" ? nil : $0 } }

    /// PEARL'S GUESS (12, `action`, 1.2 tracked), "Dining out?" and the one
    /// Primary, on a plain card (kit `.card`, 16 padding, 12 apart).
    private func guessCard(_ guess: String) -> some View {
        APCard {
            VStack(alignment: .leading, spacing: 12) {
                Text("PEARL’S GUESS")
                    .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                    .foregroundColor(Pearl.action)
                Text("\(guess)?").font(Pearl.heading(24, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Button("Yes, \(guess)") {
                    onRegularBill?(bill)
                    onSave(guess, merchant != nil && newOnes)
                }
                .buttonStyle(APPrimaryButtonStyle())
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
        }
    }

    /// Her four likeliest spending categories, not Pearl's guess: the ones
    /// she has used most (GET /api/categories `uses`), in the list's order
    /// between equals. Hers, never a fixed list.
    private var likely: [CategoryList.Category] {
        Self.likeliest(Self.spendingGroups.flatMap { tiles(in: $0) }.filter { $0.name != realGuess },
                       prefer: likelyFirst)
    }

    /// P3 / P4: the likeliest `count` of `pool` for this purchase: the
    /// server's own order for it first (`prefer`, finance/likely.py: her
    /// picks for the merchant, similar names, the bank's hint), then her
    /// most used (GET /api/categories `uses`), the list's order between
    /// equals. Only ever tiles she taps. P3d's page tiles are the same four.
    static func likeliest(_ pool: [CategoryList.Category], count: Int = 4,
                          prefer: [String]? = nil) -> [CategoryList.Category] {
        let first = (prefer ?? []).compactMap { n in pool.first { $0.name == n } }
        let rest = byUse(pool).filter { c in !first.contains(c) }
        return Array((first + rest).prefix(count))
    }

    private static func byUse(_ pool: [CategoryList.Category]) -> [CategoryList.Category] {
        let ranked = pool.enumerated().sorted { a, b in
            let ua = a.element.uses ?? 0, ub = b.element.uses ?? 0
            return ua != ub ? ua > ub : a.offset < b.offset
        }
        return ranked.map(\.element)
    }

    /// The spending categories she can pick, in the list's order.
    static func spending(_ cats: [CategoryList.Category]) -> [CategoryList.Category] {
        spendingGroups.flatMap { g in
            cats.filter { ($0.group ?? "lifestyle") == g && !notPickable.contains($0.name) && $0.hidden != true }
        }
    }

    private var steps: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: title) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    header
                    if !spendingOnly {
                        // G1-Change: kit `.seg`, not the stock picker.
                        CFSegmented(options: [(true, "Spending"), (false, "Not spending")], selection: $spending)
                            .padding(.top, 14)
                            .accessibilityLabel("Spending or not spending")
                    }
                    if answering, let cases = notSpending {
                        CaseGrid(cases: cases, chosen: $chosenCase)
                            .padding(.top, 16)
                            // Leaving every one out is a bigger step: she turns that on herself.
                            .onChange(of: chosenCase) { key in rememberCase = key != "not_mine" }
                        if let key = chosenCase, let rule = caseRule?(key) {
                            APCard { CFToggleRow(symbol: "repeat", title: rule, isOn: $rememberCase) }.padding(.top, 12)
                        }
                    }
                    if !answering && available.isEmpty {
                        LoadState(error: app.categoriesError) { Task { await app.loadCategories() } }
                    }
                    ForEach(answering ? [] : (spending ? Self.spendingGroups : Self.otherGroups), id: \.self) { group in
                        let items = tiles(in: group)
                        if !items.isEmpty {
                            groupLabel(Self.groupNames[group] ?? group)
                            CFTileGrid { ForEach(items) { c in tile(c) } }
                        }
                    }
                    if onRegularBill != nil, spending, !answering {
                        APCard { CFToggleRow(symbol: "calendar", title: "Regular bill", isOn: $bill) }.padding(.top, 16)
                    }
                    if spending, !answering, let extras = extras { extras.padding(.top, 16) }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 16)
            }
            if let line = previewLine, !answering {
                // G1-Change (REDESIGN-14): the one-line champagne banner,
                // "Also moves the 6 earlier ones · Allowance +$46".
                CFBanner(text: line)
                    .padding(.horizontal, 16).padding(.top, 8)
            }
            if answering {
                Button("Continue") {
                    if let c = chosenCase { onCase?(c, caseRule?(c) != nil && rememberCase) }
                }
                    .buttonStyle(APPrimaryButtonStyle())
                    .disabled(chosenCase == nil)
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
            } else {
            Button("Save") {
                onRegularBill?(bill && spending)
                onSave(chosen, remember)
            }
                .buttonStyle(APPrimaryButtonStyle())
                .disabled((chosen == current && !bill && !confirmsCurrent) || available.isEmpty)
                .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, remember ? 0 : 8)
            if remember {
                Button("Just this one") {
                    onRegularBill?(bill && spending)
                    onSave(chosen, false)
                }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.link))
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
        .cfSheet()
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

    /// kit `.who`: "LO  Loblaws / −$84.12 · Wed, Nov 11".
    private var header: some View {
        CFWho(name: name, line: amount, tone: tone, mark: mark, nameLines: onDelete == nil ? 1 : 3)
    }

    /// kit `.label`, 16 above and 8 below the tiles.
    private func groupLabel(_ text: String) -> some View {
        APSectionLabel(text: text).padding(.top, 16).padding(.bottom, 8)
    }

    private func tiles(in group: String) -> [CategoryList.Category] {
        available.filter {
            ($0.group ?? "lifestyle") == group && !Self.notPickable.contains($0.name)
                && ($0.hidden != true || $0.name == current)
        }
    }

    private func tile(_ c: CategoryList.Category) -> some View {
        let on = chosen == c.name
        // A+ (G1-Change, G1-WhatWasThis): a slim tile; the chosen one has the
        // 2 pt rose line; on the answer-at-once page Pearl's guess has the
        // dashed rose line.
        let mark: CFTile.Mark = answersAtOnce ? (on && !c.name.isEmpty ? .guess : .rest) : (on ? .current : .rest)
        return CFTile(symbol: Self.symbol(for: c.name), title: c.name, mark: mark) {
            if answersAtOnce {
                onRegularBill?(bill)
                onSave(c.name, merchant != nil && newOnes)
            } else {
                chosen = c.name
            }
        }
        .accessibilityLabel(c.name)
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

/// P15c: a sheet title with Back on the left and ✕ on the right.
struct BackSheetTitle: View {
    let title: String
    let back: () -> Void
    let close: () -> Void

    var body: some View {
        ZStack {
            Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                .lineLimit(1).padding(.horizontal, 56)
                .accessibilityAddTraits(.isHeader)
            HStack {
                CFBackButton(action: back)
                Spacer()
                CFCloseButton(action: close)
            }
        }
        .frame(minHeight: 44)
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 10)
    }
}

// MARK: - Answers as tiles (T-06, T-08, T-12, T-78)

/// One answer on a What was this? grid.
struct CaseTile: Identifiable, Hashable {
    let key: String
    let label: String
    let symbol: String
    var id: String { key }

    /// T-06: money out that isn't spending. P15 (TP-Words): plain names,
    /// in the board's order.
    static let notSpending: [CaseTile] = [
        CaseTile(key: "own", label: "Moved between my accounts", symbol: "arrow.left.arrow.right"),
        CaseTile(key: "saved", label: "Saved", symbol: "lifepreserver"),
        CaseTile(key: "card", label: "Paid off my card", symbol: "creditcard"),
        CaseTile(key: "lent", label: "I lent it to someone", symbol: "arrow.up.forward"),
        CaseTile(key: "paying_back", label: "Paying off a loan", symbol: "arrow.uturn.left"),
        CaseTile(key: "work", label: "Work expense", symbol: "briefcase"),
        CaseTile(key: "not_mine", label: "Someone else’s purchase", symbol: "person.crop.circle.badge.xmark"),
    ]

    /// TR-07: Leave out, under Mark as… when Confirm takes its place on Select's bar.
    static let leaveOut = CaseTile(key: "leave_out", label: "Leave out", symbol: "eye.slash")

    /// T-12: money in that isn't income. PB-10 (Paid back, 1351:8770,
    /// approved 2026-11-15): one "Paid back" tile replaces Paying me back,
    /// Money back and Work paying me back; "Who paid you back?" (PB-11)
    /// asks the rest. Six tiles; the four income tiles stay as they are.
    static let notIncome: [CaseTile] = [
        CaseTile(key: "paid_back", label: "Paid back", symbol: "person.2"),
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

    /// S-11k / T-08k (SPLIT-18): what Other income asks next, "What kind of
    /// income?", with finance/income.py's other four kinds as their keys.
    static let otherIncome: [CaseTile] = [
        CaseTile(key: "interest", label: "Interest", symbol: "percent"),
        CaseTile(key: "government", label: "Government credits", symbol: "building.columns"),
        CaseTile(key: "tax_refund", label: "Tax refund", symbol: "arrow.uturn.backward"),
        CaseTile(key: "other", label: "Other income", symbol: "ellipsis"),
    ]

    /// S-11c (SPLIT-19): what the extra from cash or another app can be.
    static func cashExtra(who: String, app: Bool) -> [CaseTile] {
        [CaseTile(key: "overpaid", label: "\(who) overpaid", symbol: "person.crop.circle.badge.xmark"),
         // PAID-02: the extra covers a different purchase.
         CaseTile(key: "payback", label: "Pays back something else", symbol: "person.2"),
         CaseTile(key: "gift", label: "A gift", symbol: "gift"),
         CaseTile(key: "returned", label: app ? "I sent it back" : "I gave it back", symbol: "arrow.uturn.backward")]
    }
}

/// A+ (G1-WhatWasThis, G1-Select's Mark as…): two across, kit `.tile.slim`;
/// the chosen answer has the 2 pt rose line.
struct CaseGrid: View {
    let cases: [CaseTile]
    @Binding var chosen: String?
    /// What VoiceOver says after the label: "Interest, income kind, button" (T-08k).
    var role: String? = nil

    var body: some View {
        CFTileGrid {
            ForEach(cases) { c in
                let on = chosen == c.key
                CFTile(symbol: c.symbol, title: c.label, mark: on ? .current : .rest,
                       iconTone: c.key == "not_mine" ? Pearl.action : Pearl.action) { chosen = c.key }
                    .accessibilityLabel(role.map { "\(c.label), \($0)" } ?? c.label)
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
                let delta: Double?
                let merchantCount: Int?
                enum CodingKeys: String, CodingKey {
                    case delta
                    case merchantCount = "merchant_count"
                }
            }

            guard let p: Preview = try? await api.post("api/transactions/\(id)/category/preview",
                                                     ["category": name, "apply_to_merchant": remember]) else { return nil }
            // REDESIGN-14 (G1-Change): one line, "Also moves the 6 earlier
            // ones · Allowance +$46". Less text: the reason goes.
            var words: [String] = []
            let others = max(0, (p.merchantCount ?? 1) - 1)
            if remember && others > 0 {
                words.append(others == 1 ? "Also moves the earlier one" : "Also moves the \(others) earlier ones")
            }
            if let delta = p.delta, abs(delta) >= 0.5 {
                words.append("Allowance \(delta > 0 ? "+" : "\u{2212}")\(Format.whole(abs(delta)))")
            }
            return words.isEmpty ? nil : words.joined(separator: " \u{00B7} ")
        }
    }
}
