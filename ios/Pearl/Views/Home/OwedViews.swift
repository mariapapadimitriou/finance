import SwiftUI

// A+ Owed to you (AP-Owed) and its person page (AP-OwedPerson), REDESIGN-04
// (THL-291, THL-289, THL-181). Reached from Home's "2 people owe you" and
// from a split purchase's "Everyone who owes you" (P16). P17 (TP-P17-Owed,
// TP-P17-OwedMore): one list of who owes her, then You owe, Not settled and
// Paid back this month under Also, each on its own page. A person row opens
// the person page; a purchase there opens that person's options sheet
// (S-40) with "Open Loblaws" under it.

/// A person's option picked away from the purchase (Owed to you), run by
/// the purchase's page once it has loaded.
struct StartChoice {
    let name: String
    let choice: PersonChoice
}

// MARK: - S-14 Owed to you (P17, TP-P17-Owed)

/// P17a–d: one list of everyone who owes her, each with their total,
/// biggest first (ties A–Z). You owe, Not settled and Paid back this month
/// are one row each under Also (P17b), each opening its own page (P17f–h);
/// a row shows only when it has something in it.
@MainActor
struct OwedView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var owed: OwedOverview?
    @State private var error: String?
    @State private var person: String?
    /// P17b: the Also row that was tapped.
    @State private var also: OwedAlso?
    /// P17d motion: the last person just paid, so the pearl arrives.
    @State private var allPaid = false

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                OwedTitle(title: "Owed to you")
                if let owed = owed {
                    let people = OwedView.sorted(owed.owesYou)
                    if people.isEmpty {
                        OwedNobody(arrived: allPaid)
                    } else {
                        OwedHeader(total: owed.total, line: OwedView.headline(people))
                        OwedList(people: people, openPerson: { person = $0 })
                    }
                    OwedAlsoRows(owed: owed, open: { also = $0 })
                } else if error != nil {
                    // G2-BOwed S-14ux: Couldn't load who owes you, with Try again.
                    OwedLoadFailed { Task { await load() } }.padding(.top, 60)
                } else {
                    // S-14ul: the card's rows as soft placeholders.
                    OwedSkeleton().padding(.top, 24)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .apPushedPage { dismiss() }
        .navigationDestination(isPresented: Binding(get: { person != nil }, set: { if !$0 { person = nil } })) {
            if let name = person { OwedPersonView(name: name) }
        }
        .navigationDestination(isPresented: Binding(get: { also != nil }, set: { if !$0 { also = nil } })) {
            if let also = also { OwedAlsoPage(kind: also) }
        }
        .task { await load() }
        .reloads { await load() }
    }

    /// P17a: biggest amount first, ties A–Z.
    static func sorted(_ rows: [OwedOverview.Row]) -> [OwedOverview.Row] {
        rows.sorted { a, b in
            if abs(a.total - b.total) >= 0.005 { return a.total > b.total }
            return a.name.localizedCaseInsensitiveCompare(b.name) == .orderedAscending
        }
    }

    /// P17a "9 people owe you"; P17c "Sam owes you".
    static func headline(_ people: [OwedOverview.Row]) -> String {
        if people.count == 1, let one = people.first { return "\(one.name) owes you" }
        return "\(people.count) people owe you"
    }

    private func load() async {
        do {
            try await app.screens.load("api/owed", as: OwedOverview.self) { new in
                apply(new)
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// P17c motion: someone paid in full, so their row springs out and the
    /// total ticks down (light haptic); P17d: the last one brings the pearl.
    private func apply(_ new: OwedOverview) {
        guard let old = owed else { owed = new; return }
        let before = Set(old.owesYou.map(\.name)), after = Set(new.owesYou.map(\.name))
        let gone = !before.subtracting(after).isEmpty
        if gone {
            allPaid = after.isEmpty
            if allPaid {
                UINotificationFeedbackGenerator().notificationOccurred(.success)
            } else {
                UIImpactFeedbackGenerator(style: .light).impactOccurred()
            }
        }
        withAnimation(reduceMotion ? .easeInOut(duration: 0.15) : .spring(response: 0.3, dampingFraction: 0.85)) {
            owed = new
        }
    }
}

extension View {
    /// A pushed A+ page: Back is the 44 pt glass circle, the bar see-through,
    /// the title drawn by the page itself in Fraunces 34.
    func apPushedPage(back: @escaping () -> Void) -> some View {
        navigationBarBackButtonHidden(true)
            .toolbar {
                // PX-AddsUp (2026-11-26 audit): the board's own 44 pt white
                // circle, without iOS 26's glass capsule around it.
                if #available(iOS 26, *) {
                    ToolbarItem(placement: .navigationBarLeading) { APBackButton(action: back) }
                        .sharedBackgroundVisibility(.hidden)
                } else {
                    ToolbarItem(placement: .navigationBarLeading) { APBackButton(action: back) }
                }
            }
            .toolbarBackground(.hidden, for: .navigationBar)
            .navigationBarTitleDisplayMode(.inline)
    }
}

/// `.ptitle`: Fraunces 34 regular, 4 in.
struct OwedTitle: View {
    let title: String

    var body: some View {
        Text(title).font(Nacre.largeTitle).foregroundColor(Pearl.ink)
            .padding(.leading, 4).padding(.top, 6)
            .accessibilityAddTraits(.isHeader)
    }
}

/// S-14ul: three placeholder rows on the card while it loads.
private struct OwedSkeleton: View {
    var body: some View {
        APCard {
            ForEach(0..<3, id: \.self) { i in
                if i > 0 { APSeparator() }
                HStack(spacing: 12) {
                    Circle().fill(APlus.trackSoft).frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 6) {
                        Capsule().fill(APlus.trackSoft).frame(width: 140, height: 10)
                        Capsule().fill(APlus.trackSoft).frame(width: 90, height: 8)
                    }
                    Spacer()
                }
                .padding(.horizontal, 16).frame(minHeight: 64)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
    }
}

/// S-14ux: the warning, "Couldn’t load who owes you", one line, Try again.
private struct OwedLoadFailed: View {
    let retry: () -> Void

    var body: some View {
        VStack(spacing: 6) {
            APIcon.warn("exclamationmark.triangle")
            Text("Couldn’t load who owes you").font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center).padding(.top, 10)
            Text("Check your connection and try again.").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
            Button("Try again", action: retry)
                .buttonStyle(APSecondaryButtonStyle())
                .padding(.top, 14)
                .accessibilityIdentifier("owed-retry")
        }
        .frame(maxWidth: .infinity)
    }
}

/// `.owhero`: "$362.02" in Fraunces 44/600 over "9 people owe you" (P17a),
/// or any page's figure and line (P17g "to 1 person", P17h "this month").
private struct OwedHeader: View {
    let total: Double
    let line: String
    var sign = ""
    var tone: Color = Pearl.ink
    /// P17a motion: the total counts up from $0 on open.
    var countUp = true
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown: Double?

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            Text("")
                .modifier(OwedCount(value: shown ?? total, sign: sign))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)
                .foregroundColor(tone).pearlAmountFit()
            Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
        }
        .padding(.leading, 4).padding(.top, 14)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(sign)\(Format.amount(total)), \(line)")
        .onAppear {
            // Reduce Motion: no count.
            guard shown == nil else { return }
            guard countUp, !reduceMotion else { shown = total; return }
            shown = 0
            withAnimation(.easeOut(duration: 0.35)) { shown = total }
        }
        .onChange(of: total) { t in
            // P17c: the total ticks down when someone pays.
            withAnimation(reduceMotion ? nil : .easeOut(duration: 0.3)) { shown = t }
        }
    }
}

