import SwiftUI

// Ask Pearl on every iPhone (THL-308, AI Phase 2; product owner's picks of
// 2026-11-27). Pearl redesign canvas, Pearl page, "Ask Pearl on every phone":
//
// PC-21 A  AI2-Start    the hero, Try asking (four questions, one tap each),
//                       Tell Pearl what you did below it
// PC-22 A  AI2-Answer   the words, a fact card, a SUGGESTION in its own dashed card
// PC-23 A  AI2-States   thinking (the step names the tool), streaming (figures
//                       whole, words as they come), couldn't answer, offline,
//                       the monthly limit's one quiet line
// PC-24 A  AI2-Privacy  Before you ask: Turn on Ask Pearl / Not now
// PC-25 A  AI2-Switch   Ask Pearl is off: Turn on Ask Pearl / Search instead
// PC-26    AI2-Types    a shop's history, a month, a search, credit cards
//
// Shared styles: the canvas's project/ask.css. Each part is a small view of
// its own, so the chat's bodies stay small on the stack (check_stack.py).

/// Where an answer's link goes. Each only opens a screen.
enum AskLink: Hashable {
    /// Cash flow on one category, in a month (PC-22's suggestion).
    case category(String, month: String?)
    /// Cash flow searching for these words ("See all 38 in Cash flow").
    case search(String)
    /// Cash flow on one month ("See October in Cash flow").
    case month(String)
    /// A transaction's page.
    case transaction(String)
}

// MARK: - The hero (PC-21, PC-24)

/// The pearl (64) and "Ask about your money" in Fraunces 28, 18 under it.
struct AskHero: View {
    var body: some View {
        VStack(spacing: 18) {
            PearlOrb(size: 64)
            Text(ChatWords.hero)
                .font(Pearl.heading(28, relativeTo: .title)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 28)
    }
}

// MARK: - PC-24 · Before you ask

/// The first open: one plain line, then Turn on Ask Pearl / Not now. The
/// message field only comes after Turn on; Not now sends nothing.
struct AskConsent: View {
    let busy: Bool
    let error: String?
    let turnOn: () -> Void
    let notNow: () -> Void

    var body: some View {
        ScrollView {
            VStack(spacing: 0) {
                AskHero()
                VStack(alignment: .leading, spacing: 6) {
                    Text(ChatWords.consentTitle)
                        .font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                        .accessibilityAddTraits(.isHeader)
                    Text(ChatWords.consentLine)
                        .font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let error = error { ChatErrorLine(text: error) }
                    Button(ChatWords.turnOn, action: turnOn)
                        .buttonStyle(APPrimaryButtonStyle(busy: busy))
                        .disabled(busy)
                        .padding(.top, 14)
                        .accessibilityIdentifier("ask-turn-on")
                    ChatQuietLink(title: ChatWords.notNow, action: notNow)
                        .disabled(busy)
                        .padding(.bottom, -6)
                        .accessibilityIdentifier("ask-not-now")
                }
                .padding(.horizontal, 18).padding(.top, 20).padding(.bottom, 18)
                .apCard()
                .padding(.top, 24)
            }
            .chatPage()
        }
    }
}

// MARK: - PC-25 · Ask Pearl is off

/// The tab stays: one tap back on, or Search instead (Cash flow's search).
struct AskOff: View {
    let busy: Bool
    let error: String?
    let turnOn: () -> Void
    let search: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            PearlOrb(size: 64)
            Text(ChatWords.offTitle)
                .font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.top, 14)
                .accessibilityAddTraits(.isHeader)
            Text(ChatWords.offLine)
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
            if let error = error { ChatErrorLine(text: error) }
            VStack(spacing: 6) {
                Button(ChatWords.turnOn, action: turnOn)
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
                    .accessibilityIdentifier("ask-turn-on")
                ChatQuietLink(title: ChatWords.searchInstead, action: search)
                    .accessibilityIdentifier("ask-search-instead")
            }
            .padding(.top, 18)
        }
        .padding(.horizontal, 36).padding(.top, 90)
        .frame(maxWidth: .infinity)
    }
}

