import SwiftUI
import UIKit

// TEST-37 (round 5): the keyboard's Done pill sat on Next (Who was it with?)
// and Save (How to split), and Save went half under the number pad. The
// stock keyboard toolbar floats its pill wherever iOS likes and the sheet
// didn't make room for it. This one footer modifier replaces it on every
// screen that had it: with the keyboard up, Done sits right above the
// keyboard on the right (where it was), and the primary button rides above
// both, clear of everything, still greyed out until the answer is valid.

extension View {
    /// On a sheet's footer (the primary button): Done above the keyboard
    /// while it's up, and the footer lifted clear of both.
    func keyboardDoneFooter(_ done: @escaping () -> Void) -> some View {
        modifier(KeyboardDoneFooter(done: done))
    }
}

struct KeyboardDoneFooter: ViewModifier {
    let done: () -> Void
    /// The keyboard's top, in screen points; nil while it's down.
    @State private var keyboardTop: CGFloat?
    /// Where the footer's space ends (the sheet's bottom, or the keyboard's
    /// top once the sheet has made room). It doesn't move with `lift`, so
    /// lifting can't feed back into itself.
    @State private var bottom: CGFloat = 0

    func body(content: Content) -> some View {
        VStack(spacing: 0) {
            content
            if keyboardTop != nil {
                HStack {
                    Spacer(minLength: 0)
                    KeyboardDonePill(action: done)
                }
                .padding(.horizontal, 16).padding(.bottom, 6)
                .transition(.opacity)
            }
        }
        .padding(.bottom, lift)
        .background(GeometryReader { g in
            Color.clear
                .onAppear { bottom = g.frame(in: .global).maxY }
                .onChange(of: g.frame(in: .global).maxY) { bottom = $0 }
        })
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillChangeFrameNotification)) { note in
            guard let end = (note.userInfo?[UIResponder.keyboardFrameEndUserInfoKey] as? NSValue)?.cgRectValue
            else { return }
            let up = end.height > 0 && end.minY < UIScreen.main.bounds.height - 1
            withAnimation(.easeOut(duration: 0.25)) { keyboardTop = up ? end.minY : nil }
        }
        .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardWillHideNotification)) { _ in
            withAnimation(.easeOut(duration: 0.25)) { keyboardTop = nil }
        }
    }

    /// Whatever the sheet's own keyboard avoidance left under the keyboard
    /// (the number pad's was short by about 26 pt).
    private var lift: CGFloat {
        guard let top = keyboardTop else { return 0 }
        return max(0, bottom - top)
    }
}

/// The Done pill: the action colour on a glass capsule, 44 pt tall.
struct KeyboardDonePill: View {
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text("Done")
                .font(Nacre.textButton).foregroundColor(Pearl.action)
                .padding(.horizontal, 20).frame(minHeight: 44)
                .background(.regularMaterial, in: Capsule())
                .overlay(Capsule().strokeBorder(APlus.cardLine, lineWidth: 1))
                .shadow(color: Pearl.cardShadow.opacity(0.14), radius: 10, y: 4)
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Puts the keyboard away")
    }
}
