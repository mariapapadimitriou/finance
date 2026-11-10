import SwiftUI
import UIKit

/// Pearl's iOS look for onboarding and signing in (Pearl iOS Handoff File,
/// Oct 30): "Iridescent pearl" in light, "Moonlit sea" in dark, pearl dust
/// and soft auras, frosted-glass cards with a nacre edge.
enum Nacre {
    // MARK: Colours

    /// Frosted glass: white at 72% in light, ocean at 66% in dark.
    static let glass = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 21 / 255, green: 27 / 255, blue: 68 / 255, alpha: 0.66)
        : UIColor(white: 1, alpha: 0.72) })
    static let glassEdge = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(white: 1, alpha: 0.14) : UIColor(white: 1, alpha: 0.8) })
    /// The pink hairline round a glass card (dark mode; light uses `horizontal`).
    static let edge = Color(hex: 0xFFC2D4)
    /// The line between rows in a card: glass/edge-light in light (REFRESH-05,
    /// color/border/subtle), unchanged in dark.
    static let separator = Pearl.border
    /// The strength meter and "Synced": seaglass teal.
    static let teal = Pearl.dynamic(light: 0x1F7A72, dark: 0x8FE3D6)
    static let mint = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 143 / 255, green: 227 / 255, blue: 214 / 255, alpha: 0.16)
        : UIColor(red: 210 / 255, green: 244 / 255, blue: 236 / 255, alpha: 0.9) })
    /// The circle behind a rose line icon (Privacy and notifications).
    static let roseWash = Color(UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 255 / 255, green: 143 / 255, blue: 177 / 255, alpha: 0.22)
        : UIColor(red: 178 / 255, green: 39 / 255, blue: 87 / 255, alpha: 0.1) })
    /// Light mode's primary button text, and dark mode's (ink on nacre).
    static let onNacre = Color(hex: 0x1C1A33)

    static let rose = Color(hex: 0xFFB6CC)
    static let lilac = Color(hex: 0xCDB9FF)
    static let seaglass = Color(hex: 0xA8E9DF)

    /// Nacre/Horizontal: the dark-mode button and the ring.
    static let horizontal = LinearGradient(
        colors: [Color(hex: 0xFFC2D4), Color(hex: 0xD9C6FF), Color(hex: 0xB8EDE6)],
        startPoint: .leading, endPoint: .trailing)

    /// "shine." in the welcome headline.
    static let shine = LinearGradient(
        stops: [.init(color: Color(hex: 0xA83A92), location: 0),
                .init(color: Color(hex: 0xC42F6A), location: 0.466),
                .init(color: Color(hex: 0xB22757), location: 0.726)],
        startPoint: .leading, endPoint: .trailing)

    // MARK: Type (the iOS text styles: 34, 28, 17, 15, 13, 11)

    static let largeTitle = Pearl.heading(34, relativeTo: .largeTitle)
    static let title = Pearl.heading(28, relativeTo: .title)
    static let title2 = Pearl.heading(22, relativeTo: .title2)
    static let body = Font.custom("Figtree-Regular", size: 17, relativeTo: .body)
    static let headline = Font.custom("Figtree-SemiBold", size: 17, relativeTo: .headline)
    static let textButton = Font.custom("Figtree-Medium", size: 16, relativeTo: .callout)
    static let subheadline = Font.custom("Figtree-Regular", size: 15, relativeTo: .subheadline)
    static let footnote = Font.custom("Figtree-Regular", size: 13, relativeTo: .footnote)
    /// Text/Label: a chip's or a pill's words.
    static let label = Font.custom("Figtree-Medium", size: 13, relativeTo: .footnote)
    static let caption1 = Font.custom("Figtree-Regular", size: 12, relativeTo: .caption)
    static let caption2 = Font.custom("Figtree-Medium", size: 11, relativeTo: .caption2)
}

// MARK: - Background