// MARK: - PC-21 · the start

/// TRY ASKING: four questions, each sent with one tap; Tell Pearl what you
/// did stays below them.
struct AskStart: View {
    let examples: [String]
    let ask: (String) -> Void
    let tell: () -> Void

    private static let symbols = ["bubble.left", "bag", "creditcard", "tv"]

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                AskHero()
                APSectionLabel(text: ChatWords.tryAsking).padding(.top, 28).padding(.bottom, 8)
                APCard {
                    ForEach(Array(examples.prefix(4).enumerated()), id: \.offset) { i, q in
                        if i > 0 { APSeparator(afterFace: false) }
                        Button { ask(q) } label: {
                            AskRow(symbol: Self.symbols[i % Self.symbols.count], title: q)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Asks Pearl")
                        .accessibilityIdentifier("ask-example-\(i)")
                    }
                }
                Button(action: tell) {
                    ChatStarterRow(symbol: "sparkles", title: "Tell Pearl what you did",
                                   sub: "Sort a few at once, in your words")
                }
                .buttonStyle(.plain)
                .apCard()
                .padding(.top, 12)
                .accessibilityIdentifier("chat-starter-tell")
            }
            .chatPage()
        }
    }
}

/// One row on Try asking or Here's what I can do: the 28 pt icon on blush,
/// the words (17, wrapping), the chevron. At least 52 high.
struct AskRow: View {
    let symbol: String
    let title: String

    var body: some View {
        HStack(spacing: 12) {
            Image(systemName: symbol).font(.system(size: 13, weight: .semibold))
                .foregroundColor(Pearl.action)
                .frame(width: 28, height: 28)
                .background(Circle().fill(Pearl.bubble))
                .accessibilityHidden(true)
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
                .frame(maxWidth: .infinity, alignment: .leading)
            ChatChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
    }
}

// MARK: - PC-23 · thinking

/// Her words, the dots, and the step naming the tool that ran.
struct AskThinking: View {
    let said: String
    let step: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                ChatYou(text: said)
                if let step = step {
                    AskDots()
                    Text(step)
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 4).padding(.top, 8)
                        .accessibilityLabel(step)
                        .accessibilityAddTraits(.updatesFrequently)
                } else {
                    ChatWorking()
                }
            }
            .chatPage()
        }
    }
}

/// G7-Chat's three rose dots, without the note under them.
struct AskDots: View {
    @Environment(\.accessibilityReduceMotion) private var still

    var body: some View {
        TimelineView(.periodic(from: .now, by: 0.35)) { context in
            let step = still ? 0 : Int(context.date.timeIntervalSinceReferenceDate / 0.35) % 3
            HStack(spacing: 5) {
                ForEach(0..<3, id: \.self) { i in
                    Circle().fill(Pearl.action)
                        .opacity([1, 0.6, 0.3][(i - step + 3) % 3])
                        .frame(width: 7, height: 7)
                }
            }
            .padding(.horizontal, 14).padding(.vertical, 12)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(APlus.card))
        }
        .padding(.horizontal, 4).padding(.top, 14)
        .accessibilityHidden(true)
    }
}

// MARK: - PC-22, PC-26 · an answer

/// Her bubble, Pearl's words (a nacre dot while they're still coming), the
/// fact cards, the suggestion, and the quiet line once per chat.
struct AskAnswerView: View {
    let answer: ChatAnswer
    let open: (AskLink) -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let said = answer.said { ChatYou(text: said) }
                if !answer.text.isEmpty || answer.streaming {
                    AskWords(text: answer.text, streaming: answer.streaming)
                }
                AskFacts(found: answer.found, open: open)
                if let s = answer.suggestion, !answer.streaming {
                    AskSuggestionCard(suggestion: s, open: open)
                }
                if let until = answer.simple { AskQuietLine(text: ChatWords.simple(until)) }
            }
            .chatPage()
        }
    }
}

