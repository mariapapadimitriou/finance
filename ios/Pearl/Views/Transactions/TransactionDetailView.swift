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
            SheetTitle(title: "Pay from a piggy bank") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: t.merchant, amount: Format.amount(charge), tone: Pearl.moneyOut, sub: nil)
                    if let banks = banks {
                        if banks.isEmpty {
                            Text("You don’t have a piggy bank yet.").font(Nacre.body).foregroundColor(Pearl.muted)
                        } else {
                            GlassCard {
                                ForEach(Array(banks.enumerated()), id: \.element.id) { index, bank in
                                    if index > 0 { RowSeparator() }
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
                                .font(Nacre.body).padding(.horizontal, 16).frame(minHeight: 52)
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
                            .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || chosen == nil || (typed ?? 0) <= 0 || (typed ?? 0) > charge + 0.005)
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
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

    /// The full detail once it's come back; the list's row until then.
    @State private var detail: Transaction?
    /// What was this?: the page sorting happens on, shared with Needs a look and Quick sort.
    @State private var sorting: Ask?
    @State private var editingNote = false
    @State private var editingTags = false
    /// A money-in question opened from here (THL-198): its kind, how often
    /// it pays, or What was this?.
    @State private var asking: Asking?

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
    /// T-41b: Unlink? before a refund goes back to Needs a look.
    @State private var unlinkingRefund = false
    @State private var message: String?
    @State private var error: String?

    private var t: Transaction { detail ?? transaction }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                header.padding(.bottom, 16)
                if let transfer = t.transfer, guessing == nil {
                    transferLegs(transfer)
                } else {
                    if let label = guessName { guessCard(label) }
                    else if !t.parts.isEmpty { partsCard } else if jointAsks { jointGuessCard }
                    else if t.asks { askingCard } else { categoryCard }
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
        .safeAreaInset(edge: .bottom) { guessActions }
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
            ToolbarItem(placement: .navigationBarTrailing) {
                if let skip = guessing?.onSkip {
                    Button("Skip", action: skip)
                        .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                        .accessibilityHint("It stays in Needs a look.")
                }
            }
        }
        .toolbarBackground(.hidden, for: .navigationBar)
        .navigationBarHidden(false)
        .navigationTitle("")
        .navigationBarTitleDisplayMode(.inline)
        .task { await load() }
        .onAppear {
            // Back on a card's page: what she'd already changed is still there.
            if let draft = guessing?.draft, chosenCategory == nil, newOnes == nil {
                chosenCategory = draft.label
                newOnes = draft.always
            }
        }
        .sheet(item: $sorting, onDismiss: { Task { await load() } }) { ask in
            // The stored category stays hers unless she changes it; a question is answered in place.
            if let guessing = guessing {
                // T-96: the guess is wrong, so the answer is the question's. Yes is already on the page.
                AnswerSheet(ask: ask, categories: categories, accounts: guessing.accounts, names: guessing.names,
                            api: app.api, start: ask.kind == .transfer ? .out : nil,
                            pageAlways: offersNewOnes && newOnesOn, pageAmount: Format.money(t),
                            pageCategory: chosenCategory,
                            onCategory: { name, remember in
                                guard guessing.onDraft == nil else { choose(name); return }
                                // Needs a look: picking is the answer (2026-11-08); picking
                                // Pearl's guess is the Yes.
                                sorting = nil
                                if name == guessing.label { guessing.onYes(remember && offersNewOnes) }
                                else { answer(with: name, always: remember && offersNewOnes) }
                            }, fromPage: true) { answer in
                    sorting = nil
                    if guessing.onDraft != nil, let label = answer.heldLabel {
                        // Not saved yet: the card agrees to it.
                        chosenCategory = label
                        holdForCard {
                            $0.answer = answer
                            $0.category = nil
                            $0.label = label
                        }
                    } else {
                        guessing.onAnswer(answer)
                    }
                }
            } else {
                AnswerSheet(ask: ask, categories: categories, accounts: [], names: recent, api: app.api,
                            pageAlways: offersNewOnes && newOnesOn, pageAmount: Format.money(t),
                            pageCategory: chosenCategory,
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
                    Task { await run { try await answer.send(app.api).title ?? answer.done } }
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
        .sheet(isPresented: $unlinkingRefund) { refundUnlinkSheet }
        .overlay(alignment: .bottom) {
            VStack(spacing: 4) {
                if let toast = toast {
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
        .sheet(item: $unlinkingPayback) { link in paybackUnlinkSheet(link) }
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
            WhoseSheet(t: t, api: app.api) { said in
                whose = false
                Task { await run { said } }
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
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
            // T-80: tap the name to rename the merchant.
            Button { if t.transfer == nil { renaming = true } } label: {
                Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center)
            }
            .buttonStyle(.plain)
            .disabled(t.transfer != nil)
            .accessibilityAddTraits(.isHeader)
            .accessibilityHint(t.transfer == nil ? "Rename the merchant" : "")
            Text(Format.money(t))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(t.tone)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(t.transfer != nil ? "Doesn’t count · Between your accounts" : dateLine)
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            if t.transfer == nil {
                // T-03's Counts pill: Spending, Income, Refund or Not counted.
                HStack(spacing: 6) {
                    Image(systemName: countsPill.up ? "arrow.up" : "arrow.down")
                        .font(.system(size: 12, weight: .semibold)).foregroundColor(countsPill.tone)
                    Text(countsPill.label)
                }
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .padding(.horizontal, 12).frame(height: 30)
                .background(Capsule().fill(Nacre.glass))
                .padding(.top, 4)
                .accessibilityElement(children: .combine)
            }
            if !t.joint.isEmpty && t.transfer == nil {
                // T-40: "Joint with Sam · 50%"; T-75 on a charge: "yours unless you say".
                HStack(spacing: 6) {
                    Image(systemName: "person.2").font(.system(size: 12, weight: .medium))
                    Text(!t.inflow && t.accountShare == nil && !t.jointPeople.isEmpty
                         ? "Joint with \(t.jointPeople.joined(separator: " and ")) · yours unless you say" : jointLine)
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
            // Income opens What was this?: its kinds, and what else it could be (2026-11-08).
            else if isIncome { asking = Asking(step: .into) } else { sorting = sortAsk(.category) }
        } label: {
            // T-03: the category's icon and name; income says what kind
            // (T-37, "Salary"). The pill above says what it counts as.
            categoryLabel(symbol: isIncome ? "Income" : (t.category ?? t.label),
                          title: isIncome ? Self.kindName(t.incomeType) : t.label, sub: countsLine)
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityHint(isIncome ? "Changes what it was" : "Changes the category")
    }

    private func categoryLabel(symbol: String, title: String, sub: String?) -> some View {
        GlassCard {
            HStack(spacing: 12) {
                Image(systemName: CategorySheet.symbol(for: symbol))
                    .font(.system(size: 15, weight: .medium)).foregroundColor(Pearl.action)
                    .frame(width: 36, height: 36)
                    .background(Circle().fill(Pearl.action.opacity(0.1)))
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(2)
                    if let sub = sub {
                        Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    }
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 60).padding(.vertical, 4)
            .contentShape(Rectangle())
        }
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
            categoryLabel(symbol: chosenCategory ?? guessing?.ask.item.guess?.text ?? t.category ?? t.label,
                          title: label, sub: still ? "Pearl’s guess" : "Your choice")
                .overlay(RoundedRectangle(cornerRadius: 26, style: .continuous)
                    .strokeBorder(Pearl.ink.opacity(still ? 0.7 : 0),
                                  style: StrokeStyle(lineWidth: 1.2, dash: [5, 3])))
        }
        .buttonStyle(.plain)
        .disabled(busy)
        .accessibilityHint("Changes the answer")
    }

    /// T-96: Yes, with the rule stated in plain sight by the Always switch.
    @ViewBuilder private var guessActions: some View {
        // From the Transactions tab the guess just stays a guess, dotted, until
        // she taps it and picks (2026-11-08): no button.
        if let label = guessName, let guessing = guessing, guessing.onDraft == nil {
            BottomActions {
                Button("Yes, \(label)") {
                    let keep = offersNewOnes && newOnesOn
                    if let name = chosenCategory {
                        answer(with: name, always: keep)
                    } else {
                        guessing.onYes(keep)
                    }
                }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            }
        }
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
    /// What the Counts pill says (T-03, T-37, T-41).
    private var countsPill: (label: String, up: Bool, tone: Color) {
        if !t.excluded.isEmpty { return ("Not counted", !t.inflow, Pearl.muted) }
        if t.refundOf != nil { return ("Refund", true, Pearl.moneyIn) }
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
        if t.split, let full = t.fullAmount {
            // S-05: "Your share · $42.06 of $84.12".
            return "Your share · \(Format.amount(t.amount)) of \(Format.amount(full))"
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

    /// "Not sorted yet · Paid back or income? Tell us": the question Needs a
    /// look is asking, answered here.
    private var askingCard: some View {
        Button { Task { await openQuestion() } } label: {
            GlassCard {
                row(title: t.label, sub: t.note.flatMap { $0.isEmpty ? nil : $0 } ?? "Needs a look", chevron: true)
            }
        }
        .buttonStyle(.plain)
        .disabled(busy)
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
                    let row = linkedRow(name: b.merchant ?? b.name,
                                        sub: [Format.short(b.date), part.map { _ in "part of \(Format.whole(abs(b.amount)))" }]
                                            .compactMap { $0 }.joined(separator: " · "),
                                        amount: part ?? abs(b.amount), inflow: true)
                    if t.splitting == nil {
                        // S-34 from the purchase: unlink the money that paid it back.
                        Button {
                            unlinkingPayback = PaybackLink(charge: t.id, inflow: b.id, who: b.person ?? b.merchant ?? b.name,
                                                           name: b.merchant ?? b.name, amount: part ?? abs(b.amount),
                                                           date: b.date)
                        } label: { row }
                        .buttonStyle(.plain)
                        .accessibilityHint("Unlink it")
                    } else {
                        row
                    }
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
            // S-33: the money that paid it back can be unlinked (S-34).
            section("Options")
            GlassCard {
                Button {
                    unlinkingPayback = PaybackLink(charge: charge.id, inflow: t.id, who: charge.person ?? "They",
                                                   name: t.merchant, amount: t.amount, date: t.date)
                } label: {
                    row(title: "Unlink", sub: "It counts as money in again", chevron: true)
                }
                .buttonStyle(.plain)
                .disabled(busy)
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
            section(t.partOf.map { "Part of a \(Format.amount($0.amount)) deposit" }
                    ?? (parts.contains { $0.kind == "payback" } ? "Pays back" : "Parts"))
            SolidCard {
                ForEach(Array(parts.enumerated()), id: \.element.id) { index, p in
                    if index > 0 { RowSeparator(inset: 72) }
                    partRow(p)
                }
            }
            section("Options")
            GlassCard {
                if t.partOf == nil {
                    // S-33's Edit: the parts sheet again, to change amounts or purchases.
                    Button { parting = deposit(rest: false) } label: {
                        row(title: "Edit", sub: "Change amounts or purchases", chevron: true)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    RowSeparator()
                }
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

    /// S-34 for one payback: "Dad will owe you $64.00 again."
    private func paybackUnlinkSheet(_ link: PaybackLink) -> some View {
        VStack(spacing: 16) {
            SheetTitle(title: "Unlink?") { unlinkingPayback = nil }
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
                .buttonStyle(NacreButtonStyle())
                Button("Keep linked") { unlinkingPayback = nil }
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

    /// A charge a piggy bank could have paid for.
    private var canPayFromBank: Bool { !t.inflow && t.transfer == nil && t.excluded.isEmpty }

    /// T-03: one Options card. Split with others, Regular pay (T-37),
    /// Unlink refund (T-41), Pay from a piggy bank and One-off purchase, each a plain row.
    @ViewBuilder private var options: some View {
        let unlink = t.refundOf != nil
        // Income can be left out of the usual month too (2026-11-08).
        let canOneOff = t.canOneOff && (!t.inflow || isIncome)
        let incomeAlways = isIncome ? t.incomeRule?.payer : nil
        if canSplit || canPart || couldBePay || unlink || canOneOff || canPayFromBank || offersNewOnes
            || incomeAlways != nil {
            section("Options")
            GlassCard {
                if canPayFromBank {
                    Button { payingFromBank = true } label: {
                        row(title: t.bankId == nil ? "Pay from a piggy bank" : "Paid from a piggy bank",
                            chevron: true, icon: "banknote")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                    if canSplit || canPart || couldBePay || unlink || canOneOff || offersNewOnes { RowSeparator() }
                }
                if canSplit || canPart {
                    Button { if canSplit { splitting = true } else { parting = deposit(rest: false) } } label: {
                        row(title: canSplit ? "Split with others" : "Split into parts", chevron: true,
                            icon: canSplit ? "person.2" : "arrow.triangle.branch")
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if couldBePay {
                    if canSplit || canPart { RowSeparator() }
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
                    if canSplit || canPart || couldBePay { RowSeparator() }
                    Button { unlinkingRefund = true } label: {
                        row(title: "Unlink refund", chevron: true)
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
                if canOneOff {
                    if canSplit || canPart || couldBePay || unlink { RowSeparator() }
                    Toggle(isOn: Binding(get: { oneOff ?? t.oneOff },
                                         set: { on in Task { await setOneOff(on) } })) {
                        HStack(spacing: 12) {
                            IconBubble(symbol: "1.circle")
                            Text("Exclude from usual month").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                    .accessibilityHint("Leaves it out of your usual month")
                    if let line = t.oneOffLine?.line, oneOff ?? t.oneOff {
                        // T-42: what leaving it out does to the month.
                        Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .padding(.horizontal, 16).padding(.bottom, 12)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                if offersNewOnes {
                    if canSplit || canPart || couldBePay || unlink || canOneOff { RowSeparator() }
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
                            IconBubble(symbol: "repeat")
                            Text("Always for \(t.merchant)").font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                    .accessibilityHint("New ones from \(t.merchant) sort the same way")
                }
                if let payer = incomeAlways {
                    if canSplit || canPart || couldBePay || unlink || canOneOff || offersNewOnes { RowSeparator() }
                    Toggle(isOn: Binding(get: { incomeAlwaysOn ?? (t.incomeRule?.on == true) },
                                         set: { on in Task { await setIncomeAlways(on) } })) {
                        HStack(spacing: 12) {
                            IconBubble(symbol: "repeat")
                            Text("Always for \(payer)").font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                    .accessibilityHint("New ones from \(payer) count as \(Self.kindName(t.incomeType))")
                }
                if canPayFromBank {
                    RowSeparator()
                    Toggle(isOn: Binding(get: { billKey != nil },
                                         set: { on in if on { addingBill = true } else { Task { await removeBill() } } })) {
                        HStack(spacing: 12) {
                            IconBubble(symbol: "calendar")
                            Text("Regular bill").font(Nacre.body).foregroundColor(Pearl.ink)
                        }
                    }
                    .tint(Pearl.action)
                    .disabled(busy)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                    .accessibilityHint("Adds it to your bills")
                }
            }
        }
    }

    /// A tile on the category page only changes what's on this page, so Yes can
    /// say it. The guess itself goes back to being the guess.
    private func choose(_ name: String) {
        sorting = nil
        // Picking Pearl's guess is still a choice: it isn't dotted any more.
        pickedGuess = name == (guessing?.label ?? t.label)
        chosenCategory = pickedGuess ? nil : name
        holdForCard {
            $0.answer = nil
            $0.category = chosenCategory
            $0.label = chosenCategory
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
        guard let key = billKey?.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) else { return }
        struct Removed: Decodable {}
        await run {
            let _: Removed = try await app.api.delete("api/income-bills/bills/\(key)")
            return "Removed from your bills."
        }
    }

    // MARK: Details

    @ViewBuilder private var details: some View {
        section("Details")
        GlassCard {
            // T-75: whose a joint charge was, first in Details.
            if !t.inflow && !t.joint.isEmpty && t.transfer == nil {
                Button { whose = true } label: {
                    row(title: "Whose was it?", sub: nil, chevron: true, value: spendWhose)
                }
                .buttonStyle(.plain)
                .disabled(busy)
                RowSeparator()
            }
            Button { editingNote = true } label: {
                if t.myNote.isEmpty {
                    row(title: "Add a note", placeholder: true, chevron: true, icon: "square.and.pencil")
                } else {
                    row(title: t.myNote, sub: "Note", chevron: true, icon: "square.and.pencil")
                }
            }
            .buttonStyle(.plain)
            // A refund's tags are its purchase's (T-41), and income has none (T-37).
            if Features.tags && t.refundOf == nil && !isIncome {
                RowSeparator()
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
            Button("Put it back") { Task { await putBack() } }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .padding(.top, 12)
                .disabled(busy)
        }
        if t.manual {
            Button("Delete transaction") { deleting = true }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.moneyOut))
                .padding(.top, 12)
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
        Button("This isn’t a transfer") { sorting = sortAsk(.transfer) }
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

    private func row(title: String, sub: String? = nil, placeholder: Bool = false, chevron: Bool,
                     value: String? = nil, icon: String? = nil) -> some View {
        HStack(spacing: 12) {
            if let icon = icon { IconBubble(symbol: icon) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(placeholder ? Nacre.body : (sub == nil ? Nacre.body : Nacre.headline))
                    .foregroundColor(placeholder ? Pearl.muted : Pearl.ink)
                    .lineLimit(2)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            Spacer(minLength: 8)
            if let value = value {
                Text(value).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
            }
            if chevron {
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16).frame(minHeight: 52).padding(.vertical, 6)
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
        if ask.item.rest != nil { parting = deposit(rest: true) } else { sorting = ask }
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
        }
        if canPayFromBank { billKey = bill?.billKey }
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

    /// T-41b: "Unlink? · It goes back to Needs a look."
    private var refundUnlinkSheet: some View {
        VStack(spacing: 16) {
            SheetTitle(title: "Unlink?") { unlinkingRefund = false }
            QuestionHeader(name: t.merchant, amount: "+" + Format.amount(t.amount), tone: Pearl.ink,
                           sub: Format.short(t.date))
                .padding(.horizontal, 16)
            Text("It goes back to Needs a look.").font(Nacre.footnote).foregroundColor(Pearl.ink)
            HStack(spacing: 10) {
                Button("Unlink") {
                    unlinkingRefund = false
                    Task { await unlinkRefund() }
                }
                .buttonStyle(NacreButtonStyle())
                Button("Keep linked") { unlinkingRefund = false }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Pearl.card))
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        .presentationDetents([.height(300)])
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
        await run {
            let reply: CategoryChange = try await app.api.put("api/transactions/\(t.id)/confirm")
            withAnimation { toast = (said ?? reply.category ?? label, undoing(reply.undo)) }
            return nil
        }
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
        await run {
            let _: QuickSortStep = try await app.api.put("api/quick-sort/\(t.id)",
                ["action": "category", "category": name, "every": false, "rows": [String](), "new_ones": remember])
            return remember ? "Always \(name) for \(merchant)." : "Moved to \(name)."
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

    /// S-07: a reminder she can paste into a message.
    private func remind(_ p: Transaction.Splitting.Person) {
        UIPasteboard.general.string = "Hey \(p.name)! Your share of \(t.merchant) on \(Format.short(t.date)) "
            + "is \(Format.amount(p.owes)). Thanks!"
        // S-07: "Copied · paste it to Sam", with Undo.
        withAnimation {
            toast = ("Copied · paste it to \(p.name)", { UIPasteboard.general.string = "" })
        }
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
    private func unlinkPayback(_ link: PaybackLink) async {
        await run {
            let _: OK = try await app.api.delete("api/transactions/\(link.charge)/paybacks/\(link.inflow)")
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

// MARK: - T-76 Whose was it?

/// A charge on a joint account: hers by default, or all theirs, or a part
/// she says, which is remembered for that merchant on the account unless she
/// turns it off (finance/joint.py).
struct WhoseSheet: View {
    @Environment(\.dismiss) private var dismiss
    let t: Transaction
    let api: APIClient
    let done: (String) -> Void

    @State private var mode: String
    @State private var part: String
    @State private var splitAlways: Bool
    @State private var mineAlways = false
    @State private var busy = false
    @State private var error: String?

    init(t: Transaction, api: APIClient, done: @escaping (String) -> Void) {
        self.t = t
        self.api = api
        self.done = done
        let full = t.fullAmount ?? t.amount
        let theirs = t.shareSet && t.amount < 0.005
        let isPart = !theirs && abs(t.amount - full) >= 0.005
        _mode = State(initialValue: theirs ? "theirs" : isPart ? "part" : "mine")
        _part = State(initialValue: isPart ? String(format: "%.2f", t.amount) : "")
        _splitAlways = State(initialValue: t.jointShare != nil || !isPart)
    }

    private var full: Double { t.fullAmount ?? t.amount }

    /// THL-282: an account set to split every purchase says so.
    private var footnote: String {
        if let share = t.accountShare {
            let mine = Int(share.rounded())
            return "On this account, purchases are split \(mine)/\(100 - mine) unless you say otherwise. Only your part counts."
        }
        return "On a joint account, spending is yours unless you say otherwise. Only your part counts."
    }
    private var amount: Double? { Double(part.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")) }
    private var ready: Bool { mode != "part" || (amount.map { $0 > 0 && $0 <= full } ?? false) }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text("Whose was it?").font(Nacre.headline).foregroundColor(Pearl.ink).accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { dismiss() } }
            .padding(.top, 20)
            HStack(spacing: 12) {
                RowAvatar(name: t.merchant, size: 48, font: Nacre.headline)
                VStack(alignment: .leading, spacing: 2) {
                    Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink)
                    Text("\(Format.money(t)) · joint with \(t.joint)").font(Nacre.footnote).foregroundColor(Pearl.ink)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    GlassCard {
                        ChoiceLine(title: "Mine", sub: "All of it counts as yours", selected: mode == "mine") { mode = "mine" }
                        RowSeparator()
                        ChoiceLine(title: "\(t.joint)’s", sub: "None of it counts", selected: mode == "theirs") { mode = "theirs" }
                        RowSeparator()
                        ChoiceLine(title: "Part of it", sub: "Say how much was yours", selected: mode == "part") { mode = "part" }
                    }
                    if mode == "part" {
                        FieldRow(label: "Your part", text: $part, prompt: Format.amount(full / 2))
                            .keyboardType(.decimalPad)
                            .sheetCard()
                        Toggle("Always split \(t.merchant) like this", isOn: $splitAlways)
                            .font(Nacre.body).tint(Pearl.action)
                            .padding(.horizontal, 16).frame(minHeight: 52)
                            .sheetCard()
                    } else if mode == "mine" {
                        Toggle("Always all mine at \(t.merchant)", isOn: $mineAlways)
                            .font(Nacre.body).tint(Pearl.action)
                            .padding(.horizontal, 16).frame(minHeight: 52)
                            .sheetCard()
                    }
                    if t.accountShare != nil {
                        Text(footnote).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    }
                    if let error = error { Hint(text: error) }
                }
            }
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || !ready)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .background(SheetBackground())
    }

    private struct Reply: Decodable { let rule: String? }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = [:]
        switch mode {
        case "theirs": body["my_share"] = 0
        case "part":
            body["my_share"] = amount ?? 0
            body["always"] = splitAlways
        default: body["my_share"] = NSNull()
        }
        do {
            let reply: Reply = try await api.put("api/transactions/\(t.id)/share", body)
            if mode == "mine" && mineAlways {
                let _: OK = try await api.put("api/transactions/\(t.id)/mine-always", ["on": true])
            }
            let said: String
            switch mode {
            case "theirs": said = "\(t.joint)’s. It doesn’t count as yours."
            case "part": said = reply.rule.flatMap { $0.isEmpty ? nil : $0 } ?? "Your part is \(Format.amount(amount ?? 0))."
            default: said = mineAlways ? "Yours, and every \(t.merchant) on this account from now on." : "Yours."
            }
            done(said)
        } catch {
            self.error = (error as? LocalizedError)?.errorDescription ?? "That didn’t save. Try again."
        }
    }
}
