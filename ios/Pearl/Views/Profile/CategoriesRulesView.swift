import SwiftUI

/// Profile › Categories and rules (CR-00 to CR-10; THL-123, THL-225, THL-226,
/// THL-234), A+ (REDESIGN-12; boards G5b-Rules, G5b-Rule, G5b-Categories,
/// G5b-Merchants, G5b-Tags): her rules and the ones learned with her, Fixed
/// or Variable for each category, her names for merchants, and her tags,
/// under one four-way segmented control. A List keeps the swipes (Delete a
/// rule; Rename or Remove a tag; Hide a category), drawn as A+ cards.
@MainActor
struct CategoriesRulesView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    enum Tab: String, CaseIterable, Identifiable {
        case rules = "Rules", categories = "Categories", merchants = "Merchants", tags = "Tags"
        var id: String { rawValue }
    }

    private struct Toast: Equatable {
        let id = UUID()
        let text: String
        var failed = false
    }

    @State private var tab = Tab.rules
    @State private var book: RulesBook?
    /// AI-05: rules Pearl learned from what she sorted, beside hers.
    @State private var learned: [LearnedRule] = []
    /// TR-09: her trips by name; a trip's tag has the trip's name.
    @State private var trips: [String: Trip] = [:]
    @State private var categories: [CategoryList.Category] = []
    @State private var error: String?
    @State private var toast: Toast?

    /// CR-04: a sorting rule's page; CR-05: a pay or leave-out rule's page.
    @State private var openRule: RulesBook.Rule?
    @State private var openCategory: CategoryList.Category?
    @State private var removingRule: RulesBook.Rule?
    @State private var renamingMerchant: RulesBook.MerchantName?
    @State private var renamingTag: RulesBook.TagTotal?
    @State private var removingTag: RulesBook.TagTotal?
    @State private var removingTagNext: RulesBook.TagTotal?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            CRHeader(tab: $tab, tags: Features.tags) { dismiss() }
                .padding(.horizontal, Pearl.gutter)
            if let book = book {
                list(book)
            } else {
                LoadState(error: error) { Task { await load() } }
                Spacer(minLength: 0)
            }
        }
        .nacreScreen()
        .navigationBarHidden(true)
        .overlay(alignment: .bottom) { toastView }
        .reloads { await load() }
        .navigationDestination(isPresented: present($openRule)) { rulePage }
        .navigationDestination(isPresented: present($openCategory)) { categoryPage }
        .sheet(item: $renamingMerchant) { merchantSheet($0) }
        // Asked once the sheet has gone: a sheet raised while one is closing
        // doesn't appear.
        .sheet(item: $renamingTag, onDismiss: {
            removingTag = removingTagNext
            removingTagNext = nil
        }) { tagSheet($0) }
        .sheet(item: $removingRule) { removeRuleSheet($0) }
        .sheet(item: $removingTag) { removeTagSheet($0) }
    }

    private func present<T>(_ item: Binding<T?>) -> Binding<Bool> {
        Binding(get: { item.wrappedValue != nil }, set: { if !$0 { item.wrappedValue = nil } })
    }

    // MARK: Pages and sheets

    @ViewBuilder private var rulePage: some View {
        if let rule = openRule {
            if rule.isSorting {
                RuleEditView(rule: rule, categories: categories, hidden: Set(book?.hidden ?? []),
                             onSaved: { text, undo in
                                 openRule = nil
                                 app.say(text, undo: undo.map(undoCall))
                                 app.changed()
                             }, onDelete: {
                                 openRule = nil
                                 delete(rule)
                             })
            } else {
                RuleInfoPage(rule: rule) { removingRule = rule }
            }
        }
    }

    @ViewBuilder private var categoryPage: some View {
        if let category = openCategory {
            CategoryKindPage(category: category, kind: book?.kinds?[category.name],
                             pearl: pearlKind(category.name),
                             hidden: isHidden(category.name), canHide: canHide(category.name),
                             onKind: { setKind(category.name, $0) },
                             onHide: { hide in
                                 openCategory = nil
                                 setHidden(category.name, hide)
                             })
        }
    }

    private func merchantSheet(_ merchant: RulesBook.MerchantName) -> some View {
        RenameSheet(title: "Rename merchant", label: "Call it", initial: merchant.name,
                    hint: "Bank: \(merchant.merchant)", other: "Use the bank’s name",
                    onSave: { name in
                        renamingMerchant = nil
                        run("Now \(name)") {
                            let _: OK = try await app.api.put("api/merchants/name",
                                                              ["merchant": merchant.merchant, "name": name])
                        }
                    }, onOther: {
                        renamingMerchant = nil
                        run("Now \(merchant.merchant)") {
                            let _: OK = try await app.api.delete("api/rules/name:\(merchant.key)")
                        }
                    })
    }

    private func tagSheet(_ tag: RulesBook.TagTotal) -> some View {
        RenameSheet(title: "Rename tag", label: "Call it", initial: tag.tag, hint: transactions(tag.count),
                    other: "Remove this tag",
                    onSave: { name in
                        renamingTag = nil
                        run("Now \(name)") {
                            let _: OK = try await app.api.put("api/tags/\(tag.tag)", ["name": name])
                        }
                    }, onOther: {
                        removingTagNext = tag
                        renamingTag = nil
                    })
    }

    /// CR-00x (TEST-06): a Pearl sheet. Red is only on the row that opened it.
    private func removeRuleSheet(_ rule: RulesBook.Rule) -> some View {
        PearlConfirmSheet(overline: "Rules", title: "Remove the rule for \(rule.name)?", message: rule.removing,
                          primary: "Remove the rule", busyLabel: "Removing…", secondary: "Keep it",
                          failure: "Couldn’t remove the rule. Nothing changed. Try again.",
                          onClose: { removingRule = nil }) {
            let reply: RuleReply = try await app.api.delete("api/rules/\(rule.id)")
            removingRule = nil
            openRule = nil
            app.say("Rule deleted", undo: reply.undo.map(undoCall))
            app.changed()
            await load()
        }
    }

    @ViewBuilder private func removeTagSheet(_ tag: RulesBook.TagTotal) -> some View {
        if let trip = trips[tag.tag] {
            // TR-09 (1331:6604): a trip's tag; removing it ends the trip, so it asks first.
            PearlConfirmSheet(overline: "Tags · A trip", title: "Remove \(tag.tag)?",
                              message: "This tag belongs to a trip, so the trip ends too. \(Trip.stayLine(trip.count)), in \(trip.months).",
                              primary: "Remove the trip and tag", busyLabel: "Removing…", secondary: "Keep it",
                              failure: "Couldn’t remove the tag. Nothing changed. Try again.",
                              onClose: { removingTag = nil }) { try await takeOff(tag) }
        } else {
            // CR-10x (TEST-06).
            PearlConfirmSheet(overline: "Tags", title: "Take \(tag.tag) off \(transactions(tag.count))?",
                              message: "The transactions stay as they are. Only the tag comes off.",
                              primary: "Remove the tag", busyLabel: "Removing…", secondary: "Keep it",
                              failure: "Couldn’t remove the tag. Nothing changed. Try again.",
                              onClose: { removingTag = nil }) { try await takeOff(tag) }
        }
    }

    private func takeOff(_ tag: RulesBook.TagTotal) async throws {
        let _: OK = try await app.api.put("api/tags/\(tag.tag)", ["name": NSNull()])
        removingTag = nil
        app.say("\(tag.tag) removed")
        app.changed()
        await load()
    }

    // MARK: The list

    private func list(_ book: RulesBook) -> some View {
        List {
            switch tab {
            case .rules: CRRulesSection(rules: book.rules, learned: learned, open: { openRule = $0 },
                                        delete: delete)
            case .categories: kinds
            case .merchants: CRMerchantsSection(names: book.names ?? []) { renamingMerchant = $0 }
            case .tags: CRTagsSection(tags: book.tags ?? [], trips: Set(trips.keys),
                                      rename: { renamingTag = $0 }, remove: { removingTag = $0 })
            }
            Color.clear.frame(height: 96).listRowBackground(Color.clear).listRowSeparator(.hidden)
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .environment(\.defaultMinListHeaderHeight, 0)
        .modifier(CRTightTop())
        .refreshable { await load() }
    }

    /// CR-01: Essentials and Lifestyle, each Fixed or Variable, or hidden.
    @ViewBuilder private var kinds: some View {
        let spending = categories.filter { $0.name != "Unsorted transfers" }
        CRKindSection(title: "Essentials", items: spending.filter { $0.group == "essentials" },
                      value: kindValue, canHide: canHide, isHidden: isHidden,
                      open: { openCategory = $0 }, hide: setHidden)
        CRKindSection(title: "Lifestyle", items: spending.filter { $0.group == "lifestyle" },
                      value: kindValue, canHide: canHide, isHidden: isHidden,
                      open: { openCategory = $0 }, hide: setHidden)
    }

    /// UN-01: the one toast look; this one is only for what failed.
    @ViewBuilder private var toastView: some View {
        if let toast = toast {
            UndoToast(text: toast.text, failed: toast.failed) {
                if self.toast == toast { withAnimation { self.toast = nil } }
            }
            .padding(.bottom, 12)
        }
    }

    // MARK: Words

    private func isHidden(_ category: String) -> Bool { book?.hidden?.contains(category) == true }

    /// "Other" is where Pearl puts what it can't place, so it can't be hidden.
    private func canHide(_ category: String) -> Bool { category != "Other" }

    private func pearlKind(_ category: String) -> String { book?.pearlKinds?[category] ?? "variable" }

    /// "Variable", "Fixed" or "Hidden" at the end of a category's row.
    private func kindValue(_ category: String) -> String {
        if isHidden(category) { return "Hidden" }
        return (book?.kinds?[category] ?? pearlKind(category)) == "fixed" ? "Fixed" : "Variable"
    }

    private func transactions(_ n: Int) -> String { "\(n) transaction\(n == 1 ? "" : "s")" }

    // MARK: Calls

    private func load() async {
        do {
            let rules: RulesBook = try await app.api.get("api/rules")
            struct Learned: Decodable { let rules: [Lenient<LearnedRule>] }
            let got: Learned? = try? await app.api.get("api/pattern-sort/rules")
            learned = got?.rules.compactMap { $0.value } ?? []
            struct Trips: Decodable { let trips: [Lenient<Trip>] }
            let gotTrips: Trips? = try? await app.api.get("api/trips")
            trips = Dictionary((gotTrips?.trips.compactMap { $0.value } ?? []).map { ($0.name, $0) },
                               uniquingKeysWith: { a, _ in a })
            // Together, so a row can't open before its categories are here.
            if let list: CategoryList = try? await app.api.get("api/categories") {
                categories = list.categories
                // She may have just hidden or added one: every other screen hears.
                app.use(list)
            }
            book = rules
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Undo through POST /api/transactions/undo with what the server sent.
    private func undoCall(_ payload: JSONValue) -> () async throws -> Void {
        let api = app.api
        return {
            guard let body = payload.any as? [String: Any] else { return }
            let _: OK = try await api.post("api/transactions/undo", body)
        }
    }

    /// A sorting rule goes at once, "Rule deleted" with Undo; a pay or
    /// leave-out rule changes what's counted, so it asks first.
    private func delete(_ rule: RulesBook.Rule) {
        guard rule.isSorting else {
            removingRule = rule
            return
        }
        Task {
            do {
                let reply: RuleReply = try await app.api.delete("api/rules/\(rule.id)")
                app.say("Rule deleted", undo: reply.undo.map(undoCall))
                app.changed()
            } catch {
                fail(error)
            }
        }
    }

    /// CR-07 answers at once; Undo puts back what it was.
    private func setKind(_ category: String, _ kind: String?) {
        let was = book?.kinds?[category]
        let word = kind.map { $0 == "fixed" ? "Fixed" : "Variable" } ?? "Pearl decides"
        let api = app.api
        run("\(category) · \(word)", undo: {
            let _: OK = try await api.put("api/rules/kinds",
                                          ["category": category, "kind": was.map { $0 as Any } ?? NSNull()])
        }) {
            let _: OK = try await api.put("api/rules/kinds",
                                          ["category": category, "kind": kind.map { $0 as Any } ?? NSNull()])
        }
    }

    /// "Fitness hidden" with Undo, which shows it again.
    private func setHidden(_ category: String, _ hidden: Bool) {
        let api = app.api
        run(hidden ? "\(category) hidden" : "\(category) shown", undo: {
            let _: OK = try await api.put("api/rules/categories", ["category": category, "hidden": !hidden])
        }) {
            let _: OK = try await api.put("api/rules/categories", ["category": category, "hidden": hidden])
        }
    }

    /// Make a change, say so (with Undo when there is one), and have every page reload.
    private func run(_ done: String, undo: (() async throws -> Void)? = nil,
                     _ call: @escaping () async throws -> Void) {
        Task {
            do {
                try await call()
                app.say(done, undo: undo)
                app.changed()
            } catch {
                fail(error)
            }
        }
    }

    private func fail(_ error: Error) {
        if let text = app.handle(error) {
            withAnimation { toast = Toast(text: text, failed: true) }
        }
    }
}

/// What a rule's change or delete answers: how many moved, and its Undo.
struct RuleReply: Decodable {
    var moved: Int? = nil
    var undo: JSONValue? = nil
}

// MARK: - The header (G5b `cr_top`)

/// Back, "Categories and rules" in 34 pt Fraunces, and the four-way control.
private struct CRHeader: View {
    @Binding var tab: CategoriesRulesView.Tab
    let tags: Bool
    let back: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack { APBackButton(action: back); Spacer() }.frame(height: 52)
            ProfileHeading(title: "Categories and rules")
            CRSegmented(options: CategoriesRulesView.Tab.allCases.filter { tags || $0 != .tags }.map(\.rawValue),
                        selected: tab.rawValue) { tab = CategoriesRulesView.Tab(rawValue: $0) ?? .rules }
                .padding(.top, 6)
        }
    }
}

