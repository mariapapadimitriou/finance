import SwiftUI

// Cash flow as one continuous list (CF-SCROLL, canvas v47, approved
// 2026-11-19: T-01s, T-47, T-48, T-67, T-67c, T-53, T-45, T-18, G1-Scroll,
// G1-Months, G1-Search, G1-Category, AP-CashFlow). Every transaction in one
// scroll, newest first, under a divider per month ("October 2026"); the
// month card only chooses what its own summary shows; the large title folds
// into a glass bar that keeps Filters and +, with the month she is in pinned
// under it. The parts live here so TransactionsView's frames stay small.

// MARK: - The card's figures as filters (T-67, T-67c)

/// Spent, Saved or Came in tapped on the month card: the list narrows to
/// that month and kind. Leftover isn't a kind. "need a look" isn't one
/// either: it opens the Needs a look page (G1-NeedsALook).
enum CardKind: String, Equatable {
    case spent, saved, cameIn

    var label: String {
        switch self {
        case .spent: return "Spent"
        case .saved: return "Saved"
        case .cameIn: return "Came in"
        }
    }

    /// The card figure's own rows come from the server (`kind=` on the
    /// list), so they add up to exactly the card.
    var server: String {
        switch self {
        case .spent: return "spent"
        case .saved: return "saved"
        case .cameIn: return "income"
        }
    }
}

/// "Spent · November": a kind in one month, its chip under the card.
struct CardFilter: Equatable {
    let month: String
    let kind: CardKind

    var label: String { "\(kind.label) \u{00B7} \(Format.monthName(month))" }

    /// T-54's empty line, for this month and kind.
    var nothingLine: String {
        let m = Format.monthName(month)
        switch kind {
        case .spent: return "Nothing spent in \(m)."
        case .saved: return "Nothing saved in \(m)."
        case .cameIn: return "No money came in in \(m)."
        }
    }
}

// MARK: - The list, as lazy blocks

/// One category's line under By category (T-18): its rows in one month.
struct CFCategoryLine: Identifiable {
    let name: String
    let rows: [Transaction]
    let total: Double
    var id: String { name }
}

/// One item of the lazy list. Each is its own LazyVStack child, so only
/// what's on screen is built, however many years she scrolls back through.
enum CFBlock: Identifiable {
    /// "October 2026" (Fraunces 22). `shown` false: the month the card is
    /// already about, at the very top, keeps only its marker for the pin.
    case divider(month: String, shown: Bool)
    /// "TODAY", "WED, NOV 12"; Select on each month's first day.
    case day(month: String, title: String, select: Bool)
    /// By merchant: the merchant and what it came to.
    case group(month: String, title: String, total: Double)
    /// One card of rows, or one slice of a long card (`top` / `bottom`
    /// say whether this slice holds the card's first or last row).
    case rows(month: String, key: String, rows: [Transaction], top: Bool, bottom: Bool)
    /// By category: "SPENT", "MONEY IN", "NOT COUNTED" in one month.
    case kind(month: String, key: String, title: String, select: Bool)
    /// By category: that kind's categories in one month.
    case categories(month: String, key: String, lines: [CFCategoryLine])

    var month: String {
        switch self {
        case .divider(let m, _), .day(let m, _, _), .group(let m, _, _), .rows(let m, _, _, _, _),
             .kind(let m, _, _, _), .categories(let m, _, _):
            return m
        }
    }

    var id: String {
        switch self {
        case .divider(let m, _): return "m:" + m
        case .day(let m, let t, _): return "d:\(m):\(t)"
        case .group(let m, let t, _): return "g:\(m):\(t)"
        case .rows(let m, let k, let rows, _, _): return "r:\(m):\(k):\(rows.first?.id ?? "")"
        case .kind(let m, let k, _, _): return "k:\(m):\(k)"
        case .categories(let m, let k, _): return "c:\(m):\(k)"
        }
    }

