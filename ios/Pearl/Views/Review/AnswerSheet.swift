import SwiftUI

/// One Needs a look question as the iOS sheets ask it (THL-231, THL-232):
/// Pearl's guess first when there is one (T-06a), then four or five answers
/// (T-06, T-08, T-12), and only the follow-up an answer needs: which account
/// (T-07), which purchase (T-09), what kind of income (T-71), how often it
/// pays (T-31), whose it is (T-13, T-60), who sent it (T-14), whether a
/// transfer repeats (T-69) or someone is paying her back (PQ-03, which
/// replaced T-70).
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
    @State private var charges: [BriefTransaction] = []
    /// For a category picked as part of another answer (a purchase, a
    /// recurring payment): what to do with it.
    @State private var then: Then = .category
    /// "A refund or payback": the deposit's parts (THL-291, S-09 to S-12).
    @State private var parting = false
    /// TEST-31 S-11w: her share is saved and more came in; "What's the extra?".
    @State private var shareExtra: ShareExtraAsk?
    @State private var shareError: String?
    @State private var heldShareReply: MarkReply?

    struct ShareExtraAsk: Identifiable {
        let reply: MarkReply
        let extra: MarkReply.ShareExtra
        var id: String { extra.charge }
    }
    /// T-08 / T-12: which side of money in is showing.
    @State private var incomeSide = true
    @State private var intoChoice: String?
    /// G1-WhatWasThis-r (T-08): Something else… opened in place.
    @State private var intoEverything = false
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
    /// TP-02 › Paid back on money in from a joint account (Paybacks 2):
    /// PB-30 with its other owner picked, or PP-01 first with more.
    @State private var jointStart: JointPaybackStart?
    /// PB-11 "Who paid you back?" (Paid back, 2026-11-15), and what she
    /// picked, acted on once it has closed.
    @State private var whoPaid = false
    @State private var pickedWho: PaidBackWho?
    /// PAID-03: who Pearl thinks it was (GET paid-back-who), picked for her
    /// on PB-11 with why, as from the purchase side (PAID-02).
    @State private var likelyWho: PaidBackWho?
    @State private var likelyPerson: String?
    /// PB-15: a person who isn't on a split; T-09's purchase list counts
    /// the whole amount as paid back by them.
    @State private var payerName: String?
    /// PB-30 for this person, with this purchase ticked (2026-11-16): PQ-03's
    /// tile when the money is more than its share, or the person its split
    /// tiles name for Something else.
    @State private var partPerson: String?
    @State private var mustTick: String?
    /// Many purchases (MP-01 / MP-02, 2026-11-17): PB-11's Work or The
    /// shop, ticking several of her purchases in the parts sheet.
    @State private var manyWho: PaidBackWho?
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
    /// PQ-01 / PQ-02: the deposits from this payer, and Pearl's guess at how often.
    @State private var deposits: Deposits?

    struct Deposits: Decodable {
        let dates: [String]
        let count: Int
        let first: String?
        let cadence: String?
        let next: String?
    }
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
        // TP-02 (Paybacks 2): the money-in end of a transfer asks the money-in
        // answers, so Paid back is there; only the money-out end asks T-06.
        case .transfer: first = ask.savedTo(accounts) != nil ? .guess : (ask.t.inflow ? .into : .out)
        case .moneyIn:
            // PQ-03 (Payback question): a likely purchase, on a split or not,
            // asks "Is mPg paying you back?". A nameless e-Transfer isn't
            // "Interac" paying her back: the server sends no question then.
            if ask.item.payback != nil && (ask.t.learnable != false || ask.item.from != nil) {
                first = .payback
            } else {
                first = ask.item.guess?.action == "own" ? .guess : .into
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
    /// T-93o / T-04n (TEST-46): Pearl's best guess is Other, so the page's
    /// guess card opens What was this? (G1-WhatWasThis-r), not the category list.
    private var otherGuess: Bool {
        ask.kind == .category && pageCategory == nil && (ask.item.guess?.text ?? t.category) == "Other"
    }
    private var who: String { t.name }

    var body: some View {
        Group {
            if step == .out {
                // T-06: Spending is the categories; Not spending, the answers.
                CategorySheet(name: who, amount: amountText, tone: tone, categories: categories,
                              current: pageCategory ?? t.category ?? ask.item.guess?.text ?? "Other",
                              merchant: learnable ? who : nil,
                              onRegularBill: fromPage ? nil : { regularBill = $0 },
                              title: fromPage && ask.kind == .category && !otherGuess ? "Category" : "What was this?",
                              preview: learnable ? CategorySheet.preview(api: api, id: t.id, merchant: who) : nil,
                              notSpending: CaseTile.notSpending, startNotSpending: ask.kind != .category,
                              onCase: { outCase($0, remember: $1) },
                              confirmsCurrent: (ask.kind == .category && confirmsGuess) || splitSaid != nil,
                              caseRule: { outRule($0) },
                              extras: fromPage ? nil : AnyView(outOptions),
                              answersAtOnce: true,
                              // Off where other rows are open or it varies: her answer here is for this row.
                              newOnesOn: pageAlways ?? (learnable && t.mixed != true && ask.item.siblings.isEmpty),
                              showsAlways: pageAlways == nil,
                              // G1-WhatWasThis-r (T-04n): Pearl's guess leads, then her
                              // four likeliest; every other answer under Something else….
                              // TEST-46: an "Other?" guess opens What was this? from the page too.
                              leadsWithLikely: !(fromPage && ask.kind == .category) || otherGuess,
                              // TEST-46: the page's own ask carries no guess, so an
                              // "Other?" guess is said here, with its Yes on top.
                              guess: ask.kind == .category && pageCategory == nil
                                  ? (ask.item.guess?.text ?? (otherGuess ? "Other" : nil)) : nil) { name, remember in
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
            } else if step == .payback, let q = ask.item.payback {
                paybackSheet(q)
            } else if step == .recurring || step == .joint || step == .cadence {
                // RQ-01, PQ-01, PQ-02 (POLISH-01): why Pearl asks, the
                // payments so far, and tiles that answer at once.
                tilesSheet
            } else {
                choiceSheet
            }
        }
        .presentationDragIndicator(.visible)
        .task(id: step) { await loadOptions() }
        .modifier(JointPaybackFlow(start: $jointStart, api: api) { reply in onAnswer(.done(reply)) })
        .sheet(isPresented: $whosing) {
            if let f = full {
                // G2b-Whose T-76: the tiles that answer at once (JointSplitViews).
                WhoseTilesSheet(t: f, api: api) { said, _ in
                    whosing = false
                    whoseSaid = said
                    // Her part may have changed, so Split my part says so.
                    Task { full = try? await api.get("api/transactions/\(f.id)") }
                }
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
            // PB-11 › A person: their shares ticked as they add up (PB-30),
            // or S-35's ticks, then part or all of each share (PB-13).
            PartsSheet(deposit: PartsDeposit(id: t.id, name: who, amount: t.amount, date: t.date), api: api,
                       paidBack: manyWho == nil, payer: manyWho == nil ? partPerson ?? ask.item.from : nil,
                       person: partPerson, mustTick: mustTick, many: manyWho,
                       // PB-11 was skipped for a person Pearl knows: Change brings it back.
                       onChangeWho: manyWho == nil && partPerson == nil ? {
                           parting = false
                           Task {
                               try? await Task.sleep(nanoseconds: 450_000_000)
                               whoPaid = true
                           }
                       } : nil) { reply in
                parting = false
                onAnswer(.done(reply))
            }
        }
        .sheet(isPresented: $whoPaid, onDismiss: {
            let picked = pickedWho
            pickedWho = nil
            if let picked = picked { paidBack(picked) }
        }) {
            // PB-11 (1351:9324): A person · The shop · Work.
            PaidBackWhoSheet(face: payer, sub: "\(amountText) · \(who) · \(Format.short(t.date))",
                             picked: likelyWho, pickedPerson: likelyPerson,
                             onPick: { pickedWho = $0; whoPaid = false },
                             onClose: { whoPaid = false })
        }
        .sheet(item: $shareExtra, onDismiss: {
            // Closed without answering: her share stays saved, the extra counts as money in.
            if let held = heldShareReply { heldShareReply = nil; onAnswer(.done(held)) }
        }) { ask in
            // TEST-31 S-11w (1294:2157): "What's the extra $15.00?" with the
            // shared tiles, for a "Your share of …" row picked on the charge
            // list; her share is the part already sorted. Work and The shop
            // from PB-11 are Many purchases now (PartsSheet `many`).
            PartsSheet(deposit: PartsDeposit(id: t.id, name: who, amount: t.amount, date: t.date), api: api,
                       credited: [PartsSheet.Part(kind: "reimbursement", amount: ask.extra.share,
                                                  charge: ask.extra.charge, merchant: ask.extra.merchant)],
                       shareLine: "\(Format.amount(ask.extra.share)) pays back your share of \(ask.extra.merchant).") { reply in
                heldShareReply = nil
                shareExtra = nil
                onAnswer(.done(reply))
            }
            .onAppear { heldShareReply = ask.reply }
        }
    }

    // MARK: Options

    /// PB-11 from the deposit (PAID-03): Pearl's pick first, read from who
    /// sent it as the purchase side reads it; with nothing to go on (or
    /// offline) it opens as before, A person first and nothing picked.
    private func askWhoPaid() async {
        struct Likely: Decodable { let kind: String?; let person: String? }
        partPerson = nil
        mustTick = nil
        manyWho = nil
        let likely: Likely? = try? await api.get("api/transactions/\(t.id)/paid-back-who")
        switch likely?.kind {
        case "person": likelyWho = .person
        case "shop": likelyWho = .shop
        case "work": likelyWho = .work
        default: likelyWho = nil
        }
        likelyPerson = likely?.person
        // PB-30 (Paybacks & undo, note 1397:4697): PB-11 is skipped when the
        // e-Transfer names someone Pearl knows; straight to what they paid back.
        if likelyWho == .person, likely?.person != nil {
            paidBack(.person)
            return
        }
        whoPaid = true
    }

    /// TP-02: money in from a joint account into one only hers, as a
    /// transfer, can be its other owner paying her back.
    private var jointPayback: JointPaybackStart? {
        guard t.inflow, let transfer = full?.transfer, let j = transfer.joint, let out = transfer.otherId else { return nil }
        return JointPaybackStart(deposit: PartsDeposit(id: t.id, name: who, amount: t.amount, date: t.date),
                                 people: j.people, account: j.account, out: out)
    }

    private func loadOptions() async {
        if step == .sender, contacts.state == .asking { await contacts.load() }
        guard step == .out || step == .into, full == nil else { return }
        struct Cases: Decodable { let learnable: Bool? }
        // Both at once (perf rehaul, 2026-11-19).
        async let casesReply: Cases? = try? api.get("api/transactions/\(t.id)/cases")
        async let fullReply: Transaction? = try? api.get("api/transactions/\(t.id)")
        if let c = await casesReply { learnable = c.learnable ?? true }
        if let f = await fullReply { full = f }
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
                APCard {
                    if joint {
                        Button { whosing = true } label: {
                            // T-06jr (G2b-Purchase): "Whose was it?   Half each ›".
                            optionLabel("Whose was it?", done: whoseSaid != nil, icon: "person.2",
                                        value: f.jointShareValue)
                        }
                        .buttonStyle(.plain)
                        if canSplit || f.canOneOff { APSeparator(afterFace: false) }
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
                    if canSplit && f.canOneOff { APSeparator(afterFace: false) }
                    if f.canOneOff {
                        Toggle(isOn: Binding(get: { oneOff ?? f.oneOff }, set: { on in Task { await setOneOff(on) } })) {
                            HStack(spacing: 12) {
                                CFIcon(symbol: "1.circle")
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

    private func optionLabel(_ title: String, done: Bool, icon: String? = nil, value: String? = nil) -> some View {
        HStack(spacing: 12) {
            if let icon = icon { CFIcon(symbol: icon) }
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer(minLength: 4)
            if let value = value {
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            }
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
            CFSheetTitle(title: guessTitle) { dismiss() }
            if ask.kind == .duplicate {
                // T-15: both charges, one above the other.
                VStack(alignment: .leading, spacing: 10) {
                    Text("Looks like the same charge twice.").font(Nacre.body).foregroundColor(Pearl.ink)
                    APCard {
                        dupRow(t)
                        if let twin = ask.item.twin {
                            APSeparator()
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
                Button(yesLabel) { yes() }.buttonStyle(APPrimaryButtonStyle())
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
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.link))
            }
        }
        .padding(.bottom, 8)
        .sheetPart()
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .cfSheet()
        // POLISH-01: sized to what it shows (Same purchase? was .large).
        .fitsContent()
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
                .foregroundColor(Pearl.ink)
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
            CFSheetTitle(title: "What was this?") { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: who, amount: amountText, tone: tone, sub: ask.evidence)
                    if let j = full?.transfer?.joint, ask.kind == .transfer {
                        // TP-02: "Paired with Joint ··1123 (you and Mom). Today it counts as your own money."
                        Text("Paired with \(j.account) (you and \(Format.andList(j.people))). Today it counts as your own money.")
                            .font(Nacre.body).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    // G1-WhatWasThis-r (T-08, approved): OR and four likely
                    // answers; every other one opens in place under Something
                    // else…; Always for the payer last. A transfer (TP-02)
                    // opens with them all, its My own money ringed.
                    if intoEverything || ask.kind == .transfer {
                        Text("INCOME").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16).accessibilityAddTraits(.isHeader)
                        CaseGrid(cases: CaseTile.income, chosen: answer(income: true))
                        Text("NOT INCOME").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16).padding(.top, 4).accessibilityAddTraits(.isHeader)
                        // TP-02: on a transfer, My own money is today's answer, ringed.
                        CaseGrid(cases: CaseTile.notIncome, chosen: answer(income: false, current: ask.kind == .transfer ? "own" : nil))
                    } else {
                        APSectionLabel(text: "Or")
                        CFTileGrid {
                            ForEach(CaseTile.likelyIn, id: \.tile.key) { item in
                                CFTile(symbol: item.tile.symbol, title: item.tile.label, mark: .rest) {
                                    answer(income: item.income).wrappedValue = item.tile.key
                                }
                                .accessibilityLabel(item.tile.label)
                            }
                        }
                        APCard {
                            Button { withAnimation(.easeOut(duration: 0.2)) { intoEverything = true } } label: {
                                CFRowLabel(symbol: "ellipsis", title: "Something else…",
                                           sub: "Every other answer, on this page", trailing: .chevron)
                            }
                            .buttonStyle(.plain)
                            .accessibilityHint("Shows every other answer here")
                        }
                    }
                    if learnable && pageAlways == nil {
                        APCard { CFToggleRow(symbol: "repeat", title: "Always for \(who)", isOn: $rememberInto) }
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
        }
        .cfSheet()
        .fitsContent()
    }

    /// A tile answers at once.
    private func answer(income: Bool, current: String? = nil) -> Binding<String?> {
        Binding(get: { current }, set: { key in
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
        // PB-10: one Paid back tile; PB-11 asks who paid her back.
        case "paid_back":
            if let start = jointPayback {
                // TP-03: PB-11 is skipped; it's the joint account's other owner.
                jointStart = start
            } else {
                Task { await askWhoPaid() }
            }
        case "own": onAnswer(.mark(t.id, ["case": "own", "remember": learnable && rememberInto]))
        case "loan": onAnswer(.mark(t.id, ["case": "borrowed"]))
        case "out_of_savings": onAnswer(.mark(t.id, ["case": "out_of_savings"]))
        case "lent_back": onAnswer(.mark(t.id, ["case": "lent_back"]))
        default: onAnswer(.mark(t.id, ["case": "not_mine", "reason": "Not mine",
                                       "remember": learnable && rememberInto]))
        }
    }

    /// PB-11's answer. The shop and Work: Many purchases, MP-02 / MP-01
    /// (replacing T-09rs / T-09w's one pick), the rest as S-11m / S-11w in
    /// the same save. A person: always the parts sheet, which routes it
    /// (PaidBackPerson.route): PB-30 for someone who owes her, PP-01 when it
    /// can't tell who, and PB-30 with OTHER PURCHASES only for someone named
    /// who owes her nothing (T-14 Who sent this? first when no one owes her
    /// and the money names no one). Not PB-15 any more (2026-11-18).
    private func paidBack(_ who: PaidBackWho) {
        manyWho = nil
        switch who {
        case .shop, .work:
            manyWho = who
            parting = true
        case .person:
            // PQ-03's tiles name who on her splits it is: PB-30 for them.
            parting = true
        }
    }

    // MARK: RQ-01, PQ-01, PQ-02: tiles that answer at once (POLISH-01)

    private var tilesSheet: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: title) { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    // RQ-01: the amount and the account only; the schedule is in the card.
                    QuestionHeader(name: who, amount: amountText, tone: tone,
                                   sub: t.accountName ?? (step == .joint ? "Joint" : nil))
                    switch step {
                    case .recurring: recurringTiles
                    case .joint: jointTiles
                    default: cadenceTiles
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
        }
        .cfSheet()
        .fitsContent()
        .task(id: step) {
            guard step == .joint || step == .cadence, deposits == nil else { return }
            deposits = try? await api.get("api/transactions/\(t.id)/paydays")
        }
    }

    /// RQ-01 (1389:23274, dark 1389:23646; THL-292, THL-295, THL-297), as
    /// LT-02 shortens it (1425:6768, dark 1425:7025; TEXT-01): the schedule
    /// is the caption ("EVERY MONTH SINCE MARCH"), the card says the money
    /// ("$374.16 from TD Chequing, around the 2nd") and "Next: around Tue,
    /// Dec 2"; no footer.
    @ViewBuilder private var recurringTiles: some View {
        let s = ask.item.series
        QuestionCaption(text: recurringCaption)
        WhyCard(sentence: recurringSentence, dates: s?.dates ?? [], amount: s?.amount ?? abs(t.amount),
                ringed: String(t.date.prefix(10)),
                footer: s?.next.map { "Next: around \(Format.weekdayDay($0))" })
        QuestionCaption(text: "Yes, it’s…")
        AnswerGrid {
            AnswerTile(title: "Rent", line: "Spending on rent", symbol: "house") { recurring("rent", "Rent") }
            AnswerTile(title: "Into savings", line: "Counts as saved", symbol: "lifepreserver") {
                recurring("saved", "Into savings")
            }
            AnswerTile(title: "My other account", line: "Doesn’t count", symbol: "arrow.left.arrow.right") {
                recurring("moved", "My other account")
            }
            // Opens the category step, as before.
            AnswerTile(title: "Something I pay for", line: "Pick a category next", symbol: "bag") {
                then = .recurring
                go(.category)
            }
        }
        // THL-292: each one is asked on its own.
        AnswerRow(symbol: "person.crop.circle.badge.xmark", title: "No, it isn’t regular",
                  line: "Ask about each one") { onAnswer(.dismiss(ask.item.key)) }
    }

    /// "all 9", or "both" for two.
    private var seriesAll: String {
        let n = ask.item.series?.count ?? 0
        return n == 2 ? "both" : n > 2 ? "all \(n)" : "it"
    }

    /// RQ-01b (1389:24086): "Rent · all 9 sorted, and the ones to come", with Undo.
    private func recurring(_ kind: String?, _ label: String, category: String? = nil) {
        onAnswer(.recurring(key: ask.item.key, kind: kind, category: category,
                            toast: "\(label) · \(seriesAll) sorted, and the ones to come"))
    }

    /// LT-02's caption: "Every month since March", "Every payday since
    /// March", "Every two weeks since March".
    private var recurringCaption: String {
        let s = ask.item.series
        let since = s?.first.map { " since \(Self.sinceMonth($0))" } ?? ""
        let every: String
        switch s?.cadence {
        case "monthly": every = "Every month"
        case "payday": every = "Every payday"
        default:
            let w = s?.when?.components(separatedBy: ", ").first ?? ""
            every = w.prefix(1).uppercased() + w.dropFirst()
        }
        let text = (every + since).trimmingCharacters(in: .whitespaces)
        return text.isEmpty ? "Why Pearl is asking" : text
    }

    /// "$374.16 from TD Chequing, around the 2nd" (LT-02): the amount, the
    /// account and the day; the schedule is in the caption.
    private var recurringSentence: String {
        let s = ask.item.series
        let money = Format.amount(s?.amount ?? abs(t.amount))
        let account = (t.accountName ?? "").components(separatedBy: " ••").first.flatMap { $0.isEmpty ? nil : $0 }
        let from = "\(money) from \(account ?? "your account")"
        switch s?.cadence {
        case "monthly":
            let day = Format.localDay(s?.dates?.last ?? t.date).map { Calendar.current.component(.day, from: $0) }
            return "\(from)\(day.map { ", around the \(ordinal($0))" } ?? "")"
        case "payday":
            return from
        default:
            let rest = s?.when?.components(separatedBy: ", ").dropFirst().joined(separator: ", ") ?? ""
            return rest.isEmpty ? from : "\(from), \(rest)"
        }
    }

    /// "March", or "March 2025" for one more than a year back.
    static func sinceMonth(_ iso: String) -> String {
        guard let d = Format.localDay(iso) else { return iso }
        let f = DateFormatter()
        let thisYear = Calendar.current.component(.year, from: Date()) == Calendar.current.component(.year, from: d)
        f.dateFormat = thisYear ? "MMMM" : "MMMM yyyy"
        return f.string(from: d)
    }

    /// PQ-01 (1393:83919, dark 1393:84293; THL-305, THL-232): Me, each person
    /// on the account, Both of us. It answers for every deposit from them.
    /// TEXT-01 string list: the card says "Every 2 weeks since September";
    /// no "It's a joint account…" line and no "Pearl remembers…" footer.
    @ViewBuilder private var jointTiles: some View {
        let people = ask.item.people ?? []
        let share = Int((ask.item.share ?? 50).rounded())
        QuestionCaption(text: "Why Pearl is asking")
        WhyCard(sentence: jointSentence, dates: deposits?.dates ?? [], amount: abs(t.amount),
                ringed: String(t.date.prefix(10)))
        QuestionCaption(text: "It’s…")
        AnswerGrid(columns: 3) {
            AnswerTile(title: "Me", line: "Counts as your pay", symbol: "briefcase", current: choice == "me") {
                onAnswer(.joint(t.id, who: "me", person: nil, remember: true))
            }
            if people.isEmpty {
                AnswerTile(title: ask.item.label ?? "Someone else", line: "Not in your numbers",
                           symbol: "person.crop.circle.badge.xmark", current: choice == "them") {
                    onAnswer(.joint(t.id, who: "them", person: nil, remember: true))
                }
            } else {
                ForEach(people, id: \.self) { person in
                    AnswerTile(title: person, line: "Not in your numbers", symbol: "person.crop.circle.badge.xmark",
                               current: choice == "them:" + person) {
                        onAnswer(.joint(t.id, who: "them", person: person, remember: true))
                    }
                }
            }
            AnswerTile(title: "Both of us", line: "Your \(share)% counts", symbol: "person.2", current: choice == "both") {
                onAnswer(.joint(t.id, who: "both", person: nil, remember: true))
            }
        }
    }

    /// "Every 2 weeks since September" (TEXT-01); "4 deposits since
    /// September" when there's no schedule.
    private var jointSentence: String {
        let since = deposits?.first.map { " since \(Self.sinceMonth($0))" } ?? ""
        let money = Format.amount(abs(t.amount))
        guard let d = deposits, d.count > 1 else { return "\(who) paid \(money) into your joint account." }
        if let every = Self.every(d.cadence) {
            return every.prefix(1).uppercased() + every.dropFirst() + since
        }
        return "\(d.count) deposits\(since)"
    }

    /// PQ-02 (1393:84663, dark 1393:85042; THL-232, THL-296): six tiles,
    /// Pearl's guess dashed and never picked for her. TEXT-01 string list:
    /// "5 deposits, about 2 weeks apart", no "Next one around…" line and no
    /// "Pearl counts every deposit…" footer.
    @ViewBuilder private var cadenceTiles: some View {
        let guess = deposits?.cadence
        QuestionCaption(text: "What Pearl sees")
        WhyCard(sentence: cadenceSentence, dates: deposits?.dates ?? [], amount: abs(t.amount),
                ringed: String(t.date.prefix(10)))
        QuestionCaption(text: "It comes…")
        AnswerGrid {
            ForEach(Self.cadences, id: \.key) { c in
                AnswerTile(title: c.title, line: guess == c.key ? "Looks like this" : c.line,
                           current: choice == c.key || (choice == "irregular" && c.key == "changes"),
                           guess: guess == c.key) {
                    if c.key == "once" {
                        // Pay that won't repeat isn't a salary.
                        onAnswer(.mark(t.id, ["case": "pay", "income_kind": "other"]))
                    } else {
                        // Her answer is the schedule in Income and bills, not Pearl's guess.
                        onAnswer(.regularPay(t, cadence: c.key == "changes" ? "irregular" : c.key))
                    }
                }
            }
        }
    }

    private static let cadences: [(key: String, title: String, line: String)] = [
        ("weekly", "Every week", "52 a year"), ("biweekly", "Every 2 weeks", "26 a year"),
        ("semimonthly", "Twice a month", "Like the 1st and 15th"), ("monthly", "Monthly", "Once a month"),
        ("changes", "It changes", "Pearl works it out"), ("once", "Just this once", "Not regular pay"),
    ]

    /// "5 deposits, about 2 weeks apart" (TEXT-01).
    private var cadenceSentence: String {
        guard let d = deposits, d.count > 1 else { return "This is the first deposit from \(who) Pearl has seen." }
        let apart: String
        switch d.cadence {
        case "weekly": apart = ", about a week apart"
        case "biweekly": apart = ", about 2 weeks apart"
        case "semimonthly": apart = ", about twice a month"
        case "monthly": apart = ", about a month apart"
        default: apart = ""
        }
        return "\(d.count) deposits\(apart)"
    }

    /// "every 2 weeks", for Pearl's guess at a schedule.
    static func every(_ cadence: String?) -> String? {
        switch cadence {
        case "weekly": return "every week"
        case "biweekly": return "every 2 weeks"
        case "semimonthly": return "twice a month"
        case "monthly": return "every month"
        default: return nil
        }
    }

    // MARK: PQ-03 Is mPg paying you back? (Payback question)

    /// PQ-03 / PQ-03b: why Pearl is asking and the likely purchases, in the
    /// server's words; a tile answers at once, with the ink toast and Undo
    /// (PQ-03c). The answer goes through the payback mark, as before.
    private func paybackSheet(_ q: PaybackQuestion) -> some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: title) { dismiss() }.sheetPart()
            ScrollView {
                PaybackQuestionBody(
                    question: q, amount: amountText, date: t.date,
                    onTile: { tile in Task { await tapTile(tile) } },
                    // "Find the purchase": PB-11's A person. The person the
                    // split tiles name: PB-30 for them; else their splits
                    // (PB-30 or PP-01 first), or PB-15's purchase search.
                    onElse: {
                        let named = Set(q.tiles.compactMap(\.person))
                        partPerson = named.count == 1 ? named.first : nil
                        mustTick = nil
                        paidBack(.person)
                    },
                    onNot: { go(.into) },
                    // T-14 Who sent this?: the name is used from then on.
                    onName: { go(.sender) })
                    .padding(.horizontal, 16).padding(.bottom, 12)
                    .sheetPart()
            }
        }
        .cfSheet()
        .fitsContent()
    }

    /// PQ-03's tile (2026-11-16): the single tap, as before, unless the money
    /// is more than the tile's share and that person owes on other purchases:
    /// then PB-30 with this one ticked and the others as they add up. Offline,
    /// the single tap.
    private func tapTile(_ tile: PaybackQuestion.Tile) async {
        if let from = await PaybackQuestion.partsPerson(api: api, id: t.id, amount: t.amount, tile: tile) {
            partPerson = from
            mustTick = tile.charge
            parting = true
            return
        }
        onAnswer(.payback(t.id, charge: tile.charge, toast: tile.toast, person: tile.person))
    }

    // MARK: A list of answers

    private struct Option: Identifiable {
        let id: String
        let label: String
        var detail: String? = nil
    }

    /// Who sent this? searches her contacts too (product owner, 2026-11-20).
    @StateObject private var contacts = ContactNames()

    private var choiceSheet: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: title) { dismiss() }.sheetPart()
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
                            // PB-15: "SAM ISN’T ON A SPLIT · PICK THE PURCHASE".
                            Text(payerName.map { "\(firstName($0)) isn’t on a split · pick the purchase".uppercased() } ?? "LIKELY")
                                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                        if step == .sender && !options.isEmpty {
                            Text(options.contains { $0.detail == "In your contacts" } && !names.isEmpty
                                 ? "RECENT AND CONTACTS" : options.contains { $0.detail == "In your contacts" }
                                 ? "CONTACTS" : "RECENT")
                                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                        if step == .sender && contacts.state == .off {
                            ContactsOffLine().padding(.horizontal, 12)
                        }
                        if !options.isEmpty {
                            APCard {
                                ForEach(Array(options.enumerated()), id: \.element.id) { index, o in
                                    if index > 0 { APSeparator(afterFace: false) }
                                    optionRow(o)
                                }
                            }
                        } else if step == .charges {
                            Text("No purchases match.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                .padding(.horizontal, 16)
                        }
                        if step == .charges, let shareError = shareError {
                            Text(shareError).font(Nacre.footnote).foregroundColor(Pearl.caution)
                                .padding(.horizontal, 16)
                        }
                    }
                    if let footer = footer {
                        Text(footer).font(Nacre.footnote).foregroundColor(Pearl.ink)
                            .frame(maxWidth: .infinity).multilineTextAlignment(.center)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 0) {
                if step == .sender {
                    // T-14 (THL-232, R-09): keep what the bank called it.
                    Button("Use your bank’s name instead") { onAnswer(.party(t.id, name: "")) }
                        .buttonStyle(NacreTextButtonStyle(tone: Pearl.link))
                    Button("Skip") { onAnswer(.skip(ask.item.key, true)) }
                        .buttonStyle(NacreTextButtonStyle(tone: Pearl.link))
                }
                // POLISH-01 audit 7: Where did it go? answers on the tap, as
                // Is Sam paying you back? does. Continue and Save stay where
                // she types (Who sent this?) or searches (What did this pay back?).
                if step != .kinds && step != .otherKinds && step != .payback && step != .accounts {
                    Button(primaryLabel) { primary() }
                        .buttonStyle(APPrimaryButtonStyle())
                        .disabled(!ready)
                        .padding(.horizontal, 16).padding(.top, 4).padding(.bottom, 8)
                }
            }
            .sheetPart()
        }
        .cfSheet()
        // POLISH-01 audit 1: sized to its content, not .large.
        .fitsContent()
        .task(id: step) {
            if step == .charges { await searchCharges() }
            if step == .accounts, accounts.isEmpty, fetchedAccounts.isEmpty,
               let o: AccountsOverview = try? await api.get("api/accounts/overview") {
                fetchedAccounts = o.linked
            }
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
            // "Where did it go?" (POLISH-01 audit 7) answers at once: no Save,
            // then Continue. "Is mPg paying you back?" is tiles (PQ-03).
            if step == .accounts { primary() }
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
        // REDESIGN-09 (G1-Asks): every sheet search is a well.
        .wellStyle(focused: false, capsule: true)
    }

    /// T-71: what kind of income, as tiles.
    private var kindTiles: some View {
        // A+ (G1-WhatWasThis, money in): slim tiles, two across.
        CFTileGrid {
            ForEach(Self.kinds, id: \.key) { k in
                // A tile answers at once.
                CFTile(symbol: k.symbol, title: k.name, mark: choice == k.key ? .current : .rest) {
                    choice = k.key; primary()
                }
                .accessibilityLabel(k.name)
            }
        }
    }

    /// T-08k (SPLIT-18): "What kind of income?" after Other income: the
    /// other four of finance/income.py's kinds. A tile saves at once, with
    /// the page's Always as it was (not asked again). If the save fails, the
    /// tile un-highlights and "Couldn’t save that. Try again." shows under
    /// the grid, here and not on the screen behind.
    private var otherKindTiles: some View {
        // T-71b (G1-MoneyIn): "Which kind?" is the sheet's title; the error
        // is kit `.errline` (ⓘ in danger) under the tiles.
        VStack(alignment: .leading, spacing: 12) {
            CaseGrid(cases: CaseTile.otherIncome, chosen: Binding(get: { savingKind }, set: { key in
                guard let key = key else { return }
                choice = key
                saveOtherKind(key)
            }), role: "income kind")
            .disabled(savingKind != nil)
            if let kindError = kindError { APErrorLine(text: kindError) }
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
                kindError = "Couldn’t save that. Try again."   // APErrorLine announces it.
            }
        }
    }

    /// The app's income kinds (Income and bills), plus "My regular pay".
    private static let kinds: [(key: String, name: String, symbol: String)] = [
        ("regular", "My pay", "briefcase"), ("bonus", "Bonus", "sparkle"),
        ("gifts", "A gift", "gift"), ("other", "Other income", "ellipsis"),
    ]

    // MARK: What each step asks

    private var title: String {
        switch step {
        case .out, .into: return "What was this?"
        case .accounts: return "Where did it go?"
        // PB-15: "What did Sam pay back?" (The shop and Work are MP-02 / MP-01.)
        case .charges:
            return payerName.map { "What did \(firstName($0)) pay back?" } ?? "What did this pay back?"
        case .kinds: return "What kind of income?"
        case .otherKinds: return "Which kind?"
        case .cadence: return "How often is this pay?"
        case .joint: return "Whose pay is this?"
        case .sender: return "Who sent this?"
        case .recurring: return "Is this a recurring transfer?"
        case .payback: return "Is \(ask.item.payback?.who ?? payer) paying you back?"
        case .guess, .category: return ""
        }
    }

    /// RQ-01 moved the schedule into its card; PQ-01's "Joint" is its tilesSheet's.
    private var sub: String? { nil }

    private var payer: String { ask.item.from ?? who }

    /// "Sam" from "Sam Lee", as PB-12 and PB-15 say it.
    private func firstName(_ name: String) -> String {
        name.split(separator: " ").first.map(String.init) ?? name
    }

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
                // TEST-31 T-09w: "Your share of Pai Northern Thai · $60.00"
                // over "Wed, Nov 12 · $120.00 split with Sam", and the whole
                // purchase as "Pai Northern Thai, all of it · $120.00" over
                // "Your share and Sam’s".
                if let others = c.splitWith, !others.isEmpty {
                    if c.share == true {
                        return Option(id: "share:" + c.id,
                                      label: "Your share of \(c.name) · \(Format.amount(c.left ?? c.amount))",
                                      detail: "\(Format.weekdayDay(c.date)) · \(Format.amount(c.whole ?? abs(c.amount))) split with \(Format.andList(others))")
                    }
                    return Option(id: c.id, label: "\(c.name), all of it · \(Format.amount(abs(c.amount)))",
                                  detail: "Your share and " + Format.andList(others.map(possessive)))
                }
                return Option(id: c.id, label: "\(c.name) · \(Format.amount(c.amount))",
                       detail: [Format.weekdayDay(c.date), c.accountName].compactMap { $0 }.joined(separator: " · "))
            }
        case .sender:
            let typed = text.trimmingCharacters(in: .whitespaces)
            let recent = names.filter { typed.isEmpty || $0.localizedCaseInsensitiveContains(typed) }
                .map { Option(id: "name:" + $0, label: $0) }
            let found = contacts.matches(typed, excluding: names)
                .map { Option(id: "name:" + $0, label: $0, detail: "In your contacts") }
            // The typed name, when nobody listed matches it, is one row to pick.
            let new = !typed.isEmpty && !names.contains { $0.caseInsensitiveCompare(typed) == .orderedSame }
                && !contacts.has(typed)
                ? [Option(id: "name:" + typed, label: "Add “\(typed)” as a new name")] : []
            return recent + found + new
        // RQ-01, PQ-01 and PQ-02 are tiles (tilesSheet); PQ-03 too (paybackSheet).
        case .kinds, .otherKinds, .guess, .category, .cadence, .joint, .recurring, .payback:
            return []
        }
    }

    /// The line under the answers. TEXT-01 cuts every "Pearl will remember
    /// this for {who}." footer (the Always toggle says it), so only PB-15's
    /// is left.
    private var footer: String? {
        switch step {
        // PB-15 (1351:10581): what picking does, and where splitting is.
        case .charges where payerName != nil:
            let first = firstName(payerName ?? who)
            return "Pick a purchase and it counts as paid back by \(first). To split it with \(first) first, open the purchase."
        default: return nil
        }
    }

    /// Continue when another question follows, Save when this is the last.
    private var primaryLabel: String {
        switch (step, choice) {
        case (.out, "paid"), (.out, "moved"), (.into, "earned"), (.into, "back"), (.into, "else"), (.kinds, "regular"),
             (.sender, _):
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
            case "back": manyWho = nil; parting = true
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
        case .charges:
            if choice.hasPrefix("share:") {
                saveShare(String(choice.dropFirst(6)))
                return
            }
            guard let charge = charges.first(where: { $0.id == choice }) else { return }
            // The same shop sending money back is a refund; anyone else, a payback.
            let refund = charge.name.lowercased() == who.lowercased()
            var body: [String: Any] = ["case": chargeCase ?? (refund ? "refund" : "payback"), "charge": charge.id]
            // PB-15: paid back by the person she named.
            if let payer = payerName { body["person"] = payer }
            onAnswer(.mark(t.id, body))
        case .sender:
            let name = choice.hasPrefix("name:") ? String(choice.dropFirst(5))
                : text.trimmingCharacters(in: .whitespaces)
            guard !name.isEmpty else { return }
            onAnswer(.party(t.id, name: name))
        case .guess, .category, .cadence, .joint, .recurring, .payback:
            break
        }
    }

    /// TEST-31: work paid her share, picked as a "Your share of …" row.
    /// Saved here so S-11w can follow when more than her share came in;
    /// otherwise it's answered as any mark.
    private func saveShare(_ charge: String) {
        Task {
            do {
                let reply: MarkReply = try await api.post("api/transactions/\(t.id)/mark",
                                                          ["case": "reimbursement",
                                                           "charge": charge, "share": true])
                if let extra = reply.extra {
                    shareExtra = ShareExtraAsk(reply: reply, extra: extra)
                } else {
                    onAnswer(.done(reply))
                }
            } catch {
                shareError = (error as? APIError)?.problem?.error ?? "Couldn’t save that. Try again."
            }
        }
    }

    private func searchCharges() async {
        struct Reply: Decodable { let charges: [Lenient<BriefTransaction>] }
        let q = text.trimmingCharacters(in: .whitespaces)
        if q.isEmpty, let candidates = ask.item.candidates, !candidates.isEmpty {
            charges = candidates.sorted { ($0.likely == true ? 0 : 1) < ($1.likely == true ? 0 : 1) }
            return
        }
        if let reply: Reply = try? await api.get("api/transactions/\(t.id)/charges",
                                                      query: ["q": q, "case": chargeCase ?? ""]) {
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
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        // S-03ax (TEST-17): at accessibility sizes the circle goes, so the
        // initials are never cut, and the name wraps to two lines.
        let big = typeSize.isAccessibilitySize
        // A+ kit `.who`: the 44 pt ring, the name in Fraunces 22, the line in 15.
        HStack(spacing: 12) {
            if !big {
                CFRing(name: name, size: 44)
            }
            VStack(alignment: .leading, spacing: 2) {
                // POLISH-01 (RQ-01, audit 2): the name and the line under it
                // wrap to two lines rather than cut ("9 so f…", the bank's name).
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(big ? 3 : 2)
                    .fixedSize(horizontal: false, vertical: true)
                (Text(amount).foregroundColor(tone)
                 + Text(sub.map { $0.isEmpty ? "" : " · " + $0 } ?? "").foregroundColor(Pearl.muted))
                    .font(Nacre.subheadline).lineLimit(big ? 3 : 2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .ignore)
        // TEST-14: "Gusto, spent $127.50", not the unread U+2212 minus.
        .accessibilityLabel([name, Format.spoken(amount), sub].compactMap { $0?.isEmpty == false ? $0 : nil }
            .joined(separator: ", "))
    }
}
