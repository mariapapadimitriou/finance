import Foundation
import Combine
import os

// Pearl chat (PC-01 to PC-13; note 1340:8893, THL-117, THL-139, THL-213,
// THL-254) and Ask Pearl (PC-20 to PC-26, THL-308): the logic, in plain
// types. No views and no UIKit here, so ios/tools/check_chat.py compiles this
// file for the Mac with Models.swift and runs the chat on a scripted model.
//
// THL-308 (AI Phase 2, 2026-11-27): no model ever runs on the phone, not
// even as a fallback. Every iPhone asks Claude through Pearl's server
// (`CloudBrain`, POST /api/ask), and Python works out every number. With no
// server answer it falls back on `ScriptedBrain` and the server's own reading.
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
    /// The trip and pattern cards waiting (GET /api/chat/asks's), in the
    /// same reply so opening the chat is one trip to the server (2026-11-15).
    /// Nil from a server before that.
    let asks: ChatAsks?
    /// Ask Pearl (THL-308): "on", "off" or "unasked" (PC-24 asks first).
    let ask: String?
    /// PC-21's Try asking card: four questions, each sent with one tap.
    let examples: [String]?
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

/// POST /api/chat/plan: PC-12's "Make a Dining out plan of $220 a month?".
/// Plans keep the nearest $5 (note 1353:11493), so $220 stays $220: what
/// she's shown is what Set it keeps in Your plan.
struct PlanProposal: Decodable, Hashable {
    let nothing: Bool
    let category: String?
    let usual: Double?
    let amount: Double?
    let months: Int?
    let line: String?
    /// Her plan's amount for this category before Set it, if it had one
    /// (finance/chat.py `current`): Undo puts it back (G7-Confirm).
    let current: Double?

    enum CodingKeys: String, CodingKey { case nothing, category, usual, amount, months, line, current }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        nothing = (try? c.decode(Bool.self, forKey: .nothing)) ?? true
        category = try? c.decodeIfPresent(String.self, forKey: .category)
        usual = try? c.decodeIfPresent(Double.self, forKey: .usual)
        amount = try? c.decodeIfPresent(Double.self, forKey: .amount)
        months = try? c.decodeIfPresent(Int.self, forKey: .months)
        line = try? c.decodeIfPresent(String.self, forKey: .line)
        current = try? c.decodeIfPresent(Double.self, forKey: .current)
    }

    init(category: String, usual: Double, amount: Double, months: Int, current: Double? = nil) {
        nothing = false
        self.category = category
        self.usual = usual
        self.amount = amount
        self.months = months
        line = nil
        self.current = current
    }
}

/// What a write endpoint says when the chat needs nothing back.
struct ChatOK: Decodable {}

// MARK: - Ask Pearl's answers (PC-22, PC-26; finance/ask.py)

/// PC-26b and PC-22: a month. This month compares with where she usually is
/// by today; a past month says what was left at the end.
struct MonthFact: Decodable, Hashable {
    struct Top: Decodable, Hashable {
        let category: String
        let amount: Double
        let share: Double
    }
    struct Change: Decodable, Hashable {
        let category: String
        let over: Double
        let count: Int
    }
    let month: String
    let name: String
    let current: Bool
    let moneyIn: Double
    let spent: Double
    let top: [Top]
    let allowanceLeft: Double?
    let overBy: Double?
    let usualByNow: Double?
    let day: Int?
    let changes: [Change]

    enum CodingKeys: String, CodingKey {
        case month, name, current, spent, top, day, changes
        case moneyIn = "money_in", allowanceLeft = "allowance_left", overBy = "over_by"
        case usualByNow = "usual_by_now"
    }
}

/// PC-26a: a shop this year, with a bar per month.
struct MerchantFact: Decodable, Hashable {
    struct Month: Decodable, Hashable {
        let month: String
        let label: String
        let amount: Double
        let now: Bool
    }
    let merchant: String
    let year: Int
    let total: Double
    let visits: Int
    let average: Double?
    let months: [Month]
    let query: String
}

/// PC-26c: up to 10 rows, and how many in all.
struct SearchFact: Decodable, Hashable {
    let query: String
    let count: Int
    let total: Double
    let rows: [BriefTransaction]
    let since: String?

    enum CodingKeys: String, CodingKey { case query, count, total, rows, since }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: CodingKeys.self)
        query = (try? c.decode(String.self, forKey: .query)) ?? ""
        count = (try? c.decode(Int.self, forKey: .count)) ?? 0
        total = (try? c.decode(Double.self, forKey: .total)) ?? 0
        rows = (try? c.decodeIfPresent([Lenient<BriefTransaction>].self, forKey: .rows))?.compactMap { $0.value } ?? []
        since = try? c.decodeIfPresent(String.self, forKey: .since)
    }
}

/// PC-26d: each credit card by its nickname. `state` is "ok", "near" (80%
/// of the limit or more: amber) or "over" (past it: red).
struct CardsFact: Decodable, Hashable {
    struct Card: Decodable, Hashable {
        let name: String
        let spent: Double
        let balance: Double?
        let limit: Double?
        let used: Double?
        let state: String
        let due: String?
    }
    let cards: [Card]
}

/// PC-22: Pearl's suggestion, its own dashed card. Its one action only
/// opens a screen ("See Dining out"); nothing in it can change anything.
struct AskSuggestion: Hashable {
    let text: String
    let label: String
    /// "category" (with `category` and `month`) or "cashflow" (with `query`).
    let open: String
    let category: String?
    let month: String?
    let query: String?
}

/// One line of POST /api/ask's stream (finance/ask.py).
enum AskEvent {
    case step(String)
    case fact(kind: String, data: Data)
    case text(String)
    case reset
    case words(String)
    case suggestion(AskSuggestion)
    case simple(until: String)
    case couldnt
    case done

    /// A line of the stream, or nil for one it doesn't know.
    static func parse(_ line: String) -> AskEvent? {
        guard let raw = line.data(using: .utf8),
              let obj = try? JSONSerialization.jsonObject(with: raw) as? [String: Any],
              let type = obj["type"] as? String else { return nil }
        switch type {
        case "step": return .step(obj["text"] as? String ?? "")
        case "fact":
            guard let kind = obj["kind"] as? String, let data = obj["data"],
                  let bytes = try? JSONSerialization.data(withJSONObject: data) else { return nil }
            return .fact(kind: kind, data: bytes)
        case "text": return .text(obj["text"] as? String ?? "")
        case "reset": return .reset
        case "words": return .words(obj["text"] as? String ?? "")
        case "suggestion":
            guard let text = obj["text"] as? String, let action = obj["action"] as? [String: Any],
                  let label = action["label"] as? String, let open = action["open"] as? String else { return nil }
            return .suggestion(AskSuggestion(text: text, label: label, open: open,
                                             category: action["category"] as? String,
                                             month: action["month"] as? String,
                                             query: action["query"] as? String))
        case "simple": return .simple(until: obj["until"] as? String ?? "")
        case "couldnt": return .couldnt
        case "done": return .done
        default: return nil
        }
    }
}

