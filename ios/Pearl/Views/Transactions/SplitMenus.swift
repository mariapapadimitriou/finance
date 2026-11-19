import SwiftUI
import UIKit

// REFRESH-02 (Design refresh, section 11 1088:1695; THL-289, THL-291,
// THL-181): the split card's ••• menu and every screen after it, as Pearl
// views. Product owner, 2026-11-09: no `.alert`, `.confirmationDialog` or
// action sheet anywhere in these flows. Built from designBOT's kit 1088:1696
// (Option row, Primary / Secondary buttons, 44 pt Close and •••, Toast with
// Undo), on the iridescent background (REFRESH-05; pearl paper before), with
// ink amounts and no red (decisions 1 and 4).
// Motion comes later (note 1096:4483); nothing here depends on it.

// MARK: - The kit (1088:1696)

/// "Pearl/Close button (44)": the round Close on every sheet.
struct PearlCloseButton: View {
    var label = "Close"
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            // A+ `.glassbtn`: the 44 pt glass circle.
            Image(systemName: "xmark").font(.system(size: 15, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(APGlassCircle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// "Pearl/More button ••• (44)": a person's options on the split card.
struct PearlMoreButton: View {
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(APGlassCircle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// "Pearl/Button primary": rose with white text, 50 high; while waiting,
/// a spinner and the waiting words in the button (note 1096:4483).
struct PearlPrimaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled
    var busy = false
    var busyLabel: String? = nil

    func makeBody(configuration: Configuration) -> some View {
        ZStack {
            configuration.label.opacity(busy ? 0 : 1)
            if busy {
                HStack(spacing: 8) {
                    ProgressView().tint(Pearl.onAction)
                    if let busyLabel = busyLabel { Text(busyLabel) }
                }
            }
        }
        // A+ `.btn` (APPrimaryLook).
        .modifier(APPrimaryLook(enabled: isEnabled || busy, pressed: configuration.isPressed))
    }
}

/// "Pearl/Button secondary": the control fill with ink text.
struct PearlSecondaryButtonStyle: ButtonStyle {
    @Environment(\.isEnabled) private var isEnabled

    func makeBody(configuration: Configuration) -> some View {
        // A+ `.btn2` (APSecondaryLook).
        configuration.label
            .modifier(APSecondaryLook(enabled: isEnabled, pressed: configuration.isPressed))
    }
}

/// The 44-high pills on a payment card: View the e-Transfer, Unlink….
struct PearlPillButtonStyle: ButtonStyle {
    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .font(Pearl.text(.callout, .medium))
            .foregroundColor(Pearl.ink)
            .multilineTextAlignment(.center)
            .padding(.horizontal, 12)
            .frame(maxWidth: .infinity, minHeight: 44)
            .background(Capsule().fill(Pearl.control))
            .opacity(configuration.isPressed ? 0.7 : 1)
            .contentShape(Capsule())
    }
}

/// A round bubble holding a line icon: A+ `.icon` (`action-wash`), or rose
/// for the usual action ("Mark paid back").
struct PearlBubble: View {
    let symbol: String
    var prominent = false
    var tone: Color = Pearl.action
    var size: CGFloat = 40

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.44, weight: .regular))
            .foregroundColor(prominent ? Pearl.onAction : tone)
            .frame(width: size, height: size)
            .background(Circle().fill(prominent ? Pearl.action : APlus.actionWash))
            .accessibilityHidden(true)
    }
}

/// A person's or a merchant's initials on A+ `face` (the sheets' faces).
struct PearlFace: View {
    let name: String
    var size: CGFloat = 44

    var body: some View {
        Text(letters)
            .font(.custom("Figtree-Medium", size: size * 0.32, relativeTo: .footnote))
            // TEST-30 (TEST-17's rule): the letters grow with Dynamic Type but
            // never truncate to "…"; they shrink to fit the circle instead.
            .lineLimit(1).minimumScaleFactor(0.4)
            .padding(.horizontal, size * 0.12)
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(APlus.face))
            .accessibilityHidden(true)
    }

    private var letters: String {
        let words = name.split { !$0.isLetter && !$0.isNumber }
        if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        let out = words.prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased()
        return out.isEmpty ? "·" : out
    }
}

/// "Pearl/Option row", drawn as A+ `APOptionRow` (#385): the 36 pt `.icon`,
/// the title 17 over what happens 15 muted, the chevron; 64 high. Its card
/// (PearlOptionCard) gives the 16 pt sides, so callers' other rows line up.
struct PearlOptionRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var prominent = false
    /// PB-22 → PB-11: the answer Pearl picked from the match, with the
    /// Choice row's Pearl-tint checkmark beside the chevron.
    var checked = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                APIcon(symbol: symbol)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if checked {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Pearl.action)
                        .accessibilityHidden(true)
                }
                APChevron()
            }
            .padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(checked ? [.isButton, .isSelected] : .isButton)
    }
}

/// A card of option rows, drawn as A+ `APOptionCard` (#385): the one A+
/// card, radius 24; 16 pt sides for whatever the caller puts in it.
struct PearlOptionCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(spacing: 0, content: content)
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, alignment: .leading)
            .pearlCard(radius: Pearl.radiusCard)
    }
}

/// The 0.5 pt A+ separator between option rows, after the icon (68 from
/// the card's edge, as APSeparator).
struct PearlDivider: View {
    var body: some View {
        Rectangle().fill(APlus.separator).frame(height: 0.5).padding(.leading, 52)
            .accessibilityHidden(true)
    }
}

/// "CHANGE THE SPLIT", "PAID SO FAR": a section's small caps.
struct PearlSectionLabel: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(Pearl.text(.footnote, .medium)).tracking(0.78)
            .foregroundColor(Pearl.muted)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The champagne Banner for errors (never red). designBOT set its fill to
/// 22% champagne so the words read in dark too. Announced by VoiceOver.
struct CautionBanner: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "exclamationmark.triangle").font(.system(size: 16))
                .accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Pearl.text(.callout, .medium))
        .foregroundColor(Pearl.ink)
        .padding(14)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
            .fill(Pearl.champagne.opacity(0.22)))
        .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
            .stroke(Pearl.champagne, lineWidth: 1))
        .accessibilityElement(children: .combine)
        .onAppear { UIAccessibility.post(notification: .announcement, argument: text) }
    }
}

/// "ⓘ Loblaws already counts in full…": a quiet note on a card.
struct InfoNote: View {
    let text: String

    var body: some View {
        HStack(alignment: .top, spacing: 10) {
            Image(systemName: "info.circle").font(.system(size: 16)).accessibilityHidden(true)
            Text(text).fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .font(Pearl.text(.callout))
        .foregroundColor(Pearl.muted)
        .padding(14)
        .pearlCard(radius: Pearl.radiusChoice)
        .accessibilityElement(children: .combine)
    }
}

/// A sheet's top: since #385, A+ `APSheetHeader` (G2-Person): the glass ✕
/// (‹ on the left when there's a way back) on its own line, then the ring
/// face or icon, the 12/600 caps, the Fraunces 22 title and its line.
struct PearlSheetHeader: View {
    var face: String? = nil
    var symbol: String? = nil
    let overline: String
    let title: String
    var sub: String? = nil
    var subTone: Color = Pearl.muted
    var back: (() -> Void)? = nil
    let close: () -> Void

