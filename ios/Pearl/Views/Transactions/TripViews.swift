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
// TR-02c By category on the trip's page, and the toasts after Make a trip and Rename
// TR-03  The trip by category (TripByCategory)
// TR-11  Add transactions · TR-12 Remove some… (TransactionsView with a TripPick)
// TR-13  Not a trip? (NotATripSheet)
// TR-14  Tap TR-01's card: its rows, AI-09's plain list (QuickSortView)

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

// MARK: - TR-02 / TR-02m / TR-02c

/// TR-02 (`1327:5084` / `1327:5267`): the trip's dates and count, its total,
/// the month it counts in, its transactions (each opens its page) and
/// "Counts in March, as usual · Tagged “Trip to Montréal”". In two currencies
/// (TR-02m `1332:70213` / `1332:70317`) the total is "$1,240 CAD + $310 USD",
/// "in 2 currencies" joins the line above it, the Counts in column goes (the
/// footer still says it) and a row in the other currency carries its code.
/// TR-02c (`1347:74145` / `1347:74261`): "By category" under the footer opens
/// TR-03. The toasts (made, renamed, added, removed, not a trip) are the
/// app's own (`AppModel.say`), since the page may open or close under them.
@MainActor
struct TripPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let id: String
    @State private var detail: TripDetail?
    @State private var error: String?
    @State private var options = false
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
                content(d)
                    .padding(.horizontal, Pearl.gutter).padding(.top, 8).padding(.bottom, 32)
            } else {
                LoadState(error: error) { Task { await load() } }
                    .padding(.top, 40)
            }
        }
        .nacreScreen()
        .navigationTitle(detail?.trip.name ?? "")
        .navigationBarTitleDisplayMode(.inline)
        .toolbar {
            ToolbarItem(placement: .navigationBarTrailing) {
                if detail != nil {
                    Button { options = true } label: {
                        Image(systemName: "ellipsis").font(.system(size: 17, weight: .semibold))
                            .foregroundColor(Pearl.ink)
                    }
                    .accessibilityLabel("Trip options")
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

    @ViewBuilder private func content(_ d: TripDetail) -> some View {
        let t = d.trip
        let mixed = t.totals.mixed
        let main = t.totals.first?.currency
        VStack(alignment: .leading, spacing: 12) {
            HStack(alignment: .center, spacing: 12) {
                VStack(alignment: .leading, spacing: 0) {
                    Text(t.line + (mixed ? " · in \(t.totals.count) currencies" : ""))
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                    Text(t.totals.shown)
                        .font(Pearl.heading(mixed ? 17 : 22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                        .lineLimit(1).minimumScaleFactor(0.7)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                if !mixed {
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Counts in").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        Text(t.months).font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                            .lineLimit(1).minimumScaleFactor(0.7)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
            .glassCard(radius: 22)
            .accessibilityElement(children: .combine)
            if !d.rows.isEmpty {
                GlassCard(radius: 22) {
                    ForEach(Array(d.rows.enumerated()), id: \.element.id) { i, row in
                        if i > 0 { RowSeparator(inset: 72) }
                        NavigationLink { TransactionByID(id: row.id, categories: app.categories) } label: {
                            TransactionRow(t: row, showsTrip: false,
                                           currency: mixed && d.currencies[row.id] != main ? d.currencies[row.id] : nil)
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            Text("Counts in \(t.months), as usual · Tagged \u{201C}\(t.name)\u{201D}")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
                .padding(.horizontal, 4)
            // TR-02c (1347:74145): "By category" opens TR-03.
            NavigationLink { TripByCategory(trip: t) } label: {
                Text("By category").font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .padding(.horizontal, 24).frame(minHeight: 44)
                    .background(Capsule().fill(Pearl.control))
                    .contentShape(Capsule())
            }
            .buttonStyle(.plain)
            .padding(.top, 4)
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

// MARK: - TR-03

/// TR-03 (`1327:5447` / `1327:5671`), from TR-02c's "By category": the trip as
/// Cash flow's By category is, "Mar 4–9 · Montréal   23 transactions", the
/// trip total, then what it spent in each category with its count.
/// Cash flow's Spent / Saved / Leftover bar, the ⌄ by the dates and the
/// rows' chevrons are left out: a trip has no Saved or Leftover, and there
/// is no frame for what the ⌄ or a row opens (engBOT, trips follow-ups).
struct TripByCategory: View {
    let trip: Trip

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 12) {
                VStack(alignment: .leading, spacing: 6) {
                    HStack(alignment: .firstTextBaseline, spacing: 8) {
                        Text([Format.span(trip.start, trip.end), trip.place].compactMap { $0 }.joined(separator: " · "))
                            .font(Nacre.headline).foregroundColor(Pearl.ink)
                        Spacer(minLength: 8)
                        Text("\(trip.count) transaction\(trip.count == 1 ? "" : "s")")
                            .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                    VStack(alignment: .leading, spacing: 0) {
                        Text("Trip total").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        Text(Self.whole(trip.totals))
                            .font(Pearl.heading(22, relativeTo: .title2)).foregroundColor(Pearl.ink)
                            .lineLimit(1).minimumScaleFactor(0.7)
                    }
                    .accessibilityElement(children: .combine)
                }
                .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 14)
                .frame(maxWidth: .infinity, alignment: .leading)
                .glassCard(radius: 22)
                let cats = trip.categories ?? []
                if !cats.isEmpty {
                    Text("SPENT").font(Nacre.caption1).foregroundColor(Pearl.ink)
                        .padding(.leading, 16).padding(.top, 4)
                        .accessibilityAddTraits(.isHeader)
                    GlassCard(radius: 22) {
                        ForEach(Array(cats.enumerated()), id: \.element.category) { i, c in
                            if i > 0 { RowSeparator() }
                            HStack(spacing: 10) {
                                Text(c.category).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                                Text("\(c.count)").font(Nacre.footnote).foregroundColor(Pearl.muted)
                                Spacer(minLength: 8)
                                Text(Self.whole(c.money)).font(Nacre.body).foregroundColor(Pearl.ink)
                                    .monospacedDigit().pearlAmountFit()
                            }
                            .padding(.horizontal, 16).frame(minHeight: 50)
                            .accessibilityElement(children: .combine)
                        }
                    }
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.top, 8).padding(.bottom, 32)
        }
        .nacreScreen()
        .navigationTitle(trip.name)
        .navigationBarTitleDisplayMode(.large)
    }

    /// "$1,284", "$930"; in several currencies "$1,240 CAD + $310 USD". No
    /// minus: a trip's total is a total (note 1329:69536, Wording).
    static func whole(_ parts: [MoneyTotal]) -> String {
        parts.count <= 1 ? Format.whole(parts.first?.amount ?? 0) : parts.shown
    }
}

// MARK: - TR-04

/// TR-04 (`1327:5894` / `1327:6011`): the trip's options from ••• on its
/// page: Add transactions and Remove some… on the In the trip card (TR-11,
/// TR-12), then Rename the trip (TR-08) and It wasn't a trip (TR-13).
struct TripOptionsSheet: View {
    let trip: Trip
    let onClose: () -> Void
    let onAdd: () -> Void
    let onRemove: () -> Void
    let onRename: () -> Void
    let onNotATrip: () -> Void

    var body: some View {
        PearlSheet {
            PearlSheetHeader(face: trip.place ?? trip.name,
                             overline: "A trip · \(Format.span(trip.start, trip.end))", title: trip.name,
                             sub: trip.by == "pearl" ? trip.day.map { "You said yes on \(Format.short($0))" } : nil,
                             subTone: Pearl.moneyIn, close: onClose)
            PearlSectionLabel(text: "In the trip")
            VStack(alignment: .leading, spacing: 10) {
                HStack(spacing: 12) {
                    PearlBubble(symbol: "airplane")
                    VStack(alignment: .leading, spacing: 2) {
                        Text(countLine).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                        Text("They still count in \(trip.months) · tagged \(trip.name)")
                            .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Text(trip.totals.shown).font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.moneyIn)
                        .pearlAmountFit()
                }
                .accessibilityElement(children: .combine)
                HStack(spacing: 8) {
                    chip("Add transactions", action: onAdd)
                    chip("Remove some\u{2026}", action: onRemove)
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .pearlCard(radius: Pearl.radiusTile)
            PearlSectionLabel(text: "The trip")
            PearlOptionCard {
                PearlOptionRow(symbol: "pencil", title: "Rename the trip", sub: "Renames its tag too", action: onRename)
                PearlOptionRow(symbol: "xmark", title: "It wasn\u{2019}t a trip",
                               sub: "Asks first · the \(trip.count) stay\(trip.count == 1 ? "s" : "") sorted as \(trip.count == 1 ? "it is" : "they are")",
                               action: onNotATrip)
            }
        }
    }

    /// TR-04's chip buttons, side by side.
    private func chip(_ title: String, action: @escaping () -> Void) -> some View {
        Button(action: action) {
            Text(title).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.8)
                .padding(.horizontal, 16).frame(maxWidth: .infinity, minHeight: 44)
                .background(Capsule().fill(Pearl.control))
                .contentShape(Capsule())
        }
        .buttonStyle(.plain)
    }

    /// "23 transactions · 5 categories".
    private var countLine: String {
        let k = trip.categories?.count ?? 0
        return "\(trip.count) transaction\(trip.count == 1 ? "" : "s")"
            + (k > 0 ? " · \(k) categor\(k == 1 ? "y" : "ies")" : "")
    }
}

// MARK: - TR-13

/// TR-13 (`1347:75171` / `1347:75224`): It wasn't a trip, asked first. The
/// trip and its tag go, the rows stay, and Pearl won't ask about those dates
/// again. Its toast's Undo puts the trip back exactly, dates unskipped too
/// (POST /api/trips/<id>/restore).
struct NotATripSheet: View {
    @EnvironmentObject private var app: AppModel
    let trip: Trip
    let onClose: () -> Void
    /// The trip has ended: its page closes.
    let onDone: () -> Void

    var body: some View {
        PearlConfirmSheet(overline: "\(trip.name) · \(Format.span(trip.start, trip.end))", title: "Not a trip?",
                          message: "The trip and its tag go. \(Trip.stayLine(trip.count)), in \(trip.months). Pearl won\u{2019}t ask about these dates again.",
                          primary: "Not a trip", busyLabel: "Ending\u{2026}", secondary: "Keep it",
                          failure: "Couldn\u{2019}t end the trip. Nothing changed. Try again.", onClose: onClose) {
            struct Ended: Decodable { let count: Int? }
            let reply: Ended = try await app.api.delete("api/trips/\(trip.id)")
            let n = reply.count ?? trip.count
            let api = app.api, id = trip.id
            app.say("Not a trip · \(n) \(n == 1 ? "stays as it is" : "stay as they are")") {
                let _: TripReply = try await api.post("api/trips/\(id)/restore", [:])
            }
            app.changed()
            onDone()
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
                          message: "It shows on each of the \(count) and on the trip\u{2019}s own page, and adds a tag with the same name. They still count in \(months).",
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