/// POST /api/ask, line by line. Only reads: the server's tools are read-only.
protocol ChatAsking {
    func ask(_ text: String, plans: Bool) -> AsyncThrowingStream<AskEvent, Error>
}

/// The phone has no connection: Send waits until it's back (PC-23).
struct ChatOffline: Error {}

/// The server says Ask Pearl is off for her (turned off on another phone).
struct ChatAskOff: Error {}

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
    /// What the server said to each read, for the chat's lifetime
    /// (2026-11-15): the same question asked again isn't another trip. Gone
    /// after any card changes something (`forget`).
    private let memo = Memo()

    init(_ io: ChatReading) { self.io = io }

    final class Memo: @unchecked Sendable {
        private let lock = NSLock()
        private var values: [String: Any] = [:]

        func get<T>(_ key: String) -> T? {
            lock.lock(); defer { lock.unlock() }
            return values[key] as? T
        }

        func set(_ key: String, _ value: Any) {
            lock.lock(); defer { lock.unlock() }
            values[key] = value
        }

        func clear() {
            lock.lock(); defer { lock.unlock() }
            values = [:]
        }
    }

    /// A card changed something: what the server said before may be out of date.
    func forget() { memo.clear() }

    private func cached<T: Decodable>(_ path: String, _ body: [String: Any]?) async throws -> T {
        let words = body.flatMap { try? JSONSerialization.data(withJSONObject: $0, options: [.sortedKeys]) }
            .map { String(decoding: $0, as: UTF8.self) } ?? ""
        let key = "\(T.self) \(path) \(words)"
        if let hit: T = memo.get(key) { return hit }
        let fresh: T
        if let body = body { fresh = try await io.read(path, body) } else { fresh = try await io.get(path) }
        memo.set(key, fresh)
        return fresh
    }

    func start() async throws -> ChatStart { try await io.get("api/chat") }

    func tell(_ text: String, category: String? = nil, days: [String]? = nil, people: [String]? = nil,
              ids: [String]? = nil) async throws -> TellReply {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        if let days = days, !days.isEmpty { body["days"] = days }
        if let people = people, !people.isEmpty { body["people"] = people }
        if let ids = ids, !ids.isEmpty { body["ids"] = ids }
        return try await cached("api/chat/tell", body)
    }

    func spending(_ text: String, category: String? = nil, month: String? = nil,
                  merchant: String? = nil) async throws -> SpendingAnswer {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        if let month = month { body["month"] = month }
        if let merchant = merchant { body["merchant"] = merchant }
        return try await cached("api/chat/spending", body)
    }

    func subscriptions() async throws -> SubscriptionsAnswer { try await cached("api/chat/subscriptions", nil) }

    func asks() async throws -> ChatAsks { try await cached("api/chat/asks", nil) }

    func plan(_ text: String, category: String? = nil) async throws -> PlanProposal {
        var body: [String: Any] = ["text": text]
        if let category = category { body["category"] = category }
        return try await cached("api/chat/plan", body)
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
    /// Ask Pearl's answers (PC-26).
    var month: MonthFact?
    var merchant: MerchantFact?
    var search: SearchFact?
    var cards: CardsFact?

    var isEmpty: Bool {
        tell == nil && spending == nil && subscriptions == nil && trips == nil && patterns == nil && plan == nil
            && !hasFacts
    }

    /// One of Ask Pearl's own answers: a fact card (PC-22, PC-26).
    var hasFacts: Bool { month != nil || merchant != nil || search != nil || cards != nil }

    /// What ChatEngine.show makes cards or a plan of (PC-05 to PC-10, PC-12).
    var showsCards: Bool {
        if tell != nil { return true }
        if !(patterns ?? []).isEmpty || !(trips ?? []).isEmpty { return true }
        if let p = plan, !p.nothing { return true }
        return false
    }

    /// What ChatEngine.show answers in words (PC-04), the model's or the server's.
    var answers: Bool { !showsCards && (spending != nil || subscriptions != nil || trips != nil || hasFacts) }
}

