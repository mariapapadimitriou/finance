import SwiftUI

// Profile › Recurring transfers (THL-295, THL-297, THL-292), A+ (REDESIGN-12;
// boards G5b-Recurring, G5b-RecurringOne): RT-01 every transfer she said
// repeats and what a month of them comes to; RT-02 one of them, pushed:
// change what it is at once, or stop treating it as recurring, each with
// Undo. New ones are still asked about in Needs a look (T-69).

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

// MARK: - RT-01 (G5b-Recurring)

/// What a month of them comes to with the count as a pill, RECURRING as
/// payment rows (rent plum with −, into savings or another of her accounts
/// muted ⇄ with no sign), and the ones Needs a look is still asking about.
@MainActor
struct RecurringTransfersView: View {
    @EnvironmentObject private var app: AppModel
    @State private var data: RecurringTransfers?
    private var categories: [CategoryList.Category] { app.categories }
    @State private var open: RecurringTransfers.Transfer?
    /// The transfers Needs a look is asking about.
    @State private var waiting: [Review.Item] = []
    @State private var error: String?

    var body: some View {
        ProfilePage {
            ProfileHeading(title: "Recurring transfers")
            if let data = data {
                if data.transfers.isEmpty && data.asking == 0 {
                    APEmptyState(title: "None yet",
                                 line: "When the same amount goes out on a schedule, Pearl asks if it repeats.",
                                 top: 120) { IconBubble(symbol: "arrow.triangle.2.circlepath") }
                } else {
                    if !data.transfers.isEmpty { RTSummary(monthly: data.monthly, count: data.count).padding(.top, 8) }
                    RTList(transfers: data.transfers) { open = $0 }
                    if data.asking > 0 { RTWaiting(waiting: waiting, asking: data.asking) }
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .navigationDestination(isPresented: Binding(get: { open != nil }, set: { if !$0 { open = nil } })) {
            if let t = open {
                RecurringTransferPage(transfer: t, categories: categories, stopped: { undo in
                    open = nil
                    // RT-02 v2: "No longer recurring", with Undo (A+).
                    app.say("No longer recurring", undo: undo)
                    app.changed()
                })
            }
        }
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

/// "A month, on average" over the 40 pt amount, and "3 recurring" as a pill.
private struct RTSummary: View {
    let monthly: Double
    let count: Int

    var body: some View {
        APCard {
            HStack(alignment: .bottom) {
                VStack(alignment: .leading, spacing: 0) {
                    Text("A month, on average").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    Text(Format.whole(monthly))
                        .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle)).tracking(-0.8)
                        .monospacedDigit().foregroundColor(Pearl.ink).pearlAmountFit()
                }
                Spacer(minLength: 8)
                StatusPill(text: "\(count) recurring", tone: .neutral)
            }
            .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 16)
        }
        .accessibilityElement(children: .combine)
    }
}

/// RECURRING: one payment row each; the whole row opens it.
private struct RTList: View {
    let transfers: [RecurringTransfers.Transfer]
    let open: (RecurringTransfers.Transfer) -> Void

    var body: some View {
        if !transfers.isEmpty {
            ProfileSection("Recurring")
            APCard {
                ForEach(Array(transfers.enumerated()), id: \.element.id) { i, t in
                    if i > 0 { APSeparator() }
                    Button { open(t) } label: {
                        ProfileRow(initials: t.title, title: t.title, sub: RTWords.line(t)) {
                            Text(RTWords.amount(t)).font(Nacre.headline).monospacedDigit()
                                .foregroundColor(RTWords.moves(t.category) ? Pearl.muted : Pearl.moneyOut)
                                .pearlAmountFit().fixedSize()
                        }
                    }
                    .buttonStyle(.plain)
                }
            }
        }
    }
}

/// NEW, IN NEEDS A LOOK: each one waiting, "Recurring?" at the end.
private struct RTWaiting: View {
    let waiting: [Review.Item]
    let asking: Int

    var body: some View {
        ProfileSection("New, in Needs a look")
        APCard {
            ForEach(Array(waiting.enumerated()), id: \.element.key) { i, item in
                if i > 0 { APSeparator() }
                NavigationLink { ReviewView() } label: {
                    ProfileRow(initials: item.txn.name, title: item.txn.name,
                               sub: "\u{21C4} \(Format.amount(abs(item.txn.amount)))",
                               pill: StatusPill(text: "Recurring?", tone: .needsALook), pillTrailing: true)
                }
                .buttonStyle(.plain)
            }
            if waiting.isEmpty {
                NavigationLink { ReviewView() } label: {
                    ProfileRow(symbol: "arrow.triangle.2.circlepath",
                               title: asking == 1 ? "1 transfer to answer" : "\(asking) transfers to answer",
                               pill: StatusPill(text: "Recurring?", tone: .needsALook), pillTrailing: true)
                }
                .buttonStyle(.plain)
            }
        }
    }
}

/// The words a recurring transfer's row and page share.
enum RTWords {
    /// What it is, by the category it sorts to (RT-02 v2's options).
    static let kinds: [(category: String, label: String, line: String)] = [
        ("Rent & Housing", "Rent", "Spending on rent"),
        ("Saved", "Into savings", "Counts as saved"),
        ("Transfers", "My other account", "Doesn’t count"),
    ]

    /// Into savings or another of her accounts: muted ⇄, no sign.
    static func moves(_ category: String) -> Bool { category == "Saved" || category == "Transfers" }

    static func amount(_ t: RecurringTransfers.Transfer) -> String {
        moves(t.category) ? "\u{21C4} " + Format.amount(t.amount) : "\u{2212}" + Format.amount(t.amount)
    }

    /// "Rent · monthly", "Every payday".
    static func line(_ t: RecurringTransfers.Transfer) -> String {
        let how = t.cadence == "payday" ? "every payday" : cadence(t.cadence).lowercased()
        let what = kinds.first { $0.category == t.category }?.label ?? t.what ?? t.category
        return what == t.title ? how.capitalizedFirst : "\(what) · \(how)"
    }
}

// MARK: - RT-02 v2 (G5b-RecurringOne)

/// One recurring transfer, pushed: its face, name and amount; WHAT IT IS,
/// where a tap answers at once ("Now Into savings", with Undo); the ones so
/// far as months (a month opens that transfer); and "Stop treating it as
/// recurring", the one red row ("No longer recurring", with Undo).
@MainActor
struct RecurringTransferPage: View {
    @EnvironmentObject private var app: AppModel
    let transfer: RecurringTransfers.Transfer
    let categories: [CategoryList.Category]
    /// Stopped: back to the list, which says so with this Undo.
    let stopped: ((() async throws -> Void)?) -> Void

    @State private var category: String?
    @State private var choosing = false
    @State private var busy = false
    @State private var error: String?
    @State private var opening: String?

    private var now: String { category ?? transfer.category }
    private var known: Bool { RTWords.kinds.contains { $0.category == now } }

    /// The ones so far, oldest first.
    private var rows: [RecurringTransfers.Transfer.Row] { Array((transfer.transactions ?? []).prefix(12).reversed()) }

    var body: some View {
        ProfilePage {
            APHero(face: transfer.title, name: title,
                   amount: RTWords.moves(now) ? "\u{21C4} " + Format.amount(transfer.amount) : Format.amount(transfer.amount),
                   amountTone: RTWords.moves(now) ? Pearl.muted : Pearl.moneyOut, lines: [line])
            RTKinds(now: now, known: known) { k in
                if let k = k { change(to: k) } else { choosing = true }
            }
            .disabled(busy)
            ProfileNote(transfer.count == 1 ? "Moves it and the ones to come." : "Moves all \(transfer.count) and the ones to come.")
            if !rows.isEmpty {
                ProfileSection(transfer.count == 1 ? "The one so far" : "The \(transfer.count) so far")
                RTMonths(rows: rows) { opening = $0 }
            }
            APCard {
                Button { Task { await stop() } } label: {
                    ProfileRow(symbol: "xmark", title: "Stop treating it as recurring",
                               sub: transfer.count == 1 ? "It keeps its category" : "The \(transfer.count) keep their category",
                               tone: Pearl.danger, chevron: false)
                }
                .buttonStyle(.plain)
                .disabled(busy)
            }
            .padding(.top, 16)
            if let error = error { APErrorLine(text: error).padding(.top, 8) }
        }
        .sheet(isPresented: $choosing) {
            CategorySheet(name: transfer.title, amount: Format.amount(transfer.amount), tone: Pearl.ink,
                          categories: categories.filter { !["Income", "Transfers", "Saved", "Rent & Housing"].contains($0.name) },
                          current: known ? "" : now, spendingOnly: true) { name, _ in
                choosing = false
                change(to: name)
            }
        }
        .navigationDestination(isPresented: Binding(get: { opening != nil }, set: { if !$0 { opening = nil } })) {
            if let id = opening { TransactionByID(id: id, categories: categories) }
        }
    }

    /// "Rent to M. Papas".
    private var title: String {
        let what = RTWords.kinds.first { $0.category == now }?.label ?? transfer.what ?? now
        return transfer.name == "Transfer" || transfer.name == what ? what : "\(what) to \(transfer.name)"
    }

    /// "every month, around the 1st · TD Chequing".
    private var line: String {
        [transfer.when ?? cadence(transfer.cadence).lowercased(), transfer.account.flatMap { $0.isEmpty ? nil : $0 }]
            .compactMap { $0 }.joined(separator: " · ")
    }

    /// A tap changes it at once; Undo puts the one it was back.
    private func change(to new: String) {
        guard new != now, !busy else { return }
        busy = true
        let id = transfer.ruleId  // plain: APIClient encodes it (TEST-33)
        let was = now
        let api = app.api
        Task {
            defer { busy = false }
            do {
                let _: OK = try await api.put("api/rules/\(id)", ["category": new])
                category = new
                error = nil
                let label = RTWords.kinds.first { $0.category == new }?.label ?? new
                app.say("Now \(label)", undo: {
                    let _: OK = try await api.put("api/rules/\(id)", ["category": was])
                    await MainActor.run { category = was }
                })
                app.changed()
            } catch {
                self.error = app.handle(error)
            }
        }
    }

    private func stop() async {
        busy = true
        defer { busy = false }
        do {
            let reply: RuleReply = try await app.api.delete("api/recurring-transfers/\(transfer.id)")
            let api = app.api
            stopped(reply.undo.map { payload in
                {
                    guard let body = payload.any as? [String: Any] else { return }
                    let _: OK = try await api.post("api/transactions/undo", body)
                }
            })
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// WHAT IT IS: Rent, Into savings, My other account, Something else.
private struct RTKinds: View {
    let now: String
    let known: Bool
    /// A kind's category, or nil for Something else.
    let pick: (String?) -> Void

    var body: some View {
        ProfileSection("What it is")
        APCard {
            ForEach(Array(RTWords.kinds.enumerated()), id: \.offset) { i, k in
                if i > 0 { APSeparator(afterFace: false) }
                APChoiceRow(title: k.label, sub: k.line, selected: now == k.category) { pick(k.category) }
            }
            APSeparator(afterFace: false)
            APChoiceRow(title: "Something else", sub: known ? "Pick a category" : now, selected: !known) { pick(nil) }
        }
    }
}

/// THE 9 SO FAR: one chip per month, six to a line; a chip opens that transfer.
private struct RTMonths: View {
    let rows: [RecurringTransfers.Transfer.Row]
    let open: (String) -> Void

    var body: some View {
        APCard {
            LazyVGrid(columns: Array(repeating: GridItem(.flexible(), spacing: 8), count: 6), spacing: 8) {
                ForEach(rows) { r in
                    Button { open(r.id) } label: {
                        Text(String(Format.monthName(String(r.date.prefix(7))).prefix(3)))
                            .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                            .frame(maxWidth: .infinity, minHeight: 34)
                            .background(Capsule().fill(APlus.chip))
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(Format.short(r.date)), \(Format.amount(r.amount))")
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 14)
        }
    }
}
