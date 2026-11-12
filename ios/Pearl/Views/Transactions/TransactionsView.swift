import SwiftUI

/// Cash flow (THL-122, T-01): the month's transactions under Spent, Came in
/// and Leftover, with search (T-45), Filters (T-17), By category (T-18) and
/// each category's page (T-46), Choose a month
/// (T-47), the bank's state: syncing, failed, disconnected (T-36, T-58, T-59),
/// Select (T-19): a category, a tag or Not counted for several at once
/// (T-51, T-20), with one Undo; and Add a transaction by hand (T-23).
@MainActor
struct TransactionsView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()

    @State private var months: [String] = []
    @State private var month: String?
    /// The whole month (or what a server-side filter keeps), newest first.
    @State private var rows: [Transaction] = []
    @State private var monthTotals: TransactionList.Totals?
    @State private var owed: Set<String> = []
    /// "Sam and Dad · 2 · $106.06", over By category.
    @State private var owedLine: OwedLine?
    @State private var tags: [String] = []
    private var categories: [CategoryList.Category] { app.categories }
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var reviewCount = 0
    @State private var loadedOnce = false
    @State private var error: String?

    @State private var query = ""
    @FocusState private var searching: Bool
    /// What the search found across every month; nil while not searching.
    @State private var results: [Transaction]?

    @State private var filters = TxFilters()
    /// T-67: Spent or Came in tapped, to see just those.
    @State private var counts: String?
    @State private var showFilters = false
    @State private var showMonths = false

    @State private var sync: SyncState = .idle
    @State private var syncedOnce = false
    @State private var reconnecting: String?
    /// Transactions or Calendar (T-49).
    @State private var showCalendar = false

    /// T-19: picking rows to change together, and the sheet for what to change.
    @State private var selecting = false
    @State private var picked: Set<String> = []
    @State private var bulk: Bulk?
    /// T-77's Leave out: why, so she can tell later.
    @State private var leavingOut = false
    @State private var leaveReason = ""
    @State private var busy = false
    @State private var toast: Toast?
    /// T-23: adding one by hand.
    @State private var adding = false

    enum Bulk: String, Identifiable {
        case category, tag, mark
        var id: String { rawValue }
    }

    struct Toast: Equatable {
        let title: String
        let undo: JSONValue?
    }

    enum SyncState { case idle, syncing, failed }

    struct OwedLine: Equatable {
        let names: [String]
        let count: Int
        let total: Double
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("Cash flow").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.top, 24)
                if noTransactionsYet {
                    emptyLedger
                } else {
                    searchRow.padding(.top, 20)
                    // T-02, T-45: the tabs and the summary stay while searching.
                    tabs.padding(.top, 14)
                    if filtersOn && !showCalendar && !inSearch { activeChips.padding(.top, 12) }
                    summaryCard.padding(.top, 16)
                    if !inSearch { bankState }
                    if showCalendar && !inSearch {
                        CalendarCard(month: month ?? Format.thisMonth(), categories: categories) { m in
                            month = m
                            Task { await reload() }
                        }
                        .padding(.top, 16)
                    } else if byCategory && loadedOnce && !shown.isEmpty {
                        categoryList.padding(.top, 8)
                    } else {
                        listHeader.padding(.top, 24)
                        list.padding(.top, 10)
                        if !inSearch && !selecting && loadedOnce {
                            Button("Add a transaction") { adding = true }
                                .font(Nacre.textButton).foregroundColor(Pearl.link)
                                .padding(.horizontal, 4).frame(minHeight: 44).padding(.top, 8)
                        }
                    }
                }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                toastView
                if selecting { selectionBar }
            }
        }
        .nacreScreen()
        .navigationBarHidden(true)
        .onChange(of: selecting) { on in app.hidesTabBar = on }
        .onDisappear { app.hidesTabBar = false }
        .sheet(isPresented: $adding) {
            AddTransactionSheet(api: app.api, categories: categories) { said in
                adding = false
                withAnimation { toast = Toast(title: said, undo: nil) }
                app.changed()
            }
        }
        .sheet(item: $bulk) { which in
            switch which {
            case .category:
                CategorySheet(name: pickedTitle, amount: pickedAmount, tone: pickedTone, categories: categories,
                              current: pickedCategory, mark: "\(picked.count)") { name, _ in
                    bulk = nil
                    Task { await change(["category": name], path: "api/transactions/batch/category") }
                }
            case .tag:
                BulkTagSheet(title: pickedTitle, amount: pickedAmount, tone: pickedTone,
                             count: picked.count, known: tags) { add in
                    bulk = nil
                    Task { await change(["add": add], path: "api/transactions/batch/tags") }
                }
            case .mark:
                // T-78: the selection as one, Spending (a category) or Not spending (T-06's
                // answers, or T-12's for deposits). Only answers that need nothing per row.
                let deposits = pickedRows.allSatisfy(\.inflow)
                CategorySheet(name: "\(picked.count) selected", amount: pickedNames, tone: pickedTone,
                              categories: categories, current: pickedCategory, mark: "\(picked.count)",
                              title: "Mark \(picked.count) as…",
                              notSpending: deposits ? CaseTile.notIncomeTogether : CaseTile.notSpending,
                              startNotSpending: true, onCase: { key, _ in
                    bulk = nil
                    let body: [String: Any]
                    switch key {
                    case "own": body = ["case": deposits ? "own" : "moved"]
                    case "card": body = ["case": "moved"]
                    case "saved": body = ["case": "saved"]
                    case "lent": body = ["case": "lent"]
                    case "work": body = ["case": "work"]
                    case "loan": body = ["case": "borrowed"]
                    case "out_of_savings", "lent_back": body = ["case": key]
                    default: body = ["case": "not_mine", "reason": "Not mine"]
                    }
                    Task { await change(body, path: "api/transactions/batch/mark") }
                }) { name, _ in
                    bulk = nil
                    Task { await change(["category": name], path: "api/transactions/batch/category") }
                }
            }
        }
        .alert("Leave out \(pickedTitle)?", isPresented: $leavingOut) {
            TextField("Why? For example, a friend’s purchase", text: $leaveReason)
            Button("Cancel", role: .cancel) { leaveReason = "" }
            // TEST-07: the server needs a reason, so Leave out waits for one
            // and the alert says why (it used to close and do nothing).
            Button("Leave out") { Task { await leaveOut() } }
                .disabled(leaveReason.trimmingCharacters(in: .whitespaces).isEmpty)
        } message: {
            Text("They’re left out of all your numbers. Put any back from its transaction. Say why, so you can tell later.")
        }
        .navigationDestination(for: Transaction.self) { t in
            TransactionDetailView(transaction: t, categories: categories, siblings: rows)
        }
        .refreshable {
            await runSync(force: true)
            await reload()
        }
        .reloads { await start() }
        .task(id: query) { await search() }
        .sheet(isPresented: $showFilters) {
            FilterSheet(filters: filters, month: month, months: months, accounts: filterAccounts,
                        categories: monthCategories, tags: tags,
                        count: { visible(applying: $0).count }) { chosen, chosenMonth in
                showFilters = false
                let reload = chosen.needsServer != filters.needsServer || chosenMonth != month
                filters = chosen
                if let chosenMonth = chosenMonth, chosenMonth != month { month = chosenMonth }
                if reload { Task { await self.reload() } }
            }
        }
        .sheet(isPresented: $showMonths) {
            MonthSheet(months: months, current: month) { chosen in
                showMonths = false
                if chosen != month {
                    month = chosen
                    Task { await reload() }
                }
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    // MARK: Search

    private var inSearch: Bool { searching || !query.isEmpty }

    /// T-54: "No money came into TD Visa this month."
    private var noMatchLine: String {
        let account = filters.accounts.count == 1 ? filterAccounts.first { filters.accounts.contains($0.id) }?.label : nil
        let when = month.map { $0 == Format.thisMonth() ? "this month" : "in \(Format.monthName($0))" } ?? "this month"
        if let account = account, filters.types == ["income"] { return "No money came into \(account) \(when)." }
        if let account = account, filters.types == ["spending"] { return "Nothing was spent on \(account) \(when)." }
        if let account = account { return "Nothing on \(account) matches \(when)." }
        return "Try fewer filters."
    }

    private var searchRow: some View {
        HStack(spacing: 10) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").font(.system(size: 16)).foregroundColor(Pearl.muted)
                TextField("", text: $query, prompt: Text("Search").foregroundColor(Pearl.muted))
                    .font(Nacre.body)
                    .foregroundColor(Pearl.ink)
                    .focused($searching)
                    .submitLabel(.search)
                    .autocorrectionDisabled()
                if !query.isEmpty {
                    Button { query = "" } label: {
                        Image(systemName: "xmark.circle.fill").foregroundColor(Pearl.muted)
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Clear search")
                }
            }
            .padding(.horizontal, 14)
            .frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            .background(Capsule().fill(.ultraThinMaterial))

            if inSearch {
                Button("Cancel") {
                    query = ""
                    searching = false
                }
                .font(Nacre.body)
                .foregroundColor(Pearl.action)
                .padding(.horizontal, 8)
            } else {
                Button { showFilters = true } label: {
                    Image(systemName: "slider.horizontal.3")
                        .font(.system(size: 18))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(.ultraThinMaterial))
                        .background(Circle().fill(Nacre.glass))
                        .overlay(Circle().strokeBorder(Nacre.edge, lineWidth: 1))
                        .overlay(alignment: .topTrailing) {
                            if filtersOn {
                                Circle().fill(Pearl.moneyOut).frame(width: 10, height: 10)
                                    .offset(x: -2, y: 2)
                            }
                        }
                }
                .buttonStyle(.plain)
                .accessibilityLabel(filtersOn ? "Filters, on" : "Filters")
            }
        }
        .animation(.easeOut(duration: 0.2), value: inSearch)
    }

    /// Transactions · Calendar, as a pill switch.
    private var tabs: some View {
        HStack(spacing: 0) {
            ForEach([false, true], id: \.self) { cal in
                let on = showCalendar == cal
                Button { withAnimation(.easeOut(duration: 0.2)) { showCalendar = cal } } label: {
                    Text(cal ? "Calendar" : "Transactions")
                        .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                        .frame(maxWidth: .infinity).frame(height: 32)
                        .background(Capsule().fill(on ? Color.white.opacity(0.9) : .clear))
                        .shadow(color: .black.opacity(on ? 0.06 : 0), radius: 3, y: 1)
                        // TEST-14: 44 pt to tap; the pill still draws at 32.
                        .frame(height: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(.horizontal, 3)
        .background(Capsule().fill(Pearl.ink.opacity(0.08)).frame(height: 38))
        .padding(.vertical, -3)
    }

    /// "TD Visa ••9021 ×": each filter that's on, to take it off in one tap.
    private var activeChips: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(filters.chips(accounts: filterAccounts), id: \.id) { chip in
                    Button {
                        let reload = chip.needsServer
                        filters.remove(chip.id)
                        if reload { Task { await self.reload() } }
                    } label: {
                        HStack(spacing: 6) {
                            Text(chip.label)
                            Image(systemName: "xmark").font(.system(size: 11, weight: .semibold))
                        }
                        .font(Nacre.footnote)
                        .foregroundColor(Pearl.onBlush)
                        .padding(.horizontal, 12).frame(height: 32)
                        .background(Capsule().fill(Pearl.blush))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Remove \(chip.label)")
                }
            }
        }
    }

    // MARK: The month

    private var summaryCard: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 12) {
                Button { showMonths = true } label: {
                    HStack(spacing: 6) {
                        Text(month.map { Format.monthName($0) } ?? "This month").font(Nacre.headline)
                        Image(systemName: "chevron.down").font(.system(size: 12, weight: .semibold))
                    }
                    .foregroundColor(Pearl.ink)
                }
                .buttonStyle(.plain)
                .disabled(months.isEmpty)
                .accessibilityLabel("Month, \(month.map { Format.month($0) } ?? "")")

                HStack(spacing: 0) {
                    // T-45, T-53: a search or a filter shows its own totals.
                    let narrowed = inSearch || filters.isActive
                    let spent = narrowed ? shown.filter { !$0.inflow && $0.counts == "spending" }.reduce(0) { $0 + $1.amount }
                        : (monthTotals?.spent ?? 0)
                    let income = narrowed ? shown.filter { $0.inflow && $0.counts == "income" }.reduce(0) { $0 + $1.amount }
                        : (monthTotals?.income ?? 0)
                    let left = income - spent
                    stat("Spent", Format.whole(spent), Pearl.moneyOut, filter: "spending")
                    divider
                    stat("Came in", Format.whole(income), Pearl.moneyIn, filter: "income")
                    divider
                    stat(left < -0.5 ? "Over" : "Leftover", narrowed ? "—" : Format.whole(left),
                         left < -0.5 && !narrowed ? Pearl.moneyOut : (narrowed ? Pearl.muted : Pearl.moneyIn), filter: nil)
                }
            }
            .padding(16)
            RowSeparator(inset: 0)
            if reviewCount > 0 {
                NavigationLink { ReviewView() } label: {
                    HStack(spacing: 10) {
                        Image(systemName: "questionmark.circle").font(.system(size: 18))
                        Text("\(reviewCount) need\(reviewCount == 1 ? "s" : "") a look").font(Nacre.body)
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                            .foregroundColor(Pearl.muted)
                    }
                    .foregroundColor(Pearl.ink)
                    .padding(.horizontal, 16).frame(height: 48)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            } else {
                Label("All sorted", systemImage: "checkmark")
                    .font(Nacre.body).foregroundColor(Nacre.teal)
                    .padding(.horizontal, 16).frame(height: 48)
            }
        }
    }

    private var divider: some View {
        Rectangle().fill(Nacre.separator).frame(width: 0.5, height: 44).padding(.horizontal, 10)
    }

    /// One of the three numbers; Spent and Came in narrow the list (T-67).
    private func stat(_ label: String, _ value: String, _ tone: Color, filter: String?) -> some View {
        let on = filter != nil && counts == filter
        let content = VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted)
            Text(value).font(Pearl.display(.title3)).foregroundColor(tone)
                .lineLimit(1).minimumScaleFactor(0.6)
        }
        .padding(.horizontal, on ? 8 : 0).padding(.vertical, on ? 4 : 0)
        .overlay(RoundedRectangle(cornerRadius: 10, style: .continuous)
            .strokeBorder(tone, lineWidth: 1.5).opacity(on ? 1 : 0))
        .frame(maxWidth: .infinity, alignment: .leading)
        return Group {
            if let filter = filter {
                Button { counts = on ? nil : filter } label: { content.contentShape(Rectangle()) }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(label) \(value)")
                    .accessibilityHint(on ? "Shows everything again" : "Shows only these")
                    .accessibilityAddTraits(on ? .isSelected : [])
            } else {
                content.accessibilityElement(children: .combine)
            }
        }
    }

    // MARK: The bank

    /// Getting the latest (T-58), couldn't (T-59), or a bank to sign in to
    /// again (T-36).
    @ViewBuilder private var bankState: some View {
        ForEach(disconnected, id: \.itemId) { bank in
            GlassCard {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 12) {
                        Image(systemName: "arrow.triangle.2.circlepath").font(.system(size: 18))
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(bank.name) is disconnected").font(Nacre.headline)
                            Text(bank.updated).font(Nacre.footnote)
                        }
                    }
                    .foregroundColor(Pearl.ink)
                    Button("Reconnect") { Task { await reconnect(bank.itemId) } }
                        .buttonStyle(NacreButtonStyle(busy: reconnecting == bank.itemId))
                        .disabled(reconnecting != nil)
                }
                .padding(16)
            }
            .padding(.top, 12)
        }
        switch sync {
        case .syncing:
            banner(symbol: "arrow.triangle.2.circlepath", text: "Getting your latest transactions…")
        case .failed:
            banner(symbol: "exclamationmark.triangle", text: "Couldn’t update just now.") {
                Button("Try again") { Task { await runSync(force: true) } }
                    .font(Nacre.textButton).foregroundColor(Pearl.link)
            }
        case .idle:
            EmptyView()
        }
    }

    private func banner<Trailing: View>(symbol: String, text: String,
                                        @ViewBuilder trailing: () -> Trailing = { EmptyView() }) -> some View {
        HStack(spacing: 10) {
            Image(systemName: symbol).font(.system(size: 15))
            Text(text).font(Nacre.footnote)
            Spacer(minLength: 8)
            trailing()
        }
        .foregroundColor(Pearl.ink)
        .padding(.horizontal, 16).frame(minHeight: 40)
        .background(RoundedRectangle(cornerRadius: 14, style: .continuous).fill(Nacre.glass))
        .overlay(RoundedRectangle(cornerRadius: 14, style: .continuous).strokeBorder(Nacre.edge, lineWidth: 1))
        .padding(.top, 12)
        .accessibilityElement(children: .combine)
    }

    private struct Disconnected {
        let itemId: String
        let name: String
        let updated: String
    }

    /// One card per bank, however many of its accounts are cut off.
    private var disconnected: [Disconnected] {
        var seen = Set<String>()
        return accounts.compactMap { a in
            guard a.needsReconnect, let item = a.itemId, !item.isEmpty, seen.insert(item).inserted else { return nil }
            return Disconnected(itemId: item, name: (a.institution ?? "").isEmpty ? a.name : a.institution!,
                                updated: Format.lastUpdated(a.updatedAt))
        }
    }

    // MARK: The list

    private var listHeader: some View {
        HStack {
            if inSearch {
                if results != nil {
                    Text(shown.count == 1 ? "1 result" : "\(shown.count) results")
                }
            } else if let counts = counts {
                Text("\(counts == "income" ? "Money in only" : "Spending only") · \(shown.count)")
                Spacer()
                Button("Show all") { self.counts = nil }
                    .font(Nacre.body).foregroundColor(Pearl.action)
            } else if selecting {
                Text("\(picked.count) selected · \(pickedAmount.replacingOccurrences(of: "\u{2212}", with: ""))")
                Spacer()
                Button("Cancel") { endSelecting() }
                    .font(Nacre.body).foregroundColor(Pearl.action)
            } else if loadedOnce {
                Text(shown.count == 1 ? "1 transaction" : "\(shown.count) transactions")
                if !shown.isEmpty {
                    Spacer()
                    Button("Select") { selecting = true }
                        .font(Nacre.body).foregroundColor(Pearl.action)
                }
            }
        }
        .font(Nacre.footnote)
        .foregroundColor(Pearl.muted)
        .padding(.horizontal, 4)
    }

    @ViewBuilder private var list: some View {
        let sections = self.sections
        if inSearch && query.isEmpty {
            EmptyView()
        } else if (!loadedOnce && !inSearch) || (inSearch && results == nil) {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if let error = error, shown.isEmpty {
            nothing(title: "Couldn’t load your transactions", line: error, action: "Try again") {
                Task { await reload() }
            }
        } else if shown.isEmpty {
            if inSearch {
                nothing(title: "No matches", line: "Try another word.", action: "Clear search") { query = "" }
            } else if filters.isActive || counts != nil {
                nothing(title: "Nothing matches", line: noMatchLine, action: "Clear filters") {
                    let reload = filters.needsServer
                    filters = TxFilters(sort: filters.sort)
                    counts = nil
                    if reload { Task { await self.reload() } }
                }
            } else {
                nothing(title: "Nothing yet in \(month.map { Format.monthName($0) } ?? "this month")",
                        line: "Transactions show up here as your bank sends them.", action: nil) {}
            }
        } else {
            VStack(alignment: .leading, spacing: 10) {
                ForEach(sections, id: \.title) { section in
                    if !section.title.isEmpty {
                        HStack {
                            Text(section.title.uppercased()).tracking(0.4)
                            Spacer()
                            Text(Format.whole(section.rows.reduce(0) { $0 + $1.amount }))
                        }
                        .font(Nacre.caption2).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).padding(.top, 10)
                    }
                    GlassCard {
                        ForEach(Array(section.rows.enumerated()), id: \.element.id) { index, t in
                            if index > 0 { RowSeparator(inset: 72) }
                            if selecting {
                                Button { toggle(t) } label: {
                                    TransactionRow(t: t, paidBack: paidBack(for: t), picked: picked.contains(t.id))
                                }
                                .buttonStyle(.plain)
                                .accessibilityAddTraits(picked.contains(t.id) ? .isSelected : [])
                            } else {
                                NavigationLink(value: t) {
                                    TransactionRow(t: t, paidBack: paidBack(for: t),
                                                   onConfirm: { Task { await confirmGuess(t) } })
                                }
                                .buttonStyle(.plain)
                            }
                        }
                    }
                }
            }
        }
    }

    // MARK: By category (T-18)

    /// Sorting by category shows the categories themselves, not their rows.
    private var byCategory: Bool { filters.sort == .category && !inSearch && !selecting }

    /// A filter is on, or the list is sorted some other way: the dot, and
    /// the chips to take each off.
    private var filtersOn: Bool { filters.isActive || filters.sort != .newest }

    private struct CategoryLine: Identifiable {
        let name: String
        let rows: [Transaction]
        let total: Double
        var id: String { name }
    }

    /// The shown rows that count this way, one line per category, biggest first.
    private func categoryLines(_ counts: String) -> [CategoryLine] {
        var by: [String: [Transaction]] = [:]
        for t in shown where t.counts == counts { by[t.label, default: []].append(t) }
        return by.map { name, rows in
            let sum = rows.reduce(0) { $0 + (counts == "spending" && $1.inflow ? -$1.amount : $1.amount) }
            return CategoryLine(name: name, rows: rows, total: sum)
        }
        .sorted { ($0.total, $1.name) > ($1.total, $0.name) }
    }

    /// Owed to you, then Spent, Money in and Not counted by category.
    @ViewBuilder private var categoryList: some View {
        VStack(alignment: .leading, spacing: 8) {
            if let line = owedLine {
                categoryHeading("Owed to you")
                GlassCard {
                    NavigationLink { OwedView() } label: {
                        categoryRow(line.names.joined(separator: " and "), count: line.count, total: line.total)
                    }
                    .buttonStyle(.plain)
                }
            }
            ForEach([("spending", "Spent"), ("income", "Money in"), ("none", "Not counted")], id: \.0) { key, title in
                let lines = categoryLines(key)
                if !lines.isEmpty {
                    categoryHeading(title)
                    GlassCard {
                        ForEach(Array(lines.enumerated()), id: \.element.id) { i, c in
                            if i > 0 { RowSeparator() }
                            NavigationLink {
                                CategoryPage(name: c.name, month: month, counts: key, rows: c.rows, total: c.total)
                            } label: {
                                categoryRow(c.name, count: key == "spending" ? c.rows.count : nil, total: c.total)
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            }
        }
    }

    private func categoryHeading(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 12)
            .accessibilityAddTraits(.isHeader)
    }

    /// "Groceries  6        $412 ›".
    private func categoryRow(_ name: String, count: Int?, total: Double) -> some View {
        HStack(spacing: 8) {
            Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            if let count = count {
                Text("\(count)").font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text(Format.whole(total)).font(Nacre.body).foregroundColor(Pearl.ink)
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 50)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    // MARK: Select (T-19)

    /// T-77: Category, Mark as…, Confirm (Pearl's guesses, when some are)
    /// and Leave out, where the tab bar was. Tag waits while tags are off
    /// (THL-286), as on the web.
    private var selectionBar: some View {
        HStack(spacing: 0) {
            barButton("Category") { bulk = .category }
            barButton("Mark as…") { bulk = .mark }
            if guesses > 0 {
                barButton("Confirm \(guesses)") {
                    let ids = pickedRows.filter(\.suggested).map(\.id)
                    Task { await change(["ids": ids], path: "api/transactions/batch/confirm") }
                }
            }
            barButton("Leave out") { leavingOut = true }
        }
        .padding(.horizontal, 8).padding(.top, 14).padding(.bottom, 10)
        .background(Pearl.bar.ignoresSafeArea(edges: .bottom))
        .overlay(alignment: .top) { Rectangle().fill(Pearl.border).frame(height: 1) }
    }

    /// Pearl's guesses among the picked rows, for Confirm.
    private var guesses: Int { pickedRows.filter(\.suggested).count }

    private func barButton(_ title: String, _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            Text(title).font(Nacre.textButton).foregroundColor(Pearl.link)
                .lineLimit(1).minimumScaleFactor(0.8)
                .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(picked.isEmpty || busy)
        .opacity(picked.isEmpty ? 0.4 : 1)
    }

    /// "✓ Changed 3 to Dining out. Allowance is now $842.  Undo".
    @ViewBuilder private var toastView: some View {
        if let toast = toast {
            HStack(spacing: 12) {
                Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
                Text(toast.title).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if toast.undo != nil {
                    Button("Undo") { Task { await undo() } }
                        .font(Nacre.textButton).foregroundColor(Pearl.link)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .background(Capsule().fill(.ultraThinMaterial))
            .background(Capsule().fill(Nacre.glass))
            .overlay(Capsule().strokeBorder(Nacre.edge, lineWidth: 1))
            .padding(.horizontal, 16).padding(.bottom, 12)
            .swipeToDismiss { self.toast = nil }
            .transition(.move(edge: .bottom).combined(with: .opacity))
            .task(id: toast) {
                try? await Task.sleep(nanoseconds: 6_000_000_000)
                if self.toast == toast { withAnimation { self.toast = nil } }
            }
        }
    }

    private var pickedRows: [Transaction] { shown.filter { picked.contains($0.id) } }

    /// "−$89.00 · Uber Eats, Shoppers, Sushi Nami" (T-78).
    private var pickedNames: String {
        let names = pickedRows.prefix(3).map { $0.merchant.components(separatedBy: " ").prefix(2).joined(separator: " ") }
        let more = pickedRows.count > 3 ? " and \(pickedRows.count - 3) more" : ""
        return "\(pickedAmount) · \(names.joined(separator: ", "))\(more)"
    }

    private var pickedTitle: String { picked.count == 1 ? "1 transaction" : "\(picked.count) transactions" }

    /// "−$89.00": what the picked rows come to, out less in.
    private var pickedAmount: String {
        let net = pickedRows.reduce(0) { $0 + ($1.inflow ? -$1.amount : $1.amount) }
        return (net < 0 ? "+" : "\u{2212}") + Format.amount(net)
    }

    private var pickedTone: Color {
        pickedRows.reduce(0) { $0 + ($1.inflow ? -$1.amount : $1.amount) } < 0 ? Pearl.moneyIn : Pearl.moneyOut
    }

    /// Their category when they all share one, so Save waits for a change.
    private var pickedCategory: String {
        let cats = Set(pickedRows.map { $0.category ?? $0.label })
        return cats.count == 1 ? cats.first ?? "" : ""
    }

    private func toggle(_ t: Transaction) {
        if picked.contains(t.id) { picked.remove(t.id) } else { picked.insert(t.id) }
    }

    /// Leave out every picked row, with her reason.
    private func leaveOut() async {
        let reason = leaveReason.trimmingCharacters(in: .whitespaces)
        leaveReason = ""
        guard !reason.isEmpty else {
            error = "Say why, so you can tell later."
            return
        }
        busy = true
        defer { busy = false }
        let ids = Array(picked)
        do {
            for id in ids {
                let _: OK = try await app.api.put("api/transactions/\(id)/exclude", ["reason": reason])
            }
            endSelecting()
            withAnimation { toast = Toast(title: ids.count == 1 ? "Left out." : "\(ids.count) left out.", undo: nil) }
            app.changed()
            await reload()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func endSelecting() {
        selecting = false
        picked = []
    }

    /// One change for every picked row; the server's words (or `say` and
    /// what it did to the Allowance) and its Undo.
    private func change(_ body: [String: Any], path: String, say: String? = nil) async {
        busy = true
        defer { busy = false }
        var payload = body
        payload["ids"] = Array(picked)
        do {
            let reply: MarkReply = try await app.api.post(path, payload)
            endSelecting()
            let title = say.map { [$0, reply.detail ?? ""].filter { !$0.isEmpty }.joined(separator: " ") }
                ?? reply.title ?? "Changed."
            withAnimation { toast = Toast(title: title, undo: reply.undo) }
            error = nil
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Tapping the dotted chip: Pearl's guess is right (2026-11-08).
    private func confirmGuess(_ t: Transaction) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let reply: MarkReply = try await app.api.post("api/transactions/batch/confirm", ["ids": [t.id]])
            withAnimation { toast = Toast(title: reply.title ?? "\(t.merchant) · \(t.label)", undo: reply.undo) }
            error = nil
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func undo() async {
        guard let payload = toast?.undo, let body = payload.any as? [String: Any] else { return }
        do {
            let _: OK = try await app.api.post("api/transactions/undo", body)
            withAnimation { toast = Toast(title: "Undone.", undo: nil) }
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func nothing(title: String, line: String, action: String?, _ run: @escaping () -> Void) -> some View {
        VStack(spacing: 8) {
            Text(title).font(Nacre.title2).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
            Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
            if let action = action {
                Button(action, action: run).font(Nacre.textButton).foregroundColor(Pearl.link).padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 40)
    }

    /// T-35: no bank yet, so nothing to show.
    private var emptyLedger: some View {
        VStack(spacing: 10) {
            Image(systemName: "magnifyingglass")
                .font(.system(size: 20, weight: .medium)).foregroundColor(Pearl.action)
                .frame(width: 56, height: 56)
                .background(Circle().fill(Pearl.blush))
                .padding(.bottom, 8)
                .accessibilityHidden(true)
            Text("No transactions yet").font(Nacre.title2)
            Text("Link a bank to see them.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
            Button { Task { await link() } } label: {
                Text("Link your bank").font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(width: 240, height: 56)
                    .overlay(Capsule().strokeBorder(Pearl.ink, lineWidth: 1.2))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .disabled(reconnecting != nil)
            .padding(.top, 12)
            // T-35.
            Button("Add one by hand") { adding = true }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .frame(width: 240)
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 72)
    }

    // MARK: What's shown

    private var noTransactionsYet: Bool { loadedOnce && months.isEmpty && rows.isEmpty && error == nil }

    private var shown: [Transaction] { visible(applying: filters) }

    /// The rows the list shows under these filters: the search's or the
    /// month's, narrowed, then sorted.
    private func visible(applying f: TxFilters) -> [Transaction] {
        let base = inSearch ? (results ?? []) : rows
        var out = base.filter { f.matches($0, owed: owed) }
        if !inSearch, let counts = counts { out = out.filter { $0.counts == counts } }
        switch f.sort {
        case .largest: out.sort { $0.amount > $1.amount }
        case .category: out.sort { ($0.label, $1.date) < ($1.label, $0.date) }
        case .merchant: out.sort { ($0.merchant.lowercased(), $1.date) < ($1.merchant.lowercased(), $0.date) }
        case .newest: break
        }
        return out
    }

    private struct Section { let title: String; let rows: [Transaction] }

    /// One card, or one per category or merchant when sorted that way.
    private var sections: [Section] {
        let rows = shown
        let key: ((Transaction) -> String)?
        switch filters.sort {
        case .category: key = { $0.label }
        case .merchant: key = { $0.merchant }
        default: key = nil
        }
        guard let key = key else { return [Section(title: "", rows: rows)] }
        var out: [Section] = []
        for t in rows {
            if let last = out.last, last.title == key(t) {
                out[out.count - 1] = Section(title: last.title, rows: last.rows + [t])
            } else {
                out.append(Section(title: key(t), rows: [t]))
            }
        }
        return out
    }

    /// "Paid back · Sushi Nami": the charge a payback is for, when it's in view.
    private func paidBack(for t: Transaction) -> String? {
        guard let id = t.repays else { return nil }
        return (rows + (results ?? [])).first { $0.id == id }?.merchant
    }

    /// The month's accounts, named as Accounts names them when it can.
    private var filterAccounts: [FilterAccount] {
        var out: [FilterAccount] = []
        for t in rows {
            guard let id = t.accountId, !id.isEmpty, !out.contains(where: { $0.id == id }) else { continue }
            let linked = accounts.first { $0.id == id }
            out.append(FilterAccount(id: id, label: linked?.label ?? t.account ?? "Account",
                                     joint: linked?.joint == true || !t.joint.isEmpty))
        }
        return out.sorted { $0.label < $1.label }
    }

    /// The month's categories, most used first.
    private var monthCategories: [String] {
        var count: [String: Int] = [:]
        for t in rows { count[t.label, default: 0] += 1 }
        return count.sorted { ($0.value, $1.key) > ($1.value, $0.key) }.map(\.key)
    }

    // MARK: Loading

    /// The months, the count, the accounts and the list, asked for together
    /// (2026-11-08) instead of one after another before the list could start.
    private func start() async {
        let api = app.api
        async let summaryReply: Summary? = try? api.get("api/summary")
        async let reviewReply: Review? = try? api.get("api/review")
        async let accountsReply: AccountsOverview? = try? api.get("api/accounts/overview")
        if month != nil {
            // Already on a month: its list needn't wait for the months.
            await reload()
        }
        if let summary = await summaryReply {
            let was = month
            months = summary.months ?? []
            if month == nil || !months.contains(month!) { month = summary.latestMonth ?? months.last }
            if month != was || !loadedOnce { await reload() }
        } else if !loadedOnce {
            await reload()
        }
        if let review = await reviewReply { reviewCount = review.open ?? review.count }
        if let overview = await accountsReply { accounts = overview.linked }
        if !syncedOnce {
            syncedOnce = true
            await runSync(force: false)
        }
    }

    private func loadAccounts() async {
        if let overview: AccountsOverview = try? await app.api.get("api/accounts/overview") {
            accounts = overview.linked
        }
    }

    private func reload() async {
        defer { loadedOnce = true }
        var p = ["limit": "1000"]
        if let month = month { p["month"] = month }
        if filters.only.contains(.leftOut) { p["excluded"] = "1" }
        if filters.only.contains(.subscriptions) { p["recurring"] = "1" }
        do {
            let list: TransactionList = try await app.api.get("api/transactions/list", query: p)
            rows = list.transactions
            owed = Set(list.owedIds)
            owedLine = list.owedTotal > 0.005
                ? OwedLine(names: list.owedNames, count: list.owedCount, total: list.owedTotal) : nil
            tags = list.tags
            if filters.needsServer, let month = month {
                // The cards are the month's, whatever the list is narrowed to.
                let plain: TransactionList? = try? await app.api.get("api/transactions/list",
                                                                     query: ["month": month, "limit": "1"])
                monthTotals = plain?.monthTotals ?? list.monthTotals
            } else {
                monthTotals = list.monthTotals
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func search() async {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else {
            results = nil
            return
        }
        try? await Task.sleep(nanoseconds: 250_000_000)
        guard !Task.isCancelled else { return }
        if let list: TransactionList = try? await app.api.get("api/transactions/list",
                                                               query: ["q": q, "limit": "200"]) {
            guard !Task.isCancelled else { return }
            results = list.transactions
        }
    }

    /// The bank's latest. Opening asks without `force`, so a sync a moment
    /// ago isn't repeated; pulling down and Try again ask with it.
    private func runSync(force: Bool) async {
        guard !accounts.isEmpty else { return }
        struct Reply: Decodable { let imported: Int?; let recent: Bool? }
        sync = .syncing
        do {
            let reply: Reply = try await app.api.post("api/plaid/sync", force ? ["force": true] : [:])
            sync = .idle
            if (reply.imported ?? 0) > 0 || force {
                await loadAccounts()
                if (reply.imported ?? 0) > 0 { app.changed() }
            }
        } catch {
            // A server without Plaid has nothing to sync: not a failure.
            let words = (error as? APIError)?.problem?.error ?? ""
            sync = words.contains("isn't configured") || error is CancellationError ? .idle : .failed
        }
    }

    /// T-36: sign in to the bank again in Plaid's update mode, then sync.
    private func reconnect(_ itemId: String) async {
        reconnecting = itemId
        defer { reconnecting = nil }
        do {
            if case .linked = try await plaid.open(api: app.api, itemId: itemId) {
                await runSync(force: true)
                app.changed()
            }
        } catch {
            sync = .failed
        }
    }

    /// T-35: link a first bank from here.
    private func link() async {
        reconnecting = "new"
        defer { reconnecting = nil }
        do {
            if case .linked(let linked) = try await plaid.open(api: app.api) {
                let _: LinkedItem = try await app.api.post("api/plaid/exchange",
                                                           ["public_token": linked.publicToken,
                                                            "institution": linked.institution])
                syncedOnce = true
                app.changed()
            }
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - A row

/// One transaction (T-01): initials, who, "Category · when", any line about
/// a split or a refund, and Pearl's guess as a dashed chip.
struct TransactionRow: View {
    let t: Transaction
    var paidBack: String? = nil
    /// Picked or not, while Cash flow is selecting (T-19); nil otherwise.
    var picked: Bool? = nil
    /// On a category's own page (T-46) the category goes without saying.
    var showsCategory = true
    /// Tapping the dotted guess says it's right, without opening the row.
    var onConfirm: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .center, spacing: 14) {
            if let picked = picked {
                Image(systemName: picked ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundColor(picked ? Pearl.action : Pearl.muted)
                    .padding(.trailing, -4)
            }
            Initials(name: t.merchant)
            VStack(alignment: .leading, spacing: 3) {
                Text(t.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(meta).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(splitNote == nil ? 1 : 2)
                if let extra = extra {
                    Text(extra).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                }
                if t.suggested {
                    if let onConfirm = onConfirm, !t.asks {
                        Button(action: onConfirm) { GuessChip(label: t.label, question: true) }
                            .buttonStyle(.plain)
                            .padding(.top, 4)
                    } else {
                        GuessChip(label: t.label, question: !t.asks).padding(.top, 4)
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(shownMoney)
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(t.tone)
                .lineLimit(1).fixedSize()
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(t.suggested ? "Pearl’s guess. Opens it to check." : "")
        .accessibilityAction(named: "Confirm \(t.label)") {
            if t.suggested, !t.asks { onConfirm?() }
        }
    }

    /// "Health · Today"; "Today · Pending" while it's a guess; "Paid back · Sushi Nami".
    private var meta: String {
        let when = Format.relativeDay(t.date)
        if let paidBack = paidBack { return "Paid back · \(paidBack)" }
        if let charge = t.refundOf { return "Refund · \(charge.merchant)" }
        // T-01r2 (TEST-25): a split says what the server says.
        if let note = splitNote { return note }
        // T-82 (THL-292): a transfer a recurring rule sorted says so.
        if t.recurring != nil, let note = t.note, note.hasPrefix("Recurring") { return note }
        if t.suggested { return t.pending ? "\(when) · Pending" : when }
        return [showsCategory ? t.label : nil, when, t.pending ? "Pending" : nil].compactMap { $0 }
            .joined(separator: " · ")
    }

    /// T-01r2 (TEST-25): the server's note on a split row, "Split with Priya
    /// +2 · $87.50 to come back", "Split 5 ways · not sure yet · $45.00 still
    /// counts" or "Your share of $59.33 · all paid back". The app used to make
    /// its own "Your share of …" and showed only what still counts.
    private var splitNote: String? {
        guard t.split, !t.inflow, let note = t.note, !note.isEmpty else { return nil }
        return note
    }

    /// T-01r2 and Rule A: the whole purchase while some is still to come
    /// back or not settled ("Split …"); her share once it's all paid back.
    private var shownMoney: String {
        if let note = splitNote, note.hasPrefix("Split "), let full = t.fullAmount {
            return "\u{2212}" + Format.amount(full)
        }
        return Format.money(t)
    }

    /// "Your share of $86", "Refunded in full · Nov 10".
    private var extra: String? {
        if splitNote == nil, t.split, let full = t.fullAmount, abs(full - t.amount) >= 0.005 {
            return "Your share of \(Format.compact(full))"
        }
        if !t.refundedBy.isEmpty {
            let back = t.refundedBy.reduce(0) { $0 + $1.amount }
            let what = back >= (t.fullAmount ?? t.amount) - 0.005 ? "Refunded in full" : "\(Format.compact(back)) refunded"
            return t.refundedBy.count == 1 ? "\(what) · \(Format.short(t.refundedBy[0].date))" : what
        }
        if t.oneOff { return "Left out of your usual month" }
        return nil
    }
}

/// The merchant's initials on a pale disc.
struct Initials: View {
    let name: String
    var size: CGFloat = 40

    var body: some View {
        Text(letters)
            .font(.custom("Figtree-Medium", size: size * 0.36))
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(Pearl.dynamic(light: 0xEFE4EB, dark: 0x252C5E)))
            .accessibilityHidden(true)
    }

    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }.prefix(2)
        let out = words.compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "·" : out
    }
}

/// "? Dining out?": Pearl's guess, dashed, waiting for a yes.
struct GuessChip: View {
    let label: String
    /// "Dining out?" for a guess; "Not sorted yet" already says it's waiting.
    var question = true

    var body: some View {
        HStack(spacing: 4) {
            Image(systemName: "questionmark.circle").font(.system(size: 11, weight: .semibold))
            Text(question ? "\(label)?" : label)
        }
        .font(Nacre.footnote)
        .foregroundColor(Pearl.ink)
        .padding(.horizontal, 10).frame(height: 24)
        .overlay(Capsule().strokeBorder(Pearl.ink.opacity(0.7), style: StrokeStyle(lineWidth: 1, dash: [3, 2])))
        .accessibilityLabel("Pearl’s guess: \(label)")
    }
}

// MARK: - Filter & sort

/// An account the filter can keep in: "TD Savings ••2210 · Joint".
struct FilterAccount: Hashable {
    let id: String
    let label: String
    let joint: Bool
}

/// What Filters (T-17) has chosen. Sections combine; choices within a
/// section are either-or.
struct TxFilters: Equatable {
    enum Sort: String, CaseIterable { case newest = "Newest first", largest = "Largest first",
                                           category = "By category", merchant = "By merchant" }
    enum Only: String, CaseIterable {
        case leftOut = "Left out", subscriptions = "Subscriptions", joint = "Joint", bills = "Bills"
        case owed = "Owed to you", pending = "Pending", look = "Needs a look", manual = "Added by hand"
    }

    var sort: Sort = .newest
    /// The accounts kept in; empty is every account.
    var accounts: Set<String> = []
    var categories: Set<String> = []
    /// Spending, income, savings, transfers.
    var types: Set<String> = []
    /// Spending types: essentials, lifestyle… and fixed, variable.
    var groups: Set<String> = []
    var only: Set<Only> = []
    var tags: Set<String> = []
    var min = ""
    var max = ""
    var merchant = ""

    static let typeNames: [(key: String, name: String)] = [
        ("spending", "Spending"), ("income", "Money in"), ("savings", "Savings"), ("transfer", "Transfers"),
    ]
    static let groupNames: [(key: String, name: String)] = [
        ("essentials", "Essentials"), ("lifestyle", "Lifestyle"), ("fixed", "Fixed"), ("variable", "Variable"),
    ]

    var isActive: Bool { self != TxFilters(sort: sort) }

    /// Left out and Subscriptions are the server's to work out.
    var needsServer: Bool { only.contains(.leftOut) || only.contains(.subscriptions) }

    var minValue: Double? { Double(min.replacingOccurrences(of: "$", with: "")) }
    var maxValue: Double? { Double(max.replacingOccurrences(of: "$", with: "")) }

    func matches(_ t: Transaction, owed: Set<String>) -> Bool {
        if !accounts.isEmpty && !accounts.contains(t.accountId ?? "") { return false }
        if !categories.isEmpty && !categories.contains(t.label) { return false }
        if !types.isEmpty && !types.contains(where: { type in
            switch type {
            case "spending": return t.counts == "spending"
            case "income": return t.counts == "income" || t.group == "income"
            default: return t.group == type
            }
        }) { return false }
        if !groups.isEmpty && !groups.contains(t.group ?? "") && !groups.contains(t.kind ?? "") { return false }
        if !tags.isEmpty && tags.isDisjoint(with: t.tags) { return false }
        if let lo = minValue, t.amount < lo - 0.005 { return false }
        if let hi = maxValue, t.amount > hi + 0.005 { return false }
        let name = merchant.trimmingCharacters(in: .whitespaces)
        if !name.isEmpty && !t.merchant.localizedCaseInsensitiveContains(name) { return false }
        // Left out and Subscriptions were already chosen by the server.
        let here = only.subtracting([.leftOut, .subscriptions])
        if !here.isEmpty && !here.contains(where: { flag in
            switch flag {
            case .joint: return !t.joint.isEmpty
            case .bills: return t.kind == "fixed" && t.counts == "spending"
            case .owed: return owed.contains(t.id)
            case .pending: return t.pending
            case .look: return t.suggested
            case .manual: return t.manual
            case .leftOut, .subscriptions: return true
            }
        }) { return false }
        return true
    }

    struct Chip { let id: String; let label: String; let needsServer: Bool }

    /// "By category ×", "TD Visa ••9021 ×": each choice that's on.
    func chips(accounts all: [FilterAccount]) -> [Chip] {
        var out: [Chip] = []
        if sort != .newest { out.append(Chip(id: "sort", label: sort.rawValue, needsServer: false)) }
        for id in accounts.sorted() {
            out.append(Chip(id: "a:" + id, label: all.first { $0.id == id }?.label ?? "Account", needsServer: false))
        }
        out += categories.sorted().map { Chip(id: "c:" + $0, label: $0, needsServer: false) }
        out += Self.typeNames.filter { types.contains($0.key) }
            .map { Chip(id: "y:" + $0.key, label: $0.name, needsServer: false) }
        out += Self.groupNames.filter { groups.contains($0.key) }
            .map { Chip(id: "g:" + $0.key, label: $0.name, needsServer: false) }
        out += Only.allCases.filter { only.contains($0) }
            .map { Chip(id: "o:" + $0.rawValue, label: $0.rawValue, needsServer: $0 == .leftOut || $0 == .subscriptions) }
        out += tags.sorted().map { Chip(id: "t:" + $0, label: "#" + $0, needsServer: false) }
        if let label = amountLabel { out.append(Chip(id: "amount", label: label, needsServer: false)) }
        if !merchant.trimmingCharacters(in: .whitespaces).isEmpty {
            out.append(Chip(id: "merchant", label: merchant, needsServer: false))
        }
        return out
    }

    /// "$50–$200", "$50 and up", or nil for any amount.
    var amountLabel: String? {
        guard minValue != nil || maxValue != nil else { return nil }
        let lo = minValue.map { Format.compact($0) } ?? "$0"
        return maxValue.map { "\(lo)–\(Format.compact($0))" } ?? "\(lo) and up"
    }

    mutating func remove(_ chip: String) {
        let value = String(chip.dropFirst(2))
        switch chip.prefix(2) {
        case "a:": accounts.remove(value)
        case "c:": categories.remove(value)
        case "y:": types.remove(value)
        case "g:": groups.remove(value)
        case "o:": if let flag = Only(rawValue: value) { only.remove(flag) }
        case "t:": tags.remove(value)
        default:
            if chip == "sort" { sort = .newest }
            if chip == "amount" { min = ""; max = "" }
            if chip == "merchant" { merchant = "" }
        }
    }
}

/// T-17: transaction and spending type as chips, then a card whose rows
/// open in place (T-17b to T-17d): month, accounts, category, tags, amount,
/// and sort, only show and merchant; and whether to show what's left out.
/// "Show 36" applies it.
struct FilterSheet: View {
    @State var filters: TxFilters
    @State var month: String?
    let months: [String]
    let accounts: [FilterAccount]
    let categories: [String]
    let tags: [String]
    let count: (TxFilters) -> Int
    let onApply: (TxFilters, String?) -> Void
    /// The month the list is on: only its rows can be counted here.
    private let initialMonth: String?

    @Environment(\.dismiss) private var dismiss
    @State private var open: Row?
    @State private var allMonths = false

    enum Row { case month, accounts, category, tags, amount, sort, only, merchant }

    init(filters: TxFilters, month: String?, months: [String], accounts: [FilterAccount],
         categories: [String], tags: [String], count: @escaping (TxFilters) -> Int,
         onApply: @escaping (TxFilters, String?) -> Void) {
        _filters = State(initialValue: filters)
        _month = State(initialValue: month)
        initialMonth = month
        self.months = months
        self.accounts = accounts
        self.categories = categories
        self.tags = tags
        self.count = count
        self.onApply = onApply
    }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Filters") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    heading("Transaction type")
                    Chips {
                        ForEach(TxFilters.typeNames, id: \.key) { y in
                            FilterChip(label: y.name, on: filters.types.contains(y.key)) {
                                filters.types.formSymmetricDifference([y.key])
                            }
                        }
                    }
                    heading("Spending type")
                    Chips {
                        ForEach(TxFilters.groupNames, id: \.key) { g in
                            FilterChip(label: g.name, on: filters.groups.contains(g.key)) {
                                filters.groups.formSymmetricDifference([g.key])
                            }
                        }
                    }
                    GlassCard { rows }.padding(.top, 6)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
                .animation(.easeOut(duration: 0.2), value: open)
            }
            .scrollDismissesKeyboard(.interactively)

            HStack(spacing: 16) {
                Button("Reset") {
                    filters = TxFilters()
                    month = initialMonth
                }
                .font(Nacre.headline).foregroundColor(Pearl.action)
                .frame(width: 84)
                Button(showLabel) { onApply(filters, month) }
                    .buttonStyle(NacreButtonStyle())
            }
            .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDragIndicator(.visible)
    }

    @ViewBuilder private var rows: some View {
        if !months.isEmpty {
            row(.month, "Month", month.map { Format.monthName($0) } ?? "This month")
            if open == .month {
                let shownMonths = allMonths ? Array(months.reversed()) : Array(months.suffix(4).reversed())
                ForEach(shownMonths, id: \.self) { m in
                    option(allMonths ? Format.month(m) : Format.monthName(m), on: month == m) { month = m }
                }
                if months.count > 4 && !allMonths {
                    option("Earlier months", on: false) { allMonths = true }
                }
            }
            RowSeparator()
        }
        if !accounts.isEmpty {
            row(.accounts, "Accounts", accountsValue)
            if open == .accounts {
                ForEach(accounts, id: \.id) { a in
                    option(a.label + (a.joint ? " · Joint" : ""),
                           on: filters.accounts.isEmpty || filters.accounts.contains(a.id)) { toggleAccount(a.id) }
                }
            }
            RowSeparator()
        }
        if !categories.isEmpty {
            row(.category, "Category", list(filters.categories.sorted()))
            if open == .category {
                ForEach(categories, id: \.self) { c in
                    option(c, on: filters.categories.contains(c)) { filters.categories.formSymmetricDifference([c]) }
                }
            }
            RowSeparator()
        }
        if Features.tags && !tags.isEmpty {
            row(.tags, "Tags", list(filters.tags.sorted().map { "#" + $0 }))
            if open == .tags {
                ForEach(tags, id: \.self) { tag in
                    option("#" + tag, on: filters.tags.contains(tag)) { filters.tags.formSymmetricDifference([tag]) }
                }
            }
            RowSeparator()
        }
        row(.amount, "Amount", filters.amountLabel ?? "Any")
        if open == .amount {
            HStack(spacing: 12) {
                amountField("Min", text: $filters.min, prompt: "$0")
                amountField("Max", text: $filters.max, prompt: "Any")
            }
            .padding(.horizontal, 16).padding(.bottom, 12)
        }
        RowSeparator()
        row(.sort, "Sort", filters.sort.rawValue)
        if open == .sort {
            ForEach(TxFilters.Sort.allCases, id: \.self) { sort in
                option(sort.rawValue, on: filters.sort == sort) { filters.sort = sort }
            }
        }
        RowSeparator()
        row(.only, "Only show", list(TxFilters.Only.allCases.filter { $0 != .leftOut && filters.only.contains($0) }
            .map(\.rawValue)))
        if open == .only {
            ForEach(TxFilters.Only.allCases.filter { $0 != .leftOut }, id: \.self) { flag in
                option(flag.rawValue, on: filters.only.contains(flag)) { filters.only.formSymmetricDifference([flag]) }
            }
        }
        RowSeparator()
        row(.merchant, "Merchant", filters.merchant.trimmingCharacters(in: .whitespaces).isEmpty ? "Any" : filters.merchant)
        if open == .merchant {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                TextField("", text: $filters.merchant, prompt: Text("Any merchant").foregroundColor(Pearl.muted))
                    .font(Nacre.body).autocorrectionDisabled()
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            .padding(.horizontal, 16).padding(.bottom, 12)
        }
        RowSeparator()
        Toggle(isOn: Binding(get: { filters.only.contains(.leftOut) },
                             set: { on in if on { filters.only.insert(.leftOut) } else { filters.only.remove(.leftOut) } })) {
            Text("Show left-out transactions").font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action)
        .padding(.horizontal, 16).frame(minHeight: 50)
    }

    /// "Show 36", or just "Show" when another month is chosen (its rows aren't here yet).
    private var showLabel: String {
        guard month == initialMonth else { return "Show" }
        return "Show \(count(filters))"
    }

    private var accountsValue: String {
        if filters.accounts.isEmpty { return "All accounts" }
        if filters.accounts.count == 1, let a = accounts.first(where: { filters.accounts.contains($0.id) }) {
            return a.label
        }
        return "\(filters.accounts.count) accounts"
    }

    /// "Groceries, Dining out", or Any.
    private func list(_ names: [String]) -> String {
        names.isEmpty ? "Any" : names.joined(separator: ", ")
    }

    private func toggleAccount(_ id: String) {
        var chosen = filters.accounts.isEmpty ? Set(accounts.map(\.id)) : filters.accounts
        chosen.formSymmetricDifference([id])
        filters.accounts = chosen.count == accounts.count ? [] : chosen
    }

    /// "Month   November ⌄": tapping opens its choices under it, and closes
    /// whichever was open.
    private func row(_ which: Row, _ title: String, _ value: String) -> some View {
        Button { open = open == which ? nil : which } label: {
            HStack(spacing: 8) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink).layoutPriority(1)
                Spacer(minLength: 12)
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                Image(systemName: open == which ? "chevron.up" : "chevron.down")
                    .font(.system(size: 12, weight: .semibold)).foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 50)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityValue(value)
        .accessibilityHint(open == which ? "Closes the choices" : "Shows the choices")
    }

    /// One choice under an open row: a ticked circle when it's on.
    private func option(_ label: String, on: Bool, _ tap: @escaping () -> Void) -> some View {
        VStack(spacing: 0) {
            RowSeparator(inset: 52)
            Button(action: tap) {
                HStack(spacing: 12) {
                    Image(systemName: on ? "checkmark.circle.fill" : "circle")
                        .font(.system(size: 22))
                        .foregroundColor(on ? Pearl.action : Pearl.muted)
                    Text(label).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Spacer()
                }
                .padding(.horizontal, 16).frame(height: 52)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(on ? .isSelected : [])
        }
    }

    private func heading(_ text: String) -> some View {
        Text(text.uppercased())
            .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 6)
            .accessibilityAddTraits(.isHeader)
    }

    private func amountField(_ label: String, text: Binding<String>, prompt: String) -> some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted)
            TextField("", text: text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                .font(Nacre.body).keyboardType(.decimalPad)
                .accessibilityLabel("\(label) amount")
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Pearl.ink.opacity(0.05)))
    }
}

/// A capsule that's on (blush) or off (outlined).
struct FilterChip: View {
    let label: String
    let on: Bool
    /// The tabs on Categories and rules (CR-00): opaque when off, and a deep
    /// blush with light words when on in dark mode.
    var solid = false
    let action: () -> Void

    private static let solidOn = Pearl.dynamic(light: 0xFFE4EC, dark: 0x4E2238)

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(solid ? Nacre.label : Nacre.footnote)
                .foregroundColor(solid ? Pearl.ink : (on ? Pearl.onBlush : Pearl.ink))
                .lineLimit(1)
                .padding(.horizontal, 14).frame(height: solid ? 36 : 34)
                .background(Capsule().fill(on ? (solid ? Self.solidOn : Pearl.blush) : (solid ? Pearl.card : Nacre.glass)))
                .overlay(Capsule().strokeBorder(on ? Color.clear : (solid ? Pearl.border : Nacre.separator), lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// Chips that wrap onto as many lines as they need.
struct Chips<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        FlowLayout(spacing: 8) { content() }
            .padding(.horizontal, 2)
    }
}

struct FlowLayout: Layout {
    var spacing: CGFloat = 8

    func sizeThatFits(proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) -> CGSize {
        let rows = arrange(width: proposal.width ?? .infinity, subviews: subviews)
        let height = rows.map(\.height).reduce(0, +) + spacing * CGFloat(max(rows.count - 1, 0))
        return CGSize(width: proposal.width ?? rows.map(\.width).max() ?? 0, height: height)
    }

    func placeSubviews(in bounds: CGRect, proposal: ProposedViewSize, subviews: Subviews, cache: inout ()) {
        var y = bounds.minY
        for row in arrange(width: bounds.width, subviews: subviews) {
            var x = bounds.minX
            for index in row.items {
                let size = subviews[index].sizeThatFits(.unspecified)
                subviews[index].place(at: CGPoint(x: x, y: y), proposal: ProposedViewSize(size))
                x += size.width + spacing
            }
            y += row.height + spacing
        }
    }

    private struct Row { var items: [Int] = []; var width: CGFloat = 0; var height: CGFloat = 0 }

    private func arrange(width: CGFloat, subviews: Subviews) -> [Row] {
        var rows: [Row] = [Row()]
        for (index, view) in subviews.enumerated() {
            let size = view.sizeThatFits(.unspecified)
            if !rows[rows.count - 1].items.isEmpty && rows[rows.count - 1].width + spacing + size.width > width {
                rows.append(Row())
            }
            var row = rows[rows.count - 1]
            row.width += (row.items.isEmpty ? 0 : spacing) + size.width
            row.height = max(row.height, size.height)
            row.items.append(index)
            rows[rows.count - 1] = row
        }
        return rows.filter { !$0.items.isEmpty }
    }
}

// MARK: - Choose a month

/// T-47: each month and how it came out; Done goes to the one chosen.
struct MonthSheet: View {
    let months: [String]
    let current: String?
    let onDone: (String?) -> Void

    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var chosen: String?
    @State private var left: [String: Double] = [:]

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Choose a month") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(years, id: \.self) { year in
                        Text(year).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16).padding(.top, 8)
                        GlassCard {
                            let inYear = months.reversed().filter { $0.hasPrefix(year) }
                            ForEach(Array(inYear.enumerated()), id: \.element) { index, m in
                                if index > 0 { RowSeparator() }
                                Button { chosen = m } label: {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(Format.monthName(m)).font(Nacre.body).foregroundColor(Pearl.ink)
                                            if let line = line(m) {
                                                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                            }
                                        }
                                        Spacer()
                                        if (chosen ?? current) == m {
                                            Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold))
                                                .foregroundColor(Pearl.action)
                                        }
                                    }
                                    .padding(.horizontal, 16).frame(minHeight: 64)
                                    .contentShape(Rectangle())
                                }
                                .buttonStyle(.plain)
                                .accessibilityAddTraits((chosen ?? current) == m ? .isSelected : [])
                            }
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
            Button("Done") { onDone(chosen ?? current) }
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .task { await loadTotals() }
    }

    private var years: [String] {
        var out: [String] = []
        for m in months.reversed() where !out.contains(String(m.prefix(4))) { out.append(String(m.prefix(4))) }
        return out
    }

    /// "Leftover $866 so far", "Over $140".
    private func line(_ m: String) -> String? {
        guard let value = left[m] else { return nil }
        let running = m == months.last && m == Format.thisMonth()
        let words = value < -0.5 ? "Over \(Format.whole(value))" : "Leftover \(Format.whole(value))"
        return running ? words + " so far" : words
    }

    private func loadTotals() async {
        let api = app.api
        await withTaskGroup(of: (String, Double?).self) { group in
            for m in months.suffix(12) {
                group.addTask {
                    let list: TransactionList? = try? await api.get("api/transactions/list",
                                                                    query: ["month": m, "limit": "1"])
                    guard let t = list?.monthTotals else { return (m, nil) }
                    return (m, (t.income ?? 0) - (t.spent ?? 0))
                }
            }
            for await (m, value) in group {
                if let value = value { left[m] = value }
            }
        }
    }
}

// MARK: - Sheet parts

/// A sheet's centred title with a round close button (T-17, T-47).
struct SheetTitle: View {
    let title: String
    let close: () -> Void

    var body: some View {
        ZStack {
            Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            HStack {
                Spacer()
                Button(action: close) {
                    Image(systemName: "xmark").font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(Nacre.glass))
                        .overlay(Circle().strokeBorder(Nacre.glassEdge, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Close")
            }
        }
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 12)
    }
}

/// A sheet's surface: in light, Iridescent/Light with the Pearl dust, like
/// every page (REFRESH-05: the sheet surface is color/surface/page; it was a
/// pale wash); in dark, the moonlit gradient as before.
struct SheetBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        if scheme == .dark {
            LinearGradient(colors: [Color(hex: 0x1C2F73), Color(hex: 0x12163F)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
        } else {
            NacreBackground()
        }
    }
}

extension Transaction {
    /// Red going out, green coming in, grey when it doesn't count.
    var tone: Color { notCounted ? Pearl.muted : (inflow ? Pearl.moneyIn : Pearl.moneyOut) }
}