    var body: some View {
        APSheetHeader(face: face, symbol: symbol, overline: overline, title: title, sub: sub,
                      subTone: subTone, back: back, close: close)
    }
}

/// Reads a view's height, so a sheet can size to what it holds.
private struct HeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// A Pearl sheet: a Pearl view, not a stock dialog (decision 4), on the
/// iridescent background with the Pearl dust (REFRESH-05: the sheet surface
/// is color/surface/page), sized to its content and scrolling past the large
/// detent (note 1096:4483), with the grabber.
struct PearlSheet<Content: View, Footer: View>: View {
    var dismissDisabled = false
    @ViewBuilder var content: () -> Content
    @ViewBuilder var footer: () -> Footer
    @State private var height: CGFloat = 360
    @State private var footerHeight: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                // A+ (#385's APSheet): 14 pt rhythm, 14 from the grabber.
                VStack(alignment: .leading, spacing: 14, content: content)
                    .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
                    .background(GeometryReader { g in Color.clear.preference(key: HeightKey.self, value: g.size.height) })
            }
            .scrollDismissesKeyboard(.interactively)
            footer()
                .background(GeometryReader { g in
                    Color.clear
                        .onAppear { footerHeight = g.size.height }
                        .onChange(of: g.size.height) { footerHeight = $0 }
                })
        }
        .background(SheetBackground())
        .toggleStyle(APToggleStyle())
        .onPreferenceChange(HeightKey.self) { h in height = h }
        .presentationDetents([.height(min(height + footerHeight + 16, UIScreen.main.bounds.height * 0.92)), .large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(dismissDisabled)
        .modifier(PaperBackground())
    }
}

extension PearlSheet where Footer == EmptyView {
    init(dismissDisabled: Bool = false, @ViewBuilder content: @escaping () -> Content) {
        self.dismissDisabled = dismissDisabled
        self.content = content
        self.footer = { EmptyView() }
    }
}

/// The sheet itself on the iridescent background where iOS lets us say so
/// (16.4+), so nothing white shows past the content.
private struct PaperBackground: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 16.4, *) {
            content.presentationBackground { SheetBackground() }
                .presentationCornerRadius(38)
        } else {
            content
        }
    }
}

/// The primary and secondary buttons at a sheet's bottom.
struct PearlSheetButtons: View {
    let primary: String
    var busy = false
    var busyLabel: String? = nil
    var secondary: String? = nil
    let onPrimary: () -> Void
    var onSecondary: () -> Void = {}

    var body: some View {
        VStack(spacing: 12) {
            Button(primary, action: onPrimary)
                .buttonStyle(PearlPrimaryButtonStyle(busy: busy, busyLabel: busyLabel))
                .accessibilityIdentifier("sheet-primary")
            if let secondary = secondary {
                Button(secondary, action: onSecondary).buttonStyle(PearlSecondaryButtonStyle())
            }
        }
        .disabled(busy)
        .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
    }
}

// MARK: - A+ sheet kit (G2 · Splits and paybacks)

// A+ restyle (REDESIGN-09/10, Claude Design "Pearl redesign" › Rollout ·
// Group 2, kit.css): the parts every G2 sheet shares. The kit above stays
// for screens other bots own; the split and payback flows use these.

/// G2 `.sheet`: light, white 66% → 44% over rose → lilac → seaglass
/// (114.76°); dark, #1C2F73 → #12163F.
struct APSheetSurface: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        if scheme == .dark {
            LinearGradient(colors: [Color(hex: 0x1C2F73), Color(hex: 0x12163F)], startPoint: .top, endPoint: .bottom)
                .ignoresSafeArea()
        } else {
            ZStack {
                LinearGradient(colors: [Color(hex: 0xFFB6CC), Color(hex: 0xCDB9FF), Color(hex: 0xA8E9DF)],
                               startPoint: UnitPoint(x: 0, y: 0.3), endPoint: UnitPoint(x: 1, y: 0.7))
                LinearGradient(colors: [.white.opacity(0.66), .white.opacity(0.44)], startPoint: .top, endPoint: .bottom)
            }
            .ignoresSafeArea()
        }
    }
}

/// `.glassbtn`: the 44 pt round ✕ (or ‹) on `card`, with its line and shadow.
struct APGlassButton: View {
    var symbol = "xmark"
    var label = "Close"
    let action: () -> Void
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 16, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(APlus.card))
                .overlay(Circle().strokeBorder(APlus.cardLine, lineWidth: 1))
                .shadow(color: scheme == .dark ? .black.opacity(0.22) : Pearl.cardShadow.opacity(0.10), radius: 14, y: 10)
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// `.ring.sm`: a 44 pt face inside the 1.2 pt nacre ring (the sheet's who).
struct APRingFace: View {
    let name: String
    var size: CGFloat = 44

    var body: some View {
        Text(APFace.initials(name))
            .font(.custom("Figtree-Medium", size: size * 0.34))
            .lineLimit(1).minimumScaleFactor(0.5)
            .foregroundColor(Pearl.ink)
            .frame(width: size - 2.4, height: size - 2.4)
            .background(Circle().fill(APlus.face))
            .padding(1.2)
            .background(Circle().fill(APlus.nacreRing))
            .accessibilityHidden(true)
    }
}

// APIcon moved to Theme/APlus.swift (one icon for the app).

/// A sheet's top (`.shead` then `.who`): the centred title with ✕ (‹ on
/// the left when there's a way back), then the ring face, the caps over the
/// display name, and its line. Either half can be left out.
struct APSheetHeader: View {
    /// `.shead h2`: "Edit split", "How did Priya pay?".
    var heading: String? = nil
    /// The centred line under the heading ("e-Transfer from Jo Park · Nov 16").
    var line: String? = nil
    var face: String? = nil
    var symbol: String? = nil
    var overline: String? = nil
    var title: String? = nil
    var sub: String? = nil
    var subTone: Color = Pearl.muted
    var back: (() -> Void)? = nil
    let close: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            VStack(spacing: 4) {
                ZStack {
                    if let heading = heading {
                        Text(heading).font(Nacre.headline).foregroundColor(Pearl.ink)
                            .multilineTextAlignment(.center)
                            .fixedSize(horizontal: false, vertical: true)
                            .padding(.horizontal, 52)
                            .accessibilityAddTraits(.isHeader)
                    }
                    HStack {
                        if let back = back { APGlassButton(symbol: "chevron.left", label: "Back", action: back) }
                        Spacer()
                        APGlassButton(action: close)
                    }
                }
                .frame(maxWidth: .infinity, minHeight: 44)
                if let line = line {
                    Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .multilineTextAlignment(.center)
                        .frame(maxWidth: .infinity)
                }
            }
            if let title = title { who(title) }
        }
    }

    private func who(_ title: String) -> some View {
        // S-03ax (TEST-17): at accessibility sizes the face goes.
        let big = typeSize.isAccessibilitySize
        return HStack(spacing: 12) {
            if !big {
                if let symbol = symbol {
                    APIcon(symbol: symbol).scaleEffect(44.0 / 36.0).frame(width: 44, height: 44)
                } else if let face = face {
                    APRingFace(name: face)
                }
            }
            VStack(alignment: .leading, spacing: 0) {
                if let overline = overline {
                    // TEST-14: the overline wraps, never clipped.
                    Text(overline.uppercased())
                        .font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption)).tracking(1.2)
                        .foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.bottom, 2)
                }
                Text(title).font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(subTone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
    }
}

/// `.shead` on a full-height sheet: the centred title, the glass ✕, 16 at
/// the sides. Was SheetTitle; `short` is said when `title` won't fit.
struct APSheetTitleBar: View {
    let title: String
    var short: String? = nil
    let close: () -> Void

    var body: some View {
        ZStack {
            Group {
                if let short = short {
                    ViewThatFits(in: .horizontal) {
                        Text(title).lineLimit(1)
                        Text(title).fixedSize(horizontal: false, vertical: true)
                        Text(short)
                    }
                } else {
                    Text(title).fixedSize(horizontal: false, vertical: true)
                }
            }
            .font(Nacre.headline).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
            .padding(.horizontal, 52)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(title)
            .accessibilityAddTraits(.isHeader)
            HStack {
                Spacer()
                APGlassButton(action: close)
            }
        }
        .frame(minHeight: 44)
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 14)
    }
}

