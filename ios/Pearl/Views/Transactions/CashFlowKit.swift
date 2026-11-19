import SwiftUI

// A+ restyle, Cash flow (REDESIGN-08, -09, -14; rollout group 1, boards
// AP-CashFlow, AP-Transaction, AP-Sheet and G1-*). The parts the Cash flow,
// transaction and sorting screens share, drawn from the boards' kit.css /
// dirA.css values (px = pt). They sit on APlus.swift's tokens and change
// nothing outside the screens that use them.

// MARK: - Icon

/// kit `.icon`: a 36 pt disc in `action-wash` (action @ 10%) holding a line
/// icon in `action`; `.icon.dz` is the danger one; `.tile.slim .icon` is 32.
struct CFIcon: View {
    let symbol: String
    var size: CGFloat = 36
    var tone: Color = Pearl.action

    var body: some View {
        Image(systemName: symbol)
            .font(.system(size: size * 0.44, weight: .regular))
            .foregroundColor(tone)
            .frame(width: size, height: size)
            .background(Circle().fill(tone.opacity(0.1)))
            .accessibilityHidden(true)
    }
}

// MARK: - Glass button

/// `.glassbtn`: the 44 pt round button (Back, ✕, Filters): `card` over the
/// card line and the card shadow, the icon in ink.
struct CFGlassButton<Mark: View>: View {
    let label: String
    let action: () -> Void
    @ViewBuilder var mark: () -> Mark

    var body: some View {
        Button(action: action) {
            mark()
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(CFGlassDisc())
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

extension CFGlassButton where Mark == Image {
    init(symbol: String, label: String, action: @escaping () -> Void) {
        self.label = label
        self.action = action
        self.mark = { Image(systemName: symbol) }
    }
}

/// The glass disc behind `.glassbtn`.
struct CFGlassDisc: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Circle().fill(APlus.card)
            .background(.ultraThinMaterial, in: Circle())
            .overlay(Circle().strokeBorder(APlus.cardLine, lineWidth: 1))
            .shadow(color: scheme == .dark ? .black.opacity(0.22) : Pearl.cardShadow.opacity(0.10), radius: 14, y: 10)
    }
}

/// Back: the 44 pt glass circle with the chevron (AP-Transaction, G1-NeedsALook).
struct CFBackButton: View {
    let action: () -> Void

    var body: some View {
        CFGlassButton(label: "Back", action: action) {
            Image(systemName: "chevron.left").font(.system(size: 17, weight: .semibold))
        }
    }
}

/// ✕ on a sheet: the same glass circle (kit `.shead .glassbtn`).
struct CFCloseButton: View {
    var label = "Close"
    let action: () -> Void

    var body: some View {
        CFGlassButton(label: label, action: action) {
            Image(systemName: "xmark").font(.system(size: 15, weight: .semibold))
        }
    }
}

// MARK: - Sheet

/// kit `.shead`: the title centred in 17 semibold with the glass ✕ on the
/// right and, when there is one, a quiet action on the left ("Reset").
struct CFSheetTitle: View {
    let title: String
    var left: String? = nil
    var onLeft: () -> Void = {}
    let close: () -> Void

    var body: some View {
        ZStack {
            Text(title).font(Nacre.headline).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).lineLimit(2)
                .padding(.horizontal, 56)
                .accessibilityAddTraits(.isHeader)
            HStack {
                if let left = left {
                    Button(left, action: onLeft)
                        .font(Nacre.body).foregroundColor(Pearl.link)
                        .frame(minHeight: 44).contentShape(Rectangle())
                }
                Spacer()
                CFCloseButton(action: close)
            }
        }
        .frame(minHeight: 44)
        .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 10)
    }
}

