import SwiftUI

// TEST-38 (round 5): rows and titles scrolled under the clock with nothing
// between them (Cash flow and Calendar, a transaction's page, Profile,
// Sign-in and security). Every A+ screen gets the same soft edge, as iOS
// draws it: the page's own ground over the status bar (and a pushed page's
// see-through bar), fading out at the top of the safe area. At rest nothing
// sits there, so it can't be seen; it only covers what scrolls under it.
//
// Round 5 re-tests:
// * The inset is read by a reader that keeps to the safe area (one that
//   ignores it reads 0, and nothing was drawn).
// * TEST-49: the reader sits in the background, and the only layer on top
//   is the band itself, as tall as the top inset. A full-screen overlay
//   (even with hit testing off) won the accessibility hit test, so XCUITest
//   and VoiceOver found nothing on the screen hittable.

extension View {
    /// The top scroll edge: the A+ ground fading out under the status bar.
    /// `nacreScreen()` adds it, so every screen on the A+ ground has it.
    func scrollEdgeFade() -> some View {
        modifier(ScrollEdgeFade())
    }
}

struct ScrollEdgeFade: ViewModifier {
    /// The top safe-area inset (status bar, and a pushed page's bar).
    @State private var top: CGFloat = 0
    /// The whole screen the page's ground fills, so the band's ground lines
    /// up with it exactly.
    @State private var ground: CGSize = .zero

    func body(content: Content) -> some View {
        content
            // Behind everything, inside the safe area: here the inset is real.
            .background(GeometryReader { g in
                Color.clear
                    .onAppear { measure(g) }
                    .onChange(of: g.safeAreaInsets) { _ in measure(g) }
                    .onChange(of: g.size) { _ in measure(g) }
            })
            // On top: only the band, `top` tall, at the very top of the screen.
            .overlay(alignment: .top) {
                ScrollEdgeFadeBand(top: top, ground: ground)
                    .ignoresSafeArea(.container, edges: .top)
            }
    }

    private func measure(_ g: GeometryProxy) {
        let i = g.safeAreaInsets
        top = i.top
        ground = CGSize(width: g.size.width + i.leading + i.trailing,
                        height: g.size.height + i.top + i.bottom)
    }
}

/// The ground over the screen's top `top` points: solid for the first 60%,
/// then fading to nothing at the safe area's edge. Its frame is the band
/// alone; the ground inside is drawn at the screen's size and clipped, so
/// its gradient matches the page's.
struct ScrollEdgeFadeBand: View {
    let top: CGFloat
    let ground: CGSize

    var body: some View {
        if top > 0 && ground.height > 0 {
            APGround()
                .frame(width: ground.width, height: ground.height)
                .frame(height: top, alignment: .top)
                .clipped()
                .mask(LinearGradient(stops: [.init(color: .black, location: 0),
                                             .init(color: .black, location: 0.6),
                                             .init(color: .clear, location: 1)],
                                     startPoint: .top, endPoint: .bottom))
                .allowsHitTesting(false)
                .accessibilityHidden(true)
        }
    }
}
