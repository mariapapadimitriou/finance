import SwiftUI

// The Allowance gauge (H-00r v2, AP-Home; n-home-gauge, decided 2026-11-21)
// and Cash flow's month meter (T-01r, AP-CashFlow; n-cf-meter, 2026-11-22):
// one picture of the month in two sizes. Three zones of the Allowance,
// seaglass to 80%, lilac to 100% (getting close), rose past it (over); the
// fill ends on the pearl bead and a tick marks where she'd be today. Every
// number is the server's (`safe_to_spend.compute`'s `allowance`, `spent`,
// `zone`, `shown`, `per_day`, `days_left`). THL-125, THL-123, THL-122.

/// On track, getting close or over: the server's `zone`.
enum AllowanceZone: String {
    case ok, close, over

    init(_ a: Allowance) {
        self = AllowanceZone(rawValue: a.zone ?? "") ?? (a.state == "over" ? .over : .ok)
    }

    /// The chip's words.
    var words: String {
        switch self {
        case .ok: return "On track"
        case .close: return "Getting close"
        case .over: return "Over"
        }
    }

    /// home.css `.ag-chip.ok/.close/.over`.
    var chipFill: Color {
        switch self {
        case .ok: return Pearl.dynamic(light: 0xE3F5F2, dark: 0x173B4C)
        case .close: return Pearl.dynamic(light: 0xF0EBFF, dark: 0x2C2763)
        case .over: return Pearl.dynamic(light: 0xFCE9F0, dark: 0x3B2050)
        }
    }

    var chipInk: Color {
        switch self {
        case .ok: return Pearl.dynamic(light: 0x1E7468, dark: 0x9BE6DB)
        case .close: return Pearl.dynamic(light: 0x6A4FB3, dark: 0xD3C1FF)
        case .over: return Pearl.dynamic(light: 0xA3204F, dark: 0xFFB8CE)
        }
    }

    /// The fill's two ends, and the bead's glow (CX-Gauge's gp0, gp1, gp2).
    var fill: [Color] {
        switch self {
        case .ok: return [Color(hex: 0x8FE0D4), Color(hex: 0xC9A8FF)]
        case .close: return [Color(hex: 0xC9A8FF), Color(hex: 0xFF8FB1)]
        case .over: return [Color(hex: 0xFF8FB1), Color(hex: 0xE0457B)]
        }
    }

    var glow: Color { fill[1] }

    /// The three zones' tracks (`.agauge .z1/.z2/.z3`, `.cfm-track`).
    static let zones = [Pearl.dynamic(light: 0xCDEFEA, dark: 0x1D4A57),
                        Pearl.dynamic(light: 0xEBDDFB, dark: 0x3A3375),
                        Pearl.dynamic(light: 0xFAD3DF, dark: 0x552A5C)]
    /// The amount when over (`.ag-amt.over`).
    static let overInk = Pearl.dynamic(light: 0xA3204F, dark: 0xFFB8CE)
}

extension Allowance {
    /// The gauge and the meter run to 115% of the Allowance: 80 seaglass,
    /// 20 lilac, 15 rose.
    static let scale = 1.15

    /// Has the gauge's numbers (not without income).
    var hasGauge: Bool { state != "needs_income" && total != nil && spent != nil }

    /// Spent, as a share of the gauge (0…1).
    var spentShare: Double {
        guard let total = total, let spent = spent else { return 0 }
        guard total > 0.5 else { return spent > 0 ? 1 : 0 }
        return min(max(spent / total / Self.scale, 0), 1)
    }

    /// Where she'd be today if she spent evenly, as a share of the gauge:
    /// the days gone of the month (or of the part it covers, O-11d).
    var todayShare: Double? {
        guard let month = month, let left = daysLeft,
              let first = Format.localDay(month + "-01"),
              var days = Calendar.current.range(of: .day, in: .month, for: first)?.count else { return nil }
        if let from = from, let start = Format.localDay(from) {
            days -= Calendar.current.component(.day, from: start) - 1
        }
        guard days > 0 else { return nil }
        return min(max(Double(days - left) / Double(days) / Self.scale, 0), 1)
    }

