import SwiftUI

// Overpaid and underpaid shares (REFRESH-18, approved 2026-11-25; THL-289,
// THL-291, THL-181, THL-301, THL-260). Claude Design › Cash flow ›
// G2-OverCard to G2-SmallLands, notes n-overunder and n-small. The rules are
// the server's (finance/over_under.py).
//
// S-11e "What's the extra $15.00?": the same sheet from the split card, the
// person's options, the deposit and Needs a look. Nothing picked; a tile
// answers at once; less than all of it and the rest is still asked.

/// What S-11e asks about: one person's extra on one purchase.
struct ExtraAsk: Identifiable, Hashable {
    let charge: String
    let merchant: String
    let name: String
    /// What's still a question, or all of it when she's changing it.
    let amount: Double
    let share: Double?
    /// "$10.00 was a gift." once some of it is said (S-11e2).
    var note: String? = nil
    /// "+$55.00 · e-Transfer · Nov 20".
    var paid: String? = nil
    /// The payment's deposit, for PB-30 and S-11 v2; nil when only cash paid.
    var deposit: String? = nil
    var day: String = ""
    /// Change what the extra is (S-40e2): what was said is taken back first.
    var again = false

    var id: String { charge + "|" + name }

    /// From a person on a split card (S-04o, S-40e, S-40e2, S-40s2).
    init?(charge: String, merchant: String, person p: Transaction.Splitting.Person, again: Bool = false) {
        guard let extra = p.extra else { return nil }
        let newest = (p.links ?? []).max { ($0.date, $0.id) < ($1.date, $1.id) }
        self.charge = charge
        self.merchant = merchant
        name = p.name
        share = p.share
        self.again = again
        // Changing it: everything over the share, the part already moved too.
        amount = again ? ExtraAsk.whole(p) : extra.amount
        note = again ? nil : extra.note
        if let link = newest {
            let whole = link.deposit?.amount ?? link.whole ?? link.amount
            paid = "+\(Format.amount(whole)) · \(link.word.map(ExtraAsk.cap) ?? PersonOptionsSheet.word(link)) · \(Format.short(link.date))"
            day = link.date
            deposit = ["cash", "app"].contains(link.kind) ? nil : (link.deposit?.id ?? link.inflow)
        }
        // Bank money under the newest cash payment can still be split up.
        if deposit == nil, let bank = (p.links ?? []).last(where: { !["cash", "app"].contains($0.kind) }) {
            deposit = bank.deposit?.id ?? bank.inflow
        }
    }

    /// From Needs a look (S-21o): the payment's row.
    init(over: Review.Item.Over, txn: BriefTransaction) {
        charge = over.charge
        merchant = over.merchant
        name = over.name
        amount = over.amount
        share = over.share
        note = over.note
        day = txn.date
        if txn.inflow {
            deposit = txn.id
            paid = "+\(Format.amount(txn.amount)) · \(ExtraAsk.cap(over.word ?? "payment")) · \(Format.short(txn.date))"
        }
    }

    /// From the deposit's page (PB-41o).
    init(over o: Transaction.OverPayment, merchant: String, deposit: Transaction) {
        charge = o.charge
        self.merchant = merchant
        name = o.name
        amount = o.asked ?? o.extra
        share = o.share
        note = o.note
        day = deposit.date
        self.deposit = deposit.partOf?.id ?? deposit.id
        paid = "+\(Format.amount(deposit.partOf?.amount ?? deposit.amount)) · \(ExtraAsk.cap(o.word ?? "payment")) · \(Format.short(deposit.date))"
    }

    /// "e-Transfer" stays; "payment" leads a phrase here, "Payment".
    private static func cap(_ word: String) -> String {
        word == "e-Transfer" ? word : word.prefix(1).uppercased() + word.dropFirst()
    }

    private static func whole(_ p: Transaction.Splitting.Person) -> Double {
        let moved = p.extra?.moved ?? 0
        return (((p.over ?? 0) + moved) * 100).rounded() / 100
    }
}

/// What S-11e saved: the toast and its Undo.
struct ExtraSaved {
    let toast: String
    let undo: JSONValue?
}

/// S-11e, S-11e2, S-11e5, and S-11e3 (PB-30) behind "Pays back something else".
@MainActor
struct ExtraSheet: View {
    let ask: ExtraAsk
    let api: APIClient
    let onSaved: (ExtraSaved) -> Void
    let onClose: () -> Void

    @State private var amount: String
    @State private var page: Page = .tiles
    @State private var busy = false
    @State private var error: String?
    @FocusState private var typing: Bool

    enum Page { case tiles, pays, other }