/// A+ `.seg`: 38 high on `chip`, the chosen one on the card with a soft shadow.
private struct CRSegmented: View {
    let options: [String]
    let selected: String
    let pick: (String) -> Void

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.self) { o in
                Button { pick(o) } label: {
                    Text(o).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity, minHeight: 32)
                        .background {
                            if o == selected {
                                Capsule().fill(Pearl.bar).shadow(color: Pearl.ink.opacity(0.12), radius: 1.5, y: 1)
                            }
                        }
                        .contentShape(Capsule())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(o == selected ? [.isButton, .isSelected] : .isButton)
            }
        }
        .padding(3)
        .frame(minHeight: 38)
        .background(Capsule().fill(APlus.chip))
    }
}

/// The grouped list's own top gap trimmed, and its sides on the page's
/// 16 pt gutter, where iOS lets us.
private struct CRTightTop: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 17.0, *) {
            content
                .contentMargins(.top, 4, for: .scrollContent)
                .contentMargins(.horizontal, Pearl.gutter, for: .scrollContent)
        } else {
            content
        }
    }
}

// MARK: - The four lists

/// CR-00: YOURS, then LEARNED WITH YOU ("You said yes").
private struct CRRulesSection: View {
    let rules: [RulesBook.Rule]
    let learned: [LearnedRule]
    let open: (RulesBook.Rule) -> Void
    let delete: (RulesBook.Rule) -> Void

