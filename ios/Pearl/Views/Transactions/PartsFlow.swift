import SwiftUI

// THL-291, the deposit side: one deposit split into parts that add up to
// it. Cash she was paid (S-13), the purchases it pays back (S-09, S-25,
// S-35), how far it's sorted (S-10, S-32, S-36), what the rest is (S-11,
// S-36b) and Check and save (S-12). "Later" keeps "$x left to sort" in
// Needs a look. 2026-11-09: Edit the $600 (S-10e, SPLIT-03), split and link
// as one save (S-24x, S-12c, S-12d, SPLIT-07), WHAT CHANGES (S-12 v2,
// SPLIT-09) and cash partly deposited (S-13 v2, SPLIT-11). What the rest
// is, on the shared What was this? tiles (S-11 v2, SPLIT-04/05/12): tiles
// answer at once for "How much of it?", then the page comes back for what's left.

/// The deposit being sorted, from the transaction page or Needs a look.
struct PartsDeposit: Identifiable, Hashable {
    let id: String
    let name: String
    /// What came in, positive whichever way the caller signs it.
    let amount: Double
    let date: String
    /// The part of an earlier split still to sort: "The other $172".
    var rest = false

    init(id: String, name: String, amount: Double, date: String, rest: Bool = false) {
        self.id = id
        self.name = name
        self.amount = abs(amount)
        self.date = date
        self.rest = rest
    }
}

@MainActor
struct PartsSheet: View {
    let deposit: PartsDeposit
    let api: APIClient
    /// S-10e Edit the $600 (SPLIT-03): the parts it has now, filled in, to
    /// change and save in one go. Empty when sorting it for the first time.
    var editing: [DepositPart] = []
    let onSaved: (MarkReply) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var step: Step = .loading
    @State private var parts: [Part] = []
    @State private var cash: [Cash] = []
    /// Ticked in order: they fill from the top until the deposit is used (S-13 v2).
    @State private var cashPicked: [Int] = []
    /// S-24 (SPLIT-07): a purchase split with the sender, held until Save so
    /// the split and the link are one save.
    @State private var heldSplit: HeldSplit?
    /// S-24x: Leave without saving? while a split is held.
    @State private var leaving = false
    /// S-12 v2 WHAT CHANGES (SPLIT-09), from the server.
    @State private var changes: [Change] = []

    struct HeldSplit {
        let charge: String
        let merchant: String
        let body: [String: Any]
    }

    /// "Allowance · November +$172.00", "Travel · September $856 → $428".
    struct Change: Decodable, Hashable {
        let label: String
        let before: Double?
        let after: Double?
        let delta: Double?
    }
    @State private var owing: [Owing] = []
    @State private var sender: String?
    /// S-35b (THL-181): the name on a deposit from someone on none of her splits.
    @State private var named: String?
    @State private var picked: [String: Double] = [:]
    @State private var query = ""
    @State private var found: [Owing] = []
    /// S-11 v2 "How much of it?": all of what's left unless she types less.
    @State private var partAmount = ""
    /// S-11 v2 Off a category: the category list, for this amount.
    @State private var pickingCategory: Double?
    /// S-11k: the amount Other income took on S-11 v2, waiting for its kind.
    @State private var otherAmount: Double?
    @State private var busy = false
    @State private var error: String?

    /// `work`: Work paying me back, the expense it pays (T-09, as on the shared page).
    /// `otherKind`: S-11k (SPLIT-18), which kind Other income is.
    enum Step { case loading, cash, owing, progress, kind, otherKind, refund, work, review }

    struct Part: Identifiable, Hashable {
        let id = UUID()
        let kind: String
        let amount: Double
        var charge: String? = nil
        var merchant: String? = nil
        var person: String? = nil
        var incomeKind: String? = nil
        var cashIds: [Int] = []
        /// The purchase's day, for "Payback · Flight to Athens, Sep 28" (S-12 v2).
        var date: String? = nil
        var category: String? = nil
        /// Their share of a purchase split in this same save (S-24, SPLIT-07).
        var held = false

        /// A part as saved, to edit (S-10e).
        init(saved p: DepositPart) {
            kind = p.kind
            amount = p.amount
            charge = p.charge?.id
            merchant = p.charge?.merchant
            person = p.person
            incomeKind = p.incomeKind
            cashIds = p.cashIds ?? []
            date = p.charge?.date
            category = p.category
        }

        init(kind: String, amount: Double, charge: String? = nil, merchant: String? = nil, person: String? = nil,
             incomeKind: String? = nil, cashIds: [Int] = [], date: String? = nil, held: Bool = false,
             category: String? = nil) {
            self.category = category
            self.kind = kind
            self.amount = amount
            self.charge = charge
            self.merchant = merchant
            self.person = person
            self.incomeKind = incomeKind
            self.cashIds = cashIds
            self.date = date
            self.held = held
        }

        static func == (a: Part, b: Part) -> Bool { a.id == b.id }
        func hash(into hasher: inout Hasher) { hasher.combine(id) }

        var label: String {
            switch kind {
            case "payback":
                // S-12c: "Splits Costco · Dad's share"; S-12 v2: "Payback · Flight to Athens, Sep 28".
                if held { return "Splits \(merchant ?? "a purchase") · \(person ?? "their")’s share" }
                return "Payback · \(merchant ?? "a purchase")" + (date.map { ", \(Format.short($0))" } ?? "")
            case "refund": return "Refund · \(merchant ?? "a purchase")"
            case "gift": return "Gift"
            case "income": return TransactionDetailView.kindName(incomeKind)
            case "moved": return "From my own accounts"
            case "savings": return "Out of savings"
            case "category": return category ?? "Other"
            case "cash": return "\(person ?? "Their") cash"
            case "overpaid": return "\(person ?? "They") overpaid"
            // S-11 v2's other tiles, as parts.
            case "reimbursement": return "Work paying me back · \(merchant ?? "an expense")"
            case "loan": return "Lent me this"
            case "lent_back": return "Money I lent, back"
            default: return "Part"
            }
        }

        /// S-10e: "Pays back Flight to Athens"; "A gift" over "Income · Gift".
        var editTitle: String {
            switch kind {
            case "payback": return "Pays back \(merchant ?? "a purchase")"
            case "gift": return "A gift"
            default: return label
            }
        }

