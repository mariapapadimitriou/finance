import SwiftUI

// MARK: - What the server sends (finance/calendar_view.py, finance/ranges.py)

/// GET /api/calendar?month=: six weeks of days, what's due, sorted ranges.
struct CalendarMonth: Decodable {
    let month: String
    let label: String
    let cells: [Cell]
    let bands: [SortedRange]
    let prev: Step?
    let next: Step?

    struct Step: Decodable { let month: String }

    struct Cell: Decodable, Identifiable, Hashable {
        let date: String
        let day: Int
        let due: [Due]
        let inMonth: Bool
        /// "on", "ahead", "none", "today", "future" or "outside".
        let state: String
        var id: String { date }

        enum CodingKeys: String, CodingKey {
            case date, day, due, state
            case inMonth = "in_month"
        }
    }

    init(from decoder: Decoder) throws {
        enum Keys: String, CodingKey { case month, label, cells, bands, prev, next }
        let c = try decoder.container(keyedBy: Keys.self)
        month = try c.decode(String.self, forKey: .month)
        label = (try? c.decode(String.self, forKey: .label)) ?? month
        cells = (try? c.decode([Lenient<Cell>].self, forKey: .cells))?.compactMap { $0.value } ?? []
        bands = (try? c.decode([Lenient<SortedRange>].self, forKey: .bands))?.compactMap { $0.value } ?? []
        prev = try? c.decodeIfPresent(Step.self, forKey: .prev)
        next = try? c.decodeIfPresent(Step.self, forKey: .next)
    }
}

/// A bill, a pay or a chest's amount, on its day.
struct Due: Decodable, Hashable {
    let amount: Double
    let kind: String?
    let label: String
}

/// Days sorted together (CAL-09, T-68).
struct SortedRange: Decodable, Identifiable, Hashable {
    let id: Int
    let name: String?
    let first: String
    let last: String
    let category: String
    let count: Int?
    let total: Double?

    func contains(_ day: String) -> Bool { day >= first && day <= last }
}

/// GET /api/calendar/day/<date>.
struct CalendarDay: Decodable {
    let label: String
    let reason: String?
    let past: Bool?
    let spent: [Spent]
    let spentTotal: Double?
    let due: [Due]

    struct Spent: Decodable, Hashable {
        let merchant: String
        let category: String?
        let amount: Double
        let unusual: Bool?
    }

    enum CodingKeys: String, CodingKey {
        case label, reason, past, spent, due
        case spentTotal = "spent_total"
    }
}

/// GET /api/calendar/range: what was spent in those days, by category.
struct CalendarRange: Decodable {
    let label: String
    let count: Int
    let byCategory: [Part]

    struct Part: Decodable, Hashable {
        let category: String
        let total: Double
    }

    enum CodingKeys: String, CodingKey {
        case label, count
        case byCategory = "by_category"
    }

    var total: Double { byCategory.reduce(0) { $0 + $1.total } }
}

/// POST /api/ranges/preview.
struct RangePreview: Decodable {
    let count: Int
    let total: Double
}

/// POST /api/ranges: what it sorted, to say so and to undo it.
struct RangeSaved: Decodable {
    let title: String?
    let range: SortedRange?
}

// MARK: - The calendar card (T-49, T-50, T-68)

/// The month as a grid: a past day is lagoon with ✓ when spending was on or
/// under the usual pace by its end, rose with ▲ when it had moved ahead;
/// today is outlined; a dot marks something due; days sorted together are
/// outlined in dashes. Select days picks a run of days to sort as one.
@MainActor
struct CalendarCard: View {
    @EnvironmentObject private var app: AppModel
    let month: String
    let categories: [CategoryList.Category]
    let onMonth: (String) -> Void

    @State private var data: CalendarMonth?
    @State private var selecting = false
    @State private var first: String?
    @State private var last: String?
    @State private var range: CalendarRange?
    @State private var day: DayPick?
    @State private var sorting: SortPick?
    @State private var toast: (title: String, undo: Int?)?
    @State private var error: String?

    struct DayPick: Identifiable { let date: String; let band: SortedRange?; var id: String { date } }
    struct SortPick: Identifiable {
        let first: String
        let last: String
        let existing: SortedRange?
        var id: String { first + last + (existing.map { String($0.id) } ?? "") }
    }

