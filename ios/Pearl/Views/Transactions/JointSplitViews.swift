import Contacts
import ContactsUI
import SwiftUI
import UIKit

// JOINT-A, JOINT-B and SPLIT-C (product owner, 2026-11-09; Jira pending):
// Design refresh section 12 (1102:4466) and section 13 (1112:6476).
//
// JOINT-A  AM-08p–p7 the people picker (S-17 v2 with a joint header),
//          AM-08x Remove someone, O-09cr setup. S-17j: Split my part's Add
//          someone, joint account holders hidden.
// JOINT-B  S-03j's strip, S-04j's joint card, S-41j Remove the split?,
//          AM-21j Change your share?, AM-08n Not a joint account?
// SPLIT-C  S-03u's explainer, S-04u's card lines, S-45 Settle up, S-46
//          That's everything.
//
// Every sheet is a Pearl view on the iridescent background (no .alert, .confirmationDialog
// or action sheet); spending is ink; 44 pt targets; no new motion yet.

// MARK: - S-17 v2 / AM-08p People picker (JOINT-A)

/// Someone she has split with (GET /api/people/recent).
struct RecentPerson: Decodable, Hashable, Identifiable {
    let name: String
    let merchant: String
    let date: String
    var id: String { name }
}

/// "Sam Lee" and "Sam": the same first name, as the server's split name
/// matcher says (finance/splits.py same_person).
func samePerson(_ a: String, _ b: String) -> Bool {
    func first(_ s: String) -> String {
        s.lowercased().split { !$0.isLetter && !$0.isNumber && $0 != "'" }.first.map(String.init) ?? ""
    }
    let x = first(a), y = first(b)
    return !x.isEmpty && x == y
}

/// The one picker for "who": people she's split with (newest first), her
/// contacts (A to Z, asked for only when it opens, never sent anywhere),
/// and Type a name. Several at once, up to `limit`. Names only.
@MainActor
struct PeoplePicker: View {
    let api: APIClient
    /// "SIMPLII CHEQUING · JOINT", "SPLIT MY PART · PIZZA NOVA".
    let overline: String
    let title: String
    var sub: String? = nil
    /// S-17j: the purchase, so the server leaves its account's holders out.
    var txn: String? = nil
    /// AM-08p4: already on the account, ticked and dimmed.
    var already: [String] = []
    /// Never offered, and refused when typed (S-17j: joint holders).
    var refused: [String] = []
    /// AM-08p4: six on a joint account.
    var limit: Int? = nil
    /// G2b-Picker (rethought, approved 2026-11-18): who a joint account is
    /// shared with. Picked people are chips on top, one Suggested list with
    /// the tick on the left, Type a name only while searching.
    var joint = false
    /// G2b-Account: Remove lives in Edit. With this set, who's on the
    /// account already shows as chips, and a chip's × asks first (AM-08x).
    var onRemoveExisting: ((String) -> Void)? = nil
    let onClose: () -> Void
    /// Saves; a thrown message shows as AM-08p7 with the ticks kept.
    let onAdd: ([String]) async throws -> Void

    enum ContactsState { case asking, on, off }

    @State private var recent: [RecentPerson]?
    @State private var contacts: [String] = []
    @State private var contactsState: ContactsState = .asking
    /// iOS 18 "limited access": Pearl only sees the contacts she chose.
    @State private var contactsLimited = false
    @State private var query = ""
    @State private var picked: [String] = []
    @State private var busy = false
    @State private var failed: String?
    @State private var loadFailed = false
    @FocusState private var searching: Bool

    private var room: Int { limit.map { max(0, $0 - already.count) } ?? Int.max }
    private var full: Bool { picked.count >= room }
    private var q: String { query.trimmingCharacters(in: .whitespaces) }

    var body: some View {
        if joint { jointBody } else { splitBody }
    }

    private var splitBody: some View {
        APSheet(dismissDisabled: busy) {
            // G2-AAddPeople S-17 v2 (rethought, approved 2026-11-18): the title,
            // "Tick as many as you like", FROM YOUR SPLITS and CONTACTS with
            // the tick on the right; Contacts off is one quiet line; the typed
            // name is the one row to tick.
            APSheetHeader(heading: title,
                          // One name (PP-01's Someone new) has no "most" to say.
                          line: full && (limit ?? 0) > 1 ? "Six is the most." : "Tick as many as you like",
                          close: onClose)
                .disabled(busy)
            searchField
            if refusal != nil, let who = refused.first(where: { samePerson($0, q) }) {
                // G2b-SplitCard S-17j: a joint holder is a dimmed row, "Their part is already off".
                APOptionCard {
                    HStack(spacing: 12) {
                        APFace(name: who, size: 40)
                        VStack(alignment: .leading, spacing: 2) {
                            Text(who).font(Nacre.body).foregroundColor(Pearl.ink)
                            Text("Their part is already off").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60)
                    .opacity(0.45)
                    .accessibilityElement(children: .combine)
                    .accessibilityLabel(refusal ?? "")
                }
            }
            if let recent = recent {
                let mine = recent.filter { r in matches(r.name) && !isRefused(r.name) }
                if !mine.isEmpty {
                    APSheetLabel(text: "From your splits")
                    APOptionCard {
                        ForEach(Array(mine.enumerated()), id: \.element.id) { i, r in
                            if i > 0 { APSeparator() }
                            row(r.name, sub: "Last split \(Format.short(r.date))")
                        }
                    }
                }
                contactsSection(recent)
            } else if loadFailed {
                APErrorLine(text: "Couldn’t load the people you’ve split with. You can still type a name.")
            } else {
                skeleton
            }
            typeRow
            if contactsState == .off { contactsOffLine }
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : addLabel, busy: busy, busyLabel: "Adding…") {
                Task { await add() }
            }
            .disabled(names.isEmpty || refusal != nil)
        }
        .task { await load() }
        .onChange(of: picked.count) { n in
            UIAccessibility.post(notification: .announcement, argument: n == 1 ? "1 person picked" : "\(n) people picked")
        }
    }

    // MARK: G2b-Picker (joint)

