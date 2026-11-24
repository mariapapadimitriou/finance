import SwiftUI

// Paybacks 2 (approved by the product owner 2026-11-16; THL-289, THL-291,
// THL-181, THL-301, THL-305, THL-172). Figma Proposals › "Paybacks 2"
// 1406:5084, notes 1408:6438–6441.
//
// PP-01 1406:5216 (dark 1406:5547): Who paid you back? behind PB-42 › Who
//        paid › A person. Search, ON THIS SPLIT (today's answer ticked),
//        FROM PAST SPLITS (joint-account people say so), Someone new. A tap
//        answers; PP-02 1406:5860 (dark 1406:5984) is PB-42 again with the
//        ink toast and Undo (PaybackLinkViews.swift).
// TP-01 1406:6098 (dark 1406:6232): "Mom paid me back" on a transfer in from
//        a joint account (TransactionDetailView's TF-01).
// TP-02 1407:6398 (dark 1407:6648): What was this? on the money-in end
//        (AnswerSheet's T-12 tiles, Paid back there).
// TP-03 1407:6896 (dark 1407:7113): PB-30 with Mom picked (no PB-11), her
//        shares ticked to the amount, and what happens to the pair
//        (PartsFlow.swift, `joint`).
// TP-04 1407:7328 (dark 1407:7487): the money in afterwards; Undo puts the
//        transfer back (finance/joint.py). G2b-JointIn, rethought: the
//        hero is "From Mom" over "Joint ••1123 · Fri, Nov 14", and the
//        toast is "Mom paid back $240.00" (`JointPaybackFlow.shortTitle`).
// TP-05 1406:6361 (dark 1406:6494): two accounts only hers: no Paid back.
//        G2b-JointIn, rethought: no options list, the legs on one line,
//        one line why (`NoPaidBackCallout`) and This isn't a transfer as
//        the one quiet link (TransactionDetailView `mineLegs`).
//
// Every step is a Pearl sheet, never a stock alert or confirmation dialog.

/// A transfer in from a joint account, about to be said to be one of its
/// other owners paying her back (TP-01, TP-02 › Paid back).
struct JointPaybackStart: Identifiable, Hashable {
    let deposit: PartsDeposit
    /// The joint account's other owners, and "Joint ··1123".
    let people: [String]
    let account: String
    /// The money out of the joint account (the transfer's other end).
    let out: String
    /// Who paid her back, once known (one owner, or PP-01's tap).
    var person: String? = nil

    var id: String { deposit.id + "|" + (person ?? "") }
}

/// TP-01 / TP-02 › Paid back: with one other owner, straight to PB-30 with
/// them picked (TP-03); with more, PP-01 asks who first. Saved, `onSaved`
/// gets the reply with TP-04's toast ("Mom paid back $240.00") and Undo.
struct JointPaybackFlow: ViewModifier {
    @Binding var start: JointPaybackStart?
    let api: APIClient
    let onSaved: (MarkReply) -> Void

    @State private var asking: JointPaybackStart?
    @State private var linking: JointPaybackStart?
    @State private var picked: JointPaybackStart?

    func body(content: Content) -> some View {
        content
            .onChange(of: start) { s in
                guard let s = s else { return }
                start = nil
                if s.people.count > 1 {
                    asking = s
                } else {
                    var one = s
                    one.person = s.people.first
                    linking = one
                }
            }
            .sheet(item: $asking, onDismiss: {
                // The picker has gone, so PB-30 can open.
                let next = picked
                picked = nil
                if let next = next { linking = next }
            }) { s in
                // TP-01 (G2b-JointIn): Who paid? is a tile per other owner.
                JointWhoPaidSheet(start: s, onPick: { name in
                    var next = s
                    next.person = name
                    picked = next
                    asking = nil
                }, onClose: { asking = nil })
            }
            .sheet(item: $linking) { s in
                // TP-03: PB-30 with them picked; PB-11 is skipped.
                PartsSheet(deposit: s.deposit, api: api, paidBack: true, payer: s.person, joint: s) { reply in
                    linking = nil
                    onSaved(MarkReply(title: Self.shortTitle(reply.title), detail: reply.detail,
                                      undo: reply.undo, extra: reply.extra))
                }
            }
    }