/// kit `.sheet`: in light the nacre gradient under white 66% → 44%; in
/// dark #1C2F73 → #12163F.
struct CFSheetBackground: View {
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        Group {
            if scheme == .dark {
                LinearGradient(colors: [Color(hex: 0x1C2F73), Color(hex: 0x12163F)], startPoint: .top, endPoint: .bottom)
            } else {
                ZStack {
                    LinearGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass],
                                   startPoint: UnitPoint(x: -0.325, y: 0.324),
                                   endPoint: UnitPoint(x: 1.325, y: 0.676))
                    LinearGradient(colors: [.white.opacity(0.66), .white.opacity(0.44)],
                                   startPoint: .top, endPoint: .bottom)
                }
            }
        }
        .ignoresSafeArea()
        .accessibilityHidden(true)
    }
}

extension View {
    /// A Cash flow sheet on the A+ sheet surface, edge to edge where iOS
    /// lets us say so (16.4+).
    func cfSheet() -> some View {
        modifier(CFSheetSurface())
    }
}

private struct CFSheetSurface: ViewModifier {
    func body(content: Content) -> some View {
        if #available(iOS 16.4, *) {
            content.background(CFSheetBackground()).presentationBackground { CFSheetBackground() }
        } else {
            content.background(CFSheetBackground())
        }
    }
}

// MARK: - Ring and face

/// kit `.ring`: initials (or ⇄) on `face` inside the 1.2 pt nacre ring; 56
/// on a transaction page, 44 (`.ring.sm`) in a sheet's header.
struct CFRing: View {
    let name: String
    var size: CGFloat = 56
    var transfer = false
    /// The letters as given ("3" for three picked).
    var mark: String? = nil

    var body: some View {
        Text(mark ?? (transfer ? "\u{21C4}" : APFace.initials(name)))
            .font(.custom("Figtree-Medium", size: size >= 56 ? 17 : 15))
            .foregroundColor(Pearl.ink)
            .lineLimit(1).minimumScaleFactor(0.5)
            .frame(width: size - 2.4, height: size - 2.4)
            .background(Circle().fill(APlus.face))
            .padding(1.2)
            .background(Circle().fill(APlus.nacreRing))
            .accessibilityHidden(true)
    }
}

/// kit `.who`: a sheet's header, the small ring, the name in Fraunces 22 and
/// the amount line (AP-Sheet, G1-WhatWasThis, G1-Change, G1-Recurring).
struct CFWho: View {
    let name: String
    let line: String
    var tone: Color = Pearl.muted
    var mark: String? = nil
    var nameLines = 1
    var trailing: String? = nil
    var trailingTone: Color = Pearl.link
    var onTrailing: (() -> Void)? = nil

    var body: some View {
        HStack(alignment: .center, spacing: 12) {
            CFRing(name: name, size: 44, mark: mark)
            VStack(alignment: .leading, spacing: 0) {
                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    .lineLimit(nameLines).fixedSize(horizontal: false, vertical: true)
                    .accessibilityAddTraits(.isHeader)
                HStack(spacing: 0) {
                    Text(line).foregroundColor(tone)
                    if let trailing = trailing, let tap = onTrailing {
                        Text(" \u{00B7} ").foregroundColor(tone)
                        Button(trailing, action: tap).foregroundColor(trailingTone).buttonStyle(.plain)
                    }
                }
                .font(Nacre.subheadline)
                .fixedSize(horizontal: false, vertical: true)
            }
            Spacer(minLength: 0)
        }
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Pill

/// kit `.pill`: 28 high on `chip`, 13 pt ink, an arrow in its tone ("↓ Spending").
struct CFPill: View {
    let text: String
    var symbol: String? = nil
    var symbolTone: Color = Pearl.ink

    var body: some View {
        HStack(spacing: 6) {
            if let symbol = symbol {
                Image(systemName: symbol).font(.system(size: 11, weight: .semibold)).foregroundColor(symbolTone)
            }
            Text(text).lineLimit(1)
        }
        .font(Nacre.footnote).foregroundColor(Pearl.ink)
        .padding(.horizontal, 12).frame(height: 28)
        .background(Capsule().fill(APlus.chip))
        .accessibilityElement(children: .combine)
    }
}

/// G1-Months (T-53, T-67): what's narrowing the list, as pills on the
/// left, and Show all on the right in `link`. 16 above, 4 at the sides.
struct CFFilterStrip: View {
    let pills: [String]
    let showAll: () -> Void

    var body: some View {
        HStack(spacing: 8) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(pills, id: \.self) { CFPill(text: $0) }
                }
            }
            Button("Show all", action: showAll)
                .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(Pearl.link)
                .frame(minWidth: 44, minHeight: 44)
                .contentShape(Rectangle())
        }
        .padding(.horizontal, 4)
    }
}