    /// The rows, in the order the list shows them (newest first, or the
    /// sort's order within each month). `shown` is already sorted that way.
    static func build(_ shown: [Transaction], sort: TxFilters.Sort, byDay: Bool, byCategory: Bool,
                      hideFirst: Bool, select: Bool) -> [CFBlock] {
        // Months newest first; within a month the rows keep `shown`'s order,
        // so every sort groups within its month (CF-SCROLL item 6).
        var byMonth: [String: [Transaction]] = [:]
        for t in shown { byMonth[String(t.date.prefix(7)), default: []].append(t) }
        var out: [CFBlock] = []
        for (i, month) in byMonth.keys.sorted(by: >).enumerated() {
            let rows = byMonth[month] ?? []
            out.append(.divider(month: month, shown: !(i == 0 && hideFirst)))
            if byCategory {
                out += categoryBlocks(rows, month: month, select: select && i == 0)
            } else if byDay {
                out += dayBlocks(rows, month: month, select: select)
            } else if sort == .merchant {
                out += groupBlocks(rows, month: month)
            } else {
                out += cards(rows, month: month, key: "all")
            }
        }
        return out
    }

    /// Rows a lazy item holds at most: a longer card (a month under Largest
    /// first, or a search) is cut into slices that draw as one card, so the
    /// list stays lazy however many rows a month has.
    static let slice = 50

    /// One card's rows as one item, or as slices of `slice` rows.
    static func cards(_ rows: [Transaction], month: String, key: String) -> [CFBlock] {
        guard rows.count > slice else { return [.rows(month: month, key: key, rows: rows, top: true, bottom: true)] }
        return stride(from: 0, to: rows.count, by: slice).map { i in
            .rows(month: month, key: key, rows: Array(rows[i..<min(i + slice, rows.count)]),
                  top: i == 0, bottom: i + slice >= rows.count)
        }
    }

    /// T-01r: a card per day. Days keep the order they first come, so a row
    /// out of order never makes a second card for a day.
    private static func dayBlocks(_ rows: [Transaction], month: String, select: Bool) -> [CFBlock] {
        var order: [String] = []
        var by: [String: [Transaction]] = [:]
        for t in rows {
            let day = Format.dayHeader(t.date)
            if by[day] == nil { order.append(day) }
            by[day, default: []].append(t)
        }
        var out: [CFBlock] = []
        for (i, day) in order.enumerated() {
            out.append(.day(month: month, title: day, select: select && i == 0))
            out += cards(by[day] ?? [], month: month, key: day)
        }
        return out
    }

    /// By merchant: a card per merchant, with what it came to.
    private static func groupBlocks(_ rows: [Transaction], month: String) -> [CFBlock] {
        var out: [CFBlock] = []
        var title: String?
        var run: [Transaction] = []
        func flush() {
            guard let t = title, !run.isEmpty else { return }
            out.append(.group(month: month, title: t, total: run.reduce(0) { $0 + $1.amount }))
            out += cards(run, month: month, key: t)
        }
        for t in rows {
            if t.merchant != title { flush(); title = t.merchant; run = [] }
            run.append(t)
        }
        flush()
        return out
    }

    /// G1-Category: Spent, Money in and Not counted by category, per month.
    private static func categoryBlocks(_ rows: [Transaction], month: String, select: Bool) -> [CFBlock] {
        var out: [CFBlock] = []
        var first = true
        for (key, title) in [("spending", "Spent"), ("income", "Money in"), ("none", "Not counted")] {
            let lines = categoryLines(rows, counts: key)
            guard !lines.isEmpty else { continue }
            out.append(.kind(month: month, key: key, title: title, select: select && first))
            out.append(.categories(month: month, key: key, lines: lines))
            first = false
        }
        return out
    }

    /// The rows that count this way, one line per category, biggest first.
    static func categoryLines(_ rows: [Transaction], counts: String) -> [CFCategoryLine] {
        var by: [String: [Transaction]] = [:]
        for t in rows where t.counts == counts { by[t.label, default: []].append(t) }
        return by.map { name, rows in
            let sum = rows.reduce(0) { $0 + (counts == "spending" && $1.inflow ? -$1.amount : $1.amount) }
            return CFCategoryLine(name: name, rows: rows, total: sum)
        }
        .sorted { ($0.total, $1.name) > ($1.total, $0.name) }
    }
}

// MARK: - Where the list is (the folding bar and the pin)

/// The search row's bottom edge, in the Cash flow scroll's space: once it
/// has gone under the bar, the bar shows Filters and +.
struct CFTopEdgeKey: PreferenceKey {
    static var defaultValue: CGFloat = .infinity
    static func reduce(value: inout CGFloat, nextValue: () -> CGFloat) { value = min(value, nextValue()) }
}

