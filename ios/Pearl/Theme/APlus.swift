import SwiftUI
import UIKit

// A+ · the chosen redesign (REDESIGN-02 to 10, product owner 2026-11-18;
// Pearl Design System "A+ · the chosen redesign", tokens.json A+ colours).
// Stage 1: the tokens and the reusable pieces. Screens move onto them in
// later stages; nothing here changes a screen that doesn't use it.

/// The A+ colour tokens, light and dark (tokens.json, "A+").
enum APlus {
    /// `card`: white glass 80% / ocean 72%, over one blur.
    static let card = rgba(light: (255, 255, 255, 0.80), dark: (21, 27, 68, 0.72))
    /// `card-line`: the card's 1 pt inner line, tiles' hairline, the profile circle's disc.
    static let cardLine = rgba(light: (255, 255, 255, 0.95), dark: (255, 255, 255, 0.08))
    /// `separator`: the 0.5 pt row line inside a card (inset 68 after a face, 16 without).
    static let separator = rgba(light: (46, 37, 71, 0.09), dark: (255, 255, 255, 0.08))
    /// `chip`: chips at rest, the segmented track, the Counts pill.
    static let chip = rgba(light: (46, 37, 71, 0.06), dark: (255, 255, 255, 0.08))
    /// `track-soft`: the empty part of the sorting streak and the paid-back bar.
    static let trackSoft = rgba(light: (46, 37, 71, 0.08), dark: (255, 255, 255, 0.10))
    /// `face`: the 40 pt initials disc for merchants and people.
    static let face = Pearl.dynamic(light: 0xF3E8EE, dark: 0x262E63)
    /// `tab-lozenge`: the glass under the selected tab (the system draws it on iOS 26).
    static let tabLozenge = rgba(light: (160, 140, 235, 0.26), dark: (255, 255, 255, 0.12))
    /// `streak-from` → `streak-to`: the sorting streak's lit dashes.
    static let streakFrom = Color(hex: 0xFF8FB1)
    static let streakTo = Color(hex: 0xC9A8FF)
    /// `well` / `well-line` (REDESIGN-09): every place she can type.
    static let well = rgba(light: (46, 37, 71, 0.05), dark: (0, 0, 0, 0.24))
    static let wellLine = rgba(light: (46, 37, 71, 0.18), dark: (255, 255, 255, 0.18))
    /// `action-wash`: the circle behind an A+ line icon (`.icon`), the inline Yes.
    static let actionWash = rgba(light: (178, 39, 87, 0.10), dark: (255, 143, 177, 0.10))
    /// `money-in` @14%: a good-news icon's circle (`.icon.good`).
    static let goodWash = rgba(light: (22, 122, 64, 0.14), dark: (110, 219, 148, 0.14))
    /// The profile circle's disc in dark (ProfileCircle README).
    static let circleDisc = rgba(light: (255, 255, 255, 0.80), dark: (28, 36, 89, 1))

    /// The nacre ring and dots: rose → lilac → seaglass.
    static let nacreRing = AngularGradient(
        colors: [Color(hex: 0xFFB6CC), Color(hex: 0xCDB9FF), Color(hex: 0xA8E9DF), Color(hex: 0xFFB6CC)],
        center: .center)
    static let nacreDot = LinearGradient(
        colors: [Color(hex: 0xFF8FB1), Color(hex: 0xC9A8FF), Color(hex: 0x8FE0D4)],
        startPoint: .topLeading, endPoint: .bottomTrailing)

    typealias RGBA = (r: CGFloat, g: CGFloat, b: CGFloat, a: CGFloat)

    static func rgba(light: RGBA, dark: RGBA) -> Color {
        Color(UIColor { t in
            let c = t.userInterfaceStyle == .dark ? dark : light
            return UIColor(red: c.r / 255, green: c.g / 255, blue: c.b / 255, alpha: c.a)
        })
    }
}

// MARK: - Card

/// A+ `Card`: the one card. `card` fill over one blur, radius 24, a 1 pt
/// `card-line` inside, `shadow-card-a` (light: 0 1 2 @4% + 0 10 28 #664D99
/// @10%; dark: 0 10 28 black @22%). No nacre edge. Rows never blur again.
struct APCardSurface: View {
    var radius: CGFloat = Pearl.radiusCard

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        shape.fill(APlus.card)
            .background(.ultraThinMaterial, in: shape)
            .overlay(shape.strokeBorder(APlus.cardLine, lineWidth: 1))
            .modifier(APCardShadow())
    }
}

