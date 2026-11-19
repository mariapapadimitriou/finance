import SwiftUI

// Trips (product owner, 2026-11-15; Figma Cash flow › Trips 1327:4973, note
// 1329:69536 · THL-122, THL-123, THL-226, THL-263; server finance/trips.py).
// A trip is its own thing (a name, its rows, their dates, a total, a page)
// and adds a tag of the same name. It never moves money between months:
// each row still counts in its own. Pearl converts nothing, so a trip across
// currencies is totalled per currency (TR-02m).
//
// TR-01  Quick sort's trip card (QuickSortView)
// TR-02  The trip's page · TR-02m in two currencies (TripPage)
// TR-04  Trip options, ••• on the page (TripOptionsSheet)
// TR-05  Cash flow rows "Shopping · Trip to Montréal" (TransactionRow)
// TR-06  The transaction page's line and trip row (TransactionDetailView)
// TR-07  Select › Make a trip (TransactionsView)
// TR-08  Name the trip, for Make a trip and Rename (NameTripSheet)
// TR-09  Tags: removing a trip's tag ends the trip (CategoriesRulesView)
// TR-02c The toasts after Make a trip and Rename
// TR-03  The trip by category: By category on the trip's page (TripCategoryCard)
// TR-11  Add transactions · TR-12 Remove some… (TransactionsView with a TripPick)
// TR-13  Not a trip? (NotATripSheet)
// TR-14  Tap TR-01's card: its rows, AI-09's plain list (QuickSortView)
// TR-17  The Calendar's Trips card (TripsCard; its rows are TripListRow)
// TR-17e The Trips card with no trips yet (TripsCard)
// TR-18  Trips, by year (AllTripsPage)
//
// A+ (REDESIGN-14): the Claude Design boards G7-Trip and G7-TripCal.

/// GET /api/trips/<id>: the trip, and its rows newest first, each with its
/// billing currency (TR-02m).
struct TripDetail: Decodable {
    let trip: Trip
    let rows: [Transaction]
    /// Row id → its currency ("CAD").
    let currencies: [String: String]

    private enum Keys: String, CodingKey { case trip, rows }
    private struct RowCurrency: Decodable {
        let id: String
        let currency: String?
    }

    init(from decoder: Decoder) throws {
        let c = try decoder.container(keyedBy: Keys.self)
        trip = try c.decode(Trip.self, forKey: .trip)
        rows = (try? c.decodeIfPresent([Lenient<Transaction>].self, forKey: .rows))?.compactMap { $0.value } ?? []
        let cur = (try? c.decodeIfPresent([Lenient<RowCurrency>].self, forKey: .rows))?.compactMap { $0.value } ?? []
        currencies = Dictionary(cur.compactMap { r in r.currency.map { (r.id, $0) } }, uniquingKeysWith: { a, _ in a })
    }
}

// MARK: - TR-02 / TR-02m / TR-03 (A+ G7-Trip)

