import SwiftUI

// PB-41 / PB-42 · Link first, edit later (Paybacks & undo, approved
// 2026-11-16; THL-289, THL-291, THL-181, THL-301). Figma Proposals ›
// "Paybacks & undo" 1395:3376: PB-42 1395:5050 (dark 1395:5168), note
// 1397:4698. One link's options, the same sheet from the purchase (the
// PAID BACK row, S-05or; Sam's row on the split card, S-40c) and from the
// deposit (PB-41): How much (PB-13), Who paid (PB-11), Which purchase
// (PB-12), View the e-Transfer, Unlink… (says what changes). Each change is
// one request (POST …/paybacks/<inflow>/change) with one Undo.
//
// Paybacks 2 (approved 2026-11-16, Proposals › "Paybacks 2" 1406:5084):
// Who paid › A person opens PP-01 (1406:5216, JointPaybackViews.swift); a tap
// answers, and PP-02 (1406:5860) is this sheet again with the new person and
// the ink toast with Undo ("Priya paid this back, not Sam. Sam owes $26.65
// again."). Someone not on the split gets the payback as theirs, as PB-15.

@MainActor
struct PaybackLinkSheet: View {
    enum Step { case options, howMuch, which }

    let link: Transaction.LinkInfo
    /// The purchase it pays back.
    let charge: String
    let merchant: String
    let date: String
    /// What they still owe on it now, this link already counted.
    let owes: Double
    /// From the deposit (PB-41): she's on its page, so no View the e-Transfer.
    var fromDeposit = false
    var start: Step = .options
    let api: APIClient
    let onClose: () -> Void
    let onView: () -> Void
    let onUnlink: () -> Void
    /// The toast's words and its Undo (UN-01).
    let onDone: (String, JSONValue?) -> Void
    /// PP-01's ON THIS SPLIT: the people on the purchase's split.
    var people: [Transaction.Splitting.Person] = []
    /// PP-02: someone else paid it back; the caller opens this sheet again
    /// for them with the toast (words, Undo, who). Nil: `onDone`.
    var onPerson: ((String, JSONValue?, String) -> Void)? = nil
    /// PP-02: the ink toast with Undo, over the options.
    var notice: PearlToast.Model? = nil

    @State private var step: Step = .options
    @State private var busy = false
    @State private var error: String?
    // PB-13
    @State private var allOfIt = false
    @State private var partText = ""
    @State private var editingPart = false
    @FocusState private var partFocused: Bool
    @State private var letGoAsk = false
    // PB-11
    @State private var whoPaid = false
    // PP-01, once PB-11 has closed.
    @State private var aPerson = false
    @State private var choosing = false
    // PB-12
    @State private var shares: [PartsSheet.Owing]?
    @State private var pick: String?

    private var person: String { link.person ?? link.sheet.face }
    private var first: String { person.split(separator: " ").first.map(String.init) ?? person }
    private var word: String { link.word ?? "payment" }
    /// They owe nothing on it now: this link pays All of it.
    private var all: Bool { owes < 0.005 }
    /// What they'd owe without this link: PB-13's "How much of Sam's $60.00?".
    private var total: Double { owes + link.amount }
    /// The most this payment can put toward it: this link and what's still free.
    private var room: Double { link.amount + (link.free ?? 0) }

    var body: some View {
        Group {
            switch step {
            case .options: options
            case .howMuch: howMuch
            case .which: which
            }
        }
        .onAppear { step = start; allOfIt = all }
        .task(id: step) { if step == .which && shares == nil { await loadShares() } }
        .sheet(isPresented: $whoPaid, onDismiss: {
            if aPerson { aPerson = false; choosing = true }
        }) {
            // PB-11, A person picked: who it came from today.
            PaidBackWhoSheet(face: person, sub: "+\(Format.amount(link.whole ?? link.amount)) · \(word) from \(person) · \(Format.short(link.deposit?.date ?? link.date))",
                             picked: .person, pickedPerson: person,
                             onPick: { who in
                                 whoPaid = false
                                 switch who {
                                 // PP-01: which person (Paybacks 2).
                                 case .person: aPerson = true
                                 case .shop: Task { await change(["kind": "shop"]) }
                                 case .work: Task { await change(["kind": "work"]) }
                                 }
                             },
                             onClose: { whoPaid = false })
        }
        .sheet(isPresented: $choosing) {
            // PP-01 Who paid you back? A tap answers.
            WhoPaidPicker(api: api, sub: "\(Format.amount(link.amount)) toward \(merchant) · \(word), \(Format.short(link.deposit?.date ?? link.date))",
                          top: WhoPaidPicker.onSplit(people, answer: person), topLabel: "On this split",
                          onPick: { name in
                              choosing = false
                              guard name != person else { return }
                              Task { await changePerson(name) }
                          },
                          onClose: { choosing = false })
        }
        .sheet(isPresented: $letGoAsk) {
            // PB-13b: All of it, but the money is less than they owe.
            PaidBackLetGoSheet(name: first, merchant: merchant, paid: room, owes: total,
                               onLetGo: { letGoAsk = false; Task { await change(["amount": room, "let_go": true]) } },
                               onStillOwes: { letGoAsk = false; Task { await change(["amount": room]) } },
                               onClose: { letGoAsk = false })
        }
    }

