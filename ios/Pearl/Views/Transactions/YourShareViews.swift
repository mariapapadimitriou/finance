import SwiftUI

// TEST-18 (THL-303's extension; product owner 2026-11-10; Figma section 18
// 1237:23124, build note 1238:25742): Not sure yet with you in it. Your own
// row on the split card, its options (S-40y), and "What was your share?"
// (S-47a–e), which turns the split into a set split. Anyone who has paid is
// locked at what they paid.

/// S-40y: your ••• on a Not sure yet split.
struct YouOptionsSheet: View {
    let t: Transaction
    let onClose: () -> Void
    let onSetShare: () -> Void

    var body: some View {
        APSheet {
            APSheetHeader(face: "Me", overline: "\(t.merchant) · Not sure yet", title: "You",
                             sub: "Your share isn’t set", close: onClose)
            APOptionCard {
                APOptionRow(symbol: "banknote", title: "Set your share",
                               sub: "Pearl gives what’s left to whoever hasn’t paid", prominent: true,
                               action: onSetShare)
            }
        }
    }
}

/// S-47a–e: "What was your share?" Type what you had; what's left (the
/// purchase − linked paybacks − your share) goes to whoever hasn't paid:
/// all of it to one person (S-47b), split evenly and editable between
/// several (S-47c, S-47d). More than what's left is an error (S-47e).
struct YourShareSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let api: APIClient
    let onClose: () -> Void
    /// S-47f: Options on the lock toast; the page opens that person's S-40u.
    var onPersonOptions: ((String) -> Void)? = nil
    /// The toast ("Alex owes you $28.00") and the server's Undo.
    let onSaved: (String, JSONValue?) -> Void

    @State private var lockToast: PearlToast.Model?
    /// S-47g: "Who paid you back", from the folded Paid back line.
    @State private var whoPaid = false
    @State private var mine = ""
    @State private var theirs: [String: String] = [:]
    /// S-47c (product owner 2026-11-10, S-47c2 rejected): Evenly, Amounts,
    /// % or Shares, each of what's left, across the people who haven't paid.
    @State private var method = "even"
    @State private var weights: [String: String] = [:]
    @State private var busy = false
    @State private var failed: String?
    @FocusState private var typing: String?

    private static let me = "\u{0}me"

    private var base: Double { split.base ?? t.fullAmount ?? t.amount }
    private var paidPeople: [Transaction.Splitting.Person] { split.people.filter { $0.paid >= 0.005 } }
    private var unpaid: [Transaction.Splitting.Person] { split.people.filter { $0.paid < 0.005 } }
    private var paidCents: Int { paidPeople.reduce(0) { $0 + cents($1.paid) } }
    private var roomCents: Int { max(cents(base) - paidCents, 0) }

    private func cents(_ d: Double) -> Int { Int((d * 100).rounded()) }
    private func parse(_ s: String) -> Double? {
        Double(s.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")
            .trimmingCharacters(in: .whitespaces))
    }

    private var mineCents: Int? { parse(mine).map(cents) }
    private var tooMuch: Bool { (mineCents ?? 0) > roomCents }
    /// What the unpaid people share once her share is typed.
    private var leftCents: Int { max(roomCents - (mineCents ?? 0), 0) }

    /// S-47c: evenly by default, the odd cent to the first who hasn't paid.
    private func evenly() -> [String: Int] {
        guard !unpaid.isEmpty else { return [:] }
        let each = leftCents / unpaid.count
        var out: [String: Int] = [:]
        for (i, p) in unpaid.enumerated() {
            out[p.name] = each + (i < leftCents - each * unpaid.count ? 1 : 0)
        }
        return out
    }

    private func number(_ name: String, default d: Double) -> Double {
        weights["\(method)\u{0}\(name)"].flatMap(parse) ?? d
    }

    /// Each unpaid person's cents of what's left, by the method chosen.
    private var allotted: [String: Int] {
        guard unpaid.count > 1 else { return Dictionary(uniqueKeysWithValues: unpaid.map { ($0.name, leftCents) }) }
        switch method {
        case "amount":
            return Dictionary(uniqueKeysWithValues: unpaid.map { p in
                (p.name, theirs[p.name].flatMap(parse).map(cents) ?? (evenly()[p.name] ?? 0)) })
        case "percent":
            // % is of the whole purchase (designBOT, 2026-11-10): her share and
            // the payers are fixed; the unpaid type theirs.
            var out: [String: Int] = [:]
            for p in unpaid {
                let pct = number(p.name, default: defaultPercent)
                out[p.name] = Int((Double(cents(base)) * pct / 100).rounded(.down))
            }
            // Within a cent a person of adding up is rounding: the odd cents
            // go one each from the top.
            // (0.01% of the whole can be more than a cent.)
            var odd = leftCents - out.values.reduce(0, +)
            if odd > 0 && odd <= unpaid.count * (cents(base) / 10000 + 1) {
                var i = 0
                while odd > 0 { out[unpaid[i % unpaid.count].name, default: 0] += 1; odd -= 1; i += 1 }
            }
            return out
        case "shares":
            // Shares divide only what's left, across the unpaid.
            let w = unpaid.map { number($0.name, default: 1) }
            let whole = w.reduce(0, +)
            guard whole > 0 else { return [:] }
            var out: [String: Int] = [:]
            for (p, x) in zip(unpaid, w) { out[p.name] = Int((Double(leftCents) * x / whole).rounded(.down)) }
            var odd = leftCents - out.values.reduce(0, +)
            var i = 0
            while odd > 0 { out[unpaid[i % unpaid.count].name, default: 0] += 1; odd -= 1; i += 1 }
            return out
        default:
            return evenly()
        }
    }

    private func theirCents(_ name: String) -> Int { allotted[name] ?? 0 }

    /// An even part of what's left, as a percent of the whole purchase.
    private var defaultPercent: Double {
        guard !unpaid.isEmpty, cents(base) > 0 else { return 0 }
        return (Double(leftCents) / Double(unpaid.count) / Double(cents(base)) * 10000).rounded(.down) / 100
    }

    private var gapCents: Int {
        leftCents - unpaid.reduce(0) { $0 + theirCents($1.name) }
    }

    private var ready: Bool { mineCents != nil && !tooMuch && gapCents == 0 && !busy }

    var body: some View {
        // TEST-16: the number pad's Done is the footer's own (TEST-37).
        NavigationStack {
            sheet
                .toolbar(.hidden, for: .navigationBar)
                // S-47f: "Priya’s $25.00 is linked…", with Options.
                .overlay(alignment: .top) {
                    if let m = lockToast {
                        PearlToast(model: m) { withAnimation { lockToast = nil } }.padding(.top, 8)
                    }
                }
        }
    }

    /// S-47f: why a locked row can't change, and Options to unlink it.
    private func showLock(_ p: Transaction.Splitting.Person) {
        let words = "\(possessive(p.name)) \(Format.amount(p.paid)) is linked. Unlink the payback to change \(possessive(p.name)) share."
        withAnimation {
            lockToast = PearlToast.Model(text: words, action: onPersonOptions == nil ? nil : "Options", failed: true,
                                         run: onPersonOptions.map { open in { lockToast = nil; open(p.name) } })
        }
    }

    /// G2-BShare (S-47a–e; Rethought, approved 2026-11-18): what's left is
    /// one big number with a one-line breakdown; the WHAT'S LEFT table and
    /// the Allowance explainer are gone.
    private var sheet: some View {
        APSheet(dismissDisabled: busy) {
            APSheetHeader(heading: "What was your share?", close: onClose)
                .disabled(busy)
            leftHero
            Text(unpaid.count == 1
                 ? "Pearl gives what’s left to \(unpaid[0].name), who hasn’t paid yet."
                 : "Pearl splits what’s left between \(Format.andList(unpaid.map(\.name))).")
                .font(Nacre.body).foregroundColor(Pearl.ink)
                .padding(.horizontal, 4)
                .fixedSize(horizontal: false, vertical: true)
            field
            if unpaid.count > 1 && !tooMuch { splitLeft }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again"
                              : unpaid.count == 1 && mineCents != nil && !tooMuch
                                ? "Save · \(unpaid[0].name) owes \(Format.amount(Double(leftCents) / 100))" : "Save",
                              busy: busy, busyLabel: "Saving…", secondary: "Cancel",
                              onPrimary: { Task { await save() } }, onSecondary: onClose)
                .disabled(!ready)
                // TEST-37: Done above the number pad, Save above both.
                .keyboardDoneFooter { typing = nil }
        }
        .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { typing = Self.me } }
        .sheet(isPresented: $whoPaid) {
            WhoPaidBackSheet(merchant: t.merchant, payers: paidPeople, onClose: { whoPaid = false }) { name in
                whoPaid = false
                // Each row opens that person's S-40u, where Unlink is.
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { onPersonOptions?(name) }
            }
        }
    }

    /// "Left for you and Alex", $45.00, then "$120.00 · 🔒 $75.00 paid back
    /// by Priya, Sam and Jo". The locked line opens who paid (S-47f / S-47g).
    private var leftHero: some View {
        VStack(spacing: 0) {
            Text(unpaid.isEmpty ? "Left for you" : "Left for you and \(Format.andList(unpaid.map(\.name)))")
                .font(Nacre.subheadline).foregroundColor(Pearl.muted)
                .multilineTextAlignment(.center)
            Text(Format.amount(Double(roomCents) / 100))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle)).tracking(-0.88)
                .foregroundColor(Pearl.ink).pearlAmountFit()
            if !paidPeople.isEmpty {
                Button { if paidPeople.count == 1 { showLock(paidPeople[0]) } else { whoPaid = true } } label: {
                    (Text("\(Format.amount(base)) · ") + Text(Image(systemName: "lock")) + Text(" \(Format.amount(Double(paidCents) / 100)) paid back by \(Format.andList(paidPeople.map(\.name)))"))
                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                        .multilineTextAlignment(.center)
                        .fixedSize(horizontal: false, vertical: true)
                }
                .buttonStyle(.plain)
                .accessibilityLabel("\(Format.amount(base)), \(Format.amount(Double(paidCents) / 100)) paid back by \(Format.andList(paidPeople.map(\.name))), locked")
                .accessibilityHint(paidPeople.count == 1 ? "Says how to change it" : "Shows who paid you back")
            } else {
                Text(Format.amount(base)).font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
        }
        .frame(maxWidth: .infinity)
        .padding(.top, 4)
    }

    /// S-47c: HOW TO SPLIT WHAT'S LEFT, the method, each who hasn't paid, and
    /// "Adds up to $120.00 ✓".
    private var splitLeft: some View {
        VStack(alignment: .leading, spacing: 12) {
            APSheetLabel(text: "How to split what’s left")
            APSegments(options: [("even", "Evenly"), ("amount", "Amounts"), ("percent", "%"), ("shares", "Shares")],
                       selection: $method)
            APOptionCard {
                ForEach(Array(unpaid.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { APSeparator() }
                    unpaidRow(p)
                }
            }
            if mineCents != nil {
                APTotalLine(text: gapCents == 0 ? "Adds up to \(Format.amount(base)) \u{2713}"
                                : gapCents > 0 ? "\(Format.amount(Double(gapCents) / 100)) left to assign"
                                : "That’s \(Format.amount(Double(-gapCents) / 100)) too much",
                            tone: gapCents == 0 ? .good : gapCents > 0 ? .quiet : .over)
            }
        }
    }

    private var field: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Your share").font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 4)
            HStack(spacing: 8) {
                Text("$").font(Nacre.headline).foregroundColor(Pearl.muted).accessibilityHidden(true)
                TextField("", text: $mine, prompt: Text("0.00").foregroundColor(Pearl.muted))
                    .font(Nacre.headline).foregroundColor(Pearl.ink).monospacedDigit()
                    .tint(Pearl.action).keyboardType(.decimalPad)
                    .focused($typing, equals: Self.me)
                    .accessibilityLabel("Your share")
                    .accessibilityIdentifier("your-share")
            }
            .padding(.horizontal, 14).frame(minHeight: 50)
            .wellStyle(focused: typing == Self.me, error: tooMuch)
            .disabled(busy)
            // S-47e: "Your share can be up to $45.00." S-47b: "Alex owes you $28.00".
            if tooMuch {
                Text("Your share can be up to \(Format.amount(Double(roomCents) / 100)).")
                    .font(Nacre.footnote).foregroundColor(Pearl.danger).padding(.horizontal, 4)
                    .fixedSize(horizontal: false, vertical: true)
            } else if unpaid.count == 1, mineCents != nil {
                Text("\(unpaid[0].name) owes you \(Format.amount(Double(leftCents) / 100))")
                    .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                    .frame(maxWidth: .infinity).padding(.top, 8)
            }
        }
    }

    /// S-47c: one who hasn't paid, with their part of what's left.
    private func unpaidRow(_ p: Transaction.Splitting.Person) -> some View {
        HStack(spacing: 12) {
            APFace(name: p.name)
            VStack(alignment: .leading, spacing: 2) {
                Text(p.name).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(method == "percent" || method == "shares"
                     ? "Nothing paid yet · owes \(Format.amount(Double(theirCents(p.name)) / 100))" : "Nothing paid yet")
                    .font(Nacre.subheadline).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if method == "even" {
                Text(Format.amount(Double(theirCents(p.name)) / 100))
                    .font(Nacre.headline).monospacedDigit().foregroundColor(Pearl.ink)
            } else {
            TextField("", text: fieldBinding(p.name), prompt: Text(prompt(p.name)).foregroundColor(Pearl.ink))
                .font(Nacre.headline).monospacedDigit().multilineTextAlignment(.trailing)
                .keyboardType(method == "shares" ? .numberPad : .decimalPad)
                .focused($typing, equals: p.name)
                .frame(width: 92, height: 36).padding(.horizontal, 8)
                .wellStyle(focused: typing == p.name)
                .accessibilityLabel("\(p.name) \(method == "percent" ? "percent" : method == "shares" ? "shares" : "amount")")
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60)
        // TEST-27: on Evenly the row is one element, "Jo, Nothing paid yet,
        // $26.00", so the spoken words are the visible ones.
        .accessibilityElement(children: method == "even" ? .combine : .contain)
    }

    private func fieldBinding(_ name: String) -> Binding<String> {
        if method == "amount" { return Binding(get: { theirs[name] ?? "" }, set: { theirs[name] = $0 }) }
        let key = "\(method)\u{0}\(name)"
        return Binding(get: { weights[key] ?? "" }, set: { weights[key] = $0 })
    }

    private func prompt(_ name: String) -> String {
        switch method {
        case "percent": return Self.plain(defaultPercent) + "%"
        case "shares": return "1"
        default: return Format.amount(Double(evenly()[name] ?? 0) / 100)
        }
    }

    private static func plain(_ d: Double) -> String {
        d == d.rounded() ? String(Int(d)) : String(format: "%.2f", d)
    }

    private func save() async {
        guard ready, let you = mineCents else { return }
        busy = true
        defer { busy = false }
        var people: [[String: Any]] = paidPeople.map { ["name": $0.name, "amount": Double(cents($0.paid)) / 100] }
        people += unpaid.map { ["name": $0.name, "amount": Double(theirCents($0.name)) / 100] }
        let body: [String: Any] = ["mode": "amount", "include_me": true, "you": Double(you) / 100,
                                   "your_share": true, "people": people, "watch": true]
        struct Reply: Decodable { let undo: JSONValue? }
        do {
            let reply: Reply = try await api.put("api/transactions/\(t.id)/split", body)
            failed = nil
            let owed = Double(leftCents) / 100
            onSaved(unpaid.count == 1 ? "\(unpaid[0].name) owes you \(Format.amount(owed))"
                    : "\(Format.andList(unpaid.map(\.name))) owe you \(Format.amount(owed))", reply.undo)
        } catch let e as APIError {
            if case .server = e { failed = e.localizedDescription } else { failed = "Couldn’t save your share. Nothing changed. Try again." }
        } catch {
            failed = "Couldn’t save your share. Nothing changed. Try again."
        }
    }
}

/// S-47g (TEST-18, section 20 1266:28020): "Who paid you back". Each payer
/// is locked; a row opens that person's S-40u, where Unlink is.
struct WhoPaidBackSheet: View {
    let merchant: String
    let payers: [Transaction.Splitting.Person]
    let onClose: () -> Void
    let onOpen: (String) -> Void

    var body: some View {
        // G2-BShare S-47g: the title centred with ✕, one quiet line, the
        // payers, then Back to your share.
        APSheet {
            APSheetHeader(heading: "Who paid you back", close: onClose)
            Text("Linked payments are locked. To change someone’s share, unlink their payback.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .padding(.horizontal, 4)
                .fixedSize(horizontal: false, vertical: true)
            APOptionCard {
                ForEach(Array(payers.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { APSeparator() }
                    row(p)
                }
            }
            Button("Back to your share", action: onClose)
                .buttonStyle(NacreTextButtonStyle())
                .frame(maxWidth: .infinity)
        }
    }

    private func row(_ p: Transaction.Splitting.Person) -> some View {
        // S-47g: "e-Transfer · Nov 14 · locked", "Cash · Nov 15 · locked".
        let cash = (p.cash ?? 0) >= p.paid - 0.005
        let how = cash ? "Cash" : (p.links?.first.map { PersonOptionsSheet.word($0) } ?? "Paid back")
        let sub = [how, p.paidOn.map { Format.short($0) }, "locked"]
            .compactMap { $0 }.joined(separator: " · ")
        return Button { onOpen(p.name) } label: {
            HStack(spacing: 12) {
                APFace(name: p.name, size: 40)
                VStack(alignment: .leading, spacing: 0) {
                    Text(p.name).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text(Format.amount(p.paid)).font(Nacre.headline).monospacedDigit()
                    .foregroundColor(Pearl.moneyIn).pearlAmountFit()
                APChevron()
            }
            .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("\(p.name), \(sub), \(Format.amount(p.paid))")
        .accessibilityHint("Opens \(possessive(p.name)) options, where you can unlink it")
    }
}
