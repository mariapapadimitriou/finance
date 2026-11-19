import SwiftUI

/// Confirming in the chat, one card at a time (note 1340:8893; A+ G7-Tell,
/// G7-TellMore): her words in her bubble, Pearl's lead over the first card,
/// one card, and Skip · Yes pinned over the composer. Never grouped, no Yes
/// to all.
///
/// PC-05  a guess from what she told Pearl ("Pearl’s guess · 1 of 7")
/// PC-06  with "Maybe split with Jo and Sam?": opens Who was it with?
///        prefilled, never splits by itself; held, "Your choice · 2 of 7"
/// PC-08  one card for the whole trip: "Were you in Montréal?"
/// PC-09  one card for the whole pattern, asked once
///
/// This file's buttons are the only place a `UserTap` is made: the chat's one
/// way to change anything (ChatCore.swift; ios/tools/check_chat.py checks).
/// That includes Undo on the toast after Set it or a trip made (G7-Confirm).
@MainActor
struct ChatDeckView: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject var engine: ChatEngine
    let deck: Deck

    /// Edits made on a card's page or in Who was it with?, held for its Yes
    /// (as Quick sort holds them, T-98s).
    @State private var drafts: [String: CardDraft] = [:]
    /// What was this? (T-96), from a tap on a told guess.
    @State private var asking: SortProposal?
    /// PC-06: Who was it with?, prefilled, for this card.
    @State private var splitting: SplitTarget?
    @State private var opening = false

    struct SplitTarget: Identifiable {
        let proposal: SortProposal
        let t: Transaction
        var id: String { proposal.id }
    }

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(spacing: 0) {
                    if deck.showsProgress {
                        // G7-Tell-r: "Out with friends Saturday · 2 of 7" for her sentence.
                        ChatDeckProgress(title: deck.progressTitle, done: deck.index, total: deck.progressTotal)
                    } else if let said = deck.said, !said.isEmpty {
                        ChatYou(text: said)
                    }
                    if let lead = deck.leadLine { ChatLine(text: lead) }
                    card
                    under
                }
                .chatPage()
            }
            ChatDeckButtons(busy: engine.busy || deck.current == nil, yesHint: yesHint, skip: skip, yes: yes)
        }
        .fullScreenCover(item: $asking) { s in
            if let item = s.item {
                GuessPage(actions: GuessActions(
                    ask: Ask(kind: .category, item: item), label: s.category, accounts: [], names: s.splitWith,
                    onYes: { _ in },
                    onSkip: {
                        asking = nil
                        Task { await engine.decide(.skip(.sort(s)), tap: UserTap("skip")) }
                    },
                    onAnswer: { answer in
                        // Held for the card's Yes, like every edit on its page.
                        asking = nil
                        drafts[s.id] = CardDraft(label: answer.heldLabel ?? s.category, answer: answer)
                    },
                    onDraft: { drafts[s.id] = $0 },
                    draft: drafts[s.id] ?? CardDraft()),
                          categories: app.categories)
            }
        }
        .sheet(item: $splitting) { target in
            // PC-06: Who was it with?, on the people Pearl suggests. Held for
            // the card: nothing is split until Yes.
            SplitSheet(t: target.t, api: app.api, recent: target.proposal.splitWith,
                       with: target.proposal.splitWith, startOnWho: true,
                       onHold: { body, _, mine in
                           let s = target.proposal
                           let held = CardSplit.held(body, mine: mine, total: target.t.splitBase)
                           let category = drafts[s.id]?.category ?? s.category
                           drafts[s.id] = CardDraft(label: held.label(category), category: drafts[s.id]?.category,
                                                    split: held)
                           splitting = nil
                       }) { _ in splitting = nil }
        }
    }

    // MARK: The card

    @ViewBuilder private var card: some View {
        switch deck.current {
        case .sort(let s)?:
            ChatSortCard(s: s, draft: drafts[s.id], over: deck.overline(choice: drafts[s.id]?.label != nil),
                         opening: opening) { Task { await openSplit(s) } }
                .contentShape(Rectangle())
                .onTapGesture { if s.item != nil { asking = s } }
                .accessibilityElement(children: .combine)
                .accessibilityAction(named: "Yes") { yes() }
                .accessibilityAction(named: "Skip") { skip() }
                .accessibilityAction(named: "What was this?") { if s.item != nil { asking = s } }
                .accessibilityIdentifier("chat-sort-card")
                .id(s.id)
        case .trip(let t)?:
            // PC-08 (G7-TellMore): "Were you in Montréal?", one card for all.
            ChatQuestionCard(over: deck.overline(), face: t.place ?? t.name ?? "Trip", trip: true,
                             name: t.place ?? t.name ?? "", amount: t.totals.shown, amountTone: Pearl.moneyOut,
                             line: t.line, question: ChatWords.tripQuestion(t), sub: ChatWords.tripAway(t)) { EmptyView() }
                .accessibilityElement(children: .combine)
                .accessibilityAction(named: "Yes") { yes() }
                .accessibilityAction(named: "Skip") { skip() }
                .accessibilityIdentifier("chat-trip-card")
                .id(t.id)
        case .pattern(let p)?:
            // PC-09 (G7-TellMore): asked once for all of them.
            ChatQuestionCard(over: deck.overline(), face: p.name, name: p.who, amount: p.shownAmount ?? "",
                             line: p.each, question: p.question, sub: ChatWords.patternSub(p)) { EmptyView() }
                .accessibilityElement(children: .combine)
                .accessibilityAction(named: "Yes") { yes() }
                .accessibilityAction(named: "Skip") { skip() }
                .accessibilityIdentifier("chat-pattern-card")
                .id(p.id)
        case .plan?, nil:
            EmptyView()
        }
    }

    /// Under the card: a held split's "Skip forgets the split.", or what
    /// went wrong (G7-Tell).
    @ViewBuilder private var under: some View {
        if case .sort(let s)? = deck.current, drafts[s.id]?.split != nil, engine.error == nil {
            // T-98s (Quick sort): a held split goes when she skips.
            ChatNote(text: "Skip forgets the split.", top: 8)
        }
        if let error = engine.error {
            ChatErrorLine(text: error)
        }
    }

    private var yesHint: String {
        switch deck.current {
        case .sort(let s)?: return drafts[s.id]?.label.map { "Saves \($0), for this one." } ?? "Sorts it as \(s.category), for this one."
        case .trip(let t)?: return "Yes groups them as one trip. They stay in \(t.months)."
        case .pattern(let p)?: return p.yesSkip
        case .plan?, nil: return ""
        }
    }

    // MARK: Her taps: the only way anything changes

    private func yes() {
        guard let card = deck.current, !engine.busy else { return }
        let decision: Decision
        if case .sort(let s) = card {
            decision = sortYes(s)
        } else {
            decision = .yes(card)
        }
        Task {
            let did = await engine.decide(decision, tap: UserTap("yes"))
            ChatToast.offer(did, decision, app: app, engine: engine)
        }
    }

    private func skip() {
        guard let card = deck.current, !engine.busy else { return }
        if case .sort(let s) = card { drafts[s.id] = nil }
        Task { await engine.decide(.skip(card), tap: UserTap("skip")) }
    }

    /// Yes on a told guess: the guess, or what she held on its page or in
    /// Who was it with?, sent the way that page sends it (one request, one Undo).
    private func sortYes(_ s: SortProposal) -> Decision {
        guard let d = drafts[s.id] else { return .yes(.sort(s)) }
        let api = app.api
        let category = d.category ?? s.category
        if let split = d.split {
            let answer = split.answer(s.txn.id, category: category)
            return .held(s, label: split.label(category)) { _ = try await answer.send(api) }
        }
        if let answer = d.answer {
            let a = answer.withAlways(d.always)
            return .held(s, label: d.label ?? category) { _ = try await a.send(api) }
        }
        if let name = d.category {
            let a = ReviewAnswer.mark(s.txn.id, ["case": "spending", "category": name, "remember": d.always ?? false])
            return .held(s, label: name) { _ = try await a.send(api) }
        }
        return .yes(.sort(s))
    }

    private func openSplit(_ s: SortProposal) async {
        guard !opening else { return }
        opening = true
        defer { opening = false }
        do {
            let t: Transaction = try await app.api.get("api/transactions/\(s.txn.id)")
            splitting = SplitTarget(proposal: s, t: t)
            engine.error = nil
        } catch {
            engine.error = app.handle(error)
        }
    }
}