/// Pearl's words, 17 on 24; while they stream, a 9 pt nacre dot after them.
struct AskWords: View {
    let text: String
    let streaming: Bool

    var body: some View {
        HStack(alignment: .lastTextBaseline, spacing: 5) {
            Text(text).font(Nacre.body).foregroundColor(Pearl.ink)
                .lineSpacing(2)
                .fixedSize(horizontal: false, vertical: true)
            if streaming {
                Circle().fill(AskStyle.nacreLine).frame(width: 9, height: 9)
                    .accessibilityHidden(true)
            }
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .padding(.horizontal, 4).padding(.top, 14)
        .accessibilityElement(children: .combine)
    }
}

/// The fact cards, whole, in the order the server found them.
struct AskFacts: View {
    let found: ChatFindings
    let open: (AskLink) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if let m = found.month { AskMonth(fact: m, open: open) }
            if let m = found.merchant { AskMerchant(fact: m, open: open) }
            if let s = found.search { AskSearch(fact: s, open: open) }
            if let c = found.cards { AskCards(fact: c) }
            if let a = found.spending, !a.nothing { AskSpending(answer: a, open: open) }
            if let s = found.subscriptions, !s.rows.isEmpty { AskRows(rows: s.rows, open: open) }
        }
    }
}

/// ask.css values the cards share.
enum AskStyle {
    static let nacreLine = LinearGradient(colors: [Color(hex: 0xFF8FB1), Color(hex: 0xC9A8FF), Color(hex: 0x8FE0D4)],
                                          startPoint: .leading, endPoint: .trailing)
    /// `.fact .big`: Fraunces 34 semibold, tabular.
    static let big = Font.custom("Fraunces-SemiBold", size: 34, relativeTo: .largeTitle)
    /// `.over`: 13 medium caps, tracked 0.78, muted.
    static func over(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
    }
}

/// `.fact`: an overline, the figure Python worked out, its line, then more.
struct AskFactCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0, content: content)
            .padding(.horizontal, 16).padding(.top, 16).padding(.bottom, 14)
            .frame(maxWidth: .infinity, alignment: .leading)
            .apCard()
            .padding(.top, 10)
    }
}

/// `.kv` inside a fact card: 44 high, the value semibold in its tone.
struct AskKV: View {
    let key: String
    let value: String
    var tone: Color = Pearl.ink
    var strong = true

    var body: some View {
        HStack {
            Text(key).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            Spacer(minLength: 8)
            Text(value).font(strong ? Nacre.headline : Nacre.body).foregroundColor(tone)
                .monospacedDigit().pearlAmountFit()
        }
        .frame(minHeight: 44)
        .accessibilityElement(children: .combine)
    }
}

struct AskDivider: View {
    var body: some View { Rectangle().fill(APlus.separator).frame(height: 0.5).accessibilityHidden(true) }
}

// MARK: PC-22 and PC-26b · a month

struct AskMonth: View {
    let fact: MonthFact
    let open: (AskLink) -> Void

    var body: some View {
        if fact.current {
            AskThisMonth(fact: fact)
        } else {
            AskPastMonth(fact: fact, open: open)
        }
    }
}

/// PC-22: NOVEMBER SO FAR, the figure, "Usual by Nov 27: $1,090", the
/// compare bar with the usual-by-now tick, and what's furthest past usual.
struct AskThisMonth: View {
    let fact: MonthFact

