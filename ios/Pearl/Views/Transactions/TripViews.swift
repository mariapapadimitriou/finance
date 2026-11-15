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

// MARK: - TR-02 / TR-02m

/// TR-02 (`1327:5084` / `1327:5267`): the trip's dates and count, its total,
/// the month it counts in, its transactions (each opens its page) and
/// "Counts in March, as usual · Tagged “Trip to Montréal”". In two currencies
/// (TR-02m `1332:70213` / `1332:70317`) the total is "$1,240 CAD + $310 USD",
/// "in 2 currencies" joins the line above it, the Counts in column goes (the
/// footer still says it) and a row in the other currency carries its code.
@MainActor
struct TripPage: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let id: String
    @State private var detail: TripDetail?
    @State private var error: String?
    @State private var options = false
    /// Rename the trip was picked on TR-04: TR-08 opens once it has gone.
    @State private var renaming = false
    @State private var showRename = false
    @State private var newName = ""

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
        // TR-08 is asked once TR-04 has gone: a sheet raised while one is
        // closing doesn't appear.
        .sheet(isPresented: $options, onDismiss: {
            if renaming, let d = detail { newName = d.trip.name; showRename = true }
            renaming = false
        }) {
            if let d = detail {
                TripOptionsSheet(trip: d.trip, onClose: { options = false }) {
                    renaming = true
                    options = false
                }
            }
        }
        .sheet(isPresented: $showRename) {
            if let d = detail {
                NameTripSheet(count: d.trip.count, dates: Format.span(d.trip.start, d.trip.end),
                              total: d.trip.totals.shown, months: d.trip.months, name: $newName,
                              primary: "Save", onClose: { showRename = false }) { name in
                    let _: OK = try await app.api.put("api/trips/\(id)", ["name": name])
                    showRename = false
                    app.changed()
                    await load()
                }
            }
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
        }
    }

    private func load() async {
        do {
            detail = try await app.api.get("api/trips/\(id)")
            error = nil
        } catch {
            if detail != nil, let e = error as? APIError, case .server = e {
                // It wasn't there any more (its tag was removed): back out.
                dismiss()
                return
            }
            self.error = app.handle(error)
        }
    }
}

// MARK: - TR-04

/// TR-04 (`1327:5894` / `1327:6011`): the trip's options from ••• on its
/// page. Add transactions, Remove some… and It wasn't a trip have no frames
/// for what they open yet, so only Rename the trip is here (engBOT, Trips build).
struct TripOptionsSheet: View {
    let trip: Trip
    let onClose: () -> Void
    let onRename: () -> Void

    var body: some View {
        PearlSheet {
            PearlSheetHeader(face: trip.place ?? trip.name,
                             overline: "A trip · \(Format.span(trip.start, trip.end))", title: trip.name,
                             sub: trip.by == "pearl" ? trip.day.map { "You said yes on \(Format.short($0))" } : nil,
                             subTone: Pearl.moneyIn, close: onClose)
            PearlSectionLabel(text: "In the trip")
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
            .padding(.horizontal, 16).padding(.vertical, 12)
            .pearlCard(radius: Pearl.radiusTile)
            .accessibilityElement(children: .combine)
            PearlSectionLabel(text: "The trip")
            PearlOptionCard {
                PearlOptionRow(symbol: "pencil", title: "Rename the trip", sub: "Renames its tag too", action: onRename)
            }
        }
    }

    /// "23 transactions · 5 categories".
    private var countLine: String {
        let k = trip.categories?.count ?? 0
        return "\(trip.count) transaction\(trip.count == 1 ? "" : "s")"
            + (k > 0 ? " · \(k) categor\(k == 1 ? "y" : "ies")" : "")
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
