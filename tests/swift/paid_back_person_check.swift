// PaidBackPerson (PP-01 then PB-30), checked with swiftc by
// tests/test_paid_back_person.py: the product owner's $30.00 from
// "anastasia papadimitriou" (2026-11-17).
import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if !ok { failures += 1; print("FAIL:", what) }
}

typealias S = PaidBackPerson.Share
let anastasia = [S(person: "Anastasia", owes: 30, date: "2026-10-28"),
                 S(person: "Anastasia", owes: 12.5, date: "2026-11-01")]
let two = anastasia + [S(person: "Sam Lee", owes: 20, date: "2026-10-30")]

// A clear first-name match is PB-30 for her, whatever the case or surname.
check(PaidBackPerson.route(sender: nil, named: "anastasia papadimitriou", shares: two) == .person("Anastasia"),
      "full lower-case name against a first name")
check(PaidBackPerson.route(sender: nil, named: "ANASTASIA", shares: two) == .person("Anastasia"), "case")
check(PaidBackPerson.route(sender: nil, named: "Sam", shares: two) == .person("Sam Lee"), "first name against a full name")

// Pearl already knows: PB-30 straight away.
check(PaidBackPerson.route(sender: "Anastasia", named: "x", shares: two) == .theirs, "sender known")

// Nobody owes her: the purchase list, never an empty PP-01.
check(PaidBackPerson.route(sender: nil, named: "Jordan", shares: []) == .purchases, "no one owes")
check(PaidBackPerson.route(sender: nil, named: "Jordan",
                           shares: [S(person: "Sam", owes: 0, date: "2026-11-01"), S(person: nil, owes: 9, date: "2026-11-01")])
      == .purchases, "paid up or no person")

// Can't tell: PP-01 with everyone who owes her, once each, newest first.
if case .ask(let people) = PaidBackPerson.route(sender: nil, named: "E-Transfer", shares: two) {
    check(people.map(\.name) == ["Anastasia", "Sam Lee"], "PP-01 rows: \(people)")
    check(people.first?.date == "2026-11-01", "newest share's date")
} else {
    check(false, "an unknown name asks")
}
// Two Anastasias: not clear, so ask.
let twins = two + [S(person: "Anastasia K", owes: 5, date: "2026-11-02")]
if case .ask(let people) = PaidBackPerson.route(sender: nil, named: "anastasia papadimitriou", shares: twins) {
    check(!people.isEmpty, "never empty")
} else {
    check(false, "two people with that first name asks")
}

// A load that never answers ends.
let sem = DispatchSemaphore(value: 0)
var timedOut = false
Task {
    do {
        _ = try await withDeadline(0.2) { () async throws -> Int in
            try await Task.sleep(nanoseconds: 5_000_000_000); return 1
        }
    } catch is PaidBackPerson.TimedOut { timedOut = true } catch {}
    sem.signal()
}
sem.wait()
check(timedOut, "deadline")

if failures > 0 { exit(1) }
print("OK")
