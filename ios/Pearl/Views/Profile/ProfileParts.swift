import SwiftUI

// The Profile pages' look, A+ (REDESIGN-11, -12, -13; Claude Design boards
// G5-*, G5b-*, G6-*, kit.css): the A+ card of rows, each row led by a 36 pt
// line icon on the action wash or a 40 pt face, the 34 pt Fraunces title
// under a 44 pt glass Back, caps section labels outside the card, the A+
// pill, toggle, radio, key-value and bullet rows, the champagne banner, the
// danger line and the empty state. Built on APlus.swift's tokens.

/// Profile-only A+ tones (tokens.css): not shared, so other screens keep theirs.
enum ProfileTone {
    /// `action-wash`: the icon's circle, a pill button's fill.
    static let actionWash = APlus.rgba(light: (178, 39, 87, 0.10), dark: (255, 143, 177, 0.10))
    /// `.icon.dz`: danger at 12%.
    static let dangerWash = APlus.rgba(light: (190, 38, 52, 0.12), dark: (255, 123, 114, 0.12))
    /// `.icon.good`, `.pill.ok`: money-in at 14%.
    static let goodWash = APlus.rgba(light: (22, 122, 64, 0.14), dark: (110, 219, 148, 0.14))
    /// `.pill.anchor`: teal at 14%.
    static let tealWash = APlus.rgba(light: (31, 122, 114, 0.14), dark: (143, 227, 214, 0.14))
    /// The banner's fill: champagne 22% (dark 10%).
    static let bannerFill = APlus.rgba(light: (243, 217, 164, 0.22), dark: (243, 217, 164, 0.10))
}

/// A+ `.icon`: a line icon on a 36 pt circle. Action wash by default; `dz`
/// for a destructive row, `warn` for a banner, `good` for done.
struct IconBubble: View {
    enum Kind { case action, danger, warn, good }

    let symbol: String
    var size: CGFloat = 36
    var tone: Color = Pearl.action
    var kind: Kind = .action

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.46, weight: .regular))
            .foregroundColor(foreground)
            .frame(width: size, height: size)
            .background(Circle().fill(background))
            .accessibilityHidden(true)
    }

    private var foreground: Color {
        switch kind {
        case .action: return tone
        case .danger: return Pearl.danger
        case .warn: return Pearl.caution
        case .good: return Pearl.moneyIn
        }
    }

    private var background: Color {
        switch kind {
        case .action: return ProfileTone.actionWash
        case .danger: return ProfileTone.dangerWash
        case .warn: return Pearl.cautionBackground
        case .good: return ProfileTone.goodWash
        }
    }
}

/// "MONEY": A+ `.label`, caps outside the card (13/500, tracked 0.78,
/// `muted`), 24 above and 8 below.
struct ProfileSection: View {
    let text: String
    var action: String? = nil
    var act: () -> Void = {}

    init(_ text: String, action: String? = nil, act: @escaping () -> Void = {}) {
        self.text = text
        self.action = action
        self.act = act
    }

    var body: some View {
        APSectionLabel(text: text, action: action, act: act)
            .padding(.top, 16)
    }
}

/// A+ `.note`: 13 `muted`, 4 in.
struct ProfileNote: View {
    let text: String
    var centred = false

    init(_ text: String, centred: Bool = false) {
        self.text = text
        self.centred = centred
    }

    var body: some View {
        Text(text).font(Nacre.footnote).foregroundColor(Pearl.muted)
            .multilineTextAlignment(centred ? .center : .leading)
            .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
            .padding(.horizontal, 4)
            .fixedSize(horizontal: false, vertical: true)
    }
}

/// A+ `.ptitle`: the 34 pt Fraunces title, 4 in, and its one `muted` lead
/// line in 17 (G5 `nav(title, lead=)`).
struct ProfileHeading: View {
    var eyebrow: String? = nil
    let title: String
    var intro: String? = nil
    var centred = false