    /// "$829", "~$820" for an estimate; over, what she's over by.
    var leftText: String {
        if state == "over" { return Format.whole(overBy ?? 0) }
        let value = Format.whole(shown ?? amount ?? 0)
        return estimate == true ? "~" + value : value
    }

    /// "$69 a day".
    var perDayText: String? { perDay.map { "\(Format.whole($0)) a day" } }

    /// "For 12 days", "For 1 day".
    var forDaysText: String? { daysLeft.map { $0 == 1 ? "For 1 day" : "For \($0) days" } }

    /// VoiceOver, as AP-Home's: "Allowance: $829 left in November. $1,284
    /// spent of $2,113. On track."
    var gaugeSpoken: String {
        guard hasGauge else { return "Allowance. " + Allowance.needsIncomeLine }
        let month = self.month.map { Format.monthName($0) } ?? "this month"
        let zone = AllowanceZone(self)
        let head = state == "over" ? "\(leftText) over your Allowance in \(month)."
                                   : "\(leftText) left in \(month)."
        let of = "\(Format.whole(spent ?? 0)) spent of \(Format.whole(total ?? 0))."
        return "Allowance: \(head) \(of) \(zone.words)."
    }
}

/// `.ag-chip`: 24 high, 12/600, the tick only when on track.
struct AllowanceChip: View {
    let zone: AllowanceZone

    var body: some View {
        HStack(spacing: 4) {
            if zone == .ok {
                // home.css: the board's 12 × 12 tick, stroke 2.2 on a 24 grid.
                ChipTick()
                    .stroke(zone.chipInk, style: StrokeStyle(lineWidth: 2.2 / 2, lineCap: .round, lineJoin: .round))
                    .frame(width: 12, height: 12)
                    .accessibilityHidden(true)
            }
            Text(zone.words).font(.custom("Figtree-SemiBold", size: 12, relativeTo: .caption))
        }
        .foregroundColor(zone.chipInk)
        .padding(.horizontal, 9)
        .frame(height: 24)
        .background(Capsule().fill(zone.chipFill))
    }
}

/// The pearl bead (`#agbx1`): white to lilac to mist, a white edge, a glow.
/// On the gauge it is r 13 with a 2 pt white stroke on its edge, 28 across,
/// under `drop-shadow(0 0 7px)` in the zone's colour. On the meter
/// (`.cfm-fill .bead`) it is 18 across with a 1.5 pt inner white line, a
/// lilac glow (0 0 8, #C9A8FF @90%) and a small drop (0 1 3, #1F1B2E @20%).
struct AllowanceBead: View {
    let size: CGFloat
    let glow: Color
    var edge: CGFloat = 2
    var meter = false

    var body: some View {
        Circle()
            .fill(RadialGradient(stops: [.init(color: .white, location: 0),
                                         .init(color: Color(hex: 0xF6EFFF), location: 0.5),
                                         .init(color: Color(hex: 0xC9DCF5), location: 1)],
                                 center: UnitPoint(x: 0.35, y: 0.30), startRadius: 0, endRadius: size * 0.75))
            .overlay(Circle().strokeBorder(Color.white, lineWidth: edge))
            // CSS blur is about twice SwiftUI's radius.
            .shadow(color: meter ? Color(hex: 0xC9A8FF).opacity(0.9) : glow, radius: meter ? 4 : 3.5)
            .shadow(color: meter ? Color(hex: 0x1F1B2E).opacity(0.2) : .clear, radius: 1.5, y: 1)
            .frame(width: size, height: size)
            .accessibilityHidden(true)
    }
}

/// The chip's tick: M5 12.5 l4.5 4.5 L19 7.5 on a 24 grid.
struct ChipTick: Shape {
    func path(in rect: CGRect) -> Path {
        let k = min(rect.width, rect.height) / 24
        var p = Path()
        p.move(to: CGPoint(x: 5 * k, y: 12.5 * k))
        p.addLine(to: CGPoint(x: 9.5 * k, y: 17 * k))
        p.addLine(to: CGPoint(x: 19 * k, y: 7.5 * k))
        return p.offsetBy(dx: rect.minX, dy: rect.minY)
    }
}

