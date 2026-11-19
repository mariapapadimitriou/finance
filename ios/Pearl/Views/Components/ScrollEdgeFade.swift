import SwiftUI

// TEST-38 (round 5): rows and titles scrolled under the clock with nothing
// between them (Cash flow and Calendar, a transaction's page, Profile,
// Sign-in and security). Every A+ screen gets the same soft edge, as iOS
// draws it: the page's own ground over the status bar (and a pushed page's
// see-through bar), fading out at the top of the safe area. At rest nothing
// sits there, so it can't be seen; it only covers what scrolls under it.
//
// Round 5 re-test: the first version read the inset inside a GeometryReader
// that itself ignored the safe area. There the inset is 0, so nothing was
// drawn. Now the reader keeps to the safe area (so it reads the real inset,
// about 62 pt under the Dynamic Island) and only the fade it draws reaches
// up into it.

extension View {
    /// The top scroll edge: the A+ ground fading out under the status bar.
    /// `nacreScreen()` adds it, so every screen on the A+ ground has it.
    func scrollEdgeFade() -> some View {
        overlay { ScrollEdgeFade() }
    }
}

struct ScrollEdgeFade: View {
    var body: some View {
        // Inside the safe area: here `safeAreaInsets.top` is the real inset.
        GeometryReader { g in
            ScrollEdgeFadeBand(top: g.safeAreaInsets.top)
                // Only the band goes up under the clock.
                .ignoresSafeArea()
        }
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}

/// The ground over the screen's top `top` points: solid for the first 60%,
/// then fading to nothing at the safe area's edge. It fills the screen the
/// way the page's ground does, so the two line up exactly.
struct ScrollEdgeFadeBand: View {
    let top: CGFloat

    var body: some View {
        if top > 0 {
            APGround()
                .mask {
                    VStack(spacing: 0) {
                        LinearGradient(stops: [.init(color: .black, location: 0),
                                               .init(color: .black, location: 0.6),
                                               .init(color: .clear, location: 1)],
                                       startPoint: .top, endPoint: .bottom)
                            .frame(height: top)
                        Spacer(minLength: 0)
                    }
                    .ignoresSafeArea()
                }
        }
    }
}
