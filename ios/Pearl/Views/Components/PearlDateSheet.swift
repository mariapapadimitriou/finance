import SwiftUI
import UIKit

// G0-DateSheet (DP-01 to DP-03; THL-173, THL-122, THL-127, THL-45, THL-289,
// THL-291), Pearl redesign canvas › Shared. One Pearl date sheet replaces
// every stock DatePicker (TEST-46): the grabber, the context title with the
// glass Close, the date as a Fraunces readout (always the real date, never
// "Today"), Today / Yesterday chips where the field allows them, the month
// grid on a card (always 6 rows, so the sheet never changes height) and one
// Done. Tapping a chip or a day only selects; Done writes the date; Close or
// a swipe down keeps the old one. No red anywhere.

/// What a date field may hold.
struct PearlDateRange {
    var earliest: Date? = nil
    var latest: Date? = nil

    /// A purchase or a payback: up to today.
    static var pastOnly: PearlDateRange { PearlDateRange(latest: Date()) }
    /// A bill's next payment: today onward.
    static var todayOnward: PearlDateRange { PearlDateRange(earliest: Date()) }
    static var any: PearlDateRange { PearlDateRange() }

    func allows(_ day: Date, _ cal: Calendar) -> Bool {
        let d = cal.startOfDay(for: day)
        if let e = earliest, d < cal.startOfDay(for: e) { return false }
        if let l = latest, d > cal.startOfDay(for: l) { return false }
        return true
    }

    func clamp(_ day: Date, _ cal: Calendar) -> Date {
        let d = cal.startOfDay(for: day)
        if let e = earliest, d < cal.startOfDay(for: e) { return cal.startOfDay(for: e) }
        if let l = latest, d > cal.startOfDay(for: l) { return cal.startOfDay(for: l) }
        return d
    }
}

struct PearlDateSheet: View {
    let title: String
    @Binding var selection: Date
    var range = PearlDateRange.any
    /// DP-01 / DP-03: Today and Yesterday, only where the field allows them.
    var quickPicks = false

    @Environment(\.dismiss) private var dismiss
    @State private var draft: Date
    @State private var month: Date
    @State private var forward = true
    @State private var bump = false

    private let cal = Calendar.current

    init(title: String, selection: Binding<Date>, range: PearlDateRange = .any, quickPicks: Bool = false) {
        self.title = title
        self._selection = selection
        self.range = range
        self.quickPicks = quickPicks
        let cal = Calendar.current
        let start = range.clamp(selection.wrappedValue, cal)
        _draft = State(initialValue: start)
        _month = State(initialValue: cal.date(from: cal.dateComponents([.year, .month], from: start)) ?? start)
    }

    var body: some View {
        PearlSheet {
            APSheetTitle(title: title) { dismiss() }
            Text(PearlDateText.readout(draft))
                .font(Pearl.display(.title2)).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity)
                .accessibilityLabel(PearlDateText.spoken(draft))
                .accessibilityAddTraits(.updatesFrequently)
            if quickPicks { chips }
            PearlMonthGrid(month: month, selected: draft, range: range, forward: forward, bump: bump,
                           pick: pick, step: step)
        } footer: {
            PearlSheetButtons(primary: "Done") {
                selection = draft
                dismiss()
            }
        }
    }

    // MARK: Today / Yesterday

    private var chips: some View {
        HStack(spacing: 8) {
            chip("Today", Date())
            if let y = cal.date(byAdding: .day, value: -1, to: Date()) { chip("Yesterday", y) }
        }
        .frame(maxWidth: .infinity)
    }

    @ViewBuilder
    private func chip(_ name: String, _ day: Date) -> some View {
        if range.allows(day, cal) {
            let on = cal.isDate(draft, inSameDayAs: day)
            Button { pick(day) } label: {
                Text(name)
                    .font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                    .foregroundColor(on ? Pearl.onAction : Pearl.ink)
                    .padding(.horizontal, 16)
                    .frame(minWidth: 44, minHeight: 36)
                    .background(Capsule().fill(on ? Pearl.action : APlus.chip))
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
        }
    }

    // MARK: Picking

    private func pick(_ day: Date) {
        let d = cal.startOfDay(for: day)
        guard range.allows(d, cal) else { return }
        UISelectionFeedbackGenerator().selectionChanged()
        draft = d
        let m = cal.date(from: cal.dateComponents([.year, .month], from: d)) ?? d
        if m != month { move(to: m) }
        guard !UIAccessibility.isReduceMotionEnabled else { return }
        bump = true
        withAnimation(.spring(response: 0.3, dampingFraction: 0.7)) { bump = false }
    }

    private func step(_ by: Int) {
        guard let m = cal.date(byAdding: .month, value: by, to: month) else { return }
        move(to: m)
    }

    private func move(to m: Date) {
        forward = m > month
        let motion: Animation = UIAccessibility.isReduceMotionEnabled
            ? .easeInOut(duration: 0.2) : .spring(response: 0.3, dampingFraction: 0.9)
        withAnimation(motion) { month = m }
    }
}

