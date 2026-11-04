import SwiftUI

/// Profile › Categories and rules (CR-00 to CR-03; THL-123, THL-225, THL-226,
/// THL-234): her saved rules, Fixed or Variable for each category, her names
/// for merchants, and her tags. The same calls as the web's RulesPanel.
///
/// The design draws the four lists and says what a swipe does. What opens from
/// a row isn't drawn, so those sheets are built from the same parts and carry
/// the web's words.
@MainActor
struct CategoriesRulesView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    private enum Tab: String, CaseIterable, Identifiable {
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
    @State private var categories: [CategoryList.Category] = []
    @State private var error: String?
    @State private var toast: Toast?

    @State private var editing: RulesBook.Rule?
    @State private var explaining: RulesBook.Rule?
    @State private var removingRule: RulesBook.Rule?
    @State private var choosing: CategoryList.Category?
    @State private var renamingMerchant: RulesBook.MerchantName?
    @State private var renamingTag: RulesBook.TagTotal?
    @State private var removingTag: RulesBook.TagTotal?
    @State private var removingTagNext: RulesBook.TagTotal?

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            header.padding(.horizontal, Pearl.gutter)
            if let book = book {
                list(book)
            } else {
                LoadState(error: error) { Task { await load() } }
                Spacer(minLength: 0)
            }
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                }
                .accessibilityLabel("Back")
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .overlay(alignment: .bottom) { toastView }
        .task(id: app.version) { await load() }
        .sheet(item: $editing) { rule in
            CategorySheet(name: rule.name, amount: rule.words, tone: Pearl.muted, categories: categories,
                          current: rule.category ?? "Other", title: "Rule",
                          onDelete: {
                              editing = nil
                              delete(rule)
                          }, onSave: { category, _ in
                              editing = nil
                              run("\(rule.name) is always \(category) now.") {
                                  let _: OK = try await app.api.put("api/rules/\(rule.id)", ["category": category])
                              }
                          })
        }
        .sheet(item: $explaining) { rule in
            // The sheet has already said what removing it does.
            RuleInfoSheet(rule: rule) {
                explaining = nil
                remove(rule)
            }
        }
        .sheet(item: $choosing) { category in
            CategoryKindSheet(category: category, kind: book?.kinds?[category.name],
                              pearl: pearlKind(category.name),
                              hidden: isHidden(category.name), canHide: canHide(category.name),
                              onKind: { kind in
                                  choosing = nil
                                  setKind(category.name, kind)
                              }, onHide: { hide in
                                  choosing = nil
                                  setHidden(category.name, hide)
                              })
        }
        .sheet(item: $renamingMerchant) { merchant in
            RenameSheet(title: "Rename merchant", label: "Call it", initial: merchant.name,
                        hint: "Bank: \(merchant.merchant)", other: "Use the bank’s name",
                        onSave: { name in
                            renamingMerchant = nil
                            run("\(merchant.merchant) is \(name) now.") {
                                let _: OK = try await app.api.put("api/merchants/name",
                                                                  ["merchant": merchant.merchant, "name": name])
                            }
                        }, onOther: {
                            renamingMerchant = nil
                            run("\(merchant.merchant) uses the bank’s name again.") {
                                let _: OK = try await app.api.delete("api/rules/name:\(merchant.key)")
                            }
                        })
        }
        // Asked once the sheet has gone: a dialog raised while one is closing
        // doesn't appear.
        .sheet(item: $renamingTag, onDismiss: {
            removingTag = removingTagNext
            removingTagNext = nil
        }) { tag in
            RenameSheet(title: "Rename tag", label: "Call it", initial: tag.tag, hint: transactions(tag.count),
                        other: "Remove this tag",
                        onSave: { name in
                            renamingTag = nil
                            run("\(tag.tag) is \(name) now.") {
                                let _: OK = try await app.api.put("api/tags/\(tag.tag)", ["name": name])
                            }
                        }, onOther: {
                            removingTagNext = tag
                            renamingTag = nil
                        })
        }
        .confirmationDialog(removingRule.map { "Remove the rule for \($0.name)?" } ?? "",
                            isPresented: present($removingRule), titleVisibility: .visible,
                            presenting: removingRule) { rule in
            Button("Remove this rule", role: .destructive) { remove(rule) }
        } message: { rule in
            Text(rule.removing)
        }
        .confirmationDialog(removingTag.map { "Take \($0.tag) off \(transactions($0.count))?" } ?? "",
                            isPresented: present($removingTag), titleVisibility: .visible,
                            presenting: removingTag) { tag in
            Button("Remove this tag", role: .destructive) {
                run("\(tag.tag) removed.") {
                    let _: OK = try await app.api.put("api/tags/\(tag.tag)", ["name": NSNull()])
                }
            }
        }
    }

    private func present<T>(_ item: Binding<T?>) -> Binding<Bool> {
        Binding(get: { item.wrappedValue != nil }, set: { if !$0 { item.wrappedValue = nil } })
    }

    // MARK: Parts

    private var header: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("Categories and rules").font(Nacre.title).tracking(0.4).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            Chips {
                ForEach(Tab.allCases) { t in
                    FilterChip(label: t.rawValue, on: tab == t, solid: true) { tab = t }
                }
            }
            .padding(.horizontal, -2)
        }
    }

    private func list(_ book: RulesBook) -> some View {
        List {
            switch tab {
            case .rules: rules(book.rules)
            case .categories: kinds
            case .merchants: merchants(book.names ?? [])
            case .tags: tags(book.tags ?? [])
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .environment(\.defaultMinListHeaderHeight, 0)
        .modifier(TightTop())
        .refreshable { await load() }
    }

    /// The grouped list's own top gap trimmed, and its sides on the page's
    /// 16pt gutter, where iOS lets us.
    private struct TightTop: ViewModifier {
        func body(content: Content) -> some View {
            if #available(iOS 17.0, *) {
                content
                    .contentMargins(.top, 0, for: .scrollContent)
                    .contentMargins(.horizontal, Pearl.gutter, for: .scrollContent)
            } else {
                content
            }
        }
    }

    /// CR-00: every rule she saved.
    @ViewBuilder private func rules(_ rules: [RulesBook.Rule]) -> some View {
        if rules.isEmpty {
            empty("No saved rules yet",
                  "Change a transaction’s category and choose “Do the same for every…”, and the rule shows up here.")
        } else {
            Section {
                ForEach(Array(rules.enumerated()), id: \.element.id) { i, rule in
                    Button { open(rule) } label: {
                        CardRow(title: rule.name, sub: rule.words) {
                            if rule.kind == "recurring" {
                                TintedIcon(symbol: "arrow.triangle.2.circlepath")
                            } else {
                                RingInitials(name: rule.name)
                            }
                        }
                    }
                    .cardRow(first: i == 0, last: i == rules.count - 1)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button("Delete") { delete(rule) }.tint(Pearl.moneyOut)
                    }
                }
            } footer: {
                CardNote("Swipe left on a rule to delete it.")
            }
        }
    }

    /// CR-01: Essentials and Lifestyle, each Fixed or Variable, or hidden.
    @ViewBuilder private var kinds: some View {
        let spending = categories.filter { $0.name != "Unsorted transfers" }
        let essentials = spending.filter { $0.group == "essentials" }
        let lifestyle = spending.filter { $0.group == "lifestyle" }
        kindSection("Essentials", essentials, note: lifestyle.isEmpty)
        kindSection("Lifestyle", lifestyle, note: true)
    }

    @ViewBuilder private func kindSection(_ title: String, _ items: [CategoryList.Category],
                                          note: Bool) -> some View {
        if !items.isEmpty {
            Section {
                ForEach(Array(items.enumerated()), id: \.element.id) { i, category in
                    let hidden = isHidden(category.name)
                    Button { choosing = category } label: {
                        CardRow(title: category.name, pill: hidden ? "Hidden" : nil,
                                value: hidden ? nil : kindWord(category.name)) {
                            TintedIcon(symbol: CategorySheet.symbol(for: category.name))
                        }
                    }
                    .cardRow(first: i == 0, last: i == items.count - 1)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if canHide(category.name) {
                            Button(hidden ? "Show" : "Hide") { setHidden(category.name, !hidden) }
                                .tint(hidden ? Pearl.action : Pearl.muted)
                        }
                    }
                }
            } header: {
                Text(title.uppercased()).font(Nacre.caption1).foregroundColor(Pearl.ink)
                    .textCase(nil)
                    .accessibilityAddTraits(.isHeader)
            } footer: {
                if note { CardNote("Swipe left on a category to hide it.") }
            }
        }
    }

    /// CR-02: her names for merchants, and the bank's.
    @ViewBuilder private func merchants(_ names: [RulesBook.MerchantName]) -> some View {
        if names.isEmpty {
            empty("No merchants renamed yet", "Give a merchant a name you’ll recognise. It shows everywhere and in search.")
        } else {
            Section {
                ForEach(Array(names.enumerated()), id: \.element.id) { i, merchant in
                    Button { renamingMerchant = merchant } label: {
                        CardRow(title: merchant.name, sub: "Bank: \(merchant.merchant)") {
                            RingInitials(name: merchant.name)
                        }
                    }
                    .cardRow(first: i == 0, last: i == names.count - 1)
                }
            } footer: {
                CardNote("Tap a merchant to rename it.")
            }
        }
    }

    /// CR-03: her tags, how many rows wear each and what they come to.
    @ViewBuilder private func tags(_ tags: [RulesBook.TagTotal]) -> some View {
        if tags.isEmpty {
            empty("No tags yet", "Tag a transaction, or several at once, from Cash flow.")
        } else {
            Section {
                ForEach(Array(tags.enumerated()), id: \.element.id) { i, tag in
                    Button { renamingTag = tag } label: {
                        CardRow(title: tag.tag, sub: transactions(tag.count), amount: Format.amount(tag.spent)) {
                            TintedIcon(symbol: "tag")
                        }
                    }
                    .cardRow(first: i == 0, last: i == tags.count - 1)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        Button("Remove") { removingTag = tag }.tint(Pearl.moneyOut)
                        Button("Rename") { renamingTag = tag }.tint(Pearl.muted)
                    }
                }
            } footer: {
                CardNote("Swipe left on a tag to rename or remove it.")
            }
        }
    }

    private func empty(_ title: String, _ line: String) -> some View {
        VStack(alignment: .leading, spacing: 4) {
            Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
            Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .accessibilityElement(children: .combine)
        .listRowInsets(EdgeInsets())
        .listRowBackground(CardRowBackground(first: true, last: true))
        .listRowSeparator(.hidden)
    }

    @ViewBuilder private var toastView: some View {
        if let toast = toast {
            HStack(spacing: 12) {
                Image(systemName: toast.failed ? "exclamationmark.circle" : "checkmark")
                    .font(.system(size: 13, weight: .bold))
                    .foregroundColor(toast.failed ? Pearl.caution : Nacre.teal)
                Text(toast.text).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .background(Capsule().fill(.ultraThinMaterial))
            .background(Capsule().fill(Nacre.glass))
            .overlay(Capsule().strokeBorder(Nacre.edge, lineWidth: 1))
            .padding(.horizontal, 16).padding(.bottom, 12)
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .task(id: toast) {
                try? await Task.sleep(nanoseconds: 6_000_000_000)
                if self.toast == toast { withAnimation { self.toast = nil } }
            }
        }
    }

    // MARK: Words

    private func isHidden(_ category: String) -> Bool { book?.hidden?.contains(category) == true }

    /// "Other" is where Pearl puts what it can't place, so it can't be hidden.
    private func canHide(_ category: String) -> Bool { category != "Other" }

    private func pearlKind(_ category: String) -> String { book?.pearlKinds?[category] ?? "variable" }

    private func kindWord(_ category: String) -> String {
        (book?.kinds?[category] ?? pearlKind(category)) == "fixed" ? "Fixed" : "Variable"
    }

    private func transactions(_ n: Int) -> String { "\(n) transaction\(n == 1 ? "" : "s")" }

    // MARK: Calls

    private func load() async {
        do {
            let rules: RulesBook = try await app.api.get("api/rules")
            // Together, so a row can't open before its categories are here.
            if let list: CategoryList = try? await app.api.get("api/categories") {
                categories = list.categories
            }
            book = rules
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// A sorting rule opens its categories; pay and leave-out rules only say
    /// what they do, since the server won't change what they file things under.
    private func open(_ rule: RulesBook.Rule) {
        if rule.isSorting { editing = rule } else { explaining = rule }
    }

    /// Removing pay or leave-out rule changes what's counted, so it asks first.
    private func delete(_ rule: RulesBook.Rule) {
        if rule.isSorting { remove(rule) } else { removingRule = rule }
    }

    private func remove(_ rule: RulesBook.Rule) {
        run("Rule deleted.") {
            let _: OK = try await app.api.delete("api/rules/\(rule.id)")
        }
    }

    private func setKind(_ category: String, _ kind: String?) {
        let done = kind.map { "\(category) is always \($0 == "fixed" ? "Fixed" : "Variable") now." }
            ?? "Pearl decides \(category) again."
        run(done) {
            let _: OK = try await app.api.put("api/rules/kinds",
                                              ["category": category, "kind": kind.map { $0 as Any } ?? NSNull()])
        }
    }

    private func setHidden(_ category: String, _ hidden: Bool) {
        run(hidden ? "\(category) is out of the pickers." : "\(category) is back.") {
            let _: OK = try await app.api.put("api/rules/categories", ["category": category, "hidden": hidden])
        }
    }

    /// Make a change, say so, and have every page reload.
    private func run(_ done: String, _ call: @escaping () async throws -> Void) {
        Task {
            do {
                try await call()
                withAnimation { toast = Toast(text: done) }
                app.changed()
            } catch {
                if let text = app.handle(error) {
                    withAnimation { toast = Toast(text: text, failed: true) }
                }
            }
        }
    }
}

// MARK: - Rows

/// One row of a card: what leads it, a name, a line or a pill under it, and an
/// amount or a word at the end.
private struct CardRow<Leading: View>: View {
    let title: String
    var sub: String? = nil
    var pill: String? = nil
    var amount: String? = nil
    var value: String? = nil
    @ViewBuilder var leading: () -> Leading

    var body: some View {
        HStack(spacing: 12) {
            leading()
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let pill = pill { StatusPill(text: pill, tone: .neutral) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let amount = amount {
                Text(amount).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            }
            if let value = value {
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                .foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

/// A row of the list drawn as part of one glass card, whose ends are rounded
/// and whose nacre edge runs unbroken from row to row. (A List is what gives a
/// row its swipe, and it can only draw a background per row.)
private struct CardRowBackground: View {
    let first: Bool
    let last: Bool

    var body: some View {
        GeometryReader { geo in
            // Past the row's own edge on the sides that join another row, so
            // only the card's real ends show their corners.
            let reach: CGFloat = 44
            RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(Nacre.glass)
                .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous)
                    .strokeBorder(Nacre.horizontal, lineWidth: 1.2))
                .frame(width: geo.size.width,
                       height: geo.size.height + (first ? 0 : reach) + (last ? 0 : reach))
                .offset(y: first ? 0 : -reach)
        }
        .clipped()
    }
}

private extension View {
    func cardRow(first: Bool, last: Bool) -> some View {
        buttonStyle(.plain)
            .listRowInsets(EdgeInsets())
            .listRowBackground(CardRowBackground(first: first, last: last))
            .listRowSeparatorTint(Nacre.separator)
            .alignmentGuide(.listRowSeparatorLeading) { _ in 16 }
            // Stops at the nacre edge rather than crossing it.
            .alignmentGuide(.listRowSeparatorTrailing) { $0.width - 1.2 }
            .listRowSeparator(last ? .hidden : .visible, edges: .bottom)
    }
}

/// "LO" in a frosted disc with a nacre ring.
private struct RingInitials: View {
    let name: String

    var body: some View {
        Text(Self.letters(name))
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .frame(width: 36, height: 36)
            .background(Circle().fill(Nacre.glass))
            .overlay(Circle().strokeBorder(Nacre.horizontal, lineWidth: 1.5))
            .accessibilityHidden(true)
    }

    /// Two words give "NL", one gives its first two letters, "LO". A transfer
    /// is known by who it went to: "e-Transfer to M. Papas" is "MP".
    static func letters(_ name: String) -> String {
        var text = name
        for prefix in ["e-transfer to ", "transfers to "] where text.lowercased().hasPrefix(prefix) {
            text = String(text.dropFirst(prefix.count))
        }
        let words = text.split { !$0.isLetter && !$0.isNumber }
        let out = words.count > 1 ? words.prefix(2).compactMap { $0.first.map(String.init) }.joined()
            : String(words.first?.prefix(2) ?? "")
        return out.isEmpty ? "·" : out.uppercased()
    }
}

/// A category's or a tag's line icon, rose on a faint rose disc.
private struct TintedIcon: View {
    let symbol: String

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 15))
            .foregroundColor(Pearl.action)
            .frame(width: 34, height: 34)
            .background(Circle().fill(Self.disc))
            .accessibilityHidden(true)
    }

    private static let disc = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 1, green: 143 / 255, blue: 177 / 255, alpha: 0.22)
        : UIColor(red: 178 / 255, green: 39 / 255, blue: 87 / 255, alpha: 0.1) })
}

