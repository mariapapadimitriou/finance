import Foundation
import Combine

// Pearl chat (PC-01 to PC-13; note 1340:8893, THL-117, THL-139, THL-213,
// THL-254): the logic, in plain types. No views, no UIKit and no
// FoundationModels here, so ios/tools/check_chat.py compiles this file for
// the Mac with Models.swift and runs the chat on a scripted model.
//
// Nothing changes until she confirms (product owner, 2026-11-15). That's
// structural, not a promise:
//
//   * The model only ever gets a `ChatTools`. It holds a `ChatReader` (which
//     can GET, and POST only to the server's read-only /api/chat/*) and the
//     findings the tools collected. It has no APIClient, no ChatWriting and
//     no ChatEngine, so no tool can change anything.
//   * What the tools find becomes `ProposedAction` values: cards held in the
//     chat. Holding one changes nothing.
//   * `ChatExecutor` is the only thing that writes, through `ChatWriting`, and
//     only for a `Decision` with a `UserTap`. Only ChatCards.swift's buttons
//     make a UserTap; check_chat.py fails if any other file does, or if the
//     model's file reaches for a writer.

// MARK: - What the server says (finance/chat.py)

/// GET /api/chat: PB-01's "has a suggestion", and what the model may name.
struct ChatStart: Decodable {
    let suggest: Bool
    let categories: [String]
    let people: [String]
    let today: String
}

/// The days she meant: "from the weekend" (PC-05), "from Sat–Sun" (PC-10).
struct ChatWindow: Decodable, Hashable {
    let start: String
    let end: String
    let days: [String]
    let label: String
    let span: String
}

/// PC-05: one transaction Pearl would sort the way she said. One card each.
struct SortProposal: Decodable, Hashable, Identifiable {
    let id: String
    /// Needs a look's key ("cat:<id>"): Skip leaves it there.
    let key: String
    let category: String
    let was: String?
    /// PC-06: "Maybe split with Jo and Sam?", as a suggestion only.
    let splitWith: [String]
    /// Boxed, as Transaction's big parts are (Boxed.swift): a card is passed
    /// around a SwiftUI body and must stay small on the stack (check_stack.py).
    @Boxed var txn: BriefTransaction
    /// The Needs a look question, for the card's What was this? (T-96).
    @Boxed var item: Review.Item?

    enum CodingKeys: String, CodingKey {
        case id, key, category, was, txn, item
        case splitWith = "split_with"
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        id = try c.decode(String.self, forKey: .id)
        key = try c.decode(String.self, forKey: .key)
        category = try c.decode(String.self, forKey: .category)
        was = try? c.decodeIfPresent(String.self, forKey: .was)
        splitWith = (try? c.decodeIfPresent([String].self, forKey: .splitWith)) ?? []
        _txn = Boxed(wrappedValue: try c.decode(BriefTransaction.self, forKey: .txn))
        _item = Boxed(wrappedValue: (try? c.decodeIfPresent(Review.Item.self, forKey: .item)) ?? nil)
    }
}

/// POST /api/chat/tell.
struct TellReply: Decodable {
    let said: String
    let category: String?
    let people: [String]
    let window: ChatWindow
    let open: Int
    let matched: Int
    let nothing: Bool
    let proposals: [SortProposal]
    /// "A guess for 7 of 9 from the weekend" (PC-05), or PC-10's line.
    let line: String

    enum CodingKeys: String, CodingKey { case said, category, people, window, open, matched, nothing, proposals, line }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        said = (try? c.decode(String.self, forKey: .said)) ?? ""
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        people = (try? c.decodeIfPresent([String].self, forKey: .people)) ?? []
        window = try c.decode(ChatWindow.self, forKey: .window)
        open = (try? c.decode(Int.self, forKey: .open)) ?? 0
        matched = (try? c.decode(Int.self, forKey: .matched)) ?? 0
        nothing = (try? c.decode(Bool.self, forKey: .nothing)) ?? true
        proposals = (try? c.decodeIfPresent([Lenient<SortProposal>].self, forKey: .proposals))?
            .compactMap { $0.value } ?? []
        line = (try? c.decode(String.self, forKey: .line)) ?? ""
    }
}