    private var jointBody: some View {
        APSheet(dismissDisabled: busy) {
            APSheetHeader(heading: title, close: onClose).disabled(busy)
            if !chips.isEmpty { JointChips(names: chips, remove: unchip).disabled(busy) }
            searchField
            if let refusal = refusal { APErrorLine(text: refusal) }
            jointList
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : addLabel, busy: busy, busyLabel: "Adding…") {
                Task { await add() }
            }
            .disabled(names.isEmpty || refusal != nil)
        }
        .task { await load() }
        .onChange(of: picked.count) { n in
            UIAccessibility.post(notification: .announcement, argument: n == 1 ? "1 person picked" : "\(n) people picked")
        }
    }

    /// Who's on it already (in Edit), then who she's picked.
    private var chips: [String] { (onRemoveExisting == nil ? [] : already) + picked }

    private func unchip(_ name: String) {
        if picked.contains(name) { pick(name) } else { onRemoveExisting?(name) }
    }

    /// One list: her splits first ("You split Loblaws"), then her contacts.
    private var suggested: [(name: String, sub: String)] {
        let mine = (recent ?? []).map { (name: $0.name, sub: "You split \($0.merchant)") }
        // Search every contact first, then cap: the cap only trims the
        // browse list, never what she types.
        let others = contactsState == .on
            ? contactMatches(recent ?? []).map { (name: $0, sub: "In your contacts") }
            : []
        return (mine + others).filter { p in
            matches(p.name) && !isRefused(p.name)
                && !(onRemoveExisting != nil && already.contains { samePerson($0, p.name) })
        }
    }

    @ViewBuilder private var jointList: some View {
        let list = suggested
        let typed = !q.isEmpty && !picked.contains(q) && !already.contains { samePerson($0, q) } && !isRefused(q)
        if recent == nil && !loadFailed {
            skeleton
        } else if !q.isEmpty {
            // AM-08p3: matches, and the typed name as one row in the same card.
            APOptionCard {
                ForEach(Array(list.enumerated()), id: \.element.name) { i, p in
                    if i > 0 { APSeparator() }
                    jointRow(p.name, sub: p.sub)
                }
                if typed {
                    if !list.isEmpty { APSeparator() }
                    Button { pick(q); query = "" } label: {
                        HStack(spacing: 12) {
                            Image(systemName: "plus").font(.system(size: 15, weight: .semibold))
                                .foregroundColor(Pearl.action)
                                .frame(width: 28, height: 28).background(Circle().fill(APlus.actionWash))
                            Text("Add “\(q)” as a new name").font(Nacre.body).foregroundColor(Pearl.action)
                            Spacer(minLength: 0)
                        }
                        .padding(.horizontal, 16).frame(minHeight: 52).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .disabled(full)
                    .accessibilityIdentifier("picker-add-typed")
                }
            }
        } else if list.isEmpty {
            // AM-08p5: no one to pick yet.
            Text("Type a name. Only you see it.").font(Nacre.footnote).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity).padding(.top, 4)
        } else {
            APSheetLabel(text: "Suggested")
            APOptionCard {
                ForEach(Array(list.enumerated()), id: \.element.name) { i, p in
                    if i > 0 { APSeparator() }
                    jointRow(p.name, sub: p.sub)
                }
            }
        }
        if contactsState == .on { moreContactsLine }
        if contactsState == .off {
            // AM-08p2: Contacts off is one quiet line.
            HStack {
                Text("Contacts are off for Pearl.").font(Nacre.footnote).foregroundColor(Pearl.muted)
                Spacer(minLength: 8)
                Button("Settings", action: openSettings)
                    .font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote)).foregroundColor(Pearl.link)
                    .buttonStyle(.plain).frame(minHeight: 32)
            }
            .padding(.horizontal, 4)
        }
    }

    /// The tick on the left, the face, the name over its line.
    private func jointRow(_ name: String, sub: String) -> some View {
        let isAlready = already.contains { samePerson($0, name) }
        let on = isAlready || picked.contains(name)
        let dim = isAlready || (!on && full)
        return Button { pick(name) } label: {
            HStack(spacing: 12) {
                APTickBox(on: on)
                APFace(name: name, size: 36)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(isAlready ? "Already shared" : sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .frame(maxWidth: .infinity, alignment: .leading)
            }
            .padding(.horizontal, 16).padding(.vertical, 8).frame(minHeight: 60).contentShape(Rectangle())
            .opacity(dim ? 0.45 : 1)
        }
        .buttonStyle(.plain)
        .disabled(dim || busy)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(isAlready ? "\(name), already shared" : "\(name), \(sub)")
        .accessibilityValue(on ? "selected" : (full ? "dimmed, six people picked already" : "not selected"))
        .accessibilityAddTraits(.isButton)
    }

    private var searchField: some View {
        HStack(spacing: 8) {
            Image(systemName: "magnifyingglass").foregroundColor(Pearl.muted).accessibilityHidden(true)
            TextField("", text: $query, prompt: Text("Search or type a name").foregroundColor(Pearl.muted))
                .font(Pearl.text(.headline)).foregroundColor(Pearl.ink)
                .textInputAutocapitalization(.words).autocorrectionDisabled()
                .focused($searching)
                .submitLabel(.done)
                .onSubmit { if !q.isEmpty && !isRefused(q) { pick(q); query = "" } }
                .accessibilityLabel("Search or type a name")
        }
        .padding(.horizontal, 14).frame(minHeight: 44)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.control))
    }

    /// S-17j (REFRESH-03): "Sam Lee’s part is already off."
    private var refusal: String? {
        guard !q.isEmpty, let who = refused.first(where: { samePerson($0, q) }) else { return nil }
        return "\(possessive(who)) part is already off."
    }

    private func isRefused(_ name: String) -> Bool { refused.contains { samePerson($0, name) } }

    private func matches(_ name: String) -> Bool { q.isEmpty || name.localizedCaseInsensitiveContains(q) }

    @ViewBuilder private func contactsSection(_ recent: [RecentPerson]) -> some View {
        switch contactsState {
        case .asking:
            APSheetLabel(text: "Contacts")
            skeleton
        case .off:
            // S-17 v2: Contacts off is the one quiet line under the list.
            EmptyView()
        case .on:
            // Anyone already in the first list shows once (same name match).
            let shown = contactMatches(recent).filter { !isRefused($0) }
            if !shown.isEmpty {
                APSheetLabel(text: "Contacts")
                APOptionCard {
                    ForEach(Array(shown.enumerated()), id: \.element) { i, name in
                        if i > 0 { APSeparator() }
                        row(name, sub: "Contact")
                    }
                }
            }
            moreContactsLine
        }
    }

    /// Browsing shows the first 60 contacts; searching looks through all of them.
    private static let browseCap = 60

    private func contactMatches(_ recent: [RecentPerson]) -> [String] {
        let all = contacts.filter { c in matches(c) && !recent.contains { samePerson($0.name, c) } }
        return q.isEmpty ? Array(all.prefix(Self.browseCap)) : all
    }

    /// Under the browse list: say that search reaches everyone, and with
    /// iOS's limited access let her share more contacts with Pearl.
    @ViewBuilder private var moreContactsLine: some View {
        if q.isEmpty && contacts.count > Self.browseCap {
            Text("Search to find anyone in your contacts.")
                .font(Nacre.footnote).foregroundColor(Pearl.muted)
                .frame(maxWidth: .infinity, alignment: .leading).padding(.horizontal, 4)
        }
        if contactsLimited, !q.isEmpty {
            if #available(iOS 18.0, *) {
                ContactAccessButton(queryString: q) { _ in Task { await loadContacts() } }
                    .frame(minHeight: 52)
            }
        }
    }

    /// "Contacts are off for Pearl. Turn on" (Settings › Pearl).
    private var contactsOffLine: some View {
        HStack(spacing: 4) {
            Text("Contacts are off for Pearl.").foregroundColor(Pearl.muted)
            Button("Turn on", action: openSettings).foregroundColor(Pearl.link).buttonStyle(.plain)
            Spacer(minLength: 0)
        }
        .font(Nacre.footnote)
        .frame(minHeight: 32)
        .padding(.horizontal, 4)
        .accessibilityElement(children: .combine)
        .accessibilityAction(named: "Turn on in Settings", openSettings)
    }

    /// S-17 v2: while she types a name nobody matches, it is the one row to
    /// tick ("Maya · New name"), and Add above the keyboard adds it.
    @ViewBuilder private var typeRow: some View {
        let typed = !q.isEmpty && !already.contains { samePerson($0, q) } && !isRefused(q)
            && !(recent ?? []).contains { $0.name.caseInsensitiveCompare(q) == .orderedSame }
            && !contacts.contains { $0.caseInsensitiveCompare(q) == .orderedSame }
        if typed {
            let on = picked.contains(q)
            APOptionCard {
                Button { pick(q) } label: {
                    HStack(spacing: 12) {
                        Image(systemName: "plus").font(.system(size: 16, weight: .semibold))
                            .foregroundColor(Pearl.action)
                            .frame(width: 40, height: 40).background(Circle().fill(APlus.actionWash))
                        VStack(alignment: .leading, spacing: 2) {
                            Text(q).font(Nacre.body).foregroundColor(Pearl.ink)
                            Text("New name").font(Nacre.footnote).foregroundColor(Pearl.muted)
                        }
                        Spacer(minLength: 8)
                        tick(on)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 8).frame(minHeight: 60).contentShape(Rectangle())
                }
                .buttonStyle(.plain)
                .disabled(!on && full)
                .accessibilityLabel("\(q), new name")
                .accessibilityValue(on ? "selected" : "not selected")
                .accessibilityIdentifier("picker-typed-name")
            }
        }
    }

    private var skeleton: some View {
        APOptionCard {
            ForEach(0..<3, id: \.self) { i in
                if i > 0 { APSeparator() }
                HStack(spacing: 12) {
                    Circle().fill(Pearl.track).frame(width: 40, height: 40)
                    VStack(alignment: .leading, spacing: 6) {
                        Capsule().fill(Pearl.track).frame(width: 120, height: 12)
                        Capsule().fill(Pearl.track).frame(width: 170, height: 10)
                    }
                    Spacer()
                }
                .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60)
            }
        }
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("Loading")
    }

    /// "Sam Lee, split Pizza Nova November 13, button, not selected."
    private func row(_ name: String, sub: String) -> some View {
        let isAlready = already.contains { samePerson($0, name) }
        let on = isAlready || picked.contains(name)
        let dim = isAlready || (!on && full)
        return Button { pick(name) } label: {
            HStack(alignment: .center, spacing: 12) {
                APFace(name: name, size: 40)
                VStack(alignment: .leading, spacing: 2) {
                    Text(name).font(Nacre.body).foregroundColor(Pearl.ink)
                    Text(isAlready ? "Already shared" : sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
                }
                .fixedSize(horizontal: false, vertical: true)
                Spacer(minLength: 8)
                tick(on)
            }
            .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 60).contentShape(Rectangle())
            .opacity(dim ? 0.45 : 1)
        }
        .buttonStyle(.plain)
        .disabled(dim || busy)
        .accessibilityElement(children: .ignore)
        .accessibilityLabel(isAlready ? "\(name), already shared" : "\(name), \(sub)")
        .accessibilityValue(on ? "selected" : (full ? "dimmed, six people picked already" : "not selected"))
        .accessibilityAddTraits(.isButton)
    }

    /// S-17 v2: the A+ tick box on the right.
    private func tick(_ on: Bool) -> some View {
        APTickBox(on: on)
            .frame(width: 44, height: 44)
            .accessibilityHidden(true)
    }

    private func pick(_ name: String) {
        if let i = picked.firstIndex(of: name) {
            picked.remove(at: i)
        } else if !full {
            picked.append(name)
            UIImpactFeedbackGenerator(style: .light).impactOccurred()
        }
        failed = nil
    }

    /// What Add saves: the ticked ones, or a typed name nobody ticked.
    private var names: [String] {
        if !picked.isEmpty { return picked }
        return !q.isEmpty && !isRefused(q) ? [q] : []
    }

    /// "Add 2 people", "Add Sam Lee".
    private var addLabel: String {
        switch names.count {
        case 0: return "Add"
        case 1: return "Add \(names[0])"
        default: return "Add \(names.count) people"
        }
    }

    private func add() async {
        let list = names
        guard !list.isEmpty else { return }
        busy = true
        defer { busy = false }
        do {
            try await onAdd(list)
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            // AM-08p7: ticks kept.
            failed = joint ? "Couldn’t save. Nothing changed. Try again." : "Couldn’t save. Your picks are kept. Try again."
        }
    }

    private func load() async {
        struct Reply: Decodable { let people: [RecentPerson] }
        do {
            let r: Reply = try await api.get("api/people/recent", query: txn.map { ["txn": $0] } ?? [:])
            recent = r.people
        } catch {
            recent = []
            loadFailed = true
        }
        await loadContacts()
    }

    /// Asked for only now, the first time the picker opens (AM-08p1).
    private func loadContacts() async {
        let store = CNContactStore()
        if CNContactStore.authorizationStatus(for: .contacts) == .notDetermined {
            _ = try? await store.requestAccess(for: .contacts)
        }
        let status = CNContactStore.authorizationStatus(for: .contacts)
        guard status != .denied && status != .restricted && status != .notDetermined else {
            contactsState = .off
            return
        }
        if #available(iOS 18.0, *) { contactsLimited = status == .limited }
        let found: [String] = await Task.detached {
            let keys = [CNContactGivenNameKey, CNContactFamilyNameKey,
                        CNContactNicknameKey, CNContactOrganizationNameKey] as [CNKeyDescriptor]
            var out: [String] = []
            let request = CNContactFetchRequest(keysToFetch: keys)
            request.sortOrder = .givenName
            // Every contact (names only, never sent anywhere). A contact with
            // no first or last name falls back to its nickname, then company.
            try? store.enumerateContacts(with: request) { c, _ in
                var name = "\(c.givenName) \(c.familyName)".trimmingCharacters(in: .whitespaces)
                if name.isEmpty { name = c.nickname.trimmingCharacters(in: .whitespaces) }
                if name.isEmpty { name = c.organizationName.trimmingCharacters(in: .whitespaces) }
                if !name.isEmpty { out.append(name) }
            }
            return out
        }.value
        var seen = Set<String>()
        contacts = found.filter { seen.insert($0.lowercased()).inserted }
            .sorted { $0.localizedCaseInsensitiveCompare($1) == .orderedAscending }
        contactsState = .on
    }

    private func openSettings() {
        // iOS Settings › Pearl, never the web (JOINT-A note 1110:6476).
        if let url = URL(string: UIApplication.openSettingsURLString) { UIApplication.shared.open(url) }
    }
}