/// `.who` for what a sheet is about: the ring face, the display name, and
/// "−$84.12 · Wed, Nov 11" (the amount in its tone). Was QuestionHeader.
struct APQuestionWho: View {
    let name: String
    let amount: String
    let tone: Color
    let sub: String?
    /// The face's letters, when they aren't the name's ("SL" for an
    /// e-Transfer from Sam Lee).
    var face: String? = nil
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        let big = typeSize.isAccessibilitySize
        HStack(spacing: 12) {
            if !big { APRingFace(name: face ?? name) }
            VStack(alignment: .leading, spacing: 0) {
                // POLISH-01: the name and its line wrap rather than cut.
                Text(name).font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                    .lineLimit(big ? 3 : 2)
                    .fixedSize(horizontal: false, vertical: true)
                // S-03j v2: no amount, so the line is the sub alone.
                (Text(amount).foregroundColor(tone)
                 + Text(sub.map { $0.isEmpty ? "" : (amount.isEmpty ? "" : " · ") + $0 } ?? "")
                    .foregroundColor(Pearl.muted))
                    .font(Nacre.subheadline).lineLimit(big ? 3 : 2)
                    .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .ignore)
        // TEST-14: "Gusto, spent $127.50", not the unread U+2212 minus.
        .accessibilityLabel([name, Format.spoken(amount), sub].compactMap { $0?.isEmpty == false ? $0 : nil }
            .joined(separator: ", "))
    }
}

/// A G2 sheet: the A+ surface, sized to what it holds, the grabber, the
/// Primary and Secondary at the bottom. Never a stock dialog.
struct APSheet<Content: View, Footer: View>: View {
    var dismissDisabled = false
    @ViewBuilder var content: () -> Content
    @ViewBuilder var footer: () -> Footer
    @State private var height: CGFloat = 360
    @State private var footerHeight: CGFloat = 0

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14, content: content)
                    .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
                    .background(GeometryReader { g in Color.clear.preference(key: APHeightKey.self, value: g.size.height) })
            }
            .scrollDismissesKeyboard(.interactively)
            footer()
                .background(GeometryReader { g in
                    Color.clear
                        .onAppear { footerHeight = g.size.height }
                        .onChange(of: g.size.height) { footerHeight = $0 }
                })
        }
        .background(APSheetSurface())
        .onPreferenceChange(APHeightKey.self) { h in height = h }
        .presentationDetents([.height(min(height + footerHeight + 16, UIScreen.main.bounds.height * 0.92)), .large])
        .presentationDragIndicator(.visible)
        .interactiveDismissDisabled(dismissDisabled)
        .modifier(APSheetBackground())
    }
}

extension APSheet where Footer == EmptyView {
    init(dismissDisabled: Bool = false, @ViewBuilder content: @escaping () -> Content) {
        self.dismissDisabled = dismissDisabled
        self.content = content
        self.footer = { EmptyView() }
    }
}

private struct APHeightKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = max(value, nextValue()) }
}

/// The A+ surface behind the whole sheet, so nothing else shows past it.
struct APSheetBackground: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 16.4, *) {
            content.presentationBackground { APSheetSurface() }
                .presentationCornerRadius(38)
        } else {
            content
        }
    }
}

/// A sheet's `.label`: caps outside a card, 24 above it and 8 below (the
/// sheet's 14 pt rhythm, evened out), with its quiet action.
struct APSheetLabel: View {
    let text: String
    var action: String? = nil
    var act: () -> Void = {}

    var body: some View {
        APSectionLabel(text: text, action: action, act: act)
            .fixedSize(horizontal: false, vertical: true)
            .padding(.top, 10).padding(.bottom, -6)
    }
}

/// `.row` with an `.icon`: the title over what happens, a chevron. At
/// least 64 high; VoiceOver reads the title, then what happens.
struct APOptionRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    /// Kept so call sites read as before; A+ draws every lead option alike.
    var prominent = false
    /// PB-22 → PB-11: the answer Pearl picked, with a tick beside the chevron.
    var checked = false
    var tone: Color = Pearl.action
    var titleTone: Color = Pearl.ink
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                APIcon(symbol: symbol, tone: tone)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(titleTone)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                if checked {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold))
                        .foregroundColor(Pearl.action)
                        .accessibilityHidden(true)
                }
                APChevron()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(checked ? [.isButton, .isSelected] : .isButton)
    }
}

/// `.chev`: the muted 8 × 14 chevron at a row's end.
struct APChevron: View {
    var body: some View {
        Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
            .foregroundColor(Pearl.muted)
            .accessibilityHidden(true)
    }
}

/// A card of rows on the A+ card; rows bring their own 16 pt sides and
/// `APSeparator()` goes between them.
struct APOptionCard<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 0, content: content)
            .frame(maxWidth: .infinity, alignment: .leading)
            .apCard()
    }
}

/// `.prow`: a 40 pt face, the name over its line, and what goes on the
/// right. At least 60 high, 10 above and below, 16 at the sides.
struct APPersonRow<Trailing: View>: View {
    let face: String
    let name: String
    var line: String? = nil
    var lineTone: Color = Pearl.muted
    @ViewBuilder var trailing: () -> Trailing

    var body: some View {
        HStack(spacing: 12) {
            APFace(name: face)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                if let line = line {
                    Text(line).font(Nacre.subheadline).foregroundColor(lineTone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            trailing()
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 60)
        .contentShape(Rectangle())
    }
}

/// `.tickbox`: 24 pt, radius 7, a 1.5 pt muted edge; ticked, rose with ✓.
struct APTickBox: View {
    let on: Bool

    var body: some View {
        ZStack {
            RoundedRectangle(cornerRadius: 7, style: .continuous)
                .fill(on ? Pearl.action : Color.clear)
            if !on {
                RoundedRectangle(cornerRadius: 7, style: .continuous).strokeBorder(Pearl.muted, lineWidth: 1.5)
            } else {
                Image(systemName: "checkmark").font(.system(size: 12, weight: .bold)).foregroundColor(Pearl.onAction)
            }
        }
        .frame(width: 24, height: 24)
        .accessibilityHidden(true)
    }
}

/// `.radio`: 24 pt, a 1.5 pt muted ring; on, a 7 pt rose ring.
struct APRadio: View {
    let on: Bool

    var body: some View {
        Circle().strokeBorder(on ? Pearl.action : Pearl.muted, lineWidth: on ? 7 : 1.5)
            .frame(width: 24, height: 24)
            .accessibilityHidden(true)
    }
}

/// `.total`: the centred 15/600 line under a card. Green with ✓ when it
/// adds up, muted while something's left over, red only when too much.
struct APTotalLine: View {
    enum Tone { case good, quiet, over }
    let text: String
    var tone: Tone = .good

    var body: some View {
        Text(text)
            .font(.custom("Figtree-SemiBold", size: 15, relativeTo: .subheadline))
            .monospacedDigit()
            .foregroundColor(tone == .good ? Pearl.moneyIn : tone == .over ? Pearl.danger : Pearl.muted)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity)
    }
}

/// The evenly sized five-part switch (REDESIGN-10): Evenly · Amounts · % ·
/// Shares · Not sure, one row that fits 375 pt. `chip` track 38 high, the
/// chosen part on `surface-card` with a soft shadow; 14/500 words.
struct APSegments: View {
    let options: [(tag: String, label: String)]
    @Binding var selection: String
    var spoken: (String) -> String = { $0 }
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.tag) { o in
                let on = o.tag == selection
                Button { selection = o.tag } label: {
                    Text(o.label)
                        .font(.custom("Figtree-Medium", size: 14, relativeTo: .subheadline))
                        .foregroundColor(Pearl.ink)
                        .lineLimit(1).minimumScaleFactor(0.8)
                        .padding(.horizontal, 8)
                        .frame(maxWidth: .infinity, maxHeight: .infinity)
                        .background {
                            if on {
                                RoundedRectangle(cornerRadius: 16, style: .continuous)
                                    .fill(scheme == .dark ? Color(hex: 0x151B44) : Color.white.opacity(0.72))
                                    .shadow(color: Pearl.ink.opacity(0.12), radius: 1.5, y: 1)
                            }
                        }
                        .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityLabel(spoken(o.label))
                .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
            }
        }
        .padding(3)
        .frame(height: 38)
        .background(Capsule().fill(APlus.chip))
    }
}