/// POST /api/chat/spending: PC-04's numbers and the rows behind them.
struct SpendingAnswer: Decodable, Hashable {
    let nothing: Bool
    /// "Dining, October".
    let title: String?
    let category: String?
    let merchant: String?
    let month: String
    let total: Double?
    let usual: Double?
    let count: Int?
    let rows: [BriefTransaction]
    /// The answer in words, when the model gives none.
    let line: String

    enum CodingKeys: String, CodingKey { case nothing, title, category, merchant, month, total, usual, count, rows, line }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        nothing = (try? c.decode(Bool.self, forKey: .nothing)) ?? true
        title = try? c.decodeIfPresent(String.self, forKey: .title)
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        merchant = try? c.decodeIfPresent(String.self, forKey: .merchant)
        month = (try? c.decode(String.self, forKey: .month)) ?? ""
        total = try? c.decodeIfPresent(Double.self, forKey: .total)
        usual = try? c.decodeIfPresent(Double.self, forKey: .usual)
        count = try? c.decodeIfPresent(Int.self, forKey: .count)
        rows = (try? c.decodeIfPresent([Lenient<BriefTransaction>].self, forKey: .rows))?.compactMap { $0.value } ?? []
        line = (try? c.decode(String.self, forKey: .line)) ?? ""
    }
}

/// GET /api/chat/subscriptions.
struct SubscriptionsAnswer: Decodable {
    let count: Int
    let monthly: Double
    let rows: [BriefTransaction]
    let line: String

    enum CodingKeys: String, CodingKey { case count, monthly, rows, line }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        count = (try? c.decode(Int.self, forKey: .count)) ?? 0
        monthly = (try? c.decode(Double.self, forKey: .monthly)) ?? 0
        rows = (try? c.decodeIfPresent([Lenient<BriefTransaction>].self, forKey: .rows))?.compactMap { $0.value } ?? []
        line = (try? c.decode(String.self, forKey: .line)) ?? ""
    }
}

/// GET /api/chat/asks: the trip and pattern cards Quick sort has too.
struct ChatAsks: Decodable {
    let patterns: [PatternAsk]
    let trips: [TripAsk]

    enum CodingKeys: String, CodingKey { case patterns, trips }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        patterns = (try? c.decodeIfPresent([Lenient<PatternAsk>].self, forKey: .patterns))?.compactMap { $0.value } ?? []
        trips = (try? c.decodeIfPresent([Lenient<TripAsk>].self, forKey: .trips))?.compactMap { $0.value } ?? []
    }
}

/// POST /api/chat/plan: PC-12's "Make a Dining plan of $225 a month?". The
/// amount is on the budgets' 5% steps, so it's what Set it keeps.
struct PlanProposal: Decodable, Hashable {
    let nothing: Bool
    let category: String?
    let usual: Double?
    let pct: Int?
    let amount: Double?
    let months: Int?
    let line: String?

    enum CodingKeys: String, CodingKey { case nothing, category, usual, pct, amount, months, line }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        nothing = (try? c.decode(Bool.self, forKey: .nothing)) ?? true
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        usual = try? c.decodeIfPresent(Double.self, forKey: .usual)
        pct = try? c.decodeIfPresent(Int.self, forKey: .pct)
        amount = try? c.decodeIfPresent(Double.self, forKey: .amount)
        months = try? c.decodeIfPresent(Int.self, forKey: .months)
        line = try? c.decodeIfPresent(String.self, forKey: .line)
    }

    init(category: String, usual: Double, pct: Int, amount: Double, months: Int) {
        nothing = false
        self.category = category
        self.usual = usual
        self.pct = pct
        self.amount = amount
        self.months = months
        line = nil
    }
}

/// What a write endpoint says when the chat needs nothing back.
struct ChatOK: Decodable {}

// MARK: - Proposals

/// Something Pearl proposes, held as a card in the chat. A value: holding one
/// changes nothing. Only `ChatExecutor`, on her tap, acts on it. Indirect:
/// its payloads live on the heap, so it's small on the stack.
indirect enum ProposedAction: Identifiable, Hashable {
    /// PC-05 / PC-06: one transaction, sorted the way she said.
    case sort(SortProposal)
    /// PC-08: one card for the whole trip.
    case trip(TripAsk)
    /// PC-09: one card for the whole pattern.
    case pattern(PatternAsk)
    /// PC-12: a plan for one category.
    case plan(PlanProposal)

    var id: String {
        switch self {
        case .sort(let s): return s.id
        case .trip(let t): return "trip:" + t.id
        case .pattern(let p): return "pattern:" + p.id
        case .plan(let p): return "plan:" + (p.category ?? "")
        }
    }
}