    // MARK: PB-42 options

    /// "All of it · Nov 14" (TEXT-01): the title already names Sam.
    private var headerSub: String {
        "\(all ? "All" : "Part") of it · \(Format.short(link.deposit?.date ?? link.date))"
    }

    /// "Sam owes $26.65 again" (TEXT-01): what stays paid is S-34's to say.
    private var unlinkSub: String {
        "\(first) owes \(Format.amount(link.amount)) again"
    }

    private var options: some View {
        APSheet(dismissDisabled: busy) {
            if let notice = notice {
                // PP-02: what moved, with Undo.
                PearlToast(model: notice, stays: true) {}
            }
            APSheetHeader(overline: "Paid back", title: link.dialog, sub: headerSub, close: onClose)
            APOptionCard {
                APOptionRow(symbol: "target", title: "How much",
                               sub: all ? "All of it · \(Format.amount(link.amount))" : "Part of it · \(Format.amount(link.amount))") {
                    step = .howMuch
                }
                APSeparator()
                APOptionRow(symbol: "person", title: "Who paid", sub: person) { whoPaid = true }
                APSeparator()
                APOptionRow(symbol: "cart", title: "Which purchase", sub: "\(merchant) · \(Format.weekdayDay(date))") {
                    step = .which
                }
                if !fromDeposit && link.view != nil {
                    APSeparator()
                    APOptionRow(symbol: "eye", title: "View the \(word)", action: onView)
                        .accessibilityHint("Opens it here in Pearl")
                }
                APSeparator()
                APOptionRow(symbol: "xmark", title: "Unlink…", sub: unlinkSub, action: onUnlink)
            }
            errorLine
        }
    }