/// PC-05 / PC-06's card: "Pearl’s guess · 1 of 7", who, how much, when and
/// where, "Dining out?"; with a split held, "Dining out, split?" over
/// "Split with Jo and Sam · your share $16.07".
private struct ChatSortCard: View {
    let s: SortProposal
    let draft: CardDraft?
    let over: String
    let opening: Bool
    let openSplit: () -> Void

    var body: some View {
        let t = s.txn
        let label = draft?.label ?? s.category
        return ChatQuestionCard(
            over: over, face: t.name, name: t.name,
            amount: (t.inflow ? "+" : "\u{2212}") + Format.amount(t.shownAmount),
            amountTone: t.inflow ? Pearl.moneyIn : Pearl.moneyOut,
            line: [Format.weekdayDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                .joined(separator: " \u{00B7} "),
            question: "\(label)?", sub: draft?.split?.note) {
            if draft == nil, !s.splitWith.isEmpty, !t.inflow {
                // PC-06: who, as a suggestion; it opens Who was it with?, prefilled.
                Button(action: openSplit) {
                    Text(ChatWords.maybeSplit(s.splitWith))
                        .font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.action)
                        .lineLimit(2).multilineTextAlignment(.center)
                        .padding(.horizontal, 14).frame(minHeight: 32)
                        .background(Capsule().fill(Pearl.action.opacity(0.1)))
                        .padding(.vertical, 6)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(opening)
                .padding(.top, 6)
                .accessibilityHint("Opens Who was it with?. Nothing is split until you say Yes.")
            }
        }
    }
}

/// Skip · Yes, side by side over the composer (G7-Tell's `yesskip`): Skip
/// the Secondary, Yes the Primary, 12 apart.
private struct ChatDeckButtons: View {
    let busy: Bool
    let yesHint: String
    let skip: () -> Void
    let yes: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button("Skip", action: skip)
                .buttonStyle(APSecondaryButtonStyle())
                .accessibilityIdentifier("chat-skip")
            Button("Yes", action: yes)
                .buttonStyle(APPrimaryButtonStyle())
                .accessibilityHint(yesHint)
                .accessibilityIdentifier("chat-yes")
        }
        .disabled(busy)
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 18)
    }
}

