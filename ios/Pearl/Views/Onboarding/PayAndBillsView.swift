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
    /// G6-PayBills-r: "See all" tapped, so the whole list shows.
    @State private var allBills = false
    @State private var allSubscriptions = false

    /// G6-PayBills-r: how many rows a list shows before "See all".
    static let shownRows = 3

    enum Sheet: Identifiable {
        case candidate(IncomeBills.Candidate), pay(IncomeBills.Pay), addPay
        case bill(IncomeBills.Bill), addBill
        case ask(IncomeBills.Ask)

        /// O-10f and O-10g (POLISH-01) size to their content.
        var fits: Bool {
            if case .ask = self { return true }
            return false
        }

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
        // G6-PayBills O-10: part 3, Money in (found pay answers Yes / No on
        // the row, approved 2026-11-18), Bills with their ticks.
        OnbScreen(part: onDone == nil ? 3 : nil, partName: "Your money") {
            OnbTitle(title: "Your pay and bills", line: "Check these look right.")
            if let data = data {
                moneyIn(data)
                // G6-PayBills-r (O-10): each list shows 3, then "See all 5
                // bills · $1,692 a month"; the count is in the label.
                billList("Bills", noun: ("bill", "bills"), rows: bills, all: $allBills, add: { sheet = .addBill })
                if !subscriptions.isEmpty {
                    billList("Subscriptions", noun: ("subscription", "subscriptions"), rows: subscriptions,
                             all: $allSubscriptions, add: nil)
                }
            } else if error == nil {
                section("Money in") { APSkeletonRow(); APSeparator(); APSkeletonRow() }
                section("Bills") { APSkeletonRow(); APSeparator(); APSkeletonRow(); APSeparator(); APSkeletonRow() }
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            OnbPrimary(title: "Looks good", busy: busy, enabled: data != nil && !noPay) { Task { await confirm() } }
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
                             amount: p.amount, cadence: p.cadence, next: p.next, account: p.account, varies: p.varies ?? false) { reply in
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
            .largeUnless(which.fits)
            .presentationDragIndicator(.visible)
        }
    }

    /// MONEY IN: confirmed pay, found pay (Yes / No), questions, or "No
    /// regular pay found" with Add.
    @ViewBuilder
    private func moneyIn(_ data: IncomeBills) -> some View {
        if noPay {
            section("Money in") {
                HStack(spacing: 12) {
                    IconBubble(symbol: "dollarsign.square")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("No regular pay found").font(Nacre.body).foregroundColor(Pearl.ink)
                        Text("Add what you usually earn").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    APPillButton(title: "Add", identifier: "add-income") { sheet = .addPay }
                }
                .padding(.horizontal, 16).padding(.vertical, 12)
                .frame(minHeight: 64)
            }
        } else {
            section("Money in", action: "Add", act: { sheet = .addPay }) {
                ForEach(Array(data.pays.enumerated()), id: \.element.id) { i, pay in
                    if i > 0 { APSeparator() }
                    incomeRow(pay.name, cadence(pay.cadence), pay.amount) { sheet = .pay(pay) }
                }
                ForEach(candidates) { c in
                    if !data.pays.isEmpty || c.id != candidates.first?.id { APSeparator() }
                    FoundPayRow(name: c.name, sub: "Your pay?", tap: { sheet = .candidate(c) },
                                yes: { Task { await answer(c.payer, "yes") } },
                                no: { Task { await answer(c.payer, "no") } })
                        .disabled(busy)
                }
                ForEach(data.asks ?? []) { a in
                    if !data.pays.isEmpty || !candidates.isEmpty || a.id != data.asks?.first?.id { APSeparator() }
                    askRow(a)
                }
            }
        }
    }

    /// Found pay, answered on the row: Yes keeps it as her pay, No says it isn't.
    private func answer(_ payer: String, _ answer: String) async {
        busy = true
        defer { busy = false }
        do {
            let reply: IncomeBills = try await app.api.post("api/income-bills/pay/answer",
                                                            ["payer": payer, "answer": answer])
            if answer == "no" { notPay.insert(payer) }
            data = reply
            error = nil
        } catch {
            self.error = app.handle(error)
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

    private func section<Content: View>(_ title: String, note: String? = nil, action: String? = nil,
                                        act: @escaping () -> Void = {},
                                        @ViewBuilder content: @escaping () -> Content) -> some View {
        MoneySection(title: title, note: note, action: action, act: act, content: content)
    }

    private func incomeRow(_ name: String, _ sub: String, _ amount: Double,
                           tap: @escaping () -> Void) -> some View {
        IncomeLine(name: name, sub: sub, amount: amount, tap: tap)
    }

    @ViewBuilder
    private func askRow(_ a: IncomeBills.Ask) -> some View {
        if a.kind == "joint" {
            // A joint deposit: Yes asks whose it is (O-10f); No, it isn't regular pay.
            FoundPayRow(name: a.name, sub: "Your pay? \u{00B7} joint", tap: { sheet = .ask(a) },
                        yes: { sheet = .ask(a) }, no: { Task { await answer(a.payer, "no") } })
                .disabled(busy)
        } else {
            AskLine(ask: a) { sheet = .ask(a) }
        }
    }

    /// G6-PayBills-r: "BILLS · 5" with Add, the first 3 rows, and under the
    /// card "See all 5 bills · $1,692 a month", which shows the rest here.
    private func billList(_ title: String, noun: (one: String, many: String), rows: [IncomeBills.Bill],
                          all: Binding<Bool>, add: (() -> Void)?) -> some View {
        let cut = rows.count > Self.shownRows && !all.wrappedValue
        let shown = cut ? Array(rows.prefix(Self.shownRows)) : rows
        return VStack(spacing: 0) {
            section(PayBillsWords.label(title, rows.count), action: add == nil ? nil : "Add", act: add ?? {}) {
                ForEach(Array(shown.enumerated()), id: \.element.id) { i, bill in
                    if i > 0 { APSeparator() }
                    billRow(bill)
                }
            }
            if cut {
                APQuietButton(title: PayBillsWords.seeAll(rows.count, noun: noun, monthly: monthly(rows)),
                              identifier: "see-all-\(noun.many)") {
                    withAnimation { all.wrappedValue = true }
                }
                .padding(.top, 2)
            }
        }
    }

    /// What a list's ticked rows come to a month, as the server counts it
    /// (finance/income_bills.py `monthly`), with her ticks as they are now.
    private func monthly(_ rows: [IncomeBills.Bill]) -> Double {
        rows.filter { ticked[$0.key] ?? $0.ticked ?? true }
            .reduce(0) { $0 + PayBillsWords.monthly($1.amount, cadence: $1.cadence) }
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
            if let onDone = onDone { onDone() } else { path.append(.saving) }
        } catch {
            self.error = app.handle(error)
        }
    }
}

/// G6-PayBills-r's words.
enum PayBillsWords {
    static let perYear: [String: Double] = ["weekly": 52, "biweekly": 26, "monthly": 12, "bimonthly": 6,
                                            "quarterly": 4, "semiannual": 2, "annual": 1]

    /// "Bills · 5": the count in the label.
    static func label(_ title: String, _ count: Int) -> String {
        count > 0 ? "\(title) \u{00B7} \(count)" : title
    }

    /// "See all 5 bills · $1,692 a month".
    static func seeAll(_ count: Int, noun: (one: String, many: String), monthly: Double) -> String {
        "See all \(count) \(count == 1 ? noun.one : noun.many) \u{00B7} \(Format.whole(monthly)) a month"
    }

    /// A bill's amount a month (finance/income_bills.py `monthly`).
    static func monthly(_ amount: Double, cadence: String) -> Double {
        amount * (perYear[cadence] ?? 12) / 12
    }
}

// MARK: - Rows (O-10 and Profile › Income and bills, IB-01)

/// "MONEY IN": the A+ caps label (with its quiet Add) and its card, with an
/// optional note in it.
struct MoneySection<Content: View>: View {
    let title: String
    var note: String? = nil
    var action: String? = nil
    var act: () -> Void = {}
    @ViewBuilder var content: () -> Content

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            APSectionLabel(text: title, action: action, act: act)
            APCard {
                content()
                if let note = note {
                    Text(note).font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16).padding(.vertical, 10)
                }
            }
        }
        .padding(.top, 12)
    }
}

