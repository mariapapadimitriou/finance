import SwiftUI

/// T-96: how a guess from Needs a look or Quick sort is answered on T-03.
struct GuessActions {
    let ask: Ask
    /// "Dining out", or "Saved to TD Savings".
    let label: String
    let accounts: [AccountsOverview.Account]
    let names: [String]
    /// Yes, and whether new ones from the merchant sort the same way.
    let onYes: (Bool) -> Void
    var onSkip: (() -> Void)? = nil
    let onAnswer: (ReviewAnswer) -> Void
    /// Opened from a Quick sort card, like Slack's catch up: edits are held for
    /// the card, which is where they're agreed to. This page has no Yes.
    var onDraft: ((CardDraft) -> Void)? = nil
    var draft = CardDraft()
}

/// What she changed on a Quick sort card's page, saved when she says Yes on the card.
struct CardDraft {
    /// "Coffee", "Saved": what the card now asks.
    var label: String?
    var category: String?
    var answer: ReviewAnswer?
    /// The Always switch, once she's touched it.
    var always: Bool?
    /// T-98s (SPLIT-06): a split made on the card's page, held for its Yes.
    var split: CardSplit?
}

/// A split held for a Quick sort card (T-98s, SPLIT-06): "Groceries, split
/// with Sam?", "Your share $42.06 · Sam owes you $42.06". Yes saves it with
/// the category in one go; Skip forgets it.
struct CardSplit {
    /// What SplitSheet would have saved.
    let body: [String: Any]
    let names: [String]
    let mine: Double
    let owed: Double

    /// What SplitSheet's onHold gives, for a purchase of `total`: the card's
    /// page and Quick sort's sheet hold the same thing (SPLIT-06, SPLIT-20).
    static func held(_ body: [String: Any], mine: Double, total: Double) -> CardSplit {
        let names = (body["people"] as? [[String: Any]] ?? []).compactMap { $0["name"] as? String }
        return CardSplit(body: body, names: names, mine: mine, owed: max(0, total - mine))
    }

    /// "Sam", "Sam and Priya", "Sam, Priya and Ben".
    var who: String {
        guard names.count > 1 else { return names.first ?? "them" }
        return names.dropLast().joined(separator: ", ") + " and " + names[names.count - 1]
    }

    func label(_ category: String) -> String { "\(category), split with \(who)" }

    var note: String {
        if body["mode"] as? String == "unknown" {
            // SPLIT-C decision 7 (SPLIT-20): Not sure yet, held for the card.
            return "Not sure yet · each payback from \(who) comes off"
        }
        return "Your share \(Format.amount(mine)) · \(who) \(names.count == 1 ? "owes" : "owe") you \(Format.amount(owed))"
    }

    /// The answer Yes sends: the split and the category it counts toward.
    func answer(_ id: String, category: String) -> ReviewAnswer {
        .split(id, body.merging(["category": category, "settle": true]) { _, new in new }, label: label(category))
    }
}