/// The model's tools, and everything they can touch: a reader, and the
/// findings they collect for the chat to show. No writer, no engine.
actor ChatTools {
    private let reader: ChatReader
    /// PC-12 is on with Your plan (Features.chatPlans).
    nonisolated let allowsPlans: Bool
    private(set) var found = ChatFindings()
    /// The trip and pattern cards, read once when the chat opened (2026-11-15):
    /// asking again is another trip to the server for the same answer.
    private var asks: ChatAsks?
    /// What the tools have found so far, as each one returns, so the chat
    /// can show cards before the model has finished its sentence.
    private let onFound: (@Sendable (ChatFindings) -> Void)?
    /// PC-23: the thinking step, naming the tool that's running.
    private let onStep: (@Sendable (String) -> Void)?

    init(reader: ChatReader, allowsPlans: Bool, asks: ChatAsks? = nil,
         onFound: (@Sendable (ChatFindings) -> Void)? = nil,
         onStep: (@Sendable (String) -> Void)? = nil) {
        self.reader = reader
        self.allowsPlans = allowsPlans
        self.asks = asks
        self.onFound = onFound
        self.onStep = onStep
    }

    /// The server is running a tool: "Looking at November…".
    func step(_ label: String) {
        guard !label.isEmpty else { return }
        onStep?(label)
    }

    /// What one of the server's read-only tools found (POST /api/ask): a
    /// fact card, whole. A kind it doesn't know is left out.
    func record(kind: String, data: Data) {
        let d = JSONDecoder()
        switch kind {
        case "month": found.month = try? d.decode(MonthFact.self, from: data)
        case "merchant": found.merchant = try? d.decode(MerchantFact.self, from: data)
        case "search": found.search = try? d.decode(SearchFact.self, from: data)
        case "cards": found.cards = try? d.decode(CardsFact.self, from: data)
        case "spending": found.spending = try? d.decode(SpendingAnswer.self, from: data)
        case "subscriptions": found.subscriptions = try? d.decode(SubscriptionsAnswer.self, from: data)
        case "tell": found.tell = try? d.decode(TellReply.self, from: data)
        case "plan": found.plan = allowsPlans ? try? d.decode(PlanProposal.self, from: data) : nil
        case "asks":
            if let a = try? d.decode(ChatAsks.self, from: data) {
                found.trips = a.trips
                found.patterns = a.patterns
            }
        default: return
        }
        onFound?(found)
    }

    func tell(_ text: String, category: String? = nil, days: [String]? = nil, people: [String]? = nil,
              ids: [String]? = nil) async throws -> TellReply {
        let reply = try await ChatLog.time("tool tell") {
            try await reader.tell(text, category: category, days: days, people: people, ids: ids)
        }
        found.tell = reply
        onFound?(found)
        return reply
    }

    func spending(_ text: String, category: String? = nil, month: String? = nil,
                  merchant: String? = nil) async throws -> SpendingAnswer {
        let answer = try await ChatLog.time("tool spending") {
            try await reader.spending(text, category: category, month: month, merchant: merchant)
        }
        found.spending = answer
        onFound?(found)
        return answer
    }

    func subscriptions() async throws -> SubscriptionsAnswer {
        let answer = try await ChatLog.time("tool subscriptions") { try await reader.subscriptions() }
        found.subscriptions = answer
        onFound?(found)
        return answer
    }

    func trips() async throws -> [TripAsk] {
        let asks = try await cachedAsks()
        found.trips = asks.trips
        onFound?(found)
        return asks.trips
    }

    func patterns() async throws -> [PatternAsk] {
        let asks = try await cachedAsks()
        found.patterns = asks.patterns
        onFound?(found)
        return asks.patterns
    }

    func plan(_ text: String, category: String? = nil) async throws -> PlanProposal? {
        guard allowsPlans else { return nil }
        let p = try await ChatLog.time("tool plan") { try await reader.plan(text, category: category) }
        found.plan = p
        onFound?(found)
        return p
    }

    private func cachedAsks() async throws -> ChatAsks {
        if let asks = asks { return asks }
        let fresh = try await ChatLog.time("tool asks") { try await reader.asks() }
        asks = fresh
        return fresh
    }
}

/// How long the chat takes, for Console on a Mac with her iPhone plugged in
/// (subsystem "Pearl", category "chat") and Instruments' os_signpost lane
/// (2026-11-15). Durations only: never her words or her numbers.
enum ChatLog {
    static let logger = Logger(subsystem: "Pearl", category: "chat")
    static let signposter = OSSignposter(subsystem: "Pearl", category: "chat")

    static func time<T>(_ what: StaticString, _ body: () async throws -> T) async throws -> T {
        let id = signposter.makeSignpostID()
        let state = signposter.beginInterval(what, id: id)
        let start = DispatchTime.now().uptimeNanoseconds
        defer {
            signposter.endInterval(what, state)
            note(what, since: start)
        }
        return try await body()
    }

    /// "<what> 412 ms", from `start` (DispatchTime's uptime nanoseconds).
    static func note(_ what: StaticString, since start: UInt64) {
        let ms = Double(DispatchTime.now().uptimeNanoseconds - start) / 1_000_000
        logger.notice("\(what, privacy: .public) \(Int(ms), privacy: .public) ms")
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
    /// PC-22: Pearl's suggestion, its own dashed card.
    var suggestion: AskSuggestion? = nil
    /// PC-23: past the monthly or daily cap, the day answers are full again
    /// ("December 1", "tomorrow"): one quiet line per chat.
    var simple: String? = nil
    /// PC-23: Pearl couldn't answer (the model failed, refused or was unsure).
    var couldnt = false
    /// Words from Ask Pearl, shown as PC-22 draws an answer.
    var cloud = false
    /// The words are still coming.
    var streaming = false
}

/// Reads what she said and uses the tools. It can only read and propose:
/// `tools` is all it gets.
protocol PearlBrain {
    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply
    /// The same, saying its answer so far as it comes (2026-11-15), so the
    /// first words show at once.
    func respond(to text: String, mode: ChatMode?, tools: ChatTools,
                 partial: @escaping @Sendable (String) -> Void) async throws -> BrainReply
    /// Get ready before her first words.
    func prewarm()
    /// A language model, worth asking when the server couldn't read her
    /// words. The scripted brain only asks the server what it already asked.
    var isModel: Bool { get }
    /// Asked first, before the server's own reading of her words: Ask Pearl
    /// on the server (THL-308) answers every question itself.
    var asksFirst: Bool { get }
}

extension PearlBrain {
    func respond(to text: String, mode: ChatMode?, tools: ChatTools,
                 partial: @escaping @Sendable (String) -> Void) async throws -> BrainReply {
        try await respond(to: text, mode: mode, tools: tools)
    }

    func prewarm() {}

    var isModel: Bool { false }

    var asksFirst: Bool { false }
}

/// Ask Pearl (THL-308, AI Phase 2): Claude, through Pearl's server. The
/// server runs the read-only tools and Python works out every number; this
/// reads the stream: the step, the fact cards whole, the words as they come.
/// It holds only an asker (POST /api/ask) and the tools: nothing that writes.
struct CloudBrain: PearlBrain {
    let asker: ChatAsking
    var plans = false

    var isModel: Bool { true }
    var asksFirst: Bool { true }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        try await respond(to: text, mode: mode, tools: tools, partial: { _ in })
    }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools,
                 partial: @escaping @Sendable (String) -> Void) async throws -> BrainReply {
        var reply = BrainReply(cloud: true)
        var words = ""
        for try await event in asker.ask(text, plans: plans) {
            switch event {
            case .step(let label): await tools.step(label)
            case .fact(let kind, let data): await tools.record(kind: kind, data: data)
            case .text(let more):
                words += more
                partial(words)
            case .reset:
                words = ""
                partial(words)
            case .words(let whole):
                words = whole
                partial(words)
            case .suggestion(let s): reply.suggestion = s
            case .simple(let until): reply.simple = until
            case .couldnt: reply.couldnt = true
            case .done: break
            }
        }
        reply.text = words.isEmpty ? nil : words
        return reply
    }
}

/// The deterministic model: routes her words to one tool and leaves the
/// reading of them to the server (finance/chat.py). For check_chat.py, for
/// Tell Pearl what you did, and the fallback when Ask Pearl's server can't
/// answer at all.
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
    /// Undo on the chat's toast only (G7-Confirm).
    func delete<T: Decodable>(_ path: String, query: [String: String]) async throws -> T
}

