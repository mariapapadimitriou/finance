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

/// Quick sort (THL-254; T-85, T-89, T-86, T-72): Needs a look's questions as
/// a stack of cards. Pearl's guesses are yes-or-no: swipe right or ✓ for yes;
/// swipe left or ✕ for something else, which opens the category sheet; Skip
/// under them leaves it in Needs a look. "All 4 from Uber Eats" sorts the
/// other guesses from the merchant with it, and a rule. Tapping a guess
/// turns it over (T-89): its category, Split with others, One-off and Leave
/// out, all saved by Yes, so each one is touched once. Any other question
/// opens the sheet Needs a look asks it with; swipe left skips it. Leaving
/// early keeps the rest in Needs a look.
@MainActor
struct QuickSortView: View {
    @EnvironmentObject private var app: AppModel
    let asks: [Ask]
    let categories: [CategoryList.Category]
    var names: [String] = []
    /// Months with a third paycheque (T-74), after the other questions.
    var months: [Review.PayMonth] = []
    let onClose: () -> Void

    /// The cards, less the ones sorted along with another (T-86).
    @State private var deck: [Ask]
    @State private var index = 0
    @State private var drag: CGSize = .zero
    /// The card flying off, and which way.
    @State private var leaving: Bool?
    /// Something else on a guess, or the category on its back: the sheet.
    @State private var picking: Picking?
    /// T-85: every open guess from the merchant, not just this one.
    @State private var every = true
    /// T-89: the card turned over, and what's been changed on it.
    @State private var flipped = false
    @State private var chosen: String?
    @State private var chosenEvery = false
    @State private var oneOff = false
    @State private var leaveOut = false
    @State private var splitSaid: String?
    @State private var splitting: Transaction?
    /// T-86: "Sorted 4 from Uber Eats", with Undo.
    @State private var toast: Sorted?

    struct Picking: Identifiable {
        let ask: Ask
        /// From the card's back: the choice waits for Yes.
        let back: Bool
        var id: String { ask.id + (back ? ":back" : "") }
    }

    struct Sorted: Identifiable {
        let id = UUID()
        let text: String
        let ask: Ask
        let undo: JSONValue?
        /// The deck as it was, to put back.
        let deck: [Ask]
        let index: Int
        let oneOff: Bool
        let leaveOut: Bool
    }
    /// Any other question: the sheet it's asked in.
    @State private var asking: Ask?
    @State private var accounts: [AccountsOverview.Account] = []
    @State private var done: QuickSortDone?
    /// An answer on its way: a closing sheet mustn't bring the card back.
    @State private var busy = false
    @State private var error: String?

    /// How far a card has to travel to count as a swipe.
    private let threshold: CGFloat = 110

