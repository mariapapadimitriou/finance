import SwiftUI

/// O-10 "Your pay and bills" (THL-127): the pay and bills Pearl found, to
/// check before the first Allowance. Tap any to change it; untick a bill
/// that isn't regular. O-10e when no regular pay was found.
@MainActor
struct PayAndBillsView: View {
    @EnvironmentObject private var app: AppModel
    @Binding var path: [SetupRoute]
    /// Profile › Income and bills' "Check again" (IB-01): the same check,
    /// without setup's progress, ending back on the page.
    var onDone: (() -> Void)? = nil
    @State private var data: IncomeBills?
    @State private var ticked: [String: Bool] = [:]
    @State private var notPay: Set<String> = []
    @State private var sheet: Sheet?
    @State private var error: String?
    @State private var busy = false

    enum Sheet: Identifiable {
        case candidate(IncomeBills.Candidate), pay(IncomeBills.Pay), addPay
        case bill(IncomeBills.Bill), addBill
        case ask(IncomeBills.Ask)

        var id: String {
            switch self {
            case .ask(let a): return "a" + a.id
            case .candidate(let c): return "c" + c.id
            case .pay(let p): return "p" + p.id
            case .addPay: return "add-pay"
            case .bill(let b): return "b" + b.id
            case .addBill: return "add-bill"
            }
        }
    }

