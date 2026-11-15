// Checks ios/Pearl/Views/Transactions/WhoseAnswer.swift on its own
// (tests/test_whose_answer.py compiles the two together). 2026-11-15.
import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if !ok { failures += 1; print("FAIL: \(what)") }
}

// The product owner's case: a $140 bill payment on a 50/50 account that
// showed as all hers. Opens on Mine; Part of it starts at $70.00, so Save
// is on as soon as she picks it.
var s = WhoseAnswer.start(mine: 140, full: 140, shareSet: false, share: 50)
check(s.mode == "mine", "opens on Mine when all of it counts")
check(s.part == "70.00", "Part of it starts at her 50%: \(s.part)")
check(WhoseAnswer.ready(mode: "part", typed: s.part, full: 140), "Save on after switching to Part of it")

// The same payment once the server shows her half: opens on Part of it.
s = WhoseAnswer.start(mine: 70, full: 140, shareSet: false, share: 50)
check(s.mode == "part" && s.part == "70.00", "opens on Part of it at $70.00")
check(WhoseAnswer.ready(mode: s.mode, typed: s.part, full: 140), "Save on")

// An account with no share: half, as the hint always said.
s = WhoseAnswer.start(mine: 81.25, full: 81.25, shareSet: false, share: nil)
check(s.part == "40.63" || s.part == "40.62", "half when there's no share: \(s.part)")
check(WhoseAnswer.ready(mode: "part", typed: s.part, full: 81.25), "Save on with half")

// A 60% account.
check(WhoseAnswer.suggested(full: 200, share: 60) == 120, "60% of 200")

// Theirs.
s = WhoseAnswer.start(mine: 0, full: 50, shareSet: true, share: nil)
check(s.mode == "theirs", "theirs when she said none of it")
check(WhoseAnswer.ready(mode: "theirs", typed: "", full: 50), "Save on for theirs")

// What she types.
check(!WhoseAnswer.ready(mode: "part", typed: "", full: 50), "empty part: Save off")
check(!WhoseAnswer.ready(mode: "part", typed: "0", full: 50), "nothing: Save off")
check(!WhoseAnswer.ready(mode: "part", typed: "60", full: 50), "more than the charge: Save off")
check(WhoseAnswer.ready(mode: "part", typed: "$1,234.50", full: 2000), "$ and , are fine")
check(WhoseAnswer.ready(mode: "part", typed: "50", full: 50), "all of it as a part is fine")
check(WhoseAnswer.amount(" 12.5 ") == 12.5, "spaces trimmed")

if failures > 0 { exit(1) }
print("ok")