    var body: some View {
        if rules.isEmpty && learned.isEmpty {
            CREmpty(symbol: "square.on.circle", title: "No rules yet",
                    line: "Change a category and pick “Do the same for every…”. The rule shows up here.")
        } else {
            if !rules.isEmpty {
                Section {
                    ForEach(Array(rules.enumerated()), id: \.element.id) { i, rule in
                        Button { open(rule) } label: {
                            CRRow(title: rule.name, sub: rule.words) { CRLead(name: rule.name, recurring: rule.kind == "recurring") }
                        }
                        .crRow(first: i == 0, last: i == rules.count - 1)
                        .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                            Button("Delete") { delete(rule) }.tint(Pearl.danger)
                        }
                    }
                } header: { CRLabel(text: "Yours") }
            }
            if !learned.isEmpty {
                Section {
                    // AI-05 (1313:4400, AI-03c): rules she said yes to, each opening AI-06.
                    ForEach(Array(learned.enumerated()), id: \.element.id) { i, rule in
                        NavigationLink { LearnedRuleView(id: rule.id) } label: {
                            CRRow(title: rule.name, sub: rule.words, pill: "You said yes") { CRLead(name: rule.name) }
                        }
                        .crRow(first: i == 0, last: i == learned.count - 1)
                    }
                } header: { CRLabel(text: "Learned with you") }
            }
        }
    }
}

