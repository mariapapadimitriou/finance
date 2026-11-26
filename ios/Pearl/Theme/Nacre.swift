import SwiftUI
import UIKit

/// Pearl's iOS look for onboarding and signing in (Pearl iOS Handoff File,
/// Oct 30): "Iridescent pearl" in light, "Moonlit sea" in dark, pearl dust
/// and soft auras, frosted-glass cards with a nacre edge.
enum Nacre {
    // MARK: Colours

    /// A+ `card`: white glass @80% in light, ocean @72% in dark.
    static let glass = APlus.card
    /// A+ `card-line`: the 1 pt line inside a card or a glass circle.
    static let glassEdge = APlus.cardLine
    /// The pink hairline round a glass card (pre-A+; nothing draws it now).
    static let edge = Color(hex: 0xFFC2D4)
    /// A+ `separator`: the 0.5 pt line between rows in a card.
    static let separator = APlus.separator
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

/// The page behind a whole screen. A+ (REDESIGN-08, dirA.css `--ground`):
/// the nacre softened with a white veil in light, the night with a lilac
/// glow in dark (APGround). The Pearl dust, auras and bubbles are gone.
struct NacreBackground: View {
    var kind: APGroundKind = .flat

    var body: some View {
        APGround(kind: kind)
    }
}

extension View {
    /// A screen on the A+ ground; its switches are the A+ switch. TEST-38:
    /// what scrolls under the status bar fades into the ground. `ground`
    /// (dirA.css): flat for working screens and pushed pages, `.wash` for a
    /// tab root with the profile circle, `.nacre` for a moment.
    func nacreScreen(_ ground: APGroundKind = .flat) -> some View {
        scrollEdgeFade(ground)
            .background(NacreBackground(kind: ground))
            .foregroundColor(Pearl.ink)
            .tint(Pearl.ink)
            .toggleStyle(APToggleStyle())
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
    /// The part is done and its shell opens (Your accounts v2, note
    /// 1415:88764: "These look right" opens the third shell with a soft
    /// 350 ms spring). The caller animates it; with Reduce Motion the shell
    /// fades instead of moving.
    var opened = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .bottom, spacing: 12) {
                ForEach(Array(["ShellClosed", "ShellOpening", "LogoMark"].enumerated()), id: \.offset) { i, image in
                    let opening = opened && i == part - 1
                    Image(image).resizable()
                        .frame(width: 34, height: 28.33)
                        .scaleEffect(opening && !reduceMotion ? 1.22 : 1, anchor: .bottom)
                        .opacity(i < part ? (opening && reduceMotion ? 0.55 : 1) : 0.3)
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

/// The glass a card is made of: since A+ (REDESIGN-08) the one A+ card,
/// `card` over one blur, radius 24, its 1 pt `card-line` and
/// `shadow-card-a`. No nacre edge. Rows inside it never blur again.
struct GlassSurface: View {
    var radius: CGFloat = Pearl.radiusCard

    var body: some View {
        APCardSurface(radius: radius)
    }
}

/// A grouped list on the A+ card (the "List section").
struct GlassCard<Content: View>: View {
    var spacing: CGFloat = 0
    var radius: CGFloat = Pearl.radiusCard
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
    func glassCard(radius: CGFloat = Pearl.radiusCard) -> some View {
        apCard(radius: radius)
    }

    /// The card every screen used before A+ (white with a border, then the
    /// REFRESH-05 glass): now the one A+ card, light and dark.
    func pearlCard(radius: CGFloat = Pearl.radiusCard) -> some View {
        apCard(radius: radius)
    }
}

/// The 0.5 pt A+ `separator` between rows, inset like an iOS list (68
/// after a face, 16 without).
struct RowSeparator: View {
    var inset: CGFloat = 16

    var body: some View {
        Rectangle().fill(Nacre.separator).frame(height: 0.5).padding(.leading, inset)
            .accessibilityHidden(true)
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
    @FocusState private var focused: Bool

    /// A+ (REDESIGN-09, G6-SignIn): the label in `muted` 13 over a visible
    /// well, 44 high; focus draws the 2 pt action outline.
    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
                .accessibilityHidden(true)
            well
                .padding(.horizontal, 14)
                .frame(minHeight: 44)
                .wellStyle(focused: focused)
                .contentShape(Rectangle())
                .onTapGesture { focused = true }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 8)
    }

    private var well: some View {
        HStack(spacing: 8) {
            Group {
                if kind == .secure && !shown {
                    SecureField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                } else {
                    TextField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                }
            }
            .font(Nacre.body)
            .foregroundColor(tone == Pearl.muted ? Pearl.ink : tone)
            .tint(Pearl.action)
            .focused($focused)
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
                        .font(.system(size: 16)).foregroundColor(Pearl.muted)
                        .tapTarget(vertical: 12, horizontal: 8)
                }
                .buttonStyle(.plain)
                .accessibilityLabel(shown ? "Hide password" : "Show password")
            }
        }
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

/// The primary capsule, A+ `.btn` (APPrimaryLook): `action` with
/// `on-action` words in both modes (rose / white in light, pink / ink in
/// dark), 50 high; while busy, a spinner in place of the words.
struct NacreButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var busy = false

    func makeBody(configuration: Configuration) -> some View {
        ZStack {
            configuration.label.opacity(busy ? 0 : 1)
            if busy { ProgressView().tint(Pearl.onAction) }
        }
        .modifier(APPrimaryLook(enabled: isEnabled || busy, pressed: configuration.isPressed))
    }
}

/// A quiet action under the primary one, A+ `.quiet`: words only, `link`
/// 15/500, 44 tall to tap.
struct NacreTextButtonStyle: ButtonStyle {
    var tone: Color = Pearl.link

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
            .foregroundColor(tone)
            .frame(maxWidth: .infinity, minHeight: 44)
            .opacity(configuration.isPressed ? 0.6 : 1)
            .contentShape(Rectangle())
    }
}

extension View {
    /// Grows what can be tapped to at least 44 × 44 pt without moving
    /// anything (UI audit, tap targets): the padding widens the tap shape and
    /// the matching negative padding gives the layout back its old size. Use
    /// it on a button's label, so the button itself takes the wider shape.
    func tapTarget(top: CGFloat = 0, leading: CGFloat = 0,
                   bottom: CGFloat = 0, trailing: CGFloat = 0) -> some View {
        padding(EdgeInsets(top: top, leading: leading, bottom: bottom, trailing: trailing))
            .contentShape(Rectangle())
            .padding(EdgeInsets(top: -top, leading: -leading, bottom: -bottom, trailing: -trailing))
    }

