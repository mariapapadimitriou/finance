import SwiftUI

// POLISH-01 (Proposals › "Polish" 1387:1741, notes 1394:3145 to 1394:3149):
// the parts the question sheets share. RQ-01 Is this a recurring transfer?,
// PQ-01 Whose pay is this?, PQ-02 How often is this pay? and RT-02 v2 say
// why Pearl is asking, draw the payments as a rhythm (one pill per payment
// under its month), and answer with tiles that apply at once, with a toast
// and Undo after: no Save. Every question sheet takes the height of what it
// shows, and the whole screen only at accessibility text sizes.

/// "WHY PEARL IS ASKING", "YES, IT’S…": the caption over a part of a sheet.
struct QuestionCaption: View {
    let text: String

    var body: some View {
        Text(text.uppercased())
            .font(Nacre.caption1).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.leading, 16).padding(.top, 4)
            .accessibilityAddTraits(.isHeader)
    }
}

/// The rhythm (RQ-01, PQ-01, PQ-02, RT-02 v2): one pill per payment with its
/// day, under it the month. The ringed pill is the one waiting in Needs a
/// look (or the latest). Spread across the card when there are many, in a
/// row from the left when there are few; it scrolls rather than squeezes at
/// large text sizes.
struct RhythmStrip: View {
    /// Each payment's day ("2026-03-02"), oldest first.
    let dates: [String]
    /// What each one was, for VoiceOver ("March 2, $374.16").
    var amount: Double? = nil
    /// The day ringed; the latest when nil.
    var ringed: String? = nil
    /// RT-02 v2: a pill opens that transfer.
    var onTap: ((Int) -> Void)? = nil

    var body: some View {
        ViewThatFits(in: .horizontal) {
            strip
            ScrollView(.horizontal, showsIndicators: false) { strip }
        }
    }

    private var ring: String? { ringed ?? dates.last }

    private var strip: some View {
        HStack(alignment: .top, spacing: dates.count >= 7 ? 0 : 14) {
            ForEach(Array(dates.enumerated()), id: \.offset) { i, day in
                if i > 0 && dates.count >= 7 { Spacer(minLength: 4) }
                pill(i, day)
            }
            if dates.count < 7 { Spacer(minLength: 0) }
        }
    }

    @ViewBuilder private func pill(_ i: Int, _ day: String) -> some View {
        let number = Self.dayFormat.string(from: Format.localDay(day) ?? Date())
        let label = VStack(spacing: 4) {
            Text(number).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .frame(width: number.count > 1 ? 36 : 32, height: 32)
                .background(Capsule().fill(Pearl.action.opacity(0.1)))
                .overlay(Capsule().strokeBorder(Pearl.action, lineWidth: day == ring ? 1.5 : 0))
            Text(Self.monthFormat.string(from: Format.localDay(day) ?? Date()))
                .font(Nacre.caption1).foregroundColor(Pearl.muted)
        }
        .fixedSize()
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([Format.monthDay(day), amount.map { Format.amount($0) }].compactMap { $0 }.joined(separator: ", "))
        if let onTap = onTap {
            Button { onTap(i) } label: { label }
                .buttonStyle(.plain)
                .accessibilityHint("Opens that transfer")
        } else {
            label
        }
    }

    private static let dayFormat: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "d"
        return f
    }()

    private static let monthFormat: DateFormatter = {
        let f = DateFormatter()
        f.dateFormat = "MMM"
        return f
    }()
}

/// The card that says what Pearl sees: one plain sentence, the rhythm, and
/// a line under it ("Next one around Tue, Dec 2").
struct WhyCard: View {
    let sentence: String
    let dates: [String]
    var amount: Double? = nil
    var ringed: String? = nil
    var footer: String? = nil
    var onTap: ((Int) -> Void)? = nil

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            Text(sentence).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if !dates.isEmpty {
                RhythmStrip(dates: dates, amount: amount, ringed: ringed, onTap: onTap)
            }
            if let footer = footer {
                Text(footer).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
        }
        .padding(16)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(RoundedRectangle(cornerRadius: 22, style: .continuous).fill(Nacre.glass))
        .overlay(RoundedRectangle(cornerRadius: 22, style: .continuous).strokeBorder(Pearl.border, lineWidth: 1))
    }
}

/// An answer as a tile: its icon, its name and one line on what it does.
/// A tap answers at once. `current` rings the answer she has (RT-02 v2);
/// `guess` dashes Pearl's guess (PQ-02), which is never picked for her.
struct AnswerTile: View {
    let title: String
    let line: String
    var symbol: String? = nil
    var current = false
    var guess = false
    let action: () -> Void