/// The iridescent background, its auras and its bubbles, behind a whole
/// screen. In light it is Iridescent/Light with the Pearl dust on top
/// (REFRESH-05: every light screen and sheet, as H-00 had it). Dark is
/// "Moonlit sea" with its own auras and bubbles, unchanged.
struct NacreBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        GeometryReader { geo in
            let w = geo.size.width
            ZStack(alignment: .topLeading) {
                if scheme == .dark {
                    // "Moonlit sea": an indigo night fading into moonlit blue.
                    LinearGradient(colors: [Color(hex: 0x12163F), Color(hex: 0x1C2F73), Color(hex: 0x245B8F)],
                                   startPoint: .top, endPoint: .bottom)
                    aura(size: 0.92 * w).offset(x: -0.15 * w, y: 0.05 * geo.size.height)
                    aura(size: 0.71 * w).offset(x: 0.41 * w, y: 0.49 * geo.size.height)
                    Image("Bubbles")
                        .resizable()
                        .frame(width: geo.size.width, height: geo.size.height)
                        .allowsHitTesting(false)
                } else {
                    // Iridescent/Light: rose → lilac → seaglass, at 114.76°
                    // (the as-built Home gradient, unchanged).
                    LinearGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass],
                                   startPoint: UnitPoint(x: -0.325, y: 0.324),
                                   endPoint: UnitPoint(x: 1.325, y: 0.676))
                    PearlDust(width: w)
                }
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }

    private func aura(size: CGFloat) -> some View {
        Circle()
            .fill(Color(hex: 0xD9C6FF).opacity(0.22))
            .frame(width: size, height: size)
            .blur(radius: size / 8)
    }
}

extension View {
    /// A screen on the iridescent background.
    func nacreScreen() -> some View {
        background(NacreBackground())
            .foregroundColor(Pearl.ink)
            .tint(Pearl.ink)
    }
}

// MARK: - The pearl

/// The open scallop with the pearl, glowing (Logo/Mark on O-01, A-01, A-08).
struct HeroShell: View {
    var width: CGFloat = 256

    var body: some View {
        let s = width / 256
        ZStack {
            Image("Glow").resizable().frame(width: 440 * s, height: 440 * s).offset(y: 4 * s)
            Ellipse()
                .fill(LinearGradient(colors: [.white.opacity(0.9), Nacre.lilac.opacity(0.5)],
                                     startPoint: .top, endPoint: .bottom))
                .frame(width: 300 * s, height: 230 * s)
                .blur(radius: 30 * s)
                .opacity(0.55)
            Ellipse()
                .fill(LinearGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass],
                                     startPoint: .leading, endPoint: .trailing))
                .frame(width: 220 * s, height: 34 * s)
                .blur(radius: 9 * s)
                .opacity(0.4)
                .offset(y: 118 * s)
            Image("LogoMark").resizable().frame(width: 256 * s, height: 213.333 * s)
        }
        .frame(width: 256 * s, height: 213.333 * s)
        .accessibilityHidden(true)
    }
}

/// "pearl" in Fraunces, ending in a pearl instead of a full stop.
struct Wordmark: View {
    var body: some View {
        HStack(alignment: .bottom, spacing: 1.8) {
            Text("pearl")
                .font(.custom("Fraunces-SemiBold", size: 26.27))
                .tracking(-0.53)
            Image("PearlDot").resizable().frame(width: 8.36, height: 13.14)
        }
        .foregroundColor(Pearl.ink)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Pearl")
    }
}

/// Closed → opening → open shell: where she is in setup, and the part's name.
struct ShellProgress: View {
    let part: Int
    let name: String

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .bottom, spacing: 12) {
                ForEach(Array(["ShellClosed", "ShellOpening", "LogoMark"].enumerated()), id: \.offset) { i, image in
                    Image(image).resizable()
                        .frame(width: 34, height: 28.33)
                        .opacity(i < part ? 1 : 0.3)
                }
            }
            Text("PART \(part) OF 3 · \(name.uppercased())")
                .font(Nacre.caption2).tracking(1.4)
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Part \(part) of 3, \(name)")
    }
}

/// A round frosted badge holding one line icon (mail, key, Face ID…).
struct IconOrb: View {
    let symbol: String
    var size: CGFloat = 64

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.34, weight: .light))
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(.ultraThinMaterial))
            .background(Circle().fill(Nacre.glass))
            .overlay(Circle().strokeBorder(
                AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                lineWidth: size > 80 ? 2 : 1.2).opacity(0.9))
            .shadow(color: Color(red: 0.4, green: 0.3, blue: 0.6).opacity(0.12), radius: 12, y: 6)
            .accessibilityHidden(true)
    }
}