/// G2b-Picker: picked people as rose chips (face, name, ×), scrolling sideways.
struct JointChips: View {
    let names: [String]
    let remove: (String) -> Void

    var body: some View {
        ScrollView(.horizontal, showsIndicators: false) {
            HStack(spacing: 8) {
                ForEach(names, id: \.self) { name in
                    Button { remove(name) } label: {
                        HStack(spacing: 6) {
                            Text(APFace.initials(name))
                                .font(.custom("Figtree-Medium", size: 10))
                                .foregroundColor(Pearl.ink)
                                .frame(width: 22, height: 22)
                                .background(Circle().fill(APlus.face))
                            Text(name).font(.custom("Figtree-Medium", size: 13, relativeTo: .footnote))
                                .foregroundColor(Pearl.action).lineLimit(1)
                            Image(systemName: "xmark").font(.system(size: 10, weight: .bold))
                                .foregroundColor(Pearl.action)
                        }
                        .padding(.leading, 4).padding(.trailing, 10).frame(height: 30)
                        .background(Capsule().fill(APlus.actionWash))
                        .padding(.vertical, 7)
                        .contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("Remove \(name)")
                }
            }
        }
    }
}

// MARK: - T-76 Whose was it? (G2b-Whose)

/// G2b-Whose T-76 (rethought, approved 2026-11-18): three tiles that answer
/// at once (Mine, Sam Lee's); only Part of it asks for an amount, in one big
/// well with "of $100.00 was yours" and Save. "Always for Pizza Nova" keeps
/// the answer for the merchant on this account. The same server calls as
/// TransactionDetailView's WhoseSheet, which this replaces once the purchase
/// page opens it (the cash flow engBOT's one-line swap).
struct WhoseTilesSheet: View {
    @Environment(\.dismiss) private var dismiss
    let t: Transaction
    let api: APIClient
    /// What to say, and the server's Undo when there is one.
    let done: (String, JSONValue?) -> Void

