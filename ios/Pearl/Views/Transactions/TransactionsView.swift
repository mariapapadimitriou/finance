import SwiftUI

/// Cash flow (THL-122, T-01; CF-SCROLL T-01s): every transaction in one
/// list, newest first, a divider per month, under the chosen month's card
/// (Spent, Came in and Leftover), with search (T-45), Filters (T-17), By category (T-18) and
/// each category's page (T-46), Choose a month
/// (T-47), the bank's state: syncing, failed, disconnected (T-36, T-58, T-59),
/// Select (T-19): a category, a tag or Not counted for several at once
/// (T-51, T-20), with one Undo; and Add a transaction by hand (T-23).
@MainActor
struct TransactionsView: View {
    @EnvironmentObject private var app: AppModel
    @StateObject private var plaid = PlaidLinker()

    @State private var months: [String] = []
    /// The month the card is about (T-47): only its summary follows it.
    @State private var month: String?
    /// CF-SCROLL: every month's rows loaded so far (or what a server-side
    /// filter keeps), newest first; older pages come as she scrolls.
    @State private var rows: [Transaction] = []
    /// How many lines the server has in all, for the next page.
    @State private var total = 0
    @State private var loadingMore = false
    /// Bumped by each fresh load, so an older one's pages are dropped.
    @State private var loadGen = 0
    /// The folding bar and the pin's position, apart from this view's state.
    @State private var tracker = CFScrollTracker()
    /// `shown`, the blocks, the paid-back names and the filter's accounts,
    /// worked out once per change of what they're made from, not on every
    /// read (perf rehaul, 2026-11-19): one body pass read `shown` half a
    /// dozen times, each a filter and a sort of every row.
    @State private var memo = CFMemo()
    /// Arrivals merged into a transfer line in `rows`, for a filter that
    /// keeps only that end (TransferEnds, 2026-11-15).
    @State private var merged: [Transaction] = []
    @State private var monthTotals: TransactionList.Totals?
    @State private var owed: Set<String> = []
    /// "Sam and Dad · 2 · $106.06", over By category.
    @State private var owedLine: OwedLine?
    @State private var tags: [String] = []
    private var categories: [CategoryList.Category] { app.categories }
    @State private var accounts: [AccountsOverview.Account] = []
    /// AP-CashFlow (r7): the card's count is its month's own; the tab badge
    /// still counts everything.
    @State private var lookByMonth: [String: Int] = [:]
    /// The card's "need a look" row opens the Needs a look page.
    @State private var showingLook = false
    /// T-01r: the card's "How it adds up".
    @State private var showingAddsUp = false
    @State private var loadedOnce = false
    @State private var error: String?

    @State private var query = ""
    @FocusState private var searching: Bool
    /// What the search found across every month; nil while not searching.
    @State private var results: [Transaction]?
    @State private var resultsMerged: [Transaction] = []

    @State private var filters = TxFilters()
    /// T-67 (CF-SCROLL): Spent, Saved or Came in tapped on the
    /// card: that month and kind, with its chip under the card.
    @State private var cardFilter: CardFilter?
    /// That figure's rows, exactly those the card adds up (the server's
    /// `kind=`); nil while they load.
    @State private var cardRows: [Transaction]?
    @State private var loadedCard: CardFilter?
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
    /// Leave out picked from Mark as… (TR-07 with guesses): asked once that sheet has gone.
    @State private var leaveOutNext = false
    /// TR-07 › TR-08: Make a trip of the picked rows, and its name.
    @State private var makingTrip = false
    @State private var tripName = ""
    @State private var busy = false
    @State private var toast: Toast?
    /// Cash flow's name in `app.changed(by:)` (perf rehaul, 2026-11-19): an
    /// edit made here, or on a page pushed from here, is shown here already,
    /// so this screen isn't fetched again for it.
    static let screenKey = "cashflow"
    /// T-23: adding one by hand.
    @State private var adding = false

    /// TR-11 / TR-12: Select for one trip, opened from its options (TR-04);
    /// nil for Cash flow itself.
    let tripPick: TripPick?
    @Environment(\.dismiss) private var dismiss
    /// TR-12 with every row picked ends the trip, so TR-13 asks first.
    @State private var endingTrip = false
    /// TR-02c: the trip just made; its page opens once TR-08 has gone.
    @State private var madeTrip: String?
    @State private var openTrip: String?

    init(tripPick: TripPick? = nil) {
        self.tripPick = tripPick
        _selecting = State(initialValue: tripPick != nil)
        // TR-11 / TR-12: the month the trip starts in, as its frames show.
        _month = State(initialValue: tripPick.map { String($0.trip.start.prefix(7)) })
    }

