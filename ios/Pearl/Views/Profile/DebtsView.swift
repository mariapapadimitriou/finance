import SwiftUI

// Debts (THL-128, THL-49, THL-300; Pearl iOS Handoff File, Pearl app page,
// "Debts"): DB-01 every balance carried on a card or a loan, with the rate
// and minimum, and DB-02 adding the ones the bank doesn't share. Balances
// aren't taken out of Allowance; minimums count as bills (finance/debts.py).

struct DebtList: Decodable {
    let debts: [Debt]
    let count: Int
    let total: Double
    let minimums: Double?

    struct Debt: Decodable, Identifiable, Hashable {
        let accountId: String
        let name: String
        /// "card", "line_of_credit", "loan", "student_loan", "mortgage".
        let kind: String
        let balance: Double
        let rate: Double?
        let minimum: Double?
        let dueDay: Int?
        var id: String { accountId }

        enum CodingKeys: String, CodingKey {
            case name, kind, balance, rate, minimum
            case accountId = "account_id"
            case dueDay = "due_day"
        }

        var isCard: Bool { kind == "card" || kind == "line_of_credit" }

        var kindWord: String {
            ["card": "Credit card", "line_of_credit": "Line of credit", "mortgage": "Mortgage"][kind] ?? "Loan"
        }

        /// "19.99% · min. $25 · due the 14th", or the kind when nothing's added.
        var line: String {
            let parts = [rate.map { "\(Self.percent($0))%" },
                         minimum.map { "min. \(Format.whole($0))" + (dueDay == nil && !isCard ? " a month" : "") },
                         dueDay.map { "due the \(ordinal($0))" }].compactMap { $0 }
            return parts.isEmpty ? kindWord : parts.joined(separator: " · ")
        }

        /// What's missing, as the row's pill.
        var action: String? {
            if rate == nil && minimum == nil { return "Add the details" }
            if rate == nil { return "Add the rate" }
            if minimum == nil { return "Add the minimum" }
            return nil
        }

        static func percent(_ v: Double) -> String {
            v == v.rounded() ? String(Int(v)) : String(format: "%g", v)
        }
    }
}

// MARK: - DB-01 Debts

@MainActor
struct DebtsView: View {
    @EnvironmentObject private var app: AppModel
    @State private var data: DebtList?
    @State private var editing: DebtList.Debt?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            ProfileHeading(title: "Debts", intro: lead)
            if let data = data {
                if data.debts.isEmpty {
                    ProfileNote("No card balance carried from an earlier month and no loans on your linked accounts. Card purchases this month are counted as spending.")
                        .padding(.top, 8)
                } else {
                    section("Cards", data.debts.filter(\.isCard))
                    section("Loans", data.debts.filter { !$0.isCard })
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        }
        .refreshable { await load() }
        .task(id: app.version) { await load() }
        .sheet(item: $editing) { d in
            DebtDetailsSheet(debt: d) { reply in
                data = reply
                app.changed()
            }
            .presentationDetents([.medium, .large])
            .presentationDragIndicator(.visible)
        }
    }

    @ViewBuilder
    private func section(_ title: String, _ debts: [DebtList.Debt]) -> some View {
        if !debts.isEmpty {
            ProfileSection(title)
            GlassCard {
                ForEach(Array(debts.enumerated()), id: \.element.id) { i, d in
                    if i > 0 { RowSeparator(inset: 62) }
                    Button { editing = d } label: {
                        ProfileRow(initials: d.name, title: d.name, sub: d.line,
                                   pill: d.action.map { StatusPill(text: $0, tone: .needsALook) }) {
                            Text(Format.amount(d.balance)).font(Nacre.body).foregroundColor(Pearl.ink)
                                .monospacedDigit().lineLimit(1).fixedSize()
                        }
                    }
                    .buttonStyle(.plain)
                    .accessibilityHint(d.action ?? "Change the details")
                }
            }
        }
    }

    /// "You owe $9,408.95. Minimums this month: $345. …"
    private var lead: String? {
        guard let data = data, !data.debts.isEmpty else { return nil }
        let minimums = data.minimums.map { "Minimums this month: \(Format.whole($0))." } ?? "Add the minimums and Pearl counts them with your bills."
        return "You owe \(Format.amount(data.total)). \(minimums) Balances aren’t taken out of your Allowance."
    }

    private func load() async {
        do {
            data = try await app.api.get("api/debts")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - DB-02 Add the details

/// The rate, minimum and due day from her statement. Clearing a field
/// clears it on the server.
@MainActor
struct DebtDetailsSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let debt: DebtList.Debt
    let saved: (DebtList) -> Void

    @State private var rate = ""
    @State private var minimum = ""
    @State private var due = ""
    @State private var busy = false
    @State private var error: String?

    private var adding: Bool { debt.rate == nil && debt.minimum == nil }

    var body: some View {
        SheetFrame(title: debt.name, subtitle: subtitle, symbol: "creditcard",
                   heading: adding ? "Add the details" : "Change the details", close: { dismiss() }) {
            VStack(spacing: 0) {
                FieldRow(label: "Interest rate", text: $rate, prompt: "5.7%").keyboardType(.decimalPad)
                RowSeparator()
                FieldRow(label: "Minimum payment a month", text: $minimum, prompt: "$120").keyboardType(.decimalPad)
                RowSeparator()
                FieldRow(label: "Day it’s due (optional)", text: $due, prompt: "14").keyboardType(.numberPad)
            }
            .sheetCard()
            if let error = error { Hint(text: error) }
        } actions: {
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy)
            Button("Cancel") { dismiss() }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
        }
        .onAppear {
            rate = debt.rate.map(DebtList.Debt.percent) ?? ""
            minimum = debt.minimum.map { String(format: "%.2f", $0) } ?? ""
            due = debt.dueDay.map(String.init) ?? ""
        }
    }

    private var subtitle: String {
        let owed = "\(Format.amount(debt.balance)) owing"
        guard debt.rate == nil else { return owed }
        return owed + (debt.isCard ? " · your bank doesn’t share the rate" : " · your lender doesn’t share the rate")
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let reply: DebtList = try await app.api.put("api/debts/\(debt.accountId)",
                                                        ["rate": rate, "minimum": minimum, "due_day": due])
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}
