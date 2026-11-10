import SwiftUI

/// The Allowance orb (REFRESH-05, library component set `Allowance orb`
/// under Section/Home; the as-built H-00 ring): on Home (H-00, H-00r, H-00u)
/// and O-11b. Bottom to top: the nacre halo, the track, the arc from 12
/// o'clock clockwise to `progress` with its glow, the pearl at the arc's end,
/// the frosted disc with the Nacre/Horizontal edge, and the words: a label,
/// the amount in Fraunces, and a line under it. 262 pt; the halo overflows
/// 34 pt on every side (a glow, not layout). No motion yet (house rule).
/// VoiceOver reads it as one element: "Allowance, $6,413 left in November".
struct AllowanceOrb: View {
    let progress: Double
    let label: String
    let amount: String
    var sub: String? = nil

    private static let size: CGFloat = 262
    private static let ring: CGFloat = 14
    /// The pearl's centre sits on the arc's centre line.
    private static let thumbRadius: CGFloat = 124

    /// The ring's angular nacre: rose → lilac → seaglass → blush → rose.
    static let nacre = AngularGradient(
        stops: [.init(color: Color(hex: 0xFF8FB1), location: 0),
                .init(color: Color(hex: 0xC9A8FF), location: 0.30),
                .init(color: Color(hex: 0x8FE0D4), location: 0.55),
                .init(color: Color(hex: 0xFFD6E0), location: 0.80),
                .init(color: Color(hex: 0xFF8FB1), location: 1)],
        center: .center)

    var body: some View {
        let p = min(max(progress, 0), 1)
        ZStack {
            // Ring halo: 330, layer blur 60, 45%.
            Circle().fill(Self.nacre)
                .frame(width: 330, height: 330)
                .blur(radius: 60)
                .opacity(0.45)
            // Track: 14 pt inside, white @55%.
            Circle().strokeBorder(.white.opacity(0.55), lineWidth: Self.ring)
                .frame(width: Self.size, height: Self.size)
            if p > 0 {
                // Arc: from 12 o'clock clockwise, glowing #D999FF @45%.
                Circle().trim(from: 0, to: p)
                    .stroke(Self.nacre, style: StrokeStyle(lineWidth: Self.ring, lineCap: .butt))
                    .rotationEffect(.degrees(-90))
                    .padding(Self.ring / 2)
                    .frame(width: Self.size, height: Self.size)
                    .shadow(color: Color(hex: 0xD999FF).opacity(0.45), radius: 18)
            }
            // Disc: glass @72% over a blur, Nacre/Horizontal 1 pt edge, #734D99 @15% shadow.
            Circle().fill(Nacre.glass)
                .background(.ultraThinMaterial, in: Circle())
                .overlay(Circle().strokeBorder(Nacre.horizontal, lineWidth: 1))
                .shadow(color: Color(hex: 0x734D99).opacity(0.15), radius: 30, y: 10)
                .frame(width: 216, height: 216)
            if p > 0 {
                // Pearl thumb: 24, radial white → #F3ECFF → #D9C6FF, glowing #FFD9F2.
                Circle()
                    .fill(RadialGradient(stops: [.init(color: .white, location: 0),
                                                 .init(color: Color(hex: 0xF3ECFF), location: 0.6),
                                                 .init(color: Color(hex: 0xD9C6FF), location: 1)],
                                         center: UnitPoint(x: 0.35, y: 0.30), startRadius: 0, endRadius: 12))
                    .overlay(Circle().strokeBorder(.white.opacity(0.9), lineWidth: 1))
                    .shadow(color: Color(hex: 0xFFD9F2).opacity(0.95), radius: 14)
                    .frame(width: 24, height: 24)
                    .offset(Self.thumbOffset(p))
            }
            VStack(spacing: 2) {
                Text(label).font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.muted)
                Text(amount)
                    .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)
                    .foregroundColor(Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
                if let sub = sub, !sub.isEmpty {
                    Text(sub).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                }
            }
            .multilineTextAlignment(.center)
            .padding(.horizontal, 30)
            .frame(width: 216)
        }
        .frame(width: Self.size, height: Self.size)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([label + ",", amount, sub ?? ""].filter { !$0.isEmpty }.joined(separator: " "))
    }

    /// Where the pearl sits: `progress` of the way round from 12 o'clock.
    static func thumbOffset(_ progress: Double) -> CGSize {
        let angle = progress * 2 * .pi
        return CGSize(width: thumbRadius * CGFloat(sin(angle)), height: -thumbRadius * CGFloat(cos(angle)))
    }
}