/// "NW  Northwind Ltd · Every 2 weeks   +$2,150" (G6-PayBills): the face,
/// the name over its line, the amount in money-in on the right edge. A tap changes it.
struct IncomeLine: View {
    let name: String
    let sub: String
    let amount: Double
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                RowAvatar(name: name)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Text("+" + Format.whole(amount)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.moneyIn).pearlAmountFit().fixedSize()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Change it")
    }
}

/// Found pay answered on the row (G6-PayBills, G5-Income; approved
/// 2026-11-18): the face, the name over "Your pay?", then Yes (action wash)
/// and No (quiet). A tap on the name opens it.
struct FoundPayRow: View {
    let name: String
    let sub: String
    let tap: () -> Void
    let yes: () -> Void
    let no: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: tap) {
                HStack(spacing: 12) {
                    RowAvatar(name: name)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityLabel("\(name), \(sub)")
            APPillButton(title: "Yes", identifier: "found-yes-\(name)", action: yes)
                .accessibilityLabel("Yes, \(name) is my pay")
            APPillButton(title: "No", quiet: true, identifier: "found-no-\(name)", action: no)
                .accessibilityLabel("No, \(name) isn\u{2019}t my pay")
        }
        .padding(.horizontal, 16).padding(.vertical, 6)
        .frame(minHeight: 64)
    }
}

