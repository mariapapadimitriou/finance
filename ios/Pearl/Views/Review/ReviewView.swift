import SwiftUI

/// Needs a look (THL-123, THL-232; T-10, T-11): every question as a row,
/// its dashed chip naming what it needs, To sort or Skipped. Tapping one
/// opens its question (AnswerSheet); swiping skips it, or puts a skipped
/// one back. Skipped ones count the way Pearl guessed.
@MainActor
struct ReviewView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss

    @State private var review: Review?
    @State private var categories: [CategoryList.Category] = []
    @State private var accounts: [AccountsOverview.Account] = []
    /// T-83 (THL-213): "all", a kind of question, "pay3" or "skipped".
    @State private var filter = "all"
    private var showingSkipped: Bool { filter == "skipped" }
    @State private var asking: Ask?
    /// T-74, open.
    @State private var payMonth: Review.PayMonth?
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
        .task { await load() }
        .fullScreenCover(isPresented: $sorting) {
            QuickSortView(asks: quick, categories: categories, names: recentNames,
                          months: review?.threePayMonth.filter { $0.skipped != true } ?? []) {
                sorting = false
                Task { await load() }
            }
        }
        .sheet(item: $payMonth) { m in
            ThirdPaychequeSheet(month: m) { answer in
                payMonth = nil
                Task { await send(answer) }
            }
            .presentationDetents([.medium])
            .presentationDragIndicator(.visible)
        }
        .sheet(item: $asking) { ask in
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
                let months = review.threePayMonth.filter { ($0.skipped ?? false) == showingSkipped && ["all", "skipped", "pay3"].contains(filter) }
                if showingSkipped && !rows.isEmpty {
                    Text("Guesses count for now. Swipe left to put one back.")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink)
                        .listRowBackground(Color.clear).listRowSeparator(.hidden)
                        .listRowInsets(EdgeInsets(top: 0, leading: 20, bottom: 4, trailing: 16))
                }
                if rows.isEmpty && months.isEmpty {
                    empty(review)
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
                        ForEach(months) { m in
                            Button { payMonth = m } label: { monthRow(m) }
                                .buttonStyle(.plain)
                                .listRowBackground(Nacre.glass)
                                .listRowSeparatorTint(Nacre.separator)
                                .listRowInsets(EdgeInsets(top: 0, leading: 0, bottom: 0, trailing: 0))
                                .swipeActions(edge: .trailing, allowsFullSwipe: true) {
                                    Button(m.skipped == true ? "Put back" : "Skip") {
                                        Task { await send(.skip(m.key, !(m.skipped ?? false))) }
                                    }
                                    .tint(m.skipped == true ? Pearl.action : Pearl.muted)
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
                let months = review.threePayMonth.filter { $0.skipped != true }.count
                let skipped = review.asks.count - open.count + review.threePayMonth.filter { $0.skipped == true }.count
                ScrollView(.horizontal, showsIndicators: false) {
                    HStack(spacing: 8) {
                        chip("All · \(open.count + months)", on: filter == "all") { filter = "all" }
                        ForEach(Self.kindOrder, id: \.self) { kind in
                            let n = open.filter { Self.kindName($0.kind) == kind }.count
                            if n > 0 { chip("\(kind) · \(n)", on: filter == kind) { filter = kind } }
                        }
                        if months > 0 { chip("Paycheques · \(months)", on: filter == "pay3") { filter = "pay3" } }
                        if skipped > 0 || showingSkipped {
                            chip("Skipped · \(skipped)", on: showingSkipped) { filter = "skipped" }
                        }
                    }
                }
            }
            if !showingSkipped && (!quick.isEmpty || review?.threePayMonth.contains { $0.skipped != true } == true) {
                QuickSortCard(count: quick.count + (review?.threePayMonth.filter { $0.skipped != true }.count ?? 0)) { sorting = true }
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
                            "Who sent it", "Income", "Duplicates"]

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
                     ?? Format.relativeDay(t.date))
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                GuessChip(label: ask.chip, question: false).padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(t.amount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(t.inflow ? Pearl.ink : Pearl.moneyOut)
                .fixedSize()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(ask.skipped ? "Answers it. Swipe to put it back." : "Answers it. Swipe to skip.")
    }

    /// "October had three paycheques", its chip, and the paycheque.
    private func monthRow(_ m: Review.PayMonth) -> some View {
        HStack(spacing: 14) {
            Image(systemName: "calendar")
                .font(.system(size: 15))
                .foregroundColor(Pearl.ink)
                .frame(width: 40, height: 40)
                .background(Circle().fill(Pearl.dynamic(light: 0xEFE4EB, dark: 0x252C5E)))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 3) {
                Text("\(Format.monthName(m.month)) had three paycheques").font(Nacre.body).foregroundColor(Pearl.ink)
                    .lineLimit(1)
                Text("Your pay").font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                GuessChip(label: "A third paycheque", question: false).padding(.top, 4)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let pay = m.paycheque {
                Text("+" + Format.amount(pay)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.ink).fixedSize()
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
        .accessibilityHint(m.skipped == true ? "Opens it. Swipe to put it back." : "Opens it. Swipe to skip.")
    }

    @ViewBuilder private func empty(_ review: Review) -> some View {
        if showingSkipped {
            Text("Nothing skipped.").font(Nacre.body).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity).padding(.vertical, 32)
        } else {
            // T-16: All sorted.
            VStack(spacing: 8) {
                Image(systemName: "checkmark").font(.system(size: 20, weight: .semibold))
                    .foregroundColor(Nacre.teal)
                    .frame(width: 56, height: 56).background(Circle().fill(Nacre.mint))
                    .padding(.bottom, 6)
                Text("All sorted").font(Nacre.title2).foregroundColor(Pearl.ink)
                Text("Your numbers are up to date.")
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
            if categories.isEmpty, let list: CategoryList = try? await app.api.get("api/categories") {
                categories = list.categories.filter { $0.hidden != true }
            }
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
        case .category(let id, let name, let remember):
            let reply: MarkReply = try await api.patch("api/transactions/\(id)",
                                                       ["category": name, "apply_to_merchant": remember])
            return MarkReply(title: reply.title ?? (remember ? "\(name), and every one like it from now on." : "Moved to \(name)."),
                             detail: reply.detail, undo: reply.undo)
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
            return MarkReply(title: title, detail: nil, undo: reply.undo)
        case .regularPay(let t, let cadence):
            let reply: MarkReply = try await api.post("api/transactions/\(t.id)/mark",
                                                      ["case": "regular_pay", "remember": true])
            // Pearl may have spotted the rhythm itself; its next date is the
            // better one when the cadence agrees, so only a different answer
            // is saved over it.
            struct Pays: Decodable {
                struct Pay: Decodable { let payer: String?; let cadence: String? }
                let pays: [Pay]
            }
            let payer = t.merchant ?? t.name
            let known: Pays? = try? await api.get("api/income-bills")
            if known?.pays.contains(where: { $0.payer == payer && $0.cadence == cadence }) != true {
                var pay: [String: Any] = ["name": t.name, "payer": payer,
                                          "amount": abs(t.amount), "cadence": cadence]
                if let next = Format.nextPay(after: t.date, cadence: cadence) { pay["next"] = next }
                let _: OK = try await api.post("api/income-bills/pay", pay)
            }
            return MarkReply(title: "Your regular pay, \(Format.cadence(cadence).lowercased()).",
                             detail: reply.detail, undo: nil)
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

// MARK: - T-74 A third paycheque

/// A month paid every two weeks that held a third paycheque: nothing to
/// sort, just what Pearl does about it. Got it dismisses it.
struct ThirdPaychequeSheet: View {
    @Environment(\.dismiss) private var dismiss
    let month: Review.PayMonth
    let answered: (ReviewAnswer) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text("A third paycheque").font(Nacre.headline).foregroundColor(Pearl.ink)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { dismiss() } }
            .padding(.top, 20)
            if let pay = month.paycheque {
                // T-74: the paycheque it's about.
                QuestionHeader(name: "Your pay", amount: "+" + Format.amount(pay), tone: Pearl.moneyIn,
                               sub: Format.monthName(month.month))
            }
            Text("\(Format.monthName(month.month)) had three paycheques")
                .font(Nacre.title2).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            Text(words).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
            Button("Got it") { answered(.dismiss(month.key)) }
                .buttonStyle(NacreButtonStyle())
            if month.skipped != true {
                Button("Skip for now") { answered(.skip(month.key, true)) }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .background(SheetBackground())
    }

    /// The server's reason, and what a month of her pay comes to.
    private var words: String {
        let reason = month.reason ?? "Paid every two weeks, so two months a year hold a third paycheque."
        guard let monthly = month.monthly, let pay = month.paycheque else { return reason }
        return "\(reason) That’s \(Format.whole(monthly)) a month from \(Format.whole(pay)) paycheques. The extra one isn’t counted as a raise."
    }
}
