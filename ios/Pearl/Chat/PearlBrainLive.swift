import Foundation
#if canImport(FoundationModels)
import FoundationModels
#endif

// Pearl chat on Apple Intelligence (ios/bots/ai-plan.md; note 1340:8893).
// FoundationModels is iOS 26 only and weak-linked: Pearl still runs on iOS
// 16 to 25, where there's no Pearl button (PC-11).
//
// The model ranks and explains; Python works out the evidence. Its tools only
// read, through ChatTools: they hold nothing that can write, and what they
// find comes back as cards she confirms herself (ChatCore.swift).

/// Whether Pearl chat can run on this iPhone. When it can't, there's no
/// Pearl button at all (PC-11, from AI-15): Search, Quick sort and rules as before.
enum PearlIntelligence {
    /// DEBUG only: `-pearl-chat-stub` runs the chat on ScriptedBrain, so it
    /// can be tried on a simulator, where Apple Intelligence can't run.
    static var stubbed: Bool {
        #if DEBUG
        return ProcessInfo.processInfo.arguments.contains("-pearl-chat-stub")
        #else
        return false
        #endif
    }

    /// Apple Intelligence is on, ready and speaks her language. Not when the
    /// iPhone can't run it (deviceNotEligible), it's off
    /// (appleIntelligenceNotEnabled) or still downloading (modelNotReady).
    static var available: Bool {
        if stubbed { return true }
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) {
            let model = SystemLanguageModel.default
            return model.availability == .available && model.supportsLocale()
        }
        #endif
        return false
    }

    static func brain(plans: Bool = false) -> PearlBrain {
        if stubbed { return ScriptedBrain() }
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) { return LivePearlBrain(plans: plans) }
        #endif
        return ScriptedBrain()
    }
}

#if canImport(FoundationModels)

/// What Pearl says back, decoded to this shape and nothing else.
@available(iOS 26.0, *)
@Generable(description: "What Pearl says back to her")
struct PearlSays {
    @Guide(description: "One or two short sentences from what the tools returned. Empty when the cards say it.")
    var reply: String
    @Guide(description: "When she said what she did: her words back in one sentence starting 'You said'. Else empty.")
    var echo: String
}

/// Who and what the tools are working for this turn. The session, and its
/// tools, are made and loaded before she types (2026-11-15); her words and
/// this turn's ChatTools are only known when she sends.
@available(iOS 26.0, *)
final class ChatTurn: @unchecked Sendable {
    private let lock = NSLock()
    private var tools: ChatTools?
    private var words = ""
    private var calls = 0
    /// Each tool call is a trip to the server and another pass of the model:
    /// two at most in a turn (2026-11-15).
    static let most = 2
    static let enough = "That's enough to answer. Answer now from what the tools returned."

    func begin(_ tools: ChatTools, said: String) {
        lock.lock(); defer { lock.unlock() }
        self.tools = tools
        words = said
        calls = 0
    }

    /// A tool's turn to call the server, or nil when the turn has had its two.
    func next() throws -> (ChatTools, String)? {
        lock.lock(); defer { lock.unlock() }
        guard let tools = tools else { throw Gone() }
        calls += 1
        return calls > Self.most ? nil : (tools, words)
    }

    func end() {
        lock.lock(); defer { lock.unlock() }
        tools = nil
    }

    struct Gone: Error {}

}

/// Apple Intelligence. 2026-11-15, for speed: the next turn's session is made
/// and prewarmed ahead (when the chat opens, and after each answer), so her
/// words go to a model that's already loaded with Pearl's instructions and
/// tools. Each turn gets a fresh session: the chat is one exchange at a time,
/// and an old turn's transcript would only eat the 4,096 tokens. The answer
/// streams, so the first words show while the rest comes.
@available(iOS 26.0, *)
final class LivePearlBrain: PearlBrain, @unchecked Sendable {
    private let plans: Bool
    private let lock = NSLock()
    private var ready: (session: LanguageModelSession, turn: ChatTurn, day: String)?

    init(plans: Bool) { self.plans = plans }

    var isModel: Bool { true }