/// TR-02 (A+ G7-Trip 1): the glass Back and ••• over the hero (the place's
/// face in the nacre ring, "Trip to Montréal" in Fraunces, the total, "Mar
/// 4–9 · 23 transactions · counts in March"), then Transactions · By
/// category, and the trip's rows under IN THE TRIP (each opens its page).
/// TR-03 (G7-Trip 2) is the By category side of the same page: each
/// category's count and total, opening the trip's page for that category
/// (TR-16, "{Category} · {trip name}", its rows and total only).
/// In two currencies (TR-02m) the total is "$1,240 CAD + $310 USD", smaller,
/// and a row in the other currency says its code. The toasts (made,
/// renamed, added, removed, not a trip) are the app's own (`AppModel.say`),
/// since the page may open or close under them.
@MainActor
struct TripPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let id: String
    /// TR-16: the trip's page for one category. The trip's options and By
    /// category act on the whole trip, so they stay on the trip's own page.
    var category: String? = nil
    @State private var detail: TripDetail?
    @State private var error: String?
    @State private var options = false
    /// Transactions or By category (G7-Trip 1 and 2).
    @State private var byCategory = false
    /// What was picked on TR-04: it opens once that sheet has gone, since a
    /// sheet raised while one is closing doesn't appear.
    @State private var next: Next?
    @State private var showRename = false
    @State private var newName = ""
    /// TR-11 / TR-12: Cash flow's Select, for this trip.
    @State private var picking: TripPick?
    /// TR-13.
    @State private var notATrip = false

    private enum Next { case rename, add, remove, notATrip }

    var body: some View {
        ScrollView {
            if let d = detail {
                TripPageContent(detail: d, category: category, byCategory: $byCategory)
                    .padding(.horizontal, Pearl.gutter).padding(.top, 8).padding(.bottom, 32)
            } else {
                LoadState(error: error) { Task { await load() } }
                    .padding(.top, 40)
            }
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                TripGlassButton(symbol: "chevron.left", label: "Back") { dismiss() }
            }
            ToolbarItem(placement: .navigationBarTrailing) {
                if detail != nil, category == nil {
                    TripGlassButton(symbol: "ellipsis", label: "Trip options") { options = true }
                }
            }
        }
        .task { await load() }
        .reloads { await load() }
        .sheet(isPresented: $options, onDismiss: openNext) {
            if let d = detail {
                TripOptionsSheet(trip: d.trip, onClose: { options = false },
                                 onAdd: { pick(.add) }, onRemove: { pick(.remove) },
                                 onRename: { pick(.rename) }, onNotATrip: { pick(.notATrip) })
            }
        }
        .sheet(isPresented: $showRename) {
            if let d = detail {
                NameTripSheet(count: d.trip.count, dates: Format.span(d.trip.start, d.trip.end),
                              total: d.trip.totals.shown, months: d.trip.months, name: $newName,
                              primary: "Save", onClose: { showRename = false }) { name in
                    let reply: TripReply = try await app.api.put("api/trips/\(id)", ["name": name])
                    showRename = false
                    let was = d.trip.name
                    // TR-02c: "Renamed to {name}" · Undo renames it back (and its tag).
                    if reply.trip?.name ?? name != was {
                        let api = app.api, id = self.id
                        app.say("Renamed to \(reply.trip?.name ?? name)") {
                            let _: OK = try await api.put("api/trips/\(id)", ["name": was])
                        }
                    }
                    app.changed()
                    await load()
                }
            }
        }
        .sheet(isPresented: $notATrip) {
            if let d = detail {
                NotATripSheet(trip: d.trip, onClose: { notATrip = false }) {
                    notATrip = false
                    dismiss()
                }
            }
        }
        .navigationDestination(isPresented: Binding(get: { picking != nil }, set: { if !$0 { picking = nil } })) {
            if let p = picking { TransactionsView(tripPick: p) }
        }
    }

    private func pick(_ which: Next) {
        next = which
        options = false
    }

    /// TR-04 has gone: open what was picked on it.
    private func openNext() {
        defer { next = nil }
        guard let d = detail, let which = next else { return }
        switch which {
        case .rename: newName = d.trip.name; showRename = true
        case .add: picking = TripPick(kind: .add, trip: d.trip, rows: d.rows)
        case .remove: picking = TripPick(kind: .remove, trip: d.trip, rows: d.rows)
        case .notATrip: notATrip = true
        }
    }

    private func load() async {
        do {
            detail = try await app.api.get("api/trips/\(id)")
            error = nil
        } catch {
            if detail != nil, let e = error as? APIError, case .server = e {
                // It wasn't there any more (its tag was removed, or Undo took
                // back Make a trip): back out.
                dismiss()
                return
            }
            self.error = app.handle(error)
        }
    }
}

/// The page under the glass buttons: the hero, the switch, and the rows.
private struct TripPageContent: View {
    @EnvironmentObject private var app: AppModel
    let detail: TripDetail
    let category: String?
    @Binding var byCategory: Bool