    init(asks: [Ask], categories: [CategoryList.Category], names: [String] = [],
         months: [Review.PayMonth] = [], onClose: @escaping () -> Void) {
        self.asks = asks
        self.categories = categories
        self.names = names
        self.months = months
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
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.top, 6)
                }
                buttons.padding(.top, 20).padding(.bottom, 40)
            }
        }
        .nacreScreen()
        .overlay(alignment: .bottom) {
            if let toast = toast, done == nil {
                UndoToast(text: toast.text, undo: { Task { await undo(toast) } }) {
                    withAnimation { if self.toast?.id == toast.id { self.toast = nil } }
                }
                .padding(.bottom, 8)
            }
        }
        .task { await begin() }
        .sheet(item: $picking, onDismiss: comeBack) { p in
            // T-79: Save moves the others from the merchant too; Just this one doesn't.
            CategorySheet(name: p.ask.t.name, amount: amount(p.ask.t), tone: tone(p.ask.t),
                          categories: categories, current: p.back ? (chosen ?? guess(p.ask)) : guess(p.ask),
                          merchant: p.ask.t.name,
                          preview: CategorySheet.preview(api: app.api, id: p.ask.t.id, merchant: p.ask.t.name)) { name, all in
                picking = nil
                if p.back {
                    chosen = name == guess(p.ask) ? nil : name
                    chosenEvery = all
                } else {
                    Task { await step(p.ask, ["action": "category", "category": name, "every": all]) }
                }
            }
        }
        .sheet(item: $splitting) { t in
            // T-89's Split with others: the usual split (S-02), saved as it goes.
            SplitSheet(t: t, api: app.api, recent: names) { said in
                splitting = nil
                splitSaid = said
            }
        }
        .sheet(item: $asking, onDismiss: comeBack) { ask in
            if ask.item.rest != nil {
                // "$172 left to sort" (S-28): sorting the rest of a deposit.
                PartsSheet(deposit: PartsDeposit(id: ask.t.id, name: ask.t.name, amount: ask.t.amount,
                                                 date: ask.t.date, rest: true), api: app.api) { reply in
                    asking = nil
                    Task { await answered(ask, .done(reply)) }
                }
            } else {
                AnswerSheet(ask: ask, categories: categories, accounts: accounts,
                            names: names, api: app.api) { answer in
                    asking = nil
                    Task { await answered(ask, answer) }
                }
            }
        }
    }

    private var current: Ask? { index < deck.count ? deck[index] : nil }

    /// Every question Quick sort walks: Needs a look's, then third paycheques.
    private var total: Int { deck.count + months.count }

    private var currentMonth: Review.PayMonth? {
        index >= deck.count && index - deck.count < months.count ? months[index - deck.count] : nil
    }

    private func isGuess(_ ask: Ask) -> Bool { ask.kind == .category || ask.savedTo(accounts) != nil }

    /// A category guess: the cards that turn over and sort the rest with them.
    private func plain(_ ask: Ask) -> Bool { ask.kind == .category && ask.savedTo(accounts) == nil }

    private func merchantKey(_ ask: Ask) -> String {
        (ask.t.merchant ?? ask.t.name).lowercased().split(separator: " ").joined(separator: " ")
    }

    /// The other guesses still to come from the same merchant (T-85).
    private func siblings(_ ask: Ask) -> [Ask] {
        guard plain(ask), index + 1 < deck.count else { return [] }
        let key = merchantKey(ask)
        return deck[(index + 1)...].filter { plain($0) && merchantKey($0) == key }
    }

    private var hint: String {
        if currentMonth != nil { return "Swipe right for got it, left to skip" }
        guard let ask = current else { return "" }
        if plain(ask) {
            return flipped ? "Tap the card to turn it back. Yes saves all of it."
                : "Swipe right for yes, left if it’s something else. Tap the card for more."
        }
        return isGuess(ask) ? "Swipe right for yes, left if it’s something else" : "Swipe right to answer, left to skip"
    }

    /// "Dining out", or T-66's "Saved to TD Savings".
    private func guess(_ ask: Ask) -> String {
        if let to = ask.savedTo(accounts) { return "Saved to \(to)" }
        return ask.item.guess?.text ?? ask.t.category ?? "Other"
    }

    // MARK: The deck

    private var header: some View {
        ZStack {
            VStack(spacing: 4) {
                Text("Quick sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                Text("\(min(index + 1, total)) of \(total)")
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
                ZStack {
                    card(ask).opacity(flipped ? 0 : 1)
                    if plain(ask) {
                        back(ask).opacity(flipped ? 1 : 0)
                            .rotation3DEffect(.degrees(180), axis: (x: 0, y: 1, z: 0))
                    }
                }
                    .rotation3DEffect(.degrees(flipped ? 180 : 0), axis: (x: 0, y: 1, z: 0), perspective: 0.5)
                    .onTapGesture {
                        guard plain(ask), leaving == nil else { return }
                        withAnimation(.spring(response: 0.45, dampingFraction: 0.85)) { flipped.toggle() }
                    }
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: isGuess(ask) ? "Yes" : "Answer") { right() }
                    .accessibilityAction(named: isGuess(ask) ? "Something else" : "Skip") { left() }
                    .accessibilityAction(named: flipped ? "Turn back" : "More") {
                        if plain(ask) { withAnimation { flipped.toggle() } }
                    }
                    .id(ask.id)
            } else if let m = currentMonth {
                monthCard(m)
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Got it") { right() }
                    .accessibilityAction(named: "Skip") { left() }
                    .id(m.id)
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
            Text(isGuess(ask) ? "PEARL’S GUESS" : "NEEDS A LOOK")
                .font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Initials(name: t.name, size: 64)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
                .padding(.top, 4)
            Text(t.name).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
            Text(amount(t))
                .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle))
                .foregroundColor(tone(t)).lineLimit(1).minimumScaleFactor(0.6)
            Text([Format.relativeDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.ink).lineLimit(1)
            Text(isGuess(ask) ? "\(guess(ask))?" : ask.chip)
                .font(Nacre.title).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2).minimumScaleFactor(0.8)
                .padding(.top, 14)
            let others = siblings(ask).count
            if others > 0 {
                // T-85: "All 4 from Uber Eats", on unless she says.
                Button { every.toggle() } label: {
                    HStack(spacing: 8) {
                        Image(systemName: every ? "checkmark.circle.fill" : "circle")
                            .font(.system(size: 17)).foregroundColor(every ? Pearl.action : Pearl.muted)
                        Text("All \(others + 1) from \(t.name)").font(Nacre.subheadline).foregroundColor(Pearl.ink)
                            .lineLimit(1)
                    }
                    .padding(.horizontal, 14).frame(height: 34)
                    .background(Capsule().fill(Color.white.opacity(0.8)))
                    .overlay(Capsule().strokeBorder(Color.white, lineWidth: 1))
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(every ? .isSelected : [])
                .accessibilityHint("Sorts the other \(others) the same way, and new ones from now on.")
            }
        }
        .modifier(CardFace())
        .overlay(alignment: .topLeading) { stamp(guessing: isGuess(ask)) }
    }

    /// T-89: the back of a guess. Its category, Split with others, One-off
    /// and Leave out; Yes saves all of it.
    private func back(_ ask: Ask) -> some View {
        let t = ask.t
        return VStack(spacing: 14) {
            VStack(spacing: 2) {
                Text(t.name).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(1)
                Text([amount(t), Format.relativeDay(t.date), t.accountName].compactMap { $0 }.filter { !$0.isEmpty }
                        .joined(separator: " · "))
                    .font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(1)
            }
            VStack(spacing: 0) {
                Button { picking = Picking(ask: ask, back: true) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: CategorySheet.symbol(for: chosen ?? guess(ask)))
                            .font(.system(size: 14, weight: .medium)).foregroundColor(Pearl.action)
                            .frame(width: 32, height: 32).background(Circle().fill(Pearl.action.opacity(0.1)))
                        Text(chosen ?? guess(ask)).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(1)
                        Spacer(minLength: 4)
                        chevron
                    }
                    .padding(.horizontal, 14).frame(minHeight: 54).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint("Changes the category")
                RowSeparator()
                Button { Task { await openSplit(ask) } } label: {
                    HStack {
                        Text("Split with others").font(Nacre.body).foregroundColor(Pearl.ink)
                        Spacer(minLength: 4)
                        if splitSaid != nil {
                            Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
                        }
                        chevron
                    }
                    .padding(.horizontal, 14).frame(minHeight: 48).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(t.inflow)
                RowSeparator()
                Toggle(isOn: $oneOff) { Text("One-off purchase").font(Nacre.body).foregroundColor(Pearl.ink) }
                    .tint(Pearl.action).padding(.horizontal, 14).frame(minHeight: 48)
                    .disabled(t.inflow)
                RowSeparator()
                Toggle(isOn: $leaveOut) {
                    Text("Leave out of my numbers").font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                }
                    .tint(Pearl.action).padding(.horizontal, 14).frame(minHeight: 48)
            }
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Color.white.opacity(0.75)))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous).strokeBorder(Color.white, lineWidth: 1))
            Spacer(minLength: 0)
        }
        .padding(.top, 4)
        .modifier(CardFace(padding: 18))
    }

    private var chevron: some View {
        Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
    }

    /// YES or SOMETHING ELSE as a guess leans one way (T-64, T-65); ANSWER
    /// or SKIP for a question.
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
            Text(guessing ? "SOMETHING ELSE" : "SKIP")
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
        let guessing = current.map(isGuess) ?? true
        let month = currentMonth != nil
        VStack(spacing: 0) {
        HStack(spacing: 64) {
            roundButton(symbol: month ? "forward" : guessing ? "xmark" : "forward",
                        label: month ? "Skip" : guessing ? "Something else" : "Skip", filled: false) { left() }
            roundButton(symbol: month ? "checkmark" : guessing ? "checkmark" : "text.bubble",
                        label: month ? "Got it" : guessing ? "Yes" : "Answer", filled: true) { right() }
        }
        .disabled((current == nil && currentMonth == nil) || leaving != nil)
        if guessing && !month && current != nil {
            // T-85: a guess can be left for later too.
            Button("Skip") { skip() }
                .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .frame(minWidth: 88, minHeight: 44)
                .padding(.top, 6)
                .disabled(leaving != nil)
                .accessibilityHint("It stays in Needs a look.")
        }
        }
    }

    /// T-74 as a card: "October had three paycheques".
    private func monthCard(_ m: Review.PayMonth) -> some View {
        VStack(spacing: 10) {
            Text("A THIRD PAYCHEQUE").font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Image(systemName: "calendar").font(.system(size: 26)).foregroundColor(Pearl.ink)
                .frame(width: 64, height: 64).background(Circle().fill(Color.white.opacity(0.85)))
                .padding(.top, 4)
            if let pay = m.paycheque {
                Text("+" + Format.amount(pay))
                    .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle)).foregroundColor(Pearl.moneyIn)
            }
            Text("\(Format.monthName(m.month)) had three paycheques")
                .font(Nacre.title).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(3).minimumScaleFactor(0.8)
                .padding(.top, 10)
            Text("Your plan uses a typical month, so the extra one isn’t counted as a raise.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(LinearGradient(colors: [Color(hex: 0xFFF1F6), Color(hex: 0xF7F3FF), Color(hex: 0xEFFBF8)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous).strokeBorder(Color.white.opacity(0.9), lineWidth: 1))
    }

    /// Got it dismisses a third paycheque; Skip moves it to Skipped.
    private func answerMonth(_ m: Review.PayMonth, gotIt: Bool) async {
        busy = true
        defer { busy = false }
        withAnimation(.easeIn(duration: 0.25)) { leaving = gotIt }
        do {
            let answer: ReviewAnswer = gotIt ? .dismiss(m.key) : .skip(m.key, true)
            _ = try await answer.send(app.api)
            error = nil
            next()
        } catch {
            self.error = app.handle(error)
            comeBack()
        }
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
        if let m = currentMonth, leaving == nil { Task { await answerMonth(m, gotIt: true) }; return }
        guard let ask = current, leaving == nil else { return }
        if ask.savedTo(accounts) != nil {
            withAnimation(.easeIn(duration: 0.25)) { leaving = true }
            Task { await answered(ask, .mark(ask.t.id, ["case": "saved", "remember": true])) }
        } else if plain(ask) {
            withAnimation(.easeIn(duration: 0.25)) { leaving = true }
            Task { await sortGuess(ask) }
        } else if isGuess(ask) {
            withAnimation(.easeIn(duration: 0.25)) { leaving = true }
            Task { await step(ask, ["action": "right"]) }
        } else {
            withAnimation(.spring()) { drag = .zero }
            asking = ask
        }
    }

    /// Yes on a guess (T-85, T-89): what the back says first, then the
    /// category, for every one from the merchant when the pill is on.
    private func sortGuess(_ ask: Ask) async {
        busy = true
        let others = siblings(ask)
        do {
            if oneOff {
                let _: OneOffReply = try await app.api.put("api/transactions/\(ask.t.id)/one-off", ["on": true])
            }
            if leaveOut {
                let _: OK = try await app.api.put("api/transactions/\(ask.t.id)/exclude", ["reason": "Left out in Quick sort"])
            }
        } catch {
            busy = false
            self.error = app.handle(error)
            comeBack()
            return
        }
        var body: [String: Any] = chosen.map { ["action": "category", "category": $0] } ?? ["action": "right"]
        body["every"] = others.isEmpty ? (chosen != nil && chosenEvery) : every
        await step(ask, body)
    }

    private func skip() {
        guard let ask = current, leaving == nil else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        Task { await step(ask, ["action": "skip"]) }
    }

    /// T-89's Split with others: the transaction in full, for the split sheet.
    private func openSplit(_ ask: Ask) async {
        do {
            splitting = try await app.api.get("api/transactions/\(ask.t.id)")
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Something else for a guess; skip a question.
    private func left() {
        if let m = currentMonth, leaving == nil { Task { await answerMonth(m, gotIt: false) }; return }
        guard let ask = current, leaving == nil else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        if ask.savedTo(accounts) != nil {
            withAnimation(.spring()) { leaving = nil; drag = .zero }
            asking = ask
        } else if isGuess(ask) {
            picking = Picking(ask: ask, back: false)
        } else {
            Task { await step(ask, ["action": "skip"]) }
        }
    }

    /// A sheet closed without an answer: the card comes back.
    private func comeBack() {
        guard !busy else { return }
        withAnimation(.spring()) { leaving = nil; drag = .zero }
    }

    /// The question's sheet did the work; the batch notes what it said, for
    /// the done screen. Skip in the sheet moves it to Skipped too.
    private func answered(_ ask: Ask, _ answer: ReviewAnswer) async {
        busy = true
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        do {
            let reply = try await answer.send(app.api)
            if case .skip(_, _) = answer {
                await step(ask, ["action": "skip"])
            } else {
                await step(ask, ["action": "marked", "title": reply.title ?? answer.done])
            }
        } catch {
            busy = false
            self.error = app.handle(error)
            comeBack()
        }
    }

    private func step(_ ask: Ask, _ body: [String: Any]) async {
        busy = true
        defer { busy = false }
        do {
            let reply: QuickSortStep = try await app.api.put("api/quick-sort/\(ask.t.id)", body)
            error = nil
            let also = Set(reply.also ?? [])
            if !also.isEmpty {
                // T-86: the others leave the deck, and the toast can take it all back.
                let before = deck
                let at = index
                withAnimation {
                    toast = Sorted(text: "Sorted \(also.count + 1) from \(ask.t.name)", ask: ask, undo: reply.undo,
                                   deck: before, index: at, oneOff: oneOff, leaveOut: leaveOut)
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
        do {
            if let body = sorted.undo?.any as? [String: Any] {
                let _: OK = try await app.api.post("api/transactions/undo", body)
            }
            let _: OK = try await app.api.put("api/quick-sort/\(sorted.ask.t.id)", ["action": "undo"])
            if sorted.oneOff {
                let _: OneOffReply = try await app.api.put("api/transactions/\(sorted.ask.t.id)/one-off", ["on": false])
            }
            if sorted.leaveOut {
                let _: OK = try await app.api.delete("api/transactions/\(sorted.ask.t.id)/exclude")
            }
            resetCard()
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
        resetCard()
        index += 1
        if index >= total { Task { await finish() } }
    }

    /// A new card starts face up, sorting the rest from the merchant with it.
    private func resetCard() {
        every = true
        flipped = false
        chosen = nil
        chosenEvery = false
        oneOff = false
        leaveOut = false
        splitSaid = nil
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

    private func amount(_ t: BriefTransaction) -> String {
        (t.inflow ? "+" : "\u{2212}") + Format.amount(abs(t.amount))
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
    var padding: CGFloat = 24

    func body(content: Content) -> some View {
        content
            .padding(padding)
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