    var body: some View {
        VStack(alignment: .leading, spacing: 12) {
            GlassCard {
                VStack(alignment: .leading, spacing: 10) {
                    header
                    weekdays
                    grid
                }
                .padding(16)
            }
            if selecting { selectionPanel }
            if let toast = toast {
                HStack(spacing: 10) {
                    Image(systemName: "checkmark").font(.system(size: 13, weight: .bold)).foregroundColor(Nacre.teal)
                    Text(toast.title).font(Nacre.footnote).foregroundColor(Pearl.ink)
                    Spacer(minLength: 8)
                    if let id = toast.undo {
                        Button("Undo") { Task { await remove(id, undo: true) } }
                            .font(Nacre.textButton).foregroundColor(Pearl.action)
                    }
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
                .background(Capsule().fill(Nacre.glass))
                .overlay(Capsule().strokeBorder(Nacre.edge, lineWidth: 1))
            }
            if let error = error {
                Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
            }
            legend
        }
        .task(id: month) { await load() }
        .sheet(item: $day) { pick in
            DaySheet(date: pick.date, band: pick.band, api: app.api,
                     onChange: { band in day = nil; sorting = SortPick(first: band.first, last: band.last, existing: band) },
                     onRemove: { band in day = nil; Task { await remove(band.id, undo: false) } })
                .presentationDetents([.medium, .large])
        }
        .sheet(item: $sorting) { pick in
            SortDaysSheet(first: pick.first, last: pick.last, existing: pick.existing,
                          categories: categories, api: app.api) { saved in
                sorting = nil
                clear()
                selecting = false
                toast = (saved.title ?? "Sorted.", pick.existing == nil ? saved.range?.id : nil)
                Task { await load() }
                app.changed()
            }
        }
    }

    // MARK: Parts

    private var header: some View {
        HStack(spacing: 10) {
            Text(data?.label ?? Format.month(month)).font(Nacre.title2).foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.8)
            HStack(spacing: 2) {
                arrow("chevron.left", to: data?.prev?.month, label: "Previous month")
                arrow("chevron.right", to: data?.next?.month, label: "Next month")
            }
            Spacer(minLength: 4)
            Button(selecting ? "Cancel" : "Select days") {
                selecting.toggle()
                clear()
            }
            .font(Nacre.footnote).foregroundColor(Pearl.ink)
            .padding(.horizontal, 14).frame(height: 32)
            .overlay(Capsule().strokeBorder(Pearl.ink, lineWidth: 1))
            .buttonStyle(.plain)
        }
    }

    private func arrow(_ symbol: String, to target: String?, label: String) -> some View {
        Button { if let target = target { onMonth(target) } } label: {
            Image(systemName: symbol).font(.system(size: 13, weight: .semibold))
                .foregroundColor(Pearl.action)
                .frame(width: 28, height: 32)
        }
        .buttonStyle(.plain)
        .disabled(target == nil)
        .accessibilityLabel(label)
    }