private struct CRKindSection: View {
    let title: String
    let items: [CategoryList.Category]
    let value: (String) -> String
    let canHide: (String) -> Bool
    let isHidden: (String) -> Bool
    let open: (CategoryList.Category) -> Void
    let hide: (String, Bool) -> Void

    var body: some View {
        if !items.isEmpty {
            Section {
                ForEach(Array(items.enumerated()), id: \.element.id) { i, category in
                    let hidden = isHidden(category.name)
                    Button { open(category) } label: {
                        CRRow(title: category.name, value: value(category.name)) {
                            IconBubble(symbol: CategorySheet.symbol(for: category.name))
                        }
                    }
                    .crRow(first: i == 0, last: i == items.count - 1)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if canHide(category.name) {
                            Button(hidden ? "Show" : "Hide") { hide(category.name, !hidden) }
                                .tint(hidden ? Pearl.action : Pearl.muted)
                        }
                    }
                }
            } header: { CRLabel(text: title) }
        }
    }
}

/// CR-02: her names for merchants, and the bank's.
private struct CRMerchantsSection: View {
    let names: [RulesBook.MerchantName]
    let rename: (RulesBook.MerchantName) -> Void

    var body: some View {
        if names.isEmpty {
            CREmpty(symbol: "bag", title: "No merchants renamed yet",
                    line: "Give one a name you’ll recognise. It shows everywhere, and in search.")
        } else {
            Section {
                ForEach(Array(names.enumerated()), id: \.element.id) { i, merchant in
                    Button { rename(merchant) } label: {
                        CRRow(title: merchant.name, sub: "Bank: \(merchant.merchant)") { CRLead(name: merchant.name) }
                    }
                    .crRow(first: i == 0, last: i == names.count - 1)
                }
            } header: { CRLabel(text: "", gap: 12) }
        }
    }
}

