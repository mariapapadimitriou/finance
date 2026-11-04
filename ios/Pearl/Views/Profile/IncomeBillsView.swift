import SwiftUI

// Profile › Income and bills (THL-127, THL-45, THL-198; Pearl iOS Handoff
// File, Pearl app page, "Income and bills"):
//
// IB-01  what comes in and the regular bills set aside before Allowance,
//        each one tapped to change it (the setup sheets, O-10a to O-10d),
//        and "Check again", which runs the setup check (O-10) over the page
// IB-02  what Pearl found in her transactions and she hasn't confirmed:
//        pay to say yes or no to, and bills to confirm together
// IB-03  her own amount a month, instead of Pearl's estimate
//
// Every write returns the whole page again (finance/income_bills_api.py),
// so nothing here adds anything up. A bill's tick saves at once once she has
// confirmed her bills; before that the ticks wait for "Confirm n bills".

@MainActor
struct IncomeBillsView: View {
    @EnvironmentObject private var app: AppModel
    @State private var data: IncomeBills?
    /// IB-02: her ticks on found bills, until she confirms them.
    @State private var ticked: [String: Bool] = [:]
    @State private var sheet: Sheet?
    @State private var rent: IncomeBills.RentQuestion?
    @State private var checking = false
    @State private var toast: (text: String, undo: (() -> Void)?)?
    @State private var busy = false
    @State private var error: String?

    enum Sheet: Identifiable {
        case candidate(IncomeBills.Candidate), pay(IncomeBills.Pay), addPay
        case bill(IncomeBills.Bill), addBill
        case ask(IncomeBills.Ask), expected

        var id: String {
            switch self {
            case .candidate(let c): return "c" + c.id
            case .pay(let p): return "p" + p.id
            case .addPay: return "add-pay"
            case .bill(let b): return "b" + b.id
            case .addBill: return "add-bill"
            case .ask(let a): return "a" + a.id
            case .expected: return "expected"
            }
        }
    }