/// `shadow-card-a`: light 0 1 2 ink @4% + 0 10 28 #664D99 @10%; dark 0 10 28 black @22%.
struct APCardShadow: ViewModifier {
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content
            .shadow(color: scheme == .dark ? .black.opacity(0.22) : Pearl.cardShadow.opacity(0.10), radius: 14, y: 10)
            .shadow(color: scheme == .dark ? .clear : Pearl.ink.opacity(0.04), radius: 1, y: 1)
    }
}

// MARK: - Ground

/// A+ `--ground` (dirA.css): the page. Light: the nacre (rose, lilac,
/// seaglass at 114.76°) softened by a white veil (50% → 22% at 45% → 34%).
/// Dark: the night (#12163F → #172566 at 55% → #1D4A7D) with a lilac glow
/// at the top right. No dust and no bubbles in A+.
struct APGround: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        ZStack {
            if scheme == .dark {
                LinearGradient(stops: [.init(color: Color(hex: 0x12163F), location: 0),
                                       .init(color: Color(hex: 0x172566), location: 0.55),
                                       .init(color: Color(hex: 0x1D4A7D), location: 1)],
                               startPoint: .top, endPoint: .bottom)
                GeometryReader { g in
                    RadialGradient(colors: [Color(hex: 0xD9C6FF).opacity(0.16), .clear],
                                   center: UnitPoint(x: 0.8, y: 0), startRadius: 0,
                                   endRadius: max(g.size.width * 0.72, g.size.height * 0.36))
                }
            } else {
                APGround.nacre
                LinearGradient(stops: [.init(color: .white.opacity(0.50), location: 0),
                                       .init(color: .white.opacity(0.22), location: 0.45),
                                       .init(color: .white.opacity(0.34), location: 1)],
                               startPoint: .top, endPoint: .bottom)
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }

    /// The nacre at 114.76°, as the boards draw it.
    static let nacre = LinearGradient(colors: [Color(hex: 0xFFB6CC), Color(hex: 0xCDB9FF), Color(hex: 0xA8E9DF)],
                                      startPoint: UnitPoint(x: -0.325, y: 0.324),
                                      endPoint: UnitPoint(x: 1.325, y: 0.676))
}

/// A+ `.sheet` (kit.css): a Pearl sheet's surface. Light: the nacre under a
/// white veil (66% → 44%); dark: #1C2F73 → #12163F.
struct APSheetGround: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        ZStack {
            if scheme == .dark {
                LinearGradient(colors: [Color(hex: 0x1C2F73), Color(hex: 0x12163F)], startPoint: .top, endPoint: .bottom)
            } else {
                APGround.nacre
                LinearGradient(colors: [.white.opacity(0.66), .white.opacity(0.44)], startPoint: .top, endPoint: .bottom)
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

/// A+ `.glassbtn`: the 44 pt glass circle under Close, Back and •••: `card`
/// fill, its 1 pt line and the card's shadow.
struct APGlassCircle: View {
    var size: CGFloat = 44

    var body: some View {
        Circle().fill(APlus.card)
            .overlay(Circle().strokeBorder(APlus.cardLine, lineWidth: 1))
            .modifier(APCardShadow())
            .frame(width: size, height: size)
    }
}

/// A+ Back on a pushed page: the chevron in the 44 pt glass circle.
struct APBackButton: View {
    /// The UI tests' handle ("profile-back", "onboarding-back"); optional.
    var identifier: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(APGlassCircle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel("Back")
        .accessibilityIdentifier(identifier ?? "back")
    }
}

/// A+ `.icon`: a 36 pt disc holding an 18 pt line icon, in `tone` on
/// `tone` @10% (`action-wash` for rose). `wash` sets the disc for `.icon.warn`
/// (caution on `caution-background`) and `.icon.good` (money-in @14%).
struct APIcon: View {
    let symbol: String
    var tone: Color = Pearl.action
    var wash: Color? = nil

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: 16, weight: .regular))
            .foregroundColor(tone)
            .frame(width: 36, height: 36)
            .background(Circle().fill(wash ?? tone.opacity(0.10)))
            .accessibilityHidden(true)
    }

    /// `.icon.warn`.
    static func warn(_ symbol: String) -> APIcon {
        APIcon(symbol: symbol, tone: Pearl.caution, wash: Pearl.cautionBackground)
    }

    /// `.icon.good`.
    static func good(_ symbol: String) -> APIcon {
        APIcon(symbol: symbol, tone: Pearl.moneyIn, wash: APlus.goodWash)
    }
}