// MARK: - Reading, the only thing the model's tools can do

/// Reads from Pearl's server. Nothing that can write conforms to this in the
/// chat: the app's `APIChatReading` only GETs, and POSTs only to /api/chat/*.
protocol ChatReading {
    func get<T: Decodable>(_ path: String) async throws -> T
    /// A read that carries what she said (POST /api/chat/*; the server keeps none of it).
    func read<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T
}

/// The chat's reads, by name. Every path is under api/chat.
struct ChatReader {
    private let io: ChatReading

    init(_ io: ChatReading) { self.io = io }

    func start() async throws -> ChatStart { try await io.get("api/chat") }

    func tell(_ text: String, category: String? = nil, days: [String]? = nil, people: [String]? = nil,
              ids: [String]? = nil) async throws -> TellReply {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        if let days = days, !days.isEmpty { body["days"] = days }
        if let people = people, !people.isEmpty { body["people"] = people }
        if let ids = ids, !ids.isEmpty { body["ids"] = ids }
        return try await io.read("api/chat/tell", body)
    }

    func spending(_ text: String, category: String? = nil, month: String? = nil,
                  merchant: String? = nil) async throws -> SpendingAnswer {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        if let month = month { body["month"] = month }
        if let merchant = merchant { body["merchant"] = merchant }
        return try await io.read("api/chat/spending", body)
    }

    func subscriptions() async throws -> SubscriptionsAnswer { try await io.get("api/chat/subscriptions") }

    func asks() async throws -> ChatAsks { try await io.get("api/chat/asks") }

    func plan(_ text: String, category: String? = nil) async throws -> PlanProposal {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        return try await io.read("api/chat/plan", body)
    }
}

/// What the tools found in one turn.
struct ChatFindings {
    var tell: TellReply?
    var spending: SpendingAnswer?
    var subscriptions: SubscriptionsAnswer?
    var trips: [TripAsk]?
    var patterns: [PatternAsk]?
    var plan: PlanProposal?
}

/// The model's tools, and everything they can touch: a reader, and the
/// findings they collect for the chat to show. No writer, no engine.
actor ChatTools {
    private let reader: ChatReader
    /// PC-12 is off until Your plan exists (Features.chatPlans).
    nonisolated let allowsPlans: Bool
    private(set) var found = ChatFindings()

    init(reader: ChatReader, allowsPlans: Bool) {
        self.reader = reader
        self.allowsPlans = allowsPlans
    }

    func tell(_ text: String, category: String? = nil, days: [String]? = nil, people: [String]? = nil,
              ids: [String]? = nil) async throws -> TellReply {
        let reply = try await reader.tell(text, category: category, days: days, people: people, ids: ids)
        found.tell = reply
        return reply
    }

    func spending(_ text: String, category: String? = nil, month: String? = nil,
                  merchant: String? = nil) async throws -> SpendingAnswer {
        let answer = try await reader.spending(text, category: category, month: month, merchant: merchant)
        found.spending = answer
        return answer
    }

    func subscriptions() async throws -> SubscriptionsAnswer {
        let answer = try await reader.subscriptions()
        found.subscriptions = answer
        return answer
    }

    func trips() async throws -> [TripAsk] {
        let asks = try await reader.asks()
        found.trips = asks.trips
        return asks.trips
    }

    func patterns() async throws -> [PatternAsk] {
        let asks = try await reader.asks()
        found.patterns = asks.patterns
        return asks.patterns
    }

    func plan(_ text: String, category: String? = nil) async throws -> PlanProposal? {
        guard allowsPlans else { return nil }
        let p = try await reader.plan(text, category: category)
        found.plan = p
        return p
    }
}

// MARK: - The model

/// The starter she tapped (PC-03), so her next words are read that way.
enum ChatMode: String {
    case tell, ask, subscriptions, trips
}

/// What the model says back: a short answer in its own words, and her words
/// said back to her ("You said you went out with friends Saturday."). Either
/// may be nil; the chat then uses the server's own line.
struct BrainReply {
    var text: String?
    var echo: String?
}