/// A Pearl sheet of radio rows (T-106's Repeats and Your share): the title
/// with ✕, one card of choices, the chosen one's radio on. A row picks at
/// once; no Done. Never a stock Menu.
struct CFRadioSheet: View {
    let title: String
    let options: [(key: String, name: String)]
    let chosen: String
    let pick: (String) -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        APSheet {
            APSheetHeader(heading: title) { dismiss() }
            APOptionCard {
                ForEach(Array(options.enumerated()), id: \.element.key) { i, o in
                    if i > 0 { APSeparator(afterFace: false) }
                    Button { pick(o.key) } label: {
                        HStack(spacing: 12) {
                            APRadio(on: chosen == o.key)
                            Text(o.name).font(Nacre.body).foregroundColor(Pearl.ink)
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityAddTraits(chosen == o.key ? [.isButton, .isSelected] : .isButton)
                }
            }
        }
    }
}

// MARK: - Segmented switch

/// kit `.seg`: 38 high on `chip`, 3 in, the chosen half on `surface-card`
/// with a soft shadow; 15 pt medium. 44 pt to tap.
struct CFSegmented<Value: Hashable>: View {
    let options: [(value: Value, label: String)]
    @Binding var selection: Value

    var body: some View {
        HStack(spacing: 0) {
            ForEach(options, id: \.value) { o in
                let on = selection == o.value
                Button { withAnimation(.easeOut(duration: 0.2)) { selection = o.value } } label: {
                    Text(o.label)
                        .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.8)
                        .frame(maxWidth: .infinity).frame(height: 32)
                        .background(Capsule().fill(on ? Pearl.card : .clear)
                            .shadow(color: Color(red: 46 / 255, green: 37 / 255, blue: 71 / 255).opacity(on ? 0.12 : 0),
                                    radius: 1.5, y: 1))
                        .frame(height: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityAddTraits(on ? .isSelected : [])
            }
        }
        .padding(.horizontal, 3)
        .background(Capsule().fill(APlus.chip).frame(height: 38))
        .padding(.vertical, -3)
    }
}

// MARK: - Rows

/// What sits at a row's right edge.
enum CFTrailing {
    case none
    case chevron
    /// A quiet word in `link`, "Change".
    case word(String)
    /// The muted value and a chevron, "November ›".
    case value(String)
}

/// kit `.row.noface`: a 36 pt icon, the title (17) over an optional line
/// (15 muted), and what's on the right; 64 high, 12 / 16 in.
struct CFRowLabel: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var subTone: Color = Pearl.muted
    var bold = false
    var titleTone: Color = Pearl.ink
    var trailing: CFTrailing = .chevron
    var iconTone: Color = Pearl.action

    var body: some View {
        HStack(spacing: 12) {
            CFIcon(symbol: symbol, tone: iconTone)
            VStack(alignment: .leading, spacing: 2) {
                Text(title)
                    .font(bold ? Nacre.headline : Nacre.body).foregroundColor(titleTone)
                    .fixedSize(horizontal: false, vertical: true)
                if let sub = sub {
                    Text(sub).font(Nacre.subheadline).foregroundColor(subTone)
                        .fixedSize(horizontal: false, vertical: true)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            CFTrailingView(trailing: trailing)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
    }
}

struct CFTrailingView: View {
    let trailing: CFTrailing

    var body: some View {
        switch trailing {
        case .none:
            EmptyView()
        case .chevron:
            CFChevron()
        case .word(let w):
            Text(w).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline)).foregroundColor(Pearl.link)
        case .value(let v):
            HStack(spacing: 8) {
                Text(v).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                CFChevron()
            }
        }
    }
}

/// `.chev`: 8 × 14, muted.
struct CFChevron: View {
    var body: some View {
        Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
            .foregroundColor(Pearl.muted).accessibilityHidden(true)
    }
}

/// A row with the iOS switch (kit `.sw`, the action tint when on).
struct CFToggleRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    @Binding var isOn: Bool