        var editSub: String? {
            switch kind {
            case "gift": return "Income · Gift"
            case "income": return "Income · \(TransactionDetailView.kindName(incomeKind))"
            default: return nil
            }
        }

        var body: [String: Any] {
            var b: [String: Any] = ["kind": kind, "amount": amount]
            if let charge = charge { b["charge"] = charge }
            if let person = person, kind != "cash" { b["person"] = person }
            if let k = incomeKind { b["income_kind"] = k }
            if kind == "category", let c = category { b["category"] = c }
            if !cashIds.isEmpty { b["cash_ids"] = cashIds }
            return b
        }
    }

    struct Cash: Decodable, Hashable, Identifiable {
        let id: Int
        let name: String
        let amount: Double
        let day: String
        let merchant: String?
        /// SPLIT-15: the whole payment this is what's left of.
        var of: Double? = nil
    }

    /// A purchase someone owes on, or one she searched for.
    struct Owing: Decodable, Hashable, Identifiable {
        /// The purchase.
        let charge: String
        let merchant: String
        let date: String
        let owes: Double
        let person: String?
        let theirs: Bool?
        /// A purchase found by searching that isn't split yet (S-23, S-24).
        var notSplit: Bool? = nil
        /// S-32: the purchase hasn't posted yet.
        var pending: Bool? = nil

        enum CodingKeys: String, CodingKey {
            case charge = "id"
            case merchant, date, owes, person, theirs, pending
        }

        /// One row per person per purchase (2026-11-09): a dinner four people
        /// owe on is four rows, and the purchase alone drew the first one four times.
        var id: String { charge + "|" + (person ?? "") }
    }

    /// S-24: a purchase that isn't split, opened to split with the sender.
    @State private var splitCharge: Transaction?