    var body: some View {
        NacreScreen {
            if onDone == nil { ShellProgress(part: 3, name: "Your money") }
            Text("Your pay and bills").font(Nacre.title).tracking(0.4).accessibilityAddTraits(.isHeader)
            Text(noPay ? "We couldn’t find a regular paycheque. Add your income so your Allowance is right."
                       : "Check these look right. Tap any to change it.")
                .font(Nacre.body)
            if let data = data {
                section("Money in") {
                    if noPay {
                        HStack(alignment: .top, spacing: 12) {
                            TrendBadge()
                            VStack(alignment: .leading, spacing: 2) {
                                Text("No regular pay found").font(Nacre.body)
                                Text("Freelance or gig work? Add what you usually earn.")
                                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            }
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12)
                    }
                    ForEach(data.pays) { pay in
                        incomeRow(pay.name, cadence(pay.cadence), pay.amount) { sheet = .pay(pay) }
                        RowSeparator(inset: 64)
                    }
                    ForEach(candidates) { c in
                        incomeRow(c.name, cadence(c.cadence), c.amount) { sheet = .candidate(c) }
                        RowSeparator(inset: 64)
                    }
                    ForEach(data.asks ?? []) { a in
                        askRow(a)
                        RowSeparator(inset: 64)
                    }
                    addRow(noPay ? "Add your income" : "Add other income") { sheet = .addPay }
                }
                section("Bills") {
                    ForEach(bills) { bill in
                        billRow(bill)
                        RowSeparator(inset: 52)
                    }
                    addRow("Add a bill") { sheet = .addBill }
                }
                if !subscriptions.isEmpty {
                    section("Subscriptions", note: "Untick any you don’t want set aside.") {
                        ForEach(Array(subscriptions.enumerated()), id: \.element.id) { i, bill in
                            if i > 0 { RowSeparator(inset: 52) }
                            billRow(bill)
                        }
                    }
                }
            } else if error == nil {
                ProgressView().frame(maxWidth: .infinity, minHeight: 200)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            BottomActions {
                Button("Looks good") { Task { await confirm() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(data == nil || noPay || busy)
            }
        }
        .task { await load() }
        .sheet(item: $sheet) { which in
            Group {
                switch which {
                case .candidate(let c):
                    PaySheet(title: c.name, subtitle: "Your pay · \(cadence(c.cadence))", payer: c.payer, payId: nil,
                             amount: c.amount, cadence: c.cadence, next: c.next) { reply in
                        if let reply = reply { data = reply } else { notPay.insert(c.payer) }
                    }
                case .pay(let p):
                    PaySheet(title: p.name, subtitle: "Your pay · \(cadence(p.cadence))", payer: p.payer, payId: p.id,
                             amount: p.amount, cadence: p.cadence, next: p.next) { reply in
                        if let reply = reply { data = reply }
                    }
                case .addPay:
                    PaySheet(title: "Add income", subtitle: "A second job, freelance work, support payments",
                             payer: nil, payId: nil, amount: nil, cadence: "monthly", next: nil) { reply in
                        if let reply = reply { data = reply }
                    }
                case .bill(let b):
                    BillSheet(bill: b, counted: Binding(get: { ticked[b.key] ?? b.ticked ?? true },
                                                       set: { ticked[b.key] = $0 })) { reply in
                        if let reply = reply { apply(reply) }
                    }
                case .addBill:
                    BillSheet(bill: nil, counted: nil) { reply in
                        if let reply = reply { apply(reply) }
                    }
                case .ask(let a) where a.kind == "joint":
                    WhosePaySheet(ask: a) { reply in apply(reply) }
                case .ask(let a):
                    WhatIsItSheet(ask: a, bills: bills) { reply in apply(reply) }
                }
            }
            .presentationDetents([.large])
            .presentationDragIndicator(.visible)
        }
    }

    // MARK: Rows

    private var noPay: Bool {
        data != nil && data!.pays.isEmpty && candidates.isEmpty && (data!.asks ?? []).isEmpty
    }

    private var candidates: [IncomeBills.Candidate] {
        (data?.candidates ?? []).filter { !notPay.contains($0.payer) }
    }

    private var bills: [IncomeBills.Bill] {
        (data?.bills ?? []).filter { !subscriptionCategories.contains($0.category ?? "") }
    }

    private var subscriptions: [IncomeBills.Bill] {
        (data?.bills ?? []).filter { subscriptionCategories.contains($0.category ?? "") }
    }

    private func section<Content: View>(_ title: String, note: String? = nil,
                                        @ViewBuilder content: @escaping () -> Content) -> some View {
        MoneySection(title: title, note: note, content: content)
    }

    private func incomeRow(_ name: String, _ sub: String, _ amount: Double,
                           tap: @escaping () -> Void) -> some View {
        IncomeLine(name: name, sub: sub, amount: amount, tap: tap)
    }

    private func askRow(_ a: IncomeBills.Ask) -> some View {
        AskLine(ask: a) { sheet = .ask(a) }
    }

    private func billRow(_ bill: IncomeBills.Bill) -> some View {
        let on = ticked[bill.key] ?? bill.ticked ?? true
        return BillLine(bill: bill, on: on, toggle: { ticked[bill.key] = !on }, edit: { sheet = .bill(bill) })
    }

    private func addRow(_ title: String, tap: @escaping () -> Void) -> some View {
        AddLine(title: title, tap: tap)
    }

    // MARK: Loading and saving

    private func apply(_ reply: IncomeBills) {
        data = reply
    }

    private func load() async {
        do {
            data = try await app.api.get("api/income-bills")
            error = nil
        } catch {
            self.error = app.handle(error)
        }
    }

    private func confirm() async {
        guard let data = data else { return }
        busy = true
        defer { busy = false }
        do {
            for c in candidates {
                let _: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": c.payer, "answer": "yes"])
            }
            for payer in notPay {
                let _: IncomeBills? = try? await app.api.post("api/income-bills/pay/answer",
                                                              ["payer": payer, "answer": "no"])
            }
            var answers: [String: Bool] = [:]
            for bill in data.bills { answers[bill.key] = ticked[bill.key] ?? bill.ticked ?? true }
            let _: IncomeBills = try await app.api.put("api/income-bills/bills", ["ticked": answers])
            app.changed()
            if let onDone = onDone { onDone() } else { path.append(.allowance) }
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - Rows (O-10 and Profile › Income and bills, IB-01)

/// "MONEY IN": the caption and its card, with an optional note in it.
struct MoneySection<Content: View>: View {
    let title: String
    var note: String? = nil
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text(title.uppercased()).font(Nacre.caption2).tracking(0.6).padding(.leading, 16)
                .accessibilityAddTraits(.isHeader)
            GlassCard {
                content()
                if let note = note {
                    Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                }
            }
        }
    }
}

/// "↗  Northwind Ltd · Every 2 weeks   +$2,150 ›".
struct IncomeLine: View {
    let name: String
    let sub: String
    let amount: Double
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                TrendBadge()
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer(minLength: 8)
                Text("+" + Format.whole(amount)).font(Nacre.headline).foregroundColor(Pearl.moneyIn)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Change it")
    }
}

/// An income row that's a question: "Brightside Co · Found · every 2 weeks
/// · Your pay? ›" (IB-02), "Maple Co · Joint account · Whose pay? ›" (O-10f).
struct QuestionLine: View {
    let name: String
    let sub: String
    let question: String
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                TrendBadge()
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer(minLength: 8)
                Text(question).font(Nacre.headline).foregroundColor(Pearl.action)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// O-10f, O-10g's questions about a deposit.
struct AskLine: View {
    let ask: IncomeBills.Ask
    let tap: () -> Void

    var body: some View {
        QuestionLine(name: ask.name,
                     sub: ask.kind == "joint" ? "Joint account" : "\(Format.whole(ask.amount)) · \(cadence(ask.cadence).lowercased())",
                     question: ask.kind == "joint" ? "Whose pay?" : "What is it?", tap: tap)
    }
}

/// "✓  Rent · Monthly · around the 1st   $1,450.00  Edit".
struct BillLine: View {
    let bill: IncomeBills.Bill
    let on: Bool
    let toggle: () -> Void
    let edit: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: toggle) {
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundColor(on ? Pearl.action : Pearl.ink)
            }
            .buttonStyle(.plain)
            .accessibilityLabel(on ? "Counted, \(bill.name)" : "Not counted, \(bill.name)")
            VStack(alignment: .leading, spacing: 2) {
                Text(bill.name).font(Nacre.body)
                Text(billWhen(bill)).font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            Text((bill.varies == true ? "~" : "") + Format.amount(bill.amount)).font(Nacre.body)
            Button("Edit", action: edit)
                .font(Nacre.subheadline).foregroundColor(Pearl.action)
                .buttonStyle(.plain)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .opacity(on ? 1 : 0.6)
    }
}

/// "⊕  Add other income".
struct AddLine: View {
    let title: String
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                Image(systemName: "plus.circle.fill").font(.system(size: 22)).foregroundColor(Pearl.action)
                Text(title).font(Nacre.body).foregroundColor(Pearl.action)
                Spacer()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

/// "Monthly · around the 1st", "Monthly · Sam pays $725" (O-10g).
func billWhen(_ bill: IncomeBills.Bill) -> String {
    let how = cadence(bill.cadence)
    let shared = bill.shared.map { " · \($0.person ?? "They") pay\($0.person == nil ? "" : "s") \(Format.whole($0.amount))" } ?? ""
    if bill.varies == true { return "\(how) · varies" + shared }
    guard let day = bill.day else { return how + shared }
    return "\(how) · around the \(ordinal(day))" + shared
}

/// Bills in these categories are listed as Subscriptions.
let subscriptionCategories: Set<String> = ["Streaming", "Software", "Subscriptions", "News & Media"]

/// The small "↗" badge on an income row.
struct TrendBadge: View {
    var body: some View {
        Image(systemName: "chart.line.uptrend.xyaxis")
            .font(.system(size: 13, weight: .semibold))
            .frame(width: 36, height: 36)
            .background(Circle().fill(Nacre.glass))
            .accessibilityHidden(true)
    }
}

func cadence(_ key: String) -> String {
    ["weekly": "Every week", "biweekly": "Every 2 weeks", "semimonthly": "Twice a month",
     "monthly": "Monthly", "irregular": "Varies", "bimonthly": "Every 2 months",
     "quarterly": "Every 3 months", "semiannual": "Twice a year", "annual": "Yearly"][key] ?? key.capitalized
}

func ordinal(_ n: Int) -> String {
    let suffix: String
    switch (n % 100, n % 10) {
    case (11...13, _): suffix = "th"
    case (_, 1): suffix = "st"
    case (_, 2): suffix = "nd"
    case (_, 3): suffix = "rd"
    default: suffix = "th"
    }
    return "\(n)\(suffix)"
}

private let isoDay: DateFormatter = {
    let f = DateFormatter()
    f.calendar = Calendar(identifier: .gregorian)
    f.locale = Locale(identifier: "en_US_POSIX")
    f.dateFormat = "yyyy-MM-dd"
    return f
}()

// MARK: - O-10b Edit your pay, O-10d Add income

@MainActor
struct PaySheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let title: String
    let subtitle: String
    let payer: String?
    let payId: String?
    let saved: (IncomeBills?) -> Void

    @State private var name = ""
    @State private var amount = ""
    @State private var how: String
    @State private var next: Date
    @State private var error: String?
    @State private var busy = false

    init(title: String, subtitle: String, payer: String?, payId: String?, amount: Double?, cadence: String,
         next: String?, saved: @escaping (IncomeBills?) -> Void) {
        self.title = title
        self.subtitle = subtitle
        self.payer = payer
        self.payId = payId
        self.saved = saved
        _amount = State(initialValue: amount.map { String(format: "%.2f", $0) } ?? "")
        _how = State(initialValue: cadence)
        _next = State(initialValue: next.flatMap { isoDay.date(from: String($0.prefix(10))) } ?? Date())
        _name = State(initialValue: payer == nil && payId == nil ? "" : title)
    }

    private var adding: Bool { payer == nil && payId == nil }

    var body: some View {
        SheetFrame(title: title, subtitle: subtitle, symbol: "chart.line.uptrend.xyaxis", close: { dismiss() }) {
            VStack(spacing: 0) {
                if adding {
                    FieldRow(label: "Name", text: $name, prompt: "e.g. Weekend job")
                    RowSeparator()
                }
                FieldRow(label: adding ? "Amount" : "Each pay", text: $amount, prompt: "$0.00")
                    .keyboardType(.decimalPad)
                RowSeparator()
                pickerRow("How often", selection: $how, options: ["weekly", "biweekly", "semimonthly", "monthly", "irregular"])
                RowSeparator()
                DatePicker(adding ? "Next payment" : "Next pay", selection: $next, displayedComponents: .date)
                    .font(Nacre.body).padding(.horizontal, 16).frame(minHeight: 52)
            }
            .sheetCard()
            Text(adding ? "Not sure? Enter what you usually get in a month. You can change it any time."
                        : "If it changes, enter what usually lands. You can change it any time.")
                .font(Nacre.footnote)
            if let error = error { Hint(text: error) }
        } actions: {
            Button(adding ? "Add income" : "Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
            if adding {
                Button("Cancel") { dismiss() }.buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            } else {
                Button("This isn’t my pay") { Task { await notMine() } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["name": adding ? name : title, "amount": amount.replacingOccurrences(of: "$", with: ""),
                                   "cadence": how, "next": isoDay.string(from: next)]
        do {
            let reply: IncomeBills
            if let id = payId {
                reply = try await app.api.put("api/income-bills/pay/\(id)", body)
            } else {
                if let payer = payer { body["payer"] = payer }
                reply = try await app.api.post("api/income-bills/pay", body)
            }
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func notMine() async {
        busy = true
        defer { busy = false }
        do {
            if let id = payId {
                let reply: IncomeBills = try await app.api.delete("api/income-bills/pay/\(id)")
                saved(reply)
            } else {
                saved(nil)
            }
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - O-10a Edit a bill, O-10c Add a bill

@MainActor
struct BillSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let bill: IncomeBills.Bill?
    /// "Count this bill": the same tick as on the list.
    let counted: Binding<Bool>?
    let saved: (IncomeBills?) -> Void

    @State private var name = ""
    @State private var amount = ""
    @State private var how = "monthly"
    @State private var next = Date()
    @State private var varies = false
    @State private var error: String?
    @State private var busy = false

    var body: some View {
        SheetFrame(title: bill?.name ?? "Add a bill",
                   subtitle: bill.map { "\($0.category ?? "Bill") · \(cadence($0.cadence))" }
                       ?? "Including ones paid by e-Transfer, cheque or cash",
                   symbol: "doc.text", close: { dismiss() }) {
            VStack(spacing: 0) {
                if bill == nil {
                    FieldRow(label: "Name", text: $name, prompt: "e.g. Tuition")
                    RowSeparator()
                }
                FieldRow(label: "Amount", text: $amount, prompt: "$0.00").keyboardType(.decimalPad)
                RowSeparator()
                pickerRow("Repeats", selection: $how,
                          options: ["weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "annual"])
                RowSeparator()
                DatePicker("Next payment", selection: $next, displayedComponents: .date)
                    .font(Nacre.body).padding(.horizontal, 16).frame(minHeight: 52)
            }
            .sheetCard()
            VStack(spacing: 0) {
                Toggle("Amount changes each month", isOn: $varies)
                    .font(Nacre.body).tint(Pearl.action)
                    .padding(.horizontal, 16).frame(minHeight: 52)
                if let counted = counted {
                    RowSeparator()
                    Toggle("Count this bill", isOn: counted)
                        .font(Nacre.body).tint(Pearl.action)
                        .padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
            .sheetCard()
            if bill != nil {
                Text("Untick it if it isn’t a regular bill.").font(Nacre.footnote)
            }
            if let error = error { Hint(text: error) }
        } actions: {
            Button(bill == nil ? "Add bill" : "Save") { Task { await save() } }
                .buttonStyle(NacreButtonStyle(busy: busy))
            if let bill = bill, bill.source == "added" {
                Button("Remove bill") { Task { await remove(bill) } }
                    .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
            }
        }
        .onAppear {
            guard let bill = bill else { return }
            name = bill.name
            amount = String(format: "%.2f", bill.amount)
            how = bill.cadence
            varies = bill.varies ?? false
            if let n = bill.next, let d = isoDay.date(from: String(n.prefix(10))) { next = d }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        let body: [String: Any] = ["name": name, "amount": amount.replacingOccurrences(of: "$", with: ""),
                                   "cadence": how, "next": isoDay.string(from: next), "varies": varies]
        do {
            let reply: IncomeBills
            if let bill = bill {
                let key = bill.key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? bill.key
                reply = try await app.api.put("api/income-bills/bills/\(key)", body)
            } else {
                reply = try await app.api.post("api/income-bills/bills", body)
            }
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }

    private func remove(_ bill: IncomeBills.Bill) async {
        busy = true
        defer { busy = false }
        do {
            let key = bill.key.addingPercentEncoding(withAllowedCharacters: .urlPathAllowed) ?? bill.key
            let reply: IncomeBills = try await app.api.delete("api/income-bills/bills/\(key)")
            saved(reply)
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - Sheet parts

/// A sheet on the nacre: an icon, a title and a line, a close button, the
/// fields, and its actions at the bottom.
struct SheetFrame<Content: View, Actions: View>: View {
    let title: String
    let subtitle: String
    let symbol: String
    let close: () -> Void
    @ViewBuilder var content: () -> Content
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    HStack(alignment: .top, spacing: 12) {
                        IconOrb(symbol: symbol, size: 44)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(title).font(Nacre.title2)
                            Text(subtitle).font(Nacre.subheadline)
                        }
                        Spacer(minLength: 8)
                        CloseButton(action: close)
                    }
                    content()
                }
                .padding(16)
            }
            VStack(spacing: 6, content: actions).padding(.horizontal, 16).padding(.bottom, 8)
        }
        .foregroundColor(Pearl.ink)
        .background(NacreBackground().opacity(0.35))
        .background(Pearl.page)
    }
}

extension View {
    /// The white rounded card fields sit in, inside a sheet.
    func sheetCard() -> some View {
        background(RoundedRectangle(cornerRadius: 16, style: .continuous).fill(Pearl.card))
    }
}

/// "Repeats   Monthly ›" as a menu.
func pickerRow(_ label: String, selection: Binding<String>, options: [String]) -> some View {
    HStack {
        Text(label).font(Nacre.body)
        Spacer()
        Menu {
            Picker(label, selection: selection) {
                ForEach(options, id: \.self) { Text(cadence($0)).tag($0) }
            }
        } label: {
            HStack(spacing: 6) {
                Text(cadence(selection.wrappedValue))
                Image(systemName: "chevron.right").font(.system(size: 12, weight: .semibold))
            }
            .font(Nacre.body).foregroundColor(Pearl.muted)
        }
    }
    .padding(.horizontal, 16).frame(minHeight: 52)
}
