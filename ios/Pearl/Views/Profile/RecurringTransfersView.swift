import SwiftUI

// Profile › Recurring transfers (THL-295, THL-297, THL-292; Pearl iOS
// Handoff File, Pearl app page, "Recurring transfers"): RT-01 every transfer
// she said repeats, what it is, its schedule and what a month of them comes
// to; RT-02 one of them: change what it is, or stop treating it as
// recurring. New ones are still asked about in Needs a look (T-69).

struct RecurringTransfers: Decodable {
    let transfers: [Transfer]
    let count: Int
    /// How many Needs a look is still asking about.
    let asking: Int
    let monthly: Double

    struct Transfer: Decodable, Identifiable, Hashable {
        let id: String
        let ruleId: String
        let name: String
        let account: String?
        let amount: Double
        /// "monthly", "biweekly", "payday"…
        let cadence: String
        /// "every month, around the 1st".
        let when: String?
        let category: String
        /// "Into savings", "Rent".
        let what: String?
        let monthly: Double
        let next: String?
        let count: Int
        let transactions: [Row]?

        struct Row: Decodable, Hashable, Identifiable {
            let id: String
            let date: String
            let amount: Double
        }

        enum CodingKeys: String, CodingKey {
            case id, name, account, amount, cadence, when, category, what, monthly, next, count, transactions
            case ruleId = "rule_id"
        }

        var title: String { name == "Transfer" ? (what ?? category) : name }
    }
}

// MARK: - RT-01