/// The hero's figure as it animates: "$0.00" → "$362.02".
private struct OwedCount: AnimatableModifier {
    var value: Double
    let sign: String

    var animatableData: Double {
        get { value }
        set { value = newValue }
    }

    func body(content: Content) -> some View {
        Text(sign + Format.amount((value * 100).rounded() / 100)).monospacedDigit()
    }
}

/// P17a: OWES YOU, then one card with a row per person. The rows settle in
/// on open, 30 ms apart; one springs out when they pay in full.
private struct OwedList: View {
    let people: [OwedOverview.Row]
    let openPerson: (String) -> Void
    @Environment(\.accessibilityReduceMotion) private var reduceMotion

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            APSectionLabel(text: "Owes you").padding(.top, 24).padding(.bottom, 8)
            APCard {
                ForEach(Array(people.enumerated()), id: \.element.id) { i, r in
                    VStack(spacing: 0) {
                        if i > 0 { APSeparator() }
                        Button { openPerson(r.name) } label: {
                            OwedRow(name: r.name, line: OwedList.line(r), amount: Format.amount(r.total))
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Opens what \(r.name) owes you for")
                    }
                    .modifier(OwedSettleIn(index: i))
                    .transition(reduceMotion ? .opacity
                                : .asymmetric(insertion: .opacity, removal: .scale(scale: 0.9).combined(with: .opacity)))
                }
            }
        }
    }

    /// "Corner Bistro · Nov 8", or "3 purchases".
    static func line(_ r: OwedOverview.Row) -> String {
        if r.items.count == 1, let i = r.items.first {
            return [i.merchant, Format.short(i.date)].compactMap { $0 }.joined(separator: " · ")
        }
        return "\(r.items.count) purchases"
    }
}

