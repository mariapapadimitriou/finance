import SwiftUI

// Profile › Accounts: joint, merging and added by hand (Pearl iOS Handoff
// File, Pearl app page, section "Joint, merging & added by hand"):
//
// AM-08 who a joint account is shared with, and how its purchases count
//       (THL-172, THL-217)
// AM-09 "Same account twice?": combine two copies of one account (THL-208)
// AM-10 add a balance by hand, with its last four digits (THL-226)

extension AccountsOverview.Account {
    /// Has transactions of its own: a linked or imported account, not a
    /// balance she added by hand (finance/merge.py has nothing to merge there).
    var hasHistory: Bool { status != "manual" || (transactions ?? 0) > 0 }

    /// The accounts this one could be another copy of: the same kind, with
    /// transactions.
    func copies(among all: [AccountsOverview.Account]) -> [AccountsOverview.Account] {
        all.filter { $0.id != id && $0.kind == kind && $0.hasHistory }
    }

    var kindWord: String {
        switch kind {
        case "savings": return "Savings"
        case "card": return "Credit card"
        case "loan": return "Loan"
        case "investment": return "Investment"
        default: return "Chequing"
        }
    }

    /// "TD" for TD, "S" for Simplii: the bank, as the design's avatars draw it.
    var bankLetters: String {
        let bank = (institution ?? "").isEmpty ? name : institution!
        let word = bank.split(separator: " ").first.map(String.init) ?? bank
        return word.count <= 2 ? word.uppercased() : String(word.prefix(1)).uppercased()
    }
}

/// Letters in a frosted disc with the nacre ring: a bank or a person.
private struct NacreAvatar: View {
    let text: String
    var size: CGFloat = 36

    var body: some View {
        Text(text)
            .font(size > 40 ? Nacre.headline : Nacre.footnote)
            .foregroundColor(Pearl.ink)
            .frame(width: size, height: size)
            .background(Circle().fill(Nacre.glass))
            .overlay(Circle().strokeBorder(
                AngularGradient(colors: [Nacre.rose, Nacre.lilac, Nacre.seaglass, Nacre.rose], center: .center),
                lineWidth: 1.5))
            .accessibilityHidden(true)
    }
}

/// One of several: a title, a line under it, a trailing tick when it's the
/// one (the Choice component's Radio type; iOS has no radio buttons).
private struct PickRow: View {
    let title: String
    var sub: String? = nil
    let selected: Bool
    let action: () -> Void