@MainActor
struct RecurringTransfersView: View {
    @EnvironmentObject private var app: AppModel
    @State private var data: RecurringTransfers?
    @State private var categories: [CategoryList.Category] = []
    @State private var open: RecurringTransfers.Transfer?
    @State private var toast: String?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            ProfileHeading(title: "Recurring transfers", intro: lead)
            if let data = data {
                if data.transfers.isEmpty {
                    ProfileNote("When the same amount goes out on a schedule, Needs a look asks whether it repeats. The ones you say yes to are sorted on their own and listed here.")
                        .padding(.top, 8)
                } else {
                    // RT-01's two tiles (THL-295).
                    HStack(spacing: 12) {
                        tile("A month, on average", Format.whole(data.monthly))
                        tile("Recurring", "\(data.count)")
                    }
                    .padding(.top, 4)
                    ProfileSection("\(data.count) recurring")
                    GlassCard {
                        ForEach(Array(data.transfers.enumerated()), id: \.element.id) { i, t in
                            if i > 0 { RowSeparator(inset: 62) }
                            Button { open = t } label: {
                                ProfileRow(initials: t.title, title: t.title, sub: line(t)) {
                                    Text(Format.amount(t.amount)).font(Nacre.body).foregroundColor(Pearl.ink)
                                        .monospacedDigit().lineLimit(1).fixedSize()
                                }
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
                if data.asking > 0 {
                    ProfileSection("New, in Needs a look")
                    GlassCard {
                        NavigationLink { ReviewView() } label: {
                            ProfileRow(symbol: "arrow.triangle.2.circlepath",
                                       title: data.asking == 1 ? "1 transfer to answer" : "\(data.asking) transfers to answer",
                                       pill: StatusPill(text: "Recurring?", tone: .needsALook))
                        }
                        .buttonStyle(.plain)
                    }
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .overlay(alignment: .bottom) {
            if let toast = toast {
                UndoToast(text: toast) { withAnimation { self.toast = nil } }.padding(.bottom, 8)
            }
        }
        .refreshable { await load() }
        .task(id: app.version) { await load() }
        .sheet(item: $open) { t in
            RecurringTransferSheet(transfer: t, categories: categories) { said in
                open = nil
                withAnimation { toast = said }
                app.changed()
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    private var lead: String? {
        guard let data = data, !data.transfers.isEmpty else { return nil }
        return "Transfers that repeat, sorted on their own."
    }

    private func tile(_ label: String, _ value: String) -> some View {
        GlassCard {
            VStack(alignment: .leading, spacing: 4) {
                Text(label).font(Nacre.footnote).foregroundColor(Pearl.ink)
                Text(value).font(.custom("Fraunces-SemiBold", size: 28, relativeTo: .title)).foregroundColor(Pearl.ink)
                    .lineLimit(1).minimumScaleFactor(0.6)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(.horizontal, 16).padding(.vertical, 14)
        }
        .accessibilityElement(children: .combine)
    }

    /// "Rent · monthly · TD Chequing · next Dec 1".
    private func line(_ t: RecurringTransfers.Transfer) -> String {
        let how = t.cadence == "payday" ? "every payday" : cadence(t.cadence).lowercased()
        return [t.what ?? t.category, how, t.account.flatMap { $0.isEmpty ? nil : $0 }, t.next.map { "next \(Format.short($0))" }]
            .compactMap { $0 }.joined(separator: " · ")
    }

    private func load() async {
        do {
            data = try await app.api.get("api/recurring-transfers")
            if categories.isEmpty, let list: CategoryList = try? await app.api.get("api/categories") {
                categories = list.categories.filter { $0.hidden != true }
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - RT-02

/// What it is (Rent, Saved, Moved, or a category), the ones so far, and
/// "Stop treating it as recurring", which keeps how those are sorted.
@MainActor
struct RecurringTransferSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let transfer: RecurringTransfers.Transfer
    let categories: [CategoryList.Category]
    let done: (String) -> Void

    @State private var pick: String
    @State private var other: String?
    @State private var choosing = false
    @State private var busy = false
    @State private var error: String?

    private static let kinds: [(category: String, label: String, sub: String)] = [
        ("Rent & Housing", "Rent", "Counted as a bill"),
        ("Saved", "Saved", "Money you put away"),
        ("Transfers", "Moved", "To another of my accounts"),
    ]

    init(transfer: RecurringTransfers.Transfer, categories: [CategoryList.Category], done: @escaping (String) -> Void) {
        self.transfer = transfer
        self.categories = categories
        self.done = done
        let known = Self.kinds.contains { $0.category == transfer.category }
        _pick = State(initialValue: known ? transfer.category : "other")
        _other = State(initialValue: known ? nil : transfer.category)
    }

    private var chosen: String? { pick == "other" ? other : pick }

    var body: some View {
        VStack(alignment: .leading, spacing: 14) {
            HStack {
                Spacer()
                Text(transfer.title).font(Nacre.headline).foregroundColor(Pearl.ink).lineLimit(1)
                    .accessibilityAddTraits(.isHeader)
                Spacer()
            }
            .overlay(alignment: .trailing) { CloseButton { dismiss() } }
            .padding(.top, 20)
            HStack(spacing: 12) {
                RowAvatar(name: transfer.title, size: 48, font: Nacre.headline)
                VStack(alignment: .leading, spacing: 2) {
                    Text(amountLine).font(Nacre.title2).foregroundColor(Pearl.ink)
                    Text(schedule).font(Nacre.footnote).foregroundColor(Pearl.ink)
                }
                Spacer(minLength: 0)
            }
            .accessibilityElement(children: .combine)
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    GlassCard {
                        ForEach(Array(Self.kinds.enumerated()), id: \.element.category) { i, k in
                            if i > 0 { RowSeparator() }
                            ChoiceLine(title: k.label, sub: k.sub, selected: pick == k.category) { pick = k.category }
                        }
                        RowSeparator()
                        ChoiceLine(title: "Something else", sub: other ?? "Pick a category",
                                   selected: pick == "other") {
                            pick = "other"
                            choosing = true
                        }
                    }
                    if let rows = transfer.transactions, !rows.isEmpty {
                        ProfileSection(transfer.count == 1 ? "The one so far" : "The \(transfer.count) so far")
                        GlassCard {
                            ForEach(Array(rows.enumerated()), id: \.element.id) { i, r in
                                if i > 0 { RowSeparator() }
                                HStack {
                                    Text(Format.weekdayDay(r.date)).font(Nacre.body).foregroundColor(Pearl.ink)
                                    Spacer()
                                    Text("\u{2212}" + Format.amount(abs(r.amount))).font(Nacre.body)
                                        .foregroundColor(Pearl.muted).monospacedDigit()
                                }
                                .padding(.horizontal, 16).frame(minHeight: 46)
                            }
                        }
                    }
                    ProfileNote("Stopping it keeps how the ones so far are sorted. New ones are asked about again.")
                }
            }
            if let error = error { Hint(text: error) }
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || chosen == nil || chosen == transfer.category)
            Button("Stop treating it as recurring") { Task { await stop() } }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(busy)
        }
        .padding(.horizontal, 16).padding(.bottom, 8)
        .background(SheetBackground())
        .sheet(isPresented: $choosing) {
            CategorySheet(name: transfer.title, amount: amountLine, tone: Pearl.ink,
                          categories: categories.filter { !["Income", "Transfers", "Saved", "Rent & Housing"].contains($0.name) },
                          current: other ?? "", spendingOnly: true) { name, _ in
                other = name
                choosing = false
            }
        }
    }

    private var amountLine: String { "\(Format.amount(transfer.amount)) \(transfer.cadence == "payday" ? "each payday" : "each time")" }

    /// "Every month, around the 1st · next Monday, December 1".
    private var schedule: String {
        let when = (transfer.when ?? cadence(transfer.cadence)).capitalizedFirst
        return [when, transfer.next.map { "next \(Format.short($0))" } ?? "next with your pay"]
            .joined(separator: " · ")
    }

    private func save() async {
        guard let category = chosen else { return }
        busy = true
        defer { busy = false }
        do {
            let id = transfer.ruleId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? transfer.ruleId
            let _: OK = try await app.api.put("api/rules/\(id)", ["category": category])
            done("\(transfer.title) is sorted as \(Self.kinds.first { $0.category == category }?.label ?? category) from now on.")
        } catch {
            self.error = app.handle(error)
        }
    }

    private func stop() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.delete("api/recurring-transfers/\(transfer.id)")
            done("\(transfer.title) isn’t treated as recurring any more.")
        } catch {
            self.error = app.handle(error)
        }
    }
}
