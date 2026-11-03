import SwiftUI

// THL-291, the purchase side: split it with people (S-02, S-03, S-15 to
// S-18), see who still owes what (S-04, S-05, S-19), mark someone paid back
// by bank deposit or in cash (S-06, S-29, S-30), remind them (S-07) or let
// the rest go (S-08, S-20).

/// S-02 then S-03: who it was with, then how to split it.
@MainActor
struct SplitSheet: View {
    let t: Transaction
    let api: APIClient
    /// Names to offer: people she's split with before.
    let recent: [String]
    let onSaved: (String) -> Void
    /// From a deposit (S-24): who it's with already, so it opens on how to
    /// split, under "Dad's share" with "Split and link".
    var title: String? = nil
    var saveTitle = "Save"

    @Environment(\.dismiss) private var dismiss
    @State private var people: [String]
    @State private var withMe = true
    @State private var step = 0
    @State private var typed = ""
    @State private var mode = "even"
    @State private var values: [String: String] = [:]
    @State private var busy = false
    @State private var error: String?

    private static let me = "\u{0}me"

    init(t: Transaction, api: APIClient, recent: [String], with names: [String]? = nil,
         title: String? = nil, saveTitle: String = "Save", onSaved: @escaping (String) -> Void) {
        self.t = t
        self.api = api
        self.recent = recent
        self.onSaved = onSaved
        self.title = title
        self.saveTitle = saveTitle
        let existing = t.splitting?.people.map(\.name) ?? []
        _people = State(initialValue: names ?? existing)
        _step = State(initialValue: names == nil ? 0 : 1)
        _withMe = State(initialValue: t.splitting.map { $0.you >= 0.005 } ?? true)
        if let s = t.splitting, let m = s.mode, m != "even" {
            _mode = State(initialValue: m == "amount" ? "amount" : m)
            var v: [String: String] = [Self.me: Self.plain(s.you)]
            for p in s.people { v[p.name] = Self.plain(p.amount) }
            _values = State(initialValue: m == "amount" ? v : [:])
        }
    }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: step == 0 ? "Who was it with?" : (title ?? "How to split")) { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: t.merchant, amount: Format.money(t), tone: t.tone, sub: nil)
                    if step == 0 { who } else { how }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            footer
        }
        .background(SheetBackground())
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
    }

    // MARK: S-02 Who was it with?

    private var who: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                TextField("", text: $typed, prompt: Text("Search or add a name").foregroundColor(Pearl.muted))
                    .font(Nacre.body).textInputAutocapitalization(.words).autocorrectionDisabled()
                    .submitLabel(.done).onSubmit(addTyped)
                if !typed.trimmingCharacters(in: .whitespaces).isEmpty {
                    Button("Add", action: addTyped).font(Nacre.textButton).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            let names = choices
            if !names.isEmpty {
                Text("RECENT").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted).padding(.horizontal, 16)
                GlassCard {
                    ForEach(Array(names.enumerated()), id: \.element) { i, name in
                        if i > 0 { RowSeparator(inset: 64) }
                        Button { toggle(name) } label: {
                            HStack(spacing: 12) {
                                Initials(name: name, size: 34)
                                Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                                Spacer()
                                Image(systemName: people.contains(name) ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 22))
                                    .foregroundColor(people.contains(name) ? Pearl.action : Pearl.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 54).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(people.contains(name) ? .isSelected : [])
                    }
                }
            }
            GlassCard {
                Toggle(isOn: $withMe) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text("I had some too").font(Nacre.body).foregroundColor(Pearl.ink)
                        Text("Turn off if it was all for them").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    }
                }
                .tint(Pearl.action)
                .padding(.horizontal, 16).padding(.vertical, 12)
            }
        }
    }

    private var choices: [String] {
        var out = people
        for n in recent where !out.contains(n) { out.append(n) }
        let q = typed.trimmingCharacters(in: .whitespaces)
        return q.isEmpty ? out : out.filter { $0.localizedCaseInsensitiveContains(q) }
    }

    private func addTyped() {
        let name = typed.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        if !people.contains(name) { people.append(name) }
        typed = ""
    }

    private func toggle(_ name: String) {
        if let i = people.firstIndex(of: name) { people.remove(at: i) } else { people.append(name) }
    }

    // MARK: S-03 How to split

    private var rows: [String] { (withMe ? [Self.me] : []) + people }

    private var how: some View {
        VStack(alignment: .leading, spacing: 10) {
            Picker("", selection: $mode) {
                Text("Evenly").tag("even")
                Text("Amounts").tag("amount")
                Text("%").tag("percent")
                Text("Shares").tag("shares")
            }
            .pickerStyle(.segmented)
            .onChange(of: mode) { _ in values = [:] }
            GlassCard {
                ForEach(Array(rows.enumerated()), id: \.element) { i, key in
                    if i > 0 { RowSeparator(inset: 64) }
                    HStack(spacing: 12) {
                        Initials(name: key == Self.me ? "Me" : key, size: 34)
                        Text(label(key)).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                        Spacer(minLength: 8)
                        if mode == "even" {
                            Text(Format.amount(evenAmount(key))).font(Nacre.body).monospacedDigit()
                                .foregroundColor(Pearl.ink)
                        } else {
                            TextField("", text: binding(key), prompt: Text(placeholder(key)).foregroundColor(Pearl.muted))
                                .font(Nacre.body).monospacedDigit().multilineTextAlignment(.trailing)
                                .keyboardType(mode == "shares" ? .numberPad : .decimalPad)
                                .frame(width: 92, height: 36)
                                .padding(.horizontal, 8)
                                .background(RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(0.8)))
                                .overlay(RoundedRectangle(cornerRadius: 10)
                                    .strokeBorder(gapCents != 0 && mode == "amount" ? Pearl.action : Nacre.separator, lineWidth: 1))
                                .accessibilityLabel("\(label(key)) \(mode == "percent" ? "percent" : mode == "shares" ? "shares" : "amount")")
                        }
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                }
            }
            Group {
                if gapCents == 0 {
                    Text(addsUp).foregroundColor(Nacre.teal)
                } else {
                    VStack(spacing: 8) {
                        Text(gapWords).foregroundColor(Pearl.moneyOut)
                        if mode == "amount" && gapCents > 0 {
                            Button("Split the rest evenly", action: splitRest)
                                .font(Nacre.textButton).foregroundColor(Pearl.action)
                        }
                    }
                }
            }
            .font(Nacre.footnote).frame(maxWidth: .infinity)
        }
    }

    private func label(_ key: String) -> String {
        guard key == Self.me else { return key }
        if mode == "shares", gapCents == 0, let a = shareAmounts[key] { return "You · \(Format.amount(a))" }
        return "You"
    }

    private func placeholder(_ key: String) -> String {
        switch mode {
        case "percent": return "0%"
        case "shares": return "1"
        default: return "$0.00"
        }
    }

    private func binding(_ key: String) -> Binding<String> {
        Binding(get: { values[key] ?? "" }, set: { values[key] = $0 })
    }

    private func number(_ key: String) -> Double {
        Double((values[key] ?? "").replacingOccurrences(of: "$", with: "").replacingOccurrences(of: "%", with: "")
            .replacingOccurrences(of: ",", with: "")) ?? (mode == "shares" ? 1 : 0)
    }

    private var totalCents: Int { Int((t.fullAmount ?? t.amount) * 100 + 0.5) }

    /// Evenly: theirs rounded down, the odd cent yours (or the first's).
    private func evenAmount(_ key: String) -> Double {
        let n = max(rows.count, 1)
        let each = totalCents / n, odd = totalCents - each * n
        guard let i = rows.firstIndex(of: key) else { return 0 }
        return Double(each + (i == 0 ? odd : 0)) / 100
    }

    private var shareAmounts: [String: Double] {
        let weights = rows.map { number($0) }
        let whole = weights.reduce(0, +)
        guard whole > 0 else { return [:] }
        var out: [String: Double] = [:]
        var given = 0
        for (k, w) in zip(rows, weights) where k != rows.first {
            let c = Int(Double(totalCents) * w / whole)
            out[k] = Double(c) / 100
            given += c
        }
        if let first = rows.first { out[first] = Double(totalCents - given) / 100 }
        return out
    }

    /// Cents still to give out ("$4.12 left to assign"); negative is too much.
    private var gapCents: Int {
        switch mode {
        case "even", "shares": return 0
        case "percent":
            return Int(((100 - rows.map { number($0) }.reduce(0, +)) * 100).rounded())
        default:
            return totalCents - rows.map { Int((number($0) * 100).rounded()) }.reduce(0, +)
        }
    }

    private var addsUp: String {
        switch mode {
        case "percent": return "Adds up to 100% ✓"
        case "shares":
            let n = rows.map { number($0) }.reduce(0, +)
            return "\(Self.plain(n)) shares · adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        default: return "Adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        }
    }

    private var gapWords: String {
        if mode == "percent" {
            let g = Double(gapCents) / 100
            return g > 0 ? "\(Self.plain(g))% left to assign" : "That’s \(Self.plain(-g))% too much"
        }
        let g = Double(abs(gapCents)) / 100
        return gapCents > 0 ? "\(Format.amount(g)) left to assign" : "That’s \(Format.amount(g)) too much"
    }

    /// The unassigned amount, shared by the rows still empty (or all).
    private func splitRest() {
        let empty = rows.filter { (values[$0] ?? "").isEmpty }
        let targets = empty.isEmpty ? rows : empty
        let each = gapCents / targets.count, odd = gapCents - each * targets.count
        for (i, k) in targets.enumerated() {
            let c = Int((number(k) * 100).rounded()) + each + (i == 0 ? odd : 0)
            values[k] = Self.plain(Double(c) / 100)
        }
    }

    static func plain(_ x: Double) -> String {
        x.rounded() == x ? String(Int(x)) : String(format: "%.2f", x)
    }

    // MARK: Save

    private var footer: some View {
        Button(step == 0 ? "Next" : saveTitle) {
            if step == 0 { addTyped(); step = 1 } else { Task { await save() } }
        }
        .buttonStyle(NacreButtonStyle(busy: busy))
        .disabled(step == 0 ? people.isEmpty && typed.trimmingCharacters(in: .whitespaces).isEmpty
                  : (gapCents != 0 || busy))
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["mode": mode, "include_me": withMe]
        switch mode {
        case "even":
            body["people"] = people.map { ["name": $0] }
        case "amount":
            body["people"] = people.map { ["name": $0, "amount": number($0)] }
            body["you"] = withMe ? number(Self.me) : 0
        case "percent":
            body["people"] = people.map { ["name": $0, "percent": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        default:
            body["people"] = people.map { ["name": $0, "shares": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        }
        do {
            let _: OK = try await api.put("api/transactions/\(t.id)/split", body)
            let n = people.count + (withMe ? 1 : 0)
            onSaved(n == 2 ? "Split with \(people[0])." : "Split \(n) ways.")
        } catch {
            self.error = error.localizedDescription
        }
    }
}

// MARK: - Who owes what (S-04, S-05, S-19, S-20)

/// The people in a split: what each owes or has paid, and what to do next.
struct SplitPeople: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onMarkPaid: (Transaction.Splitting.Person) -> Void
    let onRemind: (Transaction.Splitting.Person) -> Void
    let onLetGo: (Transaction.Splitting.Person) -> Void
    let onUndoLetGo: (Transaction.Splitting.Person) -> Void
    let onEdit: () -> Void
    let onOwed: () -> Void

    var body: some View {
        let open = split.people.filter { $0.owes >= 0.005 }
        VStack(alignment: .leading, spacing: 8) {
            Text(split.people.count > 1 ? "SPLIT \(split.people.count + (split.you >= 0.005 ? 1 : 0)) WAYS"
                 : open.isEmpty ? "PAID BACK" : "OWED TO YOU")
                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                .padding(.horizontal, 16).padding(.top, 12)
            GlassCard {
                ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { RowSeparator(inset: 64) }
                    person(p)
                }
                if let first = open.first {
                    RowSeparator(inset: 0)
                    action("Mark paid back", chevron: true) { onMarkPaid(first) }
                    RowSeparator()
                    action("Remind \(first.name)") { onRemind(first) }
                    RowSeparator()
                    action("Let it go") { onLetGo(first) }
                } else if let gone = split.people.first(where: { $0.letGo != nil }) {
                    RowSeparator(inset: 0)
                    Button { onUndoLetGo(gone) } label: {
                        VStack(alignment: .leading, spacing: 2) {
                            Text("Undo").font(Nacre.body).foregroundColor(Pearl.action)
                            Text("\(gone.name) owes you \(Format.amount((gone.letGo?.was ?? 0) - gone.paid)) again")
                                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        .frame(maxWidth: .infinity, alignment: .leading)
                        .padding(.horizontal, 16).padding(.vertical, 12).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                } else {
                    RowSeparator(inset: 0)
                    Button(action: onEdit) {
                        HStack {
                            VStack(alignment: .leading, spacing: 2) {
                                Text("Edit split").font(Nacre.body).foregroundColor(Pearl.action)
                                Text(editLine).font(Nacre.footnote).foregroundColor(Pearl.muted)
                            }
                            Spacer()
                            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                .foregroundColor(Pearl.muted)
                        }
                        .padding(.horizontal, 16).padding(.vertical, 12).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
            }
            Button("See everyone who owes you", action: onOwed)
                .font(Nacre.textButton).foregroundColor(Pearl.action)
                .frame(maxWidth: .infinity).padding(.top, 6)
        }
    }

    private var editLine: String {
        let names = (split.you >= 0.005 ? ["You"] : []) + split.people.map(\.name)
        let how = ["even": "evenly", "amount": "by amount", "percent": "by percent", "shares": "by shares"][split.mode ?? "even"] ?? ""
        return names.joined(separator: " and ") + " · " + how
    }

    private func person(_ p: Transaction.Splitting.Person) -> some View {
        HStack(spacing: 12) {
            Initials(name: p.name, size: 34)
            VStack(alignment: .leading, spacing: 4) {
                Text(p.name).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(status(p)).font(Nacre.footnote).foregroundColor(Pearl.muted)
                if p.paid >= 0.005 && p.owes >= 0.005 {
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Pearl.ink.opacity(0.1))
                            Capsule().fill(Pearl.action).frame(width: g.size.width * min(1, p.paid / max(p.amount, 0.01)))
                        }
                    }
                    .frame(height: 4)
                }
            }
            Spacer(minLength: 8)
            // What they still owe; what they paid; or what she let go.
            Text(Format.amount(p.owes >= 0.005 ? p.owes : p.letGo.map { $0.was - p.paid } ?? p.paid))
                .font(Nacre.headline).monospacedDigit()
                .foregroundColor(p.owes >= 0.005 || p.letGo != nil ? Pearl.ink : Pearl.moneyIn)
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .accessibilityElement(children: .combine)
    }

    /// "Owes you", "Paid $20.00 of $28.04", "Cash · Nov 13", "Let go · Nov 20".
    private func status(_ p: Transaction.Splitting.Person) -> String {
        if let gone = p.letGo { return "Let go · \(Format.short(gone.day))" }
        if p.owes >= 0.005 {
            return p.paid >= 0.005 ? "Paid \(Format.amount(p.paid)) of \(Format.amount(p.amount))" : "Owes you"
        }
        let how = (p.cash ?? 0) >= p.paid - 0.005 && (p.cash ?? 0) > 0 ? "Cash" : "Paid back"
        return [how, p.paidOn.map { Format.short($0) }].compactMap { $0 }.joined(separator: " · ")
    }

    private func action(_ title: String, chevron: Bool = false, _ run: @escaping () -> Void) -> some View {
        Button(action: run) {
            HStack {
                Text(title).font(Nacre.body).foregroundColor(Pearl.action)
                Spacer()
                if chevron {
                    Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 48).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
    }
}

// MARK: - Mark paid back (S-06, S-29, S-30)

@MainActor
struct MarkPaidSheet: View {
    let t: Transaction
    let person: Transaction.Splitting.Person
    let api: APIClient
    let onDone: (String) -> Void

    @Environment(\.dismiss) private var dismiss
    @State private var how = "bank"
    @State private var amount: String
    @State private var when = Date()
    @State private var finding = false
    @State private var deposits: [Candidate] = []
    /// The deposits she ticked, in the order she ticked them (S-26).
    @State private var picked: [String] = []

    /// A deposit that could pay it back, and how much of it could.
    struct Candidate: Decodable, Identifiable, Hashable {
        let id: String
        let date: String
        let merchant: String?
        let description: String?
        let amount: Double
        let accountName: String?
        let likely: Bool?
        let part: Double?

        enum CodingKeys: String, CodingKey {
            case id, date, merchant, description, amount, likely, part
            case accountName = "account_name"
        }

        var name: String { (merchant?.isEmpty == false ? merchant : description) ?? "Deposit" }
        var whole: Double { abs(amount) }
    }
    @State private var busy = false
    @State private var error: String?

    init(t: Transaction, person: Transaction.Splitting.Person, api: APIClient, onDone: @escaping (String) -> Void) {
        self.t = t
        self.person = person
        self.api = api
        self.onDone = onDone
        _amount = State(initialValue: SplitSheet.plain(person.owes))
    }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: finding ? "What paid this back?" : "Mark paid back") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if finding {
                        QuestionHeader(name: t.merchant, amount: Format.money(t), tone: t.tone,
                                       sub: Format.short(t.date))
                    } else {
                        HStack(spacing: 12) {
                            Initials(name: person.name, size: 48)
                            VStack(alignment: .leading, spacing: 2) {
                                Text(person.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                                Text("Owes \(Format.amount(person.owes))").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            }
                        }
                    }
                    if finding { depositList } else { form }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button(finding ? "Save" : how == "bank" ? "Find it" : "Mark paid back") {
                Task { await primary() }
            }
            .buttonStyle(NacreButtonStyle(busy: busy))
            .disabled(busy || (finding && picked.isEmpty))
            .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    private var form: some View {
        VStack(alignment: .leading, spacing: 12) {
            Text("HOW DID \(person.name.uppercased()) PAY?").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                .padding(.horizontal, 16)
            GlassCard {
                option("bank", "Bank deposit or e-Transfer", "Find it in your transactions")
                RowSeparator()
                option("cash", "Cash in hand", "Pearl will match it if you deposit it")
                RowSeparator()
                option("app", "Another app", "PayPal, Wise, Apple Cash…")
            }
            if how != "bank" {
                GlassCard {
                    HStack {
                        Text("Amount").font(Nacre.body).foregroundColor(Pearl.ink)
                        TextField("", text: $amount).font(Nacre.body).multilineTextAlignment(.trailing)
                            .keyboardType(.decimalPad).foregroundColor(Pearl.muted)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52)
                    RowSeparator()
                    DatePicker(selection: $when, in: ...Date(), displayedComponents: .date) {
                        Text("When").font(Nacre.body).foregroundColor(Pearl.ink)
                    }
                    .tint(Pearl.action).padding(.horizontal, 16).frame(minHeight: 52)
                }
            }
        }
    }

    private func option(_ key: String, _ title: String, _ sub: String) -> some View {
        Button { how = key } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                Spacer()
                if how == key {
                    Image(systemName: "checkmark").font(.system(size: 15, weight: .semibold)).foregroundColor(Pearl.action)
                }
            }
            .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(how == key ? .isSelected : [])
    }

    /// What each ticked deposit pays of what they owe, in the order ticked:
    /// all of it, or the part that's left (S-26's "part of $600").
    private var uses: [String: Double] {
        var left = person.owes
        var out: [String: Double] = [:]
        for id in picked {
            guard let d = deposits.first(where: { $0.id == id }), left >= 0.005 else { continue }
            let use = min(d.whole, d.part ?? d.whole, left)
            out[id] = (use * 100).rounded() / 100
            left -= use
        }
        return out
    }

    private var paying: Double { uses.values.reduce(0, +) }

    /// S-26: "DAD'S SHARE · $428.00", their deposits to tick, and how far
    /// they go towards it.
    private var depositList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(deposits.isEmpty ? "NO DEPOSITS LOOK LIKE IT YET"
                 : "\(person.name.uppercased())’S SHARE · \(Format.amount(person.amount))")
                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted).padding(.horizontal, 16)
            if !deposits.isEmpty {
                GlassCard {
                    ForEach(Array(deposits.enumerated()), id: \.element.id) { i, d in
                        if i > 0 { RowSeparator() }
                        depositRow(d)
                    }
                }
                let paid = person.paid + paying
                VStack(alignment: .leading, spacing: 6) {
                    GeometryReader { g in
                        ZStack(alignment: .leading) {
                            Capsule().fill(Pearl.ink.opacity(0.1))
                            Capsule().fill(Pearl.action)
                                .frame(width: g.size.width * min(1, paid / max(person.amount, 0.01)))
                        }
                    }
                    .frame(height: 6)
                    HStack(spacing: 14) {
                        HStack(spacing: 5) {
                            Circle().fill(Pearl.action).frame(width: 7, height: 7)
                            Text("Paid back \(Format.amount(paid))")
                        }
                        HStack(spacing: 5) {
                            Circle().fill(Pearl.ink.opacity(0.2)).frame(width: 7, height: 7)
                            Text("\(person.name)’s share \(Format.amount(person.amount))")
                        }
                    }
                    .font(Nacre.footnote).foregroundColor(Pearl.ink)
                }
                .padding(.top, 4)
                .accessibilityElement(children: .combine)
            }
        }
    }

    /// "e-Transfer from Dad · Nov 9 · part of $600 · $228.00 ✓".
    private func depositRow(_ d: Candidate) -> some View {
        let on = picked.contains(d.id)
        let use = uses[d.id]
        let how: String? = use.map { abs($0 - d.whole) < 0.005 ? "all of it" : "part of \(Format.whole(d.whole))" }
        let full = !on && person.owes - paying < 0.005
        return Button {
            if let i = picked.firstIndex(of: d.id) { picked.remove(at: i) } else { picked.append(d.id) }
        } label: {
            HStack {
                VStack(alignment: .leading, spacing: 2) {
                    Text(d.name).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                    Text([Format.short(d.date), how].compactMap { $0 }.joined(separator: " · "))
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                Spacer()
                Text(Format.amount(use ?? d.whole)).font(Nacre.headline).monospacedDigit()
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22)).foregroundColor(on ? Pearl.action : Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
            .opacity(full ? 0.5 : 1)
        }
        .buttonStyle(.plain)
        .disabled(full)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func primary() async {
        busy = true
        defer { busy = false }
        do {
            if finding {
                let linking = uses
                for id in picked {
                    guard let use = linking[id], let d = deposits.first(where: { $0.id == id }) else { continue }
                    var body: [String: Any] = ["person": person.name]
                    if use < d.whole - 0.005 { body["amount"] = use }
                    let _: OK = try await api.post("api/transactions/\(t.id)/paybacks/\(id)", body)
                }
                let total = linking.values.reduce(0, +)
                onDone(total >= person.owes - 0.005 ? "Linked. \(person.name) paid you back."
                       : "Linked. \(person.name) paid \(Format.amount(total)) of \(Format.amount(person.owes)).")
            } else if how == "bank" {
                struct Reply: Decodable { let candidates: [Lenient<Candidate>]? }
                let r: Reply = try await api.get("api/transactions/\(t.id)/paybacks")
                // Theirs first: deposits that name them, then the rest.
                let first = person.name.split(separator: " ").first.map(String.init)?.lowercased() ?? ""
                deposits = (r.candidates ?? []).compactMap { $0.value }.enumerated().sorted { a, b in
                    let x = a.element.name.lowercased().contains(first), y = b.element.name.lowercased().contains(first)
                    return x != y ? x : a.offset < b.offset
                }.map(\.element)
                picked = deposits.first(where: { $0.likely == true }).map { [$0.id] } ?? []
                finding = true
            } else {
                guard let value = Double(amount.replacingOccurrences(of: "$", with: "")), value > 0 else {
                    error = "How much did \(person.name) pay?"
                    return
                }
                let _: OK = try await api.post("api/transactions/\(t.id)/split/cash",
                                               ["name": person.name, "amount": value, "day": Format.isoDay(when)])
                onDone("\(person.name) paid \(Format.amount(value)).")
            }
            error = nil
        } catch {
            self.error = error.localizedDescription
        }
    }
}

/// S-08 Let it go? — what they owe becomes yours.
struct LetGoSheet: View {
    let person: Transaction.Splitting.Person
    let onLetGo: () -> Void
    @Environment(\.dismiss) private var dismiss

    var body: some View {
        VStack(spacing: 16) {
            SheetTitle(title: "Let it go?") { dismiss() }
            HStack(spacing: 12) {
                Initials(name: person.name, size: 48)
                VStack(alignment: .leading, spacing: 2) {
                    Text(person.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                    Text("Owes \(Format.amount(person.owes))").font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                Spacer()
            }
            .padding(.horizontal, 16)
            Text("Their \(Format.amount(person.owes)) counts as your spending instead.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink).padding(.horizontal, 16)
                .frame(maxWidth: .infinity, alignment: .leading)
            HStack(spacing: 10) {
                Button("Let it go", action: onLetGo).buttonStyle(NacreButtonStyle())
                Button("Keep waiting") { dismiss() }
                    .font(Nacre.headline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity, minHeight: 52)
                    .background(Capsule().fill(Color.white.opacity(0.85)))
                    .buttonStyle(.plain)
            }
            .padding(.horizontal, 16)
            Spacer(minLength: 0)
        }
        .frame(maxWidth: .infinity, maxHeight: .infinity, alignment: .top)
        .background(SheetBackground())
        .presentationDetents([.height(310)])
    }
}