    @State private var mode: String
    @State private var part: String
    /// "Always for Pizza Nova" before Mine is tapped, since Mine answers at once.
    @State private var always = false
    @State private var splitAlways: Bool
    @State private var busy = false
    @State private var error: String?
    /// AM-21j for this one purchase: someone has paid on its split.
    @State private var asking: [JointChange]?

    init(t: Transaction, api: APIClient, done: @escaping (String, JSONValue?) -> Void) {
        self.t = t
        self.api = api
        self.done = done
        let mine = t.splitting != nil ? (t.jointPart ?? t.amount) : t.amount
        let start = WhoseAnswer.start(mine: mine, full: t.fullAmount ?? t.amount, shareSet: t.shareSet,
                                      share: t.jointShare)
        _mode = State(initialValue: start.mode)
        _part = State(initialValue: start.part)
        // As WhoseSheet: a part is remembered for the merchant unless it was
        // already a part without a set share.
        _splitAlways = State(initialValue: t.jointShare != nil || start.mode != "part")
    }

    private var full: Double { t.fullAmount ?? t.amount }

    var body: some View {
        PearlSheet(dismissDisabled: busy) {
            APSheetTitle(title: "Whose was it?") { dismiss() }
            WhoseHead(t: t)
            WhoseTiles(theirs: "\(t.joint)’s", mode: mode, busy: busy) { pick($0) }
            if mode == "part" {
                BigAmountWell(text: $part, placeholder: "0.00", label: "Your part", identifier: "whose-part")
                Text("of \(Format.amount(full)) was yours").font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .frame(maxWidth: .infinity)
            } else {
                APCard { APToggleRow(title: "Always for \(t.merchant)", isOn: $always) }.disabled(busy)
            }
            if let error = error { APErrorLine(text: error) }
        } footer: {
            if mode == "part" {
                Button(error == nil ? "Save" : "Try again") { Task { await save() } }
                    .buttonStyle(APPrimaryButtonStyle(busy: busy))
                    .disabled(busy || !WhoseAnswer.ready(mode: mode, typed: part, full: full))
                    .accessibilityIdentifier("whose-save")
            }
        }
        .sheet(isPresented: Binding(get: { asking != nil }, set: { if !$0 { asking = nil } })) {
            if let changes = asking {
                JointChangeSheet(accountName: t.merchant, share: nil, was: nil, holders: [], changes: changes,
                                 purchase: true, onClose: { asking = nil }) {
                    try await send(confirm: true)
                    asking = nil
                }
            }
        }
    }

    private struct Reply: Decodable {
        let rule: String?
        let needsConfirm: Bool?
        let changes: [JointChange]?
        let undo: JSONValue?
        enum CodingKeys: String, CodingKey {
            case rule, changes, undo
            case needsConfirm = "needs_confirm"
        }
    }

    /// Mine or theirs answer on the tap; Part of it waits for Save.
    private func pick(_ answer: String) {
        mode = answer
        error = nil
        guard answer != "part" else { return }
        Task { await save() }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await send(confirm: false)
        } catch {
            self.error = "That didn’t save. Try again."
        }
    }

    private func send(confirm: Bool) async throws {
        var body: [String: Any] = confirm ? ["confirm": true] : [:]
        let amount = WhoseAnswer.amount(part)
        switch mode {
        case "theirs": body["my_share"] = 0
        case "part":
            body["my_share"] = amount ?? 0
            body["always"] = splitAlways
        default: body["my_share"] = NSNull()
        }
        do {
            let reply: Reply = try await api.put("api/transactions/\(t.id)/share", body)
            if reply.needsConfirm == true {
                asking = reply.changes ?? []
                return
            }
            let mineAlways = mode == "mine" && always
            if mineAlways {
                let _: OK = try await api.put("api/transactions/\(t.id)/mine-always", ["on": true])
            }
            let said: String
            switch mode {
            case "theirs": said = "Now \(t.joint)’s"
            case "part": said = reply.rule.flatMap { $0.isEmpty ? nil : $0 } ?? "Your part is \(Format.amount(amount ?? 0))"
            default: said = mineAlways ? "Yours, and every \(t.merchant) from now on" : "Now yours"
            }
            // Undo puts her share back; not "every one from now on", which it can't take back.
            done(said, mineAlways ? nil : reply.undo)
        } catch let e as APIError {
            if case .server = e, confirm { throw SplitMenuError(words: e.localizedDescription) }
            throw e
        }
    }
}

/// "Pizza Nova", "−$100.00 · joint with Sam Lee", its face on the left.
private struct WhoseHead: View {
    let t: Transaction

    var body: some View {
        HStack(spacing: 12) {
            APFace(name: t.merchant, size: 44)
            VStack(alignment: .leading, spacing: 2) {
                Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(2)
                Text("\(Format.money(t)) \u{00B7} joint with \(t.joint)").font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
    }
}

/// Mine · Sam Lee's · Part of it, two to a row.
private struct WhoseTiles: View {
    let theirs: String
    let mode: String
    let busy: Bool
    let pick: (String) -> Void

    var body: some View {
        LazyVGrid(columns: [GridItem(.flexible(), spacing: 10), GridItem(.flexible(), spacing: 10)], spacing: 10) {
            tile("mine", "person", "Mine", "All of it counts")
            tile("theirs", "person.2", theirs, "None of it counts")
            tile("part", "fork.knife", "Part of it", "Say how much")
        }
        .disabled(busy)
    }

    private func tile(_ id: String, _ symbol: String, _ title: String, _ sub: String) -> some View {
        let on = mode == id
        return Button { pick(id) } label: {
            VStack(alignment: .leading, spacing: 2) {
                APIcon(symbol: symbol).padding(.bottom, 8)
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1).minimumScaleFactor(0.8)
                Text(sub).font(Nacre.caption1).foregroundColor(Pearl.muted)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
            .padding(12)
            .apCard()
            .overlay(RoundedRectangle(cornerRadius: Pearl.radiusCard, style: .continuous)
                .strokeBorder(on ? Pearl.action : Color.clear, lineWidth: 1.5))
            .contentShape(Rectangle())
        }
        .buttonStyle(.plain)
        .accessibilityAddTraits(on ? [.isButton, .isSelected] : .isButton)
        .accessibilityIdentifier("whose-\(id)")
    }
}

/// G2b-SplitPart S-03j v2: the header's line for Split my part, which takes
/// the place of JointStrip: "Your part $50.00 of $100.00 · Sam Lee’s $50.00
/// stays theirs". For SplitFlow's header (the splits engBOT's file).
extension Transaction {
    var splitMyPartLine: String {
        let whole = fullAmount ?? amount
        return "Your part \(Format.amount(splitBase)) of \(Format.amount(whole)) \u{00B7} "
            + "\(possessive(jointWho)) \(Format.amount(whole - splitBase)) stays theirs"
    }
}

// MARK: - S-03j's strip and S-04j's card (JOINT-B)

extension Transaction {
    /// JOINT-B: what a split of this purchase splits, her part or all of it.
    var splitBase: Double { splitting?.base ?? jointPart ?? fullAmount ?? amount }

    /// A fixed share (or her answer) takes part of it off: "Split my part".
    /// "All mine unless I mark it" is the usual "Split with others"
    /// (S-01jr2, PO 2026-11-09 (4)).
    var splitsMyPart: Bool {
        !joint.isEmpty && splitBase < (fullAmount ?? amount) - 0.005
    }

    /// "Sam Lee", "Sam Lee and Maya Reyes", or the account's label.
    var jointWho: String {
        jointPeople.isEmpty ? (joint.isEmpty ? "them" : joint) : Format.andList(jointPeople)
    }

    /// "50/50", "60/40", or nil without a set share.
    var jointRatio: String? {
        let whole = fullAmount ?? amount
        guard whole > 0, splitsMyPart else { return nil }
        let mine = Int((splitBase / whole * 100).rounded())
        return "\(mine)/\(100 - mine)"
    }
}

/// S-03j: "Sam Lee’s $50.00 stays theirs · joint 50/50", read only.
struct JointStrip: View {
    let t: Transaction

    var body: some View {
        let theirs = (t.fullAmount ?? t.amount) - t.splitBase
        HStack(spacing: 10) {
            Image(systemName: "person.2").font(.system(size: 16)).foregroundColor(Pearl.action)
                .accessibilityHidden(true)
            Text("\(possessive(t.jointWho)) \(Format.amount(theirs)) stays theirs" + (t.jointRatio.map { " · joint \($0)" } ?? ""))
                .font(Pearl.text(.callout, .medium)).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 0)
        }
        .padding(.horizontal, 14).padding(.vertical, 12)
        .background(RoundedRectangle(cornerRadius: Pearl.radiusChoice, style: .continuous).fill(Pearl.bubble))
        .accessibilityElement(children: .ignore)
        .accessibilityLabel("\(possessive(t.jointWho)) \(Format.amount(theirs)) stays theirs. Joint \(t.jointRatio?.replacingOccurrences(of: "/", with: " ") ?? "").")
    }
}

/// S-04j: JOINT WITH SAM LEE · 50/50, who's on the account (their part,
/// never owed) apart from who owes her.
struct JointPartCard: View {
    let t: Transaction
    let joint: Transaction.Splitting.Joint

