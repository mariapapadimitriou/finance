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
    /// S-03re (REFRESH-02): opened from S-40's Change their share, on
    /// Amounts with that person's field focused; saving says "Split
    /// updated" with the server's Undo (S-44i).
    var focus: String? = nil
    var onUpdated: ((String, JSONValue?) -> Void)? = nil
    /// S-45c–e (SPLIT-C): Settle up's Type amounts. Not sure is hidden, each
    /// person shows what they've paid, and a share below that goes to the
    /// extra step first. Gives the toast and the server's Undo.
    var settling = false
    var onSettled: ((String, JSONValue?) -> Void)? = nil
    /// S-41j (JOINT-B): Edit split › Remove the split, on a joint purchase.
    var onRemoveSplit: (() -> Void)? = nil
    /// S-47f: Options on the lock toast; the page opens that person's S-40u.
    var onPersonOptions: ((String) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @Environment(\.dynamicTypeSize) private var typeSize
    @State private var people: [String]
    @State private var withMe = true
    @State private var step = 0
    @State private var typed = ""
    @State private var mode = "even"
    @State private var values: [String: String] = [:]
    @State private var busy = false
    @State private var error: String?
    /// S-17 v2 Add someone (JOINT-A): the people picker, over this sheet.
    @State private var adding = false
    /// S-03fr (REFRESH-02): someone who has paid, swiped away; a Pearl
    /// sheet asks before they go (it replaced the stock alert).
    @State private var removing: Transaction.Splitting.Person?
    /// S-03u at accessibility sizes: the methods as a list sheet.
    @State private var choosingMethod = false
    /// S-45e: the extra step before a settled split saves.
    @State private var sayingExtra = false
    /// TEST-18b: her answers, and who Pearl is asking about now (S-48a/b).
    @State private var answers: [String: Answer] = [:]
    @State private var asking: String?
    /// S-47f (TEST-18): the locked row she tapped, as a toast whose Options
    /// opens that person's S-40u.
    @State private var lockNote: String?
    @State private var lockToast: PearlToast.Model?
    @FocusState private var focused: String?

    private static let me = "\u{0}me"
    /// The "left · stays yours" line, scrolled to while typing (TEST-16).
    private static let statusID = "split-status"

    init(t: Transaction, api: APIClient, recent: [String], with names: [String]? = nil,
         title: String? = nil, saveTitle: String = "Save",
         onHold: (([String: Any], Double, Double) -> Void)? = nil, onSaved: @escaping (String) -> Void,
         onRemoved: ((String, JSONValue?) -> Void)? = nil,
         focus: String? = nil, onUpdated: ((String, JSONValue?) -> Void)? = nil,
         settling: Bool = false, onSettled: ((String, JSONValue?) -> Void)? = nil,
         onRemoveSplit: (() -> Void)? = nil, onPersonOptions: ((String) -> Void)? = nil) {
        self.settling = settling
        self.onPersonOptions = onPersonOptions
        self.onSettled = onSettled
        self.onRemoveSplit = onRemoveSplit
        self.onRemoved = onRemoved
        self.focus = focus
        self.onUpdated = onUpdated
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
        _step = State(initialValue: names == nil && focus == nil ? 0 : 1)
        // Her own share as the split was made: a let go made it bigger since.
        // JOINT-B: of her part of a joint purchase.
        let whole = t.splitBase
        let yours = t.splitting.map { s in whole - s.people.map(\.share).reduce(0, +) }
        // TEST-18: a Not sure yet split says whether she's in it.
        let unsureMe: Bool? = t.splitting.flatMap { $0.unsure ? $0.withMe : nil }
        _withMe = State(initialValue: unsureMe ?? yours.map { $0 >= 0.005 } ?? true)
        if let s = t.splitting, s.unsure {
            // SPLIT-C: Edit split opens on Not sure; Settle up on Evenly (S-45c).
            _mode = State(initialValue: settling ? "even" : "unknown")
        } else if let s = t.splitting, let m = s.mode, m != "even" || focus != nil, let yours = yours {
            var v: [String: String] = [:]
            if focus == nil && ["percent", "shares"].contains(m) && s.people.allSatisfy({ $0.weight != nil }) {
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
                // S-03rg (TEST-21): her share isn't filled in, so it gives way
                // (what's left, which is what she saved) until she types it.
                for p in s.people { v[p.name] = Self.plain(p.share) }
            }
            _values = State(initialValue: v)
        }
    }

    /// The person as the split was saved: what they've paid, cash, let go.
    private func saved(_ key: String) -> Transaction.Splitting.Person? {
        t.splitting?.people.first { $0.name == key }
    }

    /// "Split my part" on a joint purchase with a share off (S-03j);
    /// the usual header on "All mine unless I mark it" (S-03j4).
    private var sheetTitle: String {
        if step == 0 { return "Who was it with?" }
        if settling { return "Settle up · type amounts" }
        if let title = title { return title }
        if let focus = focus { return "Change \(possessive(focus)) share" }
        return t.splitsMyPart ? "Split my part" : "How to split"
    }

    var body: some View {
        // The keyboard's Done bar (TEST-16) needs a navigation stack to
        // live in; its own bar stays hidden.
        NavigationStack {
        VStack(spacing: 0) {
            SheetTitle(title: sheetTitle) { dismiss() }
                // TEST-16: a tap off the fields puts the number pad away.
                .contentShape(Rectangle()).onTapGesture { focused = nil }
            ScrollViewReader { scroller in
            ScrollView {
                VStack(alignment: .leading, spacing: 12) {
                    // S-45c (TEST-02): settling shows the whole purchase, not
                    // the part still counting as hers.
                    QuestionHeader(name: t.merchant,
                                   amount: settling ? (t.inflow ? "+" : "\u{2212}") + Format.amount(t.splitBase) : Format.money(t),
                                   tone: t.tone,
                                   sub: t.splitsMyPart ? "Your part \(Format.amount(t.splitBase)) of \(Format.amount(t.fullAmount ?? t.amount))" : nil)
                        .accessibilityElement(children: .combine)
                        .contentShape(Rectangle()).onTapGesture { focused = nil }
                    if t.splitsMyPart { JointStrip(t: t) }
                    if step == 0 { who } else { how }
                    if let error = error {
                        Text(error).font(Nacre.footnote).foregroundColor(Pearl.caution)
                    }
                }
                .padding(.horizontal, 16).padding(.bottom, 12)
            }
            .scrollDismissesKeyboard(.interactively)
            // TEST-16 (S-03re): with the number pad up, the status line and
            // "Split the rest evenly" stay in view right above Save.
            .onChange(of: focused) { now in
                guard now != nil else { return }
                // Once the pad and its Done bar are up, and again as she types.
                for wait in [0.35, 0.8] {
                    DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
                        withAnimation { scroller.scrollTo(Self.statusID, anchor: .bottom) }
                    }
                }
            }
            // TEST-16 (round 2): typing changes the status line and what's
            // under it ("Split the rest evenly"), which pushed it below the
            // view; keep it in sight while she types.
            .onChange(of: values) { _ in
                guard focused != nil else { return }
                for wait in [0.1, 0.5] {
                    DispatchQueue.main.asyncAfter(deadline: .now() + wait) {
                        withAnimation { scroller.scrollTo(Self.statusID, anchor: .bottom) }
                    }
                }
            }
            // Once the pad has finished coming up, and the sheet has made room.
            .onReceive(NotificationCenter.default.publisher(for: UIResponder.keyboardDidShowNotification)) { _ in
                guard focused != nil else { return }
                withAnimation { scroller.scrollTo(Self.statusID, anchor: .bottom) }
            }
            }
            // TEST-16 / TEST-22 (round 2): Save is the scroll view's sibling,
            // not an inset on it. As an inset, the content under it didn't
            // make room with the number pad up or at AX sizes, so Save sat on
            // "I had some too" and the meter. Here the scroll view ends where
            // Save begins, and the meter and status line scroll above it.
            footer
        }
        .background(SheetBackground())
        // S-47f (TEST-18): "Priya’s $25.00 is linked…", with Options.
        .overlay(alignment: .top) {
            if let m = lockToast {
                PearlToast(model: m) { withAnimation { lockToast = nil } }.padding(.top, 52)
            }
        }
        // TEST-16 (designBOT's answer): Done over every number pad here; a
        // tap on the title closes it too.
        .toolbar {
            ToolbarItemGroup(placement: .keyboard) {
                Spacer()
                Button("Done") { focused = nil }.tint(Pearl.action).foregroundColor(Pearl.action)
            }
        }
        .toolbar(.hidden, for: .navigationBar)
        }
        .presentationDetents([.large])
        .presentationDragIndicator(.visible)
        .onDisappear { UISegmentedControl.appearance().selectedSegmentTintColor = nil }
        .onAppear {
            // S-03re: that person's field, ready to type.
            if let focus = focus {
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.5) { focused = focus }
            }
        }
        .sheet(item: $removing) { p in
            // S-03fr / S-03fr2: here it only takes them off the list; Save sends it.
            RemovePersonSheet(p: p, merchant: t.merchant,
                              countsAgain: t.splitting.flatMap { $0.unsure ? ($0.still ?? $0.you) + p.paid : nil },
                              onClose: { removing = nil }) {
                removing = nil
                remove(p.name)
            }
        }
        .sheet(isPresented: $adding) {
            // S-17 v2 (JOINT-A): people she's split with, contacts, Type a
            // name. S-17j: on a joint purchase its holders are left out.
            PeoplePicker(api: api, overline: (t.splitsMyPart ? "Split my part · " : "Split · ") + t.merchant,
                         title: "Add someone",
                         // S-17j (REFRESH-03): "Sam Lee’s part is already off."
                         sub: t.joint.isEmpty || t.jointPeople.isEmpty ? nil
                             : "\(possessive(t.jointWho)) part\(t.jointPeople.count == 1 ? " is" : "s are") already off.",
                         txn: t.joint.isEmpty ? nil : t.id, already: people, refused: t.jointPeople,
                         onClose: { adding = false }) { names in
                for name in names where !people.contains(name) { people.append(name) }
                adding = false
                // Straight on to How to split (2026-11-08): who it was with is settled.
                if !people.isEmpty { step = 1 }
            }
        }
        .sheet(isPresented: $choosingMethod) {
            SplitMethodSheet(modes: modes, chosen: mode, onPick: { m in mode = m; choosingMethod = false },
                             onClose: { choosingMethod = false })
        }
        .sheet(isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } })) {
            if let key = asking {
                // S-48a / S-48b: one person at a time.
                let all = people.filter { payer($0) && shareCents($0) != lockedCents($0) && answers[$0] == nil }
                    + people.filter { answers[$0] != nil && answers[$0] != .theirShare }
                MismatchSheet(name: key, paid: Double(lockedCents(key)) / 100, share: Double(shareCents(key)) / 100,
                              even: mode == "even", step: answers.count + 1, of: max(all.count, answers.count + 1),
                              others: rows.filter { $0 != key && !locked($0) }.map { $0 == Self.me ? "you" : $0 },
                              onBack: { asking = nil; answers = [:] }) { answer in
                    answers[key] = answer
                    // Each answer can change the others: ask the next, or settle.
                    asking = nil
                    DispatchQueue.main.asyncAfter(deadline: .now() + 0.45) {
                        if let next = toCheck.first { asking = next }
                    }
                }
            }
        }
        .sheet(isPresented: $sayingExtra) {
            SettleExtraSheet(api: api, merchant: t.merchant, chargeId: t.id, over: overList,
                             onClose: { sayingExtra = false }) { extra in
                try await saveSettled(extra: extra)
                sayingExtra = false
            }
        }
    }

    /// The methods (S-03u): Not sure is the fifth, hidden while settling (S-45c).
    private var modes: [(tag: String, label: String)] {
        // THL-303 lock (TEST-18): a locked row is its amount on every
        // method; on Shares it isn't in the shares (S-45c4).
        [("even", "Evenly"), ("amount", "Amounts"), ("percent", "%"), ("shares", "Shares")]
            + (settling ? [] : [("unknown", "Not sure")])
    }

    /// TEST-18b (option C): on Settle up a payer stays at what they paid
    /// while she types amounts, and when she answers "Sam's share is
    /// $20.00"; on Evenly, % and Shares the method runs over everyone and
    /// Pearl asks about any payer whose share comes out different.
    private func payer(_ key: String) -> Bool {
        settling && key != Self.me && (saved(key)?.paid ?? 0) >= 0.005
    }
    private func locked(_ key: String) -> Bool {
        // On % a payer's percent is what they paid of the whole (S-45c3),
        // so like Amounts it can't differ.
        payer(key) && (mode == "amount" || mode == "percent" || answers[key] == .theirShare)
    }
    private var anyLocked: Bool { people.contains { locked($0) } }

    private func lockWords(_ key: String) -> String {
        // S-47f2: on Settle up a payment stays; Pearl asks if the share differs.
        "\(possessive(key)) \(Format.amount(Double(lockedCents(key)) / 100)) is linked, so it stays. If \(possessive(key)) share comes out different, Pearl asks you."
    }

    /// S-48a/b: how she answered for each payer whose share differs.
    enum Answer: Equatable { case ask, theirShare, iOwe, gift }

    /// Payers whose share differs from what they paid, not yet answered.
    private var toCheck: [String] {
        people.filter { payer($0) && !locked($0) && shareCents($0) != lockedCents($0) && answers[$0] == nil }
    }

    /// S-47f: the toast, with Options when the page can open S-40u.
    private func showLock(_ key: String) {
        lockNote = key
        guard let open = onPersonOptions else { return }
        withAnimation {
            lockToast = PearlToast.Model(text: lockWords(key), action: "Options", failed: true,
                                         run: { lockToast = nil; open(key) })
        }
    }
    private func lockedCents(_ key: String) -> Int { Int(((saved(key)?.paid ?? 0) * 100).rounded()) }

    // MARK: S-03fr Removing someone who has paid (SPLIT-02, REFRESH-02)

    /// Someone with a payback or cash asks first (S-03fr); anyone else, or
    /// someone whose share was only let go, goes at once.
    private func askRemove(_ name: String) {
        if let p = saved(name), p.paid >= 0.005 { removing = p } else { remove(name) }
    }

    // MARK: S-17 Add someone: PeoplePicker (JointSplitViews.swift), JOINT-A.

    /// S-02's card has its line; S-03r2's is the toggle alone (`compact`).
    private func withMeCard(compact: Bool = false) -> some View {
        GlassCard {
            Toggle(isOn: $withMe) {
                VStack(alignment: .leading, spacing: 2) {
                    Text("I had some too").font(Nacre.body).foregroundColor(Pearl.ink)
                    if !compact {
                        Text("Turn off if it was all for them").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    }
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
                    Button("Add", action: addTyped).font(Nacre.textButton).foregroundColor(Pearl.link)
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
            withMeCard()
        }
    }

    private var addNewRow: some View {
        Button { adding = true } label: {
            HStack {
                Text("Add someone new").font(Nacre.body).foregroundColor(Pearl.link)
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

    @ViewBuilder private var methodControl: some View {
        if typeSize.isAccessibilitySize {
            // S-03u: at accessibility sizes the segments don't fit; one 44 pt row opens the list.
            Button { choosingMethod = true } label: {
                HStack {
                    Text("How to split · \(mode == "unknown" ? "Not sure yet" : modes.first { $0.tag == mode }?.label ?? "")")
                        .font(Nacre.body).foregroundColor(Pearl.ink)
                        .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    Image(systemName: "chevron.right").foregroundColor(Pearl.muted).accessibilityHidden(true)
                }
                .padding(.horizontal, 16).frame(minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
        } else {
            Picker("", selection: $mode) {
                ForEach(modes, id: \.tag) { m in
                    Text(m.label).tag(m.tag)
                        .accessibilityLabel(m.tag == "unknown" ? "Not sure yet, split method" : m.label)
                }
            }
            .pickerStyle(.segmented)
        }
    }

    @ViewBuilder private var how: some View {
        VStack(alignment: .leading, spacing: 10) {
            methodControl
                .onChange(of: mode) { m in
                    values = [:]
                    answers = [:]
                    // S-03u: the explainer is read once after the method changes.
                    if m == "unknown" {
                        UIAccessibility.post(notification: .announcement, argument: unsureWords)
                    }
                }
            if mode == "unknown" { unsureHow } else { amountsHow }
            if let onRemoveSplit = onRemoveSplit, t.splitting != nil, !settling, focus == nil {
                // S-41j: Edit split › Remove the split.
                Button("Remove the split", action: onRemoveSplit)
                    .font(Nacre.textButton).foregroundColor(Pearl.link)
                    .frame(maxWidth: .infinity, minHeight: 44)
            }
        }
    }

    // MARK: S-03u Not sure yet (SPLIT-C)

    /// REFRESH-03 (S-03u): the info card's one line.
    private var unsureWords: String {
        "No amounts yet. Paybacks come off as they arrive."
    }

    private var unsureHow: some View {
        VStack(alignment: .leading, spacing: 10) {
            HStack(alignment: .top, spacing: 10) {
                Image(systemName: "info.circle").font(.system(size: 18)).foregroundColor(Pearl.ink)
                    .accessibilityHidden(true)
                VStack(alignment: .leading, spacing: 2) {
                    Text("Not sure yet").font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.ink)
                    Text(unsureWords).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 0)
            }
            .padding(14)
            .pearlCard(radius: Pearl.radiusTile)
            .accessibilityElement(children: .combine)
            // S-03u2 / S-03u3 (TEST-18): "I had some too", on by default.
            withMeCard()
            GlassCard {
                if withMe {
                    // S-03u2: her own row, with no amount.
                    HStack(spacing: 12) {
                        Initials(name: "Me", size: 34)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("You").font(Nacre.body).foregroundColor(Pearl.ink)
                            Text("Your share · set it any time, or never").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                    .accessibilityElement(children: .combine)
                    if !people.isEmpty { RowSeparator(inset: 64) }
                }
                ForEach(Array(people.enumerated()), id: \.element) { i, name in
                    if i > 0 { RowSeparator(inset: 64) }
                    HStack(spacing: 12) {
                        Initials(name: name, size: 34)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                            Text("Any amount they send you").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        .accessibilityElement(children: .combine)
                        .accessibilityLabel("\(name), any amount they send you")
                        Spacer(minLength: 8)
                        Button { askRemove(name) } label: {
                            Image(systemName: "xmark").font(.system(size: 15, weight: .medium)).foregroundColor(Pearl.ink)
                                .frame(width: 44, height: 44).background(Circle().fill(Pearl.control))
                        }
                        .buttonStyle(.plain)
                        .accessibilityLabel("Remove \(name)")
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                }
                if !people.isEmpty { RowSeparator() }
                addNewRow
            }
        }
    }

    private var amountsHow: some View {
        VStack(alignment: .leading, spacing: 10) {
            if settling { withMeCard() }
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
                                    .foregroundColor(settling && (saved(key)?.paid ?? 0) >= 0.005 ? Pearl.action
                                                     : overCents(key) > 0 ? Pearl.moneyOut : Pearl.muted)
                                    .fixedSize(horizontal: false, vertical: true)
                            }
                        }
                        Spacer(minLength: 8)
                        if payer(key) {
                            // S-48c: a payer shows what they paid (on %, as a percent); a tap says why.
                            Text(mode == "percent" ? Self.plain(number(key)) + "%" : Format.amount(Double(lockedCents(key)) / 100))
                                .font(Nacre.body).monospacedDigit().foregroundColor(Pearl.ink)
                        } else if locked(key) {
                            Text(mode == "percent" ? Self.plain(number(key)) + "%" : Format.amount(Double(lockedCents(key)) / 100))
                                .font(Nacre.body).monospacedDigit().foregroundColor(Pearl.ink)
                        } else if mode == "even" {
                            Text(Format.amount(evenAmount(key))).font(Nacre.body).monospacedDigit()
                                .foregroundColor(Pearl.ink)
                        } else {
                            TextField("", text: binding(key), prompt: Text(placeholder(key)).foregroundColor(Pearl.muted))
                                .font(Nacre.body).monospacedDigit().multilineTextAlignment(.trailing)
                                .keyboardType(mode == "shares" ? .numberPad : .decimalPad)
                                .focused($focused, equals: key)
                                .frame(width: 92, height: 36)
                                .padding(.horizontal, 8)
                                .background(RoundedRectangle(cornerRadius: 10).fill(Color.white.opacity(0.8)))
                                // S-03re (TEST-16): the outline is on the field
                                // being typed in, or on someone already over.
                                .overlay(RoundedRectangle(cornerRadius: 10)
                                    .strokeBorder(overCents(key) > 0 || focused == key
                                                  ? Pearl.action : Nacre.separator,
                                                  lineWidth: focused == key ? 1.5 : 1))
                                .accessibilityLabel("\(label(key)) \(mode == "percent" ? "percent" : mode == "shares" ? "shares" : "amount")")
                        }
                    }
                    .padding(.horizontal, 16).frame(minHeight: 56)
                    // TEST-14 / TEST-27: a row with no field is one element, so
                    // VoiceOver hears "Priya, $42.50" and the visible words match
                    // what's spoken (a label on the amount alone read as clipped).
                    // A locked payer's whole row says why it's locked.
                    .modifier(TextRow(on: payer(key) || locked(key) || mode == "even",
                                      locked: payer(key) || locked(key),
                                      label: "\(label(key)), paid \(Format.amount(Double(lockedCents(key)) / 100)), locked",
                                      tap: { showLock(key) }))
                    }
                }
                // More people from here, and back to the amounts after (2026-11-08).
                RowSeparator()
                addNewRow
            }
            // S-03r2 / S-03r2b / S-03j v2 (TEST-08): "I had some too" under
            // the people, where its effect is: on, the rest stays yours; off,
            // your row goes and the rest is left to assign.
            if !settling { withMeCard(compact: true) }
            VStack(spacing: 8) {
                // S-03r2: the bar, with what's assigned of the whole.
                SplitBar(others: max(assignedCents - meterMine, 0), mine: meterMine, total: totalCents)
                HStack(alignment: .firstTextBaseline) {
                    if gapCents == 0 && settling && !toCheck.isEmpty {
                        // S-48c: "2 to check: Sam and Priya".
                        Text("\(toCheck.count) to check: \(Format.andList(toCheck))").foregroundColor(Nacre.teal)
                    } else if gapCents == 0 {
                        // S-03e (REFRESH-03): "Adds up ✓ · you owe Priya $8.04"; the
                        // why is a VoiceOver hint. S-03rg (section 20): "Adds up to
                        // $84.12 ✓" beside "$84.12 of $84.12".
                        let over = settling ? "" : overWords
                        Text(over.isEmpty ? addsUp : "Adds up ✓ · \(over)").foregroundColor(Nacre.teal)
                            .accessibilityHint(over.isEmpty ? "" : overHint)
                    } else {
                        // TEST-16: the line is plain ink, never red.
                        Text(gapWords).foregroundColor(Pearl.ink)
                    }
                    Spacer(minLength: 8)
                    Text("\(Format.amount(Double(assignedCents) / 100)) of \(Format.amount(Double(totalCents) / 100))")
                        .foregroundColor(Pearl.muted).monospacedDigit()
                }
                .accessibilityElement(children: .combine)
                if mode == "amount" && gapCents > 0 {
                    Button("Split the rest evenly", action: splitRest)
                        .font(Nacre.textButton).foregroundColor(Pearl.link)
                        .frame(minHeight: 44)
                } else if let take = takeFromMine {
                    // S-03ri: one tap unpins her share; it gives way again.
                    Button("Take \(Format.amount(Double(take) / 100)) from your share") { values[Self.me] = nil }
                        .font(Nacre.textButton).foregroundColor(Pearl.link)
                        .frame(minHeight: 44)
                }
            }
            .font(Nacre.footnote).frame(maxWidth: .infinity)
            .id(Self.statusID)
            if let key = lockNote, onPersonOptions == nil {
                // Where there's no S-40u to open, the note says why.
                InfoNote(text: lockWords(key))
            }
        }
    }

    /// S-45e: who paid more than the share she's setting, and by how much.
    private var overList: [(name: String, amount: Double)] {
        people.compactMap { name in
            let c = overCents(name)
            return c > 0 ? (name, Double(c) / 100) : nil
        }
    }

    private var overTotal: Double { overList.map(\.amount).reduce(0, +) }

    /// S-48c: "Paid $20.00 · locked · even share $33.33, Pearl asks next",
    /// then what she answered.
    private func payerLine(_ key: String, paid: Double) -> String {
        let share = Double(shareCents(key)) / 100
        let diff = Format.amount(abs(share - paid))
        if locked(key) || shareCents(key) == lockedCents(key) {
            return ["Paid \(Format.amount(paid))", "locked",
                    mode == "shares" && locked(key) ? "not in the shares" : nil].compactMap { $0 }.joined(separator: " · ")
        }
        let kind = mode == "even" ? "even share" : "share"
        switch answers[key] {
        case .ask?: return "Paid \(Format.amount(paid)) · ask \(key) for \(diff)"
        case .iOwe?: return "Paid \(Format.amount(paid)) · you owe \(key) \(diff)"
        case .gift?: return "Paid \(Format.amount(paid)) · \(diff) is a gift"
        default: return "Paid \(Format.amount(paid)) · locked · \(kind) \(Format.amount(share)), Pearl asks next"
        }
    }

    private var extraNote: String? {
        guard let first = overList.first, saved(first.name) != nil else { return nil }
        let more = overList.count > 1 ? " The others too." : ""
        // REFRESH-03: "Sam paid $10.00 more than this. You’ll sort the extra next."
        return "\(first.name) paid \(Format.amount(first.amount)) more than this. You’ll sort the extra next.\(more)"
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
        default:
            // TEST-16: left empty, your field shows what it saves as, the
            // "Your share" under your name, not $0.00.
            if key == Self.me && withMe && mineCents > 0 { return Format.amount(Double(mineCents) / 100) }
            return "$0.00"
        }
    }

    private func binding(_ key: String) -> Binding<String> {
        Binding(get: { values[key] ?? "" }, set: { values[key] = $0 })
    }

    private func number(_ key: String) -> Double {
        if locked(key) {
            // A locked row is what they paid: dollars, or that as a percent.
            let cents = Double(lockedCents(key))
            return mode == "percent" ? (cents / Double(max(totalCents, 1)) * 10000).rounded() / 100 : cents / 100
        }
        return typedNumber(key)
    }

    private func typedNumber(_ key: String) -> Double {
        Double((values[key] ?? "").replacingOccurrences(of: "$", with: "").replacingOccurrences(of: "%", with: "")
            .replacingOccurrences(of: ",", with: "")) ?? (mode == "shares" ? 1 : 0)
    }

    /// JOINT-B: her part of a joint purchase is what's split (S-03j).
    private var totalCents: Int { Int(t.splitBase * 100 + 0.5) }

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
    /// THL-303: with locked rows, only what's left is split, between the rest.
    private var evenCents: [String: Int] {
        if anyLocked {
            let fixed = rows.filter { locked($0) }
            let free = rows.filter { !locked($0) }
            let left = max(totalCents - fixed.reduce(0) { $0 + lockedCents($1) }, 0)
            var out = Dictionary(uniqueKeysWithValues: fixed.map { ($0, lockedCents($0)) })
            guard !free.isEmpty else { return out }
            let each = left / free.count
            let odd = spread(left - each * free.count, over: free)
            for k in free { out[k] = each + (odd[k] ?? 0) }
            return out
        }
        return plainEvenCents
    }

    private var plainEvenCents: [String: Int] {
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
        if anyLocked {
            // S-45c4: the shares divide only what's left, across the rows
            // that aren't locked; a locked row is what they paid.
            let fixed = rows.filter { locked($0) }
            let free = rows.filter { !locked($0) }
            let left = max(totalCents - fixed.reduce(0) { $0 + lockedCents($1) }, 0)
            let sum = free.map { typedNumber($0) }.reduce(0, +)
            var out = Dictionary(uniqueKeysWithValues: fixed.map { ($0, lockedCents($0)) })
            guard sum > 0 else { return out.mapValues { Double($0) / 100 } }
            for k in free { out[k] = Int((Double(left) * typedNumber(k) / sum).rounded(.down)) }
            let odd = spread(left - free.reduce(0) { $0 + (out[$1] ?? 0) }, over: free)
            for (k, c) in odd { out[k, default: 0] += c }
            return out.mapValues { Double($0) / 100 }
        }
        return weighted(over: weightSum, spreading: true).mapValues { Double($0) / 100 }
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
        if locked(key) { return lockedCents(key) }
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
        if key == Self.me && withMe && mode == "amount" {
            // S-03rg / S-03rh / S-03ri (TEST-21).
            bits.append(givesWay ? (restCents < 0 ? "Your share · can’t go below $0.00" : "Your share · gives way · what’s left")
                        : "Your share · you typed it")
        } else if key == Self.me && withMe && gapCents > 0 {
            // S-03b v2 (REFRESH-03): "Your share $44.12", before saving; the
            // rest is said once, under the total.
            bits.append("Your share \(Format.amount(Double(mineCents) / 100))")
        }
        if mode == "shares" && anyLocked && !locked(key) {
            // S-45c4: "1 share · $20.00".
            let n = typedNumber(key)
            bits.append("\(Self.plain(n)) share\(abs(n - 1) < 0.001 ? "" : "s") · \(Format.amount(Double(cents) / 100))")
        }
        if mode == "percent" && gapCents == 0 {
            bits.append(Format.amount(Double(cents) / 100) + (mineOdd ? " · the odd cent is yours" : ""))
        } else if mode == "even" && mineOdd {
            bits.append("Includes the odd cent")
        }
        if settling, key != Self.me {
            // S-45c–e: what each person has paid so far; THL-303: locked.
            let paid = saved(key)?.paid ?? 0
            bits.append(paid >= 0.005 ? payerLine(key, paid: paid) : "Nothing paid yet")
            return bits.joined(separator: " · ")
        }
        if let p = saved(key), key != Self.me {
            let over = overCents(key)
            if p.paid >= 0.005 {
                let how = (p.cash ?? 0) >= p.paid - 0.005 ? " cash" : ""
                // TEST-16 (THL-289): "Paid back $30.00" for a share paid in
                // full, "Paid $10.00 of $30.00" for part of it.
                let share = Double(cents) / 100
                var line = over == 0 && p.paid >= share - 0.005 ? "Paid back \(Format.amount(p.paid))\(how)"
                    : over == 0 ? "Paid \(Format.amount(p.paid)) of \(Format.amount(share))\(how)"
                    : "Paid \(Format.amount(p.paid))\(how)"
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
            } else if focus != nil {
                // S-03re: each row's status, "Owes you" for nothing paid yet.
                bits.append("Owes you")
            }
        }
        return bits.isEmpty ? nil : bits.joined(separator: " · ")
    }

    /// S-03e (REFRESH-03): "you owe Priya $8.04", after "Adds up ✓ ·".
    private var overWords: String {
        let over = people.map { ($0, overCents($0)) }.filter { $0.1 > 0 }
        guard !over.isEmpty else { return "" }
        return over.map { name, c in "you owe \(name) \(Format.amount(Double(c) / 100))" }.joined(separator: " · ")
    }

    /// What the S-03e line used to spell out, for VoiceOver (names, not
    /// pronouns): "Priya paid $8.04 more than Priya’s share. It shows under
    /// You owe in Owed to you."
    private var overHint: String {
        let over = people.map { ($0, overCents($0)) }.filter { $0.1 > 0 }
        guard !over.isEmpty else { return "" }
        return over.map { name, c in "\(name) paid \(Format.amount(Double(c) / 100)) more than \(possessive(name)) share." }
            .joined(separator: " ") + " It shows under You owe in Owed to you."
    }

    /// Cents still to give out ("$4.12 left to assign"); negative is too much.
    private var gapCents: Int {
        switch mode {
        case "even", "shares": return 0
        case "percent":
            if percentRounds { return 0 }
            return Int(((100 - rows.map { number($0) }.reduce(0, +)) * 100).rounded())
        default:
            // S-03rg / S-03rh (TEST-21, section 20): until she types her own
            // share it is what's left, so raising someone else adds up; it's
            // only too much once her share would go below $0.00.
            if givesWay { return min(restCents, 0) }
            return restCents
        }
    }

    /// The amounts as typed against the total; an empty row is $0.00.
    private var restCents: Int {
        totalCents - rows.map { Int((number($0) * 100).rounded()) }.reduce(0, +)
    }

    /// S-03ri: she typed her own share, so it's pinned.
    private var mineTyped: Bool {
        !(values[Self.me] ?? "").trimmingCharacters(in: .whitespaces).isEmpty
    }

    /// S-03rg: on Amounts, her row gives way until she types in it. With
    /// "I had some too" off there's no row of hers to give way.
    private var givesWay: Bool { mode == "amount" && withMe && !mineTyped }

    /// S-03ri: "Take $15.88 from your share", when taking it makes it add up.
    private var takeFromMine: Int? {
        guard mode == "amount", withMe, mineTyped, gapCents < 0 else { return nil }
        return Int((number(Self.me) * 100).rounded()) >= -gapCents ? -gapCents : nil
    }

    private var addsUp: String {
        switch mode {
        case "shares":
            // TEST-23: a locked payer is "not in the shares"; their row's
            // number is the dollars they paid, so it isn't counted.
            let n = rows.filter { !locked($0) }.map { number($0) }.reduce(0, +)
            return "\(Self.plain(n)) shares · adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        default: return "Adds up to \(Format.amount(Double(totalCents) / 100)) ✓"
        }
    }

    private var gapWords: String {
        if mode == "percent" {
            let g = Double(gapCents) / 100
            if g > 0 && blocksShort { return "\(Self.plain(g))% left to assign" }
            return g > 0 ? "\(Self.plain(g))% left · stays yours" : "That’s \(Self.plain(-g))% too much"
        }
        let g = Double(abs(gapCents)) / 100
        // S-03b: with "I had some too" off there's no "you" to keep the rest.
        if gapCents > 0 && blocksShort { return "\(Format.amount(g)) left to assign" }
        // S-03rh: her share is already at $0.00.
        if gapCents < 0 && givesWay { return "That’s \(Format.amount(g)) too much, even with your share at $0.00" }
        // S-03b v2 / S-03r / S-03re (REFRESH-03): "$4.12 left · stays yours".
        return gapCents > 0 ? "\(Format.amount(g)) left · stays yours"
            : "That’s \(Format.amount(g)) too much"
    }

    /// SPLIT-01 (b′), S-03b v2 (2026-11-09): short of the total saves only
    /// when she's in it, and the rest is hers; otherwise Save waits, as the
    /// server does.
    private var blocksShort: Bool { gapCents > 0 && !withMe }

    /// S-03r2's bar: what's assigned of the whole, in cents.
    /// TEST-28 (S-03rg): her part of the meter, typed or giving way.
    private var meterMine: Int {
        guard withMe else { return 0 }
        if mode == "amount" { return givesWay ? max(restCents, 0) : Int((number(Self.me) * 100).rounded()) }
        return shareCents(Self.me)
    }

    private var assignedCents: Int {
        switch mode {
        case "amount": return totalCents - gapCents
        case "percent": return percentRounds ? totalCents : min(Int((Double(totalCents) * weightSum / 100).rounded()), totalCents * 10)
        default: return totalCents
        }
    }

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

    /// S-03u "Save split"; S-45e "Next: the extra $10.00".
    private var primaryTitle: String {
        if step == 0 { return "Next" }
        if busy { return "Saving…" }
        if error != nil { return "Try again" }
        // S-48c: "Next · check Sam and Priya".
        if settling && !toCheck.isEmpty { return "Next · check \(Format.andList(toCheck))" }
        if settling { return "Settle up" }
        if mode == "unknown" && saveTitle == "Save" { return "Save split" }
        return saveTitle
    }

    @ViewBuilder private var footer: some View {
        Button(primaryTitle) {
            if step == 0 { addTyped(); step = 1 }
            else if settling, let first = toCheck.first { asking = first }
            else { Task { await save() } }
        }
        .buttonStyle(NacreButtonStyle(busy: busy))
        .disabled(step == 0 ? people.isEmpty && typed.trimmingCharacters(in: .whitespaces).isEmpty
                  : mode == "unknown" ? (people.isEmpty || busy)
                  : (gapCents < 0 || blocksShort || busy))
        .padding(.horizontal, 16).padding(.top, 6).padding(.bottom, 8)
    }

    private func save() async {
        busy = true
        defer { busy = false }
        var body: [String: Any] = ["mode": mode, "include_me": withMe]
        switch mode {
        case "unknown":
            // SPLIT-C: the people only, no amounts. TEST-18: whether she's
            // in it is kept ("I had some too").
            body["people"] = people.map { ["name": $0] }
        case "even":
            body["people"] = people.map { ["name": $0] }
        case "amount":
            body["people"] = people.map { ["name": $0, "amount": number($0)] }
            body["you"] = withMe ? (givesWay ? Double(max(mineCents, 0)) / 100 : number(Self.me)) : 0
        case "percent":
            body["people"] = people.map { ["name": $0, "percent": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        default:
            body["people"] = people.map { ["name": $0, "shares": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        }
        if let onHold = onHold, let first = people.first {
            // S-24 (SPLIT-07): held for the deposit's one save. Not sure yet
            // holds no share for anyone: all of it is hers until paid back.
            if mode == "unknown" { onHold(body, 0, t.splitBase); return }
            onHold(body, Double(shareCents(first)) / 100, Double(mineCents) / 100)
            return
        }
        if settling {
            do {
                try await saveSettled(extra: nil)
            } catch {
                self.error = error.localizedDescription
            }
            return
        }
        do {
            struct Reply: Decodable { let undo: JSONValue?; let toast: String? }
            let reply: Reply = try await api.put("api/transactions/\(t.id)/split", body)
            let n = people.count + (withMe ? 1 : 0)
            // SPLIT-16: someone who had paid was removed: "Priya removed ·
            // Undo" puts their payback back on this purchase.
            let gone = (t.splitting?.people ?? []).filter { p in p.paid >= 0.005 && !people.contains(p.name) }
            if let onRemoved = onRemoved, let first = gone.first {
                onRemoved(reply.toast ?? (gone.count == 1 ? "\(first.name) removed" : "\(gone.count) people removed"),
                          reply.undo)
                return
            }
            if let onUpdated = onUpdated {
                // S-44i: "Split updated · Undo".
                onUpdated(reply.toast ?? "Split updated", reply.undo)
                return
            }
            if mode == "unknown" {
                onSaved(people.count == 1 ? "Split with \(people[0]) · not sure yet." : "Split with \(people.count) · not sure yet.")
                return
            }
            onSaved(n == 2 ? "Split with \(people[0])." : "Split \(n) ways.")
        } catch {
            self.error = error.localizedDescription
        }
    }

    /// What Save would send for the method she's on (S-45c–e reuse it).
    private var settleBody: [String: Any] {
        if people.contains(where: payer) {
            // TEST-18b: the cents each row comes to, with her answers: "Ask
            // Sam" (`ask`), and what a payer's extra is (`extra`).
            var extra: [String: [[String: Any]]] = [:]
            var ask: [String] = []
            for k in people where payer(k) {
                let diff = shareCents(k) - lockedCents(k)
                if diff > 0, answers[k] == .ask { ask.append(k) }
                if diff < 0, let a = answers[k], a == .iOwe || a == .gift {
                    extra[k] = [["kind": a == .iOwe ? "overpaid" : "gift", "amount": Double(-diff) / 100]]
                }
            }
            return ["mode": "amount", "include_me": withMe, "you": withMe ? Double(mineCents) / 100 : 0,
                    "people": people.map { ["name": $0, "amount": Double(shareCents($0)) / 100] },
                    "ask": ask, "extra": extra]
        }
        var body: [String: Any] = ["mode": mode, "include_me": withMe]
        switch mode {
        case "even": body["people"] = people.map { ["name": $0] }
        case "amount":
            body["people"] = people.map { ["name": $0, "amount": number($0)] }
            body["you"] = withMe ? (givesWay ? Double(max(mineCents, 0)) / 100 : number(Self.me)) : 0
        case "percent":
            body["people"] = people.map { ["name": $0, "percent": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        default:
            body["people"] = people.map { ["name": $0, "shares": number($0)] }
            if withMe { body["you"] = number(Self.me) }
        }
        return body
    }

    /// S-45f: Settle up by typed amounts, with S-45e's extra when there is
    /// one. Throws the server's words for the sheet that asked.
    private func saveSettled(extra: [String: [[String: Any]]]?) async throws {
        busy = true
        defer { busy = false }
        var body = settleBody
        if let extra = extra { body["extra"] = extra }
        struct Reply: Decodable { let undo: JSONValue?; let toast: String? }
        do {
            let reply: Reply = try await api.put("api/transactions/\(t.id)/split", body)
            error = nil
            // S-48d: "Settled · Sam owes $13.33 · you owe Priya $6.67";
            // nothing owed either way, "Settled up".
            var bits: [String] = []
            for k in people {
                let diff = shareCents(k) - (saved(k).map { Int(($0.paid * 100).rounded()) } ?? 0)
                if diff > 0 { bits.append("\(k) owes \(Format.amount(Double(diff) / 100))") }
                if diff < 0 && answers[k] == .iOwe { bits.append("you owe \(k) \(Format.amount(Double(-diff) / 100))") }
            }
            onSettled?(reply.toast ?? (bits.isEmpty ? "Settled up" : "Settled · " + bits.joined(separator: " · ")), reply.undo)
        } catch let e as APIError {
            if case .server = e { throw SplitMenuError(words: e.localizedDescription) }
            throw e
        }
    }
}

// MARK: - Who owes what (S-04, S-05, S-19, S-20)

/// The people in a split: what each owes or has paid, and what to do next.
/// REFRESH-02 (S-04r v2 1090:1743): each person has a 44 pt ••• and a
/// paid-back bar; the ••• and the row both open S-40, the one sheet of
/// options for every state (no stock dialog, product owner 2026-11-09).
struct SplitPeople: View {
    let t: Transaction
    let split: Transaction.Splitting
    /// S-40's choice, run once the sheet has gone so the next one can open.
    let onChoose: (Transaction.Splitting.Person, PersonChoice) -> Void
    let onEdit: () -> Void
    let onOwed: () -> Void
    /// S-05u (SPLIT-22b): "Who sent this?" on a payback credited to no one.
    var onCredit: (Transaction.Splitting.Uncredited) -> Void = { _ in }
    /// SPLIT-C (S-04u, S-46c): Settle up, That's everything, Reopen split.
    var onSettle: () -> Void = {}
    var onClose: () -> Void = {}
    var onReopen: () -> Void = {}
    /// TEST-18 (S-40y → S-47): Set your share.
    var onSetShare: () -> Void = {}
    /// S-47f's Options: open this person's S-40u from outside the card.
    var optionsFor: Binding<String?> = .constant(nil)
    @State private var youOptions = false
    /// S-40 for this person.
    @State private var options: Transaction.Splitting.Person?
    @State private var afterOptions: (() -> Void)?
    @Environment(\.accessibilityReduceMotion) private var reduceMotion
    /// TEST-22: at AX sizes a row's amount goes under the name (S-03ax).
    @Environment(\.dynamicTypeSize) private var typeSize
    private var amountsUnder: Bool { typeSize.isAccessibilitySize }

    var body: some View {
        let open = split.people.filter { $0.owes >= 0.005 }
        let unsure = split.uncredited ?? []
        VStack(alignment: .leading, spacing: 8) {
            if !unsure.isEmpty {
                // S-05u 1033:42367 (THL-181): PAID BACK, one row each, newest first.
                Text("PAID BACK").font(Nacre.caption2).tracking(0.4).foregroundColor(Pearl.muted)
                    .padding(.horizontal, 16).padding(.top, 12)
                GlassCard {
                    ForEach(Array(unsure.enumerated()), id: \.element.id) { i, u in
                        if i > 0 { RowSeparator(inset: 64) }
                        uncreditedRow(u)
                    }
                }
            }
            if let joint = split.joint, t.splitsMyPart {
                // S-04j: who's on the joint account, apart from who owes her.
                JointPartCard(t: t, joint: joint)
            }
            VStack(alignment: .leading, spacing: 0) {
                // S-04r v2: "Split 5 ways" with Edit split beside it; S-04j
                // "Your part, split 3 ways"; S-04u "Split with 2 · Not sure yet".
                HStack(alignment: .firstTextBaseline) {
                    VStack(alignment: .leading, spacing: 2) {
                        Text(heading(open: open, unsure: unsure))
                            .font(Pearl.text(.headline, .semibold)).foregroundColor(Pearl.ink)
                            .accessibilityAddTraits(.isHeader)
                        if let line = unsureLine {
                            Text(line).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                        }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(split.unsure ? "Split with \(split.people.count), not sure yet. \(unsureLine ?? "")" : heading(open: open, unsure: unsure))
                    Spacer()
                    if split.closedAt == nil {
                        // TEST-14: the 44 pt frame is the tap area, not only the words.
                        Button(action: onEdit) {
                            Text("Edit split").frame(minWidth: 44, minHeight: 44).contentShape(Rectangle())
                        }
                        .font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.link)
                        .buttonStyle(.plain)
                    }
                }
                .padding(.top, 8)
                if split.unsure && split.withMe {
                    // S-04u6 (TEST-18): her own row first, with its •••.
                    youRow
                    if !split.people.isEmpty { PearlDivider() }
                } else if !split.unsure && split.withMe && split.you >= 0.005 {
                    // S-04r v3 (TEST-18): "You · Your share · $30.00", no •••;
                    // tapping it opens Edit split.
                    setYouRow
                    if !split.people.isEmpty { PearlDivider() }
                }
                ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { PearlDivider() }
                    if split.unsure { unsurePerson(p) } else { person(p) }
                }
            }
            .padding(.horizontal, 16).padding(.vertical, 4)
            .pearlCard(radius: Pearl.radiusTile)
            .padding(.top, 12)
            // A row's amount springs when it changes (S-44): 250 ms, a cross-fade with Reduce Motion.
            .animation(reduceMotion ? .easeInOut(duration: 0.25) : .spring(response: 0.25, dampingFraction: 0.85),
                       value: split.people.map(\.owes))
            .onChange(of: optionsFor.wrappedValue) { name in
                // S-47f: Options on a lock toast, from a sheet over the page.
                guard let name = name, let p = split.people.first(where: { $0.name == name }) else { return }
                optionsFor.wrappedValue = nil
                options = p
            }
            .sheet(item: $options, onDismiss: {
                let next = afterOptions
                afterOptions = nil
                next?()
            }) { p in
                PersonOptionsSheet(t: t, split: split, p: p, onClose: { options = nil }) { choice in
                    afterOptions = { onChoose(p, choice) }
                    options = nil
                }
            }
            if split.unsure {
                // S-04u: Settle up and That's everything; S-46c Reopen split.
                // REFRESH-03: titles alone; what each does is a VoiceOver hint.
                PearlOptionCard {
                    if split.closedAt == nil {
                        PearlOptionRow(symbol: "person.2", title: "Settle up", action: onSettle)
                            .accessibilityHint("Set what each person owes.")
                        PearlDivider()
                        // S-04u8 (TEST-18, note 1238:25742): once everyone has paid.
                        PearlOptionRow(symbol: "checkmark", title: "That’s everything",
                                       sub: everyonePaid ? "Everyone has paid. \(Format.amount(split.still ?? split.you)) stays yours." : nil,
                                       action: onClose)
                            .accessibilityHint("Keeps the rest as yours and closes the split.")
                    } else {
                        PearlOptionRow(symbol: "arrow.triangle.2.circlepath", title: "Reopen split", action: onReopen)
                    }
                }
                .padding(.top, 8)
            }
            if split.closedAt == nil {
                // TEST-14: the whole 44 pt row taps, not only the words.
                Button(action: onOwed) {
                    Text("See everyone who owes you")
                        .frame(maxWidth: .infinity, minHeight: 44).contentShape(Rectangle())
                }
                .font(Nacre.textButton).foregroundColor(Pearl.link).buttonStyle(.plain)
                .padding(.top, 6)
            }
        }
    }

    /// S-04r v3: her share on a split with amounts.
    private var setYouRow: some View {
        Button(action: onEdit) {
            HStack(spacing: 12) {
                PearlFace(name: "Me", size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text("You").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                    Text("Your share").font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    if amountsUnder { youAmount }
                }
                Spacer(minLength: 8)
                if !amountsUnder { youAmount }
            }
            .padding(.vertical, 10).frame(minHeight: 56).contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .disabled(split.closedAt != nil)
        .accessibilityElement(children: .combine)
        .accessibilityLabel("You, your share, \(Format.amount(split.you))")
        .accessibilityHint("Opens Edit split")
        .accessibilityIdentifier("split-you-row")
    }

    private var youAmount: some View {
        Text(Format.amount(split.you)).font(Pearl.text(.headline, .semibold)).monospacedDigit()
            .foregroundColor(Pearl.ink).pearlAmountFit()
    }

    /// S-04u8 (note 1238:25742): everyone but you has a linked or cash
    /// payment, and your share was never set.
    private var everyonePaid: Bool {
        split.unsure && split.closedAt == nil && !split.people.isEmpty && split.people.allSatisfy { $0.paid >= 0.005 }
    }

    private var leftAmount: some View {
        Text(Format.amount(split.still ?? split.you)).font(Pearl.text(.headline, .semibold))
            .monospacedDigit().foregroundColor(Pearl.ink).pearlAmountFit()
    }

    /// S-04u6: "You · Your share · not set yet", and S-40y from its •••.
    /// S-04u8: "Your share · what's left after paybacks · $17.00".
    private var youRow: some View {
        let closed = split.closedAt != nil
        let left = closed || everyonePaid
        return HStack(spacing: 12) {
            Button { if !closed { youOptions = true } } label: {
                HStack(spacing: 12) {
                    PearlFace(name: "Me", size: 40)
                    VStack(alignment: .leading, spacing: 2) {
                        Text("You").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                        Text(closed ? "Your share · what was left"
                             : everyonePaid ? "Your share · what’s left after paybacks" : "Your share · not set yet")
                            .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                        if left && amountsUnder { leftAmount }
                    }
                    Spacer(minLength: 8)
                    if left && !amountsUnder { leftAmount }
                }
                .frame(minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .combine)
            if !closed {
                PearlMoreButton(label: "Options for you") { youOptions = true }
            }
        }
        .padding(.vertical, 10)
        .sheet(isPresented: $youOptions) {
            YouOptionsSheet(t: t, onClose: { youOptions = false }) {
                youOptions = false
                DispatchQueue.main.asyncAfter(deadline: .now() + 0.4) { onSetShare() }
            }
        }
    }

    /// "Split 5 ways", "Your part, split 3 ways" (S-04j), "Split with 2 ·
    /// Not sure yet" (S-04u), "Split with 2 · Closed Nov 20" (S-46c).
    private func heading(open: [Transaction.Splitting.Person], unsure: [Transaction.Splitting.Uncredited]) -> String {
        if split.unsure {
            // S-04u6: "Split 5 ways · Not sure yet" when she's in it.
            let who = split.withMe ? "Split \(split.people.count + 1) ways · " : "Split with \(split.people.count) · "
            return who + (split.closedAt.map { "Closed \(Format.short($0))" } ?? "Not sure yet")
        }
        if !unsure.isEmpty && !open.isEmpty { return "Owed to you" }
        if split.people.count > 1 || t.splitsMyPart {
            let ways = "\(split.people.count + (split.you >= 0.005 ? 1 : 0)) ways"
            return t.splitsMyPart ? "Your part, split \(ways)" : "Split \(ways)"
        }
        return open.isEmpty ? "Paid back" : "Owed to you"
    }

    /// S-46c "You kept $80.00 · nobody owes you". Open (S-04u), nothing: the
    /// hero's "Counts as $80.00 so far" already says it (REFRESH-03).
    private var unsureLine: String? {
        guard split.unsure, split.closedAt != nil else { return nil }
        return "You kept \(Format.amount(split.still ?? split.you)) · nobody owes you"
    }

    /// S-04u / S-46c: what someone has paid, or "Nothing yet"; never "owes".
    private func unsurePerson(_ p: Transaction.Splitting.Person) -> some View {
        let paid = p.paid >= 0.005
        let closed = split.closedAt != nil
        let how = p.links?.last.map { PersonOptionsSheet.word($0) }
        let sub = paid ? "Paid you" + (p.paidOn.map { " · \(Format.short($0))" } ?? "")
            : closed ? "Didn’t pay · that’s fine" : "Nothing yet"
        let spoken = paid ? "\(p.name), paid you \(Format.amount(p.paid))" + (p.paidOn.map { " on \(Format.monthDay($0))" } ?? "")
            : "\(p.name), \(sub)"
        return HStack(spacing: 12) {
            Button { if paid || !closed { options = p } } label: {
                HStack(spacing: 12) {
                    PearlFace(name: p.name, size: 40)
                    VStack(alignment: .leading, spacing: 2) {
                        Text(p.name).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                        Text(sub).font(Pearl.text(.callout)).foregroundColor(paid ? Pearl.moneyIn : Pearl.muted)
                        if paid, let how = how, p.links?.count == 1 {
                            Text(how).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                        }
                        if paid && amountsUnder { paidAmount(p) }
                    }
                    .fixedSize(horizontal: false, vertical: true)
                    Spacer(minLength: 8)
                    if paid && !amountsUnder { paidAmount(p) }
                }
                .frame(minHeight: 44).contentShape(Rectangle())
            }
            .buttonStyle(.plain)
            .accessibilityElement(children: .ignore)
            .accessibilityLabel(spoken)
            .accessibilityAddTraits(.isButton)
            // S-46: people who paid nothing have no ••• once it's closed.
            if paid || !closed {
                PearlMoreButton(label: "Options for \(p.name)") { options = p }
            }
        }
        .padding(.vertical, 10)
    }

    private func paidAmount(_ p: Transaction.Splitting.Person) -> some View {
        Text(Format.amount(p.paid)).font(Pearl.text(.headline, .semibold)).monospacedDigit()
            .foregroundColor(Pearl.moneyIn).pearlAmountFit()
    }

    /// What they still owe (ink); what they paid (money in); what she let go (muted).
    private func owedAmount(_ p: Transaction.Splitting.Person) -> some View {
        Text(Format.amount(p.owes >= 0.005 ? p.owes : p.letGo.map { $0.was - p.paid } ?? p.paid))
            .font(Pearl.text(.headline, .semibold)).monospacedDigit()
            .foregroundColor(p.letGo != nil ? Pearl.muted : p.owes >= 0.005 ? Pearl.ink : Pearl.moneyIn)
            .pearlAmountFit()
    }

    private func person(_ p: Transaction.Splitting.Person) -> some View {
        let full = p.owes < 0.005 && p.letGo == nil && p.paid >= 0.005
        return VStack(spacing: 8) {
            HStack(spacing: 12) {
                Button { options = p } label: {
                    HStack(spacing: 12) {
                        PearlFace(name: p.name, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(p.name).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                            Text((full ? "✓ " : "") + status(p)).font(Pearl.text(.callout))
                                .foregroundColor(full ? Pearl.moneyIn : Pearl.muted)
                            if let line = deposited(p) {
                                Text(line).font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                            }
                            if amountsUnder { owedAmount(p) }
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 8)
                        if !amountsUnder { owedAmount(p) }
                    }
                    .frame(minHeight: 44)
                    .contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(spoken(p))
                .accessibilityHint("Shows options.")
                .accessibilityAddTraits(.isButton)
                PearlMoreButton(label: "Options for \(p.name)") { options = p }
            }
            if p.paid >= 0.005 && p.letGo == nil {
                PaidBar(paid: p.paid, of: p.amount, tone: full ? Pearl.moneyIn : Pearl.action)
                    .accessibilityHidden(true)
            }
        }
        .padding(.vertical, 10)
    }

    /// VoiceOver (S-05v): "Jo, paid back 30 dollars, November 16, part of a
    /// 60 dollar e-Transfer that also paid back Pizza Nova."
    private func spoken(_ p: Transaction.Splitting.Person) -> String {
        // Note 1096:4483: "Priya, owes you 30 dollars."
        if p.owes >= 0.005 && p.paid < 0.005 { return "\(p.name), owes you \(Format.amount(p.owes))" }
        guard p.owes < 0.005, p.letGo == nil, let links = p.links, !links.isEmpty else {
            return [p.name, status(p), Format.amount(p.owes >= 0.005 ? p.owes : p.paid)].joined(separator: ", ")
        }
        let how = links.count == 1 ? links[0].message : "\(links.count) payments"
        let lowered = how.prefix(1).lowercased() + how.dropFirst()
        return [p.name, "paid back \(Format.amount(p.paid))", p.paidOn.map { Format.monthDay($0) }, lowered]
            .compactMap { $0 }.joined(separator: ", ")
    }

    /// S-05u: "$30.00 from an e-Transfer" / "Nov 16 · no name · paid back
    /// Loblaws" / "Who sent this?", with no amount column. Opens S-35c.
    private func uncreditedRow(_ u: Transaction.Splitting.Uncredited) -> some View {
        let from = u.word == "e-Transfer" ? "an e-Transfer" : "a payment"
        return Button { onCredit(u) } label: {
            HStack(spacing: 12) {
                Initials(name: u.name ?? u.word, size: 34)
                VStack(alignment: .leading, spacing: 4) {
                    Text("\(Format.amount(u.amount)) from \(from)").font(Nacre.body).foregroundColor(Pearl.ink)
                    Text("\(Format.short(u.date)) · \(u.sender ?? "no name") · paid back \(Format.andList(u.paidBack))")
                        .font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(2)
                    Text("Who sent this?").font(Nacre.footnote).foregroundColor(Pearl.action)
                }
                Spacer(minLength: 8)
                Image(systemName: "chevron.right").font(.system(size: 13, weight: .semibold))
                    .foregroundColor(Pearl.muted)
            }
            .padding(.horizontal, 16).padding(.vertical, 12)
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        // "30 dollars from an e-Transfer, November 16, not credited to anyone yet. Who sent this? Button."
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(Format.amount(u.amount)) from \(from), \(Format.monthDay(u.date)), not credited to anyone yet. Who sent this?")
        .accessibilityAddTraits(.isButton)
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
        // SPLIT-25 (S-05v): an e-Transfer that also paid back other purchases:
        // "$60.00 · paid back Loblaws and Pizza Nova".
        if let s = p.shared?.first {
            return "\(Format.amount(s.whole)) · paid back \(Format.andList([t.merchant] + s.others))"
        }
        // SPLIT-19 (S-11c, Paying me back): one payment that paid back other
        // purchases too: "$60.00 · paid back Loblaws and Pizza Nova".
        if let pay = p.payments?.last(where: { ($0.paidBack?.count ?? 0) > 1 }), let names = pay.paidBack {
            let back = (pay.givenBack ?? 0) >= 0.005 ? ", \(Format.amount(pay.givenBack ?? 0)) given back" : ""
            return "\(Format.amount(pay.whole ?? pay.amount))\(back) · paid back \(Format.andList(names))"
        }
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
    /// S-44b (REFRESH-02): "Priya paid back $30.00" and the Undo of every
    /// link or payment it saved, newest last.
    var onLinked: ((String, [JSONValue]) -> Void)? = nil

    @Environment(\.dismiss) private var dismiss
    @State private var how = "bank"
    /// S-06ra answered: on to S-06rb, S-06rc or S-06rd.
    @State private var chosen = false
    /// S-06rd's Other…: she types the app.
    @State private var typingApp = false
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
        /// Who sent an e-Transfer, as Cash flow names them (TEST-13).
        let party: String?
        /// TEST-20: "amount" when it's theirs and what they owe, so the
        /// row can say "Amount matches"; nil otherwise.
        var match: String? = nil

        enum CodingKeys: String, CodingKey {
            case id, date, merchant, description, amount, likely, part, party, match
            case accountName = "account_name"
        }

        var name: String {
            if let party = party, !party.isEmpty { return party }
            return (merchant?.isEmpty == false ? merchant : description) ?? "Deposit"
        }
        var whole: Double { abs(amount) }
    }
    @State private var busy = false
    @State private var error: String?

    init(t: Transaction, person: Transaction.Splitting.Person, api: APIClient,
         onUndoable: ((String, JSONValue?) -> Void)? = nil,
         onLinked: ((String, [JSONValue]) -> Void)? = nil, onDone: @escaping (String) -> Void) {
        self.onLinked = onLinked
        self.t = t
        self.person = person
        self.api = api
        self.onDone = onDone
        self.onUndoable = onUndoable
        // SPLIT-C (S-06uc): on Not sure yet the amount is typed, no "of $x".
        _amount = State(initialValue: t.splitting?.unsure == true ? "" : SplitSheet.plain(person.owes))
    }

    /// SPLIT-C: Not sure yet takes any amount, up to what the purchase still
    /// costs her (decision 2); a set split, what they owe.
    private var unsure: Bool { t.splitting?.unsure == true }
    private var limit: Double { unsure ? (t.splitting?.still ?? 0) : person.owes }

    var body: some View {
        if extraPage { extraSheet } else { markSheet }
    }

    // MARK: S-06ra–rd (REFRESH-02): how did they pay, then which payment,
    // cash in hand or another app. Each step has Back and Close.

    @ViewBuilder private var markSheet: some View {
        if !chosen {
            howSheet
        } else if how == "bank" {
            bankSheet
        } else {
            handSheet
        }
    }

    /// S-06ra: "How did Priya pay?"
    private var howSheet: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: person.name, overline: "Mark paid back", title: "How did \(person.name) pay?",
                             sub: unsure ? "Any amount · \(Format.amount(limit)) still counts as yours"
                                 : "\(Format.amount(person.owes)) owed on \(t.merchant)") { dismiss() }
            // REFRESH-03 (S-06ra): three titles; only Cash keeps a line.
            PearlOptionCard {
                PearlOptionRow(symbol: "creditcard", title: "Bank or e-Transfer", prominent: true) {
                    how = "bank"
                    Task { await primary() }
                }
                PearlDivider()
                PearlOptionRow(symbol: "banknote", title: "Cash in hand", sub: "Comes off \(t.merchant) now") {
                    how = "cash"; error = nil; chosen = true
                }
                PearlDivider()
                PearlOptionRow(symbol: "iphone", title: "Another app") {
                    how = "app"; error = nil; chosen = true
                }
            }
            .disabled(busy)
            if busy { ProgressView().frame(maxWidth: .infinity) }
            if let error = error { CautionBanner(text: error) }
        }
    }

    private func back() {
        chosen = false
        finding = false
        error = nil
        query = ""
    }

    /// S-06rb: "Which payment was it?", the likely ones first. More than
    /// one can be ticked when it took several (S-26).
    private var bankSheet: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(overline: "Bank or e-Transfer", title: "Which payment was it?",
                             sub: unsure ? "From \(person.name), any amount" : "From \(person.name), \(Format.amount(person.owes))",
                             back: back) { dismiss() }
            HStack(spacing: 8) {
                Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
                TextField("", text: $query, prompt: Text("Search by name or amount").foregroundColor(Pearl.muted))
                    .font(Pearl.text(.headline)).foregroundColor(Pearl.ink).autocorrectionDisabled()
                    .accessibilityLabel("Search by name or amount")
            }
            .padding(.horizontal, 14).frame(minHeight: 44)
            .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.control))
            .task(id: query) {
                try? await Task.sleep(nanoseconds: 250_000_000)
                if !Task.isCancelled { await search() }
            }
            let searching = !query.trimmingCharacters(in: .whitespaces).isEmpty
            let likely = shown.filter { $0.likely == true }
            let rest = shown.filter { $0.likely != true }
            if shown.isEmpty {
                Text(searching ? "Nothing matches that yet." : "No money in looks like it yet. Search for it above.")
                    .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            } else if searching {
                depositSection("Found", shown)
            } else {
                if !likely.isEmpty { depositSection("Suggested", likely) }
                if !rest.isEmpty { depositSection("Other money in", rest) }
            }
            if inParts && !picked.isEmpty && !unsure {
                VStack(alignment: .leading, spacing: 6) {
                    PaidBar(paid: person.paid + paying, of: person.amount)
                    Text("Paid back \(Format.amount(person.paid + paying)) of \(possessive(person.name)) \(Format.amount(person.amount))")
                        .font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                }
                .accessibilityElement(children: .combine)
            }
            if let error = error { CautionBanner(text: error) }
        } footer: {
            PearlSheetButtons(primary: error != nil ? "Try again" : "Link \(Format.amount(paying))", busy: busy,
                              busyLabel: "Linking…") { Task { await primary() } }
                .disabled(picked.isEmpty)
        }
    }

    private func depositSection(_ title: String, _ rows: [Candidate]) -> some View {
        VStack(alignment: .leading, spacing: 8) {
            PearlSectionLabel(text: title)
            PearlOptionCard {
                ForEach(Array(rows.enumerated()), id: \.element.id) { i, d in
                    if i > 0 { PearlDivider() }
                    depositRow(d)
                }
            }
        }
    }

    /// "e-Transfer · Nov 18 / Priya S. · part of $600   +$30.00  ◉".
    private func depositRow(_ d: Candidate) -> some View {
        let on = picked.contains(d.id)
        let use = uses[d.id]
        let how: String? = use.map { abs($0 - d.whole) < 0.005 ? nil : "part of \(Format.whole(d.whole))" } ?? nil
        let full = !on && limit - paying < 0.005
        return Button {
            if let i = picked.firstIndex(of: d.id) { picked.remove(at: i) } else { picked.append(d.id) }
        } label: {
            HStack(spacing: 12) {
                PearlBubble(symbol: "creditcard", tone: Pearl.moneyIn)
                VStack(alignment: .leading, spacing: 2) {
                    Text("\(d.name) · \(Format.short(d.date))").font(Pearl.text(.headline, .medium))
                        .foregroundColor(Pearl.ink)
                    // TEST-20: "Amount matches" only when it's theirs and it does.
                    let sub = [d.match == "amount" ? "Amount matches" : d.accountName, how].compactMap { $0 }
                    if !sub.isEmpty {
                        Text(sub.joined(separator: " · ")).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                    }
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                Text("+" + Format.amount(use ?? d.whole)).font(Pearl.text(.headline, .semibold)).monospacedDigit()
                    .foregroundColor(Pearl.moneyIn)
                ZStack {
                    Circle().strokeBorder(on ? Pearl.action : Pearl.borderStrong, lineWidth: 1.5)
                    if on {
                        Circle().fill(Pearl.action)
                        Image(systemName: "checkmark").font(.system(size: 11, weight: .bold)).foregroundColor(Pearl.onAction)
                    }
                }
                .frame(width: 24, height: 24)
                .accessibilityHidden(true)
            }
            .padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
            .opacity(full ? 0.5 : 1)
        }
        .buttonStyle(.plain)
        .disabled(full || busy)
        .accessibilityAddTraits(on ? .isSelected : [])
    }

    /// S-06rc cash in hand / S-06rd another app: the amount, when, then Mark
    /// paid back (or the extra, SPLIT-19).
    private var handSheet: some View {
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(overline: how == "app" ? "Another app" : "Cash in hand",
                             title: how == "app" ? "Which app did \(person.name) use?" : "Cash from \(person.name)",
                             back: back) { dismiss() }
            if how == "app" { appChips }
            VStack(spacing: 4) {
                TextField("", text: $amount, prompt: Text(Format.amount(unsure ? 0 : person.owes)).foregroundColor(Pearl.muted))
                    .font(Pearl.display(.largeTitle)).foregroundColor(Pearl.ink)
                    .multilineTextAlignment(.center).keyboardType(.decimalPad)
                    .accessibilityLabel("Amount")
                Text(unsure ? "Any amount, up to the \(Format.amount(limit)) that still counts as yours"
                     : "\(person.name) owes \(Format.amount(person.owes))").font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .padding(.vertical, 18).padding(.horizontal, 16)
            .frame(maxWidth: .infinity)
            .background(RoundedRectangle(cornerRadius: Pearl.radiusTile, style: .continuous).fill(Pearl.card))
            .overlay(RoundedRectangle(cornerRadius: Pearl.radiusTile, style: .continuous).stroke(Pearl.action, lineWidth: 1.5))
            HStack {
                Text("Received").font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Spacer()
                DatePicker("Received", selection: $when, in: ...Date(), displayedComponents: .date)
                    .labelsHidden().tint(Pearl.action)
            }
            .padding(.horizontal, 16).frame(minHeight: 56)
            .pearlCard(radius: Pearl.radiusRow)
            if how == "cash" {
                // S-06rc (REFRESH-03).
                InfoNote(text: "Deposit it later? Pearl won’t count it twice.")
            }
            if overBy >= 0.005 {
                // S-06 v2 (SPLIT-11): more than they owe; S-11c says what. Ink, not red.
                Text("\(Format.amount(overBy)) more than \(person.name) owes. You’ll sort the extra next.")
                    .font(Pearl.text(.callout)).foregroundColor(Pearl.ink)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let error = error { CautionBanner(text: error) }
        } footer: {
            PearlSheetButtons(primary: overBy >= 0.005 ? "Next: the extra \(Format.amount(overBy))"
                                       : "Mark \(Format.amount(typed ?? (unsure ? 0 : person.owes))) paid back",
                              busy: busy, busyLabel: "Saving…") {
                if overBy >= 0.005 {
                    pieces = []
                    extraAmount = ""
                    error = nil
                    extraPage = true
                } else {
                    Task { await primary() }
                }
            }
        }
        .task { await loadApps() }
    }

    /// S-06rd: the apps she named before, then Other… to type one.
    private var appChips: some View {
        VStack(alignment: .leading, spacing: 10) {
            ScrollView(.horizontal, showsIndicators: false) {
                HStack(spacing: 8) {
                    ForEach(usedApps, id: \.self) { a in
                        chip(a, on: !typingApp && a.caseInsensitiveCompare(appName) == .orderedSame) {
                            typingApp = false
                            appName = a
                        }
                    }
                    chip("Other…", on: typingApp || usedApps.isEmpty) {
                        typingApp = true
                        appName = ""
                    }
                }
            }
            if typingApp || usedApps.isEmpty {
                TextField("", text: $appName, prompt: Text("Which app? (optional)").foregroundColor(Pearl.muted))
                    .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                    .textInputAutocapitalization(.words).autocorrectionDisabled()
                    .padding(.horizontal, 14).frame(minHeight: 44)
                    .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.card))
                    .overlay(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).stroke(Pearl.border, lineWidth: 1))
                    .onChange(of: appName) { v in if v.count > 30 { appName = String(v.prefix(30)) } }
                    .accessibilityLabel("Which app")
                    // S-06 v3a (REFRESH-03): the field says "optional"; VoiceOver hears why.
                    .accessibilityHint("Leave it blank and the split reads Paid back · Another app.")
            }
        }
    }

    private func chip(_ title: String, on: Bool, action: @escaping () -> Void) -> some View {
        Button(title, action: action)
            .font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.ink)
            .padding(.horizontal, 16).frame(minHeight: 44)
            .background(Capsule().fill(on ? Pearl.bubble : Pearl.control))
            .overlay(Capsule().stroke(on ? Pearl.action : .clear, lineWidth: 1.5))
            .buttonStyle(.plain)
            .accessibilityAddTraits(on ? .isSelected : [])
    }

    private func loadApps() async {
        struct Reply: Decodable { let apps: [String] }
        if let r: Reply = try? await api.get("api/split/apps") {
            usedApps = r.apps
            if appName.isEmpty, let first = r.apps.first { appName = first }
        }
    }

    /// What each ticked deposit pays of what they owe, in the order ticked:
    /// all of it, or the part that's left (S-26's "part of $600").
    private var uses: [String: Double] {
        var left = limit
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

    /// TEST-20: an e-Transfer that names this person ("Priya Shah" for Priya).
    private func theirs(_ d: Candidate) -> Bool {
        guard let party = d.party?.lowercased(), !party.isEmpty else { return false }
        let name = person.name.lowercased()
        let first = name.split(separator: " ").first.map(String.init) ?? name
        return party == name || party.hasPrefix(name)
            || party.replacingOccurrences(of: ".", with: " ").split(separator: " ").map(String.init).contains(first)
    }

    /// S-26 when it takes more than one deposit (or part of one); S-29,
    /// one payment that looks like theirs, otherwise.
    private var inParts: Bool {
        picked.count > 1 || deposits.contains { abs(min($0.whole, $0.part ?? $0.whole) - limit) >= 0.005 && picked.contains($0.id) }
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

    // MARK: S-11c What's the extra? (SPLIT-19)

    /// What she typed, for cash or an app.
    private var typed: Double? {
        Double(amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: ""))
    }

    /// What they paid over what they owe, for cash or an app.
    private var overBy: Double {
        guard how != "bank", !unsure, let value = typed else { return 0 }
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
            // S-11c (REFRESH-03): the one fact; the tiles say the rest.
            Text("\(person.name) owes \(Format.amount(person.owes)) for \(t.merchant).")
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
        struct Saved: Decodable { let undo: JSONValue?; let toast: String? }
        do {
            if finding {
                let linking = uses
                var undos: [JSONValue] = []
                var said: String?
                for id in picked {
                    guard let use = linking[id], let d = deposits.first(where: { $0.id == id }) else { continue }
                    var body: [String: Any] = ["person": person.name]
                    if use < d.whole - 0.005 { body["amount"] = use }
                    let r: Saved = try await api.post("api/transactions/\(t.id)/paybacks/\(id)", body)
                    if let u = r.undo { undos.append(u) }
                    said = r.toast
                }
                let total = linking.values.reduce(0, +)
                // S-44b: "Priya paid back $30.00".
                let title = picked.count == 1 ? (said ?? "\(person.name) paid back \(Format.amount(total))")
                    : "\(person.name) paid back \(Format.amount(total))"
                if let onLinked = onLinked { onLinked(title, undos) } else { onDone(title) }
            } else if how == "bank" {
                struct Reply: Decodable { let candidates: [Lenient<Candidate>]? }
                // TEST-20: for this person, so their own money leads and
                // nobody else's is suggested or ticked.
                let r: Reply = try await api.get("api/transactions/\(t.id)/paybacks", query: ["person": person.name])
                // Theirs first: deposits that name them, then the rest.
                let first = person.name.split(separator: " ").first.map(String.init)?.lowercased() ?? ""
                deposits = (r.candidates ?? []).compactMap { $0.value }.enumerated().sorted { a, b in
                    let x = a.element.name.lowercased().contains(first), y = b.element.name.lowercased().contains(first)
                    return x != y ? x : a.offset < b.offset
                }.map(\.element)
                // TEST-20: pre-tick only one of theirs that fits.
                picked = deposits.first(where: { $0.likely == true && theirs($0) }).map { [$0.id] } ?? []
                finding = true
                chosen = true
            } else {
                guard let value = Double(amount.replacingOccurrences(of: "$", with: "").replacingOccurrences(of: ",", with: "")),
                      value > 0 else {
                    error = "How much did \(person.name) pay?"
                    return
                }
                if unsure && value > limit + 0.005 {
                    // Decision 2: Σ paid never more than the purchase.
                    error = "Only \(Format.amount(limit)) of \(t.merchant) still counts as yours, so that’s the most it can take."
                    return
                }
                // SPLIT-11: another app is recorded like cash, but never
                // offered as cash a deposit holds.
                var body: [String: Any] = ["name": person.name, "amount": value, "day": Format.isoDay(when),
                                           "via": how == "app" ? "app" : "cash"]
                // SPLIT-14: the app's name, when she gave one.
                let named = appName.trimmingCharacters(in: .whitespaces)
                if how == "app" && !named.isEmpty { body["app"] = named }
                let r: Saved = try await api.post("api/transactions/\(t.id)/split/cash", body)
                let title = "\(person.name) paid back \(Format.amount(value))"
                if let onLinked = onLinked { onLinked(title, r.undo.map { [$0] } ?? []) } else { onDone(title) }
            }
            error = nil
        } catch {
            // S-06r: the champagne banner; nothing was saved past what the server said.
            self.error = how == "bank" && !finding ? "Couldn’t load your money in. Try again."
                : finding ? "Couldn’t link that. Nothing changed. Try again."
                : "Couldn’t save that. Nothing changed. Try again."
        }
    }
}

/// S-08ra "Let Priya’s $30.00 go?" / S-08rb "Let the rest go?" (REFRESH-02,
/// 1091:2527–2686): what they owe becomes hers. While it waits a spinner in
/// the button, both off, no swipe-dismiss (S-08rc); a failure keeps it as it
/// was on the champagne banner (S-08rd).
struct LetGoSheet: View {
    let t: Transaction
    let person: Transaction.Splitting.Person
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed = false

    private static let error = "Couldn’t let that go. Nothing changed. Try again."

    var body: some View {
        let rest = person.paid >= 0.005
        let owes = Format.amount(person.owes)
        let into = (t.category ?? "").isEmpty ? "your spending" : "your spending in \(t.category ?? "")"
        PearlSheet(dismissDisabled: busy) {
            PearlSheetHeader(face: person.name, overline: "Let it go",
                             title: rest ? "Let the rest go?" : "Let \(possessive(person.name)) \(owes) go?",
                             close: onClose)
                .disabled(busy)
            Text(rest ? "\(person.name) paid \(Format.amount(person.paid)). The other \(owes) becomes \(into)."
                      : "\(person.name) won’t owe you anymore. The \(owes) becomes \(into).")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            // Product owner, 2026-11-09 (the payback rule); REFRESH-03 words.
            InfoNote(text: "Your Allowance doesn’t change.")
            if failed { CautionBanner(text: Self.error) }
        } footer: {
            PearlSheetButtons(primary: failed ? "Try again" : "Let \(owes) go", busy: busy, busyLabel: "Letting go…",
                              secondary: "Keep waiting", onPrimary: { Task { await letGo() } }, onSecondary: onClose)
        }
        .interactiveDismissDisabled(busy)
    }

    private func letGo() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = false
        } catch {
            failed = true
        }
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

/// S-03r2 / S-03rg (TEST-08, TEST-16, TEST-28, `split.meter`; section 20
/// note 1266:28323): left to right, in proportion to the purchase with 2 pt
/// gaps, everyone else's shares in color/action/primary, her share (typed or
/// giving way) in color/brand/blush, and what isn't assigned yet on
/// color/surface/track. "I had some too" off has no blush part; over the
/// total, the whole bar is one solid color/action/primary.
struct SplitBar: View {
    /// Everyone else's shares, in cents.
    let others: Int
    /// Her share, typed or giving way, in cents (0 when she isn't in it).
    let mine: Int
    let total: Int

    var body: some View {
        GeometryReader { g in
            let over = others + mine > total
            let whole = Double(max(total, 1))
            let parts: [(Double, Color)] = over ? [(1, Pearl.action)] : [
                (Double(max(others, 0)) / whole, Pearl.action),
                (Double(max(mine, 0)) / whole, Pearl.bubble),
                (Double(max(total - others - mine, 0)) / whole, Pearl.track),
            ].filter { $0.0 > 0.0005 }
            let gaps = CGFloat(max(parts.count - 1, 0)) * 2
            HStack(spacing: 2) {
                ForEach(Array(parts.enumerated()), id: \.offset) { _, p in
                    Capsule().fill(p.1).frame(width: max((g.size.width - gaps) * p.0, 4))
                }
            }
            .frame(width: g.size.width, alignment: .leading)
        }
        .frame(height: 8)
        .accessibilityHidden(true)
    }
}

// MARK: - S-48a / S-48b A payer's share differs (TEST-18b)

/// "Sam paid $20.00 · An even share is $33.33" (S-48a) or "Priya paid
/// $6.67 more" (S-48b): one question, answered with a tap.
struct MismatchSheet: View {
    let name: String
    let paid: Double
    let share: Double
    let even: Bool
    let step: Int
    let of: Int
    /// Who carries the difference if their share is what they paid.
    let others: [String]
    let onBack: () -> Void
    /// S-48e: "Pizza Nova · Priya" when it's asked again after settling.
    var overline: String? = nil
    let onAnswer: (SplitSheet.Answer) -> Void

    private var diff: String { Format.amount(abs(share - paid)) }
    private var kind: String { even ? "An even share" : "Their share" }

    var body: some View {
        PearlSheet {
            PearlSheetHeader(face: name, overline: overline ?? "Settle up · \(step) of \(of)",
                             title: share > paid ? "\(name) paid \(Format.amount(paid))" : "\(name) paid \(diff) more",
                             close: onBack)
            Text(share > paid
                 ? "\(kind) is \(Format.amount(share)). What should \(possessive(name)) share be?"
                 : "\(name) sent \(Format.amount(paid)). \(kind) is \(Format.amount(share)). What’s the extra \(diff)?")
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            PearlOptionCard {
                if share > paid {
                    PearlOptionRow(symbol: "envelope", title: "Ask \(name) for \(diff)",
                                   sub: "\(possessive(name)) share is \(Format.amount(share)) · \(name) owes \(diff)",
                                   prominent: true) { onAnswer(.ask) }
                    PearlDivider()
                    PearlOptionRow(symbol: "person", title: "\(possessive(name)) share is \(Format.amount(paid))",
                                   sub: "The \(diff) is spread over \(Format.andList(others))") { onAnswer(.theirShare) }
                } else {
                    PearlOptionRow(symbol: "arrow.uturn.left", title: "I owe \(name) \(diff)",
                                   sub: "\(possessive(name)) share is \(Format.amount(share)) · shows under You owe",
                                   prominent: true) { onAnswer(.iOwe) }
                    PearlDivider()
                    PearlOptionRow(symbol: "person", title: "\(possessive(name)) share is \(Format.amount(paid))",
                                   sub: "\(Format.andList(others).prefix(1).uppercased() + Format.andList(others).dropFirst()) carry \(diff) less") { onAnswer(.theirShare) }
                    PearlDivider()
                    PearlOptionRow(symbol: "banknote", title: "It’s a gift",
                                   sub: "\(possessive(name)) share is \(Format.amount(share)) · \(diff) is a gift to you") { onAnswer(.gift) }
                }
            }
            InfoNote(text: share > paid ? "Either way, your Allowance doesn’t change now."
                     // S-48b 1249:26540 (TEST-24): a gift lowers it too.
                     : "“I owe \(name)” and “It’s a gift” lower your Allowance by \(diff). “\(possessive(name)) share is \(Format.amount(paid))” doesn’t change it.")
        } footer: {
            Button(overline == nil ? "Back to amounts" : "Keep it as it is", action: onBack)
                .buttonStyle(PearlSecondaryButtonStyle())
                .padding(.horizontal, 16).padding(.top, 8).padding(.bottom, 12)
        }
    }
}

/// TEST-27: How to split's rows with no field, read as one element. A locked
/// payer's row taps anywhere to say why it's locked (S-47f).
private struct TextRow: ViewModifier {
    let on: Bool
    let locked: Bool
    let label: String
    let tap: () -> Void

    func body(content: Content) -> some View {
        if !on {
            content
        } else if locked {
            content
                .contentShape(Rectangle())
                .onTapGesture(perform: tap)
                .accessibilityElement(children: .ignore)
                .accessibilityLabel(label)
                .accessibilityAddTraits(.isButton)
                .accessibilityHint("Says how to change it")
        } else {
            content.accessibilityElement(children: .combine)
        }
    }
}
