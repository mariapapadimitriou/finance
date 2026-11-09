import SwiftUI

// THL-181 "Every repayment linked to a split is credited to someone on the
// split card. If Pearl can't tell who, it asks." (SPLIT-22b): a payback
// already linked (from search, the web's Paid back or the API) that the ask
// rule credited to no one. S-35c 1033:42573 (dark 1033:42879), its error
// 1033:42728 (dark 1033:43032). Opened from the split card's row (S-05u), the
// "Who sent this?" chip in Needs a look and Quick sort (S-21u), and the
// deposit's own page. The same "Who paid you back?" sheet (S-09, S-35a), with
// no search: it's linked already.

/// GET /api/transactions/<id>/credit.
struct CreditQuestion: Decodable {
    let id: String
    let amount: Double
    /// What it put toward the purchases it pays back, together.
    let linked: Double
    let date: String
    let sender: String?
    let merchant: String
    let purchases: [Purchase]
    let shares: [Share]

    struct Purchase: Decodable, Hashable {
        let id: String
        let merchant: String
        let date: String
        /// What this payback put toward it.
        let here: Double
    }

    /// Someone who still owes on one of those purchases.
    struct Share: Decodable, Hashable, Identifiable {
        let charge: String
        let merchant: String
        let date: String
        let person: String
        let owes: Double
        let here: Double
        /// How many people are on that purchase's split.
        let people: Int
        var id: String { charge + "|" + person }
    }
}

