import SwiftUI
import UIKit

/// Pearl's design tokens (src/tokens/tokens.css), light and dark.
enum Pearl {
    // MARK: Colours

    static let page = dynamic(light: 0xFBF8F6, dark: 0x0B1030)      // --surface-page
    static let card = dynamic(light: 0xFFFFFF, dark: 0x151B44)      // --surface-card
    static let border = dynamic(light: 0xEEDFE6, dark: 0x252C5E)    // --border
    static let track = dynamic(light: 0xF1E9EE, dark: 0x252C5E)     // --track
    static let ink = dynamic(light: 0x1C1A33, dark: 0xFBF8F6)       // --ink
    static let muted = dynamic(light: 0x686580, dark: 0xB4B1CC)     // --ink-muted
    static let action = dynamic(light: 0xB8285A, dark: 0xFF8FB1)    // --action
    static let onAction = dynamic(light: 0xFFFFFF, dark: 0x1C1A33)  // --on-action
    static let blush = Color(hex: 0xFFE4EC)                         // --blush
    static let answered = dynamic(light: 0xF1E9EE, dark: 0x252C5E)  // answered rows
    static let moneyIn = dynamic(light: 0x1E7B4C, dark: 0x56D48F)   // --money-in
    static let caution = dynamic(light: 0x8A5A12, dark: 0xF3D9A4)   // --caution
    static let cautionBackground = dynamic(light: 0xFBECC8, dark: 0x3A2E14)

    static let nacre = LinearGradient(
        colors: [Color(hex: 0xFFD6E0), Color(hex: 0xE3D4FF), Color(hex: 0xCFF3EE)],
        startPoint: .topLeading, endPoint: .bottomTrailing)

    // MARK: Type
    // Fraunces (display) and Figtree (text) on the web. On iPhone, New York
    // stands in for Fraunces and SF for Figtree, so text follows Dynamic Type.

    static func display(_ style: Font.TextStyle = .largeTitle) -> Font {
        .system(style, design: .serif).weight(.semibold)
    }

    static let title = Font.system(.title2, design: .serif).weight(.semibold)
    static let heading = Font.system(.headline, design: .serif).weight(.semibold)

    // MARK: Shape

    static let radiusCard: CGFloat = 24
    static let radiusRow: CGFloat = 16
    static let gutter: CGFloat = 16

    private static func dynamic(light: UInt32, dark: UInt32) -> Color {
        Color(UIColor { traits in
            UIColor(hex: traits.userInterfaceStyle == .dark ? dark : light)
        })
    }
}

extension Color {
    init(hex: UInt32) {
        self.init(UIColor(hex: hex))
    }
}

extension UIColor {
    convenience init(hex: UInt32) {
        self.init(red: CGFloat((hex >> 16) & 0xFF) / 255,
                  green: CGFloat((hex >> 8) & 0xFF) / 255,
                  blue: CGFloat(hex & 0xFF) / 255,
                  alpha: 1)
    }
}