    /// TP-04 (G2b-JointIn, rethought): the toast says who and how much,
    /// not how many purchases. "Mom paid back 3 purchases · $240.00" is
    /// "Mom paid back $240.00"; any other title stays as the server said.
    static func shortTitle(_ title: String?) -> String? {
        guard let title = title,
              title.range(of: #"^.+ paid back \d+ purchases · \$[\d,]+\.\d{2}$"#, options: .regularExpression) != nil,
              let mid = title.range(of: " paid back "), let dot = title.range(of: " · ", options: .backwards)
        else { return title }
        return "\(title[..<mid.lowerBound]) paid back \(title[dot.upperBound...])"
    }
}

/// PP-01 "Who paid you back?": search, the people on this split first (her
/// answer today ticked), then people from past splits, then Someone new.
/// A tap answers. Library Person rows; one accessibility element each.
@MainActor
struct WhoPaidPicker: View {
    struct Row: Hashable, Identifiable {
        let name: String
        /// "Today’s answer · on this split", "Owes you $30.00 on this split".
        let sub: String
        var ticked = false
        /// Its line stays as given (the sender, "Not on a split"), not
        /// /api/people/recent's.
        var fixed = false
        var id: String { name }
    }

    let api: APIClient
    /// "$26.65 toward Pizza Nova · e-Transfer, Nov 14".
    let sub: String
    /// ON THIS SPLIT (PB-42), or the joint account's people (TP-01).
    let top: [Row]
    /// "On this split"; none over the joint account's people.
    var topLabel: String? = nil
    var pastSplits = true
    var someoneNew = true
    /// FROM PAST SPLITS limited to these people (2026-11-16, A person from
    /// a sender Pearl can't match): whoever owes her, each with the line
    /// /api/people/recent gives them, or this row's until it has loaded.
    var onlyPast: [Row]? = nil
    let onPick: (String) -> Void
    let onClose: () -> Void

    @State private var query = ""
    @State private var recent: [Past]?
    @State private var typing = false
    /// Her contacts, searched as she types (product owner, 2026-11-24: who
    /// paid you back always looks in her contacts), where Someone new is
    /// allowed; a name nobody matches is one row to add.
    @StateObject private var contacts = ContactNames()
    /// PP-01 (G2-ALink): /api/people/recent didn't come back.
    @State private var loadFailed = false
    @State private var loading = false

    /// GET /api/people/recent, with PP-01's "4 splits" and joint flag.
    struct Past: Decodable, Hashable {
        let name: String
        let date: String
        var splits: Int? = nil
        var joint: Bool? = nil
    }

    private var q: String { query.trimmingCharacters(in: .whitespaces) }
    private func matches(_ name: String) -> Bool { q.isEmpty || name.localizedCaseInsensitiveContains(q) }

    var body: some View {
        APSheet {
            // G2-WhoPaid (people): the question centred, the payment under it.
            APSheetHeader(heading: "Who paid you back?", line: sub, close: onClose)
                .accessibilityHint("Paid back · Who paid")
            searchField
            if loadFailed {
                loadError
            } else {
                lists
            }
        }
        .task {
            if pastSplits || onlyPast != nil { await load() }
            if someoneNew { await contacts.load() }
        }
        .sheet(isPresented: $typing) {
            // Someone new: the people picker's name entry (AM-08p3), one name.
            PeoplePicker(api: api, overline: "Paid back · Who paid", title: "Who paid you back?", sub: sub,
                         limit: 1,
                         onClose: { typing = false }) { names in
                typing = false
                if let name = names.first { onPick(name) }
            }
        }
    }

    /// PP-01's load error (G2-ALink): under the search, the kit `.errline`
    /// and a Try again Secondary; nothing else until the people come back.
    private var loadError: some View {
        VStack(spacing: 12) {
            APErrorLine(text: "Couldn’t load who owes you. Try again.")
            Button("Try again") { Task { await load() } }
                .buttonStyle(APSecondaryButtonStyle())
                .disabled(loading)
                .accessibilityIdentifier("who-paid-try-again")
        }
        .padding(.top, 12)
    }