    var body: some View {
        AskFactCard {
            AskStyle.over(ChatWords.soFar(fact.name))
            Text(Format.whole(fact.spent)).font(AskStyle.big).foregroundColor(Pearl.moneyOut)
                .monospacedDigit().pearlAmountFit().padding(.top, 2)
            if let usual = fact.usualByNow {
                Text("Usual by \(Format.short(fact.month + String(format: "-%02d", fact.day ?? 1))): \(Format.whole(usual))")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                AskCompare(spent: fact.spent, usual: usual)
            }
            if !fact.changes.isEmpty {
                AskDivider().padding(.top, 12).padding(.bottom, 2)
                ForEach(Array(fact.changes.enumerated()), id: \.offset) { i, c in
                    if i > 0 { AskDivider() }
                    AskKV(key: c.category, value: "+\(Format.whole(c.over)) on usual", tone: Pearl.muted, strong: false)
                }
            }
        }
        .accessibilityElement(children: .combine)
    }
}

/// `.cmp`: this month's bar against the usual-by-now tick, and its key.
struct AskCompare: View {
    let spent: Double
    let usual: Double

    var body: some View {
        let top = max(spent, usual, 1) * 1.15
        VStack(alignment: .leading, spacing: 8) {
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(APlus.trackSoft).frame(height: 10)
                    Capsule().fill(Pearl.moneyOut).frame(width: g.size.width * spent / top, height: 10)
                    RoundedRectangle(cornerRadius: 1).fill(Pearl.ink)
                        .frame(width: 2, height: 18)
                        .offset(x: g.size.width * usual / top - 1)
                }
                .frame(height: 18)
            }
            .frame(height: 18)
            HStack(spacing: 16) {
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 3).fill(Pearl.moneyOut).frame(width: 10, height: 10)
                    Text("This month")
                }
                HStack(spacing: 6) {
                    RoundedRectangle(cornerRadius: 1).fill(Pearl.ink).frame(width: 2, height: 12)
                    Text("Usual by now")
                }
            }
            .font(Nacre.footnote).foregroundColor(Pearl.muted)
        }
        .padding(.top, 10)
        .accessibilityHidden(true)
    }
}

/// PC-26b: Money in, Spent, Allowance left; WHERE IT WENT MOST; See October in Cash flow.
struct AskPastMonth: View {
    let fact: MonthFact
    let open: (AskLink) -> Void

    var body: some View {
        VStack(spacing: 0) {
            AskFactCard {
                AskStyle.over(fact.name)
                AskKV(key: "Money in", value: "+" + Format.whole(fact.moneyIn), tone: Pearl.moneyIn).padding(.top, 4)
                AskDivider()
                AskKV(key: "Spent", value: Format.whole(fact.spent), tone: Pearl.moneyOut)
                AskDivider()
                if let over = fact.overBy {
                    AskKV(key: "Over", value: Format.whole(over), tone: Pearl.danger)
                } else {
                    AskKV(key: "Allowance left", value: Format.whole(fact.allowanceLeft ?? 0))
                }
            }
            if !fact.top.isEmpty {
                AskFactCard {
                    AskStyle.over("Where it went most")
                    ForEach(Array(fact.top.enumerated()), id: \.offset) { i, t in
                        if i > 0 { AskDivider() }
                        AskShareRow(name: t.category, amount: t.amount,
                                    width: t.amount / max(fact.top.first?.amount ?? 1, 1))
                    }
                }
            }
            ChatQuietLink(title: "See \(fact.name) in Cash flow") { open(.month(fact.month)) }
                .padding(.top, 10)
        }
    }
}

/// `.crow`: a category, its amount, and its share bar under it.
struct AskShareRow: View {
    let name: String
    let amount: Double
    let width: Double

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            HStack {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                Text(Format.whole(amount)).font(Nacre.headline).foregroundColor(Pearl.moneyOut).monospacedDigit()
            }
            GeometryReader { g in
                ZStack(alignment: .leading) {
                    Capsule().fill(APlus.trackSoft)
                    Capsule().fill(Pearl.moneyOut).frame(width: g.size.width * min(max(width, 0), 1))
                }
            }
            .frame(height: 6)
            .accessibilityHidden(true)
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

// MARK: PC-26a · a shop's history

struct AskMerchant: View {
    let fact: MerchantFact
    let open: (AskLink) -> Void

