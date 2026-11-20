import SwiftUI

/// What GET /api/quick-sort says: whether to offer it today, and what to
/// walk. One number for the whole app (2026-10-24): Quick sort goes through
/// every question Needs a look asks, in its order, not only Pearl's guesses.
struct QuickSortPrompt: Decodable {
    let show: Bool
    let review: Review?
    /// The keys of the questions not offered before (nil from an older
    /// server): on open, Quick sort deals only these.
    let new: [String]?

    /// The open questions, skipped ones left where they are.
    var asks: [Ask] { review?.shownAsks.filter { !$0.skipped } ?? [] }
    /// AI-18: the patterns Pearl asks about once, first in the deck.
    var patterns: [PatternAsk] { review?.patternAsks ?? [] }
    /// TR-01: likely trips Pearl asks about, after the patterns.
    var trips: [TripAsk] { review?.tripAsks ?? [] }

    /// THL-254, on open: only what's new since her last visit. The rest
    /// stays in Needs a look (and Home's Sort now deals everything).
    var newAsks: [Ask] { asks.filter { isNew($0.item.key) } }
    var newPatterns: [PatternAsk] { patterns.filter { isNew($0.key) } }
    var newTrips: [TripAsk] { trips.filter { isNew($0.key) } }

    private func isNew(_ key: String) -> Bool { new.map { $0.contains(key) } ?? true }

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case show, review, new }
        let c = try decoder.container(keyedBy: Keys.self)
        show = (try? c.decodeIfPresent(Bool.self, forKey: .show)) ?? false
        review = (try? c.decodeIfPresent(Review.self, forKey: .review)) ?? nil
        new = (try? c.decodeIfPresent([String].self, forKey: .new)) ?? nil
    }
}

extension PatternAsk {
    /// Its question's key, as GET /api/quick-sort lists it (pattern_sort.py).
    var key: String { "pat:" + id }
}