    /// ON THIS SPLIT, FROM PAST SPLITS and Someone new.
    @ViewBuilder private var lists: some View {
        let shown = top.filter { matches($0.name) }
        if !shown.isEmpty {
            if let label = topLabel { APSheetLabel(text: label) }
            card(shown)
        }
        if let only = onlyPast {
            let past = only.filter { matches($0.name) }.map { r in
                r.fixed ? r : (recent ?? []).first { $0.name == r.name }.map { Row(name: r.name, sub: pastLine($0)) } ?? r
            }
            if !past.isEmpty {
                APSheetLabel(text: "From past splits")
                card(past)
            }
        } else if pastSplits, let recent = recent {
            // Anyone already on this split shows once (the same name match).
            let past = recent.filter { p in matches(p.name) && !top.contains { samePerson($0.name, p.name) } }
                .map { Row(name: $0.name, sub: pastLine($0)) }
            if !past.isEmpty {
                APSheetLabel(text: "From past splits")
                card(past)
            }
        }
        if someoneNew, !q.isEmpty {
            // Her contacts that match what she typed, under the people Pearl
            // knows; then the typed name itself when nobody matches it.
            let listed = top.map(\.name) + (onlyPast ?? []).map(\.name) + (recent ?? []).map(\.name)
            let fromContacts = contacts.matches(q, excluding: listed)
            if !fromContacts.isEmpty {
                APSheetLabel(text: "Contacts")
                card(fromContacts.map { Row(name: $0, sub: "In your contacts") })
            }
            if !listed.contains(where: { $0.caseInsensitiveCompare(q) == .orderedSame }), !contacts.has(q) {
                APCard { AddTypedNameRow(name: q, picked: false) { onPick(q) } }
            }
            if contacts.state == .off { ContactsOffLine() }
        }
        if someoneNew {
            APOptionCard {
                Button { typing = true } label: {
                    HStack(spacing: 12) {
                        Text("+").font(.custom("Figtree-Medium", size: 14, relativeTo: .footnote))
                            .foregroundColor(Pearl.ink)
                            .frame(width: 40, height: 40).background(Circle().fill(APlus.face))
                            .accessibilityHidden(true)
                        texts("Someone new", "Type their name")
                        Spacer(minLength: 8)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Someone new, type their name")
                .accessibilityAddTraits(.isButton)
            }
        }
    }

    private var searchField: some View {
        PearlField(placeholder: "Search people", text: $query, kind: .search)
            .textInputAutocapitalization(.words).autocorrectionDisabled()
    }

    private func card(_ rows: [Row]) -> some View {
        APOptionCard {
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, r in
                if i > 0 { APSeparator() }
                row(r)
            }
        }
    }

    /// "Sam Lee" over "Today’s answer · on this split", with the tick.
    private func row(_ r: Row) -> some View {
        Button { onPick(r.name) } label: {
            HStack(spacing: 12) {
                APFace(name: r.name, size: 40)
                texts(r.name, r.sub)
                Spacer(minLength: 8)
                if r.ticked { APTickBox(on: true) }
            }
            .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(r.name), \(r.sub)")
        .accessibilityAddTraits(r.ticked ? [.isButton, .isSelected] : .isButton)
    }

    private func texts(_ title: String, _ sub: String) -> some View {
        VStack(alignment: .leading, spacing: 0) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
        }
        .fixedSize(horizontal: false, vertical: true)
    }

    /// "Your joint account · 4 splits", "Last split Oct 2".
    private func pastLine(_ p: Past) -> String {
        if p.joint == true {
            let n = p.splits ?? 1
            return "Your joint account · \(n) split\(n == 1 ? "" : "s")"
        }
        return "Last split \(Format.short(p.date))"
    }

    /// GET /api/people/recent. A failure is PP-01's load error (G2-ALink)
    /// with Try again, not an empty list that reads as nobody.
    private func load() async {
        struct Reply: Decodable { let people: [Lenient<Past>] }
        loading = true
        defer { loading = false }
        do {
            let r: Reply = try await api.get("api/people/recent")
            recent = r.people.compactMap { $0.value }
            loadFailed = false
        } catch is CancellationError {
            // The sheet closed while it loaded.
        } catch {
            loadFailed = true
        }
    }

    /// PB-42's ON THIS SPLIT: who's on it, and what each has done.
    static func onSplit(_ people: [Transaction.Splitting.Person], answer: String) -> [Row] {
        people.map { p in
            if samePerson(p.name, answer) || p.name == answer {
                return Row(name: p.name, sub: "Today’s answer · on this split", ticked: true)
            }
            if p.owes >= 0.005 {
                return Row(name: p.name, sub: "Owes you \(Format.amount(p.owes)) on this split")
            }
            if p.paid >= 0.005, let on = p.paidOn {
                return Row(name: p.name, sub: "Paid back · \(Format.short(on))")
            }
            return Row(name: p.name, sub: "On this split")
        }
    }
}

/// PP-01 for a payback onto a split she set up, from a sender Pearl can't
/// place on it (2026-11-16, `WhoPaidAsk`): only the split's people, no past
/// splits and no Someone new, so a payback never adds a person to her split.
/// A tap opens PB-30 for that person (Paybacks & undo, 1395:3405) with this
/// purchase ticked and their others as they add up, in this same sheet;
/// saved, `onPick` gets `.done` with its toast and one Undo. Someone who
/// owes nothing with an amount (a Not sure yet split) gets the same
/// payback as before.
@MainActor
struct WhoPaidAskSheet: View {
    let ask: WhoPaidAsk
    let api: APIClient
    let onPick: (ReviewAnswer) -> Void
    let onClose: () -> Void
    @State private var pb30: String?

