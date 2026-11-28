import Foundation

// Pearl chat's logic on a scripted model, for this Mac (ios/tools/check_chat.py
// compiles it with ios/Pearl/Chat/ChatCore.swift and API/Models.swift). No
// simulator, no Apple Intelligence: what only an iPhone can show is listed in
// check_chat.py.

var failures = 0
var checks = 0

func expect(_ ok: Bool, _ what: String, file: StaticString = #file, line: UInt = #line) {
    checks += 1
    if !ok {
        failures += 1
        print("FAIL (line \(line)): \(what)")
    }
}

func decode<T: Decodable>(_ json: String) throws -> T {
    try JSONDecoder().decode(T.self, from: Data(json.utf8))
}

/// The server, as fixtures. Records every read.
final class FakeReader: ChatReading {
    var replies: [String: String] = [:]
    /// Said once each, in order, before `replies` (the server's first reading, then the model's).
    var first: [String: [String]] = [:]
    var reads: [(String, [String: Any])] = []

    private func reply(_ path: String) throws -> String {
        if var queue = first[path], !queue.isEmpty {
            let json = queue.removeFirst()
            first[path] = queue
            return json
        }
        guard let json = replies[path] else { throw URLError(.fileDoesNotExist) }
        return json
    }

    func get<T: Decodable>(_ path: String) async throws -> T {
        reads.append((path, [:]))
        return try decode(try reply(path))
    }

    func read<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        reads.append((path, body))
        return try decode(try reply(path))
    }
}

/// Every write the chat makes. The checks below count them.
final class FakeWriter: ChatWriting {
    var writes: [(method: String, path: String, body: [String: Any])] = []
    var replies: [String: String] = [:]

    func post<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        writes.append(("POST", path, body))
        return try decode(replies[path] ?? "{}")
    }

    func put<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        writes.append(("PUT", path, body))
        return try decode(replies[path] ?? "{}")
    }

    func delete<T: Decodable>(_ path: String, query: [String: String]) async throws -> T {
        writes.append(("DELETE", path, query))
        return try decode(replies[path] ?? "{}")
    }
}

/// A server that's down: every read fails.
final class DownReader: ChatReading {
    struct Down: Error {}
    func get<T: Decodable>(_ path: String) async throws -> T { throw Down() }
    func read<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T { throw Down() }
}

/// A model that calls every tool it has, whatever she said. It still can't
/// change anything: tools are all it gets.
struct GreedyBrain: PearlBrain {
    var isModel: Bool { true }
    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        _ = try? await tools.spending(text)
        _ = try? await tools.subscriptions()
        _ = try? await tools.trips()
        _ = try? await tools.patterns()
        _ = try? await tools.plan(text)
        _ = try? await tools.tell(text, category: "Dining")
        return BrainReply(text: "Here you go.", echo: "You said you went out with friends Saturday.")
    }
}

struct BrokenBrain: PearlBrain {
    var isModel: Bool { true }
    struct Refused: Error {}
    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply { throw Refused() }
}

func brief(_ id: String, _ merchant: String, _ amount: Double) -> String {
    """
    {"id": "\(id)", "date": "2026-11-14", "merchant": "\(merchant)", "description": "\(merchant.uppercased())",
     "amount": \(amount), "my_amount": \(amount), "account_name": "TD Visa ••9021", "category": "Other"}
    """
}

func proposal(_ id: String, _ merchant: String, _ amount: Double, split: [String] = []) -> String {
    let names = split.map { "\"\($0)\"" }.joined(separator: ", ")
    return """
    {"id": "sort:\(id)", "kind": "sort", "key": "cat:\(id)", "category": "Dining", "was": "Other",
     "split_with": [\(names)], "txn": \(brief(id, merchant, amount)),
     "item": {"key": "cat:\(id)", "txn": \(brief(id, merchant, amount)), "guess": "Dining", "reason": "x"}}
    """
}

let window = """
{"start": "2026-11-14", "end": "2026-11-14", "days": ["2026-11-14"], "label": "Saturday", "span": "Sat"}
"""

let tell3 = """
{"said": "went out with friends Saturday", "category": "Dining", "people": [], "window": \(window),
 "open": 5, "matched": 3, "nothing": false, "line": "A guess for 3 of 5 from Saturday",
 "proposals": [\(proposal("a", "Bar Raval", 64.5)), \(proposal("b", "Bar Raval", 128, split: ["Jo", "Sam"])),
               \(proposal("c", "Pizza Nova", 26.65))]}
"""

let tellNone = """
{"said": "went to the cottage", "category": "Lodging", "people": [], "window": \(window),
 "open": 9, "matched": 0, "nothing": true, "proposals": [],
 "line": "None of the 9 not sorted yet from Sat\\u2013Sun fit what you said. Your cards stay as they were."}
"""

let trip = """
{"id": "2026-03-04:2026-03-09", "key": "trip:2026-03-04:2026-03-09", "ids": ["t1", "t2", "t3", "t4"],
 "start": "2026-03-04", "end": "2026-03-09", "days": 5, "place": "Montréal", "flight": true, "hotel": true,
 "name": "Trip to Montréal", "count": 23, "totals": [{"currency": "CAD", "amount": 1284.6}],
 "month_names": ["March"]}
"""

let pattern = """
{"id": "joint:ana", "kind": "joint", "merchant": "Ana Ruiz", "answer": "Ana Ruiz", "label": "Ana’s share",
 "count": 8, "need": 8, "joint": "Joint", "rhythm": "about every 2 weeks", "amount": 400, "low": 400,
 "high": 400, "same_amount": true, "etransfers": true}
"""

