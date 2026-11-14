// SPIKE (ios/bots/ai-plan.md): compile-only check that Apple's on-device
// Foundation Models framework builds into Pearl at its iOS 16 deployment
// target. Not wired to any screen, never called, never run.

import Foundation
#if canImport(FoundationModels)
import FoundationModels

/// What the model returns for one transaction it's asked to sort.
@available(iOS 26.0, *)
@Generable(description: "Pearl's answer for one transaction")
struct SortGuessSpike {
    @Guide(description: "The transaction's id, exactly as given")
    var id: String
    @Guide(description: "One of Pearl's categories, or a who/what answer",
           .anyOf(["Groceries", "Dining", "Transport", "Hers on the joint account", "Not sure"]))
    var answer: String
    @Guide(description: "How sure, from 0 to 100", .range(0...100))
    var confidence: Int
    @Guide(description: "One short sentence the person will read")
    var reason: String
}

/// A Tool the model can call for detail: one merchant's history.
@available(iOS 26.0, *)
struct MerchantHistorySpike: Tool {
    let name = "merchantHistory"
    let description = "How the person sorted this merchant before: categories and counts."

    @Generable
    struct Arguments {
        @Guide(description: "The merchant's name")
        var merchant: String
    }

    func call(arguments: Arguments) async throws -> String {
        // The real one asks Pearl's API; the spike answers from nothing.
        "\(arguments.merchant): no history"
    }
}

@available(iOS 26.0, *)
enum PearlModelSpike {
    /// Why the model can't run, in words the app could show; nil when it can.
    static var unavailableReason: String? {
        switch SystemLanguageModel.default.availability {
        case .available: return nil
        case .unavailable(.deviceNotEligible): return "This iPhone doesn’t support Apple Intelligence."
        case .unavailable(.appleIntelligenceNotEnabled): return "Apple Intelligence is off."
        case .unavailable(.modelNotReady): return "Apple Intelligence is still getting ready."
        case .unavailable: return "Apple Intelligence isn’t available."
        }
    }

    static func guess(_ lines: String) async throws -> [SortGuessSpike] {
        let session = LanguageModelSession(
            tools: [MerchantHistorySpike()],
            instructions: "You sort a person's bank transactions. Answer only from the facts given.")
        let reply = try await session.respond(to: lines, generating: [SortGuessSpike].self,
                                              options: GenerationOptions(sampling: .greedy))
        return reply.content
    }
}
#endif