// MARK: - Button looks

/// A+ `.btn`: the one primary capsule. `action` with `on-action` words,
/// 50 high, 17/600; light casts 0 6 14 action @22%, dark none. Disabled 40%.
struct APPrimaryLook: ViewModifier {
    var enabled = true
    var pressed = false
    @Environment(\.colorScheme) private var scheme

    func body(content: Content) -> some View {
        content
            .font(.custom("Figtree-SemiBold", size: 17, relativeTo: .headline))
            .foregroundColor(Pearl.onAction)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 24)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Capsule().fill(Pearl.action))
            .shadow(color: scheme == .dark || !enabled ? .clear : Pearl.action.opacity(0.22), radius: 7, y: 6)
            .opacity(enabled ? (pressed ? 0.85 : 1) : 0.4)
            .contentShape(Capsule())
    }
}

/// A+ `.btn2`: the secondary capsule, `control` fill with ink words.
struct APSecondaryLook: ViewModifier {
    var enabled = true
    var pressed = false

    func body(content: Content) -> some View {
        content
            .font(.custom("Figtree-SemiBold", size: 17, relativeTo: .headline))
            .foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 24)
            .frame(maxWidth: .infinity, minHeight: 50)
            .background(Capsule().fill(Pearl.control))
            .opacity(enabled ? (pressed ? 0.7 : 1) : 0.5)
            .contentShape(Capsule())
    }
}

// MARK: - Switch

/// A+ `.sw`: the switch, 51 × 31, `action` when on, `control` when off.
/// Every Toggle on a Pearl screen draws it (`nacreScreen()` sets it).
struct APToggleStyle: ToggleStyle {
    func makeBody(configuration: Configuration) -> some View {
        Button { configuration.isOn.toggle() } label: {
            HStack(spacing: 12) {
                configuration.label
                Spacer(minLength: 8)
                ZStack(alignment: configuration.isOn ? .trailing : .leading) {
                    Capsule().fill(configuration.isOn ? Pearl.action : Pearl.control)
                        .frame(width: 51, height: 31)
                    Circle().fill(Color.white)
                        .shadow(color: .black.opacity(0.15), radius: 4, y: 3)
                        .frame(width: 27, height: 27)
                        .padding(2)
                }
                .animation(.easeOut(duration: 0.15), value: configuration.isOn)
            }
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityRepresentation { Toggle(isOn: configuration.$isOn) { configuration.label } }
    }
}

/// Rows of one kind on the A+ card. A card shows only when it has something in it.
struct APCard<Content: View>: View {
    var radius: CGFloat = Pearl.radiusCard
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .apCard(radius: radius)
    }
}

extension View {
    /// Puts this content on the A+ card.
    func apCard(radius: CGFloat = Pearl.radiusCard) -> some View {
        clipShape(RoundedRectangle(cornerRadius: radius, style: .continuous))
            .background(APCardSurface(radius: radius))
    }
}

/// The 0.5 pt `separator` between rows: inset 68 after a face, 16 without.
struct APSeparator: View {
    var afterFace = true

    var body: some View {
        Rectangle().fill(APlus.separator).frame(height: 0.5)
            .padding(.leading, afterFace ? 68 : 16)
            .accessibilityHidden(true)
    }
}

// MARK: - Section label

/// A+ `SectionLabel`: caps outside the card (`label` 13/500, tracked 0.78,
/// `muted`, 4 in), with its quiet action on the right in `link` 15/500,
/// 44 tall to tap: Select, Edit split, See the list, Clear.
struct APSectionLabel: View {
    let text: String
    var action: String? = nil
    var act: () -> Void = {}

    var body: some View {
        HStack(alignment: .center) {
            Text(text.uppercased())
                .font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 8)
            if let action = action {
                Button(action, action: act)
                    .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                    .foregroundColor(Pearl.link)
                    .buttonStyle(.plain)
                    .frame(minHeight: 44)
                    .padding(.vertical, -13)
                    .contentShape(Rectangle())
            }
        }
        .frame(minHeight: 18)
        .padding(.horizontal, 4)
    }
}