    var body: some View {
        VStack(alignment: centred ? .center : .leading, spacing: 4) {
            if let eyebrow = eyebrow {
                Text(eyebrow.uppercased()).font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
            }
            Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                .multilineTextAlignment(centred ? .center : .leading)
                .fixedSize(horizontal: false, vertical: true)
                .accessibilityAddTraits(.isHeader)
            if let intro = intro {
                Text(intro).font(Nacre.body).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(centred ? .center : .leading)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .frame(maxWidth: .infinity, alignment: centred ? .center : .leading)
        .padding(.horizontal, 4)
    }
}

/// A+ `.face`: a bank's or a person's initials, 40 pt on `face`, 14/500.
struct RowAvatar: View {
    let name: String
    var size: CGFloat = 40
    var font: Font = .custom("Figtree-Medium", size: 14, relativeTo: .footnote)

    var body: some View {
        Text(letters)
            .font(font).foregroundColor(Pearl.ink)
            .lineLimit(1).minimumScaleFactor(0.5)
            .frame(width: size, height: size)
            .background(Circle().fill(APlus.face))
            .accessibilityHidden(true)
    }

    /// "TD" as it is, "AE" for American Express, "TA" for Tangerine (G5-Accounts).
    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }
        if words.count == 1, let w = words.first {
            return w.count <= 2 ? w.uppercased() : String(w.prefix(2)).uppercased()
        }
        let out = words.prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "·" : out
    }
}

/// A+ `.row`: an icon (or a face), a title over a line, whatever sits at the
/// end, and the chevron. 64 high, 16 at the sides, 12 between. A destructive
/// row is red, icon and words (`.dz`): the only red on the way to a
/// confirmation; the confirmation's button is the rose Primary.
struct ProfileRow<Trailing: View>: View {
    var symbol: String? = nil
    var initials: String? = nil
    let title: String
    var sub: String? = nil
    /// "Joint · 50%" on the line under the title, or (`pillTrailing`) at the end.
    var pill: StatusPill? = nil
    var tone: Color = Pearl.ink
    var chevron = true
    /// Still loading: the line under the title is a soft placeholder the
    /// same size, so nothing moves when it fills in (2026-11-08).
    var loading = false
    var pillTrailing = false
    var trailing: Trailing

