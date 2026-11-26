import SwiftUI

// Paid back from the purchase (Figma Proposals › "Paid back" 1351:8769,
// note 1352:10319; approved by the product owner 2026-11-15; THL-289,
// THL-291, THL-181). Her own row's ••• on a split starts with "Find what
// paid it back" (PB-20, in SplitMenus.swift), which opens "What paid this
// back?" (PB-22, as redrawn by LT-01; P5a "Which money paid this back?"
// since the fewer-taps boards, never a dead end). Once
// she picks the money, the usual steps run: PB-11 with the kind picked, then
// Work and The shop as T-09w / T-09rs (extras S-11w / S-11m). Money from
// someone on the split pays their share, so it goes straight to their Mark
// paid back, PB-13 / PB-13b (PartsFlow.swift). Work and The shop are Many
// purchases now (MP-01 / MP-02, 2026-11-17): this purchase ticked with any
// others the money fits, the rest (S-11w / S-11m) in the same save. Money already paying back another purchase is
// PB-24: its free part links at once; taking more always asks. Pearl
// sheets, never a stock dialog.

/// GET /api/transactions/<purchase>/paid-back-find (finance/parts_api.py).
struct PaidBackFind: Decodable {
    let merchant: String
    /// The purchase's day: LIKELY is money in after it.
    let date: String
    /// The whole purchase, and her share of it.
    let amount: Double
    let share: Double
    /// PB-23's "about $60": what she typed, or her share.
    let about: Double
    /// What of the purchase hasn't been paid back yet.
    var left: Double? = nil
    let candidates: [Lenient<Candidate>]

    struct Candidate: Decodable, Identifiable, Hashable {
        let id: String
        let date: String
        /// LT-01's tidy name: "Northwind Ltd", "Sam" (not "Cash Received -
        /// Samlee").
        let payer: String
        let amount: Double
        /// "work", "shop" or "person": the answer PB-11 picks.
        let kind: String?
        /// Who on the split, for A person.
        let person: String?
        /// The one fact after the date: "work", "refund". Empty for someone
        /// on the split; their group header says it.
        let why: String
        /// PB-24: it already pays back another purchase.
        let taken: Taken?
        /// P5 (fewer taps): the person an e-Transfer names, if any. Only a
        /// suggestion: it is theirs once she picks it.
        var sender: String? = nil

        struct Taken: Decodable, Hashable {
            let free: Double
            let need: Double
            let more: Double
            let other: Other?

            struct Other: Decodable, Hashable {
                let id: String
                let merchant: String
            }
        }

        var who: PaidBackWho? {
            switch kind {
            case "work": return .work
            case "shop": return .shop
            case "person": return .person
            default: return nil
            }
        }

        /// PB-24 asks only when she needs more than is free and there's
        /// another purchase to take it from.
        var asks: Bool {
            guard let t = taken else { return false }
            return t.other != nil && t.more >= 0.005 && t.free < t.need - 0.005
        }
    }
}

/// P5a / P5c (TP-P5-FromPurchase, fewer taps, approved 2026-11-26; was
/// PB-22 as LT-01 drew it): "Which money paid this back?". The purchase
/// ("−$90.00 · Nov 23 · split with Priya"), "Search money in", then money
/// from the people on the split first, each under "From Priya", including
/// amounts smaller than their share with a plain line ("Nov 25 · $2.50 less
/// than Priya’s $45.00"); then "Other money in". On a purchase nobody split,
/// one list, "Money in since Nov 22". Never a dead end: with nothing close it
/// still lists recent money in (GET …/paid-back-recent, finance/many_api.py).
/// A tap is the answer: there is no Next.
struct PaidBackFindSheet: View {
    let purchase: Transaction
    let api: APIClient
    /// The picked money; the opener saves it or asks one more thing.
    let onPick: (PaidBackFind.Candidate, PaidBackFind) async -> String?
    let onClose: () -> Void

    @State private var found: PaidBackFind?
    @State private var query = ""
    @State private var loading = true
    @State private var busy: String?
    @State private var error: String?
    /// The list didn't load, so the error line gets Try again (UI audit).
    @State private var loadFailed = false
    @FocusState private var searching: Bool

