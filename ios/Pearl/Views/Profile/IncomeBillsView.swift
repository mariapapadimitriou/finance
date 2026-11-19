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
// IB-04  "Are these your rent?": e-Transfers to one person that look like rent
// YP-09  1356:9864 / 1356:9956  Your plan (YP-01 to YP-08, YourPlanView.swift):
//        a card of its own above INCOME, the way in PC-13's "It's in Profile ›
//        Income and bills › Your plan" names: in use with its total, not in
//        use, or none yet (which opens YP-06)
//
// Every write returns the whole page again (finance/income_bills_api.py),
// so nothing here adds anything up. A bill's tick saves at once once she has
// confirmed her bills; before that the ticks wait for "Confirm n bills".

/// Your plan is parked along with Save (product owner, 2026-11-18). The one
/// switch for every way into it from Profile; turn it on when Save returns.
enum YourPlanGate {
    static let shown = false
}

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

        /// O-10f, O-10g and Income each month (POLISH-01 audits 8 and 9) size to their content.
        var fits: Bool {
            switch self {
            case .ask: return true
            default: return false
            }
        }

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
                // G5-Load: rows hold their place.
                ProfileSection(" ")
                APCard { APSkeletonRow(); APSeparator(); APSkeletonRow() }
            }
            if let error = error { APErrorLine(text: error).padding(.top, 4) }
        } bottom: {
            if data != nil && confirming {
                Button(confirmLabel) { Task { await confirmBills() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy)
            }
        }
        .overlay(alignment: .bottom) {
            // UN-01: the toast sits at the bottom.
            if let toast = toast {
                UndoToast(text: toast.text, undo: toast.undo) { withAnimation { self.toast = nil } }
                    .padding(.bottom, 12)
            }
        }
        .refreshable { await load() }
        .reloads { await load() }
        .sheet(item: $sheet) { which in
            sheetView(which)
                // POLISH-01: the questions and Income each month size to their content.
                .largeUnless(which.fits)
                .presentationDragIndicator(.visible)
        }
        .sheet(item: $rent) { q in
            // IB-04 (TEST-06): a Pearl sheet, not an action sheet.
            let who = q.recipient ?? "them"
            PearlConfirmSheet(face: q.recipient, overline: "A question", title: "Are these your rent?",
                              message: "If your e-Transfers to \(who) are rent, they count as Rent and \(Format.whole(q.amount)) a month is set aside.",
                              primary: "Yes, it’s my rent", busyLabel: "Saving…", secondary: "No",
                              failure: "Couldn’t save that. Nothing changed. Try again.",
                              onClose: { rent = nil }) {
                let reply: IncomeBills = try await app.api.post("api/income-bills/rent", ["key": q.key])
                rent = nil
                saved(reply)
            }
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

    /// G5-Income: the summary, Your plan, Income (with Add), Regular bills
    /// (with Add) and Subscriptions; found pay and a found rent answer Yes or
    /// No right on the row (IB-02, approved 2026-11-18); then Check again.
    @ViewBuilder
    private func content(_ data: IncomeBills) -> some View {
        if confirming || !data.candidates.isEmpty || data.rentQuestion != nil {
            APBanner(symbol: "sparkles", text: foundLine(data)).padding(.top, 8)
        } else if let income = data.totals?.income, income > 0 {
            APCard {
                APKeyValueRow(key: "Comes in") {
                    Text("+\(Format.whole(income)) a month").font(Nacre.headline).foregroundColor(Pearl.moneyIn)
                }
                APSeparator(afterFace: false)
                APKeyValueRow(key: "Set aside for bills") {
                    Text("\(Format.whole(data.totals?.bills ?? 0)) a month").font(Nacre.headline).foregroundColor(Pearl.moneyOut)
                }
            }
            .padding(.top, 8)
        }

        // YP-09: Your plan, its own card above Income. Parked with Save
        // (product owner, 2026-11-18): hidden behind YourPlanGate.shown.
        if YourPlanGate.shown {
            APCard {
                NavigationLink { YourPlanView() } label: {
                    ProfileRow(symbol: "calendar", title: "Your plan") {
                        Text(planValue(data.yourPlan)).font(Nacre.body).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                }
                .buttonStyle(.plain)
                .accessibilityIdentifier("income-your-plan")
            }
            .padding(.top, 8)
        }

        ProfileSection("Income", action: "Add") { sheet = .addPay }
        APCard {
            if let own = data.expected?.amount, own > 0 {
                IncomeLine(name: "Your own amount",
                           sub: data.expected?.varies == true ? "A month after tax · it changes" : "A month after tax",
                           amount: own) { sheet = .expected }
                APSeparator()
            }
            ForEach(data.pays) { p in
                IncomeLine(name: p.name, sub: cadence(p.cadence), amount: p.amount) { sheet = .pay(p) }
                APSeparator()
            }
            ForEach(data.candidates) { c in
                FoundLine(name: c.name, question: "Your pay?", open: { sheet = .candidate(c) },
                          yes: { Task { await answerPay(c, yes: true) } },
                          no: { Task { await answerPay(c, yes: false) } })
                APSeparator()
            }
            ForEach(data.asks ?? []) { a in
                AskLine(ask: a) { sheet = .ask(a) }
                APSeparator()
            }
            if noIncome(data) {
                if let estimate = data.expected?.estimate, estimate > 0 {
                    IncomeLine(name: "Pearl’s estimate", sub: "The average of your last 3 months",
                               amount: estimate) { sheet = .expected }
                } else {
                    NoIncomeLine { sheet = .expected }
                }
            } else if !((data.expected?.amount ?? 0) > 0) {
                Button { sheet = .expected } label: {
                    ProfileRow(symbol: "square.and.pencil", title: "Set my own amount")
                }
                .buttonStyle(.plain)
                .accessibilityHint("Use what you expect each month instead of what Pearl works out")
            }
        }

        ProfileSection("Regular bills", action: "Add") { sheet = .addBill }
        APCard {
            if let q = data.rentQuestion {
                FoundLine(name: q.recipient ?? "e-Transfers", question: "Your rent?", open: { rent = q },
                          yes: { Task { await answerRent(q, yes: true) } },
                          no: { Task { await answerRent(q, yes: false) } })
                if !regular(data).isEmpty { APSeparator() }
            }
            ForEach(Array(regular(data).enumerated()), id: \.element.id) { i, bill in
                if i > 0 { APSeparator() }
                billRow(bill)
            }
        }

        let subs = data.bills.filter { subscriptionCategories.contains($0.category ?? "") }
        if !subs.isEmpty {
            ProfileSection("Subscriptions")
            APCard {
                ForEach(Array(subs.enumerated()), id: \.element.id) { i, bill in
                    if i > 0 { APSeparator() }
                    billRow(bill)
                }
            }
        }

        if !confirming {
            Button("Check again") { checking = true }
                .buttonStyle(APSecondaryButtonStyle())
                .padding(.top, 10)
                .accessibilityIdentifier("income-check-again")
        }
        Color.clear.frame(height: 24)
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

    /// YP-09: "$1,160 a month" in use, "Not in use", or "None yet".
    private func planValue(_ card: IncomeBills.PlanCard?) -> String {
        guard let card = card, card.rows > 0 else { return "None yet" }
        if card.inUse { return "\(Format.whole(card.total)) a month" }
        return "Not in use"
    }

    /// G5-Income: only the page with no income says anything under the title.
    private var lead: String? {
        guard let data = data, noIncome(data), data.rentQuestion == nil, !confirming else { return nil }
        return "Add your income so your Allowance is right."
    }

    /// "Pearl found new pay and 3 bills. Say which are right."
    private func foundLine(_ data: IncomeBills) -> String {
        let pay = data.candidates.isEmpty ? nil : (data.candidates.count == 1 ? "new pay" : "\(data.candidates.count) new pays")
        let n = (confirming ? found(data).count : 0) + (data.rentQuestion == nil ? 0 : 1)
        let bills = n == 0 ? nil : (n == 1 ? "a bill" : "\(n) bills")
        let what = [pay, bills].compactMap { $0 }.joined(separator: " and ")
        return "Pearl found \(what.isEmpty ? "something" : what). Say which are right."
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
                toast = ("\(r.name) removed", { Task { await putBack(r) } })
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

    /// IB-02 Yes / No on the row: the same answer the pay sheet gives.
    private func answerPay(_ c: IncomeBills.Candidate, yes: Bool) async {
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": c.payer, "answer": yes ? "yes" : "no"])
            saved(reply)
        } catch {
            self.error = app.handle(error)
        }
    }

    /// IB-04 on the row: Yes counts them as Rent; No stops Pearl asking.
    private func answerRent(_ q: IncomeBills.RentQuestion, yes: Bool) async {
        do {
            var body: [String: Any] = ["key": q.key]
            if !yes { body["answer"] = "no" }
            let reply: IncomeBills = try await app.api.post("api/income-bills/rent", body)
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

    /// G5-IncomeEdit "Your own amount": the big amount well, Pearl's
    /// estimate under it, the switch, and Save riding above the keypad.
    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 14) {
                APSheetTitle(title: "Your own amount") { dismiss() }
                Text("Each month, after tax").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity).padding(.top, 2)
                BigAmountWell(text: $amount, placeholder: varies ? "Pearl works it out" : "0")
                    // The latest answer wins (decision 7): typing an amount means it doesn't change.
                    .onChange(of: amount) { typed in if !typed.isEmpty { varies = false } }
                if let estimate = expected?.estimate, estimate > 0 {
                    ProfileNote("Pearl\u{2019}s estimate is \(Format.whole(estimate))", centred: true)
                }
                APCard {
                    APToggleRow(title: "It changes month to month",
                                isOn: Binding(get: { varies }, set: { on in
                                    varies = on
                                    if on { amount = "" }
                                }))
                }
                if let error = error { APErrorLine(text: error) }
            }
            .padding(.horizontal, 16).padding(.top, 20).padding(.bottom, 16)
        }
        .scrollDismissesKeyboard(.interactively)
        .safeAreaInset(edge: .bottom, spacing: 0) {
            VStack(spacing: 4) {
                Button(error == nil ? "Save" : "Try again") { Task { await save() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy || (amount.isEmpty && !varies))
                if expected?.estimate != nil || (own != nil && hasPay) {
                    Button(expected?.estimate.map { "Use Pearl\u{2019}s estimate (\(Format.whole($0)))" } ?? "Use my pay instead") {
                        Task { await clear() }
                    }
                    .buttonStyle(APQuietTextStyle())
                    .disabled(busy)
                }
            }
            .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
        }
        .onAppear {
            varies = expected?.varies ?? false
            if let own = own, !varies { amount = String(format: "%.0f", own) }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            var body: [String: Any] = ["varies": varies]
            if !varies {
                body["amount"] = amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")
            }
            let reply: IncomeBills = try await app.api.put("api/income-bills/expected", body)
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

/// IB-02: something Pearl found, answered Yes or No right on the row (the
/// row itself opens the sheet with the details).
private struct FoundLine: View {
    let name: String
    let question: String
    let open: () -> Void
    let yes: () -> Void
    let no: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: open) {
                HStack(spacing: 12) {
                    RowAvatar(name: name)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Text(question).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            .accessibilityHint("Shows what Pearl found")
            APPillButton(title: "Yes", identifier: "found-yes-\(name)", action: yes)
                .accessibilityLabel("Yes, \(question.lowercased().replacingOccurrences(of: "?", with: "")) \(name)")
            APPillButton(title: "No", quiet: true, identifier: "found-no-\(name)", action: no)
                .accessibilityLabel("No, not \(question.lowercased().replacingOccurrences(of: "your ", with: "my ").replacingOccurrences(of: "?", with: ""))")
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
    }
}

/// G5-Income, no income yet: what comes in each month, and Add.
private struct NoIncomeLine: View {
    let add: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            IconBubble(symbol: "dollarsign.square")
            VStack(alignment: .leading, spacing: 2) {
                Text("No income yet").font(Nacre.body).foregroundColor(Pearl.ink)
                Text("What comes in each month").font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            APPillButton(title: "Add", identifier: "income-add-own", action: add)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
        .accessibilityElement(children: .contain)
    }
}

/// G5-IncomeEdit's `.fld.big`: a 72 pt well, radius 16, the amount centred
/// in 36 pt Fraunces SemiBold with its `$`, the keypad up from the start.
struct BigAmountWell: View {
    @Binding var text: String
    var placeholder = "0"
    @FocusState private var focused: Bool

    var body: some View {
        HStack(spacing: 4) {
            Text("$").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $text, prompt: Text(placeholder).foregroundColor(Pearl.muted))
                .keyboardType(.decimalPad)
                .focused($focused)
                .foregroundColor(Pearl.ink)
                .tint(Pearl.action)
                .fixedSize()
                .accessibilityLabel("Each month, after tax")
                .accessibilityIdentifier("own-amount")
        }
        .font(.custom("Fraunces-SemiBold", size: 36, relativeTo: .largeTitle))
        .monospacedDigit()
        .frame(maxWidth: .infinity, minHeight: 72)
        .background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(APlus.well))
        .overlay(RoundedRectangle(cornerRadius: 16, style: .continuous)
            .strokeBorder(focused ? Pearl.action : APlus.wellLine, lineWidth: focused ? 2 : 1))
        .contentShape(Rectangle())
        .onTapGesture { focused = true }
        .onAppear { focused = true }
    }
}