/// The short line under a card, inset to the card's text.
private struct CardNote: View {
    let text: String

    init(_ text: String) { self.text = text }

    var body: some View {
        Text(text).font(Nacre.footnote).foregroundColor(Pearl.ink)
            .textCase(nil)
            .fixedSize(horizontal: false, vertical: true)
    }
}

// MARK: - What opens from a row

/// A rule that doesn't file things under a category: her regular pay, or
/// "leave out every transaction like this". What it does, and removing it.
private struct RuleInfoSheet: View {
    @Environment(\.dismiss) private var dismiss
    let rule: RulesBook.Rule
    let onRemove: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            SheetTitle(title: "Rule") { dismiss() }
            VStack(alignment: .leading, spacing: 8) {
                Text(rule.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                Text(rule.does).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(rule.removing).font(Nacre.body).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 16)
            Button("Remove this rule", action: onRemove)
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }
}

/// Pearl decides, Always Fixed or Always Variable, and Hide or Show.
private struct CategoryKindSheet: View {
    @Environment(\.dismiss) private var dismiss
    let category: CategoryList.Category
    /// What she set: "fixed", "variable", or nil when Pearl decides.
    let kind: String?
    /// What Pearl would say, for "Pearl decides · Variable".
    let pearl: String
    let hidden: Bool
    let canHide: Bool
    let onKind: (String?) -> Void
    let onHide: (Bool) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            SheetTitle(title: category.name) { dismiss() }
            if hidden {
                ProfileNote("\(category.name) is hidden, so it doesn’t show in pickers. It stays on anything already in it.")
                Spacer(minLength: 16)
                Button("Show in pickers") { onHide(false) }
                    .buttonStyle(NacreButtonStyle())
                    .padding(.horizontal, 16).padding(.bottom, 8)
            } else {
                GlassCard {
                    choice("Pearl decides · \(pearl == "fixed" ? "Fixed" : "Variable")", nil)
                    RowSeparator()
                    choice("Always Fixed", "fixed")
                    RowSeparator()
                    choice("Always Variable", "variable")
                }
                .padding(.horizontal, 16)
                ProfileNote("Fixed is for bills that come regularly. Everything else is Variable.")
                Spacer(minLength: 16)
                if canHide {
                    Button("Hide from pickers") { onHide(true) }
                        .buttonStyle(NacreTextButtonStyle())
                        .padding(.horizontal, 16).padding(.bottom, 8)
                }
            }
        }
        .background(SheetBackground())
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
    }

    private func choice(_ label: String, _ value: String?) -> some View {
        let on = kind == value
        return Button { if !on { onKind(value) } else { dismiss() } } label: {
            HStack {
                Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                if on {
                    Image(systemName: "checkmark").font(.system(size: 14, weight: .semibold))
                        .foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16)
            .frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// A new name for a merchant or a tag, and the other thing she can do with it.
private struct RenameSheet: View {
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
            SheetTitle(title: title) { dismiss() }
            VStack(alignment: .leading, spacing: 6) {
                Text(label).font(Nacre.footnote).foregroundColor(Pearl.ink)
                TextField("", text: $name)
                    .font(Nacre.body).foregroundColor(Pearl.ink)
                    .submitLabel(.done)
                    .focused($focused)
                    .onSubmit { if canSave { onSave(cleaned) } }
                    .padding(.horizontal, 16)
                    .frame(height: 52)
                    .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
                    .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous)
                        .strokeBorder(focused ? Pearl.action : Nacre.edge, lineWidth: focused ? 1.5 : 1))
                    .accessibilityLabel(label)
                Text(hint).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 16)
            BottomActions {
                Button("Save") { onSave(cleaned) }
                    .buttonStyle(NacreButtonStyle())
                    .disabled(!canSave)
            } secondary: {
                Button(other, action: onOther)
                    .buttonStyle(NacreTextButtonStyle())
            }
        }
        .background(SheetBackground())
        .presentationDetents([.medium])
        .presentationDragIndicator(.visible)
        .onAppear { focused = true }
    }
}