    private var line: String {
        let visits = "\(fact.visits) visit\(fact.visits == 1 ? "" : "s")"
        guard let each = fact.average, fact.visits > 0 else { return visits }
        return "\(visits) \u{00B7} about \(Format.whole(each)) each"
    }

    var body: some View {
        VStack(spacing: 0) {
            AskFactCard {
                AskStyle.over(ChatWords.shopYear(fact.merchant, fact.year))
                Text(Format.whole(fact.total)).font(AskStyle.big).foregroundColor(Pearl.moneyOut)
                    .monospacedDigit().pearlAmountFit().padding(.top, 2)
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                if fact.visits > 0 { AskMonthBars(months: fact.months) }
            }
            .accessibilityElement(children: .combine)
            if fact.visits > 0 {
                ChatQuietLink(title: ChatWords.seeAll(fact.visits)) { open(.search(fact.query)) }
                    .padding(.top, 10)
            }
        }
    }
}

/// `.mbars`: a bar per month, 84 high; this month's at full strength.
struct AskMonthBars: View {
    let months: [MerchantFact.Month]

    var body: some View {
        let top = max(months.map(\.amount).max() ?? 1, 1)
        HStack(alignment: .bottom, spacing: 5) {
            ForEach(Array(months.enumerated()), id: \.offset) { _, m in
                VStack(spacing: 4) {
                    Spacer(minLength: 0)
                    UnevenBar()
                        .fill(Pearl.moneyOut.opacity(m.now ? 1 : 0.55))
                        .frame(height: max(2, 58 * m.amount / top))
                    Text(m.label)
                        .font(.custom(m.now ? "Figtree-SemiBold" : "Figtree-Regular", size: 11, relativeTo: .caption2))
                        .foregroundColor(m.now ? Pearl.ink : Pearl.muted)
                }
                .frame(maxWidth: .infinity)
            }
        }
        .frame(height: 84)
        .padding(.top, 14)
        .accessibilityHidden(true)
    }
}

/// 4 at the top, 2 at the bottom (`.mbars i`).
struct UnevenBar: Shape {
    func path(in r: CGRect) -> Path {
        let t = min(4, r.height / 2, r.width / 2), b = min(2, r.height / 2)
        var p = Path()
        p.move(to: CGPoint(x: r.minX, y: r.maxY - b))
        p.addLine(to: CGPoint(x: r.minX, y: r.minY + t))
        p.addQuadCurve(to: CGPoint(x: r.minX + t, y: r.minY), control: CGPoint(x: r.minX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX - t, y: r.minY))
        p.addQuadCurve(to: CGPoint(x: r.maxX, y: r.minY + t), control: CGPoint(x: r.maxX, y: r.minY))
        p.addLine(to: CGPoint(x: r.maxX, y: r.maxY - b))
        p.addQuadCurve(to: CGPoint(x: r.maxX - b, y: r.maxY), control: CGPoint(x: r.maxX, y: r.maxY))
        p.addLine(to: CGPoint(x: r.minX + b, y: r.maxY))
        p.addQuadCurve(to: CGPoint(x: r.minX, y: r.maxY - b), control: CGPoint(x: r.minX, y: r.maxY))
        p.closeSubpath()
        return p
    }
}

// MARK: PC-26c · a search

struct AskSearch: View {
    let fact: SearchFact
    let open: (AskLink) -> Void

    var body: some View {
        VStack(spacing: 0) {
            if !fact.rows.isEmpty { AskRows(rows: fact.rows, open: open) }
            if fact.count > fact.rows.count {
                ChatQuietLink(title: ChatWords.seeAll(fact.count)) { open(.search(fact.query)) }
                    .padding(.top, 10)
            }
        }
    }
}

/// Rows on one card, each opening its page.
struct AskRows: View {
    let rows: [BriefTransaction]
    let open: (AskLink) -> Void