/// Each month's top edge (the least of its blocks on screen), for the pin.
struct CFMonthEdgeKey: PreferenceKey {
    static var defaultValue: [String: CGFloat] = [:]
    static func reduce(value: inout [String: CGFloat], nextValue: () -> [String: CGFloat]) {
        value.merge(nextValue()) { min($0, $1) }
    }
}

/// The scroll's position, kept apart from TransactionsView's own state so a
/// scroll frame redraws only the bar and the pin, never the list.
@MainActor
final class CFScrollTracker: ObservableObject {
    /// The glass bar's height (cf.css `.cbar`).
    static let barHeight: CGFloat = 56

    @Published private(set) var folded = false
    @Published private(set) var month: String?
    /// How far the next month's divider has pushed the pin up (≤ 0).
    @Published private(set) var push: CGFloat = 0
    var pinHeight: CGFloat = 36

    /// The search row's last edge; .infinity when it isn't reported.
    private var edge: CGFloat = .infinity

    func top(_ edge: CGFloat) {
        self.edge = edge
        fold()
    }

    /// Folded once the search row is under the bar, or, deep in the list
    /// where the top may not report at all, while a month is pinned.
    private func fold() {
        let now = edge < Self.barHeight || (edge == .infinity && month != nil)
        if now != folded { withAnimation(.easeOut(duration: 0.18)) { folded = now } }
    }

    func months(_ edges: [String: CGFloat]) {
        let order = edges.keys.sorted(by: >)
        var current: String?
        var next: CGFloat = .infinity
        for (i, m) in order.enumerated() where (edges[m] ?? .infinity) <= Self.barHeight {
            current = m
            next = i + 1 < order.count ? edges[order[i + 1]] ?? .infinity : .infinity
        }
        if current != month { month = current }
        let p = min(0, next - (Self.barHeight + pinHeight))
        if abs(p - push) > 0.5 { push = p }
        fold()
    }
}

extension View {
    /// Reports this block's top edge as its month's, for the pin.
    func cfMonthEdge(_ month: String) -> some View {
        background(GeometryReader { g in
            Color.clear.preference(key: CFMonthEdgeKey.self, value: [month: g.frame(in: .named(CFScroll.space)).minY])
        })
    }

    /// Reports the search row's bottom edge, for the folding bar.
    func cfTopEdge() -> some View {
        background(GeometryReader { g in
            Color.clear.preference(key: CFTopEdgeKey.self, value: g.frame(in: .named(CFScroll.space)).maxY)
        })
    }
}

/// Cash flow's profile circle: level with the large title (16 down,
/// AP-CashFlow) and, once the title has folded, on the bar's centre line
/// (`ProfileSlot.top`).
struct CFProfileSlot: ViewModifier {
    @ObservedObject var tracker: CFScrollTracker
    let shown: Bool
    let enabled: Bool

    func body(content: Content) -> some View {
        content.profileCircleSlot(shown: shown, enabled: enabled,
                                  top: tracker.folded ? ProfileSlot.top : ProfileSlot.cashFlowTop)
    }
}

enum CFScroll {
    static let space = "cash-flow-scroll"
}

/// cf.css `.cbar`: scrolled, the large title folds into a 56 pt glass bar,
/// "Cash flow" on the left, with Filters and + (40 pt) still in reach; the
/// month she is in pins under it (`.pin`), with what's narrowing the list.
/// The profile circle stays pinned at the bar's right end, on its centre
/// line (`ProfileSlot`), with Filters and + just left of it. Centred, the
/// title ran into them on a 375 pt iPhone, so it sits small on the left
/// (product owner, 2026-11-19).
struct CFFoldedBar: View {
    @ObservedObject var tracker: CFScrollTracker
    let filtersOn: Bool
    let chips: [CFChipItem]
    let filters: () -> Void
    let add: () -> Void

    var body: some View {
        VStack(spacing: 0) {
            if tracker.folded {
                bar
                if let month = tracker.month {
                    pin(month).offset(y: tracker.push)
                }
            }
        }
        .frame(maxWidth: .infinity, alignment: .top)
    }