    var body: some View {
        HStack(spacing: 12) {
            if let symbol = symbol { IconBubble(symbol: symbol, kind: isDanger ? .danger : .action) }
            if let initials = initials { RowAvatar(name: initials) }
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(tone)
                    .fixedSize(horizontal: false, vertical: true)
                if (sub != nil && sub?.isEmpty == false) || (pill != nil && !pillTrailing) {
                    HStack(spacing: 6) {
                        if let sub = sub, !sub.isEmpty {
                            Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                                .fixedSize(horizontal: false, vertical: true)
                                .redacted(reason: loading ? .placeholder : [])
                        }
                        if let pill = pill, !pillTrailing { pill }
                    }
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let pill = pill, pillTrailing { pill }
            trailing
            if chevron { APChevron() }
        }
        .padding(.horizontal, 16)
        .padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    private var isDanger: Bool { tone == Pearl.danger }
}

extension ProfileRow {
    init(symbol: String? = nil, initials: String? = nil, title: String, sub: String? = nil,
         pill: StatusPill? = nil, tone: Color = Pearl.ink, chevron: Bool = true, loading: Bool = false,
         pillTrailing: Bool = false, @ViewBuilder trailing: () -> Trailing) {
        self.symbol = symbol
        self.initials = initials
        self.title = title
        self.sub = sub
        self.pill = pill
        self.tone = tone
        self.chevron = chevron
        self.loading = loading
        self.pillTrailing = pillTrailing
        self.trailing = trailing()
    }
}

extension ProfileRow where Trailing == EmptyView {
    init(symbol: String? = nil, initials: String? = nil, title: String, sub: String? = nil,
         pill: StatusPill? = nil, tone: Color = Pearl.ink, chevron: Bool = true, loading: Bool = false,
         pillTrailing: Bool = false) {
        self.init(symbol: symbol, initials: initials, title: title, sub: sub, pill: pill, tone: tone,
                  chevron: chevron, loading: loading, pillTrailing: pillTrailing, trailing: { EmptyView() })
    }
}

/// A+ `.pill`: 28 high, 12 at the sides, 13 pt. `warn` (needs you), `ok`
/// (up to date), `joint`, `anchor`, or plain on `chip`.
struct StatusPill: View {
    enum Tone { case positive, attention, info, neutral, joint, needsALook, anchor }

    let text: String
    var tone: Tone = .positive
    var small = false

    var body: some View {
        Text(text).lineLimit(1)
            .font(small ? .custom("Figtree-Regular", size: 12, relativeTo: .caption)
                  : (strong ? Nacre.label : Nacre.footnote))
            .foregroundColor(foreground)
            .padding(.horizontal, small ? 8 : 12).frame(height: small ? 22 : 28)
            .background(Capsule().fill(background))
            .fixedSize()
    }

    private var strong: Bool {
        switch tone {
        case .info, .neutral: return false
        default: return true
        }
    }

    private var foreground: Color {
        switch tone {
        case .positive: return Pearl.moneyIn
        case .attention, .needsALook: return Pearl.caution
        case .anchor: return Nacre.teal
        case .info, .joint, .neutral: return Pearl.ink
        }
    }

    private var background: Color {
        switch tone {
        case .positive: return ProfileTone.goodWash
        case .attention, .needsALook: return Pearl.cautionBackground
        case .anchor: return ProfileTone.tealWash
        case .joint: return Pearl.bubble
        case .info, .neutral: return APlus.chip
        }
    }
}

/// A Profile page (G5 `nav`): the 52 pt row with the glass Back (and what
/// sits at its right), the content on the ground, and any buttons pinned
/// along the bottom, 12 apart.
struct ProfilePage<Content: View, Bottom: View>: View {
    @Environment(\.dismiss) private var dismiss
    var navTrailing: AnyView? = nil
    @ViewBuilder var content: () -> Content
    @ViewBuilder var bottom: () -> Bottom

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 8) {
                HStack {
                    APBackButton(identifier: "profile-back") { dismiss() }
                    Spacer()
                    if let navTrailing = navTrailing { navTrailing }
                }
                .frame(height: 52)
                content()
            }
            .padding(.horizontal, Pearl.gutter)
            .padding(.bottom, 32)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            if Bottom.self != EmptyView.self {
                VStack(spacing: 12, content: bottom)
                    .padding(.horizontal, 16).padding(.top, 12).padding(.bottom, 4)
            }
        }
        .nacreScreen()
        .navigationBarHidden(true)
    }
}

extension ProfilePage where Bottom == EmptyView {
    init(navTrailing: AnyView? = nil, @ViewBuilder content: @escaping () -> Content) {
        self.init(navTrailing: navTrailing, content: content, bottom: { EmptyView() })
    }
}

/// An email field as a visible well (REDESIGN-09): the 13 pt label over a
/// 44 pt well, 2 pt action ring while typing.
struct EmailField: View {
    let label: String
    @Binding var text: String
    var hint: String? = nil
    var readOnly = false
    var submit: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            Group {
                if readOnly {
                    Text(text).foregroundColor(Pearl.muted)
                        .frame(maxWidth: .infinity, alignment: .leading)
                } else {
                    TextField("", text: $text, prompt: Text("you@example.com").foregroundColor(Pearl.muted))
                        .keyboardType(.emailAddress)
                        .textContentType(.emailAddress)
                        .textInputAutocapitalization(.never)
                        .autocorrectionDisabled()
                        .submitLabel(.send)
                        .focused($focused)
                        .onSubmit(submit)
                        .foregroundColor(Pearl.ink)
                        .tint(Pearl.action)
                }
            }
            .font(Nacre.body)
            .padding(.horizontal, 14)
            .frame(minHeight: 44)
            .wellStyle(focused: focused)
            .accessibilityLabel(label)
            if let hint = hint {
                Text(hint).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
    }
}

