import SwiftUI
import UIKit

/// Pearl's design tokens (src/tokens/tokens.css), light and dark.
enum Pearl {
    // MARK: Colours

    // REFRESH-05 (2026-11-10, C‴): there is no flat light page colour any
    // more. Every light screen and sheet sits on Iridescent/Light with the
    // Pearl dust (NacreBackground / SheetBackground); color/surface/card is
    // glass/light (white @72%) and color/border/subtle is glass/edge-light
    // (white @80%). Dark values are unchanged.
    static let card = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(hex: 0x151B44) : UIColor(white: 1, alpha: 0.72) })      // color/surface/card
    static let border = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(hex: 0x252C5E) : UIColor(white: 1, alpha: 0.8) })       // color/border/subtle
    /// A toast's words on its ink fill (what the page colour used to be).
    static let onInk = dynamic(light: 0xFBF8F6, dark: 0x0B1030)
    static let track = dynamic(light: 0xF1E9EE, dark: 0x252C5E)     // --track
    // Text and the one pink, from the Pearl Design System iOS library (Oct 31:
    // text is plum #2E2547 in light mode, the action rose #B22757).
    static let ink = dynamic(light: 0x2E2547, dark: 0xFBF8F6)       // color/text/primary
    /// color/text/muted: mist/600 #514D67 in light (REFRESH-05; was mist/500
    /// #605D76, too faint on the gradient), mist/300 in dark.
    static let muted = dynamic(light: 0x514D67, dark: 0xB4B1CC)
    static let action = dynamic(light: 0xB22757, dark: 0xFF8FB1)    // --action
    static let onAction = dynamic(light: 0xFFFFFF, dark: 0x1C1A33)  // --on-action
    static let blush = Color(hex: 0xFFE4EC)                         // --blush
    static let answered = dynamic(light: 0xF1E9EE, dark: 0x252C5E)  // answered rows
    static let moneyIn = dynamic(light: 0x167A40, dark: 0x6EDB94)   // color/text/money-in (dark #6EDB94, Figma library; product owner 2026-11-09)
    static let caution = dynamic(light: 0x8A5A12, dark: 0xF3D9A4)   // --caution
    static let cautionBackground = dynamic(light: 0xFBECC8, dark: 0x3A2E14)

    static let nacre = LinearGradient(
        colors: [Color(hex: 0xFFD6E0), Color(hex: 0xE3D4FF), Color(hex: 0xCFF3EE)],
        startPoint: .topLeading, endPoint: .bottomTrailing)

    static let moneyOut = dynamic(light: 0xBE2634, dark: 0xFF7B72)  // color/text/money-out
    static let rose = Color(hex: 0xE2557F)                          // --rose-500 (icons, badges)
    static let suggested = Color(hex: 0xFF8FB1)                     // --rose-300, a guess's dashed outline
    static let rule = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(hex: 0x252C5E) : UIColor(white: 1, alpha: 0.8) })       // lines between rows in a card (REFRESH-05)
    /// The glass card's shadow colour, #664D99 (REFRESH-05: @10%, y 8, blur 20).
    static let cardShadow = Color(hex: 0x664D99)
    static let onBlush = Color(hex: 0x1C1A33)                       // --on-nacre
    static let bar = dynamic(light: 0xFFFFFF, dark: 0x151B44)       // --surface-card, the tab bar
    // REFRESH-02 (Design refresh kit 1088:1696), from the Pearl Design System
    // Color variables in Light and Dark mode.
    static let bubble = dynamic(light: 0xFFE4EC, dark: 0x4E2238)    // --blush, both modes
    static let champagne = Color(hex: 0xF3D9A4)                     // --champagne (Banner, 22% fill)
    static let borderStrong = Color(hex: 0x8A87A3)                  // --border-strong (the grabber)
    /// color/fill/control: the Close and ••• circles and the secondary button.
    static let control = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 120 / 255, green: 120 / 255, blue: 128 / 255, alpha: 0.36)
        : UIColor(red: 120 / 255, green: 120 / 255, blue: 128 / 255, alpha: 0.16) })

    // MARK: Type
    // Fraunces (display) and Figtree (text), as on the web, bundled in Fonts/.
    // Sizes are the web's in points, and scale with Dynamic Type.

    /// Fraunces SemiBold: page titles, questions and big amounts.
    static func display(_ style: Font.TextStyle = .largeTitle) -> Font {
        let size: CGFloat
        switch style {
        case .largeTitle: size = 30   // Cash flow
        case .title: size = 28        // Home, Needs a look, Profile
        case .title2: size = 24       // a question ("Was this spending?")
        case .title3: size = 22       // the amount on a sort card
        default: size = 17            // the numbers in a stat tile
        }
        return .custom("Fraunces-SemiBold", size: size, relativeTo: style)
    }

    static let title = display(.title2)
    static let heading = display(.headline)
    /// Fraunces Regular for headings (Oct 31: titles are Regular; amounts and
    /// the wordmark stay SemiBold). 34 Large Title, 28 Title 1, 22 Title 2.
    static func heading(_ size: CGFloat = 28, relativeTo style: Font.TextStyle = .title) -> Font {
        .custom("Fraunces-Regular", size: size, relativeTo: style)
    }

    /// A card's title on Home ("October so far"): Figtree, not Fraunces.
    static let cardTitle = Font.custom("Figtree-Regular", size: 20, relativeTo: .title3)

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
    static let radiusSort: CGFloat = 28     // --radius-lg, the sort card
    static let radiusTile: CGFloat = 20     // --radius-md
    static let radiusRow: CGFloat = 16
    static let radiusChoice: CGFloat = 12   // --radius-sm, an answer
    static let gutter: CGFloat = 16

    static func dynamic(light: UInt32, dark: UInt32) -> Color {
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
