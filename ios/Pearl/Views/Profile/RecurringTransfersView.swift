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
    private var categories: [CategoryList.Category] { app.categories }
    @State private var open: RecurringTransfers.Transfer?
    /// The transfers Needs a look is asking about.
    @State private var waiting: [Review.Item] = []
    /// RT-02 v2: the transfer a pill opens.
    @State private var opening: String?
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
                    APCard {
                        ForEach(Array(data.transfers.enumerated()), id: \.element.id) { i, t in
                            if i > 0 { APSeparator() }
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
                    // RT-01: each one waiting, as its own row.
                    ProfileSection("New, in Needs a look")
                    APCard {
                        ForEach(Array(waiting.enumerated()), id: \.element.key) { i, item in
                            if i > 0 { APSeparator() }
                            NavigationLink { ReviewView() } label: {
                                ProfileRow(initials: item.txn.name, title: item.txn.name,
                                           sub: "\(Format.amount(abs(item.txn.amount)))" + (item.series?.when.map { " · \($0)" } ?? ""),
                                           pill: StatusPill(text: "Recurring?", tone: .needsALook))
                            }
                            .buttonStyle(.plain)
                        }
                        if waiting.isEmpty {
                            NavigationLink { ReviewView() } label: {
                                ProfileRow(symbol: "arrow.triangle.2.circlepath",
                                           title: data.asking == 1 ? "1 transfer to answer" : "\(data.asking) transfers to answer",
                                           pill: StatusPill(text: "Recurring?", tone: .needsALook))
                            }
                            .buttonStyle(.plain)
                        }
                    }
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .sheet(item: $open) { t in
            RecurringTransferSheet(transfer: t, categories: categories, done: { said, undo in
                open = nil
                // RT-02 v2: a change says so with Undo; Stop has none.
                app.say(said, undo: undo)
                app.changed()
            }, onOpen: { id in
                open = nil
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { opening = id }
            })
            .presentationDragIndicator(.visible)
        }
        .navigationDestination(isPresented: Binding(get: { opening != nil }, set: { if !$0 { opening = nil } })) {
            if let id = opening { TransactionByID(id: id, categories: categories) }
        }
    }

    private var lead: String? {
        guard let data = data, !data.transfers.isEmpty else { return nil }
        return "Transfers that repeat, sorted on their own."
    }

    private func tile(_ label: String, _ value: String) -> some View {
        APCard {
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
            if (data?.asking ?? 0) > 0, let review: Review = try? await app.api.get("api/review") {
                waiting = review.recurringTransfer
            }
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - RT-02 v2

/// RT-02 v2 (POLISH-01, 1393:85417 / 1393:85693; THL-295, THL-292,
/// THL-297): what it is as tiles, the current one ringed, and a tap changes
/// it at once with Undo (it replaces Save; product owner, 2026-11-16). Then
/// the ones so far as the rhythm (a pill opens that transfer) and "Stop
/// treating it as recurring" as a row, which keeps how those are sorted.
@MainActor
struct RecurringTransferSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let transfer: RecurringTransfers.Transfer
    let categories: [CategoryList.Category]
    /// What to say, and its Undo.
    let done: (String, (() async throws -> Void)?) -> Void
    /// A pill: open that transfer's page.
    var onOpen: ((String) -> Void)? = nil

    @State private var choosing = false
    @State private var busy = false
    @State private var error: String?

    /// RT-02 v2's tiles: what it is, by the category it sorts to.
    private static let kinds: [(category: String, label: String, line: String, symbol: String)] = [
        ("Rent & Housing", "Rent", "Spending on rent", "house"),
        ("Saved", "Into savings", "Counts as saved", "lifepreserver"),
        ("Transfers", "My other account", "Doesn’t count", "arrow.left.arrow.right"),
    ]

    private var known: Bool { Self.kinds.contains { $0.category == transfer.category } }

    /// The ones so far, oldest first; the rhythm shows the latest nine.
    private var rows: [RecurringTransfers.Transfer.Row] { Array((transfer.transactions ?? []).prefix(9).reversed()) }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: sheetTitle) { dismiss() }.sheetPart()
            ScrollView {
                VStack(alignment: .leading, spacing: 10) {
                    QuestionHeader(name: amountLine, amount: schedule, tone: Pearl.moneyOut, sub: transfer.account)
                    QuestionCaption(text: "What it is")
                    AnswerGrid {
                        ForEach(Self.kinds, id: \.category) { k in
                            AnswerTile(title: k.label, line: k.line, symbol: k.symbol,
                                       current: transfer.category == k.category) { change(to: k.category) }
                        }
                        AnswerTile(title: "Something else", line: known ? "Pick a category" : transfer.category,
                                   symbol: "bag", current: !known) { choosing = true }
                    }
                    .disabled(busy)
                    if !rows.isEmpty {
                        QuestionCaption(text: transfer.count == 1 ? "The one so far" : "The \(transfer.count) so far")
                        WhyCard(sentence: sentence, dates: rows.map(\.date), amount: transfer.amount,
                                footer: onOpen == nil ? nil : "Tap any month to open that transfer",
                                onTap: onOpen.map { open in { i in open(rows[i].id) } })
                    }
                    AnswerRow(symbol: "person.crop.circle.badge.xmark", title: "Stop treating it as recurring",
                              line: transfer.count == 1 ? "It keeps its category; new ones are asked again"
                                  : "The \(transfer.count) keep their category; new ones are asked again") {
                        Task { await stop() }
                    }
                    .disabled(busy)
                    if let error = error { Hint(text: error) }
                    QuestionFooter(text: "A change moves \(transfer.count == 1 ? "it" : "all \(transfer.count)") and the ones to come, with Undo.")
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
                .sheetPart()
            }
        }
        .background(SheetBackground())
        .fitsContent()
        .sheet(isPresented: $choosing) {
            CategorySheet(name: transfer.title, amount: amountLine, tone: Pearl.ink,
                          categories: categories.filter { !["Income", "Transfers", "Saved", "Rent & Housing"].contains($0.name) },
                          current: known ? "" : transfer.category, spendingOnly: true) { name, _ in
                choosing = false
                change(to: name)
            }
        }
    }

    /// "Rent to M. Papas".
    private var sheetTitle: String {
        let what = Self.kinds.first { $0.category == transfer.category }?.label ?? transfer.what ?? transfer.category
        return transfer.name == "Transfer" || transfer.name == what ? what : "\(what) to \(transfer.name)"
    }

    /// "$1,450.00 a month".
    private var amountLine: String { "\(Format.amount(transfer.monthly)) a month" }

    /// "Every month, around the 1st".
    private var schedule: String { (transfer.when ?? cadence(transfer.cadence)).capitalizedFirst }

    /// "Every $1,450.00 to M. Papas on or near the 1st, since March. Next one Mon, Dec 1."
    private var sentence: String {
        let to = transfer.name == "Transfer" ? "" : " to \(transfer.name)"
        let when = (transfer.when ?? "").replacingOccurrences(of: "every month, around", with: "on or near")
        let since = rows.first.map { ", since \(AnswerSheet.sinceMonth($0.date))" } ?? ""
        let next = transfer.next.map { " Next one \(Format.weekdayDay($0))." } ?? ""
        return "Every \(Format.amount(transfer.amount))\(to)\(when.isEmpty ? "" : " " + when)\(since).\(next)"
    }

    /// A tap changes it at once; Undo puts the one it was back.
    private func change(to category: String) {
        guard category != transfer.category, !busy else { return }
        busy = true
        let id = transfer.ruleId.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? transfer.ruleId
        let was = transfer.category
        let api = app.api
        Task {
            defer { busy = false }
            do {
                let _: OK = try await api.put("api/rules/\(id)", ["category": category])
                let label = Self.kinds.first { $0.category == category }?.label ?? category
                done("\(transfer.title) is sorted as \(label) from now on.", {
                    let _: OK = try await api.put("api/rules/\(id)", ["category": was])
                })
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private func stop() async {
        busy = true
        defer { busy = false }
        do {
            let _: OK = try await app.api.delete("api/recurring-transfers/\(transfer.id)")
            done("\(transfer.title) isn’t treated as recurring any more.", nil)
        } catch {
            self.error = app.handle(error)
        }
    }
}