// MARK: - A+ rows and parts (kit.css, g5.py)

/// G5 `tog`: an optional icon, a title over a line, and the switch (action
/// when on). Disabled: 45%.
struct APToggleRow: View {
    var symbol: String? = nil
    let title: String
    var sub: String? = nil
    @Binding var isOn: Bool
    var identifier: String? = nil

    @Environment(\.isEnabled) private var isEnabled

    var body: some View {
        Toggle(isOn: $isOn) {
            HStack(spacing: 12) {
                if let symbol = symbol { IconBubble(symbol: symbol) }
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
            }
        }
        .tint(Pearl.action)
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .opacity(isEnabled ? 1 : 0.45)
        .accessibilityIdentifier(identifier ?? title)
    }
}

/// G5 `choice`: the 24 pt radio (on: a 7 pt action ring), a title over a line.
struct APChoiceRow: View {
    let title: String
    var sub: String? = nil
    let selected: Bool
    var danger = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                APRadio(on: selected)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(danger ? Pearl.danger : Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
    }
}

/// G5 `kv`: a 52 pt row, the key on the left, its value `muted` (or `link`) on the right.
struct APKeyValueRow<Value: View>: View {
    let key: String
    var strong = false
    var chevron = false
    @ViewBuilder var value: () -> Value

    var body: some View {
        HStack(spacing: 8) {
            Text(key).font(strong ? Nacre.headline : Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            value().font(Nacre.body).multilineTextAlignment(.trailing)
            if chevron { APChevron() }
        }
        .padding(.horizontal, 16).padding(.vertical, 8)
        .frame(minHeight: 52)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

extension APKeyValueRow where Value == Text {
    init(key: String, value: String, link: Bool = false, strong: Bool = false, chevron: Bool = false) {
        self.key = key
        self.strong = strong
        self.chevron = chevron
        self.value = { Text(value).foregroundColor(link ? Pearl.link : Pearl.muted) }
    }
}

/// G5 `bullet`: a 6 pt dot (action, or teal for what stays) and 15 pt words.
struct APBullet: View {
    let text: String
    var sub: String? = nil
    var dot: Color = Pearl.action

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Circle().fill(dot).frame(width: 6, height: 6).padding(.top, 7).accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 0) {
                Text(text).foregroundColor(Pearl.ink)
                if let sub = sub { Text(sub).foregroundColor(Pearl.muted) }
            }
            .font(Nacre.subheadline)
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }
}

/// `.banner`: champagne 22% with its 1 pt line, radius 16, an icon, the
/// words and an optional quiet action at the end.
struct APBanner: View {
    var symbol = "exclamationmark.triangle"
    let text: String
    var action: String? = nil
    var act: () -> Void = {}

    var body: some View {
        HStack(spacing: 12) {
            IconBubble(symbol: symbol, kind: .warn)
            Text(text).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
                .fixedSize(horizontal: false, vertical: true)
            if let action = action {
                APQuietButton(title: action, action: act)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(ProfileTone.bannerFill))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
        .accessibilityElement(children: .combine)
    }
}

/// `.errline`: a real error, in `danger`, with its circle-i. Announced.
struct APErrorLine: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 8) {
            Image(systemName: "exclamationmark.circle").font(.system(size: 17)).accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Nacre.subheadline)
        .foregroundColor(Pearl.danger)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .onAppear { UIAccessibility.post(notification: .announcement, argument: text) }
    }
}

