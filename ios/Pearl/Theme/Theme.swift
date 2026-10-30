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

    static let borderStrong = dynamic(light: 0x8A87A3, dark: 0x8A87A3) // --border-strong
    static let moneyOut = dynamic(light: 0xC0392B, dark: 0xFF7B72)  // --money-out
    static let rose = Color(hex: 0xE2557F)                          // --rose (category icons)
    static let spent = dynamic(light: 0xB8285A, dark: 0xFBF8F6)     // .tm-stat.out
    static let cameIn = dynamic(light: 0x12736B, dark: 0xFBF8F6)    // .tm-stat.in
    static let onBlush = Color(hex: 0x1C1A33)                       // --on-nacre
    static let bar = dynamic(light: 0xFFFFFF, dark: 0x151B44)       // --surface, the tab bar

    // MARK: Type
    // Fraunces (display) and Figtree (text), as on the web, bundled in Fonts/.
    // Sizes are the web's in points, and scale with Dynamic Type.

    /// Fraunces SemiBold: page titles, card titles and big amounts.
    static func display(_ style: Font.TextStyle = .largeTitle) -> Font {
        let size: CGFloat
        switch style {
        case .largeTitle: size = 30   // .pk-h1
        case .title: size = 28
        case .title2: size = 24       // .pk-h2
        case .title3: size = 20
        default: size = 18            // .pk-h3
        }
        return .custom("Fraunces-SemiBold", size: size, relativeTo: style)
    }

    static let title = display(.title2)
    static let heading = display(.headline)

    /// Figtree, for everything that isn't a title.
    static func text(_ style: Font.TextStyle = .body, _ weight: Font.Weight = .regular) -> Font {
        let size: CGFloat
        switch style {
        case .largeTitle: size = 30
        case .title: size = 26
        case .title2: size = 22
        case .title3: size = 20
        case .headline: size = 17
        case .body: size = 16         // .text-body-large
        case .callout: size = 15      // .pk-row-name
        case .subheadline: size = 14
        case .footnote: size = 13     // .pk-row-meta
        case .caption: size = 12      // .pk-overline
        default: size = 11
        }
        let face: String
        switch weight {
        case .medium: face = "Figtree-Medium"
        case .semibold: face = "Figtree-SemiBold"
        case .bold, .heavy, .black: face = "Figtree-Bold"
        default: face = "Figtree-Regular"
        }
        return .custom(face, size: size, relativeTo: style)
    }

    /// The same faces for UIKit's bars.
    static func uiText(_ size: CGFloat, _ face: String = "Figtree-SemiBold") -> UIFont {
        UIFont(name: face, size: size) ?? .systemFont(ofSize: size, weight: .semibold)
    }

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
