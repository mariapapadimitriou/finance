import SwiftUI

// A+ Owed to you (AP-Owed) and its person page (AP-OwedPerson), REDESIGN-04
// (THL-291, THL-289, THL-181). Reached from Home's "2 people owe you" and
// from a split purchase's "See who else owes you". Same sections as S-14
// (Owes you, Not settled with its line, You owe, Paid back this month); the
// total sits in the header. A person row opens the person page (new); a
// purchase there opens that person's options sheet (S-40) with "Open
// Loblaws" under it.

/// A person's option picked away from the purchase (Owed to you), run by
/// the purchase's page once it has loaded.
struct StartChoice {
    let name: String
    let choice: PersonChoice
}

// MARK: - S-14 Owed to you

@MainActor
struct OwedView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State private var owed: OwedOverview?
    @State private var error: String?
    @State private var person: String?

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 0) {
                OwedTitle(title: "Owed to you")
                if let owed = owed {
                    OwedHeader(owed: owed)
                    OwedSections(owed: owed) { person = $0 }
                } else if let error = error {
                    Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution).padding(.top, 24)
                } else {
                    ProgressView().frame(maxWidth: .infinity).padding(.vertical, 40)
                }
            }
            .padding(.horizontal, Pearl.gutter).padding(.bottom, 32)
        }
        .nacreScreen()
        .apPushedPage { dismiss() }
        .navigationDestination(isPresented: Binding(get: { person != nil }, set: { if !$0 { person = nil } })) {
            if let name = person { OwedPersonView(name: name) }
        }
        .task { await load() }
        .reloads { await load() }
    }

    private func load() async {
        do {
            owed = try await app.api.get("api/owed")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}

extension View {
    /// A pushed A+ page: Back is the 44 pt glass circle, the bar see-through,
    /// the title drawn by the page itself in Fraunces 34.
    func apPushedPage(back: @escaping () -> Void) -> some View {
        navigationBarBackButtonHidden(true)
            .toolbar {
                ToolbarItem(placement: .navigationBarLeading) { APBackButton(action: back) }
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

/// "$70.10" in Fraunces 44/600 over "from 2 people".
private struct OwedHeader: View {
    let owed: OwedOverview

    var body: some View {
        VStack(alignment: .leading, spacing: 2) {
            Text(Format.amount(owed.total))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)
                .foregroundColor(Pearl.ink).pearlAmountFit()
            Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted)
        }
        .padding(.leading, 4).padding(.top, 10)
        .accessibilityElement(children: .combine)
    }

    /// "from 2 people"; S-14u0 "1 split not settled"; or nobody.
    private var line: String {
        let n = owed.notSettled?.count ?? 0
        if owed.people == 0 {
            return n == 0 ? "Nobody owes you anything" : "\(n) split\(n == 1 ? "" : "s") not settled"
        }
        return "from \(owed.people) \(owed.people == 1 ? "person" : "people")"
    }
}

private struct OwedSections: View {
    @EnvironmentObject private var app: AppModel
    let owed: OwedOverview
    let openPerson: (String) -> Void

    var body: some View {
        VStack(alignment: .leading, spacing: 0) {
            if !owed.owesYou.isEmpty {
                label("Owes you")
                APCard {
                    ForEach(Array(owed.owesYou.enumerated()), id: \.element.id) { i, r in
                        if i > 0 { APSeparator() }
                        Button { openPerson(r.name) } label: {
                            OwedRow(name: r.name, line: OwedSections.line(r), amount: Format.amount(r.total))
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Opens what \(r.name) owes you for")
                    }
                }
            }
            if let unsettled = owed.notSettled, !unsettled.isEmpty {
                label("Not settled")
                APCard {
                    ForEach(Array(unsettled.enumerated()), id: \.element.id) { i, n in
                        if i > 0 { APSeparator() }
                        NavigationLink {
                            TransactionByID(id: n.chargeId, categories: app.categories)
                        } label: { UnsettledRow(n: n) }
                        .buttonStyle(.plain)
                    }
                }
                Text("Not in the total until settled.")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 4).padding(.top, 8)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if !owed.youOwe.isEmpty {
                label("You owe")
                APCard {
                    ForEach(Array(owed.youOwe.enumerated()), id: \.element.id) { i, r in
                        if i > 0 { APSeparator() }
                        OwedRow(name: r.name, line: "Overpaid for " + (r.items.first?.merchant ?? "a purchase"),
                                amount: Format.amount(r.total))
                    }
                }
            }
            if !owed.paidBack.isEmpty {
                label("Paid back this month")
                APCard {
                    ForEach(Array(owed.paidBack.enumerated()), id: \.offset) { i, b in
                        if i > 0 { APSeparator() }
                        PaidBackRow(b: b)
                    }
                }
            }
        }
    }

    private func label(_ text: String) -> some View {
        APSectionLabel(text: text).padding(.top, 24).padding(.bottom, 8)
    }

    /// "Loblaws · Nov 11", or "2 purchases".
    static func line(_ r: OwedOverview.Row) -> String {
        if r.items.count == 1, let i = r.items.first {
            return [i.merchant, Format.short(i.date)].compactMap { $0 }.joined(separator: " · ")
        }
        return "\(r.items.count) purchases"
    }
}

/// A+ `.row`: face 40, name over line, the amount on the right edge.
struct OwedRow: View {
    let name: String
    let line: String
    let amount: String
    var tone: Color = Pearl.ink
    var note: String? = nil

    var body: some View {
        HStack(spacing: 12) {
            APFace(name: name)
            VStack(alignment: .leading, spacing: 2) {
                Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                Text(line).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(2)
                    .fixedSize(horizontal: false, vertical: true)
                if let note = note {
                    Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(amount).font(Nacre.headline).monospacedDigit().foregroundColor(tone)
                .pearlAmountFit().fixedSize()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
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

/// "Jo" over "e-Transfer · Nov 16 · Loblaws", +$30.00 in green.
private struct PaidBackRow: View {
    let b: OwedOverview.Back

    var body: some View {
        // SPLIT-14: "PayPal" or "Another app"; SPLIT-15: one cash payment,
        // with what a deposit holds; SPLIT-19 (S-11c): several purchases.
        let how = b.cash == true ? "Cash" : b.app == true ? (b.appName ?? "Another app") : nil
        let line = (b.paidBack.map { [how, Format.short(b.date), "paid back \(Format.andList($0))"] }
                    ?? [how, Format.short(b.date), b.merchant])
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
        if let owed: OwedOverview = try? await app.api.get("api/owed") {
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
