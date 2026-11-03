import SwiftUI

/// What GET /api/quick-sort says: whether to offer it today, and its cards.
struct QuickSortPrompt: Decodable {
    let show: Bool
    let items: [Card]

    struct Card: Decodable, Identifiable, Hashable {
        let id: String
        let merchant: String
        let date: String
        let account: String?
        let amount: Double
        let inflow: Bool
        /// Pearl's guess at the category.
        let guess: String
    }

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case show, items }
        let c = try decoder.container(keyedBy: Keys.self)
        show = (try? c.decodeIfPresent(Bool.self, forKey: .show)) ?? false
        items = ((try? c.decodeIfPresent([Lenient<Card>].self, forKey: .items)) ?? [])?.compactMap { $0.value } ?? []
    }
}

/// The done screen's numbers (POST /api/quick-sort/done).
struct QuickSortDone: Decodable {
    let sorted: Int
    let before: Double?
    let after: Double?
}

/// Quick sort (THL-254; T-63 to T-66, T-72): Pearl's yes-or-no guesses as a
/// stack of cards. Swipe right or ✓ for yes; swipe left or ✕ for something
/// else, which opens the category sheet. Leaving early keeps the rest in
/// Needs a look.
@MainActor
struct QuickSortView: View {
    @EnvironmentObject private var app: AppModel
    let cards: [QuickSortPrompt.Card]
    let categories: [CategoryList.Category]
    let onClose: () -> Void

    @State private var index = 0
    @State private var drag: CGSize = .zero
    /// The card flying off, and which way.
    @State private var leaving: Bool?
    @State private var picking: QuickSortPrompt.Card?
    @State private var done: QuickSortDone?
    @State private var error: String?

    /// How far a card has to travel to count as a swipe.
    private let threshold: CGFloat = 110

