import Foundation

/// Money, dates and months, worded the way Pearl's web app words them.
enum Format {
    private static let money: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = "CAD"
        f.currencySymbol = "$"
        f.locale = Locale(identifier: "en_CA")
        return f
    }()

    private static let wholeMoney: NumberFormatter = {
        let f = NumberFormatter()
        f.numberStyle = .currency
        f.currencyCode = "CAD"
        f.currencySymbol = "$"
        f.locale = Locale(identifier: "en_CA")
        f.maximumFractionDigits = 0
        return f
    }()

    /// "$1,234.56".
    /// TEST-14: what VoiceOver says for "−$127.50" or "+$42.50": the U+2212
    /// minus isn't read, so the audit called the label not human-readable.
    static func spoken(_ shown: String) -> String {
        if shown.hasPrefix("\u{2212}") || shown.hasPrefix("-") { return "spent " + shown.dropFirst() }
        if shown.hasPrefix("+") { return "came in " + shown.dropFirst() }
        return shown
    }

    static func amount(_ value: Double) -> String {
        money.string(from: NSNumber(value: abs(value))) ?? "$\(abs(value))"
    }

    /// "$1,235", for totals.
    static func whole(_ value: Double) -> String {
        wholeMoney.string(from: NSNumber(value: abs(value))) ?? "$\(Int(abs(value)))"
    }

    /// A total in each billing currency (trips; Pearl converts nothing):
    /// "$1,284.60" in one, "$1,240 CAD + $310 USD" in several (TR-02m), the
    /// biggest first as the server sends them.
    static func totals(_ parts: [(currency: String, amount: Double)]) -> String {
        if parts.count <= 1 { return amount(parts.first?.amount ?? 0) }
        return parts.map { "\(whole($0.amount)) \($0.currency)" }.joined(separator: " + ")
    }

    /// "Mar 4–9", "Oct 29 – Nov 2" (TR-10b), "Mar 4" (a trip's dates).
    static func span(_ start: String, _ end: String) -> String {
        guard let a = date(start), let b = date(end) else { return start }
        if start.prefix(10) == end.prefix(10) { return shortDay.string(from: a) }
        let sameMonth = start.prefix(7) == end.prefix(7)
        return sameMonth ? shortDay.string(from: a) + "\u{2013}" + dayOnly.string(from: b)
            : shortDay.string(from: a) + " \u{2013} " + shortDay.string(from: b)
    }

    /// What VoiceOver reads for `span`: "March 4 to 9", "October 29 to
    /// November 2", "March 4" (TR-17, TR-18; note 1329:69536).
    static func spokenSpan(_ start: String, _ end: String) -> String {
        guard let a = date(start), let b = date(end) else { return start }
        if start.prefix(10) == end.prefix(10) { return monthDayFormat.string(from: a) }
        let sameMonth = start.prefix(7) == end.prefix(7)
        return monthDayFormat.string(from: a) + " to "
            + (sameMonth ? dayOnly.string(from: b) : monthDayFormat.string(from: b))
    }

    private static let dayOnly = formatter("d")

    /// "2026-03-04" moved by whole days ("2026-03-01" for −3): TR-11's window.
    static func shiftDay(_ day: String, by days: Int) -> String {
        guard let d = iso.date(from: String(day.prefix(10))) else { return day }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        return iso.string(from: cal.date(byAdding: .day, value: days, to: d) ?? d)
    }

    /// "+$5,850.00" for money in, "$22.57" for money out.
    static func signed(_ value: Double, inflow: Bool) -> String {
        inflow ? "+" + amount(value) : amount(value)
    }

    private static let iso: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = "yyyy-MM-dd"
        return f
    }()

    private static func formatter(_ pattern: String) -> DateFormatter {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_CA")
        f.timeZone = TimeZone(identifier: "UTC")
        f.dateFormat = pattern
        return f
    }

    private static let longDay = formatter("EEEE, MMMM d")
    private static let shortDay = formatter("MMM d")
    private static let monthDayFormat = formatter("MMMM d")
    private static let monthYear = formatter("MMMM yyyy")
    private static let monthOnly = formatter("MMMM")

    static func date(_ iso: String) -> Date? {
        Format.iso.date(from: String(iso.prefix(10)))
    }

    private static let agreedDayFormat: DateFormatter = {
        let f = DateFormatter()
        f.calendar = Calendar(identifier: .gregorian)
        f.locale = Locale(identifier: "en_US_POSIX")
        f.dateFormat = "MMM d, yyyy"
        return f
    }()

    /// "Oct 2, 2026", from a consent's time in seconds, on this iPhone's clock.
    static func agreedDay(_ seconds: Double) -> String {
        agreedDayFormat.string(from: Date(timeIntervalSince1970: seconds))
    }

    /// "Wednesday, October 14".
    static func day(_ iso: String) -> String {
        date(iso).map { longDay.string(from: $0) } ?? iso
    }

    /// "Oct 14".
    static func short(_ iso: String) -> String {
        date(iso).map { shortDay.string(from: $0) } ?? iso
    }

    /// "November 2", for VoiceOver (S-35a).
    static func monthDay(_ iso: String) -> String {
        date(iso).map { monthDayFormat.string(from: $0) } ?? iso
    }

    /// "October 2026" from "2026-10".
    static func month(_ ym: String) -> String {
        date(ym + "-01").map { monthYear.string(from: $0) } ?? ym
    }

    /// "October" from "2026-10".
    static func monthName(_ ym: String) -> String {
        date(ym + "-01").map { monthOnly.string(from: $0) } ?? ym
    }

    private static let weekday = formatter("EEEE")
    private static let shortWeekdayDay = formatter("EEE, MMM d")
    private static let monthDay = formatter("MMMM d")
    private static let monthDayYear = formatter("MMMM d, yyyy")

    /// The UTC calendar `dayParts` counts in, made once: making one per
    /// call cost every row on every pass (perf rehaul, 2026-11-19).
    private static let utc: Calendar = {
        var c = Calendar(identifier: .gregorian)
        c.timeZone = TimeZone(identifier: "UTC")!
        return c
    }()

    /// `dayParts`' answers by date string, good for one local day: a list
    /// of a thousand rows asks for each row's day on every pass, and
    /// `relativeDay` and `dayHeader` ask again on top.
    private static var dayPartsCache: (day: DateComponents?, parts: [String: (name: String, date: String)]) = (nil, [:])
    private static let dayPartsLock = NSLock()

    /// A day in the list, as the web heads it: "Today" · "Thu, Oct 29",
    /// "Monday" · "Oct 26", or "October 20" · "Tuesday".
    static func dayParts(_ iso: String, now: Date = Date()) -> (name: String, date: String) {
        let local = Calendar.current.dateComponents([.year, .month, .day], from: now)
        dayPartsLock.lock()
        defer { dayPartsLock.unlock() }
        if dayPartsCache.day != local { dayPartsCache = (local, [:]) }
        if let hit = dayPartsCache.parts[iso] { return hit }
        let parts = dayParts(iso, local: local, now: now)
        dayPartsCache.parts[iso] = parts
        return parts
    }

    private static func dayParts(_ iso: String, local: DateComponents, now: Date) -> (name: String, date: String) {
        guard let day = date(iso) else { return (iso, "") }
        let today = utc.date(from: local) ?? now
        let ago = utc.dateComponents([.day], from: day, to: today).day ?? 0
        switch ago {
        case 0: return ("Today", shortWeekdayDay.string(from: day))
        case 1: return ("Yesterday", shortWeekdayDay.string(from: day))
        case 2..<7: return (weekday.string(from: day), shortDay.string(from: day))
        default:
            let sameYear = utc.component(.year, from: day) == local.year
            return ((sameYear ? monthDay : monthDayYear).string(from: day), weekday.string(from: day))
        }
    }

    /// "Good morning" / "Good afternoon" / "Good evening".
    static func greeting(now: Date = Date()) -> String {
        let hour = Calendar.current.component(.hour, from: now)
        if hour < 12 { return "Good morning" }
        if hour < 18 { return "Good afternoon" }
        return "Good evening"
    }

    /// "−$24.80" out, "+$40.00" in: signed even when it doesn't count.
    static func money(_ t: Transaction) -> String {
        (t.inflow ? "+" : "\u{2212}") + amount(t.amount)
    }

    /// "anastasia papadimitriou" → "Anastasia": the first name, capitalised.
    /// The people she shares an account with are named once per page, and
    /// by first name (less text, 2026-11-20).
    static func shortName(_ name: String) -> String {
        let first = name.split(separator: " ").first.map(String.init) ?? name
        return first.prefix(1).uppercased() + first.dropFirst()
    }

    /// "Anastasia", "Anastasia and Sam": `andList` of `shortName`s.
    static func shortList(_ names: [String]) -> String {
        andList(names.map(shortName))
    }

    /// "Loblaws", "Loblaws and Pizza Nova", "Loblaws, Costco and Pizza Nova".
    static func andList(_ names: [String]) -> String {
        names.count <= 2 ? names.joined(separator: " and ")
            : names.dropLast().joined(separator: ", ") + " and " + (names.last ?? "")
    }

    /// "$86" when whole, "$86.50" when not.
    static func compact(_ value: Double) -> String {
        abs(value.rounded() - value) < 0.005 ? whole(value) : amount(value)
    }

    /// "Today", "Yesterday", "Nov 12".
    static func relativeDay(_ iso: String, now: Date = Date()) -> String {
        let name = dayParts(iso, now: now).name
        return name == "Today" || name == "Yesterday" ? name : short(iso)
    }

    /// T-01r's day header: "Today", "Yesterday", "Wed, Nov 12".
    static func dayHeader(_ iso: String, now: Date = Date()) -> String {
        let name = dayParts(iso, now: now).name
        return name == "Today" || name == "Yesterday" ? name : weekdayDay(iso)
    }

    /// "Wed, Nov 11".
    static func weekdayDay(_ iso: String) -> String {
        date(iso).map { shortWeekdayDay.string(from: $0) } ?? iso
    }

    /// "2026-11", this month here.
    static func thisMonth(now: Date = Date()) -> String {
        let c = Calendar.current.dateComponents([.year, .month], from: now)
        return String(format: "%04d-%02d", c.year ?? 0, c.month ?? 0)
    }

    /// "Last updated this morning.", "Last updated Nov 12."
    static func lastUpdated(_ stamp: String?, now: Date = Date()) -> String {
        guard let stamp = stamp, !stamp.isEmpty else { return "It needs you to sign in again." }
        let day = String(stamp.prefix(10))
        let today = String(format: "%04d-%02d-%02d", Calendar.current.component(.year, from: now),
                           Calendar.current.component(.month, from: now), Calendar.current.component(.day, from: now))
        guard day == today else { return "Last updated \(short(day))." }
        let hour = Int(stamp.dropFirst(11).prefix(2)) ?? Calendar.current.component(.hour, from: now)
        return hour < 12 ? "Last updated this morning." : hour < 18 ? "Last updated this afternoon." : "Last updated this evening."
    }

    /// "Every 2 weeks" for a pay's cadence (Income and bills).
    static func cadence(_ c: String) -> String {
        switch c {
        case "weekly": return "Every week"
        case "biweekly": return "Every 2 weeks"
        case "semimonthly": return "Twice a month"
        case "monthly": return "Monthly"
        default: return "It changes"
        }
    }

    /// The next pay after this one, from today on: "2026-11-21".
    static func nextPay(after iso: String, cadence: String, now: Date = Date()) -> String? {
        guard var day = date(iso) else { return nil }
        var cal = Calendar(identifier: .gregorian)
        cal.timeZone = TimeZone(identifier: "UTC")!
        let today = cal.startOfDay(for: now)
        func step(_ d: Date) -> Date? {
            switch cadence {
            case "weekly": return cal.date(byAdding: .day, value: 7, to: d)
            case "biweekly": return cal.date(byAdding: .day, value: 14, to: d)
            case "semimonthly": return cal.date(byAdding: .day, value: 15, to: d)
            case "monthly": return cal.date(byAdding: .month, value: 1, to: d)
            default: return nil
            }
        }
        repeat {
            guard let next = step(day) else { return nil }
            day = next
        } while day <= today
        return Format.iso.string(from: day)
    }

    /// A calendar day as midnight here, for a date picker.
    static func localDay(_ iso: String) -> Date? {
        let parts = iso.prefix(10).split(separator: "-").compactMap { Int($0) }
        guard parts.count == 3 else { return nil }
        return Calendar.current.date(from: DateComponents(year: parts[0], month: parts[1], day: parts[2]))
    }

    /// "2026-11-06" from a date picker's day, here.
    static func isoDay(_ d: Date) -> String {
        let c = Calendar.current.dateComponents([.year, .month, .day], from: d)
        return String(format: "%04d-%02d-%02d", c.year ?? 0, c.month ?? 0, c.day ?? 0)
    }
}
