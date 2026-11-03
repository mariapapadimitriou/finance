import SwiftUI

/// One transaction (THL-122, T-03): who and how much, what it counts as,
/// Pearl's guess to confirm (T-38), the payback or refund it's linked to
/// (T-39, T-41), one-off (T-42), a note and tags; a transfer between her
/// accounts shows both ends (T-05).
@MainActor
struct TransactionDetailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let transaction: Transaction
    let categories: [CategoryList.Category]
    var siblings: [Transaction] = []

    /// The full detail once it's come back; the list's row until then.
    @State private var detail: Transaction?
    @State private var picking = false
    @State private var editingNote = false
    @State private var editingTags = false
    /// A money-in question opened from here (THL-198): its kind, how often
    /// it pays, or What was this?.
    @State private var asking: Asking?

    struct BillStart: Identifiable {
        let category: String
        var id: String { category }
    }

    struct Asking: Identifiable {
        let step: AnswerSheet.Step
        var id: AnswerSheet.Step { step }
    }
    @State private var oneOff: Bool?
    /// Splits and parts (THL-291).
    @State private var splitting = false
    @State private var marking: Transaction.Splitting.Person?
    @State private var lettingGo: Transaction.Splitting.Person?
    @State private var seeingOwed = false
    @State private var parting: PartsDeposit?
    @State private var unlinking = false
    @State private var recent: [String] = []
    /// A transaction added by hand can be taken out again.
    @State private var deleting = false
    /// T-04's Regular bill, then Add to your bills? (T-32) with the category chosen.
    @State private var regularBill = false
    @State private var billing: String?
    @State private var busy = false
    @State private var message: String?
    @State private var error: String?

    private var t: Transaction { detail ?? transaction }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                header.padding(.bottom, 16)
                if let transfer = t.transfer {
                    transferLegs(transfer)
                } else {
                    if !t.parts.isEmpty { partsCard } else if jointAsks { jointGuessCard }
                    else if t.asks { askingCard }
                    else if t.suggested { guessCard } else { categoryCard }
                    linked
                    jointRow
                    splitPeople
                    depositParts
                    options
                    details
                }
                if let message = message {
                    Text(message).font(Nacre.footnote).foregroundColor(Pearl.ink)
                        .padding(.horizontal, 16).padding(.top, 8)
                        .fixedSize(horizontal: false, vertical: true)
                }
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                        .padding(.horizontal, 16).padding(.top, 8)
                }
                footerAction
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                // The bar draws the glass circle round it.
                Button { dismiss() } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                }
                .accessibilityLabel("Back")
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationBarHidden(false)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .sheet(isPresented: $picking) {
            // The stored category, not the chip ("Transfer", "Not sorted yet").
            CategorySheet(name: t.merchant, amount: Format.money(t), tone: t.tone, categories: categories,
                          current: t.category ?? t.label, merchant: t.merchant,
                          onRegularBill: t.inflow ? nil : { regularBill = $0 }) { name, remember in
                picking = false
                let bill = regularBill
                regularBill = false
                Task {
                    if name != (t.category ?? t.label) || remember {
                        await change(to: name, remember: remember)
                    } else {
                        // Let Change category close before the next sheet opens.
                        try? await Task.sleep(nanoseconds: 450_000_000)
                    }
                    if bill { billing = name }
                }
            }
        }
        .sheet(item: Binding(get: { billing.map { BillStart(category: $0) } }, set: { billing = $0?.category })) { start in
            AddToBillsSheet(t: t, api: app.api, categories: categories, category: start.category) { said in
                billing = nil
                Task { await run { said } }
            }
        }
        .sheet(item: $asking) { a in
            AnswerSheet(ask: a.step == .joint ? jointAsk : moneyIn, categories: categories, accounts: [],
                        names: [], api: app.api, start: a.step,
                        current: a.step == .joint ? jointChoice
                            : a.step == .kinds ? t.incomeType : t.regularPay?.cadence) { answer in
                asking = nil
                Task { await run { try await answer.send(app.api).title ?? answer.done } }
            }
        }
        .sheet(isPresented: $splitting) {
            SplitSheet(t: t, api: app.api, recent: recent) { done in
                splitting = false
                Task { await run { done } }
            }
        }
        .sheet(item: $marking) { person in
            MarkPaidSheet(t: t, person: person, api: app.api) { done in
                marking = nil
                Task { await run { done } }
            }
        }
        .sheet(item: $lettingGo) { person in
            LetGoSheet(person: person) {
                lettingGo = nil
                Task { await letGo(person) }
            }
        }
        .sheet(item: $parting) { deposit in
            PartsSheet(deposit: deposit, api: app.api) { reply in
                parting = nil
                Task { await run { reply.title ?? "Sorted." } }
            }
        }
        .sheet(isPresented: $unlinking) { unlinkSheet }
        .navigationDestination(isPresented: $seeingOwed) { OwedView() }
        .sheet(isPresented: $editingNote) {
            NoteSheet(note: t.myNote) { note in
                editingNote = false
                Task { await save(note: note) }
            }
            .presentationDetents([.medium])
        }
        .sheet(isPresented: $editingTags) {
            TagsSheet(tags: t.tags, known: knownTags) { tags in
                editingTags = false
                Task { await save(tags: tags) }
            }
            .presentationDetents([.medium, .large])
        }
    }

    // MARK: Header

    private var header: some View {
        VStack(spacing: 8) {
            if t.transfer == nil {
                Initials(name: t.merchant, size: 56)
                    .overlay(Circle().strokeBorder(
                        AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                        lineWidth: 1.2))
                    .padding(.bottom, 6)
            }
            Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            Text(Format.money(t))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(t.tone)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(t.transfer != nil ? "Doesn’t count · Between your accounts" : dateLine)
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            if !t.joint.isEmpty && t.transfer == nil {
                // T-40: "Joint with Sam · 50%".
                HStack(spacing: 6) {
                    Image(systemName: "person.2").font(.system(size: 12, weight: .medium))
                    Text(jointLine)
                }
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .padding(.horizontal, 12).frame(height: 28)
                .background(Capsule().fill(Nacre.glass))
                .padding(.top, 4)
                .accessibilityElement(children: .combine)
            }
            if t.pending {
                HStack(spacing: 6) {
                    Circle().fill(Pearl.moneyOut).frame(width: 8, height: 8)
                    Text("Pending · amount may change")
                }
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .padding(.horizontal, 12).frame(height: 28)
                .background(Capsule().fill(Nacre.glass))
                .padding(.top, 4)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
    }

    /// "Wed, Nov 11 · TD Chequing ••4417".
    private var dateLine: String {
        let when = Format.relativeDay(t.date) == "Today" ? "Today" : Format.weekdayDay(t.date)
        return [when, t.account].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    // MARK: What it counts as

    private var categoryCard: some View {
        Button {
            if t.leftToSort { parting = deposit(rest: true) }
            else if isIncome { asking = Asking(step: .kinds) } else { picking = true }
        } label: {
            GlassCard {
                // Income says what kind (T-37): "Salary · Counts as income".
                row(title: isIncome ? Self.kindName(t.incomeType) : t.label, sub: countsLine, chevron: true)
            }
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityHint(isIncome ? "Changes what kind of income" : "Changes the category")
    }

    private var isIncome: Bool { t.inflow && t.counts == "income" && t.transfer == nil }

    /// Money in that could be her pay: not a refund, a payback or a transfer.
    private var couldBePay: Bool {
        t.inflow && t.transfer == nil && t.refundOf == nil && t.repays == nil && t.excluded.isEmpty
            && t.jointFrom != "them"
    }

    /// The app's income kinds, as Income and bills names them.
    nonisolated static func kindName(_ kind: String?) -> String {
        switch kind {
        case "salary": return "Salary"
        case "bonus": return "Bonus"
        case "interest": return "Interest"
        case "gifts": return "Gifts"
        case "government": return "Government credits"
        case "tax_refund": return "Tax refund"
        case "other": return "Other income"
        default: return "Income"
        }
    }

    /// "Counts as spending · Essential", "Your share counts · $46 of $86",
    /// "Refund · lowers Shopping by $68".
    private var countsLine: String {
        if !t.excluded.isEmpty { return "Left out · \(t.excluded)" }
        if t.refundOf != nil {
            return "Refund · lowers \(t.label) by \(Format.compact(t.amount))"
        }
        if t.split, let full = t.fullAmount {
            return "Your share counts · \(Format.compact(t.amount)) of \(Format.compact(full))"
        }
        switch t.counts {
        case "income" where t.jointFrom == "both":
            // T-33's Both of us: only her share is her income.
            let mine = (t.amount * (t.jointShare ?? 50) / 100 * 100).rounded() / 100
            return "Your share counts · \(Format.compact(mine)) of \(Format.compact(t.amount))"
        case "income": return "Counts as income"
        case "spending":
            if t.inflow { return t.note.flatMap { $0.isEmpty ? nil : $0 } ?? "Comes off your spending" }
            let rest = (oneOff ?? t.oneOff) ? "One-off" : groupName
            return ["Counts as spending", rest].compactMap { $0 }.joined(separator: " · ")
        default:
            return t.note.flatMap { $0.isEmpty ? nil : $0 } ?? "Doesn’t count"
        }
    }

    private var groupName: String? {
        switch t.group {
        case "essentials": return "Essential"
        case "lifestyle": return "Lifestyle"
        case "savings": return "Savings"
        default: return nil
        }
    }

    /// "Not sorted yet · Paid back or income? Tell us": Needs a look is
    /// asking, so answering it happens there.
    private var askingCard: some View {
        NavigationLink { ReviewView() } label: {
            GlassCard {
                row(title: t.label, sub: t.note.flatMap { $0.isEmpty ? nil : $0 } ?? "Needs a look", chevron: true)
            }
        }
        .buttonStyle(.plain)
        .accessibilityHint("Opens Needs a look")
    }

    /// T-38: "Was this dining out?" Yes, or something else.
    private var guessCard: some View {
        VStack(spacing: 14) {
            Text("PEARL’S GUESS").font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Text("Was this \(t.label.lowercased())?")
                .font(Nacre.title2).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
            HStack(spacing: 10) {
                Button("Yes") { Task { await confirm() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                Button("Something else") { picking = true }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Color.white.opacity(0.8)))
                    .buttonStyle(.plain)
            }
            .disabled(busy)
        }
        .padding(20)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 26, style: .continuous).fill(.ultraThinMaterial))
        .background(RoundedRectangle(cornerRadius: 26, style: .continuous)
            .fill(LinearGradient(colors: [Nacre.rose.opacity(0.35), Nacre.lilac.opacity(0.25), Nacre.seaglass.opacity(0.35)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
        .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous).strokeBorder(Nacre.edge, lineWidth: 1.2))
    }

    // MARK: Linked transactions

    /// PAID BACK (T-39), REFUND FOR (T-41), REFUNDED BY, or the charge a
    /// payback is for.
    @ViewBuilder private var linked: some View {
        if !t.repaidBy.isEmpty {
            // A split shows who paid back below; this is the money that did.
            section(t.splitting == nil ? "Paid back" : "Paid back with")
            SolidCard {
                ForEach(Array(t.repaidBy.enumerated()), id: \.element.id) { index, b in
                    if index > 0 { RowSeparator(inset: 72) }
                    let part = b.paid.flatMap { abs($0 - abs(b.amount)) >= 0.005 ? $0 : nil }
                    linkedRow(name: b.merchant ?? b.name,
                              sub: [Format.short(b.date), part.map { _ in "part of \(Format.whole(abs(b.amount)))" }]
                                .compactMap { $0 }.joined(separator: " · "),
                              amount: part ?? abs(b.amount), inflow: true)
                }
            }
        }
        if let charge = t.refundOf {
            section("Refund for")
            SolidCard {
                let category = siblings.first { $0.id == charge.id }?.label
                linkedRow(name: charge.merchant,
                          sub: [category, Format.short(charge.date)].compactMap { $0 }.joined(separator: " · "),
                          amount: charge.amount, inflow: false)
            }
        }
        if !t.refundedBy.isEmpty {
            section("Refunded by")
            SolidCard {
                ForEach(Array(t.refundedBy.enumerated()), id: \.element.id) { index, r in
                    if index > 0 { RowSeparator(inset: 72) }
                    linkedRow(name: r.merchant, sub: Format.short(r.date), amount: r.amount, inflow: true)
                }
            }
        }
        if let charge = t.repaysCharge {
            section("Pays back")
            SolidCard {
                linkedRow(name: charge.merchant ?? charge.name, sub: Format.short(charge.date),
                          amount: abs(charge.amount), inflow: false)
            }
        }
    }

    private func linkedRow(name: String, sub: String, amount: Double, inflow: Bool) -> some View {
        HStack(spacing: 14) {
            Initials(name: name)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text((inflow ? "+" : "\u{2212}") + Format.amount(amount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(inflow ? Pearl.ink : Pearl.moneyOut)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }

    // MARK: Joint accounts (T-33, T-40)

    /// "Joint with Sam · 50%", or the account's name when it has no people.
    private var jointLine: String {
        let who = t.jointPeople.isEmpty ? t.joint : "Joint with " + t.jointPeople.joined(separator: " and ")
        return who + (t.jointShare.map { " · \(Int($0.rounded()))%" } ?? "")
    }

    /// Money into a joint account nobody has said whose it is.
    private var jointAsks: Bool {
        t.inflow && !t.joint.isEmpty && t.jointFrom.isEmpty && t.transfer == nil && t.repays == nil
    }

    /// T-40: "Is this Sam's pay?" — Yes, or the whole question.
    private var jointGuessCard: some View {
        let person = t.jointPeople.count == 1 ? t.jointPeople[0] : nil
        return VStack(spacing: 14) {
            Text("PEARL’S GUESS").font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Text(person.map { "Is this \($0)’s pay?" } ?? "Is this your pay?")
                .font(Nacre.title2).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
            HStack(spacing: 10) {
                Button("Yes") {
                    let answer = ReviewAnswer.joint(t.id, who: person == nil ? "me" : "them", person: person)
                    Task { await run { try await answer.send(app.api).title } }
                }
                .buttonStyle(NacreButtonStyle(busy: busy))
                Button("Something else") { asking = Asking(step: .joint) }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Color.white.opacity(0.8)))
                    .buttonStyle(.plain)
            }
            .disabled(busy)
        }
        .padding(20)
        .frame(maxWidth: .infinity)
        .background(RoundedRectangle(cornerRadius: 26, style: .continuous).fill(.ultraThinMaterial))
        .background(RoundedRectangle(cornerRadius: 26, style: .continuous)
            .fill(LinearGradient(colors: [Nacre.rose.opacity(0.35), Nacre.lilac.opacity(0.25), Nacre.seaglass.opacity(0.35)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
        .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous).strokeBorder(Nacre.edge, lineWidth: 1.2))
    }

    /// Whose an answered joint deposit is, to change it.
    @ViewBuilder private var jointRow: some View {
        if t.inflow && !t.joint.isEmpty && !t.jointFrom.isEmpty && t.transfer == nil {
            section("Joint account")
            GlassCard {
                Button { asking = Asking(step: .joint) } label: {
                    row(title: "Whose pay", sub: jointWhose, chevron: true)
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
    }

    private var jointWhose: String {
        switch t.jointFrom {
        case "me": return "Yours"
        case "both": return "Both of yours · your share \(Int((t.jointShare ?? 50).rounded()))% counts"
        default: return t.jointPerson.map { "\($0)’s · not counted as yours" } ?? "Theirs · not counted as yours"
        }
    }

    /// The answer so far, as the joint question's choices name it.
    private var jointChoice: String? {
        switch t.jointFrom {
        case "me", "both": return t.jointFrom
        case "them": return t.jointPerson.map { "them:" + $0 } ?? "them"
        default: return nil
        }
    }

    /// This deposit as the joint question, for AnswerSheet (T-33).
    private var jointAsk: Ask {
        let brief = BriefTransaction(id: t.id, date: t.date, merchant: t.merchant, description: t.description,
                                     amount: -t.amount, accountName: t.account, accountId: t.accountId,
                                     category: t.category, skipped: nil, likely: nil)
        return Ask(kind: .joint, item: Review.Item(key: "joint:" + t.id, txn: brief, skipped: nil,
                                                    label: t.joint, people: t.jointPeople, share: t.jointShare))
    }

    // MARK: Splits and parts (THL-291)

    /// A purchase she can split: hers, counted, not a refund or split yet.
    private var canSplit: Bool {
        !t.inflow && t.transfer == nil && t.refundOf == nil && t.splitting == nil && t.excluded.isEmpty
    }

    /// Money in she can split into parts: not already sorted into some.
    private var canPart: Bool {
        t.inflow && t.transfer == nil && t.parts.isEmpty && t.partOf == nil && t.refundOf == nil
            && t.repays == nil && t.excluded.isEmpty && t.jointFrom != "them"
    }

    private func deposit(rest: Bool) -> PartsDeposit {
        PartsDeposit(id: t.id, name: t.merchant, amount: t.amount, date: t.date, rest: rest)
    }

    /// OWED TO YOU or SPLIT 3 WAYS (S-04, S-05, S-19, S-20).
    @ViewBuilder private var splitPeople: some View {
        if let split = t.splitting, !split.people.isEmpty, !t.inflow {
            SplitPeople(t: t, split: split,
                        onMarkPaid: { marking = $0 },
                        onRemind: remind,
                        onLetGo: { lettingGo = $0 },
                        onUndoLetGo: { p in Task { await undoLetGo(p) } },
                        onEdit: { splitting = true },
                        onOwed: { seeingOwed = true })
        }
    }

    /// "Payback + gift": what a deposit in parts was (S-33).
    private var partsCard: some View {
        GlassCard {
            row(title: partsTitle, sub: "In \(t.parts.count) parts", chevron: false)
        }
    }

    private var partsTitle: String {
        var kinds: [String] = []
        for p in t.parts {
            let k = p.kind == "payback" ? "Payback" : p.kind == "refund" ? "Refund" : p.label
            if !kinds.contains(k) { kinds.append(k) }
        }
        return kinds.joined(separator: " + ")
    }

    /// Its parts and what each pays back; or, for a part, the deposit it's
    /// from (S-33, S-34).
    @ViewBuilder private var depositParts: some View {
        let parts = !t.parts.isEmpty ? t.parts : (t.partOf?.parts ?? [])
        if !parts.isEmpty {
            section(t.partOf.map { "Part of a \(Format.amount($0.amount)) deposit" } ?? "Parts")
            SolidCard {
                ForEach(Array(parts.enumerated()), id: \.element.id) { index, p in
                    if index > 0 { RowSeparator(inset: 72) }
                    partRow(p)
                }
            }
            section("Options")
            GlassCard {
                Button { unlinking = true } label: {
                    row(title: "Unlink", sub: "Make it one deposit again", chevron: true)
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
    }

    /// "Flight to Athens  Travel · Dad's share  $428.00"; new money in green.
    private func partRow(_ p: DepositPart) -> some View {
        let income = ["gift", "income"].contains(p.kind)
        return HStack(spacing: 14) {
            Initials(name: p.charge?.merchant ?? p.label)
            VStack(alignment: .leading, spacing: 2) {
                Text(p.charge?.merchant ?? p.label).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(partLine(p)).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text((income ? "+" : "") + Format.amount(p.amount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(income ? Pearl.moneyIn : Pearl.ink)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }

    /// "Travel · Dad's share", "Counts as income", "Left to sort".
    private func partLine(_ p: DepositPart) -> String {
        switch p.kind {
        case "payback":
            return [p.charge?.category, p.person.map { "\($0)’s share" }].compactMap { $0 }.joined(separator: " · ")
        case "refund": return [p.charge?.category, "Refund"].compactMap { $0 }.joined(separator: " · ")
        case "gift": return "Counts as income"
        case "income": return "\(Self.kindName(p.incomeKind)) · counts as income"
        case "moved": return "Not new money"
        case "savings": return "Out of savings"
        case "cash": return "Cash you were paid"
        case "overpaid": return "You owe \(p.person ?? "them") this"
        case "rest": return p.sorted == true ? "Sorted" : "Left to sort"
        default: return p.category ?? p.label
        }
    }

    /// S-34 Unlink?: "Dad will owe you $492 again."
    private var unlinkSheet: some View {
        let parts = !t.parts.isEmpty ? t.parts : (t.partOf?.parts ?? [])
        let paybacks = parts.filter { $0.kind == "payback" }
        let back = paybacks.map(\.amount).reduce(0, +)
        let person = paybacks.compactMap(\.person).first
        return VStack(spacing: 16) {
            SheetTitle(title: "Unlink?") { unlinking = false }
            QuestionHeader(name: t.partOf == nil ? t.merchant : t.merchant,
                           amount: Format.amount(t.partOf?.amount ?? t.amount), tone: Pearl.ink,
                           sub: Format.short(t.partOf?.date ?? t.date))
                .padding(.horizontal, 16)
            Text(back > 0 ? "\(person ?? "They") will owe you \(Format.amount(back)) again."
                 : "It goes back to one deposit, not sorted yet.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
            HStack(spacing: 10) {
                Button("Unlink") {
                    unlinking = false
                    Task { await unlinkParts() }
                }
                .buttonStyle(NacreButtonStyle())
                Button("Keep linked") { unlinking = false }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Color.white.opacity(0.85)))
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        .presentationDetents([.height(320)])
    }

    // MARK: Options

    @ViewBuilder private var options: some View {
        let unlink = t.refundOf != nil
        let canOneOff = t.canOneOff && !t.inflow
        if canSplit || canPart {
            section("Options")
            GlassCard {
                Button { if canSplit { splitting = true } else { parting = deposit(rest: false) } } label: {
                    if canSplit {
                        row(title: "Split with others", sub: "Count only your share", chevron: true)
                    } else {
                        row(title: "Split into parts", sub: "Like a payback and a gift in one", chevron: true)
                    }
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
        if couldBePay {
            // T-37: her regular pay, and how often; or making it so (T-31).
            if !(canSplit || canPart) { section("Options") }
            GlassCard {
                Button { asking = Asking(step: .cadence) } label: {
                    if let pay = t.regularPay {
                        row(title: "Regular pay",
                            sub: [Format.cadence(pay.cadence ?? ""),
                                  pay.next.map { "next on \(Format.weekdayDay($0))" }]
                                .compactMap { $0 }.joined(separator: " · "),
                            chevron: true)
                    } else {
                        row(title: "This is my regular pay",
                            sub: "Pearl plans with it from now on", chevron: true)
                    }
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
        if unlink || canOneOff {
            if !(canSplit || canPart || couldBePay) { section("Options") }
            GlassCard {
                if unlink {
                    Button { Task { await unlinkRefund() } } label: {
                        row(title: "Unlink refund", sub: "Count it as money in instead", chevron: true)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if canOneOff {
                    if unlink { RowSeparator() }
                    Toggle(isOn: Binding(get: { oneOff ?? t.oneOff },
                                         set: { on in Task { await setOneOff(on) } })) {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("One-off purchase").font(Nacre.body).foregroundColor(Pearl.ink)
                            Text((oneOff ?? t.oneOff) ? "Left out of your usual month" : "Leave out of your usual month")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    if let line = t.oneOffLine?.line, oneOff ?? t.oneOff {
                        Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16).padding(.bottom, 12)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
    }

    // MARK: Details

    @ViewBuilder private var details: some View {
        section("Details")
        GlassCard {
            Button { editingNote = true } label: {
                if t.myNote.isEmpty {
                    row(title: "Add a note", placeholder: true, chevron: true)
                } else {
                    row(title: t.myNote, sub: "Note", chevron: true)
                }
            }
            .buttonStyle(.plain)
            // A refund's tags are its purchase's (T-41), and income has none (T-37).
            if t.refundOf == nil && !isIncome {
                RowSeparator()
                Button { editingTags = true } label: {
                    if t.tags.isEmpty {
                        row(title: "Add tags", placeholder: true, chevron: true)
                    } else {
                        row(title: t.tags.map { "#" + $0 }.joined(separator: "  "), sub: "Tags", chevron: true)
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// "Not income?" (T-37) under income; Delete under one added by hand.
    @ViewBuilder private var footerAction: some View {
        if isIncome {
            Button("Not income?") { asking = Asking(step: .into) }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .padding(.top, 12)
        }
        if t.manual {
            Button("Delete transaction") { deleting = true }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.moneyOut))
                .padding(.top, isIncome ? 0 : 12)
                .disabled(busy)
                .confirmationDialog("Delete \(t.merchant)?", isPresented: $deleting, titleVisibility: .visible) {
                    Button("Delete", role: .destructive) { Task { await delete() } }
                } message: {
                    Text("You added it by hand. It comes out of your numbers.")
                }
        }
    }

    // MARK: A transfer (T-05)

    @ViewBuilder private func transferLegs(_ transfer: Transaction.Transfer) -> some View {
        let outDate = transfer.from == t.account ? t.date : (transfer.otherDate ?? t.date)
        let inDate = transfer.to == t.account ? t.date : (transfer.otherDate ?? t.date)
        SolidCard {
            leg(account: transfer.from, sub: "Out · \(Format.weekdayDay(outDate))", sign: "\u{2212}")
            RowSeparator(inset: 72)
            leg(account: transfer.to, sub: "In · \(Format.weekdayDay(inDate))", sign: "+")
        }
        Spacer(minLength: 120)
        Button("This isn’t a transfer") { picking = true }
            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            .padding(.top, 24)
    }

    private func leg(account: String, sub: String, sign: String) -> some View {
        HStack(spacing: 14) {
            Initials(name: account)
            VStack(alignment: .leading, spacing: 2) {
                Text(account).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text(sign + Format.amount(t.amount)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }

    // MARK: Parts

    private func section(_ text: String) -> some View {
        Text(text.uppercased())
            .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 12)
            .accessibilityAddTraits(.isHeader)
    }

    private func row(title: String, sub: String? = nil, placeholder: Bool = false, chevron: Bool) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(placeholder ? Nacre.body : (sub == nil ? Nacre.body : Nacre.headline))
                    .foregroundColor(placeholder ? Pearl.muted : Pearl.ink)
                    .lineLimit(2)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            Spacer(minLength: 8)
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
        .contentShape(Rectangle())
    }

    /// This deposit as a money-in question, for AnswerSheet.
    private var moneyIn: Ask {
        let brief = BriefTransaction(id: t.id, date: t.date, merchant: t.merchant, description: t.description,
                                     amount: -t.amount, accountName: t.account, accountId: t.accountId,
                                     category: t.category, skipped: nil, likely: nil)
        return Ask(kind: .incomeType, item: Review.Item(key: "in:" + t.id, txn: brief, skipped: nil))
    }

    private var knownTags: [String] {
        var out: [String] = []
        for tag in siblings.flatMap(\.tags) where !out.contains(tag) { out.append(tag) }
        return out
    }

    // MARK: Changes

    private func load() async {
        if let full: Transaction = try? await app.api.get("api/transactions/\(detail?.id ?? transaction.id)") {
            detail = full
            oneOff = nil
        }
        // People she's split with before, for Who was it with? (S-02).
        if recent.isEmpty, !t.inflow, let owed: OwedOverview = try? await app.api.get("api/owed") {
            var names: [String] = []
            for n in owed.owesYou.map(\.name) + owed.paidBack.compactMap(\.name) where !names.contains(n) {
                names.append(n)
            }
            recent = names
        }
    }

    private func run(_ work: () async throws -> String?) async {
        busy = true
        defer { busy = false }
        do {
            message = try await work()
            error = nil
            await load()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Yes: Pearl's guess was right.
    private func confirm() async {
        await run {
            let _: CategoryChange = try await app.api.put("api/transactions/\(t.id)/confirm")
            return nil
        }
    }

    private func change(to name: String, remember: Bool) async {
        await run {
            let _: CategoryChange = try await app.api.patch("api/transactions/\(t.id)",
                                                            ["category": name, "apply_to_merchant": remember])
            return remember ? "\(name), and every \(t.merchant) from now on." : "Moved to \(name)."
        }
    }

    private func setOneOff(_ on: Bool) async {
        oneOff = on
        await run {
            let reply: OneOffReply = try await app.api.put("api/transactions/\(t.id)/one-off", ["on": on])
            return [reply.title, reply.detail].compactMap { $0 }.joined(separator: " ")
        }
    }

    private func unlinkRefund() async {
        await run {
            let _: OK = try await app.api.delete("api/transactions/\(t.id)/refund")
            return "Unlinked. It counts as money in now."
        }
    }

    /// A split change's reply: what to say. (Its `detail` is the whole
    /// transaction, which load() fetches anyway.)
    private struct Titled: Decodable { let title: String? }

    /// S-07: a reminder she can paste into a message.
    private func remind(_ p: Transaction.Splitting.Person) {
        UIPasteboard.general.string = "Hey \(p.name)! Your share of \(t.merchant) on \(Format.short(t.date)) "
            + "is \(Format.amount(p.owes)). Thanks!"
        message = "Reminder for \(p.name) copied. Paste it in a message."
    }

    private func letGo(_ p: Transaction.Splitting.Person) async {
        await run {
            let reply: Titled = try await app.api.post("api/transactions/\(t.id)/split/let-go", ["name": p.name])
            return reply.title
        }
    }

    private func undoLetGo(_ p: Transaction.Splitting.Person) async {
        await run {
            let reply: Titled = try await app.api.delete("api/transactions/\(t.id)/split/let-go",
                                                            query: ["name": p.name])
            return reply.title
        }
    }

    /// A part is gone once unlinked, so the page shows the deposit it was.
    private func unlinkParts() async {
        struct Reply: Decodable { let id: String; let title: String? }
        await run {
            let reply: Reply = try await app.api.delete("api/transactions/\(t.id)/parts")
            detail = try await app.api.get("api/transactions/\(reply.id)")
            return reply.title
        }
    }

    private func delete() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.delete("api/transactions/\(t.id)")
            app.changed()
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func save(note: String) async {
        await run {
            let _: OK = try await app.api.put("api/transactions/\(t.id)/note", ["note": note])
            return nil
        }
    }

    private func save(tags: [String]) async {
        await run {
            let _: OK = try await app.api.put("api/transactions/\(t.id)/tags", ["tags": tags])
            return nil
        }
    }
}

/// The white card a linked transaction sits on (T-39, T-41, T-05).
struct SolidCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(RoundedRectangle(cornerRadius: 26, style: .continuous).fill(Pearl.card))
            .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous).strokeBorder(Nacre.edge, lineWidth: 1.2))
            .shadow(color: Color(red: 0.4, green: 0.3, blue: 0.6).opacity(0.1), radius: 10, y: 6)
    }
}

/// Her own words about it, up to 200 characters.
struct NoteSheet: View {
    @State var note: String
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SheetTitle(title: "Note") { dismiss() }
            TextField("", text: $note, prompt: Text("What was it for?").foregroundColor(Pearl.muted), axis: .vertical)
                .font(Nacre.body).lineLimit(3...6)
                .focused($focused)
                .padding(16)
                .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Nacre.glass))
                .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Nacre.edge, lineWidth: 1))
                .padding(.horizontal, 16)
                .onChange(of: note) { value in if value.count > 200 { note = String(value.prefix(200)) } }
            Spacer()
            Button("Save") { onSave(note.trimmingCharacters(in: .whitespacesAndNewlines)) }
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .onAppear { focused = true }
    }
}

/// Tags: hers to name ("Cottage weekend"), any number of them.
struct TagsSheet: View {
    @State var tags: [String]
    let known: [String]
    let onSave: ([String]) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var typed = ""

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            SheetTitle(title: "Tags") { dismiss() }
            HStack(spacing: 8) {
                TextField("", text: $typed, prompt: Text("Add a tag").foregroundColor(Pearl.muted))
                    .font(Nacre.body).autocorrectionDisabled()
                    .submitLabel(.done)
                    .onSubmit(add)
                Button("Add", action: add).font(Nacre.textButton).foregroundColor(Pearl.action)
                    .disabled(typed.trimmingCharacters(in: .whitespaces).isEmpty)
            }
            .padding(.horizontal, 16).frame(height: 48)
            .background(Capsule().fill(Nacre.glass))
            .overlay(Capsule().strokeBorder(Nacre.edge, lineWidth: 1))
            .padding(.horizontal, 16)
            ScrollView {
                Chips {
                    ForEach(Array(Set(tags + known)).sorted(), id: \.self) { tag in
                        FilterChip(label: tag, on: tags.contains(tag)) {
                            if let i = tags.firstIndex(of: tag) { tags.remove(at: i) } else { tags.append(tag) }
                        }
                    }
                }
                .padding(.horizontal, 16)
            }
            Button("Save") { onSave(tags) }
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
    }

    private func add() {
        let tag = typed.trimmingCharacters(in: .whitespaces)
        guard !tag.isEmpty else { return }
        if !tags.contains(tag) { tags.append(tag) }
        typed = ""
    }
}