    var body: some View {
        Button {
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            action()
        } label: {
            VStack(alignment: .leading, spacing: 4) {
                if let symbol = symbol {
                    Image(systemName: symbol).font(.system(size: 17)).foregroundColor(Pearl.action)
                        .frame(width: 36, height: 36)
                        .background(Circle().fill(Pearl.action.opacity(0.1)))
                }
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .padding(12)
            .frame(maxWidth: .infinity, minHeight: symbol == nil ? 71 : 110, alignment: .topLeading)
            .background(RoundedRectangle(cornerRadius: 18, style: .continuous).fill(Nacre.glass))
            .overlay(edge)
            .contentShape(RoundedRectangle(cornerRadius: 18, style: .continuous))
        }
        .buttonStyle(TilePress())
        .accessibilityElement(children: .ignore)
        // RQ-01 note: "Rent. Spending on rent. Button."
        .accessibilityLabel("\(title). \(line)")
        .accessibilityAddTraits(current ? [.isButton, .isSelected] : .isButton)
    }

    @ViewBuilder private var edge: some View {
        let shape = RoundedRectangle(cornerRadius: 18, style: .continuous)
        if current {
            shape.strokeBorder(Pearl.action, lineWidth: 2)
        } else if guess {
            shape.strokeBorder(Pearl.action, style: StrokeStyle(lineWidth: 1.5, dash: [5, 3]))
        } else {
            shape.strokeBorder(Pearl.border, lineWidth: 1)
        }
    }
}

/// RQ-01 motion: the tapped tile scales to 0.97 and back (spring, 250 ms);
/// none with Reduce Motion.
struct TilePress: ButtonStyle {
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    func makeBody(configuration: Configuration) -> some View {
        configuration.label
            .scaleEffect(configuration.isPressed && !reduceMotion ? 0.97 : 1)
            .animation(reduceMotion ? .easeInOut(duration: 0.2) : .spring(response: 0.25), value: configuration.isPressed)
    }
}

/// Tiles two (or three) across.
struct AnswerGrid<Content: View>: View {
    var columns = 2
    @ViewBuilder var content: () -> Content

    var body: some View {
        LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 7, alignment: .top), count: columns),
                  spacing: 7, content: content)
    }
}

/// "No, it isn’t regular · Ask me about each one on its own": the answer
/// that isn't a tile, as a row on its own card.
struct AnswerRow: View {
    let symbol: String
    let title: String
    let line: String
    let action: () -> Void

    var body: some View {
        Button {
            UINotificationFeedbackGenerator().notificationOccurred(.success)
            action()
        } label: {
            HStack(spacing: 12) {
                Image(systemName: symbol).font(.system(size: 17)).foregroundColor(Pearl.action)
                    .frame(width: 34, height: 34)
                    .background(Circle().fill(Pearl.action.opacity(0.1)))
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .padding(.horizontal, 16).padding(.vertical, 10)
            .frame(maxWidth: .infinity, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(TilePress())
        .glassCard(radius: 22)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(title). \(line)")
        .accessibilityAddTraits(.isButton)
    }
}

/// The line under a question's answers.
struct QuestionFooter: View {
    let text: String

    var body: some View {
        Text(text).font(Nacre.footnote).foregroundColor(Pearl.muted)
            .multilineTextAlignment(.center)
            .fixedSize(horizontal: false, vertical: true)
            .frame(maxWidth: .infinity)
            .padding(.horizontal, 8)
    }
}

// MARK: - Sized to content

/// The heights of a sheet's parts, added up.
private struct SheetPartsKey: PreferenceKey {
    static var defaultValue: CGFloat = 0
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value += nextValue() }
}

/// POLISH-01 audit 1 and 3 (AnswerSheet.swift:738): a question sheet takes
/// the height of what it shows, so no half-empty sheet and no page title
/// showing faintly above it. The whole screen only at accessibility text
/// sizes, where the content needs it to scroll.
private struct FitsContent: ViewModifier {
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var height: CGFloat = 0

    func body(content: Content) -> some View {
        content
            .onPreferenceChange(SheetPartsKey.self) { h in height = h }
            .presentationDetents(detents)
    }

    private var detents: Set<PresentationDetent> {
        if typeSize.isAccessibilitySize { return [.large] }
        if height < 1 { return [.medium] }
        return [.height(min(height + 16, UIScreen.main.bounds.height * 0.92))]
    }
}

extension View {
    /// One part of a sheet that `fitsContent()` measures: its title, its
    /// scrolling content, its buttons. Parts mustn't overlap.
    func sheetPart() -> some View {
        background(GeometryReader { g in Color.clear.preference(key: SheetPartsKey.self, value: g.size.height) })
    }

    /// Sizes the sheet to its `sheetPart()`s (POLISH-01).
    func fitsContent() -> some View {
        modifier(FitsContent())
    }

    /// `.large`, unless the sheet sizes itself (`fitsContent()`).
    @ViewBuilder func largeUnless(_ fits: Bool) -> some View {
        if fits { self } else { presentationDetents([.large]) }
    }
}
