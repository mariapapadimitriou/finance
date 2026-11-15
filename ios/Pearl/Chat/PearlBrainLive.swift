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

    static func brain() -> PearlBrain {
        if stubbed { return ScriptedBrain() }
        #if canImport(FoundationModels)
        if #available(iOS 26.0, *) { return LivePearlBrain() }
        #endif
        return ScriptedBrain()
    }
}

#if canImport(FoundationModels)

/// What Pearl says back, decoded to this shape and nothing else.
@available(iOS 26.0, *)
@Generable(description: "What Pearl says back to her")
struct PearlSays {
    @Guide(description: "One or two short, plain sentences, using only what the tools returned. Empty when the cards say it all.")
    var reply: String
    @Guide(description: "Only when she told Pearl what she did: her words said back to her in one short sentence that starts with 'You said'. Otherwise empty.")
    var echo: String
}

@available(iOS 26.0, *)
struct LivePearlBrain: PearlBrain {
    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        var list: [any Tool] = [TellTool(tools: tools, said: text), SpendingTool(tools: tools, said: text),
                                SubscriptionsTool(tools: tools), TripsTool(tools: tools)]
        if tools.allowsPlans { list.append(PlanTool(tools: tools, said: text)) }
        let session = LanguageModelSession(tools: list, instructions: Self.instructions(plans: tools.allowsPlans))
        let reply = try await session.respond(to: Self.prompt(text, mode), generating: PearlSays.self,
                                              options: GenerationOptions(sampling: .greedy, maximumResponseTokens: 160))
        let says = reply.content
        return BrainReply(text: Self.clean(says.reply), echo: Self.clean(says.echo).flatMap {
            $0.hasPrefix("You said") ? $0 : nil
        })
    }

    private static func clean(_ s: String) -> String? {
        let t = s.trimmingCharacters(in: .whitespacesAndNewlines)
        return t.isEmpty ? nil : t
    }

    /// Short: instructions, tools, her words and the answer share 4,096 tokens.
    static func instructions(plans: Bool, now: Date = Date()) -> String {
        let day = DateFormatter()
        day.dateFormat = "EEEE, yyyy-MM-dd"
        day.locale = Locale(identifier: "en_US_POSIX")
        return """
        You are Pearl, a calm helper in a money app. Today is \(day.string(from: now)).
        Always use a tool, and answer only from what it returns. Never invent amounts, places or dates.
        You can't change anything. The tools only look things up or set out cards she confirms herself.
        She says what she did (went out, bought, paid): tellPearl.
        She asks what she spent: spending.
        Subscriptions: subscriptions. Trips: trips.\(plans ? " A plan or budget for a category: plan." : "")
        Reply in one or two short, plain sentences. Call what she has left to spend her "Allowance", and use no other name for it. Don't give advice.
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
    let tools: ChatTools
    let said: String
    let name = "tellPearl"
    let description = "She told Pearl what she did. Finds her transactions not sorted yet that fit and sets out one card for each."

    @Generable
    struct Arguments {
        @Guide(description: "The spending category it was, like Dining, Groceries or Coffee. Empty if unsure.")
        var category: String
        @Guide(description: "The days she meant, each as YYYY-MM-DD. Empty for the last 7 days.")
        var days: [String]
        @Guide(description: "First names of the people she was with. Empty if none.")
        var people: [String]
    }

    func call(arguments: Arguments) async throws -> String {
        let r = try await tools.tell(said, category: arguments.category.orNil,
                                     days: arguments.days.compactMap(\.orNil),
                                     people: arguments.people.compactMap(\.orNil))
        return r.nothing ? "Nothing fits. \(r.line)" : "\(r.matched) of \(r.open) fit. Pearl shows a card for each."
    }
}

@available(iOS 26.0, *)
struct SpendingTool: Tool {
    let tools: ChatTools
    let said: String
    let name = "spending"
    let description = "What she spent on a category or at a place in a month, against her usual month."

    @Generable
    struct Arguments {
        @Guide(description: "The spending category, like Dining or Groceries. Empty if she named a place.")
        var category: String
        @Guide(description: "The place, as she said it. Empty if she named a category.")
        var place: String
        @Guide(description: "The month as YYYY-MM. Empty for this month.")
        var month: String
    }

    func call(arguments: Arguments) async throws -> String {
        let a = try await tools.spending(said, category: arguments.category.orNil,
                                         month: arguments.month.orNil, merchant: arguments.place.orNil)
        return a.line
    }
}

@available(iOS 26.0, *)
struct SubscriptionsTool: Tool {
    let tools: ChatTools
    let name = "subscriptions"
    let description = "Her subscriptions: what she pays for again and again that isn't a bill."

    @Generable
    struct Arguments {
        @Guide(description: "What she asked, in a few words")
        var question: String
    }

    func call(arguments: Arguments) async throws -> String {
        try await tools.subscriptions().line
    }
}

@available(iOS 26.0, *)
struct TripsTool: Tool {
    let tools: ChatTools
    let name = "trips"
    let description = "Trips Pearl spotted in the last four months. Sets out one card for each."

    @Generable
    struct Arguments {
        @Guide(description: "What she asked, in a few words")
        var question: String
    }

    func call(arguments: Arguments) async throws -> String {
        let trips = try await tools.trips()
        return trips.isEmpty ? "No trip spotted." : "\(trips.count) possible trip(s). Pearl shows a card for each."
    }
}

@available(iOS 26.0, *)
struct PlanTool: Tool {
    let tools: ChatTools
    let said: String
    let name = "plan"
    let description = "A monthly plan for one spending category, from her usual month. Sets it out for her to confirm."

    @Generable
    struct Arguments {
        @Guide(description: "The spending category, like Dining or Groceries")
        var category: String
    }

    func call(arguments: Arguments) async throws -> String {
        guard let p = try await tools.plan(said, category: arguments.category.orNil), !p.nothing,
              let amount = p.amount else { return "Not enough history for a plan." }
        return "Proposed \(Format.whole(amount)) a month for \(p.category ?? "it"). She decides."
    }
}

#endif
