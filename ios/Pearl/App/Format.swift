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
    static func amount(_ value: Double) -> String {
        money.string(from: NSNumber(value: abs(value))) ?? "$\(abs(value))"
    }

    /// "$1,235", for totals.
    static func whole(_ value: Double) -> String {
        wholeMoney.string(from: NSNumber(value: abs(value))) ?? "$\(Int(abs(value)))"
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
    private static let monthYear = formatter("MMMM yyyy")
    private static let monthOnly = formatter("MMMM")

    static func date(_ iso: String) -> Date? {
        Format.iso.date(from: String(iso.prefix(10)))
    }

    /// "Wednesday, October 14".
    static func day(_ iso: String) -> String {
        date(iso).map { longDay.string(from: $0) } ?? iso
    }

    /// "Oct 14".
    static func short(_ iso: String) -> String {
        date(iso).map { shortDay.string(from: $0) } ?? iso
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

    /// A day in the list, as the web heads it: "Today" · "Thu, Oct 29",
    /// "Monday" · "Oct 26", or "October 20" · "Tuesday".
    static func dayParts(_ iso: String, now: Date = Date()) -> (name: String, date: String) {
        guard let day = date(iso) else { return (iso, "") }
        var utc = Calendar(identifier: .gregorian)
        utc.timeZone = TimeZone(identifier: "UTC")!
        let local = Calendar.current.dateComponents([.year, .month, .day], from: now)
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
}