    init(ask: ExtraAsk, api: APIClient, onSaved: @escaping (ExtraSaved) -> Void, onClose: @escaping () -> Void) {
        self.ask = ask
        self.api = api
        self.onSaved = onSaved
        self.onClose = onClose
        _amount = State(initialValue: SplitSheet.plain(ask.amount))
    }

    static let failed = "Couldn’t save that. Nothing changed. Try again."

    /// S-11c's four kinds; "I owe it back" replaces "… overpaid" here.
    static let tiles: [CaseTile] = [
        CaseTile(key: "overpaid", label: "I owe it back", symbol: "person"),
        CaseTile(key: "payback", label: "Pays back something else", symbol: "arrow.uturn.backward"),
        CaseTile(key: "gift", label: "A gift", symbol: "gift"),
        CaseTile(key: "returned", label: "I sent it back", symbol: "arrow.left.arrow.right"),
    ]

    var body: some View {
        ZStack {
            switch page {
            case .tiles: tilesPage
            case .pays, .other: partsPage
            }
        }
        .interactiveDismissDisabled(busy)
    }

    private var tilesPage: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    APSheetHeader(heading: "What’s the extra \(Format.amount(ask.amount))?", face: ask.name,
                                  title: ask.name, sub: ask.paid, close: onClose)
                        .padding(.top, 20)
                    field
                    Text("THE EXTRA").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 4).accessibilityAddTraits(.isHeader)
                    // Cash alone has no payment to open PB-30 on; S-11c asked it then.
                    CaseGrid(cases: ask.deposit == nil ? Self.tiles.filter { $0.key != "payback" } : Self.tiles,
                             chosen: Binding(get: { nil }, set: { key in if let key = key { take(key) } }))
                        .disabled(busy || value < 0.005 || over)
                        .opacity(over ? 0.4 : 1)
                    if ask.deposit != nil {
                        Button("Something else…") { if ready { page = .other } }
                            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                            .frame(maxWidth: .infinity)
                            .disabled(busy)
                            .accessibilityHint("Shows every answer")
                    }
                    if busy { ProgressView().frame(maxWidth: .infinity) }
                    if let error = error { errorLine(error) }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .background(APSheetSurface())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    /// "How much of it?" over the well, and "Georgia Klev’s share is $40.00."
    /// or "$10.00 was a gift." under it.
    private var field: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("How much of it?").font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            HStack(spacing: 8) {
                Text("$").font(Nacre.body).foregroundColor(Pearl.muted).accessibilityHidden(true)
                TextField("", text: $amount, prompt: Text(SplitSheet.plain(ask.amount)).foregroundColor(Pearl.muted))
                    .font(Nacre.body).monospacedDigit().foregroundColor(Pearl.ink).tint(Pearl.action)
                    .keyboardType(.decimalPad)
                    .focused($typing)
                    .accessibilityLabel("How much of it")
                    .accessibilityHint("All \(Format.amount(ask.amount)) unless you type less")
                    .accessibilityIdentifier("extra-amount")
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 48)
            .wellStyle(focused: typing, error: over)
            .contentShape(Rectangle())
            .onTapGesture { typing = true }
            if over {
                // S-11xm over (REFRESH-03): the same words as the server's.
                Text("Only \(Format.amount(ask.amount)) is extra. Make it \(Format.amount(ask.amount)) or less.")
                    .font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            } else if let under = ask.note ?? ask.share.map({ "\(possessive(ask.name)) share is \(Format.amount($0))." }) {
                Text(under).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    private func errorLine(_ words: String) -> some View {
        HStack(spacing: 8) {
            Image(systemName: "exclamationmark.circle").font(.system(size: 15))
            Text(words).font(Nacre.subheadline).fixedSize(horizontal: false, vertical: true)
        }
        .foregroundColor(Pearl.danger)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
    }

    /// S-11e3: PB-30 for this much of it, nothing ticked. Something else…:
    /// S-11 v2's tiles. Both answer here, and their parts are the pieces.
    private var partsPage: some View {
        var deposit = PartsDeposit(id: ask.deposit ?? "", name: ask.name, amount: value, date: ask.day)
        deposit.paidLine = ask.paid
        return PartsSheet(deposit: deposit, api: api, paidBack: page == .pays, person: page == .pays ? ask.name : nil,
                          saying: page == .pays ? .pays : .other,
                          onPieces: { pieces in Task { await save(pieces) } },
                          onBack: { page = .tiles }) { _ in }
            .id(page)
    }

    private var value: Double {
        let text = amount.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return ask.amount }
        return Double(text.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")) ?? 0
    }

    private var over: Bool { cents(value) > cents(ask.amount) }
    private var ready: Bool { value >= 0.005 && !over && !busy }

    private func cents(_ x: Double) -> Int { Int((x * 100).rounded()) }

    private func take(_ key: String) {
        guard ready else { return }
        error = nil
        typing = false
        if key == "payback" {
            page = .pays
            return
        }
        Task { await save([["kind": key, "amount": Double(cents(value)) / 100]]) }
    }

    private func save(_ pieces: [[String: Any]]) async {
        busy = true
        defer { busy = false }
        struct Reply: Decodable { let toast: String?; let undo: JSONValue? }
        var body: [String: Any] = ["name": ask.name, "pieces": pieces]
        if ask.again { body["again"] = true }
        do {
            let r: Reply = try await api.post("api/transactions/\(ask.charge)/split/extra", body)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            onSaved(ExtraSaved(toast: r.toast ?? "", undo: r.undo))
        } catch {
            page = .tiles
            // S-11e5. The server's own words when it says why.
            if let e = error as? APIError, case .server = e { self.error = e.localizedDescription } else { self.error = Self.failed }
            UIAccessibility.post(notification: .announcement, argument: self.error ?? Self.failed)
        }
    }
}

