import SwiftUI

/// Confirming in the chat, one card at a time (note 1340:8893): the Quick
/// sort card, inline, with Skip or Yes. Never grouped, no Yes to all.
///
/// PC-05 (1338:8507 / 1338:8574)  a guess from what she told Pearl, quoting her
/// PC-06 (1338:8629 / 1338:8698)  with "Maybe split with Jo and Sam?": opens
///                                Who was it with? prefilled, never splits by itself
/// PC-08 (1338:8994 / 1338:9061)  one card for the whole trip
/// PC-09 (1338:9116 / 1338:9183)  one card for the whole pattern
///
/// This file's buttons are the only place a `UserTap` is made: the chat's one
/// way to change anything (ChatCore.swift; ios/tools/check_chat.py checks).
@MainActor
struct ChatDeckView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.colorScheme) private var scheme
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
            // "A guess for 7 of 9 from the weekend · 1 of 7", "2 of 7", a trip's or pattern's line.
            Text(deck.position)
                .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.horizontal, 16).padding(.top, 2)
            Spacer(minLength: 12)
            stack.padding(.horizontal, 24)
            Spacer(minLength: 16)
            lines.padding(.horizontal, 16)
            if let error = engine.error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    .multilineTextAlignment(.center).padding(.horizontal, 16).padding(.top, 6)
            }
            buttons.padding(.top, 16).padding(.bottom, 12)
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

    // MARK: The stack

    private var remaining: Int { deck.cards.count - deck.index }

    private var stack: some View {
        ZStack {
            // The cards still to come, peeking out underneath (PC-05's Next card, Next-but-one).
            ForEach((1...2).reversed(), id: \.self) { depth in
                if depth < remaining {
                    RoundedRectangle(cornerRadius: Pearl.radiusSort, style: .continuous)
                        .fill(scheme == .dark ? Pearl.card : Color.white.opacity(0.55))
                        .overlay(RoundedRectangle(cornerRadius: Pearl.radiusSort, style: .continuous)
                            .strokeBorder(scheme == .dark ? Pearl.border : Nacre.edge, lineWidth: 1.2))
                        .padding(.horizontal, CGFloat(depth) * 10)
                        .offset(y: CGFloat(depth) * 10)
                        .accessibilityHidden(true)
                }
            }
            switch deck.current {
            case .sort(let s)?:
                sortCard(s)
                    .contentShape(Rectangle())
                    .onTapGesture { if s.item != nil { asking = s } }
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { yes() }
                    .accessibilityAction(named: "Skip") { skip() }
                    .accessibilityAction(named: "What was this?") { if s.item != nil { asking = s } }
                    .accessibilityIdentifier("chat-sort-card")
                    .id(s.id)
            case .trip(let t)?:
                tripCard(t)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { yes() }
                    .accessibilityAction(named: "Skip") { skip() }
                    .accessibilityIdentifier("chat-trip-card")
                    .id(t.id)
            case .pattern(let p)?:
                patternCard(p)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { yes() }
                    .accessibilityAction(named: "Skip") { skip() }
                    .accessibilityIdentifier("chat-pattern-card")
                    .id(p.id)
            case .plan?, nil:
                EmptyView()
            }
        }
        .frame(maxHeight: 410)
        .transition(.opacity)
    }

    /// PC-05: "PEARL'S GUESS", who, how much, when and where, "Dining?".
    private func sortCard(_ s: SortProposal) -> some View {
        let t = s.txn
        let draft = drafts[s.id]
        return VStack(spacing: 8) {
            ChatOverline(text: draft?.label != nil ? "Your choice" : "Pearl\u{2019}s guess")
            Initials(name: t.name, size: 64)
            Text(t.name).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
            Text((t.inflow ? "+" : "\u{2212}") + Format.amount(t.shownAmount))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.5)
            Text([Format.weekdayDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: " \u{00B7} "))
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(1)
            Text("\(draft?.label ?? s.category)?")
                .font(Pearl.heading(34, relativeTo: .largeTitle)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(3).minimumScaleFactor(0.6)
                .padding(.top, 8)
            if let split = draft?.split {
                Text(split.note).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).lineLimit(3)
            } else if draft == nil, !s.splitWith.isEmpty, !t.inflow {
                // PC-06: Who as a suggestion; it opens Who was it with?, prefilled.
                Button { Task { await openSplit(s) } } label: {
                    Text(ChatWords.maybeSplit(s.splitWith))
                        .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                        .lineLimit(2).multilineTextAlignment(.center)
                        .padding(.horizontal, 16).frame(minHeight: 44)
                        .background(Capsule().fill(Pearl.control))
                }
                .buttonStyle(.plain)
                .disabled(opening)
                .accessibilityHint("Opens Who was it with?. Nothing is split until you say Yes.")
            }
        }
        .modifier(ChatCardFace())
    }

    /// PC-08 (TR-01's card): the place, what it came to, its dates and count, "A trip?".
    private func tripCard(_ t: TripAsk) -> some View {
        VStack(spacing: 8) {
            ChatOverline(text: "A trip?")
            Initials(name: t.place ?? "Trip", size: 64)
            if let place = t.place {
                Text(place).font(Nacre.headline).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).lineLimit(2)
            }
            Text(t.totals.shown)
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.5)
            Text(t.line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
            Text("A trip?")
                .font(Pearl.heading(34, relativeTo: .largeTitle)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.6)
                .padding(.top, 8)
        }
        .modifier(ChatCardFace())
    }

    /// PC-09 (AI-18's card): one card for the whole pattern.
    private func patternCard(_ p: PatternAsk) -> some View {
        VStack(spacing: 8) {
            ChatOverline(text: "A pattern")
            Initials(name: p.name, size: 64)
            Text(p.who).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
            if let amount = p.shownAmount {
                Text(amount)
                    .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                    .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.5)
            }
            Text(p.each).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center).lineLimit(2)
            Text(p.question)
                .font(Pearl.heading(34, relativeTo: .largeTitle)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(3).minimumScaleFactor(0.6)
                .padding(.top, 8)
        }
        .modifier(ChatCardFace())
    }

    // MARK: The lines under the card

    /// What Pearl heard, in ink; what Yes does, muted (PC-05, PC-06, PC-08, PC-09).
    @ViewBuilder private var lines: some View {
        switch deck.current {
        case .sort(let s)?:
            // PC-05 / PC-06 (TEXT-01): "Dining out · from “Out with friends
            // Saturday”"; a draft's own line under it.
            pair(ChatWords.told(s.category, said: deck.said), sortHint(s))
        case .trip(let t)?:
            // PC-08 (TEXT-01): "A flight, a hotel, 5 days in Montréal. A trip?"
            pair(t.story + " A trip?", nil)
        case .pattern(let p)?:
            pair(p.because, p.yesSkip)
        case .plan?, nil:
            EmptyView()
        }
    }

    private func sortHint(_ s: SortProposal) -> String? {
        guard let draft = drafts[s.id] else { return nil }
        // T-98s (Quick sort): a held split goes when she skips.
        if draft.split != nil { return "Skip forgets the split." }
        return "Yes saves this."
    }

    private func pair(_ ink: String?, _ muted: String?) -> some View {
        VStack(spacing: 0) {
            if let ink = ink {
                Text(ink).foregroundColor(Pearl.ink)
            }
            if let muted = muted {
                Text(muted).foregroundColor(Pearl.muted)
            }
        }
        .font(Nacre.subheadline)
        .lineSpacing(1)
        .multilineTextAlignment(.center)
        .fixedSize(horizontal: false, vertical: true)
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    // MARK: Skip · Yes (64 / 72 pt)

    private var buttons: some View {
        HStack(spacing: 64) {
            Button(action: skip) {
                VStack(spacing: 8) {
                    Image(systemName: "forward")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundColor(Pearl.ink)
                        .frame(width: 64, height: 64)
                        .background(Circle().fill(scheme == .dark ? Pearl.card : Color.white.opacity(0.72)))
                        .overlay(Circle().strokeBorder(scheme == .dark ? Pearl.border : Nacre.edge, lineWidth: 1.2))
                        .shadow(color: Pearl.cardShadow.opacity(0.1), radius: 10, y: 8)
                    Text("Skip").font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.ink)
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Skip")
            .accessibilityIdentifier("chat-skip")
            Button(action: yes) {
                VStack(spacing: 8) {
                    Image(systemName: "checkmark")
                        .font(.system(size: 22, weight: .semibold))
                        .foregroundColor(Pearl.onAction)
                        .frame(width: 72, height: 72)
                        .background(Circle().fill(Pearl.action))
                    Text("Yes").font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.action)
                }
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Yes")
            .accessibilityHint(yesHint)
            .accessibilityIdentifier("chat-yes")
        }
        .disabled(engine.busy || deck.current == nil)
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
        Task { await engine.decide(decision, tap: UserTap("yes")) }
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

/// The card: frosted glass with the nacre edge, 28 pt corners (PC-05's Sort card).
struct ChatCardFace: ViewModifier {
    func body(content: Content) -> some View {
        content
            .padding(.horizontal, 24).padding(.vertical, 28)
            .frame(maxWidth: .infinity, maxHeight: .infinity)
            .glassCard(radius: Pearl.radiusSort)
    }
}

/// The card's eyebrow: "PEARL'S GUESS", "A TRIP?", "A PATTERN" (13 Medium, rose).
private struct ChatOverline: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.label).tracking(0.78)
            .foregroundColor(Pearl.action)
    }
}

/// PC-12's Set it and Not now. Set it is the plan's only way in; Not now
/// sends nothing ("Okay, nothing changed.").
@MainActor
struct ChatPlanButtons: View {
    @ObservedObject var engine: ChatEngine
    let plan: PlanProposal

    var body: some View {
        VStack(spacing: 12) {
            Button("Set it") { Task { await engine.decide(.yes(.plan(plan)), tap: UserTap("set-it")) } }
                .buttonStyle(NacreButtonStyle(busy: engine.busy))
                .accessibilityIdentifier("chat-set-it")
            Button("Not now") { Task { await engine.decide(.skip(.plan(plan)), tap: UserTap("not-now")) } }
                .buttonStyle(OutlineCapsuleStyle())
                .accessibilityIdentifier("chat-not-now")
        }
        .disabled(engine.busy)
    }
}

/// The Secondary button: an outline capsule, never filled (PC-12's Not now).
private struct OutlineCapsuleStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Nacre.headline)
            .foregroundColor(Pearl.ink)
            .frame(maxWidth: .infinity, minHeight: 52)
            .overlay(Capsule().strokeBorder(Pearl.ink, lineWidth: 1.5))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Capsule())
    }
}