/// An income row that's a question: "Brightside Co · Found · every 2 weeks
/// · Your pay? ›" (IB-02), "Sam · $725 · what is it? ›" (O-10g).
struct QuestionLine: View {
    let name: String
    let sub: String
    let question: String
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                RowAvatar(name: name)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text(question.isEmpty ? sub : "\(sub) \u{00B7} \(question.lowercased())")
                        .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                APChevron()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
    }
}

/// O-10f, O-10g's questions about a deposit.
struct AskLine: View {
    let ask: IncomeBills.Ask
    let tap: () -> Void

    var body: some View {
        QuestionLine(name: ask.name,
                     sub: ask.kind == "joint" ? "Joint account" : Format.whole(ask.amount),
                     question: ask.kind == "joint" ? "Whose pay?" : "What is it?", tap: tap)
    }
}

/// "☑  RE  Rent · Around the 1st   $1,450.00" (G6-PayBills): the tick
/// counts it, the rest of the row changes it; spending in plum.
struct BillLine: View {
    let bill: IncomeBills.Bill
    let on: Bool
    let toggle: () -> Void
    let edit: () -> Void

    var body: some View {
        HStack(spacing: 12) {
            Button(action: toggle) { APTickBox(on: on).frame(width: 44, height: 44) }
                .buttonStyle(.plain)
                .padding(.horizontal, -10)
                .accessibilityLabel(on ? "Counted, \(bill.name)" : "Not counted, \(bill.name)")
            Button(action: edit) {
                HStack(spacing: 12) {
                    RowAvatar(name: bill.name)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(bill.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Text(billShort(bill)).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    Text((bill.varies == true ? "~" : "") + Format.amount(bill.amount))
                        .font(Nacre.headline).monospacedDigit()
                        .foregroundColor(Pearl.moneyOut).pearlAmountFit().fixedSize()
                }
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityHint("Change it")
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .frame(minHeight: 64)
    }
}

/// "Around the 1st", "Varies", "Monthly · Sam pays $725": a bill's short line.
func billShort(_ bill: IncomeBills.Bill) -> String {
    let shared = bill.shared.map { " · \($0.person ?? "They") pay\($0.person == nil ? "" : "s") \(Format.whole($0.amount))" } ?? ""
    if bill.varies == true { return "Varies" + shared }
    guard let day = bill.day else { return cadence(bill.cadence) + shared }
    return "Around the \(ordinal(day))" + shared
}

/// "+  Add other income".
struct AddLine: View {
    let title: String
    let tap: () -> Void

    var body: some View {
        Button(action: tap) {
            HStack(spacing: 12) {
                IconBubble(symbol: "plus")
                Text(title).font(Nacre.body).foregroundColor(Pearl.link)
                Spacer()
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .frame(minHeight: 64)
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
        IconBubble(symbol: "chart.line.uptrend.xyaxis")
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
    /// O-10b / O-10d: where it lands, and whether it changes each time.
    @State private var account: String
    @State private var varies: Bool
    @State private var accounts: [String] = []
    @State private var error: String?
    @State private var busy = false

    init(title: String, subtitle: String, payer: String?, payId: String?, amount: Double?, cadence: String,
         next: String?, account: String? = nil, varies: Bool = false, saved: @escaping (IncomeBills?) -> Void) {
        _account = State(initialValue: account ?? "")
        _varies = State(initialValue: varies)
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

    @State private var when = false

    /// G6-PayEdit O-10b / O-10d (rethought, approved 2026-11-18): the
    /// amount leads, in one big well; how often, the next pay and where it
    /// lands are one line ("Every 2 weeks · next Nov 21") that opens them.
    var body: some View {
        AmountSheet(heading: adding ? "Add income" : "Your pay", name: adding ? nil : title,
                    sub: adding ? nil : (account.isEmpty ? nil : "Into \(account)"), close: { dismiss() }) {
            if adding {
                FieldRow(label: "Name", text: $name, prompt: "e.g. Weekend job")
            }
            BigAmountWell(text: $amount, placeholder: "0.00", label: adding ? "Amount" : "Each pay",
                          identifier: "pay-amount", autofocus: false)
            WhenLine(text: "\(cadence(how)) \u{00B7} next \(Format.short(isoDay.string(from: next)))") { when = true }
            if !adding {
                APCard {
                    APToggleRow(title: "My pay changes each time", isOn: $varies)
                }
            }
            if let error = error { APErrorLine(text: error) }
        } actions: {
            Button(adding ? "Add income" : "Save") { Task { await save() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(busy || amount.isEmpty || (adding && name.trimmingCharacters(in: .whitespaces).isEmpty))
            if !adding {
                APQuietButton(title: "This isn’t my pay", identifier: "not-my-pay") { Task { await notMine() } }
                    .disabled(busy)
            }
        }
        .sheet(isPresented: $when) {
            PearlSheet {
                APSheetTitle(title: adding ? "How often" : "When it comes") { when = false }
                APCard {
                    pickerRow("How often", selection: $how, options: ["weekly", "biweekly", "semimonthly", "monthly", "irregular"])
                    APSeparator(afterFace: false)
                    // G0-DateSheet DP-02: the Pearl date sheet, today onward.
                    PearlDateRow(label: adding ? "Next payment" : "Next pay", title: "When is it due next?",
                                 date: $next, range: .todayOnward)
                    if !accounts.isEmpty {
                        APSeparator(afterFace: false)
                        namedPicker("Goes into", selection: $account, options: accounts)
                    }
                    if adding {
                        APSeparator(afterFace: false)
                        APToggleRow(title: "Amount changes each time", isOn: $varies)
                    }
                }
            } footer: {
                Button("Done") { when = false }.buttonStyle(APPrimaryButtonStyle())
            }
        }
        .task {
            guard let o: AccountsOverview = try? await app.api.get("api/accounts/overview") else { return }
            accounts = o.linked.filter { ["chequing", "savings", "depository"].contains($0.kind ?? "chequing") }.map(\.name)
            if account.isEmpty, let first = accounts.first { account = first }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["name": adding ? name : title, "amount": amount.replacingOccurrences(of: "$", with: ""),
                                   "cadence": how, "next": isoDay.string(from: next), "varies": varies]
        if !account.isEmpty { body["account"] = account }
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
    /// O-10a / O-10c: its category and her share of it.
    @State private var category = ""
    @State private var share = "100"
    @State private var categories: [String] = []
    @State private var error: String?
    @State private var busy = false

    @State private var when = false
    @State private var more = false

    /// G6-PayEdit O-10a / O-10c (rethought, approved 2026-11-18): the
    /// amount leads; "Monthly · next Dec 1" is one line that opens when it
    /// repeats; her share, category and whether it changes sit behind More
    /// options. Remove bill is the one red quiet link.
    var body: some View {
        AmountSheet(heading: bill?.name ?? "Add a bill", name: bill?.name,
                    sub: bill.map { $0.category ?? "Bill" }, close: { dismiss() }) {
            if bill == nil {
                FieldRow(label: "Name", text: $name, prompt: "e.g. Tuition")
            }
            BigAmountWell(text: $amount, placeholder: "0.00", label: "Amount", identifier: "bill-amount",
                          autofocus: false)
            WhenLine(text: "\(cadence(how)) \u{00B7} next \(Format.short(isoDay.string(from: next)))") { when = true }
            Button { more = true } label: {
                HStack(spacing: 12) {
                    APIcon(symbol: "slider.horizontal.3")
                    VStack(alignment: .leading, spacing: 2) {
                        Text("More options").font(Nacre.body).foregroundColor(Pearl.ink)
                        Text("Your share, category, amount changes").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                    }
                    .frame(maxWidth: .infinity, alignment: .leading)
                    APChevron()
                }
                .padding(.horizontal, 16).padding(.vertical, 12).frame(minHeight: 64)
                .contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .apCard()
            .accessibilityIdentifier("bill-more-options")
            if let error = error { APErrorLine(text: error) }
        } actions: {
            Button(bill == nil ? "Add bill" : "Save") { Task { await save() } }
                .buttonStyle(APPrimaryButtonStyle(busy: busy))
                .disabled(busy || amount.isEmpty || (bill == nil && name.trimmingCharacters(in: .whitespaces).isEmpty))
            if let bill = bill {
                // O-10a: any bill can come off, found or added.
                APQuietButton(title: "Remove bill", tone: Pearl.danger, identifier: "remove-bill") {
                    Task { await remove(bill) }
                }
                .disabled(busy)
            }
        }
        .sheet(isPresented: $when) {
            PearlSheet {
                APSheetTitle(title: "How often") { when = false }
                APCard {
                    pickerRow("Repeats", selection: $how,
                              options: ["weekly", "biweekly", "monthly", "bimonthly", "quarterly", "semiannual", "annual"])
                    APSeparator(afterFace: false)
                    // G0-DateSheet DP-02: the Pearl date sheet, today onward.
                    PearlDateRow(label: "Next payment", title: "When is it due next?", date: $next,
                                 range: .todayOnward)
                }
            } footer: {
                Button("Done") { when = false }.buttonStyle(APPrimaryButtonStyle())
            }
        }
        .sheet(isPresented: $more) {
            PearlSheet {
                APSheetTitle(title: "More options") { more = false }
                APCard {
                    FieldRow(label: "Your share", text: $share, prompt: "100%").keyboardType(.numberPad)
                        .padding(.horizontal, 16).padding(.vertical, 8)
                    if !categories.isEmpty {
                        APSeparator(afterFace: false)
                        namedPicker("Category", selection: $category, options: categories, placeholder: "Choose")
                    }
                    APSeparator(afterFace: false)
                    APToggleRow(title: "Amount changes each month", isOn: $varies)
                    if let counted = counted {
                        APSeparator(afterFace: false)
                        APToggleRow(title: "Count this bill", isOn: counted)
                    }
                }
            } footer: {
                Button("Done") { more = false }.buttonStyle(APPrimaryButtonStyle())
            }
        }
        .task {
            if app.categories.isEmpty { await app.loadCategories() }
            categories = app.categories.filter { ["essentials", "lifestyle"].contains($0.group ?? "lifestyle") }.map(\.name)
        }
        .onAppear {
            guard let bill = bill else { return }
            name = bill.name
            amount = String(format: "%.2f", bill.full ?? bill.amount)
            share = "\(bill.share ?? 100)"
            category = bill.category ?? ""
            how = bill.cadence
            varies = bill.varies ?? false
            if let n = bill.next, let d = isoDay.date(from: String(n.prefix(10))) { next = d }
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["name": name, "amount": amount.replacingOccurrences(of: "$", with: ""),
                                   "cadence": how, "next": isoDay.string(from: next), "varies": varies,
                                   "share": share.replacingOccurrences(of: "%", with: "")]
        if !category.isEmpty { body["category"] = category }
        do {
            let reply: IncomeBills
            if let bill = bill {
                let key = bill.key  // plain: APIClient encodes it (TEST-33)
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
            let key = bill.key  // plain: APIClient encodes it (TEST-33)
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
    /// The centred title over the sheet ("Edit bill", "Your pay").
    var heading: String? = nil
    let close: () -> Void
    @ViewBuilder var content: () -> Content
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    if let heading = heading {
                        APSheetTitle(title: heading, close: close).padding(.top, 6)
                    }
                    HStack(alignment: .center, spacing: 12) {
                        IconBubble(symbol: symbol, size: 44)
                        VStack(alignment: .leading, spacing: 0) {
                            Text(title).font(Nacre.title2).foregroundColor(Pearl.ink)
                            Text(subtitle).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 8)
                        if heading == nil { PearlCloseButton(action: close) }
                    }
                    content()
                }
                .padding(16)
                .sheetPart()
            }
            VStack(spacing: 12, content: actions).padding(.horizontal, 16).padding(.bottom, 8)
                .sheetPart()
        }
        .foregroundColor(Pearl.ink)
        .background(SheetBackground())
    }
}

/// G6-PayEdit: the centred title with its close, the face, name and line
/// (kit `.who`) for one that exists, the fields, and the actions riding
/// above the keyboard.
struct AmountSheet<Content: View, Actions: View>: View {
    let heading: String
    var name: String? = nil
    var sub: String? = nil
    let close: () -> Void
    @ViewBuilder var content: () -> Content
    @ViewBuilder var actions: () -> Actions

    var body: some View {
        VStack(spacing: 0) {
            ScrollView {
                VStack(alignment: .leading, spacing: 14) {
                    APSheetTitle(title: heading, close: close).padding(.top, 6)
                    if let name = name {
                        HStack(spacing: 12) {
                            CFRing(name: name, size: 44)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(name).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(2)
                                if let sub = sub {
                                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1)
                                }
                            }
                            .frame(maxWidth: .infinity, alignment: .leading)
                        }
                        .accessibilityElement(children: .combine)
                    }
                    content()
                }
                .padding(16)
            }
            .scrollDismissesKeyboard(.interactively)
            VStack(spacing: 12, content: actions).padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 8)
        }
        .foregroundColor(Pearl.ink)
        .background(SheetBackground())
    }
}

/// "Monthly · next Dec 1", centred in `link` under the amount; it opens
/// how often and when.
struct WhenLine: View {
    let text: String
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            Text(text).font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote))
                .foregroundColor(Pearl.link)
                .frame(maxWidth: .infinity, minHeight: 32)
                .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityHint("Changes how often and when")
        .accessibilityIdentifier("when-line")
    }
}

extension View {
    /// The white rounded card fields sit in, inside a sheet.
    func sheetCard() -> some View {
        apCard()
    }
}

/// "Repeats   Monthly ›": opens a Pearl sheet of radio rows (house rule,
/// coordinator 2026-11-18: no stock menu; same pattern as quiet hours).
func pickerRow(_ label: String, selection: Binding<String>, options: [String]) -> some View {
    ChoiceSheetRow(label: label, selection: selection, options: options, words: { cadence($0) })
}

/// "Goes into   TD Chequing ›", "Category   Choose ›": the same Pearl sheet.
func namedPicker(_ label: String, selection: Binding<String>, options: [String], placeholder: String = "Choose") -> some View {
    ChoiceSheetRow(label: label, selection: selection, options: options, placeholder: placeholder, words: { $0 })
}

/// A key-value row whose value opens a Pearl sheet of radio rows; a tap picks at once.
struct ChoiceSheetRow: View {
    let label: String
    @Binding var selection: String
    let options: [String]
    var placeholder = "Choose"
    let words: (String) -> String
    @State private var open = false

    var body: some View {
        Button { open = true } label: {
            APKeyValueRow(key: label, chevron: true) {
                Text(selection.isEmpty ? placeholder : words(selection))
                    .foregroundColor(Pearl.muted).lineLimit(1)
            }
        }
        .buttonStyle(.plain)
        .accessibilityLabel(label)
        .accessibilityValue(selection.isEmpty ? placeholder : words(selection))
        .accessibilityIdentifier("choice-\(label)")
        .sheet(isPresented: $open) {
            PearlSheet {
                APSheetTitle(title: label) { open = false }
                APCard {
                    ForEach(Array(options.enumerated()), id: \.element) { i, o in
                        if i > 0 { APSeparator(afterFace: false) }
                        APChoiceRow(title: words(o), selected: o == selection) {
                            selection = o
                            open = false
                        }
                    }
                }
            }
        }
    }
}