// MARK: - Cards and rows

/// The glass a card is made of (REFRESH-05, C‴; the as-built H-00 card):
/// color/surface/card (white @72%) over one background blur, the
/// Nacre/Horizontal 1.2 pt edge and a #664D99 @10% shadow (y 8, blur 20).
/// Dark keeps what GlassCard drew before: ocean glass, the pink edge and the
/// softer shadow. One material per card; rows inside it never blur again.
struct GlassSurface: View {
    var radius: CGFloat = 26
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        shape.fill(Nacre.glass)
            .background(.ultraThinMaterial, in: shape)
            .overlay {
                if scheme == .dark {
                    shape.strokeBorder(Nacre.edge, lineWidth: 1.2)
                } else {
                    shape.strokeBorder(Nacre.horizontal, lineWidth: 1.2)
                }
            }
            .shadow(color: Pearl.cardShadow.opacity(scheme == .dark ? 0.12 : 0.10),
                    radius: scheme == .dark ? 12 : 20, y: 8)
    }
}

/// A frosted-glass card with the nacre edge (the "List section").
struct GlassCard<Content: View>: View {
    var spacing: CGFloat = 0
    var radius: CGFloat = 26
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: spacing, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .glassCard(radius: radius)
    }
}

extension View {
    /// Puts this content on a glass card: clipped to the card's shape, the
    /// glass (with its edge and shadow) behind it.
    func glassCard(radius: CGFloat = 26) -> some View {
        clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .background(GlassSurface(radius: radius))
    }

    /// A card that was solid white with a 1 pt border before REFRESH-05: in
    /// light it is now a glass card (S-03*, S-04*, S-40*, S-06r*, S-07r*,
    /// S-34*, H-00 and the rest); in dark it stays as it was.
    func pearlCard(radius: CGFloat = Pearl.radiusCard) -> some View {
        modifier(PearlCardStyle(radius: radius))
    }
}

private struct PearlCardStyle: ViewModifier {
    let radius: CGFloat
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        if scheme == .dark {
            content
                .background(shape.fill(Pearl.card))
                .clipShape(shape)
                .overlay(shape.stroke(Pearl.border, lineWidth: 1))
        } else {
            content.glassCard(radius: radius)
        }
    }
}

/// The 0.5pt line between rows, inset like an iOS list.
struct RowSeparator: View {
    var inset: CGFloat = 16

    var body: some View {
        Rectangle().fill(Nacre.separator).frame(height: 0.5).padding(.leading, inset)
    }
}

/// "Email   alex@example.com": a label and its field, right-aligned.
struct FieldRow: View {
    let label: String
    @Binding var text: String
    var prompt: String = ""
    var kind: Kind = .text
    var content: UITextContentType? = nil
    var tone: Color = Pearl.muted
    var submit: () -> Void = {}

    enum Kind { case text, email, secure }

    @State private var shown = false