    var body: some View {
        Toggle(isOn: $isOn) {
            HStack(spacing: 12) {
                CFIcon(symbol: symbol)
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
    }
}

// MARK: - Tiles

/// kit `.tile`: `card` with the 1 pt card line, radius 18, 12 in. Slim (one
/// line) or tall (icon over title and line). The current answer has a 2 pt
/// `action` line; Pearl's guess a 1.5 pt dashed `action` line.
struct CFTile: View {
    enum Mark { case rest, current, guess }

    let symbol: String
    let title: String
    var line: String? = nil
    var mark: Mark = .rest
    var iconTone: Color = Pearl.action
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Group {
                if let line = line {
                    VStack(alignment: .leading, spacing: 2) {
                        CFIcon(symbol: symbol, iconTone: iconTone).padding(.bottom, 6)
                        Text(title).font(.custom("Figtree-Regular", size: 16, relativeTo: .callout))
                            .foregroundColor(Pearl.ink).fixedSize(horizontal: false, vertical: true)
                        Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, minHeight: 72, alignment: .topLeading)
                } else {
                    HStack(spacing: 10) {
                        CFIcon(symbol: symbol, size: 32, tone: iconTone)
                        Text(title).font(.custom("Figtree-Regular", size: 16, relativeTo: .callout))
                            .foregroundColor(Pearl.ink).lineLimit(2).minimumScaleFactor(0.85)
                            .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .frame(maxWidth: .infinity, minHeight: 32, alignment: .leading)
                }
            }
            .padding(12)
            .background(CFTileSurface(mark: mark))
            .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityAddTraits(mark == .current ? .isSelected : [])
        .accessibilityHint(mark == .guess ? "Pearl’s guess" : "")
    }
}

private extension CFIcon {
    init(symbol: String, iconTone: Color) { self.init(symbol: symbol, tone: iconTone) }
}

struct CFTileSurface: View {
    var mark: CFTile.Mark = .rest

    var body: some View {
        let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
        shape.fill(APlus.card)
            .overlay {
                switch mark {
                case .rest: shape.strokeBorder(APlus.cardLine, lineWidth: 1)
                case .current: shape.strokeBorder(Pearl.action, lineWidth: 2)
                case .guess: shape.strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                }
            }
    }
}

/// kit `.tiles`: two across, 10 apart.
struct CFTileGrid<Content: View>: View {
    @ViewBuilder var content: () -> Content

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)],
                  alignment: .leading, spacing: 10, content: content)
    }
}

// MARK: - Banner and states

/// kit `.banner`: champagne 22% with its 1 pt line, radius 16, 15 pt.
struct CFBanner<Trailing: View>: View {
    let text: String
    /// T-58 (G1-Rows): a 16 pt rose ring turning before the words.
    var busy = false
    var trailing: () -> Trailing
    @Environment(\.colorScheme) private var scheme

    init(text: String, busy: Bool = false, @ViewBuilder trailing: @escaping () -> Trailing) {
        self.text = text
        self.busy = busy
        self.trailing = trailing
    }

    var body: some View {
        HStack(spacing: 12) {
            if busy { CFSpinner() }
            Text(text).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            trailing()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 44)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous)
            // Champagne at 22% in light; rgba(243, 217, 164, 0.10) in dark.
            .fill(Pearl.champagne.opacity(scheme == .dark ? 0.10 : 0.22)))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous).strokeBorder(Pearl.champagne, lineWidth: 1))
        .accessibilityElement(children: .combine)
    }
}