    var body: some View {
        let t = detail.trip
        // One category (TR-16): its rows and what it came to; else the whole trip.
        let totals = category.flatMap { c in t.categories?.first { $0.category == c }?.money } ?? t.totals
        let rows = category.map { c in detail.rows.filter { ($0.category ?? "Other") == c } } ?? detail.rows
        VStack(alignment: .leading, spacing: 0) {
            TripHero(place: TripFace.place(t), name: category.map { "\($0) \u{00B7} \(t.name)" } ?? t.name,
                     totals: totals, line: heroLine(t, rows: rows.count, mixed: totals.mixed))
            if category == nil {
                TripSwitch(byCategory: $byCategory).padding(.top, 16)
            }
            if byCategory && category == nil {
                TripCategoryCard(trip: t).padding(.top, 16)
            } else if !rows.isEmpty {
                APSectionLabel(text: "In the trip").padding(.top, 16).padding(.bottom, 8)
                TripRowsCard(detail: detail, rows: rows, mixed: totals.mixed, main: totals.first?.currency)
            }
        }
    }

    /// "Mar 4–9 · 23 transactions · counts in March" (TEXT-01: no "as usual").
    /// By category drops "counts in"; two currencies say so instead.
    private func heroLine(_ t: Trip, rows: Int, mixed: Bool) -> String {
        let n = category == nil ? t.count : rows
        let base = "\(Format.span(t.start, t.end)) \u{00B7} \(n) transaction\(n == 1 ? "" : "s")"
        if mixed { return base + " \u{00B7} in \(t.totals.count) currencies" }
        if byCategory && category == nil { return base }
        return base + " \u{00B7} counts in \(t.months)"
    }
}

/// G7-Trip's hero: the face in the nacre ring (56), the name in Fraunces 22,
/// the total in Fraunces 44 (smaller in two currencies), the line under it.
/// A trip's total is a total: no minus (note 1329:69536, Wording).
private struct TripHero: View {
    let place: String
    let name: String
    let totals: [MoneyTotal]
    let line: String

    var body: some View {
        VStack(spacing: 0) {
            ChatRing(name: place, size: 56, trip: true)
            Text(name).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
                .padding(.top, 8)
                .accessibilityAddTraits(.isHeader)
            Text(totals.shown)
                .font(.custom("Fraunces-SemiBold", size: totals.mixed ? 30 : 44, relativeTo: .largeTitle))
                .tracking(totals.mixed ? 0 : -0.88)
                .foregroundColor(Pearl.moneyOut)
                .lineLimit(1).minimumScaleFactor(0.5)
            Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
                .fixedSize(horizontal: false, vertical: true)
        }
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }
}

/// Transactions · By category: the A+ segmented switch (chip track, 38 high).
private struct TripSwitch: View {
    @Binding var byCategory: Bool

    var body: some View {
        HStack(spacing: 0) {
            side("Transactions", on: !byCategory) { byCategory = false }
            side("By category", on: byCategory) { byCategory = true }
        }
        .padding(3)
        .frame(height: 38)
        .background(Capsule().fill(APlus.chip))
    }

    private func side(_ title: String, on: Bool, _ act: @escaping () -> Void) -> some View {
        Button(action: act) {
            Text(title).font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                .foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, maxHeight: .infinity)
                .background(Group {
                    if on {
                        Capsule().fill(Pearl.card)
                            .shadow(color: Pearl.ink.opacity(0.12), radius: 1.5, y: 1)
                    }
                })
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
    }
}

/// The trip's rows on the A+ card, each opening its page.
private struct TripRowsCard: View {
    @EnvironmentObject private var app: AppModel
    let detail: TripDetail
    let rows: [Transaction]
    let mixed: Bool
    let main: String?