    var body: some View {
        VStack(alignment: .leading, spacing: 8) {
            APSheetLabel(text: "Joint with \(t.jointWho)" + (t.jointRatio.map { " · \($0)" } ?? ""))
                .padding(.horizontal, 4).padding(.top, 12)
            APOptionCard {
                ForEach(Array(holders.enumerated()), id: \.offset) { i, h in
                    if i > 0 { APSeparator() }
                    // G2b-SplitCard S-04j: "Their part, on this account".
                    line(face: h.name, title: h.name, sub: "Their part, on this account", amount: h.amount)
                        .accessibilityLabel("\(h.name), on this account, their part, \(Format.amount(h.amount)), not owed to you")
                        // REFRESH-03 (S-04j): the footnote under the card is gone; this row says it.
                        .accessibilityHint("Only the people in your split owe you.")
                }
                APSeparator()
                line(face: "Me", title: "Your part", sub: "Split below", amount: joint.part)
                    .accessibilityLabel("Your part, \(Format.amount(joint.part)), split below")
            }
        }
    }

    /// Each holder's part: the account's other part, shared among them.
    private var holders: [(name: String, amount: Double)] {
        let names = joint.people.isEmpty ? [joint.label] : joint.people
        let cents = Int((joint.theirs * 100).rounded())
        let each = cents / max(names.count, 1)
        return names.enumerated().map { i, n in
            (n, Double(each + (i == 0 ? cents - each * names.count : 0)) / 100)
        }
    }

    private func line(face: String, title: String, sub: String, amount: Double) -> some View {
        HStack(spacing: 12) {
            APFace(name: face, size: 40)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                Text(sub).font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            Text(Format.amount(amount)).font(Pearl.text(.headline)).monospacedDigit().foregroundColor(Pearl.ink)
        }
        .padding(.horizontal, 16).padding(.vertical, 10).frame(minHeight: 56)
        .accessibilityElement(children: .ignore)
    }
}

// MARK: - S-41j Remove the split? (JOINT-B)

/// What removing a joint purchase's split does, then Remove the split /
/// Keep the split. Saving and its error stay on the sheet (S-41j2).
struct RemoveSplitSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    var body: some View {
        APSheet(dismissDisabled: busy) {
            // G2b-RemoveSplit S-41j: the question, then what happens in words:
            // "Your part, $50.00, counts as yours again. Maya Reyes won’t owe you $25.00."
            APSheetHeader(heading: "Remove the split?", close: onClose)
                .disabled(busy)
            Text(sentence).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Remove the split", busy: busy,
                              busyLabel: "Removing…", secondary: "Keep the split",
                              onPrimary: { Task { await remove() } }, onSecondary: onClose)
        }
    }

    private var sentence: String {
        var out = ["Your part, \(Format.amount(split.base ?? t.splitBase)), counts as yours again."]
        for p in split.people {
            if p.paid >= 0.005 {
                out.append("\(possessive(p.name)) \(Format.amount(p.paid)) goes back to sort.")
            } else if split.unsure {
                out.append("\(p.name) is off the split.")
            } else {
                out.append("\(p.name) won’t owe you \(Format.amount(p.owes)).")
            }
        }
        return out.joined(separator: " ")
    }

    private func remove() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t remove the split. Nothing changed. Try again."
        }
    }
}

// MARK: - AM-21j / AM-08n Change your share? (JOINT-B)

/// The server's needs_confirm: each split purchase a change of her part
/// changes, before anything is saved.
struct JointChange: Decodable, Hashable, Identifiable {
    let chargeId: String
    let merchant: String
    let date: String
    let mode: String
    let partWas: Double
    let partNow: Double
    let yoursWas: Double
    let yoursNow: Double
    let people: [Person]
    let paid: Bool
    var id: String { chargeId }

    struct Person: Decodable, Hashable {
        let name: String
        let paid: Double
        let shareWas: Double
        let shareNow: Double
        enum CodingKeys: String, CodingKey {
            case name, paid
            case shareWas = "share_was"
            case shareNow = "share_now"
        }
    }

    enum CodingKeys: String, CodingKey {
        case merchant, date, mode, people, paid
        case chargeId = "charge_id"
        case partWas = "part_was"
        case partNow = "part_now"
        case yoursWas = "yours_was"
        case yoursNow = "yours_now"
    }
}

/// What a joint change answered: saved, or asking first.
struct JointReply: Decodable {
    let ok: Bool?
    let needsConfirm: Bool?
    let notJoint: Bool?
    let changes: [JointChange]?
    let account: AccountsOverview.Account?
    let undo: JSONValue?
    let toast: String?

    enum CodingKeys: String, CodingKey {
        case ok, changes, account, undo, toast
        case needsConfirm = "needs_confirm"
        case notJoint = "not_joint"
    }
}

/// AM-21j "Change your share to 60%?" (someone already paid her back on a
/// split purchase), or AM-08n "Not a joint account?" (her splits stay,
/// people owe the same, her share takes the rest).
struct JointChangeSheet: View {
    let accountName: String
    /// nil: not joint any more (AM-08n).
    let share: Double?
    let was: Double?
    let holders: [String]
    let changes: [JointChange]
    /// Whose was it? on one split purchase ("the same sheet for that one
    /// purchase", note 1110:6504): its part, not the account's share.
    var purchase = false
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var title: String {
        if purchase { return "Change your part to \(Format.amount(changes.first?.partNow ?? 0))?" }
        return share.map { "Change your share to \(Self.pct($0))?" } ?? "Not a joint account?"
    }