    private var bar: some View {
        HStack(spacing: 8) {
            Text("Cash flow").font(Nacre.headline).foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.8)
                .accessibilityAddTraits(.isHeader)
            Spacer(minLength: 8)
            CFBarButton(symbol: "slider.horizontal.3", label: filtersOn ? "Filters, on" : "Filters",
                        dot: filtersOn, action: filters)
            CFBarButton(symbol: "plus", label: "Add a transaction", dot: false, action: add)
        }
        // The title on the large title's edge (gutter + 4); + stops 4 short
        // of the circle's 44 pt target, a 10 pt gap between the discs.
        .padding(.leading, Pearl.gutter + 4).padding(.trailing, ProfileSlot.clearance + 4)
        .frame(height: CFScrollTracker.barHeight)
        .background(CFGlassStrip(strong: true).ignoresSafeArea(edges: .top))
        .zIndex(1)
        .transition(.opacity)
    }

    private func pin(_ month: String) -> some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(Format.month(month)).font(.custom("Fraunces-SemiBold", size: 17, relativeTo: .headline)).foregroundColor(Pearl.ink)
            if !chips.isEmpty { CFChipWrap(chips: chips) }
        }
        .padding(.horizontal, 20).padding(.top, chips.isEmpty ? 6 : 4).padding(.bottom, 8)
        .frame(maxWidth: .infinity, alignment: .leading)
        .background(CFGlassStrip(strong: false))
        .overlay(alignment: .bottom) { Rectangle().fill(APlus.separator).frame(height: 0.5) }
        .background(GeometryReader { g in
            Color.clear.onAppear { tracker.pinHeight = g.size.height }
                .onChange(of: g.size.height) { tracker.pinHeight = $0 }
        })
        .accessibilityElement(children: .contain)
        .transition(.opacity)
    }
}

/// The bar's 40 pt glass buttons (cf.css `.cbar .glassbtn`), 44 to tap.
private struct CFBarButton: View {
    let symbol: String
    let label: String
    let dot: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 16, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 40, height: 40)
                .background(CFGlassDisc())
                .overlay(alignment: .topTrailing) {
                    // The filter dot: ink, never red.
                    if dot {
                        Circle().fill(Pearl.ink).frame(width: 8, height: 8)
                            .overlay(Circle().strokeBorder(APlus.circleDisc, lineWidth: 2).padding(-2))
                            .offset(x: -4, y: 4).accessibilityHidden(true)
                    }
                }
                .frame(width: 44, height: 44).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// The bar's and the pin's glass: blur with the screen's own wash.
private struct CFGlassStrip: View {
    let strong: Bool
    @Environment(\.colorScheme) private var scheme

    var body: some View {
        let light: (Double, Double) = strong ? (0.62, 0.40) : (0.40, 0.12)
        let dark: (Double, Double) = strong ? (0.82, 0.62) : (0.62, 0.35)
        let base = scheme == .dark ? Color(red: 18 / 255, green: 22 / 255, blue: 63 / 255) : Color.white
        let (top, bottom) = scheme == .dark ? dark : light
        return LinearGradient(colors: [base.opacity(top), base.opacity(bottom)], startPoint: .top, endPoint: .bottom)
            .background(.ultraThinMaterial)
    }
}

/// "October 2026": a month's divider in the list (cf.css `.mdiv`),
/// Fraunces 22, 36 above. The first month's, when the card already names
/// it, is only a marker for the pin.
struct CFMonthDivider: View {
    let month: String
    let shown: Bool