    private var rows: [PaidBackFind.Candidate] { found?.candidates.compactMap(\.value) ?? [] }
    private var people: [Transaction.Splitting.Person] { purchase.splitting?.people ?? [] }

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitleBar(title: "Which money paid this back?", close: onClose).sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    APQuestionWho(name: purchase.merchant, amount: headLine, tone: Pearl.muted, sub: nil)
                        .padding(.bottom, 4)
                    searchField
                    list
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                            .padding(.horizontal, 16)
                        if loadFailed {
                            Button("Try again") { Task { await load() } }
                                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                                .disabled(loading)
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
                .sheetPart()
            }
            .scrollDismissesKeyboard(.interactively)
        }
        .background(APSheetSurface())
        .fitsContent()
        .presentationDragIndicator(.visible)
        .task(id: query) {
            if !query.isEmpty { try? await Task.sleep(nanoseconds: 250_000_000) }
            if !Task.isCancelled { await load() }
        }
    }

    /// "−$90.00 · Nov 23 · split with Priya", or "· not split".
    private var headLine: String {
        let whole = "\u{2212}" + Format.amount(purchase.fullAmount ?? purchase.amount)
        let with = people.isEmpty ? "not split" : "split with \(Format.andList(people.map(\.name)))"
        return [whole, Format.short(purchase.date), with].joined(separator: " · ")
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Search money in").foregroundColor(Pearl.muted))
                .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                .autocorrectionDisabled().textInputAutocapitalization(.never)
                .focused($searching)
                .accessibilityLabel("Search money in, by name or amount")
        }
        .padding(.horizontal, 14).frame(minHeight: 44)
        .wellStyle(focused: searching)
        .padding(.top, 10)
    }

    @ViewBuilder private var list: some View {
        if loading && found == nil {
            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
        } else if let f = found, rows.isEmpty {
            // Only when nothing at all came in (or the search found nothing).
            Text(query.isEmpty ? "No money in since \(Format.short(f.date)) yet." : "Nothing matches “\(query)”.")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity).padding(.vertical, 24)
        } else if let f = found {
            ForEach(groups(f), id: \.key) { g in
                APSheetLabel(text: g.header)
                APCard {
                    ForEach(Array(g.rows.enumerated()), id: \.element.id) { i, c in
                        if i > 0 { APSeparator() }
                        row(c)
                    }
                }
            }
        }
    }

    /// P5a: "From Priya" for each person on the split (in the order their
    /// money came), work and refunds as "Your share", then "Other money in".
    /// P5c: a purchase nobody split is one list.
    private func groups(_ f: PaidBackFind) -> [(key: String, header: String, rows: [PaidBackFind.Candidate])] {
        if people.isEmpty {
            return [("all", "Money in since \(Format.short(f.date))", rows)]
        }
        var out: [(key: String, header: String, rows: [PaidBackFind.Candidate])] = []
        var names: [String] = []
        for c in rows where c.kind == "person" {
            let name = c.person ?? c.payer
            if !names.contains(name) { names.append(name) }
        }
        for name in names {
            out.append(("p:" + name, "From \(Self.first(name))",
                        rows.filter { $0.kind == "person" && ($0.person ?? $0.payer) == name }))
        }
        let yours = rows.filter { $0.kind == "work" || $0.kind == "shop" }
        if !yours.isEmpty { out.append(("yours", "Your share", yours)) }
        let other = rows.filter { $0.who == nil }
        if !other.isEmpty { out.append(("other", "Other money in", other)) }
        return out
    }

    static func first(_ name: String) -> String {
        name.split(separator: " ").first.map(String.init) ?? name
    }

    /// What they owe on this split, for the compare line.
    private func owes(_ c: PaidBackFind.Candidate) -> Transaction.Splitting.Person? {
        guard c.kind == "person", let name = c.person else { return nil }
        return people.first { samePerson($0.name, name) }
    }

    /// "Nov 25 · $2.50 less than Priya’s $45.00"; "Nov 24 · no name on it";
    /// "Nov 14 · work".
    func line(_ c: PaidBackFind.Candidate) -> String {
        var bits = [Format.short(c.date)]
        if let p = owes(c), p.owes >= 0.005 {
            let diff = c.amount - p.owes
            let whose = possessive(Self.first(p.name))
            if diff <= -0.005 {
                bits.append("\(Format.amount(-diff)) less than \(whose) \(Format.amount(p.owes))")
            } else if diff >= 0.005 {
                bits.append("\(Format.amount(diff)) more than \(whose) \(Format.amount(p.owes))")
            }
        } else if c.kind == nil && (c.sender ?? "").isEmpty {
            bits.append("no name on it")
        } else if !c.why.isEmpty {
            bits.append(c.why)
        }
        return bits.joined(separator: " · ")
    }

    /// kit `.row`: the face, the tidy name over the line, "+$42.50" in green.
    private func row(_ c: PaidBackFind.Candidate) -> some View {
        Button {
            guard busy == nil, let f = found else { return }
            Task {
                busy = c.id
                loadFailed = false
                error = await onPick(c, f)
                busy = nil
            }
        } label: {
            APPersonRow(face: c.payer, name: c.payer, line: line(c)) {
                if busy == c.id {
                    ProgressView()
                } else {
                    Text("+" + Format.amount(c.amount)).font(Nacre.headline).monospacedDigit()
                        .foregroundColor(Pearl.moneyIn)
                }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy != nil)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(c.payer), \(Format.amount(c.amount)) in, \(line(c))")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("paid-back-row")
    }

    private func load() async {
        loading = true
        defer { loading = false }
        let q = query.trimmingCharacters(in: .whitespaces)
        do {
            // Empty: likely first, then recent money in, so it's never empty
            // while anything came in. A search: the finder's own.
            let f: PaidBackFind = q.isEmpty
                ? try await api.get("api/transactions/\(purchase.id)/paid-back-recent")
                : try await api.get("api/transactions/\(purchase.id)/paid-back-find", query: ["q": q])
            found = f
            error = nil
            loadFailed = false
        } catch {
            if error is CancellationError { return }
            self.error = "Couldn’t load your money in."
            loadFailed = true
        }
    }
}