// MARK: - The month card

/// The month card: the 52 pt header (month and year, Previous / Next as
/// 44 pt `control` circles), weekday letters, then 6 rows of 44 × 44 days.
/// Swiping left or right changes the month.
struct PearlMonthGrid: View {
    let month: Date
    let selected: Date
    let range: PearlDateRange
    let forward: Bool
    let bump: Bool
    let pick: (Date) -> Void
    let step: (Int) -> Void

    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    private let cal = Calendar.current

    var body: some View {
        VStack(spacing: 0) {
            header
            weekdays
            days
                .id(month)
                .transition(slide)
        }
        .padding(.horizontal, 8).padding(.top, 4).padding(.bottom, 8)
        .clipped()
        .apCard(radius: Pearl.radiusCard)
        .gesture(DragGesture(minimumDistance: 24).onEnded { g in
            guard abs(g.translation.width) > 40, abs(g.translation.width) > abs(g.translation.height) else { return }
            let by = g.translation.width < 0 ? 1 : -1
            if by > 0 ? canGoNext : canGoBack { step(by) }
        })
    }

    private var slide: AnyTransition {
        if reduceMotion { return .opacity }
        let x: CGFloat = forward ? 24 : -24
        return .asymmetric(insertion: .offset(x: x).combined(with: .opacity),
                           removal: .offset(x: -x).combined(with: .opacity))
    }

    private var header: some View {
        HStack {
            Text(PearlDateText.month(month))
                .font(Nacre.headline).foregroundColor(Pearl.ink)
                .accessibilityAddTraits(.isHeader)
            Spacer()
            HStack(spacing: 4) {
                arrow("chevron.left", "Previous month", enabled: canGoBack) { step(-1) }
                arrow("chevron.right", "Next month", enabled: canGoNext) { step(1) }
            }
        }
        .padding(.leading, 8)
        .frame(minHeight: 52)
    }

    private func arrow(_ symbol: String, _ label: String, enabled: Bool, _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            Image(systemName: symbol).font(.system(size: 15, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(Circle().fill(Pearl.control))
        }
        .buttonStyle(.plain)
        .disabled(!enabled)
        .opacity(enabled ? 1 : 0.35)
        .accessibilityLabel(label)
    }

    private var canGoBack: Bool {
        guard let e = range.earliest else { return true }
        return month > cal.startOfDay(for: e)
    }

    private var canGoNext: Bool {
        guard let l = range.latest, let next = cal.date(byAdding: .month, value: 1, to: month) else { return true }
        return next <= cal.startOfDay(for: l)
    }

    private var weekdays: some View {
        let symbols = cal.veryShortStandaloneWeekdaySymbols
        let first = cal.firstWeekday - 1
        let ordered = Array(symbols[first...] + symbols[..<first])
        return HStack(spacing: 0) {
            ForEach(Array(ordered.enumerated()), id: \.offset) { _, s in
                Text(s).font(Nacre.caption2.weight(.semibold)).tracking(0.6)
                    .foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity, minHeight: 24, alignment: .bottom)
            }
        }
        .accessibilityHidden(true)
    }

    /// Always 6 rows of 7, blanks before the 1st and after the last day.
    private var days: some View {
        let cells = gridCells
        return VStack(spacing: 2) {
            ForEach(0..<6, id: \.self) { row in
                HStack(spacing: 0) {
                    ForEach(0..<7, id: \.self) { col in
                        cell(cells[row * 7 + col]).frame(maxWidth: .infinity)
                    }
                }
            }
        }
    }