/// S-04o's dashed chip, "What’s the extra $15.00?": the only question on the
/// row, so it opens S-11e while the rest of the row opens the options.
struct ExtraChip: View {
    let amount: Double
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            GuessChip(label: "What’s the extra \(Format.amount(amount))?", question: false)
                .padding(.vertical, 10).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("What’s the extra \(Format.amount(amount))?")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("extra-chip")
    }
}

/// `.who` for S-11e3: the ring, the name over "+$55.00 · e-Transfer · Nov 20".
struct SayingWho: View {
    let name: String
    let line: String

    var body: some View {
        HStack(spacing: 12) {
            APRingFace(name: name)
            VStack(alignment: .leading, spacing: 0) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink)
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
        }
        .accessibilityElement(children: .combine)
    }
}

/// S-11e on a page (its own modifier: check_stack).
struct ExtraSheetHost: ViewModifier {
    @Binding var ask: ExtraAsk?
    let api: APIClient
    let onSaved: (ExtraSaved) -> Void

    func body(content: Content) -> some View {
        content.sheet(item: $ask) { a in
            ExtraSheet(ask: a, api: api, onSaved: { saved in
                ask = nil
                onSaved(saved)
            }, onClose: { ask = nil })
        }
    }
}

/// PB-41o: "Corner Bistro" over "Georgia Klev’s share · Nov 16", $40.00, then
/// Extra with "What’s the extra $15.00?".
struct OverPaidCard: View {
    let over: Transaction.OverPayment
    let merchant: String
    let date: String
    let onOpen: () -> Void
    let onSay: () -> Void

    var body: some View {
        SolidCard {
            Button(action: onOpen) {
                HStack(spacing: 14) {
                    Initials(name: merchant)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Text("\(possessive(over.name)) share · \(Format.short(date))").font(Nacre.subheadline)
                            .foregroundColor(Pearl.muted).lineLimit(1)
                    }
                    Spacer(minLength: 8)
                    Text(Format.amount(over.back)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            .accessibilityHint("Opens the purchase")
            APSeparator()
            OverExtraRow(amount: over.extra, line: over.state == "ask" ? nil : over.line,
                         ask: over.asks ? (over.asked ?? over.extra) : nil, onSay: onSay)
        }
    }
}

/// "Extra" and its amount: the chip while it's a question, what she said
/// once it isn't, neither when it's small (PB-41s).
struct OverExtraRow: View {
    let amount: Double
    let line: String?
    let ask: Double?
    var onSay: () -> Void = {}

    var body: some View {
        HStack(alignment: .top, spacing: 14) {
            APIcon(symbol: "questionmark.circle").frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 0) {
                Text("Extra").font(Nacre.body).foregroundColor(Pearl.ink)
                    .padding(.top, ask == nil && line == nil ? 9 : 0)
                if let line = line {
                    Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let ask = ask { ExtraChip(amount: ask, action: onSay).padding(.vertical, -6) }
            }
            Spacer(minLength: 8)
            Text(Format.amount(amount)).font(Nacre.headline).monospacedDigit()
                .foregroundColor(ask == nil ? Pearl.muted : Pearl.ink).padding(.top, 9)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: ask == nil ? .combine : .contain)
    }
}

/// S-11e from Needs a look or Quick sort (its own view: check_stack). The
/// sheet goes, then the answer is told as any other.
@MainActor
struct ReviewExtraSheet: View {
    let over: Review.Item.Over
    let t: BriefTransaction
    let api: APIClient
    let close: () -> Void
    let onDone: (MarkReply) -> Void

    var body: some View {
        ExtraSheet(ask: ExtraAsk(over: over, txn: t), api: api, onSaved: { saved in
            close()
            onDone(MarkReply(title: saved.toast, detail: nil, undo: saved.undo))
        }, onClose: close)
    }
}