    var body: some View {
        APCard {
            ForEach(Array(rows.enumerated()), id: \.element.id) { i, row in
                if i > 0 { APSeparator() }
                NavigationLink { TransactionByID(id: row.id, categories: app.categories) } label: {
                    TransactionRow(t: row, showsTrip: false,
                                   currency: mixed && detail.currencies[row.id] != main ? detail.currencies[row.id] : nil)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// TR-03 (G7-Trip 2): what the trip spent in each category, its count, and
/// the total (plum, no minus), each opening the trip's page for it (TR-16).
private struct TripCategoryCard: View {
    let trip: Trip

    var body: some View {
        let cats = trip.categories ?? []
        return APCard {
            ForEach(Array(cats.enumerated()), id: \.element.category) { i, c in
                if i > 0 { APSeparator(afterFace: false) }
                NavigationLink { TripPage(id: trip.id, category: c.category) } label: {
                    HStack(spacing: 12) {
                        ChatIcon(symbol: CategorySheet.symbol(for: c.category))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(c.category).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            Text("\(c.count) transaction\(c.count == 1 ? "" : "s")")
                                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        Text(Self.whole(c.money)).font(Nacre.headline).foregroundColor(Pearl.moneyOut)
                            .monospacedDigit().pearlAmountFit()
                        ChatChevron()
                    }
                    .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                    .contentShape(Rectangle())
                    .accessibilityElement(children: .combine)
                }
                .buttonStyle(.plain)
            }
        }
    }

    /// "$560"; in several currencies "$1,240 CAD + $310 USD".
    static func whole(_ parts: [MoneyTotal]) -> String {
        parts.count <= 1 ? Format.whole(parts.first?.amount ?? 0) : parts.shown
    }
}

/// The 44 pt glass circle (kit `glassbtn`): Back and ••• on a trip's page.
struct TripGlassButton: View {
    let symbol: String
    let label: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Image(systemName: symbol).font(.system(size: 17, weight: .semibold))
                .foregroundColor(Pearl.ink)
                .frame(width: 44, height: 44)
                .background(APCardSurface(radius: 22))
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
    }
}

/// A trip's face: its place, or the name after "Trip to" ("MO", "LI").
enum TripFace {
    static func place(_ t: Trip) -> String { place(name: t.name, place: t.place) }

    static func place(name: String, place: String?) -> String {
        if let p = place, !p.isEmpty { return p }
        return name.hasPrefix("Trip to ") ? String(name.dropFirst(8)) : name
    }

    /// Two letters for one word ("MO"), else the initials.
    static func letters(_ place: String) -> String {
        let words = place.split { !$0.isLetter && !$0.isNumber }
        if words.count == 1, let w = words.first { return String(w.prefix(2)).uppercased() }
        return APFace.initials(place)
    }
}

/// PUT / POST /api/trips…: the trip as it is now (none once it has ended).
struct TripReply: Decodable {
    var trip: Trip? = nil
    var ended: Bool? = nil
}

/// TR-11 / TR-12: Cash flow's Select, opened from TR-04 for one trip.
struct TripPick {
    enum Kind { case add, remove }
    let kind: Kind
    let trip: Trip
    /// The trip's rows as its page has them (TR-12 picks among these).
    let rows: [Transaction]

    /// TR-11: the trip's dates ±3 days ("Mar 1–12").
    var window: (start: String, end: String) {
        (Format.shiftDay(trip.start, by: -3), Format.shiftDay(trip.end, by: 3))
    }
}

// MARK: - TR-04 (A+ G7-Trip 3)

/// TR-04: the trip's options from ••• on its page, on a Pearl sheet: the
/// trip's name with ✕; Rename the trip, Add transactions, Remove some…;
/// Leave it as is (approved 2026-11-18: it stays a trip and counts in its
/// month, like any spending; closes the sheet); then It wasn't a trip, red,
/// on its own (TR-13 asks first). Pay from a piggy bank is hidden until Save
/// returns (approved 2026-11-18).
struct TripOptionsSheet: View {
    let trip: Trip
    let onClose: () -> Void
    let onAdd: () -> Void
    let onRemove: () -> Void
    let onRename: () -> Void
    let onNotATrip: () -> Void

    var body: some View {
        PearlSheet {
            APSheetTitle(title: trip.name, close: onClose)
            APCard {
                TripOptionRow(symbol: "pencil", title: "Rename the trip", sub: "Renames its tag too", action: onRename)
                APSeparator(afterFace: false)
                TripOptionRow(symbol: "plus", title: "Add transactions", action: onAdd)
                APSeparator(afterFace: false)
                TripOptionRow(symbol: "xmark", title: "Remove some\u{2026}", action: onRemove)
            }
            APCard {
                TripOptionRow(symbol: "eye", title: "Leave it as is",
                              sub: "It counts in \(trip.months), like any spending", chevron: false, action: onClose)
                    .accessibilityIdentifier("trip-leave-it")
            }
            APCard {
                TripOptionRow(symbol: "scissors", title: "It wasn\u{2019}t a trip", danger: true, chevron: false,
                              action: onNotATrip)
                    .accessibilityIdentifier("trip-not-a-trip")
            }
        }
    }
}

/// An option row on the A+ card (kit `srow`): the round icon, the title over
/// what happens, the chevron. A destructive entry row is red, no chevron.
struct TripOptionRow: View {
    let symbol: String
    let title: String
    var sub: String? = nil
    var danger = false
    var chevron = true
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                ChatIcon(symbol: symbol, danger: danger)
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(danger ? Pearl.danger : Pearl.ink)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if chevron { ChatChevron() }
            }
            .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel([title, sub].compactMap { $0 }.joined(separator: ", "))
        .accessibilityAddTraits(.isButton)
    }
}

// MARK: - TR-13 (A+ G7-Trip 4 and 5)

/// TR-13: It wasn't a trip, asked first on a Pearl sheet: "Not a trip?",
/// "The 23 stay as they are. Only the trip and its tag go.", Not a trip ·
/// Keep it. Couldn't: the red line, and Try again. The trip and its tag go,
/// the rows stay, and Pearl won't ask about those dates again. Its toast's
/// Undo puts the trip back exactly, dates unskipped too
/// (POST /api/trips/<id>/restore).
struct NotATripSheet: View {
    @EnvironmentObject private var app: AppModel
    let trip: Trip
    let onClose: () -> Void
    /// The trip has ended: its page closes.
    let onDone: () -> Void

    @State private var busy = false
    @State private var failed = false

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: "Not a trip?", close: onClose).disabled(busy)
            Text("\(Trip.stayLine(trip.count)). Only the trip and its tag go.")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if failed { ChatErrorLine(text: "Couldn\u{2019}t end the trip. Nothing changed. Try again.").padding(.top, -12) }
        } footer: {
            PearlSheetButtons(primary: failed ? "Try again" : "Not a trip", busy: busy, busyLabel: "Ending\u{2026}",
                              secondary: "Keep it", onPrimary: { Task { await end() } }, onSecondary: onClose)
        }
    }

    private func end() async {
        busy = true
        defer { busy = false }
        do {
            struct Ended: Decodable { let count: Int? }
            let reply: Ended = try await app.api.delete("api/trips/\(trip.id)")
            let n = reply.count ?? trip.count
            let api = app.api, id = trip.id
            app.say("Not a trip \u{00B7} \(n) \(n == 1 ? "stays as it is" : "stay as they are")") {
                let _: TripReply = try await api.post("api/trips/\(id)/restore", [:])
            }
            app.changed()
            onDone()
        } catch {
            failed = true
        }
    }
}

