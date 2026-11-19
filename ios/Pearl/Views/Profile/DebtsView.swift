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

// MARK: - DB-01 Debts (G5b-Debts)

/// A+ (REDESIGN-12): "You owe" over the 40 pt total with the month's
/// minimums, then CARDS and LOANS as rows (a missing rate says "Add the
/// details" in link), one line that balances don't come off her Allowance.
@MainActor
struct DebtsView: View {
    @EnvironmentObject private var app: AppModel
    @State private var data: DebtList?
    @State private var editing: DebtList.Debt?
    @State private var error: String?

    var body: some View {
        ProfilePage {
            ProfileHeading(title: "Debts")
            if let data = data {
                if data.debts.isEmpty {
                    APEmptyState(title: "Nothing owing",
                                 line: "No card balance carried over and no loans. This month’s card purchases count as spending.",
                                 top: 120) { IconBubble(symbol: "creditcard", kind: .good) }
                } else {
                    DebtSummary(total: data.total, minimums: data.minimums).padding(.top, 8)
                    DebtSection(title: "Cards", debts: data.debts.filter(\.isCard)) { editing = $0 }
                    DebtSection(title: "Loans", debts: data.debts.filter { !$0.isCard }) { editing = $0 }
                    ProfileNote("Balances don’t come off your Allowance.").padding(.top, 6)
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .sheet(item: $editing) { d in
            DebtDetailsSheet(debt: d) { reply in
                data = reply
                app.say("Details saved")
                app.changed()
            }
        }
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

/// "You owe" and the total; "Minimums this month · $145 · with your bills".
private struct DebtSummary: View {
    let total: Double
    let minimums: Double?

    var body: some View {
        APCard {
            VStack(alignment: .leading, spacing: 0) {
                Text("You owe").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                Text(Format.amount(total))
                    .font(.custom("Fraunces-SemiBold", size: 40, relativeTo: .largeTitle)).tracking(-0.8)
                    .monospacedDigit().foregroundColor(Pearl.ink).pearlAmountFit()
            }
            .padding(.horizontal, 16).padding(.top, 14).padding(.bottom, 6)
            .accessibilityElement(children: .combine)
            if let minimums = minimums {
                APKeyValueRow(key: "Minimums this month", value: "\(Format.whole(minimums)) · with your bills")
            }
        }
    }
}

private struct DebtSection: View {
    let title: String
    let debts: [DebtList.Debt]
    let open: (DebtList.Debt) -> Void

    var body: some View {
        if !debts.isEmpty {
            ProfileSection(title)
            APCard {
                ForEach(Array(debts.enumerated()), id: \.element.id) { i, d in
                    if i > 0 { APSeparator() }
                    Button { open(d) } label: { DebtRow(debt: d) }
                        .buttonStyle(.plain)
                        .accessibilityHint(d.action ?? "Change the details")
                }
            }
        }
    }
}

/// Face, name over its line (or "Add the details" in link), the balance, ›.
private struct DebtRow: View {
    let debt: DebtList.Debt

    var body: some View {
        HStack(spacing: 12) {
            RowAvatar(name: debt.name)
            VStack(alignment: .leading, spacing: 2) {
                Text(debt.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(2)
                Text(debt.action ?? debt.line).font(Nacre.subheadline)
                    .foregroundColor(debt.action == nil ? Pearl.muted : Pearl.link).lineLimit(2)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            Text(Format.amount(debt.balance)).font(Nacre.headline).monospacedDigit()
                .foregroundColor(Pearl.ink).pearlAmountFit().fixedSize()
            APChevron()
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }
}

// MARK: - DB-02 Add the details (G5b-DebtEdit)

/// The rate, minimum and due day from her statement, as wells. Clearing a
/// field clears it on the server. Couldn't save: the danger line, Try again
/// and Cancel.
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
        VStack(alignment: .leading, spacing: 0) {
            APSheetTitle(title: adding ? "Add the details" : "Change the details") { dismiss() }
                .padding(.top, 14)
            ScrollView {
                VStack(alignment: .leading, spacing: 6) {
                    APWho(face: debt.name, name: debt.name, line: subtitle).padding(.top, 14)
                    DebtWell(label: "Interest rate", text: $rate, placeholder: "0", suffix: "%", keyboard: .decimalPad)
                        .padding(.top, 10)
                    DebtWell(label: "Minimum payment a month", text: $minimum, placeholder: "0", prefix: "$",
                             keyboard: .decimalPad)
                    DebtWell(label: "Day it’s due (optional)", text: $due, placeholder: "Day of the month",
                             keyboard: .numberPad)
                    if let error = error { APErrorLine(text: error).padding(.top, 8) }
                }
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 12) {
                Button(error == nil ? "Save" : "Try again") { Task { await save() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
                if error != nil {
                    Button("Cancel") { dismiss() }.buttonStyle(APSecondaryButtonStyle())
                }
            }
            .padding(.top, 12).padding(.bottom, 8)
        }
        .padding(.horizontal, 16)
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
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
            if app.handle(error) != nil { self.error = "Couldn’t save. Nothing changed. Try again." }
        }
    }
}

/// A labelled well (REDESIGN-09) with a `$` before or a `%` after, in `muted`.
private struct DebtWell: View {
    let label: String
    @Binding var text: String
    var placeholder = ""
    var prefix: String? = nil
    var suffix: String? = nil
    var keyboard: UIKeyboardType = .default

    @FocusState private var focused: Bool

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(label).font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            HStack(spacing: 6) {
                if let prefix = prefix { Text(prefix).foregroundColor(Pearl.muted) }
                TextField("", text: $text, prompt: Text(placeholder).foregroundColor(Pearl.muted))
                    .foregroundColor(Pearl.ink).tint(Pearl.action)
                    .keyboardType(keyboard)
                    .focused($focused)
                    .accessibilityLabel(label)
                if let suffix = suffix { Text(suffix).foregroundColor(Pearl.muted) }
            }
            .font(Nacre.body)
            .padding(.horizontal, 14)
            .frame(minHeight: 44)
            .wellStyle(focused: focused)
            .contentShape(Rectangle())
            .onTapGesture { focused = true }
        }
        .padding(.top, 8)
    }
}
