import SwiftUI

/// One Needs a look question as the iOS sheets ask it (THL-231, THL-232):
/// Pearl's guess first when there is one (T-06a), then four or five answers
/// (T-06, T-08, T-12), and only the follow-up an answer needs: which account
/// (T-07), which purchase (T-09), what kind of income (T-71), how often it
/// pays (T-31), whose it is (T-13, T-60), who sent it (T-14), whether a
/// transfer repeats (T-69) or someone is paying her back (T-70).
@MainActor
struct AnswerSheet: View {
    let ask: Ask
    let categories: [CategoryList.Category]
    let accounts: [AccountsOverview.Account]
    let names: [String]
    let api: APIClient
    let onAnswer: (ReviewAnswer) -> Void

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

    enum Step: Hashable {
        case guess, out, into, accounts, charges, kinds, cadence, joint, sender, recurring, payback, category
    }

    enum Then { case category, spending, recurring }

    /// `start` opens on one step, for the transaction page (THL-198):
    /// the kind of income, how often it pays, or What was this?.
    init(ask: Ask, categories: [CategoryList.Category], accounts: [AccountsOverview.Account], names: [String],
         api: APIClient, start: Step? = nil, current: String? = nil, onAnswer: @escaping (ReviewAnswer) -> Void) {
        self.ask = ask
        self.categories = categories
        self.accounts = accounts
        self.names = names
        self.api = api
        self.onAnswer = onAnswer
        let first: Step
        switch ask.kind {
        case .category, .duplicate: first = .guess
        case .transfer: first = ask.savedTo(accounts) != nil ? .guess : .out
        case .moneyIn:
            switch ask.item.guess?.action {
            case "payback" where ask.item.guess?.charge != nil: first = .payback
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
        _incomeSide = State(initialValue: start != .into)
    }

    private var t: BriefTransaction { ask.t }
    private var who: String { t.name }

    var body: some View {
        Group {
            if step == .out {
                // T-06: Spending is the categories; Not spending, the answers.
                CategorySheet(name: who, amount: amountText, tone: tone, categories: categories,
                              current: t.category ?? "Other", merchant: who, title: "What was this?",
                              notSpending: CaseTile.notSpending, startNotSpending: true,
                              onCase: { outCase($0) }) { name, remember in
                    onAnswer(.mark(t.id, ["case": "spending", "category": name, "remember": remember]))
                }
            } else if step == .into {
                intoSheet
            } else if step == .category {
                CategorySheet(name: who, amount: amountText, tone: tone, categories: categories,
                              current: t.category ?? ask.item.guess?.text ?? "Other",
                              merchant: then == .recurring ? nil : who) { name, remember in
                    switch then {
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
        .sheet(isPresented: $parting) {
            PartsSheet(deposit: PartsDeposit(id: t.id, name: who, amount: t.amount, date: t.date), api: api) { reply in
                parting = false
                onAnswer(.done(reply))
            }
        }
    }

    // MARK: Pearl's guess (T-06a)

    private var guessSheet: some View {
        VStack(spacing: 16) {
            SheetTitle(title: guessTitle) { dismiss() }
            QuestionHeader(name: who, amount: amountText, tone: tone, sub: nil).padding(.horizontal, 16)
            HStack(spacing: 10) {
                Button(yesLabel) { yes() }.buttonStyle(NacreButtonStyle())
                Button(noLabel) { no() }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Color.white.opacity(0.85)))
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16).padding(.bottom, 8)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        .presentationDetents([.height(280)])
    }

    private var guessTitle: String {
        switch ask.kind {
        case .duplicate: return "Same purchase?"
        case .moneyIn: return "From your own account?"
        case .transfer: return "Saved to \(ask.savedTo(accounts) ?? "savings")?"
        default: return "\(ask.item.guess?.text ?? t.category ?? "Other")?"
        }
    }

    private var yesLabel: String { ask.kind == .duplicate ? "Yes, count it once" : "Yes" }
    private var noLabel: String { ask.kind == .duplicate ? "No, both are real" : "Something else" }

    private func yes() {
        switch ask.kind {
        case .duplicate: onAnswer(.duplicate(t.id, same: true))
        case .moneyIn: onAnswer(.mark(t.id, ["case": "own", "remember": true]))
        case .transfer: onAnswer(.mark(t.id, ["case": "saved", "remember": true]))
        default: onAnswer(.confirm(t.id))
        }
    }

    private func no() {
        switch ask.kind {
        case .duplicate: onAnswer(.duplicate(t.id, same: false))
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
                    QuestionHeader(name: who, amount: amountText, tone: tone, sub: nil)
                    Picker("", selection: $incomeSide) {
                        Text("Income").tag(true)
                        Text("Not income").tag(false)
                    }
                    .pickerStyle(.segmented)
                    .accessibilityLabel("Income or not income")
                    .onChange(of: incomeSide) { _ in intoChoice = nil }
                    CaseGrid(cases: incomeSide ? CaseTile.income : CaseTile.notIncome, chosen: $intoChoice)
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button("Continue") { intoCase() }
                .buttonStyle(NacreButtonStyle())
                .disabled(intoChoice == nil)
                .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    /// T-06's answers, for money out that isn't spending.
    private func outCase(_ key: String) {
        switch key {
        case "own": go(.accounts)
        case "card": onAnswer(.mark(t.id, ["case": "moved", "remember": true]))
        case "saved": onAnswer(.mark(t.id, ["case": "saved", "remember": true]))
        case "lent": onAnswer(.mark(t.id, ["case": "lent", "remember": true]))
        case "work": onAnswer(.mark(t.id, ["case": "work"]))
        default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Not mine"]))
        }
    }

    /// T-08's income kinds and T-12's answers.
    private func intoCase() {
        guard let key = intoChoice else { return }
        if incomeSide {
            if key == "regular" { go(.cadence); return }
            if ask.kind == .incomeType {
                onAnswer(.incomeType(t.id, kind: key))
            } else {
                onAnswer(.mark(t.id, ["case": "pay", "income_kind": key]))
            }
            return
        }
        switch key {
        case "paid_back", "refund": go(.charges)       // T-09: what it paid back
        case "own": onAnswer(.mark(t.id, ["case": "own", "remember": true]))
        case "loan": onAnswer(.mark(t.id, ["case": "borrowed"]))
        case "out_of_savings": onAnswer(.mark(t.id, ["case": "out_of_savings"]))
        case "lent_back": onAnswer(.mark(t.id, ["case": "lent_back"]))
        case "else": then = .category; go(.category)
        default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Not mine"]))
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
            Button(primaryLabel) { primary() }
                .buttonStyle(NacreButtonStyle())
                .disabled(!ready)
                .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .task(id: step) { if step == .charges { await searchCharges() } }
        .task(id: text) {
            guard step == .charges else { return }
            try? await Task.sleep(nanoseconds: 250_000_000)
            if !Task.isCancelled { await searchCharges() }
        }
    }

    private func optionRow(_ o: Option) -> some View {
        Button { choice = o.id } label: {
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
                Button { choice = k.key } label: {
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

    /// The app's income kinds (Income and bills), plus "My regular pay".
    private static let kinds: [(key: String, name: String, symbol: String)] = [
        ("salary", "Salary", "briefcase"), ("regular", "My regular pay", "calendar"),
        ("bonus", "Bonus", "sparkle"), ("interest", "Interest", "percent"),
        ("gifts", "Gifts", "gift"), ("government", "Government credits", "building.columns"),
        ("tax_refund", "Tax refund", "dollarsign.square"), ("other", "Other income", "ellipsis"),
    ]

    // MARK: What each step asks

    private var title: String {
        switch step {
        case .out, .into: return "What was this?"
        case .accounts: return "Where did it go?"
        case .charges: return "What did this pay back?"
        case .kinds: return "What kind of income?"
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
            let mine = accounts.filter { $0.id != t.accountId }
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
            return [Option(id: "weekly", label: "Every week"), Option(id: "biweekly", label: "Every 2 weeks"),
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
        case .kinds, .guess, .category:
            return []
        }
    }

    /// "Pearl will remember this for M. Papas."
    private var footer: String? {
        switch step {
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
            let account = accounts.first { "acct:" + $0.id == choice }
            let saved = choice == "elsewhere" || ["savings", "investment"].contains(account?.kind ?? "")
            onAnswer(.mark(t.id, ["case": saved ? "saved" : "moved", "remember": true]))
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
            if ask.kind == .incomeType {
                onAnswer(.incomeType(t.id, kind: choice))
            } else {
                onAnswer(.mark(t.id, ["case": "pay", "income_kind": choice]))
            }
        case .cadence:
            // Her answer is the schedule in Income and bills, not Pearl's guess.
            if choice == "once" {
                onAnswer(.mark(t.id, ["case": "pay", "income_kind": "salary"]))
            } else {
                onAnswer(.regularPay(t, cadence: choice == "changes" ? "irregular" : choice))
            }
        case .charges:
            guard let charge = charges.first(where: { $0.id == choice }) else { return }
            // The same shop sending money back is a refund; anyone else, a payback.
            let refund = charge.name.lowercased() == who.lowercased()
            onAnswer(.mark(t.id, ["case": refund ? "refund" : "payback", "charge": charge.id]))
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

    private var amountText: String { (t.inflow ? "+" : "\u{2212}") + Format.amount(t.amount) }
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