/// G7-Confirm (NEW, approved 2026-11-18): Undo on the ink toast after Set it
/// or a trip made in the chat. A tap on the toast's Undo, nothing else.
enum ChatUndo: Hashable {
    /// Your plan's row back as it was: its old amount, or no row.
    case plan(category: String, was: Double?)
    /// The trip she just made goes; its dates aren't marked as asked about
    /// (DELETE /api/trips/<id>?undo=1, as TR-02c's Undo).
    case trip(id: String, name: String)

    /// The toast's words: "Dining out plan set", "Trip to Montréal made".
    var toast: String {
        switch self {
        case .plan(let category, _): return "\(category) plan set"
        case .trip(_, let name): return "\(name) made"
        }
    }
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
    /// "Done. Trip to Montréal made.", its dates ("Mar 4–9"), its total and place.
    case trip(id: String, name: String, dates: String, total: String, place: String)
    /// "Done. Ana’s deposits rule made."
    case pattern(title: String)
    /// "Done. Dining out plan set to $220 a month."
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
            let made: Made = try await writer.post("api/trips/asks/\(t.id)/yes", [:])
            let name = made.trip?.name ?? t.name ?? "Trip"
            let dates = made.trip.map { Format.span($0.start, $0.end) } ?? Format.span(t.start, t.end)
            return .trip(id: made.trip?.id ?? t.id, name: name.isEmpty ? "Trip" : name, dates: dates,
                         total: (made.trip?.totals ?? t.totals).shown,
                         place: made.trip?.place ?? t.place ?? name)
        case .yes(.pattern(let p)):
            let _: ChatOK = try await writer.post("api/pattern-sort/asks/\(p.id)/yes", ["how": "pc09"])
            return .pattern(title: p.title)
        case .yes(.plan(let p)):
            // Your plan's row, marked as set in Pearl chat. With the plan in
            // use, this tap is the confirm and the Allowance follows at once.
            guard let category = p.category, let amount = p.amount else { return .nothing }
            let _: ChatOK = try await writer.put("api/your-plan/rows/\(category)", ["amount": amount, "source": "chat"])
            return .plan(category: category, amount: amount)
        case .skip(.sort), .skip(.plan):
            // PC-07: skipped ones stay in Needs a look; Not now changes nothing.
            return .skipped
        case .skip(.trip(let t)):
            let _: ChatOK = try await writer.post("api/trips/asks/\(t.id)/skip", [:])
            return .skipped
        case .skip(.pattern(let p)):
            let _: ChatOK = try await writer.post("api/pattern-sort/asks/\(p.id)/skip", [:])
            return .skipped
        }
    }

    /// Undo on the toast (G7-Confirm): puts back only what that tap did.
    func undo(_ u: ChatUndo, tap: UserTap) async throws {
        switch u {
        case .plan(let category, let was?):
            let _: ChatOK = try await writer.put("api/your-plan/rows/\(category)", ["amount": was])
        case .plan(let category, nil):
            let _: ChatOK = try await writer.delete("api/your-plan/rows/\(category)", query: [:])
        case .trip(let id, _):
            let _: ChatOK = try await writer.delete("api/trips/\(id)", query: ["undo": "1"])
        }
    }

    // Ids go in plain: APIClient encodes the path once (TEST-33).
}

// MARK: - The words (note 1340:8893; A+ G7 boards)

enum ChatWords {
    /// PC-21: the composer's prompt.
    static let placeholder = "Ask Pearl"
    /// PC-21: the start's hero.
    static let hero = "Ask about your money"
    static let tryAsking = "Try asking"
    /// PC-24 (approved 2026-11-27; counsel reviews the wording, THL-117).
    static let consentTitle = "Before you ask"
    static let consentLine = "Pearl uses Claude, by Anthropic, to understand your questions. It never sends your account numbers or bank logins."
    static let turnOn = "Turn on Ask Pearl"
    static let notNow = "Not now"
    /// PC-25.
    static let offTitle = "Ask Pearl is off"
    static let offLine = "Turn it on to ask about your money. Pearl uses Claude, never your account numbers or bank logins."
    static let searchInstead = "Search instead"
    /// PC-23: couldn't answer, then four things it can always do.
    static let couldnt = "I can\u{2019}t answer that one yet. Here\u{2019}s what I can do:"
    /// PC-23: offline. The chat stays; Send waits.
    static let offline = "You\u{2019}re offline. Ask again when you\u{2019}re back."
    /// PC-23 (Option A): one quiet line per chat past the cap. Never
    /// dollars, tokens or the word "limit".
    static func simple(_ until: String) -> String { "Pearl\u{2019}s keeping answers simple until \(until)." }
    /// PC-22's overline: "November so far".
    static func soFar(_ name: String) -> String { "\(name) so far" }
    /// PC-26a's overline: "Loblaws · 2026".
    static func shopYear(_ shop: String, _ year: Int) -> String { "\(shop) \u{00B7} \(year)" }
    /// "See all 38 in Cash flow".
    static func seeAll(_ n: Int) -> String { "See all \(n) in Cash flow" }
    static let nothingChanged = "Okay, nothing changed."
    /// G7-Chat: under the dots while Pearl works it out.
    static let working = "Pearl is working it out"
    /// G7-Unavailable: couldn't answer, with Try again.
    static let failed = "Pearl couldn\u{2019}t answer that. Try again."
    /// PC-10 (G7-TellMore): before the server's own line.
    static let couldntMatch = "Pearl couldn\u{2019}t match that."

    /// PC-12's "You: “…”" when there's no bubble for her words.
    static func quote(_ said: String) -> String { "\u{201C}\(said)\u{201D}" }
    static func youSaid(_ said: String) -> String { "You: \u{201C}\(said)\u{201D}" }

    /// The model's echo of her words, when it gave none (kept for the
    /// model's reply; A+ shows her words in her own bubble instead).
    static func echo(_ said: String) -> String { "You said \u{201C}\(said)\u{201D}." }

    /// PC-05's line over the first card: "A guess for 7 of the 9 from the
    /// weekend." The server's words, ending with a full stop.
    static func lead(_ line: String) -> String {
        let t = line.trimmingCharacters(in: .whitespacesAndNewlines)
        guard let last = t.last, !".?!".contains(last) else { return t }
        return t + "."
    }

    /// PC-06's pill: "Maybe split with Jo and Sam?".
    static func maybeSplit(_ names: [String]) -> String { "Maybe split with \(Format.andList(names))?" }