    private var weekdays: some View {
        HStack(spacing: 0) {
            ForEach(["SUN", "MON", "TUE", "WED", "THU", "FRI", "SAT"], id: \.self) { d in
                Text(d).font(Nacre.caption2).tracking(0.3).foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity)
            }
        }
        .accessibilityHidden(true)
    }

    private var grid: some View {
        let rows = (data?.cells ?? []).chunked(7).filter { row in row.contains { $0.inMonth } }
        return VStack(spacing: 6) {
            if data == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            ForEach(Array(rows.enumerated()), id: \.offset) { _, row in
                HStack(spacing: 6) {
                    ForEach(row) { cell in dayCell(cell) }
                }
            }
        }
    }

    @ViewBuilder private func dayCell(_ cell: CalendarMonth.Cell) -> some View {
        if !cell.inMonth {
            Color.clear.frame(maxWidth: .infinity).frame(height: 50)
        } else {
            let ends = cell.date == first || cell.date == last
            let between = inSelection(cell.date)
            let band = data?.bands.first { $0.contains(cell.date) }
            Button { tap(cell, band: band) } label: {
                VStack(spacing: 2) {
                    Text("\(cell.day)").font(Nacre.body)
                        .foregroundColor(ends ? Pearl.action : Pearl.ink)
                    marker(cell)
                }
                .frame(maxWidth: .infinity).frame(height: 50)
                .background(RoundedRectangle(cornerRadius: 12, style: .continuous).fill(fill(cell, between: between)))
                .overlay {
                    let shape = RoundedRectangle(cornerRadius: 12, style: .continuous)
                    if ends || cell.state == "today" {
                        shape.strokeBorder(Pearl.action, lineWidth: 2)
                    } else if band != nil {
                        shape.strokeBorder(Pearl.action.opacity(0.8), style: StrokeStyle(lineWidth: 1.5, dash: [4, 3]))
                    }
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel(label(cell, band: band))
            .accessibilityAddTraits(ends ? .isSelected : [])
        }
    }

    /// ✓ on pace, ▲ ahead of it, a dot when something's due.
    @ViewBuilder private func marker(_ cell: CalendarMonth.Cell) -> some View {
        switch cell.state {
        case "on":
            Image(systemName: "checkmark").font(.system(size: 9, weight: .bold)).foregroundColor(Nacre.teal)
        case "ahead":
            Image(systemName: "triangle.fill").font(.system(size: 7)).foregroundColor(Pearl.moneyOut.opacity(0.8))
        default:
            if !cell.due.isEmpty {
                Circle().fill(Pearl.ink.opacity(0.7)).frame(width: 4, height: 4).padding(.top, 3)
            } else {
                Color.clear.frame(height: 9)
            }
        }
    }

    private func fill(_ cell: CalendarMonth.Cell, between: Bool) -> Color {
        if between { return Pearl.blush.opacity(0.9) }
        switch cell.state {
        case "on": return Nacre.mint
        case "ahead": return Pearl.blush.opacity(0.7)
        case "today": return Color.white.opacity(0.6)
        default: return .clear
        }
    }

    private func label(_ cell: CalendarMonth.Cell, band: SortedRange?) -> String {
        var parts = [Format.day(cell.date)]
        switch cell.state {
        case "on": parts.append("on or under your usual pace")
        case "ahead": parts.append("over your usual pace")
        case "today": parts.append("today")
        default: break
        }
        if !cell.due.isEmpty { parts.append("\(cell.due.count) due") }
        if let band = band { parts.append("sorted together as \(band.name ?? band.category)") }
        return parts.joined(separator: ", ")
    }

    private var legend: some View {
        HStack(spacing: 14) {
            Label { Text("Over your usual pace") } icon: {
                Image(systemName: "triangle.fill").font(.system(size: 7)).foregroundColor(Pearl.moneyOut.opacity(0.8))
            }
            Label { Text("On pace") } icon: {
                Image(systemName: "checkmark").font(.system(size: 9, weight: .bold)).foregroundColor(Nacre.teal)
            }
            Label { Text("Due") } icon: { Circle().fill(Pearl.ink.opacity(0.7)).frame(width: 4, height: 4) }
        }
        .font(Nacre.footnote).foregroundColor(Pearl.ink)
        .labelStyle(TightLabel())
        .frame(maxWidth: .infinity)
        .accessibilityElement(children: .combine)
    }

    private struct TightLabel: LabelStyle {
        func makeBody(configuration: Configuration) -> some View {
            HStack(spacing: 4) { configuration.icon; configuration.title }
        }
    }

    // MARK: Select days (T-50)

    @ViewBuilder private var selectionPanel: some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 8) {
                if let range = range, first != nil, last != nil {
                    Text(range.label).font(Nacre.headline).foregroundColor(Pearl.ink)
                    Text("\(range.count) purchase\(range.count == 1 ? "" : "s") · \(Format.whole(range.total)) spent")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink)
                    if !range.byCategory.isEmpty {
                        Text(range.byCategory.prefix(3).map { "\($0.category) \(Format.whole($0.total))" }
                            .joined(separator: " · "))
                            .font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(2)
                    }
                    HStack {
                        Button("Sort these days") {
                            if let a = first, let b = last { sorting = SortPick(first: a, last: b, existing: nil) }
                        }
                        .buttonStyle(NacreButtonStyle())
                        .disabled(range.count == 0)
                        Button("Clear") { clear() }
                            .font(Nacre.textButton).foregroundColor(Pearl.action)
                            .padding(.horizontal, 16)
                    }
                    .padding(.top, 4)
                } else {
                    Text(first == nil ? "Tap the first day." : "Now tap the last day.")
                        .font(Nacre.body).foregroundColor(Pearl.ink)
                }
            }
            .padding(16)
        }
    }

    private func inSelection(_ day: String) -> Bool {
        guard let a = first, let b = last else { return false }
        return day > min(a, b) && day < max(a, b)
    }

    private func tap(_ cell: CalendarMonth.Cell, band: SortedRange?) {
        guard selecting else {
            day = DayPick(date: cell.date, band: band)
            return
        }
        if first == nil || last != nil {
            first = cell.date
            last = nil
            range = nil
        } else if let a = first {
            first = min(a, cell.date)
            last = max(a, cell.date)
            Task { await loadRange() }
        }
    }

    private func clear() {
        first = nil
        last = nil
        range = nil
    }

    // MARK: Loading

    private func load() async {
        do {
            data = try await app.api.get("api/calendar", query: ["month": month])
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func loadRange() async {
        guard let a = first, let b = last else { return }
        range = try? await app.api.get("api/calendar/range", query: ["first": a, "last": b])
    }

    private func remove(_ id: Int, undo: Bool) async {
        do {
            struct Reply: Decodable { let title: String? }
            let reply: Reply = try await app.api.delete("api/ranges/\(id)")
            toast = (undo ? "Undone." : (reply.title ?? "Removed."), nil)
            await load()
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - One day

/// What a day held: what was spent, what's due, one line on its shading,
/// and the days it was sorted with, with Change and Remove.
@MainActor
struct DaySheet: View {
    let date: String
    let band: SortedRange?
    let api: APIClient
    let onChange: (SortedRange) -> Void
    let onRemove: (SortedRange) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var data: CalendarDay?

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: data?.label ?? Format.day(date)) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if let reason = data?.reason, !reason.isEmpty {
                        Text(reason).font(Nacre.subheadline).foregroundColor(Pearl.ink)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let band = band {
                        GlassCard {
                            VStack(alignment: .leading, spacing: 6) {
                                Text("Sorted together as \(band.name.flatMap { $0.isEmpty ? nil : $0 } ?? band.category)")
                                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                                Text("\(Format.short(band.first)) – \(Format.short(band.last)) · \(band.category)")
                                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                                HStack(spacing: 20) {
                                    Button("Change") { onChange(band) }
                                    Button("Remove") { onRemove(band) }
                                }
                                .font(Nacre.textButton).foregroundColor(Pearl.action).padding(.top, 4)
                            }
                            .padding(16)
                        }
                    }
                    if let data = data {
                        if !data.spent.isEmpty {
                            heading(data.past == false ? "Spent so far" : "Spent")
                            GlassCard {
                                ForEach(Array(data.spent.enumerated()), id: \.offset) { i, s in
                                    if i > 0 { RowSeparator() }
                                    line(s.merchant, sub: [s.category, s.unusual == true ? "unusual" : nil]
                                            .compactMap { $0 }.joined(separator: " · "),
                                         amount: "\u{2212}" + Format.amount(s.amount), tone: Pearl.moneyOut)
                                }
                            }
                        }
                        if !data.due.isEmpty {
                            heading("Due")
                            GlassCard {
                                ForEach(Array(data.due.enumerated()), id: \.offset) { i, d in
                                    if i > 0 { RowSeparator() }
                                    let pay = d.kind == "pay"
                                    line(d.label, sub: nil,
                                         amount: (pay ? "+" : "\u{2212}") + Format.amount(d.amount),
                                         tone: pay ? Pearl.moneyIn : (d.kind == "chest" ? Pearl.muted : Pearl.moneyOut))
                                }
                            }
                        }
                        if data.spent.isEmpty && data.due.isEmpty {
                            Text(data.past == false ? "Nothing is due." : "Nothing was spent.")
                                .font(Nacre.body).foregroundColor(Pearl.muted)
                        }
                    } else {
                        ProgressView().frame(maxWidth: .infinity).padding(.vertical, 24)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
        }
        .background(SheetBackground())
        .task { data = try? await api.get("api/calendar/day/\(date)") }
    }

    private func heading(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 4)
    }

    private func line(_ name: String, sub: String?, amount: String, tone: Color) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                if let sub = sub, !sub.isEmpty {
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            Spacer(minLength: 8)
            Text(amount).font(Nacre.headline).monospacedDigit().foregroundColor(tone)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }
}

// MARK: - Sort these days (T-21)

/// From and to, one category and an optional name; the purchases in those
/// days take the category. Money in and transfers stay as they are.
@MainActor
struct SortDaysSheet: View {
    let existing: SortedRange?
    let categories: [CategoryList.Category]
    let api: APIClient
    let onSaved: (RangeSaved) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var from: Date
    @State private var to: Date
    @State private var category: String?
    @State private var name: String
    @State private var picking = false
    @State private var preview: RangePreview?
    @State private var busy = false
    @State private var error: String?

    init(first: String, last: String, existing: SortedRange?, categories: [CategoryList.Category],
         api: APIClient, onSaved: @escaping (RangeSaved) -> Void) {
        self.existing = existing
        self.categories = categories
        self.api = api
        self.onSaved = onSaved
        _from = State(initialValue: Format.localDay(first) ?? Date())
        _to = State(initialValue: Format.localDay(last) ?? Date())
        _category = State(initialValue: existing?.category)
        _name = State(initialValue: existing?.name ?? "")
    }

    private var first: String { Format.isoDay(min(from, to)) }
    private var last: String { Format.isoDay(max(from, to)) }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: "Sort these days") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 8) {
                    Text("Money in and transfers stay as they are.")
                        .font(Nacre.footnote).foregroundColor(Pearl.ink).padding(.horizontal, 4)
                    heading("Dates")
                    GlassCard {
                        dateRow("From", selection: $from)
                        RowSeparator()
                        dateRow("To", selection: $to)
                    }
                    heading("Sort as")
                    GlassCard {
                        Button { picking = true } label: {
                            HStack {
                                Text("Category").font(Nacre.body).foregroundColor(Pearl.ink)
                                Spacer()
                                Text(category ?? "Choose").font(Nacre.body)
                                    .foregroundColor(category == nil ? Pearl.action : Pearl.muted)
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(Pearl.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 52)
                            .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        RowSeparator()
                        HStack {
                            Text("Name").font(Nacre.body).foregroundColor(Pearl.ink)
                            TextField("", text: $name, prompt: Text("Optional, like Montreal trip").foregroundColor(Pearl.muted))
                                .font(Nacre.body).multilineTextAlignment(.trailing)
                                .foregroundColor(Pearl.muted)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.horizontal, 4)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 16)
            }
            if let p = preview {
                Text("\(Format.amount(p.total)) total").font(Nacre.footnote).foregroundColor(Pearl.ink)
                    .padding(.bottom, 6)
            }
            Button(buttonLabel) { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(category == nil || (preview?.count ?? 0) == 0 || busy)
                .padding(.horizontal, 16).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDragIndicator(.visible)
        .task(id: "\(first)\(last)\(category ?? "")") { await loadPreview() }
        .sheet(isPresented: $picking) {
            CategorySheet(name: name.isEmpty ? "These days" : name, amount: preview.map { Format.amount($0.total) } ?? "",
                          tone: Pearl.moneyOut, categories: categories, current: category ?? "",
                          spendingOnly: true) { picked, _ in
                category = picked
                picking = false
            }
        }
    }

    private var buttonLabel: String {
        guard let p = preview, category != nil else { return existing == nil ? "Sort" : "Save" }
        return "Sort \(p.count) transaction\(p.count == 1 ? "" : "s")"
    }

    private func heading(_ text: String) -> some View {
        Text(text.uppercased()).font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
            .padding(.horizontal, 16).padding(.top, 10)
    }

    private func dateRow(_ label: String, selection: Binding<Date>) -> some View {
        DatePicker(selection: selection, displayedComponents: .date) {
            Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
        }
        .tint(Pearl.action)
        .padding(.horizontal, 16).frame(minHeight: 52)
    }

    private var body_: [String: Any] {
        var b: [String: Any] = ["first": first, "last": last, "name": name.trimmingCharacters(in: .whitespaces)]
        if let category = category { b["category"] = category }
        if let id = existing?.id { b["id"] = id }
        return b
    }

    private func loadPreview() async {
        guard category != nil else {
            // A category is needed to preview; count with one the range won't keep.
            var b = body_
            b["category"] = "Other"
            preview = try? await api.post("api/ranges/preview", b)
            return
        }
        do {
            preview = try await api.post("api/ranges/preview", body_)
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let reply: RangeSaved
            if let id = existing?.id {
                reply = try await api.put("api/ranges/\(id)", body_)
            } else {
                reply = try await api.post("api/ranges", body_)
            }
            onSaved(reply)
        } catch {
            self.error = error.localizedDescription
        }
    }
}

extension Array {
    /// [1…14] into rows of 7.
    func chunked(_ size: Int) -> [[Element]] {
        stride(from: 0, to: count, by: size).map { Array(self[$0..<Swift.min($0 + size, count)]) }
    }
}