extension CFBanner where Trailing == EmptyView {
    init(text: String, busy: Bool = false) {
        self.init(text: text, busy: busy) { EmptyView() }
    }
}

/// The banner's 16 pt ring: 2 pt `action`, a quarter open, turning (still
/// with Reduce Motion).
struct CFSpinner: View {
    @State private var turning = false
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        Circle().trim(from: 0, to: 0.75)
            .stroke(Pearl.action, style: StrokeStyle(lineWidth: 2, lineCap: .round))
            .frame(width: 14, height: 14)
            .rotationEffect(.degrees(turning ? 360 : 0))
            .frame(width: 16, height: 16)
            .onAppear {
                guard !reduceMotion else { return }
                withAnimation(.linear(duration: 0.9).repeatForever(autoreverses: false)) { turning = true }
            }
            .accessibilityHidden(true)
    }
}

/// kit `.state`: a title in Fraunces 22, a muted line, and a quiet action.
/// `warn` (T-35e, G1-Results): the caution icon above, and the action as a
/// full-width Secondary.
struct CFState: View {
    let title: String
    let line: String
    var action: String? = nil
    var warn = false
    var run: () -> Void = {}

    var body: some View {
        VStack(spacing: 6) {
            if warn { APIcon.warn("exclamationmark.triangle") }
            Text(title).font(Nacre.title2).foregroundColor(Pearl.ink).multilineTextAlignment(.center)
                .padding(.top, warn ? 6 : 0)
            if !line.isEmpty {
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted).multilineTextAlignment(.center)
            }
            if let action = action {
                if warn {
                    Button(action, action: run)
                        .buttonStyle(APSecondaryButtonStyle())
                        .padding(.top, 14)
                } else {
                    Button(action, action: run)
                        .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                        .foregroundColor(Pearl.link)
                        .frame(minHeight: 44)
                        .padding(.top, 4)
                }
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 20).padding(.vertical, 40)
    }
}

/// T-35l (G1-Results): three rows holding their place while the month
/// loads: a `track` disc and two 12 pt bars (55% and 30%) in a card.
struct CFLoadingRows: View {
    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Color.clear.frame(height: 32)
            APCard {
                ForEach(0..<3, id: \.self) { i in
                    if i > 0 { APSeparator() }
                    HStack(spacing: 12) {
                        Circle().fill(Pearl.track).frame(width: 40, height: 40)
                        GeometryReader { g in
                            VStack(alignment: .leading, spacing: 8) {
                                Capsule().fill(Pearl.track).frame(width: g.size.width * 0.55, height: 12)
                                Capsule().fill(Pearl.track).frame(width: g.size.width * 0.30, height: 12)
                            }
                            .frame(maxHeight: .infinity)
                        }
                        .frame(height: 40)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                }
            }
        }
        .accessibilityElement()
        .accessibilityLabel("Loading your transactions")
    }
}

/// kit `.count`: the rose count chip (the tab tint, never red).
struct CFCount: View {
    let n: Int

    var body: some View {
        Text("\(n)")
            .font(.custom("Figtree-SemiBold", size: 13, relativeTo: .footnote))
            .foregroundColor(Pearl.onAction)
            .padding(.horizontal, 7).frame(minWidth: 22, minHeight: 22)
            .background(Capsule().fill(Pearl.action))
    }
}

/// kit `.chip`: 34 high, `chip` at rest, `action` when on; 15 pt.
struct CFChip: View {
    let label: String
    let on: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(label)
                .font(Nacre.subheadline)
                .foregroundColor(on ? Pearl.onAction : Pearl.ink)
                .lineLimit(1)
                .padding(.horizontal, 14).frame(height: 34)
                .background(Capsule().fill(on ? Pearl.action : APlus.chip))
                .frame(minHeight: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }
}

/// The big hero amount (kit `.hero .big`): Fraunces SemiBold 44, −0.88 tracked.
extension Font {
    static let cfBig = Font.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)
}