/// CR-03: her tags, how many rows wear each and what they come to.
private struct CRTagsSection: View {
    let tags: [RulesBook.TagTotal]
    let trips: Set<String>
    let rename: (RulesBook.TagTotal) -> Void
    let remove: (RulesBook.TagTotal) -> Void

    /// CR-03 (REDESIGN-22): a tag's total is a total, like a trip's: plum
    /// with no minus; net money in is green with "+".
    static func total(_ spent: Double) -> String {
        spent < 0 ? "+" + Format.amount(spent) : Format.amount(spent)
    }

    var body: some View {
        if tags.isEmpty {
            CREmpty(symbol: "tag", title: "No tags yet", line: "Tag a transaction, or several at once, from Cash flow.")
        } else {
            Section {
                ForEach(Array(tags.enumerated()), id: \.element.id) { i, tag in
                    Button { rename(tag) } label: {
                        CRRow(title: tag.tag, sub: line(tag), amount: Self.total(tag.spent),
                              amountTone: tag.spent < 0 ? Pearl.moneyIn : Pearl.moneyOut) { CRLead(name: tag.tag) }
                    }
                    .crRow(first: i == 0, last: i == tags.count - 1)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button("Remove") { remove(tag) }.tint(Pearl.danger)
                        Button("Rename") { rename(tag) }.tint(Pearl.muted)
                    }
                }
            } header: { CRLabel(text: "", gap: 12) }
        }
    }

    /// "12 transactions", "9 transactions · a trip".
    private func line(_ tag: RulesBook.TagTotal) -> String {
        "\(tag.count) transaction\(tag.count == 1 ? "" : "s")" + (trips.contains(tag.tag) ? " · a trip" : "")
    }
}

// MARK: - Rows

/// A+ caps label over a list section (24 above, 8 below); empty is just the gap.
private struct CRLabel: View {
    let text: String
    var gap: CGFloat = 20

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
            .textCase(nil)
            .padding(.leading, 4).padding(.top, gap).padding(.bottom, 0)
            .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 8, trailing: 0))
            .accessibilityAddTraits(.isHeader)
    }
}

/// What leads a row: the 40 pt face, or ⇄ for a recurring transfer's rule.
private struct CRLead: View {
    let name: String
    var recurring = false

    var body: some View {
        if recurring {
            IconBubble(symbol: "arrow.triangle.2.circlepath", size: 40)
        } else {
            RowAvatar(name: CRLead.letters(name))
        }
    }