    /// PC-05's overline: "Pearl’s guess · 1 of 7", "Your choice · 2 of 7".
    /// After the first card the count moves to the progress line over the
    /// cards (G7-Tell-r), so the overline is just "Pearl’s guess".
    static func guessOver(choice: Bool, _ counter: String?) -> String {
        let head = choice ? "Your choice" : "Pearl\u{2019}s guess"
        guard let counter = counter else { return head }
        return head + " \u{00B7} " + counter
    }

    /// G7-Tell-r: her words cut to their first part, for the small line that
    /// replaces her bubble after the first card: "Out with friends Saturday,
    /// brunch with Jo and Sam, Uber home" → "Out with friends Saturday".
    static func shortSaid(_ said: String) -> String {
        let t = said.trimmingCharacters(in: .whitespacesAndNewlines)
        let first = t.split(whereSeparator: { ",;.!?\n".contains($0) }).first
            .map { $0.trimmingCharacters(in: .whitespaces) } ?? ""
        return first.isEmpty ? t : first
    }

    /// PC-07 (G7-TellMore): "Sorted 7. 2 left for later."
    static func sortedTitle(sorted: Int, left: Int) -> String {
        [sorted > 0 ? "Sorted \(sorted)." : nil, left > 0 ? "\(left) left for later." : nil]
            .compactMap { $0 }.joined(separator: " ")
    }

    /// PC-07's row: "2 back in Needs a look"; nothing when none are left.
    static func sortedBody(left: Int) -> String? {
        left > 0 ? "\(left) back in Needs a look" : nil
    }

    static func seeThe(_ left: Int) -> String { "See the \(left)" }

    /// PC-08's overline (G7-TellMore): "A trip? · one card for all 23".
    static func tripOver(_ t: TripAsk) -> String { "A trip? \u{00B7} one card for all \(t.count)" }

    /// The trip question (approved 2026-11-18): "Were you in Montréal?",
    /// never "A trip?". Without a place: "Was this a trip?".
    static func tripQuestion(_ t: TripAsk) -> String {
        guard let place = t.place?.trimmingCharacters(in: .whitespaces), !place.isEmpty else {
            return "Was this a trip?"
        }
        return "Were you in \(place)?"
    }

    /// Under the question: "A flight, a hotel, 5 days away." The place is
    /// in the question, so not again here.
    static func tripAway(_ t: TripAsk) -> String {
        let lead = [t.flight == true ? "a flight" : nil, t.hotel == true ? "a hotel" : nil].compactMap { $0 }
        let stay = "\(t.days) day\(t.days == 1 ? "" : "s") away"
        let text = lead.isEmpty ? stay : lead.joined(separator: ", ") + ", " + stay
        return text.prefix(1).uppercased() + text.dropFirst() + "."
    }

    /// PC-09's overline: "A pattern · once for all of them".
    static let patternOver = "A pattern \u{00B7} once for all of them"

    /// PC-09 under the question: "Your last 5 at Farm Boy were Groceries.",
    /// "Your last 8 were Ana’s share."
    static func patternSub(_ p: PatternAsk) -> String {
        p.isJoint ? "Your last \(p.count) were \(p.label)." : "Your last \(p.count) at \(p.name) were \(p.label)."
    }

    /// PC-12.
    static func planLead(months: Int) -> String {
        "Here\u{2019}s a plan from your last \(months == 1 ? "month" : "\(months) months"). Nothing changes until you set it."
    }

    static func planQuestion(_ category: String, _ amount: Double) -> String {
        "Make a \(category) plan of \(Format.whole(amount)) a month?"
    }

    /// PC-12: "Usual $214" (TEXT-01).
    static func planSub(usual: Double) -> String {
        "Usual \(Format.whole(usual))"
    }

    /// PC-13 and every other confirmation: "Done. {What} {set|made|renamed} …".
    static func planDone(_ category: String, _ amount: Double) -> String {
        "Done. \(category) plan set to \(Format.whole(amount)) a month."
    }

    /// PC-13's card: "Dining out plan · $220 a month" over "Set Nov 18".
    static func planTitle(_ category: String, _ amount: Double) -> String {
        "\(category) plan \u{00B7} \(Format.whole(amount)) a month"
    }

    static func planSet(_ day: String) -> String { "Set \(Format.short(day))" }

    static func tripDone(_ name: String) -> String { "Done. \(name) made." }
    static func patternDone(_ title: String) -> String { "Done. \(title) rule made." }

    /// G7-Confirm under a trip made: where it lives.
    static let tripLives = "Change or remove it in Cash flow, or ask Pearl."

    /// "Was this a trip?" with none to ask about (engBOT's words; no frame).
    static let noTrip = "Pearl didn\u{2019}t spot a trip."
}

// MARK: - The chat

/// Where a confirmation now lives (PC-13's link).
enum DoneLink: Hashable {
    case trip(String)
    case rules
    case plan
}

/// PC-13 (G7-Confirm): "Done. …", a card saying what was made, and the way
/// there. A trip's card is its row (face, name, dates, total); a plan's or a
/// rule's has its symbol and a link under it.
struct DoneNote: Hashable, Identifiable {
    enum Kind: Hashable { case plan, trip, rule }

    let line: String
    let kind: Kind
    let title: String
    /// "Set Nov 18", "Mar 4–9".
    let sub: String?
    /// A trip's total ("$1,284.60").
    var amount: String? = nil
    /// A trip's place, for its face ("MO").
    var face: String? = nil
    let link: DoneLink?
    /// Under a plan's or rule's card: "See it in Your plan".
    let linkLabel: String?
    /// Under a trip's card: "Change or remove it in Cash flow, or ask Pearl."
    var note: String? = nil
    /// What the toast's Undo takes back.
    var undo: ChatUndo? = nil
    var id: String { line }
}

/// A run of cards, one at a time (PC-05, PC-06, PC-08, PC-09). Never grouped,
/// no Yes to all.
struct Deck {
    let cards: [ProposedAction]
    var index = 0
    /// PC-05's "A guess for 7 of the 9 from the weekend", for told guesses.
    let lead: String?
    /// The model's echo of her words (A+ shows her own bubble instead).
    let echo: String?
    /// What she told Pearl: her bubble over the cards.
    var said: String? = nil
    var sorted = 0
    var left = 0
    var done: [DoneNote] = []

    var current: ProposedAction? { index < cards.count ? cards[index] : nil }
    var told: Bool { cards.contains { if case .sort = $0 { return true } else { return false } } }
    private var sorts: Int { cards.filter { if case .sort = $0 { return true } else { return false } }.count }