/// P17a motion: a row rises 8 pt and fades in (200 ms), 30 ms after the one
/// above it. Reduce Motion: a 150 ms fade.
private struct OwedSettleIn: ViewModifier {
    let index: Int
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false

    func body(content: Content) -> some View {
        content
            .opacity(shown ? 1 : 0)
            .offset(y: shown || reduceMotion ? 0 : 8)
            .onAppear {
                guard !shown else { return }
                if reduceMotion {
                    withAnimation(.easeInOut(duration: 0.15)) { shown = true }
                } else {
                    withAnimation(.easeOut(duration: 0.2).delay(Double(min(index, 12)) * 0.03)) { shown = true }
                }
            }
    }
}

/// P17d: nobody owes her: the pearl and one calm line. When the last person
/// has just paid, the pearl fades in with a soft shimmer (400 ms); Reduce
/// Motion: a fade only.
private struct OwedNobody: View {
    let arrived: Bool
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    @State private var shown = false
    @State private var sweep = false

    var body: some View {
        VStack(spacing: 18) {
            PearlOrb(size: 96)
                .overlay(
                    LinearGradient(colors: [.clear, .white.opacity(0.55), .clear],
                                   startPoint: .leading, endPoint: .trailing)
                        .frame(width: 40)
                        .offset(x: sweep ? 70 : -70)
                        .opacity(arrived && !reduceMotion ? 0.9 : 0)
                        .mask(Circle())
                        .allowsHitTesting(false))
                .scaleEffect(shown || reduceMotion || !arrived ? 1 : 0.92)
            Text("Nobody owes you anything.")
                .font(Nacre.body).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
        }
        .opacity(shown || !arrived ? 1 : 0)
        .frame(maxWidth: .infinity)
        .padding(.horizontal, 20).padding(.top, 96)
        .onAppear {
            guard arrived, !shown else { shown = true; return }
            withAnimation(.easeOut(duration: reduceMotion ? 0.15 : 0.4)) { shown = true }
            if !reduceMotion {
                withAnimation(.easeInOut(duration: 0.4)) { sweep = true }
            }
        }
    }
}

// MARK: - Also (P17b) and its pages (P17f–h)

/// P17b: the three Also rows, and the page each opens.
enum OwedAlso: Hashable {
    case youOwe, notSettled, paidBack
}

/// P17b: ALSO, one row each for You owe (its amount), Not settled ("1
/// split") and Paid back this month (+$70.00 in green). A row shows only
/// when it has something; with none, Also goes.
private struct OwedAlsoRows: View {
    let owed: OwedOverview
    let open: (OwedAlso) -> Void