/// Reads what she said and uses the tools. It can only read and propose:
/// `tools` is all it gets.
protocol PearlBrain {
    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply
}

/// The deterministic model: routes her words to one tool and leaves the
/// reading of them to the server (finance/chat.py). For check_chat.py, for
/// DEBUG's -pearl-chat-stub, and the fallback when Apple Intelligence can't
/// answer (a guardrail, a refusal, a full context).
struct ScriptedBrain: PearlBrain {
    enum Route: Equatable { case tell, spending, subscriptions, trips, plan }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        switch Self.route(text, mode, plans: tools.allowsPlans) {
        case .tell: _ = try await tools.tell(text)
        case .spending: _ = try await tools.spending(text)
        case .subscriptions: _ = try await tools.subscriptions()
        case .trips: _ = try await tools.trips()
        case .plan: _ = try await tools.plan(text)
        }
        return BrainReply()
    }

    static func route(_ text: String, _ mode: ChatMode?, plans: Bool) -> Route {
        switch mode {
        case .tell?: return .tell
        case .ask?: return .spending
        case .subscriptions?: return .subscriptions
        case .trips?: return .trips
        case nil: break
        }
        let words = " " + text.lowercased().replacingOccurrences(of: "?", with: " ?") + " "
        func has(_ any: [String]) -> Bool { any.contains { words.contains($0) } }
        if plans && has([" plan ", " plan.", " budget"]) { return .plan }
        if has(["subscription"]) { return .subscriptions }
        if has([" trip", " travel", " vacation", " holiday"]) { return .trips }
        if has([" how much", " what did i spend", " spent ", " spend ", " spending", " ?", " plan ", " budget"]) {
            return .spending
        }
        return .tell
    }
}

// MARK: - Writing, only on her tap

/// Proof of a tap on a card's Yes or Skip, or PC-12's Set it or Not now.
/// Only ChatCards.swift's buttons make one (check_chat.py checks).
struct UserTap {
    let control: String
    init(_ control: String) { self.control = control }
}

/// Writes to Pearl's server: the app's APIClient, given only to the executor.
protocol ChatWriting {
    func post<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T
    func put<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T
}

/// What she decided on a card.
enum Decision {
    /// Yes (PC-05, PC-08, PC-09) or Set it (PC-12).
    case yes(ProposedAction)
    /// Yes on a card she changed on its page or in Who was it with? (PC-06):
    /// a split or another answer held for this Yes, sent the way that page
    /// sends it.
    case held(SortProposal, label: String, send: () async throws -> Void)
    /// Skip, or Not now. A told guess or a plan: no request at all. A trip
    /// or a pattern: its Skip, as in Quick sort.
    case skip(ProposedAction)
}

/// What happened, for the chat to say.
enum Performed: Equatable {
    case nothing
    case sorted
    case skipped
    /// "Done. Trip to Montréal made."
    case trip(id: String, name: String, line: String)
    /// "Done. Ana’s deposits rule made."
    case pattern(title: String)
    /// "Done. Dining plan set to $225 a month."
    case plan(category: String, amount: Double)
}

/// The only thing in the chat that changes the app, each through the
/// endpoint that change already uses (finance/chat.py lists them).
struct ChatExecutor {
    private let writer: ChatWriting

    init(writer: ChatWriting) { self.writer = writer }

    func perform(_ decision: Decision, tap: UserTap) async throws -> Performed {
        switch decision {
        case .yes(.sort(let s)):
            // A told guess is this one only: no rule for the merchant.
            let _: MarkReply = try await writer.post("api/transactions/\(s.txn.id)/mark",
                                                     ["case": "spending", "category": s.category, "remember": false])
            return .sorted
        case .held(_, _, let send):
            try await send()
            return .sorted
        case .yes(.trip(let t)):
            struct Made: Decodable { let trip: Trip? }
            let made: Made = try await writer.post("api/trips/asks/\(Self.path(t.id))/yes", [:])
            let name = made.trip?.name ?? t.name ?? "Trip"
            return .trip(id: made.trip?.id ?? t.id, name: name.isEmpty ? "Trip" : name, line: made.trip?.line ?? t.line)
        case .yes(.pattern(let p)):
            let _: ChatOK = try await writer.post("api/pattern-sort/asks/\(p.id)/yes", ["how": "pc09"])
            return .pattern(title: p.title)
        case .yes(.plan(let p)):
            guard let category = p.category, let pct = p.pct, let amount = p.amount else { return .nothing }
            let _: ChatOK = try await writer.put("api/category-budgets", ["category": category, "pct": pct])
            return .plan(category: category, amount: amount)
        case .skip(.sort), .skip(.plan):
            // PC-07: skipped ones stay in Needs a look; Not now changes nothing.
            return .skipped
        case .skip(.trip(let t)):
            let _: ChatOK = try await writer.post("api/trips/asks/\(Self.path(t.id))/skip", [:])
            return .skipped
        case .skip(.pattern(let p)):
            let _: ChatOK = try await writer.post("api/pattern-sort/asks/\(p.id)/skip", [:])
            return .skipped
        }
    }