    private var gridCells: [Date?] {
        let lead = (cal.component(.weekday, from: month) - cal.firstWeekday + 7) % 7
        let count = cal.range(of: .day, in: .month, for: month)?.count ?? 30
        var out: [Date?] = Array(repeating: nil, count: lead)
        for d in 0..<count { out.append(cal.date(byAdding: .day, value: d, to: month)) }
        while out.count < 42 { out.append(nil) }
        return Array(out.prefix(42))
    }

    @ViewBuilder
    private func cell(_ day: Date?) -> some View {
        if let day = day {
            PearlDayCell(day: day,
                         selected: cal.isDate(day, inSameDayAs: selected),
                         today: cal.isDateInToday(day),
                         allowed: range.allows(day, cal),
                         bump: bump) { pick(day) }
        } else {
            Color.clear.frame(width: 44, height: 44).accessibilityHidden(true)
        }
    }
}

/// One day: selected is `action` with `on-action` at 600; today (not
/// selected) a 1.5 pt `action` ring; out of range `muted` at 40%, not
/// tappable and hidden from VoiceOver.
private struct PearlDayCell: View {
    let day: Date
    let selected: Bool
    let today: Bool
    let allowed: Bool
    let bump: Bool
    let pick: () -> Void

    var body: some View {
        Button(action: pick) {
            Text("\(Calendar.current.component(.day, from: day))")
                .font(.custom(selected || today ? "Figtree-SemiBold" : "Figtree-Regular", size: 17, relativeTo: .body))
                .monospacedDigit()
                .lineLimit(1).minimumScaleFactor(0.6)
                .foregroundColor(colour)
                .frame(width: 44, height: 44)
                .background(Circle().fill(selected ? Pearl.action : Color.clear))
                .overlay(Circle().strokeBorder(Pearl.action, lineWidth: today && !selected ? 1.5 : 0))
                .scaleEffect(selected && bump ? 0.9 : 1)
                .contentShape(Circle())
        }
        .buttonStyle(.plain)
        .disabled(!allowed)
        .accessibilityHidden(!allowed)
        .accessibilityLabel((today ? "Today, " : "") + PearlDateText.spoken(day))
        .accessibilityAddTraits(selected ? [.isButton, .isSelected] : .isButton)
    }

    private var colour: Color {
        if selected { return Pearl.onAction }
        if !allowed { return Pearl.muted.opacity(0.4) }
        return today ? Pearl.action : Pearl.ink
    }
}

/// The sheet's words: "Tue, Nov 17", "November 2026", "Tuesday, November 17".
enum PearlDateText {
    private static func formatter(_ template: String) -> DateFormatter {
        let f = DateFormatter()
        f.setLocalizedDateFormatFromTemplate(template)
        return f
    }

    private static let short = formatter("EEEMMMd")
    private static let long = formatter("EEEEMMMMd")
    private static let monthYear = formatter("MMMMy")

    static func readout(_ d: Date) -> String { short.string(from: d) }
    static func spoken(_ d: Date) -> String { long.string(from: d) }
    static func month(_ d: Date) -> String { monthYear.string(from: d) }
}

extension View {
    /// Opens the Pearl date sheet (G0-DateSheet) for a date field.
    func pearlDateSheet(isPresented: Binding<Bool>, title: String, selection: Binding<Date>,
                        range: PearlDateRange = .any, quickPicks: Bool = false) -> some View {
        sheet(isPresented: isPresented) {
            PearlDateSheet(title: title, selection: selection, range: range, quickPicks: quickPicks)
        }
    }
}

/// A date row on a card: the label, the day on the right ("Today", "Wed,
/// Nov 12") and a chevron; it opens the Pearl date sheet.
struct PearlDateRow: View {
    let label: String
    let title: String
    @Binding var date: Date
    var range = PearlDateRange.any
    var quickPicks = false
    @State private var open = false

    var body: some View {
        Button { open = true } label: {
            HStack(spacing: 8) {
                Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer()
                Text(Format.dayHeader(Format.isoDay(date)))
                    .font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                APChevron()
            }
            .padding(.horizontal, 16).frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .pearlDateSheet(isPresented: $open, title: title, selection: $date, range: range, quickPicks: quickPicks)
    }
}
