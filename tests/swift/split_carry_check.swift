// Checks ios/Pearl/Views/Transactions/SplitCarry.swift on its own
// (tests/test_split_carry.py compiles the two together). TEST-36, 2026-11-19.
import Foundation

var failures = 0
func check(_ got: [String: String], _ want: [String: String], _ what: String) {
    if got != want { failures += 1; print("FAIL: \(what): \(got)") }
}

let me = "\u{0}me"
// $60.00 each with Sam (TEST-36): Amounts keeps Sam at $60, hers gives way.
let even = [(key: me, cents: 6000), (key: "Sam", cents: 6000)]
check(SplitCarry.values(even, to: "amount", me: me), ["Sam": "60.00"], "50/50 on Amounts")
check(SplitCarry.values(even, to: "percent", me: me), ["Sam": "50", me: "50"], "50/50 on %")
check(SplitCarry.values(even, to: "shares", me: me), ["Sam": "1", me: "1"], "50/50 on Shares")

// $80 and $40: 2 and 1 shares; 66.67% and 33.33%.
let twoOne = [(key: me, cents: 8000), (key: "Sam", cents: 4000)]
check(SplitCarry.values(twoOne, to: "shares", me: me), ["Sam": "1", me: "2"], "2:1 on Shares")
check(SplitCarry.values(twoOne, to: "percent", me: me), ["Sam": "33.33", me: "66.67"], "2:1 on %")
check(SplitCarry.values(twoOne, to: "amount", me: me), ["Sam": "40.00"], "2:1 on Amounts")

// Three ways of $100.00 with the odd cent: 1, 1 and 1.
let thirds = [(key: me, cents: 3334), (key: "Sam", cents: 3333), (key: "Priya", cents: 3333)]
check(SplitCarry.values(thirds, to: "shares", me: me), ["Sam": "1", "Priya": "1", me: "1"], "thirds on Shares")
check(SplitCarry.values(thirds, to: "percent", me: me), ["Sam": "33.33", "Priya": "33.33", me: "33.34"], "thirds on %")

// Without her: every row is typed.
let them = [(key: "Sam", cents: 2525), (key: "Priya", cents: 7575)]
check(SplitCarry.values(them, to: "amount", me: nil), ["Sam": "25.25", "Priya": "75.75"], "without her on Amounts")
check(SplitCarry.values(them, to: "shares", me: nil), ["Sam": "1", "Priya": "3"], "without her on Shares")

// Odd ratios: against the smallest share, to two places.
let odd = [(key: me, cents: 4206), (key: "Sam", cents: 8413)]
check(SplitCarry.values(odd, to: "shares", me: me), ["Sam": "2", me: "1"], "odd cents on Shares")

// Nothing to carry: Evenly, Not sure, an empty purchase.
check(SplitCarry.values(even, to: "even", me: me), [:], "Evenly")
check(SplitCarry.values(even, to: "unknown", me: me), [:], "Not sure")
check(SplitCarry.values([(key: me, cents: 0)], to: "amount", me: me), [:], "nothing")

if failures > 0 { exit(1) }
print("OK")