/// The month's chevron (AP-CashFlow): M1 1.5 l5 5 5-5 on a 12 × 8 grid, 11 × 8.
struct MonthChevron: Shape {
    func path(in rect: CGRect) -> Path {
        let x = rect.width / 12, y = rect.height / 8
        var p = Path()
        p.move(to: CGPoint(x: 1 * x, y: 1.5 * y))
        p.addLine(to: CGPoint(x: 6 * x, y: 6.5 * y))
        p.addLine(to: CGPoint(x: 11 * x, y: 1.5 * y))
        return p.offsetBy(dx: rect.minX, dy: rect.minY)
    }
}

// MARK: - Home's gauge

/// H-00r v2 (AP-Home, AP-HomeCalm and every Home board): the 320 × 282 dial
/// (`.ag-dial`), then spent so far | the daily amount (`.ag-stats`). Over,
/// "Over your Allowance" in rose and the Allowance on the right (CX-Gauge's
/// over state). Tapping it opens How it adds up (n-home-gauge).
struct AllowanceGauge: View {
    let allowance: Allowance
    let open: () -> Void

    var body: some View {
        let zone = AllowanceZone(allowance)
        VStack(spacing: 4) {
            Button(action: open) {
                ZStack(alignment: .top) {
                    GaugeDial(spent: allowance.spentShare, today: allowance.todayShare, zone: zone)
                    GaugeCentre(allowance: allowance, zone: zone).padding(.top, 94)
                }
                .frame(width: 320, height: 282, alignment: .top)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(allowance.gaugeSpoken)
            // The usual line under it, hidden on Home (REFRESH-03), is read here.
            .accessibilityHint(allowance.ringCaption == Allowance.restCaption
                               ? "\(Allowance.restCaption) Opens How it adds up." : "Opens How it adds up.")
            .accessibilityAddTraits([.isButton, .isHeader])
            .accessibilityIdentifier("allowance-gauge")
            if allowance.hasGauge { GaugeStats(allowance: allowance, zone: zone) }
        }
        .frame(maxWidth: .infinity)
    }
}

/// The dial: the pearl disc (r 110), the three zones on a 132 arc from
/// 235° to 125° (250° of sweep), the fill, the today tick and the bead.
private struct GaugeDial: View {
    let spent: Double
    let today: Double?
    let zone: AllowanceZone

    @Environment(\.colorScheme) private var scheme

    static let centre = CGPoint(x: 160, y: 160)
    static let radius: CGFloat = 132
    /// Of the gauge: 80% and 100% of 115, about 3° apart as AP-Home's
    /// paths are (1.6° of the 250° sweep either side).
    static let gap = 1.6 / 250
    static let bounds: [(Double, Double)] = [(0, 0.8 / 1.15 - gap),
                                             (0.8 / 1.15 + gap, 1 / 1.15 - gap),
                                             (1 / 1.15 + gap, 1)]

    var body: some View {
        ZStack(alignment: .topLeading) {
            disc
            ForEach(0..<3, id: \.self) { i in
                GaugeArc(from: Self.bounds[i].0, to: Self.bounds[i].1)
                    .stroke(AllowanceZone.zones[i], style: StrokeStyle(lineWidth: 14, lineCap: .round))
            }
            if spent > 0.001 {
                GaugeArc(from: 0, to: spent)
                    .stroke(LinearGradient(colors: zone.fill,
                                           startPoint: UnitPoint(x: 52 / 320, y: 236 / 300),
                                           endPoint: Self.unit(Self.point(spent, Self.radius))),
                            style: StrokeStyle(lineWidth: 14, lineCap: .round))
            }
            if let today = today {
                Path { p in
                    p.move(to: Self.point(today, 144))
                    p.addLine(to: Self.point(today, 154))
                }
                .stroke(Pearl.ink.opacity(0.5), style: StrokeStyle(lineWidth: 2.5, lineCap: .round))
            }
            AllowanceBead(size: 28, glow: zone.glow)
                .position(Self.point(spent, Self.radius))
        }
        .frame(width: 320, height: 300)
        .accessibilityHidden(true)
    }