// MARK: - TR-08

/// TR-08 (`1331:6480` / `1331:6551`): Name the trip, after Select › Make a
/// trip ("Make the trip") or Rename the trip ("Save"). The name is
/// prefilled "Trip to {place}" when Pearl knows it. The server's words
/// ("You already have a trip with that name.") show on the sheet.
struct NameTripSheet: View {
    let count: Int
    /// "Mar 3–7".
    let dates: String
    /// "$1,136.90", or "$1,240 CAD + $310 USD".
    let total: String
    /// "March".
    let months: String
    @Binding var name: String
    var primary = "Make the trip"
    let onClose: () -> Void
    /// Makes or renames it with the name she typed.
    let save: (String) async throws -> Void

    var body: some View {
        PearlConfirmSheet(overline: "\(count) transaction\(count == 1 ? "" : "s") · \(dates) · \(total)",
                          title: "Name the trip",
                          message: count == 1 ? "Adds the tag." : "Adds the tag to all \(count).",
                          field: .init(label: "Trip name", identifier: "trip-name"), text: $name,
                          primary: primary, secondary: "Cancel", onClose: onClose) {
            do {
                try await save(name.trimmingCharacters(in: .whitespacesAndNewlines))
            } catch let e as APIError {
                if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
                throw e
            }
        }
    }
}

