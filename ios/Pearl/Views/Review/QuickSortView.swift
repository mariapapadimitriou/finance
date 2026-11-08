import SwiftUI

/// What GET /api/quick-sort says: whether to offer it today, and what to
/// walk. One number for the whole app (2026-10-24): Quick sort goes through
/// every question Needs a look asks, in its order, not only Pearl's guesses.
struct QuickSortPrompt: Decodable {
    let show: Bool
    let review: Review?

    /// The open questions, skipped ones left where they are.
    var asks: [Ask] { review?.asks.filter { !$0.skipped } ?? [] }

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case show, review }
        let c = try decoder.container(keyedBy: Keys.self)
        show = (try? c.decodeIfPresent(Bool.self, forKey: .show)) ?? false
        review = (try? c.decodeIfPresent(Review.self, forKey: .review)) ?? nil
    }
}

/// What PUT /api/quick-sort/<id> says: the others sorted with it (T-86)
/// and how to put all of it back.
struct QuickSortStep: Decodable {
    let also: [String]?
    let undo: JSONValue?

    /// T-91: "Always Dining out".
    static func always(_ label: String, sorted: Int) -> String {
        sorted > 1 ? "Sorted \(sorted) · Always \(label)" : "Always \(label)"
    }
}

/// The done screen's numbers (POST /api/quick-sort/done).
struct QuickSortDone: Decodable {
    let sorted: Int
    let before: Double?
    let after: Double?
}

extension Review {
    /// Names she already uses, for "Who sent this?".
    var people: [String] {
        var out: [String] = []
        for name in jointIn.flatMap({ $0.people ?? [] }) where !out.contains(name) { out.append(name) }
        return out
    }
}

/// Quick sort (THL-254; T-85, T-86, T-72): Needs a look's questions as
/// a stack of cards, one transaction each. A guess has two answers: swipe right
/// or ✓ for Yes, with Undo on the toast, or swipe left or Skip. Tapping the card
/// opens its page, like Slack's catch up: edits are held, she goes back, and the
/// card asks about them. A merchant sorted different ways gets no rule from
/// Yes (T-97). A question with no guess has Answer in place of Yes. Leaving early
/// keeps the rest in Needs a look.
@MainActor
struct QuickSortView: View {
    @EnvironmentObject private var app: AppModel
    let asks: [Ask]
    let categories: [CategoryList.Category]
    var names: [String] = []
    let onClose: () -> Void

    /// The cards, less the ones sorted along with another (T-86).
    @State private var deck: [Ask]
    @State private var index = 0
    @State private var drag: CGSize = .zero
    /// The card flying off, and which way.
    @State private var leaving: Bool?
    /// T-86: "Sorted 4 from Uber Eats", with Undo.
    @State private var toast: Sorted?

    struct Sorted: Identifiable {
        let id = UUID()
        let text: String
        let ask: Ask
        let undo: JSONValue?
        /// The deck as it was, to put back.
        let deck: [Ask]
        let index: Int
    }
    /// The sheet a question is asked in; What was this? for a guess.
    @State private var asking: Ask?
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var done: QuickSortDone?
    /// An answer on its way: a closing sheet mustn't bring the card back.
    @State private var busy = false
    @State private var error: String?

    /// Edits made on a card's page, waiting for Yes on the card.
    @State private var drafts: [String: CardDraft] = [:]
    /// What counts as hers now, after a split or a piggy bank on the page.
    @State private var amounts: [String: Double] = [:]

    /// How far a card has to travel to count as a swipe.
    private let threshold: CGFloat = 110

    init(asks: [Ask], categories: [CategoryList.Category], names: [String] = [],
         onClose: @escaping () -> Void) {
        self.asks = asks
        self.categories = categories
        self.names = names
        self.onClose = onClose
        _deck = State(initialValue: asks)
    }