    func prewarm() {
        let next = take(keep: true)
        next.session.prewarm()
    }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        try await respond(to: text, mode: mode, tools: tools, partial: { _ in })
    }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools,
                 partial: @escaping @Sendable (String) -> Void) async throws -> BrainReply {
        let began = DispatchTime.now().uptimeNanoseconds
        let now = take(keep: false, plans: tools.allowsPlans)
        now.turn.begin(tools, said: text)
        defer {
            now.turn.end()
            prewarm()
        }
        let stream = now.session.streamResponse(to: Self.prompt(text, mode), generating: PearlSays.self,
                                                options: GenerationOptions(sampling: .greedy, maximumResponseTokens: 160))
        var reply: String?
        var echo: String?
        var first = true
        for try await snapshot in stream {
            if first {
                ChatLog.note("model first words", since: began)
                first = false
            }
            reply = snapshot.content.reply
            echo = snapshot.content.echo
            if let words = Self.clean(reply ?? "") { partial(words) }
        }
        ChatLog.note("model", since: began)
        return BrainReply(text: Self.clean(reply ?? ""), echo: Self.clean(echo ?? "").flatMap {
            $0.hasPrefix("You said") ? $0 : nil
        })
    }

    /// The session made ahead, if it's still today's and has the right
    /// tools; else a new one. `keep` leaves it ready for the next turn.
    private func take(keep: Bool, plans wanted: Bool? = nil) -> (session: LanguageModelSession, turn: ChatTurn, day: String) {
        lock.lock(); defer { lock.unlock() }
        let day = Self.day.string(from: Date())
        let plans = wanted ?? self.plans
        if let r = ready, r.day == day, plans == self.plans, !r.session.isResponding {
            if !keep { ready = nil }
            return r
        }
        let turn = ChatTurn()
        var list: [any Tool] = [TellTool(turn: turn), SpendingTool(turn: turn),
                                SubscriptionsTool(turn: turn), TripsTool(turn: turn)]
        if plans { list.append(PlanTool(turn: turn)) }
        let made = (session: LanguageModelSession(tools: list, instructions: Self.instructions(plans: plans)),
                    turn: turn, day: day)
        ready = keep ? made : nil
        return made
    }

    private static let day: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM-dd"
        f.locale = Locale(identifier: "en_US_POSIX")
        return f
    }()

    private static func clean(_ s: String) -> String? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }

    /// Short: instructions, tools, her words and the answer share 4,096
    /// tokens, and every token is time on the iPhone. 2026-11-15: the model
    /// only sees words the server couldn't read, so this says only what it
    /// needs for those.
    static func instructions(plans: Bool, now: Date = Date()) -> String {
        let day = DateFormatter()
        day.dateFormat = "EEEE, yyyy-MM-dd"
        day.locale = Locale(identifier: "en_US_POSIX")
        return """
        You are Pearl in a money app. Today is \(day.string(from: now)).
        Call one tool, then answer only from what it returns. Never invent amounts, places or dates. You can't change anything.
        What she did: tellPearl. What she spent: spending. Subscriptions: subscriptions. Trips: trips.\(plans ? " A plan: plan." : "")
        One or two short sentences. Call what she has left to spend her "Allowance". No advice.
        """
    }

    private static func prompt(_ text: String, _ mode: ChatMode?) -> String {
        switch mode {
        case .tell?: return "She's telling Pearl what she did: \(text)"
        case .ask?: return "She's asking about her spending: \(text)"
        case .subscriptions?: return "Find her subscriptions."
        case .trips?: return "Was there a trip?"
        case nil: return text
        }
    }
}

@available(iOS 26.0, *)
private extension String {
    var orNil: String? {
        let t = trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }
}

/// She said what she did: what isn't sorted yet that fits, one card each.
/// Her own words go to the server; the model's reading of them are hints.
@available(iOS 26.0, *)
struct TellTool: Tool {
    let turn: ChatTurn
    let name = "tellPearl"
    let description = "She said what she did. Sets out a card for each unsorted transaction that fits."

    @Generable
    struct Arguments {
        @Guide(description: "Category, like Dining or Groceries. Empty if unsure.")
        var category: String
        @Guide(description: "Days she meant, YYYY-MM-DD. Empty: last 7 days.")
        var days: [String]
        @Guide(description: "First names of who she was with.")
        var people: [String]
    }

    func call(arguments: Arguments) async throws -> String {
        guard let (tools, said) = try turn.next() else { return ChatTurn.enough }
        let r = try await tools.tell(said, category: arguments.category.orNil,
                                     days: arguments.days.compactMap(\.orNil),
                                     people: arguments.people.compactMap(\.orNil))
        return r.nothing ? "Nothing fits. \(r.line)" : "\(r.matched) of \(r.open) fit. Pearl shows a card for each."
    }
}

@available(iOS 26.0, *)
struct SpendingTool: Tool {
    let turn: ChatTurn
    let name = "spending"
    let description = "What she spent on a category or at a place in a month."

    @Generable
    struct Arguments {
        @Guide(description: "Category, like Dining. Empty if she named a place.")
        var category: String
        @Guide(description: "Place, as she said it. Empty if a category.")
        var place: String
        @Guide(description: "Month, YYYY-MM. Empty: this month.")
        var month: String
    }

    func call(arguments: Arguments) async throws -> String {
        guard let (tools, said) = try turn.next() else { return ChatTurn.enough }
        let a = try await tools.spending(said, category: arguments.category.orNil,
                                         month: arguments.month.orNil, merchant: arguments.place.orNil)
        return a.line
    }
}

@available(iOS 26.0, *)
struct SubscriptionsTool: Tool {
    let turn: ChatTurn
    let name = "subscriptions"
    let description = "Her subscriptions."

    @Generable
    struct Arguments {}

    func call(arguments: Arguments) async throws -> String {
        guard let (tools, _) = try turn.next() else { return ChatTurn.enough }
        return try await tools.subscriptions().line
    }
}

@available(iOS 26.0, *)
struct TripsTool: Tool {
    let turn: ChatTurn
    let name = "trips"
    let description = "Trips Pearl spotted. Sets out a card for each."

    @Generable
    struct Arguments {}

    func call(arguments: Arguments) async throws -> String {
        guard let (tools, _) = try turn.next() else { return ChatTurn.enough }
        let trips = try await tools.trips()
        return trips.isEmpty ? "No trip spotted." : "\(trips.count) possible trip(s). Pearl shows a card for each."
    }
}

@available(iOS 26.0, *)
struct PlanTool: Tool {
    let turn: ChatTurn
    let name = "plan"
    let description = "A monthly plan for one category, for her to confirm."

    @Generable
    struct Arguments {
        @Guide(description: "Category, like Dining")
        var category: String
    }

    func call(arguments: Arguments) async throws -> String {
        guard let (tools, said) = try turn.next() else { return ChatTurn.enough }
        guard let p = try await tools.plan(said, category: arguments.category.orNil), !p.nothing,
              let amount = p.amount else { return "Not enough history for a plan." }
        return "Proposed \(Format.whole(amount)) a month for \(p.category ?? "it"). She decides."
    }
}

#endif