/// PC-12's Set it and Not now (G7-Confirm), under the plan's card. Set it is
/// the plan's only way in; Not now sends nothing ("Okay, nothing changed.").
@MainActor
struct ChatPlanButtons: View {
    @EnvironmentObject private var app: AppModel
    @ObservedObject var engine: ChatEngine
    let plan: PlanProposal

    var body: some View {
        VStack(spacing: 12) {
            Button("Set it") {
                Task {
                    let decision = Decision.yes(.plan(plan))
                    let did = await engine.decide(decision, tap: UserTap("set-it"))
                    ChatToast.offer(did, decision, app: app, engine: engine)
                }
            }
            .buttonStyle(APPrimaryButtonStyle(busy: engine.busy))
            .accessibilityIdentifier("chat-set-it")
            Button("Not now") { Task { await engine.decide(.skip(.plan(plan)), tap: UserTap("not-now")) } }
                .buttonStyle(APSecondaryButtonStyle())
                .accessibilityIdentifier("chat-not-now")
        }
        .disabled(engine.busy)
        .padding(.top, 18)
    }
}

/// G7-Confirm (NEW, approved 2026-11-18): after Set it or a trip made, the
/// ink toast with Undo, the same as everywhere ("Dining out plan set",
/// "Trip to Montréal made"). Its Undo is her tap, so it's made here.
@MainActor
enum ChatToast {
    static func offer(_ did: Performed?, _ decision: Decision, app: AppModel, engine: ChatEngine) {
        guard let did = did, let u = ChatEngine.undo(for: did, decision) else { return }
        app.say(u.toast) { try await engine.undo(u, tap: UserTap("undo")) }
    }
}