/// `.stepper`: − n + in a well, 36 high.
struct APStepper: View {
    let value: String
    let label: String
    let minus: () -> Void
    let plus: () -> Void

    var body: some View {
        HStack(spacing: 0) {
            Button(action: minus) { Text("\u{2212}").frame(width: 36, height: 36).contentShape(Rectangle()) }
                .accessibilityLabel("Fewer shares for \(label)")
            Text(value).font(Nacre.headline).monospacedDigit().frame(minWidth: 24)
                .accessibilityLabel("\(label), \(value) shares")
            Button(action: plus) { Text("+").frame(width: 36, height: 36).contentShape(Rectangle()) }
                .accessibilityLabel("More shares for \(label)")
        }
        .buttonStyle(.plain)
        .font(.system(size: 18))
        .foregroundColor(Pearl.ink)
        .frame(height: 36)
        .wellStyle(focused: false)
    }
}

/// `.tile`: a kind to pick (A person · The shop · Work), 96 high.
struct APTile: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var current = false
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            VStack(alignment: .leading, spacing: 2) {
                APIcon(symbol: symbol).padding(.bottom, 6)
                Text(title).font(.custom("Figtree-Regular", size: 16, relativeTo: .callout)).foregroundColor(Pearl.ink)
                if let sub = sub {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: 96, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(APlus.card))
            .overlay(RoundedRectangle(cornerRadius: 18, style: .continuous)
                .strokeBorder(current ? Pearl.action : APlus.cardLine, lineWidth: current ? 2 : 1))
            .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(current ? [.isButton, .isSelected] : .isButton)
    }
}

/// G2-Person "PAID SO FAR": the payment as a row ("e-Transfer · Nov 12",
/// what it was, the amount in green), then View… and Unlink… as rows in
/// the same card (they were pills).
struct APPaymentCard: View {
    let title: String
    var line: String? = nil
    let amount: Double
    var viewLabel: String? = nil
    var onView: () -> Void = {}
    let unlinkTitle: String
    var unlinkSub: String? = nil
    let onUnlink: () -> Void

    var body: some View {
        APOptionCard {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let line = line, !line.isEmpty {
                        Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text(Format.amount(amount)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.moneyIn)
            }
            .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 56)
            .accessibilityElement(children: .combine)
            if let viewLabel = viewLabel {
                APSeparator(afterFace: false)
                APOptionRow(symbol: "arrow.left.arrow.right", title: viewLabel, action: onView)
                    .accessibilityHint("Opens it here in Pearl")
            }
            APSeparator(afterFace: false)
            APOptionRow(symbol: "link", title: unlinkTitle, sub: unlinkSub, action: onUnlink)
        }
    }
}

/// G2-APersonStates (S-40c, S-40c2; Rethought, approved 2026-11-18): a
/// payment is one tappable row: its icon, "e-Transfer · Nov 16" over what it
/// was, the amount in green and a chevron. Its options (View…, Unlink…)
/// open on tap instead of sitting as two rows under every payment.
struct APLinkRow: View {
    let symbol: String
    let title: String
    var line: String? = nil
    let amount: Double
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                APIcon(symbol: symbol, tone: Pearl.moneyIn)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let line = line, !line.isEmpty {
                        Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text(Format.amount(amount)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.moneyIn).pearlAmountFit()
                APChevron()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, line, Format.amount(amount)].compactMap { $0 }.joined(separator: ", "))
        .accessibilityHint("Shows its options")
        .accessibilityAddTraits(.isButton)
    }
}

/// `.bullet` rows in a card: WHAT CHANGES.
struct APBullets: View {
    let lines: [String]

    var body: some View {
        APOptionCard {
            ForEach(Array(lines.enumerated()), id: \.offset) { i, line in
                if i > 0 { APSeparator(afterFace: false) }
                HStack(alignment: .firstTextBaseline, spacing: 10) {
                    Circle().fill(Pearl.action).frame(width: 6, height: 6)
                        .alignmentGuide(.firstTextBaseline) { d in d[.bottom] + 4 }
                        .accessibilityHidden(true)
                    Text(line).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 0)
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
            }
        }
    }
}

// MARK: - S-44 Toasts

/// "Pearl/Toast with Undo" (S-44a–i): ink, with a 44-high action. It stays
/// 6 s, longer while VoiceOver is on; it's announced, and its action is an
/// accessibility action too (note 1096:4483).
extension View {
    /// TEST-22 (designBOT 2026-11-11): an amount never wraps inside the
    /// number; it shrinks to fit, and rows move it under the name at AX sizes.
    func pearlAmountFit() -> some View {
        lineLimit(1).minimumScaleFactor(0.7).allowsTightening(true)
    }
}

struct PearlToast: View {
    struct Model: Equatable {
        let id = UUID()
        let text: String
        /// "Undo", "Try again", or none.
        var action: String? = nil
        var failed = false
        var run: (() -> Void)? = nil

        static func == (a: Model, b: Model) -> Bool { a.id == b.id }
    }