/// P5d / P5h (TP-P5-FromPurchase, TP-P5-NeedsALook): the money has no
/// clear name, so Pearl asks once. Everyone on the split first ("On Pai
/// Northern Thai", with what they owe), then the people she has split with,
/// and a field to type any name. A pick saves; nothing is remembered.
struct PaybackSenderSheet: View {
    let money: PaidBackFind.Candidate
    let purchase: Transaction
    let api: APIClient
    let onPick: (String) async -> String?
    let onBack: () -> Void
    let onClose: () -> Void

    @State private var typed = ""
    @State private var recent: [String] = []
    @State private var busy: String?
    @State private var error: String?
    @FocusState private var focused: Bool

    private var onSplit: [Transaction.Splitting.Person] { purchase.splitting?.people ?? [] }
    private var others: [String] {
        recent.filter { n in !onSplit.contains { samePerson($0.name, n) } }
    }
    private var name: String { typed.trimmingCharacters(in: .whitespaces) }

    var body: some View {
        VStack(spacing: 0) {
            APSheetTitleBar(title: "Who sent this?", back: onBack, close: onClose)
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    APQuestionWho(name: money.payer,
                                   amount: "+\(Format.amount(money.amount)) · \(Format.short(money.date)) · for \(purchase.merchant)",
                                   tone: Pearl.moneyIn, sub: nil)
                    HStack(spacing: 8) {
                        TextField("", text: $typed, prompt: Text("Type a name").foregroundColor(Pearl.muted))
                            .font(Nacre.body).foregroundColor(Pearl.ink).tint(Pearl.action)
                            .textInputAutocapitalization(.words).autocorrectionDisabled()
                            .focused($focused)
                            .submitLabel(.done).onSubmit { pick(name) }
                            .accessibilityIdentifier("who-sent-name")
                        if !name.isEmpty {
                            Button("Save") { pick(name) }.font(Nacre.textButton).foregroundColor(Pearl.link)
                                .disabled(busy != nil)
                        }
                    }
                    .padding(.horizontal, 14).frame(minHeight: 48)
                    .wellStyle(focused: focused)
                    .padding(.top, 6)
                    if let error = error { APErrorLine(text: error) }
                    if !onSplit.isEmpty {
                        APSheetLabel(text: "On \(purchase.merchant)")
                        APCard {
                            ForEach(Array(onSplit.enumerated()), id: \.element.name) { i, p in
                                if i > 0 { APSeparator() }
                                person(p.name, line: p.owes >= 0.005 ? "Owes \(Format.amount(p.owes))" : nil)
                            }
                        }
                    }
                    if !others.isEmpty {
                        APSheetLabel(text: onSplit.isEmpty ? "People you split with" : "Other people")
                        APCard {
                            ForEach(Array(others.enumerated()), id: \.element) { i, n in
                                if i > 0 { APSeparator() }
                                person(n, line: nil)
                            }
                        }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
        }
        .background(APSheetSurface())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task {
            struct Past: Decodable { let name: String }
            struct Reply: Decodable { let people: [Lenient<Past>] }
            let r: Reply? = try? await api.get("api/people/recent")
            recent = (r?.people ?? []).compactMap { $0.value?.name }
        }
    }

    private func person(_ n: String, line: String?) -> some View {
        Button { pick(n) } label: {
            APPersonRow(face: n, name: n, line: line) {
                if busy == n { ProgressView() }
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy != nil)
    }

    private func pick(_ n: String) {
        guard !n.isEmpty, busy == nil else { return }
        Task {
            busy = n
            error = await onPick(n)
            busy = nil
        }
    }
}

/// PB-24 (1359:10057, dark 1359:10117): she needs more than is free of a
/// deposit that already pays back another purchase. Eyebrow "NORTHWIND LTD ·
/// +$60.00 · NOV 14", "Take $40.00 from Air Canada?", and Take or Use only
/// the free part. With nothing free, the body starts "All of this deposit
/// pays back Air Canada." and the second button leaves it there.
struct PaidBackTakeSheet: View {
    let c: PaidBackFind.Candidate
    var busy = false
    var error: String? = nil
    let onTake: () -> Void
    let onFreeOnly: () -> Void
    let onClose: () -> Void

    var body: some View {
        let t = c.taken
        let free = t?.free ?? 0
        let more = Format.amount(t?.more ?? 0)
        let other = t?.other?.merchant ?? ""
        let none = free < 0.005
        APSheet {
            APSheetHeader(overline: "\(c.payer) · +\(Format.amount(c.amount)) · \(Format.short(c.date))",
                             title: "Take \(more) from \(other)?", close: onClose)
            Text(none
                 ? "All of this deposit pays back \(other). Taking it means \(other) counts \(more) more again."
                 : "\(Format.amount(free)) of this deposit is free, so it pays back your share first. The other \(more) pays back \(other). Taking it means \(other) counts \(more) more again.")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
            }
        } footer: {
            PearlSheetButtons(primary: "Take \(more)", busy: busy,
                              secondary: none ? "Leave it on \(other)" : "Use only the \(Format.amount(free))",
                              onPrimary: onTake, onSecondary: onFreeOnly)
        }
    }
}

/// Where a step of Find what paid it back is.
enum PaidBackStep: Identifiable {
    case find
    /// PB-11 with the match's kind picked.
    case who(PaidBackFind.Candidate)
    /// PB-24.
    case take(PaidBackFind.Candidate)
    /// PB-13 / PB-13b for a person's share of this purchase.
    case person(PaidBackFind.Candidate)
    /// MP-01 / MP-02: Work or The shop, this purchase ticked.
    case many(PaidBackFind.Candidate, PaidBackWho)
    /// P5d: no clear name on the money, so Who sent this? once.
    case sender(PaidBackFind.Candidate)