let plan = """
{"nothing": false, "category": "Dining", "usual": 214.0, "amount": 220, "months": 3}
"""

let spending = """
{"nothing": false, "title": "Dining, October", "category": "Dining", "merchant": null, "month": "2026-10",
 "total": 286.0, "usual": 214.0, "count": 4, "rows": [\(brief("p1", "Pai Northern Thai", 120))],
 "line": "You spent $286 on Dining in October, $72 more than usual."}
"""

/// 2026-11-15 (speed): a model that's slow after its tool, as Apple
/// Intelligence is while it writes its sentence. `look` runs while it's still
/// "writing", to see what the chat shows by then.
final class SlowBrain: PearlBrain, @unchecked Sendable {
    var prewarmed = 0
    let tool: (ChatTools) async throws -> Void
    let words: [String]
    let echo: String?
    let fail: Bool
    var look: (@MainActor () -> Void)?

    init(words: [String] = [], echo: String? = nil, fail: Bool = false,
         tool: @escaping (ChatTools) async throws -> Void) {
        self.words = words
        self.echo = echo
        self.fail = fail
        self.tool = tool
    }

    func prewarm() { prewarmed += 1 }

    var isModel: Bool { true }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools) async throws -> BrainReply {
        try await respond(to: text, mode: mode, tools: tools, partial: { _ in })
    }

    func respond(to text: String, mode: ChatMode?, tools: ChatTools,
                 partial: @escaping @Sendable (String) -> Void) async throws -> BrainReply {
        try await tool(tools)
        for w in words {
            partial(w)
            try await Task.sleep(nanoseconds: 30_000_000)
        }
        try await Task.sleep(nanoseconds: 30_000_000)
        if let look = look { await look() }
        struct Refused: Error {}
        if fail { throw Refused() }
        return BrainReply(text: words.last, echo: echo)
    }
}

let spendingNone = """
{"nothing": true, "month": "2026-11", "line": "Pearl couldn’t tell which spending you meant."}
"""

func server(suggest: Bool = false, trips: Bool = true, patterns: Bool = false) -> FakeReader {
    let r = FakeReader()
    r.replies["api/chat"] = """
    {"suggest": \(suggest), "categories": ["Dining", "Groceries"], "people": ["Jo", "Sam"], "today": "2026-11-15"}
    """
    r.replies["api/chat/tell"] = tell3
    r.replies["api/chat/spending"] = spending
    r.replies["api/chat/subscriptions"] = """
    {"count": 1, "monthly": 16.99, "rows": [\(brief("s1", "Streamflix", 16.99))], "line": "You have 1 subscription, about $17 a month."}
    """
    r.replies["api/chat/asks"] = "{\"patterns\": [\(patterns ? pattern : "")], \"trips\": [\(trips ? trip : "")]}"
    r.replies["api/chat/plan"] = plan
    return r
}


/// Ask Pearl's server, as a script of stream lines (THL-308; finance/ask.py).
/// Records every question. `fail` throws instead; `offline` as no connection.
final class FakeAsker: ChatAsking, @unchecked Sendable {
    var lines: [String]
    var fail: Error?
    var asked: [String] = []

    init(_ lines: [String], fail: Error? = nil) {
        self.lines = lines
        self.fail = fail
    }

    func ask(_ text: String, plans: Bool) -> AsyncThrowingStream<AskEvent, Error> {
        asked.append(text)
        let lines = self.lines, fail = self.fail
        return AsyncThrowingStream { c in
            for l in lines { if let e = AskEvent.parse(l) { c.yield(e) } }
            if let fail = fail { c.finish(throwing: fail) } else { c.finish() }
        }
    }
}

let monthFact = """
{"type": "fact", "kind": "month", "data": {"month": "2026-11", "name": "November", "current": true,
 "money_in": 4300, "spent": 1284, "top": [{"category": "Dining", "amount": 400, "share": 0.31}],
 "allowance_left": 829, "over_by": null, "usual_by_now": 1090, "day": 27,
 "changes": [{"category": "Dining", "over": 120, "count": 9}]}}
"""

let cardsFact = """
{"type": "fact", "kind": "cards", "data": {"cards": [
 {"name": "TD Visa", "spent": 642, "balance": 1840, "limit": 5000, "used": 0.368, "state": "ok", "due": "2026-12-03"},
 {"name": "Amex Cobalt", "spent": 318, "balance": 2710, "limit": 3000, "used": 0.9033, "state": "near", "due": "2026-12-14"}]}}
"""

let suggestion = """
{"type": "suggestion", "text": "Dining is the biggest change. Want to look at those 9 purchases?",
 "action": {"label": "See Dining", "open": "category", "category": "Dining", "month": "2026-11"}}
"""

@MainActor
func answer(_ e: ChatEngine) -> ChatAnswer? {
    if case .answer(let a) = e.screen { return a }
    return nil
}

@MainActor
func engine(_ reader: FakeReader, _ writer: FakeWriter, brain: PearlBrain = ScriptedBrain(),
            plans: Bool = true) -> ChatEngine {
    ChatEngine(brain: brain, reader: ChatReader(reader), executor: ChatExecutor(writer: writer), allowsPlans: plans)
}

@MainActor
func deck(_ e: ChatEngine) -> Deck? {
    if case .cards(let d) = e.screen { return d }
    return nil
}