    var body: some View {
        VStack(spacing: 0) {
            if let done = done {
                doneScreen(done)
            } else {
                header
                Spacer(minLength: 12)
                stack.padding(.horizontal, 32)
                Spacer(minLength: 16)
                Text("Swipe right for yes, left if it’s something else")
                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .accessibilityHidden(true)
                if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.top, 6)
                }
                buttons.padding(.top, 20).padding(.bottom, 40)
            }
        }
        .nacreScreen()
        .task { await begin() }
        .sheet(item: $picking, onDismiss: {
            // Closed without choosing: the card comes back.
            withAnimation(.spring()) { leaving = nil; drag = .zero }
        }) { card in
            CategorySheet(name: card.merchant, amount: amount(card), tone: tone(card),
                          categories: categories, current: card.guess) { name, _ in
                picking = nil
                Task { await answer(card, ["action": "category", "category": name]) }
            }
        }
    }

    // MARK: The deck

    private var header: some View {
        ZStack {
            VStack(spacing: 4) {
                Text("Quick sort").font(Nacre.headline).foregroundColor(Pearl.ink)
                Text("\(min(index + 1, cards.count)) of \(cards.count)")
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
                if index + depth < cards.count {
                    RoundedRectangle(cornerRadius: 28, style: .continuous)
                        .fill(Color.white.opacity(0.55))
                        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous)
                            .strokeBorder(Color.white.opacity(0.8), lineWidth: 1))
                        .padding(.horizontal, CGFloat(depth) * 8)
                        .offset(y: CGFloat(depth) * 10)
                }
            }
            if index < cards.count {
                card(cards[index])
                    .offset(x: offsetX, y: drag.height * 0.2)
                    .rotationEffect(.degrees(Double(offsetX / 18)))
                    .gesture(swipe)
                    .accessibilityElement(children: .combine)
                    .accessibilityAction(named: "Yes") { Task { await yes() } }
                    .accessibilityAction(named: "Something else") { no() }
                    .id(cards[index].id)
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

    private func card(_ c: QuickSortPrompt.Card) -> some View {
        VStack(spacing: 10) {
            Text("PEARL’S GUESS").font(Nacre.caption2).tracking(0.6).foregroundColor(Pearl.action)
            Initials(name: c.merchant, size: 64)
                .overlay(Circle().strokeBorder(
                    AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                    lineWidth: 1.2))
                .padding(.top, 4)
            Text(c.merchant).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
            Text(amount(c))
                .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle))
                .foregroundColor(tone(c)).lineLimit(1).minimumScaleFactor(0.6)
            Text([Format.relativeDay(c.date), c.account].compactMap { $0 }.filter { !$0.isEmpty }
                    .joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.ink).lineLimit(1)
            Text("\(c.guess)?")
                .font(Nacre.title).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).padding(.top, 14)
        }
        .padding(24)
        .frame(maxWidth: .infinity, maxHeight: .infinity)
        .background(RoundedRectangle(cornerRadius: 28, style: .continuous)
            .fill(LinearGradient(colors: [Color(hex: 0xFFF1F6), Color(hex: 0xF7F3FF), Color(hex: 0xEFFBF8)],
                                 startPoint: .topLeading, endPoint: .bottomTrailing)))
        .overlay(RoundedRectangle(cornerRadius: 28, style: .continuous)
            .strokeBorder(LinearGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass],
                                         startPoint: .topLeading, endPoint: .bottomTrailing), lineWidth: 1.2))
        .shadow(color: Color(red: 0.4, green: 0.3, blue: 0.6).opacity(0.15), radius: 16, y: 10)
        .overlay(alignment: .topLeading) { stamp }
    }

    /// YES or SOMETHING ELSE, as the card leans one way (T-64, T-65).
    @ViewBuilder private var stamp: some View {
        let lean = leaving.map { $0 ? threshold : -threshold } ?? drag.width
        let strength = min(1, abs(lean) / threshold)
        if lean > 8 {
            Text("YES")
                .font(.custom("Figtree-SemiBold", size: 18)).tracking(1)
                .foregroundColor(Pearl.action)
                .padding(.horizontal, 14).padding(.vertical, 6)
                .overlay(RoundedRectangle(cornerRadius: 10).strokeBorder(Pearl.action, lineWidth: 2))
                .rotationEffect(.degrees(-12))
                .padding(28)
                .opacity(strength)
        } else if lean < -8 {
            Text("SOMETHING ELSE")
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
                    Task { await yes() }
                } else if value.translation.width < -threshold {
                    no()
                } else {
                    withAnimation(.spring()) { drag = .zero }
                }
            }
    }

    private var buttons: some View {
        HStack(spacing: 64) {
            roundButton(symbol: "xmark", label: "Something else", filled: false) { no() }
            roundButton(symbol: "checkmark", label: "Yes", filled: true) { Task { await yes() } }
        }
        .disabled(index >= cards.count || leaving != nil)
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
        // Started: today's offer is used, and these cards aren't new any more.
        let _: OK? = try? await app.api.post("api/quick-sort/seen", ["ids": cards.map(\.id), "start": true])
    }

    private func yes() async {
        guard index < cards.count, leaving == nil else { return }
        let card = cards[index]
        withAnimation(.easeIn(duration: 0.25)) { leaving = true }
        await answer(card, ["action": "right"])
    }

    private func no() {
        guard index < cards.count, leaving == nil else { return }
        withAnimation(.easeIn(duration: 0.25)) { leaving = false }
        picking = cards[index]
    }

    private func answer(_ card: QuickSortPrompt.Card, _ body: [String: Any]) async {
        do {
            let _: OK = try await app.api.put("api/quick-sort/\(card.id)", body)
            error = nil
            next()
        } catch {
            self.error = app.handle(error)
            withAnimation(.spring()) { leaving = nil; drag = .zero }
        }
    }

    private func next() {
        drag = .zero
        leaving = nil
        index += 1
        if index >= cards.count { Task { await finish() } }
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

    private func amount(_ c: QuickSortPrompt.Card) -> String {
        (c.inflow ? "+" : "\u{2212}") + Format.amount(c.amount)
    }

    private func tone(_ c: QuickSortPrompt.Card) -> Color { c.inflow ? Pearl.moneyIn : Pearl.moneyOut }
}

/// "Quick sort · 4 guesses to check" at the top of Needs a look (T-10).
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
                    Text(count == 1 ? "1 guess to check" : "\(count) guesses to check")
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