    var body: some View {
        APSheet(dismissDisabled: busy) {
            // G2b-Share (AM-21j, AM-08n): the question, one sentence, WHAT
            // CHANGES, each purchase on one line.
            APSheetHeader(heading: title, close: onClose)
                .disabled(busy)
            Text(sentence).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            APSheetLabel(text: "What changes")
            APOptionCard {
                ForEach(Array(changes.enumerated()), id: \.element.id) { i, c in
                    if i > 0 { APSeparator() }
                    HStack(alignment: .center, spacing: 12) {
                        APFace(name: c.merchant, size: 36)
                        VStack(alignment: .leading, spacing: 2) {
                            Text("\(c.merchant) · \(Format.short(c.date))").font(Nacre.body)
                                .foregroundColor(Pearl.ink)
                            Text(line(c)).font(Nacre.footnote).foregroundColor(Pearl.muted).lineLimit(2)
                        }
                        .fixedSize(horizontal: false, vertical: true)
                        Spacer(minLength: 0)
                    }
                    .padding(.horizontal, 16).padding(.vertical, 10)
                    .accessibilityElement(children: .combine)
                }
            }
            if share != nil || purchase {
                Text("Typed amounts stay. Even, % and shares update.")
                    .font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again"
                                  : purchase ? "Change my part"
                                  : share.map { "Change to \(Self.pct($0))" } ?? "Not joint any more",
                              busy: busy, busyLabel: "Saving…",
                              secondary: purchase ? "Keep it as it is" : share == nil ? "Keep it joint"
                                  : was.map { "Keep \(Self.pct($0))" } ?? "Keep it as it is",
                              onPrimary: { Task { await save() } }, onSecondary: onClose)
        }
    }

    /// REFRESH-03 (AM-21j, AM-08n): "Your part $50.00 → $60.00 · Jo owes
    /// $3.34 more", "Your part $20.00 → $24.00", "Your share $16.68 → $66.68".
    private func line(_ c: JointChange) -> String {
        if share == nil && !purchase {
            return "Your share \(Format.amount(c.yoursWas)) → \(Format.amount(c.yoursNow))"
        }
        var bits = ["Your part \(Format.amount(c.partWas)) → \(Format.amount(c.partNow))"]
        for p in c.people where p.paid >= 0.005 {
            let more = p.shareNow - p.paid
            if more >= 0.005 { bits.append("\(p.name) owes \(Format.amount(more)) more") }
            else if more <= -0.005 { bits.append("you owe \(p.name) \(Format.amount(-more))") }
        }
        return bits.joined(separator: " · ")
    }

    static func pct(_ x: Double) -> String { x == x.rounded() ? "\(Int(x))%" : String(format: "%.1f%%", x) }

    /// "Every purchase on it counts as all yours. Sam Lee and Maya Reyes
    /// come off it." or "Someone already paid you back on a split purchase."
    private var sentence: String {
        if share == nil && !purchase {
            let who = holders.isEmpty ? "" : " \(Format.andList(holders)) \(holders.count > 1 ? "come" : "comes") off it."
            return "Every purchase on it counts as all yours." + who
        }
        return "Someone already paid you back on \(purchase ? "this split" : "a split purchase")."
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t save that. Nothing changed. Try again."
        }
    }
}

// MARK: - AM-08x Remove someone from a joint account (JOINT-A)

struct RemoveJointPersonSheet: View {
    let name: String
    let accountName: String
    let others: [String]
    let share: Double?
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var first: String { name.split(separator: " ").first.map(String.init) ?? name }

    var body: some View {
        APSheet(dismissDisabled: busy) {
            // G2b-Account AM-08x (rethought): the question and one sentence.
            APSheetHeader(heading: "Remove \(name)?", close: onClose)
                .disabled(busy)
            Text(sentence).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Remove \(first)", busy: busy, busyLabel: "Removing…",
                              secondary: "Keep \(first)", onPrimary: { Task { await save() } }, onSecondary: onClose)
        }
    }

    /// "Your share stays 50%, and earlier answers stay."
    private var sentence: String {
        let share = share.map { "Your share stays \(JointChangeSheet.pct($0))" } ?? "Your purchases count as they do now"
        return share + ", and earlier answers stay."
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch {
            failed = "Couldn’t remove \(first). Nothing changed. Try again."
        }
    }
}

// MARK: - S-45 Settle up (SPLIT-C)