    var body: some View {
        let rows = OwedAlsoRows.rows(owed)
        if !rows.isEmpty {
            VStack(alignment: .leading, spacing: 0) {
                APSectionLabel(text: "Also").padding(.top, 24).padding(.bottom, 8)
                APCard {
                    ForEach(Array(rows.enumerated()), id: \.element.kind) { i, r in
                        if i > 0 { APSeparator(afterFace: false) }
                        Button { open(r.kind) } label: { OwedAlsoRow(row: r) }
                            .buttonStyle(.plain)
                            .accessibilityIdentifier("owed-also-\(r.kind)")
                    }
                }
            }
        }
    }

    struct Row {
        let kind: OwedAlso
        let title: String
        let value: String
    }

    /// Only the rows with something in them, in the board's order.
    static func rows(_ owed: OwedOverview) -> [Row] {
        var out: [Row] = []
        let owe = owed.youOwe.reduce(0) { $0 + $1.total }
        if !owed.youOwe.isEmpty {
            out.append(Row(kind: .youOwe, title: "You owe", value: Format.amount(owe)))
        }
        let n = owed.notSettled?.count ?? 0
        if n > 0 {
            out.append(Row(kind: .notSettled, title: "Not settled", value: n == 1 ? "1 split" : "\(n) splits"))
        }
        if !owed.paidBack.isEmpty {
            let back = owed.paidBack.reduce(0) { $0 + $1.amount }
            out.append(Row(kind: .paidBack, title: "Paid back this month", value: "+" + Format.amount(back)))
        }
        return out
    }
}

/// `.also .row`: the icon, the words, the figure, the chevron (56 high).
private struct OwedAlsoRow: View {
    let row: OwedAlsoRows.Row
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        HStack(spacing: 12) {
            icon
            if typeSize.isAccessibilitySize {
                // P17e's Person row rule: at the larger text sizes the figure
                // moves under the words, so neither breaks mid-word.
                VStack(alignment: .leading, spacing: 2) {
                    title
                    value
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            } else {
                title.frame(maxWidth: .infinity, alignment: .leading)
                value
            }
            CFChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .frame(minHeight: 56)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(row.title), \(row.value)")
        .accessibilityAddTraits(.isButton)
    }

    private var title: some View {
        Text(row.title).font(Nacre.body).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
    }

    private var value: some View {
        Text(row.value)
            .font(row.kind == .notSettled ? Nacre.body : Nacre.headline).monospacedDigit()
            .foregroundColor(row.kind == .notSettled ? Pearl.muted : row.kind == .paidBack ? Pearl.moneyIn : Pearl.ink)
            .lineLimit(1).fixedSize()
    }

    @ViewBuilder private var icon: some View {
        switch row.kind {
        case .youOwe: APIcon(symbol: "arrow.up")
        case .notSettled: APIcon(symbol: "clock")
        case .paidBack: APIcon.good("checkmark")
        }
    }
}

/// P17f–h: each Also row's own page. It loads Owed to you itself, so it
/// stays right after a change made from it.
@MainActor
private struct OwedAlsoPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let kind: OwedAlso
    @State private var owed: OwedOverview?
    @State private var failed = false
    /// S-14o2 (REFRESH-18): the You owe row that was tapped.
    @State private var oweBack: OwedOverview.Row?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                OwedTitle(title: title)
                if let owed = owed {
                    content(owed)
                } else if failed {
                    OwedLoadFailed { Task { await load() } }.padding(.top, 60)
                } else {
                    OwedSkeleton().padding(.top, 24)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .apPushedPage { dismiss() }
        .modifier(OweBackOptions(row: $oweBack))
        .task { await load() }
        .reloads { await load() }
    }

    private var title: String {
        switch kind {
        case .youOwe: return "You owe"
        case .notSettled: return "Not settled"
        case .paidBack: return "Paid back"
        }
    }