    let model: Model
    /// Stays until something replaces it (Quick sort's Undo, UN-01).
    var stays = false
    let done: () -> Void
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        // TEST-22 (designBOT 2026-11-11): at AX sizes the words wrap to two
        // or three lines and Undo goes on its own line under them.
        Group {
            if typeSize.isAccessibilitySize {
                VStack(alignment: .leading, spacing: 2) {
                    words.frame(maxWidth: .infinity, alignment: .leading).padding(.top, 6)
                    actionButton.padding(.leading, -14)
                }
            } else {
                HStack(spacing: 12) {
                    words
                    Spacer(minLength: 8)
                    actionButton
                }
            }
        }
        .fixedSize(horizontal: false, vertical: true)
        .foregroundColor(Pearl.onInk)
        .padding(.leading, 16).padding(.trailing, 8).padding(.vertical, 6)
        .frame(minHeight: 56)
        .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Pearl.ink))
        // A+ `--shadow-toast`: 0 8 12 black @16%.
        .shadow(color: .black.opacity(0.16), radius: 6, y: 8)
        .padding(.horizontal, 16)
        .swipeToDismiss(done)
        .transition(.move(edge: .bottom).combined(with: .opacity))
        .accessibilityElement(children: .combine)
        .accessibilityActions {
            if let action = model.action, let run = model.run { Button(action) { run() } }
        }
        .task(id: model.id) {
            UIAccessibility.post(notification: .announcement, argument: model.text)
            guard !stays else { return }
            let seconds: UInt64 = UIAccessibility.isVoiceOverRunning ? 15 : 6
            try? await Task.sleep(nanoseconds: seconds * 1_000_000_000)
            if !Task.isCancelled { done() }
        }
    }

    private var words: some View {
        HStack(alignment: .firstTextBaseline, spacing: 12) {
            Image(systemName: model.failed ? "info.circle" : "checkmark")
                .font(.system(size: 17, weight: .semibold))
                .accessibilityHidden(true)
            Text(model.text).font(Pearl.text(.callout, .medium))
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    @ViewBuilder private var actionButton: some View {
        if let action = model.action, let run = model.run {
            Button(action) { run() }
                .font(Pearl.text(.callout, .semibold))
                .padding(.horizontal, 14).frame(minHeight: 44)
                .contentShape(Rectangle())
                .buttonStyle(.plain)
        }
    }
}

// MARK: - S-40 Person options (one sheet, sections by state)

/// What she picked on S-40; it runs once the sheet has gone, so the next
/// sheet can open (handoff note 1096:4498).
enum PersonChoice {
    case markPaid, remind, letGo, undoLetGo, changeShare, remove
    /// S-48e (TEST-18b): change what she answered for a payer.
    case changeAnswer
    case view(Transaction.LinkInfo), unlink(Transaction.LinkInfo)
    /// PB-20 (Paid back, 2026-11-15): her own row's Find what paid it back.
    case findPaidBack
    /// PB-42 (Paybacks & undo, 2026-11-16): S-40c's How much and Which purchase.
    case howMuch(Transaction.LinkInfo), whichPurchase(Transaction.LinkInfo)
}

/// TEST-31 S-40w: the ••• on her own reimbursed row. REIMBURSED BY with View
/// the deposit and Unlink… (the S-34kr7 sheet), then Change your share. No
/// Remove: she can't remove herself. S-40m (Money back): REFUNDED BY, the
/// refund card, View the refund and Unlink… (S-34kr8 "Unlink refund?").
/// PB-20 (1359:9271, dark 1359:9386; Paid back, approved 2026-11-15): the
/// options start with Find what paid it back, and the ••• is there before
/// anything is linked too (`mine` nil): "Your share $60.00 · nothing paid
/// it back yet" in money-in green, then YOUR SHARE.
struct MineOptionsSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let mine: Transaction.Splitting.Mine?
    let by: String
    let onClose: () -> Void
    let onChoose: (PersonChoice) -> Void

    private var ways: Int { split.people.count + 1 }

    private var sub: String {
        // REDESIGN-10: "Not paid back yet".
        guard let mine = mine else { return "Not paid back yet" }
        // G2-BOptions S-40w: "Reimbursed by Northwind · $60.00".
        return mine.full
            ? (mine.refunded ? "Refunded" : "Reimbursed by \(by)") + " · \(Format.amount(mine.reimbursed))"
            : "\(mine.refunded ? "Refunded" : "Reimbursed") \(Format.amount(mine.reimbursed)) of \(Format.amount(mine.amount)) · \(Format.amount(mine.stays)) stays yours"
    }

    var body: some View {
        APSheet {
            APSheetHeader(face: "Me", overline: "\(t.merchant) · split \(ways) ways", title: "You",
                             sub: sub, subTone: mine.map { $0.full ? Pearl.moneyIn : Pearl.muted } ?? Pearl.muted,
                             close: onClose)
            if let mine = mine, let links = mine.links, !links.isEmpty {
                APSheetLabel(text: mine.refunded ? "Refunded by" : "Reimbursed by")
                ForEach(links) { link in card(link, only: links.count == 1) }
            }
            // G2-FromPurchase: no label before anything is linked.
            if mine != nil { APSheetLabel(text: "Change the split") }
            APOptionCard {
                // PB-20: first, also before anything is linked. The frame
                // draws the title alone; what it finds is the VoiceOver hint.
                // S-40w: once all of her share is reimbursed, nothing is left to find.
                if mine?.full != true {
                    APOptionRow(symbol: "questionmark.circle", title: "Find what paid it back") { onChoose(.findPaidBack) }
                        .accessibilityHint("Work, a refund, or someone paying you")
                        .accessibilityIdentifier("find-paid-back")
                    APSeparator()
                }
                APOptionRow(symbol: "person.2", title: "Change your share") { onChoose(.changeShare) }
            }
        }
    }

    /// "Northwind Ltd · Nov 14" over "Paid back · work", $60.00.
    private func card(_ link: Transaction.LinkInfo, only: Bool) -> some View {
        // PAID-02: a link reads "Paid back · {who}".
        APPaymentCard(title: "\(link.sheet.face) · \(Format.short(link.date))",
                      line: link.kind == "refund" ? "Paid back · refund" : "Paid back · work",
                      amount: link.amount, viewLabel: link.view?.label, onView: { onChoose(.view(link)) },
                      unlinkTitle: only ? "Unlink…" : "Unlink \(Format.amount(link.amount))…",
                      onUnlink: { onChoose(.unlink(link)) })
    }
}