/// `.quiet`: a quiet action in `link` 15/500, 44 to tap.
struct APQuietButton: View {
    let title: String
    var tone: Color = Pearl.link
    var identifier: String? = nil
    let action: () -> Void

    var body: some View {
        Button(title, action: action)
            .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
            .foregroundColor(tone)
            .buttonStyle(.plain)
            .frame(minHeight: 44)
            .contentShape(Rectangle())
            .accessibilityIdentifier(identifier ?? title)
    }
}

/// `.pill-btn`: 32 high, 15/600 on the action wash; `quiet` is ink on `chip`.
struct APPillButton: View {
    let title: String
    var quiet = false
    var identifier: String? = nil
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(title)
                .font(.custom(quiet ? "Figtree-Medium" : "Figtree-SemiBold", size: 15, relativeTo: .subheadline))
                .foregroundColor(quiet ? Pearl.ink : Pearl.action)
                .padding(.horizontal, 14).frame(height: 32)
                .background(Capsule().fill(quiet ? APlus.chip : ProfileTone.actionWash))
                .padding(.vertical, 6)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier(identifier ?? title)
    }
}

/// G5 `who`: the ringed face, the name in 22 Fraunces and its line (a sheet's top).
struct APWho: View {
    let face: String
    let name: String
    var line: String? = nil
    var lineTone: Color = Pearl.muted

