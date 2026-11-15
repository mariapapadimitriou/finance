import Foundation

/// A transfer between two of her accounts is one line in Transactions, the
/// departure's row, "TD Chequing ··4417 → TD Savings ··2210" (2026-10-22,
/// finance/txlist.collapse_transfers). The phone filters the month itself, by
/// account, category, type and the rest, so filtered to the savings account
/// that line was filtered out, and the arrival, merged into it, showed
/// nowhere: a transfer she marked vanished (2026-11-15).
///
/// The server now sends each merged arrival with the line it went into
/// (`merged_into`). Where a filter keeps the arrival but not its line, the
/// arrival shows as its own row, on its own day, as it would with no pair.
/// With no filter the line is there and nothing changes. Generic and
/// Foundation only, so it can be checked on its own.
enum TransferEnds {
    /// `shown` (newest first, as the server sent it) with each of `merged`
    /// that `keep` keeps and whose line isn't in `shown`, put in by date.
    static func adding<T>(_ merged: [T], to shown: [T], keep: (T) -> Bool,
                          id: (T) -> String, line: (T) -> String?, date: (T) -> String) -> [T] {
        guard !merged.isEmpty else { return shown }
        let here = Set(shown.map(id))
        var out = shown
        for end in merged where keep(end) && !here.contains(line(end) ?? "") && !out.contains(where: { id($0) == id(end) }) {
            // Before the first row from an earlier day, so the day's card is
            // the one it goes in and no day shows twice.
            let day = date(end)
            let at = out.firstIndex { date($0) < day } ?? out.count
            out.insert(end, at: at)
        }
        return out
    }
}