    var id: String {
        switch self {
        case .find: return "find"
        case .who(let c): return "who" + c.id
        case .take(let c): return "take" + c.id
        case .person(let c): return "person" + c.id
        case .many(let c, _): return "many" + c.id
        case .sender(let c): return "sender" + c.id
        }
    }
}

/// Runs Find what paid it back over the purchase's page: one sheet at a
/// time, the next opening once the last has gone. `done` gets the toast
/// and its Undo; `failed` what went wrong, nothing saved.
struct PaidBackFromPurchase: ViewModifier {
    @Binding var step: PaidBackStep?
    let purchase: Transaction
    let api: APIClient
    let done: (String, JSONValue?) -> Void
    let failed: (String) -> Void

    @State private var then: PaidBackStep?
    @State private var busy = false
    @State private var error: String?
    /// The list the money was picked from (what's left of the purchase).
    @State private var listed: PaidBackFind?

    func body(content: Content) -> some View {
        content.sheet(item: $step, onDismiss: {
            busy = false
            error = nil
            if let next = then {
                then = nil
                step = next
            }
        }) { s in
            sheet(s)
        }
    }

    /// Each step in its own frame (check_stack, 2026-11-26: one switch of
    /// every sheet was 48 KB in the Debug device build).
    private func sheet(_ s: PaidBackStep) -> AnyView {
        switch s {
        case .find: return findSheet()
        case .sender(let c): return senderSheet(c)
        case .who(let c): return whoSheet(c)
        case .take(let c): return takeSheet(c)
        case .person(let c): return personSheet(c)
        case .many(let c, let who): return manySheet(c, who)
        }
    }

