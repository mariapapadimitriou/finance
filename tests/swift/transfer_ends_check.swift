// Checks ios/Pearl/Views/Transactions/TransferEnds.swift on its own
// (tests/test_transfer_ends.py compiles the two together). 2026-11-15.
import Foundation

var failures = 0
func check(_ ok: Bool, _ what: String) {
    if !ok { failures += 1; print("FAIL: \(what)") }
}

struct Row { let id, date, account: String; var label = "Transfer"; var line: String? = nil }

// The month as the server sends it, newest first: the transfer is one line,
// Chequing's, on the 1st; its arrival into Savings, on the 2nd, is merged.
let month = [Row(id: "coffee", date: "2026-11-03", account: "sav", label: "Dining"),
             Row(id: "grocer", date: "2026-11-02", account: "chq", label: "Groceries"),
             Row(id: "line", date: "2026-11-01", account: "chq"),
             Row(id: "rent", date: "2026-10-31", account: "sav", label: "Rent")]
let merged = [Row(id: "arrival", date: "2026-11-02", account: "sav", line: "line")]

func view(_ keep: @escaping (Row) -> Bool) -> [String] {
    TransferEnds.adding(merged, to: month.filter(keep), keep: keep,
                        id: { $0.id }, line: { $0.line }, date: { $0.date }).map(\.id)
}

// No filter: today's single line, nothing added.
check(view { _ in true } == ["coffee", "grocer", "line", "rent"], "no filter: \(view { _ in true })")

// Filtered to Savings: the arrival shows, on its own day (the 2nd), in order.
let sav = view { $0.account == "sav" }
check(sav == ["coffee", "arrival", "rent"], "Savings: \(sav)")

// Filtered to Chequing: the line, as today; the arrival isn't added.
check(view { $0.account == "chq" } == ["grocer", "line"], "Chequing")

// Both accounts: the line, once.
check(view { ["chq", "sav"].contains($0.account) } == ["coffee", "grocer", "line", "rent"], "both")

// A category the arrival has and the line hasn't.
let saved = [Row(id: "arrival", date: "2026-11-02", account: "sav", label: "Saved", line: "line")]
let bySaved = TransferEnds.adding(saved, to: month.filter { $0.label == "Saved" }, keep: { $0.label == "Saved" },
                                  id: { $0.id }, line: { $0.line }, date: { $0.date }).map(\.id)
check(bySaved == ["arrival"], "category Saved: \(bySaved)")

// A filter that keeps neither: nothing.
check(view { $0.account == "card" } == [], "card")

// Same day as the last row, or after every row: at the end of its day.
let late = TransferEnds.adding([Row(id: "a", date: "2026-10-30", account: "sav", line: "line")],
                               to: [Row(id: "b", date: "2026-11-01", account: "sav")], keep: { _ in true },
                               id: { $0.id }, line: { $0.line }, date: { $0.date }).map(\.id)
check(late == ["b", "a"], "oldest last: \(late)")
let first = TransferEnds.adding([Row(id: "a", date: "2026-11-05", account: "sav", line: "line")],
                                to: [Row(id: "b", date: "2026-11-01", account: "sav")], keep: { _ in true },
                                id: { $0.id }, line: { $0.line }, date: { $0.date }).map(\.id)
check(first == ["a", "b"], "newest first: \(first)")

// Never twice.
let twice = TransferEnds.adding(merged + merged, to: [], keep: { _ in true },
                                id: { $0.id }, line: { $0.line }, date: { $0.date }).map(\.id)
check(twice == ["arrival"], "once: \(twice)")

if failures > 0 { exit(1) }
print("ok")
