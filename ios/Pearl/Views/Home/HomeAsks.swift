import SwiftUI

// Fewer taps (the tap audit, 2026-11-26; approved by the product owner):
// the two questions Home asks in place, each one card with one answer
// (taps.css `.askcard`: 18 padding, 14 apart, the question in Fraunces
// 22/28, its line in 15/20 muted, the buttons side by side).
//
// P12a (TP-P12-Home, THL-127, THL-45, THL-125, THL-104): "Is $5,850 from
//   Acme your pay?" under the ring, Yes / No; Profile › Income and bills
//   no longer has to be found first (3 taps → 1).
// P6f (TP-P6-News, THL-117, THL-139): "Want a heads-up next time?" under
//   the first news, Turn on / Not now; set-up has no notification screen.

/// P12a: the found pay as one question.
struct PayAskCard: View {
    let pay: IncomeBills.Candidate
    var busy = false
    let onYes: () -> Void
    let onNo: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text("Is \(Format.whole(pay.amount)) from \(pay.name) your pay?")
                .font(.custom("Fraunces-SemiBold", size: 22, relativeTo: .title2))
                .foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let line = PayAskCard.cameIn(pay.seen ?? []) {
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            HStack(spacing: 12) {
                Button("Yes", action: onYes)
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .accessibilityLabel("Yes, \(pay.name) is my pay")
                    .accessibilityIdentifier("pay-ask-yes")
                Button("No", action: onNo)
                    .buttonStyle(APSecondaryButtonStyle())
                    .accessibilityLabel("No, \(pay.name) isn’t my pay")
                    .accessibilityIdentifier("pay-ask-no")
            }
            .disabled(busy)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .apCard()
    }

    /// "It came in Nov 14 and Oct 31." (P12a), or one day.
    static func cameIn(_ days: [String]) -> String? {
        let shown = days.prefix(2).map { Format.short($0) }
        guard !shown.isEmpty else { return nil }
        return "It came in \(shown.joined(separator: " and "))."
    }
}

/// P6f: notifications, asked when Pearl has something to tell her.
struct NotifyAskCard: View {
    let quiet: NotificationSettings.Quiet
    var busy = false
    let onTurnOn: () -> Void
    let onNotNow: () -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack(spacing: 12) {
                APIcon(symbol: "bell")
                Text("Want a heads-up next time?")
                    .font(.custom("Fraunces-SemiBold", size: 20, relativeTo: .title3))
                    .foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
            }
            Text("Like this one. Quiet from \(QuietTime.short(quiet.from)) to \(QuietTime.short(quiet.to)).")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
            HStack(spacing: 12) {
                Button("Turn on", action: onTurnOn)
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .accessibilityIdentifier("notify-turn-on")
                Button("Not now", action: onNotNow)
                    .buttonStyle(APSecondaryButtonStyle())
                    .accessibilityIdentifier("notify-not-now")
            }
            .disabled(busy)
        }
        .padding(18)
        .frame(maxWidth: .infinity, alignment: .leading)
        .apCard()
    }

    /// P6f: Not now hides the card on this iPhone for 30 days.
    static let hiddenKey = "pearl.notifyAsk.hiddenUntil"

    static var hidden: Bool {
        let until = UserDefaults.standard.double(forKey: hiddenKey)
        return until > Date().timeIntervalSince1970
    }

    static func hideForAMonth() {
        UserDefaults.standard.set(Date().addingTimeInterval(30 * 24 * 3600).timeIntervalSince1970, forKey: hiddenKey)
    }
}

/// What a pay answer returns: the check again, and how to undo it.
struct PayAnswered: Decodable {
    let candidates: [IncomeBills.Candidate]
    let undo: JSONValue?
}

/// kit.css `.pearlorb`: the pearl itself, white to blush to lilac, with a
/// lilac halo, a rose glow and its highlight.
struct PearlOrb: View {
    var size: CGFloat = 64
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let dark = scheme == .dark
        Circle()
            .fill(RadialGradient(stops: [.init(color: .white, location: 0),
                                         .init(color: Color(hex: 0xFCE8F0), location: 0.48),
                                         .init(color: Color(hex: 0xD7C2FF), location: 0.82),
                                         .init(color: Color(hex: 0xC3A8F5), location: 1)],
                                 center: UnitPoint(x: 0.4, y: 0.34), startRadius: 0, endRadius: size * 0.62))
            .overlay(
                Ellipse().fill(Color.white.opacity(0.92))
                    .frame(width: size * 0.28, height: size * 0.20)
                    .rotationEffect(.degrees(-12))
                    .offset(x: -size * 0.10, y: -size * 0.18))
            .frame(width: size, height: size)
            .background(Circle().fill(Color(hex: dark ? 0xE3D4FF : 0xCDB9FF).opacity(dark ? 0.16 : 0.30))
                .frame(width: size + 14, height: size + 14))
            .shadow(color: Color(hex: dark ? 0xC9A8FF : 0xFFAAC8).opacity(dark ? 0.55 : 0.65), radius: 23)
            .shadow(color: Color(hex: 0x734D99).opacity(dark ? 0 : 0.22), radius: 15, y: 14)
            .accessibilityHidden(true)
    }
}

/// P7b (TP-P7-LinkLater, THL-114, THL-119, THL-118, THL-125): Home before a
/// bank is one card, one action (taps.css `.linkcard`).
struct LinkBankCard: View {
    var busy = false
    let link: () -> Void

    var body: some View {
        VStack(spacing: 12) {
            PearlOrb(size: 64)
            Text("Link your bank to see your Allowance.")
                .font(.custom("Fraunces-SemiBold", size: 22, relativeTo: .title2))
                .foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .frame(maxWidth: 260)
                .fixedSize(horizontal: false, vertical: true)
            Button("Link your bank", action: link)
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(busy)
                .padding(.top, 6)
                .accessibilityIdentifier("home-link-bank")
        }
        .padding(.horizontal, 20).padding(.top, 28).padding(.bottom, 20)
        .frame(maxWidth: .infinity)
        .apCard()
    }
}