    private var inTrip: Bool { tripPick != nil }

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
        scroll
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 0) {
                toastView
                if selecting { selectionBar }
            }
        }
        .nacreScreen(inTrip ? .flat : .wash)
        // Pinned over the scroll and its folding bar, so it stays put when
        // the title folds. G1-Select: while selecting, the circle goes; a
        // trip's pick (TR-11, TR-12) keeps it, but only Select answers.
        .modifier(CFProfileSlot(tracker: tracker, shown: !selecting || inTrip, enabled: !inTrip))
        .navigationBarHidden(true)
        .onChange(of: selecting) { on in if !inTrip { app.hidesTabBar = on } }
        .onDisappear { if !inTrip { app.hidesTabBar = false } }
        .modifier(HidesTabBar(on: inTrip))
        .sheet(isPresented: $adding) {
            AddTransactionSheet(api: app.api, categories: categories) { said in
                adding = false
                withAnimation { toast = Toast(title: said, undo: nil) }
                app.changed()
            }
        }
        .sheet(item: $bulk, onDismiss: {
            if leaveOutNext { leaveOutNext = false; leavingOut = true }
        }) { which in
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
                              notSpending: (deposits ? CaseTile.notIncomeTogether : CaseTile.notSpending)
                                  + (guesses > 0 ? [CaseTile.leaveOut] : []),
                              startNotSpending: true, onCase: { key, _ in
                    bulk = nil
                    if key == CaseTile.leaveOut.key {
                        // TR-07: with Confirm on the bar, Leave out moves under Mark as….
                        leaveOutNext = true
                        return
                    }
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
        .sheet(isPresented: $leavingOut) {
            // T-77c / T-77c2 (G1-PConfirm, rethought): a reason only if she
            // wants to give one, behind "Add a reason"; Leave out acts at once.
            let n = picked.count
            PearlConfirmSheet(overline: "Leave out · \(n) selected",
                              title: n == 1 ? "Leave out 1 transaction?" : "Leave out \(n) transactions?",
                              message: n == 1 ? "It’s left out of all your numbers. You can put it back from its page."
                                              : "They’re left out of your numbers. You can put any back from its page.",
                              field: .init(label: "Why?", prompt: "Say why, so you can tell later",
                                           needs: .nothing, identifier: "leave-out-reason", reveal: "Add a reason"),
                              text: $leaveReason,
                              primary: n == 1 ? "Leave out" : "Leave out \(n)", busyLabel: "Leaving out…",
                              failure: "Couldn’t leave \(n == 1 ? "it" : "them") out. Nothing changed. Try again.",
                              onClose: { leavingOut = false; leaveReason = "" }) {
                try await leaveOut()
                leavingOut = false
            }
        }
        .sheet(isPresented: $makingTrip, onDismiss: {
            // TR-02c: the new trip's page, under its toast.
            if let id = madeTrip { madeTrip = nil; openTrip = id }
        }) {
            // TR-08 (1331:6480) from TR-07's Make a trip.
            NameTripSheet(count: picked.count, dates: pickedDates,
                          total: pickedAmount.replacingOccurrences(of: "\u{2212}", with: ""),
                          months: pickedMonths, name: $tripName, onClose: { makingTrip = false }) { name in
                let reply: TripReply = try await app.api.post("api/trips", ["ids": Array(picked), "name": name])
                if let trip = reply.trip {
                    // TR-02c (1347:74145): "Trip to Montréal made · 23 transactions" ·
                    // Undo takes the trip and its tag away, and doesn't count
                    // as skipping its dates (DELETE ?undo=1).
                    let api = app.api, id = trip.id
                    app.say("\(trip.name) made · \(trip.count) transaction\(trip.count == 1 ? "" : "s")") {
                        let _: OK = try await api.delete("api/trips/\(id)", query: ["undo": "1"])
                    }
                    madeTrip = trip.id
                }
                makingTrip = false
                endSelecting()
                app.changed()
                await reload()
            }
        }
        .sheet(isPresented: $endingTrip) {
            // TR-12 with every row picked: that's TR-13 (1347:75171).
            if let p = tripPick {
                NotATripSheet(trip: p.trip, onClose: { endingTrip = false }) {
                    endingTrip = false
                    dismiss()
                }
            }
        }
        .navigationDestination(isPresented: Binding(get: { openTrip != nil }, set: { if !$0 { openTrip = nil } })) {
            if let id = openTrip { TripPage(id: id) }
        }
        // G1-NeedsALook: the card's "need a look" row; its Quick sort card sorts them.
        .navigationDestination(isPresented: $showingLook) { ReviewView() }
        .navigationDestination(isPresented: $showingAddsUp) { AddsUpView() }
        .navigationDestination(for: Transaction.self) { t in
            TransactionDetailView(transaction: t, categories: categories, siblings: rows)
        }
        .refreshable {
            if !inTrip { await runSync(force: true) }
            await reload()
        }
        .reloads(key: Self.screenKey) { await start() }
        .task(id: query) { await search() }
        .onReceive(app.$changedRows) { changed in
            // The rows a write touched, wherever it was made (a detail page,
            // Needs a look): swapped in here, no fetch.
            if let changed = changed { absorb(changed) }
        }
        .onReceive(CashFlowFocus.shared.$request) { request in
            guard let request = request, !inTrip else { return }
            CashFlowFocus.shared.request = nil
            focus(on: request)
        }
        .sheet(isPresented: $showFilters) {
            // fix/filters-expanded: the old sheet, opened expanded. Its
            // Month keeps the list to one month (the card's chooser is
            // apart); "Show N" counts every month, once every page is here.
            FilterSheet(filters: filters, months: months, accounts: filterAccounts,
                        categories: allCategories, tags: tags,
                        counted: rows.count >= total || inTrip,
                        count: { visible(applying: $0).count }) { chosen in
                showFilters = false
                let reload = chosen.needsServer != filters.needsServer
                filters = chosen
                if reload { Task { await self.reload() } }
            }
        }
        .sheet(isPresented: $showMonths) {
            // T-47 (CF-SCROLL): choosing a month changes only the card.
            MonthSheet(months: months, current: month) { chosen in
                showMonths = false
                if chosen != month {
                    month = chosen
                    Task { await loadCard() }
                }
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
        // Detail pages pushed from here count their edits as Cash flow's own.
        .environment(\.screenKey, Self.screenKey)
    }

    /// CashFlowFocus: Cash flow filtered to one category, every month, as if
    /// she had picked it in Filters; its chip takes it off. A month given
    /// puts the card on that month.
    private func focus(on request: CashFlowFocus.Request) {
        let reload = filters.needsServer
        query = ""
        searching = false
        showCalendar = false
        cardFilter = nil
        filters = TxFilters(categories: [request.category])
        if let m = request.month, m != month { month = m; Task { await loadCard() } }
        if reload { Task { await self.reload() } }
    }

    // MARK: The scroll (CF-SCROLL)

    /// The top (title, search, tabs, the card) then the list as lazy blocks,
    /// with the folding bar and the pinned month over it.
    private var scroll: some View {
        ScrollView {
            LazyVStack(alignment: .leading, spacing: 0) {
                top.padding(.horizontal, Pearl.gutter)
                if showsBlocks {
                    ForEach(blocks) { block in
                        blockView(block).padding(.horizontal, Pearl.gutter)
                    }
                    listFoot.padding(.horizontal, Pearl.gutter)
                }
            }
            .padding(.bottom, 32)
        }
        .coordinateSpace(name: CFScroll.space)
        .scrollDismissesKeyboard(.interactively)
        .onPreferenceChange(CFTopEdgeKey.self) { tracker.top($0) }
        .onPreferenceChange(CFMonthEdgeKey.self) { tracker.months($0) }
        .overlay(alignment: .top) {
            if !selecting && !inTrip && !noTransactionsYet && !showCalendar {
                CFFoldedBar(tracker: tracker, filtersOn: filtersOn, chips: inSearch ? [] : chipItems,
                            filters: { showFilters = true }, add: { adding = true })
            }
        }
        .onChange(of: needsEverything) { on in if on { Task { await loadRest() } } }
        .onChange(of: cardFilter) { _ in Task { await loadCardRows() } }
    }

    /// Title, search, tabs, chips, the card, the bank, and the list's own
    /// states (loading, empty, error) or the calendar.
    @ViewBuilder private var top: some View {
        VStack(alignment: .leading, spacing: 0) {
            // A+ (AP-CashFlow, kit `.hdr`): Cash flow in Fraunces 34, level
            // with the profile circle (`ProfileSlot`), which `body` pins over
            // the page; the row keeps its place empty.
            HStack(alignment: .center) {
                Text("Cash flow").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .padding(.leading, 4)
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 8)
                Color.clear.frame(width: ProfileSlot.size - 4, height: ProfileSlot.size)
            }
            .frame(minHeight: ProfileSlot.size)
            // AP-CashFlow: the title row is 16 down (Home's is 6).
            .padding(.top, ProfileSlot.cashFlowTop)
            if noTransactionsYet {
                emptyLedger
            } else if selecting && !inTrip {
                // G1-Select: "3 selected · $89.00   Cancel" under the
                // title, then the days with a tick on each row.
                listHeader.padding(.top, 14)
                listState.padding(.top, 16)
            } else {
                // TR-11 / TR-12: Cash flow as it is, but only the trip's
                // Select answers taps; search, the tabs and the month wait.
                searchRow.disabled(inTrip).padding(.top, 14).cfTopEdge()
                tabs.disabled(inTrip).padding(.top, 14)
                // T-45 (G1-Search): the card hides while she searches.
                if !showCalendar && !inSearch { summaryCard.allowsHitTesting(!inTrip).padding(.top, 16) }
                // T-67 (G1-Months): the card's chip and Filters' chips, under the card.
                if !showCalendar && !inSearch && !chipItems.isEmpty { CFChipWrap(chips: chipItems).padding(.top, 12) }
                if !inSearch && !inTrip { bankState }
                if showCalendar && !inSearch {
                    // Calendar stays as it is; its month is the card's.
                    CalendarCard(month: month ?? Format.thisMonth(), categories: categories) { m in
                        month = m
                        Task { await loadCard() }
                    }
                    .padding(.top, 16)
                } else {
                    // T-01r: under Newest each month's first day carries
                    // Select, so the plain list has no header of its own.
                    if !selectOnFirstDay { listHeader.padding(.top, 24) }
                    listState.padding(.top, selectOnFirstDay ? 24 : 8)
                }
            }
        }
    }

    /// Whether the rows show as blocks (not the calendar, a state or nothing).
    private var showsBlocks: Bool {
        guard !noTransactionsYet, !(showCalendar && !inSearch), !(inSearch && query.isEmpty) else { return false }
        if !inSearch && !loadedOnce || inSearch && results == nil { return false }
        return !shown.isEmpty
    }

    /// The list as months, days and cards, newest month first.
    private var blocks: [CFBlock] {
        // The first month's divider is left out when it's this month: the
        // card above already names it (AP-CashFlow, G1-Category). A search
        // shows every month's (G1-Search), and so does a month picked in
        // Filters: its rows sit under its divider.
        let shown = self.shown
        let first = shown.first.map { String($0.date.prefix(7)) }
        let key = CFMemo.BlocksKey(shown: shown, sort: filters.sort, byDay: byDay, byCategory: byCategory,
                                   hideFirst: !inSearch && filters.month == nil && first == Format.thisMonth(),
                                   select: !selecting && !inTrip && !inSearch && (!byCategory || owedLine == nil))
        return memo.blocks(key) {
            CFBlock.build(key.shown, sort: key.sort, byDay: key.byDay, byCategory: key.byCategory,
                          hideFirst: key.hideFirst, select: key.select)
        }
    }

    @ViewBuilder private func blockView(_ block: CFBlock) -> some View {
        switch block {
        case .divider(let month, let shown):
            CFMonthDivider(month: month, shown: shown)
        case .day(let month, let title, let select):
            // T-01r, A+ (kit `.label`): 24 above and 8 below; TEST-14:
            // Select is 44 pt to tap, drawn at 18.
            APSectionLabel(text: title, action: select ? "Select" : nil) { selecting = true }
                .padding(.top, 24).padding(.bottom, 8)
                .accessibilityIdentifier("day-header")
                .cfMonthEdge(month)
        case .group(let month, let title, let sum):
            APSectionLabel(text: title, action: nil)
                .overlay(alignment: .trailing) {
                    Text(Format.whole(sum)).font(Nacre.label).foregroundColor(Pearl.muted).padding(.trailing, 4)
                }
                .padding(.top, 24).padding(.bottom, 8)
                .cfMonthEdge(month)
        case .rows(let month, _, let rows, let top, let bottom):
            if top && bottom {
                APCard { OwnBody { dayRows(rows) } }
                    .padding(.top, byDay || filters.sort == .merchant ? 0 : 12)
                    .cfMonthEdge(month)
            } else {
                // Q4: a long card's slice; the line between slices is drawn
                // as any other row's.
                VStack(alignment: .leading, spacing: 0) {
                    if !top { APSeparator().padding(.leading, selecting ? 34 : 0) }
                    OwnBody { dayRows(rows) }
                }
                .modifier(CFCardSlice(top: top, bottom: bottom))
                .padding(.top, top && !(byDay || filters.sort == .merchant) ? 12 : 0)
                .cfMonthEdge(month)
            }
        case .kind(let month, _, let title, let select):
            APSectionLabel(text: title, action: select ? "Select" : nil) { selecting = true }
                .padding(.top, 24).padding(.bottom, 8)
                .cfMonthEdge(month)
        case .categories(let month, let key, let lines):
            categoryCard(month: month, key: key, lines: lines).cfMonthEdge(month)
        }
    }

    /// Older pages as she nears the end; a spinner while one comes.
    @ViewBuilder private var listFoot: some View {
        if !inSearch && !inTrip && rows.count < total {
            HStack { Spacer(); CFSpinner(); Spacer() }
                .frame(minHeight: 64)
                .onAppear { Task { await loadMore() } }
                .accessibilityLabel("Loading earlier transactions")
        }
    }

    /// Everything must be here: a filter, a sort, a card chip, or Filters
    /// open (its "Show N" counts every month).
    private var needsEverything: Bool {
        !inTrip && (filters.isActive || filters.sort != .newest || showFilters)
    }

    /// Each thing narrowing the list, as a chip with its ✕ (cf.css `.fchip`).
    private var chipItems: [CFChipItem] {
        var out: [CFChipItem] = []
        if let c = cardFilter {
            out.append(CFChipItem(id: "card", label: c.label) { cardFilter = nil })
        }
        for chip in filters.chips(accounts: filterAccounts) {
            out.append(CFChipItem(id: chip.id, label: chip.label) {
                let reload = chip.needsServer
                filters.remove(chip.id)
                if reload { Task { await self.reload() } }
            })
        }
        return out
    }

    // MARK: Search

    private var inSearch: Bool { searching || !query.isEmpty }

    /// T-54: "No money came into TD Visa." (CF-SCROLL: every month, so no
    /// "this month"); a card chip says its month: "Nothing spent in November."
    private var noMatchLine: String {
        if let c = cardFilter, !filters.isActive { return c.nothingLine }
        let account = filters.accounts.count == 1 ? filterAccounts.first { filters.accounts.contains($0.id) }?.label : nil
        if let account = account, filters.types == ["income"] { return "No money came into \(account)." }
        if let account = account, filters.types == ["spending"] { return "Nothing was spent on \(account)." }
        if let account = account { return "Nothing on \(account) matches." }
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
            // REDESIGN-09: search is a visible well (kit `.search`), a capsule.
            .wellStyle(focused: searching, capsule: true)
            .contentShape(Capsule())
            .onTapGesture { searching = true }

            if inSearch {
                Button("Cancel") {
                    query = ""
                    searching = false
                }
                .font(Nacre.body)
                .foregroundColor(Pearl.link)
                .frame(minHeight: 44)
                .padding(.leading, 4)
            } else {
                // `.glassbtn`; A+ decision: the filters-on dot is ink, not red.
                CFGlassButton(label: filtersOn ? "Filters, on" : "Filters", action: { showFilters = true }) {
                    Image(systemName: "slider.horizontal.3").font(.system(size: 17))
                }
                .overlay(alignment: .topTrailing) {
                    if filtersOn {
                        Circle().fill(Pearl.ink).frame(width: 8, height: 8)
                            .overlay(Circle().strokeBorder(APlus.circleDisc, lineWidth: 2).padding(-2))
                            .offset(x: -3, y: 3)
                            .accessibilityHidden(true)
                    }
                }
                // TEST-46: Add a transaction (T-23) in reach from the top.
                CFGlassButton(label: "Add a transaction", action: { adding = true }) {
                    Image(systemName: "plus").font(.system(size: 17, weight: .semibold))
                }
                .accessibilityIdentifier("add-transaction")
            }
        }
        .animation(.easeOut(duration: 0.2), value: inSearch)
    }

    /// Transactions · Calendar, kit `.seg` (TEST-32: the chosen half is
    /// color/surface/card, so the ink word reads in both; TEST-14: 44 to tap).
    private var tabs: some View {
        CFSegmented(options: [(false, "Transactions"), (true, "Calendar")], selection: $showCalendar)
    }

    // MARK: The month

    /// T-01r (TEST-05, REFRESH-00 decision 1), A+ (AP-CashFlow, G1-Over):
    /// the month and Came in, Leftover as the one headline in Fraunces 44, a
    /// bar of Spent (plum) / Saved (green) / Leftover (track), its legend,
    /// and "6 need a look", which opens Needs a look. Red only for over.
    private var summaryCard: some View {
        // T-67 (TEST-34): a filter or a search never changes the month
        // card; it is always the month's own Came in, Leftover and legend.
        // (Narrowed totals gave "Came in $0", Leftover "—" and "Leftover $0".)
        let spent = monthTotals?.spent ?? 0
        let income = monthTotals?.income ?? 0
        let saved = monthTotals?.saved ?? 0
        // T-01r3 (TEST-05, section 20): before this month's pay is in, the
        // headline is "Spent so far" in ink and the pay still to come shows,
        // not a red Over measured against money that hasn't come yet.
        let pay = monthTotals?.pay
        return APCard {
            if let allowance = monthAllowance {
                // T-01r, refined 2026-11-22 (n-cf-meter): this month is Home's
                // Allowance, Left and the meter; How it adds up on the card.
                OwnBody {
                    AllowanceMonthSummary(month: month.map { Format.monthName($0) } ?? "This month",
                                          monthSpoken: month.map { Format.month($0) } ?? "",
                                          canPick: !months.isEmpty, allowance: allowance,
                                          pickMonth: { showMonths = true })
                }
                Rectangle().fill(APlus.separator).frame(height: 0.5).accessibilityHidden(true)
                AddsUpRow { showingAddsUp = true }
            } else {
                OwnBody {
                    MonthSummary(month: month.map { Format.monthName($0) } ?? "This month",
                                 monthSpoken: month.map { Format.month($0) } ?? "",
                                 canPick: !months.isEmpty,
                                 spent: spent, income: income, saved: saved, pay: pay,
                                 picked: cardFilter.flatMap { $0.month == month ? $0.kind : nil },
                                 pick: { pickOnCard($0) },
                                 pickMonth: { showMonths = true })
                }
            }
            OwnBody { needsALookRow }
        }
    }

    /// The Allowance, when the card is on its month (the app's, moved by
    /// every write). A month that's over has none, so it keeps Came in and
    /// Leftover (G1-Months), as does a month without income.
    private var monthAllowance: Allowance? {
        guard let a = app.allowance, a.hasGauge, let m = month, a.month == m else { return nil }
        return a
    }

    /// T-67 (CF-SCROLL): a figure on the card narrows the list to its month
    /// and kind; tapped again, or its chip's ✕, shows everything again.
    private func pickOnCard(_ kind: CardKind) {
        guard let m = month else { return }
        let next = CardFilter(month: m, kind: kind)
        cardFilter = cardFilter == next ? nil : next
    }

    /// The month's own count (AP-CashFlow r7: 6 on the card, 8 on the tab).
    /// The whole row opens the Needs a look page, as usual (all months: the
    /// page has no month filter); Quick sort is its top card. No streak.
    @ViewBuilder private var needsALookRow: some View {
        Rectangle().fill(APlus.separator).frame(height: 0.5).accessibilityHidden(true)
        let count = month.flatMap { lookByMonth[$0] } ?? 0
        if count > 0 {
            CFLookRow(count: count) { showingLook = true }
        } else {
            // T-48 (G1-Months): "✓ All sorted" in teal, a 52 pt row.
            HStack(spacing: 8) {
                Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).accessibilityHidden(true)
                Text("All sorted").font(Nacre.body)
            }
            .foregroundColor(Nacre.teal)
            .padding(.horizontal, 16).frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .accessibilityElement(children: .combine)
        }
    }

    // MARK: The bank

    /// Getting the latest (T-58), couldn't (T-59), or a bank to sign in to
    /// again (T-36).
    @ViewBuilder private var bankState: some View {
        ForEach(disconnected, id: \.itemId) { bank in
            // G1-Over: the caution icon, the bank and when it last updated,
            // then the rose Reconnect.
            APCard {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(alignment: .center, spacing: 12) {
                        Image(systemName: "link").font(.system(size: 15, weight: .medium))
                            .foregroundColor(Pearl.caution)
                            .frame(width: 36, height: 36)
                            .background(Circle().fill(Pearl.cautionBackground))
                            .accessibilityHidden(true)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(bank.name) is disconnected").font(Nacre.body).foregroundColor(Pearl.ink)
                            Text(bank.updated).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                    }
                    Button("Reconnect") { Task { await reconnect(bank.itemId) } }
                        .buttonStyle(APPrimaryButtonStyle(busy: reconnecting == bank.itemId))
                        .disabled(reconnecting != nil)
                }
                .padding(.horizontal, 16).padding(.vertical, 14)
            }
            .padding(.top, 12)
        }
        // G1-Over: kit `.banner` (champagne), with Try again as a quiet link.
        switch sync {
        case .syncing:
            CFBanner(text: "Getting your latest transactions…", busy: true).padding(.top, 12)
        case .failed:
            CFBanner(text: "Couldn’t update just now.") {
                Button("Try again") { Task { await runSync(force: true) } }
                    .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.link)
                    .frame(minHeight: 44)
            }
            .padding(.top, 12)
        case .idle:
            EmptyView()
        }
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

    /// The list's header. A+: a section label (kit `.label`, "3 RESULTS")
    /// with its quiet action; while selecting (G1-Select) "3 selected ·
    /// $89.00" in 17 semibold ink with Cancel in `link`.
    @ViewBuilder private var listHeader: some View {
        if let p = tripPick {
            // TR-11 (1347:74377): "2 to add · Mar 1–12" · Cancel; TR-12
            // (1347:74773): "2 selected · they stay in March" · Done.
            switch p.kind {
            case .add:
                selectHeader("\(picked.count) to add · \(Format.span(p.window.start, p.window.end))", "Cancel") {
                    dismiss()
                }
            case .remove:
                selectHeader("\(picked.count) selected · they stay in \(picked.isEmpty ? p.trip.months : pickedMonths)",
                             "Done") { dismiss() }
            }
        } else if selecting {
            selectHeader("\(picked.count) selected · \(pickedAmount.replacingOccurrences(of: "\u{2212}", with: ""))",
                         "Cancel") { endSelecting() }
        } else if inSearch {
            if results != nil {
                APSectionLabel(text: shown.count == 1 ? "1 result" : "\(shown.count) results")
            }
        } else if loadedOnce && !byCategory {
            APSectionLabel(text: shown.count == 1 ? "1 transaction" : "\(shown.count) transactions",
                           action: shown.isEmpty ? nil : "Select") { selecting = true }
        }
    }

    /// G1-Select's header: what's picked, and how to stop.
    private func selectHeader(_ text: String, _ action: String, _ run: @escaping () -> Void) -> some View {
        HStack {
            Text(text).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.8)
            Spacer(minLength: 8)
            Button(action, action: run)
                .font(Nacre.body).foregroundColor(Pearl.link)
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .padding(.horizontal, 4)
    }

    /// The list's own states: loading, couldn't load, nothing to show. The
    /// rows themselves are the lazy blocks under the top (CF-SCROLL).
    @ViewBuilder private var listState: some View {
        if inSearch && query.isEmpty {
            EmptyView()
        } else if (!loadedOnce && !inSearch) || (inSearch && results == nil) {
            // T-35l (G1-Results): the rows hold their place while they load.
            CFLoadingRows()
        } else if let error = error, shown.isEmpty {
            // T-35e (G1-Results): the caution icon, the reason, a Secondary Try again.
            CFState(title: "Couldn’t load your transactions", line: error, action: "Try again", warn: true) {
                Task { await reload() }
            }
        } else if shown.isEmpty {
            if inSearch {
                // G1-Empty: "No matches · Try another word. · Clear search".
                CFState(title: "No matches", line: "Try another word.", action: "Clear search") { query = "" }
            } else if filters.isActive || cardFilter != nil {
                if cardFilter == nil && rows.count < total || cardFilter != nil && cardRows == nil {
                    CFLoadingRows()
                } else {
                    CFState(title: "Nothing matches", line: noMatchLine, action: "Clear filters") {
                        let reload = filters.needsServer
                        filters = TxFilters(sort: filters.sort)
                        cardFilter = nil
                        if reload { Task { await self.reload() } }
                    }
                }
            } else {
                // CF-SCROLL: one list for every month, so no month in the words.
                CFState(title: "Nothing yet", line: "Transactions show up here as your bank sends them.")
            }
        } else if byCategory, let line = owedLine {
            owedSection(line)
        }
    }

    /// One card's rows (its own body, stack check): a face, the name over
    /// its line, the amount on the right edge; ticks while selecting.
    @ViewBuilder private func dayRows(_ rows: [Transaction]) -> some View {
        ForEach(Array(rows.enumerated()), id: \.element.id) { index, t in
            // G1-Select: the line starts under the name, past the tick.
            if index > 0 { APSeparator().padding(.leading, selecting ? 34 : 0) }
            if selecting {
                Button { toggle(t) } label: {
                    TransactionRow(t: t, paidBack: paidBack(for: t), picked: picked.contains(t.id),
                                   showsDay: !byDay, showsTrip: !inTrip)
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(picked.contains(t.id) ? .isSelected : [])
            } else {
                NavigationLink(value: t) {
                    TransactionRow(t: t, paidBack: paidBack(for: t), showsDay: !byDay,
                                   onConfirm: { Task { await confirmGuess(t) } })
                }
                .buttonStyle(.plain)
            }
        }
    }

    // MARK: By category (T-18)

    /// Sorting by category shows the categories themselves, not their rows.
    private var byCategory: Bool { filters.sort == .category && !inSearch && !selecting }

    /// A filter is on, or the list is sorted some other way: the dot, and
    /// the chips to take each off.
    private var filtersOn: Bool { filters.isActive || filters.sort != .newest }

    /// Owed to you, over the months' categories (G1-Category: kit `.label`,
    /// then a card of icon rows with the total). It isn't a month's.
    private func owedSection(_ line: OwedLine) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            categoryHeading("Owed to you", first: true)
            APCard {
                NavigationLink { OwedView() } label: {
                    categoryRow(line.names.joined(separator: " and "), symbol: "person.2",
                                count: line.count, total: line.total)
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// One month's Spent, Money in or Not counted, by category; each opens
    /// its page for that month (T-46).
    private func categoryCard(month: String, key: String, lines: [CFCategoryLine]) -> some View {
        APCard {
            ForEach(Array(lines.enumerated()), id: \.element.id) { i, c in
                if i > 0 { APSeparator() }
                NavigationLink {
                    CategoryPage(name: c.name, month: month, counts: key, rows: c.rows, total: c.total)
                } label: {
                    categoryRow(c.name, symbol: CategorySheet.symbol(for: c.name),
                                count: c.rows.count, total: c.total)
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// "SPENT   Select": the first heading carries Select, as the day's does.
    private func categoryHeading(_ text: String, first: Bool) -> some View {
        APSectionLabel(text: text, action: first && !inTrip ? "Select" : nil) { selecting = true }
            .padding(.top, 24).padding(.bottom, 8)
    }

    /// G1-Category: "🛒 Groceries / 6 transactions        $412".
    private func categoryRow(_ name: String, symbol: String, count: Int, total: Double) -> some View {
        HStack(spacing: 12) {
            CFIcon(symbol: symbol)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(count == 1 ? "1 transaction" : "\(count) transactions")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(Format.whole(total)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
        }
        .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    // MARK: Select (T-19)

    /// T-77: Category, Mark as…, Confirm (Pearl's guesses, when some are)
    /// and Leave out, where the tab bar was. Tag waits while tags are off
    /// (THL-286), as on the web. TR-07 (1331:5763): Make a trip comes third.
    /// With Confirm on the bar Leave out moves under Mark as… (engBOT, Trips
    /// build); TR-15: Leave out is the last tile of Mark as…'s Not spending
    /// grid. TR-11 / TR-12: one action.
    ///
    /// A+ (G1-Select, kit `.selbar`): a floating card 12 in from the sides,
    /// radius 28, the actions as 40 pt chips; TR-07 (G7-TripMore): Make a
    /// trip takes its own row in rose, and Confirm its own row under it.
    private var selectionBar: some View {
        VStack(spacing: 8) {
            if let p = tripPick {
                barButton(p.kind == .add ? "Add \(picked.count) to the trip" : "Remove \(picked.count) from the trip",
                          on: true) {
                    tripChange(p)
                }
            } else {
                // TR-07 (G7-TripMore, kit `.selbar`): Category and Mark as… on
                // the first row, Make a trip on its own row in rose, then
                // Confirm on its own row.
                HStack(spacing: 8) {
                    barButton("Category") { bulk = .category }
                    barButton("Mark as…") { bulk = .mark }
                    if guesses == 0 {
                        barButton("Leave out") { leavingOut = true }
                    }
                    // Cancel lives in the list's header too, but Select is
                    // offered on every day's heading, and from far down the
                    // page the header is out of sight (2026-11-20): the bar
                    // has to let her out as well.
                    barButton("Cancel") { endSelecting() }
                }
                barButton("Make a trip", on: true) { tripName = ""; makingTrip = true }
                if guesses > 0 {
                    barButton("Confirm \(guesses)") {
                        let ids = pickedRows.filter(\.suggested).map(\.id)
                        Task { await change(["ids": ids], path: "api/transactions/batch/confirm") }
                    }
                }
            }
        }
        .padding(10)
        .background(SelectionBarSurface())
        .padding(.horizontal, 12).padding(.bottom, 8)
    }

    /// Pearl's guesses among the picked rows, for Confirm.
    private var guesses: Int { pickedRows.filter(\.suggested).count }

    /// kit `.selbar .chip`: 40 high, `chip` (or `action` when it's the one
    /// to press), 15 pt medium.
    private func barButton(_ title: String, on: Bool = false, _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            Text(title).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(on ? Pearl.onAction : Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.75)
                .padding(.horizontal, 8)
                .frame(maxWidth: .infinity, minHeight: 40)
                .background(Capsule().fill(on ? Pearl.action : APlus.chip))
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(picked.isEmpty || busy)
        .opacity(picked.isEmpty ? 0.4 : 1)
    }

    /// "✓ Changed 3 to Dining out. Allowance is now $842.  Undo". UN-01: the
    /// one Undo look (PearlToast's ink), 12 above the tab bar.
    @ViewBuilder private var toastView: some View {
        if let toast = toast {
            UndoToast(text: toast.title, undo: toast.undo == nil ? nil : { Task { await undo() } }) {
                if self.toast == toast { withAnimation { self.toast = nil } }
            }
            .padding(.bottom, 12)
        }
    }

    private var pickedRows: [Transaction] { shown.filter { picked.contains($0.id) } }

    /// "−$89.00 · Uber Eats, Shoppers, Sushi Nami" (T-78).
    private var pickedNames: String {
        let names = pickedRows.prefix(3).map { $0.merchant.components(separatedBy: " ").prefix(2).joined(separator: " ") }
        let more = pickedRows.count > 3 ? " and \(pickedRows.count - 3) more" : ""
        return "\(pickedAmount) · \(names.joined(separator: ", "))\(more)"
    }

    /// TR-08's dates: "Mar 3–7".
    private var pickedDates: String {
        let days = pickedRows.map { String($0.date.prefix(10)) }.sorted()
        guard let first = days.first, let last = days.last else { return "" }
        return Format.span(first, last)
    }

    /// TR-08's "They still count in March" (and April…).
    private var pickedMonths: String {
        let months = Set(pickedRows.map { String($0.date.prefix(7)) }).sorted()
        return Format.andList(months.map(Format.monthName))
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

    /// Leave out every picked row, with her reason (T-77c). Throws so the
    /// sheet stays up with its Banner.
    private func leaveOut() async throws {
        // T-77c (rethought): the reason is hers to give; without one the
        // server keeps "Left out" (it needs words to store).
        let typed = leaveReason.trimmingCharacters(in: .whitespaces)
        let reason = typed.isEmpty ? "Left out" : typed
        busy = true
        defer { busy = false }
        let ids = Array(picked)
        for id in ids {
            let _: OK = try await app.api.put("api/transactions/\(id)/exclude", ["reason": reason])
        }
        leaveReason = ""
        endSelecting()
        withAnimation { toast = Toast(title: ids.count == 1 ? "Left out." : "\(ids.count) left out.", undo: nil) }
        app.changed()
        await reload()
    }

    private func endSelecting() {
        selecting = false
        picked = []
    }

    /// TR-11 / TR-12: add the picked rows to the trip, or take them out, then
    /// back to its page with "Added 2 to Trip to Montréal" (or "Removed 2
    /// from …") and an Undo that does the opposite. Picking every row of the
    /// trip would end it, so that asks first, as TR-13.
    private func tripChange(_ p: TripPick) {
        let ids = Array(picked)
        guard !ids.isEmpty, !busy else { return }
        if p.kind == .remove && rows.allSatisfy({ picked.contains($0.id) }) {
            endingTrip = true
            return
        }
        Task {
            busy = true
            defer { busy = false }
            let api = app.api, id = p.trip.id, name = p.trip.name, n = ids.count
            do {
                let _: TripReply = try await api.put("api/trips/\(id)", [p.kind == .add ? "add" : "remove": ids])
                if p.kind == .add {
                    app.say("Added \(n) to \(name)") {
                        let _: TripReply = try await api.put("api/trips/\(id)", ["remove": ids])
                    }
                } else {
                    app.say("Removed \(n) from \(name)") {
                        let _: TripReply = try await api.put("api/trips/\(id)", ["add": ids])
                    }
                }
                app.changed()
                dismiss()
            } catch {
                if let words = app.handle(error) { app.say(words) }
            }
        }
    }

    /// One change for every picked row; the server's words (or `say` and
    /// what it did to the Allowance) and its Undo.
    private func change(_ body: [String: Any], path: String, say: String? = nil) async {
        busy = true
        defer { busy = false }
        var payload = body
        let ids = (body["ids"] as? [String]) ?? Array(picked)
        payload["ids"] = ids
        // Shown at once (perf rehaul, 2026-11-19): a category or a Yes reads
        // on the rows the moment she picks it. The server's own rows replace
        // them when its answer comes; a refusal puts them back.
        let before = (rows, results, cardRows)
        let chosen = Set(ids)
        let name = path.hasSuffix("/category") ? body["category"] as? String : nil
        if name != nil || path.hasSuffix("/confirm") {
            func patched(_ t: Transaction) -> Transaction {
                guard chosen.contains(t.id) else { return t }
                return name.map { t.sorted(as: $0) } ?? t.guessConfirmed()
            }
            withAnimation(.easeInOut(duration: 0.2)) {
                rows = rows.map(patched)
                results = results?.map(patched)
                cardRows = cardRows?.map(patched)
            }
        }
        func restore() { withAnimation { (rows, results, cardRows) = before } }
        do {
            // Through the outbox: sent once with an op id, or queued when the
            // server can't be reached (nil), with what she sees kept.
            let sent: Outbox.Sent<MarkReply>? = try await app.outbox.send("POST", path, payload, rollback: restore)
            endSelecting()
            let reply = sent?.body
            let title = say.map { [$0, reply?.detail ?? ""].filter { !$0.isEmpty }.joined(separator: " ") }
                ?? reply?.title ?? "Changed."
            withAnimation { toast = Toast(title: title, undo: reply?.undo) }
            error = nil
            if let sent = sent { settle(sent.changed) }
        } catch {
            restore()
            self.error = app.handle(error)
        }
    }

    /// Tapping the dotted chip: Pearl's guess is right (2026-11-08).
    private func confirmGuess(_ t: Transaction) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        // The chip reads as hers at once (perf rehaul); back if refused.
        let before = (rows, results, cardRows)
        func patched(_ row: Transaction) -> Transaction { row.id == t.id ? row.guessConfirmed() : row }
        withAnimation(.easeInOut(duration: 0.2)) {
            rows = rows.map(patched)
            results = results?.map(patched)
            cardRows = cardRows?.map(patched)
        }
        func restore() { withAnimation { (rows, results, cardRows) = before } }
        do {
            let sent: Outbox.Sent<MarkReply>? = try await app.outbox.send(
                "POST", "api/transactions/batch/confirm", ["ids": [t.id]], rollback: restore)
            withAnimation {
                toast = Toast(title: sent?.body.title ?? "\(t.merchant) · \(t.label)", undo: sent?.body.undo)
            }
            error = nil
            if let sent = sent { settle(sent.changed) }
        } catch {
            restore()
            self.error = app.handle(error)
        }
    }

    /// A write's `changed` taken in: its rows swapped into the lists here,
    /// the app told (the Allowance, the badge, the other screens' ETag
    /// checks), and this screen left as it is rather than fetched again.
    /// With no envelope, everything reloads as before.
    private func settle(_ changed: Changed?) {
        if let changed = changed { absorb(changed) }
        app.apply(changed, by: Self.screenKey)
    }

    /// Rows a write touched, swapped into every list here. The month card's
    /// totals can move with them: asked again, one small read (304 when
    /// nothing there changed).
    private func absorb(_ changed: Changed) {
        var moved = false
        withAnimation(.easeInOut(duration: 0.2)) {
            if rows.merge(changed) { moved = true }
            // Rows the write made (a deposit's parts, 2026-11-20) join the
            // list too, when it is the plain list; `shown` puts them in place.
            if !inTrip && listQuery.isEmpty {
                let known = Set(rows.map(\.id))
                let new = changed.rows.filter { !known.contains($0.id) }
                if !new.isEmpty { rows.append(contentsOf: new); moved = true }
            }
            if merged.merge(changed) { moved = true }
            if results?.merge(changed) == true { moved = true }
            if cardRows?.merge(changed) == true { moved = true }
        }
        if moved { Task { await loadCard() } }
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
        // G1-Empty: the title in Fraunces 22 and its line, the rose Link your
        // bank, and Add one by hand as a quiet link. No icon, no card.
        VStack(spacing: 6) {
            Text("No transactions yet").font(Nacre.title2).foregroundColor(Pearl.ink)
            Text("Link a bank to see them.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
            Button("Link your bank") { Task { await link() } }
                .buttonStyle(APPrimaryButtonStyle(busy: reconnecting == "new"))
                .disabled(reconnecting != nil)
                .padding(.top, 28)
            // T-35.
            Button("Add one by hand") { adding = true }
                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(Pearl.link)
                .frame(minHeight: 44)
                .padding(.top, 8)
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger).multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 4)
        .padding(.top, 150)
    }

    // MARK: What's shown

    private var noTransactionsYet: Bool { !inTrip && loadedOnce && months.isEmpty && rows.isEmpty && error == nil }

    private var shown: [Transaction] {
        let key = CFMemo.ShownKey(rows: rows, merged: merged, results: results, resultsMerged: resultsMerged,
                                  cardRows: cardRows, cardFilter: cardFilter, inSearch: inSearch,
                                  filters: filters, owed: owed)
        return memo.shown(key) { visible(applying: filters) }
    }

    /// The rows the list shows under these filters and the card's chip:
    /// the search's or every month's, narrowed, then sorted. Grouped by
    /// month afterwards (CFBlock), so each sort stays within its month.
    private func visible(applying f: TxFilters) -> [Transaction] {
        let figure = !inSearch && cardFilter != nil
        let base = inSearch ? (results ?? []) : figure ? (cardRows ?? []) : rows
        let kept: (Transaction) -> Bool = { t in f.matches(t, owed: owed) }
        // A transfer's arrival, where the filter keeps it but not the line
        // it was merged into ("Savings" kept, the line is Chequing's).
        var out = TransferEnds.adding(inSearch ? resultsMerged : figure ? [] : merged, to: base.filter(kept), keep: kept,
                                       id: { $0.id }, line: { $0.mergedInto }, date: { $0.date })
        switch f.sort {
        case .largest: out.sort { $0.amount > $1.amount }
        case .category: out.sort { ($0.label, $1.date) < ($1.label, $0.date) }
        case .merchant: out.sort { ($0.merchant.lowercased(), $1.date) < ($1.merchant.lowercased(), $0.date) }
        case .newest: break
        }
        return out
    }

    /// T-01r: Newest first is a card per day, under its day. A search (T-45)
    /// is a card of results per month, each with its day (G1-Search).
    private var byDay: Bool { filters.sort == .newest && !inSearch }

    /// Newest first: Select sits on each month's first day.
    private var selectOnFirstDay: Bool {
        byDay && !selecting && loadedOnce && !shown.isEmpty
    }

    /// "Paid back · Sushi Nami": the charge a payback is for, when it's in view.
    private func paidBack(for t: Transaction) -> String? {
        // TEST-31 Money back: her share's refund reads "Refund · <shop>".
        guard let id = t.repays, t.refundOf == nil else { return nil }
        // The list's rows first, then the search's, as the scan was.
        return memo.merchants(rows: rows, results: results) {
            Dictionary((rows + (results ?? [])).map { ($0.id, $0.merchant) }, uniquingKeysWith: { first, _ in first })
        }[id]
    }

    /// Every account in the list, named as Accounts names them when it can.
    private var filterAccounts: [FilterAccount] {
        memo.filterAccounts(rows: rows, accounts: accounts) {
            var out: [FilterAccount] = []
            for t in rows {
                guard let id = t.accountId, !id.isEmpty, !out.contains(where: { $0.id == id }) else { continue }
                let linked = accounts.first { $0.id == id }
                out.append(FilterAccount(id: id, label: linked?.label ?? t.account ?? "Account",
                                         joint: linked?.joint == true || !t.joint.isEmpty))
            }
            return out.sorted { $0.label < $1.label }
        }
    }

    /// Every category in the list, most used first.
    private var allCategories: [String] {
        var count: [String: Int] = [:]
        for t in rows { count[t.label, default: 0] += 1 }
        return count.sorted { ($0.value, $1.key) > ($1.value, $0.key) }.map(\.key)
    }

    // MARK: Loading

    /// The months, the count, the accounts and the list, asked for together
    /// (2026-11-08) instead of one after another before the list could start.
    private func start() async {
        if inTrip {
            await reload()
            return
        }
        // Each from its kept answer at once, then the server's if it changed
        // (ScreenStore, perf rehaul 2026-11-19).
        let screens = app.screens
        async let summaryLoad: Bool? = try? screens.load("api/summary", as: Summary.self) { summary in
            months = summary.months ?? []
            let was = month
            if month == nil || !months.contains(month!) { month = summary.latestMonth ?? months.last }
            // The card's numbers come from the kept summary's month at
            // once (2026-11-20), not after the server has confirmed it:
            // "Spent so far" filled in last and moved the page.
            if month != was || monthTotals == nil { Task { await loadCard() } }
        }
        async let reviewLoad: Bool? = try? screens.load("api/review", as: Review.self) { took($0) }
        async let accountsLoad: Bool? = try? screens.load("api/accounts/overview", as: AccountsOverview.self) {
            accounts = $0.linked
        }
        // CF-SCROLL: the list is every month's, so it needn't wait for them.
        async let listed: Void = reload()
        _ = await summaryLoad
        _ = await listed
        _ = await (reviewLoad, accountsLoad)
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

    /// A page of rows; older pages follow as she scrolls (`loadMore`).
    private static let page = 200

    /// The server's own filters (left out, subscriptions), on every page.
    private var listQuery: [String: String] {
        var p: [String: String] = [:]
        if filters.only.contains(.leftOut) { p["excluded"] = "1" }
        if filters.only.contains(.subscriptions) { p["recurring"] = "1" }
        return p
    }

    /// The list from the top, as many rows as were already here (so a
    /// change made deep in the list keeps her place), then the rest if a
    /// filter or a sort needs every month.
    private func reload() async {
        defer { loadedOnce = true }
        if let p = tripPick {
            await reloadTrip(p)
            return
        }
        loadGen += 1
        let gen = loadGen
        // T-01r: the card's Allowance is Home's; opened before Home has
        // loaded, Home's answer seeds it (kept or fresh).
        if app.allowance == nil {
            Task { [app] in _ = try? await app.screens.load("api/home", as: Home.self) { app.seed($0) } }
        }
        let want = max(Self.page, rows.count)
        var got: [Transaction] = []
        var arrivals: [Transaction] = []
        do {
            repeat {
                var p = listQuery
                p["offset"] = String(got.count)
                p["limit"] = String(min(1000, want - got.count))
                let list: TransactionList
                if got.isEmpty {
                    // The first page is kept (ScreenStore): an empty list
                    // shows it the moment the screen opens, and the server
                    // is asked with its ETag.
                    if rows.isEmpty,
                       let kept = await app.screens.cached(TransactionList.self, "api/transactions/list", query: p) {
                        guard gen == loadGen else { return }
                        show(kept)
                    }
                    list = try await app.screens.fetch(TransactionList.self, "api/transactions/list", query: p).value
                } else {
                    list = try await app.api.get("api/transactions/list", query: p)
                }
                guard gen == loadGen else { return }
                if got.isEmpty {
                    owed = Set(list.owedIds)
                    owedLine = list.owedTotal > 0.005
                        ? OwedLine(names: list.owedNames, count: list.owedCount, total: list.owedTotal) : nil
                    tags = list.tags
                }
                got += list.transactions
                arrivals += list.merged
                total = list.total
                if list.transactions.isEmpty { break }
            } while got.count < min(want, total)
            withAnimation(.easeInOut(duration: 0.2)) {
                rows = got
                merged = arrivals
            }
            error = nil
        } catch {
            guard gen == loadGen else { return }
            self.error = app.handle(error)
        }
        if needsEverything { await loadRest() }
        if cardFilter != nil { await loadCardRows() }
    }

    /// The kept first page, as it was, without animation. It counts as
    /// loaded (2026-11-20): the loading rows used to sit over it until the
    /// server answered, then swap for the same rows.
    private func show(_ kept: TransactionList) {
        var quiet = SwiftUI.Transaction()
        quiet.disablesAnimations = true
        withTransaction(quiet) {
            loadedOnce = true
            rows = kept.transactions
            merged = kept.merged
            total = kept.total
            owed = Set(kept.owedIds)
            owedLine = kept.owedTotal > 0.005
                ? OwedLine(names: kept.owedNames, count: kept.owedCount, total: kept.owedTotal) : nil
            tags = kept.tags
        }
    }

    /// A card chip's rows: what the card's Spent, Saved or Came in adds up
    /// for its month, from the server, so they match it exactly (CF-SCROLL).
    private func loadCardRows() async {
        guard let c = cardFilter else { cardRows = nil; return }
        let kind = c.kind.server
        if cardRows == nil || c != loadedCard { cardRows = nil }
        var got: [Transaction] = []
        var p = listQuery
        p["month"] = c.month
        p["kind"] = kind
        p["limit"] = "1000"
        do {
            repeat {
                p["offset"] = String(got.count)
                let list: TransactionList = try await app.api.get("api/transactions/list", query: p)
                guard cardFilter == c else { return }
                got += list.transactions
                if list.transactions.isEmpty || got.count >= list.total { break }
            } while true
            cardRows = got
            loadedCard = c
        } catch {
            guard cardFilter == c else { return }
            self.error = app.handle(error)
            cardRows = []
        }
    }

    /// The next older page, as the end of the list comes into view.
    private func loadMore() async {
        guard !inTrip, !loadingMore, rows.count < total else { return }
        loadingMore = true
        defer { loadingMore = false }
        let gen = loadGen
        var p = listQuery
        p["offset"] = String(rows.count)
        p["limit"] = String(needsEverything ? 1000 : Self.page)
        guard let list: TransactionList = try? await app.api.get("api/transactions/list", query: p),
              gen == loadGen else { return }
        let have = Set(rows.map(\.id))
        rows += list.transactions.filter { !have.contains($0.id) }
        merged += list.merged
        total = list.total
        if list.transactions.isEmpty { total = rows.count }
    }

    /// Every month, for a filter, a sort, a card chip or Filters' count.
    private func loadRest() async {
        while !inTrip && needsEverything && rows.count < total {
            let before = rows.count
            await loadMore()
            if rows.count == before { break }
        }
    }

    /// T-47: the card's month, its own totals (whatever the list shows).
    /// The cards are the month's, whatever the list is narrowed to.
    private func loadCard() async {
        guard !inTrip, let m = month else { return }
        try? await app.screens.load("api/transactions/list", query: ["month": m, "limit": "1"],
                                    as: TransactionList.self) { plain in
            if m == month { monthTotals = plain.monthTotals }
        }
    }

    /// TR-11: every row from the trip's dates ±3 days not already in a trip
    /// (the trip's own are hidden; another trip's can't join this one).
    /// TR-12: the trip's rows. The month card is the trip's first month.
    private func reloadTrip(_ p: TripPick) async {
        let api = app.api
        async let reviewReply: Review? = try? api.get("api/review")
        do {
            switch p.kind {
            case .add:
                let w = p.window
                var all: [Transaction] = []
                var m = String(w.start.prefix(7))
                let last = String(w.end.prefix(7))
                while m <= last {
                    let list: TransactionList = try await api.get("api/transactions/list",
                                                                  query: ["month": m, "limit": "1000"])
                    all += list.transactions
                    if m == month { monthTotals = list.monthTotals }
                    // The 1st plus 31 days is always in the next month.
                    m = String(Format.shiftDay(m + "-01", by: 31).prefix(7))
                }
                let own = Set(p.trip.ids)
                let kept = all.filter {
                    let day = String($0.date.prefix(10))
                    return day >= w.start && day <= w.end && !own.contains($0.id) && $0.trip == nil
                }
                .sorted { $0.date > $1.date }
                withAnimation(.easeInOut(duration: 0.2)) { rows = kept }
            case .remove:
                let d: TripDetail = try await api.get("api/trips/\(p.trip.id)")
                withAnimation(.easeInOut(duration: 0.2)) { rows = d.rows }
                if let month = month {
                    let list: TransactionList? = try? await api.get("api/transactions/list",
                                                                    query: ["month": month, "limit": "1"])
                    monthTotals = list?.monthTotals
                }
            }
            picked = picked.intersection(rows.map(\.id))
            error = nil
        } catch {
            self.error = app.handle(error)
        }
        if let review = await reviewReply { took(review) }
        // TEST-50: Choose a month opens with each month's result already here.
        Task { await MonthSheet.prefetch(app.api) }
    }

    /// "6 need a look" on the card: the month's open questions (no streak).
    private func took(_ review: Review) {
        // TEST-35: the rows Needs a look lists, as its "All" chip, by month
        // (AP-CashFlow r7: the card counts its own month; the badge, all).
        let open = review.shownAsks.filter { !$0.skipped }
        var by: [String: Int] = [:]
        for ask in open { by[String(ask.t.date.prefix(7)), default: 0] += 1 }
        lookByMonth = by
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
            resultsMerged = list.merged
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
    /// T-01r: under a day header the day goes without saying.
    var showsDay = true
    /// Tapping the dotted guess says it's right, without opening the row.
    var onConfirm: (() -> Void)? = nil
    /// TR-05: "Shopping · Trip to Montréal"; not on the trip's own page.
    var showsTrip = true
    /// TR-02m: a row in a trip's other currency says so ("−$142.00 USD").
    var currency: String? = nil

    /// A+ (kit `.row`, APPaymentRow): the 40 pt face, the name (17) over its
    /// line (15 muted), the guess as a dashed chip, every amount on one
    /// right edge in 17 semibold; with a guess the amount lines up with the
    /// name. G1-Select: kit `.seltick` before the face.
    var body: some View {
        HStack(alignment: t.suggested ? .top : .center, spacing: 12) {
            if let picked = picked {
                SelectTick(on: picked).padding(.top, t.suggested ? 9 : 0)
            }
            Initials(name: t.merchant)
            VStack(alignment: .leading, spacing: 2) {
                Text(t.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                if !meta.isEmpty {
                    metaText.font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(splitNote == nil ? 1 : 2)
                }
                if let extra = extra {
                    Text(extra).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                }
                // T-93o: a best guess of Other is a guess like any other, "Other?".
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
            moneyText
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(t.rowTone)
                .lineLimit(1).fixedSize()
                .costCountDown(t.amount)
                .padding(.top, t.suggested ? 9 : 0)
                .accessibilityLabel(t.movedBetweenAccounts
                                    ? Format.movedSpoken(t.amount, to: t.movedTo) : Format.spoken(shownMoney))
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .costSpoken(costSpoken)
        .accessibilityHint(t.suggested ? "Pearl’s guess. Opens it to check." : "")
        .accessibilityAction(named: "Confirm \(t.label)") {
            if t.suggested, !t.asks { onConfirm?() }
        }
    }

    /// TR-05 (G7-TripMore): the meta line with the trip's name in `action`,
    /// "Lodging · Trip to Montréal".
    private var metaText: Text {
        let line = meta
        guard showsTrip, let trip = t.trip?.name, !trip.isEmpty, let r = line.range(of: trip) else { return Text(line) }
        return Text(String(line[..<r.lowerBound])) + Text(trip).foregroundColor(Pearl.action)
            + Text(String(line[r.upperBound...]))
    }

    /// "Health · Today"; "Today · Pending" while it's a guess; "Paid back · Sushi Nami".
    /// Under T-01r's day header: "Health", "Pending".
    private var meta: String {
        let when: String? = showsDay ? Format.relativeDay(t.date) : nil
        if let paidBack = paidBack { return "Paid back · \(paidBack)" }
        // A deposit whose parts all paid purchases back (2026-11-23): the
        // server's line, "Paid back · Denise · 6 purchases".
        if t.chip?.label == "Paid back", let note = t.note, !note.isEmpty { return note }
        if let charge = t.refundOf { return "Refund · \(charge.merchant)" }
        // T-01r2 (TEST-25): a split says what the server says.
        if let note = splitNote { return note }
        // T-82 (THL-292): a transfer a recurring rule sorted says so.
        if t.recurring != nil, let note = t.note, note.hasPrefix("Recurring") { return note }
        let trip = showsTrip ? t.trip?.name : nil
        if t.suggested { return [when, t.pending ? "Pending" : nil, trip].compactMap { $0 }.joined(separator: " · ") }
        // TR-05 (1327:6116): "Shopping · Trip to Montréal", in its own day.
        return [showsCategory ? t.label : nil, trip, when, t.pending ? "Pending" : nil].compactMap { $0 }
            .joined(separator: " · ")
    }

    /// RC-01 (ROWCOST-01; replaces T-01r2, TEST-25): the server's line on a
    /// split row, "$127.50 split · $30.00 back · $57.50 to come", "$59.33
    /// split · $39.54 back" or "$120.00 split 5 ways · not sure yet". The
    /// app makes none of its own.
    private var splitNote: String? {
        guard t.split, !t.inflow, let note = t.note, !note.isEmpty else { return nil }
        return note
    }

    /// RC-01: what it costs her now, the server's `amount`, which Spent and
    /// the Allowance count too. Rule A stays on the server: a split nobody
    /// has paid yet costs the whole purchase, and each payback lowers it.
    /// The amount; a transfer's ⇄ smaller than the figures (product owner,
    /// 2026-11-21), so it reads as a mark, not a character of the amount.
    private var moneyText: Text {
        if t.movedBetweenAccounts {
            return Text("\u{21C4}").font(.system(size: 12, weight: .semibold)) + Text(" " + Format.amount(t.amount))
        }
        return Text(shownMoney)
    }

    private var shownMoney: String {
        Format.row(t) + (currency.map { " \($0)" } ?? "")
    }

    /// RC-01 VoiceOver (note 1402:5082): "Gusto, costs you $97.50 now,
    /// $127.50 split, $30.00 back, $57.50 to come."
    private var costSpoken: String? {
        guard let cost = t.cost, splitNote != nil else { return nil }
        return "\(t.merchant), costs you \(Format.amount(t.amount)) now, "
            + cost.line.replacingOccurrences(of: " · ", with: ", ")
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
    /// A trip's avatar: always two letters, "MO" for Montréal, "QC" for
    /// Québec City (note 1329:69536, Wording). Other avatars are unchanged.
    var trip = false

    /// A+ `face` (#F3E8EE / #262E63), initials 14/500 at 40.
    var body: some View {
        Text(letters)
            .font(.custom("Figtree-Medium", size: size * 0.35))
            .tracking(0.2)
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(APlus.face))
            .accessibilityHidden(true)
    }

    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }.prefix(2)
        if trip, words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
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
        // kit `.guess`: a 1 pt dashed line in ink at 60%.
        .overlay(Capsule().strokeBorder(Pearl.ink.opacity(0.6), style: StrokeStyle(lineWidth: 1, dash: [3, 2])))
        // TEST-45: one element, so the words are said once, not by the icon
        // and the text each.
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Pearl’s guess: \(label)")
    }
}

/// kit `.seltick`: 22 pt, a 1.5 pt muted ring, or `action` with a tick.
struct SelectTick: View {
    let on: Bool

    var body: some View {
        ZStack {
            if on {
                Circle().fill(Pearl.action)
                Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundColor(Pearl.onAction)
            } else {
                Circle().strokeBorder(Pearl.muted, lineWidth: 1.5)
            }
        }
        .frame(width: 22, height: 22)
        .accessibilityHidden(true)
    }
}

/// G1-Select: the floating bar's glass (kit `.selbar`): `card` over a blur,
/// the card line, radius 28, a 0 10 28 shadow.
struct SelectionBarSurface: View {
    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 28, style: .continuous)
        shape.fill(APlus.card)
            .background(.ultraThinMaterial, in: shape)
            .overlay(shape.strokeBorder(APlus.cardLine, lineWidth: 1))
            .shadow(color: Color(red: 28 / 255, green: 22 / 255, blue: 56 / 255).opacity(0.16), radius: 14, y: 10)
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
    /// Filters' Month row (fix/filters-expanded): one month of the list,
    /// "2026-11"; nil is All months. Apart from the card's own month (T-47).
    var month: String?

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
        if let m = month, !t.date.hasPrefix(m) { return false }
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
        if let m = month { out.append(Chip(id: "month", label: Self.monthLabel(m), needsServer: false)) }
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

    /// "November" this year, "November 2025" before it.
    static func monthLabel(_ m: String) -> String {
        m.prefix(4) == Format.thisMonth().prefix(4) ? Format.monthName(m) : Format.month(m)
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
            if chip == "month" { month = nil }
            if chip == "amount" { min = ""; max = "" }
            if chip == "merchant" { merchant = "" }
        }
    }
}

/// T-17 (G1-Search-r, fix/filters-expanded): the sheet opens with every
/// filter showing, as More filters used to leave it; there is no More
/// filters step. Transaction type as chips, Month on its own card (All
/// months, or one month of the list), spending type as chips, then a card
/// whose rows open in place (T-17b to T-17d): accounts, category, tags,
/// amount, sort, only show and merchant; and whether to show what's left
/// out. "Show 214" counts every month and applies it.
struct FilterSheet: View {
    @State var filters: TxFilters
    /// The list's months, oldest first.
    let months: [String]
    let accounts: [FilterAccount]
    let categories: [String]
    let tags: [String]
    /// Every month's rows are here, so the count is the whole list's.
    let counted: Bool
    let count: (TxFilters) -> Int
    let onApply: (TxFilters) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var open: Row?
    @State private var allMonths = false

    enum Row { case month, accounts, category, tags, amount, sort, only, merchant }

    init(filters: TxFilters, months: [String], accounts: [FilterAccount], categories: [String], tags: [String],
         counted: Bool = true, count: @escaping (TxFilters) -> Int, onApply: @escaping (TxFilters) -> Void) {
        _filters = State(initialValue: filters)
        self.months = months
        self.accounts = accounts
        self.categories = categories
        self.tags = tags
        self.counted = counted
        self.count = count
        self.onApply = onApply
    }

    /// A+ (G1-Search, Filters): Reset · Filters · ✕, the types as chips
    /// (kit `.chip`, rose when on), Month on its card, spending types, a
    /// card of rows, the left-out switch on its own card, and "Show 24" as
    /// the one Primary.
    var body: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: "Filters", left: "Reset", onLeft: { filters = TxFilters() }) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 0) {
                    FilterChipSection(title: "Transaction type", names: TxFilters.typeNames.map { ($0.key, $0.name) },
                                      on: { filters.types.contains($0) }) { filters.types.formSymmetricDifference([$0]) }
                    if !months.isEmpty {
                        APCard { OwnBody { monthRows } }.padding(.top, 16)
                    }
                    FilterChipSection(title: "Spending type", names: TxFilters.groupNames.map { ($0.key, $0.name) },
                                      on: { filters.groups.contains($0) }) { filters.groups.formSymmetricDifference([$0]) }
                        .padding(.top, 20)
                    APCard { OwnBody { rows } }.padding(.top, 16)
                    APCard { leftOutToggle }.padding(.top, 12)
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
                .animation(.easeOut(duration: 0.2), value: open)
            }
            .scrollDismissesKeyboard(.interactively)

            Button(showLabel) { onApply(filters) }
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 8)
        }
        .cfSheet()
        .presentationDragIndicator(.visible)
    }

    private var leftOutToggle: some View {
        Toggle(isOn: Binding(get: { filters.only.contains(.leftOut) },
                             set: { on in if on { filters.only.insert(.leftOut) } else { filters.only.remove(.leftOut) } })) {
            Text("Show left-out transactions").font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action)
        .padding(.horizontal, 16).frame(minHeight: 64)
    }

    /// Month, and its choices in place once tapped (T-17b): All months,
    /// the last four, then Earlier months. One month keeps only its rows.
    @ViewBuilder private var monthRows: some View {
        row(.month, "Month", filters.month.map(TxFilters.monthLabel) ?? "All months")
        if open == .month {
            option("All months", on: filters.month == nil) { filters.month = nil }
            let shownMonths = allMonths ? Array(months.reversed()) : Array(months.suffix(4).reversed())
            ForEach(shownMonths, id: \.self) { m in
                option(allMonths ? Format.month(m) : TxFilters.monthLabel(m), on: filters.month == m) { filters.month = m }
            }
            if months.count > 4 && !allMonths {
                option("Earlier months", on: false) { allMonths = true }
            }
        }
    }

    @ViewBuilder private var rows: some View {
        if !accounts.isEmpty {
            row(.accounts, "Accounts", accountsValue)
            if open == .accounts {
                // T-17c (G1-FilterOpen): All accounts first, then each one.
                option("All accounts", on: filters.accounts.isEmpty) { filters.accounts = [] }
                ForEach(accounts, id: \.id) { a in
                    option(a.label + (a.joint ? " · Joint" : ""),
                           on: filters.accounts.contains(a.id)) { toggleAccount(a.id) }
                }
            }
            APSeparator(afterFace: false)
        }
        if !categories.isEmpty {
            row(.category, "Category", list(filters.categories.sorted()))
            if open == .category {
                ForEach(categories, id: \.self) { c in
                    option(c, on: filters.categories.contains(c)) { filters.categories.formSymmetricDifference([c]) }
                }
            }
            APSeparator(afterFace: false)
        }
        // Tags sit under Category, as on the old sheet (only while tags are on).
        if Features.tags && !tags.isEmpty {
            row(.tags, "Tags", list(filters.tags.sorted().map { "#" + $0 }))
            if open == .tags {
                ForEach(tags, id: \.self) { tag in
                    option("#" + tag, on: filters.tags.contains(tag)) { filters.tags.formSymmetricDifference([tag]) }
                }
            }
            APSeparator(afterFace: false)
        }
        row(.amount, "Amount", filters.amountLabel ?? "Any")
        if open == .amount {
            HStack(spacing: 12) {
                amountField("Min", text: $filters.min, prompt: "0")
                amountField("Max", text: $filters.max, prompt: "Any")
            }
            .padding(.horizontal, 16).padding(.bottom, 12)
        }
        APSeparator(afterFace: false)
        row(.sort, "Sort", filters.sort.rawValue)
        if open == .sort {
            ForEach(TxFilters.Sort.allCases, id: \.self) { sort in
                option(sort.rawValue, on: filters.sort == sort) { filters.sort = sort }
            }
        }
        APSeparator(afterFace: false)
        row(.only, "Only show", list(TxFilters.Only.allCases.filter { $0 != .leftOut && filters.only.contains($0) }
            .map(\.rawValue)))
        if open == .only {
            ForEach(TxFilters.Only.allCases.filter { $0 != .leftOut }, id: \.self) { flag in
                option(flag.rawValue, on: filters.only.contains(flag)) { filters.only.formSymmetricDifference([flag]) }
            }
        }
        APSeparator(afterFace: false)
        row(.merchant, "Merchant", filters.merchant.trimmingCharacters(in: .whitespaces).isEmpty ? "Any" : filters.merchant)
        if open == .merchant {
            // REDESIGN-09: a search well.
            PearlField(placeholder: "Any merchant", text: $filters.merchant, kind: .search)
                .autocorrectionDisabled()
                .padding(.horizontal, 16).padding(.bottom, 12)
        }
    }

    /// "Show 214" across every month; just "Show" while the older months
    /// are still on their way.
    private var showLabel: String {
        counted ? "Show \(count(filters))" : "Show"
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

    /// From All accounts, a tap keeps just that one; taps add or take off
    /// more; none left, or every one, is All accounts again.
    private func toggleAccount(_ id: String) {
        var chosen = filters.accounts
        chosen.formSymmetricDifference([id])
        filters.accounts = chosen.count == accounts.count ? [] : chosen
    }

    /// "Month   November ›": tapping opens its choices under it, and closes
    /// whichever was open.
    private func row(_ which: Row, _ title: String, _ value: String) -> some View {
        Button { open = open == which ? nil : which } label: {
            // kit `.kv`: 52 high, the value muted with the chevron.
            // G1-FilterOpen: an open row's value turns `link` and its chevron goes.
            HStack(spacing: 8) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink).layoutPriority(1)
                Spacer(minLength: 12)
                Text(value).font(Nacre.body).foregroundColor(open == which ? Pearl.link : Pearl.muted).lineLimit(1)
                if open != which { CFChevron() }
            }
            .padding(.horizontal, 16).frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityValue(value)
        .accessibilityHint(open == which ? "Closes the choices" : "Shows the choices")
    }

    /// One choice under an open row (G1-FilterOpen): 28 in, 16 pt, 48
    /// high, the rose ✓ on the right when it's on.
    private func option(_ label: String, on: Bool, _ tap: @escaping () -> Void) -> some View {
        VStack(spacing: 0) {
            Rectangle().fill(APlus.separator).frame(height: 0.5).padding(.leading, 28)
            Button(action: tap) {
                HStack(spacing: 12) {
                    Text(label).font(.custom("Figtree-Regular", size: 16, relativeTo: .body))
                        .foregroundColor(Pearl.ink).lineLimit(1)
                    Spacer()
                    if on {
                        Image(systemName: "checkmark").font(.system(size: 14, weight: .semibold))
                            .foregroundColor(Pearl.action).accessibilityHidden(true)
                    }
                }
                .padding(.leading, 28).padding(.trailing, 16).frame(minHeight: 48)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(on ? .isSelected : [])
        }
    }

    /// REDESIGN-09: Min and Max are amount wells.
    private func amountField(_ label: String, text: Binding<String>, prompt: String) -> some View {
        PearlField(label: label, placeholder: prompt, text: text, kind: .amount, identifier: "\(label) amount")
            .frame(maxWidth: .infinity)
    }
}

/// One Filters chip section (kit `.label` then `.chip`, 36 high, rose when
/// on), wrapping. Its own body (stack check).
struct FilterChipSection: View {
    let title: String
    let names: [(key: String, name: String)]
    let on: (String) -> Bool
    let tap: (String) -> Void

    init(title: String, names: [(String, String)],
         on: @escaping (String) -> Bool, tap: @escaping (String) -> Void) {
        self.title = title
        self.names = names.map { (key: $0.0, name: $0.1) }
        self.on = on
        self.tap = tap
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            APSectionLabel(text: title).padding(.bottom, 10)
            Chips {
                ForEach(names, id: \.key) { n in
                    CFChip(label: n.name, on: on(n.key)) { tap(n.key) }
                }
            }
            .padding(.vertical, -5)
        }
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
            CFSheetTitle(title: "Choose a month") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    ForEach(years, id: \.self) { year in
                        APSectionLabel(text: year).padding(.top, 16).padding(.bottom, 0)
                        APCard {
                            let inYear = months.reversed().filter { $0.hasPrefix(year) }
                            ForEach(Array(inYear.enumerated()), id: \.element) { index, m in
                                if index > 0 { APSeparator(afterFace: false) }
                                // T-47 (G1-Months, rethought): a month answers on tap; no Done.
                                Button { chosen = m; onDone(m) } label: {
                                    HStack {
                                        VStack(alignment: .leading, spacing: 2) {
                                            Text(Format.monthName(m)).font(Nacre.body).foregroundColor(Pearl.ink)
                                            if let line = line(m) {
                                                // "Over $140" in danger: red only for over.
                                                Text(line).font(Nacre.subheadline)
                                                    .foregroundColor(line.hasPrefix("Over") ? Pearl.danger : Pearl.muted)
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
                .padding(.horizontal, 16).padding(.bottom, 24)
            }
        }
        .cfSheet()
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

    /// TEST-41: every month's result in one call (GET /api/transactions/months),
    /// remembered between opens so the lines show at once the next time.
    /// TEST-50: Cash flow fetches them as it loads (`prefetch`), so the
    /// sheet opens with them; this only refreshes.
    private func loadTotals() async {
        if left.isEmpty { left = Self.remembered }
        await Self.prefetch(app.api)
        if !Self.remembered.isEmpty { left = Self.remembered }
    }

    private static var remembered: [String: Double] = [:]

    /// Every month's Leftover (negative: Over), kept for the next open.
    @MainActor static func prefetch(_ api: APIClient) async {
        guard let reply: MonthResults = try? await api.get("api/transactions/months") else { return }
        var out: [String: Double] = [:]
        for m in reply.months { out[m.month] = m.left }
        remembered = out
    }

    init(months: [String], current: String?, onDone: @escaping (String?) -> Void) {
        self.months = months
        self.current = current
        self.onDone = onDone
        _left = State(initialValue: Self.remembered)
    }

    private struct MonthResults: Decodable {
        struct Month: Decodable { let month: String; let left: Double }
        let months: [Month]
    }
}

// MARK: - Sheet parts

/// A sheet's centred title with a round close button (T-17, T-47).
struct SheetTitle: View {
    let title: String
    /// MP-01 / MP-02 (MANY-01): the title said shorter, for when `title`
    /// won't fit on one line beside the close button.
    var short: String? = nil
    let close: () -> Void

    var body: some View {
        ZStack {
            if let short = short {
                ViewThatFits(in: .horizontal) {
                    Text(title).lineLimit(1)
                    Text(short)
                }
                .font(Nacre.headline).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
                .padding(.horizontal, 52)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(title)
                .accessibilityAddTraits(.isHeader)
            } else {
                Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
            }
            HStack {
                Spacer()
                Button(action: close) {
                    Image(systemName: "xmark").font(.system(size: 16, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 44, height: 44)
                        .background(APGlassCircle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Close")
            }
        }
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 12)
    }
}

/// A sheet's surface, A+ `.sheet` (APSheetGround): the nacre under a
/// white veil in light, #1C2F73 → #12163F in dark.
struct SheetBackground: View {
    var body: some View {
        APSheetGround()
    }
}

extension Transaction {
    /// Red going out, green coming in, grey when it doesn't count.
    /// SP-B: spending in plum (`moneyOut`), money in green, grey when it doesn't count.
    var tone: Color { notCounted ? Pearl.muted : (inflow ? Pearl.moneyIn : Pearl.moneyOut) }

    /// TC-A (1368:8300, 1368:8898, 1368:9480): a row's amount on Cash flow,
    /// the Calendar day list and a trip page. Moved between her accounts is
    /// grey, like anything else that doesn’t count (product owner,
    /// 2026-11-15); spending stays ink and money in green.
    var rowTone: Color { movedBetweenAccounts ? Pearl.moved : tone }
}

/// RC-03 (note 1402:5082, Motion): when a payback lands, the amount counts
/// down, 400 ms ease-out; with Reduce Motion the new number cross-fades.
/// No haptic beyond the toast's.
struct CostCountDown: ViewModifier {
    let value: Double
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func body(content: Content) -> some View {
        if #available(iOS 17.0, *), !reduceMotion {
            content.contentTransition(.numericText(value: value))
                .animation(.easeOut(duration: 0.4), value: value)
        } else {
            content.contentTransition(.opacity)
                .animation(.easeInOut(duration: 0.25), value: value)
        }
    }
}

/// RC-01's one spoken label for a split row; any other row keeps what its
/// parts say.
struct CostSpoken: ViewModifier {
    let label: String?

    func body(content: Content) -> some View {
        if let label = label { content.accessibilityLabel(label) } else { content }
    }
}

extension View {
    /// RC-03: the amount counts down (or up) when it changes.
    func costCountDown(_ value: Double) -> some View { modifier(CostCountDown(value: value)) }
    /// RC-01: "Gusto, costs you $97.50 now, $127.50 split, …".
    func costSpoken(_ label: String?) -> some View { modifier(CostSpoken(label: label)) }
}

extension Format {
    /// TC-A: "⇄ $500.00" moved between her accounts (grey), "$612.00" for anything
    /// else that doesn't count (no sign: nothing left or came in), else
    /// "−$24.80" / "+$2,150.00" as `money(_:)`.
    static func row(_ t: Transaction) -> String {
        if t.movedBetweenAccounts { return moved(t.amount) }
        return t.notCounted ? amount(t.amount) : money(t)
    }

    /// TC-A: the ⇄ is a text glyph in the frame, not an SF Symbol.
    static func moved(_ value: Double) -> String { "\u{21C4} " + amount(value) }

    /// TC-A VoiceOver: "Moved $500.00 to Tangerine Savings".
    static func movedSpoken(_ value: Double, to: String) -> String {
        "Moved \(amount(value)) to \(to)"
    }
}


/// T-01r's month bar, A+ (AP-CashFlow, G1-Over): Spent in plum
/// (`money-out`), Saved in green, what's left on `track-soft`, as parts of
/// what came in; over, the rest is the over part in red. 8 high, 3 apart.
struct MonthBar: View {
    let spent: Double
    let saved: Double
    let income: Double
    var over = false

    var body: some View {
        GeometryReader { g in
            let whole = max(income, spent + saved, 1)
            let a = min(max(spent, 0) / whole, 1)
            let b = min(max(saved, 0) / whole, 1 - a)
            HStack(spacing: 3) {
                if a > 0 { Capsule().fill(Pearl.moneyOut).frame(width: max(g.size.width * a - 3, 4)) }
                if b > 0 { Capsule().fill(Pearl.moneyIn).frame(width: max(g.size.width * b - 3, 4)) }
                Capsule().fill(over ? Pearl.danger : APlus.trackSoft)
            }
        }
        .frame(height: 8)
        .accessibilityHidden(true)
    }
}

/// The top of Cash flow's month card (AP-CashFlow, G1-Over, G1-Search):
/// "November ⌄ … Came in $2,150", the headline, the bar and its legend.
/// Spent, Saved and Came in narrow the list (T-67). Its own body (stack check).
struct MonthSummary: View {
    let month: String
    let monthSpoken: String
    let canPick: Bool
    let spent: Double
    let income: Double
    let saved: Double
    let pay: TransactionList.Totals.Pay?
    /// T-67 (CF-SCROLL): the figure narrowing the list, ringed; nil for none.
    let picked: CardKind?
    /// Spent, Saved or Came in tapped: that month and kind. Leftover isn't one.
    let pick: (CardKind) -> Void
    let pickMonth: () -> Void

    private var left: Double { income - spent - saved }
    private var over: Bool { left < -0.5 && pay == nil }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center) {
                Button(action: pickMonth) {
                    HStack(spacing: 6) {
                        Text(month).font(Nacre.headline)
                        // AP-CashFlow: the board's 11 × 8 chevron, stroke 2.
                        MonthChevron()
                            .stroke(Pearl.ink, style: StrokeStyle(lineWidth: 2 * 11 / 12, lineCap: .round, lineJoin: .round))
                            .frame(width: 11, height: 8)
                            .accessibilityHidden(true)
                    }
                    .foregroundColor(Pearl.ink)
                    .frame(minHeight: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canPick)
                .accessibilityLabel("Month, \(monthSpoken)")
                Spacer(minLength: 8)
                if let day = pay?.expected {
                    // T-01r3: "Pay expected Nov 15".
                    Text("Pay expected \(Format.short(day))").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .accessibilityLabel("Pay expected \(Format.monthDay(day))")
                } else {
                    // T-67: Came in narrows the list to the month's money in.
                    figure(.cameIn, "Came in \(Format.whole(income))", dot: nil, tone: Pearl.moneyIn)
                        .font(Nacre.subheadline)
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                Text(pay != nil ? "Spent so far" : over ? "Over" : "Leftover")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                Text(Format.whole(pay != nil ? spent : abs(left)))
                    .font(.cfBig).tracking(-0.88)
                    .foregroundColor(over ? Pearl.danger : Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
            }
            .padding(.top, 2)
            .accessibilityElement(children: .combine)
            // T-01r3: the bar runs to what will have come in by month's end.
            MonthBar(spent: spent, saved: saved, income: income + (pay?.toCome ?? 0), over: over)
                .padding(.top, 12).padding(.bottom, 10)
            legend
        }
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 14)
    }

    /// kit `.legend`: 8 pt dots, 13 pt, 16 apart. Spent and Saved narrow
    /// the list (cf.css `.legend .lb`); Leftover isn't tappable.
    private var legend: some View {
        HStack(spacing: 16) {
            figure(.spent, "Spent \(Format.whole(spent))", dot: Pearl.moneyOut, tone: Pearl.moneyOut)
            figure(.saved, "Saved \(Format.whole(saved))", dot: Pearl.moneyIn, tone: Pearl.moneyIn)
            if let pay = pay {
                dot("Pay to come \(Format.whole(pay.toCome))", APlus.trackSoft, Pearl.muted)
            } else if over {
                dot("Over \(Format.whole(-left))", Pearl.danger, Pearl.danger)
            } else {
                dot("Leftover \(Format.whole(max(left, 0)))", APlus.trackSoft, Pearl.muted)
            }
            Spacer(minLength: 0)
        }
        .font(Nacre.footnote).lineLimit(1).minimumScaleFactor(0.8)
        .padding(.vertical, -13)
    }

    /// One of the card's figures as a button: ringed in its own colour on
    /// `chip` while it narrows the list (cf.css `.lb.on`), 44 pt to tap.
    private func figure(_ kind: CardKind, _ text: String, dot fill: Color?, tone: Color) -> some View {
        let on = picked == kind
        return Button { pick(kind) } label: {
            Group {
                if let fill = fill { dot(text, fill, tone) } else { Text(text).foregroundColor(tone) }
            }
            .padding(.horizontal, on ? 8 : 0).padding(.vertical, on ? 3 : 0)
            .background(Capsule().fill(on ? APlus.chip : .clear))
            .overlay(Capsule().strokeBorder(tone, lineWidth: 1.5).opacity(on ? 1 : 0))
            .padding(.horizontal, on ? -8 : 0).padding(.vertical, on ? -3 : 0)
            .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint(on ? "Shows everything again" : "Shows only these")
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func dot(_ text: String, _ fill: Color, _ tone: Color) -> some View {
        HStack(spacing: 6) {
            Circle().fill(fill).frame(width: 8, height: 8).accessibilityHidden(true)
            Text(text).foregroundColor(tone)
        }
    }
}

/// TR-11 / TR-12: Cash flow's Select pushed for a trip has its own bar where
/// the tab bar is, as Cash flow's own Select does.
private struct HidesTabBar: ViewModifier {
    let on: Bool

    func body(content: Content) -> some View {
        if on {
            content.toolbar(.hidden, for: .tabBar)
        } else {
            content
        }
    }
}

// MARK: - Opening Cash flow filtered (the filtering hook)

/// The one way another screen opens Cash flow filtered to a category
/// (2026-11-18, the theme follow-up: Home's "$120 less on takeout" opens
/// Cash flow filtered to Takeout). Set a request, then switch to the Cash
/// flow tab; Cash flow takes it (once), shows that month if one is given,
/// and puts the category in Filters with its chip, so one tap takes it off.
///
/// Cash flow's derived lists, each kept with the inputs it was made from
/// and remade only when they change (perf rehaul, 2026-11-19). A plain
/// class in `@State`: reading it in `body` never triggers a redraw, and an
/// unchanged `@State` array compares to its copy by storage, not row by row.
@MainActor
final class CFMemo {
    struct ShownKey: Equatable {
        let rows: [Transaction]
        let merged: [Transaction]
        let results: [Transaction]?
        let resultsMerged: [Transaction]
        let cardRows: [Transaction]?
        let cardFilter: CardFilter?
        let inSearch: Bool
        let filters: TxFilters
        let owed: Set<String>
    }

    struct BlocksKey: Equatable {
        let shown: [Transaction]
        let sort: TxFilters.Sort
        let byDay: Bool
        let byCategory: Bool
        let hideFirst: Bool
        let select: Bool
    }

    private var shownKey: ShownKey?
    private var shownValue: [Transaction] = []
    private var blocksKey: BlocksKey?
    private var blocksValue: [CFBlock] = []
    private var merchantsKey: (rows: [Transaction], results: [Transaction]?)?
    private var merchantsValue: [String: String] = [:]
    private var accountsKey: (rows: [Transaction], accounts: [AccountsOverview.Account])?
    private var accountsValue: [FilterAccount] = []

    func shown(_ key: ShownKey, make: () -> [Transaction]) -> [Transaction] {
        if shownKey != key { shownValue = make(); shownKey = key }
        return shownValue
    }

    func blocks(_ key: BlocksKey, make: () -> [CFBlock]) -> [CFBlock] {
        if blocksKey != key { blocksValue = make(); blocksKey = key }
        return blocksValue
    }

    /// Each row's merchant by id, for "Paid back · <shop>".
    func merchants(rows: [Transaction], results: [Transaction]?, make: () -> [String: String]) -> [String: String] {
        if merchantsKey?.rows != rows || merchantsKey?.results != results {
            merchantsValue = make()
            merchantsKey = (rows, results)
        }
        return merchantsValue
    }

    func filterAccounts(rows: [Transaction], accounts: [AccountsOverview.Account],
                        make: () -> [FilterAccount]) -> [FilterAccount] {
        if accountsKey?.rows != rows || accountsKey?.accounts != accounts {
            accountsValue = make()
            accountsKey = (rows, accounts)
        }
        return accountsValue
    }
}

///     CashFlowFocus.shared.show(category: "Takeout", month: "2026-11")
///     tab = .cashFlow
@MainActor
final class CashFlowFocus: ObservableObject {
    static let shared = CashFlowFocus()

    struct Request: Equatable {
        /// The category's name, as Filters lists it ("Takeout").
        let category: String
        /// "2026-11"; nil keeps the month Cash flow is on.
        let month: String?
    }

    /// The waiting request; Cash flow sets it back to nil once it has it.
    @Published var request: Request?

    func show(category: String, month: String? = nil) {
        request = Request(category: category, month: month)
    }
}