    /// A transfer is known by who it went to: "e-Transfer to M. Papas" is "M. Papas".
    static func letters(_ name: String) -> String {
        var text = name
        for prefix in ["e-transfer to ", "transfers to "] where text.lowercased().hasPrefix(prefix) {
            text = String(text.dropFirst(prefix.count))
        }
        return text
    }
}

/// A+ `.row` in a list: what leads it, a name over a line, a pill, an amount
/// or a value, and the chevron. 64 high.
private struct CRRow<Leading: View>: View {
    let title: String
    var sub: String? = nil
    var pill: String? = nil
    var amount: String? = nil
    /// The amount's colour: ink, or a tag's total (plum, green when net in).
    var amountTone: Color = Pearl.ink
    var value: String? = nil
    @ViewBuilder var leading: () -> Leading

    var body: some View {
        HStack(spacing: 12) {
            leading()
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(2)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(2)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let pill = pill { StatusPill(text: pill, tone: .anchor, small: true) }
            if let amount = amount {
                Text(amount).font(Nacre.headline).monospacedDigit().foregroundColor(amountTone)
                    .pearlAmountFit().fixedSize()
            }
            if let value = value {
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1).fixedSize()
            }
            APChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// `.state` inside the list: an icon, the title and its line.
private struct CREmpty: View {
    let symbol: String
    let title: String
    let line: String

    var body: some View {
        APEmptyState(title: title, line: line, top: 90) { IconBubble(symbol: symbol) }
            .listRowInsets(EdgeInsets())
            .listRowBackground(Color.clear)
            .listRowSeparator(.hidden)
    }
}

/// A row of the list drawn as part of one A+ card (`card` with its 1 pt
/// `card-line`, radius 24): only the card's real ends are rounded.
private struct CRRowBackground: View {
    let first: Bool
    let last: Bool

    var body: some View {
        GeometryReader { geo in
            let reach: CGFloat = 48
            let shape = RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous)
            shape.fill(APlus.card)
                .background(.ultraThinMaterial, in: shape)
                .overlay(shape.strokeBorder(APlus.cardLine, lineWidth: 1))
                .frame(width: geo.size.width,
                       height: geo.size.height + (first ? 0 : reach) + (last ? 0 : reach))
                .offset(y: first ? 0 : -reach)
        }
        .clipped()
    }
}

private extension View {
    func crRow(first: Bool, last: Bool) -> some View {
        buttonStyle(.plain)
            .listRowInsets(EdgeInsets())
            .listRowBackground(CRRowBackground(first: first, last: last))
            .listRowSeparatorTint(APlus.separator)
            .alignmentGuide(.listRowSeparatorLeading) { _ in 68 }
            .listRowSeparator(last ? .hidden : .visible, edges: .bottom)
    }
}

// MARK: - CR-04 A sorting rule (G5b-Rule)

/// The rule's page: its face and "Always Groceries", Spending / Not
/// spending, and its category as chips. Save is greyed until it changes;
/// then "Also moves the 14 earlier ones." with Save (moves them too) and
/// "Only new ones" (A+, approved 2026-11-18). "Delete this rule" is the
/// one red row.
@MainActor
struct RuleEditView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let rule: RulesBook.Rule
    let categories: [CategoryList.Category]
    let hidden: Set<String>
    /// The toast's words and its Undo payload.
    let onSaved: (String, JSONValue?) -> Void
    let onDelete: () -> Void

    @State private var picked: String?
    @State private var spending = true
    @State private var earlier: Int?
    @State private var busy = false
    @State private var error: String?

    private var current: String { rule.category ?? "Other" }
    private var chosen: String { picked ?? current }
    private var changed: Bool { picked != nil && picked != current }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack { APBackButton { dismiss() }; Spacer() }.frame(height: 52)
                APHero(face: CRLead.letters(rule.name), name: rule.name, lines: ["Always \(chosen)"])
                CRSegmented(options: ["Spending", "Not spending"], selected: spending ? "Spending" : "Not spending") {
                    spending = $0 == "Spending"
                }
                .padding(.top, 8)
                RuleChips(groups: groups, chosen: chosen) { pick($0) }
                if !changed {
                    APCard {
                        Button(action: onDelete) {
                            ProfileRow(symbol: "trash", title: "Delete this rule", tone: Pearl.danger, chevron: false)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.top, 16)
                }
                if let error = error { APErrorLine(text: error).padding(.top, 8) }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .safeAreaInset(edge: .bottom, spacing: 0) { actions }
        .nacreScreen()
        .navigationBarHidden(true)
        .onAppear { spending = !Self.notSpending(current) }
    }