@MainActor
struct WhoSentSheet: View {
    let id: String
    let api: APIClient
    /// Quick sort (S-21u): the tick is held for the card as "Paid back by
    /// Sam?". Yes saves it with one Undo, and Skip drops it, as SPLIT-20.
    var onHeld: ((ReviewAnswer) -> Void)? = nil
    /// Saved: "Sam paid back $30.00 · Undo".
    let onSaved: (MarkReply) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var question: CreditQuestion?
    @State private var picked: Set<String> = []
    @State private var loading = true
    @State private var busy = false
    @State private var error: String?
    /// S-35c error: the save failed; Sam stays ticked and Save stays on.
    @State private var failed = false
    /// Over the share: what's left goes to "What's the other $x?" (S-11 v2).
    @State private var extra: [PartsSheet.Part]?

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Who sent this?") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let q = question {
                        QuestionHeader(name: q.merchant, amount: Format.amount(q.amount), tone: Pearl.ink,
                                       sub: "\(Format.short(q.date)) · paid back \(Format.andList(q.purchases.map(\.merchant)))")
                        content(q)
                    } else if loading {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 16)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            if question != nil {
                // Off until she ticks someone; a spinner while it saves.
                Button("Save") { save() }
                    .buttonStyle(NacreButtonStyle(busy: busy)).disabled(picked.isEmpty || busy)
                    .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await load() }
        .sheet(item: Binding(get: { extra.map { Extra(parts: $0) } }, set: { extra = $0?.parts })) { e in
            // S-11 v2 "What's the other $15.00?": the credit and the rest in one save.
            if let q = question {
                PartsSheet(deposit: PartsDeposit(id: q.id, name: q.merchant, amount: q.amount, date: q.date),
                           api: api, credited: e.parts) { reply in
                    extra = nil
                    onSaved(reply)
                }
            }
        }
    }

    private struct Extra: Identifiable {
        let parts: [PartsSheet.Part]
        var id: Int { parts.count }
    }

    @ViewBuilder private func content(_ q: CreditQuestion) -> some View {
        let shops = merchants(q)
        Text("ON \(Format.andList(shops).uppercased())").font(Nacre.caption2).tracking(0.4)
            .foregroundColor(Pearl.muted).padding(.horizontal, 16)
        GlassCard {
            ForEach(Array(q.shares.enumerated()), id: \.element.id) { i, s in
                if i > 0 { RowSeparator() }
                row(s)
            }
        }
        if failed {
            // S-35c error, as T-08k's.
            Text("Couldn’t save that. Try again.").font(Nacre.footnote).foregroundColor(Pearl.caution)
                .padding(.horizontal, 16)
        } else {
            Text(askText(q)).font(Nacre.footnote).foregroundColor(Pearl.ink)
                .padding(.horizontal, 16).fixedSize(horizontal: false, vertical: true)
        }
        bar(q)
    }

    /// The purchases with someone still owing, in the order they're listed.
    private func merchants(_ q: CreditQuestion) -> [String] {
        var seen = Set<String>()
        return q.shares.map(\.merchant).filter { seen.insert($0).inserted }
    }

    /// What it put toward the purchases she's asked about. S-21xw (THL-301):
    /// on a payback that's also extra on Loblaws, only Pizza Nova's $30.00.
    private func asked(_ q: CreditQuestion) -> Double {
        let on = Set(q.shares.map(\.charge))
        return Double(q.purchases.filter { on.contains($0.id) }.map { cents($0.here) }.reduce(0, +)) / 100
    }

    /// Why Pearl asks (S-35c note 1034:42639).
    func askText(_ q: CreditQuestion) -> String {
        let shops = Format.andList(merchants(q))
        let amount = Format.amount(asked(q))
        let fits = q.shares.filter { cents($0.owes) == cents($0.here) }
        var seen = Set<String>()
        let names = fits.map { firstName($0.person) }.filter { seen.insert($0.lowercased()).inserted }
        if names.count >= 2 {
            // "Sam and Priya each owe $30.00 on Loblaws, so Pearl won't guess. Tick who sent it."
            return "\(Format.andList(names)) each owe \(amount) on \(shops), so Pearl won’t guess. Tick who sent it."
        }
        if q.shares.count == 1, let s = q.shares.first, s.people == 1 {
            // "Sam owes $42.06 on Loblaws and this is $30.00, so Pearl won't guess. Tick Sam if it was them."
            let name = firstName(s.person)
            return "\(name) owes \(Format.amount(s.owes)) on \(s.merchant) and this is \(amount), so Pearl won’t guess. Tick \(name) if it was them."
        }
        // "No one on Loblaws owes $45.00, so Pearl won't guess. Tick who sent it."
        return "No one on \(shops) owes \(amount), so Pearl won’t guess. Tick who sent it."
    }

    /// "Sam" over "Loblaws · Nov 11 · Sam's share". VoiceOver: "Sam, Loblaws,
    /// November 11, $30.00, not selected".
    private func row(_ s: CreditQuestion.Share) -> some View {
        let on = picked.contains(s.id)
        return Button { toggle(s) } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(s.person).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text("\(s.merchant) · \(Format.short(s.date)) · \(firstName(s.person))’s share")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
                }
                Spacer(minLength: 8)
                Text(Format.amount(s.owes)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22)).foregroundColor(on ? Pearl.action : Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 56).padding(.vertical, 2).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(s.person), \(s.merchant), \(Format.monthDay(s.date)), \(Format.amount(s.owes))")
        .accessibilityValue(on ? "selected" : "not selected")
        .accessibilityAddTraits(.isButton)
    }

    /// "● Credited $30.00 to Sam   ● Not credited $0.00".
    private func bar(_ q: CreditQuestion) -> some View {
        let whole = max(asked(q), 0.01)
        let done = min(credited(q), asked(q))
        let who = person.map { " to \(firstName($0))" } ?? ""
        return VStack(alignment: .leading, spacing: 6) {
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(Pearl.ink.opacity(0.1))
                    Capsule().fill(Pearl.action).frame(width: g.size.width * done / whole)
                }
            }
            .frame(height: 6)
            HStack(spacing: 14) {
                legend(Pearl.action, "Credited \(Format.amount(done))\(who)")
                legend(Pearl.ink.opacity(0.2), "Not credited \(Format.amount(asked(q) - done))")
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

    // MARK: Ticking and saving

    /// Who's ticked: one payment has one sender, so ticking someone else
    /// starts again with them.
    private var person: String? {
        question?.shares.first { picked.contains($0.id) }?.person
    }

    private func toggle(_ s: CreditQuestion.Share) {
        failed = false
        if picked.contains(s.id) {
            picked.remove(s.id)
            return
        }
        if let who = person, who != s.person { picked = [] }
        picked.insert(s.id)
    }

    /// What ticking credits: each ticked share, up to what this paid toward it.
    private func credited(_ q: CreditQuestion) -> Double {
        Double(q.shares.filter { picked.contains($0.id) }.map { min(cents($0.owes), cents($0.here)) }.reduce(0, +)) / 100
    }

    /// Paid more than the ticked shares: the rest needs saying (S-11 v2).
    private func over(_ q: CreditQuestion) -> Bool {
        q.shares.contains { picked.contains($0.id) && cents($0.here) > cents($0.owes) }
    }

    private func save() {
        guard let q = question, let who = person else { return }
        // S-21xw (THL-301): when part of it is extra on a purchase nobody owes
        // on, Save credits and closes; the extra is its own question (S-21xm),
        // so the credit and the extra each have their own Undo.
        let allAsked = q.purchases.allSatisfy { p in q.shares.contains { $0.charge == p.id } }
        if over(q) && allAsked {
            // Her share is a payback part; what's left is asked on S-11 v2,
            // and both are saved together there. Close saves nothing.
            extra = q.purchases.map { p in
                let tick = q.shares.first { $0.charge == p.id && $0.person == who && picked.contains($0.id) }
                let on = tick != nil || q.shares.contains { $0.charge == p.id && $0.person == who }
                return PartsSheet.Part(kind: "payback", amount: tick.map { min($0.owes, p.here) } ?? p.here,
                                       charge: p.id, merchant: p.merchant, person: on ? who : nil, date: p.date)
            }
            return
        }
        let answer = ReviewAnswer.credit(q.id, person: who, label: "Paid back by \(firstName(who))")
        if let onHeld = onHeld {
            // Quick sort: held for the card; nothing is saved here.
            onHeld(answer)
            return
        }
        Task {
            busy = true
            defer { busy = false }
            do {
                let reply = try await answer.send(api)
                onSaved(reply)
            } catch {
                failed = true
                UIAccessibility.post(notification: .announcement, argument: "Couldn’t save that. Try again.")
            }
        }
    }

    private func load() async {
        struct Reply: Decodable { let question: CreditQuestion? }
        loading = true
        defer { loading = false }
        do {
            let r: Reply = try await api.get("api/transactions/\(id)/credit")
            guard let q = r.question else {
                // Answered somewhere else meanwhile: nothing left to ask.
                dismiss()
                return
            }
            question = q
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// "Priya" from "Priya S.".
    private func firstName(_ name: String) -> String {
        name.split(separator: " ").first.map(String.init) ?? name
    }

    private func cents(_ x: Double) -> Int { Int((x * 100).rounded()) }
}