    @inline(never) private func findSheet() -> AnyView {
        AnyView(PaidBackFindSheet(purchase: purchase, api: api, onPick: { c, f in
            listed = f
            return await next(c)
        }, onClose: { go(nil) }))
    }

    @inline(never) private func senderSheet(_ c: PaidBackFind.Candidate) -> AnyView {
        AnyView(PaybackSenderSheet(money: c, purchase: purchase, api: api,
                                   onPick: { name in await save(c, person: name) },
                                   onBack: { go(.find) }, onClose: { go(nil) }))
    }

    /// PB-11 (1351:9324): the face and the money, the kind picked.
    @inline(never) private func whoSheet(_ c: PaidBackFind.Candidate) -> AnyView {
        AnyView(PaidBackWhoSheet(face: c.payer,
                                 sub: "+\(Format.amount(c.amount)) · \(c.payer) · \(Format.short(c.date))",
                                 picked: c.who, pickedPerson: c.person,
                                 onPick: { who in pickWho(c, who) },
                                 onClose: { go(nil) }))
    }

    @inline(never) private func takeSheet(_ c: PaidBackFind.Candidate) -> AnyView {
        AnyView(PaidBackTakeSheet(c: c, busy: busy, error: error,
                                  onTake: { Task { await take(c, more: true) } },
                                  onFreeOnly: {
                                      if (c.taken?.free ?? 0) < 0.005 { go(nil) } else { Task { await take(c, more: false) } }
                                  },
                                  onClose: { go(nil) }))
    }

    /// PB-13 / PB-13b, saved as the deposit side saves them (PB-14's toast and Undo).
    @inline(never) private func personSheet(_ c: PaidBackFind.Candidate) -> AnyView {
        AnyView(PartsSheet(deposit: PartsDeposit(id: c.id, name: c.payer, amount: c.amount, date: c.date), api: api,
                           paidBack: true, payer: c.kind == "person" ? c.person : nil, forCharge: purchase.id,
                           person: c.kind == "person" ? c.person : nil) { reply in
            go(nil)
            done(reply.title ?? "Sorted.", reply.undo)
        })
    }

    /// MP-01 / MP-02, then S-11w / S-11m for what's left: one save, one Undo (MP-05).
    @inline(never) private func manySheet(_ c: PaidBackFind.Candidate, _ who: PaidBackWho) -> AnyView {
        AnyView(PartsSheet(deposit: PartsDeposit(id: c.id, name: c.payer, amount: c.amount, date: c.date), api: api,
                           forCharge: purchase.id, many: who) { reply in
            go(nil)
            done(reply.title ?? "Sorted.", reply.undo)
        })
    }

    /// Close this sheet, then open `next` (nil: none).
    private func go(_ next: PaidBackStep?) {
        then = next
        step = nil
    }