// MARK: - TR-17 / TR-17e / TR-18 (A+ G7-TripCal)

/// TR-17 (G7-TripCal 1): the Calendar's Trips card under the grid and
/// legend. TRIPS with See all on the right, then up to three trips on the A+
/// card, each its face, name over dates, the total in plum (no minus) and
/// the chevron, opening its page (TR-02). TR-17e (G7-TripCal 2): no trips
/// yet, one line, no See all. Shown once the month has loaded.
///
/// Built here for Cash flow's CalendarView (its engBOT places it):
/// `TripsCard(trips: card.trips)` for `data?.tripCard`.
struct TripsCard: View {
    let trips: [CalendarMonth.TripCard.Row]

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            HStack {
                Text("TRIPS").font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                    .accessibilityLabel("Trips")
                    .accessibilityAddTraits(.isHeader)
                Spacer(minLength: 8)
                if !trips.isEmpty {
                    NavigationLink { AllTripsPage() } label: {
                        Text("See all").font(.custom("Figtree-Medium", size: 15, relativeTo: .subheadline))
                            .foregroundColor(Pearl.link)
                            .frame(minHeight: 44).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .padding(.vertical, -13)
                    .accessibilityLabel("See all trips")
                }
            }
            .padding(.horizontal, 4)
            APCard {
                if trips.isEmpty {
                    Text("No trips yet. Pearl asks when it spots one.")
                        .font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                        .padding(.horizontal, 16).padding(.vertical, 12)
                        .frame(minHeight: 52, alignment: .leading)
                } else {
                    ForEach(Array(trips.enumerated()), id: \.element.id) { i, trip in
                        if i > 0 { APSeparator() }
                        NavigationLink { TripPage(id: trip.id) } label: {
                            TripListRow(name: trip.name, place: TripFace.place(name: trip.name, place: nil),
                                        start: trip.start, end: trip.end, totals: trip.totals)
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Opens the trip")
                    }
                }
            }
        }
    }
}

/// One trip on the A+ card (G7-TripCal): the face, "Trip to Montréal" over
/// "Mar 4–9", the total in plum, the chevron. In two currencies (TR-02m) the
/// other's part joins the dates ("Jun 12–16 · + $310 USD"). VoiceOver reads
/// "Trip to Montréal, March 4 to 9, $1,284.60". At accessibility sizes the
/// total goes under the dates, so nothing is cut.
struct TripListRow: View {
    @Environment(\.dynamicTypeSize) private var textSize
    let name: String
    let place: String
    let start: String
    let end: String
    let totals: [MoneyTotal]

    private var main: String { Format.whole(totals.first?.amount ?? 0) }
    private var amount: String { totals.count > 1 ? main : totals.shown }
    private var dates: String {
        let more = totals.dropFirst().map { "+ \(Format.whole($0.amount)) \($0.currency)" }
        return ([Format.span(start, end)] + more).joined(separator: " \u{00B7} ")
    }