    /// PC-05's count in the overline: "1 of 7", "2 of 7".
    var counter: String { "\(index + 1) of \(sorts)" }

    /// The card's overline: "Pearl’s guess · 1 of 7", "A trip? · one card for
    /// all 23", "A pattern · once for all of them". A guess she changed
    /// says "Your choice" (the view knows).
    func overline(choice: Bool = false) -> String {
        switch current {
        case .sort?: return ChatWords.guessOver(choice: choice, showsProgress ? nil : counter)
        case .trip(let t)?: return ChatWords.tripOver(t)
        case .pattern?: return ChatWords.patternOver
        case .plan?, nil: return ""
        }
    }

    /// G7-Tell-r (PC-05, PC-06): after the first told guess, a small "Out
    /// with friends Saturday · 2 of 7" and a dash per card replace her whole
    /// sentence; the count leaves the card's overline.
    var showsProgress: Bool {
        guard index > 0, case .sort? = current else { return false }
        return true
    }

    /// The progress line's words: her sentence, cut short ("" without one).
    var progressTitle: String { said.map(ChatWords.shortSaid) ?? "" }

    /// The told guesses in this run, for "2 of 7" and its dashes.
    var progressTotal: Int { sorts }

    /// Pearl's line over the first told guess only.
    var leadLine: String? {
        guard index == 0, case .sort? = current, let lead = lead, !lead.isEmpty else { return nil }
        return ChatWords.lead(lead)
    }
}

/// PC-22, PC-26: one of Ask Pearl's answers. A class, so the screen stays
/// small on the stack (check_stack.py).
final class ChatAnswer {
    let said: String?
    let text: String
    let found: ChatFindings
    let suggestion: AskSuggestion?
    /// PC-23's quiet line, on the first answer past the cap only.
    let simple: String?
    let streaming: Bool

    init(said: String?, text: String, found: ChatFindings, suggestion: AskSuggestion? = nil,
         simple: String? = nil, streaming: Bool = false) {
        self.said = said
        self.text = text
        self.found = found
        self.suggestion = suggestion
        self.simple = simple
        self.streaming = streaming
    }
}