    @ViewBuilder private var errorLine: some View {
        if let error = error {
            Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    // MARK: PB-13 How much of their share (Paid back, 1352:716)

    private var partValue: Double {
        let text = partText.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return min(link.amount, room) }
        return Double(text.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")) ?? 0
    }

    private var partFits: Bool {
        let v = cents(partValue)
        return v >= 1 && v <= cents(room) && v < cents(total)
    }

    private var howMuch: some View {
        APSheet(dismissDisabled: busy) {
            APSheetHeader(overline: "\(merchant) · \(first) owes \(Format.amount(total))",
                             title: "How much of \(possessive(first)) \(Format.amount(total))?",
                             back: { if start == .options { step = .options } else { onClose() } },
                             close: onClose)
            APCard {
                // PB-13 for a person, UI audit: "Sam still owes $45.00", no
                // hint to tap it (the amount already looks editable).
                let owesAfter = Text("\(first) still owes \(Format.amount(max(0, total - partValue)))")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                if editingPart && !allOfIt {
                    choiceLine(on: true) {
                        HStack(spacing: 0) {
                            Text("Part of it · ").font(Nacre.body).foregroundColor(Pearl.ink)
                            TextField("", text: $partText, prompt: Text(Format.amount(partValue)).foregroundColor(Pearl.ink))
                                .font(Nacre.body).monospacedDigit().keyboardType(.decimalPad)
                                .focused($partFocused)
                                .accessibilityLabel("Part of it")
                                .accessibilityHint("Up to \(Format.amount(min(room, total))), less than \(Format.amount(total))")
                        }
                        owesAfter.fixedSize(horizontal: false, vertical: true)
                    }
                } else {
                    Button {
                        if !allOfIt { editingPart = true; partFocused = true }
                        allOfIt = false
                    } label: {
                        choiceLine(on: !allOfIt) {
                            Text("Part of it · \(Format.amount(partValue))").font(Nacre.body).foregroundColor(Pearl.ink)
                            owesAfter.fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityElement(children: .combine)
                    .accessibilityAddTraits(!allOfIt ? .isSelected : [])
                }
                APSeparator(afterFace: false)
                Button {
                    allOfIt = true
                    editingPart = false
                    partFocused = false
                } label: {
                    choiceLine(on: allOfIt) {
                        Text("All of it · \(Format.amount(total))").font(Nacre.body).foregroundColor(Pearl.ink)
                        Text("\(first)’s paid in full").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .combine)
                .accessibilityAddTraits(allOfIt ? .isSelected : [])
            }
            Text("\(possessive(first)) share of \(merchant) · \(Format.weekdayDay(date))")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity).multilineTextAlignment(.center)
            errorLine
        } footer: {
            PearlSheetButtons(primary: "Save", busy: busy) { saveHowMuch() }
                .disabled(!(allOfIt || partFits))
        }
    }

    private func choiceLine<Words: View>(on: Bool, @ViewBuilder _ words: () -> Words) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2, content: words)
            Spacer(minLength: 8)
            if on {
                Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    /// All of it with less money than they owe asks first (PB-13b).
    private func saveHowMuch() {
        if allOfIt {
            if cents(room) < cents(total) { letGoAsk = true; return }
            Task { await change(["amount": total]) }
        } else {
            guard partFits else { return }
            Task { await change(["amount": Double(cents(partValue)) / 100]) }
        }
    }

    // MARK: PB-12 Which of their shares (Paid back, 1351:9586)

    private var which: some View {
        APSheet(dismissDisabled: busy) {
            APSheetHeader(overline: "Paid back", title: "What did \(first) pay back?",
                             back: { if start == .options { step = .options } else { onClose() } },
                             close: onClose)
            if let rows = shares {
                if rows.isEmpty {
                    Text("No purchases match.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                } else {
                    APSheetLabel(text: "Likely")
                    APCard {
                        ForEach(Array(rows.enumerated()), id: \.element.id) { i, o in
                            if i > 0 { APSeparator(afterFace: false) }
                            shareRow(o, on: pick == o.id)
                        }
                    }
                }
            } else {
                ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
            }
            errorLine
        } footer: {
            PearlSheetButtons(primary: "Save", busy: busy) {
                if let o = shares?.first(where: { $0.id == pick }) { Task { await change(["to": o.charge]) } }
            }
            .disabled(pick == nil)
        }
    }

    /// "Sam’s share of Pai Northern Thai · owes $60.00" over "Wed, Nov 12 ·
    /// split 2 ways", with a checkmark (one pick).
    private func shareRow(_ o: PartsSheet.Owing, on: Bool) -> some View {
        let sub = [o.pending == true ? "Pending" : Format.weekdayDay(o.date), o.ways.map { "split \($0) ways" }]
            .compactMap { $0 }.joined(separator: " · ")
        return Button { pick = o.id } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(possessive(first)) share of \(o.merchant) · owes \(Format.amount(o.owes))")
                        .font(Nacre.body).foregroundColor(Pearl.ink).fixedSize(horizontal: false, vertical: true)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer(minLength: 8)
                if on {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// Their other shares still owed, from the payment's own list (S-09).
    private func loadShares() async {
        struct Reply: Decodable { let items: [Lenient<PartsSheet.Owing>] }
        let deposit = link.deposit?.id ?? link.inflow ?? link.id
        let r: Reply? = try? await api.get("api/transactions/\(deposit)/owing")
        let me = first.lowercased()
        shares = (r?.items ?? []).compactMap { $0.value }.filter { o in
            o.charge != charge && o.unknown != true && o.owes >= 0.005
                && (o.person?.split(separator: " ").first.map { $0.lowercased() == me } ?? false)
        }
    }

    // MARK: Server

    private struct Reply: Decodable { let title: String?; let undo: JSONValue? }

    private func change(_ body: [String: Any]) async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            let r: Reply = try await api.post("api/transactions/\(charge)/paybacks/\(link.inflow ?? link.id)/change", body)
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            onDone(r.title ?? "Changed", r.undo)
        } catch {
            // A failed save keeps what she said; nothing changed.
            self.error = error.localizedDescription
        }
    }

    /// PP-01's tap: who paid it back now, on the split or not (PB-15).
    private func changePerson(_ name: String) async {
        busy = true
        error = nil
        defer { busy = false }
        do {
            let r: Reply = try await api.post("api/transactions/\(charge)/paybacks/\(link.inflow ?? link.id)/change",
                                              ["kind": "person", "person": name])
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            if let onPerson = onPerson { onPerson(r.title ?? "Changed", r.undo, name) } else { onDone(r.title ?? "Changed", r.undo) }
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func cents(_ x: Double) -> Int { Int((x * 100).rounded()) }
}