    /// The same, evenly on each side.
    func tapTarget(vertical: CGFloat, horizontal: CGFloat = 0) -> some View {
        tapTarget(top: vertical, leading: horizontal, bottom: vertical, trailing: horizontal)
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
            // A+ `.code` (G6-Code): six wells 46 × 56, radius 12, the digit
            // in Fraunces 28/600; the current one has the 2 pt action outline
            // and caret; a wrong code outlines them all in danger.
            HStack(spacing: 8) {
                ForEach(0..<6, id: \.self) { i in
                    let chars = Array(code)
                    let current = i == min(chars.count, 5) && focused
                    let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
                    ZStack {
                        shape.fill(APlus.well)
                        shape.strokeBorder(failed ? Pearl.danger : (current ? Pearl.action : APlus.wellLine),
                                           lineWidth: failed || current ? 2 : 1)
                        if i < chars.count {
                            Text(String(chars[i])).font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title2))
                        } else if current {
                            Rectangle().fill(Pearl.action).frame(width: 2, height: 28)
                        }
                    }
                    .frame(width: 46, height: 56)
                }
            }
            .frame(maxWidth: .infinity)
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
        .nacreScreen(.nacre)
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
            // A+ `.ptitle` (G6-Offline, G6-Linked): Fraunces 34 regular, the
            // line in `muted` 17.
            Text(title).font(Nacre.largeTitle).multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            if let line = line {
                Text(line).font(Nacre.body).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
                    .padding(.horizontal, 20)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 40)
    }
}