    var body: some View {
        VStack(spacing: 0) {
            if let done = done {
                doneScreen(done)
            } else {
                header
                Spacer(minLength: 12)
                stack.padding(.horizontal, 32)
                Spacer(minLength: 16)
                Text(hint)
                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).padding(.horizontal, 32)
                    .accessibilityHidden(true)
                if current.map(hasYes) == true {
                    Text("Tap the card for other answers.")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .padding(.top, 2)
                        .accessibilityHidden(true)
                }
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.top, 6)
                }
                // T-95: the buttons rise into the hint's place, clear of the toast.
                buttons.padding(.top, 20).padding(.bottom, 40)
                    .padding(.bottom, toast == nil ? 0 : 28)
            }
        }
        .nacreScreen()
        .overlay(alignment: .bottom) {
            if let toast = toast, done == nil {
                // Stays until the next answer, so a mis-tap can still be taken back.
                UndoToast(text: toast.text, undo: toast.undo == nil ? nil : { Task { await undo(toast) } }, stays: true) {
                    withAnimation { if self.toast?.id == toast.id { self.toast = nil } }
                }
                .padding(.bottom, 8)
            }
        }
        .task { await begin() }
        .fullScreenCover(item: Binding(get: { asking.flatMap { $0.opensPage(accounts) ? $0 : nil } },
                                       set: { asking = $0 }), onDismiss: comeBack) { ask in
            GuessPage(actions: GuessActions(
                ask: ask, label: guess(ask), accounts: accounts, names: names,
                onYes: { _ in },
                onSkip: { asking = nil; left() },
                onAnswer: { answer in
                    asking = nil
                    Task { await answered(ask, answer) }
                },
                onDraft: { drafts[ask.id] = $0 },
                draft: drafts[ask.id] ?? CardDraft()),
                      categories: categories)
        }
        .sheet(item: Binding(get: { asking.flatMap { $0.opensPage(accounts) ? nil : $0 } },
                             set: { asking = $0 }), onDismiss: comeBack) { ask in
            if ask.item.rest != nil {
                // "$172 left to sort" (S-28): sorting the rest of a deposit.
                PartsSheet(deposit: PartsDeposit(id: ask.t.id, name: ask.t.name, amount: ask.t.amount,
                                                 date: ask.t.date, rest: true), api: app.api) { reply in
                    asking = nil
                    Task { await answered(ask, .done(reply)) }
                }
            } else {
                AnswerSheet(ask: ask, categories: categories, accounts: accounts, names: names,
                            api: app.api) { answer in
                    asking = nil
                    if let label = answer.heldLabel {
                        // Held for the card, like any other edit: Yes there saves it.
                        drafts[ask.id] = CardDraft(label: label, answer: answer)
                    } else {
                        Task { await answered(ask, answer) }
                    }
                }
            }
        }
    }

    private var current: Ask? { index < deck.count ? deck[index] : nil }

    /// Every question Quick sort walks: Needs a look's.
    private var total: Int { deck.count }

    private func isGuess(_ ask: Ask) -> Bool { ask.isGuess(accounts) }

    /// A category guess: the cards that open What was this? and sort the rest with them.
    private func plain(_ ask: Ask) -> Bool { ask.kind == .category && ask.savedTo(accounts) == nil }

    /// Whether the card has something to say Yes to: Pearl's guess, or her edit.
    private func hasYes(_ ask: Ask) -> Bool { isGuess(ask) || drafts[ask.id]?.label != nil }

    private var hint: String {
        guard let ask = current else { return "" }
        guard let draft = drafts[ask.id] else { return isGuess(ask) ? ask.yesLine(accounts) : "" }
        if draft.answer != nil { return "Yes saves this." }
        if draft.category == nil && draft.always == nil { return ask.yesLine(accounts) }
        return (draft.always ?? ask.savesRule(accounts)) ? "Yes sorts this, and always for \(ask.t.name)."
            : "Yes sorts just this one."
    }

    /// "Dining out", or T-66's "Saved to TD Savings".
    private func guess(_ ask: Ask) -> String { ask.guessLabel(accounts) }

    // MARK: The deck

    private var header: some View {
        ZStack {
            VStack(spacing: 4) {
                Text("Quick sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                // Counts down as she answers: what's still to sort.
                Text("\(max(total - index, 0)) left")
                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
            }
            .accessibilityElement(children: .combine)
            HStack {
                Button { Task { await leave() } } label: {
                    Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 44, height: 44)
                        .background(Circle().fill(Color.white.opacity(0.85)))
                }
                .buttonStyle(.plain)
                .accessibilityLabel("Later")
                .accessibilityHint("The rest stay in Needs a look.")
                Spacer()
            }
        }
        .padding(.horizontal, 16).padding(.top, 8)
    }

    private var stack: some View {
        ZStack {
            // The cards still to come, peeking out underneath.
            ForEach((1...2).reversed(), id: \.self) { depth in
                if index + depth < total {
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(Color.white.opacity(0.55))
                        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.8), lineWidth: 1))
                        .padding(.horizontal, CGFloat(depth) * 8)
                        .offset(y: CGFloat(depth) * 10)
                }
            }
            if let ask = current {
                card(ask)
                    .onTapGesture {
                        guard leaving == nil else { return }
                        asking = ask
                    }
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: hasYes(ask) ? "Yes" : "Answer") { right() }
                    .accessibilityAction(named: "Skip") { left() }
                    .accessibilityAction(named: "Other answers") { asking = ask }
                    .accessibilityIdentifier("quick-sort-card")
                    .id(ask.id)
            }
        }
        .frame(height: 400)
    }

    private var offsetX: CGFloat {
        switch leaving {
        case true?: return 600
        case false?: return -600
        case nil: return drag.width
        }
    }

    /// Who, how much, when, and the question: "Dining out?" for a guess,
    /// "Saved or spent?", "Who sent this?"… for the rest.
    private func card(_ ask: Ask) -> some View {
        let t = ask.t
        return VStack(spacing: 10) {
            Text(drafts[ask.id]?.label != nil ? "YOUR CHOICE" : isGuess(ask) ? "PEARL’S GUESS" : "NEEDS A LOOK")
                .font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Initials(name: t.name, size: 64)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
                .padding(.top, 4)
            Text(t.name).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(amounts[ask.id] ?? t.shownAmount))
                .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle))
                .foregroundColor(tone(t)).lineLimit(1).minimumScaleFactor(0.6)
            if let note = amounts[ask.id].map({ abs(t.amount) - $0 > 0.005 ? "Your share of \(Format.amount(abs(t.amount)))" : "" }) ?? t.shareNote, !note.isEmpty {
                Text(note).font(Nacre.footnote).foregroundColor(Pearl.ink)
            }
            Text([Format.relativeDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.ink).lineLimit(1)
            Text(drafts[ask.id]?.label.map { "\($0)?" } ?? (isGuess(ask) ? (ask.item.pair?.question ?? "\(guess(ask))?") : ask.chip))
                .font(Nacre.title).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(3).minimumScaleFactor(0.7)
                .padding(.top, 8)
            if drafts[ask.id]?.label == nil, let evidence = ask.evidence {
                Text(evidence).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).lineLimit(3)
            }
        }
        .modifier(CardFace())
        .overlay(alignment: .topLeading) { stamp(guessing: hasYes(ask)) }
    }

    /// YES or SKIP as a guess leans one way (T-64, T-65); ANSWER or SKIP for a
    /// question.
    @ViewBuilder private func stamp(guessing: Bool) -> some View {
        let lean = leaving.map { $0 ? threshold : -threshold } ?? drag.width
        let strength = min(1, abs(lean) / threshold)
        if lean > 8 {
            Text(guessing ? "YES" : "ANSWER")
                .font(.custom("Figtree-SemiBold", size: 18)).tracking(1)
                .foregroundColor(Pearl.action)
                .padding(.horizontal, 14).padding(.vertical, 6)
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Pearl.action, lineWidth: 2))
                .rotationEffect(.degrees(-12))
                .padding(28)
                .opacity(strength)
        } else if lean < -8 {
            Text("SKIP")
                .font(.custom("Figtree-SemiBold", size: 16)).tracking(1)
                .foregroundColor(Pearl.ink)
                .padding(.horizontal, 14).padding(.vertical, 6)
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Pearl.ink, lineWidth: 2))
                .rotationEffect(.degrees(8))
                .padding(28)
                .frame(maxWidth: .infinity, alignment: .trailing)
                .opacity(strength)
        }
    }

    private var swipe: some Gesture {
        DragGesture()
            .onChanged { drag = $0.translation }
            .onEnded { value in
                if value.translation.width > threshold {
                    right()
                } else if value.translation.width < -threshold {
                    left()
                } else {
                    withAnimation(.spring()) { drag = .zero }
                }
            }
    }

    @ViewBuilder private var buttons: some View {
        let guessing = current.map(hasYes) ?? true
        HStack(spacing: current?.kind == .check ? 36 : 64) {
            roundButton(symbol: "forward", label: "Skip", filled: false) { left() }
            // Plan questions ("Is TD Savings where you save?") take a No on the card.
            if let ask = current, ask.kind == .check {
                roundButton(symbol: "xmark", label: "No", filled: false) { no(ask) }
            }
            roundButton(symbol: guessing ? "checkmark" : "text.bubble",
                        label: guessing ? "Yes" : "Answer", filled: true) { right() }
        }
        .disabled(current == nil || leaving != nil)
    }

    private func roundButton(symbol: String, label: String, filled: Bool,
                             action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: symbol)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(filled ? .white : Pearl.ink)
                    .frame(width: 68, height: 68)
                    .background(Circle().fill(filled ? Pearl.action : Color.white.opacity(0.9)))
                    .shadow(color: (filled ? Pearl.action : Color.black).opacity(0.18), radius: 8, y: 4)
                Text(label).font(Nacre.footnote).foregroundColor(filled ? Pearl.action : Pearl.ink)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }

    // MARK: Done (T-72)

    private func doneScreen(_ d: QuickSortDone) -> some View {
        VStack(spacing: 12) {
            Spacer()
            HeroShell(width: 150)
            Text("\(d.sorted) sorted").font(Nacre.title).foregroundColor(Pearl.ink).padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            Text(doneLine(d)).font(Nacre.body).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).padding(.horizontal, 24)
            Spacer()
            Button("Done", action: onClose)
                .buttonStyle(NacreButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 16)
        }
    }

    /// "Your allowance went up $200. Anything you skip stays in Needs a look."
    private func doneLine(_ d: QuickSortDone) -> String {
        let rest = "Anything you skip stays in Needs a look."
        guard let before = d.before, let after = d.after, abs(after - before) >= 0.5 else { return rest }
        let change = after > before ? "went up" : "went down"
        return "Your allowance \(change) \(Format.whole(after - before)). \(rest)"
    }

    // MARK: Answers

    private func begin() async {
        // Started: today's offer is used, and these questions aren't new any more.
        let _: OK? = try? await app.api.post("api/quick-sort/seen", ["ids": asks.map(\.item.key), "start": true])
        if accounts.isEmpty, let overview: AccountsOverview = try? await app.api.get("api/accounts/overview") {
            accounts = overview.linked
        }
    }

    /// Yes to a guess, or open a question.
    private func right() {
        guard let ask = current, leaving == nil else { return }
        if hasYes(ask) {
            yes(ask)
        } else {
            withAnimation(.spring()) { drag = .zero }
            asking = ask
        }
    }

    /// Yes on a guess (T-95): the rows on the card and the rule, with Undo. A
    /// merchant that varies answers this row alone, and the toast says why (T-97).
    private func yes(_ ask: Ask) {
        let label = guess(ask)
        let draft = drafts[ask.id]
        let rule = draft?.always ?? ask.savesRule(accounts)
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        Task {
            if let answer = draft?.answer {
                await answered(ask, answer.withAlways(draft?.always))
            } else if let name = draft?.category {
                if plain(ask) {
                    await sortAs(ask, name, newOnes: rule)
                } else {
                    await answered(ask, .mark(ask.t.id, ["case": "spending", "category": name, "remember": rule]))
                }
            } else if !plain(ask) {
                await answered(ask, ask.yesAnswer(accounts, newOnes: rule))
            } else {
                let varies = ask.varies(accounts)
                await step(ask, ["action": "right", "every": false, "rows": [String](), "new_ones": rule],
                           said: varies && !rule ? "\(ask.t.name) varies, so no rule"
                               : rule ? nil : "\(ask.t.name) · \(label)",
                           always: rule ? label : nil)
            }
        }
    }

    /// A tile on the answer page: this row, and new ones if the switch is on.
    /// The guess unchanged is a Yes for this row alone.
    private func sortAs(_ ask: Ask, _ name: String, newOnes: Bool) async {
        let same = name == (ask.t.category ?? ask.item.guess?.text)
        await step(ask, ["action": same ? "right" : "category", "category": name, "every": false,
                         "rows": [String](), "new_ones": newOnes],
                   said: "\(ask.t.name) · \(name)")
    }

    /// No to a plan question: answered, and off the deck.
    private func no(_ ask: Ask) {
        guard leaving == nil, !busy else { return }
        Task { await answered(ask, .check(ask.item.key, yes: false)) }
    }

    /// Skip, for a guess or a question: it stays in Needs a look.
    private func left() {
        guard let ask = current, leaving == nil else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        Task { await step(ask, ["action": "skip"]) }
    }

    /// A sheet or page closed: the card comes back, with what she changed.
    private func comeBack() {
        guard !busy else { return }
        withAnimation(.spring()) { leaving = nil; drag = .zero }
        guard let ask = current else { return }
        // A split or a piggy bank saves on the page, and changes what's hers.
        Task {
            if let full: Transaction = try? await app.api.get("api/transactions/\(ask.t.id)"), !ask.t.inflow {
                amounts[ask.id] = abs(full.amount)
            }
        }
    }

    /// The question's sheet did the work; the batch notes what it said, for
    /// the done screen. Skip in the sheet moves it to Skipped too.
    private func answered(_ ask: Ask, _ answer: ReviewAnswer, always: String? = nil) async {
        busy = true
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        do {
            let reply = try await answer.send(app.api)
            if case .skip(_, _) = answer {
                await step(ask, ["action": "skip"])
            } else {
                let before = deck
                let at = index
                await step(ask, ["action": "marked", "title": reply.title ?? answer.done], quiet: true)
                withAnimation {
                    toast = Sorted(text: always.map { QuickSortStep.always($0, sorted: 1) } ?? reply.title ?? answer.done,
                                   ask: ask, undo: reply.undo, deck: before, index: at)
                }
            }
        } catch {
            busy = false
            self.error = app.handle(error)
            comeBack()
        }
    }

    private func step(_ ask: Ask, _ body: [String: Any], said: String? = nil, always: String? = nil,
                      quiet: Bool = false) async {
        busy = true
        defer { busy = false }
        do {
            let reply: QuickSortStep = try await app.api.put("api/quick-sort/\(ask.t.id)", body)
            error = nil
            let also = Set(reply.also ?? [])
            if quiet {
                // answered() says what happened.
            } else if body["action"] as? String == "skip" {
                withAnimation { toast = nil }
            } else if !also.isEmpty || always != nil || said != nil {
                // T-86: the others leave the deck, and the toast can take it all back.
                let before = deck
                let at = index
                withAnimation {
                    toast = Sorted(text: said ?? always.map { QuickSortStep.always($0, sorted: also.count + 1) }
                                       ?? "Sorted \(also.count + 1) from \(ask.t.name)",
                                   ask: ask, undo: reply.undo, deck: before, index: at)
                }
                deck = deck.enumerated().filter { $0.offset <= index || !also.contains($0.element.t.id) }.map(\.element)
            }
            next()
        } catch {
            self.error = app.handle(error)
            busy = false
            comeBack()
        }
    }

    /// Undo on T-86's toast: the ledger, the batch and the deck as they were.
    private func undo(_ sorted: Sorted) async {
        withAnimation { toast = nil }
        drafts[sorted.ask.id] = nil
        do {
            if let body = sorted.undo?.any as? [String: Any] {
                let _: OK = try await app.api.post("api/transactions/undo", body)
            }
            let _: OK = try await app.api.put("api/quick-sort/\(sorted.ask.t.id)", ["action": "undo"])
            withAnimation(.spring()) {
                deck = sorted.deck
                index = sorted.index
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func next() {
        drag = .zero
        leaving = nil
        index += 1
        if index >= total { Task { await finish() } }
    }

    private func finish() async {
        let summary: QuickSortDone? = try? await app.api.post("api/quick-sort/done")
        withAnimation { done = summary ?? QuickSortDone(sorted: index, before: nil, after: nil) }
        app.changed()
    }

    /// Later: what's sorted stays sorted; the rest wait in Needs a look.
    private func leave() async {
        if index > 0 {
            let _: QuickSortDone? = try? await app.api.post("api/quick-sort/done")
            app.changed()
        }
        onClose()
    }

    private func tone(_ t: BriefTransaction) -> Color { t.inflow ? Pearl.moneyIn : Pearl.moneyOut }
}

/// "Quick sort · 11 to sort, one at a time" at the top of Needs a look (T-10).
struct QuickSortCard: View {
    let count: Int
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 14) {
                Image(systemName: "rectangle.stack")
                    .font(.system(size: 24)).foregroundColor(Pearl.action)
                    .frame(width: 40, height: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Quick sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                    Text("\(count) to sort, one at a time")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink)
                }
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.ink)
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .background(RoundedRectangle(cornerRadius: 22, style: .continuous)
                .fill(LinearGradient(colors: [Color.white.opacity(0.75), Nacre.seaglass.opacity(0.35)],
                                     startPoint: .leading, endPoint: .trailing)))
            .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Nacre.glassEdge, lineWidth: 1))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// The card itself: soft nacre, a pearly edge.
private struct CardFace: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(24)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .background(RoundedRectangle(cornerRadius: 28, style: .continuous)
                .fill(LinearGradient(colors: [Color(hex: 0xFFF1F6), Color(hex: 0xF7F3FF), Color(hex: 0xEFFBF8)],
                                     startPoint: .topLeading, endPoint: .bottomTrailing)))
            .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous)
                .strokeBorder(LinearGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass],
                                             startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.2))
            .shadow(color: Color(red: 0.4, green: 0.3, blue: 0.6).opacity(0.15), radius: 16, y: 10)
    }
}