// MARK: - Payment row

/// A+ `PaymentRow`: face 40, name over line, every amount on one right edge,
/// nothing after it. The whole row is the tap target (it opens what the •••
/// used to). Spending is plum with −, money in green with +, a transfer
/// muted ⇄ with no sign, what doesn't count muted with no sign. Never red.
struct APPaymentRow: View {
    enum Money {
        case out(Double), into(Double), moved(Double), uncounted(Double)
    }

    let name: String
    var line: String? = nil
    var lineTone: Color = Pearl.muted
    let money: Money
    /// A guess under the line (the dashed GuessChip); the amount then aligns with the name.
    var guess: String? = nil

    var body: some View {
        HStack(alignment: guess == nil ? .center : .top, spacing: 12) {
            APFace(name: name, transfer: isTransfer)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                if let line = line {
                    Text(line).font(Nacre.subheadline).foregroundColor(lineTone).lineLimit(1)
                }
                if let guess = guess {
                    GuessChip(label: guess, question: true).padding(.top, 4)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(APPaymentRow.words(money))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(APPaymentRow.tone(money))
                .pearlAmountFit().fixedSize()
                .padding(.top, guess == nil ? 0 : 9)
                .accessibilityLabel(APPaymentRow.spoken(money))
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var isTransfer: Bool {
        if case .moved = money { return true }
        return false
    }

    static func words(_ m: Money) -> String {
        switch m {
        case .out(let v): return "\u{2212}" + Format.amount(v)
        case .into(let v): return "+" + Format.amount(v)
        case .moved(let v): return "\u{21C4} " + Format.amount(v)
        case .uncounted(let v): return Format.amount(v)
        }
    }

    static func tone(_ m: Money) -> Color {
        switch m {
        case .out: return Pearl.moneyOut
        case .into: return Pearl.moneyIn
        case .moved, .uncounted: return Pearl.muted
        }
    }

    static func spoken(_ m: Money) -> String {
        switch m {
        case .out(let v): return "spent " + Format.amount(v)
        case .into(let v): return "came in " + Format.amount(v)
        case .moved(let v): return "moved " + Format.amount(v)
        case .uncounted(let v): return Format.amount(v) + ", doesn’t count"
        }
    }
}

/// The 40 pt A+ face: initials 14/500 on `face`, or ⇄ for a transfer.
struct APFace: View {
    let name: String
    var transfer = false
    var size: CGFloat = 40

    var body: some View {
        Text(transfer ? "\u{21C4}" : APFace.initials(name))
            .font(.custom("Figtree-Medium", size: size * 0.35))
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(APlus.face))
            .accessibilityHidden(true)
    }

    /// Up to two letters from the first two words ("Uber Eats" → "UE"); one
    /// word gives its first two ("Sam" → "SA", G2 boards).
    static func initials(_ name: String) -> String {
        let words = name.split { !$0.isLetter && !$0.isNumber }.prefix(2)
        if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        let out = words.compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "\u{00B7}" : out
    }
}

// MARK: - Buttons

/// A+ Primary: unchanged from the built one (rose capsule, 50 high, one per
/// screen; busy words with a spinner). The Secondary is `control`.
typealias APPrimaryButtonStyle = PearlPrimaryButtonStyle
typealias APSecondaryButtonStyle = PearlSecondaryButtonStyle

// MARK: - Sorting streak

/// A+ `SortStreak` (from B): 12 dashes, lit = sorted ÷ (sorted + to sort)
/// rounded to twelfths. Full: 8 high, 4 apart. Mini (Cash flow's "need a
/// look" row): 108 wide, 5 high, 2 apart. VoiceOver: "40 of 48 sorted"
/// (never the only place the count is said).
struct SortStreak: View {
    let sorted: Int
    let toSort: Int
    var mini = false

    static let dashes = 12

    /// How many of the 12 dashes are lit.
    static func lit(sorted: Int, toSort: Int) -> Int {
        let total = max(0, sorted) + max(0, toSort)
        guard total > 0 else { return 0 }
        let share = Double(max(0, sorted)) / Double(total)
        return min(dashes, max(0, Int((share * Double(dashes)).rounded())))
    }

    var body: some View {
        let on = SortStreak.lit(sorted: sorted, toSort: toSort)
        let height: CGFloat = mini ? 5 : 8
        HStack(spacing: mini ? 2 : 4) {
            ForEach(0..<SortStreak.dashes, id: \.self) { i in
                Capsule()
                    .fill(i < on
                          ? AnyShapeStyle(LinearGradient(colors: [APlus.streakFrom, APlus.streakTo],
                                                         startPoint: .leading, endPoint: .trailing))
                          : AnyShapeStyle(APlus.trackSoft))
                    .frame(height: height)
            }
        }
        .frame(width: mini ? 108 : nil)
        .accessibilityElement()
        .accessibilityLabel("\(max(0, sorted)) of \(max(0, sorted) + max(0, toSort)) sorted")
    }
}

// MARK: - Paid-back bar

/// A+ `PaidBackBar` (from B): one segment per row of a split card, in the
/// rows' order, 10 high, 3 apart, radius 4. Your share plum; paid in full
/// green; part paid rose filled to the part; owes empty; let go muted @35%.
struct PaidBackBar: View {
    enum Segment: Equatable {
        case yours
        case paid
        /// 0…1 of their share paid so far.
        case part(Double)
        case owes
        case letGo
    }

    let segments: [Segment]
    /// "Paid back so far: Jo all, Sam a third, Priya nothing yet, Alex let go".
    let spoken: String

    var body: some View {
        HStack(spacing: 3) {
            ForEach(Array(segments.enumerated()), id: \.offset) { _, s in
                GeometryReader { g in
                    ZStack(alignment: .leading) {
                        RoundedRectangle(cornerRadius: 4, style: .continuous).fill(APlus.trackSoft)
                        RoundedRectangle(cornerRadius: 4, style: .continuous)
                            .fill(PaidBackBar.fill(s))
                            .frame(width: g.size.width * PaidBackBar.filled(s))
                    }
                }
            }
        }
        .frame(height: 10)
        .accessibilityElement()
        .accessibilityLabel(spoken)
    }

    static func filled(_ s: Segment) -> CGFloat {
        switch s {
        case .yours, .paid, .letGo: return 1
        case .part(let p): return CGFloat(min(1, max(0, p)))
        case .owes: return 0
        }
    }

    static func fill(_ s: Segment) -> Color {
        switch s {
        case .yours: return Pearl.moneyOut
        case .paid: return Pearl.moneyIn
        case .part: return Pearl.action
        case .owes: return .clear
        case .letGo: return Pearl.muted.opacity(0.35)
        }
    }
}

// MARK: - Toast

/// A+ `Toast`: the ink toast with Undo, the one place Pearl says "done".
/// It is the built one (UN-01): ink fill, `on-ink` words, 6 s (15 s with
/// VoiceOver), Undo as an accessibility action, swipe to dismiss.
typealias APToast = UndoToast

// MARK: - Fields (REDESIGN-09)

/// A+ `TextField` / `AmountField` / `SearchField`: a visible well. `well`
/// fill, 1 pt `well-line`, radius 12 (search: a capsule), at least 44 high,
/// 14 at the sides, the placeholder in `muted`. Focus: a 2 pt `action`
/// outline and the `action` caret. Error: a 2 pt `danger` outline and the
/// reason under it in `danger` (only a real error). Disabled: 45%.
struct PearlField: View {
    enum Kind: Equatable {
        case text
        /// A `$` prefix in `muted`, the decimal pad, right-aligned.
        case amount
        /// A leading magnifier; a capsule.
        case search
    }

    var label: String? = nil
    let placeholder: String
    @Binding var text: String
    var kind: Kind = .text
    var error: String? = nil
    var identifier: String? = nil
    var submit: () -> Void = {}
    /// Focus it as it appears (G2-PB30-r: the search a link opened).
    var autofocus = false

    @FocusState private var focused: Bool
    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            if let label = label {
                Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            }
            HStack(spacing: 8) {
                if kind == .search {
                    Image(systemName: "magnifyingglass").font(.system(size: 16)).foregroundColor(Pearl.muted)
                        .accessibilityHidden(true)
                }
                if kind == .amount {
                    Spacer(minLength: 0)
                    Text("$").font(Nacre.headline).foregroundColor(Pearl.muted).accessibilityHidden(true)
                }
                TextField("", text: $text, prompt: Text(placeholder).foregroundColor(Pearl.muted))
                    .font(kind == .amount ? Nacre.headline : Nacre.body)
                    .foregroundColor(Pearl.ink)
                    .tint(Pearl.action)
                    .multilineTextAlignment(kind == .amount ? .trailing : .leading)
                    .keyboardType(kind == .amount ? .decimalPad : .default)
                    .submitLabel(kind == .search ? .search : .done)
                    .fixedSize(horizontal: kind == .amount, vertical: false)
                    .focused($focused)
                    .onSubmit(submit)
                    .accessibilityLabel(label ?? placeholder)
                    .accessibilityIdentifier(identifier ?? (label ?? placeholder))
            }
            .padding(.horizontal, 14)
            .frame(minHeight: 44)
            .wellStyle(focused: focused, error: error != nil, capsule: kind == .search)
            .contentShape(Rectangle())
            .onTapGesture { focused = true }
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.danger)
                    .padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .opacity(isEnabled ? 1 : 0.45)
        .onAppear {
            guard autofocus else { return }
            DispatchQueue.main.asyncAfter(deadline: .now() + 0.25) { focused = true }
        }
    }
}

