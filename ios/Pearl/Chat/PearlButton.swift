import SwiftUI

/// PB-01 (1337:7575; on PC-01 1337:7650 and PC-02 1337:7855): the Pearl
/// button. A 56 pt Glass button with Logo/Mark, floating 16 pt from the right
/// edge and 4 pt above the full-width tab bar, on the five tabs only. Never
/// hidden on scroll. With a suggestion (a trip or a pattern waiting) a Nacre
/// ring sweeps once (1.2 s) and a small nacre dot stays; Reduce Motion fades
/// the ring in. It stays 56 pt at large text sizes: it's an icon.
struct PearlButton: View {
    /// A trip or pattern card is waiting (GET /api/chat `suggest`).
    let suggest: Bool
    let action: () -> Void

    /// What every scrolling list on a tab adds at the bottom, over the tab
    /// bar's own: the button and its gap (note 1340:8893: tab bar + 56 + 16).
    static let clearance: CGFloat = 56 + 16

    @Environment(\.colorScheme) private var scheme
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var sweep: CGFloat = 0
    @State private var ringShown = false

    var body: some View {
        Button(action: action) {
            ZStack {
                if suggest {
                    // The Nacre ring, 64 pt round the 56 pt button.
                    Circle()
                        .trim(from: 0, to: reduceMotion ? 1 : sweep)
                        .stroke(Nacre.horizontal, style: StrokeStyle(lineWidth: 2, lineCap: .round))
                        .rotationEffect(.degrees(-90))
                        .frame(width: 62, height: 62)
                        .opacity(reduceMotion ? (ringShown ? 1 : 0) : 1)
                }
                Circle()
                    .fill(Nacre.glass)
                    .background(.ultraThinMaterial, in: Circle())
                    .overlay(Circle().strokeBorder(Nacre.glassEdge, lineWidth: 1))
                    .shadow(color: Color(hex: 0x1C1A33).opacity(0.1), radius: 5, y: 6)
                    .frame(width: 56, height: 56)
                Image("LogoMark")
                    .resizable()
                    .aspectRatio(contentMode: .fit)
                    .frame(width: 30, height: 25)
                if suggest {
                    // "Dot · something to suggest", 10 pt at the top right.
                    Circle()
                        .fill(Nacre.horizontal)
                        .overlay(Circle().strokeBorder(.white.opacity(scheme == .dark ? 0.6 : 0.9), lineWidth: 1))
                        .frame(width: 10, height: 10)
                        .offset(x: 21, y: -21)
                }
            }
            .frame(width: 64, height: 64)
            .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Pearl")
        .accessibilityHint("Opens Pearl chat")
        .accessibilityIdentifier("pearl-button")
        .onAppear(perform: animateRing)
        .onChange(of: suggest) { _ in animateRing() }
    }

    private func animateRing() {
        guard suggest else {
            sweep = 0
            ringShown = false
            return
        }
        if reduceMotion {
            withAnimation(.easeIn(duration: 0.6)) { ringShown = true }
        } else {
            sweep = 0
            withAnimation(.easeInOut(duration: 1.2)) { sweep = 1 }
        }
    }
}

extension View {
    /// PB-01 on one of the five tabs: the button over the bottom right, and
    /// room under every scrolling list so its last row clears it. Shown only
    /// where Apple Intelligence can run Pearl chat (PC-11: else no button).
    func pearlButton(shown: Bool, suggest: Bool, action: @escaping () -> Void) -> some View {
        safeAreaInset(edge: .bottom, spacing: 0) {
            if shown { Color.clear.frame(height: PearlButton.clearance) }
        }
        .overlay(alignment: .bottomTrailing) {
            if shown {
                // 64 pt frame round the 56 pt button: 16 and 4 pt from its edge.
                PearlButton(suggest: suggest, action: action)
                    .padding(.trailing, 16 - 4)
                    .padding(.bottom, 4 - 4)
                    .transition(.opacity)
            }
        }
    }
}
