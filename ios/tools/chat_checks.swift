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
    var reads: [(String, [String: Any])] = []

    func get<T: Decodable>(_ path: String) async throws -> T {
        reads.append((path, [:]))
        guard let json = replies[path] else { throw URLError(.fileDoesNotExist) }
        return try decode(json)
    }

    func read<T: Decodable>(_ path: String, _ body: [String: Any]) async throws -> T {
        reads.append((path, body))
        guard let json = replies[path] else { throw URLError(.fileDoesNotExist) }
        return try decode(json)
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
}

/// A model that calls every tool it has, whatever she said. It still can't
/// change anything: tools are all it gets.
struct GreedyBrain: PearlBrain {
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
{"nothing": false, "category": "Dining", "usual": 214.0, "pct": 105, "amount": 224.7, "months": 3}
"""

let spending = """
{"nothing": false, "title": "Dining, October", "category": "Dining", "merchant": null, "month": "2026-10",
 "total": 286.0, "usual": 214.0, "count": 4, "rows": [\(brief("p1", "Pai Northern Thai", 120))],
 "line": "You spent $286 on Dining in October, $72 more than usual."}
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
            expect(d.position == "A guess for 3 of 5 from Saturday · 1 of 3", "PC-05 line: \(d.position)")
            expect(d.echo == "You said “went out with friends Saturday”.", "echo fallback: \(d.echo ?? "nil")")
            expect(w.writes.isEmpty, "nothing changes before she taps")
            expect(r.reads.allSatisfy { $0.0.hasPrefix("api/chat") }, "the model's tools read only /api/chat")

            await e.decide(.yes(d.cards[0]), tap: UserTap("yes"))
            expect(w.writes.count == 1, "Yes writes once")
            expect(w.writes.first?.path == "api/transactions/a/mark", "Yes marks the transaction")
            expect(w.writes.first?.body["remember"] as? Bool == false, "a told guess saves no rule")
            expect(w.writes.first?.body["category"] as? String == "Dining", "as she said")
            expect(deck(e)?.position == "2 of 3", "PC-06 line: \(deck(e)?.position ?? "")")

            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            expect(w.writes.count == 1, "Skip on a told guess sends nothing: it stays in Needs a look")

            await e.decide(.yes(deck(e)!.current!), tap: UserTap("yes"))
            if case .sorted(let sorted, let left) = e.screen {
                expect(sorted == 2 && left == 1, "PC-07 counts")
                expect(ChatWords.sortedTitle(sorted: sorted, left: left) == "Sorted 2. 1 left for later.", "PC-07 title")
                expect(ChatWords.sortedBody(left: 2) == "The 2 are in Needs a look. What you told Pearl is forgotten now.",
                       "PC-07 body")
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
            expect(ChatWords.yesSorts("Dining", split: true) == "Yes sorts it as Dining, all yours. To split it, tap Maybe split.",
                   "PC-06 line")
            var sent = false
            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            await e.decide(.held(s, label: "Dining, split with Jo and Sam") { sent = true }, tap: UserTap("yes"))
            expect(sent, "the held split is sent on Yes")
            expect(w.writes.isEmpty, "and by its own page's request, not another")
        }

        // A model that calls every tool still changes nothing.
        do {
            let r = server(), w = FakeWriter()
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
            expect(ChatWords.planQuestion("Dining", p.amount!) == "Make a Dining plan of $225 a month?", "PC-12 question")
            expect(ChatWords.planLead(months: 3) == "Here’s a plan from your last 3 months. Nothing changes until you set it.",
                   "PC-12 lead")
            await e.decide(.skip(.plan(p)), tap: UserTap("not-now"))
            if case .noChange = e.screen {} else { expect(false, "Not now → Okay, nothing changed.") }
            expect(ChatWords.nothingChanged == "Okay, nothing changed.", "Not now's words")
            expect(w.writes.isEmpty, "Not now sends nothing")

            await e.send("Make me a plan for eating out.")
            guard case .plan(_, let p2) = e.screen else { expect(false, "PC-12 again"); return }
            await e.decide(.yes(.plan(p2)), tap: UserTap("set-it"))
            expect(w.writes.count == 1 && w.writes[0].method == "PUT" && w.writes[0].path == "api/category-budgets",
                   "Set it: the budgets endpoint")
            expect(w.writes[0].body["pct"] as? Int == 105, "on the 5% step shown")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.line == "Done. Dining plan set to $225 a month.", "PC-13: \(notes.first?.line ?? "")")
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
            w.replies["api/trips/asks/2026-03-04%3A2026-03-09/yes"] = """
            {"ok": true, "trip": {"id": "tr1", "name": "Trip to Montréal", "ids": ["t1"], "start": "2026-03-04",
             "end": "2026-03-09", "count": 23, "totals": [{"currency": "CAD", "amount": 1284.6}]}}
            """
            let e = engine(r, w)
            await e.pick(.trips)
            guard let d = deck(e), case .trip(let t)? = d.current else { expect(false, "PC-08"); return }
            expect(d.position == "Maybe a trip, \(Format.span(t.start, t.end)) · one card for all 23", "PC-08 line")
            expect(w.writes.isEmpty, "a trip card changes nothing by itself")
            await e.decide(.yes(d.current!), tap: UserTap("yes"))
            expect(w.writes.first?.path == "api/trips/asks/2026-03-04%3A2026-03-09/yes", "Yes: TR-01's endpoint")
            if case .done(_, let notes) = e.screen {
                expect(notes.first?.line == "Done. Trip to Montréal made.", "trip confirmation")
                expect(notes.first?.link == .trip("tr1"), "a link to where it lives")
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
            expect(d.position == ChatWords.patternLine, "PC-09 line")
            await e.decide(.skip(d.current!), tap: UserTap("skip"))
            expect(w.writes.last?.path == "api/pattern-sort/asks/joint:ana/skip", "Skip: AI-18's own skip")
            await e.decide(.skip(deck(e)!.current!), tap: UserTap("skip"))
            expect(w.writes.last?.path == "api/trips/asks/2026-03-04%3A2026-03-09/skip", "Skip: TR-01's own skip")
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

        // Nothing waiting: the starters.
        do {
            let r = server(suggest: false), w = FakeWriter()
            let e = engine(r, w)
            await e.open()
            if case .start = e.screen {} else { expect(false, "PC-03 when nothing waits") }
        }

        print("\(checks) checks, \(failures) failed")
        print(failures == 0 ? "OK" : "FAIL")
        exit(failures == 0 ? 0 : 1)
    }
}