    @ViewBuilder private var actions: some View {
        VStack(spacing: 12) {
            if changed, let n = earlier, n > 0 {
                Text(n == 1 ? "Also moves the earlier one." : "Also moves the \(n) earlier ones.")
                    .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(ProfileTone.bannerFill))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
            }
            Button("Save") { Task { await save(earlier: true) } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(!changed || busy || (changed && earlier == nil))
                .accessibilityIdentifier("rule-save")
            if changed, let n = earlier, n > 0 {
                APQuietButton(title: "Only new ones") { Task { await save(earlier: false) } }
                    .disabled(busy)
            }
        }
        .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 4)
    }

    /// Spending: Essentials and Lifestyle. Not spending: savings and transfers.
    private var groups: [(String, [String])] {
        let usable = categories.filter { !hidden.contains($0.name) || $0.name == current }
        if spending {
            return [("Essentials", usable.filter { $0.group == "essentials" }.map(\.name)),
                    ("Lifestyle", usable.filter { $0.group == "lifestyle" }.map(\.name))]
        }
        return [("Not spending", usable.filter { Self.notSpending($0.name, group: $0.group) }.map(\.name))]
    }

    static func notSpending(_ name: String, group: String? = nil) -> Bool {
        if name == "Unsorted transfers" || name == "Income" { return false }
        if let group = group { return group == "savings" || group == "transfer" }
        return ["Saved", "Transfers", "Lent", "Borrowed"].contains(name)
    }

    private func pick(_ category: String) {
        picked = category == current ? nil : category
        earlier = nil
        error = nil
        guard category != current else { return }
        Task {
            struct Count: Decodable { let count: Int }
            let got: Count? = try? await app.api.get("api/rules/earlier", query: ["id": rule.id, "category": category])
            if picked == category { earlier = got?.count ?? 0 }
        }
    }

    private func save(earlier move: Bool) async {
        guard let category = picked else { return }
        busy = true
        defer { busy = false }
        do {
            let id = rule.id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? rule.id
            let reply: RuleReply = try await app.api.put("api/rules/\(id)", ["category": category, "earlier": move])
            let n = reply.moved ?? 0
            onSaved(n > 0 ? "Now \(category) · \(n) moved" : "Now \(category)", reply.undo)
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// G5b `chips` on a card under each group's label; the chosen one is rose.
private struct RuleChips: View {
    let groups: [(String, [String])]
    let chosen: String
    let pick: (String) -> Void

    var body: some View {
        ForEach(groups, id: \.0) { title, names in
            if !names.isEmpty {
                ProfileSection(title)
                APCard {
                    FlowLayout(spacing: 8) {
                        ForEach(names, id: \.self) { name in
                            CRChip(title: name, on: name == chosen) { pick(name) }
                        }
                    }
                    .padding(.horizontal, 16).padding(.vertical, 14)
                }
            }
        }
    }
}

/// A+ `.chip`: 34 high on `chip`; on, `action` with `on-action` words.
private struct CRChip: View {
    let title: String
    let on: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title).font(Nacre.subheadline)
                .foregroundColor(on ? Pearl.onAction : Pearl.ink)
                .padding(.horizontal, 14).frame(height: 34)
                .background(Capsule().fill(on ? Pearl.action : APlus.chip))
                .padding(.vertical, 5)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
    }
}

// MARK: - CR-05 A pay or leave-out rule

/// "Gusto · Always your pay": what it does, and "Remove this rule" (red,
/// the entry row), which asks on a Pearl sheet.
private struct RuleInfoPage: View {
    let rule: RulesBook.Rule
    let onRemove: () -> Void