    @ViewBuilder private func content(_ owed: OwedOverview) -> some View {
        switch kind {
        case .youOwe:
            // P17g: what she got back over a share; a row opens that
            // person's options on the purchase (S-14o).
            if owed.youOwe.isEmpty {
                CalmState()
            } else {
                let n = owed.youOwe.count
                OwedHeader(total: owed.youOwe.reduce(0) { $0 + $1.total },
                           line: n == 1 ? "to 1 person" : "to \(n) people", countUp: false)
                APCard {
                    ForEach(Array(owed.youOwe.enumerated()), id: \.element.id) { i, r in
                        if i > 0 { APSeparator() }
                        Button { oweBack = r } label: {
                            OwedRow(name: r.name, line: "Overpaid for " + (r.items.first?.merchant ?? "a purchase"),
                                    amount: Format.amount(r.total))
                        }
                        .buttonStyle(.plain)
                        .disabled(r.items.first?.chargeId == nil)
                    }
                }
                .padding(.top, 24)
            }
        case .notSettled:
            // P17f: its one explaining line, then the splits; a row opens
            // the purchase, where Settle up lives.
            Text("Not in the total until settled.")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4).padding(.top, 10)
                .fixedSize(horizontal: false, vertical: true)
            if let unsettled = owed.notSettled, !unsettled.isEmpty {
                APCard {
                    ForEach(Array(unsettled.enumerated()), id: \.element.id) { i, n in
                        if i > 0 { APSeparator() }
                        NavigationLink {
                            TransactionByID(id: n.chargeId, categories: app.categories)
                        } label: { UnsettledRow(n: n) }
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 16)
            } else {
                CalmState()
            }
        case .paidBack:
            // P17h: the record, in green; rows are not buttons.
            if owed.paidBack.isEmpty {
                CalmState()
            } else {
                OwedHeader(total: owed.paidBack.reduce(0) { $0 + $1.amount }, line: "this month",
                           sign: "+", tone: Pearl.moneyIn, countUp: false)
                APCard {
                    ForEach(Array(owed.paidBack.enumerated()), id: \.offset) { i, b in
                        if i > 0 { APSeparator() }
                        PaidBackRow(b: b)
                    }
                }
                .padding(.top, 24)
            }
        }
    }

    private func load() async {
        do {
            try await app.screens.load("api/owed", as: OwedOverview.self) { owed = $0 }
            failed = false
        } catch {
            _ = app.handle(error)
            failed = owed == nil
        }
    }
}

/// A+ `.row`: face 40, name over line, the amount on the right edge. P17e:
/// a long name takes one line and ends in "…"; the amount never shrinks or
/// wraps, and at the larger text sizes it moves under the name.
struct OwedRow: View {
    let name: String
    let line: String
    let amount: String
    var tone: Color = Pearl.ink
    var note: String? = nil
    @Environment(\.dynamicTypeSize) private var typeSize