    /// `#agdlx1` / `#agddx1`, with its lilac drop shadow.
    private var disc: some View {
        let stops: [UInt32] = scheme == .dark ? [0x2A3170, 0x1E2558, 0x1A2050] : [0xFFFFFF, 0xFAF6FC, 0xF1EAF6]
        return Circle()
            .fill(RadialGradient(stops: [.init(color: Color(hex: stops[0]), location: 0),
                                         .init(color: Color(hex: stops[1]), location: 0.7),
                                         .init(color: Color(hex: stops[2]), location: 1)],
                                 center: UnitPoint(x: 0.38, y: 0.30), startRadius: 0, endRadius: 176))
            .shadow(color: Color(hex: 0xC9A8FF).opacity(0.28), radius: 10, y: 8)
            .frame(width: 220, height: 220)
            .position(Self.centre)
    }

    /// A point `share` of the way along the arc, `r` from the centre.
    static func point(_ share: Double, _ r: CGFloat) -> CGPoint {
        let clock = (235 + 250 * share) * .pi / 180
        return CGPoint(x: centre.x + r * CGFloat(sin(clock)), y: centre.y - r * CGFloat(cos(clock)))
    }

    static func unit(_ p: CGPoint) -> UnitPoint { UnitPoint(x: p.x / 320, y: p.y / 300) }
}

/// Part of the gauge's arc, as shares of it.
private struct GaugeArc: Shape {
    let from: Double
    let to: Double

    func path(in rect: CGRect) -> Path {
        // Clock angles (0° at 12, clockwise) to SwiftUI's (0° at 3).
        var p = Path()
        p.addArc(center: GaugeDial.centre, radius: GaugeDial.radius,
                 startAngle: .degrees(235 + 250 * from - 90), endAngle: .degrees(235 + 250 * to - 90),
                 clockwise: false)
        return p
    }
}

/// `.ag-c`: LEFT TO SPEND, the amount in Fraunces 48, the chip.
private struct GaugeCentre: View {
    let allowance: Allowance
    let zone: AllowanceZone

    var body: some View {
        let over = allowance.state == "over"
        VStack(spacing: 0) {
            Text((over ? "Over your Allowance" : "Left to spend").uppercased())
                .font(.custom("Figtree-Medium", size: 12, relativeTo: .caption)).tracking(1.2)
                .foregroundColor(Pearl.muted)
            Text(allowance.hasGauge ? allowance.leftText : "—")
                .font(.custom("Fraunces-SemiBold", size: 48, relativeTo: .largeTitle)).tracking(-0.5)
                .foregroundColor(over ? AllowanceZone.overInk : Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
                .frame(maxWidth: 190)
                .padding(.top, 2).padding(.bottom, 8)
            if allowance.hasGauge { AllowanceChip(zone: zone) }
        }
    }
}

/// `.ag-stats`: two columns of 120 or more, 22 apart, a hairline between.
private struct GaugeStats: View {
    let allowance: Allowance
    let zone: AllowanceZone

    var body: some View {
        let over = allowance.state == "over"
        HStack(alignment: .center, spacing: 22) {
            stat(Format.whole(allowance.spent ?? 0), "Spent so far")
            Rectangle().fill(APlus.separator).frame(width: 1, height: 44).accessibilityHidden(true)
            if over {
                stat(Format.whole(allowance.total ?? 0), "Your Allowance")
            } else {
                stat(allowance.perDayText ?? "—", allowance.forDaysText ?? "")
            }
        }
        .accessibilityElement(children: .combine)
    }

    private func stat(_ value: String, _ label: String) -> some View {
        VStack(spacing: 0) {
            Text(value).font(.custom("Figtree-SemiBold", size: 22, relativeTo: .title2)).monospacedDigit()
                .foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.7)
            Text(label.uppercased()).font(.custom("Figtree-Medium", size: 12, relativeTo: .caption))
                .tracking(0.8).foregroundColor(Pearl.muted).lineLimit(1)
        }
        .frame(minWidth: 120)
    }
}

// MARK: - Cash flow's meter

/// T-01r (`.cfm`): the gauge in a line, 10 high. The zones at 80 / 20 / 15
/// with 3 between, the fill to what's spent ending on an 18 pt bead, the
/// today tick (2 × 20, ink at 45%).
struct AllowanceMeter: View {
    let allowance: Allowance