    var body: some View {
        APCard {
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, t in
                if i > 0 { APSeparator() }
                Button { open(.transaction(t.id)) } label: {
                    APPaymentRow(name: t.name, line: Format.short(t.date),
                                 money: t.inflow ? .into(t.shownAmount) : .out(t.shownAmount))
                        .padding(.horizontal, 16).padding(.vertical, 8)
                        .frame(minHeight: 56)
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityHint("Opens it")
            }
        }
        .padding(.top, 10)
    }
}

/// Today's spending answer on Ask Pearl: its total and usual, then the rows.
struct AskSpending: View {
    let answer: SpendingAnswer
    let open: (AskLink) -> Void

    var body: some View {
        VStack(spacing: 0) {
            if let total = answer.total {
                AskFactCard {
                    AskStyle.over(answer.title ?? "")
                    Text(Format.whole(total)).font(AskStyle.big).foregroundColor(Pearl.moneyOut)
                        .monospacedDigit().pearlAmountFit().padding(.top, 2)
                    if let usual = answer.usual {
                        Text("Usual month: \(Format.whole(usual))").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .accessibilityElement(children: .combine)
            }
            if !answer.rows.isEmpty { AskRows(rows: Array(answer.rows.prefix(10)), open: open) }
        }
    }
}

// MARK: PC-26d · credit cards

struct AskCards: View {
    let fact: CardsFact

    var body: some View {
        VStack(spacing: 10) {
            ForEach(Array(fact.cards.enumerated()), id: \.offset) { _, c in AskCreditCard(card: c) }
        }
        .padding(.top, 10)
    }
}

/// One card by its nickname: due pill, Spent this month, the limit bar.
/// The bar is ink until 80% of the limit, the softer limit amber from
/// there (`Pearl.limitNear*`), red only over it.
struct AskCreditCard: View {
    let card: CardsFact.Card

    /// The words under the bar: muted, `limitNear` near the limit, red over it.
    private var tone: Color {
        switch card.state {
        case "over": return Pearl.danger
        case "near": return Pearl.limitNear
        default: return Pearl.muted
        }
    }

    /// The bar's fill: ink at 70%, `limitNearBar` from 80%, red only over the limit.
    private var fill: Color {
        switch card.state {
        case "over": return Pearl.danger
        case "near": return Pearl.limitNearBar
        default: return Pearl.ink.opacity(0.7)
        }
    }

    private var right: String {
        switch card.state {
        case "over": return "Over its limit"
        case "near": return "Close to its limit"
        default: return "\(Int(((card.used ?? 0) * 100).rounded()))% used"
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            HStack(spacing: 8) {
                Text(card.name).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(1)
                Spacer(minLength: 8)
                if let due = card.due { AskDuePill(text: "Due \(Format.short(due))", state: card.state) }
            }
            AskKV(key: "Spent this month", value: Format.whole(card.spent), tone: Pearl.moneyOut)
                .font(Nacre.subheadline)
                .padding(.top, 6)
            if let balance = card.balance, let limit = card.limit {
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        Capsule().fill(APlus.trackSoft)
                        Capsule().fill(fill).frame(width: g.size.width * min(max(balance / limit, 0), 1))
                    }
                }
                .frame(height: 10)
                .padding(.top, 12)
                .accessibilityHidden(true)
                HStack {
                    Text("\(Format.whole(balance)) of \(Format.whole(limit))")
                    Spacer(minLength: 8)
                    Text(right)
                }
                .font(card.state == "ok" ? Nacre.footnote : Nacre.label)
                .foregroundColor(tone)
                .monospacedDigit()
                .padding(.top, 6)
            }
        }
        .padding(16)
        .apCard()
        .accessibilityElement(children: .combine)
    }
}

/// `.pill` ("Due Dec 3"); `.pill.warn` near the limit; the danger wash over it.
struct AskDuePill: View {
    let text: String
    let state: String