    var body: some View {
        HStack(spacing: 12) {
            APRingFace(name: face, size: 44)
            VStack(alignment: .leading, spacing: 0) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                if let line = line {
                    Text(line).font(Nacre.subheadline).foregroundColor(lineTone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

/// G5 `hero`: a detail page's top, centred: the ringed face, the name in 22
/// Fraunces, the big amount (44, Fraunces SemiBold), its lines and a pill.
struct APHero: View {
    let face: String
    let name: String
    var amount: String? = nil
    var amountTone: Color = Pearl.ink
    var lines: [String] = []
    var pill: StatusPill? = nil
    var symbol: String? = nil

    var body: some View {
        VStack(spacing: 0) {
            if let symbol = symbol {
                IconBubble(symbol: symbol)
            } else {
                APRingFace(name: face, size: 56)
            }
            Text(name).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            if let amount = amount {
                Text(amount).font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                    .tracking(-0.88).monospacedDigit()
                    .foregroundColor(amountTone)
                    .pearlAmountFit()
            }
            ForEach(lines, id: \.self) { l in
                Text(l).font(Nacre.subheadline).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
            }
            if let pill = pill { pill.padding(.top, 10) }
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// `.state`: nothing here yet, or it couldn't load. An icon or the mark, a
/// 22 pt Fraunces title, a 15 pt `muted` line and an optional button.
struct APEmptyState<Art: View, Actions: View>: View {
    let title: String
    var line: String? = nil
    var top: CGFloat = 110
    @ViewBuilder var art: () -> Art
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 6) {
            art().padding(.bottom, 8)
            Text(title).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .accessibilityAddTraits(.isHeader)
            if let line = line {
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .multilineTextAlignment(.center)
                    .fixedSize(horizontal: false, vertical: true)
            }
            actions().padding(.top, 12)
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 20)
        .padding(.top, top)
    }
}

extension APEmptyState where Actions == EmptyView {
    init(title: String, line: String? = nil, top: CGFloat = 110, @ViewBuilder art: @escaping () -> Art) {
        self.init(title: title, line: line, top: top, art: art, actions: { EmptyView() })
    }
}

/// G5-Load: a row holding its place while the page loads.
struct APSkeletonRow: View {
    var body: some View {
        HStack(spacing: 12) {
            Circle().fill(APlus.trackSoft).frame(width: 40, height: 40)
            VStack(alignment: .leading, spacing: 8) {
                Capsule().fill(APlus.trackSoft).frame(width: 150, height: 12)
                Capsule().fill(APlus.trackSoft).frame(width: 80, height: 12)
            }
            Spacer()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .accessibilityHidden(true)
    }
}

/// `.quiet` as a button style: `link` 15/500, the full width, 44 to tap.
struct APQuietTextStyle: ButtonStyle {
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

/// `.seg`: the segmented track on `chip` (38 high, radius 19, 3 in); the
/// picked one on the card white with a soft shadow. 15/500 words.
struct APSegmented: View {
    let options: [(id: String, title: String)]
    @Binding var selection: String?

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.id) { o in
                let on = selection == o.id
                Button { selection = o.id } label: {
                    Text(o.title)
                        .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.ink)
                        .lineLimit(1).minimumScaleFactor(0.7)
                        .frame(maxWidth: .infinity, minHeight: 32)
                        .background {
                            if on {
                                RoundedRectangle(cornerRadius: 16, style: .continuous).fill(APSegmented.thumb)
                                    .shadow(color: Pearl.ink.opacity(0.12), radius: 1.5, y: 1)
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
            }
        }
        .padding(3)
        .frame(minHeight: 38)
        .background(RoundedRectangle(cornerRadius: 19, style: .continuous).fill(APlus.chip))
    }

    /// `surface-card`: white, or the deep ocean in dark.
    static let thumb = Pearl.dynamic(light: 0xFFFFFF, dark: 0x262E63)
}

/// G5-Email `.code`: six 46 × 56 wells, 8 apart, the digits in 28 pt
/// Fraunces; the next one has the 2 pt action ring and caret; a wrong code
/// rings them all in danger. One hidden field takes the digits, so iOS can
/// fill it from Mail and paste works.
struct ProfileCodeWells: View {
    @Binding var code: String
    var failed = false
    var onComplete: () -> Void = {}

    @FocusState private var focused: Bool

    var body: some View {
        ZStack {
            TextField("", text: $code)
                .keyboardType(.numberPad)
                .textContentType(.oneTimeCode)
                .focused($focused)
                .foregroundColor(.clear)
                .tint(.clear)
                .accessibilityLabel("6-digit code")
                .accessibilityIdentifier("code-wells")
                .onChange(of: code) { value in
                    let digits = String(value.filter(\.isNumber).prefix(6))
                    if digits != value { code = digits }
                    if digits.count == 6 { onComplete() }
                }
            HStack(spacing: 8) {
                ForEach(0..<6, id: \.self) { i in
                    let chars = Array(code)
                    let current = i == chars.count && focused && !failed
                    ZStack {
                        RoundedRectangle(cornerRadius: 12, style: .continuous).fill(APlus.well)
                        RoundedRectangle(cornerRadius: 12, style: .continuous)
                            .strokeBorder(failed ? Pearl.danger : (current ? Pearl.action : APlus.wellLine),
                                          lineWidth: failed || current ? 2 : 1)
                        if i < chars.count {
                            Text(String(chars[i])).font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title))
                                .foregroundColor(Pearl.ink)
                        } else if current {
                            RoundedRectangle(cornerRadius: 1).fill(Pearl.action).frame(width: 2, height: 28)
                        }
                    }
                    .frame(width: 46, height: 56)
                }
            }
            .allowsHitTesting(false)
            .accessibilityHidden(true)
        }
        .frame(maxWidth: .infinity)
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
        .onAppear { focused = true }
    }
}

/// The Pearl mark (LogoMark), sized by width.
struct APMark: View {
    var width: CGFloat = 150

    var body: some View {
        Image("LogoMark").resizable().frame(width: width, height: width * 0.833)
            .accessibilityHidden(true)
    }
}

// MARK: - The detail sheets (src/pearl/docs.jsx)

/// What Pearl stores, who sees it, how Plaid works, help, and the drafts.
enum PearlDoc: String, Identifiable {
    /// `terms` and `privacy` are LG-01 and LG-02: the drafts, read in the
    /// app from the welcome screen, setup's consent and Privacy and consent.
    case plaid, store, share, help, terms, privacy

    var id: String { rawValue }

    /// "pearl-doc:terms": a link in running text that opens the page here.
    var url: URL { URL(string: "pearl-doc:\(rawValue)")! }

    init?(url: URL) {
        guard url.scheme == "pearl-doc" else { return nil }
        self.init(rawValue: url.absoluteString.replacingOccurrences(of: "pearl-doc:", with: ""))
    }

    struct Fact: Hashable {
        let label: String
        let text: String
        var tag: String? = nil
    }

    struct Part: Hashable {
        var heading: String? = nil
        let text: String
    }

    var eyebrow: String {
        switch self {
        case .plaid: return "Linking a bank"
        case .store: return "What we store"
        case .share: return "Who we share with"
        case .help: return "Help"
        case .terms, .privacy: return "Draft"
        }
    }

    var title: String {
        switch self {
        case .plaid: return "How signing in through Plaid works"
        case .store: return "Your data, plainly"
        case .share: return "Who sees your data"
        case .help: return "Getting in"
        case .terms: return "Terms"
        case .privacy: return "Privacy policy"
        }
    }

    static let storeFacts = [
        Fact(label: "We keep", text: "Account names and types, balances, transactions, and the categories and goals you set"),
        Fact(label: "We never keep", text: "Your bank username or password, or full card or account numbers"),
        Fact(label: "Where", text: "Our cloud database, encrypted when stored and when it moves. Bank connections are encrypted again with a key only Pearl holds."),
        Fact(label: "For how long", text: "While you use Pearl. When you delete your account, we delete your data straight away, and the last copies in our host’s backups within 30 days."),
    ]

    static let shareFacts = [
        Fact(label: "Plaid", text: "Connects to your bank, read-only", tag: "Needed"),
        Fact(label: "Our cloud host", text: "Runs Pearl and stores your data (Vercel and Neon)", tag: "Needed"),
        Fact(label: "Our email service", text: "Delivers your sign-in codes", tag: "Needed"),
        Fact(label: "An investing partner", text: "Only if you choose to go there when you’re ready to grow your money. We always ask first.", tag: "Your choice"),
    ]

    var facts: [Fact] {
        switch self {
        case .store: return Self.storeFacts
        case .share: return Self.shareFacts
        default: return []
        }
    }

    var parts: [Part] {
        switch self {
        case .plaid:
            return [
                Part(text: "When you link a bank, Plaid opens in its own secure window. You sign in to your bank there, and your username and password go to your bank — Pearl never sees them."),
                Part(text: "Your bank then lets Plaid share a read-only view: your accounts, their balances and your transactions. Pearl can’t move money, make payments or change anything at your bank."),
                Part(text: "You can disconnect a bank any time from Profile › Accounts, and Pearl stops receiving anything from it."),
            ]
        case .help:
            return [
                Part(heading: "Signing in", text: "Use Face ID on this iPhone, or ask for a 6-digit code by email. Codes work for 10 minutes; ask for a new one if yours has run out."),
                Part(heading: "New phone or computer?", text: "Sign in with an email code. If you’ve signed in somewhere before, Pearl asks you to approve the new device there."),
                Part(heading: "Too many tries?", text: "Sign-in pauses for 15 minutes after too many attempts. Nothing about your money changes while it’s paused."),
            ]
        case .privacy:
            // G5-Extras LG-02: four short cards; the Draft pill says it's a draft.
            return [
                Part(heading: "We keep", text: "Account names and types, balances, transactions, and the categories and goals you set."),
                Part(heading: "We never keep", text: "Your bank username or password, or full card or account numbers."),
                Part(heading: "Where", text: "Our cloud database, encrypted when stored and when it moves."),
                Part(heading: "For how long", text: "While you use Pearl. Delete your account and it goes straight away; backups within 30 days."),
            ]
        case .terms:
            return [
                Part(text: "A plain-language draft, not yet formal terms of service."),
                Part(heading: "What Pearl is", text: "Pearl helps you see your Allowance and plan what’s next. It reads your accounts. It doesn’t move money, and it isn’t financial advice."),
                Part(heading: "Your part", text: "Keep your email and devices secure. A code sent to your email, or Face ID on this iPhone, is how you get in."),
                Part(heading: "Ending", text: "You can stop any time. Deleting your account in Profile › Your data disconnects your banks and deletes your data."),
            ]
        default:
            return []
        }
    }

    var closing: String? {
        switch self {
        case .store: return "You can download or delete your data any time in Profile › Your data."
        case .share: return "We don’t sell your data, and we don’t show you ads."
        default: return nil
        }
    }
}

/// One detail sheet, with "Got it" at the bottom.
struct DocSheet: View {
    @Environment(\.dismiss) private var dismiss
    let doc: PearlDoc

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    Text(doc.title).font(Nacre.title2).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .accessibilityAddTraits(.isHeader)
                        .padding(.top, 28)
                    ForEach(doc.parts, id: \.self) { part in
                        VStack(alignment: .leading, spacing: 4) {
                            if let heading = part.heading {
                                Text(heading).font(Nacre.headline).foregroundColor(Pearl.ink)
                            }
                            Text(part.text).font(Nacre.body).foregroundColor(Pearl.ink)
                                .fixedSize(horizontal: false, vertical: true)
                        }
                    }
                    if !doc.facts.isEmpty {
                        APCard {
                            ForEach(Array(doc.facts.enumerated()), id: \.element) { i, fact in
                                if i > 0 { APSeparator(afterFace: false) }
                                factRow(fact)
                            }
                        }
                    }
                    if let closing = doc.closing { ProfileNote(closing) }
                }
                .padding(.horizontal, 16)
                .padding(.bottom, 24)
            }
            Button("Got it") { dismiss() }
                .buttonStyle(APPrimaryButtonStyle())
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
    }

    private func factRow(_ fact: PearlDoc.Fact) -> some View {
        HStack(alignment: .top, spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(fact.label).font(Nacre.footnote).foregroundColor(Pearl.muted)
                Text(fact.text).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if let tag = fact.tag {
                StatusPill(text: tag, tone: tag == "Needed" ? .info : .neutral)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }
}

extension PearlDoc {
    /// LG-01, LG-02: Terms and the Privacy policy are pages, not sheets.
    var isPage: Bool { self == .terms || self == .privacy }
}

/// LG-01 Terms, LG-02 Privacy policy (G5-Protect): pushed, with Back and
/// the Draft pill; each part is a caps label over a card of 17/24 words.
struct DocPage: View {
    let doc: PearlDoc

    var body: some View {
        ProfilePage(navTrailing: AnyView(StatusPill(text: "Draft", tone: .neutral))) {
            ProfileHeading(title: doc.title)
            ForEach(doc.parts.filter { $0.heading != nil }, id: \.self) { part in
                ProfileSection(part.heading ?? "")
                APCard {
                    Text(part.text).font(Nacre.body).lineSpacing(2).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 14)
                }
            }
        }
    }
}

extension View {
    /// A detail sheet over a Profile page; Terms and the Privacy policy push.
    func docSheet(_ doc: Binding<PearlDoc?>) -> some View {
        sheet(item: Binding(get: { doc.wrappedValue?.isPage == true ? nil : doc.wrappedValue },
                            set: { doc.wrappedValue = $0 })) { d in
            DocSheet(doc: d)
                .background(SheetBackground())
                .presentationDetents([.medium, .large])
                .presentationDragIndicator(.visible)
        }
        .navigationDestination(isPresented: Binding(get: { doc.wrappedValue?.isPage == true },
                                                    set: { if !$0 { doc.wrappedValue = nil } })) {
            if let d = doc.wrappedValue { DocPage(doc: d) }
        }
    }
}