    var body: some View {
        HStack(spacing: 12) {
            Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
            Group {
                if kind == .secure && !shown {
                    SecureField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                } else {
                    TextField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                }
            }
            .font(Nacre.body)
            .foregroundColor(tone)
            .multilineTextAlignment(.trailing)
            .textContentType(content)
            .keyboardType(kind == .email ? .emailAddress : .default)
            .textInputAutocapitalization(.never)
            .autocorrectionDisabled()
            .submitLabel(.next)
            .onSubmit(submit)
            .accessibilityLabel(label)
            if kind == .secure {
                Button { shown.toggle() } label: {
                    Image(systemName: shown ? "eye.slash" : "eye")
                        .font(.system(size: 16)).foregroundColor(Pearl.ink)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(shown ? "Hide password" : "Show password")
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 52)
    }
}

/// A short line under a field: a warning, a countdown or a reassurance.
struct Hint: View {
    let text: String
    var symbol = "exclamationmark.triangle"

    var body: some View {
        Label {
            Text(text).font(Nacre.subheadline).fixedSize(horizontal: false, vertical: true)
        } icon: {
            Image(systemName: symbol).font(.system(size: 14))
        }
        .foregroundColor(Pearl.ink)
    }
}

/// "TD" in a small round badge, for an account or a bank.
struct BankBadge: View {
    let text: String

    var body: some View {
        Text(text)
            .font(.custom("Figtree-Medium", size: 12))
            .foregroundColor(Pearl.ink)
            .frame(width: 32, height: 32)
            .background(Circle().fill(Pearl.track))
            .accessibilityHidden(true)
    }
}

/// "✓ Synced", "✓ Done": a small mint pill.
struct DonePill: View {
    let text: String

    var body: some View {
        Label(text, systemImage: "checkmark")
            .font(Nacre.footnote)
            .labelStyle(.titleAndIcon)
            .foregroundColor(Nacre.teal)
            .padding(.horizontal, 10).padding(.vertical, 4)
            .background(Capsule().fill(Nacre.mint))
    }
}

// MARK: - Buttons

/// The primary capsule: rose in light; nacre with ink text in dark.
struct NacreButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    @Environment(\.colorScheme) private var scheme
    var busy = false

    func makeBody(configuration: Configuration) -> some View {
        ZStack {
            configuration.label.opacity(busy ? 0 : 1)
            if busy { ProgressView().tint(scheme == .dark ? Nacre.onNacre : .white) }
        }
        .font(Nacre.headline)
        .foregroundColor(scheme == .dark ? Nacre.onNacre : .white)
        .frame(maxWidth: .infinity, minHeight: 52)
        .background {
            if scheme == .dark {
                Capsule().fill(Nacre.horizontal)
            } else {
                Capsule().fill(Pearl.action)
            }
        }
        .opacity(isEnabled ? (configuration.isPressed ? 0.85 : 1) : 0.5)
        .shadow(color: scheme == .dark ? Color(hex: 0xE3D4FF).opacity(0.35) : Pearl.action.opacity(0.28),
                radius: 6, y: 6)
        .contentShape(Capsule())
    }
}

/// A secondary action under the primary one: text only.
struct NacreTextButtonStyle: ButtonStyle {
    var tone: Color = Pearl.ink

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Nacre.textButton)
            .foregroundColor(tone)
            .frame(maxWidth: .infinity, minHeight: 44)
            .opacity(configuration.isPressed ? 0.6 : 1)
            .contentShape(Rectangle())
    }
}

/// The bottom of a screen: one primary action and, sometimes, one quieter one.
struct BottomActions<Primary: View, Secondary: View>: View {
    @ViewBuilder var primary: () -> Primary
    @ViewBuilder var secondary: () -> Secondary

    var body: some View {
        VStack(spacing: 6) {
            primary()
            secondary()
        }
        .padding(.horizontal, 16)
        .padding(.bottom, 8)
    }
}

extension BottomActions where Secondary == EmptyView {
    init(@ViewBuilder primary: @escaping () -> Primary) {
        self.primary = primary
        self.secondary = { EmptyView() }
    }
}

// MARK: - The code boxes (O-03, A-02)

/// Six boxes for an emailed code. One hidden field takes the digits, so
/// iOS can fill it from Mail (`.oneTimeCode`) and paste works.
struct CodeBoxes: View {
    @Binding var code: String
    var failed = false
    var onComplete: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        ZStack(alignment: .leading) {
            TextField("", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($focused)
                .foregroundColor(.clear)
                .tint(.clear)
                .accessibilityLabel("Six-digit code")
                .onChange(of: code) { value in
                    let digits = String(value.filter(\.isNumber).prefix(6))
                    if digits != value { code = digits }
                    if digits.count == 6 { onComplete() }
                }
            HStack(spacing: 12) {
                ForEach(0..<6, id: \.self) { i in
                    let chars = Array(code)
                    let current = i == min(chars.count, 5) && focused
                    ZStack {
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .fill(Nacre.glass)
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(failed && current ? Pearl.action : Nacre.glassEdge,
                                          lineWidth: failed && current ? 1.5 : 1)
                        if i < chars.count {
                            Text(String(chars[i])).font(Pearl.heading(26, relativeTo: .title2))
                        } else if current {
                            Rectangle().fill(Pearl.action).frame(width: 1.5, height: 26)
                        }
                    }
                    .frame(width: 44, height: 52)
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity, alignment: .leading)
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
        .onAppear { focused = true }
    }
}

// MARK: - The password meter (O-02, A-07)

/// Four segments and a word, then the three rules, each ticked as it's met.
struct PasswordMeter: View {
    let rules: PasswordRules

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack(spacing: 10) {
                HStack(spacing: 4) {
                    ForEach(0..<4, id: \.self) { i in
                        RoundedRectangle(cornerRadius: 2)
                            .fill(i < rules.segments ? (rules.ok ? Nacre.teal : Pearl.ink) : Nacre.glass)
                            .frame(height: 4)
                    }
                }
                Text(rules.label).font(Nacre.subheadline)
            }
            rule(met: rules.length,
                 text: rules.length ? "At least 12 characters" : "At least 12 characters · \(rules.more) more")
            rule(met: rules.common, text: "Not a common or leaked password")
            rule(met: rules.email, text: "Doesn’t include your email")
        }
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("Password strength: \(rules.label)")
    }