/// S-45a "How do you want to settle?": PAID SO FAR, then Use what each
/// paid (S-45b confirms) or Type amounts (How to split, S-45c–e).
struct SettleUpSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let onType: () -> Void
    /// S-45b's Settle up; throws to show S-45bx.
    let run: () async throws -> Void
    /// S-45a2 (TEST-18): she isn't in it and one person hasn't paid: that
    /// person owes what's left. Throws to show the Banner.
    var onLeftTo: ((Transaction.Splitting.Person, Double) async throws -> Void)? = nil
    @State private var confirming = false
    @State private var busy = false
    @State private var failed: String?

    private var still: Double { split.still ?? split.you }

    var body: some View {
        APSheet(dismissDisabled: busy) {
            if confirming { confirm } else { choose }
        } footer: {
            if confirming {
                PearlSheetButtons(primary: failed != nil ? "Try again" : "Settle up", busy: busy, busyLabel: "Settling…",
                                  secondary: "Keep it as it is", onPrimary: { Task { await save() } },
                                  onSecondary: { confirming = false; failed = nil })
            }
        }
    }

    /// G2-BSettle S-45a: "Settle up", the purchase with who paid what on one
    /// line, then the ways to settle; each says its amounts.
    @ViewBuilder private var choose: some View {
        APSheetHeader(heading: "Settle up", close: onClose)
        HStack(spacing: 12) {
            APFace(name: t.merchant, size: 44)
            VStack(alignment: .leading, spacing: 2) {
                if split.unsure {
                    Text("NOT SURE YET").font(Nacre.label).tracking(0.78).foregroundColor(Pearl.muted)
                }
                Text(t.merchant).font(Nacre.title2).foregroundColor(Pearl.ink).lineLimit(2)
                Text(paidLine).font(Nacre.footnote).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            .frame(maxWidth: .infinity, alignment: .leading)
        }
        .accessibilityElement(children: .combine)
        if let failed = failed, !confirming { APErrorLine(text: failed) }
        APOptionCard {
            if let last = leftTo, let onLeftTo = onLeftTo {
                // S-45a2 (TEST-18): "Alex owes what's left · $40.00 · Sam and
                // Priya stay at what they paid".
                APOptionRow(symbol: "person", title: "\(last.name) owes what’s left",
                               sub: "\(Format.amount(still)) \u{00B7} \(payersStay)") {
                    Task {
                        busy = true
                        defer { busy = false }
                        do { try await onLeftTo(last, still); failed = nil }
                        catch let e as SplitMenuError { failed = e.words }
                        catch { failed = "Couldn’t settle it. Nothing changed. Try again." }
                    }
                }
                .disabled(busy)
                APSeparator()
            }
            APOptionRow(symbol: "person.2", title: "Use what each paid", sub: eachPaidLine) {
                confirming = true
            }
            APSeparator()
            APOptionRow(symbol: "pencil", title: "Type amounts", sub: "Evenly, amounts, % or shares", action: onType)
        }
        Text("Your Allowance doesn’t change now.").font(Nacre.caption1).foregroundColor(Pearl.muted)
            .frame(maxWidth: .infinity)
    }

    /// G2-BSettle S-45b: one sentence says the result; WHAT CHANGES is the
    /// purchase and Allowance (no change).
    @ViewBuilder private var confirm: some View {
        APSheetHeader(heading: "Use what each paid?", close: onClose)
            .disabled(busy)
        Text(resultSentence).font(Nacre.body).foregroundColor(Pearl.ink)
            .fixedSize(horizontal: false, vertical: true)
        APSheetLabel(text: "What changes")
        APOptionCard {
            changeRow(t.merchant, split.unsure
                      ? "Not sure yet \u{2192} split \(split.people.count + (split.withMe ? 1 : 0)) ways" : "Settled")
            APSeparator()
            changeRow("Allowance \u{00B7} \(Format.monthName(String(t.date.prefix(7))))", "No change")
        }
        if let failed = failed { APErrorLine(text: failed) }
    }

    /// "Sam paid $20.00 · Priya $40.00 · Alex nothing yet".
    private var paidLine: String {
        split.people.enumerated().map { i, p in
            let what = p.paid >= 0.005 ? Format.amount(p.paid) : "nothing yet"
            return i == 0 ? "\(p.name) paid \(what)" : "\(p.name) \(what)"
        }.joined(separator: " \u{00B7} ")
    }

    /// "Sam $20.00 · Priya $40.00 · you $40.00", or "… · the $40.00 stays yours".
    private var eachPaidLine: String {
        let paid = split.people.filter { $0.paid >= 0.005 }.map { "\($0.name) \(Format.amount($0.paid))" }
        let rest = split.withMe ? "you \(Format.amount(still))" : "the \(Format.amount(still)) stays yours"
        return (paid + (still >= 0.005 || split.withMe ? [rest] : [])).joined(separator: " \u{00B7} ")
    }

    /// "Sam and Priya stay at what they paid".
    private var payersStay: String {
        let payers = split.people.filter { $0.paid >= 0.005 }.map(\.name)
        guard !payers.isEmpty else { return "the purchase less what’s been paid back" }
        return "\(Format.andList(payers)) \(payers.count == 1 ? "stays" : "stay") at what they paid"
    }

    /// "Sam’s share becomes $20.00 and Priya’s $40.00. The other $40.00 stays yours."
    private var resultSentence: String {
        let parts = split.people.enumerated().map { i, p in
            i == 0 ? "\(possessive(p.name)) share becomes \(Format.amount(p.paid))"
                   : "\(possessive(p.name)) \(Format.amount(p.paid))"
        }
        var out = Format.andList(parts) + "."
        if still >= 0.005 { out += " The other \(Format.amount(still)) stays yours." }
        return out
    }

    private func changeRow(_ title: String, _ value: String) -> some View {
        HStack(spacing: 12) {
            Text(title).font(Nacre.body).foregroundColor(Pearl.ink).lineLimit(1)
            Spacer(minLength: 8)
            Text(value).font(Nacre.subheadline).foregroundColor(Pearl.muted).lineLimit(1).minimumScaleFactor(0.8)
        }
        .padding(.horizontal, 16).frame(minHeight: 52)
        .accessibilityElement(children: .combine)
    }

    /// S-45a2: the one person left, when she isn't in it.
    private var leftTo: Transaction.Splitting.Person? {
        let unpaid = split.people.filter { $0.paid < 0.005 }
        return !split.withMe && unpaid.count == 1 && still >= 0.005 ? unpaid[0] : nil
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t settle up. Nothing changed. Try again."
        }
    }
}

// MARK: - S-46a That's everything? (SPLIT-C)

struct ThatsEverythingSheet: View {
    let t: Transaction
    let split: Transaction.Splitting
    let onClose: () -> Void
    let run: () async throws -> Void
    @State private var busy = false
    @State private var failed: String?

    private var still: Double { split.still ?? split.you }

    var body: some View {
        let paid = split.people.filter { $0.paid >= 0.005 }
        APSheet(dismissDisabled: busy) {
            // G2-BSettle2 S-46a3 / G2-BRemove S-46as, S-46ax: the question, one
            // sentence, then each person (and You) under WHAT CHANGES.
            APSheetHeader(heading: "That’s everything?", close: onClose)
                .disabled(busy)
            Text(lead(paid)).font(Nacre.body).foregroundColor(Pearl.ink)
                .fixedSize(horizontal: false, vertical: true)
            APSheetLabel(text: "What changes")
            APOptionCard {
                ForEach(Array(split.people.enumerated()), id: \.element.id) { i, p in
                    if i > 0 { APSeparator() }
                    // S-46a v2 (TEST-11): someone who didn't pay has nothing on the right.
                    row(p.name, sub(p, everyone: paid.count == split.people.count),
                        p.paid >= 0.005 ? Format.amount(p.paid) : nil, Pearl.moneyIn)
                }
                if split.withMe {
                    APSeparator()
                    // S-46a3 (TEST-18): your own line.
                    row("You", "Your share · what’s left", Format.amount(still), Pearl.ink)
                }
            }
            if let failed = failed { APErrorLine(text: failed) }
        } footer: {
            PearlSheetButtons(primary: failed != nil ? "Try again" : "Close the split", busy: busy, busyLabel: "Closing…",
                              secondary: "Keep it open", onPrimary: { Task { await close() } }, onSecondary: onClose)
        }
    }

    /// "Everyone has paid. The $17.00 stays yours and nobody owes you." or
    /// "The split closes. The $80.00 stays yours and nobody owes you."
    private func lead(_ paid: [Transaction.Splitting.Person]) -> String {
        // S-04u8 / S-46a3 (TEST-18): everyone has paid.
        let first = !split.people.isEmpty && paid.count == split.people.count ? "Everyone has paid." : "The split closes."
        return "\(first) The \(Format.amount(still)) stays yours and nobody owes you."
    }

    /// "Keeps what they paid", "Paid you $20.00 · keeps it", "Didn’t pay · that’s fine".
    private func sub(_ p: Transaction.Splitting.Person, everyone: Bool) -> String {
        if p.paid < 0.005 { return "Didn’t pay · that’s fine" }
        return everyone ? "Keeps what they paid" : "Paid you \(Format.amount(p.paid)) · keeps it"
    }

    private func row(_ title: String, _ sub: String, _ value: String?, _ tone: Color) -> some View {
        HStack(spacing: 12) {
            APFace(name: title == "You" ? "Me" : title, size: 36)
            VStack(alignment: .leading, spacing: 2) {
                Text(title).font(Nacre.body).foregroundColor(Pearl.ink)
                Text(sub).font(Nacre.footnote).foregroundColor(Pearl.muted)
            }
            .fixedSize(horizontal: false, vertical: true)
            Spacer(minLength: 8)
            if let value = value {
                Text(value).font(Nacre.headline).monospacedDigit().foregroundColor(tone)
            }
        }
        .padding(.horizontal, 16).padding(.vertical, 10)
        .accessibilityElement(children: .combine)
    }

    private func close() async {
        busy = true
        defer { busy = false }
        do {
            try await run()
            failed = nil
        } catch {
            failed = "Couldn’t close the split. Nothing changed. Try again."
        }
    }
}

// MARK: - S-45e What's the extra? when settling (SPLIT-C decision 6)