    var body: some View {
        if let name = pb30, let deposit = ask.deposit {
            PartsSheet(deposit: PartsDeposit(id: deposit, name: ask.sender, amount: ask.amount, date: ask.date ?? ""),
                       api: api, paidBack: true, payer: name, person: name, mustTick: ask.charge) { reply in
                onPick(.done(reply))
            }
        } else {
            picker
        }
    }

    /// Their shares with an amount (…/owing?person=, as PB-30 reads them).
    private func picked(_ name: String) async {
        struct Reply: Decodable { let from: String?; let items: [Lenient<PartsSheet.Owing>] }
        if let deposit = ask.deposit,
           let r: Reply = try? await api.get("api/transactions/\(deposit)/owing", query: ["person": name]),
           r.from != nil,
           r.items.compactMap(\.value).contains(where: { $0.theirs == true && $0.unknown != true && $0.owes >= 0.005 }) {
            pb30 = name
            return
        }
        if let answer = ask.answer(name) { onPick(answer) } else { onClose() }
    }

    private var picker: some View {
        WhoPaidPicker(api: api, sub: "\(Format.amount(ask.amount)) toward \(ask.merchant) · \(ask.sender)",
                      top: ask.people.map { p in
                          WhoPaidPicker.Row(name: p.name, sub: (p.owes ?? 0) >= 0.005
                                            ? "Owes you \(Format.amount(p.owes ?? 0)) on this split" : "On this split")
                      },
                      topLabel: "On this split", pastSplits: false, someoneNew: false,
                      onPick: { name in Task { await picked(name) } },
                      onClose: onClose)
    }
}

/// TP-05 (G2b-JointIn, rethought): under a transfer between two accounts
/// only hers, one quiet line says why there's no Paid back.
struct NoPaidBackCallout: View {
    var body: some View {
        Text("Both accounts are only yours.")
            .font(Nacre.caption1).foregroundColor(Pearl.muted)
            .frame(maxWidth: .infinity)
            .padding(.top, 4)
            .accessibilityLabel("Both accounts are only yours, so there’s no Paid back here.")
    }
}

/// TP-01 (G2b-JointIn, rethought): "Who paid you back?" on money in from a
/// joint account with more than one other owner: the account and the
/// amount, then a tile per owner ("Mom · Joint with you"). A tap answers.
struct JointWhoPaidSheet: View {
    let start: JointPaybackStart
    let onPick: (String) -> Void
    let onClose: () -> Void

    var body: some View {
        PearlSheet {
            APSheetTitle(title: "Who paid you back?", close: onClose)
            HStack(spacing: 12) {
                APFace(name: start.account, size: 44)
                VStack(alignment: .leading, spacing: 2) {
                    Text(start.account).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(1)
                    Text("+\(Format.amount(start.deposit.amount)) \u{00B7} \(Format.short(start.deposit.date))")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .accessibilityElement(children: .combine)
            LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
                ForEach(start.people, id: \.self) { name in
                    Button { onPick(name) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            APIcon(symbol: "person").padding(.bottom, 8)
                            Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Text("Joint with you").font(Nacre.caption1).foregroundColor(Pearl.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(12)
                        .apCard()
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityIdentifier("joint-who-\(name)")
                }
            }
        }
    }
}