/// T-96 for a question: fetches the transaction, then shows the page a
/// transaction always opens on.
@MainActor
struct GuessPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let actions: GuessActions
    let categories: [CategoryList.Category]
    @State private var full: Transaction?
    @State private var error: String?

    var body: some View {
        Group {
            if let full = full {
                NavigationStack {
                    TransactionDetailView(transaction: full, categories: categories, guessing: actions)
                }
            } else {
                LoadState(error: error) { Task { await load() } }
                    .frame(maxWidth: .infinity, maxHeight: .infinity)
                    .nacreScreen()
                    // A full page can't be swiped away, so a failed load needs a way out.
                    .overlay(alignment: .topLeading) {
                        Button { dismiss() } label: {
                            Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                                .foregroundColor(Pearl.ink)
                                .frame(width: 44, height: 44)
                        }
                        .buttonStyle(.plain)
                        .padding(.leading, 8)
                        .accessibilityLabel("Back")
                    }
            }
        }
        .task { await load() }
    }

    private func load() async {
        do {
            full = try await app.api.get("api/transactions/\(actions.ask.t.id)")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// Which piggy bank paid, and how much. What's left stays her spending.
@MainActor
struct PiggyPaySheet: View {
    struct Bank: Decodable, Identifiable {
        let id: Int
        let name: String
        /// Real money in it now: what was paid in, less what it paid out.
        let held: Double?
    }

    let t: Transaction
    let api: APIClient
    let onDone: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @State private var banks: [Bank]?
    @State private var chosen: Int?
    @State private var amount = ""
    @State private var error: String?
    @State private var busy = false

    private var charge: Double { abs(t.amount) }
    private var typed: Double? { Double(amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")) }

    var body: some View {
        VStack(spacing: 0) {
            CFSheetTitle(title: "Pay from a piggy bank") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: t.merchant, amount: Format.amount(charge), tone: Pearl.ink, sub: nil)
                    if let banks = banks {
                        if banks.isEmpty {
                            Text("You don’t have a piggy bank yet.").font(Nacre.body).foregroundColor(Pearl.muted)
                        } else {
                            APCard {
                                ForEach(Array(banks.enumerated()), id: \.element.id) { index, bank in
                                    if index > 0 { APSeparator(afterFace: false) }
                                    Button { chosen = bank.id } label: {
                                        HStack {
                                            VStack(alignment: .leading, spacing: 2) {
                                                Text(bank.name).font(Nacre.body).foregroundColor(Pearl.ink)
                                                if let held = bank.held {
                                                    Text(held > 0 ? "Has \(Format.whole(held))" : "Empty").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                                }
                                            }
                                            Spacer()
                                            if chosen == bank.id {
                                                Image(systemName: "checkmark").foregroundColor(Pearl.action)
                                            }
                                        }
                                        .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                            TextField("Amount", text: $amount)
                                .keyboardType(.decimalPad)
                                .font(Nacre.body).padding(.horizontal, 16).frame(minHeight: 64)
                                .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Pearl.card))
                                .accessibilityLabel("How much the piggy bank paid")
                            if let typed = typed, typed > 0, typed <= charge {
                                Text(typed == charge ? "All of it comes out of the piggy bank."
                                     : "\(Format.amount(charge - typed)) stays yours. \(Format.amount(typed)) comes out of the piggy bank.")
                                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
                            }
                        }
                    } else {
                        LoadState(error: error) { Task { await load() } }
                    }
                    if let error = error, banks != nil {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                    if t.bankId != nil {
                        Button("Put it back in the month") { Task { await takeBack() } }
                            .buttonStyle(NacreTextButtonStyle(tone: Pearl.link))
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            Button("Save") { Task { await save() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(busy || chosen == nil || (typed ?? 0) <= 0 || (typed ?? 0) > charge + 0.005)
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .cfSheet()
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .task { await load() }
    }

    private func load() async {
        struct List: Decodable { let banks: [Lenient<Bank>] }
        do {
            let list: List = try await api.get("api/piggy")
            banks = list.banks.compactMap { $0.value }
            chosen = t.bankId ?? (banks?.count == 1 ? banks?.first?.id : nil)
            if amount.isEmpty { amount = String(format: "%.2f", charge) }
            error = nil
        } catch {
            self.error = "Couldn’t load your piggy banks."
        }
    }

    private func save() async {
        guard let chosen = chosen, let typed = typed else { return }
        busy = true
        defer { busy = false }
        do {
            struct Paid: Decodable { let covered: Double?; let short: Double? }
            let paid: Paid = try await api.post("api/piggy/\(chosen)/allocate", ["txn_id": t.id, "amount": typed])
            let name = banks?.first { $0.id == chosen }?.name ?? "the piggy bank"
            let covered = paid.covered ?? typed
            if let short = paid.short, short > 0.005 {
                // Decision 1: the chest paid it all; what it didn't hold comes off the Anchor.
                onDone("\(name) paid for it. It was \(Format.amount(short)) short, so that comes off your Anchor until you move \(Format.amount(short)) from savings.")
            } else if covered < typed - 0.005 {
                onDone("\(name) only had \(Format.amount(covered)), so it paid that. The rest stays in your month.")
            } else {
                onDone(covered >= charge ? "\(name) paid for it." : "\(name) paid \(Format.amount(covered)). \(Format.amount(charge - covered)) is yours.")
            }
        } catch {
            self.error = "That didn’t save. Try again."
        }
    }

    private func takeBack() async {
        do {
            let _: OK = try await api.delete("api/piggy/allocations/\(t.id)")
            onDone("Back in the month.")
        } catch {
            self.error = "That didn’t save. Try again."
        }
    }
}

/// One transaction (THL-122, T-03): who and how much, what it counts as,
/// Pearl's guess to confirm (T-96), the payback or refund it's linked to
/// (T-39, T-41), one-off (T-42), a note and tags; a transfer between her
/// accounts shows both ends (T-05).
@MainActor
struct TransactionDetailView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let transaction: Transaction
    let categories: [CategoryList.Category]
    var siblings: [Transaction] = []
    /// T-96 opened from Needs a look or Quick sort; nil from the list.
    var guessing: GuessActions? = nil
    /// AP-OwedPerson (REDESIGN-04): what she picked on a person's options
    /// from Owed to you, run here once the purchase has loaded.
    var startChoice: StartChoice? = nil
    @State private var ranStartChoice = false

    /// The full detail once it's come back; the list's row until then.
    @State private var detail: Transaction?
    /// The screen this page was pushed from (`app.changed(by:)`): its edits
    /// are that screen's own (perf rehaul, 2026-11-19).
    @Environment(\.screenKey) private var screenKey
    /// What the last write changed, applied once the page has reloaded.
    @State private var lastChanged: Changed?
    /// S-04ue (G2-BCard2): the full detail didn't come back.
    @State private var loadFailed = false
    /// What was this?: the page sorting happens on, shared with Needs a look and Quick sort.
    @State private var sorting: Ask?
    @State private var editingNote = false
    @State private var editingTags = false
    /// A money-in question opened from here (THL-198): its kind, how often
    /// it pays, or What was this?.
    @State private var asking: Asking?
    /// PP-01 for a payback the server couldn't place on the split.
    @State private var whoPaid: WhoPaidAsk?
    /// PQ-03p (Payback question): Pearl's guess on an unsorted deposit, in words.
    @State private var paybackAsk: PaybackQuestion?
    /// Whether `paybackAsk` has been settled for this page; until then the
    /// row's own question shows, so the card never changes shape as the
    /// page loads (2026-11-20).
    @State private var paybackChecked = false
    /// The payback question as the page shows it: the settled one, or the
    /// row's until then. Every reader uses this, so the Counts pill and
    /// "Name them" are right on the first frame too, not only the card.
    private var shownPaybackAsk: PaybackQuestion? {
        paybackAsk ?? (paybackChecked ? nil : t.paybackQuestion)
    }

    struct Asking: Identifiable {
        let step: AnswerSheet.Step
        var id: AnswerSheet.Step { step }
    }
    @State private var oneOff: Bool?
    /// Splits and parts (THL-291).
    @State private var splitting = false
    /// SPLIT-C: S-45a Settle up, its Type amounts, S-46a That's everything.
    @State private var settlingUp = false
    /// TEST-18 (S-47): What was your share?
    @State private var settingShare = false
    /// S-47f: whose S-40u to open once the sheet over the page has gone.
    @State private var optionsFor: String?
    @State private var typingSettle = false
    @State private var closingSplit = false
    /// JOINT-B: S-41j Remove the split?
    @State private var removingSplit = false
    @State private var marking: Transaction.Splitting.Person?
    @State private var lettingGo: Transaction.Splitting.Person?
    /// REFRESH-02: S-07r Remind, S-03re Change their share, S-03fr Remove.
    @State private var reminding: Transaction.Splitting.Person?
    @State private var changingShare: Transaction.Splitting.Person?
    /// S-48e (TEST-18b): S-48a / S-48b again for someone, after settling.
    @State private var changingAnswer: Transaction.Splitting.Person?
    @State private var removingPerson: Transaction.Splitting.Person?
    /// S-44a–i: the split flow's ink toast, with Undo (or Try again, S-44h).
    @State private var splitToast: PearlToast.Model?
    @State private var seeingOwed = false
    @State private var parting: PartsDeposit?
    /// The Recurring row's sheet (2026-11-24): Not this one, Stop the rule.
    @State private var recurringMenu = false
    /// S-35c "Who sent this?" (SPLIT-22b): the payback it asks about.
    @State private var crediting: Crediting?
    /// S-11x (SPLIT-23 (1)): the deposit's question card opened on the
    /// extra on a paid-back purchase.
    @State private var partsExtra: Review.Item.Extra?

    struct Crediting: Identifiable { let id: String }
    /// S-10e: the parts sheet opened from S-33's Edit, with the parts filled in.
    @State private var editingParts = false
    /// PB-41 Change what it paid back: PB-30 again with today's ticks.
    @State private var repicking = false
    /// PB-42 from the deposit (PB-41), then its Unlink? (S-34kr).
    @State private var depositLink: DepositLink?
    @State private var depositUnlink: DepositLink?
    /// PB-42 from the purchase: the step S-40c's How much / Which purchase opens on.
    @State private var linkStart: PaybackLinkSheet.Step = .options
    /// PP-02 (Paybacks 2): PB-42 again for who paid it now, with the toast.
    @State private var linkNotice: PearlToast.Model?
    /// TP-01 (Paybacks 2): "Mom paid me back" on the money in.
    @State private var jointStart: JointPaybackStart?
    @State private var unlinking = false
    /// S-34 for a payback linked to one purchase, from either side.
    @State private var unlinkingPayback: PaybackLink?

    struct PaybackLink: Identifiable {
        let charge: String
        let inflow: String
        /// "Dad", the e-Transfer's sender.
        let who: String
        let name: String
        let amount: Double
        let date: String
        var id: String { charge + inflow }
    }
    @State private var recent: [String] = []
    /// A transaction added by hand can be taken out again.
    @State private var deleting = false
    /// T-80: renaming the merchant; T-76: whose a joint charge was.
    @State private var renaming = false
    @State private var whose = false
    @State private var busy = false
    /// From the list: whether a rule could match this name, and whether she
    /// has sorted the merchant different ways (T-97).
    /// The page's own answer (GET …/cases); until it comes, the list's (2026-11-08),
    /// so the Always switch is there as the page opens.
    @State private var cases: Cases?
    private var learnable: Bool { cases?.learnable ?? transaction.rule?.learnable ?? false }
    private var varies: Bool { cases?.mixed ?? transaction.rule?.mixed ?? false }
    /// Pay from a piggy bank.
    @State private var payingFromBank = false
    /// The income Always switch, as she just set it, until the page reloads.
    @State private var incomeAlwaysOn: Bool?
    /// She picked Pearl's own guess on the category page (Quick sort holds it for the card).
    @State private var pickedGuess = false
    /// A category picked for this guess, waiting for Yes.
    @State private var chosenCategory: String?
    /// The latest edits held for the Quick sort card.
    @State private var held: CardDraft?
    /// A rule already sorts this merchant.
    private var hasRule: Bool { cases?.hasRule ?? transaction.rule?.hasRule ?? false }
    /// The bill this merchant is on, and the sheet that adds it.
    @State private var billKey: String?
    @State private var addingBill = false
    /// The Always switch, once she's touched it.
    @State private var newOnes: Bool?
    /// T-38b / T-40b: "Dining out · Undo" after a guess is confirmed.
    @State private var toast: (title: String, undo: (() -> Void)?)?
    /// PB-22 to PB-24: where Find what paid it back is.
    @State private var paidBackStep: PaidBackStep?
    /// T-41b: Unlink? before a refund goes back to Needs a look.
    @State private var unlinkingRefund = false
    /// SPLIT-25: S-05o for a PAID BACK or REFUNDED BY row on a purchase that
    /// isn't split (the split card has its own), then S-34s / S-34k.
    @State private var linkOptions: Transaction.LinkInfo?
    @State private var afterOptions: (() -> Void)?
    @State private var unlinkingLink: Transaction.LinkInfo?
    /// S-05o's View the e-Transfer / deposit / refund.
    @State private var viewing: Transaction?
    /// TF-01c: "This isn't a transfer?" asks first.
    @State private var unpairing = false
    /// Link transfers (2026-11-22): the sheet that picks the other legs.
    @State private var linking = false
    /// The ⋯ beside a leg of the Moved card (product owner, 2026-11-22):
    /// which leg, and the transactions behind it.
    struct LegMenu: Identifiable { let id: String; let account: String; let ids: [String] }
    @State private var legMenu: LegMenu?
    /// TF-01c: the other end, asked What was this? once this one is answered.
    @State private var otherSide: String?
    @State private var error: String?
    /// S-04r v2s: the hero has scrolled under the bar.
    @State private var heroGone = false

    private var t: Transaction { detail ?? transaction }

    // 2026-11-16 (stack check, TransactionDetailView.body.getter at 40,960
    // bytes on main): the page's sheets are put on in stages, each in its own
    // body (OwnBody), so no one Debug frame holds the whole modifier chain.
    // Same views, same modifiers, same order; only where they're built.
    var body: some View {
        OwnBody { linkSheets }
        .sheet(item: $unlinkingPayback) { link in paybackUnlinkSheet(link) }
        .sheet(item: $unlinkingLink) { link in
            // S-34s / S-34k (SPLIT-25), then S-05t's toast with Undo.
            UnlinkLinkSheet(link: link, charge: t.id, api: app.api, onCancel: { unlinkingLink = nil }) { title, undo in
                unlinkingLink = nil
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                Task {
                    await load()
                    app.changed()
                    // S-44a; its Undo links it back (S-44g "Linked again").
                    showSplit(title, undo: undo.map { u in { try await postUndo(u); return "Linked again" } })
                }
            }
        }
        .sheet(item: $linkOptions, onDismiss: {
            // The choice runs once S-05o has gone, so its next sheet can open.
            linkStart = .options
            linkNotice = nil
            let next = afterOptions
            afterOptions = nil
            next?()
        }) { link in
            if Self.personPayback(link) {
                // PB-42 (Paybacks & undo, 1395:5050): S-05or grows How much, Who
                // paid and Which purchase; S-40c's rows open it on their step.
                PaybackLinkSheet(link: link, charge: t.id, merchant: t.merchant, date: t.date, owes: owesOn(link),
                                 start: linkStart, api: app.api,
                                 onClose: { linkOptions = nil },
                                 onView: {
                                     afterOptions = { if let id = link.view?.id { Task { await open(id) } } }
                                     linkOptions = nil
                                 },
                                 onUnlink: {
                                     afterOptions = { unlinkingLink = link }
                                     linkOptions = nil
                                 },
                                 onDone: { title, undo in
                                     linkOptions = nil
                                     linkChanged(title, undo)
                                 },
                                 people: t.splitting?.people ?? [],
                                 onPerson: { title, undo, name in
                                     // PP-02: back on PB-42 for who paid it now.
                                     afterOptions = { Task { await reopenLink(link, for: name, title, undo) } }
                                     linkOptions = nil
                                 },
                                 notice: linkNotice)
            } else {
                // S-05or (REFRESH-02): View… opens it here in Pearl; Unlink… → S-34kr.
                PaybackOptionsSheet(link: link, overline: link.kind == "refund" ? "REFUNDED BY" : "PAID BACK",
                                    onClose: { linkOptions = nil },
                                    onView: {
                                        afterOptions = { if let id = link.view?.id { Task { await open(id) } } }
                                        linkOptions = nil
                                    },
                                    onUnlink: {
                                        afterOptions = { unlinkingLink = link }
                                        linkOptions = nil
                                    })
            }
        }
        .sheet(item: $depositLink, onDismiss: {
            let next = afterOptions
            afterOptions = nil
            next?()
        }) { d in
            // PB-42 from the deposit (PB-41): she's on the e-Transfer, so no View.
            PaybackLinkSheet(link: d.link, charge: d.charge, merchant: d.merchant, date: d.date, owes: d.owes,
                             fromDeposit: true, api: app.api,
                             onClose: { depositLink = nil },
                             onView: {},
                             onUnlink: {
                                 afterOptions = { depositUnlink = d }
                                 depositLink = nil
                             },
                             onDone: { title, undo in
                                 depositLink = nil
                                 linkChanged(title, undo)
                             },
                             people: d.people)
        }
        .sheet(item: $depositUnlink) { d in
            // S-34kr for one purchase this deposit paid back (PB-42 › Unlink…).
            UnlinkLinkSheet(link: d.link, charge: d.charge, api: app.api, onCancel: { depositUnlink = nil }) { title, undo in
                depositUnlink = nil
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                Task {
                    await settled(title, undo: undo.map { u in { try await postUndo(u); return "Linked again" } })
                }
            }
        }
        .navigationDestination(isPresented: Binding(get: { viewing != nil }, set: { if !$0 { viewing = nil } })) {
            if let viewing = viewing {
                TransactionDetailView(transaction: viewing, categories: categories)
            }
        }
        .sheet(isPresented: $renaming) {
            RenameSheet(title: "Rename merchant", label: "Call it", initial: t.merchant,
                        hint: "Bank: \(t.bankMerchant ?? t.merchant)", other: "Use the bank’s name",
                        onSave: { name in
                            renaming = false
                            Task { await rename(to: name) }
                        }, onOther: {
                            renaming = false
                            Task { await rename(to: "") }
                        })
        }
        .sheet(isPresented: $whose) {
            // G2b-Whose T-76: the tiles that answer at once (JointSplitViews).
            WhoseTilesSheet(t: t, api: app.api) { said, undo in
                whose = false
                // "Yours." (POLISH-01): a toast with Undo, not a line under the page.
                Task { await run { withAnimation { toast = (said, undoing(undo)) }; return nil } }
            }
        }
        .navigationDestination(isPresented: $seeingOwed) { OwedView() }
        .sheet(isPresented: $editingNote) {
            NoteSheet(note: t.myNote, name: t.merchant,
                      line: (t.inflow ? "+" : "\u{2212}") + Format.amount(t.amount) + " · " + Format.weekdayDay(t.date)) { note in
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

    /// The page, its bar and its title: what `body` used to start with.
    private var page: some View {
        ScrollView {
            // 2026-11-14 (stack overflow on the product owner's iPhone): each
            // section is built in its own body (OwnBody), so no one body's
            // stack frame holds the whole page, and Transaction is small (Boxed).
            VStack(alignment: .leading, spacing: 8) {
                OwnBody { header }.padding(.bottom, 10)
                    // S-04r v2s (TEST-09): once the hero scrolls under the bar,
                    // the bar takes the merchant's name.
                    .background(GeometryReader { g in
                        Color.clear
                            .onAppear { heroGone = g.frame(in: .global).maxY < 120 }
                            .onChange(of: g.frame(in: .global).maxY) { heroGone = $0 < 120 }
                    })
                if let transfer = t.transfer, guessing == nil {
                    // TF-01 (1389:24632 / 1389:24833): How it counts, Moved,
                    // Options, Details.
                    OwnBody { transferLegs(transfer) }
                    OwnBody { details }
                } else {
                    OwnBody { whatItIs }
                    OwnBody { linked }
                    OwnBody { jointRow }
                    OwnBody { splitPeople }
                    OwnBody { depositParts }
                    OwnBody { options }
                    OwnBody { details }
                }
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                        .padding(.horizontal, 16).padding(.top, 8)
                }
                OwnBody { footerAction }
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .safeAreaInset(edge: .bottom) {
            VStack(spacing: 0) {
                guessActions
                // S-01jr (G2b-Purchase) and TP-01 (G2b-JointIn): the page's one Primary.
                OwnBody { pagePrimary }
            }
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
        .modifier(GuessHidesTabBar(on: guessFromList))
        // S-04r v2s (TEST-09, TEST-26): a real inline bar with the merchant's
        // name once the hero has gone. The app's bars are see-through
        // (PearlApp), so the page draws S-04r v2s's --surface-page bar itself
        // then, behind Back, the title and the clock.
        .toolbarBackground(Pearl.scrolledBar, for: .navigationBar)
        .toolbarBackground(heroGone ? .visible : .hidden, for: .navigationBar)
        .navigationBarHidden(false)
        .navigationTitle(heroGone ? t.merchant : "")
        .navigationBarTitleDisplayMode(.inline)
        .task {
            await load()
            runStartChoice()
        }
        .onAppear {
            // Back on a card's page: what she'd already changed is still there.
            if let draft = guessing?.draft, chosenCategory == nil, newOnes == nil {
                // A held split's label isn't a category (T-98s).
                chosenCategory = draft.split != nil ? draft.category : draft.label
                newOnes = draft.always
            }
        }
    }

    /// What was this? and the money-in questions.
    private var sortSheets: some View {
        OwnBody { page }
        .sheet(item: $sorting, onDismiss: {
            // Closed without an answer: TF-01c doesn't go on to the other end.
            otherSide = nil
            Task { await load() }
        }) { ask in
            // The stored category stays hers unless she changes it; a question is answered in place.
            if let guessing = guessing {
                // T-96: the guess is wrong, so the answer is the question's. Yes is already on the page.
                AnswerSheet(ask: ask, categories: categories, accounts: guessing.accounts, names: guessing.names,
                            // TP-02 (Paybacks 2): the money-in end asks the money-in answers.
                            api: app.api, start: ask.kind == .transfer ? (ask.t.inflow ? .into : .out) : nil,
                            pageAlways: offersNewOnes && newOnesOn, pageAmount: Format.money(t),
                            pageCategory: chosenCategory,
                            onCategory: { name, remember in
                                guard guessing.onDraft == nil else { choose(name); return }
                                // Needs a look: picking is the answer (2026-11-08); picking
                                // Pearl's guess is the Yes.
                                sorting = nil
                                if name == guessing.label { guessing.onYes(remember && offersNewOnes) }
                                else { answer(with: name, always: remember && offersNewOnes) }
                            }, fromPage: true, holds: guessing.onDraft != nil) { answer in
                    sorting = nil
                    if guessing.onDraft != nil, let label = answer.heldLabel {
                        // Not saved yet: the card agrees to it.
                        chosenCategory = label
                        holdForCard {
                            $0.answer = answer
                            $0.category = nil
                            $0.label = label
                            // Another answer instead: a held split goes (SPLIT-06).
                            $0.split = nil
                        }
                    } else {
                        guessing.onAnswer(answer)
                    }
                }
            } else {
                // TF-01c's other end is its own transaction, not this page's.
                let here = ask.t.id == t.id
                AnswerSheet(ask: ask, categories: categories, accounts: [], names: recent, api: app.api,
                            pageAlways: here ? offersNewOnes && newOnesOn : nil, pageAmount: here ? Format.money(t) : nil,
                            pageCategory: here ? chosenCategory : nil,
                            onCategory: ask.kind == .category && !t.inflow ? { name, remember in
                                sorting = nil
                                // Pearl's guess, picked: that's her yes.
                                if guessName != nil, name == t.label, !remember || !canRule {
                                    Task { await confirm(said: varies && canRule ? "\(t.merchant) varies, so no rule" : nil) }
                                    return
                                }
                                if guessName != nil, name == t.label {
                                    Task { await always() }
                                    return
                                }
                                Task {
                                    if name != (t.category ?? t.label) || remember {
                                        await change(to: name, remember: remember)
                                    }
                                }
                            } : nil,
                            confirmsGuess: false, fromPage: true) { answer in
                    sorting = nil
                    // TF-01c: then what the other end was.
                    let other = otherSide
                    otherSide = nil
                    Task {
                        await answered(answer)
                        if let other = other { await askOtherSide(other) }
                    }
                }
            }
        }
        .sheet(item: $asking) { a in
            AnswerSheet(ask: a.step == .joint ? jointAsk : moneyIn, categories: categories, accounts: [],
                        names: [], api: app.api, start: a.step,
                        current: a.step == .joint ? jointChoice
                            : a.step == .kinds ? t.incomeType : t.regularPay?.cadence,
                        fromPage: a.step == .into) { answer in
                asking = nil
                Task { await answered(answer) }
            }
        }
        .sheet(item: $whoPaid) { w in
            WhoPaidAskSheet(ask: w, api: app.api, onPick: { answer in
                whoPaid = nil
                Task { await answered(answer) }
            }, onClose: { whoPaid = nil })
        }
    }

    /// Split, your share, settle up, That's everything, Remove the split?
    private var splitSheets: some View {
        OwnBody { sortSheets }
        .sheet(isPresented: $recurringMenu) { recurringSheet }
        .sheet(item: $legMenu) { m in
            // A leg's ⋯ (2026-11-22): Unlink from transfer, for that leg.
            LegMenuSheet(account: m.account, onUnlink: { legMenu = nil; Task { await unpairLegs(m.ids) } },
                         onClose: { legMenu = nil })
        }
        .sheet(isPresented: $linking) {
            // Link transfers (product owner, 2026-11-22): the other legs of
            // one move, ticked; Link (or Unlink) saves with one Undo.
            LinkTransfersSheet(t: t, api: app.api) { reply in
                linking = false
                lastChanged = reply.changed
                Task {
                    await run { nil }
                    app.say(reply.title ?? "Linked.", undo: reply.undo.map { payload in {
                        guard let body = payload.any as? [String: Any] else { return }
                        let _: OK = try await app.api.post("api/transactions/undo", body)
                    } })
                }
            }
        }
        .sheet(isPresented: $splitting) {
            // T-98s (SPLIT-06): from a Quick sort card's page the split is
            // held for the card, like every other edit here; Yes saves it.
            // TEST-42 (G2-Amounts S-03e): Edit split opens on Edit split, its
            // people already there; Add someone new and a swipe change them.
            SplitSheet(t: t, api: app.api, recent: recent, with: t.splitting?.people.map(\.name),
                       onHold: guessing?.onDraft == nil ? nil : { body, _, mine in holdSplit(body, mine: mine) },
                       onSaved: { done in
                splitting = false
                Task { await run { done } }
            }, onRemoved: { title, undo in
                // SPLIT-16: "Priya removed · Undo" puts the link back.
                splitting = false
                Task {
                    await run { nil }
                    withAnimation { toast = (title, undoing(undo)) }
                }
            }, onRemoveSplit: t.joint.isEmpty ? nil : {
                // S-41j: from Edit split.
                splitting = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { removingSplit = true }
            })
        }
        .sheet(isPresented: $settingShare) {
            if let split = t.splitting {
                // S-47a–e → S-04u7: a set split, "Alex owes you $28.00" with
                // Undo back to Not sure yet.
                YourShareSheet(t: t, split: split, api: app.api, onClose: { settingShare = false },
                               onPersonOptions: { name in
                                   settingShare = false
                                   DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { optionsFor = name }
                               }) { title, undo in
                    settingShare = false
                    Task {
                        await settled(title, undo: undo.map { u in { try await postUndo(u); return "Not sure yet again" } })
                    }
                }
            }
        }
        .sheet(isPresented: $settlingUp) {
            if let split = t.splitting {
                // S-45a / S-45b → S-45g.
                SettleUpSheet(t: t, split: split, onClose: { settlingUp = false }, onType: {
                    settlingUp = false
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { typingSettle = true }
                }, run: {
                    let (title, undo) = try await settleWithWhatEachPaid(split)
                    settlingUp = false
                    await settled(title, undo: undo)
                }, onLeftTo: { last, left in
                    // S-45a2 (TEST-18): payers at what they paid, the last one the rest.
                    var people: [[String: Any]] = split.people.filter { $0.paid >= 0.005 }
                        .map { ["name": $0.name, "amount": $0.paid] }
                    people.append(["name": last.name, "amount": left])
                    struct Reply: Decodable { let undo: JSONValue? }
                    do {
                        let reply: Reply = try await app.api.put("api/transactions/\(t.id)/split",
                                                                 ["mode": "amount", "include_me": false, "watch": true,
                                                                  "people": people])
                        settlingUp = false
                        await settled("\(last.name) owes you \(Format.amount(left))",
                                  undo: reply.undo.map { u in { try await postUndo(u); return "Not sure yet again" } })
                    } catch let e as APIError {
                        if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
                        throw e
                    }
                })
            }
        }
        .sheet(isPresented: $typingSettle) {
            // S-45c–e → S-45f. Opens on How to split with the split's
            // people: who it was with is already said (TEST-02).
            SplitSheet(t: t, api: app.api, recent: recent, with: t.splitting?.people.map(\.name),
                       onSaved: { done in
                typingSettle = false
                Task { await run { done } }
            }, settling: true, onSettled: { title, undo in
                typingSettle = false
                Task {
                    await run { nil }
                    showSplit(title, undo: undo.map { u in { try await postUndo(u); return "Not sure yet again" } })
                }
            }, onPersonOptions: { name in
                // S-47f: Options on the lock toast opens that person's S-40u.
                typingSettle = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) { optionsFor = name }
            })
        }
        .sheet(isPresented: $closingSplit) {
            if let split = t.splitting {
                // S-46a → S-46b, whose Undo puts it back (S-46d).
                ThatsEverythingSheet(t: t, split: split, onClose: { closingSplit = false }) {
                    struct Reply: Decodable { let toast: String?; let undo: JSONValue? }
                    let r: Reply = try await app.api.post("api/transactions/\(t.id)/split/close")
                    closingSplit = false
                    UINotificationFeedbackGenerator().notificationOccurred(.success)
                    await settled(r.toast ?? "Closed", undo: r.undo.map { u in { try await postUndo(u); return "Open again" } })
                }
            }
        }
        .sheet(isPresented: $removingSplit) {
            if let split = t.splitting {
                // S-41j → S-41j1; S-41j2 on the sheet if it fails.
                RemoveSplitSheet(t: t, split: split, onClose: { removingSplit = false }) {
                    struct Reply: Decodable { let toast: String?; let undo: JSONValue? }
                    do {
                        let r: Reply = try await app.api.delete("api/transactions/\(t.id)/split")
                        removingSplit = false
                        await settled(r.toast ?? "Split removed", undo: r.undo.map { u in { try await postUndo(u); return nil } })
                    } catch let e as APIError {
                        if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
                        throw e
                    }
                }
            }
        }
    }

    /// One person in a split: Mark paid back, Let go, Remind, answer again,
    /// change their share, remove them.
    private var personSheets: some View {
        OwnBody { splitSheets }
        .sheet(item: $marking) { person in
            MarkPaidSheet(t: t, person: person, api: app.api, onUndoable: { title, undo in
                // SPLIT-19 (S-11c): Undo takes back the whole payment and its extra.
                marking = nil
                Task {
                    await run { nil }
                    showSplit(title, undo: undo.map { u in { try await postUndo(u); return nil } })
                }
            }, onLinked: { title, undos, changed in
                // S-44b: "Priya paid back $30.00 · Undo" takes back every link it made.
                marking = nil
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                // The toast at once (perf rehaul); the page reloads under it
                // and the rest of the app takes the write's `changed`.
                showSplit(title, undo: undos.isEmpty ? nil : {
                    for u in undos.reversed() { try await postUndo(u) }
                    return nil
                })
                lastChanged = changed
                Task { await run { nil } }
            }) { done in
                marking = nil
                Task { await run { done } }
            }
        }
        .sheet(item: $lettingGo) { person in
            // S-08r → S-44c, whose Undo puts it back.
            LetGoSheet(t: t, person: person, onClose: { lettingGo = nil }) {
                let said = try await letGo(person)
                lettingGo = nil
                UINotificationFeedbackGenerator().notificationOccurred(.success)
                await settled(said, undo: { try await undoLetGo(person) })
            }
        }
        .sheet(item: $reminding) { person in
            // S-07r → S-44f; Undo empties the clipboard again. No haptic on Remind.
            RemindSheet(t: t, p: person, onClose: { reminding = nil }) {
                reminding = nil
                showSplit("Copied", undo: {
                    UIPasteboard.general.string = ""
                    return nil
                })
            }
        }
        .sheet(item: $changingAnswer) { p in
            // S-48e: the same question, answered again; the server swaps a
            // gift or "you owe" and spreads a changed share.
            let others = (t.splitting?.people ?? []).map(\.name).filter { $0 != p.name }
            MismatchSheet(name: p.name, paid: p.paid + (p.gift ?? 0), share: p.amount, even: false, step: 1, of: 1,
                          others: ((t.splitting?.withMe ?? true) ? ["you"] : []) + others,
                          onBack: { changingAnswer = nil },
                          overline: "\(t.merchant) · \(p.name)") { answer in
                changingAnswer = nil
                Task { await answerAgain(p, answer) }
            }
        }
        .sheet(item: $changingShare) { person in
            // S-03re: How to split on Amounts, their field focused → S-44i.
            SplitSheet(t: t, api: app.api, recent: recent, onSaved: { done in
                changingShare = nil
                Task { await run { done } }
            }, focus: person.name, onUpdated: { title, undo in
                changingShare = nil
                Task {
                    await run { nil }
                    showSplit(title, undo: undo.map { u in { try await postUndo(u); return nil } })
                }
            })
        }
        .sheet(item: $removingPerson) { person in
            // S-03fr / S-03fr2 from S-40: saves at once, with loading and error.
            RemovePersonSheet(p: person, merchant: t.merchant,
                              countsAgain: t.splitting.flatMap { $0.unsure ? ($0.still ?? $0.you) + person.paid : nil },
                              onClose: { removingPerson = nil }) {
                let (title, undo) = try await removeFromSplit(person)
                removingPerson = nil
                await settled(title, undo: undo)
            }
            .onlyPerson(t.splitting?.people.count == 1)  // G2-BRemove S-03fu1 (splits engBOT)
        }
    }

    /// Parts, Who sent this?, Unlink, Find what paid it back, the toasts,
    /// Add to bills and Pay from a piggy bank.
    private var linkSheets: some View {
        OwnBody { personSheets }
        .sheet(item: $parting, onDismiss: { editingParts = false; repicking = false; partsExtra = nil }) { deposit in
            // S-33's Edit opens S-10e with the parts it has (SPLIT-03); PB-41's
            // Change what it paid back opens PB-30 with today's ticks.
            PartsSheet(deposit: deposit, api: app.api, editing: editingParts ? t.parts : [],
                       whole: partsExtra, paidBack: repicking, repick: repicking) { reply in
                parting = nil
                editingParts = false
                repicking = false
                Task {
                    await run {
                        // S-12d: "Costco split and $600 sorted · Undo" puts it all back.
                        withAnimation { toast = (reply.title ?? "Sorted.", undoing(reply.undo)) }
                        return nil
                    }
                }
            }
        }
        // TP-01 › TP-03 (Paybacks 2): PB-30 with the joint account's other
        // owner picked; TP-04's ink toast with Undo, which makes it a transfer again.
        .modifier(JointPaybackFlow(start: $jointStart, api: app.api) { reply in
            Task {
                await run {
                    withAnimation { toast = (reply.title ?? "Sorted.", undoing(reply.undo)) }
                    return nil
                }
            }
        })
        .sheet(item: $crediting) { c in
            // S-35c from S-05u, or the deposit's Needs a look question card (S-21u; SPLIT-23 (3): no other entry on its page).
            WhoSentSheet(id: c.id, api: app.api) { reply in
                crediting = nil
                Task {
                    await run {
                        withAnimation { toast = (reply.title ?? "Sorted.", undoing(reply.undo)) }
                        return nil
                    }
                }
            }
        }
        .sheet(isPresented: $unlinking) { unlinkSheet }
        // PB-20 to PB-24 (Paid back, 2026-11-15): Find what paid it back,
        // from her own row's •••; the toast and Undo land here.
        .modifier(PaidBackFromPurchase(step: $paidBackStep, purchase: t, api: app.api, done: { title, undo in
            Task { await run { withAnimation { toast = (title, undoing(undo)) }; return nil } }
        }, failed: { text in
            withAnimation { toast = nil; splitToast = PearlToast.Model(text: text, failed: true) }
        }))
        .sheet(isPresented: $unlinkingRefund) { refundUnlinkSheet }
        .overlay(alignment: .bottom) {
            VStack(spacing: 4) {
                if let model = splitToast {
                    PearlToast(model: model) { withAnimation { if splitToast == model { splitToast = nil } } }
                } else if let toast = toast {
                    // Stays until something replaces it, so nothing moves under a finger.
                    UndoToast(text: toast.title, undo: toast.undo, stays: false) {
                        withAnimation { self.toast = nil }
                    }
                }
            }
            .padding(.bottom, 8)
        }
        .sheet(isPresented: $addingBill) {
            AddToBillsSheet(t: t, api: app.api, categories: categories, category: t.category) { said in
                addingBill = false
                Task { await run { said } }
            }
        }
        .sheet(isPresented: $payingFromBank) {
            PiggyPaySheet(t: t, api: app.api) { said in
                payingFromBank = false
                Task { await run { said } }
            }
        }
    }

    // MARK: Header

    /// A+ (AP-Transaction, G1-TxSpend, G1-TxMore, G1-TxRefund; kit `.hero`):
    /// the 56 pt ring in the bar's row beside Back, the Counts pill on the
    /// right of that row, the name in Fraunces 22, the amount in Fraunces
    /// 44, and its lines in 15 muted.
    private var header: some View {
        VStack(spacing: 0) {
            // TF-01: ⇄ in the ring for a transfer. TP-04: the payer's initials.
            CFRing(name: t.jointPayback?.person ?? t.merchant, size: 56, transfer: t.transfer != nil)
                .padding(.bottom, 8)
            if t.transfer == nil {
                // T-80: tap the name to rename the merchant.
                Button { renaming = true } label: {
                    // TP-04 (G2b-JointIn, rethought): "From Mom".
                    Text(heroName)
                        .font(Nacre.title2).foregroundColor(Pearl.ink)
                        .multilineTextAlignment(.center)
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(.isHeader)
                .accessibilityHint("Rename the merchant")
            } else {
                // TF-01 (POLISH-01): a transfer's name isn't renamed here, but
                // it's in ink, not dimmed as a disabled button (it was
                // `.disabled(t.transfer != nil)`), on up to two lines.
                Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            Text(heroAmount)
                .font(.cfBig).tracking(-0.88)
                // RC-03: a payback counts it down, 400 ms ease-out.
                .costCountDown(t.amount)
                // T-41w: money that paid a purchase back is money in, green.
                // T-41m: a refund of her share too. TF-01: a transfer in
                // money-transfer grey, with no sign.
                .foregroundColor(paidBackAnswer != nil || t.refundOf?.share == true ? Pearl.moneyIn
                                 : t.transfer != nil ? Pearl.moved : t.tone)
                .lineLimit(1).minimumScaleFactor(0.5)
                .accessibilityLabel(heroSpoken)
            if let line = costLine {
                // RC-02 (1401:86515): the split's line, then the date and her share.
                CostHeaderLines(line: line, back: t.cost?.back ?? 0, date: costDateLine)
            } else {
                // TP-04: "Joint ••1123 · Fri, Nov 14".
                Text(heroDateLine)
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
            }
            if namesSender {
                // PQ-03p (G2-APQ): "Name them" on its own line under the date.
                NameThemLink { asking = Asking(step: .sender) }
            }
            // The Counts pill under the transaction's own lines (product
            // owner, 2026-11-21), not off in the top right.
            OwnBody { countsOrName }.padding(.top, 10)
            OwnBody { heroPills }
        }
        .frame(maxWidth: .infinity)
        // The ring sits in the bar's row, 8 under the status bar, as drawn.
        .padding(.top, -36)
    }

    /// RC-02 (ROWCOST-01; replaces S-04r v2's header): what it costs her
    /// now, the server's `amount`, as on her Cash flow row. Rule A stays:
    /// nobody paid yet is the whole purchase; each payback, and work paying
    /// her share, lowers it at once (RC-03). Not sure yet keeps what it
    /// counts as so far (S-04u).
    /// T-40's joint pill and the pending pill, in their own body (stack
    /// check, 2026-11-16: the header's closure was past 24 KB).
    @ViewBuilder private var heroPills: some View {
        if !t.joint.isEmpty && t.transfer == nil {
            // T-40: "Joint with Sam · 50%"; T-75 on a charge: "yours unless you say".
            CFPill(text: !t.inflow && t.accountShare == nil && !t.jointPeople.isEmpty
                   ? "Joint with \(Format.shortList(t.jointPeople)) · yours unless you say" : jointLine,
                   symbol: "person.2")
                .padding(.top, 10)
        }
        if t.pending {
            // Pending isn't an error: no red dot (A+: red only for over and errors).
            CFPill(text: "Pending · amount may change", symbol: "clock", symbolTone: Pearl.muted)
                .padding(.top, 10)
        }
    }

    /// T-03's Counts pill: Spending, Income, Refund or Not counted. PQ-03p
    /// (G2-APQ): no pill on a deposit Pearl asks a payback about while the
    /// bank's name is all it has; "Name them" sits under the date instead
    /// and opens T-14 Who sent this?.
    @ViewBuilder private var countsOrName: some View {
        if t.transfer != nil {
            // TF-01's Counts pill (G1-TxMore): "⇄ Doesn’t count".
            CFPill(text: "Doesn’t count", symbol: "arrow.left.arrow.right", symbolTone: Pearl.muted)
        } else if namesSender {
            EmptyView()
        } else {
            // G2-BPayback (S-33 v2, T-41w, T-41m): "↑ Payback", "↑ Paid back",
            // "↑ Refund"; otherwise the Counts arrow.
            CFPill(text: countsPill.label, symbol: countsPill.up ? "arrow.up" : "arrow.down",
                   symbolTone: countsPill.tone)
        }
    }

    /// PQ-03p: the payback question's sender has no name of hers yet.
    private var namesSender: Bool {
        guard let q = shownPaybackAsk else { return false }
        return !q.named && t.asks && t.transfer == nil
    }

    /// The hero's name: TP-04 (G2b-JointIn, rethought) "From Mom" on money
    /// a joint account's other owner paid her back with; the account goes
    /// on the line under the amount. Its own small frame, out of the
    /// header's (stack check).
    @inline(never)
    private var heroName: String {
        guard let jp = t.jointPayback else { return t.merchant }
        return "From \(jp.person)"
    }

    /// TF-01's dates, TP-04's "Joint ••1123 · Fri, Nov 14", or the day.
    @inline(never)
    private var heroDateLine: String {
        if let transfer = t.transfer { return transferDates(transfer) }
        if let jp = t.jointPayback { return "\(jp.account) · \(Format.weekdayDay(t.date))" }
        return dateLine
    }

    private var heroAmount: String {
        // TF-01: a transfer has no sign; it didn't leave her.
        if t.transfer != nil { return Format.amount(t.amount) }
        return Format.money(t)
    }

    /// VoiceOver: "Moved $500.00" (TF-01); RC-02 "Costs you $110.00 now";
    /// otherwise "spent $24.80".
    private var heroSpoken: String {
        if t.transfer != nil { return "Moved \(heroAmount)" }
        if costLine != nil { return "Costs you \(Format.amount(t.amount)) now" }
        return Format.spoken(heroAmount)
    }

    /// RC-02: the server's line under the header on a split with shares;
    /// nil for Not sure yet, which keeps S-04u's date line.
    private var costLine: String? {
        guard let cost = t.cost, !cost.unsure, !t.inflow, t.transfer == nil, t.splitting != nil else { return nil }
        return cost.header
    }

    /// RC-02: "Wed, Nov 11 · your share $30.00"; TR-06's trip after it.
    private var costDateLine: String {
        let when = Format.relativeDay(t.date) == "Today" ? "Today" : Format.weekdayDay(t.date)
        let share = t.cost?.share.map { "your share \(Format.amount($0))" }
        return [when, share, t.trip?.name].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    /// The card that says what it is: Pearl's guess, its parts, a joint
    /// deposit's question, Needs a look's question, or its category.
    @ViewBuilder private var whatItIs: some View {
        if let label = guessName { guessCard(label) }
        // S-33 v2 (G2-BPayback): the parts' label says what it was; PB-41 keeps its card.
        else if !t.parts.isEmpty { if paidBackOnly { partsCard } } else if jointAsks { jointGuessCard }
        else if t.asks { askingOrPayback }
        // T-41w / T-41m (G2-BPayback): the PAID BACK / REFUND FOR card and
        // its Options say it; no category card.
        else if !sharePaidBack {
            if showsShareBar {
                // S-01jr / S-01jr2 (G2b-Purchase): whose it was, as a bar, over the category.
                JointShareBarCard(t: t) { whose = true }.padding(.top, 8)
            }
            categoryCard
        }
    }

    /// The page shows the category card (whatItIs), which carries TR-06's trip.
    private var showsCategoryCard: Bool {
        t.transfer == nil && guessName == nil && t.parts.isEmpty && !jointAsks && !t.asks && !sharePaidBack
    }

    /// S-01jr: a joint purchase not split yet, sorted: the share bar in place
    /// of Options' Whose was it?, and Split my part as the page's Primary.
    private var showsShareBar: Bool {
        jointCharge && t.splitting == nil && t.refundOf == nil && guessName == nil && !t.asks
            && t.parts.isEmpty && !jointAsks
    }

    /// S-01jr "Split my part" / S-01jr2 "Split it with friends"; TP-01
    /// "Mom paid me back" over the quiet "This isn’t a transfer".
    @ViewBuilder private var pagePrimary: some View {
        if guessName == nil {
            if let transfer = t.transfer, guessing == nil, let joint = transfer.joint, t.inflow,
               let out = transfer.otherId {
                VStack(spacing: 12) {
                    Button(joint.people.count == 1 ? "\(joint.people[0]) paid me back" : "Someone paid me back") {
                        startJointPayback(joint, out: out)
                    }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
                    .accessibilityHint("Pick what it paid for")
                    notATransferLink
                }
                .padding(.horizontal, 16).padding(.bottom, 8)
            } else if let transfer = t.transfer, guessing == nil, mineOnlyIn(transfer) {
                // TP-05 (G2b-JointIn, rethought): the one quiet link.
                notATransferLink
                    .padding(.horizontal, 16).padding(.bottom, 8)
            } else if showsShareBar && canSplitJoint && t.splitBase >= 0.005 {
                Button(t.splitsMyPart ? "Split my part" : "Split it with friends") { splitting = true }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
                    .padding(.horizontal, 16).padding(.bottom, 8)
            }
        }
    }

    /// TP-01 / TP-05: "This isn’t a transfer", quiet, asks first (TF-01c).
    private var notATransferLink: some View {
        Button { unpairing = true } label: {
            Text("This isn’t a transfer")
                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline)).foregroundColor(Pearl.link)
                .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
    }

    /// T-41w / T-41m: money in that paid back (or refunded) her own share.
    private var sharePaidBack: Bool {
        if let charge = t.refundOf { return charge.share == true }
        if let charge = t.repaysCharge, charge.person == "me" { return true }
        return false
    }

    /// "Your share of $120.00 · Nov 12" (T-41w, T-41m).
    private func shareLine(whole: Double, date: String) -> String {
        "Your share of \(Format.amount(abs(whole))) · \(Format.short(date))"
    }

    /// "Wed, Nov 11 · TD Chequing ••4417".
    private var dateLine: String {
        let when = Format.relativeDay(t.date) == "Today" ? "Today" : Format.weekdayDay(t.date)
        // S-04u: "Counts as $80.00 so far"; S-46c "Counts as $80.00"; S-04j
        // "Your share $16.68"; S-01jr "Your part $50.00".
        var lead: String? = nil
        if let s = t.splitting, !t.inflow {
            if s.unsure {
                lead = "Counts as \(Format.amount(s.still ?? s.you))" + (s.closedAt == nil ? " so far" : "")
            } else if let mine = s.mine {
                // TEST-31: S-04w "Your share $60.00 · reimbursed", S-04w2
                // "Your share $60.00 · $45.00 reimbursed"; once Sam has paid
                // too, S-04w3 "Costs you $0.00".
                lead = s.people.allSatisfy({ $0.owes < 0.005 })
                    ? "Costs you \(Format.amount(mine.stays))"
                    : "Your share \(Format.amount(mine.amount)) · "
                        // S-04m: "refunded", "$45.00 refunded" for Money back.
                        + (mine.full ? (mine.refunded ? "refunded" : "reimbursed")
                           : "\(Format.amount(mine.reimbursed)) \(mine.refunded ? "refunded" : "reimbursed")")
            } else {
                // S-04r v2: "Your share $30.00 · Wed, Nov 11"; S-04j the same.
                lead = "Your share \(Format.amount(s.you))"
            }
        } else if !t.inflow && t.splitsMyPart {
            lead = "Your part \(Format.amount(t.splitBase))"
        }
        // TR-06 (G7-TripMore): "Mon, Mar 4 · TD Visa ••9021"; the trip has its
        // own row under the category, so the hero names it only without that card.
        let trip = showsCategoryCard ? nil : t.trip?.name
        return [lead, when, t.account, trip].compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
    }

    // MARK: What it counts as

    private var categoryCard: some View {
        APCard {
            Button { changeWhatItIs() } label: {
                // T-03: the category's icon and name; income says what kind
                // (T-37, "Salary"). The pill above says what it counts as.
                // T-03r (1074:698): "Change" by the chevron.
                if let answer = paidBackAnswer {
                    // T-41w: "Work paying me back", no second line.
                    categoryRow(symbol: "", title: answer.label, sub: nil, systemImage: answer.symbol)
                } else {
                    categoryRow(symbol: isIncome ? "Income" : (t.category ?? t.label),
                                title: isIncome ? Self.kindName(t.incomeType) : t.label, sub: countsLine,
                                change: !isIncome && !t.inflow)
                }
            }
            .buttonStyle(.plain)
            .disabled(busy)
            .accessibilityHint(isIncome || paidBackAnswer != nil ? "Changes what it was" : "Changes the category")
            if paidBackAnswer == nil, t.split, let full = t.fullAmount {
                // S-05 (2026-11-20): "Your share $42.06" as a pill, "of $84.12"
                // beside it in muted, under the category and in line with it.
                HStack(spacing: 8) {
                    CFPill(text: "Your share \(Format.amount(t.splitting.map { $0.you } ?? t.amount))",
                           symbol: "person.2", symbolTone: Pearl.moneyOut)
                    Text("of \(Format.amount(full))").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    Spacer(minLength: 0)
                }
                .padding(.leading, 16 + 36 + 12).padding(.trailing, 16).padding(.bottom, 14).padding(.top, -4)
                .accessibilityElement(children: .combine)
            }
            if let trip = t.trip {
                // TR-06 (G7-TripMore): the trip it's in, under the category,
                // "Trip to Montréal" over "Mar 4–9 · 23 transactions"; it opens TR-02.
                APSeparator(afterFace: false)
                NavigationLink { TripPage(id: trip.id) } label: {
                    row(title: trip.name,
                        sub: [Format.span(trip.start, trip.end),
                              trip.count.map { "\($0) transaction\($0 == 1 ? "" : "s")" }]
                            .compactMap { $0 }.joined(separator: " · "),
                        chevron: true, icon: "airplane")
                }
                .buttonStyle(.plain)
                .accessibilityHint("Opens the trip")
            }
            if let rule = t.recurringRule {
                // T-03t (G1-TxRecurring, 2026-11-24): the rule behind the
                // category, in Always's slot; RS-01 is the way out of it.
                APSeparator(afterFace: false)
                Button { recurringMenu = true } label: {
                    row(title: "Recurring", sub: rule.when, chevron: true, icon: "repeat")
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .accessibilityHint("Not this one, or stop the rule")
            }
            if alwaysInCategoryCard {
                // T-03r (1074:698, dark 1074:814): Always for the merchant is
                // part of what it is, so it sits under the category, not in Options.
                APSeparator(afterFace: false)
                // A+ (REDESIGN-09 fix): no line repeating the row's title.
                alwaysToggle(sub: nil)
            }
            if isIncome, let payer = t.incomeRule?.payer {
                // Income's Always too (product owner, 2026-11-21: under the
                // category on every page, never in Options).
                APSeparator(afterFace: false)
                incomeAlwaysToggle(payer)
            }
        }
    }

    /// T-03r: the sorted spending row's Always switch is in the category card.
    private var alwaysInCategoryCard: Bool {
        offersNewOnes && guessName == nil && t.parts.isEmpty && !jointAsks && !t.asks && !isIncome
            && t.transfer == nil
    }

    private func categoryLabel(symbol: String, title: String, sub: String?) -> some View {
        APCard { categoryRow(symbol: symbol, title: title, sub: sub) }
    }

    /// A+ (G1-TxSpend, G1-TxMore, G1-TxRefund): the category's icon, its
    /// name in 17 semibold over any line, and "Change" in `link` (no
    /// chevron then); income's kind ends in the chevron.
    private func categoryRow(symbol: String, title: String, sub: String?, change: Bool = false,
                             systemImage: String? = nil) -> some View {
        CFRowLabel(symbol: systemImage ?? CategorySheet.symbol(for: symbol), title: title, sub: sub, bold: true,
                   trailing: change ? .word("Change") : .chevron)
    }

    // MARK: Pearl's guess (T-96)

    /// The guess waiting for a yes: the question's, or the transaction's own.
    private var guessName: String? {
        if let guessing = guessing { return chosenCategory ?? guessing.label }
        guard t.transfer == nil, t.parts.isEmpty, !jointAsks, !t.asks, t.suggested else { return nil }
        return chosenCategory ?? t.label
    }

    /// From the list, whether a rule is possible at all.
    private var canRule: Bool { learnable && (t.category ?? "Other") != "Other" }

    /// Whether the Always switch shows: a rule could match this merchant.
    private var offersNewOnes: Bool {
        // Income has its own Always, for the kind of income (2026-11-08): one switch, not two.
        if isIncome && t.incomeRule?.payer != nil { return false }
        if let guessing = guessing { return guessing.ask.canSaveRule(guessing.accounts) }
        // Already sorted: only for spending, where a rule means something.
        return canRule && (guessName != nil || (!t.inflow && t.transfer == nil && t.excluded.isEmpty))
    }

    /// The switch's starting place: off where the merchant doesn't sort one way.
    private var newOnesOn: Bool {
        if let choice = newOnes { return choice }
        if let guessing = guessing { return guessing.ask.savesRule(guessing.accounts) }
        // A row that's already sorted shows whether a rule is there.
        return guessName != nil ? !varies : hasRule
    }

    /// T-96: the category, marked as a guess. Tapping it changes the answer.
    private func guessCard(_ label: String) -> some View {
        Button { sorting = guessing?.ask ?? sortAsk(.category) } label: {
            let still = chosenCategory == nil && !pickedGuess
            let symbol = chosenCategory ?? guessing?.ask.item.guess?.text ?? t.category ?? t.label
            // T-93o (product owner, 2026-11-13): a best guess of Other reads
            // "Other", Pearl's guess, like any guess; Yes is this one alone,
            // with no Always (Ask.canRule), and tapping still opens What was this?.
            // A+ (G1-TxSpend): PEARL'S GUESS over the icon and "Dining out?"
            // in Fraunces 20, on a card with a dashed rose outline and no
            // shadow; her own pick is the plain card.
            VStack(alignment: .leading, spacing: 12) {
                Text(still ? "PEARL’S GUESS" : "YOUR CHOICE")
                    .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                    .foregroundColor(Pearl.action)
                HStack(spacing: 12) {
                    CFIcon(symbol: CategorySheet.symbol(for: symbol))
                    Text(still ? "\(label)?" : label)
                        .font(Pearl.heading(20, relativeTo: .title3)).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }
            }
            .padding(16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .background(GuessCardSurface(dashed: still))
            .contentShape(RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous))
            .accessibilityElement(children: .combine)
            .accessibilityLabel(still ? "Pearl’s guess, \(label)" : "Your choice, \(label)")
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityHint("Changes the answer")
    }

    /// T-96: Yes, with the rule stated in plain sight by the Always switch.
    /// A+ (G1-TxSpend, kit `.btnrow`): Skip and "Yes, Dining out" side by
    /// side at the bottom, from Needs a look and from the list alike; from
    /// the list the tab bar goes so they have the bottom (REDESIGN-09).
    /// Skip leaves it in Needs a look; from the list it goes back.
    @ViewBuilder private var guessActions: some View {
        if let label = guessName, guessing?.onDraft == nil, guessing != nil || !t.asks {
            HStack(spacing: 12) {
                Button("Skip") {
                    if let skip = guessing?.onSkip { skip() } else { dismiss() }
                }
                .buttonStyle(APSecondaryButtonStyle())
                .accessibilityHint("It stays in Needs a look.")
                Button("Yes, \(label)") {
                    let keep = offersNewOnes && newOnesOn
                    if let guessing = guessing, chosenCategory == nil {
                        guessing.onYes(keep)
                    } else {
                        answer(with: chosenCategory ?? label, always: keep)
                    }
                }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
            }
            .disabled(busy)
            .padding(.horizontal, 16).padding(.bottom, 8)
        }
    }

    /// A guess opened from the list hides the tab bar (REDESIGN-09).
    private var guessFromList: Bool { guessing == nil && guessName != nil && !t.asks }

    private var isIncome: Bool { t.inflow && t.counts == "income" && t.transfer == nil }

    /// Link transfers (2026-11-22): a row that is, or could be, one leg of
    /// money moving between her accounts and has no other end paired: a
    /// transfer, Not sorted yet, Saved, Other, or money in that isn't pay.
    private var canLink: Bool {
        // Opened from a Needs a look card too (2026-11-22): the leg left on
        // its own is usually the one Pearl is asking about. Not on a payback
        // or a refund: those have their own Options, and a second OPTIONS
        // card read as a mistake.
        guard t.transfer == nil, t.partOf == nil, t.parts.isEmpty, t.repaysCharge == nil, t.refundOf == nil
        else { return false }
        return t.counts != "spending" || t.category == "Unsorted transfers" || t.category == "Other"
            || (t.inflow && !isIncome)
    }

    /// T-41w (1297:64759, built from T-41): a deposit that pays a purchase
    /// back reads as her answer on What was this?, with its tile's icon:
    /// PAID-02: "Paid back · work" (briefcase), "Paid back · refund", or
    /// "Paid back · Priya" (person.2), "Paid back" with no name.
    /// A "Paid back" chip and a green amount go with it.
    private var paidBackAnswer: (label: String, symbol: String)? {
        // T-41m: a refund of her share stays a refund page (T-41).
        guard t.inflow, t.transfer == nil, t.excluded.isEmpty, t.refundOf == nil,
              let charge = t.repaysCharge else { return nil }
        // PB-10 folded these tiles into Paid back; PAID-02 redrew T-41w:
        // every link reads "Paid back · {who}".
        switch charge.kind {
        case "reimbursement": return ("Paid back · work", "briefcase")
        case "refund_share": return ("Paid back · refund", "arrow.uturn.backward")
        default:
            let who = charge.person.flatMap { $0.isEmpty || $0 == "me" ? nil : $0 }
            return (who.map { "Paid back · \($0)" } ?? "Paid back", "person.2")
        }
    }

    /// Money in that could be her pay: not a refund, a payback or a transfer.
    private var couldBePay: Bool {
        // A deposit sorted into parts, or a part of one, isn't pay (2026-11-20:
        // "This is my regular pay" sat under a payback's own Options).
        t.inflow && t.transfer == nil && t.refundOf == nil && t.repays == nil && t.excluded.isEmpty
            && t.jointFrom != "them" && t.parts.isEmpty && t.partOf == nil
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
    /// What the Counts pill says (T-03, T-37, T-41).
    private var countsPill: (label: String, up: Bool, tone: Color) {
        if !t.excluded.isEmpty { return ("Not counted", !t.inflow, Pearl.muted) }
        // T-41w: a deposit that paid a purchase back says so.
        if paidBackAnswer != nil { return ("Paid back", true, Pearl.moneyIn) }
        if t.refundOf != nil { return ("Refund", true, Pearl.moneyIn) }
        // S-33 v2 (G2-BPayback): a deposit in parts that pays something back.
        if t.partOf == nil, !paidBackOnly, t.parts.contains(where: { $0.kind == "payback" }) {
            return ("Payback", true, Pearl.moneyIn)
        }
        switch t.counts {
        case "income": return ("Income", true, Pearl.moneyIn)
        case "spending": return ("Spending", t.inflow, t.inflow ? Pearl.moneyIn : Pearl.moneyOut)
        default: return ("Not counted", t.inflow, Pearl.muted)
        }
    }

    /// The category card's second line, only when the frames draw one:
    /// a share (T-39, S-05), why it's left out, or a payback's note.
    private var countsLine: String? {
        if !t.excluded.isEmpty { return "Left out · \(t.excluded)" }
        if t.refundOf != nil { return nil }
        if t.split, t.fullAmount != nil {
            // S-05: the share is a pill under the row (`sharePill`), not a
            // line of text (2026-11-20). Rule A: the share as split, not
            // what counts until they pay.
            return nil
        }
        switch t.counts {
        case "income" where t.jointFrom == "both":
            // T-33's Both of us: only her share is her income.
            let mine = (t.amount * (t.jointShare ?? 50) / 100 * 100).rounded() / 100
            return "Your share counts · \(Format.compact(mine)) of \(Format.compact(t.amount))"
        case "income": return nil
        case "spending":
            return t.inflow ? t.note.flatMap { $0.isEmpty ? nil : $0 } : nil
        default:
            return t.note.flatMap { $0.isEmpty ? nil : $0 }
        }
    }

    /// PQ-03p (G2-APQ): A QUESTION, "Paying you back for Añejo?" with Yes
    /// and Not this, in place of the flat Not sorted yet card. Not this
    /// opens Needs a look's question with every answer.
    @ViewBuilder private var askingOrPayback: some View {
        if let q = shownPaybackAsk {
            PaybackQuestionCard(question: q, onYes: { Task { await answerPaybackGuess(q) } },
                                onNot: { Task { await openQuestion() } })
                .disabled(busy)
                .padding(.top, 8)
        } else {
            askingCard
        }
    }

    /// PQ-03p's Yes: Pearl's guess, as the sheet's first tile answers it
    /// (PQ-03c's toast with Undo). When the money is more than that share and
    /// the person owes on other purchases, the question opens instead, where
    /// the tile goes on to PB-30 with this one ticked.
    @inline(never)
    private func answerPaybackGuess(_ q: PaybackQuestion) async {
        guard let tile = q.tiles.first else { return }
        busy = true
        let parts = await PaybackQuestion.partsPerson(api: app.api, id: t.id, amount: t.amount, tile: tile)
        busy = false
        if parts != nil {
            await openQuestion()
            return
        }
        await answered(.payback(t.id, charge: tile.charge, toast: tile.toast, person: tile.person))
    }

    /// PQ-03p: the payback question for this deposit, when Needs a look is
    /// asking about it (GET payback-question).
    @inline(never)
    private func loadPaybackQuestion() async {
        guard guessing == nil, t.asks, t.inflow else { paybackAsk = nil; paybackChecked = true; return }
        if t.paybackKnown {
            // The row brought it (2026-11-20): nothing to ask.
            paybackAsk = t.paybackQuestion
            paybackChecked = true
            return
        }
        struct Reply: Decodable { let question: PaybackQuestion? }
        let reply: Reply? = try? await app.api.get("api/transactions/\(t.id)/payback-question")
        paybackAsk = reply?.question
        paybackChecked = true
    }

    /// "Not sorted yet · Paid back or income? Tell us": the question Needs a
    /// look is asking, answered here.
    private var askingCard: some View {
        Button { Task { await openQuestion() } } label: {
            APCard {
                row(title: t.label, sub: t.note.flatMap { $0.isEmpty ? nil : $0 } ?? "Needs a look", chevron: true)
            }
        }
        .buttonStyle(.plain)
        .disabled(busy)
    }

    // MARK: Linked transactions

    /// PAID BACK (T-39), REFUND FOR (T-41), REFUNDED BY, or the charge a
    /// payback is for.
    /// Its own bodies (stack check: one was 31 KB).
    @ViewBuilder private var linked: some View {
        OwnBody { linkedBack }
        OwnBody { paysBack }
    }

    @ViewBuilder private var linkedBack: some View {
        // SPLIT-25 (S-05v): a split purchase's card is the one place its
        // paybacks are listed; one that isn't split keeps PAID BACK.
        if !t.repaidBy.isEmpty && t.splitting == nil {
            section("Paid back")
            SolidCard {
                ForEach(Array(t.repaidBy.enumerated()), id: \.element.id) { index, b in
                    if index > 0 { APSeparator() }
                    let part = b.paid.flatMap { abs($0 - abs(b.amount)) >= 0.005 ? $0 : nil }
                    // S-05o from the purchase: View, then Unlink… (S-34s / S-34k).
                    Button {
                        if let link = b.link {
                            linkOptions = link
                        } else {
                            unlinkingPayback = PaybackLink(charge: t.id, inflow: b.id, who: b.person ?? b.merchant ?? b.name,
                                                           name: b.merchant ?? b.name, amount: part ?? abs(b.amount),
                                                           date: b.date)
                        }
                    } label: {
                        linkedRow(name: b.merchant ?? b.name,
                                  sub: [Format.short(b.date), part.map { _ in "part of \(Format.whole(abs(b.amount)))" }]
                                      .compactMap { $0 }.joined(separator: " · "),
                                  amount: part ?? abs(b.amount), inflow: true, chevron: true)
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint("Shows options, including Unlink")
                }
            }
        }
        if let charge = t.refundOf, charge.share == true {
            // TEST-31 Money back T-41m (G2-BPayback): REFUND FOR, "Pai Northern
            // Thai" over "Your share of $120.00 · Nov 12", what it refunded of
            // her share; Options: Change what it refunded, Unlink.
            let paid = charge.paid ?? abs(t.amount)
            section("Refund for")
            SolidCard {
                Button { Task { await open(charge.id) } } label: {
                    HStack(spacing: 14) {
                        Initials(name: charge.merchant)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(charge.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Text(shareLine(whole: charge.amount, date: charge.date)).font(Nacre.subheadline)
                                .foregroundColor(Pearl.muted).lineLimit(1)
                        }
                        Spacer(minLength: 8)
                        Text(Format.amount(paid)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Refund for your share of \(charge.merchant), \(Format.amount(paid))")
                .accessibilityHint("Opens its split")
                .accessibilityAddTraits(.isButton)
            }
            shareOptions(change: "Change what it refunded") { unlinkingRefund = true }
        } else if let charge = t.refundOf {
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
                    if index > 0 { APSeparator() }
                    if let link = r.link {
                        // SPLIT-25: S-05o "View the refund", "Unlink refund…".
                        Button { linkOptions = link } label: {
                            linkedRow(name: r.merchant, sub: Format.short(r.date), amount: r.amount, inflow: true,
                                      chevron: true)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Shows options, including Unlink")
                    } else {
                        linkedRow(name: r.merchant, sub: Format.short(r.date), amount: r.amount, inflow: true)
                    }
                }
            }
        }
    }

    /// What this money in paid back: her share (TEST-31 T-41w) or a split.
    @ViewBuilder private var paysBack: some View {
        if let charge = t.repaysCharge, charge.person == "me", t.refundOf == nil {
            // TEST-31 T-41w (G2-BPayback): work paid her share. PAID BACK, the
            // purchase over "Your share of $120.00 · Nov 12", opening its
            // split card; Options: Change what it paid back, Unlink.
            let paid = charge.paid ?? abs(t.amount)
            section("Paid back")
            SolidCard {
                Button { Task { await open(charge.id) } } label: {
                    HStack(spacing: 14) {
                        Initials(name: charge.merchant ?? charge.name)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(charge.merchant ?? charge.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Text(shareLine(whole: charge.amount, date: charge.date)).font(Nacre.subheadline)
                                .foregroundColor(Pearl.muted).lineLimit(1)
                        }
                        Spacer(minLength: 8)
                        Text(Format.amount(paid)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel("Paid back, your share of \(charge.merchant ?? charge.name), \(Format.amount(paid))")
                .accessibilityHint("Opens its split")
                .accessibilityAddTraits(.isButton)
            }
            shareOptions(change: "Change what it paid back") {
                if let link = charge.link {
                    unlinkingLink = link
                } else {
                    unlinkingPayback = PaybackLink(charge: charge.id, inflow: t.id, who: t.merchant,
                                                   name: t.merchant, amount: paid, date: t.date)
                }
            }
        } else if let charge = t.repaysCharge, t.refundOf == nil {
            section("Pays back")
            // Just the purchase it paid back, opening it (product owner,
            // 2026-11-22): the split's people and shares belong on the
            // purchase's own page, not repeated here (supersedes 2026-11-08).
            SolidCard {
                Button { Task { await open(charge.id) } } label: {
                    linkedRow(name: charge.merchant ?? charge.name,
                              sub: charge.split.map { "\(Format.short(charge.date)) · split \($0.people.count + ($0.you >= 0.005 ? 1 : 0)) ways" }
                                  ?? Format.short(charge.date),
                              amount: abs(charge.amount), inflow: false, chevron: true)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .accessibilityHint("Opens the purchase")
            }
            // S-33: the money that paid it back can be unlinked (S-34).
            section("Options")
            APCard {
                if wholeSinglePart {
                    // The one Options card for a payback saved on Paid back
                    // (2026-11-20): PB-41's Change what it paid back on the
                    // deposit, and the parts' Unlink.
                    Button {
                        editingParts = true
                        repicking = true
                        parting = parentDeposit()
                    } label: {
                        row(title: "Change what it paid back", chevron: true, icon: "arrow.left.arrow.right")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    APSeparator(afterFace: false)
                    Button { unlinking = true } label: {
                        row(title: "Unlink", sub: "It counts as money in again", chevron: true, icon: "link")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                } else {
                    Button {
                        // TEST-31: "all of it" is work's, not a person's.
                        unlinkingPayback = PaybackLink(charge: charge.id, inflow: t.id,
                                                       who: charge.person == "everyone" ? t.merchant : (charge.person ?? "They"),
                                                       name: t.merchant, amount: t.amount, date: t.date)
                    } label: {
                        row(title: "Unlink", sub: "It counts as money in again", chevron: true, icon: "link")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
            }
        }
    }

    /// A payback saved on Paid back for one purchase is the deposit's one
    /// part, as big as the deposit (finance/parts.py). The page opened on
    /// that part said it twice: PAYS BACK with Unlink, then "Part of a
    /// $58.00 deposit" naming the same purchase, with Unlink again
    /// (product owner, 2026-11-20). Such a row is shown as the payback it
    /// is: one card, one Options.
    private var wholeSinglePart: Bool {
        guard let parent = t.partOf, t.repaysCharge != nil else { return false }
        return parent.parts.count == 1 && abs(parent.amount - abs(t.amount)) < 0.005
    }

    /// The deposit this part is from, for PB-41 on it.
    private func parentDeposit() -> PartsDeposit? {
        guard let parent = t.partOf else { return nil }
        return PartsDeposit(id: parent.id, name: t.merchant, amount: -parent.amount, date: parent.date, rest: false)
    }

    /// T-41w / T-41m (G2-BPayback): OPTIONS, "Change what it paid back" (or
    /// refunded), which opens What was this? as the category card did, and
    /// Unlink, which asks first.
    @ViewBuilder private func shareOptions(change: String, unlink: @escaping () -> Void) -> some View {
        section("Options")
        APCard {
            Button { changeWhatItIs() } label: {
                row(title: change, chevron: true, icon: "arrow.left.arrow.right")
            }
            .buttonStyle(.plain)
            .disabled(busy)
            APSeparator(afterFace: false)
            Button(action: unlink) {
                row(title: "Unlink", chevron: true, icon: "link")
            }
            .buttonStyle(.plain)
            .disabled(busy)
        }
    }

    /// The category card's tap: what the deposit was, asked again.
    private func changeWhatItIs() {
        if t.leftToSort { parting = deposit(rest: true) }
        // Income opens What was this?: its kinds, and what else it could be (2026-11-08).
        // T-41w: her answer opens What was this? again, as income does.
        else if isIncome || paidBackAnswer != nil { asking = Asking(step: .into) } else { sorting = sortAsk(.category) }
    }

    private func linkedRow(name: String, sub: String, amount: Double, inflow: Bool,
                           chevron: Bool = false) -> some View {
        HStack(spacing: 14) {
            Initials(name: name)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text((inflow ? "+" : "\u{2212}") + Format.amount(amount))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(Pearl.ink)
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    // MARK: Joint accounts (T-33, T-40)

    /// "Joint with Sam · 50%", or the account's name when it has no people.
    private var jointLine: String {
        let who = t.jointPeople.isEmpty ? t.joint : "Joint with " + Format.shortList(t.jointPeople)
        return who + (t.jointShare.map { " · \(Int($0.rounded()))%" } ?? "")
    }

    /// Money into a joint account nobody has said whose it is.
    private var jointAsks: Bool {
        t.inflow && !t.joint.isEmpty && t.jointFrom.isEmpty && t.transfer == nil && t.repays == nil
    }

    /// T-40: "Is this Sam's pay?" — Yes, or the whole question.
    private var jointGuessCard: some View {
        let person = t.jointPeople.count == 1 ? t.jointPeople[0] : nil
        // T-40 (G1-TxNote): the caps and the question on the left, then
        // Something else and Yes side by side, Yes on the right.
        return VStack(alignment: .leading, spacing: 14) {
            VStack(alignment: .leading, spacing: 4) {
                Text("PEARL’S GUESS")
                    .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                    .foregroundColor(Pearl.action)
                Text(person.map { "Is this \($0)’s pay?" } ?? "Is this your pay?")
                    .font(Nacre.title2).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 10) {
                // TEST-32: the control fill reads in both modes.
                Button("Something else") { asking = Asking(step: .joint) }
                    .buttonStyle(APSecondaryButtonStyle())
                Button("Yes") {
                    let answer = ReviewAnswer.joint(t.id, who: person == nil ? "me" : "them", person: person)
                    Task {
                        busy = true
                        defer { busy = false }
                        do {
                            let reply = try await answer.send(app.api)
                            // T-40b: "Sam's pay · Undo".
                            withAnimation { toast = (person.map { "\($0)’s pay" } ?? "Your pay", undoing(reply.undo)) }
                            await load()
                            app.changed()
                        } catch {
                            self.error = app.handle(error)
                        }
                    }
                }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
            }
            .disabled(busy)
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        // A+: Pearl's guess is the dashed rose outline (G1-TxSpend).
        .background(GuessCardSurface(dashed: true))
    }

    /// Whose an answered joint deposit is, to change it.
    @ViewBuilder private var jointRow: some View {
        if t.inflow && !t.joint.isEmpty && !t.jointFrom.isEmpty && t.transfer == nil {
            section("Joint account")
            APCard {
                Button { asking = Asking(step: .joint) } label: {
                    // T-40b (G1-TxNote): "Whose pay   Sam's · not yours ›".
                    row(title: "Who put it in", chevron: true, value: jointWhose, icon: "person.2")
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
    }

    /// "Yours", "Sam’s", "$93.20 of $186.40".
    private var spendWhose: String {
        let full = t.fullAmount ?? t.amount
        if t.shareSet && t.amount < 0.005 { return "\(t.joint)’s" }
        if abs(t.amount - full) >= 0.005 { return "\(Format.amount(t.amount)) of \(Format.amount(full))" }
        return "Yours"
    }

    private var jointWhose: String {
        switch t.jointFrom {
        case "me": return "Yours"
        case "both":
            // "Everyone" on an account shared with several people (2026-11-21).
            return "\(t.jointPeople.count > 1 ? "Everyone’s" : "Both of yours") · your share \(Int((t.jointShare ?? 50).rounded()))% counts"
        default: return t.jointPerson.map { "\($0)’s · not yours" } ?? "Theirs · not yours"
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
    /// Not on a joint account (S-01j, SPLIT-08): that's Whose was it?.
    /// JOINT-B (S-01jr): a joint-account purchase is split from its own row,
    /// "Split my part", next to Whose was it?.
    private var canSplit: Bool {
        !t.inflow && t.transfer == nil && t.refundOf == nil && t.splitting == nil && t.excluded.isEmpty
            && t.joint.isEmpty
    }

    /// JOINT-B: a joint purchase not split yet. Dimmed when none of it is hers (T-06jr1).
    private var canSplitJoint: Bool {
        jointCharge && t.refundOf == nil && t.splitting == nil && t.excluded.isEmpty
    }

    /// S-01j: a joint-account purchase, asked Whose was it? in Options.
    private var jointCharge: Bool { !t.inflow && !t.joint.isEmpty && t.transfer == nil }

    /// "Joint with Sam · yours, Sam’s or shared", or what she said.
    private var whoseSub: String {
        if t.shareSet { return spendWhose }
        let them = t.jointPeople.isEmpty ? "theirs"
            : t.jointPeople.map { "\(Format.shortName($0))’s" }.joined(separator: ", ")
        let who = t.jointPeople.isEmpty ? t.joint : "Joint with " + Format.shortList(t.jointPeople)
        return "\(who) · yours, \(them) or shared"
    }

    /// S-01jr "Split my part" (REFRESH-03: no subtitle; the hero says the
    /// part); S-01jr2 on "All mine unless I mark it" the usual "Split with
    /// others"; T-06jr1 dimmed with why when none of it is hers (VoiceOver
    /// reads the reason).
    private var jointSplitRow: some View {
        let none = t.splitBase < 0.005
        return Button { splitting = true } label: {
            row(title: t.splitsMyPart ? "Split my part" : "Split with others",
                sub: none ? "None of it is yours to split."
                    : t.splitsMyPart ? nil : "Split it with friends",
                chevron: !none, icon: "person.2")
                .opacity(none ? 0.45 : 1)
        }
        .buttonStyle(.plain)
        .disabled(busy || none)
    }

    private func deposit(rest: Bool) -> PartsDeposit {
        PartsDeposit(id: t.id, name: t.merchant, amount: t.amount, date: t.date, rest: rest)
    }

    /// OWED TO YOU or SPLIT 3 WAYS (S-04, S-05, S-19, S-20).
    @ViewBuilder private var splitPeople: some View {
        if let split = t.splitting, !split.people.isEmpty, !t.inflow {
            SplitPeople(t: t, split: split, onChoose: choose,
                        onEdit: { splitting = true },
                        onOwed: { seeingOwed = true },
                        onCredit: { crediting = Crediting(id: $0.id) },
                        onSettle: { settlingUp = true },
                        onClose: { closingSplit = true },
                        onReopen: { Task { await reopenSplit() } },
                        onSetShare: { settingShare = true },
                        optionsFor: $optionsFor,
                        onMine: chooseMine)
        } else if detail == nil, t.splitMode != nil, !t.inflow, t.transfer == nil {
            // S-04ul / S-04ue (G2-BCard2): the split card while the purchase
            // loads (two grey rows), or "Couldn’t load the split." with Try again.
            SplitCardPending(heading: pendingSplitHeading, failed: loadFailed, busy: busy,
                             onRetry: { Task { busy = true; await load(); busy = false } },
                             onOwed: { seeingOwed = true })
        }
    }

    /// "Split with 2 · Not sure yet" before the split itself has come back:
    /// what the list row knows (RC-01's ways, SPLIT-C's mode).
    private var pendingSplitHeading: String {
        let unsure = t.splitMode == "unknown" || t.cost?.unsure == true
        let ways = t.cost?.ways ?? 0
        let lead = ways >= 2 ? "Split \(ways) ways" : "Split"
        return unsure ? "\(lead) · Not sure yet" : lead
    }

    /// "Payback + gift": what a deposit in parts was (S-33).
    private var partsCard: some View {
        APCard {
            let people = Set(t.parts.compactMap(\.person))
            if paidBackOnly, people.count == 1, let who = people.first {
                // PB-41: "Paid back · Sam Lee" (How it counts).
                row(title: "Paid back · \(who)", chevron: false, icon: "person.2")
                if let jp = t.jointPayback {
                    // TP-04: the joint side is theirs; it opens that money out.
                    APSeparator(afterFace: false)
                    Button { Task { await open(jp.outId) } } label: {
                        row(title: "Joint side: \(possessive(jp.person)) money, not your spending", chevron: true, icon: "person.2")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
            } else {
                row(title: partsTitle, sub: "In \(t.parts.count) parts", chevron: false)
            }
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
        if wholeSinglePart {
            // Said once, by PAYS BACK and its Options (`wholeSinglePart`).
            EmptyView()
        } else if paidBackOnly {
            paidBackParts
        } else if !parts.isEmpty {
            // S-33 v2 (G2-BPayback): PAYBACK + GIFT, every part, so they add
            // up to the deposit; the label says what it was (no card above).
            section(t.partOf.map { "Part of a \(Format.amount($0.amount)) deposit" } ?? partsTitle)
            SolidCard {
                ForEach(Array(parts.enumerated()), id: \.element.id) { index, p in
                    if index > 0 { APSeparator() }
                    partRow(p)
                }
            }
            section("Options")
            APCard {
                if t.partOf == nil {
                    // S-33 v2's Edit: S-10e, the parts filled in (SPLIT-03).
                    Button {
                        editingParts = true
                        parting = deposit(rest: false)
                    } label: {
                        row(title: "Edit", sub: "Change the parts or what they pay back", chevron: true, icon: "pencil")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    APSeparator(afterFace: false)
                }
                Button { unlinking = true } label: {
                    // S-33 v2: no second line; the sheet says what it does.
                    row(title: "Unlink", chevron: true, icon: "link")
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
        }
    }

    /// PB-41: a deposit that only pays back people's shares (PB-30's), all of it.
    private var paidBackOnly: Bool {
        t.partOf == nil && !t.parts.isEmpty
            && t.parts.allSatisfy { $0.kind == "payback" && $0.person != nil && $0.charge != nil }
    }

    /// PB-41 (1395:4794, dark 1395:4922): PAID BACK · 2 PURCHASES, a row each
    /// opening PB-42; Options: Change what it paid back (PB-30 with today's
    /// ticks), Unlink both (asks first, as T-41b).
    @ViewBuilder private var paidBackParts: some View {
        let n = t.parts.count
        // TP-04 (G2b-JointIn): "Paid back 3 of Mom’s shares".
        section(t.jointPayback.map { "Paid back \(n) of \(possessive($0.person)) share\(n == 1 ? "" : "s")" }
                ?? "Paid back · \(n) purchase\(n == 1 ? "" : "s")")
        SolidCard {
            ForEach(Array(t.parts.enumerated()), id: \.element.id) { index, p in
                if index > 0 { APSeparator() }
                Button { Task { await openDepositLink(p) } } label: { paidBackRow(p) }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    .accessibilityHint("How much, who, which purchase, or Unlink")
            }
        }
        section("Options")
        APCard {
            Button {
                editingParts = true
                repicking = true
                parting = deposit(rest: false)
            } label: {
                row(title: "Change what it paid back", chevron: true, icon: "arrow.left.arrow.right")
            }
            .buttonStyle(.plain)
            .disabled(busy)
            APSeparator(afterFace: false)
            Button { unlinking = true } label: {
                // TP-04: "Unlink all · it's a transfer again".
                row(title: t.jointPayback != nil ? "Unlink all · it’s a transfer again" : n == 2 ? "Unlink both" : "Unlink",
                    chevron: true, icon: "link")
            }
            .buttonStyle(.plain)
            .disabled(busy)
        }
    }

    /// "Pai Northern Thai" over "Sam’s share · all of it · Nov 12", $60.00.
    private func paidBackRow(_ p: DepositPart) -> some View {
        let name = p.person.map { $0.split(separator: " ").first.map(String.init) ?? $0 } ?? "Their"
        let all = p.share.map { Int(($0 * 100).rounded()) <= Int((p.amount * 100).rounded()) } ?? true
        let merchant = p.charge?.merchant ?? p.label
        return HStack(spacing: 14) {
            Initials(name: merchant)
            VStack(alignment: .leading, spacing: 2) {
                Text(merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                // TP-04: the label already says whose; the row keeps the day.
                Text(t.jointPayback != nil ? Format.short(p.charge?.date ?? t.date)
                     : "\(possessive(name)) share · \(all ? "all of it" : "part of it") · \(Format.short(p.charge?.date ?? t.date))")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Spacer(minLength: 8)
            Text(Format.amount(p.amount)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// PB-41 → PB-42: the link as the purchase's split card has it.
    private func openDepositLink(_ p: DepositPart) async {
        guard let charge = p.charge else { return }
        do {
            let c: Transaction = try await app.api.get("api/transactions/\(charge.id)")
            let on = c.splitting?.people.first { ($0.links ?? []).contains { $0.id == p.id } }
            guard let person = on, let link = person.links?.first(where: { $0.id == p.id }) else {
                error = "Couldn’t open that. Pull to refresh."
                return
            }
            depositLink = DepositLink(link: link, charge: c.id, merchant: c.merchant, date: c.date, owes: person.owes,
                                      people: c.splitting?.people ?? [])
        } catch {
            self.error = app.handle(error) ?? "Couldn’t open that. Pull to refresh."
        }
    }

    /// A payback by someone on a split, bank or part: PB-42's options.
    static func personPayback(_ link: Transaction.LinkInfo) -> Bool {
        ["bank", "part"].contains(link.kind) && link.person != nil
    }

    /// What the person this link is credited to still owes here.
    private func owesOn(_ link: Transaction.LinkInfo) -> Double {
        t.splitting?.people.first { ($0.links ?? []).contains { $0.id == link.id } }?.owes ?? 0
    }

    /// PP-02 (Paybacks 2): the page again, then PB-42 for the same payment
    /// on who paid it now, with the ink toast and its Undo. Someone not on
    /// the split has no row to open it from: the page's toast instead.
    private func reopenLink(_ was: Transaction.LinkInfo, for name: String, _ title: String, _ undo: JSONValue?) async {
        await load()
        app.changed()
        let payment = was.deposit?.id ?? was.inflow ?? was.id
        let now = t.splitting?.people.first { $0.name == name }?.links?.first { ($0.deposit?.id ?? $0.inflow ?? $0.id) == payment }
        guard let link = now, Self.personPayback(link) else {
            showSplit(title, undo: undo.map { u in { try await postUndo(u); return nil } })
            return
        }
        linkNotice = PearlToast.Model(text: title, action: undo == nil ? nil : "Undo", run: undo.map { u in {
            linkOptions = nil
            Task { await runUndo { try await postUndo(u); return nil } }
        } })
        linkStart = .options
        linkOptions = link
    }

    /// PB-42's change saved: the page again, and UN-01's toast with Undo.
    private func linkChanged(_ title: String, _ undo: JSONValue?) {
        Task {
            await settled(title, undo: undo.map { u in { try await postUndo(u); return nil } })
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
        // S-33 v2: "Income · Gift".
        case "gift": return "Income · Gift"
        case "income": return "Income · \(Self.kindName(p.incomeKind))"
        case "moved": return "Not new money"
        case "savings": return "Out of savings"
        case "cash": return "Cash you were paid"
        case "overpaid": return "You owe \(p.person ?? "them") this"
        // S-11 v2 (SPLIT-04).
        case "reimbursement": return [p.charge?.category, "Paid back · work"].compactMap { $0 }.joined(separator: " · ")
        case "loan": return "Borrowed · Lent me this"
        case "lent_back": return "Lent · Money I lent, back"
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
            CFSheetTitle(title: "Unlink?") { unlinking = false }
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
                .buttonStyle(APPrimaryButtonStyle())
                Button("Keep linked") { unlinking = false }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Pearl.card))  // TEST-32
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .cfSheet()
        .presentationDetents([.height(320)])
    }

    /// S-34 for one payback: "Dad will owe you $64.00 again."
    private func paybackUnlinkSheet(_ link: PaybackLink) -> some View {
        VStack(spacing: 16) {
            CFSheetTitle(title: "Unlink?") { unlinkingPayback = nil }
            QuestionHeader(name: link.name, amount: Format.amount(link.amount), tone: Pearl.ink,
                           sub: Format.short(link.date))
                .padding(.horizontal, 16)
            Text("\(link.who) will owe you \(Format.amount(link.amount)) again.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
            HStack(spacing: 10) {
                Button("Unlink") {
                    unlinkingPayback = nil
                    Task { await unlinkPayback(link) }
                }
                .buttonStyle(APPrimaryButtonStyle())
                Button("Keep linked") { unlinkingPayback = nil }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Pearl.card))  // TEST-32
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .cfSheet()
        .presentationDetents([.height(320)])
    }

    // MARK: Options

    /// A charge a piggy bank paid for. "Pay from a piggy bank" is parked with
    /// Save (product owner, 2026-11-18), so the row only shows on a charge a
    /// piggy bank already paid ("Paid from a piggy bank"), to undo it.
    private var canPayFromBank: Bool {
        t.bankId != nil && !t.inflow && t.transfer == nil && t.excluded.isEmpty
    }

    /// T-03: one Options card. Split with others, Regular pay (T-37),
    /// Unlink refund (T-41), Pay from a piggy bank and One-off purchase, each a plain row.
    /// "Always for Loblaws": new ones from the merchant sort the same way.
    private func alwaysToggle(sub: String?) -> some View {
        Toggle(isOn: Binding(get: { newOnesOn }, set: { on in
            // Nothing left to answer on a sorted row, so the switch acts at once.
            if guessName == nil {
                Task { await setAlways(on) }
            } else {
                newOnes = on
                holdForCard { $0.always = on }
            }
        })) {
            HStack(spacing: 12) {
                CFIcon(symbol: "repeat")
                VStack(alignment: .leading, spacing: 3) {
                    // One label whatever the merchant is called (2026-11-20):
                    // a bank's long descriptor made it a paragraph.
                    Text("Always for this merchant").font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .tint(Pearl.action)
        .disabled(busy)
        .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)

        .accessibilityHint("New ones from \(t.merchant) sort the same way")
    }

    /// TEST-31 S-40w: what her reimbursed row's ••• chose.
    private func chooseMine(_ choice: PersonChoice) {
        switch choice {
        case .view(let link): if let id = link.view?.id { Task { await open(id) } }
        case .unlink(let link): unlinkingLink = link
        case .changeShare: splitting = true
        // PB-20 → PB-22: What paid back your share?
        case .findPaidBack: paidBackStep = .find
        default: break
        }
    }

    @ViewBuilder private var options: some View {
        // T-41m's Unlink is in its own Options under REFUND FOR (G2-BPayback).
        let unlink = t.refundOf != nil && t.refundOf?.share != true
        // Income can be left out of the usual month too (2026-11-08).
        let canOneOff = t.canOneOff && (!t.inflow || isIncome)
        // Income's Always is in the category card too (2026-11-21).
        let incomeAlways: String? = nil
        // T-03r: on a sorted row Always is in the category card instead.
        let offersNewOnes = self.offersNewOnes && !alwaysInCategoryCard
        // S-01jr (G2b-Purchase): the share bar and the Primary take Whose was
        // it? and Split my part out of Options.
        let jointCharge = self.jointCharge && !showsShareBar
        // Mark as paid back from the purchase (product owner, 2026-11-22):
        // the finder that was only on a split's own row (PB-20).
        let canFindPayback = !t.inflow && t.transfer == nil && t.partOf == nil && t.excluded.isEmpty
            && t.counts == "spending" && t.refundOf == nil
        if canSplit || canFindPayback || couldBePay || unlink || canLink || canOneOff || canPayFromBank || offersNewOnes
            || incomeAlways != nil || jointCharge {
            section("Options")
            APCard {
                if jointCharge {
                    // S-01jr (JOINT-B, supersedes S-01j): Whose was it?, then Split my part.
                    Button { whose = true } label: {
                        row(title: "Whose was it?", sub: whoseSub, chevron: true, icon: "person.2")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    if canSplitJoint {
                        APSeparator(afterFace: false)
                        jointSplitRow
                    }
                    if canPayFromBank || canSplit || couldBePay || unlink || canOneOff || offersNewOnes
                        || incomeAlways != nil { APSeparator(afterFace: false) }
                }
                if canPayFromBank {
                    Button { payingFromBank = true } label: {
                        row(title: t.bankId == nil ? "Pay from a piggy bank" : "Paid from a piggy bank",
                            chevron: true, icon: "banknote")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    if canSplit || couldBePay || unlink || canOneOff || offersNewOnes { APSeparator(afterFace: false) }
                }
                // No Split into parts on money in (2026-11-09): a payback picks
                // everything it paid back on Who paid you back?.
                if canSplit {
                    Button { splitting = true } label: {
                        row(title: "Split with others", chevron: true, icon: "person.2")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if canFindPayback {
                    if canSplit { APSeparator(afterFace: false) }
                    Button { paidBackStep = .find } label: {
                        row(title: "Mark as paid back", sub: "Find the money that paid it back", chevron: true,
                            icon: "arrow.uturn.backward")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if couldBePay {
                    if canSplit || canFindPayback { APSeparator(afterFace: false) }
                    Button { asking = Asking(step: .cadence) } label: {
                        if let pay = t.regularPay {
                            // T-37: "Every 2 weeks · next on Fri, Nov 21".
                            row(title: "Regular pay",
                                sub: [Format.cadence(pay.cadence ?? ""),
                                      pay.next.map { "next on \(Format.weekdayDay($0))" }]
                                    .compactMap { $0 }.joined(separator: " · "),
                                chevron: true, icon: "briefcase")
                        } else {
                            row(title: "This is my regular pay", chevron: true, icon: "briefcase")
                        }
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if unlink {
                    if canSplit || canFindPayback || couldBePay { APSeparator(afterFace: false) }
                    Button { unlinkingRefund = true } label: {
                        row(title: "Unlink refund", chevron: true, icon: "link")
                    }

                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if canLink {
                    // Link transfers (2026-11-22): a leg with no other end
                    // paired, or the legs it's linked with.
                    if canSplit || canFindPayback || couldBePay || unlink { APSeparator(afterFace: false) }
                    Button { linking = true } label: {
                        row(title: t.links.isEmpty ? "Link to another transfer" : "Linked transfers",
                            sub: t.links.isEmpty ? nil : Format.shortList(t.links.compactMap(\.accountName)),
                            chevron: true, icon: "link")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if canOneOff {
                    if canSplit || canFindPayback || couldBePay || unlink || canLink { APSeparator(afterFace: false) }
                    Toggle(isOn: Binding(get: { oneOff ?? t.oneOff },
                                         set: { on in Task { await setOneOff(on) } })) {
                        // T-42 (G1-TxNote): what leaving it out does, under the title.
                        HStack(spacing: 12) {
                            CFIcon(symbol: "1.circle")
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Exclude from usual month").font(Nacre.body).foregroundColor(Pearl.ink)
                                if let line = t.oneOffLine?.line, oneOff ?? t.oneOff {
                                    Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                        .fixedSize(horizontal: false, vertical: true)
                                }
                            }
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                    .accessibilityHint("Leaves it out of your usual month")
                }
                if offersNewOnes {
                    if canSplit || canFindPayback || couldBePay || unlink || canLink || canOneOff { APSeparator(afterFace: false) }
                    alwaysToggle(sub: nil)
                }
                if let payer = incomeAlways {
                    if canSplit || canFindPayback || couldBePay || unlink || canLink || canOneOff || offersNewOnes { APSeparator(afterFace: false) }
                    incomeAlwaysToggle(payer)
                }
                if canPayFromBank {
                    APSeparator(afterFace: false)
                    Toggle(isOn: Binding(get: { billKey != nil },
                                         set: { on in if on { addingBill = true } else { Task { await removeBill() } } })) {
                        HStack(spacing: 12) {
                            CFIcon(symbol: "calendar")
                            Text("Regular bill").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).frame(minHeight: 64)
                    .accessibilityHint("Adds it to your bills")
                }
            }
        }
    }

    /// Income's Always (2026-11-08): new ones from the payer count as this
    /// kind. The one label every page uses (2026-11-21), the payer in the
    /// VoiceOver hint.
    private func incomeAlwaysToggle(_ payer: String) -> some View {
        Toggle(isOn: Binding(get: { incomeAlwaysOn ?? (t.incomeRule?.on == true) },
                             set: { on in Task { await setIncomeAlways(on) } })) {
            HStack(spacing: 12) {
                CFIcon(symbol: "repeat")
                Text("Always for this merchant").font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .tint(Pearl.action)
        .disabled(busy)
        .padding(.horizontal, 16).frame(minHeight: 64)
        .accessibilityHint("New ones from \(payer) count as \(Self.kindName(t.incomeType))")
    }

    /// A tile on the category page only changes what's on this page, so Yes can
    /// say it. The guess itself goes back to being the guess.
    private func choose(_ name: String) {
        sorting = nil
        // Picking Pearl's guess is still a choice: it isn't dotted any more.
        pickedGuess = name == (guessing?.label ?? t.label)
        chosenCategory = pickedGuess ? nil : name
        let category = cardCategory
        holdForCard {
            $0.answer = nil
            $0.category = chosenCategory
            // A held split keeps going with the category she picks (T-98s).
            $0.label = $0.split.map { $0.label(category) } ?? chosenCategory
        }
    }

    /// The category a held split counts toward: hers, or the card's guess.
    private var cardCategory: String {
        chosenCategory ?? (guessing?.ask.kind == .category ? guessing?.ask.item.guess?.text : nil)
            ?? t.category ?? "Other"
    }

    /// T-98s (SPLIT-06): nothing is saved; the card asks "Groceries, split with Sam?".
    private func holdSplit(_ body: [String: Any], mine: Double) {
        splitting = false
        let split = CardSplit.held(body, mine: mine, total: t.splitBase)
        let category = cardCategory
        holdForCard {
            $0.split = split
            $0.answer = nil
            $0.category = chosenCategory
            $0.label = split.label(category)
        }
    }

    /// An edit for the Quick sort card to agree to.
    private func holdForCard(_ change: (inout CardDraft) -> Void) {
        guard let guessing = guessing, let onDraft = guessing.onDraft else { return }
        var draft = held ?? guessing.draft
        change(&draft)
        held = draft
        onDraft(draft)
    }

    /// Yes on a category she chose: saved the way the page was opened.
    private func answer(with name: String, always: Bool) {
        guard let guessing = guessing else {
            Task { await change(to: name, remember: always) }
            return
        }
        if guessing.ask.kind == .category {
            guessing.onAnswer(.category(t.id, name: name, remember: always))
        } else {
            guessing.onAnswer(.mark(t.id, ["case": "spending", "category": name, "remember": always]))
        }
    }

    /// Always on a row that's already sorted: new ones go where this one is.
    private func setAlways(_ on: Bool) async {
        let category = t.label
        let merchant = t.merchant
        await run {
            let _: OK = try await app.api.put("api/transactions/\(t.id)/always", ["on": on])
            return on ? "Always \(category) for \(merchant)." : "No rule for \(merchant) now."
        }
    }

    /// Off: it leaves her bills.
    private func removeBill() async {
        guard let key = billKey else { return }  // plain: APIClient encodes it (TEST-33)
        struct Removed: Decodable {}
        await run {
            let _: Removed = try await app.api.delete("api/income-bills/bills/\(key)")
            return "Removed from your bills."
        }
    }

    // MARK: Details

    @ViewBuilder private var details: some View {
        section("Details")
        APCard {
            // T-75's Whose was it? is in Options now (S-01j, SPLIT-08).
            Button { editingNote = true } label: {
                if t.myNote.isEmpty {
                    row(title: "Add a note", placeholder: true, chevron: true, icon: "square.and.pencil")
                } else {
                    row(title: t.myNote, sub: "Note", chevron: true, icon: "square.and.pencil")
                }
            }
            .buttonStyle(.plain)
            if let trip = t.trip, !showsCategoryCard {
                // TR-06 (1327:6382): the trip it's in, which opens the trip's
                // page (TR-02); under the category when the page has that card.
                APSeparator(afterFace: false)
                NavigationLink { TripPage(id: trip.id) } label: {
                    row(title: "\(trip.name) · \(Format.span(trip.start, trip.end))", chevron: true, icon: "tag")
                }
                .buttonStyle(.plain)
                .accessibilityHint("Opens the trip")
            }
            // A refund's tags are its purchase's (T-41), and income has none (T-37).
            if Features.tags && t.refundOf == nil && !isIncome {
                APSeparator(afterFace: false)
                Button { editingTags = true } label: {
                    if t.tags.isEmpty {
                        row(title: "Add tags", placeholder: true, chevron: true, icon: "tag")
                    } else {
                        row(title: t.tags.map { "#" + $0 }.joined(separator: "  "), sub: "Tags", chevron: true, icon: "tag")
                    }
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// Put it back, and Delete under one added by hand. Income's "Not income?"
    /// is the Income category itself now (2026-11-08).
    @ViewBuilder private var footerAction: some View {
        if !t.excluded.isEmpty && t.transfer == nil {
            // Left out (T-56, T-77's Leave out): put it back in her numbers.
            // A real button (product owner, 2026-11-20), A+ `.btn2`, not a
            // line of text at the foot of the page.
            Button("Put it back") { Task { await putBack() } }
                .buttonStyle(APSecondaryButtonStyle())
                .padding(.top, 12)
                .disabled(busy)
        }
        if t.manual {
            // G1-PConfirm (T-03x): a red entry row on its own card.
            APCard {
                PearlDestructiveRow(symbol: "trash", title: "Delete \(t.merchant)") { deleting = true }
                    .accessibilityIdentifier("Delete transaction")
            }
                .padding(.top, 12)
                .disabled(busy)
                .sheet(isPresented: $deleting) {
                    // T-03x (TEST-06): a Pearl sheet; T-03x2 if it fails.
                    PearlConfirmSheet(face: t.merchant, overline: "Added by hand", title: "Delete \(t.merchant)?",
                                      message: "You added it by hand, so it comes out of your numbers. This can’t be undone.",
                                      primary: "Delete \(t.merchant)", busyLabel: "Deleting…", secondary: "Keep it",
                                      failure: "Couldn’t delete \(t.merchant). Nothing changed. Try again.",
                                      onClose: { deleting = false }) {
                        let _: OK = try await app.api.delete("api/transactions/\(t.id)")
                        deleting = false
                        app.changed()
                        dismiss()
                    }
                }
        }
    }

    // MARK: A transfer (TF-01, POLISH-01; was T-05)

    /// The day each end moved.
    private func legDates(_ transfer: Transaction.Transfer) -> (out: String, in: String) {
        (transfer.from == t.account ? t.date : (transfer.otherDate ?? t.date),
         transfer.to == t.account ? t.date : (transfer.otherDate ?? t.date))
    }

    /// "Thu, Nov 12 → Fri, Nov 13", or the one day.
    private func transferDates(_ transfer: Transaction.Transfer) -> String {
        let (out, into) = legDates(transfer)
        let a = Format.weekdayDay(out), b = Format.weekdayDay(into)
        return a == b ? a : "\(a) \u{2192} \(b)"
    }

    /// TF-01 (1389:24632 / 1389:24833; THL-292, THL-181): How it counts, both
    /// ends with how far apart, and "This isn't a transfer", which asks first
    /// (TF-01c). The red link under a 120 pt gap is gone.
    @ViewBuilder private func transferLegs(_ transfer: Transaction.Transfer) -> some View {
        if t.inflow, transfer.joint != nil, transfer.otherId != nil {
            OwnBody { jointLegs(transfer) }
        } else if mineOnlyIn(transfer) {
            OwnBody { mineLegs(transfer) }
        } else {
            OwnBody { plainLegs(transfer) }
        }
    }

    /// TP-01 (G2b-JointIn, rethought, approved): the two legs on one line,
    /// "Joint ••1123 → Chequing ••4417" over "Same day", on one card; "Mom
    /// paid me back" is the page's Primary and This isn't a transfer the
    /// quiet link under it (pagePrimary).
    @ViewBuilder private func jointLegs(_ transfer: Transaction.Transfer) -> some View {
        howItCounts
        legsLine(transfer)
            .padding(.top, 8)
            .sheet(isPresented: $unpairing) { unpairSheet(transfer) }
    }

    /// "Between your accounts ›", opening What was this? (product owner,
    /// 2026-11-21: a transfer on a joint account gave no way to say it was
    /// something else; only the plain transfer page had this card).
    @ViewBuilder private var howItCounts: some View {
        section("How it counts")
        APCard {
            Button { sorting = sortAsk(.transfer) } label: {
                categoryRow(symbol: "", title: "Between your accounts", sub: nil, systemImage: "arrow.left.arrow.right")
            }
            .buttonStyle(.plain)
            .disabled(busy)
            .accessibilityHint("Changes what it was")
        }
    }

    /// TP-05: the money in of a transfer between two accounts only hers.
    private func mineOnlyIn(_ transfer: Transaction.Transfer) -> Bool {
        t.inflow && transfer.mineOnly == true
    }

    /// TP-05 (G2b-JointIn, rethought, approved): no options list. The legs
    /// on one line, "Both accounts are only yours." under them, and This
    /// isn't a transfer as the one quiet link at the foot (pagePrimary).
    @ViewBuilder private func mineLegs(_ transfer: Transaction.Transfer) -> some View {
        howItCounts
        VStack(spacing: 0) {
            legsLine(transfer)
            NoPaidBackCallout().padding(.top, 10)
        }
        .padding(.top, 8)
        .sheet(isPresented: $unpairing) { unpairSheet(transfer) }
    }

    /// "Joint ••1123 → Chequing ••4417" over "Same day", ⇄ on its disc, on
    /// one card (TP-01, TP-05).
    private func legsLine(_ transfer: Transaction.Transfer) -> some View {
        let (outDate, inDate) = legDates(transfer)
        return APCard {
            HStack(spacing: 12) {
                CFIcon(symbol: "arrow.left.arrow.right")
                VStack(alignment: .leading, spacing: 2) {
                    Text(route(transfer)).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Text(apartWords(outDate, inDate)).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer(minLength: 0)
                // The ⋯ (2026-11-22): Unlink from transfer, both legs.
                moreButton { legMenu = LegMenu(id: "pair", account: route(transfer), ids: legIds(transfer)) }
            }
            .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
            .accessibilityElement(children: .combine)
            .accessibilityLabel("From \(transfer.from) to \(transfer.to), \(apartWords(outDate, inDate))")
        }
    }

    @ViewBuilder private func plainLegs(_ transfer: Transaction.Transfer) -> some View {
        let (outDate, inDate) = legDates(transfer)
        section("How it counts")
        APCard {
            // Opens What was this? to change it.
            Button { sorting = sortAsk(.transfer) } label: {
                categoryRow(symbol: "", title: "Between your accounts", sub: nil, systemImage: "arrow.left.arrow.right")
            }
            .buttonStyle(.plain)
            .disabled(busy)
            .accessibilityHint("Changes what it was")
        }
        // G1-TxMore: MOVED with how far apart on the right, in `link`.
        HStack {
            APSectionLabel(text: "Moved")
            Spacer(minLength: 8)
            Text(apartWords(outDate, inDate))
                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline)).foregroundColor(Pearl.link)
                .padding(.trailing, 4)
        }
        .padding(.top, 16)
        SolidCard {
            // The ⋯ beside each leg (product owner, 2026-11-22) unlinks that
            // leg: its row(s) come off the line and stand on their own.
            let ids = legIds(transfer)
            leg(account: transfer.from, sub: "Out · \(Format.weekdayDay(outDate))") {
                legMenu = LegMenu(id: "out", account: transfer.from, ids: [ids[0]])
            }
            // A chain (2026-11-22): the accounts it passed through, between.
            ForEach(Array((transfer.via ?? []).enumerated()), id: \.offset) { k, account in
                APSeparator()
                leg(account: account, sub: "Through") {
                    legMenu = LegMenu(id: "through\(k)", account: account,
                                      ids: Array(ids[min(2 * k + 1, ids.count - 1)...min(2 * k + 2, ids.count - 1)]))
                }
            }
            APSeparator()
            leg(account: transfer.to, sub: "In · \(Format.weekdayDay(inDate))") {
                legMenu = LegMenu(id: "in", account: transfer.to, ids: [ids[ids.count - 1]])
            }
        }
        section("Options")
        APCard {
            if !t.links.isEmpty {
                // Linked by her (2026-11-22): the sheet shows the legs, and Unlink.
                Button { linking = true } label: {
                    row(title: "Linked transfers", sub: Format.shortList(t.links.compactMap(\.accountName)),
                        chevron: true, icon: "link")
                }
                .buttonStyle(.plain)
                .disabled(busy)
            } else {
                Button { unpairing = true } label: {
                    // TEXT-01: no second line; the sheet asks.
                    row(title: "This isn’t a transfer", chevron: true, icon: "link")
                }
                .buttonStyle(.plain)
                .disabled(busy)
                .accessibilityElement(children: .combine)
            }
        }
        .sheet(isPresented: $unpairing) { unpairSheet(transfer) }
    }

    /// TF-01c (1390:2451 / 1390:2586): a Pearl sheet, not an alert.
    /// G1-TxSheets (TF-01c): the transfer as the who, ⇄ on a quiet disc.
    private func unpairSheet(_ transfer: Transaction.Transfer) -> some View {
        PearlConfirmSheet(overline: "Transfer · \(Format.amount(t.amount))", title: "This isn’t a transfer?",
                          who: .init(name: "Transfer", amount: Format.amount(t.amount), tone: Pearl.muted,
                                     sub: route(transfer), symbol: "arrow.left.arrow.right"),
                          message: "Pearl stops pairing them and asks what each one was.",
                          primary: "Not a transfer", secondary: "Keep it a transfer",
                          onClose: { unpairing = false }) {
            unpairing = false
            otherSide = transfer.otherId
            try? await Task.sleep(nanoseconds: 450_000_000)
            sorting = sortAsk(.transfer)
        }
    }

    /// RS-01 (2026-11-24). Both act once the sheet has gone.
    @ViewBuilder private var recurringSheet: some View {
        if let rule = t.recurringRule {
            RecurringRowSheet(rule: rule,
                              onNotThisOne: { recurringMenu = false; Task { await notRecurring() } },
                              onStop: { recurringMenu = false; Task { await stopRecurringRule() } },
                              onClose: { recurringMenu = false })
        }
    }

    /// POST …/not-recurring: this one keeps its category as her own answer (RS-01a).
    private func notRecurring() async {
        await run {
            let reply: MarkReply? = try await write("POST", "api/transactions/\(t.id)/not-recurring")
            if let reply = reply { app.say("Left out of the rule", undo: undoLater(reply.undo)) }
            return nil
        }
    }

    /// DELETE …/recurring-transfers/<rule>: as Profile's Stop treating it as recurring (RS-01b).
    private func stopRecurringRule() async {
        guard let rule = t.recurringRule?.id ?? t.recurring else { return }
        await run {
            let reply: MarkReply? = try await write("DELETE", "api/recurring-transfers/\(rule)")
            if let reply = reply { app.say("Rule stopped", undo: undoLater(reply.undo)) }
            return nil
        }
    }

    /// The server's undo payload as the toast's Undo.
    private func undoLater(_ payload: JSONValue?) -> (() async throws -> Void)? {
        payload.map { payload in {
            guard let body = payload.any as? [String: Any] else { return }
            let _: OK = try await app.api.post("api/transactions/undo", body)
        } }
    }

    /// POST …/unpair with the leg's transactions: they come off the line;
    /// the page reloads and the toast carries Undo.
    private func unpairLegs(_ ids: [String]) async {
        await run {
            let reply: MarkReply? = try await write("POST", "api/transactions/\(t.id)/unpair", ["ids": ids])
            if let reply = reply {
                app.say(reply.title ?? "Unlinked.", undo: reply.undo.map { payload in {
                    guard let body = payload.any as? [String: Any] else { return }
                    let _: OK = try await app.api.post("api/transactions/undo", body)
                } })
            }
            return nil
        }
    }

    /// TP-01's Primary: PB-30 with the joint account's other owner picked
    /// (TP-03); with more than one, PP-01 asks who first (Who paid? as tiles).
    private func startJointPayback(_ joint: Transaction.Transfer.JointFrom, out: String) {
        jointStart = JointPaybackStart(deposit: PartsDeposit(id: t.id, name: t.merchant, amount: t.amount, date: t.date),
                                       people: joint.people, account: joint.account, out: out)
    }

    /// TF-01: an end of the transfer, as a transaction row with no amount
    /// (the hero already says it).
    private func leg(account: String, sub: String, more: (() -> Void)? = nil) -> some View {
        HStack(spacing: 12) {
            Initials(name: account)
            VStack(alignment: .leading, spacing: 2) {
                Text(account).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 0)
            if let more = more { moreButton(more) }
        }
        .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
        .accessibilityElement(children: .combine)
    }

    /// The ⋯ at a leg's right edge (2026-11-22).
    private func moreButton(_ action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Image(systemName: "ellipsis").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.muted)
                .frame(width: 32, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .padding(.trailing, -8)
        .accessibilityLabel("More")
        .accessibilityHint("Unlink from transfer")
    }

    /// The transactions behind the Moved card's legs, in order (2026-11-22):
    /// a chain's `legs`; a pair's departure then arrival.
    private func legIds(_ transfer: Transaction.Transfer) -> [String] {
        if let legs = transfer.legs, legs.count >= 2 { return legs }
        let other = transfer.otherId ?? t.id
        return transfer.from == t.account ? [t.id, other] : [other, t.id]
    }

    /// "1 day apart", "Same day" (G1-TxMore: beside MOVED).
    /// "Chequing → Savings → Family": every account the money passed through.
    private func route(_ transfer: Transaction.Transfer) -> String {
        ([transfer.from] + (transfer.via ?? []) + [transfer.to]).joined(separator: " \u{2192} ")
    }

    private func apartWords(_ out: String, _ into: String) -> String {
        let days = abs(Calendar.current.dateComponents([.day], from: Format.localDay(out) ?? Date(),
                                                       to: Format.localDay(into) ?? Date()).day ?? 0)
        return days == 0 ? "Same day" : days == 1 ? "1 day apart" : "\(days) days apart"
    }

    // MARK: Parts

    /// A+ kit `.label`: caps outside the card, 24 above (the page's 8 and
    /// 16 more) and 8 below. TEST-14: it grows with Dynamic Type and wraps.
    private func section(_ text: String) -> some View {
        APSectionLabel(text: text)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 16)
    }

    /// A+ kit `.row.noface`: the 36 pt icon, the title (17) over its line
    /// (15 muted), the chevron; 64 high. "Add a note" is in ink (G1-TxMore).
    private func row(title: String, sub: String? = nil, placeholder: Bool = false, chevron: Bool,
                     value: String? = nil, icon: String? = nil) -> some View {
        HStack(spacing: 12) {
            if let icon = icon { CFIcon(symbol: icon) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .lineLimit(2)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 8)
            if let value = value {
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            }
            if chevron { CFChevron() }
        }
        .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
        .contentShape(Rectangle())
    }

    /// This transaction as a question for What was this?.
    private func sortAsk(_ kind: Question) -> Ask {
        let brief = BriefTransaction(id: t.id, date: t.date, merchant: t.merchant, description: t.description,
                                     amount: t.inflow ? -abs(t.amount) : abs(t.amount), accountName: t.account,
                                     accountId: t.accountId, category: t.category, skipped: nil, likely: nil)
        return Ask(kind: kind, item: Review.Item(key: "sort:" + t.id, txn: brief, skipped: nil))
    }

    /// The question Needs a look has for it (Same purchase?, Who sent this?…),
    /// or What was this? if it's gone by now.
    private func openQuestion() async {
        let review: Review? = try? await app.api.get("api/review")
        guard let ask = review?.asks.first(where: { $0.t.id == t.id }) else {
            sorting = sortAsk(t.inflow ? .moneyIn : .transfer)
            return
        }
        if ask.item.rest != nil { parting = deposit(rest: true) }
        // S-21u's question on its own page: S-35c, not What was this?.
        else if ask.item.credit != nil { crediting = Crediting(id: t.id) }
        // S-21x's question on its own page: S-11x for the whole amount;
        // S-21xm's (THL-301): S-11xm for the extra part.
        else if let extra = ask.item.extra { partsExtra = extra; parting = deposit(rest: false).part(of: extra) }
        else { sorting = ask }
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

    private struct Cases: Decodable {
        let learnable: Bool?; let mixed: Bool?; let hasRule: Bool?
        enum CodingKeys: String, CodingKey { case learnable, mixed; case hasRule = "has_rule" }
    }
    private struct Bill: Decodable {
        let billKey: String?
        enum CodingKeys: String, CodingKey { case billKey = "bill_key" }
    }

    /// Everything the page needs, asked for together and shown at once
    /// (2026-11-08): one after another, the page changed four times as each
    /// answer came in.
    private func load() async {
        let id = detail?.id ?? transaction.id
        let api = app.api
        async let fullReply: Transaction? = try? api.get("api/transactions/\(id)")
        async let casesReply: Cases? = guessing == nil ? (try? api.get("api/transactions/\(id)/cases")) : nil
        async let owedReply: OwedOverview? = recent.isEmpty && !transaction.inflow ? (try? api.get("api/owed")) : nil
        async let billReply: Bill? = canPayFromBank ? (try? api.get("api/transactions/\(id)/bill")) : nil
        let (full, cases, owed, bill) = await (fullReply, casesReply, owedReply, billReply)
        if let full = full {
            detail = full
            oneOff = nil
            loadFailed = false
        } else if detail == nil {
            // S-04ue: the split card says it couldn't load, with Try again.
            loadFailed = true
        }
        if canPayFromBank { billKey = bill?.billKey }
        await loadPaybackQuestion()
        if guessing == nil {
            self.cases = cases ?? Cases(learnable: false, mixed: false, hasRule: false)
        }
        // People she's split with before, for Who was it with? (S-02).
        if let owed = owed {
            var names: [String] = []
            for n in owed.owesYou.map(\.name) + owed.paidBack.compactMap(\.name) where !names.contains(n) {
                names.append(n)
            }
            recent = names
        }
    }

    /// Does a change, then reloads. What it returns is said in the toast
    /// (POLISH-01: it was a plain line left under the page, "Yours.").
    private func run(_ work: () async throws -> String?) async {
        busy = true
        defer { busy = false }
        do {
            if let said = try await work() {
                withAnimation { splitToast = nil; toast = (said, nil) }
            }
            error = nil
            await load()
            // What it changed goes to the rest of the app (rows swapped into
            // lists, the Allowance, the badge); with no envelope, a reload.
            app.apply(lastChanged, by: screenKey)
            lastChanged = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// A write through the outbox (perf rehaul, 2026-11-19): sent once with
    /// an op id, or queued when the server can't be reached (nil, and what
    /// the page shows stays). Its `changed` is noted for `run`/`settled`.
    private func write<T: Decodable>(_ method: String, _ path: String, query: [String: String] = [:],
                                     _ body: [String: Any]? = nil) async throws -> T? {
        guard let sent: Outbox.Sent<T> = try await app.outbox.send(method, path, query: query, body) else { return nil }
        lastChanged = sent.changed
        return sent.body
    }

    /// After a split change: the toast at once, the page's own reload under
    /// it, and what the write changed applied to the rest of the app.
    private func settled(_ text: String, undo: (() async throws -> String?)?) async {
        showSplit(text, undo: undo)
        await load()
        app.apply(lastChanged, by: screenKey)
        lastChanged = nil
    }

    /// An answer from What was this? (or its other questions): the toast
    /// says what it did, with the server's Undo.
    private func answered(_ answer: ReviewAnswer) async {
        await run {
            do {
                let reply = try await answer.send(app.api)
                withAnimation { splitToast = nil; toast = (reply.title ?? answer.done, undoing(reply.undo)) }
            } catch let e where e.whoPaid != nil {
                // Nothing saved: ask who, once the answer's sheet has gone (2026-11-16).
                try? await Task.sleep(nanoseconds: 450_000_000)
                whoPaid = e.whoPaid
            }
            return nil
        }
    }

    /// TF-01c: What was this? for the transfer's other end.
    private func askOtherSide(_ id: String) async {
        guard let other: Transaction = try? await app.api.get("api/transactions/\(id)") else { return }
        let brief = BriefTransaction(id: other.id, date: other.date, merchant: other.merchant,
                                     description: other.description,
                                     amount: other.inflow ? -abs(other.amount) : abs(other.amount),
                                     accountName: other.account, accountId: other.accountId,
                                     category: other.category, skipped: nil, likely: nil)
        // The sheet that just closed has to be gone first.
        try? await Task.sleep(nanoseconds: 450_000_000)
        sorting = Ask(kind: other.inflow ? .moneyIn : .transfer,
                      item: Review.Item(key: "sort:" + other.id, txn: brief, skipped: nil))
    }

    /// T-41b (G1-TxSheets): "Unlink?" with ✕, "Amazon refund · +$68.00 ·
    /// Nov 13", "It goes back to Needs a look.", Unlink and Keep linked.
    private var refundUnlinkSheet: some View {
        PearlConfirmSheet(overline: "Refund", title: "Unlink?",
                          who: .init(name: "\(t.merchant) refund", amount: "+" + Format.amount(t.amount),
                                     tone: Pearl.moneyIn, sub: Format.short(t.date)),
                          message: "It goes back to Needs a look.",
                          primary: "Unlink", secondary: "Keep linked",
                          onClose: { unlinkingRefund = false }) {
            unlinkingRefund = false
            await unlinkRefund()
        }
    }

    /// Undo for a server change, when it sent one.
    private func undoing(_ payload: JSONValue?) -> (() -> Void)? {
        payload.map { p in { Task { await undo(p) } } }
    }

    private func undo(_ payload: JSONValue) async {
        guard let body = payload.any as? [String: Any] else { return }
        withAnimation { toast = nil }
        await run {
            let _: OK = try await app.api.post("api/transactions/undo", body)
            return "Undone."
        }
    }

    /// Yes: Pearl's guess was right. T-38b: "Dining out · Undo".
    private func confirm(said: String? = nil) async {
        let label = t.label
        // The chip reads as hers at once (perf rehaul); back if refused.
        let before = detail
        withAnimation(.easeInOut(duration: 0.2)) { detail = t.guessConfirmed() }
        busy = true
        defer { busy = false }
        do {
            let sent: Outbox.Sent<CategoryChange>? = try await app.outbox.send(
                "PUT", "api/transactions/\(t.id)/confirm", rollback: { detail = before })
            withAnimation { toast = (said ?? sent?.body.category ?? label, undoing(sent?.body.undo)) }
            error = nil
            if let sent = sent { take(sent.changed) }
        } catch {
            withAnimation { detail = before }
            self.error = app.handle(error)
        }
    }

    /// A category write's `changed` taken in: this row's sorting from the
    /// server's own row (the page keeps its split and the rest), the app
    /// told. No envelope: the page and everything else reload.
    private func take(_ changed: Changed?) {
        guard let changed = changed else {
            Task { await load() }
            app.changed()
            return
        }
        if let row = changed.rows.first(where: { $0.id == t.id }), var now = detail {
            now.category = row.category
            now.chip = row.chip
            now.suggested = row.suggested
            now.rule = row.rule
            withAnimation(.easeInOut(duration: 0.2)) { detail = now }
        }
        app.apply(changed, by: screenKey)
    }

    /// Yes from the list: every open guess from the merchant, and a rule.
    private func always() async {
        let label = t.label
        await run {
            let reply: QuickSortStep = try await app.api.put("api/quick-sort/\(t.id)",
                ["action": "right", "every": false, "rows": [String](), "new_ones": true])
            withAnimation {
                toast = (QuickSortStep.always(label, sorted: (reply.also?.count ?? 0) + 1), undoing(reply.undo))
            }
            return nil
        }
    }

    /// A new category: this row, and the rule when Always is on. Other rows
    /// from the merchant stay as they are.
    private func change(to name: String, remember: Bool) async {
        let merchant = t.merchant
        // Shown at once (perf rehaul): the page as it reads once sorted;
        // the server's row settles it, a refusal puts it back.
        let before = detail
        withAnimation(.easeInOut(duration: 0.2)) { detail = t.sorted(as: name) }
        busy = true
        defer { busy = false }
        do {
            let sent: Outbox.Sent<QuickSortStep>? = try await app.outbox.send(
                "PUT", "api/quick-sort/\(t.id)",
                ["action": "category", "category": name, "every": false, "rows": [String](), "new_ones": remember],
                rollback: { detail = before })
            let said = remember ? "Always \(name) for \(merchant)." : "Moved to \(name)."
            withAnimation { splitToast = nil; toast = (said, nil) }
            error = nil
            if let sent = sent { take(sent.changed) }
        } catch {
            withAnimation { detail = before }
            self.error = app.handle(error)
        }
    }

    private func putBack() async {
        await run {
            let _: OK = try await app.api.delete("api/transactions/\(t.id)/exclude")
            return "Back in your numbers."
        }
    }

    /// T-80: her name for the merchant; empty goes back to the bank's.
    private func rename(to name: String) async {
        let bank = t.bankMerchant ?? t.merchant
        await run {
            let _: OK = try await app.api.put("api/merchants/name", ["merchant": bank, "name": name])
            return name.isEmpty ? "\(bank) uses the bank’s name again." : "\(bank) is \(name) now."
        }
    }

    /// Always for the payer, on income: their deposits count as this kind.
    private func setIncomeAlways(_ on: Bool) async {
        incomeAlwaysOn = on
        struct Reply: Decodable { let title: String? }
        await run {
            let reply: Reply = try await app.api.put("api/transactions/\(t.id)/income-always", ["on": on])
            return reply.title
        }
        incomeAlwaysOn = nil
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

    // MARK: REFRESH-02 — S-40's choices, and the S-44 toasts

    /// What she picked on a person's S-40 (it has gone by now).
    /// S-48e: POST the new answer; the toast says what it is now.
    private func answerAgain(_ p: Transaction.Splitting.Person, _ answer: SplitSheet.Answer) async {
        let word: String
        switch answer {
        case .ask: word = "ask"
        case .theirShare: word = "share"
        case .iOwe: word = "owe"
        case .gift: word = "gift"
        }
        struct Reply: Decodable { let toast: String? }
        do {
            let reply: Reply = try await app.api.post("api/transactions/\(t.id)/split/answer",
                                                       ["name": p.name, "answer": word])
            await settled(reply.toast ?? "Changed", undo: nil)
        } catch {
            showFailed(app.handle(error) ?? "Couldn’t change that. Nothing changed.") { Task { await answerAgain(p, answer) } }
        }
    }

    /// AP-OwedPerson: the choice from Owed to you, once.
    private func runStartChoice() {
        guard let start = startChoice, !ranStartChoice,
              let p = (detail ?? transaction).splitting?.people.first(where: { $0.name == start.name }) else { return }
        ranStartChoice = true
        choose(p, start.choice)
    }

    private func choose(_ p: Transaction.Splitting.Person, _ choice: PersonChoice) {
        switch choice {
        case .markPaid: marking = p
        case .remind: reminding = p
        case .letGo: lettingGo = p
        case .changeShare: changingShare = p
        case .changeAnswer: changingAnswer = p
        case .view(let link): if let id = link.view?.id { Task { await open(id) } }
        case .unlink(let link): unlinkingLink = link
        // PB-42 (Paybacks & undo): S-40c's How much and Which purchase.
        case .howMuch(let link): linkStart = .howMuch; linkOptions = link
        case .whichPurchase(let link): linkStart = .which; linkOptions = link
        case .undoLetGo:
            // S-40d → S-44e at once; its Undo lets it go again.
            Task {
                do {
                    let said = try await undoLetGo(p)
                    await settled(said ?? "\(p.name) owes you again", undo: { _ = try await letGo(p); return nil })
                } catch {
                    showFailed("Couldn’t undo that. Nothing changed.") { choose(p, .undoLetGo) }
                }
            }
        case .remove:
            // Someone who paid is asked first (S-03fr); anyone else goes at once (S-44d).
            if p.paid >= 0.005 { removingPerson = p; return }
            Task {
                do {
                    let (title, undo) = try await removeFromSplit(p)
                    await settled(title, undo: undo)
                } catch {
                    showFailed("Couldn’t remove \(p.name). Nothing changed.") { choose(p, .remove) }
                }
            }
        // Her own row's (PB-20); someone else's row has Mark paid back.
        case .findPaidBack: paidBackStep = .find
        }
    }

    /// An S-44 toast; Undo runs `undo`, then says what it returns (S-44g
    /// "Linked again"), or S-44h if it fails, with Try again.
    private func showSplit(_ text: String, undo: (() async throws -> String?)?) {
        withAnimation {
            toast = nil
            splitToast = PearlToast.Model(text: text, action: undo == nil ? nil : "Undo",
                                          run: undo.map { work in { Task { await runUndo(work) } } })
        }
    }

    private func runUndo(_ work: @escaping () async throws -> String?) async {
        withAnimation { splitToast = nil }
        do {
            let said = try await work()
            await load()
            app.changed()
            if let said = said { withAnimation { splitToast = PearlToast.Model(text: said) } }
        } catch {
            // S-44h: "Couldn’t undo that. Nothing changed." · Try again.
            showFailed("Couldn’t undo that. Nothing changed.") { Task { await runUndo(work) } }
        }
    }

    private func showFailed(_ text: String, retry: @escaping () -> Void) {
        withAnimation {
            toast = nil
            splitToast = PearlToast.Model(text: text, action: "Try again", failed: true, run: retry)
        }
    }

    private func postUndo(_ payload: JSONValue) async throws {
        guard let body = payload.any as? [String: Any] else { return }
        let _: OK = try await app.api.post("api/transactions/undo", body)
    }

    /// A split change's toast (S-44c, S-44e).
    private struct Toasted: Decodable { let title: String?; let toast: String?; let undo: JSONValue? }

    @discardableResult
    private func letGo(_ p: Transaction.Splitting.Person) async throws -> String {
        let reply: Toasted? = try await write("POST", "api/transactions/\(t.id)/split/let-go", ["name": p.name])
        return reply?.toast ?? reply?.title ?? "Let go"
    }

    private func undoLetGo(_ p: Transaction.Splitting.Person) async throws -> String? {
        let reply: Toasted? = try await write("DELETE", "api/transactions/\(t.id)/split/let-go", query: ["name": p.name])
        return reply?.toast ?? reply?.title
    }

    /// S-40's Remove (handoff 1096:4498): PUT …/split without them, their
    /// share hers (SPLIT-16 rules on the server). Gives S-44d's toast and
    /// its Undo. The only person on it: the split goes, and Undo puts it back.
    private func removeFromSplit(_ p: Transaction.Splitting.Person) async throws -> (String, () async throws -> String?) {
        guard let split = t.splitting else { throw SplitMenuError(words: "That isn’t split anymore.") }
        // JOINT-B: of her part of a joint purchase.
        let whole = t.splitBase
        func body(_ people: [Transaction.Splitting.Person]) -> [String: Any] {
            if split.unsure {
                // SPLIT-C (S-03fu): still Not sure yet, without them.
                return ["mode": "unknown", "people": people.map { ["name": $0.name] }]
            }
            let shares = people.map { ["name": $0.name, "amount": $0.share] as [String: Any] }
            let you = ((whole - people.map(\.share).reduce(0, +)) * 100).rounded() / 100
            return ["mode": "amount", "include_me": you >= 0.005, "you": max(0, you), "people": shares]
        }
        let kept = split.people.filter { $0.name != p.name }
        // S-44d (REFRESH-03): "Priya removed", with Undo.
        let title = "\(p.name) removed"
        do {
            if kept.isEmpty {
                struct Gone: Decodable { let undo: JSONValue? }
                let gone: Gone? = try await write("DELETE", "api/transactions/\(t.id)/split")
                let old = body(split.people)
                let id = t.id
                return (title, {
                    // The server's Undo when it sent one (JOINT-B), else the split again.
                    if let undo = gone?.undo { try await postUndo(undo) } else {
                        let _: OK = try await app.api.put("api/transactions/\(id)/split", old)
                    }
                    return nil
                })
            }
            struct Reply: Decodable { let toast: String?; let undo: JSONValue? }
            let reply: Reply? = try await write("PUT", "api/transactions/\(t.id)/split", body(kept))
            let undo = reply?.undo
            return (reply?.toast ?? title, {
                if let undo = undo { try await postUndo(undo) }
                return nil
            })
        } catch let e as APIError {
            if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
            throw e
        }
    }

    /// S-45b: each share is what that person paid; hers is the rest. Nobody
    /// owes after. Undo puts it back to Not sure yet with the same links.
    private func settleWithWhatEachPaid(_ split: Transaction.Splitting) async throws -> (String, () async throws -> String?) {
        let people = split.people.map { ["name": $0.name, "amount": $0.paid] as [String: Any] }
        let you = max(0, ((t.splitBase - split.people.map(\.paid).reduce(0, +)) * 100).rounded() / 100)
        struct Reply: Decodable { let undo: JSONValue? }
        do {
            let r: Reply? = try await write("PUT", "api/transactions/\(t.id)/split",
                                            ["mode": "amount", "include_me": true, "you": you, "people": people])
            let undo = r?.undo
            // S-45g (REFRESH-03).
            return ("Settled up", {
                if let undo = undo { try await postUndo(undo) }
                return "Not sure yet again"
            })
        } catch let e as APIError {
            if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
            throw e
        }
    }

    /// S-46c Reopen split → S-46d, with Undo.
    private func reopenSplit() async {
        struct Reply: Decodable { let toast: String?; let undo: JSONValue? }
        do {
            let r: Reply? = try await write("DELETE", "api/transactions/\(t.id)/split/close")
            await settled(r?.toast ?? "Split reopened", undo: r?.undo.map { u in { try await postUndo(u); return "Closed again" } })
        } catch {
            showFailed("Couldn’t reopen it. Nothing changed.") { Task { await reopenSplit() } }
        }
    }

    /// S-05o's View: the e-Transfer, the deposit or the refund, in the app.
    private func open(_ id: String) async {
        do {
            viewing = try await app.api.get("api/transactions/\(id)")
        } catch {
            self.error = app.handle(error)
        }
    }

    /// A part is gone once unlinked, so the page shows the deposit it was.
    /// From the payback's own page (S-34) this unlinks every purchase it paid
    /// (`whole`); from a purchase, UnlinkLinkSheet unlinks only that one.
    private func unlinkPayback(_ link: PaybackLink) async {
        await run {
            let _: OK? = try await write("DELETE", "api/transactions/\(link.charge)/paybacks/\(link.inflow)",
                                         query: link.inflow == t.id ? ["whole": "1"] : [:])
            return "Unlinked. \(link.who) owes you \(Format.amount(link.amount)) again."
        }
    }

    private func unlinkParts() async {
        struct Reply: Decodable { let id: String; let title: String? }
        await run {
            let reply: Reply = try await app.api.delete("api/transactions/\(t.id)/parts")
            detail = try await app.api.get("api/transactions/\(reply.id)")
            return reply.title
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

/// A+ (G1-TxSpend): Pearl's guess on the A+ card with a 1.5 pt dashed
/// `action` outline and no shadow; her own pick on the plain card.
struct GuessCardSurface: View {
    let dashed: Bool

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous)
        if dashed {
            shape.fill(APlus.card)
                .overlay(shape.strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5, dash: [5, 3])))
        } else {
            APCardSurface()
        }
    }
}

/// A guess opened from the list hides the tab bar, so Skip and Yes have
/// the bottom (REDESIGN-09).
struct GuessHidesTabBar: ViewModifier {
    let on: Bool

    func body(content: Content) -> some View {
        if on { content.toolbar(.hidden, for: .tabBar) } else { content }
    }
}

/// The card a linked transaction sits on (T-39, T-41, T-05): the one A+

/// card (G1-TxRefund's REFUND FOR, G1-TxMore's MOVED).
struct SolidCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        APCard(content: content)
    }
}

/// Her own words about it, up to 200 characters. T-43 (G1-TxNote): Note
/// with ✕, the purchase (face, name, "−$84.12 · Wed, Nov 11"), the Note
/// well with "20 of 200" under it, and Save just above the keyboard.
struct NoteSheet: View {
    @State var note: String
    var name: String? = nil
    var line: String? = nil
    let onSave: (String) -> Void
    @Environment(\.dismiss) private var dismiss
    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            CFSheetTitle(title: "Note") { dismiss() }
            if let name = name {
                APQuestionWho(name: name, amount: line ?? "", tone: Pearl.muted, sub: nil)
                    .padding(.horizontal, 16)
            }
            Text("Note").font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 20)
                .padding(.bottom, -6)
            TextField("", text: $note, prompt: Text("What was it for?").foregroundColor(Pearl.muted), axis: .vertical)
                .font(Nacre.body).lineLimit(3...6)
                .focused($focused)
                .tint(Pearl.action)
                .padding(.horizontal, 14).padding(.vertical, 12)
                .frame(minHeight: 96, alignment: .topLeading)
                // REDESIGN-09: a visible well (kit `.fld.area`).
                .wellStyle(focused: focused)
                .padding(.horizontal, 16)

                .onChange(of: note) { value in if value.count > 200 { note = String(value.prefix(200)) } }
                .accessibilityLabel("Note")
            Text("\(note.count) of 200").font(Nacre.footnote).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity, alignment: .trailing).padding(.horizontal, 20)
                .accessibilityHidden(true)
            Spacer()
            Button("Save") { onSave(note.trimmingCharacters(in: .whitespacesAndNewlines)) }
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .cfSheet()
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
            CFSheetTitle(title: "Tags") { dismiss() }
            HStack(spacing: 8) {
                TextField("", text: $typed, prompt: Text("Add a tag").foregroundColor(Pearl.muted))
                    .font(Nacre.body).autocorrectionDisabled()
                    .submitLabel(.done)
                    .onSubmit(add)
                Button("Add", action: add).font(Nacre.textButton).foregroundColor(Pearl.link)
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
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .cfSheet()
    }

    private func add() {
        let tag = typed.trimmingCharacters(in: .whitespaces)
        guard !tag.isEmpty else { return }
        if !tags.contains(tag) { tags.append(tag) }
        typed = ""
    }
}

/// Builds `content` in its own body (2026-11-14). A section of a long page
/// inlined into one body adds its whole stack frame to that body's; as its
/// own view, SwiftUI builds it after the page's body has returned, so the
/// deepest stack is one section, not the page.
struct OwnBody<Content: View>: View {
    let content: () -> Content
    init(@ViewBuilder _ content: @escaping () -> Content) { self.content = content }
    var body: Content { content() }
}

/// PB-42 opened from the deposit (PB-41): the link and its purchase.
struct DepositLink: Identifiable {
    let link: Transaction.LinkInfo
    let charge: String
    let merchant: String
    let date: String
    let owes: Double
    /// PP-01's ON THIS SPLIT.
    var people: [Transaction.Splitting.Person] = []
    var id: String { link.id }
}


/// RC-02 (1401:86515, dark 1401:86575): under the header, "$150.00 split 5
/// ways · $40.00 back · $50.00 to come", then "Wed, Nov 11 · your share
/// $30.00", 15 pt muted. RC-03: what's back counts up as a payback lands.
/// Its own view so TransactionDetailView's header stays small (check_stack).
struct CostHeaderLines: View {
    let line: String
    let back: Double
    let date: String

    var body: some View {
        VStack(spacing: 0) {
            Text(line).costCountDown(back)
                .accessibilityLabel(line.replacingOccurrences(of: " · ", with: ", "))
            Text(date)
        }
        .font(Nacre.subheadline).foregroundColor(Pearl.muted)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
        .accessibilityElement(children: .combine)
    }
}
