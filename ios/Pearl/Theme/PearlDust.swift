import SwiftUI

/// Pearl dust (REFRESH-05, library component `Pearl dust` under
/// Section/Home): two white auras and ten bubbles at fixed positions on the
/// 393×852 page, between the Iridescent/Light gradient and the content of
/// every light screen, as H-00 had it. Positions are the component's and are
/// not re-laid per screen; the whole sheet scales with the screen's width so
/// the top-right cluster stays by the corner on every iPhone. Light only:
/// dark keeps its own auras and bubbles in NacreBackground.
struct PearlDust: View {
    /// The screen's width; the dust is drawn for 393 pt and scaled to it.
    var width: CGFloat = PearlDust.pageWidth

    static let pageWidth: CGFloat = 393
    static let pageHeight: CGFloat = 852

    /// A bubble: the top-left corner and the diameter, as in Figma.
    struct Bubble: Identifiable {
        let x: CGFloat
        let y: CGFloat
        let size: CGFloat
        var id: String { "\(x),\(y)" }
        var center: CGPoint { CGPoint(x: x + size / 2, y: y + size / 2) }
    }

    /// The top-right cluster, then the edges.
    static let bubbles: [Bubble] = [
        Bubble(x: 338, y: 60, size: 9), Bubble(x: 360, y: 76, size: 5), Bubble(x: 324, y: 80, size: 4),
        Bubble(x: 348, y: 89, size: 6), Bubble(x: 367, y: 58, size: 4), Bubble(x: 333, y: 96, size: 3),
        Bubble(x: 4, y: 337, size: 4), Bubble(x: 4, y: 551, size: 4), Bubble(x: 2, y: 584, size: 6),
        Bubble(x: 382, y: 624, size: 6),
    ]

    var body: some View {
        let scale = max(width, 1) / Self.pageWidth
        ZStack(alignment: .topLeading) {
            // Auras: white, layer blur 90; 360 at (−60, 40) @50%, 280 at (160, 420) @40%.
            aura(size: 360, opacity: 0.5).position(x: -60 + 180, y: 40 + 180)
            aura(size: 280, opacity: 0.4).position(x: 160 + 140, y: 420 + 140)
            ForEach(Self.bubbles) { b in
                Circle()
                    .fill(RadialGradient(stops: [.init(color: .white.opacity(0), location: 0),
                                                 .init(color: .white.opacity(0.10), location: 0.7),
                                                 .init(color: .white.opacity(0.40), location: 1)],
                                         center: .center, startRadius: 0, endRadius: b.size / 2))
                    .overlay(Circle().strokeBorder(.white.opacity(0.85), lineWidth: 0.8))
                    .frame(width: b.size, height: b.size)
                    .position(b.center)
            }
        }
        .frame(width: Self.pageWidth, height: Self.pageHeight, alignment: .topLeading)
        .scaleEffect(scale, anchor: .topLeading)
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }

    private func aura(size: CGFloat, opacity: Double) -> some View {
        Circle().fill(.white)
            .frame(width: size, height: size)
            .blur(radius: 90)
            .opacity(opacity)
    }
}