    var body: some View {
        ProfilePage {
            ProfileHeading(title: "Income and bills", intro: lead)
            if let data = data {
                content(data)
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            if data != nil {
                if confirming {
                    Button(confirmLabel) { Task { await confirmBills() } }
                        .buttonStyle(NacreButtonStyle(busy: busy))
                        .disabled(busy)
                } else {
                    Button("Check again") { checking = true }
                        .buttonStyle(SecondaryButtonStyle())
                }
            }
        }
        .overlay(alignment: .top) {
            if let toast = toast {
                UndoToast(text: toast.text, undo: toast.undo) { withAnimation { self.toast = nil } }
            }
        }
        .refreshable { await load() }
        .task(id: app.version) { await load() }
        .sheet(item: $sheet) { which in
            sheetView(which)
                .presentationDetents([.large])
                .presentationDragIndicator(.visible)
        }
        .confirmationDialog(rent.map { "Are your e-Transfers to \($0.recipient ?? "them") your rent?" } ?? "",
                            isPresented: Binding(get: { rent != nil }, set: { if !$0 { rent = nil } }),
                            titleVisibility: .visible, presenting: rent) { q in
            Button("Yes, it’s my rent") { Task { await answerRent(q) } }
            Button("No", role: .cancel) {}
        } message: { q in
            Text("They’ll count as Rent from now on, and \(Format.whole(q.amount)) a month is set aside.")
        }
        .fullScreenCover(isPresented: $checking) {
            NavigationStack {
                PayAndBillsView(path: .constant([])) {
                    checking = false
                    Task { await load() }
                }
                .toolbar {
                    ToolbarItem(placement: .navigationBarLeading) {
                        CloseButton { checking = false }
                    }
                }
            }
        }
    }

    // MARK: The page

    @ViewBuilder
    private func content(_ data: IncomeBills) -> some View {
        MoneySection(title: "Income") {
            if let own = data.expected?.amount, own > 0 {
                IncomeLine(name: "Your own amount",
                           sub: data.expected?.varies == true ? "A month after tax · it changes" : "A month after tax",
                           amount: own) { sheet = .expected }
                RowSeparator(inset: 64)
            }
            ForEach(data.pays) { p in
                IncomeLine(name: p.name, sub: cadence(p.cadence), amount: p.amount) { sheet = .pay(p) }
                RowSeparator(inset: 64)
            }
            ForEach(data.candidates) { c in
                QuestionLine(name: c.name, sub: "Found · \(cadence(c.cadence).lowercased())",
                             question: "Your pay?") { sheet = .candidate(c) }
                    .accessibilityHint("Pearl found this in your transactions. Say whether it’s your pay.")
                RowSeparator(inset: 64)
            }
            ForEach(data.asks ?? []) { a in
                AskLine(ask: a) { sheet = .ask(a) }
                RowSeparator(inset: 64)
            }
            if noIncome(data) {
                if let estimate = data.expected?.estimate, estimate > 0 {
                    IncomeLine(name: "Pearl’s estimate", sub: "The average of your last 3 months",
                               amount: estimate) { sheet = .expected }
                } else {
                    QuestionLine(name: "No income confirmed yet", sub: "Tell us what comes in each month",
                                 question: "Add") { sheet = .expected }
                }
                RowSeparator(inset: 64)
            }
            AddLine(title: "Add other income") { sheet = .addPay }
            if !noIncome(data), !((data.expected?.amount ?? 0) > 0) {
                RowSeparator(inset: 64)
                AddLine(title: "Set my own amount") { sheet = .expected }
                    .accessibilityHint("Use what you expect each month instead of what Pearl works out")
            }
        }

        MoneySection(title: "Regular bills") {
            if let q = data.rentQuestion {
                QuestionLine(name: "e-Transfers to \(q.recipient ?? "someone")",
                             sub: "\(Format.whole(q.amount)) · monthly" + (q.day.map { " · around the \(ordinal($0))" } ?? ""),
                             question: "Your rent?") { rent = q }
                RowSeparator(inset: 52)
            }
            ForEach(regular(data)) { bill in
                billRow(bill)
                RowSeparator(inset: 52)
            }
            AddLine(title: "Add a bill") { sheet = .addBill }
        }

        let subs = data.bills.filter { subscriptionCategories.contains($0.category ?? "") }
        if !subs.isEmpty {
            MoneySection(title: "Subscriptions", note: "Untick any you don’t want set aside.") {
                ForEach(Array(subs.enumerated()), id: \.element.id) { i, bill in
                    if i > 0 { RowSeparator(inset: 52) }
                    billRow(bill)
                }
            }
        }

        if !confirming {
            ProfileSection("Something changed?")
            ProfileNote("A new job, a new place, a bill that stopped. Check again with your latest transactions.")
        }
    }

    private func billRow(_ bill: IncomeBills.Bill) -> some View {
        let on = isOn(bill)
        return BillLine(bill: bill, on: on,
                        toggle: { Task { await tick(bill, !on) } },
                        edit: { sheet = .bill(bill) })
    }

    @ViewBuilder
    private func sheetView(_ which: Sheet) -> some View {
        switch which {
        case .candidate(let c):
            PaySheet(title: c.name, subtitle: "Your pay · \(cadence(c.cadence))", payer: c.payer, payId: nil,
                     amount: c.amount, cadence: c.cadence, next: c.next) { reply in
                if let reply = reply { saved(reply) } else { Task { await notPay(c) } }
            }
        case .pay(let p):
            PaySheet(title: p.name, subtitle: "Your pay · \(cadence(p.cadence))", payer: p.payer, payId: p.id,
                     amount: p.amount, cadence: p.cadence, next: p.next, account: p.account, varies: p.varies ?? false) { reply in
                if let reply = reply { saved(reply) }
            }
        case .addPay:
            PaySheet(title: "Add income", subtitle: "A second job, freelance work, support payments",
                     payer: nil, payId: nil, amount: nil, cadence: "monthly", next: nil) { reply in
                if let reply = reply { saved(reply) }
            }
        case .bill(let b):
            BillSheet(bill: b, counted: nil) { reply in
                if let reply = reply { saved(reply) }
            }
        case .addBill:
            BillSheet(bill: nil, counted: nil) { reply in
                if let reply = reply { saved(reply) }
            }
        case .ask(let a) where a.kind == "joint":
            WhosePaySheet(ask: a) { reply in saved(reply) }
        case .ask(let a):
            WhatIsItSheet(ask: a, bills: data?.bills ?? []) { reply in saved(reply) }
        case .expected:
            ExpectedIncomeSheet(expected: data?.expected, hasPay: !(data?.pays.isEmpty ?? true)) { reply in
                saved(reply)
            }
        }
    }

    // MARK: Words

    /// IB-02 while there's something found to confirm; otherwise the totals.
    private var lead: String? {
        guard let data = data else { return nil }
        if confirming || !data.candidates.isEmpty {
            let pay = data.candidates.isEmpty ? nil : (data.candidates.count == 1 ? "new pay" : "\(data.candidates.count) new pays")
            let n = confirming ? found(data).count : 0
            let bills = n == 0 ? nil : (n == 1 ? "a bill" : "\(n) bills")
            let what = [pay, bills].compactMap { $0 }.joined(separator: " and ")
            return "Pearl found \(what) in your transactions. Say which are right."
        }
        guard let income = data.totals?.income, income > 0 else {
            return "Add your income so your Allowance is right."
        }
        let bills = data.totals?.bills ?? 0
        return "\(Format.whole(income)) a month in · \(Format.whole(bills)) in bills set aside before your Allowance."
    }

    /// Found, not confirmed (IB-02): she hasn't confirmed her bills yet, and
    /// Pearl found some.
    private var confirming: Bool {
        guard let data = data else { return false }
        return data.checked?.bills == nil && !found(data).isEmpty
    }

    private func found(_ data: IncomeBills) -> [IncomeBills.Bill] {
        data.bills.filter { $0.source != "added" && $0.ticked == true }
    }

    private var confirmLabel: String {
        let n = (data?.bills ?? []).filter { $0.source != "added" && isOn($0) }.count
        return n == 0 ? "Confirm: no regular bills" : n == 1 ? "Confirm 1 bill" : "Confirm \(n) bills"
    }

    private func isOn(_ bill: IncomeBills.Bill) -> Bool {
        ticked[bill.key] ?? bill.ticked ?? true
    }

    private func noIncome(_ data: IncomeBills) -> Bool {
        data.pays.isEmpty && data.candidates.isEmpty && (data.asks ?? []).isEmpty
            && !((data.expected?.amount ?? 0) > 0)
    }

    private func regular(_ data: IncomeBills) -> [IncomeBills.Bill] {
        data.bills.filter { !subscriptionCategories.contains($0.category ?? "") }
    }

    // MARK: Calls

    private func load() async {
        do {
            data = try await app.api.get("api/income-bills")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Every change moves Home's numbers, so the rest of the app reloads too.
    private func saved(_ reply: IncomeBills) {
        data = reply
        error = nil
        app.changed()
        if let r = reply.removed {
            withAnimation {
                toast = ("\(r.name) removed. It no longer counts in your bills.", { Task { await putBack(r) } })
            }
        }
    }

    private func tick(_ bill: IncomeBills.Bill, _ on: Bool) async {
        if confirming && bill.source != "added" {
            ticked[bill.key] = on
            return
        }
        if bill.source == "added" {
            // A bill she added always counts; untick it by removing it.
            sheet = .bill(bill)
            return
        }
        ticked[bill.key] = on
        do {
            let reply: IncomeBills = try await app.api.put("api/income-bills/bills", ["ticked": [bill.key: on]])
            ticked[bill.key] = nil
            saved(reply)
        } catch {
            ticked[bill.key] = nil
            self.error = app.handle(error)
        }
    }

    private func confirmBills() async {
        guard let data = data else { return }
        busy = true
        defer { busy = false }
        var answers: [String: Bool] = [:]
        for bill in data.bills where bill.source != "added" { answers[bill.key] = isOn(bill) }
        do {
            let reply: IncomeBills = try await app.api.put("api/income-bills/bills", ["ticked": answers])
            ticked = [:]
            saved(reply)
        } catch {
            self.error = app.handle(error)
        }
    }

    private func notPay(_ c: IncomeBills.Candidate) async {
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": c.payer, "answer": "no"])
            saved(reply)
        } catch {
            self.error = app.handle(error)
        }
    }

    private func answerRent(_ q: IncomeBills.RentQuestion) async {
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/rent", ["key": q.key])
            saved(reply)
        } catch {
            self.error = app.handle(error)
        }
    }

    /// Undo a removed bill: add it back as it was.
    private func putBack(_ r: IncomeBills.Removed) async {
        withAnimation { toast = nil }
        var body: [String: Any] = ["name": r.name, "amount": r.amount, "cadence": r.cadence,
                                   "varies": r.varies ?? false]
        if let next = r.next { body["next"] = next }
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/bills", body)
            data = reply
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - IB-03 Your own amount

/// What she expects each month after tax, used instead of Pearl's estimate
/// until she clears it. The same figure Home uses (`home_income`).
@MainActor
struct ExpectedIncomeSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let expected: IncomeBills.Expected?
    /// With pay confirmed, clearing her amount goes back to the pay.
    let hasPay: Bool
    let saved: (IncomeBills) -> Void

    @State private var amount = ""
    @State private var varies = false
    @State private var busy = false
    @State private var error: String?

    private var own: Double? { expected?.amount.flatMap { $0 > 0 ? $0 : nil } }

    var body: some View {
        SheetFrame(title: "Income each month", subtitle: subtitle, symbol: "chart.line.uptrend.xyaxis",
                   heading: "Your own amount", close: { dismiss() }) {
            FieldRow(label: "Each month, after tax", text: $amount, prompt: "$0.00")
                .keyboardType(.decimalPad)
                .sheetCard()
            Toggle("It changes month to month", isOn: $varies)
                .font(Nacre.body).tint(Pearl.action)
                .padding(.horizontal, 16).frame(minHeight: 52)
                .sheetCard()
            Text(varies ? "Pearl plans carefully when it changes, so your Allowance doesn’t run ahead of you."
                        : "Your own amount is used instead of Pearl’s estimate until you clear it.")
                .font(Nacre.footnote)
            if let error = error { Hint(text: error) }
        } actions: {
            Button("Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
                .disabled(busy || amount.isEmpty)
            if expected?.estimate != nil || (own != nil && hasPay) {
                Button(expected?.estimate.map { "Use Pearl’s estimate (\(Format.whole($0)))" } ?? "Use my pay instead") {
                    Task { await clear() }
                }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(busy)
            } else {
                Button("Cancel") { dismiss() }.buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
        .onAppear {
            if let own = own { amount = String(format: "%.2f", own) }
            varies = expected?.varies ?? false
        }
    }

    private var subtitle: String {
        if let estimate = expected?.estimate, estimate > 0 {
            return "Pearl’s estimate is \(Format.whole(estimate)), from your last 3 months"
        }
        return "Roughly what comes in each month after tax"
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            let reply: IncomeBills = try await app.api.put("api/income-bills/expected", [
                "amount": amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: ""),
                "varies": varies,
            ])
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func clear() async {
        busy = true
        defer { busy = false }
        do {
            let reply: IncomeBills = try await app.api.delete("api/income-bills/expected")
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}