    var body: some View {
        let zone = AllowanceZone(allowance)
        GeometryReader { g in
            let w = g.size.width
            let fill = w * allowance.spentShare
            // Everything is 10 high and centred on the bar; the tick (20)
            // overhangs 5 above and below, under the fill, and the bead (18)
            // 4 either side.
            ZStack(alignment: .leading) {
                HStack(spacing: 3) {
                    ForEach(0..<3, id: \.self) { i in
                        RoundedRectangle(cornerRadius: 5, style: .continuous).fill(AllowanceZone.zones[i])
                            .frame(width: max((w - 6) * [80, 20, 15][i] / 115, 0), height: 10)
                    }
                }
                if let today = allowance.todayShare {
                    RoundedRectangle(cornerRadius: 1).fill(Pearl.ink.opacity(0.45))
                        .frame(width: 2, height: 20)
                        .offset(x: w * today - 1)
                }
                if fill > 0.5 {
                    RoundedRectangle(cornerRadius: 5, style: .continuous)
                        .fill(LinearGradient(colors: zone.fill, startPoint: .leading, endPoint: .trailing))
                        .frame(width: fill, height: 10)
                }
                AllowanceBead(size: 18, glow: zone.glow, edge: 1.5, meter: true)
                    .offset(x: min(max(fill - 9, -4), w - 14))
            }
            .frame(width: w, height: 10)
        }
        .frame(height: 10)
        .accessibilityHidden(true)
    }
}

/// T-01r's card top for this month (AP-CashFlow, n-cf-meter): "November ⌄
/// … Allowance $2,113", Left $829 in Fraunces 44, the meter, then "Spent
/// $1,284 of $2,113" with the chip. Past months keep MonthSummary.
struct AllowanceMonthSummary: View {
    let month: String
    let monthSpoken: String
    let canPick: Bool
    let allowance: Allowance
    let pickMonth: () -> Void

    var body: some View {
        let zone = AllowanceZone(allowance)
        let over = allowance.state == "over"
        VStack(alignment: .leading, spacing: 0) {
            HStack(alignment: .center) {
                Button(action: pickMonth) {
                    HStack(spacing: 6) {
                        Text(month).font(Nacre.headline)
                        MonthChevron()
                            .stroke(Pearl.ink, style: StrokeStyle(lineWidth: 2 * 11 / 12, lineCap: .round, lineJoin: .round))
                            .frame(width: 11, height: 8)
                            .accessibilityHidden(true)
                    }
                    .foregroundColor(Pearl.ink)
                    .frame(minHeight: 44).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!canPick)
                .accessibilityLabel("Month, \(monthSpoken)")
                Spacer(minLength: 8)
                Text("Allowance \(Format.whole(allowance.total ?? 0))")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            VStack(alignment: .leading, spacing: 0) {
                Text(over ? "Over" : "Left").font(Nacre.footnote).foregroundColor(Pearl.muted)
                Text(allowance.leftText)
                    .font(.cfBig).tracking(-0.88)
                    .foregroundColor(over ? AllowanceZone.overInk : Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
            }
            .padding(.top, 2)
            .accessibilityElement(children: .combine)
            AllowanceMeter(allowance: allowance).padding(.top, 14).padding(.bottom, 12)
            HStack {
                (Text("Spent ") + Text(Format.whole(allowance.spent ?? 0)).foregroundColor(Pearl.ink)
                    .font(.custom("Figtree-SemiBold", size: 13, relativeTo: .footnote))
                    + Text(" of \(Format.whole(allowance.total ?? 0))"))
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .lineLimit(1).minimumScaleFactor(0.8)
                Spacer(minLength: 8)
                AllowanceChip(zone: zone)
            }
            .accessibilityElement(children: .ignore)
            .accessibilityLabel("\(Format.whole(allowance.spent ?? 0)) spent of \(Format.whole(allowance.total ?? 0)). \(zone.words).")
        }
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 14)
    }
}

/// "How it adds up" on the month card (T-01r), over "need a look".
struct AddsUpRow: View {
    let open: () -> Void

    var body: some View {
        Button(action: open) {
            HStack(spacing: 12) {
                Text("How it adds up").font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                APChevron()
            }
            .padding(.horizontal, 16)
            .frame(maxWidth: .infinity, minHeight: 52, alignment: .leading)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityIdentifier("cf-adds-up")
    }
}
