import Foundation

/// Paid back › A person from money Pearl can't put a name to (PP-01 then
/// PB-30, 2026-11-16): where it goes. Foundation only, so swiftc checks it
/// on its own (tests/test_paid_back_person.py).
///
/// 2026-11-17 (the product owner's $30.00 from "anastasia papadimitriou"):
/// PP-01 opened with no one in it over a spinner that never ended. Now it
/// is never empty, and a name that is clearly one of hers isn't asked about.
///
/// 2026-11-18 (after #380): someone who owes her nothing still gets PB-30,
/// with OTHER PURCHASES only, instead of the old purchase list (PB-15 /
/// S-09); with no one owing her and no name, T-14 Who sent this? first.
enum PaidBackPerson {
    /// One share someone owes her (…/owing's items).
    struct Share: Hashable {
        let person: String?
        let owes: Double
        let date: String
    }

    /// PP-01's row: who owes her, and the date of their newest open share
    /// ("Last split Oct 2").
    struct Ower: Hashable {
        let name: String
        let date: String
    }

    enum Route: Equatable {
        /// Pearl knows who sent it: PB-30 for them.
        case theirs
        /// The bank's name is clearly this one person on her splits: PB-30
        /// for them, without asking.
        case person(String)
        /// PP-01 with only these people. Never empty.
        case ask([Ower])
        /// Pearl knows who, and they owe her nothing: PB-30 for them with
        /// OTHER PURCHASES only (no "{NAME}'S SHARE").
        case others(String)
        /// No one owes her and Pearl can't name who sent it: T-14 Who sent
        /// this?, then `others` for the name she gives.
        case whoSent
    }

    /// Everyone who owes her, once each, newest share first.
    static func owers(_ shares: [Share]) -> [Ower] {
        var out: [Ower] = []
        for s in shares.sorted(by: { $0.date > $1.date }) {
            guard let p = s.person, !p.isEmpty, s.owes >= 0.005, !out.contains(where: { $0.name == p }) else { continue }
            out.append(Ower(name: p, date: s.date))
        }
        return out
    }

    /// `sender`: who …/owing says sent it (only ever someone who owes her).
    /// `known`: who the caller already knows it was: a picked person, PQ-03's
    /// tile, the joint account's other owner, or T-14's answer.
    /// `named`: the name the money shows ("anastasia papadimitriou"), matched
    /// to her people when the server couldn't: the same first name, any case,
    /// a full name against a first name, and only when it fits exactly one.
    /// `notOnSplits`: the name …/owing reads off the money when it's on none
    /// of her splits (`named` in its reply).
    static func route(sender: String?, known: String? = nil, named: String?, notOnSplits: String? = nil,
                      shares: [Share]) -> Route {
        if sender != nil { return .theirs }
        // …/owing found no share of theirs, so they owe her nothing.
        if let k = clean(known) { return .others(k) }
        let people = owers(shares)
        if let named = named, let first = firstWord(named) {
            let hits = people.filter { firstWord($0.name) == first }
            if hits.count == 1 { return .person(hits[0].name) }
        }
        if let n = clean(notOnSplits) { return .others(n) }
        return people.isEmpty ? .whoSent : .ask(people)
    }

    private static func clean(_ name: String?) -> String? {
        let n = (name ?? "").split(whereSeparator: \.isWhitespace).joined(separator: " ")
        return n.isEmpty ? nil : n
    }

    struct TimedOut: Error {}

    /// "anastasia papadimitriou" and "Anastasia P." both read "anastasia".
    static func firstWord(_ name: String) -> String? {
        let words = name.lowercased().split { !$0.isLetter && $0 != "'" }
        guard let w = words.first, w.count >= 2 else { return nil }
        return String(w)
    }
}

/// `op`, or `PaidBackPerson.TimedOut` after `seconds`: a load that never
/// answers ends in Try again instead of a spinner (2026-11-17).
func withDeadline<T>(_ seconds: Double, _ op: @escaping () async throws -> T) async throws -> T {
    try await withThrowingTaskGroup(of: T.self) { group in
        group.addTask { try await op() }
        group.addTask {
            try await Task.sleep(nanoseconds: UInt64(seconds * 1_000_000_000))
            throw PaidBackPerson.TimedOut()
        }
        defer { group.cancelAll() }
        guard let first = try await group.next() else { throw PaidBackPerson.TimedOut() }
        return first
    }
}