    var body: some View {
        Text(text)
            .font(state == "ok" ? Nacre.footnote : Nacre.label)
            .foregroundColor(state == "over" ? Pearl.danger : state == "near" ? Pearl.limitNear : Pearl.ink)
            .padding(.horizontal, 12).frame(height: 28)
            .background(Capsule().fill(state == "over" ? ProfileTone.dangerWash
                                       : state == "near" ? Pearl.limitNearWash : APlus.chip))
            .fixedSize()
    }
}

// MARK: - PC-22 · the suggestion

/// Pearl's guess language: a dashed rose outline, SUGGESTION over it, the
/// words, and one pill whose action only opens a screen.
struct AskSuggestionCard: View {
    let suggestion: AskSuggestion
    let open: (AskLink) -> Void

    private var link: AskLink? {
        switch suggestion.open {
        case "category": return suggestion.category.map { .category($0, month: suggestion.month) }
        case "cashflow", "search": return suggestion.query.map { .search($0) }
        case "month": return suggestion.month.map { .month($0) }
        default: return nil
        }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 6) {
                Image(systemName: "sparkle").font(.system(size: 12, weight: .semibold))
                Text("SUGGESTION").font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
            }
            .foregroundColor(Pearl.link)
            .accessibilityHidden(true)
            Text(suggestion.text).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let link = link {
                Button(suggestion.label) { open(link) }
                    .font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.link)
                    .padding(.horizontal, 14).frame(height: 32)
                    .background(Capsule().fill(APlus.actionWash))
                    .contentShape(Rectangle().inset(by: -6))
                    .buttonStyle(.plain)
                    .padding(.top, 4)
                    .accessibilityIdentifier("ask-suggestion")
            }
        }
        .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .overlay(RoundedRectangle(cornerRadius: 24, style: .continuous)
            .strokeBorder(Pearl.link, style: StrokeStyle(lineWidth: 1.5, dash: [5, 4])))
        .padding(.top, 12)
        .accessibilityElement(children: .contain)
        .accessibilityLabel("Suggestion")
    }
}

/// `.aihint`: the nacre dot and one quiet 13 pt line.
struct AskQuietLine: View {
    let text: String

    var body: some View {
        HStack(spacing: 8) {
            Circle().fill(AskStyle.nacreLine).frame(width: 10, height: 10).accessibilityHidden(true)
            Text(text).font(Nacre.footnote).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(.horizontal, 4).padding(.top, 14)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - PC-23 · couldn't answer, offline

/// "I can't answer that one yet. Here's what I can do:" and four rows it
/// can always answer, with no model at all.
struct AskCouldnt: View {
    let said: String
    let examples: [String]
    let ask: (String) -> Void
    let search: () -> Void

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if !said.isEmpty { ChatYou(text: said) }
                ChatLine(text: ChatWords.couldnt)
                APCard {
                    row("bubble.left", "How\u{2019}s this month going?") { ask("How\u{2019}s this month going?") }
                    APSeparator(afterFace: false)
                    row("bag", "Spending at one shop") { ask(examples.count > 1 ? examples[1] : "Where did my money go last month?") }
                    APSeparator(afterFace: false)
                    row("creditcard", "My credit cards") { ask("When are my cards due?") }
                    APSeparator(afterFace: false)
                    row("magnifyingglass", "Search Cash flow", action: search)
                }
                .padding(.top, 10)
            }
            .chatPage()
        }
    }

    private func row(_ symbol: String, _ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) { AskRow(symbol: symbol, title: title) }.buttonStyle(.plain)
    }
}

/// `.banner.off`: offline. The chat stays under it; Send waits.
struct AskOfflineBanner: View {
    var body: some View {
        HStack(spacing: 10) {
            Image(systemName: "wifi.slash").font(.system(size: 15, weight: .medium)).accessibilityHidden(true)
            Text(ChatWords.offline).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Nacre.subheadline).foregroundColor(Pearl.ink)
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(APlus.chip))
        .padding(.horizontal, 16).padding(.top, 8)
        .accessibilityElement(children: .combine)
        .accessibilityIdentifier("ask-offline")
    }
}
