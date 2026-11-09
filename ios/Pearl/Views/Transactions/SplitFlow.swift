import Contacts
import SwiftUI

// THL-291, the purchase side: split it with people (S-02, S-03, S-15 to
// S-18), see who still owes what (S-04, S-05, S-19), mark someone paid back
// by bank deposit or in cash (S-06, S-29, S-30), remind them (S-07) or let
// the rest go (S-08, S-20). Edit split after someone has paid (S-03e, S-03f,
// SPLIT-02) and the odd cent (S-15 v2, S-18 v2, SPLIT-10), 2026-11-09.

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
    /// S-24 from a deposit (SPLIT-07): the split is held, not saved, and
    /// goes with the deposit's parts in one save. Gets the split as it would
    /// be sent, the first person's share and hers. A Quick sort card's page
    /// holds it the same way, for the card's Yes (T-98s, SPLIT-06).
    var onHold: (([String: Any], Double, Double) -> Void)? = nil
    /// SPLIT-16: saved with someone who had paid taken out; the toast's
    /// title and the server's Undo.
    var onRemoved: ((String, JSONValue?) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var people: [String]
    @State private var withMe = true
    @State private var step = 0
    @State private var typed = ""
    @State private var mode = "even"
    @State private var values: [String: String] = [:]
    @State private var busy = false
    @State private var error: String?
    /// S-17 Add someone: names from her contacts, and the one she picked.
    @State private var adding = false
    @State private var contacts: [String] = []
    /// Contacts and names ticked on Add someone, added together (2026-11-08).
    @State private var picked: [String] = []
    /// S-03f: someone who has paid, swiped away; asks before they go.
    @State private var removing: String?

    private static let me = "\u{0}me"

    init(t: Transaction, api: APIClient, recent: [String], with names: [String]? = nil,
         title: String? = nil, saveTitle: String = "Save",
         onHold: (([String: Any], Double, Double) -> Void)? = nil, onSaved: @escaping (String) -> Void,
         onRemoved: ((String, JSONValue?) -> Void)? = nil) {
        self.onRemoved = onRemoved
        // S-03 Dark (designBOT round 5): the selected split method is
        // rgb(0.30, 0.33, 0.58), not a token; light keeps the system white.
        // Set before the picker is made, and put back when the sheet goes.
        UISegmentedControl.appearance().selectedSegmentTintColor = Self.segment
        self.t = t
        self.api = api
        self.recent = recent
        self.onSaved = onSaved
        self.title = title
        self.saveTitle = saveTitle
        self.onHold = onHold
        let existing = t.splitting?.people.map(\.name) ?? []
        _people = State(initialValue: names ?? existing)
        _step = State(initialValue: names == nil ? 0 : 1)
        // Her own share as the split was made: a let go made it bigger since.
        let whole = t.fullAmount ?? t.amount
        let yours = t.splitting.map { s in whole - s.people.map(\.share).reduce(0, +) }
        _withMe = State(initialValue: yours.map { $0 >= 0.005 } ?? true)
        if let s = t.splitting, let m = s.mode, m != "even", let yours = yours {
            var v: [String: String] = [:]
            if ["percent", "shares"].contains(m) && s.people.allSatisfy({ $0.weight != nil }) {
                // S-03e (SPLIT-02): opened in the mode it was saved in, with
                // the same numbers, not turned into Amounts.
                _mode = State(initialValue: m)
                for p in s.people { v[p.name] = Self.plain(p.weight ?? 0) }
                if yours >= 0.005 {
                    if m == "percent" {
                        v[Self.me] = Self.plain(max(0, 100 - s.people.compactMap(\.weight).reduce(0, +)))
                    } else if let p = s.people.first(where: { ($0.weight ?? 0) > 0 && $0.share > 0 }),
                              let w = p.weight {
                        v[Self.me] = Self.plain((yours / (p.share / w) * 100).rounded() / 100)
                    }
                }
            } else {
                // Opened again (2026-11-08): each share as it was saved, in
                // Amounts, so nothing has to be typed twice.
                _mode = State(initialValue: "amount")
                v[Self.me] = Self.plain(yours)
                for p in s.people { v[p.name] = Self.plain(p.share) }
            }
            _values = State(initialValue: v)
        }
    }

    /// The person as the split was saved: what they've paid, cash, let go.
    private func saved(_ key: String) -> Transaction.Splitting.Person? {
        t.splitting?.people.first { $0.name == key }
    }

    var body: some View {
        VStack(spacing: 0) {
            SheetTitle(title: adding ? "Add someone" : step == 0 ? "Who was it with?" : (title ?? "How to split")) {
                if adding { adding = false; typed = ""; picked = [] } else { dismiss() }
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    QuestionHeader(name: t.merchant, amount: Format.money(t), tone: t.tone, sub: nil)
                    if adding { addSomeone } else if step == 0 { who } else { how }
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
        .onDisappear { UISegmentedControl.appearance().selectedSegmentTintColor = nil }
        .alert(removing.map { "Remove \($0)?" } ?? "",
               isPresented: Binding(get: { removing != nil }, set: { if !$0 { removing = nil } }),
               presenting: removing) { name in
            Button(bankPaid(name) >= 0.005 ? "Unlink and remove" : "Remove", role: .destructive) { remove(name) }
            Button("Keep \(name)", role: .cancel) {}
        } message: { name in
            Text(removeWords(name))
        }
    }

    // MARK: S-03f Removing someone who has paid (SPLIT-02)

    /// What they paid by bank, not in cash or another app.
    private func bankPaid(_ name: String) -> Double {
        guard let p = saved(name) else { return 0 }
        return p.paid - (p.cash ?? 0) - (p.app ?? 0)
    }

    /// Someone with a payback or cash asks first (S-03f); anyone else, or
    /// someone whose share was only let go, goes at once.
    private func askRemove(_ name: String) {
        if let p = saved(name), p.paid >= 0.005 { removing = name } else { remove(name) }
    }

    /// "Priya paid you $28.04 on Nov 14. Removing Priya unlinks that
    /// payment, and it goes back to Needs a look." Cash or another app is
    /// forgotten with them instead.
    private func removeWords(_ name: String) -> String {
        guard let p = saved(name) else { return "" }
        let shared = p.shared ?? []
        let bank = bankPaid(name) - shared.map(\.here).reduce(0, +), kept = (p.cash ?? 0) + (p.app ?? 0)
        var words: [String] = []
        // SPLIT-16: a payback that also paid back other purchases loses only
        // this purchase's part. (designBOT's copy says "Her"; Pearl doesn't
        // know anyone's pronouns, so it says their name.)
        for s in shared {
            let others = s.others.count <= 2 ? s.others.joined(separator: " and ")
                : s.others.dropLast().joined(separator: ", ") + " and " + (s.others.last ?? "")
            words.append("\(name)’s \(Format.amount(s.whole)) \(s.word) also paid back \(others). "
                         + "Removing \(name) here unlinks only the \(Format.amount(s.here)) for \(t.merchant); "
                         + "\(others) \(s.others.count == 1 ? "stays" : "stay") paid back.")
        }
        if bank >= 0.005 {
            words.append("\(name) paid you \(Format.amount(bank))"
                         + (p.paidOn.map { " on \(Format.short($0))" } ?? "")
                         + ". Removing \(name) unlinks that payment, and it goes back to Needs a look.")
        }
        if kept >= 0.005 {
            let how = (p.app ?? 0) >= 0.005 && (p.cash ?? 0) < 0.005 ? "through another app" : "in cash"
            words.append(bank >= 0.005
                         ? "The \(Format.amount(kept)) \(how) is forgotten too."
                         : "\(name) paid you \(Format.amount(kept)) \(how). Removing \(name) forgets that payment.")
        }
        return words.joined(separator: " ")
    }

    // MARK: S-17 Add someone

    private var addSomeone: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                TextField("", text: $typed, prompt: Text("Name").foregroundColor(Pearl.muted))
                    .font(Nacre.body).textInputAutocapitalization(.words).autocorrectionDisabled()
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            let q = typed.trimmingCharacters(in: .whitespaces)
            // Ticked ones stay ticked while she searches for the next person.
            let ticked = picked.filter { !contacts.contains($0) }
            if !ticked.isEmpty {
                Text("ADDING").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 16)
                GlassCard {
                    ForEach(Array(ticked.enumerated()), id: \.element) { i, name in
                        if i > 0 { RowSeparator(inset: 64) }
                        pickRow(name, sub: nil)
                    }
                }
            }
            if !contacts.isEmpty || !q.isEmpty {
                if !contacts.isEmpty {
                    Text("FROM YOUR CONTACTS").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                        .padding(.horizontal, 16)
                }
                GlassCard {
                    ForEach(Array(contacts.enumerated()), id: \.element) { i, name in
                        if i > 0 { RowSeparator(inset: 64) }
                        pickRow(name, sub: "In your contacts")
                    }
                    if !q.isEmpty && !picked.contains(q) {
                        if !contacts.isEmpty { RowSeparator() }
                        Button { pick(q); typed = "" } label: {
                            HStack {
                                Text("Add “\(q)” without a contact").font(Nacre.body).foregroundColor(Pearl.action)
                                Spacer()
                                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                                    .foregroundColor(Pearl.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                    }
                }
            }
            withMeCard
        }
        .task(id: typed) {
            try? await Task.sleep(nanoseconds: 200_000_000)
            if !Task.isCancelled { await searchContacts() }
        }
    }

    /// Names in her contacts matching what she typed. iOS asks the first time.
    private func searchContacts() async {
        let q = typed.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { contacts = []; return }
        let store = CNContactStore()
        if CNContactStore.authorizationStatus(for: .contacts) == .notDetermined {
            _ = try? await store.requestAccess(for: .contacts)
        }
        let status = CNContactStore.authorizationStatus(for: .contacts)
        guard status != .denied && status != .restricted && status != .notDetermined else { contacts = []; return }
        let found: [String] = await Task.detached {
            let keys = [CNContactGivenNameKey, CNContactFamilyNameKey] as [CNKeyDescriptor]
            let people = (try? store.unifiedContacts(matching: CNContact.predicateForContacts(matchingName: q),
                                                     keysToFetch: keys)) ?? []
            return people.map { "\($0.givenName) \($0.familyName)".trimmingCharacters(in: .whitespaces) }
                .filter { !$0.isEmpty }
        }.value
        contacts = Array(NSOrderedSet(array: found).array as? [String] ?? found).prefix(6).map { $0 }
    }

    private func pickRow(_ name: String, sub: String?) -> some View {
        let on = picked.contains(name)
        return Button { pick(name) } label: {
            HStack(spacing: 12) {
                Initials(name: name, size: 34)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                    if let sub = sub { Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted) }
                }
                Spacer()
                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                    .font(.system(size: 22))
                    .foregroundColor(on ? Pearl.action : Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 54).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func pick(_ name: String) {
        if let i = picked.firstIndex(of: name) { picked.remove(at: i) } else { picked.append(name) }
    }

    /// Everyone ticked, plus a typed name nobody ticked, into the split.
    private func addPicked() {
        var names = picked
        let q = typed.trimmingCharacters(in: .whitespaces)
        if names.isEmpty && !q.isEmpty { names = [q] }
        for name in names where !people.contains(name) { people.append(name) }
        typed = ""
        contacts = []
        picked = []
        adding = false
        // Straight on to How to split (2026-11-08): who it was with is settled.
        if !people.isEmpty { step = 1 }
    }

    private var addLabel: String {
        let q = typed.trimmingCharacters(in: .whitespaces)
        let names = picked.isEmpty ? (q.isEmpty ? [] : [q]) : picked
        switch names.count {
        case 0: return "Add"
        case 1: return "Add \(names[0].components(separatedBy: " ").first ?? names[0])"
        default: return "Add \(names.count) people"
        }
    }

    private var withMeCard: some View {
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
                    RowSeparator()
                    // S-02: Add someone new opens S-17.
                    addNewRow
                }
            } else {
                GlassCard { addNewRow }
            }
            withMeCard
        }
    }

    private var addNewRow: some View {
        Button { adding = true } label: {
            HStack {
                Text("Add someone new").font(Nacre.body).foregroundColor(Pearl.action)
                Spacer()
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold)).foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
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

    /// Swiped away on How to split (2026-11-08).
    private func remove(_ name: String) {
        withAnimation {
            people.removeAll { $0 == name }
            values[name] = nil
            if people.isEmpty { step = 0 }
        }
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
                    SwipeToRemove(enabled: key != Self.me, label: label(key)) { askRemove(key) } content: {
                    HStack(spacing: 12) {
                        Initials(name: key == Self.me ? "Me" : key, size: 34)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(label(key)).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                            if let line = caption(key) {
                                // S-03e: what they've paid; S-15 v2 / S-18 v2: dollars and the odd cent.
                                Text(line).font(Nacre.footnote)
                                    .foregroundColor(overCents(key) > 0 ? Pearl.moneyOut : Pearl.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
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
                                    .strokeBorder(overCents(key) > 0 || (gapCents != 0 && mode == "amount")
                                                  ? Pearl.action : Nacre.separator, lineWidth: 1))
                                .accessibilityLabel("\(label(key)) \(mode == "percent" ? "percent" : mode == "shares" ? "shares" : "amount")")
                        }
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                    }
                }
                // More people from here, and back to the amounts after (2026-11-08).
                RowSeparator()
                addNewRow
            }
            Group {
                if gapCents == 0 {
                    Text(addsUp + overWords).foregroundColor(Nacre.teal)
                        .multilineTextAlignment(.center)
                } else {
                    VStack(spacing: 8) {
                        Text(gapWords).foregroundColor(gapCents > 0 && !blocksShort ? Pearl.ink : Pearl.moneyOut)
                            .multilineTextAlignment(.center)
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

    /// SPLIT-10, the server's rule for preview and save: leftover cents go
    /// to you when you're in it, otherwise one each from the top of the list.
    private func spread(_ cents: Int, over keys: [String]) -> [String: Int] {
        guard cents > 0, !keys.isEmpty else { return [:] }
        if withMe && keys.contains(Self.me) { return [Self.me: cents] }
        var out: [String: Int] = [:]
        for i in 0..<cents { out[keys[i % keys.count], default: 0] += 1 }
        return out
    }

    /// Evenly: everyone rounded down, then the odd cents by `spread` (S-18 v2).
    private var evenCents: [String: Int] {
        let n = max(rows.count, 1)
        let each = totalCents / n
        let odd = spread(totalCents - each * n, over: rows)
        return Dictionary(uniqueKeysWithValues: rows.map { ($0, each + (odd[$0] ?? 0)) })
    }

    private func evenAmount(_ key: String) -> Double { Double(evenCents[key] ?? 0) / 100 }

    /// Each one's cents for these weights: rounded down, the rest by `spread`.
    /// `over` is what the weights are out of; with nothing to spread, what's
    /// left isn't anyone's yet.
    private func weighted(over whole: Double, spreading: Bool) -> [String: Int] {
        var out = floors(over: whole)
        if spreading {
            for (k, c) in spread(totalCents - out.values.reduce(0, +), over: rows) { out[k, default: 0] += c }
        }
        return out
    }

    private func floors(over whole: Double) -> [String: Int] {
        guard whole > 0 else { return [:] }
        return Dictionary(uniqueKeysWithValues: rows.map {
            ($0, Int((Double(totalCents) * number($0) / whole).rounded(.down)))
        })
    }

    private var weightSum: Double { rows.map { number($0) }.reduce(0, +) }

    private var shareAmounts: [String: Double] {
        weighted(over: weightSum, spreading: true).mapValues { Double($0) / 100 }
    }

    /// S-15 v2: % works in cents. Short of 100% by less than a cent a person
    /// is rounding (33.33 × 3), not a gap.
    private var percentRounds: Bool {
        let short = Int((Double(totalCents) * (100 - weightSum) / 100).rounded())
        return weightSum < 100 && short < rows.count
    }

    /// A real % gap stays nobody's yet; otherwise every cent is placed.
    private var percentShort: Bool { weightSum < 100 && !percentRounds }

    private var percentCents: [String: Int] {
        percentShort ? weighted(over: 100, spreading: false) : weighted(over: weightSum, spreading: true)
    }

    /// The odd cent landed on you (S-18 v2, S-15 v2).
    private var oddToMe: Bool {
        guard withMe, rows.count > 1 else { return false }
        switch mode {
        case "even": return totalCents % rows.count != 0
        case "percent", "shares":
            if mode == "percent" && percentShort { return false }
            return (shareCents(Self.me) - (floors(over: weightSum)[Self.me] ?? 0)) > 0
        default: return false
        }
    }

    /// What this row's share comes to now, in cents, whichever way it's split.
    private func shareCents(_ key: String) -> Int {
        switch mode {
        case "even": return evenCents[key] ?? 0
        case "percent": return percentCents[key] ?? 0
        case "shares": return Int(((shareAmounts[key] ?? 0) * 100).rounded())
        default: return Int((number(key) * 100).rounded())
        }
    }

    /// S-03e: how much more than this share they've already paid.
    private func overCents(_ key: String) -> Int {
        guard key != Self.me, let p = saved(key), p.paid >= 0.005 else { return 0 }
        return max(0, Int((p.paid * 100).rounded()) - shareCents(key))
    }

    /// Under a name: "Paid $20.00 cash · let go $8.04", "Paid $28.04 · $8.04
    /// more than this share" (S-03e); "$28.34 · the odd cent is yours" (S-15
    /// v2); "Includes the odd cent" (S-18 v2).
    private func caption(_ key: String) -> String? {
        var bits: [String] = []
        let cents = shareCents(key)
        let mineOdd = key == Self.me && oddToMe
        if key == Self.me && withMe && gapCents > 0 {
            // S-03b v2: "Your share $44.12 · $4.12 of it is the rest", before saving.
            let rest = mineCents - cents
            bits.append("Your share \(Format.amount(Double(mineCents) / 100)) · \(Format.amount(Double(rest) / 100)) of it is the rest")
        }
        if mode == "percent" && gapCents == 0 {
            bits.append(Format.amount(Double(cents) / 100) + (mineOdd ? " · the odd cent is yours" : ""))
        } else if mode == "even" && mineOdd {
            bits.append("Includes the odd cent")
        }
        if let p = saved(key), key != Self.me {
            let over = overCents(key)
            if p.paid >= 0.005 {
                let how = (p.cash ?? 0) >= p.paid - 0.005 ? " cash" : ""
                var line = "Paid \(Format.amount(p.paid))\(how)"
                if over > 0 {
                    line += " · \(Format.amount(Double(over) / 100)) more than this share"
                } else if p.letGo != nil, cents - Int((p.paid * 100).rounded()) > 0 {
                    line += " · let go \(Format.amount(Double(cents) / 100 - p.paid))"
                } else if how.isEmpty, let day = p.paidOn {
                    line += " · \(Format.short(day))"
                }
                bits.append(line)
            } else if p.letGo != nil {
                bits.append("Let go \(Format.amount(Double(cents) / 100))")
            }
        }
        return bits.isEmpty ? nil : bits.joined(separator: " · ")
    }

    /// S-03e: " · Priya paid $8.04 more than this share, so you’ll owe Priya
    /// $8.04 (You owe, in Owed to you)."
    private var overWords: String {
        let over = people.map { ($0, overCents($0)) }.filter { $0.1 > 0 }
        guard !over.isEmpty else { return "" }
        return over.map { name, c in
            " · \(name) paid \(Format.amount(Double(c) / 100)) more than this share, so you’ll owe \(name) \(Format.amount(Double(c) / 100))"
        }.joined() + " (You owe, in Owed to you)."
    }

    /// Cents still to give out ("$4.12 left to assign"); negative is too much.
    private var gapCents: Int {
        switch mode {
        case "even", "shares": return 0
        case "percent":
            if percentRounds { return 0 }
            return Int(((100 - rows.map { number($0) }.reduce(0, +)) * 100).rounded())
        default:
            return totalCents - rows.map { Int((number($0) * 100).rounded()) }.reduce(0, +)
        }
    }

    private var addsUp: String {
        switch mode {
        case "shares":
            let n = rows.map { number($0) }.reduce(0, +)
            return "\(Self.plain(n)) shares · adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        default: return "Adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        }
    }

    private var gapWords: String {
        if mode == "percent" {
            let g = Double(gapCents) / 100
            if g > 0 && blocksShort { return "\(Self.plain(g))% left to assign" }
            return g > 0 ? "\(Self.plain(g))% isn’t anyone’s yet · it stays yours" : "That’s \(Self.plain(-g))% too much"
        }
        let g = Double(abs(gapCents)) / 100
        // S-03b: with "I had some too" off there's no "you" to keep the rest.
        if gapCents > 0 && blocksShort { return "\(Format.amount(g)) left to assign" }
        return gapCents > 0 ? "\(Format.amount(g)) isn’t anyone’s yet · it stays yours"
            : "That’s \(Format.amount(g)) too much"
    }

    /// SPLIT-01 (b′), S-03b v2 (2026-11-09): short of the total saves only
    /// when she's in it, and the rest is hers; otherwise Save waits, as the
    /// server does.
    private var blocksShort: Bool { gapCents > 0 && !withMe }

    /// Her share as it would save: her own part plus anything nobody has yet.
    private var mineCents: Int { totalCents - people.map { shareCents($0) }.reduce(0, +) }

    /// The unassigned amount, shared by the rows still empty (or all), odd
    /// cents by the same rule as Evenly (SPLIT-10).
    private func splitRest() {
        let empty = rows.filter { (values[$0] ?? "").isEmpty }
        let targets = empty.isEmpty ? rows : empty
        let each = gapCents / targets.count
        let odd = spread(gapCents - each * targets.count, over: targets)
        for k in targets {
            let c = Int((number(k) * 100).rounded()) + each + (odd[k] ?? 0)
            values[k] = Self.plain(Double(c) / 100)
        }
    }

    static let segment = UIColor { $0.userInterfaceStyle == .dark
        ? UIColor(red: 0.30, green: 0.33, blue: 0.58, alpha: 1) : .white }

    static func plain(_ x: Double) -> String {
        x.rounded() == x ? String(Int(x)) : String(format: "%.2f", x)
    }

    // MARK: Save

    @ViewBuilder private var footer: some View {
        if adding {
            Button(addLabel) { addPicked() }
                .buttonStyle(NacreButtonStyle())
                .disabled(addLabel == "Add")
                .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        } else {
        Button(step == 0 ? "Next" : saveTitle) {
            if step == 0 { addTyped(); step = 1 } else { Task { await save() } }
        }
        .buttonStyle(NacreButtonStyle(busy: busy))
        .disabled(step == 0 ? people.isEmpty && typed.trimmingCharacters(in: .whitespaces).isEmpty
                  : (gapCents < 0 || blocksShort || busy))
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
        }
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
        if let onHold = onHold, let first = people.first {
            // S-24 (SPLIT-07): held for the deposit's one save.
            onHold(body, Double(shareCents(first)) / 100, Double(mineCents) / 100)
            return
        }
        do {
            struct Reply: Decodable { let undo: JSONValue? }
            let reply: Reply = try await api.put("api/transactions/\(t.id)/split", body)
            let n = people.count + (withMe ? 1 : 0)
            // SPLIT-16: someone who had paid was removed: "Priya removed ·
            // Undo" puts their payback back on this purchase.
            let gone = (t.splitting?.people ?? []).filter { p in p.paid >= 0.005 && !people.contains(p.name) }
            if let onRemoved = onRemoved, let first = gone.first {
                onRemoved(gone.count == 1 ? "\(first.name) removed" : "\(gone.count) people removed", reply.undo)
                return
            }
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
    /// The person she tapped, for their choices.
    @State private var chosen: Transaction.Splitting.Person?

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
                    // What to do about someone is on them (2026-11-08): tap to
                    // mark paid back, remind or let it go.
                    Button { chosen = p } label: { person(p) }
                        .buttonStyle(.plain)
                        .disabled(p.owes < 0.005 && p.letGo == nil)
                        .accessibilityHint(p.owes >= 0.005 ? "Mark paid back, remind or let it go" : "")
                }
                RowSeparator(inset: 0)
                Button(action: onEdit) {
                    HStack {
                        Text("Edit split").font(Nacre.body).foregroundColor(Pearl.action)
                        Spacer()
                        Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                            .foregroundColor(Pearl.muted)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
            }
            .confirmationDialog(chosen?.name ?? "", isPresented: Binding(get: { chosen != nil },
                                                                       set: { if !$0 { chosen = nil } }),
                                titleVisibility: .visible, presenting: chosen) { p in
                if p.owes >= 0.005 {
                    Button("Mark paid back") { onMarkPaid(p) }
                    Button("Remind \(p.name)") { onRemind(p) }
                    Button("Let it go") { onLetGo(p) }
                } else if p.letGo != nil {
                    Button("Undo let it go") { onUndoLetGo(p) }
                }
                Button("Cancel", role: .cancel) {}
            } message: { p in
                if p.owes >= 0.005 {
                    Text("Owes you \(Format.amount(p.owes))")
                } else if let was = p.letGo?.was {
                    Text("You let \(Format.amount(was - p.paid)) go")
                }
            }
            Button("See everyone who owes you", action: onOwed)
                .font(Nacre.textButton).foregroundColor(Pearl.action)
                .frame(maxWidth: .infinity).padding(.top, 6)
        }
    }

    private func person(_ p: Transaction.Splitting.Person) -> some View {
        HStack(spacing: 12) {
            Initials(name: p.name, size: 34)
            VStack(alignment: .leading, spacing: 4) {
                Text(p.name).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(status(p)).font(Nacre.footnote).foregroundColor(Pearl.muted)
                if let line = deposited(p) {
                    Text(line).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
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
            if p.owes >= 0.005 || p.letGo != nil {
                // Tapping them has choices.
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 12)
        .contentShape(Rectangle())
        .accessibilityElement(children: .combine)
    }

    /// "Owes you", "Paid $20.00 of $28.04", "Cash · Nov 13", "Let go · Nov 20".
    private func status(_ p: Transaction.Splitting.Person) -> String {
        if let gone = p.letGo { return "Let go · \(Format.short(gone.day))" }
        if p.owes >= 0.005 {
            return p.paid >= 0.005 ? "Paid \(Format.amount(p.paid)) of \(Format.amount(p.amount))" : "Owes you"
        }
        let how = (p.cash ?? 0) >= p.paid - 0.005 && (p.cash ?? 0) > 0 ? "Cash" : "Paid back"
        // SPLIT-14 (S-06 v3): "Paid back · PayPal · Nov 13", or "Another app" when unnamed.
        let app: String? = (p.app ?? 0) >= p.paid - 0.005 && (p.app ?? 0) > 0 ? (p.appName ?? "Another app") : nil
        return [how, app, p.paidOn.map { Format.short($0) }].compactMap { $0 }.joined(separator: " · ")
    }

    /// SPLIT-15: a cash payment a deposit holds part of, once: "$200.00
    /// deposited Nov 12 · $50.00 still cash".
    private func deposited(_ p: Transaction.Splitting.Person) -> String? {
        // SPLIT-19 (S-11c, I gave it back): "$60.00, $17.94 given back".
        if let pay = p.payments?.last(where: { ($0.givenBack ?? 0) >= 0.005 }), let back = pay.givenBack {
            return "\(Format.amount(pay.whole ?? pay.amount + back)), \(Format.amount(back)) given back"
        }
        guard let pay = p.payments?.last(where: { $0.deposited >= 0.005 && $0.still >= 0.005 }) else { return nil }
        return "\(Format.amount(pay.deposited)) deposited"
            + (pay.depositedOn.map { " \(Format.short($0))" } ?? "")
            + " · \(Format.amount(pay.still)) still cash"
    }

}

// MARK: - Mark paid back (S-06, S-29, S-30)

@MainActor
struct MarkPaidSheet: View {
    let t: Transaction
    let person: Transaction.Splitting.Person
    let api: APIClient
    let onDone: (String) -> Void
    /// SPLIT-19: a payment with its extra said, and the Sorted toast's Undo.
    var onUndoable: ((String, JSONValue?) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var how = "bank"
    /// S-11c (SPLIT-19): "What’s the extra $17.94?", for cash or an app.
    @State private var extraPage = false
    /// What the extra is so far; nothing is saved until all of it is said.
    @State private var pieces: [ExtraPiece] = []
    /// S-11c "How much of it?": all of what's left unless she types less.
    @State private var extraAmount = ""
    /// S-11c Paying me back: the open shares to tick (S-09).
    @State private var choosingShares = false
    @State private var shares: [OpenShare] = []
    @State private var ticked: [String: Double] = [:]

    struct ExtraPiece: Hashable {
        let kind: String
        let amount: Double
        var charge: String? = nil
        var person: String? = nil

        var body: [String: Any] {
            var b: [String: Any] = ["kind": kind, "amount": amount]
            if let charge = charge { b["charge"] = charge }
            if let person = person { b["person"] = person }
            return b
        }
    }

    /// Someone's open share on another split, from Owed to you.
    struct OpenShare: Identifiable, Hashable {
        let charge: String
        let merchant: String
        let date: String
        let person: String
        let owes: Double
        let theirs: Bool
        var id: String { charge + "|" + person }
    }
    @State private var amount: String
    @State private var when = Date()
    @State private var finding = false
    @State private var deposits: [Candidate] = []
    /// The deposits she ticked, in the order she ticked them (S-26).
    @State private var picked: [String] = []
    /// S-29: "Search any purchase" past the likely ones.
    @State private var query = ""
    @State private var found: [Candidate] = []
    /// S-06 v3 (SPLIT-14): which app, typed; and the ones she named before.
    @State private var appName = ""
    @State private var usedApps: [String] = []

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

    init(t: Transaction, person: Transaction.Splitting.Person, api: APIClient,
         onUndoable: ((String, JSONValue?) -> Void)? = nil, onDone: @escaping (String) -> Void) {
        self.t = t
        self.person = person
        self.api = api
        self.onDone = onDone
        self.onUndoable = onUndoable
        _amount = State(initialValue: SplitSheet.plain(person.owes))
    }

    var body: some View {
        if extraPage { extraSheet } else { markSheet }
    }

    private var markSheet: some View {
        VStack(spacing: 0) {
            SheetTitle(title: finding ? (inParts ? "What paid this back?" : "Find \(person.name)’s payment")
                       : "Mark paid back") { dismiss() }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    if finding && inParts {
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
                    if !finding && overBy >= 0.005 {
                        // S-06 v2 (SPLIT-11): more than they owe; S-11c says what.
                        Text("That’s \(Format.amount(overBy)) more than \(person.name) owes. Next you’ll say what the extra is.")
                            .font(Nacre.footnote).foregroundColor(Pearl.moneyOut)
                            .fixedSize(horizontal: false, vertical: true)
                    }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            Button(finding ? (inParts ? "Save" : "Link payment") : how == "bank" ? "Find it"
                   : overBy >= 0.005 ? "Next: the extra \(Format.amount(overBy))" : "Mark paid back") {
                if !finding && overBy >= 0.005 {
                    pieces = []
                    extraAmount = ""
                    error = nil
                    extraPage = true
                } else {
                    Task { await primary() }
                }
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
                option("app", "Another app", "Pearl won’t look for it in your bank")
            }
            if how != "bank" {
                GlassCard {
                    if how == "app" {
                        // S-06 v3: App on top, only for Another app. Optional.
                        HStack {
                            Text("App").font(Nacre.body).foregroundColor(Pearl.ink)
                            TextField("", text: $appName, prompt: Text("Which app?").foregroundColor(Pearl.muted))
                                .font(Nacre.body).multilineTextAlignment(.trailing)
                                .textInputAutocapitalization(.words).autocorrectionDisabled()
                                .foregroundColor(Pearl.muted)
                                .onChange(of: appName) { v in if v.count > 30 { appName = String(v.prefix(30)) } }
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52)
                        RowSeparator()
                    }
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
                if how == "app" { appHelp }
            }
        }
        .task { await loadApps() }
    }

    /// S-06 v3: "Used before" chips (S-06 v3a: none yet), and what the
    /// split will say.
    @ViewBuilder private var appHelp: some View {
        if !usedApps.isEmpty {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    Text("Used before").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    ForEach(usedApps, id: \.self) { a in
                        let on = a.caseInsensitiveCompare(appName.trimmingCharacters(in: .whitespaces)) == .orderedSame
                        Button(a) { appName = a }
                            .font(Nacre.subheadline).foregroundColor(Pearl.ink)
                            .padding(.horizontal, 14).frame(minHeight: 36)
                            .background(Capsule().fill(on ? Pearl.answered : Pearl.card))
                            .buttonStyle(.plain)
                            .accessibilityAddTraits(on ? .isSelected : [])
                    }
                }
                .padding(.horizontal, 16)
            }
            Text("Shows on the split as “Paid back · \(appLabel) · \(Format.short(Format.isoDay(when)))”. Apps you’ve named before appear here.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
        } else {
            Text("Name the app so the split shows where it came from. You can leave it blank: it then reads “Paid back · Another app”.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted).padding(.horizontal, 16)
        }
    }

    private var appLabel: String {
        let a = appName.trimmingCharacters(in: .whitespaces)
        return a.isEmpty ? "Another app" : a
    }

    private func loadApps() async {
        struct Reply: Decodable { let apps: [String] }
        if let r: Reply = try? await api.get("api/split/apps") { usedApps = r.apps }
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

    /// S-26 when it takes more than one deposit (or part of one); S-29,
    /// one payment that looks like theirs, otherwise.
    private var inParts: Bool {
        picked.count > 1 || deposits.contains { abs(min($0.whole, $0.part ?? $0.whole) - person.owes) >= 0.005 && picked.contains($0.id) }
    }

    /// The likely ones and, while searching, what the search found.
    private var shown: [Candidate] {
        query.trimmingCharacters(in: .whitespaces).isEmpty ? deposits
            : found + deposits.filter { d in picked.contains(d.id) && !found.contains { $0.id == d.id } }
    }

    private func search() async {
        let q = query.trimmingCharacters(in: .whitespaces)
        guard !q.isEmpty else { found = []; return }
        struct Reply: Decodable { let deposits: [Lenient<Candidate>]? }
        let r: Reply? = try? await api.get("api/transactions/\(t.id)/deposits", query: ["q": q])
        let more = (r?.deposits ?? []).compactMap { $0.value }
        found = more
        for d in more where !deposits.contains(where: { $0.id == d.id }) { deposits.append(d) }
    }

    /// S-26: "DAD'S SHARE · $428.00", their deposits to tick, and how far
    /// they go towards it.
    private var depositList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(shown.isEmpty ? "NO DEPOSITS LOOK LIKE IT YET"
                 : !query.isEmpty ? "FOUND"
                 : inParts ? "\(person.name.uppercased())’S SHARE · \(Format.amount(person.amount))" : "LOOKS LIKE THIS ONE")
                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted).padding(.horizontal, 16)
            if !shown.isEmpty {
                GlassCard {
                    ForEach(Array(shown.enumerated()), id: \.element.id) { i, d in
                        if i > 0 { RowSeparator() }
                        depositRow(d)
                    }
                }
            }
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted)
                TextField("", text: $query, prompt: Text("Search any purchase").foregroundColor(Pearl.muted))
                    .font(Nacre.body).autocorrectionDisabled()
            }
            .padding(.horizontal, 14).frame(height: 44)
            .background(Capsule().fill(Pearl.ink.opacity(0.08)))
            .task(id: query) {
                try? await Task.sleep(nanoseconds: 250_000_000)
                if !Task.isCancelled { await search() }
            }
            if !deposits.isEmpty && inParts {
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

    // MARK: S-11c What's the extra? (SPLIT-19)

    /// What she typed, for cash or an app.
    private var typed: Double? {
        Double(amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: ""))
    }

    /// What they paid over what they owe, for cash or an app.
    private var overBy: Double {
        guard how != "bank", let value = typed else { return 0 }
        return max(0, Double(cents(value) - cents(person.owes)) / 100)
    }

    private var extraLeft: Double {
        Double(max(0, cents(overBy) - pieces.map { cents($0.amount) }.reduce(0, +))) / 100
    }

    private var extraChosen: Double {
        let text = extraAmount.trimmingCharacters(in: .whitespaces)
        guard !text.isEmpty else { return extraLeft }
        let v = Double(text.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")) ?? 0
        return min(v, extraLeft)
    }

    /// "Sam · Cash", "Sam · PayPal".
    private var paidHow: String {
        how == "app" ? (appName.trimmingCharacters(in: .whitespaces).isEmpty ? "Another app"
                        : appName.trimmingCharacters(in: .whitespaces)) : "Cash"
    }

    private var extraSheet: some View {
        VStack(spacing: 0) {
            SheetTitle(title: choosingShares ? "Who paid you back?" : "What’s the extra \(Format.amount(extraLeft))?") {
                // Close goes back to S-06 v2 with the amount still typed.
                if choosingShares { choosingShares = false; return }
                pieces = []
                extraPage = false
            }
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    HStack(spacing: 12) {
                        Initials(name: person.name, size: 48)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(person.name) · \(paidHow)").font(Nacre.title2).foregroundColor(Pearl.ink)
                            Text("\(Format.amount(typed ?? 0)) · \(Format.short(Format.isoDay(when)))")
                                .font(Nacre.subheadline).foregroundColor(Pearl.moneyIn)
                        }
                    }
                    .accessibilityElement(children: .combine)
                    if choosingShares { shareList } else { extraTiles }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            if choosingShares {
                Button("Next") { takeShares() }
                    .buttonStyle(NacreButtonStyle(busy: busy)).disabled(busy || ticked.isEmpty)
                    .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
            }
        }
        .background(SheetBackground())
        .presentationDetents([.large])
    }

    private var extraTiles: some View {
        VStack(alignment: .leading, spacing: 12) {
            HStack {
                Text("How much of it?").font(Nacre.body).foregroundColor(Pearl.ink)
                Spacer(minLength: 8)
                TextField("", text: $extraAmount, prompt: Text(Format.amount(extraLeft)).foregroundColor(Pearl.ink))
                    .font(Nacre.headline).monospacedDigit().multilineTextAlignment(.trailing)
                    .keyboardType(.decimalPad).frame(maxWidth: 140)
                    .accessibilityLabel("How much of it")
                    .accessibilityHint("All \(Format.amount(extraLeft)) unless you type less")
            }
            .padding(.horizontal, 4)
            Text("THE EXTRA").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                .padding(.horizontal, 16).accessibilityAddTraits(.isHeader)
            CaseGrid(cases: CaseTile.cashExtra(who: person.name, app: how == "app"),
                     chosen: Binding(get: { nil }, set: { key in if let key = key { takeExtra(key) } }))
                .disabled(busy)
            Text("\(person.name) owes \(Format.amount(person.owes)) for \(t.merchant). Nothing is saved until you say what the other \(Format.amount(extraLeft)) is.")
                .font(Nacre.footnote).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
        }
    }

    /// S-09 for the extra: their other open shares first, ticked, then
    /// everyone else's. A tick takes what it owes, up to "How much of it?".
    private var shareList: some View {
        VStack(alignment: .leading, spacing: 8) {
            Text(shares.isEmpty ? "NOBODY ELSE OWES YOU" : "OPEN SHARES · \(Format.amount(extraChosen))")
                .font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted).padding(.horizontal, 16)
            if !shares.isEmpty {
                GlassCard {
                    ForEach(Array(shares.enumerated()), id: \.element.id) { i, s in
                        if i > 0 { RowSeparator() }
                        let on = ticked[s.id] != nil
                        let room = cents(extraChosen) - ticked.values.map { cents($0) }.reduce(0, +)
                        Button {
                            if on { ticked[s.id] = nil }
                            else if room > 0 { ticked[s.id] = Double(min(cents(s.owes), room)) / 100 }
                        } label: {
                            HStack {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.merchant).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
                                    Text("\(s.person) · owes \(Format.amount(s.owes)) · \(Format.short(s.date))")
                                        .font(Nacre.footnote).foregroundColor(Pearl.muted)
                                }
                                Spacer()
                                Text(Format.amount(ticked[s.id] ?? s.owes)).font(Nacre.headline).monospacedDigit()
                                Image(systemName: on ? "checkmark.circle.fill" : "circle")
                                    .font(.system(size: 22)).foregroundColor(on ? Pearl.action : Pearl.muted)
                            }
                            .padding(.horizontal, 16).frame(minHeight: 56).contentShape(Rectangle())
                            .opacity(!on && room <= 0 ? 0.5 : 1)
                        }
                        .buttonStyle(.plain)
                        .disabled(!on && room <= 0)
                        .accessibilityAddTraits(on ? .isSelected : [])
                    }
                }
            }
        }
    }

    private func takeExtra(_ key: String) {
        let chosen = extraChosen
        guard chosen >= 0.005 else { return }
        error = nil
        if key == "payback" {
            Task { await loadShares() }
            return
        }
        pieces.append(ExtraPiece(kind: key, amount: chosen))
        afterPiece()
    }

    private func takeShares() {
        for s in shares {
            guard let use = ticked[s.id], use >= 0.005 else { continue }
            pieces.append(ExtraPiece(kind: "payback", amount: use, charge: s.charge, person: s.person))
        }
        ticked = [:]
        choosingShares = false
        afterPiece()
    }

    /// Back for what's left of the extra, or save when all of it is said.
    private func afterPiece() {
        extraAmount = ""
        if cents(extraLeft) == 0 { Task { await saveExtra() } }
    }

    private func loadShares() async {
        struct Item: Decodable {
            let chargeId: String
            let merchant: String
            let date: String
            let owes: Double
            enum CodingKeys: String, CodingKey {
                case chargeId = "charge_id"
                case merchant, date, owes
            }
        }
        struct Row: Decodable { let name: String; let items: [Lenient<Item>] }
        struct Reply: Decodable { let owesYou: [Lenient<Row>]
            enum CodingKeys: String, CodingKey { case owesYou = "owes_you" } }
        do {
            let r: Reply = try await api.get("api/owed")
            let taken = Set(pieces.compactMap { p in p.charge.map { $0 + "|" + (p.person ?? "") } })
            var out: [OpenShare] = []
            for row in r.owesYou.compactMap({ $0.value }) {
                let theirs = row.name.caseInsensitiveCompare(person.name) == .orderedSame
                for i in row.items.compactMap({ $0.value }) where i.chargeId != t.id {
                    let s = OpenShare(charge: i.chargeId, merchant: i.merchant, date: i.date,
                                      person: row.name, owes: i.owes, theirs: theirs)
                    if !taken.contains(s.id) { out.append(s) }
                }
            }
            // Theirs first, then everyone else's (S-09, aa07127).
            shares = out.enumerated().sorted { a, b in
                a.element.theirs != b.element.theirs ? a.element.theirs : a.offset < b.offset
            }.map(\.element)
            var room = cents(extraChosen)
            ticked = [:]
            for s in shares where s.theirs && room > 0 {
                let use = min(cents(s.owes), room)
                ticked[s.id] = Double(use) / 100
                room -= use
            }
            choosingShares = true
        } catch {
            self.error = "Couldn’t load who owes you. Try again."
        }
    }

    private func saveExtra() async {
        guard let value = typed else { return }
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["name": person.name, "amount": value, "day": Format.isoDay(when),
                                   "via": how == "app" ? "app" : "cash", "extra": pieces.map(\.body)]
        let named = appName.trimmingCharacters(in: .whitespaces)
        if how == "app" && !named.isEmpty { body["app"] = named }
        do {
            struct Reply: Decodable { let undo: JSONValue? }
            let r: Reply = try await api.post("api/transactions/\(t.id)/split/cash", body)
            let title = "\(person.name) paid \(Format.amount(value))."
            if let onUndoable = onUndoable { onUndoable(title, r.undo) } else { onDone(title) }
        } catch {
            // Nothing was saved: start the extra again.
            pieces = []
            self.error = error.localizedDescription
        }
    }

    private func cents(_ x: Double) -> Int { Int((x * 100).rounded()) }

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
                // SPLIT-11: another app is recorded like cash, but never
                // offered as cash a deposit holds.
                var body: [String: Any] = ["name": person.name, "amount": value, "day": Format.isoDay(when),
                                           "via": how == "app" ? "app" : "cash"]
                // SPLIT-14: the app's name, when she gave one.
                let named = appName.trimmingCharacters(in: .whitespaces)
                if how == "app" && !named.isEmpty { body["app"] = named }
                let _: OK = try await api.post("api/transactions/\(t.id)/split/cash", body)
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


/// A row she can swipe left to take out (2026-11-08), like Mail's.
struct SwipeToRemove<Content: View>: View {
    var enabled = true
    let label: String
    let onRemove: () -> Void
    @ViewBuilder var content: () -> Content
    @State private var offset: CGFloat = 0
    private let reveal: CGFloat = 88

    var body: some View {
        ZStack(alignment: .trailing) {
            if offset < 0 {
                Button(action: onRemove) {
                    Text("Remove").font(Nacre.footnote.weight(.semibold)).foregroundColor(.white)
                        .frame(width: max(-offset, 0)).frame(maxHeight: .infinity)
                        .background(Pearl.moneyOut)
                }
                .buttonStyle(.plain)
            }
            content()
                .offset(x: offset)
        }
        .clipped()
        .contentShape(Rectangle())
        .gesture(enabled ? DragGesture(minimumDistance: 20)
            .onChanged { v in
                guard abs(v.translation.width) > abs(v.translation.height) else { return }
                let start: CGFloat = offset <= -reveal ? -reveal : 0
                offset = min(0, max(-reveal * 1.6, start + v.translation.width))
            }
            .onEnded { v in
                if offset < -reveal * 1.4 {
                    onRemove()
                    offset = 0
                } else {
                    withAnimation(.spring()) { offset = offset < -reveal / 2 ? -reveal : 0 }
                }
            } : nil)
        .accessibilityAction(named: "Remove \(label)") { if enabled { onRemove() } }
    }
}