    private var wholeCents: Int { cents(deposit.amount) }
    private var sortedCents: Int { parts.map { cents($0.amount) }.reduce(0, +) }
    private var leftCents: Int { max(0, wholeCents - sortedCents) }
    private var left: Double { Double(leftCents) / 100 }
    private var sortedDone: Double { Double(sortedCents) / 100 }
    private var who: String { sender ?? deposit.name }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: title) {
                // S-11k: Close goes back to S-11 v2 with nothing added.
                if step == .otherKind { otherAmount = nil; step = .kind; return }
                // S-24x: a held split would be dropped, so ask first.
                if heldSplit != nil { leaving = true } else { dismiss() }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: deposit.name, amount: Format.amount(deposit.amount), tone: Pearl.ink,
                                   sub: Format.short(deposit.date))
                    content
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                            .padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            buttons
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await load() }
        // S-24x: swiping down can't drop a held split without asking; X asks.
        .interactiveDismissDisabled(heldSplit != nil)
        .alert("Leave without saving?", isPresented: $leaving) {
            Button("Keep sorting", role: .cancel) {}
            Button("Leave", role: .destructive) {
                heldSplit = nil
                dismiss()
            }
        } message: {
            Text("\(heldSplit?.merchant ?? "It") won’t be split with \(who), and the \(Format.whole(deposit.amount)) stays in Needs a look.")
        }
        .sheet(item: $splitCharge) { t in
            // S-24 (SPLIT-07): "Split and link" holds the split; the deposit's
            // Save does both in one go.
            SplitSheet(t: t, api: api, recent: [], with: [who], title: "\(who)’s share",
                       saveTitle: "Split and link", onHold: { body, share, _ in hold(t, body, share) }) { _ in }
        }
        .sheet(item: Binding(get: { pickingCategory.map { Picking(amount: $0) } },
                             set: { pickingCategory = $0?.amount })) { p in
            // S-11 v2 Off a category: the spending categories, answering at once.
            CategorySheet(name: deposit.name, amount: Format.amount(p.amount), tone: Pearl.ink, categories: [],
                          current: "Other", spendingOnly: true, answersAtOnce: true, showsAlways: false) { name, _ in
                pickingCategory = nil
                add(Part(kind: "category", amount: p.amount, category: name))
            }
        }
        .task(id: query) {
            guard step == .owing || step == .refund || step == .work else { return }
            try? await Task.sleep(nanoseconds: 250_000_000)
            if !Task.isCancelled { await search() }
        }
    }

    private var extra: Bool {
        leftCents > 0 && !owing.isEmpty && owing.filter { $0.theirs == true }.allSatisfy { o in
            parts.contains { $0.charge == o.charge && cents($0.amount) >= cents(o.owes) }
        } && parts.contains { $0.kind == "payback" }
    }

    private var title: String {
        switch step {
        case .loading: return ""
        case .cash: return "Is this cash you were paid?"
        case .owing:
            if owing.isEmpty { return "Find what it paid back" }
            return sender == nil ? "Who paid you back?" : "What did this pay back?"
        // T-09r's title (SPLIT-12): the same question as anywhere else.
        case .refund: return "What was this a refund for?"
        // T-09's title, as the shared page asks it for Work paying me back.
        case .work: return "What did this pay back?"
        case .progress:
            if !editing.isEmpty { return "Edit the \(Format.whole(deposit.amount))" }
            if extra { return "\(who) sent extra" }
            return deposit.rest ? "The other \(Format.amount(deposit.amount))" : "Sort the \(Format.amount(deposit.amount))"
        case .otherKind: return "What kind of income?"
        case .kind:
            if parts.isEmpty { return "What was the \(Format.amount(left))?" }
            return extra ? "What’s the extra \(Format.amount(left))?" : "What’s the other \(Format.amount(left))?"
        case .review: return "Check and save"
        }
    }

    @ViewBuilder private var content: some View {
        switch step {
        case .loading:
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        case .cash: cashList
        case .owing, .refund, .work: owingList
        case .progress: progressView
        case .kind: kindList
        case .otherKind: otherKindList
        case .review: reviewList
        }
    }

    // MARK: S-13 Cash

    private var cashList: some View {
        VStack(alignment: .leading, spacing: 8) {
            label("Cash you marked as paid back")
            GlassCard {
                ForEach(Array(cash.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { RowSeparator(inset: 64) }
                    let use = cashUse[c.id]
                    let partly = use.map { cents($0) < cents(c.amount) } ?? false
                    // S-13 v2: "$250.00 cash · Nov 1" when only part of it went in.
                    // SPLIT-15: a remainder reads "$50.00 left of $250.00 cash · Nov 3".
                    pickRow(name: c.name, sub: [c.of.map { "\(Format.amount(c.amount)) left of \(Format.amount($0)) cash" }
                                                ?? (partly ? "\(Format.amount(c.amount)) cash" : c.merchant),
                                                Format.short(c.day)].compactMap { $0 }
                                .filter { !$0.isEmpty }.joined(separator: " · "),
                            amount: use ?? c.amount, on: cashPicked.contains(c.id)) {
                        if let i = cashPicked.firstIndex(of: c.id) { cashPicked.remove(at: i) } else { cashPicked.append(c.id) }
                    }
                }
            }
            ForEach(cash.filter { c in cashUse[c.id].map { cents($0) < cents(c.amount) } ?? false }) { c in
                let use = cashUse[c.id] ?? 0
                // S-13 v2: the rest stays cash in hand and can match a later deposit.
                Text("\(Format.amount(use)) of \(c.name)’s \(Format.amount(c.amount)) cash. The other \(Format.amount(c.amount - use)) stays as cash in hand and still counts as paid back.")
                    .font(Nacre.footnote).foregroundColor(Pearl.ink).padding(.horizontal, 16)
                    .fixedSize(horizontal: false, vertical: true)
            }
            let picked = cash.filter { cashPicked.contains($0.id) }
            bar(sorted: sortedDone + cashUse.values.reduce(0, +),
                first: picked.count == 1 ? "\(picked[0].name)’s cash" : "Cash", second: "Left to sort")
        }
    }

    /// What each ticked cash record puts in, from the top until the deposit
    /// is used up (S-13 v2). One not reached puts in nothing.
    private var cashUse: [Int: Double] {
        var room = leftCents
        var out: [Int: Double] = [:]
        for id in cashPicked {
            guard let c = cash.first(where: { $0.id == id }), room > 0 else { continue }
            let use = min(cents(c.amount), room)
            out[id] = Double(use) / 100
            room -= use
        }
        return out
    }

    // MARK: S-09, S-25, S-35 What did this pay back?

    private var owingList: some View {
        VStack(alignment: .leading, spacing: 8) {
            // On top (2026-11-09): the people who owe her, and any other
            // purchase a search away, without scrolling past everyone first.
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                TextField("", text: $query, prompt: Text("Search other purchases").foregroundColor(Pearl.muted))
                    .font(Nacre.body).autocorrectionDisabled().textInputAutocapitalization(.never)
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            if asking && query.isEmpty {
                askList
            } else if step == .owing && !owing.isEmpty && query.isEmpty {
                let theirs = owing.filter { $0.theirs == true }
                let others = owing.filter { $0.theirs != true }
                if !theirs.isEmpty {
                    label(theirs.allSatisfy { $0.pending == true } ? "Still pending"
                          : sender.map { "\($0) owes you" } ?? "Owes you")
                    GlassCard {
                        ForEach(Array(theirs.enumerated()), id: \.element.id) { i, o in
                            if i > 0 { RowSeparator() }
                            owingRow(o, false)
                        }
                    }
                }
                if !others.isEmpty {
                    label(theirs.isEmpty ? "Owes you" : "Others who owe you")
                    GlassCard {
                        ForEach(Array(others.enumerated()), id: \.element.id) { i, o in
                            if i > 0 { RowSeparator() }
                            owingRow(o, true)
                        }
                    }
                }
            }
            let more = found.filter { f in !owing.contains { $0.charge == f.charge } }
            if more.isEmpty && owing.isEmpty && step == .owing {
                Text(query.isEmpty ? "Search for the purchase, or tap Next if it isn’t one."
                     : "No purchases match.")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
            }
            if !more.isEmpty {
                if !query.isEmpty { label("Results for “\(query)”") }
                GlassCard {
                    ForEach(Array(more.enumerated()), id: \.element.id) { i, o in
                        if i > 0 { RowSeparator() }
                        owingRow(o, false)
                    }
                }
            }
            if step == .owing && sender != nil && query.isEmpty {
                // S-25's bar; S-35 (who paid?) and S-23's results go without it.
                bar(sorted: sortedDone + picked.values.reduce(0, +),
                    first: "\(Format.amount(sortedDone + picked.values.reduce(0, +))) of \(Format.amount(deposit.amount))",
                    second: "\(Format.amount(max(0, deposit.amount - sortedDone - picked.values.reduce(0, +)))) left")
            }
        }
    }

    // MARK: S-35a, S-35b If Pearl can't tell who, it asks (THL-181, SPLIT-21)

    /// The shares still owed that are exactly what's left of a deposit Pearl
    /// can't put a name to.
    private var fits: [Owing] {
        guard sender == nil else { return [] }
        return owing.filter { $0.theirs != true && $0.person != nil && cents($0.owes) == leftCents }
    }

    /// Who it was isn't for Pearl to guess: more than one share is its
    /// amount (S-35a), or none is (S-35b). With exactly one, S-09/S-35 tick
    /// it as before ("same amount").
    private var asking: Bool {
        step == .owing && sender == nil && editing.isEmpty && !owing.isEmpty && fits.count != 1
    }

    @ViewBuilder private var askList: some View {
        let either = fits
        let rest = owing.filter { o in !either.contains(o) }
        if either.count >= 2 {
            // S-35a: the shares it could be on top, nothing ticked.
            label("Could be either")
            GlassCard {
                ForEach(Array(either.enumerated()), id: \.element.id) { i, o in
                    if i > 0 { RowSeparator() }
                    askRow(o)
                }
            }
            askLine
            if !rest.isEmpty {
                label("Others who owe you")
                GlassCard {
                    ForEach(Array(rest.enumerated()), id: \.element.id) { i, o in
                        if i > 0 { RowSeparator() }
                        askRow(o)
                    }
                }
            }
        } else {
            // S-35b: nothing fits; every open share, nothing ticked.
            label("Owes you")
            GlassCard {
                ForEach(Array(owing.enumerated()), id: \.element.id) { i, o in
                    if i > 0 { RowSeparator() }
                    askRow(o)
                }
            }
            askLine
        }
        // S-35a/S-35b: "● Linked $0.00   ● Not linked $30.00".
        bar(sorted: sortedDone + picked.values.reduce(0, +), first: "Linked", second: "Not linked")
    }

    /// Why Pearl asks (S-35a, S-35b).
    private var askLine: some View {
        Text(askText).font(Nacre.footnote).foregroundColor(Pearl.ink)
            .padding(.horizontal, 16).fixedSize(horizontal: false, vertical: true)
    }

    private var askText: String {
        let amount = Format.amount(left)
        let either = fits
        if either.count >= 2 {
            var seen = Set<String>()
            let names = either.compactMap { $0.person.map(firstName) }.filter { seen.insert($0.lowercased()).inserted }
            if names.count >= 2 {
                // S-35a: "Sam and Priya each owe $30.00, so Pearl won't guess. Tick who sent it."
                return "\(Format.andList(names)) each owe \(amount), so Pearl won’t guess. Tick who sent it."
            }
            // One person owing that much on more than one purchase (not drawn;
            // SPLIT-22 asks designBOT): which purchase is the question.
            var shops = Set<String>()
            let merchants = either.map(\.merchant).filter { shops.insert($0.lowercased()).inserted }
            return "\(names.first ?? "Someone") owes \(amount) on \(Format.andList(merchants)), so Pearl won’t guess. Tick what it paid back."
        }
        // S-35b: "Jordan isn't on any of your splits, and no one owes $45.00. …"
        let tail = "Tick what it paid back, or search for the purchase."
        if let name = named {
            return "\(name) isn’t on any of your splits, and no one owes \(amount). \(tail)"
        }
        return "No one owes \(amount). \(tail)"
    }

    /// S-35a/S-35b row: "Sam" over "Pizza Nova · Nov 2 · Sam's share". VoiceOver
    /// (S-35a note): "Sam, Pizza Nova, November 2, 30 dollars, not selected".
    private func askRow(_ o: Owing) -> some View {
        let name = o.person ?? o.merchant
        let sub = [o.merchant, o.pending == true ? "Pending" : Format.short(o.date),
                   o.person.map { "\(firstName($0))’s share" }].compactMap { $0 }.joined(separator: " · ")
        let on = picked[o.id] != nil
        return pickRow(name: name, sub: sub, amount: o.owes, on: on, trait: false) { toggle(o) }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(name), \(o.merchant), \(Format.monthDay(o.date)), \(Format.amount(o.owes))")
            .accessibilityValue(on ? "selected" : "not selected")
            .accessibilityAddTraits(.isButton)
    }

    /// "Priya" from "Priya S.", as S-35a's line and "Priya's share" say it.
    private func firstName(_ name: String) -> String {
        name.split(separator: " ").first.map(String.init) ?? name
    }

    private func owingRow(_ o: Owing, _ byName: Bool) -> some View {
        if o.notSplit == true && step == .owing {
            // S-23: "Costco · Oct 11 · not split yet ›" — split it first (S-24).
            return AnyView(Button { Task { await openSplit(o) } } label: {
                HStack(spacing: 12) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(o.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Text("\(Format.short(o.date)) · not split yet").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    }
                    Spacer(minLength: 8)
                    Text(Format.amount(o.owes)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                    Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
                }
                .padding(.horizontal, 16).frame(minHeight: 56).padding(.vertical, 2).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint("Splits it with \(who), then links it"))
        }
        // S-35: "Owes $64.00 · same amount"; S-32: "Pending · Sam's share".
        // By name, the purchase says which of theirs it is.
        let sub = byName ? "Owes \(Format.amount(o.owes))" + (abs(o.owes - deposit.amount) < 0.005 ? " · same amount"
                                                                : " · \(o.merchant), \(Format.short(o.date))")
            : [o.pending == true ? "Pending" : Format.short(o.date),
               o.person.map { "\($0)’s share" } ?? "\(Format.amount(o.owes)) left"]
                .joined(separator: " · ")
        return AnyView(pickRow(name: byName ? (o.person ?? o.merchant) : o.merchant, sub: sub, amount: o.owes,
                               on: picked[o.id] != nil) { toggle(o) })
    }

    /// S-24: the purchase in full, to split with whoever sent this.
    private func openSplit(_ o: Owing) async {
        do {
            splitCharge = try await api.get("api/transactions/\(o.charge)")
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// Split and link (S-24, SPLIT-07): nothing is saved yet. Their share is
    /// a part of this deposit, and the split goes with the parts in one save.
    private func hold(_ t: Transaction, _ body: [String: Any], _ share: Double) {
        splitCharge = nil
        guard share >= 0.005 else { return }
        parts.removeAll { $0.held }
        heldSplit = HeldSplit(charge: t.id, merchant: t.merchant, body: body)
        found.removeAll { $0.charge == t.id }
        query = ""
        add(Part(kind: "payback", amount: min(share, left), charge: t.id, merchant: t.merchant, person: who,
                 date: t.date, held: true), then: .progress)
    }

    /// A part taken out; a held split goes with its part.
    private func remove(_ p: Part) {
        parts.removeAll { $0.id == p.id }
        if p.held { heldSplit = nil }
    }

    private func toggle(_ o: Owing) {
        if step == .refund || step == .work {
            picked = [o.id: min(o.owes, chosenAmount)]
            return
        }
        if picked[o.id] != nil {
            picked[o.id] = nil
        } else {
            let room = wholeCents - sortedCents - picked.values.map { cents($0) }.reduce(0, +)
            guard room > 0 else { return }
            picked[o.id] = Double(min(cents(o.owes), room)) / 100
        }
    }

    // MARK: S-10, S-32, S-36 How far it's sorted

    @ViewBuilder private var progressView: some View {
        if !editing.isEmpty { editView } else { sortingView }
    }

    /// S-10e Edit the $600 (SPLIT-03): the parts as saved; swipe one away and
    /// its amount goes back to Left to sort.
    private var editView: some View {
        VStack(alignment: .leading, spacing: 8) {
            let paybacks = parts.filter { $0.kind == "payback" }.map(\.amount).reduce(0, +)
            let others = parts.filter { $0.kind != "payback" }
            if leftCents == 0 && paybacks > 0 && !others.isEmpty {
                // "● Paybacks $492.00   ● Gift $108.00"
                bar(sorted: paybacks, first: "Paybacks",
                    second: Set(others.map(\.label)).count == 1 ? others[0].label : "Other parts")
            } else {
                bar(sorted: sortedDone, first: "Sorted", second: "Left to sort")
            }
            GlassCard {
                ForEach(Array(parts.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { RowSeparator() }
                    SwipeToRemove(label: p.editTitle) { withAnimation { remove(p) } } content: {
                        HStack(spacing: 10) {
                            VStack(alignment: .leading, spacing: 2) {
                                Text(p.editTitle).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                                if let sub = p.editSub {
                                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                                }
                            }
                            Spacer(minLength: 8)
                            Text((["gift", "income"].contains(p.kind) ? "+" : "") + Format.amount(p.amount))
                                .font(Nacre.headline).monospacedDigit()
                                .foregroundColor(["gift", "income"].contains(p.kind) ? Pearl.moneyIn : Pearl.ink)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 56)
                    }
                }
                if leftCents > 0 {
                    if !parts.isEmpty { RowSeparator() }
                    HStack {
                        Text("Left to sort").font(Nacre.body).foregroundColor(Pearl.ink)
                        Spacer()
                        Text(Format.amount(left)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.action)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
            Text("Swipe a part to remove it. Its amount goes back to Left to sort.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity).multilineTextAlignment(.center)
        }
    }

    private var sortingView: some View {
        VStack(alignment: .leading, spacing: 8) {
            bar(sorted: sortedDone, first: parts.count == 1 ? parts[0].label : "Sorted",
                second: extra ? "Extra" : "Left to sort")
            GlassCard {
                ForEach(parts) { p in
                    partRow(p, removable: true)
                    RowSeparator()
                }
                VStack(alignment: .leading, spacing: 2) {
                    HStack {
                        Text(extra ? "The extra" : "Left to sort").font(Nacre.body).foregroundColor(Pearl.ink)
                        Spacer()
                        Text(Format.amount(left)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.action)
                    }
                    Text(extra ? "\(who) paid more than they owed" : "Pearl won’t guess this part")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
            }
        }
    }

    private func partRow(_ p: Part, removable: Bool) -> some View {
        HStack(spacing: 10) {
            Text(p.label).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            Spacer(minLength: 8)
            Text((["gift", "income"].contains(p.kind) ? "+" : "") + Format.amount(p.amount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(["gift", "income"].contains(p.kind) ? Pearl.moneyIn : Pearl.ink)
            if removable {
                Button { remove(p) } label: {
                    Image(systemName: "xmark.circle.fill").font(.system(size: 18)).foregroundColor(Pearl.muted)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Remove \(p.label)")
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52)
    }

    // MARK: S-11 v2 What's the other $x? (SPLIT-04, SPLIT-05 (b), SPLIT-12)

    struct Picking: Identifiable {
        let amount: Double
        var id: Double { amount }
    }

    /// T-12's tiles for a part: Not mine isn't one (SPLIT-04), and two more
    /// answer what only a part can be: "Dad overpaid" and "Off a category".
    private var notIncomeTiles: [CaseTile] {
        CaseTile.notIncome.filter { $0.key != "not_mine" } + [
            CaseTile(key: "overpaid", label: "\(who) overpaid", symbol: "person.crop.circle.badge.xmark"),
            CaseTile(key: "category", label: "Off a category", symbol: "arrow.uturn.backward"),
        ]
    }

    /// The shared What was this? page (T-08), for the rest or the extra:
    /// "How much of it?" on top, then tiles that answer at once.
    private var kindList: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("How much of it?").font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                TextField("", text: $partAmount, prompt: Text(Format.amount(left)).foregroundColor(Pearl.ink))
                    .font(Nacre.headline).monospacedDigit().multilineTextAlignment(.trailing)
                    .keyboardType(.decimalPad).frame(maxWidth: 140)
                    .accessibilityLabel("How much of it")
                    .accessibilityHint("All \(Format.amount(left)) unless you type less")
            }
            .padding(.horizontal, 4)
            label("Income").accessibilityAddTraits(.isHeader)
            CaseGrid(cases: CaseTile.income, chosen: tile)
            label("Not income").padding(.top, 4).accessibilityAddTraits(.isHeader)
            CaseGrid(cases: notIncomeTiles, chosen: tile)
            if !parts.isEmpty {
                // S-11 v2: "Sort the rest later" under Options.
                label("Options").padding(.top, 4).accessibilityAddTraits(.isHeader)
                GlassCard {
                    Button { Task { await save(later: true) } } label: {
                        HStack(spacing: 12) {
                            IconBubble(symbol: "arrow.triangle.branch")
                            Text("Sort the rest later").font(Nacre.body).foregroundColor(Pearl.ink)
                            Spacer(minLength: 4)
                            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                .foregroundColor(Pearl.muted)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    .accessibilityHint("\(Format.amount(left)) stays in Needs a look")
                }
            }
        }
    }

    /// S-11k (SPLIT-18): "Other income · $172.00", then the four kinds; a
    /// tile adds the part at once and the flow goes on as S-11 v2 does.
    private var otherKindList: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("Other income").font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                Text(Format.amount(otherAmount ?? 0)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
            }
            .padding(.horizontal, 4)
            .accessibilityElement(children: .combine)
            label("Which kind?").accessibilityAddTraits(.isHeader)
            CaseGrid(cases: CaseTile.otherIncome, chosen: Binding(get: { nil }, set: { key in
                guard let key = key, let amount = otherAmount else { return }
                otherAmount = nil
                add(Part(kind: "income", amount: amount, incomeKind: key))
            }), role: "income kind")
            Text("Tap one and it’s saved as that kind. Back goes to “\(otherBack)”.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// The S-11 v2 page Close goes back to.
    private var otherBack: String {
        if parts.isEmpty { return "What was the \(Format.amount(left))?" }
        return extra ? "What’s the extra \(Format.amount(left))?" : "What’s the other \(Format.amount(left))?"
    }

    /// A tile answers at once.
    private var tile: Binding<String?> {
        Binding(get: { nil }, set: { key in if let key = key { take(key) } })
    }

    // MARK: S-12 Check and save

    private var reviewList: some View {
        VStack(alignment: .leading, spacing: 8) {
            GlassCard {
                ForEach(Array(parts.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { RowSeparator() }
                    partRow(p, removable: false)
                }
                if leftCents > 0 {
                    RowSeparator()
                    HStack {
                        Text("Left to sort").font(Nacre.body).foregroundColor(Pearl.ink)
                        Spacer()
                        Text(Format.amount(left)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.action)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
            if !changes.isEmpty {
                // S-12 v2 WHAT CHANGES (SPLIT-09): Allowance in the deposit's
                // month; a payback lowers its purchase's category in that purchase's month.
                label("What changes")
                GlassCard {
                    ForEach(Array(changes.enumerated()), id: \.offset) { i, c in
                        if i > 0 { RowSeparator() }
                        HStack {
                            Text(c.label).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Spacer(minLength: 8)
                            if let delta = c.delta {
                                Text((delta >= 0 ? "+" : "−") + Format.amount(abs(delta)))
                                    .font(Nacre.headline).monospacedDigit()
                                    .foregroundColor(delta >= 0 ? Pearl.moneyIn : Pearl.ink)
                            } else if let before = c.before, let after = c.after {
                                Text("\(Format.whole(before)) → \(Format.whole(after))")
                                    .font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                            }
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                        .accessibilityElement(children: .combine)
                    }
                }
            }
            if let held = heldSplit {
                // S-12c: the split and the link are one save, and one Undo.
                Text("Saving splits \(held.merchant) with \(who) and links this payback in one go. One Undo puts both back.")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .task(id: parts.map(\.id)) { await loadChanges() }
    }

    /// What saving would change, worked out by the server without saving.
    private func loadChanges() async {
        struct Reply: Decodable { let changes: [Lenient<Change>] }
        let r: Reply? = try? await api.post("api/transactions/\(deposit.id)/parts/preview",
                                             ["parts": parts.map(\.body)])
        changes = (r?.changes ?? []).compactMap { $0.value }
    }

    // MARK: Buttons

    @ViewBuilder private var buttons: some View {
        switch step {
        case .loading, .kind, .otherKind:
            // S-11 v2 / S-11k: the tiles answer at once; no Review or Add part.
            EmptyView()
        case .cash:
            pair("Next", disabled: cashPicked.isEmpty, { takeCash() }, "None of these") { afterCash() }
        case .owing:
            let n = picked.count
            if asking && query.isEmpty {
                // S-35a/S-35b: Next stays off until she ticks one; Close saves nothing.
                Button(n >= 2 ? "Link these \(n) purchases" : "Next") { takeOwing() }
                    .buttonStyle(NacreButtonStyle()).disabled(picked.isEmpty)
                    .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
            } else if sender == nil && !owing.isEmpty && query.isEmpty {
                // S-35: who it was, or none of them.
                let who = owing.first { picked[$0.id] != nil }?.person
                pair(who.map { "It was \($0)" } ?? "Next", disabled: picked.isEmpty, { takeOwing() },
                     "None of these") { picked = [:]; takeOwing() }
            } else if !query.isEmpty && picked.isEmpty {
                // S-23: just the results until she taps one.
                EmptyView()
            } else {
                let pending = !owing.isEmpty && owing.filter { picked[$0.id] != nil }.allSatisfy { $0.pending == true } && n > 0
                Button(n >= 2 ? "Link these \(n) purchases" : pending ? "Link it" : "Next") { takeOwing() }
                    .buttonStyle(NacreButtonStyle())
                    .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
            }
        case .refund, .work:
            Button("Next") { takeRefund() }
                .buttonStyle(NacreButtonStyle()).disabled(picked.isEmpty)
                .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        case .progress:
            if !editing.isEmpty && leftCents == 0 {
                // S-10e: Save changes replaces every part in one save; Cancel changes nothing.
                pair("Save changes", disabled: parts.isEmpty, { Task { await save(later: false) } }, "Cancel") { dismiss() }
            } else if leftCents == 0 {
                pair("Review", disabled: false, { step = .review }, "Add a part") { step = .kind }
            } else {
                pair(extra ? "Sort the extra" : "Sort the rest", disabled: false, { step = .kind },
                     "Later") { Task { await save(later: true) } }
            }
        case .review:
            pair("Save", disabled: busy, { Task { await save(later: false) } }, "Edit") { step = .progress }
        }
    }

    private func pair(_ first: String, disabled: Bool, _ run: @escaping () -> Void,
                      _ second: String, _ other: @escaping () -> Void) -> some View {
        HStack(spacing: 10) {
            Button(first, action: run).buttonStyle(NacreButtonStyle(busy: busy)).disabled(disabled || busy)
            Button(second, action: other)
                .font(Nacre.headline).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, minHeight: 52)
                .background(Capsule().fill(Color.white.opacity(0.85)))
                .buttonStyle(.plain).disabled(busy)
        }
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
    }

    // MARK: Moving on

    /// "How much of it?": what she typed, up to what's left; all of it when blank.
    private var chosenAmount: Double {
        let text = partAmount.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return left }
        let typed = Double(text.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: ""))
        return min(typed ?? 0, left)
    }

    private func takeCash() {
        // In the order ticked, only the ones the deposit reached (S-13 v2).
        let used = cashPicked.filter { (cashUse[$0] ?? 0) > 0 }
        let names = Set(cash.filter { used.contains($0.id) }.map(\.name))
        add(Part(kind: "cash", amount: cashUse.values.reduce(0, +),
                 person: names.count == 1 ? names.first : nil, cashIds: used), next: false)
        afterCash()
    }

    private func afterCash() {
        step = leftCents == 0 ? .review : .owing
    }

    private func takeOwing() {
        // S-35b: what it didn't pay back goes on to "What's the other $x?" (S-11 v2).
        let asked = asking
        let all = owing + found
        for (id, amount) in picked {
            guard let o = all.first(where: { $0.id == id }) else { continue }
            let person = o.person ?? sender
            parts.removeAll { $0.charge == o.charge && $0.person == person && ["payback", "refund"].contains($0.kind) }
            // The same shop sending money back is a refund; anyone else, a payback.
            let refund = o.person == nil && o.merchant.lowercased() == deposit.name.lowercased()
            parts.append(Part(kind: refund ? "refund" : "payback", amount: amount, charge: o.charge, merchant: o.merchant,
                              person: refund ? nil : person, date: o.date))
        }
        picked = [:]
        query = ""
        step = leftCents == 0 ? .review : (parts.isEmpty || asked ? .kind : .progress)
    }

    private func takeRefund() {
        guard let (id, amount) = picked.first, let o = (owing + found).first(where: { $0.id == id }) else { return }
        picked = [:]
        query = ""
        add(Part(kind: step == .work ? "reimbursement" : "refund", amount: amount, charge: o.charge,
                 merchant: o.merchant, date: o.date))
    }

    /// S-11 v2: what each tile makes of "How much of it?" (SPLIT-04).
    private func take(_ key: String) {
        let amount = chosenAmount
        guard amount >= 0.005 else { return }
        switch key {
        case "regular": add(Part(kind: "income", amount: amount, incomeKind: "salary"))
        case "bonus": add(Part(kind: "income", amount: amount, incomeKind: "bonus"))
        case "gifts": add(Part(kind: "gift", amount: amount))
        // S-11k (SPLIT-18): Other income asks which kind first.
        case "other":
            otherAmount = amount
            step = .otherKind
        case "paid_back":
            if !editing.isEmpty {
                // S-10e: the purchases it already pays back stay listed, ticked.
                for p in parts where p.kind == "payback" && !p.held {
                    if let c = p.charge { picked[c + "|" + (p.person ?? "")] = p.amount }
                }
                parts.removeAll { $0.kind == "payback" && !$0.held }
            }
            step = .owing
        case "refund", "reimbursement":
            picked = [:]
            step = key == "refund" ? .refund : .work
            Task { await search() }
        case "own": add(Part(kind: "moved", amount: amount))
        case "loan": add(Part(kind: "loan", amount: amount))
        case "out_of_savings": add(Part(kind: "savings", amount: amount))
        case "lent_back": add(Part(kind: "lent_back", amount: amount))
        case "overpaid": add(Part(kind: "overpaid", amount: amount, person: who))
        case "category": pickingCategory = amount
        default: break
        }
    }

    /// Adds a part, then on to what's left: S-11 v2 comes back for the new
    /// rest, or Check and save when nothing is.
    private func add(_ part: Part, next: Bool = true, then: Step = .kind) {
        guard part.amount > 0 else { return }
        parts.append(part)
        partAmount = ""
        if next { step = leftCents == 0 ? .review : then }
    }

    // MARK: Server

    private func load() async {
        struct CashReply: Decodable { let cash: [Lenient<Cash>] }
        struct Linked: Decodable { let id: String; let merchant: String; let date: String; let amount: Double; let person: String? }
        struct OwingReply: Decodable {
            let from: String?; let named: String?; let items: [Lenient<Owing>]; let linked: [Lenient<Linked>]?
        }
        if !editing.isEmpty && parts.isEmpty {
            // S-10e: what it's in now; a part still to sort is Left to sort again.
            parts = editing.filter { $0.kind != "rest" }.map { Part(saved: $0) }
        }
        if let r: CashReply = try? await api.get("api/transactions/\(deposit.id)/cash-matches") {
            cash = r.cash.compactMap { $0.value }
        }
        if let r: OwingReply = try? await api.get("api/transactions/\(deposit.id)/owing") {
            sender = r.from
            named = r.named
            var items = r.items.compactMap { $0.value }
            if !editing.isEmpty {
                // S-10e: the purchases this deposit already pays back stay listed,
                // with what it pays on top of anything still owed.
                for l in (r.linked ?? []).compactMap({ $0.value }) {
                    if let i = items.firstIndex(where: { $0.charge == l.id && $0.person == l.person }) {
                        let o = items[i]
                        items[i] = Owing(charge: o.charge, merchant: o.merchant, date: o.date, owes: o.owes + l.amount,
                                         person: o.person, theirs: true, pending: o.pending)
                    } else {
                        items.insert(Owing(charge: l.id, merchant: l.merchant, date: l.date, owes: l.amount,
                                           person: l.person, theirs: true), at: 0)
                    }
                }
            }
            // Theirs, or, from someone Pearl can't name, whoever's share is closest.
            // Every share anyone owes her (2026-11-09), to tick as many as it
            // paid back: the sender's first, then everyone else's, closest
            // to what came in first.
            let close: (Owing, Owing) -> Bool = { abs($0.owes - self.deposit.amount) < abs($1.owes - self.deposit.amount) }
            owing = items.filter { $0.theirs == true } + items.filter { $0.theirs != true }.sorted(by: close)
        }
        if !editing.isEmpty {
            step = .progress
            return
        }
        step = !cash.isEmpty ? .cash : .owing
        if step == .owing {
            // Pearl's likeliest: their shares, up to what came in.
            for o in owing where sender != nil && o.theirs == true { toggle(o) }
            // THL-181 (SPLIT-21): from someone Pearl can't name, only the one
            // share that is exactly its amount is ticked (S-35, "same amount");
            // two or none, and she's asked (S-35a, S-35b).
            if sender == nil, fits.count == 1 { toggle(fits[0]) }
        }
    }

    private func search() async {
        struct Reply: Decodable { let charges: [Lenient<Charge>] }
        struct Charge: Decodable {
            let id: String; let date: String; let merchant: String; let left: Double?; let split: Bool?
        }
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty || step == .refund || step == .work else { found = []; return }
        if let r: Reply = try? await api.get("api/transactions/\(deposit.id)/charges", query: ["q": q]) {
            found = r.charges.compactMap { $0.value }.filter { ($0.left ?? 0) >= 0.01 }.map {
                Owing(charge: $0.id, merchant: $0.merchant, date: $0.date, owes: $0.left ?? 0, person: nil, theirs: nil,
                      notSplit: $0.split == false && step == .owing)
            }
        }
    }

    private func save(later: Bool) async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["parts": parts.map(\.body), "later": later]
        // S-10e: Save changes replaces the parts it had (SPLIT-03).
        if !editing.isEmpty { body["replace"] = true }
        if let held = heldSplit, parts.contains(where: { $0.held }) {
            // S-12c (SPLIT-07): the split and the link in one request.
            body["split"] = held.body.merging(["charge": held.charge]) { _, new in new }
        }
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(deposit.id)/parts", body)
            // A failed save leaves the sheet open with nothing split or linked.
            heldSplit = nil
            onSaved(reply)
        } catch {
            self.error = error.localizedDescription
        }
    }

    // MARK: Pieces

    private func cents(_ x: Double) -> Int { Int((x * 100).rounded()) }

    private func label(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16)
    }

    /// "● Linked $428.00   ● Not linked $172.00" under a filling bar.
    private func bar(sorted: Double, first: String, second: String) -> some View {
        let whole = max(deposit.amount, 0.01)
        let done = min(sorted, deposit.amount)
        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Pearl.ink.opacity(0.1))
                    Capsule().fill(Pearl.action).frame(width: g.size.width * done / whole)
                }
            }
            .frame(height: 6)
            HStack(spacing: 14) {
                legend(Pearl.action, "\(first) \(Format.amount(done))")
                legend(Pearl.ink.opacity(0.2), "\(second) \(Format.amount(deposit.amount - done))")
            }
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
        }
        .padding(.top, 4)
        .accessibilityElement(children: .combine)
    }

    private func legend(_ color: Color, _ text: String) -> some View {
        HStack(spacing: 5) {
            Circle().fill(color).frame(width: 7, height: 7)
            Text(text).lineLimit(1).minimumScaleFactor(0.8)
        }
    }

    /// `trait` off when the caller speaks the state itself (S-35a's "not selected").
    private func pickRow(name: String, sub: String, amount: Double, on: Bool, trait: Bool = true,
                         _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                }
                Spacer(minLength: 8)
                Text(Format.amount(amount)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22)).foregroundColor(on ? Pearl.action : Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 56).padding(.vertical, 2).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on && trait ? .isSelected : [])
    }
}

// MARK: - S-14 Owed to you

@MainActor
struct OwedView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var owed: OwedOverview?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                if let owed = owed {
                    GlassCard {
                        VStack(alignment: .leading, spacing: 4) {
                            Text(Format.amount(owed.total))
                                .font(.custom("Fraunces-SemiBold", size: 34, relativeTo: .largeTitle))
                                .foregroundColor(Pearl.ink)
                            Text(owed.people == 0 ? "Nobody owes you anything"
                                 : "owed to you by \(owed.people) \(owed.people == 1 ? "person" : "people")")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        .padding(16)
                    }
                    if !owed.owesYou.isEmpty {
                        section("Owes you")
                        GlassCard {
                            ForEach(Array(owed.owesYou.enumerated()), id: \.element.id) { i, r in
                                if i > 0 { RowSeparator(inset: 64) }
                                personRow(r.name, sub: line(r), amount: r.total, tone: Pearl.ink)
                            }
                        }
                    }
                    if !owed.youOwe.isEmpty {
                        section("You owe")
                        GlassCard {
                            ForEach(Array(owed.youOwe.enumerated()), id: \.element.id) { i, r in
                                if i > 0 { RowSeparator(inset: 64) }
                                personRow(r.name, sub: "Overpaid for " + (r.items.first?.merchant ?? "a purchase"),
                                          amount: r.total, tone: Pearl.ink)
                            }
                        }
                    }
                    if !owed.paidBack.isEmpty {
                        section("Paid back this month")
                        GlassCard {
                            ForEach(Array(owed.paidBack.enumerated()), id: \.offset) { i, b in
                                if i > 0 { RowSeparator(inset: 64) }
                                // SPLIT-14: "PayPal" or "Another app"; SPLIT-15: one cash
                                // payment, with what a deposit holds under it. SPLIT-19
                                // (S-11c): one payment that paid back several purchases
                                // reads "Cash · Nov 13 · paid back Loblaws and Pizza Nova".
                                let how = b.cash == true ? "Cash" : b.app == true ? (b.appName ?? "Another app") : nil
                                personRow(b.name ?? "Someone",
                                          sub: (b.paidBack.map { [how, Format.short(b.date), "paid back \(Format.andList($0))"] }
                                                ?? [b.merchant, Format.short(b.date), how])
                                            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · "),
                                          amount: b.amount, tone: Pearl.moneyIn,
                                          note: b.deposited.map { d in
                                              "\(Format.amount(d)) deposited" + (b.depositedOn.map { " \(Format.short($0))" } ?? "")
                                                  + " · \(Format.amount(b.still ?? 0)) still cash" })
                            }
                        }
                    }
                } else if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(16)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold)).foregroundColor(Pearl.ink)
                }
                .accessibilityLabel("Back")
            }
            ToolbarItem(placement: .principal) {
                Text("Owed to you").font(Nacre.headline).foregroundColor(Pearl.ink)
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
    }

    /// "Loblaws · Nov 11", or "2 purchases".
    private func line(_ r: OwedOverview.Row) -> String {
        if r.items.count == 1, let i = r.items.first {
            return [i.merchant, Format.short(i.date)].compactMap { $0 }.joined(separator: " · ")
        }
        return "\(r.items.count) purchases"
    }

    private func section(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 12)
            .accessibilityAddTraits(.isHeader)
    }

    private func personRow(_ name: String, sub: String, amount: Double, tone: Color,
                           note: String? = nil) -> some View {
        HStack(spacing: 12) {
            Initials(name: name, size: 34)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                if let note = note {
                    Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            Spacer(minLength: 8)
            Text(Format.amount(amount)).font(Nacre.headline).monospacedDigit().foregroundColor(tone)
        }
        .padding(.horizontal, 16).frame(minHeight: 56)
        .accessibilityElement(children: .combine)
    }

    private func load() async {
        do {
            owed = try await app.api.get("api/owed")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}