/// S-40a owes · S-40b paid part · S-40c / c2 paid in full · S-40d let go.
/// Built from `Splitting.Person` and its `links` only (no new call).
struct PersonOptionsSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let p: Transaction.Splitting.Person
    let onClose: () -> Void
    let onChoose: (PersonChoice) -> Void
    /// AP-OwedPerson (REDESIGN-04): from Owed to you, "Open Loblaws" under
    /// the options opens the purchase. Nil on the purchase's own page.
    var onOpen: (() -> Void)? = nil

    private var links: [Transaction.LinkInfo] { p.links ?? [] }
    private var letGoAmount: Double { max(0, (p.letGo?.was ?? 0) - p.paid) }
    private var ways: Int { split.people.count + (split.you >= 0.005 ? 1 : 0) }

    var body: some View {
        if split.unsure { unsureBody } else { setBody }
    }

    /// S-40u (paid) / S-40u2 (nothing yet), SPLIT-C: PAID SO FAR, Mark paid
    /// back (any amount), Remind (no amount), Remove. No Let it go and no
    /// Change share: nothing is owed. Closed (S-46): only the links.
    private var unsureBody: some View {
        APSheet {
            APSheetHeader(face: p.name, overline: "\(t.merchant) · Not sure yet", title: p.name,
                             sub: unsureLine, subTone: p.paid >= 0.005 ? Pearl.moneyIn : Pearl.muted, close: onClose)
            if split.closedAt == nil {
                // G2-BOptions (S-40u): PAID SO FAR is one card: the payment,
                // then Mark paid back, Remind and Unlink… under it.
                if !links.isEmpty { APSheetLabel(text: "Paid so far") }
                APOptionCard {
                    ForEach(links) { link in
                        paymentLine(link)
                        APSeparator(afterFace: false)
                    }
                    APOptionRow(symbol: "arrow.uturn.backward", title: "Mark paid back",
                                   prominent: true) { onChoose(.markPaid) }
                    APSeparator()
                    APOptionRow(symbol: "pencil.line", title: "Remind \(p.name)") { onChoose(.remind) }
                    ForEach(links) { link in
                        APSeparator()
                        APOptionRow(symbol: "link", title: links.count == 1 ? "Unlink…" : "Unlink \(Format.amount(link.amount))…") {
                            onChoose(.unlink(link))
                        }
                    }
                }
                APSheetLabel(text: "Change the split")
                APOptionCard {
                    APOptionRow(symbol: "person.2", title: "Change the split") { onChoose(.changeShare) }
                    APSeparator()
                    // S-40u: Remove is the destructive row, in red, with
                    // what it gives back under it.
                    APOptionRow(symbol: "person", title: "Remove \(p.name)",
                                sub: p.paid >= 0.005 ? "The \(Format.amount(p.paid)) goes back to \(t.merchant)" : nil,
                                tone: Pearl.danger, titleTone: Pearl.danger) { onChoose(.remove) }
                        .accessibilityHint(p.paid >= 0.005 ? "" : (removeSub ?? ""))
                }
            } else if !links.isEmpty {
                APSheetLabel(text: "Paid so far")
                ForEach(links) { link in paymentCard(link) }
            }
            openPurchase
        }
    }

    /// S-40u: "Paid you $20.00 · Nov 14", or "Nothing yet".
    private var unsureLine: String {
        guard p.paid >= 0.005 else { return "Nothing yet" }
        let last = links.map(\.date).max()
        return "Paid you \(Format.amount(p.paid))" + (last.map { " · \(Format.short($0))" } ?? " so far")
    }

    /// S-40u: the payment at the top of the PAID SO FAR card, "e-Transfer ·
    /// Nov 14" and its amount in green; its Unlink… is a row below.
    private func paymentLine(_ link: Transaction.LinkInfo) -> some View {
        HStack(spacing: 12) {
            Text("\(Self.word(link)) · \(Format.short(link.date))").font(Nacre.body).foregroundColor(Pearl.ink)
            Spacer(minLength: 8)
            Text(Format.amount(link.amount)).font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.moneyIn)
        }
        .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 56)
        .accessibilityElement(children: .combine)
    }

    /// A+ `.quiet`, centred: "Open Loblaws" (AP-OwedPerson).
    @ViewBuilder private var openPurchase: some View {
        if let onOpen = onOpen {
            Button("Open \(t.merchant)", action: onOpen)
                .buttonStyle(NacreTextButtonStyle())
                .accessibilityIdentifier("open-purchase")
        }
    }

    private var setBody: some View {
        APSheet {
            APSheetHeader(face: p.name, overline: "\(t.merchant) · split \(ways) ways", title: p.name,
                             sub: headline, subTone: paidInFull ? Pearl.moneyIn : Pearl.muted, close: onClose)
            if answerExtra != nil {
                settledCard
            } else {
                paymentsCard
                stateCard
                payBackCard
                changeSplitCard
            }
            openPurchase
        }
        .sheet(item: $payment, onDismiss: {
            // The pick runs once its sheet has gone, as S-40's own do.
            let next = afterPayment
            afterPayment = nil
            if let next = next { onChoose(next) }
        }) { link in
            // S-05or: the payment's own options, View… and Unlink….
            PaybackOptionsSheet(link: link, overline: "PAID BACK", onClose: { payment = nil },
                                onView: { afterPayment = .view(link); payment = nil },
                                onUnlink: { afterPayment = .unlink(link); payment = nil })
        }
    }

    /// G2-APersonStates (S-40c, S-40c2; Rethought, approved): PAID WITH /
    /// PAID SO FAR, every payment one row in one card; a tap opens its options.
    @ViewBuilder private var paymentsCard: some View {
        // TEST-46 (G2-Person S-40a): while they still owe, the payments sit in
        // the PAID SO FAR card with Mark the rest paid back (stateCard).
        if !links.isEmpty && !(p.owes >= 0.005 && p.letGo == nil) {
            APSheetLabel(text: paidInFull ? "Paid with" : "Paid so far")
            APOptionCard {
                ForEach(Array(links.enumerated()), id: \.element.id) { i, link in
                    if i > 0 { APSeparator() }
                    paymentRow(link)
                }
            }
        }
    }

    /// S-40d Undo let it go, or S-40a / S-40b Mark paid back, Remind, Let it go.
    @ViewBuilder private var stateCard: some View {
        if p.letGo != nil {
            APOptionCard {
                APOptionRow(symbol: "arrow.triangle.2.circlepath", title: "Undo let it go",
                               sub: "\(p.name) owes you \(Format.amount(letGoAmount)) again", prominent: true) {
                    onChoose(.undoLetGo)
                }
            }
        } else if p.owes >= 0.005 {
            let part = p.paid >= 0.005
            // REFRESH-03 (S-40a, S-40b): subtitles that only described the
            // row are gone; VoiceOver keeps them as hints. The one that
            // costs money ("becomes your spending") stays.
            // G2-Person S-40a (TEST-46): PAID SO FAR is one card, each payment
            // then Mark the rest paid back, Remind and Let the rest go.
            if !links.isEmpty { APSheetLabel(text: "Paid so far") }
            APOptionCard {
                ForEach(links) { link in
                    paymentRow(link)
                    APSeparator()
                }
                APOptionRow(symbol: "arrow.uturn.backward", title: part ? "Mark the rest paid back" : "Mark paid back",
                               prominent: true) { onChoose(.markPaid) }
                    .accessibilityHint("By bank, cash or another app")
                APSeparator()
                APOptionRow(symbol: "pencil.line", title: "Remind \(p.name)") { onChoose(.remind) }
                    .accessibilityHint(part ? "Copies a message for the \(Format.amount(p.owes)) left"
                                            : "Copies a message for you to send")
                APSeparator()
                // G2-Person: the title alone; what it costs is the hint.
                APOptionRow(symbol: "chevron.right", title: part ? "Let the rest go" : "Let it go") { onChoose(.letGo) }
                    .accessibilityHint("The \(Format.amount(p.owes)) becomes your spending")
            }
        }
    }

    /// PB-42 note (1397:4698): S-40c keeps How much and Which purchase, each
    /// opening PB-42 on that step.
    @ViewBuilder private var payBackCard: some View {
        if paidInFull, links.count == 1, let link = links.first, TransactionDetailView.personPayback(link) {
            APOptionCard {
                APOptionRow(symbol: "target", title: "How much", sub: "All of it · \(Format.amount(link.amount))") {
                    onChoose(.howMuch(link))
                }
                APSeparator()
                APOptionRow(symbol: "cart", title: "Which purchase", sub: "\(t.merchant) · \(Format.weekdayDay(t.date))") {
                    onChoose(.whichPurchase(link))
                }
            }
        }
    }

    /// CHANGE THE SPLIT: Change Sam's share, Remove Sam.
    @ViewBuilder private var changeSplitCard: some View {
        APSheetLabel(text: "Change the split")
        APOptionCard {
            if p.paid >= 0.005 && p.owes >= 0.005 && p.letGo == nil {
                // S-48e: Sam paid less; his share reopens S-48a.
                APOptionRow(symbol: "person.2", title: "Change \(possessive(p.name)) share") { onChoose(.changeAnswer) }
            } else {
                APOptionRow(symbol: "person.2", title: "Change \(possessive(p.name)) share") { onChoose(.changeShare) }
            }
            APSeparator()
            // S-40c / S-40c2: what removing undoes first shows under the
            // title ("Unlinks both payments first").
            APOptionRow(symbol: "person", title: "Remove \(p.name)",
                        sub: p.paid >= 0.005 ? removeSub : nil) { onChoose(.remove) }
                .accessibilityHint(p.paid >= 0.005 ? "" : (removeSub ?? ""))
        }
    }

    /// G2-BOptions S-48e: after settling with an extra, one card: Change what
    /// the extra $6.67 is (reopens the question), View the payment, Unlink….
    @ViewBuilder private var settledCard: some View {
        if let extra = answerExtra {
            APOptionCard {
                APOptionRow(symbol: "arrow.triangle.2.circlepath", title: "Change what the extra \(Format.amount(extra)) is",
                               sub: "Reopens the question") {
                    onChoose(.changeAnswer)
                }
                .accessibilityHint((p.gift ?? 0) >= 0.005 ? "Now a gift" : "Now you owe \(p.name)")
                ForEach(links) { link in
                    if link.view != nil {
                        APSeparator()
                        APOptionRow(symbol: "eye", title: links.count == 1 ? "View the payment" : "View \(Format.amount(link.amount))") {
                            onChoose(.view(link))
                        }
                    }
                    APSeparator()
                    APOptionRow(symbol: "link", title: links.count == 1 ? "Unlink…" : "Unlink \(Format.amount(link.amount))…") {
                        onChoose(.unlink(link))
                    }
                }
            }
        }
    }

    /// The payment whose options are open (S-40c's tappable row).
    @State private var payment: Transaction.LinkInfo?
    @State private var afterPayment: PersonChoice?

    /// S-40c: "e-Transfer · Nov 16" over "Part of $60.00", $30.00, ›.
    private func paymentRow(_ link: Transaction.LinkInfo) -> some View {
        APLinkRow(symbol: Self.symbol(link.kind), title: "\(Self.word(link)) · \(Format.short(link.date))",
                     line: detail(link), amount: link.amount) { payment = link }
            .accessibilityLabel("\(Self.word(link)) · \(Format.short(link.date)), \(detail(link, spoken: true)), \(Format.amount(link.amount))")
            .accessibilityIdentifier("payment-\(link.id)")
    }

    private var paidInFull: Bool { p.owes < 0.005 && p.letGo == nil && p.paid >= 0.005 }

    /// S-48e: the extra a payer sent, whether she owes it back or it's a gift.
    private var answerExtra: Double? {
        let extra = (p.over ?? 0) + (p.gift ?? 0)
        return extra >= 0.005 ? extra : nil
    }

    /// REDESIGN-10: "Owes you $30.00", "Paid $10.00 · owes $20.00",
    /// "✓ Paid back in full · Nov 16", "You let $30.00 go · Nov 20".
    private var headline: String {
        if let gone = p.letGo { return "You let \(Format.amount(letGoAmount)) go · \(Format.short(gone.day))" }
        if p.owes >= 0.005 {
            return p.paid >= 0.005
                ? "Paid \(Format.amount(p.paid)) · owes \(Format.amount(p.owes))"
                : "Owes you \(Format.amount(p.owes))"
        }
        // S-48e: "Paid $40.00 · you owe Priya $6.67".
        if let over = p.over, over >= 0.005 {
            return "Paid \(Format.amount(p.paid)) · you owe \(p.name) \(Format.amount(over))"
        }
        if let gift = p.gift, gift >= 0.005 {
            return "Paid \(Format.amount(p.paid)) · \(Format.amount(gift)) a gift"
        }
        return "✓ Paid back in full" + (p.paidOn.map { " · \(Format.short($0))" } ?? "")
    }

    /// Remove's line: what it costs, or what asking first will say. None
    /// for someone let go (REFRESH-03, S-40d): it goes at once, with Undo.
    private var removeSub: String? {
        if p.paid < 0.005 {
            // S-40u2 (TEST-11): on Not sure yet nobody has a share, so
            // there's nothing to give back: "Nothing to unlink".
            if p.letGo != nil { return nil }
            return t.splitting?.unsure == true || p.share < 0.005 ? "Nothing to unlink"
                : "The \(Format.amount(p.share)) goes back to your share"
        }
        // G2-APersonStates: "Unlinks only Loblaws’ $30.00 first",
        // "Unlinks both payments first". Remove still asks before it goes.
        if links.count > 1 { return links.count == 2 ? "Unlinks both payments first" : "Unlinks \(links.count) payments first" }
        guard let link = links.first else { return nil }
        switch link.kind {
        case "cash": return "Forgets the \(Format.amount(link.amount)) cash first"
        case "app": return "Forgets the \(Format.amount(link.amount)) \(link.noun) first"
        default:
            return (link.others ?? []).isEmpty ? "Unlinks the \(link.noun) first"
                : "Unlinks only \(possessive(t.merchant)) \(Format.amount(link.amount)) first"
        }
    }

    /// One payment: what it was, how much of it was theirs here, then View
    /// (bank or a deposit only) and its own Unlink.
    private func paymentCard(_ link: Transaction.LinkInfo) -> some View {
        APPaymentCard(title: "\(Self.word(link)) · \(Format.short(link.date))", line: detail(link),
                      amount: link.amount, viewLabel: link.view?.label, onView: { onChoose(.view(link)) },
                      unlinkTitle: links.count == 1 && link.view != nil ? "Unlink…" : "Unlink \(Format.amount(link.amount))…",
                      onUnlink: { onChoose(.unlink(link)) })
    }

    /// G2-APersonStates: "You marked it", "Part of $60.00" (S-40c),
    /// "From Sam Lee" (S-40c2). The other purchases it paid are on its options.
    private func detail(_ link: Transaction.LinkInfo, spoken: Bool = false) -> String {
        switch link.kind {
        case "cash":
            return link.deposit.map { "Deposited \(Format.short($0.date))" } ?? "You marked it"
        case "app": return "You marked it"
        case "part": return link.message
        default:
            if let others = link.others, !others.isEmpty, let whole = link.whole {
                // VoiceOver still hears what else it paid back.
                return spoken ? "Part of \(Format.amount(whole)) · also paid back \(Format.andList(others))"
                    : "Part of \(Format.amount(whole))"
            }
            if let r = link.sheet.name.range(of: " from ") { return "From " + link.sheet.name[r.upperBound...] }
            return link.message
        }
    }

    static func symbol(_ kind: String) -> String {
        switch kind {
        case "cash": return "banknote"
        case "app": return "iphone"
        case "refund": return "cart"
        case "reimbursement": return "briefcase"
        default: return "creditcard"
        }
    }

    /// "e-Transfer", "Cash", "PayPal", "Part of a deposit".
    static func word(_ link: Transaction.LinkInfo) -> String {
        switch link.kind {
        case "cash": return "Cash"
        case "app": return link.noun.replacingOccurrences(of: " payment", with: "")
        case "part": return "Part of a deposit"
        default: return link.noun == "e-Transfer" ? "e-Transfer" : link.noun.prefix(1).uppercased() + link.noun.dropFirst()
        }
    }
}