    var body: some View {
        Button(action: action) {
            HStack(spacing: 12) {
                VStack(alignment: .leading, spacing: 2) {
                    Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    if let sub = sub {
                        Text(sub).font(Nacre.subheadline).foregroundColor(Pearl.muted)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                }
                .frame(maxWidth: .infinity, alignment: .leading)
                Image(systemName: "checkmark")
                    .font(.system(size: 15, weight: .semibold))
                    .foregroundColor(Pearl.action)
                    .opacity(selected ? 1 : 0)
            }
            .padding(.horizontal, 16).padding(.vertical, 11)
            .frame(minHeight: 52)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(selected ? .isSelected : [])
    }
}

/// "Last four digits   5521": a label and a field, right-aligned, in a card.
private struct InlineField: View {
    let label: String
    @Binding var text: String
    var prompt = ""
    var keyboard: UIKeyboardType = .default
    var suffix: String? = nil

    var body: some View {
        HStack(spacing: 10) {
            Text(label).font(Nacre.body).foregroundColor(Pearl.ink)
            TextField("", text: $text, prompt: Text(prompt).foregroundColor(Pearl.muted))
                .font(Nacre.body)
                .foregroundColor(Pearl.ink)
                .multilineTextAlignment(.trailing)
                .keyboardType(keyboard)
                .textInputAutocapitalization(keyboard == .default ? .words : .never)
                .autocorrectionDisabled()
                .accessibilityLabel(label)
            if let suffix = suffix {
                Text(suffix).font(Nacre.body).foregroundColor(Pearl.ink).accessibilityHidden(true)
            }
        }
        .padding(.horizontal, 16)
        .frame(minHeight: 50)
    }
}

// MARK: - AM-08 Joint: who you share it with

@MainActor
struct JointAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    @State var account: AccountsOverview.Account
    @State private var fixed = false
    @State private var shareText = ""
    /// "all" or "from_today": which purchases a change of share reaches.
    @State private var apply = "all"
    @State private var adding = false
    @State private var newName = ""
    @State private var removing: String?
    @State private var busy = false
    @State private var error: String?

    private struct Saved: Decodable { let account: AccountsOverview.Account? }

    private var people: [String] { account.jointPeople ?? [] }
    private var enteredShare: Double? {
        Double(shareText.replacingOccurrences(of: "%", with: "").trimmingCharacters(in: .whitespaces))
    }
    private var shareIsValid: Bool { enteredShare.map { (1...99).contains($0) } ?? false }

    /// How purchases count differs from what's saved.
    private var changed: Bool {
        if fixed != (account.jointShare != nil) { return true }
        return fixed && enteredShare != account.jointShare
    }

    var body: some View {
        ProfilePage {
            hero
            ProfileSection("Shared with")
            GlassCard {
                ForEach(Array(people.enumerated()), id: \.element) { i, name in
                    personRow(name)
                    if i < people.count - 1 || people.count < 6 { RowSeparator() }
                }
                // The server keeps six at most.
                if people.count < 6 {
                    Button { newName = ""; adding = true } label: {
                        HStack(spacing: 12) {
                            Text("Add someone").font(Nacre.body).foregroundColor(Pearl.action)
                                .frame(maxWidth: .infinity, alignment: .leading)
                            Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                .foregroundColor(Pearl.muted)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 50)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(busy)
                }
            }
            ProfileSection("Your share")
            GlassCard {
                PickRow(title: "All mine unless I mark it",
                        sub: "Mark the purchases someone else paid for",
                        selected: !fixed) { fixed = false }
                RowSeparator()
                PickRow(title: "A fixed share", sub: "For example, 50%", selected: fixed) { fixed = true }
                if fixed {
                    RowSeparator()
                    InlineField(label: "Your share", text: $shareText, prompt: "50", keyboard: .decimalPad, suffix: "%")
                }
            }
            if changed {
                ProfileSection("Which purchases")
                GlassCard {
                    PickRow(title: "All purchases from this account",
                            sub: "Ones you marked as someone else’s, or gave your own part, stay as you said.",
                            selected: apply == "all") { apply = "all" }
                    RowSeparator()
                    PickRow(title: "Starting today",
                            sub: "Earlier purchases keep counting the way they do now.",
                            selected: apply == "from_today") { apply = "from_today" }
                }
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            if changed {
                Button("Save") { Task { await saveShare() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy || (fixed && !shareIsValid))
            }
            Button("Not a joint account") { Task { await stopSharing() } }
                .buttonStyle(NacreTextButtonStyle(tone: Pearl.action))
                .disabled(busy)
        }
        .onAppear(perform: syncShare)
        .alert("Add someone", isPresented: $adding) {
            TextField("Their name", text: $newName)
                .textInputAutocapitalization(.words)
            Button("Cancel", role: .cancel) {}
            Button("Add") { Task { await addPerson() } }
        } message: {
            Text("Pearl offers their name when it asks “Who put this in?”. Only you can see this.")
        }
        .confirmationDialog("Remove \(removing ?? "them") from \(account.name)?",
                            isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
                            titleVisibility: .visible) {
            Button("Remove", role: .destructive) {
                if let name = removing { Task { await save(people: people.filter { $0 != name }) } }
            }
        }
    }

    private var hero: some View {
        VStack(spacing: 10) {
            NacreAvatar(text: account.bankLetters, size: 56)
            Text(account.name).font(Nacre.title2).foregroundColor(Pearl.ink)
                .multilineTextAlignment(.center)
            Text(Format.amount(abs(account.balance ?? 0)))
                .font(.custom("Fraunces-SemiBold", size: 44, relativeTo: .largeTitle))
                .tracking(-0.88)
                .foregroundColor(Pearl.ink)
                .lineLimit(1).minimumScaleFactor(0.6)
            Text([account.kindWord, (account.mask ?? "").isEmpty ? nil : "••\(account.mask!)"]
                .compactMap { $0 }.joined(separator: " · "))
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
            StatusPill(text: "Joint", tone: .joint)
        }
        .frame(maxWidth: .infinity)
        .padding(.vertical, 4)
    }

    /// "SA  Sam". The server needs one person named, so the last one stays.
    @ViewBuilder
    private func personRow(_ name: String) -> some View {
        let row = HStack(spacing: 12) {
            NacreAvatar(text: Self.letters(name))
            Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                .frame(maxWidth: .infinity, alignment: .leading)
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .contentShape(Rectangle())
        if people.count < 2 {
            row
        } else {
            Button { removing = name } label: { row }
                .buttonStyle(.plain)
                .disabled(busy)
                .accessibilityHint("Removes them from this account")
        }
    }

    /// "SA" for Sam, "SL" for Sam Lee.
    static func letters(_ name: String) -> String {
        let words = name.split(separator: " ")
        if words.count > 1 { return words.prefix(2).compactMap { $0.first.map(String.init) }.joined().uppercased() }
        return String(name.prefix(2)).uppercased()
    }

    private func syncShare() {
        fixed = account.jointShare != nil
        shareText = account.jointShare.map { $0 == $0.rounded() ? "\(Int($0))" : "\($0)" } ?? ""
    }

    private func addPerson() async {
        let name = newName.trimmingCharacters(in: .whitespaces)
        guard !name.isEmpty else { return }
        await save(people: people + [name])
    }

    private func save(people: [String]) async {
        removing = nil
        await put(["joint_people": people])
    }

    private func saveShare() async {
        // "auto" keeps it joint with no set share (finance/joint.py).
        let share: Any = fixed ? (enteredShare ?? 0) : "auto"
        await put(["joint_share": share, "apply": apply])
        if error == nil { syncShare() }
    }

    private func stopSharing() async {
        await put(["joint_share": NSNull()])
        if error == nil { dismiss() }
    }

    private func put(_ body: [String: Any]) async {
        busy = true
        defer { busy = false }
        do {
            let reply: Saved = try await app.api.put("api/accounts/\(account.id)/settings", body)
            if let a = reply.account { account = a }
            error = nil
            app.changed()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - AM-09 Same account twice?

@MainActor
struct SameAccountView: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let account: AccountsOverview.Account
    /// Every account she has, to find the others of the same kind.
    let all: [AccountsOverview.Account]
    /// What was done, in words, once they're combined.
    let combined: (String) -> Void
    @State private var keep: String?
    @State private var preview: Preview?
    @State private var busy = false
    @State private var error: String?

    private struct Preview: Decodable { let matched: Int; let moved: Int }

    private var candidates: [AccountsOverview.Account] { account.copies(among: all) }

    /// Two accounts: pick either to keep. More than two: this page's account
    /// is the copy, and she picks which of the others it's a copy of.
    private var rows: [AccountsOverview.Account] {
        candidates.count == 1 ? [account] + candidates : candidates
    }

    private var kept: AccountsOverview.Account? { rows.first { $0.id == keep } }
    /// The one that goes, once she's picked.
    private var copy: AccountsOverview.Account? {
        guard let kept = kept else { return nil }
        return kept.id == account.id ? candidates.first : account
    }

    var body: some View {
        ProfilePage {
            VStack(alignment: .leading, spacing: 12) {
                Text("Same account twice?").font(Nacre.title).foregroundColor(Pearl.ink)
                    .accessibilityAddTraits(.isHeader)
                Text("Combine them so nothing shows twice.").font(Nacre.footnote).foregroundColor(Pearl.ink)
            }
            if candidates.isEmpty {
                ProfileNote("There’s no other account of the same kind to combine with.").padding(.top, 8)
            } else {
                ProfileSection("Keep")
                GlassCard {
                    ForEach(Array(rows.enumerated()), id: \.element.id) { i, a in
                        if i > 0 { RowSeparator() }
                        PickRow(title: a.label, sub: line(a), selected: keep == a.id) { keep = a.id }
                    }
                }
                if let note = note { ProfileNote(note).padding(.top, 4) }
            }
            if let error = error { Hint(text: error).padding(.top, 4) }
        } bottom: {
            if !candidates.isEmpty {
                Button("Combine them") { Task { await combine() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(busy || copy == nil)
            }
        }
        .task(id: keep) { await loadPreview() }
    }

    /// "Linked · 312 transactions".
    private func line(_ a: AccountsOverview.Account) -> String {
        let source = a.status == "manual" ? "Imported" : a.status == "disconnected" ? "Disconnected" : "Linked"
        let n = a.transactions ?? 0
        return "\(source) · \(n) transaction\(n == 1 ? "" : "s")"
    }

    /// "291 purchases are in both. Your categories and splits stay." and what
    /// happens to the copy, since combining can't be undone.
    private var note: String? {
        guard let copy = copy else { return nil }
        let leaves = "\(copy.name) leaves Accounts and stops syncing."
        let word = account.isCard ? "purchase" : "transaction"
        guard let p = preview else { return "Your categories and splits stay. \(leaves)" }
        var out = p.matched == 0 ? "Nothing is in both."
            : "\(p.matched) \(word)\(p.matched == 1 ? " is" : "s are") in both. Your categories and splits stay."
        if p.moved > 0 {
            out += " \(p.moved) only on \(copy.name) move\(p.moved == 1 ? "s" : "") across."
        }
        return "\(out) \(leaves)"
    }

    private func loadPreview() async {
        preview = nil
        guard let copy = copy, let kept = kept else { return }
        // The note still reads without the count if this doesn't arrive.
        preview = try? await app.api.get("api/accounts/\(copy.id)/merge/preview", query: ["into": kept.id])
    }

    private func combine() async {
        guard let copy = copy, let kept = kept else { return }
        busy = true
        defer { busy = false }
        do {
            let _: Preview = try await app.api.post("api/accounts/\(copy.id)/merge", ["into": kept.id])
            app.changed()
            combined("Combined. \(kept.name) stays and \(copy.name) is gone.")
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}

// MARK: - AM-10 Add a balance by hand

@MainActor
struct AddHandBalanceSheet: View {
    @EnvironmentObject private var app: AppModel
    @Environment(\.dismiss) private var dismiss
    let added: () async -> Void
    @State private var name = ""
    /// Nothing is chosen for her.
    @State private var kind: String?
    @State private var last4 = ""
    @State private var balance = ""
    @State private var busy = false
    @State private var error: String?

    private let kinds = [("chequing", "Chequing"), ("savings", "Savings"),
                         ("investment", "Investment"), ("credit", "Card")]

    /// Only savings and investments take digits (finance/profile_api.py).
    private var takesDigits: Bool { kind == "savings" || kind == "investment" }

    private var canAdd: Bool {
        !name.trimmingCharacters(in: .whitespaces).isEmpty && kind != nil
            && !balance.trimmingCharacters(in: .whitespaces).isEmpty
            && (!takesDigits || last4.isEmpty || last4.count == 4)
    }

    private var note: String {
        if takesDigits && last4.count == 4 { return "Transfers to ••\(last4) will be sorted as Saved." }
        if kind == "investment" { return "Not part of your Anchor. Add its last four digits and transfers to it are sorted as Saved." }
        if kind == "savings" { return "Add its last four digits and transfers to it are sorted as Saved." }
        return "For a bank Pearl can’t link yet."
    }

    var body: some View {
        ScrollView {
            VStack(alignment: .leading, spacing: 10) {
                HStack {
                    Color.clear.frame(width: 44, height: 10)
                    Text("Add a balance").font(Nacre.headline).foregroundColor(Pearl.ink)
                        .frame(maxWidth: .infinity)
                        .accessibilityAddTraits(.isHeader)
                    CloseButton { dismiss() }
                }
                GlassCard {
                    InlineField(label: "Name", text: $name, prompt: "TD TFSA")
                }
                HStack(spacing: 8) {
                    ForEach(kinds, id: \.0) { id, title in
                        FilterChip(label: title, on: kind == id) { kind = id }
                    }
                }
                GlassCard {
                    if takesDigits {
                        InlineField(label: "Last four digits", text: $last4, prompt: "Optional", keyboard: .numberPad)
                        RowSeparator()
                    }
                    InlineField(label: "Balance today", text: $balance, prompt: "$0.00", keyboard: .decimalPad)
                }
                ProfileNote(note)
                if let error = error { Hint(text: error) }
                Button("Add account") { Task { await add() } }
                    .buttonStyle(NacreButtonStyle(busy: busy))
                    .disabled(!canAdd || busy)
            }
            .padding(.horizontal, 16).padding(.top, 24).padding(.bottom, 16)
        }
        .scrollDismissesKeyboard(.interactively)
        .foregroundColor(Pearl.ink)
        .onChange(of: last4) { value in
            let digits = String(value.filter(\.isNumber).prefix(4))
            if digits != value { last4 = digits }
        }
    }

    private func add() async {
        guard let kind = kind else { return }
        busy = true
        defer { busy = false }
        do {
            var body: [String: Any] = ["name": name, "kind": kind, "balance": balance]
            if takesDigits, !last4.isEmpty { body["last4"] = last4 }
            let _: OK = try await app.api.post("api/accounts/manual", body)
            app.changed()
            await added()
            dismiss()
        } catch {
            self.error = app.handle(error)
        }
    }
}