/// What PUT /api/quick-sort/<id> says: the others sorted with it (T-86)
/// and how to put all of it back.
struct QuickSortStep: Decodable {
    let also: [String]?
    let undo: JSONValue?
    /// What the write changed (perf rehaul, 2026-11-19).
    var changed: Changed? = nil

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
/// or ✓ for Yes, or swipe left or Skip; Undo at the card's top right takes
/// the last answer back. Tapping the card
/// opens its page, like Slack's catch up: edits are held, she goes back, and the
/// card asks about them. A merchant sorted different ways gets no rule from
/// Yes (T-97). A question with no guess has Answer in place of Yes. Leaving early
/// keeps the rest in Needs a look.
@MainActor
struct QuickSortView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.colorScheme) private var scheme
    let asks: [Ask]
    let categories: [CategoryList.Category]
    var names: [String] = []
    /// AI-18: one card for each pattern Pearl asks about, before the rest.
    var patterns: [PatternAsk] = []
    /// TR-01: one card for each likely trip, after the patterns.
    var trips: [TripAsk] = []
    let onClose: () -> Void

    /// The cards, less the ones sorted along with another (T-86).
    @State private var deck: [Ask]
    @State private var index = 0
    /// How many of `patterns` have been answered; they come first.
    @State private var patternAt = 0
    /// How many of `trips` have been answered; they come next.
    @State private var tripAt = 0
    /// TR-14: the trip card was tapped; its rows, before she answers.
    @State private var seeingTrip: TripAsk?
    /// The last answer in this sitting, for Undo at the card's top right
    /// (product owner, 2026-11-20): no toasts in Quick sort, where one sat
    /// over Skip and Yes on every card when sorting quickly. Cleared by the
    /// next answer, so Undo only ever goes one card back.
    @State private var lastAnswer: LastAnswer?

    enum LastAnswer {
        /// T-86: a Yes, with the ledger's Undo and the deck as it was.
        case sorted(Sorted)
        /// A Skip: the deck as it was; the batch forgets it.
        case skipped(Sorted)
        /// G7-TripAsk: the trip just made.
        case trip(MadeTrip)
        /// AI-18y: the pattern just said Yes to.
        case pattern(PatternAsk)
    }

    struct MadeTrip: Identifiable, Equatable {
        let id = UUID()
        /// The trip's own id, for DELETE /api/trips/<id>?undo=1.
        let trip: String
        let name: String
    }
    @State private var drag: CGSize = .zero
    /// The card flying off, and which way.
    @State private var leaving: Bool?
    /// What a Yes or a Skip did, for Undo: the deck as it was, to put back.
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
    /// PP-01 for a payback the server couldn't place on the split, and its card.
    @State private var whoPaid: QuickWhoPaid?

    /// Edits made on a card's page, waiting for Yes on the card.
    @State private var drafts: [String: CardDraft] = [:]
    /// What counts as hers now, after a split or a piggy bank on the page.
    @State private var amounts: [String: Double] = [:]

    /// How far a card has to travel to count as a swipe.
    private let threshold: CGFloat = 110

    init(asks: [Ask], categories: [CategoryList.Category], names: [String] = [],
         patterns: [PatternAsk] = [], trips: [TripAsk] = [], onClose: @escaping () -> Void) {
        self.asks = asks
        self.categories = categories
        self.names = names
        self.patterns = patterns
        self.trips = trips
        self.onClose = onClose
        _deck = State(initialValue: asks)
    }

    var body: some View {
        VStack(spacing: 0) {
            if let done = done {
                doneScreen(done)
            } else {
                // A+ (G1-QuickSort, G1-QuickSort2): ✕ and "9 left", the
                // streak across the top, the card, and Skip / Yes at the
                // bottom. No notes under the card (A+ decision), and no
                // toast (2026-11-20): Undo sits at the card's top right.
                header
                // QS-SAME (G1-QuickSame, approved r7): every card one size
                // (358 × 420 on the board, never taller than the room here),
                // centred between the progress and the circles. It never grows.
                GeometryReader { g in
                    stack.padding(.horizontal, 16)
                        .overlay(alignment: .topTrailing) { undoButton.padding(.top, 10).padding(.trailing, 26) }
                        .environment(\.quickSortCardHeight, Self.cardHeight(room: g.size.height))
                        .frame(width: g.size.width, height: g.size.height)
                }
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger).padding(.bottom, 8)
                }
                buttons.padding(.horizontal, 16).padding(.top, 16).padding(.bottom, 26)
            }
        }
        .nacreScreen()
        .task { await begin() }
        .sheet(item: $seeingTrip) { t in
            // TR-14 (G7-TripMore): "In the trip · 23" as a sheet over the
            // card, its first rows and "and 19 more"; each row opens its page.
            TripRowsSheet(count: t.count, ids: t.ids) { seeingTrip = nil }
        }
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
        .sheet(item: $whoPaid) { w in
            WhoPaidAskSheet(ask: w.who, api: app.api, onPick: { answer in
                whoPaid = nil
                Task { await answered(w.ask, answer) }
            }, onClose: { whoPaid = nil })
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
            } else if let extra = ask.item.extra {
                // S-21x: Yes/Skip can't say what it was, so the card opens
                // S-11x. The tile is held for the card ("A gift?"); Yes saves
                // it with one Undo, and Skip drops it (as SPLIT-20, S-21u).
                PartsSheet(deposit: PartsDeposit(id: ask.t.id, name: ask.t.name, amount: ask.t.amount,
                                                 date: ask.t.date).part(of: extra), api: app.api, whole: extra,
                           onHeld: { body, label in
                    asking = nil
                    let answer = ReviewAnswer.extra(ask.t.id, body, label: label)
                    drafts[ask.id] = CardDraft(label: answer.heldLabel, answer: answer)
                }) { reply in
                    asking = nil
                    Task { await answered(ask, .done(reply)) }
                }
            } else if ask.item.credit != nil {
                // S-21u: Yes/Skip can't say who, so the card opens S-35c. The
                // tick is held for the card as "Paid back by Sam?"; Yes saves
                // it with one Undo, and Skip drops it (as SPLIT-20). Over the
                // share, S-11 v2 saves the parts there, as S-28's sheet does.
                WhoSentSheet(id: ask.t.id, api: app.api, onHeld: { answer in
                    asking = nil
                    drafts[ask.id] = CardDraft(label: answer.heldLabel, answer: answer)
                }) { reply in
                    asking = nil
                    Task { await answered(ask, .done(reply)) }
                }
            } else {
                AnswerSheet(ask: ask, categories: categories, accounts: accounts, names: names,
                            api: app.api, holds: true,
                            onHeldSplit: { split, category in
                                // T-98s (SPLIT-20): "Groceries, split with Sam?"; Yes saves
                                // the split and the category in one request, Skip drops it.
                                asking = nil
                                drafts[ask.id] = CardDraft(label: split.label(category), category: category,
                                                           split: split)
                            }) { answer in
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

    // 2026-11-16 (stack check, closure #1 in QuickSortView.body.getter at
    // 30,304 bytes in the Debug device build, near the 32 KB that crashed the
    // product owner's iPhone in #340 and #364): the lines under the card are
    // built here, in their own body (OwnBody), not in body's VStack, and each
    // case in its own function, so no one Debug frame holds them all. Same
    // views, same modifiers, same order.
    /// What the card is about and what Yes and Skip do, under the card.
    @ViewBuilder private var cardLines: some View {
        if let pattern = pattern {
            patternLines(pattern)
        } else if let trip = trip {
            tripLines(trip)
        } else if let ask = current, drafts[ask.id] == nil, let unsure = ask.item.unsure {
            unsureLines(unsure)
        } else {
            hintLines
        }
    }

    /// AI-18 (1326:64004): what she did, in ink; what Yes and Skip do, muted.
    @ViewBuilder private func patternLines(_ pattern: PatternAsk) -> some View {
        Text(pattern.because)
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center).padding(.horizontal, 32)
            .fixedSize(horizontal: false, vertical: true)
        Text(pattern.yesSkip)
            .font(Nacre.footnote).foregroundColor(Pearl.muted)
            .multilineTextAlignment(.center).padding(.horizontal, 32)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 2)
    }

    /// TR-01 (1327:4974): what Pearl saw, as a question: "A flight, a
    /// hotel, 5 days in Montréal. A trip?" (TEXT-01).
    @ViewBuilder private func tripLines(_ trip: TripAsk) -> some View {
        Text(ChatWords.tripAway(trip) + " " + ChatWords.tripQuestion(trip))
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center).padding(.horizontal, 32)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// AI-07 (1315:4227): why Pearl isn't sure, in ink. What Yes does is the
    /// dashed guess chip on the card, so no second line (less text 2).
    /// Still Skip or Yes.
    @ViewBuilder private func unsureLines(_ unsure: Review.Item.Unsure) -> some View {
        Text(unsure.line)
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center).padding(.horizontal, 32)
            .fixedSize(horizontal: false, vertical: true)
    }

    /// What Yes does, and how to get the other answers.
    @ViewBuilder private var hintLines: some View {
        Text(hint)
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center).padding(.horizontal, 32)
            .accessibilityHidden(true)
        if current.map(hasYes) == true, current.flatMap({ drafts[$0.id]?.split }) == nil {
            // T-98s (REFRESH-03): a held split's one line is `hint`; no second line.
            // T-93o (1284:103): on an Other guess, "Tap the card to pick something else."
            Text(current.map { $0.guessesOther && drafts[$0.id] == nil } == true
                 ? "Tap the card to pick something else." : "Tap the card for other answers.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .padding(.top, 2)
                .accessibilityHidden(true)
        }
    }

    /// AI-18: the pattern on top, while there is one; the deck waits under it.
    private var pattern: PatternAsk? { patternAt < patterns.count ? patterns[patternAt] : nil }

    /// TR-01: a likely trip, once the patterns are answered.
    private var trip: TripAsk? { pattern == nil && tripAt < trips.count ? trips[tripAt] : nil }

    private var current: Ask? { pattern == nil && trip == nil && index < deck.count ? deck[index] : nil }

    /// Every question Quick sort walks: Needs a look's.
    private var total: Int { deck.count }

    /// What's still to sort, patterns and trips too.
    private var remaining: Int {
        max(patterns.count - patternAt, 0) + max(trips.count - tripAt, 0) + max(total - index, 0)
    }

    private func isGuess(_ ask: Ask) -> Bool { ask.isGuess(accounts) }

    /// A category guess: the cards that open What was this? and sort the rest with them.
    private func plain(_ ask: Ask) -> Bool { ask.kind == .category && ask.savedTo(accounts) == nil }

    /// Whether the card has something to say Yes to: Pearl's guess, or her edit.
    /// T-93o: every guess has a Yes, Other too ("should always be Skip or Yes").
    private func hasYes(_ ask: Ask) -> Bool { isGuess(ask) || drafts[ask.id]?.label != nil }

    private var hint: String {
        guard let ask = current else { return "" }
        guard let draft = drafts[ask.id] else { return isGuess(ask) ? ask.yesLine(accounts) : "" }
        // T-98s (SPLIT-06, REFRESH-03): "Skip forgets the split."; what Yes
        // saves is the Yes button's VoiceOver hint.
        if draft.split != nil { return "Skip forgets the split." }
        if draft.answer != nil { return "Yes saves this." }
        if draft.category == nil && draft.always == nil { return ask.yesLine(accounts) }
        return (draft.always ?? ask.savesRule(accounts)) ? "Yes sorts this, and always for \(ask.t.name)."
            : "Yes sorts just this one."
    }

    /// The category a held split counts toward: the one she picked, or the guess.
    private func splitCategory(_ ask: Ask, _ draft: CardDraft) -> String {
        draft.category ?? (ask.kind == .category ? ask.item.guess?.text : nil) ?? ask.t.category ?? "Other"
    }

    /// "Dining out", or T-66's "Saved to TD Savings".
    private func guess(_ ask: Ask) -> String { ask.guessLabel(accounts) }

    // MARK: The deck

    /// A+ (G1-QuickSort): ✕ (the glass button) and "9 left" in its row, then
    /// the 12-dash streak (A+ decision: the streak at the top).
    private var header: some View {
        VStack(spacing: 14) {
            ZStack {
                // Counts down as she answers: what's still to sort.
                Text("\(remaining) left")
                    .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline)).foregroundColor(Pearl.ink)
                    .accessibilityLabel("Quick sort, \(remaining) left")
                HStack {
                    CFCloseButton(label: "Later") { Task { await leave() } }
                        .accessibilityHint("The rest stay in Needs a look.")
                    Spacer()
                }
            }
            SortStreak(sorted: sortedSoFar, toSort: remaining)
        }
        .padding(.horizontal, 16).padding(.top, 8)
    }

    /// What's been answered in this sitting, for the streak.
    private var sortedSoFar: Int { patternAt + tripAt + index }

    private var stack: some View {
        // A+: one card, no peeking stack (G1-QuickSort).
        ZStack(alignment: .top) {
            if let pattern = pattern {
                patternCard(pattern)
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { right() }
                    .accessibilityAction(named: "Skip") { patternSkip(pattern) }
                    .accessibilityHint(pattern.yesSkip)
                    .accessibilityIdentifier("quick-sort-pattern")
                    .id(pattern.id)
            } else if let trip = trip {
                tripCard(trip)
                    // TR-14 (1347:75265): tapping the card shows its rows.
                    .onTapGesture {
                        guard leaving == nil else { return }
                        seeingTrip = trip
                    }
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { right() }
                    .accessibilityAction(named: "Skip") { tripSkip(trip) }
                    .accessibilityAction(named: "See the \(trip.count)") { seeingTrip = trip }
                    .accessibilityHint("Yes groups them as one trip. They stay in \(trip.months).")
                    .accessibilityIdentifier("quick-sort-trip")
                    .id(trip.key)
            } else if let ask = current {
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
                    // T-98s (REFRESH-03): a held split's card.
                    .accessibilityHint(drafts[ask.id]?.split != nil ? "Opens the page to change it." : "")
                    .accessibilityIdentifier("quick-sort-card")
                    .id(ask.id)
            }
        }
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
        // A+ kit `.qcard`: the overline, the 56 pt ring, the name, the
        // amount in Fraunces 40, its day and card, and the question.
        return VStack(spacing: 0) {
            Text(drafts[ask.id]?.label != nil ? "YOUR CHOICE" : isGuess(ask) ? "PEARL’S GUESS" : "NEEDS A LOOK")
                .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                .foregroundColor(Pearl.action)
            CFRing(name: t.name, size: 56).padding(.top, 14)
            // QS-SAME: the name on one line, with an ellipsis.
            Text(t.name).font(Nacre.body).foregroundColor(Pearl.ink)
                .lineLimit(1).truncationMode(.tail).padding(.top, 10)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(amounts[ask.id] ?? t.shownAmount))
                .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle)).tracking(-0.8)
                .foregroundColor(tone(t)).lineLimit(1).minimumScaleFactor(0.6)
            if let note = amounts[ask.id].map({ abs(t.amount) - $0 > 0.005 ? "Your share of \(Format.amount(abs(t.amount)))" : "" }) ?? t.shareNote, !note.isEmpty {
                Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
            }
            Text([Format.relativeDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
            Text(drafts[ask.id]?.label.map { "\($0)?" }
                 ?? (isGuess(ask) ? (ask.item.pair?.question ?? "\(guess(ask))?") : ask.chip))
                .font(Self.question).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.top, 14)
            if let split = drafts[ask.id]?.split {
                // T-98s (G1-QuickMore): "Sam owes you $42.06. Skip forgets the split."
                Text((split.note.components(separatedBy: " \u{00B7} ").last ?? split.note) + ". Skip forgets the split.").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 6)
            } else if drafts[ask.id]?.label == nil, let evidence = ask.evidence {
                Text(evidence).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).lineLimit(2)
            }
            if let line = cardHint(ask) {
                // G1-QuickMore (T-93o, T-97, T-98, T-98s, AI-07): one muted line in the card.
                Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 6)
            }
        }
        .modifier(CardFace(dashed: drafts[ask.id] == nil && ask.item.unsure != nil))
        .overlay(alignment: .topLeading) { stamp(guessing: hasYes(ask)) }
    }

    /// G1-QuickMore: what the card's Yes or Skip does, in one line.
    /// Other: "Tap the card to pick something else."; a merchant that varies:
    /// "Amazon varies, so just this one."; her choice: "Yes sorts just this
    /// one."; a held split: "Skip forgets the split."; AI-07: why Pearl isn't sure.
    private func cardHint(_ ask: Ask) -> String? {
        if let draft = drafts[ask.id] {
            if draft.split != nil { return nil }   // its note says it, with Skip forgets the split.
            return hint.isEmpty ? nil : hint
        }
        if let unsure = ask.item.unsure { return unsure.line }
        guard isGuess(ask), ask.item.pair == nil, ask.incomeGuess == nil else { return nil }
        if ask.guessesOther { return "Tap the card to pick something else." }
        if ask.varies(accounts) { return "\(ask.t.name) varies, so just this one." }
        return nil
    }

    /// AI-18 (1326:64004): one card for the whole pattern. It shows "Each one"
    /// and a rhythm where a transaction shows its date and card.
    private func patternCard(_ p: PatternAsk) -> some View {
        VStack(spacing: 8) {
            Text("A PATTERN")
                .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                .foregroundColor(Pearl.action)
            CFRing(name: p.name, size: 56)
            Text(p.who).font(Nacre.headline).foregroundColor(Pearl.ink)
                .lineLimit(1).truncationMode(.tail)
            // AI-18b (1332:63964): "$12–$48" over "Usually $27 · about every week"
            // unless every one is within $1.
            if let amount = p.shownAmount {
                Text(amount)
                    .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                    .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.6)
            }
            Text(p.each).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
            Text(p.question)
                .font(Self.question).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.top, 8)
            // AI-18 (G1-QuickAsk): why Pearl asks, one muted line in the card.
            Text(p.isJoint ? "Your last \(p.count) were \(p.label)." : "Your last \(p.count) at \(p.name) were \(p.label).")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
                .fixedSize(horizontal: false, vertical: true)
        }
        .modifier(CardFace())
        .overlay(alignment: .topLeading) { stamp(guessing: true) }
    }

    /// TR-01 (1327:4974): one card for the whole trip: the place, what it
    /// came to (per currency, TR-02m), its dates and count, "Were you in Montréal?" (G7-TripAsk).
    private func tripCard(_ t: TripAsk) -> some View {
        VStack(spacing: 8) {
            Text("A TRIP")
                .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                .foregroundColor(Pearl.action)
            CFRing(name: t.place ?? "Trip", size: 56,
                   mark: String((t.place ?? "Trip").filter { $0.isLetter }.prefix(2)).uppercased())
            if let place = t.place {
                Text(place).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .lineLimit(1).truncationMode(.tail)
            }
            Text(t.totals.shown)
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.5)
            Text(t.line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
            // G7-TripAsk (approved 2026-11-18): "Were you in Montréal?",
            // never "A trip?", and what Pearl saw under it.
            Text(ChatWords.tripQuestion(t))
                .font(Self.question).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.top, 8)
            Text(ChatWords.tripAway(t)).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
        }
        .modifier(CardFace())
        .overlay(alignment: .topLeading) { stamp(guessing: true) }
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

    /// QS-SAME (G1-QuickSame, qs.css `.qbtns`, approved r7): Skip and Yes
    /// (or Answer) as 56 pt circles with their words under them, 56 apart;
    /// a plan question has No between them, 32 apart. VoiceOver keeps Skip,
    /// Yes, No and Answer.
    @ViewBuilder private var buttons: some View {
        let guessing = current.map(hasYes) ?? true
        HStack(spacing: current?.kind == .check ? 32 : 56) {
            roundButton(symbol: "forward", label: "Skip", filled: false) { left() }
            // Plan questions ("Is TD Savings where you save?") take a No on the card.
            if let ask = current, ask.kind == .check {
                roundButton(symbol: "xmark", label: "No", filled: false) { no(ask) }
            }
            roundButton(symbol: guessing ? "checkmark" : "text.bubble",
                        label: guessing ? "Yes" : "Answer", filled: true) { right() }
                // T-98s (REFRESH-03): "Saves the split and Groceries, for this one."
                .accessibilityHint(current.flatMap { ask in drafts[ask.id].flatMap { d in
                    d.split != nil ? "Saves the split and \(splitCategory(ask, d)), for this one." : nil } } ?? "")
        }
        .frame(maxWidth: .infinity)
        .disabled((current == nil && pattern == nil && trip == nil) || leaving != nil)
    }

    /// The pre-A+ `roundButton`, restyled in A+ tokens: a 56 pt circle
    /// (`card` with its line for Skip and No, `action` for Yes), a 22 pt
    /// icon, its word under it (13 medium, `action` under Yes). The whole
    /// column answers the tap: at least 56 × 44.
    private func roundButton(symbol: String, label: String, filled: Bool,
                             action: @escaping () -> Void) -> some View {
        Button(action: action) {
            VStack(spacing: 8) {
                Image(systemName: symbol)
                    .font(.system(size: 22, weight: .semibold))
                    .foregroundColor(filled ? Pearl.onAction : Pearl.ink)
                    .frame(width: Self.circle, height: Self.circle)
                    .background(Circle().fill(filled ? Pearl.action
                                              : scheme == .dark ? Pearl.card : Color.white.opacity(0.9)))
                    .overlay(Circle().strokeBorder(!filled && scheme == .dark ? Pearl.border : .clear, lineWidth: 1))
                    .shadow(color: (filled ? Pearl.action.opacity(0.30) : Color.black.opacity(scheme == .dark ? 0.25 : 0.10)),
                            radius: filled ? 10 : 8, y: 4)
                Text(label).font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote))
                    .foregroundColor(filled ? Pearl.action : Pearl.ink)
            }
            .frame(minWidth: 68, minHeight: 44)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(label)
        .accessibilityAddTraits(.isButton)
    }

    /// kit `.qcard .q`: the question in Fraunces 24, two lines at most (QS-SAME).
    static let question = Font.custom("Fraunces-SemiBold", size: 24, relativeTo: .title)

    /// QS-SAME: the circles' size.
    static let circle: CGFloat = 56

    /// Undo at the card's top right (2026-11-20): "↶ Undo" in `link`, there
    /// after an answer and until the next one, still while a card is moving.
    @ViewBuilder private var undoButton: some View {
        if lastAnswer != nil, done == nil, leaving == nil, drag == .zero {
            Button { Task { await undoLast() } } label: {
                HStack(spacing: 5) {
                    Image(systemName: "arrow.uturn.backward").font(.system(size: 12, weight: .semibold))
                    Text("Undo").font(.custom("Figtree-Medium", size: 14, relativeTo: .subheadline))
                }
                .foregroundColor(Pearl.link)
                .padding(.horizontal, 8).frame(minHeight: 44)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .disabled(busy)
            .accessibilityLabel("Undo the last answer")
            .accessibilityIdentifier("quick-sort-undo")
            .transition(.opacity)
        }
    }

    /// Undo: the last answer is taken back and its card comes back on top.
    private func undoLast() async {
        guard let last = lastAnswer, !busy else { return }
        switch last {
        case .sorted(let s): await undo(s)
        case .skipped(let s): await undoSkip(s)
        case .trip(let made): await undoTrip(made)
        case .pattern(let p): await undoYes(p)
        }
    }

    /// The card's one height: 420 where it fits, less on a small iPhone.
    static func cardHeight(room: CGFloat) -> CGFloat { min(420, max(room - 24, 280)) }

    // MARK: Done (T-72)

    /// A+ (G1-QuickSort2): the full streak, "9 sorted" in Fraunces 28, what
    /// it did to the Allowance, and Done.
    private func doneScreen(_ d: QuickSortDone) -> some View {
        VStack(spacing: 0) {
            SortStreak(sorted: max(d.sorted, 1), toSort: 0)
                .padding(.horizontal, 32).padding(.top, 200)
            Text("\(d.sorted) sorted").font(Nacre.title).foregroundColor(Pearl.ink).padding(.top, 36)
                .accessibilityAddTraits(.isHeader)
            Text(doneLine(d)).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).padding(.horizontal, 24).padding(.top, 8)
            Spacer()
            Button("Done", action: onClose)
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 26)
        }
    }

    /// "Your allowance went up $200. Anything you skip stays in Needs a look."
    private func doneLine(_ d: QuickSortDone) -> String {
        let rest = "Anything you skip stays in Needs a look."
        guard let before = d.before, let after = d.after, abs(after - before) >= 0.5 else { return rest }
        let change = after > before ? "went up" : "went down"
        return "Your Allowance \(change) \(Format.whole(after - before)).\n\(rest)"
    }

    // MARK: Answers

    private func begin() async {
        // Started: today's offer is used, and these questions aren't new any more.
        // The pattern and trip cards too, or they'd count as new on every open.
        let keys = asks.map(\.item.key) + patterns.map(\.key) + trips.map(\.key)
        let _: OK? = try? await app.api.post("api/quick-sort/seen", ["ids": keys, "start": true])
        if accounts.isEmpty, let overview: AccountsOverview = try? await app.api.get("api/accounts/overview") {
            accounts = overview.linked
        }
    }

    /// Yes to a guess, or open a question.
    private func right() {
        if let pattern = pattern {
            patternYes(pattern)
            return
        }
        if let trip = trip {
            tripYes(trip)
            return
        }
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
            if let draft = draft, let split = draft.split {
                // T-98s (SPLIT-06): the split and the category in one save, one Undo.
                await answered(ask, split.answer(ask.t.id, category: splitCategory(ask, draft)))
            } else if let answer = draft?.answer {
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

    // MARK: AI-18, a pattern

    /// Yes: Pearl sorts new ones like this from now on; nothing waiting is sorted.
    private func patternYes(_ p: PatternAsk) {
        guard leaving == nil, !busy else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        Task { await answerPattern(p, "yes") }
    }

    /// Skip: Pearl asks again after `need` more answers; a second Skip, never.
    private func patternSkip(_ p: PatternAsk) {
        guard leaving == nil, !busy else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        Task { await answerPattern(p, "skip") }
    }

    private func answerPattern(_ p: PatternAsk, _ answer: String) async {
        lastAnswer = nil
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.post("api/pattern-sort/asks/\(p.id)/\(answer)",
                                               answer == "yes" ? ["how": "ai18"] : [:])
            error = nil
            withAnimation {
                // AI-18y: a Yes can be undone; a Skip can't (Pearl asks again later).
                lastAnswer = answer == "yes" ? .pattern(p) : nil
            }
            drag = .zero
            leaving = nil
            patternAt += 1
            if remaining == 0 { await finish() }
        } catch {
            self.error = app.handle(error)
            withAnimation(.spring()) { leaving = nil; drag = .zero }
        }
    }

    /// AI-18y's Undo: the Yes is taken back and the pattern's card comes
    /// back on top. Undo goes at the next answer, so nothing after it has
    /// been answered yet.
    private func undoYes(_ p: PatternAsk) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let after = patternAt
        withAnimation(Self.undoEase) {
            lastAnswer = nil
            if let at = patterns.firstIndex(of: p), at < patternAt { patternAt = at }
        }
        do {
            let _: OK = try await app.api.post("api/pattern-sort/asks/\(p.id)/undo", [:])
            error = nil
        } catch {
            self.error = app.handle(error)
            withAnimation(Self.undoEase) { patternAt = after }
        }
    }

    // MARK: TR-01, a trip

    /// Yes: the rows become one trip, named for its place. They stay in their months.
    private func tripYes(_ t: TripAsk) {
        guard leaving == nil, !busy else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        Task { await answerTrip(t, "yes") }
    }

    /// Skip: Pearl never asks about those dates again.
    private func tripSkip(_ t: TripAsk) {
        guard leaving == nil, !busy else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        Task { await answerTrip(t, "skip") }
    }

    private func answerTrip(_ t: TripAsk, _ answer: String) async {
        busy = true
        defer { busy = false }
        do {
            // The id goes in plain: APIClient encodes the path once (TEST-33).
            struct Made: Decodable { let trip: Trip? }
            let made: Made = try await app.api.post("api/trips/asks/\(t.id)/\(answer)", [:])
            error = nil
            withAnimation {
                // G7-TripAsk: a Yes can be undone; a Skip can't (those dates aren't asked again).
                lastAnswer = made.trip.map { trip in
                    let name = trip.name.isEmpty ? (t.name ?? "") : trip.name
                    return .trip(MadeTrip(trip: trip.id, name: name.isEmpty ? "Trip" : name))
                }
            }
            drag = .zero
            leaving = nil
            tripAt += 1
            if remaining == 0 { await finish() }
        } catch {
            self.error = app.handle(error)
            withAnimation(.spring()) { leaving = nil; drag = .zero }
        }
    }

    /// Undo on "Trip to Montréal made": the trip goes (its dates aren't
    /// skipped, so Pearl can ask again) and its card comes back on top.
    private func undoTrip(_ made: MadeTrip) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let after = tripAt
        withAnimation(Self.undoEase) { lastAnswer = nil; done = nil; tripAt = max(tripAt - 1, 0) }
        do {
            struct Gone: Decodable {}
            let _: Gone = try await app.api.delete("api/trips/\(made.trip)", query: ["undo": "1"])
            error = nil
            app.changed()
        } catch {
            self.error = app.handle(error)
            withAnimation(Self.undoEase) { tripAt = after }
        }
    }

    /// Skip, for a guess or a question: it stays in Needs a look.
    private func left() {
        if let pattern = pattern {
            patternSkip(pattern)
            return
        }
        if let trip = trip {
            tripSkip(trip)
            return
        }
        guard let ask = current, leaving == nil else { return }
        // T-98s: Skip forgets a held split.
        if drafts[ask.id]?.split != nil {
            drafts[ask.id]?.split = nil
            drafts[ask.id]?.label = drafts[ask.id]?.category
        }
        // S-21u (SPLIT-22b): and a held "Paid back by Sam?".
        if case .credit? = drafts[ask.id]?.answer { drafts[ask.id] = nil }
        // S-21x (SPLIT-23 (1)): and a held S-11x answer.
        if case .extra? = drafts[ask.id]?.answer { drafts[ask.id] = nil }
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
        lastAnswer = nil
        busy = true
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        do {
            let reply = try await answer.send(app.api)
            // The Allowance and the badge move now (perf rehaul); the deck's
            // end reloads the rest.
            app.apply(reply.changed, by: nil, bump: false)
            if case .skip(_, _) = answer {
                await step(ask, ["action": "skip"])
            } else {
                let before = deck
                let at = index
                if case .credit = answer, let follow = await followUp(ask) {
                    // S-21xw → S-21xm (THL-301): Yes saved who sent it; the same
                    // deposit comes back as the next card for its extra, so it
                    // never has two cards at once. Undo puts the deck back.
                    deck.insert(follow, at: index + 1)
                }
                await step(ask, ["action": "marked", "title": reply.title ?? answer.done], quiet: true)
                withAnimation {
                    lastAnswer = .sorted(Sorted(
                        text: always.map { QuickSortStep.always($0, sorted: 1) } ?? reply.title ?? answer.done,
                        ask: ask, undo: reply.undo, deck: before, index: at))
                }
            }
        } catch let e where e.whoPaid != nil {
            // Nothing saved: the card comes back and PP-01 asks who (2026-11-16).
            busy = false
            comeBack()
            try? await Task.sleep(nanoseconds: 450_000_000)
            if let who = e.whoPaid { whoPaid = QuickWhoPaid(ask: ask, who: who) }
        } catch {
            busy = false
            self.error = app.handle(error)
            comeBack()
        }
    }

    /// THL-301 (S-21xm): the extra still to ask about on a deposit whose
    /// sender was just saved, from Needs a look's list.
    private func followUp(_ ask: Ask) async -> Ask? {
        guard let review: Review = try? await app.api.get("api/review") else { return nil }
        return review.shownAsks.first { $0.item.key == "extra:" + ask.t.id && !$0.skipped }
    }

    private func step(_ ask: Ask, _ body: [String: Any], said: String? = nil, always: String? = nil,
                      quiet: Bool = false) async {
        lastAnswer = nil
        busy = true
        defer { busy = false }
        let deckBefore = deck
        // The next card comes as the swipe finishes, not when the server
        // answers (perf rehaul, 2026-11-19): the PUT goes on behind it,
        // through the outbox. The last card waits for it, so the done
        // screen counts it right.
        let at = index
        let ahead = index + 1 < total
        let outbox = app.outbox
        let path = "api/quick-sort/\(ask.t.id)"
        let put = Task { () throws -> Outbox.Sent<QuickSortStep>? in try await outbox.send("PUT", path, body) }
        if ahead {
            try? await Task.sleep(nanoseconds: 250_000_000)
            next()
            busy = false
        }
        do {
            let sent = try await put.value
            let reply = sent?.body
            error = nil
            let also = Set(reply?.also ?? [])
            if quiet {
                // answered() notes what happened.
            } else if body["action"] as? String == "skip" {
                // A Skip can be taken back too: the card comes back on top.
                withAnimation { lastAnswer = .skipped(Sorted(text: "", ask: ask, undo: nil, deck: deckBefore, index: at)) }
            } else {
                // T-86: the others leave the deck, and Undo can take it all back.
                let before = deck
                withAnimation {
                    lastAnswer = .sorted(Sorted(
                        text: said ?? always.map { QuickSortStep.always($0, sorted: also.count + 1) }
                            ?? "Sorted \(also.count + 1) from \(ask.t.name)",
                        ask: ask, undo: reply?.undo, deck: before, index: at))
                }
                // The card she's on stays, even if the rule sorted it too.
                let now = index
                deck = deck.enumerated()
                    .filter { $0.offset <= at || $0.offset == now || !also.contains($0.element.t.id) }.map(\.element)
            }
            // The Allowance and the badge move now; the deck's end reloads the rest.
            if let sent = sent { app.apply(sent.changed, by: nil, bump: false) }
            if !ahead { next() }
        } catch {
            self.error = app.handle(error)
            busy = false
            if ahead, index > at, at < deck.count {
                // Refused: the card comes back, where she is now.
                let card = deck.remove(at: at)
                deck.insert(card, at: index - 1)
                withAnimation(.spring()) { index -= 1; leaving = nil; drag = .zero }
            } else {
                comeBack()
            }
        }
    }

    /// The card comes back at once (product owner, 2026-11-20: Undo felt
    /// slow): a short ease, not the spring, and the server catches up
    /// behind it. If the server refuses, the deck goes forward again.
    static let undoEase = Animation.easeOut(duration: 0.18)

    /// Undo on a Skip: the card comes back on top; the batch forgets it.
    private func undoSkip(_ sorted: Sorted) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        let after = (deck, index)
        withAnimation(Self.undoEase) { lastAnswer = nil; deck = sorted.deck; index = sorted.index }
        do {
            let _: OK = try await app.api.put("api/quick-sort/\(sorted.ask.t.id)", ["action": "undo"])
            error = nil
        } catch {
            self.error = app.handle(error)
            withAnimation(Self.undoEase) { deck = after.0; index = after.1 }
        }
    }

    /// Undo on a Yes (T-86): the card comes back on top; the ledger and the
    /// batch are put back behind it.
    private func undo(_ sorted: Sorted) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        drafts[sorted.ask.id] = nil
        let after = (deck, index)
        withAnimation(Self.undoEase) { lastAnswer = nil; deck = sorted.deck; index = sorted.index }
        do {
            if let body = sorted.undo?.any as? [String: Any] {
                let _: OK = try await app.api.post("api/transactions/undo", body)
            }
            let _: OK = try await app.api.put("api/quick-sort/\(sorted.ask.t.id)", ["action": "undo"])
            error = nil
        } catch {
            self.error = app.handle(error)
            withAnimation(Self.undoEase) { deck = after.0; index = after.1 }
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

/// "9 to sort · About 2 minutes", the streak and Quick sort, at the top of
/// Needs a look (T-10; A+ G1-NeedsALook).
struct QuickSortCard: View {
    let count: Int
    /// What's sorted already, for the streak.
    var sorted = 0
    let action: () -> Void

    /// About ten seconds a card.
    private var howLong: String {
        let minutes = Int((Double(count) * 10 / 60).rounded())
        return minutes <= 1 ? "About a minute" : "About \(minutes) minutes"
    }

    var body: some View {
        APCard {
            VStack(alignment: .leading, spacing: 14) {
                HStack {
                    Text("\(count) to sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                    Spacer(minLength: 8)
                    Text(howLong).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                .accessibilityElement(children: .combine)
                SortStreak(sorted: sorted, toSort: count)
                Button("Quick sort", action: action).buttonStyle(APPrimaryButtonStyle())
            }
            .padding(.horizontal, 18).padding(.vertical, 16)
        }
    }
}

/// The card itself: soft nacre, a pearly edge. In dark it is --surface-card
/// (T-93r dark, 1077:1478), so the ink text on it reads (TEST-01).
private struct CardFace: ViewModifier {
    /// AI-07 (G1-QuickMore): an unsure guess has the dashed rose edge.
    var dashed = false
    @Environment(\.colorScheme) private var scheme

    /// QS-SAME: every card the same height, whatever it holds.
    @Environment(\.quickSortCardHeight) private var height

    func body(content: Content) -> some View {
        // A+ kit `.qcard`, qs.css `.qcard.qfix`: the A+ card at radius 28,
        // 24 / 22 in, one fixed height with what it holds centred and
        // clipped, so it never grows.
        content
            .padding(.vertical, 24).padding(.horizontal, 22)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .frame(height: height)
            .clipped()
            .apCard(radius: Pearl.radiusSort)
            .overlay {
                if dashed {
                    RoundedRectangle(cornerRadius: Pearl.radiusSort, style: .continuous)
                        .strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
                }
            }
    }
}

/// QS-SAME: the one height every Quick sort card takes.
private struct QuickSortCardHeight: EnvironmentKey {
    static let defaultValue: CGFloat = 420
}

extension EnvironmentValues {
    fileprivate var quickSortCardHeight: CGFloat {
        get { self[QuickSortCardHeight.self] }
        set { self[QuickSortCardHeight.self] = newValue }
    }
}

/// A Quick sort card's payback waiting on PP-01's answer (2026-11-16).
struct QuickWhoPaid: Identifiable {
    let ask: Ask
    let who: WhoPaidAsk
    var id: String { who.id }
}

/// TR-14 (G7-TripMore): the trip card's rows before she answers, as a sheet
/// over the card: "In the trip · 23" with ✕, one card of its first four rows
/// (face, name over the day, the amount), and "and 19 more", which shows the
/// rest in place. Each row opens its page; ✕ goes back to the card.
struct TripRowsSheet: View {
    @EnvironmentObject private var app: AppModel
    let count: Int
    let ids: [String]
    let onClose: () -> Void
    @State private var rows: [Transaction] = []
    @State private var all = false
    @State private var failed = false

    private static let first = 4

    var body: some View {
        NavigationStack {
            VStack(spacing: 0) {
                CFSheetTitle(title: "In the trip · \(count)", close: onClose)
                ScrollView {
                    VStack(spacing: 8) {
                        if rows.isEmpty && !failed {
                            ProgressView().frame(maxWidth: .infinity).padding(.vertical, 32)
                        } else if failed && rows.isEmpty {
                            Text("Couldn’t load the trip’s rows.").font(Nacre.body).foregroundColor(Pearl.muted)
                                .padding(.vertical, 24)
                        }
                        if !rows.isEmpty {
                            APCard {
                                ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                                    if i > 0 { APSeparator() }
                                    NavigationLink { TransactionByID(id: t.id, categories: app.categories) } label: {
                                        // "Hotel Le Germain" over "Mar 4".
                                        TransactionRow(t: t, showsCategory: false, showsTrip: false)
                                    }
                                    .buttonStyle(.plain)
                                }
                            }
                        }
                        let more = ids.count - rows.count
                        if !all && more > 0 && !rows.isEmpty {
                            Button { all = true } label: {
                                Text("and \(more) more").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                    .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
                            }
                            .buttonStyle(.plain)
                            .accessibilityHint("Shows the rest")
                        }
                    }
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 16)
                }
            }
            .cfSheet()
            .toolbar(.hidden, for: .navigationBar)
        }
        .presentationDetents([.medium, .large])
        .presentationDragIndicator(.visible)
        .task(id: all) { await load() }
    }

    private func load() async {
        let wanted = all ? ids : Array(ids.prefix(Self.first))
        var out = rows
        for id in wanted.dropFirst(rows.count) {
            if let t: Transaction = try? await app.api.get("api/transactions/\(id)") { out.append(t) }
            else { failed = true }
        }
        rows = out
    }
}