/// What the chat shows: one exchange at a time, as the frames draw it.
indirect enum ChatScreen {
    /// PC-03.
    case start
    /// Her words, while Pearl works it out (G7-Chat: the dots), and the
    /// step naming the tool that's running (PC-23: "Looking at November…").
    case thinking(said: String, step: String?)
    /// PC-22, PC-26: Ask Pearl's answer: the words, the fact cards, a suggestion.
    case answer(ChatAnswer)
    /// PC-23: couldn't answer, and four things it can always do.
    case couldnt(said: String)
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
    case noChange(said: String?, plan: PlanProposal? = nil)
    /// G7-Unavailable: Pearl couldn't answer · Try again.
    case failed(said: String)
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
    /// The last thing asked, for G7-Unavailable's Try again.
    private var last: (said: String?, text: String, mode: ChatMode?)?
    /// The trip and pattern cards, from opening (2026-11-15), for the tools;
    /// read again after a card changes something.
    private var asks: ChatAsks?
    /// This turn, so a late word from an earlier one can't land on this one.
    private var turn = 0
    /// The turn still being worked out: its first findings and words show
    /// as they come; once it's done, nothing late changes the screen.
    private var working: Int?
    /// What this turn's tools have found so far.
    private var latest = ChatFindings()
    /// This turn's cards are already on screen (shown when the tool found them).
    private var shownEarly = false
    /// "Set Nov 18": today, for PC-13's card.
    var today: () -> String = { Format.isoDay(Date()) }
    /// Ask Pearl (THL-308): "on", "off" or "unasked", from GET /api/chat;
    /// nil until it has answered. Set to "on" by the tab's Turn on.
    @Published var askState: String?
    /// PC-21's four questions.
    @Published private(set) var examples: [String] = []
    /// PC-23: the quiet line is said once per chat.
    private var simpleShown = false
    /// PC-23 (offline): what she asked when the connection dropped, for the
    /// composer to hold until it's back.
    @Published var waiting: String?
    /// Whether the phone has a connection (NWPathMonitor, in the view).
    var isOnline: @MainActor () -> Bool = { true }

    init(brain: PearlBrain, reader: ChatReader, executor: ChatExecutor, allowsPlans: Bool,
         describe: @escaping (Error) -> String = { $0.localizedDescription }) {
        self.brain = brain
        self.reader = reader
        self.executor = executor
        self.allowsPlans = allowsPlans
        self.describe = describe
    }

    /// Her words in this exchange, for her bubble (G7: right, in blush).
    var heard: String? { said }

    /// Opened: what Pearl has to suggest comes first (PB-01's shimmer), the
    /// same cards Quick sort has; else the starters.
    ///
    /// 2026-11-15: the model loads while the server answers, and the cards
    /// come in GET /api/chat's own reply: one trip to the server, not two.
    func open() async {
        brain.prewarm()
        let began = DispatchTime.now().uptimeNanoseconds
        guard let start = try? await reader.start() else { return }
        ChatLog.note("open", since: began)
        // A server before THL-308 says nothing: Ask Pearl isn't there yet.
        askState = start.ask ?? "unasked"
        examples = start.examples ?? []
        if start.suggest, start.asks == nil, let more = try? await reader.asks() {
            asks = more
        } else {
            asks = start.asks
        }
        guard start.suggest, let asks = asks else { return }
        let cards = asks.patterns.map(ProposedAction.pattern) + asks.trips.map(ProposedAction.trip)
        if !cards.isEmpty { screen = .cards(Deck(cards: cards, lead: nil, echo: nil)) }
    }

    /// Ask Pearl's state again (turned on or off in Profile › Privacy).
    func refreshAsk() async {
        guard let start = try? await reader.start() else { return }
        askState = start.ask ?? "unasked"
        examples = start.examples ?? []
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
        // PC-23: offline, the chat stays and Send waits.
        guard isOnline() else {
            waiting = text
            return
        }
        let m = mode
        mode = nil
        await run(said: text, text: text, mode: m)
    }

    /// G7-Unavailable's Try again: the same words, asked again.
    func retry() async {
        guard let last = last, !busy else { return }
        await run(said: last.said, text: last.text, mode: last.mode)
    }

    /// Back to the starters (PC-10's Tell it differently).
    func restart() {
        screen = .start
        said = nil
        error = nil
    }

    /// A+ Pearl tab (REDESIGN-03): New chat, after she said yes on the
    /// "Start a new chat?" sheet. What she told Pearl is forgotten (a turn
    /// still being worked out can't land); nothing it sorted changes. Then
    /// it opens again as fresh: a waiting suggestion first, else the starters.
    func newChat() async {
        turn += 1
        working = nil
        mode = nil
        asks = nil
        last = nil
        simpleShown = false
        waiting = nil
        restart()
        await open()
    }

    private func run(said: String?, text: String, mode: ChatMode?) async {
        let before = screen
        self.said = said
        last = (said, text, mode)
        error = nil
        screen = .thinking(said: said ?? text, step: nil)
        turn += 1
        let now = turn
        working = now
        latest = ChatFindings()
        shownEarly = false
        defer { if working == now { working = nil } }
        let began = DispatchTime.now().uptimeNanoseconds
        var reply = BrainReply()
        // Ask Pearl (THL-308): a question goes to the server's Claude first;
        // Tell Pearl what you did and the starters read as before.
        if brain.asksFirst && (mode == nil || mode == .ask) {
            await ask(said: said, text: text, mode: mode, before: before, turn: now, began: began)
            return
        }
        // 2026-11-15: the server first. It reads her words itself and works
        // out the answer (totals, the cards); when it could, that's the
        // answer and the model isn't asked at all. The model is for words the
        // server couldn't read, and for when it can't, what the server said stands.
        let first = ChatTools(reader: reader, allowsPlans: allowsPlans, asks: asks)
        let answered = await serverAnswered(text, mode, first)
        if answered || !brain.isModel {
            let f = await first.found
            if !f.isEmpty {
                ChatLog.note("turn (server)", since: began)
                guard turn == now else { return }
                working = nil
                show(f, reply, said: said)
                return
            }
        }
        // The model's turn: what its tools find, and its words, show as they
        // come, not once the whole answer is in.
        let tools = ChatTools(reader: reader, allowsPlans: allowsPlans, asks: asks) { [weak self] f in
            Task { @MainActor in self?.found(f, turn: now) }
        }
        do {
            reply = try await brain.respond(to: text, mode: mode, tools: tools) { [weak self] words in
                Task { @MainActor in self?.saying(words, turn: now) }
            }
            ChatLog.note("turn (model)", since: began)
        } catch {
            ChatLog.note("turn failed", since: began)
            // The model couldn't (a guardrail, a refusal, a full
            // context). What a tool already found stands; else the server's
            // own reading, from above; else it reads her words again.
            if (await tools.found).isEmpty {
                let f = await first.found
                if !f.isEmpty {
                    guard turn == now else { return }
                    working = nil
                    show(f, BrainReply(), said: said)
                    return
                }
                do {
                    reply = try await ScriptedBrain().respond(to: text, mode: mode, tools: tools)
                } catch {
                    // A New chat since: this turn's words are forgotten.
                    guard turn == now else { return }
                    // G7-Unavailable: "Pearl couldn't answer that. Try again."
                    screen = .failed(said: said ?? text)
                    return
                }
            } else {
                reply = BrainReply()
            }
        }
        guard turn == now else { return }
        working = nil
        var f = await tools.found
        // The model used no tool: the server's own reading is the answer.
        if f.isEmpty { f = await first.found }
        if shownEarly {
            // The cards went up when the tool found them. Until she has
            // answered one, the whole answer replaces them: the model's echo
            // of her words, and what the later tools found, as before.
            if isUntouched { show(f, reply, said: said) }
            return
        }
        show(f, reply, said: said)
    }

    /// Ask Pearl's turn (PC-21 to PC-26): the step while the server works,
    /// the fact cards whole as each tool returns, the words as they come.
    /// Offline, the chat stays as it was and the words wait (PC-23); with no
    /// answer from the server at all, its own reading of her words.
    private func ask(said: String?, text: String, mode: ChatMode?, before: ChatScreen,
                     turn now: Int, began: UInt64) async {
        let tools = ChatTools(reader: reader, allowsPlans: allowsPlans, asks: asks, onFound: { [weak self] f in
            Task { @MainActor in self?.found(f, turn: now) }
        }, onStep: { [weak self] label in
            Task { @MainActor in self?.stepping(label, turn: now) }
        })
        var reply: BrainReply
        do {
            reply = try await brain.respond(to: text, mode: mode, tools: tools) { [weak self] words in
                Task { @MainActor in self?.saying(words, turn: now) }
            }
            ChatLog.note("turn (ask)", since: began)
        } catch is ChatOffline {
            guard turn == now else { return }
            working = nil
            screen = before
            waiting = said ?? text
            return
        } catch is ChatAskOff {
            guard turn == now else { return }
            working = nil
            screen = before
            askState = "off"
            return
        } catch {
            ChatLog.note("turn (ask) failed", since: began)
            // What a tool already found stands; else the server's own
            // reading of her words; else G7-Unavailable's Try again.
            let got = await tools.found
            guard got.isEmpty else {
                guard turn == now else { return }
                working = nil
                show(got, BrainReply(cloud: true), said: said)
                return
            }
            let first = ChatTools(reader: reader, allowsPlans: allowsPlans, asks: asks)
            let answered = await serverAnswered(text, mode, first)
            guard turn == now else { return }
            working = nil
            let f = await first.found
            if answered, !f.isEmpty { show(f, BrainReply(), said: said) } else { screen = .failed(said: said ?? text) }
            return
        }
        guard turn == now else { return }
        working = nil
        if let until = reply.simple {
            reply.simple = simpleShown ? nil : until
            simpleShown = true
        }
        let f = await tools.found
        if shownEarly && !isUntouched { return }
        show(f, reply, said: said)
    }

    /// PC-23: the step under the dots, naming the tool that's running.
    private func stepping(_ label: String, turn now: Int) {
        guard working == now, turn == now, case .thinking(let said, _) = screen else { return }
        screen = .thinking(said: said, step: label)
    }

    /// The server's own reading of her words (ScriptedBrain's route): true
    /// when that's an answer. Not when it couldn't tell which spending, or
    /// when what she said fits none of the open ones she has.
    private func serverAnswered(_ text: String, _ mode: ChatMode?, _ tools: ChatTools) async -> Bool {
        do {
            switch ScriptedBrain.route(text, mode, plans: allowsPlans) {
            case .subscriptions: _ = try await tools.subscriptions(); return true
            case .trips: _ = try await tools.trips(); return true
            case .plan: return (try await tools.plan(text))?.category != nil
            case .spending: return !(try await tools.spending(text)).nothing
            case .tell:
                let r = try await tools.tell(text)
                return r.matched > 0 || r.open == 0
            }
        } catch {
            return false
        }
    }

    /// Cards or a plan she hasn't answered yet: a later answer may replace them.
    private var isUntouched: Bool {
        guard !busy else { return false }
        switch screen {
        case .cards(let d): return d.index == 0 && d.done.isEmpty
        case .plan, .thinking, .answer: return true
        default: return false
        }
    }

    /// A tool returned. Cards show now: the model's sentence after them only
    /// says her words back.
    private func found(_ f: ChatFindings, turn now: Int) {
        guard working == now, turn == now else { return }
        latest = f
        if brain.asksFirst, !f.showsCards, f.hasFacts {
            // PC-23 (streaming): the figures land whole, the words follow.
            switch screen {
            case .thinking, .answer: show(f, BrainReply(cloud: true, streaming: true), said: said)
            default: break
            }
            return
        }
        guard case .thinking = screen, f.showsCards else { return }
        show(f, BrainReply(), said: said)
        shownEarly = true
    }

    /// The model's answer so far, on PC-04 as it comes.
    private func saying(_ words: String, turn now: Int) {
        guard working == now, turn == now, !shownEarly else { return }
        if brain.asksFirst {
            switch screen {
            case .thinking, .answer:
                guard !words.isEmpty || latest.hasFacts else { return }
                show(latest, BrainReply(text: words, cloud: true, streaming: true), said: said)
            default: break
            }
            return
        }
        guard latest.answers else { return }
        switch screen {
        case .thinking, .reply: show(latest, BrainReply(text: words), said: said)
        default: break
        }
    }

    /// The findings, as the screen the frames draw for them.
    func show(_ f: ChatFindings, _ reply: BrainReply, said: String?) {
        if reply.couldnt {
            screen = .couldnt(said: said ?? last?.text ?? "")
            return
        }
        if let tell = f.tell {
            if tell.proposals.isEmpty {
                screen = .nothing(line: tell.line)
            } else {
                screen = .cards(Deck(cards: tell.proposals.map(ProposedAction.sort), lead: tell.line,
                                     echo: reply.echo ?? ChatWords.echo(tell.said), said: tell.said))
            }
            return
        }
        let asked = (f.patterns ?? []).map(ProposedAction.pattern) + (f.trips ?? []).map(ProposedAction.trip)
        if !asked.isEmpty {
            screen = .cards(Deck(cards: asked, lead: nil, echo: nil, said: said ?? last?.text))
            return
        }
        if let p = f.plan, !p.nothing {
            screen = .plan(said: said ?? "", p)
            return
        }
        if reply.cloud {
            // PC-22, PC-26: Ask Pearl's words, its fact cards and a suggestion.
            let text = reply.text ?? (reply.streaming ? "" : (f.spending?.line ?? f.subscriptions?.line
                                                            ?? (f.trips != nil ? ChatWords.noTrip : "")))
            if text.isEmpty && f.isEmpty && !reply.streaming {
                screen = .couldnt(said: said ?? last?.text ?? "")
                return
            }
            screen = .answer(ChatAnswer(said: said, text: text, found: f, suggestion: reply.suggestion,
                                        simple: reply.simple, streaming: reply.streaming))
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

    /// Her tap on a card. The only way the chat changes anything. Says what
    /// happened, so her tap's view can raise the toast with Undo.
    @discardableResult
    func decide(_ decision: Decision, tap: UserTap) async -> Performed? {
        guard !busy else { return nil }
        busy = true
        defer { busy = false }
        do {
            let did = try await executor.perform(decision, tap: tap)
            // A trip made or a pattern answered: the cards waiting have changed,
            // and what the server said before may be out of date.
            forgetReads()
            error = nil
            advance(did, decision)
            return did
        } catch {
            self.error = describe(error)
            return nil
        }
    }

    /// The toast's Undo for a plan set or a trip made (G7-Confirm). Its note
    /// leaves the chat; with nothing else done there, "Okay, nothing changed."
    /// Throws so the toast can say it couldn't.
    func undo(_ u: ChatUndo, tap: UserTap) async throws {
        try await executor.undo(u, tap: tap)
        forgetReads()
        switch screen {
        case .done(let said, let notes):
            let rest = notes.filter { $0.undo != u }
            screen = rest.isEmpty ? .noChange(said: said) : .done(said: said, rest)
        case .cards(var deck):
            deck.done.removeAll { $0.undo == u }
            screen = .cards(deck)
        default:
            break
        }
    }

    /// What Undo would take back for this decision, if anything.
    static func undo(for did: Performed, _ decision: Decision) -> ChatUndo? {
        switch did {
        case .plan(let category, _):
            if case .yes(.plan(let p)) = decision { return .plan(category: category, was: p.current) }
            return .plan(category: category, was: nil)
        case .trip(let id, let name, _, _, _):
            return .trip(id: id, name: name)
        default:
            return nil
        }
    }

    private func forgetReads() {
        asks = nil
        reader.forget()
    }

    private func advance(_ did: Performed, _ decision: Decision) {
        let undo = Self.undo(for: did, decision)
        switch screen {
        case .plan(_, let shown):
            if case .plan(let category, let amount) = did {
                screen = .done(said: said, [DoneNote(
                    line: ChatWords.planDone(category, amount), kind: .plan,
                    title: ChatWords.planTitle(category, amount), sub: ChatWords.planSet(today()),
                    link: .plan, linkLabel: "See it in Your plan", undo: undo)])
            } else {
                screen = .noChange(said: said, plan: shown)
            }
        case .cards(var deck):
            switch did {
            case .sorted: deck.sorted += 1
            case .skipped: deck.left += 1
            case .trip(let id, let name, let dates, let total, let place):
                deck.done.append(DoneNote(line: ChatWords.tripDone(name), kind: .trip, title: name, sub: dates,
                                          amount: total, face: place, link: .trip(id), linkLabel: nil,
                                          note: ChatWords.tripLives, undo: undo))
            case .pattern(let title):
                deck.done.append(DoneNote(line: ChatWords.patternDone(title), kind: .rule, title: title, sub: nil,
                                          link: .rules, linkLabel: "See it in Categories and rules"))
            case .nothing, .plan: break
            }
            deck.index += 1
            if deck.current != nil {
                screen = .cards(deck)
            } else if deck.told {
                screen = .sorted(sorted: deck.sorted, left: deck.left)
            } else if !deck.done.isEmpty {
                screen = .done(said: deck.said ?? said, deck.done)
            } else {
                screen = .start
            }
        default:
            break
        }
    }
}