extension View {
    /// The well behind a field: rest, focus (2 pt action), error (2 pt danger).
    /// For fields laid out by hand (the Pearl composer).
    func wellStyle(focused: Bool, error: Bool = false, capsule: Bool = false) -> some View {
        modifier(WellStyle(focused: focused, error: error, capsule: capsule))
    }
}

private struct WellStyle: ViewModifier {
    let focused: Bool
    let error: Bool
    let capsule: Bool

    func body(content: Content) -> some View {
        let radius: CGFloat = capsule ? 22 : Pearl.radiusChoice
        let shape = RoundedRectangle(cornerRadius: radius, style: .continuous)
        content
            .background(shape.fill(APlus.well))
            .overlay(
                shape.strokeBorder(error ? Pearl.danger : (focused ? Pearl.action : APlus.wellLine),
                                   lineWidth: error || focused ? 2 : 1)
            )
    }
}

// MARK: - Calm state

/// A+ `CalmState`: nothing needs her. One calm line under the orb, `muted`
/// 17. No empty cards, no "nothing here" cards.
struct CalmState: View {
    var line = "You\u{2019}re all caught up."

    var body: some View {
        Text(line)
            .font(Nacre.body).foregroundColor(Pearl.muted)
            .multilineTextAlignment(.center)
            .frame(maxWidth: .infinity)
            .padding(.top, 24)
    }
}