    private func rule(met: Bool, text: String) -> some View {
        HStack(spacing: 6) {
            Image(systemName: met ? "checkmark" : "circle")
                .font(.system(size: met ? 10 : 12, weight: met ? .semibold : .regular))
                .frame(width: 14)
            Text(text).font(Nacre.footnote)
        }
        .accessibilityLabel(met ? "\(text), met" : "\(text), not yet")
    }
}

extension PasswordRules {
    /// What the meter shows before the server has answered: length and the
    /// email checked here, "common" assumed fine until the server says not.
    static func local(_ password: String, email: String) -> PasswordRules {
        let length = password.count >= 12
        let local = email.split(separator: "@").first.map(String.init)?.lowercased() ?? ""
        let lower = password.lowercased()
        let mail = email.isEmpty || !(lower.contains(email.lowercased()) || (local.count >= 3 && lower.contains(local)))
        let ok = length && mail
        let label: String
        let segments: Int
        if !length {
            (segments, label) = (1, "Too short")
        } else if !mail {
            (segments, label) = (1, "Weak")
        } else {
            let kinds = [password.contains(where: \.isLowercase), password.contains(where: \.isUppercase),
                         password.contains(where: \.isNumber),
                         password.contains(where: { !$0.isLetter && !$0.isNumber })].filter { $0 }.count
            segments = min(2 + (password.count >= 16 ? 1 : 0) + (kinds >= 3 || password.count >= 20 ? 1 : 0), 4)
            label = [2: "Fair", 3: "Good", 4: "Strong"][segments] ?? "Fair"
        }
        return PasswordRules(length: length, common: true, email: mail, more: max(12 - password.count, 0),
                             ok: ok, segments: segments, label: label)
    }
}

// MARK: - A full screen

/// The layout every onboarding screen shares: content at the top, its
/// actions pinned to the bottom, all on the iridescent background.
struct NacreScreen<Content: View, Actions: View>: View {
    var scrolls = true
    @ViewBuilder var content: () -> Content
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 0) {
            if scrolls {
                ScrollView {
                    VStack(alignment: .leading, spacing: 16, content: content)
                        .padding(.horizontal, 16)
                        .padding(.top, 8)
                        .padding(.bottom, 24)
                }
                .scrollDismissesKeyboard(.interactively)
            } else {
                VStack(alignment: .leading, spacing: 16, content: content)
                    .padding(.horizontal, 16)
                    .padding(.top, 8)
                Spacer(minLength: 0)
            }
            actions()
        }
        .nacreScreen()
        .navigationBarTitleDisplayMode(.inline)
    }
}

/// A centred message screen: a picture, a title and a line (O-09a, A-04, A-06…).
struct MessageBlock<Art: View>: View {
    let title: String
    var line: String? = nil
    @ViewBuilder var art: () -> Art

    var body: some View {
        VStack(spacing: 12) {
            art().padding(.bottom, 12)
            Text(title).font(Nacre.title).tracking(0.4).multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            if let line = line {
                Text(line).font(Nacre.body).multilineTextAlignment(.center)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 40)
    }
}