    /// PB-22's Next: PB-24 for money already paying back something else
    /// (its free part links at once when that's enough); someone on the
    /// split straight to their Mark paid back (LT-01: it pays their share,
    /// PB-13 / PB-13b); else PB-11.
    private func next(_ c: PaidBackFind.Candidate) async -> String? {
        if c.taken != nil {
            if c.asks { go(.take(c)); return nil }
            return await link(c, more: false)
        }
        // A work expense waiting to be reimbursed (product owner, 2026-11-21:
        // "it shouldn't even ask"): straight to her purchases, this one
        // ticked (MP-01). Everything else asks PB-11 (product owner,
        // 2026-11-24: always a person, the shop or other), with Pearl's read
        // of the money picked first.
        if purchase.excluded == "Waiting to be reimbursed" {
            go(.many(c, .work))
            return nil
        }
        // P5b (fewer taps): picking the money tells Pearl who and what, so
        // it saves. Work and the shop are known: their purchases (MP-01/02).
        if let who = c.who, who != .person {
            go(.many(c, who))
            return nil
        }
        // Someone on the split: their share; more than it by a dollar or
        // more still asks what the extra is (PB-13, S-11).
        if c.kind == "person", let name = c.person {
            if let p = onSplit(name), c.amount > p.owes + Self.small { go(.person(c)); return nil }
            return await save(c, person: name)
        }
        // A clear name (the e-Transfer's sender): on a purchase nobody split,
        // or one split only by paybacks, theirs at once (owner point 7);
        // someone on the split by that name, their share.
        if let sender = c.sender?.trimmingCharacters(in: .whitespaces), !sender.isEmpty {
            let people = purchase.splitting?.people ?? []
            if let p = people.first(where: { samePerson($0.name, sender) }) {
                if c.amount > p.owes + Self.small { go(.person(c)); return nil }
                return await save(c, person: p.name)
            }
            if people.isEmpty { return await save(c, person: sender) }
        }
        // No clear name: ask once (P5d). Never a guess, never the sender added.
        go(.sender(c))
        return nil
    }

    /// Under a dollar settles by itself (S-04s, small payback differences).
    private static let small = 0.995

    private func onSplit(_ name: String) -> Transaction.Splitting.Person? {
        purchase.splitting?.people.first { samePerson($0.name, name) }
    }

    /// P5b: POST …/parts for the money, one payback part: their share of a
    /// split (what they owe, never more), or on a purchase nobody split a
    /// split made by this payback, their share what they paid (`new_split`,
    /// finance/parts_api.py `_grows`). The rest is still owed, and shown.
    /// "Priya paid back $42.50." with Undo.
    private func save(_ c: PaidBackFind.Candidate, person: String) async -> String? {
        var amount = c.amount
        var part: [String: Any] = ["kind": "payback", "charge": purchase.id, "person": person]
        if let p = onSplit(person) {
            amount = min(c.amount, p.owes)
        } else {
            // Not on the split: it splits the purchase with them, if it can.
            let left = listed?.left ?? purchase.amount
            amount = min(c.amount, max(left, 0))
            part["new_split"] = true
        }
        guard amount >= 0.01 else { return "Nothing of \(purchase.merchant) is left to pay back." }
        part["amount"] = (amount * 100).rounded() / 100
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(c.id)/parts", ["parts": [part]])
            go(nil)
            let first = PaidBackFindSheet.first(person)
            done("\(first) paid back \(Format.amount(part["amount"] as? Double ?? amount)).", reply.undo)
            return nil
        } catch {
            return (error as? APIError)?.problem?.error ?? "Couldn’t save that. Try again."
        }
    }

    /// PB-11's answer. Work and The shop: MP-01 / MP-02 with this purchase
    /// ticked (Many purchases, replacing T-09w / T-09rs's one pick). A
    /// person is PB-13 for their share of it.
    private func pickWho(_ c: PaidBackFind.Candidate, _ who: PaidBackWho) {
        switch who {
        case .person: go(.person(c))
        case .work, .shop: go(.many(c, who))
        }
    }

    /// PB-24 Take, or Use only the free part.
    private func take(_ c: PaidBackFind.Candidate, more: Bool) async {
        busy = true
        if let problem = await link(c, more: more) {
            busy = false
            error = problem
        }
    }

    /// POST …/paid-back-take: "Linked $20.00 · Pai Northern Thai" or "Moved
    /// $40.00 from Air Canada", with Undo. Returns what went wrong, if it did.
    private func link(_ c: PaidBackFind.Candidate, more: Bool) async -> String? {
        do {
            let reply: MarkReply = try await api.post("api/transactions/\(purchase.id)/paid-back-take",
                                                      ["deposit": c.id, "take": more])
            go(nil)
            done(reply.title ?? "Sorted.", reply.undo)
            return nil
        } catch {
            return (error as? APIError)?.problem?.error ?? "Couldn’t save that. Try again."
        }
    }
}