    var body: some View {
        HStack(spacing: 12) {
            APFace(name: name)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                    .lineLimit(1).truncationMode(.tail)
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if let note = note {
                    Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                if typeSize.isAccessibilitySize { figure.padding(.top, 2) }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if !typeSize.isAccessibilitySize { figure }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        // VoiceOver reads the whole name, however it's cut.
        .accessibilityElement(children: .combine)
    }

    private var figure: some View {
        Text(amount).font(Nacre.headline).monospacedDigit().foregroundColor(tone)
            .lineLimit(1).fixedSize()
            .layoutPriority(1)
    }
}

/// S-14u: "Corner Bistro" over "You and 3 · $40.00 paid", the Not settled pill.
private struct UnsettledRow: View {
    let n: OwedOverview.NotSettled

    var body: some View {
        HStack(spacing: 12) {
            APFace(name: n.merchant)
            VStack(alignment: .leading, spacing: 2) {
                Text(n.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(n.me ?? true ? "You and \(n.people.count) · \(Format.amount(n.paid)) paid"
                     : "\(n.people.joined(separator: ", ")) · \(Format.amount(n.paid)) paid")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text("Not settled").font(Nacre.footnote).foregroundColor(Pearl.ink)
                .padding(.horizontal, 10).frame(minHeight: 26)
                .background(Capsule().fill(Pearl.bubble))
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(n.merchant), \(Format.monthDay(n.date)), \(Format.andList(n.people)), \(Format.amount(n.paid)) paid so far, not settled")
        .accessibilityAddTraits(.isButton)
    }
}

/// P17h: "Jo" over "Corner Bistro · Nov 12", +$22.66 in green.
private struct PaidBackRow: View {
    let b: OwedOverview.Back

    var body: some View {
        // SPLIT-14: "PayPal" or "Another app"; SPLIT-15: one cash payment,
        // with what a deposit holds; SPLIT-19 (S-11c): several purchases.
        let how = b.cash == true ? "Cash" : b.app == true ? (b.appName ?? "Another app") : nil
        // P17h: "Flight to Athens · Nov 9", or "Cash · Nov 13".
        let line = (b.paidBack.map { [how, Format.short(b.date), "paid back \(Format.andList($0))"] }
                    ?? [how ?? b.merchant, Format.short(b.date)])
            .compactMap { $0 }.filter { !$0.isEmpty }.joined(separator: " · ")
        return OwedRow(name: b.name ?? "Someone", line: line, amount: "+" + Format.amount(b.amount),
                       tone: Pearl.moneyIn,
                       note: b.deposited.map { d in
                           "\(Format.amount(d)) deposited" + (b.depositedOn.map { " \(Format.short($0))" } ?? "")
                               + " · \(Format.amount(b.still ?? 0)) still cash" })
    }
}

// MARK: - The person page (AP-OwedPerson, new)

/// What one person owes her for: their face, name and total, then OWES YOU
/// FOR with each purchase. A purchase opens S-40 for that person on that
/// purchase, plus "Open Loblaws"; a choice there runs on the purchase's page.
@MainActor
struct OwedPersonView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let name: String

    @State private var row: OwedOverview.Row?
    @State private var loaded = false
    /// The purchase whose options are open, and its split.
    @State private var options: Options?
    /// What runs once the sheet has gone (S-40's rule: the next sheet can open).
    @State private var after: (() -> Void)?
    @State private var open: Open?
    @State private var busy: String?
    @State private var problem: String?

    /// A class, so the 900-byte purchase isn't copied into every closure
    /// frame (check_stack).
    final class Options: Identifiable {
        let t: Transaction
        let split: Transaction.Splitting
        let p: Transaction.Splitting.Person
        var id: String { t.id }

        init(t: Transaction, split: Transaction.Splitting, p: Transaction.Splitting.Person) {
            self.t = t
            self.split = split
            self.p = p
        }
    }

    struct Open {
        let id: String
        var choice: StartChoice? = nil
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                if let row = row {
                    OwedPersonHero(row: row)
                    APSectionLabel(text: "Owes you for").padding(.top, 24).padding(.bottom, 8)
                    APCard {
                        ForEach(Array(row.items.enumerated()), id: \.offset) { i, item in
                            if i > 0 { APSeparator() }
                            Button { Task { await openOptions(item) } } label: {
                                OwedRow(name: item.merchant ?? "A purchase", line: OwedPersonView.line(item),
                                        amount: Format.amount(item.owes ?? item.amount ?? 0))
                                    .opacity(busy == item.chargeId ? 0.5 : 1)
                            }
                            .buttonStyle(.plain)
                            .disabled(item.chargeId == nil)
                        }
                    }
                    if let problem = problem {
                        Text(problem).font(Nacre.footnote).foregroundColor(Pearl.danger)
                            .padding(.horizontal, 4).padding(.top, 8)
                    }
                } else if loaded {
                    // Paid up since: nothing left to show.
                    CalmState(line: "\(name) doesn’t owe you anything now.")
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .apPushedPage { dismiss() }
        .sheet(item: $options, onDismiss: {
            let next = after
            after = nil
            next?()
        }) { o in
            OwedOptionsSheet(o: o, close: { options = nil }) { next in
                after = { open = next }
                options = nil
            }
        }
        .navigationDestination(isPresented: Binding(get: { open != nil }, set: { if !$0 { open = nil } })) {
            if let o = open { OwedOpenPurchase(open: o) }
        }
        .task { await load() }
        .reloads { await load() }
    }

    /// "Nov 11 · paid $10.00 of $30.00", or the date alone.
    static func line(_ i: OwedOverview.Row.Item) -> String {
        let paid = (i.amount ?? 0) - (i.owes ?? 0)
        if let share = i.amount, paid >= 0.005 {
            return "\(Format.short(i.date)) · paid \(Format.amount(paid)) of \(Format.amount(share))"
        }
        return Format.short(i.date)
    }

    private func load() async {
        try? await app.screens.load("api/owed", as: OwedOverview.self) { owed in
            row = owed.owesYou.first { $0.name == name }
        }
        loaded = true
    }

    /// Loads the purchase, finds this person on its split, opens S-40.
    private func openOptions(_ item: OwedOverview.Row.Item) async {
        guard let id = item.chargeId, busy == nil else { return }
        busy = id
        defer { busy = nil }
        do {
            let t: Transaction = try await app.api.get("api/transactions/\(id)")
            if let split = t.splitting, let p = split.people.first(where: { $0.name == name }) {
                problem = nil
                options = Options(t: t, split: split, p: p)
            } else {
                open = Open(id: id)
            }
        } catch {
            problem = app.handle(error)
        }
    }
}

/// The purchase, opened from Owed to you (its own view: check_stack).
private struct OwedOpenPurchase: View {
    @EnvironmentObject private var app: AppModel
    let open: OwedPersonView.Open

    var body: some View {
        TransactionByID(id: open.id, categories: app.categories, startChoice: open.choice)
    }
}

/// S-40 for one person on one purchase, from Owed to you: a choice opens
/// the purchase and runs there; "Open Loblaws" just opens it.
private struct OwedOptionsSheet: View {
    let o: OwedPersonView.Options
    let close: () -> Void
    let go: (OwedPersonView.Open) -> Void

    var body: some View {
        PersonOptionsSheet(t: o.t, split: o.split, p: o.p, onClose: close, onChoose: { choice in
            go(OwedPersonView.Open(id: o.t.id, choice: StartChoice(name: o.p.name, choice: choice)))
        }, onOpen: {
            go(OwedPersonView.Open(id: o.t.id))
        })
    }
}

/// S-14o2 (REFRESH-18): a You owe row's person on the purchase they overpaid,
/// with Open Corner Bistro under their options.
private struct OweBackOptions: ViewModifier {
    @EnvironmentObject private var app: AppModel
    @Binding var row: OwedOverview.Row?
    @State private var options: OwedPersonView.Options?
    @State private var after: (() -> Void)?
    @State private var open: OwedPersonView.Open?

    func body(content: Content) -> some View {
        content
            .onChange(of: row) { r in if let r = r { row = nil; Task { await load(r) } } }
            .sheet(item: $options, onDismiss: {
                let next = after
                after = nil
                next?()
            }) { o in
                OwedOptionsSheet(o: o, close: { options = nil }) { next in
                    after = { open = next }
                    options = nil
                }
            }
            .navigationDestination(isPresented: Binding(get: { open != nil }, set: { if !$0 { open = nil } })) {
                if let o = open { OwedOpenPurchase(open: o) }
            }
    }

    private func load(_ r: OwedOverview.Row) async {
        guard let id = r.items.first?.chargeId else { return }
        guard let t: Transaction = try? await app.api.get("api/transactions/\(id)") else { return }
        if let split = t.splitting, let p = split.people.first(where: { $0.name == r.name }) {
            options = OwedPersonView.Options(t: t, split: split, p: p)
        } else {
            open = OwedPersonView.Open(id: id)
        }
    }
}

/// Face 56, the name in Fraunces 22, the amount 44/600, "owes you for 2 purchases".
private struct OwedPersonHero: View {
    let row: OwedOverview.Row

    var body: some View {
        VStack(spacing: 0) {
            APFace(name: row.name, size: 56)
            Text(row.name).font(Nacre.title2).foregroundColor(Pearl.ink).padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            Text(Format.amount(row.total))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)
                .foregroundColor(Pearl.ink).pearlAmountFit()
            Text("owes you for \(row.items.count == 1 ? "1 purchase" : "\(row.items.count) purchases")")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 8)
        .accessibilityElement(children: .combine)
    }
}