/// The SPLIT-19 extra step (S-11c) for a settled share below what someone
/// already paid: they overpaid, it pays their share on another purchase, a
/// gift, or she gave it back. One person at a time; nothing is saved until
/// every extra is said, then the split saves with it.
struct SettleExtraSheet: View {
    let api: APIClient
    let merchant: String
    let chargeId: String
    /// Name → how much they paid over their new share.
    let over: [(name: String, amount: Double)]
    let onClose: () -> Void
    /// The pieces for each name, to send as the split's `extra`; throws to show the error.
    let run: ([String: [[String: Any]]]) async throws -> Void

    @State private var at = 0
    @State private var pieces: [String: [[String: Any]]] = [:]
    @State private var choosing = false
    @State private var shares: [MarkPaidSheet.OpenShare] = []
    @State private var ticked: [String: Double] = [:]
    @State private var busy = false
    @State private var failed: String?

    private var who: String { over[min(at, over.count - 1)].name }
    private var whole: Double { over[min(at, over.count - 1)].amount }
    private var left: Double {
        let said = (pieces[who] ?? []).compactMap { $0["amount"] as? Double }.reduce(0, +)
        return max(0, ((whole - said) * 100).rounded() / 100)
    }

    var body: some View {
        APSheet(dismissDisabled: busy) {
            APSheetHeader(face: who, overline: "Settle up · \(merchant)",
                             title: choosing ? "Which of \(possessive(who)) shares?" : "What’s the extra \(Format.amount(left))?",
                             sub: "\(who) already paid you more than their share.",
                             back: choosing ? { choosing = false } : nil, close: onClose)
                .disabled(busy)
            if choosing { shareList } else {
                CaseGrid(cases: CaseTile.cashExtra(who: who, app: false),
                         chosen: Binding(get: { nil }, set: { key in if let key = key { take(key) } }))
                    .disabled(busy)
                Text("\(possessive(who)) share of \(merchant) is set, so the other \(Format.amount(left)) needs saying. Nothing is saved until you do.")
                    .font(Pearl.text(.footnote)).foregroundColor(Pearl.muted)
                    .fixedSize(horizontal: false, vertical: true)
            }
            if let failed = failed { CautionBanner(text: failed) }
        } footer: {
            if choosing {
                PearlSheetButtons(primary: "Next", busy: busy) { takeShares() }
                    .disabled(ticked.isEmpty)
            } else if failed != nil {
                PearlSheetButtons(primary: "Try again", busy: busy, busyLabel: "Saving…") { Task { await save() } }
            }
        }
    }

    private var shareList: some View {
        VStack(alignment: .leading, spacing: 8) {
            if shares.isEmpty {
                Text("\(who) doesn’t owe you on anything else.").font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
            } else {
                APOptionCard {
                    ForEach(Array(shares.enumerated()), id: \.element.id) { i, s in
                        if i > 0 { APSeparator() }
                        let on = ticked[s.id] != nil
                        Button {
                            if on { ticked[s.id] = nil } else {
                                let room = Int((left * 100).rounded()) - ticked.values.map { Int(($0 * 100).rounded()) }.reduce(0, +)
                                if room > 0 { ticked[s.id] = Double(min(Int((s.owes * 100).rounded()), room)) / 100 }
                            }
                        } label: {
                            HStack(spacing: 12) {
                                VStack(alignment: .leading, spacing: 2) {
                                    Text(s.merchant).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                                    Text("Owes \(Format.amount(s.owes)) · \(Format.short(s.date))")
                                        .font(Pearl.text(.callout)).foregroundColor(Pearl.muted)
                                }
                                Spacer(minLength: 8)
                                Text(Format.amount(ticked[s.id] ?? s.owes)).font(Pearl.text(.headline)).monospacedDigit()
                                    .foregroundColor(Pearl.ink)
                                Image(systemName: on ? "checkmark.circle.fill" : "circle").font(.system(size: 22))
                                    .foregroundColor(on ? Pearl.action : Pearl.muted).frame(width: 44, height: 44)
                            }
                            .frame(minHeight: 56).contentShape(Rectangle())
                        }
                        .buttonStyle(.plain)
                        .accessibilityAddTraits(on ? .isSelected : [])
                    }
                }
            }
        }
    }

    private func take(_ key: String) {
        failed = nil
        if key == "payback" {
            Task { await loadShares() }
            return
        }
        pieces[who, default: []].append(["kind": key, "amount": left])
        next()
    }

    private func takeShares() {
        for s in shares {
            guard let use = ticked[s.id], use >= 0.005 else { continue }
            pieces[who, default: []].append(["kind": "payback", "amount": use, "charge": s.charge, "person": s.person])
        }
        ticked = [:]
        choosing = false
        next()
    }

    /// The next person's extra, or save once all of it is said.
    private func next() {
        if left >= 0.005 { return }
        if at + 1 < over.count { at += 1 } else { Task { await save() } }
    }

    /// Their other open shares (Paying me back: S-09 for the extra).
    private func loadShares() async {
        struct Item: Decodable {
            let chargeId: String
            let merchant: String
            let date: String
            let owes: Double
            enum CodingKeys: String, CodingKey { case chargeId = "charge_id"; case merchant, date, owes }
        }
        struct Row: Decodable { let name: String; let items: [Lenient<Item>] }
        struct Reply: Decodable { let owesYou: [Lenient<Row>]; enum CodingKeys: String, CodingKey { case owesYou = "owes_you" } }
        do {
            let r: Reply = try await api.get("api/owed")
            shares = r.owesYou.compactMap(\.value).filter { samePerson($0.name, who) }.flatMap { row in
                row.items.compactMap(\.value).filter { $0.chargeId != chargeId }.map {
                    MarkPaidSheet.OpenShare(charge: $0.chargeId, merchant: $0.merchant, date: $0.date,
                                            person: row.name, owes: $0.owes, theirs: true)
                }
            }
            choosing = true
        } catch {
            failed = "Couldn’t load who owes you. Try again."
        }
    }

    private func save() async {
        busy = true
        defer { busy = false }
        do {
            try await run(pieces)
            failed = nil
        } catch let e as SplitMenuError {
            failed = e.words
        } catch {
            failed = "Couldn’t settle up. Nothing changed. Try again."
        }
    }
}

// MARK: - S-03u's method list at accessibility sizes (SPLIT-C)

/// The five methods in a Pearl list sheet, for when the segments don't fit
/// (note 1120:9270: same pattern as Edit split).
struct SplitMethodSheet: View {
    let modes: [(tag: String, label: String)]
    let chosen: String
    let onPick: (String) -> Void
    let onClose: () -> Void

    var body: some View {
        APSheet {
            APSheetHeader(overline: "How to split", title: "Pick a method", close: onClose)
            APOptionCard {
                ForEach(Array(modes.enumerated()), id: \.element.tag) { i, m in
                    if i > 0 { APSeparator() }
                    Button { onPick(m.tag) } label: {
                        HStack {
                            Text(m.label).font(Pearl.text(.headline, .medium)).foregroundColor(Pearl.ink)
                            Spacer()
                            if m.tag == chosen {
                                Image(systemName: "checkmark").foregroundColor(Pearl.action).accessibilityHidden(true)
                            }
                        }
                        .frame(minHeight: 52).contentShape(Rectangle())
                    }
                    .buttonStyle(.plain)
                    .accessibilityLabel("\(m.label), split method, \(i + 1) of \(modes.count)")
                    .accessibilityAddTraits(m.tag == chosen ? .isSelected : [])
                }
            }
        }
    }
}