    private static func path(_ id: String) -> String {
        id.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? id
    }
}

// MARK: - The words (note 1340:8893)

enum ChatWords {
    static let placeholder = "Message Pearl"
    static let onDevice = "Worked out on this iPhone. Nothing leaves it."
    static let nothingChanged = "Okay, nothing changed."

    /// PC-04's quote, and PC-12's "You: “…”".
    static func quote(_ said: String) -> String { "\u{201C}\(said)\u{201D}" }
    static func youSaid(_ said: String) -> String { "You: \u{201C}\(said)\u{201D}" }

    /// PC-05's first line under the card, when the model didn't say it back.
    static func echo(_ said: String) -> String { "You said \u{201C}\(said)\u{201D}." }

    /// PC-05: "Yes sorts it as Dining. Tap the card for more."; PC-06 with a split suggestion.
    static func yesSorts(_ category: String, split: Bool) -> String {
        split ? "Yes sorts it as \(category), all yours. To split it, tap Maybe split."
            : "Yes sorts it as \(category). Tap the card for more."
    }

    /// PC-06's pill: "Maybe split with Jo and Sam?".
    static func maybeSplit(_ names: [String]) -> String { "Maybe split with \(Format.andList(names))?" }

    /// PC-07.
    static func sortedTitle(sorted: Int, left: Int) -> String {
        [sorted > 0 ? "Sorted \(sorted)." : nil, left > 0 ? "\(left) left for later." : nil]
            .compactMap { $0 }.joined(separator: " ")
    }

    static func sortedBody(left: Int) -> String {
        let rest = "What you told Pearl is forgotten now."
        switch left {
        case 0: return rest
        case 1: return "The 1 is in Needs a look. " + rest
        default: return "The \(left) are in Needs a look. " + rest
        }
    }

    static func seeThe(_ left: Int) -> String { "See the \(left)" }

    /// PC-08's line over the card: "Maybe a trip, Mar 4–9 · one card for all 23".
    static func tripLine(_ t: TripAsk) -> String {
        "Maybe a trip, \(Format.span(t.start, t.end)) · one card for all \(t.count)"
    }

    static let patternLine = "A pattern Pearl spotted · one card for all of them"

    /// PC-12.
    static func planLead(months: Int) -> String {
        "Here\u{2019}s a plan from your last \(months == 1 ? "month" : "\(months) months"). Nothing changes until you set it."
    }

    static func planQuestion(_ category: String, _ amount: Double) -> String {
        "Make a \(category) plan of \(Format.whole(amount)) a month?"
    }

    static func planSub(usual: Double) -> String {
        "Your usual is \(Format.whole(usual)). Setting it adds it to Your plan in Income and bills."
    }

    /// PC-13 and every other confirmation: "Done. {What} {set|made|renamed} …".
    static func planDone(_ category: String, _ amount: Double) -> String {
        "Done. \(category) plan set to \(Format.whole(amount)) a month."
    }

    static func tripDone(_ name: String) -> String { "Done. \(name) made." }
    static func patternDone(_ title: String) -> String { "Done. \(title) rule made." }

    /// "Was this a trip?" with none to ask about (engBOT's words; no frame).
    static let noTrip = "Pearl didn\u{2019}t spot a trip in the last four months."
}

// MARK: - The chat

/// Where a confirmation now lives (PC-13's link).
enum DoneLink: Hashable {
    case trip(String)
    case rules
    case plan
}

/// PC-13: "Done. …", a card saying where it lives, and a link there.
struct DoneNote: Hashable, Identifiable {
    let line: String
    let title: String
    let place: String?
    let link: DoneLink?
    let linkLabel: String?
    var id: String { line }
}

