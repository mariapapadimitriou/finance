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
        PearlSheet {
            PearlSheetHeader(face: "Me", overline: "\(t.merchant) · Not sure yet", title: "You",
                             sub: "Your share isn’t set", close: onClose)
            PearlOptionCard {
                PearlOptionRow(symbol: "banknote", title: "Set your share",
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
    @State private var mine = ""
    @State private var theirs: [String: String] = [:]
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

    private func theirCents(_ name: String) -> Int {
        if unpaid.count == 1 { return leftCents }
        if let typed = theirs[name], let v = parse(typed) { return cents(v) }
        return evenly()[name] ?? 0
    }

    private var gapCents: Int {
        leftCents - unpaid.reduce(0) { $0 + theirCents($1.name) }
    }

    private var ready: Bool { mineCents != nil && !tooMuch && gapCents == 0 && !busy }

    var body: some View {
        // TEST-16: the number pad's Done bar needs a navigation stack.
        NavigationStack {
            sheet
                .toolbar {
                    ToolbarItemGroup(placement: .keyboard) {
                        Spacer()
                        Button("Done") { typing = nil }.tint(Pearl.action).foregroundColor(Pearl.action)
                    }
                }
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

    private var sheet: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: "Me", overline: "Your share · \(t.merchant)", title: "What was your share?",
                             close: onClose)
                .disabled(busy)
            Text(unpaid.count == 1
                 ? "Type what you had. Pearl gives what’s left to \(unpaid[0].name), who hasn’t paid yet."
                 : "Type what you had. Pearl splits what’s left between \(Format.andList(unpaid.map(\.name))).")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            field
            PearlSectionLabel(text: "What’s left")
            PearlOptionCard {
                line(t.merchant, "The whole purchase", Format.amount(base))
                if !paidPeople.isEmpty && unpaid.count > 1 {
                    // S-47c / S-47f: each payer, locked; a tap says how to change it.
                    ForEach(paidPeople) { p in
                        PearlDivider()
                        Button { showLock(p) } label: {
                            line(p.name, ["Paid back", p.paidOn.map { Format.short($0) }, "locked"]
                                    .compactMap { $0 }.joined(separator: " · "),
                                 "\u{2212}" + Format.amount(p.paid))
                                .contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityHint("Says how to change it")
                    }
                } else if !paidPeople.isEmpty {
                    PearlDivider()
                    Button { if paidPeople.count == 1 { showLock(paidPeople[0]) } } label: {
                        line("Paid back", "\(Format.andList(paidPeople.map(\.name))) · linked, locked",
                             "\u{2212}" + Format.amount(Double(paidCents) / 100))
                            .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                }
                PearlDivider()
                line("Your share", "What you had",
                     mineCents.map { "\u{2212}" + Format.amount(Double($0) / 100) } ?? "—")
                ForEach(unpaid) { p in
                    PearlDivider()
                    if unpaid.count == 1 {
                        line("\(p.name) owes you", "Hasn’t paid · gets what’s left",
                             Format.amount(Double(leftCents) / 100))
                    } else {
                        unpaidRow(p)
                    }
                }
            }
            if unpaid.count > 1 && mineCents != nil && !tooMuch {
                // S-47c / S-47d: "Adds up to $120.00 ✓" or "$13.00 left to assign".
                Text(gapCents == 0 ? "Adds up to \(Format.amount(base)) \u{2713}"
                     : gapCents > 0 ? "\(Format.amount(Double(gapCents) / 100)) left to assign"
                     : "That’s \(Format.amount(Double(-gapCents) / 100)) too much")
                    .font(Nacre.footnote).foregroundColor(gapCents == 0 ? Nacre.teal : Pearl.ink)
                    .frame(maxWidth: .infinity)
            }
            InfoNote(text: unpaid.count == 1
                     ? "Your Allowance doesn’t change now. When \(unpaid[0].name) pays, your \(mineCents.map { Format.amount(Double($0) / 100) } ?? "share") is what stays counted."
                     : "Your Allowance doesn’t change now. As they pay, it goes up; your share is what stays counted.")
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again"
                              : unpaid.count == 1 && mineCents != nil && !tooMuch
                                ? "Save · \(unpaid[0].name) owes \(Format.amount(Double(leftCents) / 100))" : "Save",
                              busy: busy, busyLabel: "Saving…", secondary: "Cancel",
                              onPrimary: { Task { await save() } }, onSecondary: onClose)
                .disabled(!ready)
        }
        .onAppear { DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { typing = Self.me } }
    }

    private var field: some View {
        VStack(alignment: .leading, spacing: 6) {
            Text("Your share").font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
            TextField("", text: $mine, prompt: Text("$0.00").foregroundColor(Pearl.muted))
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink).keyboardType(.decimalPad)
                .focused($typing, equals: Self.me)
                .padding(.horizontal, 14).frame(minHeight: 50)
                .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.card))
                .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous)
                    .strokeBorder(tooMuch || typing == Self.me ? Pearl.action : Pearl.border,
                                  lineWidth: tooMuch || typing == Self.me ? 1.5 : 1))
                .accessibilityLabel("Your share")
                .accessibilityIdentifier("your-share")
                .disabled(busy)
            // S-47e: more than what's left; S-47a: not typed yet.
            Text(tooMuch ? "Your share can be up to \(Format.amount(Double(roomCents) / 100))"
                 : mineCents == nil ? "You can leave it and set it later." : "")
                .font(Pearl.text(.footnote)).foregroundColor(tooMuch ? Pearl.action : Pearl.muted)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    private func line(_ title: String, _ sub: String, _ value: String) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(value).font(Pearl.text(.headline, .medium)).monospacedDigit().foregroundColor(Pearl.ink)
        }
        .padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    /// S-47c: one who hasn't paid, with their part of what's left.
    private func unpaidRow(_ p: Transaction.Splitting.Person) -> some View {
        HStack(spacing: 12) {
            VStack(alignment: .leading, spacing: 2) {
                Text(p.name).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text("Nothing paid yet").font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            Spacer(minLength: 8)
            TextField("", text: Binding(get: { theirs[p.name] ?? "" }, set: { theirs[p.name] = $0 }),
                      prompt: Text(Format.amount(Double(evenly()[p.name] ?? 0) / 100)).foregroundColor(Pearl.ink))
                .font(Pearl.text(.headline)).monospacedDigit().multilineTextAlignment(.trailing)
                .keyboardType(.decimalPad)
                .focused($typing, equals: p.name)
                .frame(width: 92, height: 36).padding(.horizontal, 8)
                .background(RoundedRectangle(cornerRadius: 10).fill(Pearl.card))
                .overlay(RoundedRectangle(cornerRadius: 10)
                    .strokeBorder(typing == p.name ? Pearl.action : Pearl.border, lineWidth: typing == p.name ? 1.5 : 1))
                .accessibilityLabel("\(p.name) amount")
        }
        .padding(.vertical, 8)
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