    var body: some View {
        if shown {
            Text(Format.month(month)).font(.custom("Fraunces-SemiBold", size: 22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                .padding(.horizontal, 4)
                .frame(maxWidth: .infinity, alignment: .leading)
                .accessibilityAddTraits(.isHeader)
                .cfMonthEdge(month)
                .padding(.top, 36).padding(.bottom, 2)
        } else {
            Color.clear.frame(height: 0).cfMonthEdge(month).accessibilityHidden(true)
        }
    }
}

// MARK: - A long card in slices

/// One slice of a long card: the A+ card (`APCardSurface`'s fill, line and
/// shadow) drawn as one tall rounded card and cut to this slice, so only
/// the first slice has the rounded top and only the last the rounded
/// bottom, with no line or shadow where two slices meet.
struct CFCardSlice: ViewModifier {
    let top: Bool
    let bottom: Bool
    var radius: CGFloat = Pearl.radiusCard

    func body(content: Content) -> some View {
        content
            .frame(maxWidth: .infinity, alignment: .leading)
            .clipShape(CFSliceShape(top: top, bottom: bottom, radius: radius, edges: false))
            .background(
                GeometryReader { g in
                    let reach = radius + 2
                    APCardSurface(radius: radius)
                        .frame(height: g.size.height + (top ? 0 : reach) + (bottom ? 0 : reach))
                        .offset(y: top ? 0 : -reach)
                }
                .clipShape(CFSliceShape(top: top, bottom: bottom, radius: radius, edges: true))
            )
    }
}

/// Where a slice may draw. `edges`: the card's surface, with room for its
/// shadow at the sides and at the card's own top and bottom, cut flat where
/// it meets the next slice. Otherwise the content, rounded at the card's
/// own corners only.
private struct CFSliceShape: Shape {
    let top: Bool
    let bottom: Bool
    let radius: CGFloat
    let edges: Bool

    func path(in r: CGRect) -> Path {
        if edges {
            let out: CGFloat = 40
            return Path(CGRect(x: r.minX - out, y: top ? r.minY - out : r.minY, width: r.width + 2 * out,
                               height: r.height + (top ? out : 0) + (bottom ? out : 0)))
        }
        let reach = radius + 2
        let tall = CGRect(x: r.minX, y: top ? r.minY : r.minY - reach, width: r.width,
                          height: r.height + (top ? 0 : reach) + (bottom ? 0 : reach))
        return Path(roundedRect: tall, cornerRadius: radius, style: .continuous)
    }
}

// MARK: - Chips (cf.css `.fchip`)

/// One thing narrowing the list, and how to take it off.
struct CFChipItem: Identifiable {
    let id: String
    let label: String
    let clear: () -> Void
}

/// cf.css `.fchip`: 34 high, `action-wash` with a rose edge, 15 pt medium
/// ink, and its ✕ (28, 44 to tap) that clears it.
struct CFClearChip: View {
    let item: CFChipItem

    var body: some View {
        HStack(spacing: 4) {
            Text(item.label).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(Pearl.ink).lineLimit(1)
            Button(action: item.clear) {
                Image(systemName: "xmark").font(.system(size: 11, weight: .bold)).foregroundColor(Pearl.ink)
                    .frame(width: 28, height: 28)
                    .frame(width: 44, height: 44).contentShape(Rectangle())
                    .padding(.vertical, -5).padding(.horizontal, -8)
            }
            .buttonStyle(.plain)
            .accessibilityLabel("Clear \(item.label)")
        }
        .padding(.leading, 14).padding(.trailing, 4)
        .frame(height: 34)
        .background(Capsule().fill(APlus.actionWash))
        .overlay(Capsule().strokeBorder(Pearl.action.opacity(0.35), lineWidth: 1))
    }
}

/// The chips, wrapping onto as many lines as they need, 8 apart.
struct CFChipWrap: View {
    let chips: [CFChipItem]

    var body: some View {
        FlowLayout(spacing: 8) {
            ForEach(chips) { CFClearChip(item: $0) }
        }
    }
}

// MARK: - The card's need-a-look row

/// G1-Months / AP-CashFlow: "6 need a look" (the month's own count) with a
/// chevron, one tap target that opens the Needs a look page (G1-NeedsALook),
/// whose Quick sort card sorts them. No Sort capsule, no list filter, no
/// streak (product owner, after #398).
struct CFLookRow: View {
    let count: Int
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 12) {
                CFCount(n: count)
                Text("need\(count == 1 ? "s" : "") a look").font(Nacre.body).foregroundColor(Pearl.ink)
                    .lineLimit(1)
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 14, weight: .semibold))
                    .foregroundColor(Pearl.muted)
                    .accessibilityHidden(true)
            }
            .padding(.leading, 16).padding(.trailing, 16).padding(.vertical, 4)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(count) need\(count == 1 ? "s" : "") a look")
        .accessibilityHint("Opens Needs a look")
        .accessibilityAddTraits(.isButton)
        .accessibilityIdentifier("cf-need-a-look")
    }
}
