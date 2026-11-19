import SwiftUI

// TEST-38 (round 5): rows and titles scrolled under the clock with nothing
// between them (Cash flow and Calendar, a transaction's page, Profile,
// Sign-in and security). Every A+ screen gets the same soft edge, as iOS
// draws it: the page's own ground over the status bar (and a pushed page's
// see-through bar), fading out at the top of the safe area. At rest nothing
// sits there, so it can't be seen; it only covers what scrolls under it.

extension View {
    /// The top scroll edge: the A+ ground fading out under the status bar.
    /// `nacreScreen()` adds it, so every screen on the A+ ground has it.
    func scrollEdgeFade() -> some View {
        overlay { ScrollEdgeFade() }
    }
}

struct ScrollEdgeFade: View {
    var body: some View {
        GeometryReader { g in
            let top = g.safeAreaInsets.top
            if top > 0 {
                // The same ground as the page, in the same place, so it
                // lines up with what's behind it exactly.
                APGround()
                    .mask(alignment: .top) {
                        LinearGradient(stops: [.init(color: .black, location: 0),
                                               .init(color: .black, location: 0.6),
                                               .init(color: .clear, location: 1)],
                                       startPoint: .top, endPoint: .bottom)
                            .frame(height: top)
                    }
            }
        }
        .ignoresSafeArea()
        .allowsHitTesting(false)
        .accessibilityHidden(true)
    }
}