/// The paid-back bar under a person (S-04r v2): rose on the track.
struct PaidBar: View {
    let paid: Double
    let of: Double
    var tone: Color = Pearl.action

    var body: some View {
        GeometryReader { g in
            ZStack(alignment: .leading) {
                Capsule().fill(Pearl.track)
                Capsule().fill(tone).frame(width: g.size.width * min(1, paid / max(of, 0.01)))
            }
        }
        .frame(height: 6)
    }
}

/// "Loblaws’ $30.00", "Pizza Nova’s $30.00".
func possessive(_ name: String) -> String {
    name.lowercased().hasSuffix("s") ? "\(name)’" : "\(name)’s"
}

// MARK: - S-07r Remind

/// S-07ra (owes) / S-07rb (part-paid): a message she can change, then
/// Copy. Pearl doesn't send anything (no server call; handoff 1096:4498).
struct RemindSheet: View {
    let t: Transaction
    let p: Transaction.Splitting.Person
    let onClose: () -> Void
    let onCopied: () -> Void
    @State private var text: String
    @FocusState private var editing: Bool
    private var unsure: Bool { t.splitting?.unsure == true }

    init(t: Transaction, p: Transaction.Splitting.Person, onClose: @escaping () -> Void,
         onCopied: @escaping () -> Void) {
        self.t = t
        self.p = p
        self.onClose = onClose
        self.onCopied = onCopied
        _text = State(initialValue: Self.message(t: t, p: p))
    }

