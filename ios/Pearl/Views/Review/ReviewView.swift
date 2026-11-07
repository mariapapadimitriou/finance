import SwiftUI

/// Needs a look (THL-123, THL-232; T-10, T-11): every question as a row,
/// its dashed chip naming what it needs, To sort or Skipped. Tapping one
/// opens its guess on the transaction's own page (T-92), or its question
/// (AnswerSheet); swiping skips it, or puts a skipped one back. Skipped ones
/// count the way Pearl guessed.
@MainActor
struct ReviewView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var review: Review?
    private var categories: [CategoryList.Category] { app.categories }
    @State private var accounts: [AccountsOverview.Account] = []
    /// T-83 (THL-213): "all", a kind of question, "pay3" or "skipped".
    @State private var filter = "all"
    private var showingSkipped: Bool { filter == "skipped" }
    private var showingSorted: Bool { ["today", "pearl"].contains(filter) }
    @State private var asking: Ask?
    /// Sorted today or Pearl sorted, when one of those is the filter.
    @State private var sortedRows: [SortedRow]?
    @State private var sorting = false
    @State private var toast: Toast?
    @State private var busy = false
    @State private var error: String?

    struct Toast: Equatable {
        let title: String
        let undo: JSONValue?
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            header.padding(.horizontal, 16)
            list
        }
        .nacreScreen()
        .accessibilityHidden(sorting)
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
        // Quick sort is part of this screen, not a screen presented over it:
        // nothing dismissed inside it can close it. On iOS 27 a sheet and a
        // page closing together took a presented Quick sort with them.
        .overlay {
            if sorting {
                QuickSortView(asks: quick, categories: categories, names: recentNames) {
                    sorting = false
                    Task { await load() }
                }
                .transition(.move(edge: .bottom))
            }
        }
        .animation(.easeOut(duration: 0.25), value: sorting)
        .toolbar(sorting ? .hidden : .visible, for: .navigationBar)
        // The tab holding this screen decides the bar: tell it, so Quick sort has the whole screen.
        .onChange(of: sorting) { on in app.hidesTabBar = on }
        .onDisappear { app.hidesTabBar = false }
        .task { await load() }
        .fullScreenCover(item: Binding(get: { asking.flatMap { $0.opensPage(accounts) ? $0 : nil } },
                                       set: { asking = $0 })) { ask in
            GuessPage(actions: GuessActions(
                ask: ask, label: ask.guessLabel(accounts), accounts: accounts, names: recentNames,
                onYes: { newOnes in asking = nil; Task { await send(ask.yesAnswer(accounts, newOnes: newOnes)) } },
                onSkip: ask.skipped ? nil : {
                    asking = nil
                    Task { await send(.skip(ask.item.key, true)) }
                },
                onAnswer: { answer in asking = nil; Task { await send(answer) } }),
                      categories: categories)
        }
        .sheet(item: Binding(get: { asking.flatMap { $0.opensPage(accounts) ? nil : $0 } },
                             set: { asking = $0 })) { ask in
            if ask.item.rest != nil {
                // "$172 left to sort" (S-28): sorting the rest of a deposit.
                PartsSheet(deposit: PartsDeposit(id: ask.t.id, name: ask.t.name, amount: ask.t.amount,
                                                 date: ask.t.date, rest: true), api: app.api) { reply in
                    asking = nil
                    Task { await send(.done(reply)) }
                }
            } else {
                AnswerSheet(ask: ask, categories: categories, accounts: accounts,
                            names: recentNames, api: app.api) { answer in
                    asking = nil
                    Task { await send(answer) }
                }
            }
        }
    }

    private var list: some View {
        List {
            if let review = review {
                let rows = review.asks.filter { $0.skipped == showingSkipped && (["all", "skipped"].contains(filter) || Self.kindName($0.kind) == filter) }
                if showingSkipped && !rows.isEmpty {
                    Text("Guesses count for now. Swipe left to put one back.")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink)
                        .listRowBackground(Color.clear).listRowSeparator(.hidden)
                        .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 4, trailing: 16))
                }
                if showingSorted {
                    sortedList
                } else if rows.isEmpty {
                    empty(review, shown: rows.count)
                        .listRowBackground(Color.clear).listRowSeparator(.hidden)
                } else {
                    Section {
                        ForEach(rows) { ask in
                            Button { asking = ask } label: { row(ask) }
                                .buttonStyle(.plain)
                                .listRowBackground(Nacre.glass)
                                .listRowSeparatorTint(Nacre.separator)
                                .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0))
                                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                    Button(ask.skipped ? "Put back" : "Skip") {
                                        Task { await send(.skip(ask.item.key, !ask.skipped)) }
                                    }
                                    .tint(ask.skipped ? Pearl.action : Pearl.muted)
                                }
                        }
                    }
                }
            } else {
                LoadState(error: error) { Task { await load() } }
                    .listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
        }
        .listStyle(.insetGrouped)
        .scrollContentBackground(.hidden)
        .environment(\.defaultMinListHeaderHeight, 0)
        .modifier(TightTop())
        .clipped()
    }

    /// The grouped list's own top gap, trimmed where iOS lets us.
    private struct TightTop: ViewModifier {
        func body(content: Content) -> some View {
            if #available(iOS 17.0, *) {
                content.contentMargins(.top, 0, for: .scrollContent)
            } else {
                content
            }
        }
    }

    // MARK: Parts

    private var header: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Needs a look").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            if let review = review {
                // T-83: All, then a chip per kind of question with any to sort,
                // then Skipped, third paycheques included.
                let open = review.asks.filter { !$0.skipped }
                let skipped = review.asks.count - open.count
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        chip("All · \(open.count)", on: filter == "all") { filter = "all" }
                        ForEach(Self.kindOrder, id: \.self) { kind in
                            let n = open.filter { Self.kindName($0.kind) == kind }.count
                            if n > 0 { chip("\(kind) · \(n)", on: filter == kind) { filter = kind } }
                        }
                        if skipped > 0 || showingSkipped {
                            chip("Skipped · \(skipped)", on: showingSkipped) { filter = "skipped" }
                        }
                        if review.sortedToday > 0 {
                            chip("Sorted today · \(review.sortedToday)", on: filter == "today") { showSorted("today") }
                        }
                        if review.pearlSorted > 0 {
                            chip("Pearl sorted · \(review.pearlSorted)", on: filter == "pearl") { showSorted("pearl") }
                        }
                    }
                }
            }
            if !showingSkipped && !showingSorted && !quick.isEmpty {
                QuickSortCard(count: quick.count) { sorting = true }
                // T-10.
                Text("Tap one to sort it.").font(Nacre.footnote).foregroundColor(Pearl.ink)
            }
            if let error = error, review != nil {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
            }
        }
        .padding(.bottom, 12)
    }

    /// The web's names for each kind of question (NeedsALook.jsx).
    static let kindOrder = ["Where it went", "Recurring", "Categories", "Money in", "Joint deposits",
                            "Who sent it", "Income", "Duplicates", "Your plan"]

    static func kindName(_ q: Question) -> String {
        switch q {
        case .transfer: return "Where it went"
        case .recurring: return "Recurring"
        case .category: return "Categories"
        case .moneyIn: return "Money in"
        case .joint: return "Joint deposits"
        case .whoSent: return "Who sent it"
        case .incomeType: return "Income"
        case .duplicate: return "Duplicates"
        case .check: return "Your plan"
        }
    }

    private func chip(_ label: String, on: Bool, _ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(label)
                .font(Nacre.footnote)
                .foregroundColor(Pearl.ink)
                .padding(.horizontal, 14).frame(height: 34)
                .background(Capsule().fill(on ? Color.white.opacity(0.9) : Nacre.glass))
                .overlay(Capsule().strokeBorder(Nacre.glassEdge, lineWidth: 1))
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// Initials, who, when, the question as a dashed chip, and the amount.
    private func row(_ ask: Ask) -> some View {
        let t = ask.t
        return HStack(spacing: 14) {
            Initials(name: t.name)
            VStack(alignment: .leading, spacing: 3) {
                Text(t.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(ask.kind == .joint ? "Joint · \(Format.relativeDay(t.date))"
                     : ask.item.rest.map { "\(Format.relativeDay(t.date)) · \(Format.amount($0.sorted)) sorted" }
                     ?? [Format.relativeDay(t.date), t.shareNote].compactMap { $0 }.joined(separator: " · "))
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                GuessChip(label: ask.chip, question: false).padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(t.shownAmount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(t.inflow ? Pearl.ink : Pearl.moneyOut)
                .fixedSize()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(ask.skipped ? "Answers it. Swipe to put it back." : "Answers it. Swipe to skip.")
    }

    // MARK: Sorted today, Pearl sorted

    private func showSorted(_ view: String) {
        filter = view
        sortedRows = nil
        Task { await loadSorted() }
    }

    private func loadSorted() async {
        guard showingSorted else { return }
        struct Rows: Decodable { let rows: [Lenient<SortedRow>] }
        let got: Rows? = try? await app.api.get("api/review/sorted", query: ["view": filter])
        sortedRows = got?.rows.compactMap { $0.value } ?? []
    }

    /// Each row with why it's sorted. A row opens its own page, to change it;
    /// today's can also be taken back with a swipe.
    @ViewBuilder private var sortedList: some View {
        if let rows = sortedRows {
            if rows.isEmpty {
                Text(filter == "today" ? "Nothing sorted today." : "Pearl hasn’t sorted anything by itself.")
                    .font(Nacre.body).foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity).padding(.vertical, 32)
                    .listRowBackground(Color.clear).listRowSeparator(.hidden)
            }
            Section {
                ForEach(rows) { row in
                    NavigationLink {
                        TransactionByID(id: row.id, categories: categories)
                    } label: {
                        sortedRow(row)
                    }
                    .listRowBackground(Nacre.glass)
                    .listRowSeparatorTint(Nacre.separator)
                    .swipeActions(edge: .trailing, allowsFullSwipe: false) {
                        if let body = row.undo {
                            Button("Undo") { Task { await undoSorted(body) } }.tint(Pearl.action)
                        }
                    }
                }
            }
        } else {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                .listRowBackground(Color.clear).listRowSeparator(.hidden)
        }
    }

    private func sortedRow(_ row: SortedRow) -> some View {
        HStack(spacing: 14) {
            Initials(name: row.merchant ?? "?")
            VStack(alignment: .leading, spacing: 3) {
                Text(row.merchant ?? "Transaction").font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(row.line).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text((row.amount < 0 ? "+" : "\u{2212}") + Format.amount(abs(row.amount)))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(row.amount < 0 ? Pearl.ink : Pearl.moneyOut)
                .fixedSize()
        }
        .padding(.vertical, 4)
        .accessibilityElement(children: .combine)
    }

    private func undoSorted(_ payload: JSONValue) async {
        guard let body = payload.any as? [String: Any] else { return }
        do {
            let _: OK = try await app.api.post("api/transactions/undo", body)
            withAnimation { toast = Toast(title: "Undone.", undo: nil) }
            await load()
            await loadSorted()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    /// All sorted only at zero: an empty filter says what's left, and skipped
    /// ones aren't sorted (T-16).
    @ViewBuilder private func empty(_ review: Review, shown: Int) -> some View {
        let open = review.asks.filter { !$0.skipped }.count
        let skipped = review.asks.filter(\.skipped).count
        if open > 0 {
            VStack(spacing: 12) {
                Text(showingSkipped ? "Nothing skipped." : "None of these.").font(Nacre.body).foregroundColor(Pearl.muted)
                Button("\(open) other\(open == 1 ? "" : "s") to sort") { filter = "all" }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            .frame(maxWidth: .infinity).padding(.vertical, 32)
        } else if showingSkipped {
            Text("Nothing skipped.").font(Nacre.body).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity).padding(.vertical, 32)
        } else if skipped > 0 {
            VStack(spacing: 12) {
                Text("You skipped \(skipped). Pearl uses its guess until you sort them.")
                    .font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                Button("See skipped") { filter = "skipped" }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            .frame(maxWidth: .infinity).padding(.vertical, 32)
        } else {
            // T-16: All sorted.
            VStack(spacing: 8) {
                Image(systemName: "checkmark").font(.system(size: 20, weight: .semibold))
                    .foregroundColor(Nacre.teal)
                    .frame(width: 56, height: 56).background(Circle().fill(Nacre.mint))
                    .padding(.bottom, 6)
                Text("All sorted").font(Nacre.title2).foregroundColor(Pearl.ink)
                Text(review.pearlSorted > 0 ? "Nothing left to sort. Pearl sorted \(review.pearlSorted) more by itself."
                     : "Your numbers are up to date.")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                Button("Done") { dismiss() }
                    .buttonStyle(NacreButtonStyle())
                    .padding(.top, 20)
            }
            .frame(maxWidth: .infinity).padding(.vertical, 40)
        }
    }

    @ViewBuilder private var toastView: some View {
        if let toast = toast {
            HStack(spacing: 12) {
                Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
                Text(toast.title).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if toast.undo != nil {
                    Button("Undo") { Task { await undo() } }
                        .font(Nacre.textButton).foregroundColor(Pearl.action)
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

    /// Names she already uses, for "Who sent this?".
    private var recentNames: [String] { review?.people ?? [] }

    /// Quick sort (THL-254) walks the same open questions as this list.
    private var quick: [Ask] { review?.asks.filter { !$0.skipped } ?? [] }

    // MARK: Loading and answering

    private func load() async {
        do {
            review = try await app.api.get("api/review")
            if accounts.isEmpty, let overview: AccountsOverview = try? await app.api.get("api/accounts/overview") {
                accounts = overview.linked
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func send(_ answer: ReviewAnswer) async {
        busy = true
        defer { busy = false }
        do {
            let reply = try await answer.send(app.api)
            withAnimation { toast = Toast(title: reply.title ?? answer.done, undo: reply.undo) }
            error = nil
            await load()
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
            await load()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// What an answer does on the server, each the call the web makes for it.
enum ReviewAnswer {
    /// Pearl's guess is right.
    case confirm(String)
    /// Yes where a rule is right: this row, and the rule for new ones.
    case always(String, label: String)
    /// Yes on a question the evidence asked (finance/pairs.py): this row.
    case pair(String)
    /// Yes or No on a question about her plan (finance/checks.py).
    case check(String, yes: Bool)
    /// T-97: Yes on a merchant she has sorted different ways, with no rule.
    case varies(String, name: String)
    /// A different category, and maybe every one like it.
    case category(String, name: String, remember: Bool)
    /// "What was this?" answered: `case` and its details (finance/marks.py).
    case mark(String, [String: Any])
    /// The kind of income, for money already counted as income.
    case incomeType(String, kind: String)
    /// "Whose pay is this?" on a joint account (T-33): "me", "both" (her
    /// share counts), or "them" and who.
    case joint(String, who: String, person: String?, remember: Bool = true)
    /// "This is my regular pay" (THL-198, T-31): every deposit from this
    /// payer is her pay, on the schedule she chose.
    case regularPay(BriefTransaction, cadence: String)
    /// "Who sent this?": the name the bank left out.
    case party(String, name: String)
    /// "Same purchase?": count it once, or both are real.
    case duplicate(String, same: Bool)
    /// "Is this a recurring transfer?": what the series is.
    case recurring(key: String, kind: String?, category: String?)
    /// "No, it doesn't repeat": not asked again.
    case dismiss(String)
    /// Skip for now, or put a skipped one back.
    case skip(String, Bool)
    /// Already sent (a deposit split into parts, THL-291): its reply.
    case done(MarkReply)

    /// What a Quick sort card asks once this answer is held for its Yes. Nil is
    /// an answer that has already happened, or that isn't one to hold.
    var heldLabel: String? {
        switch self {
        case .mark(_, let body):
            switch body["case"] as? String {
            case "spending": return body["category"] as? String
            case "saved": return "Saved"
            case "moved": return "My own account"
            case "own": return "My own money"
            case "lent": return "Lending to someone"
            case "paying_back": return "Paying back a loan"
            case "work": return "Work expense"
            case "not_mine": return "Not mine"
            case "refund": return "Money back"
            case "payback": return "Paying me back"
            case "reimbursement": return "Work paying me back"
            case "borrowed": return "Lent me this"
            case "out_of_savings": return "Out of savings"
            case "lent_back": return "Money I lent, back"
            case "pay": return TransactionDetailView.kindName(body["income_kind"] as? String)
            default: return "This answer"
            }
        case .category(_, let name, _): return name
        case .incomeType(_, let kind): return TransactionDetailView.kindName(kind)
        case .regularPay: return "My pay"
        case .joint(_, let who, let person, _):
            return who == "me" ? "Yours" : who == "both" ? "Both of yours" : (person ?? "Theirs")
        case .party(_, let name): return name.isEmpty ? "Your bank’s name" : "From \(name)"
        case .duplicate(_, let same): return same ? "Same purchase" : "Both are real"
        case .recurring: return "Recurring"
        case .dismiss: return "Doesn’t repeat"
        case .confirm, .always, .varies, .pair, .check, .skip, .done: return nil
        }
    }

    /// With the card's Always switch, where this answer can make a rule.
    func withAlways(_ always: Bool?) -> ReviewAnswer {
        guard let always = always else { return self }
        switch self {
        case .mark(let id, var body) where body["remember"] != nil:
            body["remember"] = always
            return .mark(id, body)
        case .category(let id, let name, _):
            return .category(id, name: name, remember: always)
        default:
            return self
        }
    }

    /// What the toast says when the server doesn't.
    var done: String {
        switch self {
        case .skip(_, let on): return on ? "Moved to Skipped. Pearl uses its guess until you sort it." : "Back in To sort."
        case .party(_, let name): return "Sent by \(name)."
        case .duplicate(_, let same): return same ? "Counted once." : "Both counted."
        case .dismiss: return "Pearl won’t ask about it again."
        default: return "Sorted."
        }
    }

    func send(_ api: APIClient) async throws -> MarkReply {
        switch self {
        case .confirm(let id):
            return try await api.put("api/transactions/\(id)/confirm")
        case .varies(let id, let name):
            let reply: MarkReply = try await api.put("api/transactions/\(id)/confirm")
            return MarkReply(title: "\(name) varies, so no rule", detail: nil, undo: reply.undo)
        case .always(let id, let label):
            let reply: QuickSortStep = try await api.put("api/quick-sort/\(id)",
                ["action": "right", "every": false, "rows": [String](), "new_ones": true])
            return MarkReply(title: QuickSortStep.always(label, sorted: 1), detail: nil, undo: reply.undo)
        case .pair(let id):
            return try await api.post("api/review/pair/\(id)")
        case .check(let key, let yes):
            return try await api.post("api/review/check/\(key)", ["yes": yes])
        case .category(let id, let name, let remember):
            // Only this row moves; the rule is for new ones. Rows she can't see stay put.
            let reply: QuickSortStep = try await api.put("api/quick-sort/\(id)",
                ["action": "category", "category": name, "every": false, "rows": [String](), "new_ones": remember])
            return MarkReply(title: remember ? "Always \(name)." : "Moved to \(name).",
                             detail: nil, undo: reply.undo)
        case .mark(let id, let body):
            return try await api.post("api/transactions/\(id)/mark", body)
        case .incomeType(let id, let kind):
            return try await api.put("api/transactions/\(id)/income-type", ["kind": kind])
        case .joint(let id, let who, let person, let remember):
            var body: [String: Any] = ["who": who, "remember": remember]
            if let person = person { body["person"] = person }
            let reply: MarkReply = try await api.put("api/transactions/\(id)/joint-from", body)
            let title: String
            switch who {
            case "me": title = "Yours."
            case "both": title = "Both of yours. Your share counts."
            default: title = "\(person ?? "Theirs"). Not counted as yours."
            }
            return MarkReply(title: reply.title ?? title, detail: nil, undo: reply.undo)
        case .regularPay(let t, let cadence):
            // One request: the server adds the pay on the schedule she chose,
            // and its Undo takes it back (the logic review, gap 28).
            var body: [String: Any] = ["case": "regular_pay", "remember": true, "cadence": cadence]
            if let next = Format.nextPay(after: t.date, cadence: cadence) { body["next"] = next }
            let reply: MarkReply = try await api.post("api/transactions/\(t.id)/mark", body)
            return MarkReply(title: "Your regular pay, \(Format.cadence(cadence).lowercased()).",
                             detail: reply.detail, undo: reply.undo)
        case .party(let id, let name):
            return try await api.put("api/transactions/\(id)/party", ["name": name])
        case .duplicate(let id, let same):
            return try await api.post("api/review/duplicates/\(id)", ["answer": same ? "same" : "different"])
        case .recurring(let key, let kind, let category):
            var body: [String: Any] = ["key": key]
            if let kind = kind { body["kind"] = kind }
            if let category = category { body["category"] = category }
            return try await api.post("api/recurring-transfers", body)
        case .dismiss(let key):
            return try await api.post("api/review/dismiss", ["key": key])
        case .skip(let key, let on):
            return try await api.post("api/review/skip", ["key": key, "skip": on])
        case .done(let reply):
            return reply
        }
    }
}

/// A transaction's own page, from its id: for a list that only has the row.
@MainActor
struct TransactionByID: View {
    @EnvironmentObject private var app: AppModel
    let id: String
    let categories: [CategoryList.Category]
    @State private var full: Transaction?
    @State private var error: String?

    var body: some View {
        Group {
            if let full = full {
                TransactionDetailView(transaction: full, categories: categories)
            } else {
                LoadState(error: error) { Task { await load() } }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .nacreScreen()
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            full = try await app.api.get("api/transactions/\(id)")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}
