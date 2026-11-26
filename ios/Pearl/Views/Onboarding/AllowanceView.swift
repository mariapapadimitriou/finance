import SwiftUI

/// O-11 "Your Allowance" (THL-125, THL-129): the first Allowance in a nacre
/// ring, and the first steps. O-11b while Pearl is still learning, O-11c over
/// this month's plan, O-11d started mid-month, O-12 when linking was skipped.
@MainActor
struct AllowanceView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [SetupRoute]
    let skipped: Bool
    @State private var home: AllowanceHome?
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        // G6-Allowance O-11 / O-11b / O-11d / O-12: the overline, the
        // Allowance on its card, then the first steps. "Build your safety
        // net" is hidden while Save is parked (approved 2026-11-18).
        OnbScreen(back: false) {
            Text(skipped ? "Almost there" : "You\u{2019}re all set")
                .textCase(.uppercase)
                .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity)
                .padding(.top, 10)
            // P6e (TP-P6-Setup): "Allowance left · November", no line under
            // it, and one next step. Notifications are asked on Home (P6f).
            AllowanceCard(month: cardMonth, amount: ringAmount, line: skipped ? caption : "",
                          over: !skipped && allowance?.state == "over" && (allowance?.overBy ?? 0) >= 0.5)
            ProfileSection("Next")
            APCard {
                Button { if skipped { linkBank() } else { Task { await finish() } } } label: {
                    ProfileRow(symbol: skipped ? "building.columns" : "rectangle.on.rectangle",
                               title: skipped ? "Link your bank" : "Sort this month\u{2019}s spending",
                               sub: skipped ? nil : sortLine)
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            if skipped {
                OnbPrimary(title: "Link your bank") { linkBank() }
            } else {
                OnbPrimary(title: "Go to Home", busy: busy) { Task { await finish() } }
            }
        }
        .task {
            guard !skipped else { return }
            do {
                home = try await app.api.get("api/home")
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private func linkBank() {
        if let i = path.firstIndex(of: .linkBank) {
            path = Array(path.prefix(i + 1))
        } else {
            path = [.linkBank]
        }
    }

    /// "November", "Nov 20–30", "12 days left".
    private var cardMonth: String {
        let words = allowance?.ringOverline(month: month) ?? Format.monthName(month)
        return words.contains("DAYS LEFT") ? words.lowercased() : words.capitalized
    }

    private var allowance: Allowance? { home?.safeToSpend }

    /// "8 to sort · about a minute".
    private var sortLine: String? {
        guard let n = home?.reviewCount, n > 0 else { return nil }
        let minutes = Int((Double(n) * 10 / 60).rounded())
        return "\(n) to sort \u{00B7} " + (minutes <= 1 ? "about a minute" : "about \(minutes) minutes")
    }
    private var month: String { home?.month ?? Allowance.thisMonth }

    private var ringOverline: String { allowance?.ringOverline(month: month) ?? Format.monthName(month).uppercased() }
    private var ringAmount: String { skipped ? "—" : allowance?.ringAmount ?? "—" }

    private var caption: String {
        if skipped { return "Link a bank to see your Allowance." }
        return allowance?.ringCaption ?? ""
    }



    private func finish() async {
        busy = true
        defer { busy = false }
        error = await finishSetup(app)
    }
}

/// What the ring says about an Allowance: on O-11 and on Home.
extension Allowance {
    static var thisMonth: String {
        let f = DateFormatter()
        f.dateFormat = "yyyy-MM"
        return f.string(from: Date())
    }

    private var over: Bool { state == "over" }

    /// "NOVEMBER", "12 DAYS LEFT" when over, or "NOV 20–30" mid-month (O-11d).
    func ringOverline(month: String) -> String {
        if over, let left = daysLeft { return "\(left) DAYS LEFT" }
        if let range = midMonth { return range }
        return Format.monthName(month).uppercased()
    }

    private var midMonth: String? {
        guard let from = from, let start = Format.localDay(from) else { return nil }
        guard let days = Calendar.current.range(of: .day, in: .month, for: start)?.count else { return nil }
        let f = DateFormatter()
        f.dateFormat = "MMM d"
        return "\(f.string(from: start))–\(days)".uppercased()
    }

    var ringAmount: String {
        guard state != "needs_income" else { return "—" }
        if over { return "−" + Format.whole(overBy ?? 0) }
        let value = Format.whole(shown ?? amount ?? 0)
        return estimate == true ? "~" + value : value
    }

    /// How much of the month is left, which is how far round the pearl sits.
    var ringProgress: Double {
        guard !over, let left = daysLeft else { return 0 }
        var days = Double(Calendar.current.range(of: .day, in: .month, for: Date())?.count ?? 30)
        // Started mid-month: of the days it covers, not the whole month.
        if let from = from, let start = Format.localDay(from) {
            days -= Double(Calendar.current.component(.day, from: start) - 1)
        }
        return min(max(Double(left) / max(days, 1), 0.05), 1)
    }

    var ringCaption: String {
        let next = nextPay.map { " Next pay: \(Format.short($0))." } ?? ""
        switch state {
        case "needs_income": return "Add your income to see your Allowance."
        case "over":
            if (overBy ?? 0) < 0.5 { return "You’ve used this month’s Allowance.\(next)" }
            return "\(Format.whole(overBy ?? 0)) past this month’s plan.\(next)"
        default:
            if midMonth != nil { return "For the rest of this month." }
            if estimate == true {
                let when = nextPay.map { " on \(Format.short($0))" } ?? ""
                return "An estimate for now. It gets sharper after your next pay\(when)."
            }
            return Self.restCaption
        }
    }

    /// The usual line under the ring. Home hides it (REFRESH-03, H-00n: the
    /// ring already says Allowance) and reads it as the ring's VoiceOver hint.
    /// P6e (TP-P6-Setup, TP-Words): none; "Left to spend or save on
    /// non-essentials" went, the ring and the card already say Allowance left.
    static let restCaption = ""

    /// The line under the amount inside Home's orb (REFRESH-05, H-00r):
    /// "left in November"; the overline's words when the month is over or
    /// started part-way ("12 days left", "Nov 20–30"); nothing without income.
    func orbSub(month: String) -> String? {
        if state == "needs_income" { return nil }
        if over, let left = daysLeft { return "\(left) days left" }
        if let range = midMonth { return range.capitalized }
        return Self.orbSub(forMonth: month)
    }

    static func orbSub(forMonth month: String) -> String {
        "left in \(Format.monthName(month))"
    }
}

/// O-11a "What's a safety net?"
struct SafetyNetTip: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("What’s a safety net?").font(Nacre.headline)
            Text("Money set aside for surprises, like a car repair or time between jobs. A good first goal is 3 months of essentials.")
                .font(Nacre.footnote)
                .fixedSize(horizontal: false, vertical: true)
        }
        .padding(16)
        .frame(width: 290)
        .foregroundColor(Pearl.ink)
    }
}

/// G6-Allowance's card: "Your Allowance · November", the amount in 56 pt
/// Fraunces, and its line.
struct AllowanceCard: View {
    let month: String
    let amount: String
    let line: String
    /// G6-Over O-11c: over this month's plan, the amount is red (red only for over).
    var over = false

    var body: some View {
        VStack(spacing: 4) {
            // P6e / TP-Words: the ring's words.
            Text("Allowance left \u{00B7} \(month)").font(Nacre.subheadline).foregroundColor(Pearl.muted)
            Text(amount).font(.custom("Fraunces-SemiBold", size: 56, relativeTo: .largeTitle))
                .tracking(-1).monospacedDigit().foregroundColor(over ? Pearl.danger : Pearl.ink)
                .pearlAmountFit()
            if !line.isEmpty {
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
                    .padding(.top, 2)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 16).padding(.vertical, 22)
        .apCard()
        .padding(.top, 2)
        .accessibilityElement(children: .combine)
    }
}