    /// S-07ra: "Hey Priya! Your share of Loblaws on Nov 11 is $30.00. Thanks!"
    /// S-07rb (product owner, 2026-11-09): "Hey Sam! Thanks for the $10.00.
    /// Your share of Loblaws on Nov 11 was $30.00, so $20.00 to go."
    static func message(t: Transaction, p: Transaction.Splitting.Person) -> String {
        if t.splitting?.unsure == true {
            // S-07u (SPLIT-C): no amount, because she hasn't set one.
            return "Hi \(p.name)! When you get a chance, could you send me your part of \(t.merchant) from \(Format.short(t.date))? Thanks!"
        }
        let on = "\(t.merchant) on \(Format.short(t.date))"
        if p.paid >= 0.005 {
            return "Hey \(p.name)! Thanks for the \(Format.amount(p.paid)). Your share of \(on) was "
                + "\(Format.amount(p.amount)), so \(Format.amount(p.owes)) to go."
        }
        return "Hey \(p.name)! Your share of \(on) is \(Format.amount(p.owes)). Thanks!"
    }

    var body: some View {
        APSheet {
            // G2-CashRemind: "Remind Priya" centred, Priya and what's owed,
            // then the message in a well under its label.
            APSheetHeader(heading: "Remind \(p.name)", face: p.name, title: p.name,
                          sub: unsure ? "A friendly nudge" : "Owes you \(Format.amount(p.owes))",
                          close: onClose)
            VStack(alignment: .leading, spacing: 6) {
                Text("Message").font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
                    .accessibilityHidden(true)
                TextField("", text: $text, axis: .vertical)
                    .font(Nacre.body)
                    .foregroundColor(Pearl.ink).tint(Pearl.action)
                    .lineLimit(3...8)
                    .focused($editing)
                    .padding(.horizontal, 14).padding(.vertical, 12)
                    .frame(minHeight: 96, alignment: .topLeading)
                    .wellStyle(focused: editing)
                    .accessibilityLabel("Message to \(p.name)")
                    .accessibilityHint("Tap to change the message.")
                // REFRESH-03 (S-07ra, S-07rb, S-07u): one line under the message.
                Text("Pearl doesn’t send it. You paste it.")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } footer: {
            PearlSheetButtons(primary: "Copy message") {
                UIPasteboard.general.string = text
                onCopied()
            }
        }
    }
}

// MARK: - S-03fr Remove from the split?

/// What removing someone who paid does (S-03fr / S-03fr2, SPLIT-16 rules):
/// a line about what they paid, then WHAT CHANGES.
struct RemoveWords {
    let lead: String
    let changes: [String]
    /// A bank payment comes off: "Unlink and remove", else "Remove Sam".
    let unlinks: Bool

    /// `countsAgain` (S-03fu, a Not sure yet split): what the purchase counts
    /// as once their paybacks are unlinked, said instead of a share.
    init(_ p: Transaction.Splitting.Person, merchant: String, countsAgain: Double? = nil, only: Bool = false) {
        let name = p.name
        let shared = p.shared ?? []
        let kept = (p.cash ?? 0) + (p.app ?? 0)
        let bank = p.paid - kept - shared.map(\.here).reduce(0, +)
        let on = p.paidOn.map { " on \(Format.short($0))" } ?? ""
        var lead: [String] = [], changes: [String] = []
        // REFRESH-03: each consequence once, in a few words.
        for s in shared {
            let others = Format.andList(s.others)
            // S-03fr: "Jo paid $30.00 of a $60.00 e-Transfer."
            lead.append("\(name) paid \(Format.amount(s.here)) of a \(Format.amount(s.whole)) \(s.word).")
            changes.append("Only \(possessive(merchant)) \(Format.amount(s.here)) is unlinked. \(others) "
                           + "\(s.others.count == 1 ? "stays" : "stay") paid back.")
            changes.append("The \(Format.amount(s.here)) goes back to Needs a look.")
        }
        if bank >= 0.005 && countsAgain != nil {
            // G2-BRemove S-03fu: "Sam’s $20.00 e-Transfer goes back to Needs a look".
            let word = p.links?.first(where: { !["cash", "app"].contains($0.kind) }).map { PersonOptionsSheet.word($0) } ?? "payment"
            changes.append("\(possessive(name)) \(Format.amount(bank)) \(word) goes back to Needs a look")
        } else if bank >= 0.005 {
            // S-03f: "Priya’s $28.04 goes back to Needs a look."
            changes.append("\(possessive(name)) \(Format.amount(bank)) goes back to Needs a look.")
        }
        if kept >= 0.005 {
            let app = (p.app ?? 0) >= 0.005 && (p.cash ?? 0) < 0.005
            let day = p.payments?.last.map { " on \(Format.short($0.day))" } ?? on
            lead.append("\(name) paid you \(Format.amount(kept)) \(app ? "through another app" : "in cash")\(day).")
            // S-03fr2: "The $10.00 cash is forgotten."
            changes.append("The \(Format.amount(kept)) \(app ? "app payment" : "cash") is forgotten.")
        }
        if let counts = countsAgain {
            // G2-BRemove S-03fu: "Pizza Nova counts as $100.00 again"; the
            // only person (S-03fu1): "Nobody is left, so the split goes".
            changes.append("\(merchant) counts as \(Format.amount(counts)) again")
            if only { changes.append("Nobody is left, so the split goes") }
        } else {
            changes.append("\(possessive(name)) \(Format.amount(p.share)) share becomes yours.")
        }
        self.lead = lead.joined(separator: " ")
        self.changes = changes
        self.unlinks = bank >= 0.005 || !shared.isEmpty
    }
}

/// S-03fr: "Remove Jo from the split?", WHAT CHANGES, then Unlink and
/// remove / Keep Jo. From S-40 it saves at once: a spinner in the button
/// (S-03fr loading), and the champagne banner if it fails (S-03fr error).
/// From How to split it only takes them off the list until Save.
struct RemovePersonSheet: View {
    let p: Transaction.Splitting.Person
    let merchant: String
    /// S-03fu (a Not sure yet split): what the purchase counts as after.
    var countsAgain: Double? = nil
    let onClose: () -> Void
    /// Throws a message to show, or nothing went wrong.
    let run: () async throws -> Void
    /// G2-BRemove S-03fu1: the only person on a Not sure yet split, so the
    /// split goes with them. Set by whoever knows the split.
    var only = false
    @State private var busy = false
    @State private var failed: String?

    /// S-03fu1: `.onlyPerson(split.people.count == 1)` on the sheet.
    func onlyPerson(_ yes: Bool) -> RemovePersonSheet {
        var copy = self
        copy.only = yes
        return copy
    }

    var body: some View {
        let words = RemoveWords(p, merchant: merchant, countsAgain: countsAgain, only: only)
        APSheet(dismissDisabled: busy) {
            // G2-LetGo (Remove): the question centred, what they paid, then
            // WHAT CHANGES as bullets. S-03fu1: "Remove the only person?".
            APSheetHeader(heading: only && countsAgain != nil ? "Remove the only person?" : "Remove \(p.name) from the split?",
                          close: onClose)
                .disabled(busy)
            if !words.lead.isEmpty {
                Text(words.lead).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            APSheetLabel(text: "What changes")
            APBullets(lines: words.changes)
            if let failed = failed {
                // G2-BRemove: the error is a red line with ⓘ under WHAT CHANGES.
                Label(failed, systemImage: "exclamationmark.circle")
                    .font(Nacre.footnote).foregroundColor(Pearl.danger)
                    .fixedSize(horizontal: false, vertical: true)
            }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : words.unlinks ? "Unlink and remove" : "Remove \(p.name)",
                              busy: busy, busyLabel: "Removing…", secondary: "Keep \(p.name)",
                              onPrimary: { Task { await remove() } }, onSecondary: onClose)
        }
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t remove \(p.name). Nothing changed. Try again."
        }
    }
}

/// A refusal the server put in words ("That cash is in a deposit…"), shown
/// on the banner instead of the general line.
struct SplitMenuError: Error { let words: String }
