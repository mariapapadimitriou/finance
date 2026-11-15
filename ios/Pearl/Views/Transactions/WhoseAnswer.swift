import Foundation

/// T-76 Whose was it? (WhoseSheet): which answer the sheet opens on, what
/// "Your part" starts at, and when Save can be tapped. Kept apart from the
/// view, with Foundation only, so it can be checked on its own.
///
/// 2026-11-15: on a joint account set to 50/50, a bill payment showed as all
/// hers, so the sheet opened on Mine with "Your part" empty. Tapping Part of
/// it showed half of it in grey, as a hint, and Save stayed off until she
/// typed a number. Part of it now starts at her share of it, the number the
/// hint showed, so Save works straight away.
enum WhoseAnswer {
    /// "mine", "theirs" or "part", and "Your part" as typed, for a charge of
    /// `full` that counts `mine` as hers. `share` is the percent of it that is
    /// hers: the name's rule, else the account's (AM-04); nil when every
    /// purchase is hers unless she says.
    static func start(mine: Double, full: Double, shareSet: Bool,
                      share: Double?) -> (mode: String, part: String) {
        let theirs = shareSet && mine < 0.005
        let isPart = !theirs && abs(mine - full) >= 0.005
        let mode = theirs ? "theirs" : isPart ? "part" : "mine"
        return (mode, String(format: "%.2f", isPart ? mine : suggested(full: full, share: share)))
    }

    /// Her part when she first picks Part of it: her share of the charge,
    /// or half when there's none.
    static func suggested(full: Double, share: Double?) -> Double {
        ((full * (share ?? 50) / 100) * 100).rounded() / 100
    }

    /// "Your part" as a number: "$1,234.50" reads as 1234.5.
    static func amount(_ typed: String) -> Double? {
        Double(typed.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")
            .trimmingCharacters(in: .whitespaces))
    }

    /// Save is on for Mine and theirs, and for Part of it once her part is
    /// more than nothing and no more than the charge.
    static func ready(mode: String, typed: String, full: Double) -> Bool {
        mode != "part" || (amount(typed).map { $0 > 0 && $0 <= full + 0.005 } ?? false)
    }
}
