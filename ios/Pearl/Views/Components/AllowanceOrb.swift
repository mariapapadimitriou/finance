import SwiftUI

/// The Allowance orb, A+ (AP-Home, AP-HomeCalm, AP-PhotoHome; REDESIGN-04):
/// on Home and O-11b. 232 pt when it stands alone (the calm state, setup),
/// 188 when cards follow it on Home. Bottom to top: the nacre halo (blur 46,
/// 30% light / 22% dark, 26 pt past the orb), the track (white 55% / 12%),
/// the arc from 12 o'clock clockwise to `progress`, the pearl at the arc's
/// end, the glass disc, and the words: a label, the amount in Fraunces, and
/// a line under it. VoiceOver reads it as one element: "Allowance, $6,413
/// left in November".
struct AllowanceOrb: View {
    let progress: Double
    let label: String
    let amount: String
    var sub: String? = nil
    /// 232 alone, 188 with cards under it (`.orb.sm`).
    var size: CGFloat = AllowanceOrb.full

    static let full: CGFloat = 232
    static let small: CGFloat = 188

    @Environment(\.colorScheme) private var scheme

    /// The ring's angular nacre: rose → lilac → seaglass → mist.
    static let nacre = AngularGradient(
        stops: [.init(color: Color(hex: 0xFF8FB1), location: 0),
                .init(color: Color(hex: 0xC9A8FF), location: 0.30),
                .init(color: Color(hex: 0x8FE0D4), location: 0.55),
                .init(color: Color(hex: 0xC8E6E6), location: 0.72),
                .init(color: Color(hex: 0xFFD6E0), location: 0.86),
                .init(color: Color(hex: 0xFF8FB1), location: 1)],
        center: .center)

    private var small: Bool { size < AllowanceOrb.full }
    /// 11 pt at 232 (mask at 105 of 116), 9 pt at 188 (85 of 94).
    private var ring: CGFloat { small ? 9 : 11 }
    /// The disc sits 20 in (16 at 188).
    private var disc: CGFloat { size - 2 * (small ? 16 : 20) }
    private var thumb: CGFloat { small ? 20 : 22 }

    var body: some View {
        let p = min(max(progress, 0), 1)
        ZStack {
            Circle().fill(Self.nacre)
                .frame(width: size + 52, height: size + 52)
                .blur(radius: 46)
                .opacity(scheme == .dark ? 0.22 : 0.30)
                .allowsHitTesting(false)
            Circle().strokeBorder(Color.white.opacity(scheme == .dark ? 0.12 : 0.55), lineWidth: ring)
                .frame(width: size, height: size)
            if p > 0 {
                Circle().trim(from: 0, to: p)
                    .stroke(Self.nacre, style: StrokeStyle(lineWidth: ring, lineCap: .butt))
                    .rotationEffect(.degrees(-90))
                    .padding(ring / 2)
                    .frame(width: size, height: size)
            }
            discView
            if p > 0 {
                Circle()
                    .fill(RadialGradient(stops: [.init(color: .white, location: 0),
                                                 .init(color: Color(hex: 0xF3ECFF), location: 0.6),
                                                 .init(color: Color(hex: 0xD9C6FF), location: 1)],
                                         center: UnitPoint(x: 0.35, y: 0.30), startRadius: 0, endRadius: thumb / 2))
                    .overlay(Circle().strokeBorder(Color.white.opacity(0.9), lineWidth: 1))
                    .shadow(color: Color(hex: 0xFFD9F2).opacity(0.95), radius: 7)
                    .frame(width: thumb, height: thumb)
                    .offset(Self.thumbOffset(p, radius: size / 2 - ring / 2))
            }
            words
        }
        .frame(width: size, height: size)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([label + ",", amount, sub ?? ""].filter { !$0.isEmpty }.joined(separator: " "))
    }

    /// The glass disc: white 78% / ocean 80%, a 1 pt inner line, its shadow.
    private var discView: some View {
        Circle()
            .fill(scheme == .dark ? Color(red: 21 / 255, green: 27 / 255, blue: 68 / 255).opacity(0.80)
                                  : Color.white.opacity(0.78))
            .overlay(Circle().strokeBorder(Color.white.opacity(scheme == .dark ? 0.10 : 0.95), lineWidth: 1))
            .shadow(color: scheme == .dark ? .black.opacity(0.25) : Color(hex: 0x734D99).opacity(0.14),
                    radius: 15, y: 10)
            .frame(width: disc, height: disc)
    }

    /// "Allowance" 15/500 muted; the amount Fraunces 44 (38 small) /600;
    /// "left in November" 13 muted.
    private var words: some View {
        VStack(spacing: 2) {
            Text(label).font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.muted)
            Text(amount)
                .font(.custom("Fraunces-SemiBold", size: small ? 38 : 44, relativeTo: .largeTitle))
                .tracking(small ? -0.8 : -0.88)
                .foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
                // The digits roll to a new number (a write's `changed.allowance`).
            if let sub = sub, !sub.isEmpty {
                Text(sub).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                    .lineLimit(2).minimumScaleFactor(0.8)
            }
        }
        .multilineTextAlignment(.center)
        .padding(.horizontal, small ? 18 : 24)
        .frame(width: disc)
    }

    /// Where the pearl sits: `progress` of the way round from 12 o'clock,
    /// on the ring's centre line.
    static func thumbOffset(_ progress: Double, radius: CGFloat = 110.5) -> CGSize {
        let angle = progress * 2 * .pi
        return CGSize(width: radius * CGFloat(sin(angle)), height: -radius * CGFloat(cos(angle)))
    }
}