/// A run of cards, one at a time (PC-05, PC-06, PC-08, PC-09). Never grouped,
/// no Yes to all.
struct Deck {
    let cards: [ProposedAction]
    var index = 0
    /// PC-05's "A guess for 7 of 9 from the weekend", for told guesses.
    let lead: String?
    /// Her words said back, under a told guess's card.
    let echo: String?
    var sorted = 0
    var left = 0
    var done: [DoneNote] = []

    var current: ProposedAction? { index < cards.count ? cards[index] : nil }
    var told: Bool { cards.contains { if case .sort = $0 { return true } else { return false } } }
    private var sorts: Int { cards.filter { if case .sort = $0 { return true } else { return false } }.count }

    /// The line over the card: "A guess for 7 of 9 from the weekend · 1 of 7",
    /// then "2 of 7"; a trip's or a pattern's own line.
    var position: String {
        switch current {
        case .sort?:
            let n = "\(index + 1) of \(sorts)"
            if index == 0, let lead = lead { return "\(lead) · \(n)" }
            return n
        case .trip(let t)?: return ChatWords.tripLine(t)
        case .pattern?: return ChatWords.patternLine
        case .plan?, nil: return ""
        }
    }
}

/// What the chat shows: one exchange at a time, as the frames draw it.
indirect enum ChatScreen {
    /// PC-03.
    case start
    /// Her words, while Pearl works it out (no frame: a spinner under them).
    case thinking(said: String)
    /// PC-04: her words, Pearl's answer, the totals and the rows behind it.
    case reply(said: String?, text: String, answer: SpendingAnswer?, rows: [BriefTransaction])
    /// PC-05, PC-06, PC-08, PC-09.
    case cards(Deck)
    /// PC-07.
    case sorted(sorted: Int, left: Int)
    /// PC-10.
    case nothing(line: String)
    /// PC-12.
    case plan(said: String, PlanProposal)
    /// PC-13, and the trip and pattern confirmations.
    case done(said: String?, [DoneNote])
    /// "Okay, nothing changed."
    case noChange(said: String?)
}

/// The chat's state. Starts fresh each time it opens (note 1340:8893).
@MainActor
final class ChatEngine: ObservableObject {
    @Published private(set) var screen: ChatScreen = .start
    /// The starter she tapped, for her next words.
    @Published var mode: ChatMode?
    /// A card's answer on its way.
    @Published private(set) var busy = false
    @Published var error: String?

    private let brain: PearlBrain
    private let reader: ChatReader
    private let executor: ChatExecutor
    private let allowsPlans: Bool
    private let describe: (Error) -> String
    private var said: String?

    init(brain: PearlBrain, reader: ChatReader, executor: ChatExecutor, allowsPlans: Bool,
         describe: @escaping (Error) -> String = { $0.localizedDescription }) {
        self.brain = brain
        self.reader = reader
        self.executor = executor
        self.allowsPlans = allowsPlans
        self.describe = describe
    }

    /// Opened: what Pearl has to suggest comes first (PB-01's shimmer), the
    /// same cards Quick sort has; else the starters.
    func open() async {
        guard let start = try? await reader.start(), start.suggest,
              let asks = try? await reader.asks() else { return }
        let cards = asks.patterns.map(ProposedAction.pattern) + asks.trips.map(ProposedAction.trip)
        if !cards.isEmpty { screen = .cards(Deck(cards: cards, lead: nil, echo: nil)) }
    }

    /// PC-03's starters. Find subscriptions and Was this a trip? answer at
    /// once; the other two wait for her words.
    func pick(_ starter: ChatMode) async {
        switch starter {
        case .tell, .ask:
            mode = starter
        case .subscriptions:
            await run(said: nil, text: "Find subscriptions", mode: .subscriptions)
        case .trips:
            await run(said: nil, text: "Was this a trip?", mode: .trips)
        }
    }

    /// Her words from the composer.
    func send(_ text: String) async {
        let text = text.trimmingCharacters(in: .whitespacesAndNewlines)
        guard !text.isEmpty, !busy else { return }
        let m = mode
        mode = nil
        await run(said: text, text: text, mode: m)
    }

