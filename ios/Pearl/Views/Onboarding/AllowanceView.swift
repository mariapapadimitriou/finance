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
    @State private var tip = false
    @State private var busy = false
    @State private var error: String?

    var body: some View {
        NacreScreen {
            VStack(spacing: 6) {
                Text(skipped ? "ALMOST THERE" : "YOU’RE ALL SET").font(Nacre.caption2).tracking(1.4)
                Text("Your Allowance").font(Nacre.largeTitle).tracking(0.4)
                    .accessibilityAddTraits(.isHeader)
            }
            .frame(maxWidth: .infinity)
            // REFRESH-05: the shared Allowance orb, with O-11b's own words
            // (the month, or "12 DAYS LEFT", over the amount).
            AllowanceOrb(progress: progress, label: ringOverline, amount: ringAmount)
                .frame(maxWidth: .infinity)
                .padding(.vertical, 8)
            Text(caption).font(Nacre.subheadline).multilineTextAlignment(.center)
                .frame(maxWidth: .infinity)
            GlassCard(spacing: 0) {
                Text("Your first steps").font(Nacre.headline)
                    .padding(.horizontal, 20).padding(.top, 18).padding(.bottom, 6)
                step(1, "Link your bank accounts", done: !skipped, current: skipped)
                step(2, "Sort this month’s spending", done: false, current: !skipped)
                HStack(alignment: .top) {
                    step(3, "Build your safety net for the unexpected", done: false, current: false)
                    Button { tip.toggle() } label: {
                        Image(systemName: "info.circle").font(.system(size: 15))
                    }
                    .buttonStyle(.plain)
                    .padding(.trailing, 20).padding(.top, 14)
                    .accessibilityLabel("What’s a safety net?")
                    .popover(isPresented: $tip) {
                        if #available(iOS 16.4, *) {
                            SafetyNetTip().presentationCompactAdaptation(.popover)
                        } else {
                            SafetyNetTip()
                        }
                    }
                }
                .padding(.bottom, 10)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                if skipped {
                    Button("Link your bank") {
                        if let i = path.firstIndex(of: .linkBank) {
                            path = Array(path.prefix(i + 1))
                        } else {
                            path = [.linkBank]
                        }
                    }
                    .buttonStyle(NacreButtonStyle())
                } else {
                    Button("Go to Home") { Task { await finish() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                }
            }
        }
        .navigationBarBackButtonHidden(!skipped)
        .task {
            guard !skipped else { return }
            do {
                home = try await app.api.get("api/home")
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private var allowance: Allowance? { home?.safeToSpend }
    private var month: String { home?.month ?? Allowance.thisMonth }

    private var ringOverline: String { allowance?.ringOverline(month: month) ?? Format.monthName(month).uppercased() }
    private var ringAmount: String { skipped ? "—" : allowance?.ringAmount ?? "—" }
    private var progress: Double { skipped ? 0 : allowance?.ringProgress ?? 0 }

    private var caption: String {
        if skipped { return "Link a bank to see your Allowance." }
        return allowance?.ringCaption ?? ""
    }



    private func step(_ n: Int, _ title: String, done: Bool, current: Bool) -> some View {
        HStack(alignment: .top, spacing: 12) {
            ZStack {
                if done {
                    Circle().fill(Pearl.action)
                    Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundColor(.white)
                } else {
                    Circle().fill(Nacre.glass).opacity(current ? 1 : 0.6)
                    Circle().strokeBorder(current ? Nacre.lilac : Color.clear, lineWidth: 1.5)
                    Text("\(n)").font(.custom("Figtree-Medium", size: 15))
                }
            }
            .frame(width: 30, height: 30)
            Text(title)
                .font(current ? Nacre.headline : Nacre.body)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.top, 4)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 20).padding(.vertical, 8)
        .accessibilityElement(children: .combine)
        .accessibilityValue(done ? "Done" : current ? "Next" : "")
    }

    private func finish() async {
        busy = true
        defer { busy = false }
        do {
            struct Reply: Decodable { let user: PearlUser? }
            let reply: Reply = try await app.api.post("api/onboarding", ["done": true])
            app.justCreated = false
            app.signedIn(reply.user)
        } catch {
            self.error = app.handle(error)
        }
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
    static let restCaption = "Left to spend or save on non-essentials."

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