    var body: some View {
        ProfilePage {
            APHero(face: CRLead.letters(rule.name), name: rule.name, lines: [rule.words])
            APCard {
                Text(rule.does).font(Nacre.body).lineSpacing(2).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.horizontal, 16).padding(.vertical, 14)
            }
            .padding(.top, 10)
            APCard {
                Button(action: onRemove) {
                    ProfileRow(symbol: "trash", title: "Remove this rule", tone: Pearl.danger, chevron: false)
                }
                .buttonStyle(.plain)
            }
            .padding(.top, 16)
        }
    }
}

// MARK: - CR-07, CR-08 A category

/// Groceries: Fixed or Variable, answered at once, and Hide from pickers.
/// Hidden: one line, and Show in pickers.
private struct CategoryKindPage: View {
    let category: CategoryList.Category
    /// What she set: "fixed", "variable", or nil when Pearl decides.
    let kind: String?
    let pearl: String
    let hidden: Bool
    let canHide: Bool
    let onKind: (String?) -> Void
    let onHide: (Bool) -> Void

    var body: some View {
        ProfilePage {
            APHero(face: "", name: category.name, symbol: CategorySheet.symbol(for: category.name))
            if hidden {
                APCard {
                    Text("Hidden from pickers. It stays on anything already in it.")
                        .font(Nacre.body).lineSpacing(2).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 14)
                }
                .padding(.top, 10)
                Button("Show in pickers") { onHide(false) }
                    .buttonStyle(APPrimaryButtonStyle())
                    .padding(.top, 10)
            } else {
                ProfileSection("Fixed or Variable")
                APCard {
                    APChoiceRow(title: "Pearl decides", sub: "\(pearl == "fixed" ? "Fixed" : "Variable") for now",
                                selected: kind == nil) { if kind != nil { onKind(nil) } }
                    APSeparator(afterFace: false)
                    APChoiceRow(title: "Always Fixed", sub: "Bills that come regularly",
                                selected: kind == "fixed") { if kind != "fixed" { onKind("fixed") } }
                    APSeparator(afterFace: false)
                    APChoiceRow(title: "Always Variable", selected: kind == "variable") {
                        if kind != "variable" { onKind("variable") }
                    }
                }
                if canHide {
                    APCard {
                        Button { onHide(true) } label: {
                            ProfileRow(symbol: "eye.slash", title: "Hide from pickers", chevron: false)
                        }
                        .buttonStyle(.plain)
                    }
                    .padding(.top, 16)
                }
            }
        }
    }
}

// MARK: - CR-09, CR-10 Rename

/// A new name for a merchant or a tag (G5b-Merchants, G5b-Tags): the
/// centred title with ✕, the "Call it" well in focus, its line, and the other
/// thing she can do with it; Save greyed until the name changes.
struct RenameSheet: View {
    @Environment(\.dismiss) private var dismiss
    let title: String
    let label: String
    let hint: String
    let other: String
    let onSave: (String) -> Void
    let onOther: () -> Void
    private let initial: String

    @State private var name: String
    @FocusState private var focused: Bool

    init(title: String, label: String, initial: String, hint: String, other: String,
         onSave: @escaping (String) -> Void, onOther: @escaping () -> Void) {
        self.title = title
        self.label = label
        self.initial = initial
        self.hint = hint
        self.other = other
        self.onSave = onSave
        self.onOther = onOther
        _name = State(initialValue: initial)
    }

    private var cleaned: String { name.trimmingCharacters(in: .whitespacesAndNewlines) }
    private var canSave: Bool { !cleaned.isEmpty && cleaned != initial }

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            APSheetTitle(title: title) { dismiss() }
                .padding(.top, 14)
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4).padding(.top, 10)
            TextField("", text: $name)
                .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                .submitLabel(.done)
                .focused($focused)
                .onSubmit { if canSave { onSave(cleaned) } }
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .wellStyle(focused: focused)
                .accessibilityLabel(label)
            Text(hint).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4).padding(.top, 2)
                .fixedSize(horizontal: false, vertical: true)
            APQuietButton(title: other, action: onOther)
                .frame(maxWidth: .infinity)
                .padding(.top, 6)
            Spacer(minLength: 16)
            Button("Save") { onSave(cleaned) }
                .buttonStyle(APPrimaryButtonStyle())
                .disabled(!canSave)
                .padding(.bottom, 8)
        }
        .padding(.horizontal, 16)
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onAppear { focused = true }
    }
}