    /// Back to the starters (PC-10's Tell it differently).
    func restart() {
        screen = .start
        said = nil
        error = nil
    }

    private func run(said: String?, text: String, mode: ChatMode?) async {
        self.said = said
        error = nil
        screen = .thinking(said: said ?? text)
        let tools = ChatTools(reader: reader, allowsPlans: allowsPlans)
        var reply = BrainReply()
        do {
            reply = try await brain.respond(to: text, mode: mode, tools: tools)
        } catch {
            // Apple Intelligence couldn't (a guardrail, a refusal, a full
            // context): the server reads her words instead.
            do {
                reply = try await ScriptedBrain().respond(to: text, mode: mode, tools: tools)
            } catch {
                screen = .reply(said: said, text: describe(error), answer: nil, rows: [])
                return
            }
        }
        show(await tools.found, reply, said: said)
    }

    /// The findings, as the screen the frames draw for them.
    func show(_ f: ChatFindings, _ reply: BrainReply, said: String?) {
        if let tell = f.tell {
            if tell.proposals.isEmpty {
                screen = .nothing(line: tell.line)
            } else {
                screen = .cards(Deck(cards: tell.proposals.map(ProposedAction.sort), lead: tell.line,
                                     echo: reply.echo ?? ChatWords.echo(tell.said)))
            }
            return
        }
        let asked = (f.patterns ?? []).map(ProposedAction.pattern) + (f.trips ?? []).map(ProposedAction.trip)
        if !asked.isEmpty {
            screen = .cards(Deck(cards: asked, lead: nil, echo: nil))
            return
        }
        if let p = f.plan, !p.nothing {
            screen = .plan(said: said ?? "", p)
            return
        }
        if let a = f.spending {
            screen = .reply(said: said, text: reply.text ?? a.line, answer: a.nothing ? nil : a, rows: a.rows)
            return
        }
        if let s = f.subscriptions {
            screen = .reply(said: said, text: reply.text ?? s.line, answer: nil, rows: s.rows)
            return
        }
        if f.trips != nil {
            screen = .reply(said: said, text: reply.text ?? ChatWords.noTrip, answer: nil, rows: [])
            return
        }
        let text = reply.text ?? f.plan?.line ?? ""
        screen = text.isEmpty ? .start : .reply(said: said, text: text, answer: nil, rows: [])
    }

    /// Her tap on a card. The only way the chat changes anything.
    func decide(_ decision: Decision, tap: UserTap) async {
        guard !busy else { return }
        busy = true
        defer { busy = false }
        do {
            let did = try await executor.perform(decision, tap: tap)
            error = nil
            advance(did)
        } catch {
            self.error = describe(error)
        }
    }

    private func advance(_ did: Performed) {
        switch screen {
        case .plan:
            if case .plan(let category, let amount) = did {
                screen = .done(said: said, [DoneNote(
                    line: ChatWords.planDone(category, amount), title: "\(category) plan \u{00B7} \(Format.whole(amount)) a month",
                    place: "It\u{2019}s in Profile \u{203A} Income and bills \u{203A} Your plan. Change or remove it there, or ask Pearl.",
                    link: .plan, linkLabel: "See it in Your plan")])
            } else {
                screen = .noChange(said: said)
            }
        case .cards(var deck):
            switch did {
            case .sorted: deck.sorted += 1
            case .skipped: deck.left += 1
            case .trip(let id, let name, let line):
                deck.done.append(DoneNote(line: ChatWords.tripDone(name), title: "\(name) \u{00B7} \(line)",
                                          place: "It\u{2019}s in Cash flow. Change or remove it there, or ask Pearl.",
                                          link: .trip(id), linkLabel: "See the trip"))
            case .pattern(let title):
                deck.done.append(DoneNote(line: ChatWords.patternDone(title), title: title,
                                          place: "It\u{2019}s in Profile \u{203A} Categories and rules. Change or remove it there, or ask Pearl.",
                                          link: .rules, linkLabel: "See it in Categories and rules"))
            case .nothing, .plan: break
            }
            deck.index += 1
            if deck.current != nil {
                screen = .cards(deck)
            } else if deck.told {
                screen = .sorted(sorted: deck.sorted, left: deck.left)
            } else if !deck.done.isEmpty {
                screen = .done(said: said, deck.done)
            } else {
                screen = .start
            }
        default:
            break
        }
    }
}