    var body: some View {
        HStack(spacing: 12) {
            Text(TripFace.letters(place))
                .font(.custom("Figtree-Medium", size: 14)).foregroundColor(Pearl.ink)
                .frame(width: 40, height: 40)
                .background(Circle().fill(APlus.face))
                .accessibilityHidden(true)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
                Text(dates).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
                if textSize.isAccessibilitySize {
                    Text(amount).font(Nacre.headline).foregroundColor(Pearl.moneyOut).monospacedDigit()
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            if !textSize.isAccessibilitySize {
                Text(amount).font(Nacre.headline).foregroundColor(Pearl.moneyOut).monospacedDigit()
                    .pearlAmountFit()
            }
            ChatChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(name), \(Format.spokenSpan(start, end)), \(totals.shown)")
    }
}

/// The Calendar's old Trips card row (TR-17 before A+), kept for
/// CalendarView until it moves onto `TripsCard`.
struct TripCardRow: View {
    @Environment(\.dynamicTypeSize) private var textSize
    let name: String
    let start: String
    let end: String
    let totals: [MoneyTotal]

    var body: some View {
        TripListRow(name: name, place: TripFace.place(name: name, place: nil), start: start, end: end, totals: totals)
            .padding(.horizontal, -16)
    }
}

/// TR-18 (G7-TripCal 3): Trips, from See all on the Calendar's Trips card.
/// The glass Back, "Trips" large in Fraunces, then each year ("2026") over
/// its card, newest first; each row opens its page (TR-02). GET /api/trips.
@MainActor
struct AllTripsPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var trips: [Trip]?
    @State private var error: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                Text("Trips").font(Nacre.largeTitle).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                    .padding(.horizontal, 4)
                if let trips = trips {
                    ForEach(years(trips), id: \.year) { group in
                        APSectionLabel(text: group.year).padding(.top, 20).padding(.bottom, 8)
                        APCard {
                            ForEach(Array(group.trips.enumerated()), id: \.element.id) { i, trip in
                                if i > 0 { APSeparator() }
                                NavigationLink { TripPage(id: trip.id) } label: {
                                    TripListRow(name: trip.name, place: TripFace.place(trip), start: trip.start,
                                                end: trip.end, totals: trip.totals)
                                }
                                .buttonStyle(.plain)
                                .accessibilityHint("Opens the trip")
                            }
                        }
                    }
                } else {
                    LoadState(error: error) { Task { await load() } }
                        .padding(.top, 40)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .navigationBarBackButtonHidden(true)
        .navigationBarTitleDisplayMode(.inline)
        .toolbarBackground(.hidden, for: .navigationBar)
        .toolbar {
            ToolbarItem(placement: .navigationBarLeading) {
                TripGlassButton(symbol: "chevron.left", label: "Back") { dismiss() }
            }
        }
        .reloads { await load() }
    }

    /// The years, newest first, each with its trips newest first.
    private func years(_ trips: [Trip]) -> [(year: String, trips: [Trip])] {
        let sorted = trips.sorted { ($0.start, $0.end) > ($1.start, $1.end) }
        var out: [(year: String, trips: [Trip])] = []
        for t in sorted {
            let y = String(t.start.prefix(4))
            if out.last?.year == y { out[out.count - 1].trips.append(t) } else { out.append((y, [t])) }
        }
        return out
    }

    private func load() async {
        do {
            let reply: Reply = try await app.api.get("api/trips")
            // No frame for an empty Trips: it opens only from a card that
            // has trips, so if the last one has gone, go back to that card.
            if reply.trips.isEmpty && trips != nil { dismiss(); return }
            trips = reply.trips
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private struct Reply: Decodable {
        let trips: [Trip]

        init(from decoder: Decoder) throws {
            enum Keys: String, CodingKey { case trips }
            let c = try decoder.container(keyedBy: Keys.self)
            trips = (try? c.decode([Lenient<Trip>].self, forKey: .trips))?.compactMap { $0.value } ?? []
        }
    }
}