@main
struct ChatChecks {
    @MainActor
    static func main() async {
        // Routing her words when the model can't.
        expect(ScriptedBrain.route("went out with friends Saturday", nil, plans: true) == .tell, "told → tell")
        expect(ScriptedBrain.route("What did I spend eating out in October?", nil, plans: true) == .spending, "asked → spending")
        expect(ScriptedBrain.route("find my subscriptions", nil, plans: true) == .subscriptions, "subscriptions")
        expect(ScriptedBrain.route("was this a trip", nil, plans: true) == .trips, "trips")
        expect(ScriptedBrain.route("Make me a plan for eating out.", nil, plans: true) == .plan, "plan")
        expect(ScriptedBrain.route("Make me a plan for eating out.", nil, plans: false) == .spending,
               "plans off: a plan question gets the numbers")
        expect(ScriptedBrain.route("anything", .ask, plans: true) == .spending, "a starter wins")

        // PC-05: told guesses, one card each; nothing written until a tap.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w)
            await e.send("went out with friends Saturday")
            guard let d = deck(e) else { expect(false, "told: cards"); return }
            expect(d.cards.count == 3, "one card per transaction")
            expect(d.leadLine == "A guess for 3 of 5 from Saturday.", "PC-05 lead: \(d.leadLine ?? "nil")")
            expect(d.overline() == "Pearl’s guess · 1 of 3", "PC-05 overline: \(d.overline())")
            expect(d.said == "went out with friends Saturday", "her words, for her bubble")
            expect(d.echo == "You said “went out with friends Saturday”.", "echo fallback: \(d.echo ?? "nil")")
            expect(w.writes.isEmpty, "nothing changes before she taps")
            expect(r.reads.allSatisfy { $0.0.hasPrefix("api/chat") }, "the model's tools read only /api/chat")

            await e.decide(.yes(d.cards[0]), tap: UserTap("yes"))
            expect(w.writes.count == 1, "Yes writes once")
            expect(w.writes.first?.path == "api/transactions/a/mark", "Yes marks the transaction")
            expect(w.writes.first?.body["remember"] as? Bool == false, "a told guess saves no rule")
            expect(w.writes.first?.body["category"] as? String == "Dining", "as she said")
            // G7-Tell-r: after the first card the count is in the progress line.
            expect(deck(e)?.overline() == "Pearl’s guess", "PC-06 overline: \(deck(e)?.overline() ?? "")")
            expect(deck(e)?.overline(choice: true) == "Your choice", "a held answer says Your choice")
            expect(deck(e)?.leadLine == nil, "the lead is over the first card only")
            expect(deck(e)?.showsProgress == true, "G7-Tell-r: the progress line after the first card")
            expect(deck(e)?.progressTitle == "went out with friends Saturday", "her words, short: \(deck(e)?.progressTitle ?? "")")
            expect(deck(e)?.progressTotal == 3 && deck(e)?.index == 1, "2 of 3")
            expect(d.showsProgress == false, "the first card keeps her bubble")
            expect(ChatWords.shortSaid("Out with friends Saturday, brunch with Jo and Sam, Uber home") == "Out with friends Saturday",
                   "G7-Tell-r: her sentence to its first part")

            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            expect(w.writes.count == 1, "Skip on a told guess sends nothing: it stays in Needs a look")

            await e.decide(.yes(deck(e)!.current!), tap: UserTap("yes"))
            if case .sorted(let sorted, let left) = e.screen {
                expect(sorted == 2 && left == 1, "PC-07 counts")
                expect(ChatWords.sortedTitle(sorted: sorted, left: left) == "Sorted 2. 1 left for later.", "PC-07 title")
                expect(ChatWords.sortedBody(left: 2) == "2 back in Needs a look", "PC-07 row")
                expect(ChatWords.sortedBody(left: 0) == nil, "no row when none are left")
                expect(ChatWords.seeThe(2) == "See the 2", "PC-07 link")
            } else {
                expect(false, "PC-07 after the last card")
            }
        }

