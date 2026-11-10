import SwiftUI

/// One Needs a look question as the iOS sheets ask it (THL-231, THL-232):
/// Pearl's guess first when there is one (T-06a), then four or five answers
/// (T-06, T-08, T-12), and only the follow-up an answer needs: which account
/// (T-07), which purchase (T-09), what kind of income (T-71), how often it
/// pays (T-31), whose it is (T-13, T-60), who sent it (T-14), whether a
/// transfer repeats (T-69) or someone is paying her back (T-70).
///
/// The one page sorting happens on: Needs a look, Quick sort and a transaction
/// all open it, so every answer in Figma's Outcome table and every option
/// (a rule, Regular bill, Split with others, One-off) is reachable from each.
@MainActor
struct AnswerSheet: View {
    @Environment(\.colorScheme) private var scheme
    let ask: Ask
    let categories: [CategoryList.Category]
    let accounts: [AccountsOverview.Account]
    let names: [String]
    let api: APIClient
    let onAnswer: (ReviewAnswer) -> Void
    /// Quick sort's guesses: a category from What was this? is theirs to save,
    /// so the others from the merchant can go with it. Save on the guess
    /// unchanged confirms it.
    var onCategory: ((String, Bool) -> Void)? = nil
    /// Save on the unchanged category confirms it; not on a settled one.
    var confirmsGuess = true
    /// Opened from the transaction's page (T-03, T-96), which has the options
    /// already: the tiles alone, as CR-04 has them.
    var fromPage = false
    /// The page's Always switch, when it has one: this sheet doesn't ask again.
    var pageAlways: Bool? = nil
    /// The amount the page behind this sheet shows: her share, on a shared row.
    var pageAmount: String? = nil
    /// A category already picked on the page behind, shown as the current one.
    var pageCategory: String? = nil
    /// The opener holds an answer for a Quick sort card's Yes (SPLIT-06,
    /// SPLIT-20): an answer with a card label isn't saved here, and Split with
    /// others is held too, not saved, so there's nothing here to fail. A tile
    /// that only goes on to another step still saves nothing until its answer.
    var holds = false
    /// T-98s from Quick sort's sheet (SPLIT-20): a held split and the category
    /// it counts toward, for the card's "Groceries, split with Sam?".
    var onHeldSplit: ((CardSplit, String) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var step: Step
    @State private var choice: String?
    @State private var text = ""
    /// T-13: remember the joint answer for every deposit from them.
    @State private var rememberAll = true
    @State private var charges: [BriefTransaction] = []
    /// For a category picked as part of another answer (a purchase, a
    /// recurring payment): what to do with it.
    @State private var then: Then = .category
    /// "A refund or payback": the deposit's parts (THL-291, S-09 to S-12).
    @State private var parting = false
    /// T-08 / T-12: which side of money in is showing.
    @State private var incomeSide = true
    @State private var intoChoice: String?
    /// Her confirmed pay, for T-31's hint.
    @State private var pays: [IncomeBills.Pay] = []
    /// The transaction in full, for the options.
    @State private var full: Transaction?
    /// Whether a rule for this name could match the right rows (not "Interac e-Transfer").
    @State private var learnable = true
    /// Accounts for "Where did it go?", when the caller has none to hand.
    @State private var fetchedAccounts: [AccountsOverview.Account] = []
    /// The rule for an answer with a follow-up, and for money in.
    @State private var rememberAnswer = true
    @State private var rememberInto = true
    /// What "What did this pay back?" is answering: nil works it out.
    @State private var chargeCase: String?
    @State private var splitting = false
    /// T-06jr (JOINT-B): Whose was it? on a joint purchase, beside Split my part.
    @State private var whosing = false
    @State private var whoseSaid: String?
    @State private var splitSaid: String?
    /// SPLIT-20: the split made here, held for the Quick sort card's Yes.
    @State private var heldSplit: CardSplit?
    @State private var oneOff: Bool?
    /// T-04's Regular bill, then Add to your bills? (T-32), then the answer.
    @State private var regularBill = false
    @State private var billing: BillStart?
    @State private var pending: (() -> Void)?
    /// T-08k (SPLIT-18): the kind being saved from this page, and what went wrong.
    @State private var savingKind: String?
    @State private var kindError: String?

    struct BillStart: Identifiable {
        let t: Transaction
        let category: String
        var id: String { t.id }
    }

    enum Step: Hashable {
        case guess, out, into, accounts, charges, kinds, otherKinds, cadence, joint, sender, recurring, payback, category
    }

    enum Then { case category, spending, recurring }

    /// `start` opens on one step, for the transaction page (THL-198):
    /// the kind of income, how often it pays, or What was this?.
    init(ask: Ask, categories: [CategoryList.Category], accounts: [AccountsOverview.Account], names: [String],
         api: APIClient, start: Step? = nil, pageAlways: Bool? = nil, pageAmount: String? = nil, pageCategory: String? = nil, current: String? = nil, onCategory: ((String, Bool) -> Void)? = nil,
         confirmsGuess: Bool = true, fromPage: Bool = false, holds: Bool = false,
         onHeldSplit: ((CardSplit, String) -> Void)? = nil,
         onAnswer: @escaping (ReviewAnswer) -> Void) {
        self.fromPage = fromPage
        self.holds = holds
        self.onHeldSplit = onHeldSplit
        self.pageAlways = pageAlways
        self.pageAmount = pageAmount
        self.pageCategory = pageCategory
        _rememberInto = State(initialValue: pageAlways ?? true)
        self.ask = ask
        self.categories = categories
        self.accounts = accounts
        self.names = names
        self.api = api
        self.onAnswer = onAnswer
        self.onCategory = onCategory
        self.confirmsGuess = confirmsGuess
        let first: Step
        switch ask.kind {
        // T-52: straight to the categories, on the page with every other answer.
        case .category: first = ask.t.inflow ? .into : .out
        case .duplicate, .check: first = .guess
        case .transfer: first = ask.savedTo(accounts) != nil ? .guess : .out
        case .moneyIn:
            switch ask.item.guess?.action {
            // A nameless e-Transfer isn't "Interac" paying her back, and a guess
            // with nothing behind it isn't worth asking: the answers instead.
            case "payback" where ask.item.guess?.charge != nil && ask.t.learnable != false: first = .payback
            case "own": first = .guess
            default: first = .into
            }
        case .incomeType: first = .kinds
        case .joint: first = .joint
        case .whoSent: first = .sender
        case .recurring: first = .recurring
        }
        _step = State(initialValue: start ?? first)
        _choice = State(initialValue: current)
        // "Not income?" on a transaction opens on the Not income side.
        _incomeSide = State(initialValue: start != .into && ask.kind != .category)
    }

    private var t: BriefTransaction { ask.t }
    private var who: String { t.name }

    var body: some View {
        Group {
            if step == .out {
                // T-06: Spending is the categories; Not spending, the answers.
                CategorySheet(name: who, amount: amountText, tone: tone, categories: categories,
                              current: pageCategory ?? t.category ?? ask.item.guess?.text ?? "Other",
                              merchant: learnable ? who : nil,
                              onRegularBill: fromPage ? nil : { regularBill = $0 },
                              title: fromPage && ask.kind == .category ? "Category" : "What was this?",
                              preview: learnable ? CategorySheet.preview(api: api, id: t.id, merchant: who) : nil,
                              notSpending: CaseTile.notSpending, startNotSpending: ask.kind != .category,
                              onCase: { outCase($0, remember: $1) },
                              confirmsCurrent: (ask.kind == .category && confirmsGuess) || splitSaid != nil,
                              caseRule: { outRule($0) },
                              extras: fromPage ? nil : AnyView(outOptions),
                              answersAtOnce: true,
                              // Off where other rows are open or it varies: her answer here is for this row.
                              newOnesOn: pageAlways ?? (learnable && t.mixed != true && ask.item.siblings.isEmpty),
                              showsAlways: pageAlways == nil) { name, remember in
                    saveSpending(name, remember)
                }
            } else if step == .into {
                intoSheet
            } else if step == .category {
                CategorySheet(name: who, amount: amountText, tone: tone, categories: categories,
                              current: t.category ?? ask.item.guess?.text ?? "Other",
                              merchant: then == .recurring ? nil : who,
                              preview: then == .recurring ? nil : CategorySheet.preview(api: api, id: t.id, merchant: who),
                              confirmsCurrent: ask.kind == .category && then == .category) { name, remember in
                    switch then {
                    case .category where ask.kind == .category && name == (t.category ?? ask.item.guess?.text) && !remember:
                        onAnswer(.confirm(t.id))
                    case .category: onAnswer(.category(t.id, name: name, remember: remember))
                    case .spending: onAnswer(.mark(t.id, ["case": "spending", "category": name, "remember": remember]))
                    case .recurring: onAnswer(.recurring(key: ask.item.key, kind: nil, category: name))
                    }
                }
            } else if step == .guess {
                guessSheet
            } else {
                choiceSheet
            }
        }
        .presentationDragIndicator(.visible)
        .task(id: step) { await loadOptions() }
        .sheet(isPresented: $whosing) {
            if let f = full {
                WhoseSheet(t: f, api: api) { said in
                    whosing = false
                    whoseSaid = said
                    // Her part may have changed, so Split my part says so.
                    Task { full = try? await api.get("api/transactions/\(f.id)") }
                }
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
            }
        }
        .sheet(isPresented: $splitting) {
            if let f = full {
                // T-98s (SPLIT-20): from Quick sort's sheet the split is held,
                // as on the card's page; the category she picks next goes with it.
                SplitSheet(t: f, api: api, recent: names,
                           onHold: holds && onHeldSplit != nil ? { body, _, mine in
                               splitting = false
                               heldSplit = CardSplit.held(body, mine: mine, total: f.splitBase)
                               splitSaid = heldSplit?.note
                           } : nil) { said in
                    splitting = false
                    splitSaid = said
                }
            }
        }
        .sheet(item: $billing, onDismiss: {
            let finish = pending
            pending = nil
            finish?()
        }) { start in
            AddToBillsSheet(t: start.t, api: api, categories: categories, category: start.category) { _ in
                billing = nil
            }
        }
        .sheet(isPresented: $parting) {
            PartsSheet(deposit: PartsDeposit(id: t.id, name: who, amount: t.amount, date: t.date), api: api) { reply in
                parting = false
                onAnswer(.done(reply))
            }
        }
    }

    // MARK: Options

    private func loadOptions() async {
        guard step == .out || step == .into, full == nil else { return }
        struct Cases: Decodable { let learnable: Bool? }
        if let c: Cases = try? await api.get("api/transactions/\(t.id)/cases") { learnable = c.learnable ?? true }
        if let f: Transaction = try? await api.get("api/transactions/\(t.id)") { full = f }
    }

    /// What Spending saves: the caller's way, or the answer for this question.
    private func saveSpending(_ name: String, _ remember: Bool) {
        let finish: () -> Void = {
            if let split = heldSplit, let onHeldSplit = onHeldSplit {
                // SPLIT-20: held for the card, "for this one" (no rule), as T-98s says.
                onHeldSplit(split, name)
            } else if let onCategory = onCategory {
                onCategory(name, remember)
            } else if ask.kind == .category {
                if name == (t.category ?? ask.item.guess?.text) && !remember {
                    onAnswer(.confirm(t.id))
                } else {
                    onAnswer(.category(t.id, name: name, remember: remember))
                }
            } else {
                onAnswer(.mark(t.id, ["case": "spending", "category": name, "remember": remember]))
            }
        }
        guard regularBill, let f = full else { finish(); return }
        regularBill = false
        pending = finish
        billing = BillStart(t: f, category: name)
    }

    /// The Outcome table's rule for T-06's answers: work never makes one.
    private func outRule(_ key: String) -> String? {
        guard learnable else { return nil }
        switch key {
        case "work": return nil
        case "not_mine": return "Leave out every \(who) from now on"
        default: return "Do this for every \(who) from now on"
        }
    }

    /// Split with others (THL-289) and One-off (T-42), for a purchase.
    @ViewBuilder private var outOptions: some View {
        if let f = full {
            // T-06jr (JOINT-B, supersedes S-01j): on a joint purchase, Whose was
            // it? and Split my part; "Split with others" on "All mine unless I
            // mark it" (S-01jr2); dimmed with why when none of it is hers (T-06jr1).
            let joint = !f.joint.isEmpty && f.transfer == nil
            let canSplit = f.transfer == nil && f.refundOf == nil && f.splitting == nil && f.excluded.isEmpty
            if canSplit || f.canOneOff || joint {
                Text("OPTIONS").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 16).padding(.top, 4)
                    .accessibilityAddTraits(.isHeader)
                GlassCard {
                    if joint {
                        Button { whosing = true } label: {
                            optionLabel("Whose was it?", done: whoseSaid != nil, icon: "person.2")
                        }
                        .buttonStyle(.plain)
                        if canSplit || f.canOneOff { RowSeparator() }
                    }
                    if canSplit {
                        let none = joint && f.splitBase < 0.005
                        Button { splitting = true } label: {
                            VStack(alignment: .leading, spacing: 2) {
                                optionLabel(joint && f.splitsMyPart ? "Split my part" : "Split with others",
                                            done: splitSaid != nil, icon: "person.2")
                                // T-06jr / T-06jr1 (REFRESH-03): Split my part has no
                                // subtitle; none of it hers says so in five words.
                                if joint && (none || !f.splitsMyPart) {
                                    Text(none ? "None of it is yours to split." : "Split it with friends")
                                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                                        .padding(.leading, 64).padding(.bottom, 8)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                            .opacity(none ? 0.45 : 1)
                        }
                        .buttonStyle(.plain)
                        .disabled(none)
                        .accessibilityElement(children: .combine)
                    }
                    if canSplit && f.canOneOff { RowSeparator() }
                    if f.canOneOff {
                        Toggle(isOn: Binding(get: { oneOff ?? f.oneOff }, set: { on in Task { await setOneOff(on) } })) {
                            HStack(spacing: 12) {
                                IconBubble(symbol: "1.circle")
                                Text("Exclude from usual month").font(Nacre.body).foregroundColor(Pearl.ink)
                            }
                        }
                        .tint(Pearl.action)
                        .padding(.horizontal, 16).frame(minHeight: 52)
                        .accessibilityHint("Leaves it out of your usual month")
                    }
                }
            }
        }
    }

    private func optionLabel(_ title: String, done: Bool, icon: String? = nil) -> some View {
        HStack(spacing: 12) {
            if let icon = icon { IconBubble(symbol: icon) }
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer(minLength: 4)
            if done {
                Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
            }
            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
        }
        .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
    }

    private func setOneOff(_ on: Bool) async {
        oneOff = on
        do {
            let _: OneOffReply = try await api.put("api/transactions/\(t.id)/one-off", ["on": on])
        } catch {
            oneOff = !on
        }
    }

    // MARK: Pearl's guess (T-06a)

    private var guessSheet: some View {
        VStack(spacing: 16) {
            SheetTitle(title: guessTitle) { dismiss() }
            if ask.kind == .duplicate {
                // T-15: both charges, one above the other.
                VStack(alignment: .leading, spacing: 10) {
                    Text("Looks like the same charge twice.").font(Nacre.body).foregroundColor(Pearl.ink)
                    GlassCard {
                        dupRow(t)
                        if let twin = ask.item.twin {
                            RowSeparator(inset: 62)
                            dupRow(twin)
                        }
                    }
                }
                .padding(.horizontal, 16)
            } else {
                QuestionHeader(name: who, amount: amountText, tone: tone,
                               sub: ask.kind == .check ? ask.evidence : nil).padding(.horizontal, 16)
            }
            HStack(spacing: 10) {
                Button(yesLabel) { yes() }.buttonStyle(NacreButtonStyle())
                Button(noLabel) { no() }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    // Dark: the control fill, so the ink word reads (TEST-01).
                    .background(Capsule().fill(scheme == .dark ? Pearl.control : Color.white.opacity(0.85)))
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            if ask.kind != .duplicate && ask.kind != .check && t.learnable != false {
                Button("Just this one") { yes(remember: false) }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        .presentationDetents(ask.kind == .duplicate ? [.large] : [.height(320)])
    }

    /// "CO  Costco · Groceries · Nov 9 · TD Visa ••9021   −$142.60".
    private func dupRow(_ b: BriefTransaction) -> some View {
        HStack(spacing: 12) {
            Initials(name: b.name, size: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(b.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text([b.category, Format.short(b.date), b.accountName].compactMap { $0 }.joined(separator: " · "))
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text((b.inflow ? "+" : "\u{2212}") + Format.amount(abs(b.amount))).font(Nacre.headline).monospacedDigit()
                .foregroundColor(b.inflow ? Pearl.ink : Pearl.moneyOut)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private var guessTitle: String {
        switch ask.kind {
        case .duplicate: return "Same purchase?"
        case .check: return ask.item.pair?.question ?? "Is this right?"
        case .moneyIn: return "From your own account?"
        case .transfer: return "Saved to \(ask.savedTo(accounts) ?? "savings")?"
        default: return "\(ask.item.guess?.text ?? t.category ?? "Other")?"
        }
    }

    private var yesLabel: String { ask.kind == .duplicate ? "Yes, count it once" : "Yes" }
    private var noLabel: String {
        ask.kind == .duplicate ? "No, both are real" : ask.kind == .check ? "No" : "Something else"
    }

    /// Yes saves the rule where one can match; Just this one doesn't.
    private func yes(remember: Bool? = nil) {
        let rule = remember ?? (t.learnable != false)
        switch ask.kind {
        case .duplicate: onAnswer(.duplicate(t.id, same: true))
        case .check: onAnswer(.check(ask.item.key, yes: true))
        case .moneyIn: onAnswer(.mark(t.id, ["case": "own", "remember": rule]))
        case .transfer: onAnswer(.mark(t.id, ["case": "saved", "remember": rule]))
        default: onAnswer(.confirm(t.id))
        }
    }

    private func no() {
        switch ask.kind {
        case .duplicate: onAnswer(.duplicate(t.id, same: false))
        case .check: onAnswer(.check(ask.item.key, yes: false))
        case .moneyIn: go(.into)
        case .transfer: go(.out)
        default:
            then = .category
            go(.category)
        }
    }

    // MARK: T-08 / T-12 Money in: Income or Not income, as tiles

    private var intoSheet: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "What was this?") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: who, amount: amountText, tone: tone, sub: ask.evidence)
                    if learnable && pageAlways == nil {
                        Toggle(isOn: $rememberInto) {
                            Text("Always for \(who)").font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                        .tint(Pearl.action).padding(.horizontal, 4)
                    }
                    Text("INCOME").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).accessibilityAddTraits(.isHeader)
                    CaseGrid(cases: CaseTile.income, chosen: answer(income: true))
                    Text("NOT INCOME").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).padding(.top, 4).accessibilityAddTraits(.isHeader)
                    CaseGrid(cases: CaseTile.notIncome, chosen: answer(income: false))
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    /// A tile answers at once.
    private func answer(income: Bool) -> Binding<String?> {
        Binding(get: { nil }, set: { key in
            guard let key = key else { return }
            incomeSide = income
            intoChoice = key
            // Leaving every one out is a bigger step: never by a switch left on.
            if key == "not_mine" { rememberInto = false }
            intoCase()
        })
    }

    /// The rule money in can make: its own account, or leaving it out.
    private var intoRule: String? {
        switch intoChoice {
        case "own": return "Do this for every \(who) from now on"
        case "not_mine": return "Leave out every \(who) from now on"
        default: return nil
        }
    }

    /// T-06's answers, for money out that isn't spending.
    private func outCase(_ key: String, remember: Bool) {
        switch key {
        case "own":
            rememberAnswer = remember
            go(.accounts)
        case "card": onAnswer(.mark(t.id, ["case": "moved", "remember": remember]))
        case "saved": onAnswer(.mark(t.id, ["case": "saved", "remember": remember]))
        case "lent": onAnswer(.mark(t.id, ["case": "lent", "remember": remember]))
        case "paying_back": onAnswer(.mark(t.id, ["case": "paying_back", "remember": remember]))
        case "work": onAnswer(.mark(t.id, ["case": "work"]))
        default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Not mine", "remember": remember]))
        }
    }

    /// T-08's income kinds and T-12's answers.
    private func intoCase() {
        guard let key = intoChoice else { return }
        if incomeSide {
            if key == "regular" { go(.cadence); return }
            // T-08k (SPLIT-18): Other income asks which kind, not saves "other".
            if key == "other" { go(.otherKinds); return }
            if ask.kind == .incomeType {
                onAnswer(.incomeType(t.id, kind: key))
            } else {
                onAnswer(.mark(t.id, ["case": "pay", "income_kind": key]))
            }
            return
        }
        switch key {
        case "paid_back":
            // Who paid you back? (2026-11-09): every share she split with
            // someone, tick as many as it paid back, not one purchase searched for.
            parting = true
        case "refund":                                 // T-09: what it paid back
            chargeCase = nil
            go(.charges)
        case "reimbursement":
            chargeCase = key
            go(.charges)
        case "own": onAnswer(.mark(t.id, ["case": "own", "remember": learnable && rememberInto]))
        case "loan": onAnswer(.mark(t.id, ["case": "borrowed"]))
        case "out_of_savings": onAnswer(.mark(t.id, ["case": "out_of_savings"]))
        case "lent_back": onAnswer(.mark(t.id, ["case": "lent_back"]))
        default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Not mine",
                                       "remember": learnable && rememberInto]))
        }
    }

    // MARK: A list of answers

    private struct Option: Identifiable {
        let id: String
        let label: String
        var detail: String? = nil
    }

    private var choiceSheet: some View {
        VStack(spacing: 0) {
            SheetTitle(title: title) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: who, amount: amountText, tone: tone, sub: sub)
                    if step == .sender || step == .charges {
                        searchField
                    }
                    if step == .kinds {
                        kindTiles
                    } else if step == .otherKinds {
                        otherKindTiles
                    } else {
                        if step == .charges && !options.isEmpty {
                            Text("LIKELY").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                        if step == .sender && !options.isEmpty {
                            Text("RECENT").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                        if !options.isEmpty {
                            GlassCard {
                                ForEach(Array(options.enumerated()), id: \.element.id) { index, o in
                                    if index > 0 { RowSeparator() }
                                    optionRow(o)
                                }
                            }
                        } else if step == .charges {
                            Text("No purchases match.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                    }
                    if step == .joint {
                        // T-13 (THL-232, R-08): this deposit, or every one from them.
                        Toggle("Every deposit from \(who)", isOn: $rememberAll)
                            .font(Nacre.body).tint(Pearl.action)
                            .padding(.horizontal, 16).frame(minHeight: 52)
                            .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Pearl.card))
                        Text(rememberAll ? "Pearl will remember this for \(who)." : "Off answers just this one.")
                            .font(Nacre.footnote).foregroundColor(Pearl.ink)
                            .frame(maxWidth: .infinity).multilineTextAlignment(.center)
                    } else if let footer = footer {
                        Text(footer).font(Nacre.footnote).foregroundColor(Pearl.ink)
                            .frame(maxWidth: .infinity).multilineTextAlignment(.center)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            if step == .sender {
                // T-14 (THL-232, R-09): keep what the bank called it.
                Button("Use your bank’s name instead") { onAnswer(.party(t.id, name: "")) }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                Button("Skip") { onAnswer(.skip(ask.item.key, true)) }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
            if step != .kinds && step != .otherKinds && step != .payback {
                Button(primaryLabel) { primary() }
                    .buttonStyle(NacreButtonStyle())
                    .disabled(!ready)
                    .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .task(id: step) {
            if step == .charges { await searchCharges() }
            if step == .accounts, accounts.isEmpty, fetchedAccounts.isEmpty,
               let o: AccountsOverview = try? await api.get("api/accounts/overview") {
                fetchedAccounts = o.linked
            }
            if step == .cadence, pays.isEmpty, let d: IncomeBills = try? await api.get("api/income-bills") { pays = d.pays }
        }
        .task(id: text) {
            guard step == .charges else { return }
            try? await Task.sleep(nanoseconds: 250_000_000)
            if !Task.isCancelled { await searchCharges() }
        }
    }

    private func optionRow(_ o: Option) -> some View {
        Button {
            choice = o.id
            // "Is Ben Tran paying you back?" answers at once: no Save, then Continue.
            if step == .payback { primary() }
        } label: {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(o.label).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let detail = o.detail {
                        Text(detail).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                Spacer(minLength: 8)
                if choice == o.id {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(choice == o.id ? .isSelected : [])
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
            TextField("", text: $text, prompt: Text(step == .sender ? "Name" : "Search purchases")
                .foregroundColor(Pearl.muted))
                .font(Nacre.body).autocorrectionDisabled()
                .textInputAutocapitalization(step == .sender ? .words : .never)
                .onChange(of: text) { value in
                    if step == .sender, !value.isEmpty { choice = nil }
                }
        }
        .padding(.horizontal, 14).frame(height: 44)
        .background(Capsule().fill(Pearl.ink.opacity(0.08)))
    }

    /// T-71: what kind of income, as tiles.
    private var kindTiles: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 3), spacing: 8) {
            ForEach(Self.kinds, id: \.key) { k in
                let on = choice == k.key
                // A tile answers at once.
                Button { choice = k.key; primary() } label: {
                    VStack(spacing: 6) {
                        Image(systemName: k.symbol).font(.system(size: 16)).foregroundColor(Pearl.action)
                            .frame(width: 36, height: 36).background(Circle().fill(Pearl.blush.opacity(0.7)))
                        Text(k.name)
                            .font(.custom(on ? "Figtree-SemiBold" : "Figtree-Regular", size: 13, relativeTo: .footnote))
                            .foregroundColor(on ? Pearl.action : Pearl.ink)
                            .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.85)
                            .padding(.horizontal, 4)
                    }
                    .frame(maxWidth: .infinity, minHeight: 76).padding(.vertical, 6)
                    .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .fill(on ? Pearl.blush.opacity(0.75) : Nacre.glass))
                    .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
                        .strokeBorder(on ? Pearl.action : Nacre.separator, lineWidth: on ? 1.5 : 1))
                }
                .buttonStyle(.plain)
                .accessibilityLabel(k.name)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
    }

    /// T-08k (SPLIT-18): "What kind of income?" after Other income: the
    /// other four of finance/income.py's kinds. A tile saves at once, with
    /// the page's Always as it was (not asked again). If the save fails, the
    /// tile un-highlights and "Couldn’t save that. Try again." shows under
    /// the grid, here and not on the screen behind.
    private var otherKindTiles: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("WHICH KIND?").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                .padding(.horizontal, 16).accessibilityAddTraits(.isHeader)
            CaseGrid(cases: CaseTile.otherIncome, chosen: Binding(get: { savingKind }, set: { key in
                guard let key = key else { return }
                choice = key
                saveOtherKind(key)
            }), role: "income kind")
            .disabled(savingKind != nil)
            if let kindError = kindError {
                Text(kindError).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    .padding(.horizontal, 16).fixedSize(horizontal: false, vertical: true)
            }
        }
    }

    /// An income kind, saved as T-08 saves it.
    private func saveIncome(_ kind: String) {
        onAnswer(incomeAnswer(kind))
    }

    private func incomeAnswer(_ kind: String) -> ReviewAnswer {
        ask.kind == .incomeType ? .incomeType(t.id, kind: kind) : .mark(t.id, ["case": "pay", "income_kind": kind])
    }

    /// T-08k: the page saves the kind itself, so a failure is said under its
    /// grid; the opener gets the reply (`.done`) for its toast and Undo, and
    /// shows no error of its own. Held for a Quick sort card: nothing to save.
    private func saveOtherKind(_ kind: String) {
        guard savingKind == nil else { return }
        let answer = incomeAnswer(kind)
        if holds && answer.heldLabel != nil { onAnswer(answer); return }
        savingKind = kind
        kindError = nil
        Task {
            do {
                let reply = try await answer.send(api)
                onAnswer(.done(reply))
            } catch {
                savingKind = nil
                choice = nil
                kindError = "Couldn’t save that. Try again."
                UIAccessibility.post(notification: .announcement, argument: "Couldn’t save that. Try again.")
            }
        }
    }

    /// The app's income kinds (Income and bills), plus "My regular pay".
    private static let kinds: [(key: String, name: String, symbol: String)] = [
        ("regular", "My pay", "briefcase"), ("bonus", "Bonus", "sparkle"),
        ("gifts", "A gift", "gift"), ("other", "Other income", "ellipsis"),
    ]

    /// T-31: "Like Northwind Ltd" under the schedule her pay already has.
    private func like(_ cadence: String) -> String? {
        pays.first { $0.cadence == cadence && $0.name.lowercased() != who.lowercased() }.map { "Like \($0.name)" }
    }

    // MARK: What each step asks

    private var title: String {
        switch step {
        case .out, .into: return "What was this?"
        case .accounts: return "Where did it go?"
        case .charges: return "What did this pay back?"
        case .kinds, .otherKinds: return "What kind of income?"
        case .cadence: return "How often is this pay?"
        case .joint: return "Whose pay is this?"
        case .sender: return "Who sent this?"
        case .recurring: return "Is this a recurring transfer?"
        case .payback: return "Is \(payer) paying you back?"
        case .guess, .category: return ""
        }
    }

    /// "$1,980.00 · Joint", "−$500.00 · every month, around the 10th · 3 so far".
    private var sub: String? {
        switch step {
        case .joint: return "Joint"
        case .recurring:
            let s = ask.item.series
            return [s?.when, s?.count.map { "\($0) so far" }].compactMap { $0 }.joined(separator: " · ")
        default: return nil
        }
    }

    private var payer: String { ask.item.from ?? who }

    private var options: [Option] {
        switch step {
        case .out:
            return [Option(id: "paid", label: "Something I paid for", detail: "A purchase or a bill"),
                    Option(id: "moved", label: "Moved to my own account"),
                    Option(id: "lent", label: "Lent to someone", detail: "I’ll get it back"),
                    Option(id: "work", label: "Work expense", detail: "Work will pay me back")]
        case .into:
            return [Option(id: "earned", label: "Money I earned", detail: "Pay, a side gig or a bonus"),
                    Option(id: "back", label: "A refund or payback",
                           detail: "A refund, a friend paying me back, or work"),
                    Option(id: "own", label: "From my own accounts"),
                    Option(id: "loan", label: "A loan", detail: "Money I’ll have to pay back"),
                    // T-12 (THL-232, R-07): the rest of "Or it isn't income".
                    Option(id: "out_of_savings", label: "Taken out of my savings"),
                    Option(id: "lent_back", label: "Money I lent, coming back"),
                    Option(id: "holding", label: "Holding it for someone", detail: "Like collecting for a group gift"),
                    Option(id: "else", label: "Something else", detail: "Pick a category")]
        case .accounts:
            let mine = (accounts.isEmpty ? fetchedAccounts : accounts).filter { $0.id != t.accountId }
            return mine.map { a in
                Option(id: "acct:" + a.id, label: a.label,
                       detail: a.joint == true ? "Joint\(a.jointShare.map { " · \(Int($0))%" } ?? "")" : nil)
            } + [Option(id: "elsewhere", label: "Another account", detail: "Not linked")]
        case .charges:
            return charges.map { c in
                Option(id: c.id, label: "\(c.name) · \(Format.amount(c.amount))",
                       detail: [Format.weekdayDay(c.date), c.accountName].compactMap { $0 }.joined(separator: " · "))
            }
        case .cadence:
            return [Option(id: "weekly", label: "Every week", detail: like("weekly")),
                    Option(id: "biweekly", label: "Every 2 weeks", detail: like("biweekly")),
                    Option(id: "semimonthly", label: "Twice a month", detail: "Like the 1st and the 15th"),
                    Option(id: "monthly", label: "Monthly"), Option(id: "changes", label: "It changes"),
                    Option(id: "once", label: "Just this once")]
        case .joint:
            // T-33: hers, theirs, or both of theirs (her share counts).
            let people = ask.item.people ?? []
            let share = Int((ask.item.share ?? 50).rounded())
            return [Option(id: "me", label: "Me")]
                + (people.isEmpty ? [Option(id: "them", label: ask.item.label ?? "Someone else")]
                   : people.map { Option(id: "them:" + $0, label: $0) })
                + [Option(id: "both", label: "Both of us", detail: "Your share · \(share)%")]
        case .sender:
            let typed = text.trimmingCharacters(in: .whitespaces)
            return names.filter { typed.isEmpty || $0.localizedCaseInsensitiveContains(typed) }
                .map { Option(id: "name:" + $0, label: $0) }
        case .recurring:
            return [Option(id: "rent", label: "Yes, rent"), Option(id: "saved", label: "Yes, into savings"),
                    Option(id: "moved", label: "Yes, to another of my accounts"),
                    Option(id: "pay", label: "Yes, something I pay for"), Option(id: "no", label: "No")]
        case .payback:
            let c = ask.item.guess?.charge
            return [Option(id: "this", label: "Yes, for \(c?.name ?? "that purchase") · \(c.map { Format.short($0.date) } ?? "")",
                           detail: c.map { "\(Format.amount($0.amount)) on \($0.accountName ?? "your card")" }),
                    Option(id: "other", label: "Yes, for something else", detail: "Pick the purchase"),
                    Option(id: "no", label: "No, it isn’t a payback", detail: "Then we’ll ask if it’s income")]
        case .kinds, .otherKinds, .guess, .category:
            return []
        }
    }

    /// "Pearl will remember this for M. Papas."
    private var footer: String? {
        switch step {
        case .accounts where !rememberAnswer: return nil
        case .accounts, .joint, .charges: return "Pearl will remember this for \(who)."
        case .cadence where choice != nil && choice != "once": return "Pearl will count every deposit from \(who) as pay."
        default: return nil
        }
    }

    /// Continue when another question follows, Save when this is the last.
    private var primaryLabel: String {
        switch (step, choice) {
        case (.out, "paid"), (.out, "moved"), (.into, "earned"), (.into, "back"), (.into, "else"), (.kinds, "regular"),
             (.recurring, "pay"), (.payback, "other"), (.payback, "no"), (.sender, _):
            return "Continue"
        default: return "Save"
        }
    }

    private var ready: Bool {
        if step == .sender { return choice != nil || !text.trimmingCharacters(in: .whitespaces).isEmpty }
        return choice != nil
    }

    private func go(_ next: Step) {
        choice = nil
        text = ""
        step = next
    }

    private func primary() {
        guard let choice = choice ?? (step == .sender ? "typed" : nil) else { return }
        switch step {
        case .out:
            switch choice {
            case "paid": then = .spending; go(.category)
            case "moved": go(.accounts)
            case "lent": onAnswer(.mark(t.id, ["case": "lent", "remember": true]))
            default: onAnswer(.mark(t.id, ["case": "work"]))
            }
        case .accounts:
            // A savings account, or one Pearl can't see, is money put away;
            // anything else is her money moving.
            let account = (accounts.isEmpty ? fetchedAccounts : accounts).first { "acct:" + $0.id == choice }
            let saved = choice == "elsewhere" || ["savings", "investment"].contains(account?.kind ?? "")
            onAnswer(.mark(t.id, ["case": saved ? "saved" : "moved", "remember": rememberAnswer]))
        case .into:
            switch choice {
            case "earned": go(.kinds)
            case "back": parting = true
            case "own": onAnswer(.mark(t.id, ["case": "own", "remember": true]))
            case "loan": onAnswer(.mark(t.id, ["case": "borrowed"]))
            case "out_of_savings": onAnswer(.mark(t.id, ["case": "out_of_savings"]))
            case "lent_back": onAnswer(.mark(t.id, ["case": "lent_back"]))
            case "else": then = .category; go(.category)
            default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Holding it for someone"]))
            }
        case .kinds:
            if choice == "regular" { go(.cadence); return }
            // T-08k (SPLIT-18): Other income asks which kind.
            if choice == "other" { go(.otherKinds); return }
            saveIncome(choice)
        case .otherKinds:
            saveIncome(choice)
        case .cadence:
            // Her answer is the schedule in Income and bills, not Pearl's guess.
            if choice == "once" {
                // Pay that won't repeat isn't a salary.
                onAnswer(.mark(t.id, ["case": "pay", "income_kind": "other"]))
            } else {
                onAnswer(.regularPay(t, cadence: choice == "changes" ? "irregular" : choice))
            }
        case .charges:
            guard let charge = charges.first(where: { $0.id == choice }) else { return }
            // The same shop sending money back is a refund; anyone else, a payback.
            let refund = charge.name.lowercased() == who.lowercased()
            onAnswer(.mark(t.id, ["case": chargeCase ?? (refund ? "refund" : "payback"), "charge": charge.id]))
        case .payback:
            switch choice {
            case "this":
                if let charge = ask.item.guess?.charge {
                    onAnswer(.mark(t.id, ["case": "payback", "charge": charge.id]))
                }
            case "other": parting = true
            default: go(.into)
            }
        case .joint:
            if choice == "me" || choice == "both" {
                onAnswer(.joint(t.id, who: choice, person: nil, remember: rememberAll))
            } else {
                let person = choice.hasPrefix("them:") ? String(choice.dropFirst(5)) : nil
                onAnswer(.joint(t.id, who: "them", person: person, remember: rememberAll))
            }
        case .sender:
            let name = choice.hasPrefix("name:") ? String(choice.dropFirst(5))
                : text.trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return }
            onAnswer(.party(t.id, name: name))
        case .recurring:
            switch choice {
            case "pay": then = .recurring; go(.category)
            case "no": onAnswer(.dismiss(ask.item.key))
            default: onAnswer(.recurring(key: ask.item.key, kind: choice, category: nil))
            }
        case .guess, .category:
            break
        }
    }

    private func searchCharges() async {
        struct Reply: Decodable { let charges: [Lenient<BriefTransaction>] }
        let q = text.trimmingCharacters(in: .whitespaces)
        if q.isEmpty, let candidates = ask.item.candidates, !candidates.isEmpty {
            charges = candidates.sorted { ($0.likely == true ? 0 : 1) < ($1.likely == true ? 0 : 1) }
            return
        }
        if let reply: Reply = try? await api.get("api/transactions/\(t.id)/charges", query: ["q": q]) {
            charges = reply.charges.compactMap { $0.value }
        }
    }

    // MARK: Money

    private var amountText: String { pageAmount ?? ((t.inflow ? "+" : "\u{2212}") + Format.amount(t.shownAmount)) }
    private var tone: Color { t.inflow ? Pearl.moneyIn : Pearl.moneyOut }
}

/// "MP  e-Transfer to M. Papas  −$200.00": the transaction a question is about.
struct QuestionHeader: View {
    let name: String
    let amount: String
    let tone: Color
    let sub: String?

    var body: some View {
        HStack(spacing: 12) {
            Initials(name: name, size: 48)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(1)
                (Text(amount).foregroundColor(tone)
                 + Text(sub.map { $0.isEmpty ? "" : " · " + $0 } ?? "").foregroundColor(Pearl.ink))
                    .font(Nacre.subheadline).lineLimit(1)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}