// MARK: - Sheet (A+)

/// A+ `Sheet` header: the title centred in `ios-headline` 17/600 with the
/// ✕ on the right (G7 "Start a new chat?"). The body and the Primary /
/// Secondary buttons are the built PearlSheet's.
struct APSheetTitle: View {
    let title: String
    let close: () -> Void

    var body: some View {
        ZStack {
            Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.horizontal, 52)
                .accessibilityAddTraits(.isHeader)
            HStack {
                Spacer()
                PearlCloseButton(action: close)
            }
        }
        .frame(minHeight: 44)
    }
}

/// A+ confirmation on a Pearl sheet: the centred title, one message, the
/// Primary naming the action and a Secondary that keeps things as they are
/// (✕ and a swipe down do the same). Never a stock alert.
struct APConfirmSheet: View {
    let title: String
    let message: String
    let primary: String
    let secondary: String
    let onConfirm: () -> Void
    let onClose: () -> Void

    var body: some View {
        PearlSheet {
            APSheetTitle(title: title, close: onClose)
            Text(message).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
        } footer: {
            PearlSheetButtons(primary: primary, secondary: secondary,
                              onPrimary: onConfirm, onSecondary: onClose)
        }
    }
}

// MARK: - Nacre dot

/// The 10 pt nacre dot: on the profile circle when Profile needs her, on the
/// Pearl tab when Pearl has a suggestion. Never a number.
struct NacreDot: View {
    var ring: Color = APlus.card

    var body: some View {
        Circle().fill(APlus.nacreDot)
            .frame(width: 10, height: 10)
            .overlay(Circle().strokeBorder(ring, lineWidth: 2).padding(-2))
            .accessibilityHidden(true)
    }
}