        // PC-06: a held split from Who was it with? is sent only by Yes.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w)
            await e.send("dinner with Jo and Sam Saturday")
            let second = deck(e)!.cards[1]
            guard case .sort(let s) = second else { expect(false, "sort card"); return }
            expect(s.splitWith == ["Jo", "Sam"], "who, as a suggestion")
            expect(ChatWords.maybeSplit(s.splitWith) == "Maybe split with Jo and Sam?", "PC-06 pill")
            expect(ChatWords.lead("A guess for 7 of the 9 from the weekend.") == "A guess for 7 of the 9 from the weekend.",
                   "a lead that already ends keeps its stop")
            var sent = false
            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            await e.decide(.held(s, label: "Dining, split with Jo and Sam") { sent = true }, tap: UserTap("yes"))
            expect(sent, "the held split is sent on Yes")
            expect(w.writes.isEmpty, "and by its own page's request, not another")
        }

        // A model that calls every tool still changes nothing. (2026-11-15:
        // the model is asked only when the server couldn't read her words.)
        do {
            let r = server(), w = FakeWriter()
            r.first["api/chat/tell"] = [tellNone]
            let e = engine(r, w, brain: GreedyBrain())
            await e.send("went out with friends Saturday")
            expect(w.writes.isEmpty, "a greedy model writes nothing")
            expect(deck(e)?.echo == "You said you went out with friends Saturday.", "the model's echo")
        }

        // Apple Intelligence can't answer: the server reads her words instead.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w, brain: BrokenBrain())
            await e.send("went out with friends Saturday")
            expect(deck(e)?.cards.count == 3, "falls back to the scripted model")
        }
        // The server couldn't, and the model can't either: the server's reading stands.
        do {
            let r = server(), w = FakeWriter()
            r.replies["api/chat/tell"] = tellNone
            let e = engine(r, w, brain: BrokenBrain())
            await e.send("went to the cottage")
            if case .nothing = e.screen {} else { expect(false, "PC-10 from the server's reading") }
            expect(r.reads.filter { $0.0 == "api/chat/tell" }.count == 1, "and it isn't asked twice")
        }

        // PC-10: nothing matched.
        do {
            let r = server(), w = FakeWriter()
            r.replies["api/chat/tell"] = tellNone
            let e = engine(r, w)
            await e.send("went to the cottage")
            if case .nothing(let line) = e.screen {
                expect(line.hasPrefix("None of the 9 not sorted yet from Sat–Sun"), "PC-10 line")
            } else {
                expect(false, "PC-10")
            }
            expect(w.writes.isEmpty, "nothing matched writes nothing")
        }

        // PC-04: an answer with the rows behind it.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w)
            await e.send("What did I spend eating out in October?")
            if case .reply(let said, let text, let answer, let rows) = e.screen {
                expect(said == "What did I spend eating out in October?", "her words quoted")
                expect(text.hasPrefix("You spent $286"), "the server's words without a model")
                expect(answer?.usual == 214 && rows.count == 1, "totals and rows")
            } else {
                expect(false, "PC-04")
            }
            expect(w.writes.isEmpty, "asking writes nothing")
        }

        // PC-12 / PC-13: Not now changes nothing; Set it is one PUT.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w)
            await e.send("Make me a plan for eating out.")
            guard case .plan(_, let p) = e.screen else { expect(false, "PC-12"); return }
            expect(ChatWords.planQuestion("Dining", p.amount!) == "Make a Dining plan of $220 a month?", "PC-12 question")
            expect(ChatWords.planLead(months: 3) == "Here’s a plan from your last 3 months. Nothing changes until you set it.",
                   "PC-12 lead")
            await e.decide(.skip(.plan(p)), tap: UserTap("not-now"))
            if case .noChange = e.screen {} else { expect(false, "Not now → Okay, nothing changed.") }
            expect(ChatWords.nothingChanged == "Okay, nothing changed.", "Not now's words")
            expect(w.writes.isEmpty, "Not now sends nothing")

            await e.send("Make me a plan for eating out.")
            guard case .plan(_, let p2) = e.screen else { expect(false, "PC-12 again"); return }
            await e.decide(.yes(.plan(p2)), tap: UserTap("set-it"))
            expect(w.writes.count == 1 && w.writes[0].method == "PUT" && w.writes[0].path == "api/your-plan/rows/Dining",
                   "Set it: Your plan's row")
            expect(w.writes[0].body["amount"] as? Double == 220, "the $220 shown, not a 5% step")
            expect(w.writes[0].body["source"] as? String == "chat", "marked as set in Pearl chat")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.line == "Done. Dining plan set to $220 a month.", "PC-13: \(notes.first?.line ?? "")")
            } else {
                expect(false, "PC-13")
            }
        }

        // Plans off (Features.chatPlans): no plan proposal at all.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w, plans: false)
            await e.send("Make me a plan for eating out.")
            if case .plan = e.screen { expect(false, "no plans while off") }
            expect(!r.reads.contains { $0.0 == "api/chat/plan" }, "the plan endpoint isn't read")
        }

        // PC-08: Was this a trip? One card; Yes is TR-01's own endpoint.
        do {
            let r = server(), w = FakeWriter()
            w.replies["api/trips/asks/2026-03-04:2026-03-09/yes"] = """
            {"ok": true, "trip": {"id": "tr1", "name": "Trip to Montréal", "ids": ["t1"], "start": "2026-03-04",
             "end": "2026-03-09", "count": 23, "totals": [{"currency": "CAD", "amount": 1284.6}]}}
            """
            let e = engine(r, w)
            await e.pick(.trips)
            guard let d = deck(e), case .trip(let t)? = d.current else { expect(false, "PC-08"); return }
            expect(d.overline() == "A trip? · one card for all 23", "PC-08 overline: \(d.overline())")
            expect(ChatWords.tripQuestion(t) == "Were you in Montréal?", "the trip question names the place")
            expect(ChatWords.tripAway(t) == "A flight, a hotel, 5 days away.", "PC-08 sub: \(ChatWords.tripAway(t))")
            expect(d.said == "Was this a trip?", "the starter's words, for her bubble")
            expect(w.writes.isEmpty, "a trip card changes nothing by itself")
            await e.decide(.yes(d.current!), tap: UserTap("yes"))
            expect(w.writes.first?.path == "api/trips/asks/2026-03-04:2026-03-09/yes", "Yes: TR-01's endpoint")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.line == "Done. Trip to Montréal made.", "trip confirmation")
                expect(notes.first?.link == .trip("tr1"), "a link to where it lives")
                expect(notes.first?.sub == Format.span("2026-03-04", "2026-03-09") && notes.first?.amount == "$1,284.60",
                       "the trip's row: dates and total")
                expect(notes.first?.undo == .trip(id: "tr1", name: "Trip to Montréal"), "Undo can take it back")
            } else {
                expect(false, "done after the trip")
            }
        }

        // No trip to ask about.
        do {
            let r = server(trips: false), w = FakeWriter()
            let e = engine(r, w)
            await e.pick(.trips)
            if case .reply(_, let text, _, _) = e.screen {
                expect(text == ChatWords.noTrip, "no trip")
            } else {
                expect(false, "no trip reply")
            }
        }

        // PB-01's suggestion: opening the chat offers the pattern first, as Quick sort does.
        do {
            let r = server(suggest: true, trips: true, patterns: true), w = FakeWriter()
            let e = engine(r, w)
            await e.open()
            guard let d = deck(e) else { expect(false, "suggestions first"); return }
            expect(d.cards.count == 2, "pattern and trip")
            expect(d.overline() == "A pattern · once for all of them", "PC-09 overline")
            if case .pattern(let p)? = d.current {
                expect(ChatWords.patternSub(p) == "Your last 8 were Ana’s share.", "PC-09 sub: \(ChatWords.patternSub(p))")
            }
            await e.decide(.skip(d.current!), tap: UserTap("skip"))
            expect(w.writes.last?.path == "api/pattern-sort/asks/joint:ana/skip", "Skip: AI-18's own skip")
            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            expect(w.writes.last?.path == "api/trips/asks/2026-03-04:2026-03-09/skip", "Skip: TR-01's own skip")
            if case .start = e.screen {} else { expect(false, "both skipped: back to the starters") }
        }

        // A pattern's Yes.
        do {
            let r = server(suggest: true, trips: false, patterns: true), w = FakeWriter()
            let e = engine(r, w)
            await e.open()
            await e.decide(.yes(deck(e)!.current!), tap: UserTap("yes"))
            expect(w.writes.first?.path == "api/pattern-sort/asks/joint:ana/yes", "Yes: AI-18's endpoint")
            expect(w.writes.first?.body["how"] as? String == "pc09", "said where")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.line == "Done. Ana’s deposits rule made.", "pattern confirmation: \(notes.first?.line ?? "")")
            } else {
                expect(false, "done after the pattern")
            }
        }


        // G7 trip question: never "A trip?", and without a place, still a question.
        do {
            let noPlace: TripAsk = try! decode("""
            {"id": "x", "key": "trip:x", "ids": ["t1"], "start": "2026-06-12", "end": "2026-06-16", "days": 4,
             "flight": true, "count": 18, "totals": [{"currency": "CAD", "amount": 1240}]}
            """)
            expect(ChatWords.tripQuestion(noPlace) == "Was this a trip?", "no place: \(ChatWords.tripQuestion(noPlace))")
            expect(ChatWords.tripAway(noPlace) == "A flight, 4 days away.", "no hotel: \(ChatWords.tripAway(noPlace))")
            let farm: PatternAsk = try! decode("""
            {"id": "m:farm", "kind": "merchant", "merchant": "Farm Boy", "answer": "Groceries", "label": "Groceries",
             "count": 5, "need": 5, "amount": 27, "low": 12, "high": 48, "rhythm": "about every week"}
            """)
            expect(ChatWords.patternSub(farm) == "Your last 5 at Farm Boy were Groceries.", "PC-09 sub, a shop")
            expect(farm.question == "Always Groceries?", "PC-09 question")
        }

        // G7-Confirm (NEW): Undo on the toast after Set it puts the plan back as it was.
        do {
            let r = server(), w = FakeWriter()
            let e = engine(r, w)
            e.today = { "2026-11-18" }
            await e.send("Make me a plan for eating out.")
            guard case .plan(_, let p) = e.screen else { expect(false, "PC-12 for Undo"); return }
            let did = await e.decide(.yes(.plan(p)), tap: UserTap("set-it"))
            let u = did.flatMap { ChatEngine.undo(for: $0, .yes(.plan(p))) }
            expect(u == .plan(category: "Dining", was: nil), "no row before: Undo removes it")
            expect(u?.toast == "Dining plan set", "the toast's words: \(u?.toast ?? "")")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.title == "Dining plan · $220 a month", "PC-13 card: \(notes.first?.title ?? "")")
                expect(notes.first?.sub == "Set \(Format.short("2026-11-18"))", "PC-13 sub: \(notes.first?.sub ?? "")")
                expect(notes.first?.undo == u, "the note knows its Undo")
            } else { expect(false, "PC-13 before Undo") }
            try? await e.undo(u!, tap: UserTap("undo"))
            expect(w.writes.last?.method == "DELETE" && w.writes.last?.path == "api/your-plan/rows/Dining",
                   "Undo: Your plan's row goes")
            if case .noChange = e.screen {} else { expect(false, "after Undo: Okay, nothing changed.") }
            expect(w.writes.count == 2, "Set it, then Undo: two writes")
        }
        do {
            let r = server(), w = FakeWriter()
            r.replies["api/chat/plan"] = """
            {"nothing": false, "category": "Dining", "usual": 214.0, "amount": 220, "months": 3, "current": 180}
            """
            let e = engine(r, w)
            await e.send("Make me a plan for eating out.")
            guard case .plan(_, let p) = e.screen else { expect(false, "PC-12 with a row"); return }
            expect(p.current == 180, "the row she had")
            let did = await e.decide(.yes(.plan(p)), tap: UserTap("set-it"))
            let u = did.flatMap { ChatEngine.undo(for: $0, .yes(.plan(p))) }
            expect(u == .plan(category: "Dining", was: 180), "Undo knows the old amount")
            try? await e.undo(u!, tap: UserTap("undo"))
            expect(w.writes.last?.method == "PUT" && w.writes.last?.body["amount"] as? Double == 180,
                   "Undo: the old amount back")
        }
        // G7-Confirm (NEW): Undo on "Trip to Montréal made" takes back only that trip.
        do {
            let r = server(), w = FakeWriter()
            w.replies["api/trips/asks/2026-03-04:2026-03-09/yes"] = """
            {"ok": true, "trip": {"id": "tr1", "name": "Trip to Montréal", "ids": ["t1"], "start": "2026-03-04",
             "end": "2026-03-09", "count": 23, "totals": [{"currency": "CAD", "amount": 1284.6}]}}
            """
            let e = engine(r, w)
            await e.pick(.trips)
            guard let card = deck(e)?.current else { expect(false, "trip card for Undo"); return }
            let did = await e.decide(.yes(card), tap: UserTap("yes"))
            let u = did.flatMap { ChatEngine.undo(for: $0, .yes(card)) }
            expect(u?.toast == "Trip to Montréal made", "the trip toast")
            try? await e.undo(u!, tap: UserTap("undo"))
            expect(w.writes.last?.method == "DELETE" && w.writes.last?.path == "api/trips/tr1"
                   && w.writes.last?.body["undo"] as? String == "1", "Undo: DELETE the trip, dates not skipped")
            if case .noChange = e.screen {} else { expect(false, "after the trip's Undo") }
        }
        // A skip or a told guess has no Undo on the toast.
        do {
            expect(ChatEngine.undo(for: .sorted, .yes(.plan(PlanProposal(category: "x", usual: 1, amount: 1, months: 1)))) == nil,
                   "a sort has no chat Undo")
            expect(ChatEngine.undo(for: .skipped, .skip(.plan(PlanProposal(category: "x", usual: 1, amount: 1, months: 1)))) == nil,
                   "a skip has no Undo")
        }

        // G7-Unavailable: Pearl couldn't answer · Try again asks the same again.
        do {
            let w = FakeWriter()
            let e = ChatEngine(brain: BrokenBrain(), reader: ChatReader(DownReader()),
                               executor: ChatExecutor(writer: w), allowsPlans: true)
            await e.send("What did I spend at Costco this year?")
            if case .failed(let said) = e.screen {
                expect(said == "What did I spend at Costco this year?", "her words stay")
            } else { expect(false, "couldn't answer: \(e.screen)") }
            expect(ChatWords.failed == "Pearl couldn’t answer that. Try again.", "G7 words")
            await e.retry()
            if case .failed = e.screen {} else { expect(false, "Try again asked again") }
            expect(w.writes.isEmpty, "failing writes nothing")
        }

        // Nothing waiting: the starters.
        do {
            let r = server(suggest: false), w = FakeWriter()
            let e = engine(r, w)
            await e.open()
            if case .start = e.screen {} else { expect(false, "PC-03 when nothing waits") }
        }

        // 2026-11-15, speed. Opening: the model loads, and the cards come in
        // GET /api/chat's own reply, one read.
        do {
            let r = server(suggest: true, trips: true), w = FakeWriter()
            r.replies["api/chat"] = """
            {"suggest": true, "categories": ["Dining"], "people": ["Jo"], "today": "2026-11-15",
             "asks": {"patterns": [], "trips": [\(trip)]}}
            """
            let b = SlowBrain { _ = try await $0.trips() }
            let e = engine(r, w, brain: b)
            await e.open()
            expect(b.prewarmed == 1, "opening prewarms the model")
            expect(r.reads.map(\.0) == ["api/chat"], "one read to open: \(r.reads.map(\.0))")
            expect(deck(e)?.cards.count == 1, "the trip card from the one reply")
            // Was this a trip? uses the cards already read, not another trip to the server.
            e.restart()
            await e.pick(.trips)
            expect(!r.reads.map(\.0).contains("api/chat/asks"), "trips from what opening read")
            // A Yes changes what's waiting: the next ask reads again.
            w.replies["api/trips/asks/2026-03-04:2026-03-09/yes"] = """
            {"ok": true, "trip": {"id": "tr1", "name": "Trip to Montréal", "ids": ["t1"], "start": "2026-03-04",
             "end": "2026-03-09", "count": 23, "totals": [{"currency": "CAD", "amount": 1284.6}]}}
            """
            if let card = deck(e)?.current {
                await e.decide(.yes(card), tap: UserTap("yes"))
            } else {
                expect(false, "the trip card again")
            }
            expect(w.writes.count == 1, "the Yes was sent")
            await e.pick(.trips)
            expect(r.reads.map(\.0).contains("api/chat/asks"), "after a Yes, asked again")
        }
        // An old server without asks in GET /api/chat: asked for them, as before.
        do {
            let r = server(suggest: true, trips: true), w = FakeWriter()
            let e = engine(r, w)
            await e.open()
            expect(r.reads.map(\.0) == ["api/chat", "api/chat/asks"], "old server: two reads")
            expect(deck(e)?.cards.count == 1, "old server: the trip card")
        }
        // Cards show when the tool finds them, while the model still writes;
        // its echo comes in once it's done.
        do {
            let r = server(), w = FakeWriter()
            r.first["api/chat/tell"] = [tellNone]
            let b = SlowBrain(echo: "You said you went out Saturday.") {
                _ = try await $0.tell("went out Saturday", category: "Dining")
            }
            let e = engine(r, w, brain: b)
            var early: Deck?
            b.look = { early = deck(e) }
            await e.send("went out Saturday")
            expect(early?.cards.count == 3, "the cards are up before the model is done")
            expect(early?.echo == ChatWords.echo("went out Saturday") || early?.echo != nil, "with the server's echo meanwhile")
            expect(deck(e)?.echo == "You said you went out Saturday.", "then the model's echo")
            expect(w.writes.isEmpty, "showing early writes nothing")
        }
        // Words stream onto PC-04 as they come.
        do {
            let r = server(), w = FakeWriter()
            r.first["api/chat/spending"] = [spendingNone]
            let b = SlowBrain(words: ["You spent", "You spent $286 on Dining."]) {
                _ = try await $0.spending("how much on dining?", category: "Dining")
            }
            let e = engine(r, w, brain: b)
            var midway: String?
            b.look = { if case .reply(_, let text, _, _) = e.screen { midway = text } }
            await e.send("how much on dining?")
            expect(midway == "You spent $286 on Dining.", "the words so far: \(midway ?? "none")")
            if case .reply(_, let text, let a, _) = e.screen {
                expect(text == "You spent $286 on Dining." && a?.total == 286, "then the whole answer")
            } else { expect(false, "PC-04 after streaming") }
        }
        // The model fails after its tool found something: that stands, and
        // the server isn't asked twice.
        do {
            let r = server(), w = FakeWriter()
            r.first["api/chat/spending"] = [spendingNone]
            let b = SlowBrain(fail: true) { _ = try await $0.spending("how much on dining?", category: "Dining") }
            let e = engine(r, w, brain: b)
            await e.send("how much on dining?")
            expect(r.reads.filter { $0.0 == "api/chat/spending" }.count == 2, "the server's reading, then the model's")
            if case .reply(_, let text, _, _) = e.screen {
                expect(text == "You spent $286 on Dining in October, $72 more than usual.", "the server's line")
            } else { expect(false, "PC-04 from what the tool found") }
        }

        // Simple questions skip the model: the starters, and words the server
        // could read. One read each, no model.
        do {
            let r = server(), w = FakeWriter()
            var asked = 0
            let b = SlowBrain { _ in asked += 1 }
            let e = engine(r, w, brain: b)
            await e.pick(.subscriptions)
            await e.send("how much on dining?")
            e.restart()
            await e.send("went out with friends Saturday")
            expect(asked == 0, "the model wasn't asked: \(asked)")
            expect(r.reads.map(\.0) == ["api/chat/subscriptions", "api/chat/spending", "api/chat/tell"],
                   "one read each: \(r.reads.map(\.0))")
            expect(deck(e)?.cards.count == 3, "the told guesses")
            expect(deck(e)?.echo == ChatWords.echo("went out with friends Saturday"), "the server's echo")
            // The same question again in this chat: no trip to the server.
            e.restart()
            await e.send("how much on dining?")
            expect(r.reads.filter { $0.0 == "api/chat/spending" }.count == 1, "asked again: from the chat's memory")
            if case .reply(_, let text, let a, _) = e.screen {
                expect(text == "You spent $286 on Dining in October, $72 more than usual." && a?.total == 286,
                       "the server's answer")
            } else { expect(false, "PC-04") }
        }
        // Words the server can't read: then the model.
        do {
            let r = server(), w = FakeWriter()
            r.first["api/chat/spending"] = [spendingNone]
            var asked = 0
            let b = SlowBrain(words: ["You spent $286 on Dining."]) {
                asked += 1
                _ = try await $0.spending("what about eating out", category: "Dining")
            }
            let e = engine(r, w, brain: b)
            await e.send("what about eating out?")
            expect(asked == 1, "the model, once")
        }

        // ── Ask Pearl (THL-308): CloudBrain, on a fake server stream ──────
        expect(CloudBrain(asker: FakeAsker([])).isModel && CloudBrain(asker: FakeAsker([])).asksFirst,
               "CloudBrain is a model, asked first")
        expect(!ScriptedBrain().asksFirst, "the scripted brain isn't asked first")
        do {
            // PC-22: the step, the fact whole, the words, a suggestion; no write.
            let r = server(), w = FakeWriter()
            let asker = FakeAsker(["{\"type\": \"step\", \"text\": \"Looking at November…\"}", monthFact,
                                   "{\"type\": \"text\", \"text\": \"You’ve spent $1,284 \"}",
                                   "{\"type\": \"text\", \"text\": \"so far in November.\"}",
                                   suggestion, "{\"type\": \"done\"}"])
            let e = engine(r, w, brain: CloudBrain(asker: asker))
            await e.send("How\u{2019}s this month going?")
            let a = answer(e)
            expect(a != nil, "an answer screen")
            expect(a?.text == "You\u{2019}ve spent $1,284 so far in November.", "the words, whole")
            expect(a?.found.month?.spent == 1284 && a?.found.month?.usualByNow == 1090, "the month fact")
            expect(a?.suggestion?.open == "category" && a?.suggestion?.category == "Dining", "the suggestion opens a screen")
            expect(a?.simple == nil && a?.streaming == false, "no quiet line, done streaming")
            expect(asker.asked == ["How\u{2019}s this month going?"], "asked the server once")
            expect(w.writes.isEmpty, "Ask Pearl never writes")
            expect(r.reads.allSatisfy { !$0.0.hasPrefix("api/chat/") }, "no scripted read when the server answered")
        }
        do {
            // A reset drops a preamble; the server's own words replace them.
            let r = server(), w = FakeWriter()
            let asker = FakeAsker(["{\"type\": \"text\", \"text\": \"Let me check.\"}", "{\"type\": \"reset\"}",
                                   cardsFact, "{\"type\": \"words\", \"text\": \"Two cards.\"}"])
            let e = engine(r, w, brain: CloudBrain(asker: asker))
            await e.send("When are my cards due?")
            expect(answer(e)?.text == "Two cards.", "reset and words")
            expect(answer(e)?.found.cards?.cards.map(\.state) == ["ok", "near"], "cards with their states")
        }
        do {
            // PC-23: one quiet line per chat past the cap.
            let r = server(), w = FakeWriter()
            let asker = FakeAsker(["{\"type\": \"simple\", \"until\": \"December 1\"}", cardsFact,
                                   "{\"type\": \"words\", \"text\": \"Two cards.\"}"])
            let e = engine(r, w, brain: CloudBrain(asker: asker))
            await e.send("When are my cards due?")
            expect(answer(e)?.simple == "December 1", "the quiet line, the first time")
            expect(ChatWords.simple("December 1") == "Pearl\u{2019}s keeping answers simple until December 1.",
                   "the quiet line's words")
            await e.send("When are my cards due?")
            expect(answer(e) != nil && answer(e)?.simple == nil, "not again in the same chat")
            await e.newChat()
            await e.send("When are my cards due?")
            expect(answer(e)?.simple == "December 1", "a new chat says it again")
            let words = ChatWords.simple("December 1").lowercased()
            expect(!words.contains("$") && !words.contains("token") && !words.contains("limit"), "no dollars, tokens or limit")
        }
        do {
            // PC-23: couldn't answer.
            let r = server(), w = FakeWriter()
            let e = engine(r, w, brain: CloudBrain(asker: FakeAsker(["{\"type\": \"couldnt\"}"])))
            await e.send("Can I afford a trip to Lisbon?")
            if case .couldnt(let said) = e.screen { expect(said == "Can I afford a trip to Lisbon?", "her words stay") }
            else { expect(false, "couldn't answer") }
        }
        do {
            // PC-23: offline. Nothing is asked; the words wait; the screen stays.
            let r = server(), w = FakeWriter()
            let asker = FakeAsker([])
            let e = engine(r, w, brain: CloudBrain(asker: asker))
            e.isOnline = { false }
            await e.send("How\u{2019}s this month going?")
            expect(asker.asked.isEmpty, "offline: nothing sent")
            expect(e.waiting == "How\u{2019}s this month going?", "offline: the words wait")
            if case .start = e.screen {} else { expect(false, "offline: the chat stays") }
        }
        do {
            // The connection drops part way: back to the screen before, words held.
            let r = server(), w = FakeWriter()
            let e = engine(r, w, brain: CloudBrain(asker: FakeAsker([], fail: ChatOffline())))
            await e.send("When are my cards due?")
            expect(e.waiting == "When are my cards due?", "dropped: the words wait")
            if case .start = e.screen {} else { expect(false, "dropped: the chat stays") }
        }
        do {
            // Turned off on another phone: the server refuses and the tab shows off.
            let r = server(), w = FakeWriter()
            let e = engine(r, w, brain: CloudBrain(asker: FakeAsker([], fail: ChatAskOff())))
            e.askState = "on"
            await e.send("When are my cards due?")
            expect(e.askState == "off", "refused: Ask Pearl is off")
        }
        do {
            // No server answer at all: its own reading (the scripted route), as before.
            let r = server(), w = FakeWriter()
            struct Broken: Error {}
            let e = engine(r, w, brain: CloudBrain(asker: FakeAsker([], fail: Broken())))
            await e.send("What did I spend eating out in October?")
            if case .reply(_, let text, _, _) = e.screen {
                expect(text.hasPrefix("You spent $286"), "fallback: the server's spending line")
            } else { expect(false, "fallback: the scripted reading") }
            expect(w.writes.isEmpty, "fallback: still no write")
        }
        do {
            // Tell Pearl what you did still reads the server's own way first.
            let r = server(), w = FakeWriter()
            let asker = FakeAsker([])
            let e = engine(r, w, brain: CloudBrain(asker: asker))
            e.mode = .tell
            await e.send("went out with friends Saturday")
            expect(deck(e) != nil && asker.asked.isEmpty, "tell: cards from /api/chat/tell, Claude not asked")
        }
        do {
            // GET /api/chat's Ask Pearl state and the four questions.
            let r = server()
            r.replies["api/chat"] = """
            {"suggest": false, "categories": [], "people": [], "today": "2026-11-27", "ask": "unasked",
             "examples": ["How’s this month going?", "How much at Loblaws this year?", "When are my cards due?", "Any subscriptions I forgot?"]}
            """
            let e = engine(r, FakeWriter(), brain: CloudBrain(asker: FakeAsker([])))
            await e.open()
            expect(e.askState == "unasked" && e.examples.count == 4, "open: Ask Pearl's state and examples")
            let old = engine(server(), FakeWriter())
            await old.open()
            expect(old.askState == "unasked", "an older server: not asked yet")
        }
        expect(AskEvent.parse("not json") == nil, "a line it can't read is left out")

        print("\(checks) checks, \(failures) failed")
        print(failures == 0 ? "OK" : "FAIL")
        exit(failures == 0 ? 0 : 1)
    }
}
